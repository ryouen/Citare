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
from citare_mcp.quality_gate import evaluate_quality
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
def audit_papers(dois: list[str]) -> dict[str, Any]:
    """Batch-check Citare registration status and quality for many DOIs.

    Replaces N round-trip search_claims calls when an orchestrator needs to
    check status of many papers (e.g., a 50-reference draft, a 132-paper
    project audit, or the citation list of a literature review).

    Each DOI in the input is checked against the papers table. For registered
    papers, claim_count and `paper_quality` (the same shape as
    register_claims' paper_quality field) are returned so the caller can
    decide whether the entry is trustworthy or warrants RE_EXTRACT.

    Args:
        dois: list of DOIs, up to 200 items per call.

    Returns:
        {
          "results": [
            {"doi": "...", "status": "REGISTERED"|"NOT_REGISTERED",
             "paper_id": <id or null>, "claim_count": <int>,
             "confidence_tier": "HIGH"|"MEDIUM"|"LOW"|null,
             "recommended_action": "RE_EXTRACT"|"ACQUIRE_AND_REGISTER"|null}
          ],
          "summary": {"total": N, "by_tier": {...}, "action_required_count": M}
        }
    """
    if not isinstance(dois, list) or not dois:
        return {"error": "dois must be a non-empty list of strings"}
    if len(dois) > 200:
        return {"error": f"too many DOIs ({len(dois)}); split into batches of <= 200"}

    from citare_mcp.quality_flags import compute_paper_quality_from_db

    conn = _open_conn()
    try:
        results: list[dict[str, Any]] = []
        for doi in dois:
            if not isinstance(doi, str) or not doi.strip():
                results.append({
                    "doi": doi,
                    "status": "NOT_REGISTERED",
                    "paper_id": None,
                    "claim_count": 0,
                    "confidence_tier": None,
                    "recommended_action": "ACQUIRE_AND_REGISTER",
                })
                continue
            doi = doi.strip()
            paper_row = conn.execute(
                "SELECT id FROM papers WHERE id = ? OR id IN "
                "(SELECT paper_id FROM paper_identifiers WHERE identifier_value = ?)",
                (doi, doi),
            ).fetchone()
            if paper_row is None:
                results.append({
                    "doi": doi,
                    "status": "NOT_REGISTERED",
                    "paper_id": None,
                    "claim_count": 0,
                    "confidence_tier": None,
                    "recommended_action": "ACQUIRE_AND_REGISTER",
                })
                continue
            paper_id = paper_row["id"]
            quality = compute_paper_quality_from_db(conn, paper_id)
            results.append({
                "doi": doi,
                "status": "REGISTERED",
                "paper_id": paper_id,
                "claim_count": quality["claim_count"],
                "confidence_tier": quality["confidence_tier"],
                "recommended_action": quality["recommended_action"],
                "flags_count": len(quality["flags"]),
            })
    finally:
        conn.close()

    by_tier: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NOT_REGISTERED": 0}
    action_required = 0
    for r in results:
        if r["status"] == "NOT_REGISTERED":
            by_tier["NOT_REGISTERED"] += 1
        else:
            by_tier[r["confidence_tier"]] = by_tier.get(r["confidence_tier"], 0) + 1
        if r["recommended_action"] is not None:
            action_required += 1

    return {
        "results": results,
        "summary": {
            "total": len(results),
            "by_tier": by_tier,
            "action_required_count": action_required,
        },
    }


@mcp.tool
def report_extraction_failure(
    paper_doi: str,
    stage: str,
    claims_completed: int,
    reason: str,
    partial_extraction_available: bool = False,
) -> dict[str, Any]:
    """Report a structured extraction failure instead of compressing or abandoning silently.

    This is the THIRD OPTION for a sub-agent that has run out of context budget
    mid-extraction. The first two options — silently compressing claims to fit, or
    abandoning the paper with no record — are both anti-patterns that caused the
    2026-05-11 incident in which 47 papers were under-registered.

    Calling this tool:
      - Records the incident with an ID (appended to /app/data/extraction_incidents.jsonl)
      - Returns a structured retry strategy the parent orchestrator can act on
      - Does NOT register any partial claims (all-or-nothing semantics preserved)

    Args:
        paper_doi: the paper that could not be completed
        stage: free-form description of where you stopped (e.g.,
            "extracting_section_4_discussion", "computing_l3_for_claim_17")
        claims_completed: how many claims you successfully drafted before stopping
        reason: free-form description of why (e.g., "context budget exhausted at page 19/30")
        partial_extraction_available: false unless you wrote the partial JSON to disk
            (rarely useful; the orchestrator usually wants a clean retry)

    Returns:
        {"acknowledged": true, "incident_id": "...", "no_partial_registration": true,
         "advice_for_parent": {"retry_strategy_code": "SECTION_FILTERED"|"SMALLER_PAPER"|"NO_RETRY",
                               "retry_parameters": {...}, "estimated_tokens_for_retry": <int>}}
    """
    import datetime
    import os
    import uuid

    incident_id = f"I-{datetime.date.today().isoformat()}-{uuid.uuid4().hex[:6].upper()}"
    record = {
        "incident_id": incident_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "paper_doi": paper_doi,
        "stage": stage,
        "claims_completed": int(claims_completed) if claims_completed is not None else 0,
        "reason": reason,
        "partial_extraction_available": bool(partial_extraction_available),
    }
    log_dir = Path(os.environ.get("CITARE_DB", "/app/data/citare.db")).parent
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "extraction_incidents.jsonl"
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        return {
            "acknowledged": False,
            "error": "incident_log_write_failed",
            "detail": str(e),
        }

    if claims_completed and claims_completed >= 5:
        strategy_code = "SECTION_FILTERED"
        retry_params = {
            "sections_to_extract_next": ["sections_after_" + stage],
            "claims_already_completed": claims_completed,
        }
        estimated_tokens = 50000
    elif claims_completed and claims_completed > 0:
        strategy_code = "SMALLER_PAPER"
        retry_params = {"reduce_context_or_use_higher_capacity_model": True}
        estimated_tokens = 80000
    else:
        strategy_code = "NO_RETRY"
        retry_params = {"investigate_root_cause": True}
        estimated_tokens = 0

    return {
        "acknowledged": True,
        "incident_id": incident_id,
        "no_partial_registration": True,
        "advice_for_parent": {
            "retry_strategy_code": strategy_code,
            "retry_parameters": retry_params,
            "estimated_tokens_for_retry": estimated_tokens,
        },
    }


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
    path and the new /mcp path produce identical responses. The actual
    quality-gate rules live in citare_mcp.quality_gate so all three
    register paths (/sse, /mcp, /api/register) share one source of truth.
    """
    payload = json.loads(json_data)
    ext = Extraction.model_validate(payload)
    payload_kb = len(json_data) / 1024
    problems, warnings_size = evaluate_quality(ext, payload_kb)
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
        from citare_mcp.quality_flags import compute_paper_quality_from_db
        paper_quality = compute_paper_quality_from_db(conn, report.paper_id)
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
        "paper_quality": paper_quality,
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
