"""Analyze R82 grid: 6 papers × 3 efforts × 4 prompts = 72 runs.

Outputs:
  - experiments/R82_GRID_RESULTS.md (markdown report)
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
from score_against_gold import score  # type: ignore

GOLDS = {
    "noyzhang":  "experiments/ground_truth/real_papers/noy_zhang_2023_gold.json",
    "hubinger":  "experiments/ground_truth/real_papers/hubinger_2024_gold.json",
    "park":      "experiments/ground_truth/real_papers/park_2023_gold.json",
    "edmondson": "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
    "wei":       "experiments/ground_truth/real_papers/wei_2022_gold.json",
    "t7":        "experiments/ground_truth/trap_papers/T7_gold.json",
}

PAPERS = ["noyzhang", "hubinger", "park", "edmondson", "wei", "t7"]
EFFORTS = ["none", "low", "medium"]
PROMPTS = ["v013d", "v013f", "v013g", "v013h"]


def main():
    rows = []
    skipped = []
    for d in sorted((ROOT / "experiments" / "runs").glob("*_R82_*")):
        if not d.is_dir(): continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            skipped.append((d.name, "no extraction"))
            continue
        # Parse: R82_<promptkey>_<paper>_eff<effort>_s1
        m = re.search(r"_R82_(v013[a-z])_(\w+?)_eff(\w+?)_s\d+$", d.name)
        if not m:
            skipped.append((d.name, "name parse"))
            continue
        prompt, paper, effort = m.group(1), m.group(2), m.group(3)
        if paper not in GOLDS:
            skipped.append((d.name, f"unknown paper {paper}"))
            continue
        metr = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
        try:
            res = score(ext, ROOT / GOLDS[paper])
        except Exception as e:
            skipped.append((d.name, f"score fail: {e}"))
            continue
        ax = res.get("axes", {})
        rows.append({
            "paper": paper, "effort": effort, "prompt": prompt,
            "dir": d.name,
            "cov": ax.get("coverage"),
            "ip": ax.get("integrity_penalty"),
            "claims": metr.get("claim_counts", {}).get("total", 0),
            "exist_claims": metr.get("claim_counts", {}).get("EXISTENCE_CLAIM", 0),
            "rel_claims": metr.get("claim_counts", {}).get("RELATION", 0),
            "cost": metr.get("cost_usd", 0),
            "dur": metr.get("duration_sec", 0),
            "out_tok": metr.get("output_tokens", 0),
        })

    print(f"Loaded {len(rows)} valid runs (skipped {len(skipped)})")
    if skipped:
        for name, reason in skipped[:5]:
            print(f"  skip: {name}: {reason}")

    by_cell = {(r["paper"], r["effort"], r["prompt"]): r for r in rows}

    md = ["# R82 Grid Results: 6 papers × 3 efforts × 4 prompts (72 runs)", "",
          "Test: which prompt × effort combo recovers noyzhang regression while preserving hubinger/wei gains?",
          "",
          "**Prompt axis:**",
          "- v013d: baseline (current production)",
          "- v013f: pre-extraction declarative rule (EXISTENCE preservation)",
          "- v013g: extended-thinking-specific anti-compression rule",
          "- v013h: post-extraction self-check + completeness verification",
          ""]

    # ===== Coverage tables: one per paper, prompt × effort =====
    md += ["## Coverage by paper (prompt × effort)", ""]
    for paper in PAPERS:
        md += [f"### {paper}", "",
               f"| prompt | none | low | medium |",
               "|--------|-----:|----:|-------:|"]
        for prompt in PROMPTS:
            cells = []
            for eff in EFFORTS:
                r = by_cell.get((paper, eff, prompt))
                if r and r["cov"] is not None:
                    cells.append(f"{r['cov']*100:.1f}%")
                else:
                    cells.append("—")
            md.append(f"| {prompt} | {' | '.join(cells)} |")
        md.append("")

    # ===== Per-prompt aggregate =====
    md += ["## Cross-paper aggregate per prompt × effort", "",
           "| prompt | none | low | medium |",
           "|--------|-----:|----:|-------:|"]
    for prompt in PROMPTS:
        cells = []
        for eff in EFFORTS:
            covs = [r["cov"] for r in rows
                    if r["prompt"] == prompt and r["effort"] == eff and r["cov"] is not None]
            if covs:
                cells.append(f"{st.mean(covs)*100:.1f}%")
            else:
                cells.append("—")
        md.append(f"| {prompt} | {' | '.join(cells)} |")
    md.append("")

    # ===== Per-prompt grand mean =====
    md += ["## Per-prompt grand mean (across all efforts × papers)", "",
           "| prompt | avg cov | avg cost | avg duration | avg claims | avg EXIST | avg REL |",
           "|--------|--------:|---------:|-------------:|-----------:|----------:|--------:|"]
    for prompt in PROMPTS:
        prows = [r for r in rows if r["prompt"] == prompt and r["cov"] is not None]
        if not prows: continue
        md.append(f"| **{prompt}** | "
                  f"{st.mean([r['cov'] for r in prows])*100:.1f}% | "
                  f"${st.mean([r['cost'] for r in prows]):.2f} | "
                  f"{st.mean([r['dur'] for r in prows]):.0f}s | "
                  f"{st.mean([r['claims'] for r in prows]):.1f} | "
                  f"{st.mean([r['exist_claims'] for r in prows]):.1f} | "
                  f"{st.mean([r['rel_claims'] for r in prows]):.1f} |")
    md.append("")

    # ===== Per-effort grand mean =====
    md += ["## Per-effort grand mean (across all prompts × papers)", "",
           "| effort | avg cov | avg cost | avg claims | avg EXIST |",
           "|--------|--------:|---------:|-----------:|----------:|"]
    for eff in EFFORTS:
        erows = [r for r in rows if r["effort"] == eff and r["cov"] is not None]
        if not erows: continue
        md.append(f"| **{eff}** | "
                  f"{st.mean([r['cov'] for r in erows])*100:.1f}% | "
                  f"${st.mean([r['cost'] for r in erows]):.2f} | "
                  f"{st.mean([r['claims'] for r in erows]):.1f} | "
                  f"{st.mean([r['exist_claims'] for r in erows]):.1f} |")
    md.append("")

    # ===== noyzhang focus: did any prompt fix the regression? =====
    md += ["## noyzhang regression analysis (the headline question)", "",
           "Baseline: v013d × none = 100%, v013d × low = 73.7% (R81 finding).",
           "Did any prompt × effort combo restore noyzhang to 100% while keeping low's other benefits?",
           "",
           "| prompt | none | low | medium | low recovery? |",
           "|--------|-----:|----:|-------:|---------------|"]
    for prompt in PROMPTS:
        cells = []
        low_cov = None
        for eff in EFFORTS:
            r = by_cell.get(("noyzhang", eff, prompt))
            if r and r["cov"] is not None:
                cells.append(f"{r['cov']*100:.1f}%")
                if eff == "low":
                    low_cov = r["cov"]
            else:
                cells.append("—")
        recov = "—"
        if low_cov is not None:
            if low_cov >= 0.95:
                recov = f"✅ recovered ({low_cov*100:.1f}%)"
            elif low_cov >= 0.85:
                recov = f"🟡 partial ({low_cov*100:.1f}%)"
            else:
                recov = f"🔴 still regressed ({low_cov*100:.1f}%)"
        md.append(f"| {prompt} | {' | '.join(cells)} | {recov} |")
    md.append("")

    # ===== Pareto winner: best avg coverage at minimum cost =====
    md += ["## Pareto picks", ""]
    by_cell_means = []
    for prompt in PROMPTS:
        for eff in EFFORTS:
            covs = [r["cov"] for r in rows if r["prompt"] == prompt and r["effort"] == eff and r["cov"] is not None]
            costs = [r["cost"] for r in rows if r["prompt"] == prompt and r["effort"] == eff]
            if covs:
                by_cell_means.append({
                    "label": f"{prompt} × {eff}",
                    "cov": st.mean(covs),
                    "cost": st.mean(costs),
                    "n": len(covs),
                })
    by_cell_means.sort(key=lambda x: -x["cov"])
    md.append("Top 5 by mean coverage:")
    md.append("")
    md.append("| rank | combo | mean cov | mean cost | n |")
    md.append("|-----:|-------|---------:|----------:|--:|")
    for i, c in enumerate(by_cell_means[:5], 1):
        md.append(f"| {i} | {c['label']} | {c['cov']*100:.1f}% | ${c['cost']:.2f} | {c['n']} |")
    md.append("")

    out = ROOT / "experiments" / "R82_GRID_RESULTS.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {out}")
    for line in md:
        print(line)


if __name__ == "__main__":
    main()
