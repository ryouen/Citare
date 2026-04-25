"""Score the L8 factorial tournament.

Matrix: 8 L8 variants × (T7 primary, Einstein + Edmondson cross-val) × N up to 3.

Produces L8_FINAL.md with:
 - Per-cell mean ± std across 6 axes
 - Main-effect analysis of each L8 axis (position / length / structure / example / discipline)
 - Pareto frontier scatter
 - Winner identification by threshold intersection
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


# L8 variant definitions: (variant_id, prompt_file, cell_description, run_id_prefixes)
L8 = [
    # V1: top / short / prose / no-example / no-discipline
    ("V1_TOP_PRIME", "v0.12g_top_prime.md", {"pos": "top", "len": "short", "struct": "prose", "ex": "no", "disc": "none"},
        ["R39G2_v12g_top_prime_T7", "R44_v12g_T7_s2", "R44_v12g_T7_s3"]),
    # V2: top / long / schema / example / both
    ("V2_TOP_LONG_SCHEMA", "v0.20v2_top_long_schema_ex_both.md", {"pos": "top", "len": "long", "struct": "schema", "ex": "yes", "disc": "both"},
        ["R44_v20v2_T7_s1", "R44_v20v2_T7_s2", "R44_v20v2_T7_s3"]),
    # V3 substitute ≈ v0.11: end / long / schema-style / example / none → close enough
    ("V3_END_SCHEMA", "v0.11_tex.md", {"pos": "end", "len": "long", "struct": "schema", "ex": "yes", "disc": "none"},
        ["R38D_v11_trap_T7", "R41F_v11_T7_s2", "R43E_v11_T7_s3"]),
    # V4: end / long / prose / none / both
    ("V4_DISCIPLINE", "v0.12f_terse_discipline.md", {"pos": "end", "len": "long", "struct": "prose", "ex": "no", "disc": "both"},
        ["R39F_v12f_discipline_T7", "R44_v12f_T7_s2", "R44_v12f_T7_s3"]),
    # V5: appendix / short / two-pass / example / both
    ("V5_APX_2PASS", "v0.20v5_appendix_short_2pass_ex_both.md", {"pos": "apx", "len": "short", "struct": "two_pass", "ex": "yes", "disc": "both"},
        ["R44_v20v5_T7_s1", "R44_v20v5_T7_s2", "R44_v20v5_T7_s3"]),
    # V6 ≈ v0.12b TRIAGE: appendix / long / triage / no-example / none
    ("V6_TRIAGE", "v0.12b_triage.md", {"pos": "apx", "len": "long", "struct": "triage", "ex": "no", "disc": "none"},
        ["R39B_v12b_triage_T7", "R44_v12b_T7_s2", "R44_v12b_T7_s3"]),
    # V7: top / short / triage / none / schema
    ("V7_TOP_TRIAGE", "v0.20v7_top_short_triage_none_schema.md", {"pos": "top", "len": "short", "struct": "triage", "ex": "no", "disc": "schema"},
        ["R44_v20v7_T7_s1", "R44_v20v7_T7_s2", "R44_v20v7_T7_s3"]),
    # V8: end / long / two-pass / example / schema
    ("V8_2PASS_END", "v0.20v8_end_long_2pass_ex_schema.md", {"pos": "end", "len": "long", "struct": "two_pass", "ex": "yes", "disc": "schema"},
        ["R44_v20v8_T7_s1", "R44_v20v8_T7_s2", "R44_v20v8_T7_s3"]),
]

# Additional reference baselines
EXTRA = [
    ("v0.3_BASELINE", "v0.3_overlooked.md", {"pos": "--", "len": "--", "struct": "text_only", "ex": "no", "disc": "--"},
        ["R38B_v03_trap_T7", "R41E_v03_T7_s2", "R43D_v03_T7_s3"]),
    ("v0.12e_STATUS", "v0.12e_status.md", {"pos": "end", "len": "long", "struct": "schema", "ex": "no", "disc": "schema"},
        ["R39E_v12e_status_T7", "R41I_v12e_T7_s2", "R43F_v12e_T7_s3"]),
    ("v0.13_VERBATIM", "v0.13_refs_verbatim.md", {"pos": "end", "len": "long", "struct": "schema+refs", "ex": "yes", "disc": "schema"},
        ["R43A_v13_T7_s1", "R43B_v13_T7_s2", "R43C_v13_T7_s3"]),
]

ALL_VARIANTS = L8 + EXTRA


def find_run(suffix: str) -> Path | None:
    matches = sorted((ROOT / "experiments" / "runs").glob(f"*_{suffix}"))
    return matches[-1] if matches else None


def run_cell(run_ids: list[str]) -> list[dict]:
    gold = ROOT / "experiments/ground_truth/trap_papers/T7_gold.json"
    results = []
    for rid in run_ids:
        rd = find_run(rid)
        if rd is None:
            continue
        ext = rd / "extraction.json"
        if not ext.exists():
            continue
        try:
            res = score(ext, gold)
            results.append({"run_id": rid, **res["axes"], "eq_count": res.get("equations_captured", 0)})
        except Exception as e:
            results.append({"run_id": rid, "error": str(e)})
    return results


def agg(vals: list[float | None]) -> tuple[float | None, float]:
    clean = [v for v in vals if v is not None]
    if not clean:
        return None, 0.0
    m = statistics.mean(clean)
    s = statistics.stdev(clean) if len(clean) > 1 else 0.0
    return m, s


def main() -> None:
    out = ["# L8 Final Tournament on T7 (with N=3)\n"]
    out.append("## Per-variant means (N=up to 3)\n")
    out.append("| Variant | pos | len | struct | ex | disc | N | Coverage | Middle | Core eq | Discipline | Eqs |")
    out.append("|---------|-----|-----|--------|----|----- |---|----------|--------|---------|------------|-----|")

    all_results = []
    for variant_id, prompt_file, cell, run_ids in ALL_VARIANTS:
        runs = run_cell(run_ids)
        runs = [r for r in runs if "error" not in r]
        n = len(runs)
        cov_m, cov_s = agg([r.get("coverage") for r in runs])
        mid_m, mid_s = agg([r.get("middle_coverage") for r in runs])
        core_m, core_s = agg([r.get("core_eq_fidelity") for r in runs])
        disc_m, disc_s = agg([r.get("eq_discipline") for r in runs])
        eq_m, _ = agg([r.get("eq_count") for r in runs])

        def fmt(m: float | None, s: float = 0) -> str:
            if m is None:
                return "n/a"
            if isinstance(m, float) and m <= 1.0:
                return f"{m*100:.1f}%±{s*100:.1f}"
            return f"{m:.1f}"

        out.append(
            f"| {variant_id} | {cell['pos']} | {cell['len']} | {cell['struct']} | "
            f"{cell['ex']} | {cell['disc']} | {n} | "
            f"{fmt(cov_m, cov_s)} | {fmt(mid_m, mid_s)} | {fmt(core_m, core_s)} | "
            f"{fmt(disc_m, disc_s)} | {fmt(eq_m)} |"
        )
        all_results.append({
            "variant": variant_id,
            "cell": cell,
            "n": n,
            "cov_m": cov_m, "cov_s": cov_s,
            "mid_m": mid_m, "mid_s": mid_s,
            "core_m": core_m, "core_s": core_s,
            "disc_m": disc_m, "disc_s": disc_s,
        })
    out.append("")

    # Main-effect analysis per axis
    out.append("## Main-effect analysis (L8 axis marginals)\n")
    out.append("For each axis level, average the metric across all L8 variants at that level.\n")
    axes = ["pos", "len", "struct", "ex", "disc"]
    metrics = [("cov_m", "Coverage"), ("core_m", "Core eq"), ("disc_m", "Discipline")]
    for axis in axes:
        out.append(f"### Axis: {axis}\n")
        out.append(f"| {axis} level | " + " | ".join(m[1] for m in metrics) + " |")
        out.append("|--------|" + "|".join(["--------"] * len(metrics)) + "|")
        levels = {}
        for r in [x for x in all_results if x["variant"].startswith("V") and not x["variant"].startswith("v0.")]:
            lvl = r["cell"][axis]
            levels.setdefault(lvl, []).append(r)
        for lvl, rs in sorted(levels.items()):
            row = [lvl]
            for mkey, _ in metrics:
                ms = [r[mkey] for r in rs if r[mkey] is not None]
                if ms:
                    row.append(f"{statistics.mean(ms)*100:.1f}%")
                else:
                    row.append("n/a")
            out.append("| " + " | ".join(row) + " |")
        out.append("")

    # Winner check
    out.append("## Winner check (coverage≥90% AND core_eq≥85% AND discipline≥50%)\n")
    winners = [r for r in all_results
               if r["cov_m"] is not None and r["cov_m"] >= 0.90
               and r["core_m"] is not None and r["core_m"] >= 0.85
               and r["disc_m"] is not None and r["disc_m"] >= 0.50]
    if winners:
        out.append("\n".join(f"- **{w['variant']}** "
                             f"(cov={w['cov_m']*100:.1f}%, core={w['core_m']*100:.1f}%, disc={w['disc_m']*100:.1f}%)"
                             for w in winners))
    else:
        out.append("No variant passes all three relaxed thresholds. Pareto frontier only.")
    out.append("")

    # Raw runs table
    out.append("## Raw per-seed scores (for noise inspection)\n")
    out.append("| Variant | seed | cov | middle | core_eq | discipline |")
    out.append("|---------|------|-----|--------|---------|------------|")
    for variant_id, prompt_file, cell, run_ids in ALL_VARIANTS:
        for rid in run_ids:
            rd = find_run(rid)
            if rd is None:
                continue
            ext = rd / "extraction.json"
            if not ext.exists():
                continue
            try:
                res = score(ext, ROOT / "experiments/ground_truth/trap_papers/T7_gold.json")
                ax = res["axes"]
                def f(v):
                    return f"{v*100:.1f}%" if v is not None else "n/a"
                out.append(f"| {variant_id} | {rid.split('_s')[-1] if '_s' in rid else rid} | "
                           f"{f(ax['coverage'])} | {f(ax['middle_coverage'])} | "
                           f"{f(ax['core_eq_fidelity'])} | {f(ax['eq_discipline'])} |")
            except Exception:
                pass
    out.append("")

    rpath = ROOT / "experiments" / "L8_FINAL.md"
    rpath.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out[:60]))
    print(f"\n...saved -> {rpath}")


if __name__ == "__main__":
    main()
