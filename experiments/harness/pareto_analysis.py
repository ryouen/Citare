"""
Pareto analysis of extraction runs: cost vs coverage.

Identifies which (model, prompt, effort) combinations are Pareto-optimal:
no other combination is both cheaper AND higher coverage.

Usage:
    python pareto_analysis.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def main():
    rows = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        m_path = run_dir / "metrics.json"
        s_path = run_dir / "score.json"
        if not (m_path.exists() and s_path.exists()):
            continue
        m = json.loads(m_path.read_text(encoding="utf-8"))
        s = json.loads(s_path.read_text(encoding="utf-8"))
        rows.append({
            "run_id": m.get("run_id", "?"),
            "pdf": m.get("pdf_filename", "?"),
            "model": m.get("model", "?"),
            "effort": m.get("effort", "?"),
            "prompt": m.get("prompt_file", "?"),
            "cost": m.get("cost_usd", 0),
            "duration_sec": m.get("duration_sec", 0),
            "claims": (m.get("claim_counts") or {}).get("total", 0),
            "score": s.get("coverage_score", 0),
            "harness": m.get("harness_mode", "api"),
        })

    # Group by paper for within-paper pareto
    by_pdf = defaultdict(list)
    for r in rows:
        by_pdf[r["pdf"]].append(r)

    print("# Pareto Analysis (cost vs coverage, per paper)\n")
    print("A run is Pareto-optimal if no other run on the same paper has both higher score AND lower cost.\n")

    for pdf, items in sorted(by_pdf.items()):
        items.sort(key=lambda x: (-x["score"], x["cost"]))
        paretos = []
        for r in items:
            dominated = False
            for r2 in items:
                if r2 is r:
                    continue
                if r2["score"] > r["score"] and r2["cost"] < r["cost"]:
                    dominated = True
                    break
                if r2["score"] >= r["score"] and r2["cost"] < r["cost"] and r2 is not r:
                    if r2["score"] > r["score"] or r2["cost"] < r["cost"]:
                        dominated = True
                        break
            if not dominated:
                paretos.append(r)

        print(f"## {pdf}\n")
        print("| run | model | prompt | effort | cost | score | claims | dur | pareto |")
        print("|-----|-------|--------|--------|------|-------|--------|-----|--------|")
        for r in items:
            star = "+" if r in paretos else ""
            print(
                f"| {r['run_id'][:32]} "
                f"| {r['model'].replace('claude-', '').replace('-20251001', '')[:15]} "
                f"| {r['prompt'].replace('.md', '')[:16]} "
                f"| {r['effort']} "
                f"| ${r['cost']:.2f} "
                f"| {r['score']*100:.0f}% "
                f"| {r['claims']} "
                f"| {int(r['duration_sec'])}s "
                f"| {star} |"
            )
        print()

    # Overall winners by coverage tier
    print("## Overall winners by paper\n")
    for pdf, items in sorted(by_pdf.items()):
        items.sort(key=lambda x: (-x["score"], x["cost"]))
        top = items[0]
        cheapest_top = min(
            [r for r in items if r["score"] >= top["score"] - 0.05],
            key=lambda x: x["cost"],
        )
        print(
            f"- **{pdf[:35]}**: top score {top['score']*100:.0f}% "
            f"({top['run_id']}, ${top['cost']:.2f}); "
            f"cheapest within 5% of top: ${cheapest_top['cost']:.2f} ({cheapest_top['run_id']})"
        )


if __name__ == "__main__":
    main()
