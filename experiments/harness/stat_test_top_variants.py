"""Paired statistical significance test on top broad-panel variants.

Pairs tested: (v0.16b, v0.13d), (v0.16b, v0.13 bare), (v0.13d, v0.13 bare).
For each pair, we collect per-paper means of cov_core and cov_minor across
all 13 papers, compute paper-level deltas (n=13), and report:
  1. Mean delta + 95% bootstrap CI (1000 resamples)
  2. p-value (Wilcoxon signed-rank if scipy, else paired permutation)
  3. Significance at alpha=0.05.
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

# Reuse variant detection + scoring from analyze_weighted_coverage_v2.
from analyze_weighted_coverage_v2 import (  # type: ignore
    GOLDS,
    paper_from_run_dir,
    score_weighted,
    variant_from_dir,
)

try:
    from scipy import stats as scipy_stats  # type: ignore
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False


PAIRS = [
    ("v0.16b", "v0.13d"),
    ("v0.16b", "v0.13"),
    ("v0.13d", "v0.13"),
]
ALPHA = 0.05
BOOT_N = 1000
PERM_N = 10000  # only used if scipy missing


def collect_cells() -> dict[str, dict[str, list[dict]]]:
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
        paper = paper_from_run_dir(d.name)
        if paper is None or paper not in GOLDS:
            continue
        sw = score_weighted(ext, ROOT / GOLDS[paper])
        if sw is None:
            continue
        cells[variant][paper].append(sw)
    return cells


def paper_means(cells: dict, variant: str, metric: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for paper, runs in cells.get(variant, {}).items():
        vals = [r[metric] for r in runs if r.get(metric) is not None]
        if vals:
            out[paper] = statistics.mean(vals)
    return out


def paired_deltas(a: dict[str, float], b: dict[str, float]) -> tuple[list[str], list[float]]:
    common = sorted(set(a) & set(b))
    deltas = [a[p] - b[p] for p in common]
    return common, deltas


def bootstrap_ci(deltas: list[float], n_boot: int = BOOT_N, alpha: float = 0.05,
                  seed: int = 42) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return (float("nan"), float("nan"))
    means = []
    for _ in range(n_boot):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return (lo, hi)


def perm_test_paired(deltas: list[float], n_perm: int = PERM_N,
                      seed: int = 7) -> float:
    """Paired permutation test: randomly flip signs of each delta."""
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return float("nan")
    obs = abs(sum(deltas) / n)
    count = 0
    for _ in range(n_perm):
        s = sum(d * (1 if rng.random() < 0.5 else -1) for d in deltas)
        if abs(s / n) >= obs - 1e-12:
            count += 1
    # +1 smoothing to avoid p=0
    return (count + 1) / (n_perm + 1)


def pvalue_wilcoxon_or_perm(deltas: list[float]) -> tuple[float, str]:
    n_nonzero = sum(1 for d in deltas if d != 0)
    if HAVE_SCIPY and n_nonzero >= 1:
        try:
            res = scipy_stats.wilcoxon(deltas, zero_method="wilcox",
                                         alternative="two-sided",
                                         method="auto")
            return float(res.pvalue), "wilcoxon"
        except Exception:
            pass
    return perm_test_paired(deltas), "perm"


def fmt_pct(x: float) -> str:
    return f"{x*100:+.2f}pp"


def fmt_ci(lo: float, hi: float) -> str:
    return f"[{lo*100:+.2f}, {hi*100:+.2f}]pp"


def main() -> None:
    print("# Paired statistical significance test - top broad-panel variants")
    print()
    print(f"scipy available: {HAVE_SCIPY}  | bootstrap_n={BOOT_N}")
    print()
    cells = collect_cells()

    # Sanity: papers covered by each variant
    for v in {x for pair in PAIRS for x in pair}:
        ps = sorted(cells.get(v, {}).keys())
        print(f"{v}: {len(ps)} papers - {ps}")
    print()

    print("| Pair | Metric | n | Mean delta | 95% CI (bootstrap) | p-value | Sig (a=0.05) |")
    print("|------|--------|--:|-----------:|-------------------:|--------:|:-------------|")

    results = []
    for a_var, b_var in PAIRS:
        for metric in ("cov_core", "cov_minor"):
            a_means = paper_means(cells, a_var, metric)
            b_means = paper_means(cells, b_var, metric)
            papers, deltas = paired_deltas(a_means, b_means)
            n = len(deltas)
            if n == 0:
                print(f"| {a_var} vs {b_var} | {metric} | 0 | -- | -- | -- | -- |")
                continue
            mean_d = statistics.mean(deltas)
            ci_lo, ci_hi = bootstrap_ci(deltas)
            pval, method = pvalue_wilcoxon_or_perm(deltas)
            sig = "YES" if pval < ALPHA else "no"
            print(f"| {a_var} vs {b_var} | {metric} | {n} | "
                  f"{fmt_pct(mean_d)} | {fmt_ci(ci_lo, ci_hi)} | "
                  f"{pval:.4f} ({method}) | {sig} |")
            results.append({
                "pair": f"{a_var} vs {b_var}",
                "metric": metric,
                "n": n,
                "papers": papers,
                "deltas": deltas,
                "mean_delta": mean_d,
                "ci": (ci_lo, ci_hi),
                "pvalue": pval,
                "method": method,
                "sig": pval < ALPHA,
            })

    # Detailed per-paper deltas
    print()
    print("## Per-paper deltas")
    for r in results:
        print()
        print(f"### {r['pair']} - {r['metric']} (n={r['n']})")
        print(f"papers (paired): {r['papers']}")
        print(f"deltas (pp): {[round(d*100, 1) for d in r['deltas']]}")

    # Final verdict
    print()
    print("## Verdict")
    for r in results:
        verdict = "REAL effect" if r["sig"] else "noise"
        print(f"- {r['pair']} | {r['metric']}: mean={fmt_pct(r['mean_delta'])}, "
              f"p={r['pvalue']:.4f} -> {verdict}")


if __name__ == "__main__":
    main()
