"""
Aggregate statistics across all experiment runs.

Outputs:
- Grand totals (runs, tokens, cost, duration)
- By prompt (with variance)
- By model
- By paper
- By effort level
- Chronology (session-level)
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


def normalize_prompt(pf: str) -> str:
    """Collapse v3.x legacy names to v0.x."""
    mapping = {
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
    for key, short in mapping.items():
        if key in pf:
            return short
    return "?"


def normalize_model(m: str) -> str:
    if "opus" in m.lower():
        return "opus-4.7"
    if "sonnet" in m.lower():
        return "sonnet-4.6"
    if "haiku" in m.lower():
        return "haiku-4.5"
    return m


def normalize_paper(pdf: str) -> str:
    mapping = [
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
    for key, short in mapping:
        if key in pdf:
            return short
    return pdf[:20]


def collect():
    rows = []
    for run_dir in sorted(RUNS_DIR.iterdir()):
        m_path = run_dir / "metrics.json"
        e_path = run_dir / "error.json"
        s_path = run_dir / "score.json"
        if m_path.exists():
            m = json.loads(m_path.read_text(encoding="utf-8"))
            score = None
            if s_path.exists():
                try:
                    score = json.loads(s_path.read_text(encoding="utf-8")).get("coverage_score", 0) * 100
                except Exception:
                    pass
            rows.append({
                "run_id": m.get("run_id", run_dir.name),
                "timestamp": m.get("timestamp", ""),
                "prompt": normalize_prompt(m.get("prompt_file", "")),
                "model": normalize_model(m.get("model", "?")),
                "paper": normalize_paper(m.get("pdf_filename", "")),
                "effort": m.get("effort", "?"),
                "duration_sec": m.get("duration_sec", 0),
                "input_tokens": m.get("input_tokens", 0),
                "output_tokens": m.get("output_tokens", 0),
                "cache_creation": m.get("cache_creation_input_tokens", 0),
                "cache_read": m.get("cache_read_input_tokens", 0),
                "cost_usd": m.get("cost_usd", 0),
                "json_valid": m.get("json_valid", False),
                "claims_total": (m.get("claim_counts") or {}).get("total", 0),
                "harness": m.get("harness_mode", "api"),
                "status": "DONE",
                "score": score,
            })
        elif e_path.exists():
            rows.append({
                "run_id": run_dir.name,
                "status": "FAIL",
                "prompt": "?", "model": "?", "paper": "?", "effort": "?",
                "duration_sec": 0, "input_tokens": 0, "output_tokens": 0,
                "cache_creation": 0, "cache_read": 0, "cost_usd": 0,
                "json_valid": False, "claims_total": 0, "harness": "?",
                "score": None, "timestamp": "",
            })
    return rows


def main():
    rows = collect()
    done = [r for r in rows if r["status"] == "DONE"]
    failed = [r for r in rows if r["status"] == "FAIL"]

    print("# Citare Extraction Campaign — Statistics\n")
    print(f"**Total runs attempted**: {len(rows)}  (DONE: {len(done)}, FAIL: {len(failed)})")
    print()

    # Grand totals
    total_input = sum(r["input_tokens"] for r in done)
    total_output = sum(r["output_tokens"] for r in done)
    total_cache_creation = sum(r["cache_creation"] for r in done)
    total_cache_read = sum(r["cache_read"] for r in done)
    total_all_tokens = total_input + total_output + total_cache_creation + total_cache_read
    total_cost = sum(r["cost_usd"] for r in done)
    total_duration = sum(r["duration_sec"] for r in done)

    print("## Grand totals\n")
    print(f"| metric | value |")
    print(f"|--------|-------|")
    print(f"| Successful runs | {len(done)} |")
    print(f"| Failed runs | {len(failed)} |")
    print(f"| **Input tokens (regular)** | {total_input:,} |")
    print(f"| **Output tokens** | {total_output:,} |")
    print(f"| **Cache creation tokens** | {total_cache_creation:,} |")
    print(f"| **Cache read tokens** | {total_cache_read:,} |")
    print(f"| **Total tokens processed** | {total_all_tokens:,} |")
    print(f"| **Total cost (shown)** | ${total_cost:.2f} |")
    print(f"| **Total wall-clock (successful)** | {total_duration/60:.1f} min ({total_duration/3600:.1f} hours) |")
    print(f"| Mean cost per successful run | ${total_cost/len(done):.3f} |")
    print(f"| Mean duration per run | {total_duration/len(done):.1f} sec |")
    print()

    # By prompt
    print("## By prompt\n")
    by_prompt = defaultdict(list)
    for r in done:
        by_prompt[r["prompt"]].append(r)
    print("| prompt | runs | total $ | mean $ | mean dur | mean claims | JSON valid | n scored |")
    print("|--------|------|---------|--------|----------|-------------|------------|----------|")
    for p in sorted(by_prompt.keys()):
        xs = by_prompt[p]
        scored = [x for x in xs if x["score"] is not None]
        jv = sum(1 for x in xs if x["json_valid"])
        print(f"| {p} | {len(xs)} | ${sum(x['cost_usd'] for x in xs):.2f} | ${sum(x['cost_usd'] for x in xs)/len(xs):.3f} "
              f"| {sum(x['duration_sec'] for x in xs)/len(xs):.0f}s "
              f"| {sum(x['claims_total'] for x in xs)/len(xs):.1f} "
              f"| {jv}/{len(xs)} | {len(scored)} |")
    print()

    # By model
    print("## By model\n")
    by_model = defaultdict(list)
    for r in done:
        by_model[r["model"]].append(r)
    print("| model | runs | total $ | mean $ | mean dur | JSON valid |")
    print("|-------|------|---------|--------|----------|------------|")
    for m in sorted(by_model.keys()):
        xs = by_model[m]
        jv = sum(1 for x in xs if x["json_valid"])
        print(f"| {m} | {len(xs)} | ${sum(x['cost_usd'] for x in xs):.2f} "
              f"| ${sum(x['cost_usd'] for x in xs)/len(xs):.3f} "
              f"| {sum(x['duration_sec'] for x in xs)/len(xs):.0f}s "
              f"| {jv}/{len(xs)} |")
    print()

    # By effort
    print("## By effort level\n")
    by_effort = defaultdict(list)
    for r in done:
        by_effort[r["effort"]].append(r)
    print("| effort | runs | total $ | mean $ | mean dur | mean claims |")
    print("|--------|------|---------|--------|----------|-------------|")
    for e in ["none", "low", "medium", "high", "xhigh", "max", "?"]:
        xs = by_effort.get(e, [])
        if not xs:
            continue
        print(f"| {e} | {len(xs)} | ${sum(x['cost_usd'] for x in xs):.2f} "
              f"| ${sum(x['cost_usd'] for x in xs)/len(xs):.3f} "
              f"| {sum(x['duration_sec'] for x in xs)/len(xs):.0f}s "
              f"| {sum(x['claims_total'] for x in xs)/len(xs):.1f} |")
    print()

    # By paper
    print("## By paper\n")
    by_paper = defaultdict(list)
    for r in done:
        by_paper[r["paper"]].append(r)
    print("| paper | runs | total $ | mean $ | mean claims | mean score |")
    print("|-------|------|---------|--------|-------------|------------|")
    for p in sorted(by_paper.keys()):
        xs = by_paper[p]
        scored = [x for x in xs if x["score"] is not None]
        mean_score = sum(x["score"] for x in scored) / len(scored) if scored else None
        score_str = f"{mean_score:.1f}%" if mean_score is not None else "-"
        print(f"| {p} | {len(xs)} | ${sum(x['cost_usd'] for x in xs):.2f} "
              f"| ${sum(x['cost_usd'] for x in xs)/len(xs):.3f} "
              f"| {sum(x['claims_total'] for x in xs)/len(xs):.1f} "
              f"| {score_str} |")
    print()

    # Harness mode
    print("## By harness (API vs Max-plan CLI)\n")
    by_harness = defaultdict(list)
    for r in done:
        by_harness[r["harness"]].append(r)
    for h in sorted(by_harness.keys()):
        xs = by_harness[h]
        label = "API (pay-per-use)" if h == "api" else "CLI (Max plan)" if h == "cli" else h
        print(f"- {label}: {len(xs)} runs, ${sum(x['cost_usd'] for x in xs):.2f} total")
    print()

    # Failures by type
    if failed:
        print("## Failed runs\n")
        print(f"- {len(failed)} total")
        # Detail would need error.json reads; skip for brevity
    print()


if __name__ == "__main__":
    main()
