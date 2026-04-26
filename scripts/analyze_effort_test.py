"""Analyze R80 effort comparison: 3 papers × 4 efforts.

Outputs:
  - experiments/EFFORT_COMPARISON.md  (markdown report)
  - prints summary table + recommendation
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))

from score_against_gold import score  # type: ignore

GOLDS = {
    "edmondson":   "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
    "hayes":       "experiments/ground_truth/real_papers/hayes_2006_gold.json",
    "t7":          "experiments/ground_truth/trap_papers/T7_gold.json",
    "einstein":    "experiments/ground_truth/real_papers/einstein_1905_gold.json",
    "vaswani":     "experiments/ground_truth/real_papers/vaswani_2017_gold.json",
    "hubinger":    "experiments/ground_truth/real_papers/hubinger_2024_gold.json",
    "wei":         "experiments/ground_truth/real_papers/wei_2022_gold.json",
    "noyzhang":    "experiments/ground_truth/real_papers/noy_zhang_2023_gold.json",
}

def main() -> None:
    rows = []
    for d in sorted((ROOT / "experiments" / "runs").glob("*_R8[01]_v013d_*")):
        if not d.is_dir(): continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100: continue
        # Parse run-id format: R80_v013d_<paper>_eff<effort>_s1
        name = d.name
        # Find paper + effort
        import re
        m = re.search(r"_v013d_(\w+?)_eff(\w+?)_s\d+$", name)
        if not m:
            print(f"[skip] cannot parse: {name}", file=sys.stderr)
            continue
        paper = m.group(1)
        effort = m.group(2)
        if paper not in GOLDS:
            continue
        # Load metrics
        metr = d / "metrics.json"
        if not metr.exists(): continue
        m_data = json.loads(metr.read_text(encoding="utf-8"))
        cost = m_data.get("cost_usd", 0)
        dur = m_data.get("duration_sec", 0)
        in_tok = (m_data.get("input_tokens",0)
                  + m_data.get("cache_creation_input_tokens",0)
                  + m_data.get("cache_read_input_tokens",0))
        out_tok = m_data.get("output_tokens",0)
        claims = m_data.get("claim_counts", {}).get("total", 0)
        # Score
        try:
            res = score(ext, ROOT / GOLDS[paper])
        except Exception as e:
            print(f"[skip score] {name}: {e}", file=sys.stderr)
            continue
        ax = res.get("axes", {})
        rows.append({
            "paper": paper,
            "effort": effort,
            "dir": d.name,
            "cov": ax.get("coverage"),
            "ip": ax.get("integrity_penalty"),
            "core_eq_fid": ax.get("core_eq_fidelity"),
            "eq_disc": ax.get("eq_discipline"),
            "middle_cov": ax.get("middle_coverage"),
            "claims": claims,
            "cost": cost,
            "dur": dur,
            "in_tok": in_tok,
            "out_tok": out_tok,
        })

    if not rows:
        print("No R80 runs found")
        return

    # Pivot table
    EFFORTS = ["none", "low", "medium", "high"]
    PAPERS = sorted(set(r["paper"] for r in rows))

    by_pe = {(r["paper"], r["effort"]): r for r in rows}

    md_lines = ["# Effort comparison — empirical (R80, 2026-04-26)", "",
                "Test: v0.13d locked prompt × 3 papers × 4 effort levels (none/low/medium/high) = 12 runs.",
                "Each paper has gold for quantitative scoring.",
                ""]

    md_lines += ["## Per-paper × effort: coverage", "",
                 "| Paper | none | low | medium | high |",
                 "|-------|-----:|----:|-------:|-----:|"]
    for p in PAPERS:
        row = f"| {p} |"
        for e in EFFORTS:
            r = by_pe.get((p, e))
            if r and r["cov"] is not None:
                row += f" {r['cov']*100:.1f}% |"
            else:
                row += " — |"
        md_lines.append(row)

    md_lines += ["", "## Per-paper × effort: cost (USD)", "",
                 "| Paper | none | low | medium | high |",
                 "|-------|-----:|----:|-------:|-----:|"]
    for p in PAPERS:
        row = f"| {p} |"
        for e in EFFORTS:
            r = by_pe.get((p, e))
            row += f" ${r['cost']:.2f} |" if r else " — |"
        md_lines.append(row)

    md_lines += ["", "## Per-paper × effort: duration (s) + output tokens", "",
                 "| Paper | none | low | medium | high |",
                 "|-------|------|-----|--------|------|"]
    for p in PAPERS:
        row = f"| {p} |"
        for e in EFFORTS:
            r = by_pe.get((p, e))
            if r:
                row += f" {r['dur']:.0f}s/{r['out_tok']/1000:.0f}K |"
            else:
                row += " — |"
        md_lines.append(row)

    md_lines += ["", "## Per-paper × effort: claims emitted", "",
                 "| Paper | none | low | medium | high |",
                 "|-------|-----:|----:|-------:|-----:|"]
    for p in PAPERS:
        row = f"| {p} |"
        for e in EFFORTS:
            r = by_pe.get((p, e))
            row += f" {r['claims']} |" if r else " — |"
        md_lines.append(row)

    # Aggregate per-effort across papers
    md_lines += ["", "## Cross-paper aggregate per effort", "",
                 "| Effort | avg cov | avg cost | avg duration | avg out_tok | avg claims |",
                 "|--------|--------:|---------:|-------------:|------------:|-----------:|"]
    by_e = defaultdict(list)
    for r in rows: by_e[r["effort"]].append(r)
    import statistics as st
    for e in EFFORTS:
        runs = by_e.get(e, [])
        if not runs: continue
        cov_avg = st.mean([r["cov"] for r in runs if r["cov"] is not None])
        cost_avg = st.mean([r["cost"] for r in runs])
        dur_avg = st.mean([r["dur"] for r in runs])
        out_avg = st.mean([r["out_tok"] for r in runs])
        cl_avg = st.mean([r["claims"] for r in runs])
        md_lines.append(f"| **{e}** | {cov_avg*100:.1f}% | ${cost_avg:.2f} | {dur_avg:.0f}s | "
                       f"{out_avg/1000:.0f}K | {cl_avg:.1f} |")

    # Recommendation
    md_lines += ["", "## Recommendation", ""]
    # Find best-cov, best-cost-eff
    avg_per_e = {}
    for e in EFFORTS:
        runs = by_e.get(e, [])
        if not runs: continue
        cov_xs = [r["cov"] for r in runs if r["cov"] is not None]
        cost_xs = [r["cost"] for r in runs]
        avg_per_e[e] = {
            "cov": st.mean(cov_xs) if cov_xs else 0,
            "cost": st.mean(cost_xs),
        }
    if avg_per_e:
        best_cov = max(avg_per_e.items(), key=lambda x: x[1]["cov"])
        cheapest = min(avg_per_e.items(), key=lambda x: x[1]["cost"])
        md_lines.append(f"- **Highest coverage**: effort={best_cov[0]} "
                       f"({best_cov[1]['cov']*100:.1f}%, ${best_cov[1]['cost']:.2f}/run)")
        md_lines.append(f"- **Cheapest**: effort={cheapest[0]} "
                       f"({cheapest[1]['cov']*100:.1f}%, ${cheapest[1]['cost']:.2f}/run)")
        if best_cov[0] == cheapest[0]:
            md_lines.append(f"- → both metrics agree: **use effort={best_cov[0]}**")
        else:
            delta_cov = (best_cov[1]['cov'] - cheapest[1]['cov']) * 100
            delta_cost = best_cov[1]['cost'] - cheapest[1]['cost']
            md_lines.append(f"- Trade-off: +{delta_cov:.1f}pp cov costs +${delta_cost:.2f}/run "
                           f"(× expected n={1000} papers ≈ +${delta_cost*1000:.0f} for full corpus)")

    out = ROOT / "experiments" / "EFFORT_COMPARISON.md"
    out.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Wrote {out}")
    print()
    for line in md_lines:
        print(line)


if __name__ == "__main__":
    main()
