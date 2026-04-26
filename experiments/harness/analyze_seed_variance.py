"""Seed-to-seed variance analysis for top broad-panel variants.

For each (variant, paper) cell with N >= 3 seeds, compute std-dev of cov_core.
Identify:
  1. HIGH-variance cells (std > 0.10) — noisy, mean unreliable
  2. Whether the v0.16b vs v0.13d 0.3pp gap is within typical noise
  3. Per-paper "stable" vs "unstable" classification

Reuses score_against_gold and the directory-based variant detection from
analyze_weighted_coverage_v2.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from analyze_weighted_coverage_v2 import (  # type: ignore
    GOLDS,
    paper_from_run_dir,
    score_weighted,
    variant_from_dir,
)

# Variants of interest
TARGET_VARIANTS = {"v0.16b", "v0.13d", "v0.13", "v0.12e", "v0.16e"}


def main() -> None:
    # cells[variant][paper] = list of cov_core values
    cells: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cells_all: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    cells_minor: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for d in sorted((ROOT / "experiments" / "runs").iterdir()):
        if not d.is_dir():
            continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            continue
        variant = variant_from_dir(d.name)
        if variant not in TARGET_VARIANTS:
            continue
        paper = paper_from_run_dir(d.name)
        if paper is None or paper not in GOLDS:
            continue

        sw = score_weighted(ext, ROOT / GOLDS[paper])
        if sw is None:
            continue
        if sw["cov_core"] is not None:
            cells[variant][paper].append(sw["cov_core"])
        cells_all[variant][paper].append(sw["cov_overall"])
        if sw["cov_minor"] is not None:
            cells_minor[variant][paper].append(sw["cov_minor"])

    # --- Output ---
    out: list[str] = []
    out.append("# Seed-to-seed variance analysis: top broad-panel variants")
    out.append("")
    out.append("Variants analyzed: v0.16b, v0.13d, v0.13 (bare), v0.12e, v0.16e")
    out.append("Metric: std-dev of `cov_core` across seeds within each (variant, paper) cell.")
    out.append("Threshold for 'HIGH variance' (noisy): std-dev > 0.10")
    out.append("")

    # --- Per-cell variance table ---
    out.append("## Per-cell std-dev of cov_core (cells with N >= 3 seeds)")
    out.append("")
    out.append("| Variant | Paper | N seeds | Mean cov_core | Std-dev | Min | Max | Range | Status |")
    out.append("|---------|-------|--------:|--------------:|--------:|----:|----:|------:|--------|")

    high_var_cells: list[tuple[str, str, float, float, int]] = []
    all_stds: list[float] = []
    by_variant_stats: dict[str, list[tuple[str, int, float, float]]] = defaultdict(list)
    by_paper_stats: dict[str, list[tuple[str, int, float, float]]] = defaultdict(list)

    for variant in sorted(TARGET_VARIANTS):
        for paper in sorted(cells.get(variant, {}).keys()):
            vals = cells[variant][paper]
            n = len(vals)
            if n < 3:
                continue
            mean = statistics.mean(vals)
            std = statistics.stdev(vals)
            mn = min(vals)
            mx = max(vals)
            rng = mx - mn
            status = "HIGH" if std > 0.10 else ("med" if std > 0.05 else "low")
            if std > 0.10:
                high_var_cells.append((variant, paper, mean, std, n))
            all_stds.append(std)
            by_variant_stats[variant].append((paper, n, mean, std))
            by_paper_stats[paper].append((variant, n, mean, std))
            out.append(
                f"| {variant} | {paper} | {n} | {mean*100:.1f}% | "
                f"{std*100:.1f}pp | {mn*100:.0f}% | {mx*100:.0f}% | "
                f"{rng*100:.1f}pp | **{status}** |"
            )

    out.append("")

    # --- High-variance cells ---
    out.append("## (1) HIGH-variance cells (std-dev > 0.10) - noisy, mean unreliable")
    out.append("")
    if not high_var_cells:
        out.append("None. All cells with >=3 seeds have std-dev <= 0.10.")
    else:
        out.append("| Variant | Paper | N | Mean | Std-dev |")
        out.append("|---------|-------|--:|-----:|--------:|")
        for v, p, m, s, n in sorted(high_var_cells, key=lambda x: -x[3]):
            out.append(f"| {v} | {p} | {n} | {m*100:.1f}% | **{s*100:.1f}pp** |")
    out.append("")

    # --- Aggregate noise floor ---
    out.append("## (2) Is the v0.16b vs v0.13d 0.3pp gap within noise?")
    out.append("")
    if all_stds:
        median_std = statistics.median(all_stds)
        mean_std = statistics.mean(all_stds)
        out.append(
            f"- Across all {len(all_stds)} (variant, paper) cells with N>=3 seeds:"
        )
        out.append(f"  - **Median seed std-dev: {median_std*100:.2f}pp**")
        out.append(f"  - Mean seed std-dev: {mean_std*100:.2f}pp")
        out.append(f"  - Max seed std-dev: {max(all_stds)*100:.2f}pp")
        out.append(f"  - Min seed std-dev: {min(all_stds)*100:.2f}pp")
        out.append("")

    # Compute per-paper std for v0.16b and v0.13d, and the per-paper delta
    out.append("### Per-paper v0.16b vs v0.13d head-to-head (cov_core)")
    out.append("")
    out.append(
        "| Paper | v0.16b mean (N) | v0.16b std | v0.13d mean (N) | v0.13d std | "
        "Delta (16b-13d) | Pooled std | |Delta|/pooled |"
    )
    out.append(
        "|-------|------------------|-----------:|------------------|-----------:|"
        "----------------:|-----------:|---------------:|"
    )
    common_papers = sorted(
        set(cells.get("v0.16b", {}).keys()) & set(cells.get("v0.13d", {}).keys())
    )
    deltas: list[tuple[str, float, float, int, int]] = []
    for paper in common_papers:
        a = cells["v0.16b"][paper]
        b = cells["v0.13d"][paper]
        if len(a) < 1 or len(b) < 1:
            continue
        ma, mb = statistics.mean(a), statistics.mean(b)
        sa = statistics.stdev(a) if len(a) >= 2 else 0.0
        sb = statistics.stdev(b) if len(b) >= 2 else 0.0
        # Pooled std (simple sqrt of mean of variances)
        if len(a) >= 2 and len(b) >= 2:
            pooled = ((sa**2 + sb**2) / 2) ** 0.5
        else:
            pooled = max(sa, sb)
        delta = ma - mb
        ratio = abs(delta) / pooled if pooled > 0 else float("inf") if delta != 0 else 0
        deltas.append((paper, delta, pooled, len(a), len(b)))
        ratio_s = "inf" if pooled == 0 and delta != 0 else f"{ratio:.2f}"
        out.append(
            f"| {paper} | {ma*100:.1f}% ({len(a)}) | {sa*100:.1f}pp | "
            f"{mb*100:.1f}% ({len(b)}) | {sb*100:.1f}pp | "
            f"{delta*100:+.1f}pp | {pooled*100:.1f}pp | {ratio_s} |"
        )
    out.append("")

    # Mean abs delta across papers
    if deltas:
        mean_delta = statistics.mean([d[1] for d in deltas])
        mean_abs_delta = statistics.mean([abs(d[1]) for d in deltas])
        # Aggregate-level: collapse to paper-means then global mean (matches v2 reporter)
        agg_a = statistics.mean(
            [statistics.mean(cells["v0.16b"][p]) for p in common_papers if cells["v0.16b"][p]]
        )
        agg_b = statistics.mean(
            [statistics.mean(cells["v0.13d"][p]) for p in common_papers if cells["v0.13d"][p]]
        )
        out.append(
            f"- **Aggregate per-paper-mean cov_core**: v0.16b={agg_a*100:.2f}% vs v0.13d={agg_b*100:.2f}% "
            f"-> delta = {(agg_a-agg_b)*100:+.2f}pp"
        )
        out.append(
            f"- Mean per-paper delta (16b - 13d): {mean_delta*100:+.2f}pp"
        )
        out.append(
            f"- Mean |per-paper delta|: {mean_abs_delta*100:.2f}pp"
        )
        if all_stds:
            verdict = (
                "WITHIN NOISE"
                if abs(mean_delta) < median_std
                else "MARGINAL (delta >= median noise)"
            )
            out.append(
                f"- **Verdict**: |aggregate delta| ({abs(agg_a-agg_b)*100:.2f}pp) "
                f"vs median seed std ({median_std*100:.2f}pp) -> "
                f"**{'WITHIN NOISE' if abs(agg_a-agg_b) < median_std else 'EXCEEDS MEDIAN NOISE'}**"
            )
            out.append(f"- Per-paper interpretation: {verdict}")
    out.append("")

    # --- Per-paper stability ---
    out.append("## (3) Per-paper stability classification")
    out.append("")
    out.append(
        "For each paper, average the seed std-dev across all 5 target variants "
        "(only cells with N>=3). Classify:"
    )
    out.append("- **stable**: avg std-dev <= 0.05 (5pp). Trust the mean.")
    out.append(
        "- **moderate**: 0.05 < avg <= 0.10. Caution; means probably ok but small "
        "deltas suspect."
    )
    out.append("- **unstable**: avg std-dev > 0.10. NEED more seeds.")
    out.append("")
    out.append("| Paper | Variants w/ N>=3 | Avg std-dev | Max std-dev | Status |")
    out.append("|-------|-----------------:|------------:|------------:|--------|")
    paper_summary = []
    for paper in sorted(by_paper_stats.keys()):
        rows = by_paper_stats[paper]
        if not rows:
            continue
        avg = statistics.mean([r[3] for r in rows])
        mx = max([r[3] for r in rows])
        status = (
            "**unstable**" if avg > 0.10 else "moderate" if avg > 0.05 else "stable"
        )
        paper_summary.append((paper, len(rows), avg, mx, status))
    paper_summary.sort(key=lambda r: -r[2])
    for paper, n_v, avg, mx, status in paper_summary:
        out.append(
            f"| {paper} | {n_v} | {avg*100:.2f}pp | {mx*100:.2f}pp | {status} |"
        )
    out.append("")

    # --- Per-variant stability ---
    out.append("## Per-variant stability (mean seed std across covered papers)")
    out.append("")
    out.append("| Variant | Cells w/ N>=3 | Avg std-dev | Max std-dev |")
    out.append("|---------|--------------:|------------:|------------:|")
    variant_summary = []
    for variant in sorted(by_variant_stats.keys()):
        rows = by_variant_stats[variant]
        if not rows:
            continue
        avg = statistics.mean([r[3] for r in rows])
        mx = max([r[3] for r in rows])
        variant_summary.append((variant, len(rows), avg, mx))
    variant_summary.sort(key=lambda r: r[2])
    for variant, n_c, avg, mx in variant_summary:
        out.append(f"| {variant} | {n_c} | {avg*100:.2f}pp | {mx*100:.2f}pp |")
    out.append("")

    # Strategic conclusion
    out.append("## Strategic conclusion")
    out.append("")
    if all_stds and deltas:
        agg_delta = abs(agg_a - agg_b) * 100
        med = median_std * 100
        if agg_delta < med:
            out.append(
                f"The reported v0.16b vs v0.13d cov_core gap ({agg_delta:.2f}pp on the per-paper-mean) "
                f"is **smaller than the median seed std-dev ({med:.2f}pp)**. "
                f"**The gap is consistent with seed noise** — within a single paper, "
                f"re-running v0.13d with a fresh seed could plausibly reproduce v0.16b's mean. "
                f"Decision-making between v0.16b and v0.13d should not rely on this delta alone."
            )
        else:
            out.append(
                f"The aggregate v0.16b vs v0.13d delta ({agg_delta:.2f}pp) **exceeds the median "
                f"seed std-dev ({med:.2f}pp)**. The gap is unlikely to be pure noise, but "
                f"it is small relative to the worst-case per-cell variance. Treat as suggestive, "
                f"not decisive."
            )
    out.append("")

    text = "\n".join(out)
    print(text)

    save_path = ROOT / "experiments" / "SEED_VARIANCE.md"
    save_path.write_text(text + "\n", encoding="utf-8")
    print(f"\n[saved to {save_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()
