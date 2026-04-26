# REST `/api/register` — escape hatch for MCP SSE failures

Added 2026-04-26 in response to MCP Python SDK SSE session-decay bug
that blocks `register_claims` calls from Claude Code clients when the
SSE socket pool retains a dead session_id.

## When to use

Use the MCP `register_claims` tool first. If you get repeated -32602
errors (Invalid request parameters) and you've already done:

  1. `claude mcp remove citare -s user`
  2. `claude mcp add --transport sse citare https://citare.dev/sse`
  3. `/clear` and a fresh chat

…and the call still doesn't reach the server (tail VPS-side docker
logs to confirm — no `[tool]` entry means the call is stuck in the
client's broken socket pool), fall back to this REST endpoint.

The MCP `/sse` path remains the primary surface. This is purely a
fallback for SDK-bug recovery.

## Endpoint

  POST https://citare.dev/api/register
  Content-Type: application/json
  Body: the v0.13g extraction JSON (the same payload you'd pass as
        `json_data` to register_claims)

No auth. Rate-limited at 30 req/min/IP via nginx.

## Example (curl)

  curl -sS -X POST https://citare.dev/api/register \
       -H "Content-Type: application/json" \
       --data-binary @/tmp/citare_pdfs/dai2022_v013g.json

## Validation (matches the MCP path exactly)

The endpoint enforces:

  - **size**: 25 KB ≤ payload ≤ 200 KB (warning above 200 KB,
    rejected with 422 `extraction_quality_gate` below 25 KB)
  - **schema**: full Pydantic Extraction validation; 422
    `schema_validation_failed` on mismatch
  - **content**: claims non-empty, paper.title ≥ 5 chars, paper has
    DOI or authors, every claim has source_text ≥ 10 chars
  - **WARNING-not-REJECT**: soft issues (overwrite, possible
    duplicate paper) land in the response `warnings` field but do
    not block the insert

## Response shape (success)

  {
    "via": "rest",
    "paper_id": "10.48550/arXiv.2104.08696",
    "created_paper": true,
    "claims_added": 28,
    "claims_total_for_paper": 28,
    "warnings": [],
    "potential_duplicate_claims": [],
    "next_steps": ["Verify with: GET /api/search?q=10.48550/arXiv.2104.08696"]
  }

## Response shape (error)

  HTTP 400 — empty/invalid JSON body
    {"error": "empty_body" | "invalid_json", "detail": "..."}

  HTTP 422 — schema validation failed
    {"error": "schema_validation_failed", "detail": "..."}

  HTTP 422 — content quality gate failed
    {"error": "extraction_quality_gate", "problems": [...],
     "see": "Re-run extraction with v0.13g + omit `thinking` and `effort` parameters."}

## Verified working

Bench-tested 2026-04-26 with 3 papers from the local LLM that hit MCP
SSE session decay. All 3 landed cleanly:

  - Dai 2022 (Knowledge Neurons): 28 claims, 14 EXIST
  - Zhang & Nanda 2024 (Activation Patching): 39 claims, 20 EXIST
  - Hanna 2023 (GPT-2 greater-than): 37 claims, 21 EXIST

EXIST counts match the v0.13g × effort=none target of ~16.7/paper from
the R82 grid.
