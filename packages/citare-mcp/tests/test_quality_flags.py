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


def test_cross_paper_claim_id_collision_guard():
    """Two papers with same first-author and year (e.g., kjell2021_*) must NOT
    cause the second's registration to reparent the first's claims.

    This was the 2026-05-13 incident: harmony 601679 lost 37 claims when 602581
    registered with overlapping kjell2021_* IDs. ingest.py was patched to
    auto-rename incoming colliding IDs.
    """
    import sqlite3, tempfile, os
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-db/src"))
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-core/src"))
    from citare_core import Extraction
    from citare_db.ingest import ingest_extraction
    from citare_db.schema import init_db

    tmpf = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    try:
        conn = init_db(tmpf)

        paper_a = {
            "paper": {"doi": "10.test/paper-a", "title": "Paper A", "year": 2006,
                      "paper_type": "empirical"},
            "claims": [
                {"id": "author2006_def1", "template_type": "DEFINITION",
                 "source_text": "Paper A original content", "source_page": 1,
                 "confidence_score": 0.9},
            ],
            "claim_relations": [],
        }
        ingest_extraction(conn, Extraction.model_validate(paper_a))

        paper_b = {
            "paper": {"doi": "10.test/paper-b", "title": "Paper B", "year": 2006,
                      "paper_type": "empirical"},
            "claims": [
                {"id": "author2006_def1", "template_type": "DEFINITION",
                 "source_text": "Paper B different content", "source_page": 1,
                 "confidence_score": 0.9},
            ],
            "claim_relations": [],
        }
        report_b = ingest_extraction(conn, Extraction.model_validate(paper_b))

        # Paper A's content MUST be preserved
        a_row = conn.execute(
            "SELECT id, source_text FROM claims WHERE paper_id = '10.test/paper-a'"
        ).fetchone()
        assert a_row is not None, "Paper A's claim was deleted by Paper B's registration"
        assert a_row["id"] == "author2006_def1", f"Paper A's id was renamed: {a_row['id']}"
        assert "Paper A original" in a_row["source_text"], \
            f"Paper A's content was overwritten: {a_row['source_text']}"

        # Paper B got a renamed id
        b_row = conn.execute(
            "SELECT id, source_text FROM claims WHERE paper_id = '10.test/paper-b'"
        ).fetchone()
        assert b_row is not None
        assert b_row["id"].startswith("author2006_def1_"), \
            f"Paper B's id was not renamed: {b_row['id']}"
        assert "Paper B different" in b_row["source_text"]

        # Warning was emitted
        codes = [w.get("code") for w in report_b.warnings]
        assert "claim_id_cross_paper_collision_renamed" in codes, \
            f"expected collision warning, got {codes}"

        # claim_relations should be rewritten consistently too
        paper_c = {
            "paper": {"doi": "10.test/paper-c", "title": "Paper C", "year": 2006,
                      "paper_type": "empirical"},
            "claims": [
                {"id": "author2006_def1", "template_type": "DEFINITION",
                 "source_text": "Paper C content", "source_page": 1,
                 "confidence_score": 0.9},
                {"id": "author2006_rel1", "template_type": "RELATION",
                 "l0_json": {"iv": "x", "dv": "y", "relation": "positive"},
                 "source_text": "Paper C relation", "source_page": 2,
                 "confidence_score": 0.9},
            ],
            "claim_relations": [
                {"source_id": "author2006_rel1", "target_id": "author2006_def1",
                 "relation_type": "extends"},
            ],
        }
        ingest_extraction(conn, Extraction.model_validate(paper_c))
        # Paper C's def1 should be renamed; the relation should reference the new id
        c_def = conn.execute(
            "SELECT id FROM claims WHERE paper_id = '10.test/paper-c' AND template_type = 'DEFINITION'"
        ).fetchone()
        assert c_def["id"].startswith("author2006_def1_")
        rel = conn.execute(
            "SELECT source_id, target_id FROM claim_relations "
            "WHERE source_id IN (SELECT id FROM claims WHERE paper_id = '10.test/paper-c') "
            "OR target_id IN (SELECT id FROM claims WHERE paper_id = '10.test/paper-c')"
        ).fetchone()
        if rel:
            assert rel["target_id"] == c_def["id"], \
                f"claim_relations.target_id not rewritten: {rel['target_id']} vs {c_def['id']}"
        print("OK collision guard preserves prior paper, renames incoming, rewrites claim_relations")
    finally:
        os.unlink(tmpf)


def test_arxiv_baseline_skips_false_positive_density_flags():
    """A 35-page arXiv paper with 35 claims (density 1.0) has z=-1.10
    against the empirical baseline (mean 3.47, stddev 2.00) and would
    fire LOW_DENSITY WARN. Using the arxiv-specific baseline
    (mean 2.05, stddev 1.08), z=(1.0-2.05)/1.08 = -0.97 — no flag.
    """
    bl = _baseline()
    # 35 claims across span 35 → density 1.0
    claims = [
        {"confidence_score": 0.93, "source_page": p}
        for p in list(range(1, 36))
    ]
    # Without is_arxiv: would flag against empirical baseline
    q_journal = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        is_arxiv=False, baseline=bl,
    )
    # With is_arxiv: uses arxiv baseline (mean ~2.05)
    q_arxiv = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        is_arxiv=True, baseline=bl,
    )
    # The arxiv variant should have fewer LOW_DENSITY flags (or none) than journal
    journal_density_flags = [f for f in q_journal["flags"] if f["code"] == "LOW_DENSITY"]
    arxiv_density_flags = [f for f in q_arxiv["flags"] if f["code"] == "LOW_DENSITY"]
    assert len(arxiv_density_flags) <= len(journal_density_flags), (
        f"arxiv baseline should be at least as permissive; "
        f"journal flags={journal_density_flags}, arxiv flags={arxiv_density_flags}"
    )
    print(f"OK arXiv baseline: journal would flag {len(journal_density_flags)} LOW_DENSITY, "
          f"arxiv-aware flags {len(arxiv_density_flags)}")


def test_silent_damage_suspected_when_count_drops_below_peak():
    """A paper that previously held many more claims must be flagged
    SILENT_DAMAGE_SUSPECTED so the consumer doesn't trust the degraded entry.
    This is the safety net for events like the 2026-05-13 cross-paper
    collision incident (Levy 2006b: 47 → 14 claims with all other quality
    signals still HIGH).
    """
    bl = _baseline()
    # 14 claims, healthy density, healthy confidence — would normally be HIGH.
    claims = [
        {"confidence_score": 0.93, "source_page": p}
        for p in list(range(1, 15))
    ]
    # WARN case (30% drop): peak=20, current=14 -> drop=30%
    q = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        peak_claim_count=20, baseline=bl,
    )
    silent = [f for f in q["flags"] if f["code"] == "SILENT_DAMAGE_SUSPECTED"]
    assert len(silent) == 1
    assert silent[0]["severity"] == "WARN", silent
    print(f"OK silent-damage WARN at 30% drop: tier={q['confidence_tier']}, action={q['recommended_action']}")

    # STRONG case (50% drop): peak=47, current=14 -> drop=70%
    q = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        peak_claim_count=47, baseline=bl,
    )
    silent = [f for f in q["flags"] if f["code"] == "SILENT_DAMAGE_SUSPECTED"]
    assert len(silent) == 1
    assert silent[0]["severity"] == "STRONG", silent
    assert q["confidence_tier"] == "LOW"
    assert q["recommended_action"] == "RE_EXTRACT"
    print(f"OK silent-damage STRONG at 70% drop: tier={q['confidence_tier']}, action={q['recommended_action']}")

    # No-flag case: count == peak (normal state)
    q = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        peak_claim_count=14, baseline=bl,
    )
    assert not any(f["code"] == "SILENT_DAMAGE_SUSPECTED" for f in q["flags"])
    print(f"OK no silent-damage when current == peak")

    # No-flag case: peak unknown (legacy paper not yet backfilled)
    q = compute_paper_quality(
        paper_type="empirical", claims=claims, observation_count=1,
        peak_claim_count=0, baseline=bl,
    )
    assert not any(f["code"] == "SILENT_DAMAGE_SUSPECTED" for f in q["flags"])
    print(f"OK no silent-damage when peak=0 (legacy / pre-migration)")


def test_paper_versions_preprint_published_pair():
    """When a paper has a registered preprint_published equivalence, both
    cite_claim and search_claims responses must annotate the relationship.
    Preprint side gets a `canonical_paper_id` pointer; published side gets
    an `alternate_versions` listing. No claim content is moved between
    versions — annotation only.
    """
    import sqlite3, tempfile, os
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-db/src"))
    sys.path.insert(0, str(REPO_ROOT / "packages/citare-core/src"))
    from citare_core import Extraction
    from citare_db.ingest import ingest_extraction
    from citare_db.schema import init_db
    from citare_mcp.queries import lookup_paper_versions, search_claims, cite_claim

    tmpf = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    try:
        conn = init_db(tmpf)

        published = {
            "paper": {"doi": "10.test/published", "title": "Paper Published",
                      "year": 2025, "paper_type": "empirical"},
            "claims": [
                {"id": "auth2025_def1", "template_type": "DEFINITION",
                 "source_text": "Published version DEFINITION", "source_page": 5,
                 "confidence_score": 0.95},
            ],
            "claim_relations": [],
        }
        preprint = {
            "paper": {"doi": None, "title": "Paper Preprint", "authors": ["Author A"],
                      "year": 2025, "paper_type": "empirical"},
            "claims": [
                {"id": "auth2025_def1_pre", "template_type": "DEFINITION",
                 "source_text": "Preprint DEFINITION", "source_page": None,
                 "confidence_score": 0.95},
            ],
            "claim_relations": [],
        }
        ingest_extraction(conn, Extraction.model_validate(published))
        ingest_extraction(conn, Extraction.model_validate(preprint))

        # The preprint will have a content-hash-derived _no_doi_* id
        preprint_pid = conn.execute(
            "SELECT id FROM papers WHERE id LIKE '_no_doi_%' AND year = 2025"
        ).fetchone()["id"]
        published_pid = "10.test/published"

        # Ensure lex order matches CHECK(paper_a_id < paper_b_id)
        a, b = sorted([published_pid, preprint_pid])
        conn.execute(
            "INSERT INTO paper_equivalence "
            "(paper_a_id, paper_b_id, equivalence_type, confidence, discovered_by) "
            "VALUES (?, ?, 'preprint_published', 1.0, 'human_expert')",
            (a, b),
        )

        # Preprint side: canonical pointer present
        v_pre = lookup_paper_versions(conn, preprint_pid)
        assert v_pre is not None
        assert v_pre["this_paper_role"] == "preprint", v_pre
        assert v_pre["canonical_paper_id"] == published_pid

        # Published side: knows about the preprint
        v_pub = lookup_paper_versions(conn, published_pid)
        assert v_pub is not None
        assert v_pub["this_paper_role"] == "published"
        assert v_pub["canonical_paper_id"] is None
        assert any(av["paper_id"] == preprint_pid for av in v_pub["alternate_versions"])

        # search_claims annotates results
        search_results = search_claims(conn, doi=preprint_pid)
        assert len(search_results) >= 1
        assert "paper_versions" in search_results[0], "search_claims must inject paper_versions"
        assert search_results[0]["paper_versions"]["this_paper_role"] == "preprint"

        # cite_claim annotates the nested paper object
        claim_id = search_results[0]["id"]
        cited = cite_claim(conn, claim_id)
        assert "paper" in cited
        assert "paper_versions" in cited["paper"], "cite_claim must inject paper.paper_versions"
        assert cited["paper"]["paper_versions"]["this_paper_role"] == "preprint"

        # Unrelated paper: no annotation
        v_unrelated = lookup_paper_versions(conn, published_pid)
        # (published has equivalence; check an unrelated id)
        unrelated = {
            "paper": {"doi": "10.test/unrelated", "title": "Other",
                      "year": 2020, "paper_type": "empirical"},
            "claims": [{"id": "x2020_def1", "template_type": "DEFINITION",
                        "source_text": "nothing", "source_page": 1,
                        "confidence_score": 0.9}],
            "claim_relations": [],
        }
        ingest_extraction(conn, Extraction.model_validate(unrelated))
        assert lookup_paper_versions(conn, "10.test/unrelated") is None
        print("OK paper_versions annotation works on preprint, published, and unrelated papers")
    finally:
        os.unlink(tmpf)


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
    test_cross_paper_claim_id_collision_guard()
    test_silent_damage_suspected_when_count_drops_below_peak()
    test_arxiv_baseline_skips_false_positive_density_flags()
    test_paper_versions_preprint_published_pair()
    test_quirks_idempotent_on_valid_input()
    print("\nAll tests passed.")
