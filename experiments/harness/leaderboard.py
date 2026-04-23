"""
Generate a leaderboard across all experiment runs, grouping by paper.

Usage:
    python leaderboard.py > experiments/leaderboard.md
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def short_pdf(name: str) -> str:
    """Shorten PDF name for table readability."""
    n = name.replace("_stripped.pdf", "*").replace(".pdf", "")
    # keep author+year+short title
    parts = n.split("_")
    if len(parts) >= 2:
        return "_".join(parts[:2])
    return n[:20]


def normalize_prompt_name(name: str) -> str:
    """Map historical prompt filenames to current canonical names."""
    mapping = {
        "v3.4_baseline": "v0.1_baseline",
        "v3.5_terse": "v0.5_terse",
        "v3.6_fewshot": "v0.6_fewshot",
        "v3.7_purpose_first": "v0.7_purpose_first",
        "v3.8_hypothesis_aware": "v0.8_hypothesis_aware",
        "v3.9_adaptive": "v0.9_adaptive",
    }
    for old, new in mapping.items():
        name = name.replace(old, new)
    return name


def main():
    rows = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        m_path = run_dir / "metrics.json"
        if not m_path.exists():
            e_path = run_dir / "error.json"
            status = "FAILED" if e_path.exists() else "running"
            continue
        m = json.loads(m_path.read_text(encoding="utf-8"))
        s_path = run_dir / "score.json"
        score_pct = None
        if s_path.exists():
            try:
                s = json.loads(s_path.read_text(encoding="utf-8"))
                score_pct = s.get("coverage_score", 0) * 100
            except Exception:
                score_pct = None
        rows.append({"metrics": m, "score_pct": score_pct, "run_dir": run_dir.name})

    # Group by pdf_filename
    by_paper = defaultdict(list)
    for r in rows:
        pdf = r["metrics"].get("pdf_filename", "?")
        by_paper[pdf].append(r)

    print("# Citare Extraction Experiment Leaderboard\n")
    print(f"Total completed runs: {len(rows)}\n")

    total_cost = sum(r["metrics"].get("cost_usd", 0) for r in rows)
    print(f"**Aggregate spend so far: ${total_cost:.2f}**\n")

    for pdf, runs in sorted(by_paper.items()):
        print(f"## {short_pdf(pdf)} ({pdf})\n")
        print("| run_id | prompt | effort | dur | cost | valid | claims(D/R/E/M) | mms | rels | refs | score |")
        print("|--------|--------|--------|-----|------|-------|-----------------|-----|------|------|-------|")
        for r in sorted(runs, key=lambda x: x["metrics"].get("timestamp", "")):
            m = r["metrics"]
            cc = m.get("claim_counts", {})
            score_cell = f"{r['score_pct']:.0f}%" if r["score_pct"] is not None else "-"
            print(
                f"| {m.get('run_id','?')[:28]} "
                f"| {normalize_prompt_name(m.get('prompt_file','?'))[:18]} "
                f"| {m.get('effort','?')} "
                f"| {m.get('duration_sec', 0):.0f}s "
                f"| ${m.get('cost_usd', 0):.2f} "
                f"| {'Y' if m.get('json_valid') else 'N'} "
                f"| {cc.get('total', 0)} ({cc.get('DEFINITION', 0)}/{cc.get('RELATION', 0)}/{cc.get('EXISTENCE_CLAIM', 0)}/{cc.get('META_CLAIM', 0)}) "
                f"| {m.get('measurement_method_count', 0)} "
                f"| {m.get('claim_relation_count', 0)} "
                f"| {m.get('paper_reference_count', 0)} "
                f"| {score_cell} |"
            )
        print()


if __name__ == "__main__":
    main()
