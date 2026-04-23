"""
Score an extraction.json against a gold "must-catch" fixture.

Usage:
    python score_against_gold.py \
        --extraction experiments/runs/20260422T195209Z_R1_baseline_edmondson/extraction.json \
        --gold experiments/ground_truth/real_papers/edmondson_1999_gold.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _as_list(x):
    return x if isinstance(x, list) else [x] if x is not None else []


def _norm(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return s.lower().replace(" ", "_").replace("-", "_")


def _regex_match(pattern: str, target: str) -> bool:
    if not target or not pattern:
        return False
    return bool(re.search(pattern, target, flags=re.IGNORECASE))


def check_paper_level(extraction: dict, key: str, spec: dict) -> tuple[bool, str]:
    paper = extraction.get("paper", {}) or {}
    where = spec.get("where", "")
    must = spec.get("must_have", {})
    if where == "paper.default_causal_strength":
        obj = paper.get("default_causal_strength", {}) or {}
        checks = []
        if "design_basis" in must:
            checks.append(obj.get("design_basis") == must["design_basis"])
        if "author_framing_include" in must:
            checks.append(obj.get("author_framing") in must["author_framing_include"])
        if "temporal_precedence" in must:
            checks.append(obj.get("temporal_precedence") == must["temporal_precedence"])
        ok = all(checks) if checks else False
        return ok, f"default_causal_strength={obj}"
    if where == "paper.default_method":
        obj = paper.get("default_method", {}) or {}
        checks = []
        if "unit_of_analysis" in must:
            checks.append(obj.get("unit_of_analysis") == must["unit_of_analysis"])
        if "sample_size_near" in must:
            n = obj.get("sample_size")
            checks.append(isinstance(n, (int, float)) and abs(n - must["sample_size_near"]) <= 2)
        if "study_design_contains_any_of" in must:
            sd = (obj.get("study_design") or "").lower()
            checks.append(any(t.lower() in sd for t in must["study_design_contains_any_of"]))
        ok = all(checks) if checks else False
        return ok, f"default_method={obj}"
    if where == "paper.paper_type":
        val = (paper.get("paper_type") or "").lower()
        ok = any(t in val for t in must.get("value_include", []))
        return ok, f"paper_type={val}"
    return False, f"unknown where={where}"


def check_measurement_method(extraction: dict, spec: dict) -> tuple[bool, str]:
    mms = extraction.get("measurement_methods", []) or []
    must = spec.get("must_have", {})
    target_measure = must.get("measures_regex", "")
    alpha_target = must.get("reliability_reported_near")
    for mm in mms:
        measures = str(mm.get("measures", ""))
        if target_measure and not _regex_match(target_measure, measures):
            continue
        if alpha_target is not None:
            details = mm.get("details", {}) or {}
            # Handle multiple reliability shapes:
            # (a) details.reliability_reported: 0.82       (v0.1 style)
            # (b) details.reliability: 0.82                 (bare number)
            # (c) details.reliability: {"alpha": 0.82}     (legacy dict)
            # (d) details.reliability: {"type": "cronbach_alpha", "value": 0.82}  (v0.3+ structured)
            alpha = details.get("reliability_reported", details.get("reliability"))
            if isinstance(alpha, dict):
                alpha = alpha.get("value", alpha.get("alpha"))
            try:
                if alpha is not None and abs(float(alpha) - alpha_target) <= 0.05:
                    return True, f"found {mm.get('id')} with alpha={alpha}"
            except (TypeError, ValueError):
                pass
        else:
            return True, f"found {mm.get('id')}"
    return False, f"no mm matching measures={target_measure} alpha≈{alpha_target}"


def check_incompleteness(extraction: dict, spec: dict) -> tuple[bool, str]:
    wanted = spec["must_have"].get("incompleteness_category_include", [])
    # Claim-level
    claim_level = set()
    for c in extraction.get("claims", []) or []:
        l3 = c.get("l3_json", {}) or {}
        if isinstance(l3, dict) and "incompleteness_category" in l3:
            claim_level.add(l3["incompleteness_category"])
        if "incompleteness_category" in c:
            claim_level.add(c["incompleteness_category"])
    # Relation-level
    rel_level = set()
    for r in extraction.get("claim_relations", []) or []:
        if "incompleteness_category" in r:
            rel_level.add(r["incompleteness_category"])
    found = claim_level | rel_level
    for w in wanted:
        if w in found:
            return True, f"found at {'claim' if w in claim_level else 'relation'} level: {w}"
    return False, f"wanted {wanted}, found claim={claim_level} rel={rel_level}"


def check_claim(extraction: dict, spec: dict) -> tuple[bool, str]:
    claims = extraction.get("claims", []) or []
    tt = spec.get("template_type")
    must = spec.get("must_have", {})
    for c in claims:
        if tt and c.get("template_type") != tt:
            continue
        l0 = c.get("l0_json", {}) or {}

        # DEFINITION matching
        if tt == "DEFINITION":
            concept = str(l0.get("concept", ""))
            if "concept_regex" in must and not _regex_match(must["concept_regex"], concept):
                continue
            if "key_elements_include_any_of" in must:
                elements = " ".join(str(x) for x in (l0.get("key_elements") or []))
                wanted = must["key_elements_include_any_of"]
                if not any(w.lower() in elements.lower() for w in wanted):
                    continue
            return True, f"matched {c.get('id')}"

        # RELATION matching
        if tt == "RELATION":
            iv = str(l0.get("iv", ""))
            dv = str(l0.get("dv", ""))
            if "iv_regex" in must and not _regex_match(must["iv_regex"], iv):
                continue
            if "dv_regex" in must and not _regex_match(must["dv_regex"], dv):
                continue
            if "mediator_regex" in must:
                mediator = str(l0.get("mediator") or "")
                if not _regex_match(must["mediator_regex"], mediator):
                    continue
            if "relation" in must:
                rel = str(l0.get("relation", "")).lower()
                if must["relation"] not in rel:
                    continue
            if "verification_status_include" in must:
                if c.get("verification_status") not in must["verification_status_include"]:
                    continue
            if must.get("l3_mediation_must_exist"):
                l3 = c.get("l3_json", {}) or {}
                if not (isinstance(l3, dict) and l3.get("mediation")):
                    continue
            if "direct_p_after_mediator_near" in must:
                l3 = c.get("l3_json", {}) or {}
                m = l3.get("mediation", {}) if isinstance(l3, dict) else {}
                # Accept several field-name variants: direct_p, direct_p_when_mediator_included,
                # direct_p_with_mediator, direct_p_after_controlling, etc.
                p = None
                if isinstance(m, dict):
                    for key in ("direct_p", "direct_p_when_mediator_included",
                                "direct_p_with_mediator", "direct_p_after_controlling",
                                "direct_effect_p"):
                        if key in m:
                            p = m[key]
                            break
                try:
                    p_val = float(str(p).replace("=", "").replace("<", "").strip()) if p is not None else None
                    if p_val is None or abs(p_val - must["direct_p_after_mediator_near"]) > 0.1:
                        continue
                except (TypeError, ValueError):
                    continue
            return True, f"matched {c.get('id')}"

        # EXISTENCE_CLAIM matching
        if tt == "EXISTENCE_CLAIM":
            phen = str(l0.get("phenomenon", ""))
            src = (c.get("source_text") or "")
            if "phenomenon_regex" in must and not _regex_match(must["phenomenon_regex"], phen):
                continue
            if "source_text_contains_all_of" in must:
                if not all(t.lower() in src.lower() for t in must["source_text_contains_all_of"]):
                    continue
            if "source_text_contains_any_of" in must:
                if not any(t.lower() in src.lower() for t in must["source_text_contains_any_of"]):
                    continue
            if "sample_size_numbers_mentioned_any_of" in must:
                ev = str(l0.get("evidence", "")) + " " + src
                nums = must["sample_size_numbers_mentioned_any_of"]
                if not any(str(n) in ev for n in nums):
                    continue
            if "source_section_includes_any_of" in must:
                section = str(c.get("source_section", ""))
                if not any(s in section for s in must["source_section_includes_any_of"]):
                    continue
            return True, f"matched {c.get('id')}"

    return False, f"no match for {tt}"


def score(extraction_path: Path, gold_path: Path) -> dict:
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    gold = json.loads(gold_path.read_text(encoding="utf-8"))

    results = []
    total_weight = 0.0
    scored_weight = 0.0

    for spec in gold["must_catch_claims"]:
        key = spec["key"]
        weight = spec.get("weight", 1.0)
        total_weight += weight

        where = spec.get("where", "")
        if where.startswith("paper."):
            ok, detail = check_paper_level(extraction, key, spec)
        elif where == "measurement_methods":
            ok, detail = check_measurement_method(extraction, spec)
        elif where in ("claim_relations or claim-level incompleteness_category",):
            ok, detail = check_incompleteness(extraction, spec)
        elif "template_type" in spec:
            ok, detail = check_claim(extraction, spec)
        else:
            ok, detail = False, "unknown spec shape"

        if ok:
            scored_weight += weight
        results.append({
            "key": key,
            "weight": weight,
            "matched": ok,
            "detail": detail,
            "description": spec.get("description", ""),
        })

    return {
        "extraction_file": str(extraction_path),
        "gold_file": str(gold_path),
        "coverage_score": round(scored_weight / total_weight, 4) if total_weight > 0 else 0.0,
        "scored_weight": scored_weight,
        "total_weight": total_weight,
        "results": results,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--extraction", required=True)
    p.add_argument("--gold", required=True)
    p.add_argument("--save", help="Optional path to save full result JSON")
    args = p.parse_args()

    res = score(Path(args.extraction), Path(args.gold))

    matched = [r for r in res["results"] if r["matched"]]
    missed = [r for r in res["results"] if not r["matched"]]

    print(f"# Coverage: {res['coverage_score']*100:.1f}% ({res['scored_weight']:.1f} / {res['total_weight']:.1f})\n")
    print(f"## Matched ({len(matched)})")
    for r in matched:
        print(f"  [+] {r['key']} (w={r['weight']}) - {r['detail']}")
    print(f"\n## Missed ({len(missed)})")
    for r in missed:
        print(f"  [-] {r['key']} (w={r['weight']}) - {r['description']}")
        print(f"      reason: {r['detail']}")

    if args.save:
        Path(args.save).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
