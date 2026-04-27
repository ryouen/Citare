"""Citare MCP server — FastMCP + Streamable HTTP (stateless).

This module is the modern transport for Citare. It mirrors the proven design
of the previous production Citare (FastMCP 2.x with `stateless_http=True`),
which never exhibited the SSE init-race that the bare `mcp.server.sse`
transport in our SDK 1.27 hits under concurrent / reconnect load.

Why a separate module from server.py:
  - server.py wraps the bare `mcp.server.Server` for the legacy /sse path.
  - This module wraps `fastmcp.FastMCP` for /mcp.
  - Both are exposed on the same container during the migration window so
    existing clients on /sse keep working while new clients adopt /mcp.
  - When /sse is fully retired, server.py can be removed and this becomes
    the sole entry point.

The tool *logic* is reused unchanged from the existing helpers
(citare_mcp.queries, citare_mcp.guides, citare_mcp.discovery, citare_db.ingest).
Only the transport binding changes.

Run:
    citare-mcp-fastmcp-http --db /path/to/citare.db --host 0.0.0.0 --port 8767
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from citare_core import Extraction
from citare_db import ingest_extraction
from citare_mcp.discovery import enrich_zero_result
from citare_mcp.guides import get_extraction_prompt as _get_extraction_prompt
from citare_mcp.guides import get_pdf_acquisition_guide as _get_pdf_acquisition_guide
from citare_mcp.instructions import INSTRUCTIONS
from citare_mcp.queries import cite_claim as _cite_claim
from citare_mcp.queries import get_claim_graph as _get_claim_graph
from citare_mcp.queries import search_claims as _search_claims


# --- DB connection helper (one connection per request, closed at end) ------

def _open_conn() -> sqlite3.Connection:
    db_path = Path(os.environ.get("CITARE_DB", "/app/data/citare.db"))
    if not db_path.exists():
        raise FileNotFoundError(f"Citare DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# --- FastMCP instance ------------------------------------------------------

mcp = FastMCP("Citare", instructions=INSTRUCTIONS)


# --- Tool definitions (one wrapper per existing helper) --------------------

@mcp.tool
def search_claims(
    query: str | None = None,
    iv: str | None = None,
    dv: str | None = None,
    doi: str | None = None,
    template_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search for structured academic claims in Citare.

    SEARCH TIPS:
      - Best: by DOI → search_claims(doi="10.1234/example")
      - Good: short "Author Year" → search_claims(query="Edmondson 1999")
      - For specific variables: iv="team_psychological_safety" or dv="team_performance"
      - Avoid long multi-author queries; keep query 2-4 words.

    At least one of query, iv, dv, or doi is required.
    Filter by template_type (DEFINITION/RELATION/EXISTENCE_CLAIM/META_CLAIM).
    Returns up to `limit` results with traffic-light colors and integrity hints.
    On 0 hits returns CrossRef metadata + acquisition guidance for the paper.
    """
    conn = _open_conn()
    try:
        hits = _search_claims(
            conn, query=query, iv=iv, dv=dv, doi=doi,
            template_type=template_type, limit=limit,
        )
        if hits:
            return {"results": hits, "count": len(hits)}
        return {
            "results": [],
            "count": 0,
            **enrich_zero_result(query=query, doi=doi, iv=iv, dv=dv),
        }
    finally:
        conn.close()


@mcp.tool
def cite_claim(claim_id: str, style: str = "apa7") -> dict[str, Any]:
    """Get full citation details for a claim.

    Returns: source_text (verbatim quote), source_page, statistics, method,
    causal_guidance, safe_verbs, paper_reference (APA7/Chicago/Harvard/Vancouver/BibTeX),
    and traffic_light (green/yellow/red cite-safety).
    Get claim_id from search_claims results first.
    """
    conn = _open_conn()
    try:
        return _cite_claim(conn, claim_id, style=style)
    finally:
        conn.close()


@mcp.tool
def get_claim_graph(claim_id: str, depth: int = 1) -> dict[str, Any]:
    """Get the relationship network and integrity warnings for a claim.

    Call this BEFORE reporting any claim to the user. Returns the center claim,
    its mediators/moderators/controls within `depth` hops, and integrity_warnings
    (e.g. "effect_disappears_under_control", "hub_component" — must cite mediator too).
    """
    conn = _open_conn()
    try:
        return _get_claim_graph(conn, claim_id, depth=depth)
    finally:
        conn.close()


@mcp.tool
def get_extraction_prompt() -> dict[str, Any]:
    """Get the locked v0.13g extraction prompt + sub-agent invocation guidance.

    Returns the COMPLETE prompt (~5500 tokens). Pass it VERBATIM to a sub-agent
    along with the PDF — do NOT summarize or modify. The prompt's anti-compression
    rules, hedging-gate, and incompleteness_category definitions are critical for
    correct extraction.
    """
    return _get_extraction_prompt()


@mcp.tool
def get_pdf_acquisition_guide() -> dict[str, Any]:
    """Get the PDF acquisition guide (Stages 0-7).

    Strategies for finding PDFs: local file search → direct OA → CrossRef →
    Unpaywall → web search → site-specific gotchas. Use when search_claims
    returns 0 results and acquisition_guidance.auto_downloadable is false.
    """
    return _get_pdf_acquisition_guide()


@mcp.tool
def register_claims(json_data: str) -> dict[str, Any]:
    """Register an LLM-extracted claim bundle into Citare.

    Input is a JSON string matching the Extraction schema (paper, claims,
    claim_relations, measurement_methods, paper_references). The server
    runs a Pydantic validation + a content quality gate (claims non-empty,
    title present, doi or authors present, source_text >= 10 chars per claim,
    payload size 25 KB <= n <= 200 KB).

    WARNING-not-REJECT semantics for soft issues. Returns paper_id,
    claims_added, claims_updated, warnings, and next_steps.
    """
    return _do_register_claims(json_data)


# --- Internal: register_claims body (same logic as server.py) --------------

def _do_register_claims(json_data: str) -> dict[str, Any]:
    """Validate + ingest an Extraction envelope. Pure function (no MCP types).

    Mirrors server.py's `register_claims` branch verbatim so the legacy /sse
    path and the new /mcp path produce identical responses.
    """
    payload = json.loads(json_data)
    ext = Extraction.model_validate(payload)

    problems: list[str] = []
    warnings_size: list[str] = []

    payload_kb = len(json_data) / 1024
    if payload_kb < 25:
        problems.append(
            f"payload is only {payload_kb:.1f} KB — v0.13g typical is 30-100 KB. "
            "The model almost certainly missed claims. Re-run v0.13g, omit `thinking`/`effort`."
        )
    elif payload_kb > 200:
        warnings_size.append(
            f"payload is {payload_kb:.1f} KB — much larger than the 30-100 KB norm. "
            "Possible over-extraction; review before promoting tier."
        )
    if not ext.claims:
        problems.append("payload has zero claims (v0.13g minimum: 5 empirical, 8 conceptual)")
    if not ext.paper.title or len(ext.paper.title.strip()) < 5:
        problems.append("paper.title missing or too short (<5 chars)")
    if not ext.paper.doi and not ext.paper.authors:
        problems.append("paper has neither doi nor authors — cannot identify the work")
    no_quote = [c.id for c in ext.claims if not (c.source_text and len(c.source_text.strip()) >= 10)]
    if no_quote:
        problems.append(
            f"{len(no_quote)} claim(s) missing source_text: "
            + ", ".join(no_quote[:5]) + ("..." if len(no_quote) > 5 else "")
        )
    if problems:
        return {
            "error": "extraction_quality_gate",
            "detail": "Pydantic validated the JSON shape, but content does not look like a real v0.13g extraction.",
            "problems": problems,
            "see": "Call get_extraction_prompt and re-run with the locked v0.13g prompt verbatim.",
        }

    conn = _open_conn()
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        pre_pid = ext.paper.doi
        pre_count = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (pre_pid or "",)
        ).fetchone()[0] if pre_pid else 0

        report = ingest_extraction(conn, ext)

        post_count = conn.execute(
            "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (report.paper_id,)
        ).fetchone()[0]
        rel_count = conn.execute(
            "SELECT COUNT(*) FROM claim_relations WHERE source_id IN "
            "(SELECT id FROM claims WHERE paper_id = ?) "
            "OR target_id IN (SELECT id FROM claims WHERE paper_id = ?)",
            (report.paper_id, report.paper_id),
        ).fetchone()[0]
    finally:
        conn.close()

    claims_in_payload = len(ext.claims)
    claims_added = max(0, post_count - pre_count)
    claims_updated = max(0, claims_in_payload - claims_added)

    next_steps: list[str] = []
    if report.created_paper:
        next_steps.append(f"New paper registered. Verify: search_claims(doi='{report.paper_id}')")
    else:
        next_steps.append(f"Existing paper updated ({claims_added} new, {claims_updated} updated).")
    if report.potential_duplicate_claims:
        next_steps.append(
            f"{len(report.potential_duplicate_claims)} potential duplicate(s) — "
            "same (iv,dv) seen on existing claims; review with cite_claim."
        )
    if any(w.get("code") == "paper_possible_duplicate" for w in report.warnings):
        next_steps.append(
            "Possible duplicate paper (content_hash match). Not auto-merged; consider paper_equivalence registration."
        )
    for w in warnings_size:
        next_steps.append(f"⚠ {w}")

    return {
        "paper_id": report.paper_id,
        "created_paper": report.created_paper,
        "claims_added": claims_added,
        "claims_updated": claims_updated,
        "claims_total_for_paper": post_count,
        "relations_total_for_paper": rel_count,
        "warnings": report.warnings,
        "potential_duplicate_claims": report.potential_duplicate_claims,
        "next_steps": next_steps,
    }


# --- Entry point -----------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Citare MCP — FastMCP + Streamable HTTP (stateless) transport"
    )
    parser.add_argument(
        "--host", default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Bind host (default 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("MCP_PORT", "8767")),
        help="Bind port (default 8767, distinct from /sse on 8765 during migration)",
    )
    parser.add_argument(
        "--path", default="/mcp",
        help="Mount path under host:port (default /mcp)",
    )
    parser.add_argument(
        "--db", default=os.environ.get("CITARE_DB", "/app/data/citare.db"),
        help="Path to citare.db (default $CITARE_DB or /app/data/citare.db)",
    )
    args = parser.parse_args()

    # Surface the DB path to the per-request _open_conn() helper.
    os.environ["CITARE_DB"] = args.db

    import uvicorn
    app = mcp.http_app(path=args.path, stateless_http=True)
    print(
        f"[fastmcp] Citare on {args.host}:{args.port}{args.path} (stateless_http=True, db={args.db})",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
