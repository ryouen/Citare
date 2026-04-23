"""
Demo script: show Citare catching citation errors that a naive LLM would make.

For a hackathon demo, this is the "Wow moment":
  1. Ask the naive LLM: "What did Edmondson (1999) find about psychological safety?"
  2. Show the LLM saying "psychological safety CAUSES learning behavior" (causal misattribution)
  3. Query Citare: load the extraction JSON, pull the RELATION claim
  4. Citare shows: design_basis=cross_sectional, author_framing=associational
  5. Citare blocks the causal verb, suggests "is associated with" + mediation warning

Usage:
    python demo_citation_check.py \
        --extraction experiments/runs/20260423T021928Z_R10H_cli_v34_high/extraction.json \
        --query "team_psychological_safety" --target "team_performance"
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


SAFE_VERBS = {
    ("rct", "causal"): "causes / increases / leads to",
    ("rct", "existence_proof"): "demonstrates / achieves",
    ("longitudinal", "causal"): "predicts (longitudinally)",
    ("longitudinal", "associational"): "is associated with (over time)",
    ("cross_sectional", "associational"): "is associated with",
    ("cross_sectional", "causal"): "is associated with",  # author overclaims; we correct
    ("cross_sectional", "suggestive"): "may be related to",
    ("computational_demonstration", "existence_proof"): "achieves on benchmarks",
    ("theoretical", "causal"): "is theoretically proposed to",
    ("meta_analysis", "causal"): "meta-analytically predicts",
}


def safe_verb(design_basis: str, author_framing: str) -> str:
    return SAFE_VERBS.get(
        (design_basis, author_framing),
        "is associated with",
    )


def find_relation(extraction: dict, iv: str, dv: str) -> list[dict]:
    results = []
    for c in extraction.get("claims", []) or []:
        if c.get("template_type") != "RELATION":
            continue
        l0 = c.get("l0_json") or {}
        if l0.get("iv") == iv and l0.get("dv") == dv:
            results.append(c)
    return results


def incompleteness_warnings(extraction: dict, claim_id: str) -> list[dict]:
    warns = []
    for r in extraction.get("claim_relations", []) or []:
        if r.get("source_id") == claim_id or r.get("target_id") == claim_id:
            cat = r.get("incompleteness_category")
            if cat and cat != "none":
                warns.append(r)
    return warns


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--extraction", required=True)
    p.add_argument("--query", required=True, help="iv concept name (e.g. team_psychological_safety)")
    p.add_argument("--target", required=True, help="dv concept name (e.g. team_performance)")
    args = p.parse_args()

    extraction = json.loads(Path(args.extraction).read_text(encoding="utf-8"))
    paper = extraction.get("paper", {}) or {}
    default_cs = paper.get("default_causal_strength", {}) or {}

    print(f"## Citare Citation Check")
    print(f"**Paper**: {paper.get('title', '?')} (DOI: {paper.get('doi', '?')})\n")

    matches = find_relation(extraction, args.query, args.target)
    if not matches:
        print(f"No RELATION claim found with iv={args.query}, dv={args.target} in this paper.")
        return

    for c in matches:
        claim_id = c.get("id")
        cs = c.get("causal_strength") or default_cs
        design = cs.get("design_basis", "?")
        framing = cs.get("author_framing", "?")
        verb = safe_verb(design, framing)

        print(f"### Claim `{claim_id}`")
        print(f"- **Source text**: \"{c.get('source_text', '?')[:180]}\"")
        print(f"- **iv -> dv**: `{args.query}` -> `{args.target}`")
        print(f"- **Design basis**: `{design}` | **Author framing**: `{framing}`")
        print(f"- **Safe verb**: **{verb}**")

        if framing == "causal" and design in ("cross_sectional", "theoretical"):
            print(f"- WARNING: author framed as causal, but design={design} does not support causal inference.")
            print(f"  Citation should use 'is associated with', not 'causes'.")

        warns = incompleteness_warnings(extraction, claim_id)
        if warns:
            print(f"\n**Incompleteness warnings** ({len(warns)}):")
            for w in warns:
                cat = w.get("incompleteness_category")
                rt = w.get("relation_type")
                other = w.get("target_id") if w.get("source_id") == claim_id else w.get("source_id")
                print(f"  - `{cat}` (via `{rt}`, links to `{other}`)")
                if cat == "effect_disappears_under_control":
                    print(f"    This effect vanishes when controlling for another variable.")
                    print(f"    Citing this alone is MISLEADING — include the mediator.")
                elif cat == "hub_component":
                    print(f"    This claim is a component of a larger mediation/moderation model.")
                    print(f"    Citing alone loses the hub context.")
                elif cat == "boundary_condition":
                    print(f"    A boundary condition exists — cite only within the stated scope.")

        print()


if __name__ == "__main__":
    main()
