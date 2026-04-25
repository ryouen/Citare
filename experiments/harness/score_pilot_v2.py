"""Score the v2 pilot: 3 variants × 3 papers × 2 runs.

Produces PILOT_V2.md with per-cell mean/std and per-variant per-paper
aggregates. Addresses the N=1 and single-paper limitations of v0.1.
"""
from __future__ import annotations

import glob
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))

from score_against_gold import score  # type: ignore

# Pilot matrix: variant × paper × all run-id prefixes that populate each cell
CELLS: dict[tuple[str, str], list[str]] = {
    # (variant, paper) -> list of run-id substrings (N=3 where available)
    ("v0.3",  "T7"):        ["R38B_v03_trap_T7", "R41E_v03_T7_s2", "R43D_v03_T7_s3"],
    ("v0.3",  "einstein"):  ["R41A_v03_einstein_s1", "R41B_v03_einstein_s2", "R43L_v03_einstein_s3"],
    ("v0.3",  "edmondson"): ["R41C_v03_edmondson_s1", "R41D_v03_edmondson_s2", "R43M_v03_edmondson_s3"],
    ("v0.11", "T7"):        ["R38D_v11_trap_T7", "R41F_v11_T7_s2", "R43E_v11_T7_s3"],
    ("v0.11", "einstein"):  ["R36A_v11_einstein", "R41G_v11_einstein_s2", "R43N_v11_einstein_s3"],
    ("v0.11", "edmondson"): ["R36D_v11_edmondson", "R41H_v11_edmondson_s2", "R43O_v11_edmondson_s3"],
    ("v0.12e","T7"):        ["R39E_v12e_status_T7", "R41I_v12e_T7_s2", "R43F_v12e_T7_s3"],
    ("v0.12e","einstein"):  ["R40A_v12e_einstein", "R41J_v12e_einstein_s2", "R43P_v12e_einstein_s3"],
    ("v0.12e","edmondson"): ["R40B_v12e_edmondson", "R41K_v12e_edmondson_s2", "R43Q_v12e_edmondson_s3"],
    # v0.13 added with N=3
    ("v0.13", "T7"):        ["R43A_v13_T7_s1", "R43B_v13_T7_s2", "R43C_v13_T7_s3"],
    ("v0.13", "einstein"):  ["R43G_v13_einstein_s1", "R43H_v13_einstein_s2", "R43I_v13_einstein_s3"],
    ("v0.13", "edmondson"): ["R42B_v13_edmondson", "R43J_v13_edmondson_s2", "R43K_v13_edmondson_s3"],
}

# Which gold file to use per paper
GOLDS = {
    "T7":        ROOT / "experiments/ground_truth/trap_papers/T7_gold.json",
    "einstein":  ROOT / "experiments/ground_truth/real_papers/einstein_1905_gold.json",
    "edmondson": ROOT / "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
}


def find_run(run_id_part: str) -> Path | None:
    matches = sorted((ROOT / "experiments" / "runs").glob(f"*_{run_id_part}"))
    return matches[-1] if matches else None


def _fmt(m: float | None) -> str:
    if m is None:
        return "n/a"
    return f"{m*100:.1f}%" if m <= 1.0 else f"{m:.1f}"


def main() -> None:
    all_rows = []
    for (variant, paper), run_ids in CELLS.items():
        gold = GOLDS[paper]
        scores = []
        for rid in run_ids:
            rd = find_run(rid)
            if rd is None:
                continue
            ext = rd / "extraction.json"
            if not ext.exists():
                continue
            res = score(ext, gold)
            scores.append({
                "run_id": rid,
                "run_dir": rd.name,
                "axes": res["axes"],
                "eqs_captured": res["equations_captured"],
            })
        all_rows.append({
            "variant": variant,
            "paper": paper,
            "runs": scores,
            "n_runs": len(scores),
        })

    # ----- Build report -----
    out = []
    out.append("# Pilot v2 Results (3 variants × 3 papers × up to 2 runs)\n")
    out.append("Addresses v0.1 tournament's N=1 and single-paper limitations.\n")

    # Table 1: per-cell mean (over the N runs in that cell)
    out.append("## Per-cell means\n")
    out.append("| Variant | Paper | N | coverage | core_eq | discipline | eqs |")
    out.append("|---------|-------|---|----------|---------|------------|-----|")
    for r in all_rows:
        n = r["n_runs"]
        if n == 0:
            out.append(f"| {r['variant']} | {r['paper']} | 0 | — | — | — | — |")
            continue

        covs = [s["axes"]["coverage"] for s in r["runs"]]
        cores = [s["axes"]["core_eq_fidelity"] for s in r["runs"]]
        discs = [s["axes"]["eq_discipline"] for s in r["runs"] if s["axes"]["eq_discipline"] is not None]
        eqs = [s["eqs_captured"] for s in r["runs"]]

        cov_m = statistics.mean(covs) if covs else None
        cov_s = statistics.stdev(covs) if len(covs) > 1 else 0.0
        core_m = statistics.mean(cores) if cores else None
        core_s = statistics.stdev(cores) if len(cores) > 1 else 0.0
        disc_m = statistics.mean(discs) if discs else None
        eq_m = statistics.mean(eqs) if eqs else 0

        def fs(m: float | None, s: float = 0.0) -> str:
            if m is None:
                return "n/a"
            return f"{m*100:.1f}%±{s*100:.1f}"

        out.append(
            f"| {r['variant']} | {r['paper']} | {n} | "
            f"{fs(cov_m, cov_s)} | {fs(core_m, core_s)} | {fs(disc_m)} | {eq_m:.0f} |"
        )
    out.append("")

    # Table 2: per-variant across-paper roll-up
    out.append("## Per-variant aggregate (averaged across papers)\n")
    out.append("| Variant | coverage | core_eq | discipline | runs total |")
    out.append("|---------|----------|---------|------------|------------|")
    by_variant: dict[str, list] = {}
    for r in all_rows:
        by_variant.setdefault(r["variant"], []).extend(r["runs"])
    for variant, scores in by_variant.items():
        if not scores:
            continue
        covs = [s["axes"]["coverage"] for s in scores]
        cores = [s["axes"]["core_eq_fidelity"] for s in scores]
        discs = [s["axes"]["eq_discipline"] for s in scores if s["axes"]["eq_discipline"] is not None]

        out.append(
            f"| {variant} | {statistics.mean(covs)*100:.1f}%±{(statistics.stdev(covs) if len(covs)>1 else 0)*100:.1f} | "
            f"{statistics.mean(cores)*100:.1f}%±{(statistics.stdev(cores) if len(cores)>1 else 0)*100:.1f} | "
            f"{statistics.mean(discs)*100:.1f}%±{(statistics.stdev(discs) if len(discs)>1 else 0)*100:.1f} | "
            f"{len(scores)} |"
        )
    out.append("")

    # Noise assessment
    out.append("## Noise check: within-cell std\n")
    out.append("If within-cell std is small relative to between-variant mean differences, rankings are reliable.\n")
    out.append("| Cell | cov std | core_eq std | rank-stable? |")
    out.append("|------|---------|-------------|--------------|")
    for r in all_rows:
        if r["n_runs"] < 2:
            out.append(f"| {r['variant']}/{r['paper']} | n=1 | n=1 | — |")
            continue
        covs = [s["axes"]["coverage"] for s in r["runs"]]
        cores = [s["axes"]["core_eq_fidelity"] for s in r["runs"]]
        cov_s = statistics.stdev(covs)
        core_s = statistics.stdev(cores)
        stable = "OK" if max(cov_s, core_s) < 0.05 else "HIGH VARIANCE"
        out.append(
            f"| {r['variant']}/{r['paper']} | {cov_s*100:.1f}pp | {core_s*100:.1f}pp | {stable} |"
        )
    out.append("")

    # Write output
    rpath = ROOT / "experiments" / "PILOT_V2.md"
    rpath.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))
    print(f"\nsaved -> {rpath}")


if __name__ == "__main__":
    main()
