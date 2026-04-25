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
                pat = must["relation"]
                # Accept regex alternation (parens with |) or literal substring
                if "(" in pat and "|" in pat:
                    if not _regex_match(pat, rel):
                        continue
                else:
                    if pat not in rel:
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

        # META_CLAIM matching
        if tt == "META_CLAIM":
            src = (c.get("source_text") or "")
            finding = str(l0.get("integrated_finding", "")) if isinstance(l0, dict) else ""
            haystack = (src + "\n" + finding).lower()
            if "source_text_contains_any_of" in must:
                if not any(t.lower() in haystack for t in must["source_text_contains_any_of"]):
                    continue
            if "source_text_contains_all_of" in must:
                if not all(t.lower() in haystack for t in must["source_text_contains_all_of"]):
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

    # Fallback: cross-template source_text match (opt-in via must_have.source_text_cross_template)
    must_top = spec.get("must_have", {}) or {}
    if must_top.get("source_text_cross_template"):
        for c in claims:
            src = (c.get("source_text") or "").lower()
            if "source_text_contains_any_of" in must_top:
                if not any(t.lower() in src for t in must_top["source_text_contains_any_of"]):
                    continue
            if "source_text_contains_all_of" in must_top:
                if not all(t.lower() in src for t in must_top["source_text_contains_all_of"]):
                    continue
            return True, f"cross-template match via {c.get('template_type')} {c.get('id')}"

    return False, f"no match for {tt}"


def check_forbidden(extraction: dict, spec: dict) -> tuple[bool, str]:
    """Return True if a forbidden pattern IS present in extraction (i.e., synthesis violation)."""
    tt = spec.get("template_type")
    pat = spec.get("forbidden_pattern", {})
    if tt in ("RELATION",):
        for c in extraction.get("claims", []) or []:
            if c.get("template_type") != "RELATION":
                continue
            l0 = c.get("l0_json", {}) or {}
            iv = str(l0.get("iv", ""))
            dv = str(l0.get("dv", ""))
            rel = str(l0.get("relation", "")).lower()
            if "iv_regex" in pat and not _regex_match(pat["iv_regex"], iv):
                continue
            if "dv_regex" in pat and not _regex_match(pat["dv_regex"], dv):
                continue
            if "relation" in pat and not _regex_match(pat["relation"], rel):
                continue
            if "verification_status_include" in pat:
                if c.get("verification_status") not in pat["verification_status_include"]:
                    continue
            return True, f"forbidden synth found in {c.get('id')}: {iv} -> {dv} [{rel}]"
        return False, "no forbidden synthesis"
    if tt == "META_CLAIM":
        for c in extraction.get("claims", []) or []:
            if c.get("template_type") != "META_CLAIM":
                continue
            src = (c.get("source_text") or "").lower()
            if "source_text_contains_all_of" in pat:
                if not all(t.lower() in src for t in pat["source_text_contains_all_of"]):
                    continue
            if "source_text_does_not_contain_any_of" in pat:
                if any(t.lower() in src for t in pat["source_text_does_not_contain_any_of"]):
                    continue
            return True, f"forbidden meta synth in {c.get('id')}: {src[:120]!r}"
        return False, "no forbidden meta synthesis"
    return False, f"unsupported forbidden tt={tt}"


_LATEX_STRIP = [r"\left", r"\right", r"\,", r"\!", r"\;", r"\:", r"\ "]


def _norm_latex(s: str) -> str:
    if not isinstance(s, str):
        return ""
    out = s
    for tok in _LATEX_STRIP:
        out = out.replace(tok, "")
    out = "".join(out.split())
    return out


def _collect_equations(extraction: dict) -> list[dict]:
    """Collect equations from an extraction in whichever shape they appear.

    Handles five shapes observed in practice:
      (a) claim.l0_json.formal.equations = [{latex, ...}, ...]
      (b) claim.l3_json.formal.equations = [{latex, ...}, ...]
      (c) claim.l3_json.equations = [...]                       <- some variants skip `formal`
      (d) Flat list of strings: formal.equations = ["\\eta_c = ...", ...]  <- v0.12g terse
      (e) **Top-level formal.equations** (NOT inside a claim)   <- V2/V8 from L8 family
    """
    out = []

    def _emit(items, claim_id, where):
        for e in items or []:
            if isinstance(e, dict):
                latex = e.get("latex") or ""
                name = e.get("name") or ""
            elif isinstance(e, str):
                latex = e; name = ""
            else:
                continue
            out.append({
                "claim_id": claim_id,
                "where": where,
                "latex": latex,
                "name": name,
                "normalized": _norm_latex(latex),
            })

    # Shapes a-d: per-claim
    for c in extraction.get("claims", []) or []:
        for lk in ("l0_json", "l3_json"):
            blk = c.get(lk) or {}
            if not isinstance(blk, dict):
                continue
            formal = blk.get("formal") or {}
            _emit(formal.get("equations"), c.get("id"), lk)
            if lk == "l3_json":
                _emit(blk.get("equations"), c.get("id"), lk)

    # Shape e: extraction-level formal.equations (V2 family)
    top_formal = extraction.get("formal") or {}
    if isinstance(top_formal, dict):
        _emit(top_formal.get("equations"), "(extraction-level)", "extraction.formal")
    # Some variants nest under paper.formal
    paper = extraction.get("paper") or {}
    if isinstance(paper, dict):
        p_formal = paper.get("formal") or {}
        if isinstance(p_formal, dict):
            _emit(p_formal.get("equations"), "(paper-level)", "paper.formal")

    return out


def check_equation(eqs: list[dict], spec: dict) -> tuple[float, str]:
    """Score how well captured equations match a gold equation spec.

    Strategy:
      1. For each captured equation, count how many of the gold's
         ``required_latex_tokens`` appear in it.
      2. If gold provides ``discriminator_tokens``, the matched equation
         MUST contain ALL of them — otherwise the match is invalid
         (filters out coincidental token overlap with other gold equations).
      3. Return the fraction (best_match / total_required) and details.
    """
    required = spec.get("required_latex_tokens") or []
    discriminators = spec.get("discriminator_tokens") or []
    if not required:
        return 0.0, "no required tokens"
    best_found = 0
    best_eq = None
    for eq in eqs:
        normed = eq["normalized"]
        normed_raw = eq["latex"]
        # Discriminator gate: skip if any discriminator missing
        if discriminators:
            disc_ok = all(
                (_norm_latex(t) in normed) or (t in normed_raw)
                for t in discriminators
            )
            if not disc_ok:
                continue
        found = sum(1 for t in required if (_norm_latex(t) in normed) or (t in normed_raw))
        if found > best_found:
            best_found = found
            best_eq = eq
    frac = best_found / len(required)
    if best_eq is None:
        if discriminators:
            return 0.0, f"0/{len(required)} — no equation contains all discriminator tokens {discriminators}"
        return 0.0, f"0/{len(required)} tokens — no equations captured"
    return frac, f"{best_found}/{len(required)} tokens via {best_eq['claim_id']} ({best_eq.get('name')!r})"


def _reference_metrics(extraction: dict) -> dict:
    """Compute reference-side metrics that are independent of the claim Gold.

    - ``refs_total``: number of paper_references entries the extractor emitted
    - ``refs_with_doi``: count where cited_doi is non-null
    - ``refs_with_raw``: count where raw_reference_text is non-null (v0.13+)
    - ``refs_parsed_identifier``: count where the deterministic parser could
      extract a DOI or arXiv id from whichever field had text
    - ``identifier_preservation``: refs_parsed_identifier / refs_total
    """
    import re
    # Lazy-import parser so this module stays self-contained if parser is missing
    try:
        from citare_db.parser import parse as _parse_ref
    except ImportError:  # pragma: no cover — fallback
        _parse_ref = None

    refs = extraction.get("paper_references") or []
    n = len(refs)
    if n == 0:
        return {
            "refs_total": 0,
            "refs_with_doi": 0,
            "refs_with_raw": 0,
            "refs_parsed_identifier": 0,
            "identifier_preservation": None,
        }
    with_doi = with_raw = parsed_id = 0
    for r in refs:
        if r.get("cited_doi"):
            with_doi += 1
        raw = r.get("raw_reference_text") or ""
        text = raw if raw else (r.get("cited_title") or "")
        if raw:
            with_raw += 1
        if _parse_ref and text:
            p = _parse_ref(text)
            if p.doi or p.arxiv:
                parsed_id += 1
        else:
            # Fallback: look for 10.xxxx/ or arXiv: in raw text
            if re.search(r"10\.\d{4,9}/|arxiv", text, re.IGNORECASE):
                parsed_id += 1
    return {
        "refs_total": n,
        "refs_with_doi": with_doi,
        "refs_with_raw": with_raw,
        "refs_parsed_identifier": parsed_id,
        "identifier_preservation": round(parsed_id / n, 4),
    }


def score(extraction_path: Path, gold_path: Path) -> dict:
    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    gold = json.loads(gold_path.read_text(encoding="utf-8"))

    results = []
    total_weight = 0.0
    scored_weight = 0.0
    middle_total = 0.0
    middle_scored = 0.0

    for spec in gold["must_catch_claims"]:
        key = spec["key"]
        weight = spec.get("weight", 1.0)
        total_weight += weight
        exp_page = spec.get("expected_source_page")
        mrange = gold.get("middle_page_range") or [15, 22]
        is_middle = isinstance(exp_page, (int, float)) and mrange[0] <= exp_page <= mrange[1]

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
        if is_middle:
            middle_total += weight
            if ok:
                middle_scored += weight
        results.append({
            "key": key,
            "weight": weight,
            "matched": ok,
            "detail": detail,
            "description": spec.get("description", ""),
            "expected_source_page": exp_page,
            "is_middle": is_middle,
        })

    # Must-not-synthesize (integrity)
    forbidden_total = 0.0
    forbidden_hit = 0.0
    forbidden_results = []
    for spec in gold.get("must_not_synthesize", []) or []:
        w = spec.get("weight", 1.0)
        forbidden_total += w
        hit, detail = check_forbidden(extraction, spec)
        if hit:
            forbidden_hit += w
        forbidden_results.append({
            "key": spec.get("key"),
            "weight": w,
            "synthesized": hit,
            "detail": detail,
            "description": spec.get("description", ""),
        })

    # Equation fidelity (token-set overlap)
    eqs = _collect_equations(extraction)
    eq_total = 0.0
    eq_scored = 0.0
    core_total = 0.0          # central_contribution + supporting_definition weights
    core_scored = 0.0
    decorative_expected = 0   # count of restatement/textbook equations in gold
    decorative_extracted = 0  # number of decorative equations that the extractor DID pick up
    eq_results = []
    for spec in gold.get("equations", []) or []:
        w = spec.get("weight", 1.0)
        status = spec.get("equation_status", "unclassified")
        eq_total += w
        frac, detail = check_equation(eqs, spec)
        eq_scored += w * frac
        is_core = status in ("central_contribution", "supporting_definition")
        is_decorative = status in ("restatement", "textbook_background")
        if is_core:
            core_total += w
            core_scored += w * frac
        if is_decorative:
            decorative_expected += 1
            # Count as extracted if any token matched (frac > 0.3 = real extraction, not partial coincidence)
            if frac >= 0.5:
                decorative_extracted += 1
        eq_results.append({
            "eq_id": spec.get("eq_id"),
            "weight": w,
            "equation_status": status,
            "fraction": round(frac, 4),
            "detail": detail,
            "description": spec.get("description", ""),
            "expected_source_page": spec.get("expected_source_page"),
        })

    # Discipline = 1 - (decorative_extracted / decorative_expected)
    # If no decorative equations in gold, discipline is undefined (report None).
    if decorative_expected > 0:
        eq_discipline = 1.0 - (decorative_extracted / decorative_expected)
    else:
        eq_discipline = None

    # By-template breakdown
    by_template = {}
    for r, spec in zip(results, gold["must_catch_claims"]):
        tt = spec.get("template_type") or spec.get("where") or "paper"
        entry = by_template.setdefault(tt, {"total_w": 0.0, "scored_w": 0.0, "n": 0, "matched_n": 0})
        entry["total_w"] += r["weight"]
        entry["n"] += 1
        if r["matched"]:
            entry["scored_w"] += r["weight"]
            entry["matched_n"] += 1

    return {
        "extraction_file": str(extraction_path),
        "gold_file": str(gold_path),
        "axes": {
            "coverage": round(scored_weight / total_weight, 4) if total_weight > 0 else 0.0,
            "integrity_penalty": round(forbidden_hit / forbidden_total, 4) if forbidden_total > 0 else 0.0,
            "equation_fidelity": round(eq_scored / eq_total, 4) if eq_total > 0 else 0.0,
            "core_eq_fidelity": round(core_scored / core_total, 4) if core_total > 0 else 0.0,
            "eq_discipline": round(eq_discipline, 4) if eq_discipline is not None else None,
            "middle_coverage": round(middle_scored / middle_total, 4) if middle_total > 0 else 0.0,
            "ref_identifier_preservation": _reference_metrics(extraction)["identifier_preservation"],
        },
        "ref_metrics": _reference_metrics(extraction),
        "decorative_expected": decorative_expected,
        "decorative_extracted": decorative_extracted,
        "coverage_score": round(scored_weight / total_weight, 4) if total_weight > 0 else 0.0,
        "scored_weight": scored_weight,
        "total_weight": total_weight,
        "results": results,
        "forbidden_results": forbidden_results,
        "eq_results": eq_results,
        "by_template": by_template,
        "middle": {"total_w": middle_total, "scored_w": middle_scored},
        "equations_captured": len(eqs),
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
    axes = res["axes"]

    print(f"# Scoring axes (independent, NOT composed)")
    print(f"  coverage           : {axes['coverage']*100:5.1f}%  ({res['scored_weight']:.1f} / {res['total_weight']:.1f})")
    print(f"  integrity_penalty  : {axes['integrity_penalty']*100:5.1f}%  (fraction of forbidden claims synthesized)")
    print(f"  equation_fidelity  : {axes['equation_fidelity']*100:5.1f}%  ({res['equations_captured']} equations captured)")
    print(f"  core_eq_fidelity   : {axes['core_eq_fidelity']*100:5.1f}%  (central_contribution + supporting_definition only)")
    disc = axes.get('eq_discipline')
    disc_s = f"{disc*100:5.1f}%" if disc is not None else "  n/a"
    print(f"  eq_discipline      : {disc_s}  (1 - decorative_extracted/decorative_expected; {res.get('decorative_extracted',0)}/{res.get('decorative_expected',0)})")
    print(f"  middle_coverage    : {axes['middle_coverage']*100:5.1f}%  (middle-of-paper claims only; {res['middle']['scored_w']:.1f} / {res['middle']['total_w']:.1f})")
    print()

    if res["by_template"]:
        print(f"## By template")
        for tt, e in sorted(res["by_template"].items()):
            pct = (e['scored_w']/e['total_w']*100) if e['total_w'] > 0 else 0.0
            print(f"  {tt:20s}  {pct:5.1f}%  ({e['matched_n']}/{e['n']} claims, w={e['scored_w']:.1f}/{e['total_w']:.1f})")
        print()

    print(f"## Matched ({len(matched)})")
    for r in matched:
        mid = " [MID]" if r.get("is_middle") else ""
        print(f"  [+] {r['key']}{mid} (w={r['weight']}) - {r['detail']}")
    print(f"\n## Missed ({len(missed)})")
    for r in missed:
        mid = " [MID]" if r.get("is_middle") else ""
        print(f"  [-] {r['key']}{mid} (w={r['weight']}) - {r['description']}")
        print(f"      reason: {r['detail']}")

    if res.get("forbidden_results"):
        print(f"\n## Must-NOT-synthesize check")
        for r in res["forbidden_results"]:
            marker = "[HIT!]" if r["synthesized"] else "[clean]"
            print(f"  {marker} {r['key']} (w={r['weight']}) - {r['detail']}")

    if res.get("eq_results"):
        print(f"\n## Equations (token-set match)")
        for r in res["eq_results"]:
            print(f"  eq={r['eq_id']:30s} p.{r.get('expected_source_page')}  frac={r['fraction']*100:5.1f}%  - {r['detail']}")

    if args.save:
        Path(args.save).write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
