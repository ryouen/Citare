"""MCP server entry point for Citare.

Exposes the following tools (per ``read_only`` flag):

  Always exposed (read):
    - search_claims(query?, doi?, iv?, dv?, template_type?, limit=20)
    - cite_claim(claim_id)
    - get_claim_graph(claim_id, depth=1)
    - get_extraction_prompt()         — locked v0.13g prompt + sub-agent guide
    - get_pdf_acquisition_guide()     — Stages 0-7 + validation rules

  Exposed only when read_only=False (write):
    - register_claims(json_data)      — ingest an extraction JSON envelope

Run: citare-mcp --db /path/to/citare.db

Environment overrides: CITARE_DB sets the DB path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from citare_core import Extraction
from citare_db import ingest_extraction
from citare_mcp.auth import SCOPE_SERVER_EXTRACT
from citare_mcp.auth_context import current_key
from citare_mcp.instructions import INSTRUCTIONS
from citare_mcp.queries import cite_claim, get_claim_graph, search_claims
from citare_mcp.guides import (
    EXTRACTION_PROMPT_VERSION,
    PDF_ACQUISITION_GUIDE_VERSION,
    get_extraction_prompt,
    get_pdf_acquisition_guide,
)


def _ensure_conn(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Citare DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _make_server(db_path: Path, read_only: bool = False) -> Server:
    """Build the Citare MCP Server instance.

    Args:
        db_path: SQLite DB file path.
        read_only: If True, the ``register_claims`` write tool is filtered out
            of ``list_tools`` and rejected at ``call_tool``. Used for public
            VPS deployments where writes should only happen via local stdio/CI.
    """
    server: Server = Server("citare", instructions=INSTRUCTIONS)

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        tools = [
            Tool(
                name="search_claims",
                description=(
                    "Search claims in the Citare knowledge graph. At least one of "
                    "query, doi, iv, dv, or template_type must be provided. Returns "
                    "a list of claims with source_text, causal_strength, and verification_status."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Free-text search via FTS5 against source_text and l0_concepts "
                                "(snake_case concept keys are normalised to space-separated words "
                                "for tokenizer matching)."
                            ),
                        },
                        "doi": {"type": "string", "description": "Paper DOI"},
                        "iv": {"type": "string", "description": "Independent variable (substring match)"},
                        "dv": {"type": "string", "description": "Dependent variable (substring match)"},
                        "template_type": {
                            "type": "string",
                            "enum": ["DEFINITION", "RELATION", "EXISTENCE_CLAIM", "META_CLAIM"],
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                },
            ),
            Tool(
                name="cite_claim",
                description=(
                    "Return a full citation bundle for one claim by ID. Includes the "
                    "paper's bibliographic info, a formatted reference string (APA7 / "
                    "Chicago / BibTeX), source_text, integrity warnings from related "
                    "claims, and a safe_verbs hint based on the design basis. "
                    "Use this whenever an AI application is about to cite a claim."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "style": {
                            "type": "string",
                            "enum": ["apa7", "chicago", "bibtex"],
                            "default": "apa7",
                            "description": "Citation style for paper.paper_reference. Aliases 'apa' / 'harvard' map to apa7.",
                        },
                    },
                    "required": ["claim_id"],
                },
            ),
            Tool(
                name="get_claim_graph",
                description=(
                    "Return the local neighbourhood of a claim with integrity "
                    "warnings. Use this to check if a claim has mediation, "
                    "moderation, or effect-disappears-under-control warnings "
                    "before citing."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "depth": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                    },
                    "required": ["claim_id"],
                },
            ),
            Tool(
                name="get_extraction_prompt",
                description=(
                    f"Return the locked production extraction prompt ({EXTRACTION_PROMPT_VERSION}) "
                    "with sub-agent invocation guidance. Use this when a paper is not in Citare "
                    "and you need to extract its claims from a PDF. The returned prompt MUST be "
                    "passed verbatim to a separate sub-agent / context — do not summarise or "
                    "reinterpret it. After the sub-agent returns JSON, call register_claims."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_pdf_acquisition_guide",
                description=(
                    f"Return the PDF acquisition playbook ({PDF_ACQUISITION_GUIDE_VERSION}). "
                    "Stages 0-7 cover local file search, direct OA download, CrossRef PDF link, "
                    "Unpaywall, web search, Europe PMC (with PoW warning), and asking the user. "
                    "Includes site-specific gotchas and validation rules."
                ),
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
        if not read_only:
            tools.append(
                Tool(
                    name="register_claims",
                    description=(
                        "Register an LLM-extracted claim bundle into Citare. Input is a "
                        "JSON string matching the Extraction schema (paper, claims, "
                        "claim_relations, measurement_methods, paper_references). "
                        "Quality gate: claims non-empty, paper.title present, paper has "
                        "doi or authors, every claim has source_text >= 10 chars. "
                        "WARNING-not-REJECT semantics for soft issues. "
                        "FALLBACK: if this tool returns -32602 Invalid request parameters, "
                        "that is the Python MCP SDK's SSE init-race, NOT a payload/auth "
                        "problem. POST the raw Extraction body (no json_data wrapper) to "
                        "https://citare.dev/api/register — same DB, same validation, same "
                        "response shape. See docs/REGISTRATION_PATHS.md."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "json_data": {"type": "string", "description": "Extraction JSON envelope as string"}
                        },
                        "required": ["json_data"],
                    },
                )
            )
            tools.append(
                Tool(
                    name="extract_and_register",
                    description=(
                        "Server-side extraction: download/decode a PDF, run the locked "
                        f"production prompt ({EXTRACTION_PROMPT_VERSION}) against Claude "
                        "(server's API key + budget), then register the resulting claims. "
                        "Requires Bearer auth + 'server_extract' scope. Pre-flight checks "
                        "remaining monthly budget; charges actual cost regardless of whether "
                        "the JSON validates. Provide pdf_url OR pdf_base64 (not both)."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pdf_url": {"type": "string", "description": "Public HTTPS URL to a PDF"},
                            "pdf_base64": {"type": "string", "description": "Base64-encoded PDF (when uploading directly)"},
                            "paper_hint": {
                                "type": "object",
                                "description": "Optional. {doi?, title?} — if doi already exists in DB, the call returns immediately without spending the budget.",
                                "properties": {
                                    "doi": {"type": "string"},
                                    "title": {"type": "string"},
                                },
                            },
                        },
                    },
                )
            )
        return tools

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        # Lightweight observability — every tool invocation hits the docker
        # logs so we can see exactly what the client is calling and with
        # what shape, without needing to attach a debugger.
        try:
            arg_summary = {
                k: (f"<{type(v).__name__} len={len(v)}>" if isinstance(v, (str, bytes)) and len(v) > 80
                    else v)
                for k, v in (arguments or {}).items()
            }
        except Exception:
            arg_summary = "<unprintable>"
        print(f"[tool] name={name!r} args={arg_summary}", flush=True)
        conn = _ensure_conn(db_path)
        try:
            if name == "search_claims":
                hits = search_claims(conn, **arguments)
                if hits:
                    result = {"results": hits, "count": len(hits)}
                else:
                    # 0-hit enrichment: probe CrossRef for the identifier (if any),
                    # always return acquisition + registration guidance.
                    from citare_mcp.discovery import enrich_zero_result
                    result = {
                        "results": [],
                        "count": 0,
                        **enrich_zero_result(
                            query=arguments.get("query"),
                            doi=arguments.get("doi"),
                            iv=arguments.get("iv"),
                            dv=arguments.get("dv"),
                        ),
                    }
            elif name == "cite_claim":
                result = cite_claim(
                    conn,
                    arguments["claim_id"],
                    style=arguments.get("style", "apa7"),
                )
            elif name == "get_claim_graph":
                result = get_claim_graph(
                    conn,
                    arguments["claim_id"],
                    depth=arguments.get("depth", 1),
                )
            elif name == "get_extraction_prompt":
                result = get_extraction_prompt()
            elif name == "get_pdf_acquisition_guide":
                result = get_pdf_acquisition_guide()
            elif name == "register_claims":
                if read_only:
                    return [TextContent(type="text", text=json.dumps({"error": "register_claims disabled (read-only mode)"}))]
                payload = json.loads(arguments["json_data"])
                ext = Extraction.model_validate(payload)

                # Single source of truth for the rule logic — the same
                # function powers /mcp and /api/register so all three paths
                # produce identical reject/warn decisions.
                from citare_mcp.quality_gate import evaluate_quality
                _payload_kb = len(arguments["json_data"]) / 1024
                _problems, _warnings = evaluate_quality(ext, _payload_kb)
                if _problems:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "extraction_quality_gate",
                        "detail": "Pydantic validated the JSON shape, but the content does not look like a real v0.13g extraction. Fix the issues below and resubmit.",
                        "problems": _problems,
                        "warnings": _warnings,
                        "see": "Call get_extraction_prompt and re-run with the locked v0.13g prompt verbatim, omitting `thinking` and `effort` parameters.",
                    }, ensure_ascii=False, indent=2))]

                conn.execute("PRAGMA foreign_keys = ON")
                # Snapshot pre-ingest counts for delta reporting
                pre_claims_pid = ext.paper.doi  # may be None — handled below
                pre_count_before = conn.execute(
                    "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (pre_claims_pid or "",)
                ).fetchone()[0] if pre_claims_pid else 0
                report = ingest_extraction(conn, ext)
                # Post-ingest counts (use the resolved paper_id from the report)
                post_count = conn.execute(
                    "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (report.paper_id,)
                ).fetchone()[0]
                rel_count = conn.execute(
                    "SELECT COUNT(*) FROM claim_relations WHERE source_id IN "
                    "(SELECT id FROM claims WHERE paper_id = ?) "
                    "OR target_id IN (SELECT id FROM claims WHERE paper_id = ?)",
                    (report.paper_id, report.paper_id),
                ).fetchone()[0]
                claims_in_payload = len(ext.claims)
                claims_added = max(0, post_count - pre_count_before)
                claims_updated = max(0, claims_in_payload - claims_added)
                next_steps = []
                if report.created_paper:
                    next_steps.append(
                        f"New paper registered. Verify with: search_claims(doi='{report.paper_id}')"
                    )
                else:
                    next_steps.append(
                        f"Existing paper updated ({claims_added} new, {claims_updated} updated)."
                    )
                if report.potential_duplicate_claims:
                    next_steps.append(
                        f"{len(report.potential_duplicate_claims)} potential duplicate(s) — same (iv,dv) seen on existing claims; review with cite_claim."
                    )
                if any(w.get("code") == "paper_possible_duplicate" for w in report.warnings):
                    next_steps.append(
                        "Possible duplicate paper detected (content_hash match). Not auto-merged; consider paper_equivalence registration."
                    )
                # Surface size-sanity warnings that didn't block ingest
                for w in _warnings:
                    next_steps.append(f"⚠ {w}")
                result = {
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
            elif name == "extract_and_register":
                if read_only:
                    return [TextContent(type="text", text=json.dumps({"error": "extract_and_register disabled (read-only mode)"}))]
                # Lazy imports — extractor pulls in anthropic SDK, only needed
                # when the admin container actually serves this tool.
                from citare_mcp.extractor import extract_pdf
                from citare_mcp.pdf_fetcher import resolve_pdf_input, PdfFetchError
                from citare_mcp.auth import KeyRegistry

                # ---- 1. Auth + scope ---------------------------------
                key = current_key.get()
                if key is None:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "auth_required",
                        "detail": "extract_and_register requires Bearer auth. Connect via /admin/sse with a key issued by the operator.",
                    }))]
                if not key.has_scope(SCOPE_SERVER_EXTRACT):
                    return [TextContent(type="text", text=json.dumps({
                        "error": "scope_denied",
                        "required_scope": SCOPE_SERVER_EXTRACT,
                        "your_scopes": key.scopes,
                        "detail": "Ask the operator to grant 'server_extract' on your key.",
                    }))]

                # ---- 2. Pre-flight: budget ---------------------------
                # We refuse before fetching the PDF if the budget is tight,
                # so we don't waste bandwidth on a doomed call.
                BUDGET_FLOOR_USD = 2.00
                if key.remaining_budget_usd() < BUDGET_FLOOR_USD:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "budget_exhausted",
                        "remaining_budget_usd": round(key.remaining_budget_usd(), 4),
                        "spent_this_month_usd": round(key.spent_this_month_usd, 4),
                        "monthly_budget_usd": key.monthly_budget_usd,
                        "detail": (
                            f"At least ${BUDGET_FLOOR_USD:.2f} required to attempt one extraction. "
                            "Ask the operator to raise your budget."
                        ),
                    }))]

                # ---- 3. Pre-flight: dedup against existing papers ---
                paper_hint = arguments.get("paper_hint") or {}
                hint_doi = (paper_hint.get("doi") or "").strip() or None
                if hint_doi:
                    existing = conn.execute(
                        "SELECT id, canonical_title FROM papers WHERE id = ? LIMIT 1",
                        (hint_doi,),
                    ).fetchone()
                    if existing is None:
                        existing = conn.execute(
                            "SELECT papers.id, papers.canonical_title FROM paper_identifiers "
                            "JOIN papers ON papers.id = paper_identifiers.paper_id "
                            "WHERE paper_identifiers.identifier_value = ? LIMIT 1",
                            (hint_doi,),
                        ).fetchone()
                    if existing:
                        return [TextContent(type="text", text=json.dumps({
                            "status": "already_exists",
                            "paper_id": existing["id"],
                            "title": existing["canonical_title"],
                            "cost_usd": 0.0,
                            "detail": "Paper already in Citare. No extraction performed; budget unaffected.",
                            "next_steps": [f"search_claims(doi={existing['id']!r}) to inspect existing claims."],
                        }, ensure_ascii=False, indent=2))]

                # ---- 4. Fetch / decode PDF --------------------------
                try:
                    pdf_bytes, source_label = resolve_pdf_input(
                        pdf_url=arguments.get("pdf_url"),
                        pdf_base64=arguments.get("pdf_base64"),
                    )
                except PdfFetchError as e:
                    return [TextContent(type="text", text=json.dumps({
                        "error": "pdf_input_failed", "detail": str(e),
                    }))]

                # ---- 5. Extract via Claude API ----------------------
                # Cost is charged whether the extraction succeeded or failed
                # at the Pydantic / quality-gate layer — the API call already
                # happened and the tokens were billed.
                try:
                    extraction_result = extract_pdf(
                        pdf_bytes,
                        pdf_filename=(paper_hint.get("title") or "paper.pdf"),
                        user_hint=paper_hint.get("title"),
                    )
                except Exception as e:  # noqa: BLE001 — network/API errors handled below
                    return [TextContent(type="text", text=json.dumps({
                        "error": "extraction_api_failed",
                        "detail": f"{type(e).__name__}: {e}",
                        "cost_usd": 0.0,
                        "note": "API call did not complete — no charge applied.",
                    }, ensure_ascii=False))]

                # ---- 6. Charge the budget ---------------------------
                registry_path = os.environ.get("CITARE_KEY_REGISTRY")
                charged = True
                budget_remaining = key.remaining_budget_usd() - extraction_result.cost_usd
                if registry_path:
                    registry = KeyRegistry(registry_path)
                    ok, budget_remaining = registry.charge(key.key, extraction_result.cost_usd)
                    if not ok:
                        # Rare: budget exhausted between pre-flight and now
                        # (concurrent calls). The API already cost us money;
                        # we still ingest, but flag the overage.
                        charged = False

                ext = extraction_result.extraction
                # ---- 7. Quality gate (same as register_claims) ------
                _problems: list[str] = []
                if not ext.claims:
                    _problems.append("model returned zero claims")
                if not ext.paper.title or len(ext.paper.title.strip()) < 5:
                    _problems.append("paper.title missing or too short")
                if not ext.paper.doi and not ext.paper.authors:
                    _problems.append("paper has neither doi nor authors")
                _no_quote = [c.id for c in ext.claims if not (c.source_text and len(c.source_text.strip()) >= 10)]
                if _no_quote:
                    _problems.append(f"{len(_no_quote)} claim(s) missing source_text")
                if _problems:
                    # Charge applied; ingest skipped. Caller can re-attempt
                    # later (e.g., with a cleaner PDF) but should know the
                    # extraction was paid for.
                    return [TextContent(type="text", text=json.dumps({
                        "error": "extraction_quality_gate",
                        "detail": "Model returned JSON, but it failed minimum-content checks.",
                        "problems": _problems,
                        "cost_usd": round(extraction_result.cost_usd, 4),
                        "budget_remaining_usd": round(max(0.0, budget_remaining), 4),
                        "charged": charged,
                    }, ensure_ascii=False, indent=2))]

                # ---- 8. Ingest --------------------------------------
                conn.execute("PRAGMA foreign_keys = ON")
                pre_count = (
                    conn.execute("SELECT COUNT(*) FROM claims WHERE paper_id = ?", (ext.paper.doi or "",)).fetchone()[0]
                    if ext.paper.doi else 0
                )
                report = ingest_extraction(conn, ext)
                post_count = conn.execute(
                    "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (report.paper_id,)
                ).fetchone()[0]
                claims_added = max(0, post_count - pre_count)

                result = {
                    "status": "registered",
                    "paper_id": report.paper_id,
                    "created_paper": report.created_paper,
                    "claims_added": claims_added,
                    "claims_total_for_paper": post_count,
                    "warnings": report.warnings,
                    "potential_duplicate_claims": report.potential_duplicate_claims,
                    "extraction": {
                        "model": extraction_result.model,
                        "prompt_version": EXTRACTION_PROMPT_VERSION,
                        "input_tokens": extraction_result.input_tokens,
                        "output_tokens": extraction_result.output_tokens,
                        "cache_creation_input_tokens": extraction_result.cache_creation_input_tokens,
                        "cache_read_input_tokens": extraction_result.cache_read_input_tokens,
                        "stop_reason": extraction_result.stop_reason,
                        "source": source_label,
                    },
                    "cost_usd": round(extraction_result.cost_usd, 4),
                    "budget_remaining_usd": round(max(0.0, budget_remaining), 4),
                    "charged": charged,
                    "next_steps": [
                        f"search_claims(doi={report.paper_id!r}) to verify the new entries.",
                    ],
                }
            else:
                return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        finally:
            conn.close()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server


async def _run(db_path: Path) -> None:
    server = _make_server(db_path)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    p = argparse.ArgumentParser(description="Citare MCP server (stdio)")
    p.add_argument("--db", default=os.environ.get("CITARE_DB", "citare.db"), help="Path to SQLite DB")
    args = p.parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Citare DB not found at {db_path}. Run the ingest script first.")
    asyncio.run(_run(db_path))


if __name__ == "__main__":
    main()
