"""Score the 9 v0.16b-hg targeted-test runs and compare to v0.16b/v0.13d.

Targeted runs: 20260425T144301Z_R70_v016bhg_<paper>_s<seed>
  for paper in {T7, wei, noyzhang} and seed in {1,2,3}.
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from score_against_gold import score  # type: ignore
from analyze_weighted_coverage_v2 import (  # type: ignore
    score_weighted, variant_from_dir, paper_from_run_dir, GOLDS,
)

PAPERS = ["T7", "wei", "noyzhang"]
SEEDS = [1, 2, 3]
TS = "20260425T144301Z"

# Reference numbers for v0.16b and v0.13d on the same papers
REF = {
    "T7":       {"v0.16b": (0.93, 0.88), "v0.13d": (0.80, 0.88)},
    "wei":      {"v0.16b": (0.92, 0.97), "v0.13d": (1.00, 0.93)},
    "noyzhang": {"v0.16b": (1.00, 0.73), "v0.13d": (1.00, 0.93)},
}

# Items of interest for "now caught vs previously missed"
INTEREST = {
    "noyzhang": "exist_effect_heterogeneity",
    "T7":       "rel_R1_dataset_size_to_tail_coverage",
}


def get_run_dir(paper: str, seed: int) -> Path:
    return ROOT / "experiments" / "runs" / f"{TS}_R70_v016bhg_{paper}_s{seed}"


def per_run_scoring():
    """Return dict[paper] = list of per-run dicts (one per seed)."""
    by_paper: dict[str, list[dict]] = {p: [] for p in PAPERS}

    for paper in PAPERS:
        gold_path = ROOT / GOLDS[paper]
        for seed in SEEDS:
            run_dir = get_run_dir(paper, seed)
            ext = run_dir / "extraction.json"
            metrics_path = run_dir / "metrics.json"
            if not ext.exists() or not metrics_path.exists():
                print(f"WARN: missing files for {run_dir.name}")
                continue
            res = score(ext, gold_path)
            sw = score_weighted(ext, gold_path)
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            in_tok = (
                metrics.get("input_tokens", 0)
                + metrics.get("cache_creation_input_tokens", 0)
                + metrics.get("cache_read_input_tokens", 0)
            )
            out_tok = metrics.get("output_tokens", 0)

            # Capture matched-status of items of interest
            matched_items = {r["key"]: r["matched"] for r in res["results"]}
            interest_key = INTEREST.get(paper)
            interest_matched = matched_items.get(interest_key) if interest_key else None

            by_paper[paper].append({
                "seed": seed,
                "run_dir": run_dir.name,
                "cov_overall": sw["cov_overall"],
                "cov_core": sw["cov_core"],
                "cov_minor": sw["cov_minor"],
                "cost": metrics.get("cost_usd", 0),
                "duration_s": metrics.get("duration_sec", 0),
                "in_tok": in_tok,
                "out_tok": out_tok,
                "claims": metrics.get("claim_counts", {}).get("total", 0),
                "interest_key": interest_key,
                "interest_matched": interest_matched,
                "results": res["results"],
            })
    return by_paper


def main():
    by_paper = per_run_scoring()

    out_md = []
    out_md.append("# v0.16b-hg targeted-test (R70) scoring + Pareto comparison\n")
    out_md.append(f"\nGenerated from 9 runs: `{TS}_R70_v016bhg_<paper>_s<1..3>` for paper in {PAPERS}.\n")
    out_md.append("\nv0.16b-hg = v0.16b base + hedging-language additions intended to recover")
    out_md.append("\nminor coverage on noyzhang (effect heterogeneity / qualitative findings).\n")

    # Per-paper averages
    out_md.append("\n## Per-paper means (3 seeds each)\n")
    out_md.append("\n| Paper | seeds | core mean | core seeds | minor mean | minor seeds | claims | duration (s) | cost ($) |\n")
    out_md.append("|-------|------:|----------:|------------|-----------:|-------------|-------:|-------------:|---------:|\n")

    paper_means = {}
    for paper in PAPERS:
        runs = by_paper[paper]
        if not runs:
            continue
        cores = [r["cov_core"] for r in runs if r["cov_core"] is not None]
        minors = [r["cov_minor"] for r in runs if r["cov_minor"] is not None]
        durs = [r["duration_s"] for r in runs]
        costs = [r["cost"] for r in runs]
        claims = [r["claims"] for r in runs]
        paper_means[paper] = {
            "core": statistics.mean(cores) if cores else 0,
            "minor": statistics.mean(minors) if minors else 0,
            "n": len(runs),
        }
        core_str = " / ".join(f"{c*100:.0f}%" for c in cores)
        minor_str = " / ".join(f"{c*100:.0f}%" for c in minors)
        out_md.append(
            f"| {paper} | {len(runs)} | "
            f"**{paper_means[paper]['core']*100:.0f}%** | {core_str} | "
            f"**{paper_means[paper]['minor']*100:.0f}%** | {minor_str} | "
            f"{statistics.mean(claims):.1f} | {statistics.mean(durs):.0f} | "
            f"${statistics.mean(costs):.3f} |\n"
        )

    # Comparison table vs v0.16b and v0.13d
    out_md.append("\n## Pareto comparison: v0.16b vs v0.13d vs v0.16b-hg\n")
    out_md.append("\n| Paper | v0.16b core | v0.13d core | **v0.16b-hg core** | v0.16b minor | v0.13d minor | **v0.16b-hg minor** |\n")
    out_md.append("|-------|------------:|------------:|-------------------:|-------------:|-------------:|--------------------:|\n")

    deltas = {}
    for paper in PAPERS:
        v16b_core, v16b_minor = REF[paper]["v0.16b"]
        v13d_core, v13d_minor = REF[paper]["v0.13d"]
        hg_core = paper_means[paper]["core"]
        hg_minor = paper_means[paper]["minor"]
        deltas[paper] = {
            "core_vs_v16b":  hg_core - v16b_core,
            "minor_vs_v16b": hg_minor - v16b_minor,
            "core_vs_v13d":  hg_core - v13d_core,
            "minor_vs_v13d": hg_minor - v13d_minor,
        }
        out_md.append(
            f"| {paper} | "
            f"{v16b_core*100:.0f}% | {v13d_core*100:.0f}% | "
            f"**{hg_core*100:.0f}%** | "
            f"{v16b_minor*100:.0f}% | {v13d_minor*100:.0f}% | "
            f"**{hg_minor*100:.0f}%** |\n"
        )

    out_md.append("\n### Delta vs v0.16b (positive = v0.16b-hg better)\n\n")
    out_md.append("| Paper | core delta | minor delta |\n|---|---:|---:|\n")
    for paper in PAPERS:
        d = deltas[paper]
        out_md.append(f"| {paper} | {d['core_vs_v16b']*100:+.0f}pp | {d['minor_vs_v16b']*100:+.0f}pp |\n")

    out_md.append("\n### Delta vs v0.13d (positive = v0.16b-hg better)\n\n")
    out_md.append("| Paper | core delta | minor delta |\n|---|---:|---:|\n")
    for paper in PAPERS:
        d = deltas[paper]
        out_md.append(f"| {paper} | {d['core_vs_v13d']*100:+.0f}pp | {d['minor_vs_v13d']*100:+.0f}pp |\n")

    # Items of interest — did v0.16b-hg catch them?
    out_md.append("\n## Items of interest: v0.16b-hg catches what v0.16b missed?\n")
    out_md.append("\n| Paper | Item | seed1 | seed2 | seed3 | hit rate |\n")
    out_md.append("|-------|------|:-----:|:-----:|:-----:|---------:|\n")
    for paper in PAPERS:
        runs = by_paper[paper]
        interest_key = INTEREST.get(paper)
        if not interest_key:
            continue
        hits = []
        cells = []
        for seed in SEEDS:
            run = next((r for r in runs if r["seed"] == seed), None)
            if run is None:
                cells.append("N/A")
                continue
            m = run["interest_matched"]
            cells.append("[+]" if m else "[-]")
            hits.append(m)
        hit_rate = sum(1 for h in hits if h) / len(hits) if hits else 0
        out_md.append(f"| {paper} | `{interest_key}` | {cells[0]} | {cells[1]} | {cells[2]} | {hit_rate*100:.0f}% ({sum(hits)}/{len(hits)}) |\n")

    # Aggregate cost / duration / tokens across all 9 runs
    all_runs = [r for runs in by_paper.values() for r in runs]
    total_cost = sum(r["cost"] for r in all_runs)
    total_dur = sum(r["duration_s"] for r in all_runs)
    total_in = sum(r["in_tok"] for r in all_runs)
    total_out = sum(r["out_tok"] for r in all_runs)

    out_md.append("\n## Aggregate cost / duration / tokens (9 runs)\n\n")
    out_md.append(f"- **Total cost**: ${total_cost:.3f}\n")
    out_md.append(f"- **Total duration**: {total_dur:.0f}s ({total_dur/60:.1f} min)\n")
    out_md.append(f"- **Total input tokens** (incl cache create + cache read): {total_in:,}\n")
    out_md.append(f"- **Total output tokens**: {total_out:,}\n")
    out_md.append(f"- **Total tokens**: {total_in + total_out:,}\n")
    out_md.append(f"- **Mean per-run cost**: ${total_cost/len(all_runs):.3f}\n")
    out_md.append(f"- **Mean per-run duration**: {total_dur/len(all_runs):.0f}s\n")

    # Strategic verdict — answer the questions
    out_md.append("\n## Strategic verdict\n\n")
    nz_minor_v16b = REF["noyzhang"]["v0.16b"][1]
    nz_minor_v13d = REF["noyzhang"]["v0.13d"][1]
    nz_minor_hg = paper_means["noyzhang"]["minor"]
    delta_vs_v16b = nz_minor_hg - nz_minor_v16b
    # "Closed" = within rounding of v0.13d (the better baseline) AND clearly above v0.16b
    nz_minor_gap_closed_v16b = delta_vs_v16b > 0.05  # >5pp improvement
    nz_minor_gap_closed_v13d = nz_minor_hg >= nz_minor_v13d - 0.01

    out_md.append(f"### Q1: Did v0.16b-hg close the noyzhang minor gap?\n\n")
    out_md.append(f"- v0.16b minor on noyzhang (baseline being patched): **{nz_minor_v16b*100:.0f}%**\n")
    out_md.append(f"- v0.13d minor on noyzhang (ceiling target): **{nz_minor_v13d*100:.0f}%**\n")
    out_md.append(f"- v0.16b-hg minor on noyzhang: **{nz_minor_hg*100:.1f}%**\n")
    out_md.append(f"- Delta vs v0.16b: **{delta_vs_v16b*100:+.1f} pp**\n")
    out_md.append(f"- Delta vs v0.13d: **{(nz_minor_hg - nz_minor_v13d)*100:+.1f} pp**\n")
    if nz_minor_gap_closed_v13d:
        verdict = "YES — fully closed (matches v0.13d)"
    elif nz_minor_gap_closed_v16b:
        verdict = "PARTIAL — beats v0.16b but does not reach v0.13d ceiling"
    else:
        verdict = "**NO** — essentially flat vs v0.16b; the 20pp gap to v0.13d remains"
    out_md.append(f"- Gap closed? {verdict}\n")

    # Pareto check vs v0.16b
    pareto_v16b_dom = all(
        deltas[p]["core_vs_v16b"] >= -0.0001 and deltas[p]["minor_vs_v16b"] >= -0.0001
        for p in PAPERS
    )
    pareto_v16b_strict = pareto_v16b_dom and any(
        deltas[p]["core_vs_v16b"] > 0.0001 or deltas[p]["minor_vs_v16b"] > 0.0001
        for p in PAPERS
    )
    pareto_v13d_dom = all(
        deltas[p]["core_vs_v13d"] >= -0.0001 and deltas[p]["minor_vs_v13d"] >= -0.0001
        for p in PAPERS
    )
    pareto_v13d_strict = pareto_v13d_dom and any(
        deltas[p]["core_vs_v13d"] > 0.0001 or deltas[p]["minor_vs_v13d"] > 0.0001
        for p in PAPERS
    )

    out_md.append(f"\n### Q2: Pareto-better than v0.16b on these 3 papers?\n\n")
    out_md.append(f"- Weakly Pareto-dominates v0.16b (no axis worse): **{'YES' if pareto_v16b_dom else 'NO'}**\n")
    out_md.append(f"- Strictly Pareto-better (>=1 axis strictly higher, none lower): **{'YES' if pareto_v16b_strict else 'NO'}**\n")

    out_md.append(f"\n### Q3: Pareto-better than v0.13d on these 3 papers?\n\n")
    out_md.append(f"- Weakly Pareto-dominates v0.13d: **{'YES' if pareto_v13d_dom else 'NO'}**\n")
    out_md.append(f"- Strictly Pareto-better: **{'YES' if pareto_v13d_strict else 'NO'}**\n")

    # Summary of where it underperforms
    out_md.append("\n### Where does v0.16b-hg underperform?\n\n")
    underperform = []
    for paper in PAPERS:
        d = deltas[paper]
        for variant in ("v16b", "v13d"):
            ref_label = "v0.16b" if variant == "v16b" else "v0.13d"
            for axis_label, axis_key in [("core", f"core_vs_{variant}"), ("minor", f"minor_vs_{variant}")]:
                val = d[axis_key]
                if val < -0.0001:
                    underperform.append((paper, ref_label, axis_label, val))
    if underperform:
        for paper, ref_label, axis_label, val in underperform:
            out_md.append(f"- {paper}: {axis_label} is **{val*100:+.0f}pp** vs {ref_label}\n")
    else:
        out_md.append("None — v0.16b-hg matches or exceeds both baselines on every (paper, axis) cell.\n")

    # Per-run details — append at bottom
    out_md.append("\n## Appendix: per-run detail\n\n")
    for paper in PAPERS:
        out_md.append(f"\n### {paper}\n\n")
        for run in by_paper[paper]:
            out_md.append(f"- **{run['run_dir']}**: cov_overall={run['cov_overall']*100:.0f}%, "
                          f"core={run['cov_core']*100:.0f}%, minor={run['cov_minor']*100:.0f}%, "
                          f"claims={run['claims']}, dur={run['duration_s']:.0f}s, cost=${run['cost']:.3f}\n")

    md_text = "".join(out_md)

    out_path = ROOT / "experiments" / "V016BHG_TARGETED_TEST.md"
    out_path.write_text(md_text, encoding="utf-8")
    print(f"Wrote: {out_path}")
    print()
    print(md_text)


if __name__ == "__main__":
    main()
