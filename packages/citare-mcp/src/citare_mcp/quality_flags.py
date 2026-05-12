"""Paper-level quality flags returned alongside `register_claims` responses.

This module is layered ON TOP of the existing `quality_gate.evaluate_quality`
REJECT/WARN gate. The gate decides whether to accept the payload; this
module decides the resulting paper's `confidence_tier` so downstream LLMs
(citation checkers, audit agents) can reason about whether to trust the
entry without re-extraction.

**Design principle — unambiguous data.** This module returns enums + numbers
ONLY. No natural-language summaries. The calling LLM composes user-facing
wording from the structured fields, eliminating misread risk.

**Why this exists.** On 2026-05-11 a sub-agent silently truncated 30-60
claims down to 4-5 per paper to fit context, registering 47 under-quality
papers. The size-based gate alone passed those payloads because the
existing rule only rejects when payload < 25 KB AND claim_count < 3.
Truncated-but-formally-valid output slipped through. The paper_quality
layer adds a second signal: claim density vs paper_type baseline, plus
mean confidence and a stricter claim-count floor, surfacing a
`RE_EXTRACT` recommendation that orchestrators can act on without
the original failure being silent.

Compound rule: 1 STRONG flag OR 2 WARN flags → `tier=LOW` with
`recommended_action=RE_EXTRACT`. Phase-D-class compression (5 claims
out of expected ~30-60, large source_page span) is detected by the
LOW_CLAIM_COUNT + LOW_DENSITY warn-pair.
"""
from __future__ import annotations

import json
from importlib import resources
from typing import Any

_BASELINE_CACHE: dict | None = None
BASELINE_ASSET = "quality_baseline.json"


def _load_baseline() -> dict:
    global _BASELINE_CACHE
    if _BASELINE_CACHE is None:
        text = resources.files("citare_mcp.assets").joinpath(BASELINE_ASSET).read_text(encoding="utf-8")
        _BASELINE_CACHE = json.loads(text)
    return _BASELINE_CACHE


class FlagCode:
    LOW_CLAIM_COUNT = "LOW_CLAIM_COUNT"
    LOW_MEAN_CONFIDENCE = "LOW_MEAN_CONFIDENCE"
    LOW_DENSITY = "LOW_DENSITY"
    DISPUTED_CLAIMS = "DISPUTED_CLAIMS"


class Severity:
    WARN = "WARN"
    STRONG = "STRONG"


class RecommendedAction:
    NONE = None
    RE_EXTRACT = "RE_EXTRACT"
    ACQUIRE_AND_REGISTER = "ACQUIRE_AND_REGISTER"
    REVIEW_DISPUTED_CLAIMS = "REVIEW_DISPUTED_CLAIMS"
    VERIFY_PDF_IDENTITY = "VERIFY_PDF_IDENTITY"


def compute_paper_quality(
    *,
    paper_type: str | None,
    claims: list[dict],
    observation_count: int = 1,
    disputed_claims_count: int = 0,
    baseline: dict | None = None,
) -> dict:
    """Compute the `paper_quality` block for a register_claims response.

    Args:
        paper_type: from papers.paper_type (e.g., "empirical")
        claims: list of dicts with `confidence_score` and `source_page`
        observation_count: how many distinct extraction runs have produced
            claims for this paper (1 = single observation, the default
            state for a freshly-registered paper). Exposed as a top-level
            field, NOT a flag — single-observation is normal, not a
            problem.
        disputed_claims_count: claims marked DISPUTED by reconciliation
            (0 if multi-extraction consensus model is not yet enabled).
        baseline: result of _load_baseline(); auto-loaded if None.

    Returns:
        Dict with confidence_tier ('HIGH'|'MEDIUM'|'LOW'), observation_count,
        claim_count, flags (list with full numerical context), and
        recommended_action. Calling LLM composes wording from these fields.
    """
    if baseline is None:
        baseline = _load_baseline()

    th = baseline["thresholds"]
    claim_count = len(claims)
    flags: list[dict] = []

    # ---- LOW_CLAIM_COUNT (sanity check, span-independent) ----
    if claim_count < th["claim_count_strong"]:
        flags.append({
            "code": FlagCode.LOW_CLAIM_COUNT,
            "severity": Severity.STRONG,
            "measured": claim_count,
            "threshold": th["claim_count_strong"],
        })
    elif claim_count < th["claim_count_warn"]:
        flags.append({
            "code": FlagCode.LOW_CLAIM_COUNT,
            "severity": Severity.WARN,
            "measured": claim_count,
            "threshold": th["claim_count_warn"],
        })

    # ---- LOW_MEAN_CONFIDENCE ----
    confs = [c.get("confidence_score") for c in claims if c.get("confidence_score") is not None]
    if confs:
        mean_conf = sum(confs) / len(confs)
        if mean_conf < th["mean_conf_strong"]:
            flags.append({
                "code": FlagCode.LOW_MEAN_CONFIDENCE,
                "severity": Severity.STRONG,
                "measured": round(mean_conf, 3),
                "threshold": th["mean_conf_strong"],
            })
        elif mean_conf < th["mean_conf_warn"]:
            flags.append({
                "code": FlagCode.LOW_MEAN_CONFIDENCE,
                "severity": Severity.WARN,
                "measured": round(mean_conf, 3),
                "threshold": th["mean_conf_warn"],
            })

    # ---- LOW_DENSITY (vs paper_type baseline) ----
    # source_page span proxy: max - min + 1. Avoids journal-volume
    # pagination artifact (e.g., Annalen der Physik 1905 = page 921).
    pages = [c.get("source_page") for c in claims if c.get("source_page")]
    if pages and len(pages) >= 2:
        span = max(pages) - min(pages) + 1
        if 1 <= span <= 200:
            density = claim_count / span
            bl = baseline["by_paper_type"].get(paper_type or "")
            if not bl or bl.get("reliability") == "INSUFFICIENT_SAMPLE":
                fallback_key = bl["fallback_to"] if bl else "empirical"
                bl = baseline["by_paper_type"].get(fallback_key)
            if bl and bl["density_stddev"] > 0:
                z = (density - bl["density_mean"]) / bl["density_stddev"]
                if z < th["density_z_strong"]:
                    flags.append({
                        "code": FlagCode.LOW_DENSITY,
                        "severity": Severity.STRONG,
                        "measured": round(density, 3),
                        "baseline_mean": bl["density_mean"],
                        "baseline_stddev": bl["density_stddev"],
                        "baseline_paper_type": paper_type or "fallback",
                        "z_score": round(z, 3),
                        "span_used": span,
                    })
                elif z < th["density_z_warn"]:
                    flags.append({
                        "code": FlagCode.LOW_DENSITY,
                        "severity": Severity.WARN,
                        "measured": round(density, 3),
                        "baseline_mean": bl["density_mean"],
                        "baseline_stddev": bl["density_stddev"],
                        "baseline_paper_type": paper_type or "fallback",
                        "z_score": round(z, 3),
                        "span_used": span,
                    })

    # ---- DISPUTED_CLAIMS (from reconciliation, when available) ----
    if disputed_claims_count > 0:
        flags.append({
            "code": FlagCode.DISPUTED_CLAIMS,
            "severity": Severity.STRONG,
            "measured": disputed_claims_count,
        })

    # ---- Compound tier rule ----
    # 1 STRONG OR 2+ WARN → LOW. 1 WARN → MEDIUM. 0 → HIGH.
    strong_count = sum(1 for f in flags if f["severity"] == Severity.STRONG)
    warn_count = sum(1 for f in flags if f["severity"] == Severity.WARN)
    if strong_count >= 1 or warn_count >= 2:
        tier = "LOW"
    elif warn_count == 1:
        tier = "MEDIUM"
    else:
        tier = "HIGH"

    # ---- Recommended action ----
    if any(f["code"] == FlagCode.DISPUTED_CLAIMS for f in flags):
        action = RecommendedAction.REVIEW_DISPUTED_CLAIMS
    elif tier == "LOW" and claim_count == 0:
        # Skeleton paper — record exists (probably as a reference target) but
        # was never extracted. The right action is acquisition, not re-extraction.
        action = RecommendedAction.ACQUIRE_AND_REGISTER
    elif tier == "LOW":
        action = RecommendedAction.RE_EXTRACT
    else:
        action = RecommendedAction.NONE

    return {
        "confidence_tier": tier,
        "observation_count": observation_count,
        "claim_count": claim_count,
        "flags": flags,
        "recommended_action": action,
    }


def compute_paper_quality_from_db(
    conn: Any,
    paper_id: str,
    *,
    observation_count: int = 1,
    disputed_claims_count: int = 0,
) -> dict:
    """Compute paper_quality from the DB's post-ingest state.

    This is the right entry point for `register_claims` responses: it
    reflects the paper's final state after this submission has merged
    with any prior claims, not just the payload's content. Critical when
    a truncated payload updates an existing well-populated paper — we
    want to flag the resulting paper, not the incoming chunk.

    Args:
        conn: sqlite3.Connection (or compatible) on the citare DB
        paper_id: papers.id of the just-ingested paper
        observation_count: distinct extraction runs (default 1; multi-
            extraction schema will populate this from the `extractions`
            table when it lands)
        disputed_claims_count: from reconciliation (default 0)

    Returns:
        Same shape as compute_paper_quality().
    """
    paper_row = conn.execute(
        "SELECT paper_type FROM papers WHERE id = ?", (paper_id,)
    ).fetchone()
    if paper_row is None:
        return compute_paper_quality(
            paper_type=None,
            claims=[],
            observation_count=observation_count,
            disputed_claims_count=disputed_claims_count,
        )
    paper_type = paper_row[0] if not hasattr(paper_row, "keys") else paper_row["paper_type"]

    claim_rows = conn.execute(
        "SELECT confidence_score, source_page FROM claims WHERE paper_id = ?",
        (paper_id,),
    ).fetchall()
    claims = [
        {
            "confidence_score": (r[0] if not hasattr(r, "keys") else r["confidence_score"]),
            "source_page": (r[1] if not hasattr(r, "keys") else r["source_page"]),
        }
        for r in claim_rows
    ]
    return compute_paper_quality(
        paper_type=paper_type,
        claims=claims,
        observation_count=observation_count,
        disputed_claims_count=disputed_claims_count,
    )
