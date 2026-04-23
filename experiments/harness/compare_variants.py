"""
Compare prompt variants head-to-head on the same papers.

Usage:
    python compare_variants.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

RUNS_DIR = Path(__file__).resolve().parents[1] / "runs"


PROMPT_KEYS = [
    ("v0.1_baseline", "v0.1"),
    ("v0.2_cleaned", "v0.2"),
    ("v0.3_overlooked", "v0.3"),
    ("v0.4_minimal", "v0.4"),
    ("v0.5_terse", "v0.5"),
    ("v0.6_fewshot", "v0.6"),
    ("v0.7_purpose_first", "v0.7"),
    ("v0.8_hypothesis_aware", "v0.8"),
    ("v0.9_adaptive", "v0.9"),
]

# historical prompt filenames that should remap
LEGACY_MAP = {
    "v3.4_baseline": "v0.1",
    "v3.5_terse": "v0.5",
    "v3.6_fewshot": "v0.6",
    "v3.7_purpose_first": "v0.7",
    "v3.8_hypothesis_aware": "v0.8",
    "v3.9_adaptive": "v0.9",
}


def prompt_to_short(pf: str) -> str | None:
    for key, short in PROMPT_KEYS:
        if key in pf:
            return short
    for key, short in LEGACY_MAP.items():
        if key in pf:
            return short
    return None


PAPERS = [
    ("Edmondson_1999", "Edmondson"),
    ("Barney_1991", "Barney"),
    ("DellAcqua_2023", "DellAcqua"),
    ("Noy_Zhang_2023", "Noy_Zhang"),
    ("Vaswani_2017", "Vaswani"),
    ("Hayes_2006", "Hayes"),
    ("Wei_2022", "Wei"),
    ("Hubinger_2024", "Hubinger"),
    ("Einstein_1905", "Einstein"),
    ("WatsonCrick1953", "WatsonCrick"),
    ("Computing Machinery", "Turing"),
    ("entropy", "Shannon"),
]


def paper_to_short(pdf: str) -> str | None:
    for key, short in PAPERS:
        if key in pdf:
            return short
    return None


def main():
    # best score per (prompt, paper)
    best = {}
    costs = {}
    for d in sorted(RUNS_DIR.iterdir()):
        m_p = d / "metrics.json"
        s_p = d / "score.json"
        if not (m_p.exists() and s_p.exists()):
            continue
        m = json.loads(m_p.read_text(encoding="utf-8"))
        if "opus" not in m.get("model", "").lower():
            continue
        paper = paper_to_short(m.get("pdf_filename", ""))
        prompt = prompt_to_short(m.get("prompt_file", ""))
        if not paper or not prompt:
            continue
        s = json.loads(s_p.read_text(encoding="utf-8"))
        score = s.get("coverage_score", 0) * 100
        key = (prompt, paper)
        if key not in best or score > best[key]:
            best[key] = score
            costs[key] = m.get("cost_usd", 0)

    # Print head-to-head matrix
    prompts_used = sorted({k[0] for k in best.keys()})
    papers_used = [p[1] for p in PAPERS if any(k[1] == p[1] for k in best.keys())]

    print("# Head-to-head matrix (best Opus 4.7 score per paper x prompt)\n")
    print(f"{'paper':15s}", end='')
    for pr in prompts_used:
        print(f" | {pr:>6s}", end='')
    print()
    print('-' * (15 + 9 * len(prompts_used)))
    for p in papers_used:
        print(f"{p[:15]:15s}", end='')
        for pr in prompts_used:
            v = best.get((pr, p))
            print(f" | {v:>5.0f}%" if v is not None else f" | {'-':>6s}", end='')
        print()

    # Delta analysis vs baseline
    print("\n# Delta vs v0.1 baseline (positive = improvement)\n")
    print(f"{'paper':15s}", end='')
    for pr in prompts_used:
        if pr == "v0.1":
            continue
        print(f" | {pr:>7s}", end='')
    print()
    print('-' * (15 + 10 * (len(prompts_used) - 1)))
    for p in papers_used:
        base = best.get(("v0.1", p))
        print(f"{p[:15]:15s}", end='')
        for pr in prompts_used:
            if pr == "v0.1":
                continue
            v = best.get((pr, p))
            if v is None or base is None:
                print(f" | {'-':>7s}", end='')
            else:
                delta = v - base
                sign = "+" if delta > 0 else ""
                print(f" | {sign}{delta:>5.0f}pp", end='')
        print()

    # Summary of winners
    print("\n# Best prompt per paper\n")
    for p in papers_used:
        entries = [(pr, best.get((pr, p))) for pr in prompts_used if best.get((pr, p)) is not None]
        if not entries:
            continue
        entries.sort(key=lambda x: (-x[1], costs.get((x[0], p), 0)))
        top = entries[0]
        print(f"- **{p:15s}**: {top[0]} -> {top[1]:.0f}%")


if __name__ == "__main__":
    main()
