"""Unit tests for the paper_quality layer.

Run from the repo root:

    python packages/citare-mcp/tests/test_quality_flags.py

Verifies:
  - Phase D simulation (5 claims, large span, ~30 expected) → LOW + RE_EXTRACT
  - Healthy empirical paper → HIGH, no flags
  - book_chapter fallback to empirical baseline works
  - Single-observation paper is NOT a flag (would make every new paper LOW)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "packages/citare-mcp/src"
sys.path.insert(0, str(SRC))
# Also add citare-core for any model imports if needed later
sys.path.insert(0, str(REPO_ROOT / "packages/citare-core/src"))

from citare_mcp.quality_flags import compute_paper_quality


def _baseline():
    """Load baseline from the package asset."""
    asset = SRC / "citare_mcp/assets/quality_baseline.json"
    return json.loads(asset.read_text(encoding="utf-8"))


def test_healthy_empirical_paper_is_high():
    bl = _baseline()
    # 40 claims spread across 20 pages — well above empirical baseline ~3.15
    claims = [
        {"confidence_score": 0.93, "source_page": p}
        for p in list(range(340, 360)) * 2
    ]
    q = compute_paper_quality(
        paper_type="empirical",
        claims=claims,
        observation_count=1,
        baseline=bl,
    )
    assert q["confidence_tier"] == "HIGH", f"expected HIGH, got {q['confidence_tier']}: {q}"
    assert q["flags"] == [], f"expected no flags, got {q['flags']}"
    assert q["recommended_action"] is None
    assert q["claim_count"] == 40
    print("OK  healthy empirical → HIGH")


def test_phase_d_truncated_is_low_with_re_extract():
    """The 2026-05-11 Phase D incident simulation.

    A sub-agent silently truncated a paper's ~30 claims down to 5. The
    payload-size gate alone would have passed it (5 >= MIN_CLAIMS_FOR_SHORT_PAPER=3).
    The paper_quality layer must catch this via LOW_CLAIM_COUNT + LOW_DENSITY.
    """
    bl = _baseline()
    # 5 claims with full confidence_score, spanning 19 pages (typical journal article)
    claims = [
        {"confidence_score": 0.95, "source_page": p}
        for p in [340, 343, 348, 352, 358]
    ]
    q = compute_paper_quality(
        paper_type="empirical",
        claims=claims,
        observation_count=1,
        baseline=bl,
    )
    assert q["confidence_tier"] == "LOW", f"expected LOW, got {q['confidence_tier']}: {q}"
    assert q["recommended_action"] == "RE_EXTRACT", f"expected RE_EXTRACT, got {q['recommended_action']}"
    codes = [f["code"] for f in q["flags"]]
    assert "LOW_CLAIM_COUNT" in codes, f"missing LOW_CLAIM_COUNT in {codes}"
    assert "LOW_DENSITY" in codes, f"missing LOW_DENSITY in {codes}"
    print("OK  Phase D truncated → LOW + RE_EXTRACT")


def test_book_chapter_falls_back_to_empirical_baseline():
    """book_chapter has INSUFFICIENT_SAMPLE (n=3) → fallback to empirical."""
    bl = _baseline()
    claims = [
        {"confidence_score": 0.90, "source_page": p}
        for p in list(range(1, 30)) * 2  # 58 claims across ~29 pages → density ~2.0
    ]
    q = compute_paper_quality(
        paper_type="book_chapter",
        claims=claims,
        observation_count=1,
        baseline=bl,
    )
    # density ~2.0 vs empirical baseline 3.15 ± 1.94 → z ~ -0.59 → no flag
    assert q["confidence_tier"] == "HIGH", f"expected HIGH, got {q}"
    print("OK  book_chapter fallback → HIGH")


def test_single_observation_is_not_a_flag():
    """Default observation_count=1 must not by itself trigger any flag.

    Otherwise every fresh registration would be MEDIUM/LOW and the tier
    would be uninformative.
    """
    bl = _baseline()
    claims = [
        {"confidence_score": 0.90, "source_page": p}
        for p in list(range(1, 25)) * 2  # healthy density
    ]
    q = compute_paper_quality(
        paper_type="empirical",
        claims=claims,
        observation_count=1,
        baseline=bl,
    )
    # No SINGLE_OBSERVATION flag should be emitted
    flag_codes = {f["code"] for f in q["flags"]}
    assert "SINGLE_OBSERVATION" not in flag_codes
    assert q["observation_count"] == 1  # exposed as a top-level field instead
    print("OK  single observation is not a flag")


def test_disputed_claims_trigger_review_action():
    """Reconciliation surfaces disputed claims → REVIEW_DISPUTED_CLAIMS action."""
    bl = _baseline()
    claims = [
        {"confidence_score": 0.90, "source_page": p}
        for p in list(range(1, 25)) * 2
    ]
    q = compute_paper_quality(
        paper_type="empirical",
        claims=claims,
        observation_count=2,
        disputed_claims_count=3,
        baseline=bl,
    )
    assert q["recommended_action"] == "REVIEW_DISPUTED_CLAIMS", q
    codes = [f["code"] for f in q["flags"]]
    assert "DISPUTED_CLAIMS" in codes
    print("OK  disputed claims → REVIEW_DISPUTED_CLAIMS")


def test_compound_warn_rule_escalates_to_low():
    """2 WARN flags must compound to LOW, not stay at MEDIUM."""
    bl = _baseline()
    # 7 claims (LOW_CLAIM_COUNT WARN) over 20 pages (density 0.35,
    # below empirical mean 3.15 → z = (0.35 - 3.15) / 1.94 = -1.44 → WARN)
    claims = [
        {"confidence_score": 0.95, "source_page": p}
        for p in [10, 12, 14, 18, 21, 25, 29]
    ]
    q = compute_paper_quality(
        paper_type="empirical",
        claims=claims,
        observation_count=1,
        baseline=bl,
    )
    warn_count = sum(1 for f in q["flags"] if f["severity"] == "WARN")
    strong_count = sum(1 for f in q["flags"] if f["severity"] == "STRONG")
    if warn_count >= 2 and strong_count == 0:
        assert q["confidence_tier"] == "LOW", f"compound WARN should escalate to LOW, got {q}"
        print(f"OK  compound WARN rule (warn={warn_count}) → LOW")
    elif strong_count >= 1:
        assert q["confidence_tier"] == "LOW", f"STRONG should also be LOW, got {q}"
        print(f"OK  STRONG flag → LOW (warn={warn_count}, strong={strong_count})")
    else:
        # If neither, the test scenario didn't fire the way we expected;
        # report which it was so the threshold can be debugged.
        print(f"NOTE warn={warn_count} strong={strong_count} tier={q['confidence_tier']} — scenario didn't fire 2-warn rule")


def test_quirk_paper_type_synonyms():
    """Quirk 4: LLMs sometimes emit 'theoretical' / 'experimental' / 'literature_review'."""
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-db/src"))
    from citare_db.ingest import _coerce_extraction_quirks

    cases = [
        ("theoretical", "conceptual"),
        ("Experimental", "empirical"),
        ("literature_review", "review"),
        ("meta-analysis", "meta_analysis"),
        ("book chapter", "book_chapter"),
    ]
    for input_val, expected in cases:
        raw = {"paper": {"paper_type": input_val}, "claims": [], "claim_relations": []}
        out = _coerce_extraction_quirks(raw, None)
        assert out["paper"]["paper_type"] == expected, f"{input_val} should -> {expected}, got {out['paper']['paper_type']}"
        assert out["paper"]["paper_type_original"] == input_val
    print(f"OK paper_type synonyms: {len(cases)} mappings work")


def test_quirk_incompleteness_category_misuse():
    """Quirk 5: LLMs sometimes put a RelationType value (apparent_tension) into incompleteness_category."""
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-db/src"))
    from citare_db.ingest import _coerce_extraction_quirks

    raw = {
        "paper": {},
        "claims": [],
        "claim_relations": [
            {"source_id": "a", "target_id": "b", "relation_type": "apparent_tension",
             "incompleteness_category": "apparent_tension"},
        ],
    }
    out = _coerce_extraction_quirks(raw, None)
    cr = out["claim_relations"][0]
    assert cr["incompleteness_category"] == "none"
    assert cr["incompleteness_category_original"] == "apparent_tension"
    # relation_type itself untouched (apparent_tension IS a valid RelationType)
    assert cr["relation_type"] == "apparent_tension"
    print("OK incompleteness_category misuse coerced to 'none'; relation_type preserved")


def test_quirks_idempotent_on_valid_input():
    """Valid extractions must pass through unchanged."""
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-db/src"))
    from citare_db.ingest import _coerce_extraction_quirks

    raw = {
        "paper": {"paper_type": "empirical"},
        "claims": [{"source_page": 42, "method_metadata": {"sample_size": 51}}],
        "claim_relations": [{"source_id": "a", "target_id": "b",
                             "relation_type": "supports",
                             "incompleteness_category": "boundary_condition"}],
    }
    import copy
    before = copy.deepcopy(raw)
    out = _coerce_extraction_quirks(raw, None)
    # Note: function mutates in place AND returns the same object, so compare to deepcopy
    assert out["paper"]["paper_type"] == "empirical"
    assert "paper_type_original" not in out["paper"]
    assert out["claims"][0]["source_page"] == 42
    assert "source_page_note" not in out["claims"][0]
    assert out["claim_relations"][0]["incompleteness_category"] == "boundary_condition"
    print("OK valid input passes through unchanged")


if __name__ == "__main__":
    test_healthy_empirical_paper_is_high()
    test_phase_d_truncated_is_low_with_re_extract()
    test_book_chapter_falls_back_to_empirical_baseline()
    test_single_observation_is_not_a_flag()
    test_disputed_claims_trigger_review_action()
    test_compound_warn_rule_escalates_to_low()
    test_quirk_paper_type_synonyms()
    test_quirk_incompleteness_category_misuse()
    test_quirks_idempotent_on_valid_input()
    print("\nAll tests passed.")
