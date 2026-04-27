"""Single source of truth for the register-time content quality gate.

The gate fires AFTER Pydantic validation. Its job is to catch payloads
that are structurally valid (parseable JSON, schema-correct) but obvious
extraction failures — empty, placeholder-only, missing identifiers, etc.

Three caller paths share this code:
  - server.py (legacy /sse register_claims)
  - fastmcp_server.py (/mcp register_claims)
  - http_server.py (/api/register REST)

Centralising the rules here keeps the three paths from drifting apart.
The parity test in tests/test_failure_mode_docs.py asserts that none of
the three callers reimplement the rules inline.

Design notes:

- Returns (problems, warnings). `problems` triggers a 422 reject;
  `warnings` are surfaced to the client but do not block ingest. The
  exact error envelope is constructed by each caller (MCP TextContent vs
  REST JSONResponse) — only the rule logic is shared.

- The 25 KB / 200 KB size signals were originally proxies for "the model
  missed claims" / "the model over-extracted". The lower bound proved
  too aggressive for legitimately short papers (Watson-Crick 1953,
  Frey 2011 Science). As of 2026-04-28, payload < 25 KB is demoted to
  WARNING when the extraction has >= MIN_CLAIMS_FOR_SHORT_PAPER claims;
  it stays a REJECT only when both the size and the claim count are
  below the floor (i.e. the extraction looks empty AND short).

- All other content rules (claims non-empty, title present, doi-or-
  authors, source_text >= 10 chars per claim) are unchanged.
"""

from __future__ import annotations

from typing import Any


# Below this claim count AND under the size floor → reject (looks empty).
# At-or-above this count and under the size floor → warn (looks like a
# legitimately short paper). v0.13g's prompt asks for >= 5 empirical or
# >= 8 conceptual claims; 3 sits below both as the "definitely too few"
# threshold.
MIN_CLAIMS_FOR_SHORT_PAPER = 3

SIZE_FLOOR_KB = 25
SIZE_CEIL_KB = 200


def evaluate_quality(ext: Any, payload_kb: float) -> tuple[list[str], list[str]]:
    """Return (problems, warnings) for an Extraction object + raw payload size.

    `ext` is a citare_core.Extraction instance (already passed model_validate).

    Caller maps `problems` -> 422 reject, `warnings` -> append to the
    success response's next_steps / warnings field.
    """
    problems: list[str] = []
    warnings: list[str] = []

    claim_count = len(ext.claims) if ext.claims else 0

    # ---- Size signal --------------------------------------------------
    if payload_kb < SIZE_FLOOR_KB:
        if claim_count >= MIN_CLAIMS_FOR_SHORT_PAPER:
            warnings.append(
                f"payload {payload_kb:.1f} KB is below the typical 30-100 KB norm, "
                f"but the {claim_count} claims look structurally complete. Treated as "
                f"a legitimately short paper (e.g. Nature one-pager, short report). "
                f"Registered with this warning so reviewers can confirm."
            )
        else:
            problems.append(
                f"payload is only {payload_kb:.1f} KB AND has only {claim_count} claim(s). "
                f"Both signals point to extraction failure (v0.13g typical: 30-100 KB, "
                f">= {MIN_CLAIMS_FOR_SHORT_PAPER} claims). Re-run the extraction with "
                "the v0.13g prompt and the `thinking`/`effort` parameters omitted."
            )
    elif payload_kb > SIZE_CEIL_KB:
        warnings.append(
            f"payload is {payload_kb:.1f} KB — much larger than the 30-100 KB norm. "
            "Possible over-extraction / hallucination; review before promoting tier."
        )

    # ---- Content rules (unchanged from prior versions) -----------------
    if claim_count == 0:
        problems.append(
            "payload has zero claims (v0.13g minimum: 5 for empirical, 8 for conceptual)"
        )
    if not ext.paper.title or len(ext.paper.title.strip()) < 5:
        problems.append("paper.title missing or too short (<5 chars)")
    if not ext.paper.doi and not ext.paper.authors:
        problems.append("paper has neither doi nor authors — cannot identify the work")

    no_quote = [
        c.id for c in (ext.claims or [])
        if not (c.source_text and len(c.source_text.strip()) >= 10)
    ]
    if no_quote:
        problems.append(
            f"{len(no_quote)} claim(s) missing source_text (Citare requires verbatim quotes "
            f"for citation safety): " + ", ".join(no_quote[:5])
            + ("..." if len(no_quote) > 5 else "")
        )

    return problems, warnings
