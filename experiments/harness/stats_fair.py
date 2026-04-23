"""
Fair (apples-to-apples) statistics: compare prompts holding (paper, model, effort) constant.

For each (paper, model, effort) cell, show prompt-level statistics: mean score,
mean cost, mean duration, mean claims, variance, n.

Then roll up by prompt across all cells where that prompt has data.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


PROMPT_MAP = {
    "v3.4_baseline": "v0.1", "v0.1_baseline": "v0.1",
    "v3.5_terse": "v0.5", "v0.5_terse": "v0.5",
    "v3.6_fewshot": "v0.6", "v0.6_fewshot": "v0.6",
    "v3.7_purpose_first": "v0.7", "v0.7_purpose_first": "v0.7",
    "v3.8_hypothesis_aware": "v0.8", "v0.8_hypothesis_aware": "v0.8",
    "v3.9_adaptive": "v0.9", "v0.9_adaptive": "v0.9",
    "v0.2_cleaned": "v0.2",
    "v0.3_overlooked": "v0.3",
    "v0.4_minimal": "v0.4",
    "v0.10_combined": "v0.10",
}

PAPER_MAP = [
    ("Edmondson_1999", "Edmondson"),
    ("Barney_1991", "Barney"),
    ("DellAcqua_2023", "DellAcqua"),
    ("Noy_Zhang_2023", "Noy-Zhang"),
    ("Vaswani_2017", "Vaswani"),
    ("Hayes_2006", "Hayes"),
    ("Wei_2022", "Wei"),
    ("Hubinger_2024", "Hubinger"),
    ("Einstein_1905", "Einstein"),
    ("WatsonCrick1953", "Watson-Crick"),
    ("Computing Machinery", "Turing"),
    ("entropy", "Shannon"),
    ("Park_2023", "Park"),
]


def norm_prompt(pf):
    for k, v in PROMPT_MAP.items():
        if k in pf:
            return v
    return None


def norm_model(m):
    if "opus" in m.lower(): return "opus-4.7"
    if "sonnet" in m.lower(): return "sonnet-4.6"
    if "haiku" in m.lower(): return "haiku-4.5"
    return m


def norm_paper(pdf):
    for k, v in PAPER_MAP:
        if k in pdf:
            return v
    return None


def collect():
    rows = []
    for d in sorted(RUNS_DIR.iterdir()):
        m_p = d / "metrics.json"
        s_p = d / "score.json"
        if not m_p.exists():
            continue
        m = json.loads(m_p.read_text(encoding="utf-8"))
        score = None
        if s_p.exists():
            try:
                score = json.loads(s_p.read_text(encoding="utf-8")).get("coverage_score", 0) * 100
            except Exception:
                pass
        prompt = norm_prompt(m.get("prompt_file", ""))
        paper = norm_paper(m.get("pdf_filename", ""))
        model = norm_model(m.get("model", "?"))
        effort = m.get("effort", "?")
        if not prompt or not paper:
            continue
        rows.append({
            "run_id": m.get("run_id", d.name),
            "prompt": prompt, "paper": paper, "model": model, "effort": effort,
            "cost": m.get("cost_usd", 0),
            "dur": m.get("duration_sec", 0),
            "claims": (m.get("claim_counts") or {}).get("total", 0),
            "output_tokens": m.get("output_tokens", 0),
            "input_tokens": m.get("input_tokens", 0),
            "cache_creation": m.get("cache_creation_input_tokens", 0),
            "cache_read": m.get("cache_read_input_tokens", 0),
            "json_valid": m.get("json_valid", False),
            "score": score,
        })
    return rows


def mean(xs):
    return sum(xs) / len(xs) if xs else 0


def stdev(xs):
    return statistics.stdev(xs) if len(xs) >= 2 else 0


def main():
    rows = [r for r in collect() if r["model"] == "opus-4.7" and r["effort"] == "none"]
    # ^ freeze model and effort at production baseline for apples-to-apples

    print("# Citare Stats — Apples-to-Apples (Opus 4.7, effort=none)\n")
    print(f"Filter: only runs with model=Opus 4.7, effort=none. Total {len(rows)} runs.\n")

    # Per (paper, prompt) cell
    by_cell = defaultdict(list)
    for r in rows:
        by_cell[(r["paper"], r["prompt"])].append(r)

    prompts_seen = sorted({r["prompt"] for r in rows})
    papers_seen = [p for _, p in PAPER_MAP if any(r["paper"] == p for r in rows)]

    # Score matrix
    print("## Score matrix — mean across runs in each cell\n")
    print(f"{'paper':15s} ", end="")
    for p in prompts_seen:
        print(f"| {p:>8s} ", end="")
    print()
    print("-" * (16 + 11 * len(prompts_seen)))
    for paper in papers_seen:
        print(f"{paper:15s} ", end="")
        for prompt in prompts_seen:
            cell = by_cell.get((paper, prompt), [])
            if not cell:
                print(f"| {'—':>8s} ", end="")
                continue
            scores = [r["score"] for r in cell if r["score"] is not None]
            if not scores:
                print(f"| {'n='+str(len(cell)):>8s} ", end="")
                continue
            if len(scores) == 1:
                print(f"| {scores[0]:>6.0f}%  ", end="")
            else:
                print(f"| {mean(scores):>4.0f}%({len(scores)}) ", end="")
        print()
    print()

    # Cost matrix
    print("## Cost matrix — mean $ per run per cell (shown value)\n")
    print(f"{'paper':15s} ", end="")
    for p in prompts_seen:
        print(f"| {p:>7s} ", end="")
    print()
    print("-" * (16 + 10 * len(prompts_seen)))
    for paper in papers_seen:
        print(f"{paper:15s} ", end="")
        for prompt in prompts_seen:
            cell = by_cell.get((paper, prompt), [])
            if not cell:
                print(f"| {'—':>7s} ", end="")
                continue
            costs = [r["cost"] for r in cell]
            print(f"| ${mean(costs):>5.2f} ", end="")
        print()
    print()

    # Duration matrix
    print("## Duration matrix — mean seconds per run per cell\n")
    print(f"{'paper':15s} ", end="")
    for p in prompts_seen:
        print(f"| {p:>7s} ", end="")
    print()
    print("-" * (16 + 10 * len(prompts_seen)))
    for paper in papers_seen:
        print(f"{paper:15s} ", end="")
        for prompt in prompts_seen:
            cell = by_cell.get((paper, prompt), [])
            if not cell:
                print(f"| {'—':>7s} ", end="")
                continue
            durs = [r["dur"] for r in cell]
            print(f"| {mean(durs):>6.0f}s ", end="")
        print()
    print()

    # Output tokens matrix
    print("## Output tokens — mean per cell\n")
    print(f"{'paper':15s} ", end="")
    for p in prompts_seen:
        print(f"| {p:>7s} ", end="")
    print()
    print("-" * (16 + 10 * len(prompts_seen)))
    for paper in papers_seen:
        print(f"{paper:15s} ", end="")
        for prompt in prompts_seen:
            cell = by_cell.get((paper, prompt), [])
            if not cell:
                print(f"| {'—':>7s} ", end="")
                continue
            out = [r["output_tokens"] for r in cell]
            print(f"| {mean(out):>6.0f} ", end="")
        print()
    print()

    # Claims matrix
    print("## Claims count — mean per cell\n")
    print(f"{'paper':15s} ", end="")
    for p in prompts_seen:
        print(f"| {p:>6s} ", end="")
    print()
    print("-" * (16 + 9 * len(prompts_seen)))
    for paper in papers_seen:
        print(f"{paper:15s} ", end="")
        for prompt in prompts_seen:
            cell = by_cell.get((paper, prompt), [])
            if not cell:
                print(f"| {'—':>6s} ", end="")
                continue
            cl = [r["claims"] for r in cell]
            print(f"| {mean(cl):>5.1f} ", end="")
        print()
    print()

    # Roll-up per prompt (matched papers only)
    # To be fair, compare each prompt ONLY on papers it has been tested on, AND
    # restrict the baseline to the same papers for comparison purposes.
    print("## Per-prompt roll-up (Opus 4.7, effort=none)\n")
    print(f"{'prompt':6s} | n runs | papers | mean score | mean $ | mean dur | mean out tokens | std(score) |")
    print("-" * 90)
    for prompt in prompts_seen:
        prompt_rows = [r for r in rows if r["prompt"] == prompt]
        if not prompt_rows:
            continue
        scores = [r["score"] for r in prompt_rows if r["score"] is not None]
        costs = [r["cost"] for r in prompt_rows]
        durs = [r["dur"] for r in prompt_rows]
        out = [r["output_tokens"] for r in prompt_rows]
        papers = sorted({r["paper"] for r in prompt_rows})
        print(f"{prompt:6s} | {len(prompt_rows):>6d} | {len(papers):>6d} "
              f"| {mean(scores):>9.1f}% | ${mean(costs):>5.2f} "
              f"| {mean(durs):>6.0f}s | {mean(out):>13.0f} "
              f"| {stdev(scores):>9.1f} |")
    print()
    print("Note: mean score is NOT comparable across prompts unless the paper sets are identical.")
    print("Use the per-cell matrices above for apples-to-apples comparison.")
    print()

    # Fair delta vs v0.1 on identical (paper) sets
    print("## Fair delta vs v0.1 — averaged over papers where BOTH have data (Opus 4.7, none)\n")
    baseline_rows = [r for r in rows if r["prompt"] == "v0.1"]
    baseline_papers = {r["paper"]: r["score"] for r in baseline_rows if r["score"] is not None}
    print(f"{'prompt':6s} | shared papers | mean delta (pp) | per-paper delta |")
    print("-" * 100)
    for prompt in prompts_seen:
        if prompt == "v0.1":
            continue
        other_rows = [r for r in rows if r["prompt"] == prompt]
        # Per-paper: delta = prompt_score - v0.1_score
        pairs = []
        per_paper = []
        for r in other_rows:
            if r["paper"] in baseline_papers and r["score"] is not None:
                d = r["score"] - baseline_papers[r["paper"]]
                pairs.append(d)
                per_paper.append(f"{r['paper']}:{d:+.0f}")
        if pairs:
            print(f"{prompt:6s} | {len(set(r['paper'] for r in other_rows if r['paper'] in baseline_papers)):>13d} "
                  f"| {mean(pairs):>+14.1f} | {', '.join(sorted(set(per_paper)))} |")
    print()


if __name__ == "__main__":
    main()
