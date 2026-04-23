"""
Aggregate metrics.json across all runs into a leaderboard.

Usage:
    python aggregate_metrics.py > experiments/leaderboard.md
"""
from __future__ import annotations

import json
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def main():
    rows = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        metrics_path = run_dir / "metrics.json"
        if not metrics_path.exists():
            continue
        m = json.loads(metrics_path.read_text(encoding="utf-8"))
        rows.append(m)

    if not rows:
        print("# Leaderboard\n\n(no runs yet)")
        return

    print("# Leaderboard\n")
    print("| run_id | model | think | prompt | pdf | claims | cost | dur | valid |")
    print("|--------|-------|-------|--------|-----|--------|------|-----|-------|")
    for m in rows:
        claims = (m.get("claim_counts") or {}).get("total", 0)
        print(
            f"| {m.get('run_id','')} | "
            f"{m.get('model','').replace('claude-','')} | "
            f"{m.get('thinking_budget_tokens', 0)} | "
            f"{m.get('prompt_file','')} | "
            f"{m.get('pdf_filename','')[:30]} | "
            f"{claims} | "
            f"${m.get('cost_usd', 0):.3f} | "
            f"{m.get('duration_sec', 0):.1f}s | "
            f"{'✓' if m.get('json_valid') else '✗'} |"
        )

    total_cost = sum(m.get("cost_usd", 0) for m in rows)
    print(f"\n**Total cost across {len(rows)} runs: ${total_cost:.2f}**")


if __name__ == "__main__":
    main()
