"""Per-variant equation-axis aggregator.

For each variant in a target list, walks all matching run dirs and aggregates:
  - equation_fidelity (avg)
  - core_eq_fidelity (avg)
  - eq_discipline (avg, ignoring None)
  - equations_captured (mean count)
  - decorative_extracted / decorative_expected (mean)

Per-paper means first, then cross-paper mean per variant. Uses the same
directory-based variant detection as analyze_weighted_coverage_v2.py.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from score_against_gold import score  # type: ignore

GOLDS = {
    "T7":          "experiments/ground_truth/trap_papers/T7_gold.json",
    "einstein":    "experiments/ground_truth/real_papers/einstein_1905_gold.json",
    "edmondson":   "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
    "wei":         "experiments/ground_truth/real_papers/wei_2022_gold.json",
    "barney":      "experiments/ground_truth/real_papers/barney_1991_gold.json",
    "vaswani":     "experiments/ground_truth/real_papers/vaswani_2017_gold.json",
    "shannon":     "experiments/ground_truth/real_papers/shannon_1948_gold.json",
    "turing":      "experiments/ground_truth/real_papers/turing_1950_gold.json",
    "watsoncrick": "experiments/ground_truth/real_papers/watson_crick_1953_gold.json",
    "park":        "experiments/ground_truth/real_papers/park_2023_gold.json",
    "noyzhang":    "experiments/ground_truth/real_papers/noy_zhang_2023_gold.json",
    "hubinger":    "experiments/ground_truth/real_papers/hubinger_2024_gold.json",
    "hayes":       "experiments/ground_truth/real_papers/hayes_2006_gold.json",
}

PAPER_KEYS = [
    ("watsoncrick", ["watsoncrick", "watson_crick"]),
    ("noyzhang", ["noyzhang", "noy_zhang"]),
    ("einstein", ["einstein"]),
    ("edmondson", ["edmondson"]),
    ("wei", ["wei_", "_wei"]),
    ("barney", ["barney"]),
    ("vaswani", ["vaswani"]),
    ("shannon", ["shannon", "entropy"]),
    ("turing", ["turing"]),
    ("park", ["park"]),
    ("hubinger", ["hubinger"]),
    ("hayes", ["hayes"]),
    ("T7", ["t7", "trap"]),
]


def variant_from_dir(name: str) -> str | None:
    m = re.search(r"_v0?(?:\.)?13([a-z])_", name)
    if m: return f"v0.13{m.group(1)}"
    if re.search(r"_v0?(?:\.)?13_", name): return "v0.13"
    m = re.search(r"_v0?(?:\.)?12([a-z])_", name)
    if m: return f"v0.12{m.group(1)}"
    m = re.search(r"_v0?(?:\.)?16([a-z])_", name)
    if m: return f"v0.16{m.group(1)}"
    if re.search(r"_v0?(?:\.)?16_", name): return "v0.16"
    m = re.search(r"_v0\.(\d+[a-z]?)_", name)
    if m: return f"v0.{m.group(1)}"
    m = re.search(r"_v3(\d)(?:[a-z]+)?_", name)
    if m: return f"v3.{m.group(1)}"
    m = re.search(r"_v(\d+[a-z]?)_", name)
    if m: return f"v0.{m.group(1)}"
    return None


def paper_from_dir(name: str) -> str | None:
    n = name.lower()
    for paper, keys in PAPER_KEYS:
        for k in keys:
            if k in n:
                return paper
    return None


def main() -> None:
    cells: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for d in sorted((ROOT / "experiments" / "runs").iterdir()):
        if not d.is_dir():
            continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            continue
        variant = variant_from_dir(d.name)
        if variant is None:
            continue
        paper = paper_from_dir(d.name)
        if paper is None or paper not in GOLDS:
            continue
        try:
            res = score(ext, ROOT / GOLDS[paper])
        except Exception:
            continue
        ax = res.get("axes", {})
        cells[variant][paper].append({
            "eq_fid": ax.get("equation_fidelity"),
            "core_eq_fid": ax.get("core_eq_fidelity"),
            "eq_disc": ax.get("eq_discipline"),
            "eq_cap": res.get("equations_captured", 0),
            "dec_ex": res.get("decorative_extracted", 0),
            "dec_exp": res.get("decorative_expected", 0),
        })

    target_variants = ["v0.13", "v0.13d", "v0.13e", "v0.13a", "v0.13b", "v0.13c",
                       "v0.16b", "v0.16c", "v0.16d", "v0.16e", "v0.12e"]

    print("# Equation-axis cross-variant summary")
    print()
    print("Aggregated as: per-paper means first, then cross-paper mean per variant.")
    print()
    print("| Variant | Papers | Runs | eq_fid | core_eq_fid | eq_discipline | eqs_captured | decorative |")
    print("|---------|-------:|-----:|-------:|------------:|--------------:|-------------:|-----------:|")

    for variant in target_variants:
        if variant not in cells:
            continue
        papers = cells[variant]
        per_paper_means = []
        all_runs = 0
        for paper, runs in papers.items():
            all_runs += len(runs)
            ef = [r["eq_fid"] for r in runs if r["eq_fid"] is not None]
            cef = [r["core_eq_fid"] for r in runs if r["core_eq_fid"] is not None]
            ed = [r["eq_disc"] for r in runs if r["eq_disc"] is not None]
            cap = [r["eq_cap"] for r in runs]
            dex = [r["dec_ex"] for r in runs]
            dxp = [r["dec_exp"] for r in runs]
            per_paper_means.append({
                "ef": statistics.mean(ef) if ef else None,
                "cef": statistics.mean(cef) if cef else None,
                "ed": statistics.mean(ed) if ed else None,
                "cap": statistics.mean(cap),
                "dex": statistics.mean(dex),
                "dxp": statistics.mean(dxp),
            })

        ef_xs = [p["ef"] for p in per_paper_means if p["ef"] is not None]
        cef_xs = [p["cef"] for p in per_paper_means if p["cef"] is not None]
        ed_xs = [p["ed"] for p in per_paper_means if p["ed"] is not None]
        cap_xs = [p["cap"] for p in per_paper_means]
        dex_xs = [p["dex"] for p in per_paper_means]
        dxp_xs = [p["dxp"] for p in per_paper_means]

        ef_s = f"{statistics.mean(ef_xs)*100:.1f}%" if ef_xs else "-"
        cef_s = f"{statistics.mean(cef_xs)*100:.1f}%" if cef_xs else "-"
        ed_s = f"{statistics.mean(ed_xs)*100:.1f}%" if ed_xs else "-"
        cap_s = f"{statistics.mean(cap_xs):.1f}" if cap_xs else "-"
        dec_s = f"{statistics.mean(dex_xs):.1f}/{statistics.mean(dxp_xs):.1f}" if dex_xs else "-"

        print(f"| {variant} | {len(papers)} | {all_runs} | {ef_s} | {cef_s} | {ed_s} | {cap_s} | {dec_s} |")

    # Per-paper detail for v0.13 specifically
    print()
    print("## v0.13 (bare) per-paper equation detail")
    print()
    print("| Paper | N | eq_fid | core_eq_fid | eq_discipline | eqs_captured | decorative ext/exp |")
    print("|-------|--:|-------:|------------:|--------------:|-------------:|-------------------:|")
    if "v0.13" in cells:
        for paper in GOLDS:
            runs = cells["v0.13"].get(paper, [])
            if not runs:
                continue
            ef = [r["eq_fid"] for r in runs if r["eq_fid"] is not None]
            cef = [r["core_eq_fid"] for r in runs if r["core_eq_fid"] is not None]
            ed = [r["eq_disc"] for r in runs if r["eq_disc"] is not None]
            cap = [r["eq_cap"] for r in runs]
            dex = [r["dec_ex"] for r in runs]
            dxp = [r["dec_exp"] for r in runs]
            ef_s = f"{statistics.mean(ef)*100:.1f}%" if ef else "-"
            cef_s = f"{statistics.mean(cef)*100:.1f}%" if cef else "-"
            ed_s = f"{statistics.mean(ed)*100:.1f}%" if ed else "-"
            print(f"| {paper} | {len(runs)} | {ef_s} | {cef_s} | {ed_s} | "
                  f"{statistics.mean(cap):.1f} | {statistics.mean(dex):.1f}/{statistics.mean(dxp):.1f} |")


if __name__ == "__main__":
    main()
