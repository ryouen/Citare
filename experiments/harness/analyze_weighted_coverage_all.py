"""Re-analyse ALL existing extractions across all v0.x variants.

For each (variant, paper) cell:
  - Aggregate all matching runs
  - Split coverage into core (gold weight >= 2) vs minor (weight == 1)
  - Aggregate cost / duration / tokens / claim count

Auto-detects variant by reading prompt_used.md first line. NO new extractions.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from score_against_gold import score  # type: ignore


GOLDS = {
    "T7":          "experiments/ground_truth/trap_papers/T7_gold.json",
    "einstein":    "experiments/ground_truth/real_papers/einstein_1905_gold.json",
    "edmondson":   "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
    "wei":         "experiments/ground_truth/real_papers/wei_2022_gold.json",
    "barney":      "experiments/ground_truth/real_papers/barney_1991_gold.json",
    "vaswani":     "experiments/ground_truth/real_papers/vaswani_2017_gold.json",
    "shannon":     "experiments/ground_truth/real_papers/shannon_1948_gold.json",
    "turing":      "experiments/ground_truth/real_papers/turing_1950_gold.json",
    "watsoncrick": "experiments/ground_truth/real_papers/watson_crick_1953_gold.json",
    "park":        "experiments/ground_truth/real_papers/park_2023_gold.json",
    "noyzhang":    "experiments/ground_truth/real_papers/noy_zhang_2023_gold.json",
    "hubinger":    "experiments/ground_truth/real_papers/hubinger_2024_gold.json",
    "hayes":       "experiments/ground_truth/real_papers/hayes_2006_gold.json",
}

# Map run-id snippet to a paper key
PAPER_KEYS = {
    "T7": "T7", "trap_T7": "T7", "trap": "T7",
    "einstein": "einstein",
    "edmondson": "edmondson",
    "wei": "wei", "wei_": "wei",
    "barney": "barney",
    "vaswani": "vaswani",
    "shannon": "shannon", "entropy": "shannon",
    "turing": "turing",
    "watsoncrick": "watsoncrick", "watson_crick": "watsoncrick",
    "park": "park",
    "noyzhang": "noyzhang", "noy_zhang": "noyzhang",
    "hubinger": "hubinger",
    "hayes": "hayes",
}


def variant_from_prompt(prompt_path: Path) -> str | None:
    if not prompt_path.exists():
        return None
    line = prompt_path.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
    m = re.search(r"v0\.(\d+[a-z]?)", line)
    return f"v0.{m.group(1)}" if m else None


def paper_from_run_dir(name: str) -> str | None:
    name_l = name.lower()
    for key, paper in PAPER_KEYS.items():
        if key.lower() in name_l:
            return paper
    return None


def score_weighted(extraction_path: Path, gold_path: Path) -> dict | None:
    try:
        res = score(extraction_path, gold_path)
    except Exception:
        return None
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    items = gold.get("must_catch_claims", [])
    weight_map = {x["key"]: x.get("weight", 1.0) for x in items}

    core_total = core_hit = 0
    minor_total = minor_hit = 0
    for r in res["results"]:
        w = weight_map.get(r["key"], 1.0)
        if w >= 2:
            core_total += 1
            core_hit += int(r["matched"])
        else:
            minor_total += 1
            minor_hit += int(r["matched"])

    return {
        "cov_overall": res["axes"]["coverage"],
        "cov_core": core_hit / core_total if core_total else None,
        "cov_minor": minor_hit / minor_total if minor_total else None,
    }


def main() -> None:
    # cells[variant][paper] = list of dicts
    cells: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

    for d in sorted((ROOT / "experiments" / "runs").iterdir()):
        if not d.is_dir():
            continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            continue
        prompt_used = d / "prompt_used.md"
        variant = variant_from_prompt(prompt_used)
        if variant is None:
            continue
        paper = paper_from_run_dir(d.name)
        if paper is None or paper not in GOLDS:
            continue

        sw = score_weighted(ext, ROOT / GOLDS[paper])
        if sw is None:
            continue

        m_path = d / "metrics.json"
        if not m_path.exists():
            continue
        m = json.loads(m_path.read_text(encoding="utf-8"))

        cells[variant][paper].append({
            **sw,
            "cost": m.get("cost_usd", 0),
            "duration_s": m.get("duration_sec", 0),
            "in_tok": (
                m.get("input_tokens", 0)
                + m.get("cache_creation_input_tokens", 0)
                + m.get("cache_read_input_tokens", 0)
            ),
            "out_tok": m.get("output_tokens", 0),
            "claims": m.get("claim_counts", {}).get("total", 0),
        })

    # Build cross-paper summary per variant
    print("# All-variant weighted coverage re-analysis")
    print()
    print("Splits coverage by gold weight: **core** (≥2) vs **minor** (=1).")
    print()
    print("## Cross-paper summary (only variants with ≥3 papers covered)")
    print()
    print("| Variant | Papers | Total runs | **Cov(core)** | Cov(minor) | Cov(all) | Avg cost | Avg time | Avg tokens | Avg claims |")
    print("|---------|--------|-----------:|--------------:|-----------:|---------:|---------:|---------:|-----------:|-----------:|")

    summary = []
    for variant, papers in cells.items():
        if len(papers) < 3:
            continue
        total_runs = sum(len(v) for v in papers.values())
        all_c = []; core_c = []; minor_c = []
        costs = []; durs = []; toks = []; claims = []
        for paper, runs in papers.items():
            if not runs:
                continue
            all_c.append(statistics.mean([r["cov_overall"] for r in runs]))
            cc = [r["cov_core"] for r in runs if r["cov_core"] is not None]
            cm = [r["cov_minor"] for r in runs if r["cov_minor"] is not None]
            if cc:
                core_c.append(statistics.mean(cc))
            if cm:
                minor_c.append(statistics.mean(cm))
            costs.append(statistics.mean([r["cost"] for r in runs]))
            durs.append(statistics.mean([r["duration_s"] for r in runs]))
            toks.append(statistics.mean([r["in_tok"] + r["out_tok"] for r in runs]))
            claims.append(statistics.mean([r["claims"] for r in runs]))
        if not all_c:
            continue
        row = {
            "variant": variant,
            "papers": len(papers),
            "runs": total_runs,
            "cov_core": statistics.mean(core_c) if core_c else 0,
            "cov_minor": statistics.mean(minor_c) if minor_c else 0,
            "cov_all": statistics.mean(all_c),
            "cost": statistics.mean(costs),
            "dur": statistics.mean(durs),
            "tok": statistics.mean(toks),
            "claims": statistics.mean(claims),
        }
        summary.append(row)

    summary.sort(key=lambda r: r["cov_core"], reverse=True)
    for r in summary:
        print(f"| {r['variant']:7s} | {r['papers']:>3d} | {r['runs']:>3d} | "
              f"**{r['cov_core']*100:.1f}%** | "
              f"{r['cov_minor']*100:.1f}% | "
              f"{r['cov_all']*100:.1f}% | "
              f"${r['cost']:.2f} | "
              f"{r['dur']:.0f}s | "
              f"{r['tok']/1000:.0f}K | "
              f"{r['claims']:.1f} |")

    # Per-paper x per-variant detail (only top 6 variants by core)
    top_variants = [r["variant"] for r in summary[:8]]
    print()
    print(f"## Per-paper × top {len(top_variants)} variants — core coverage")
    print()
    header = "| Paper | " + " | ".join(top_variants) + " |"
    print(header)
    print("|" + "|".join(["-" * (len(s) + 2) for s in header.split("|")[1:-1]]) + "|")

    for paper in GOLDS:
        row = [paper]
        for v in top_variants:
            runs = cells.get(v, {}).get(paper, [])
            if not runs:
                row.append("—")
                continue
            cc = [r["cov_core"] for r in runs if r["cov_core"] is not None]
            row.append(f"{statistics.mean(cc)*100:.0f}%" if cc else "—")
        print("| " + " | ".join(row) + " |")

    print()
    print(f"## Per-paper × top {len(top_variants)} variants — minor coverage")
    print()
    print(header)
    print("|" + "|".join(["-" * (len(s) + 2) for s in header.split("|")[1:-1]]) + "|")
    for paper in GOLDS:
        row = [paper]
        for v in top_variants:
            runs = cells.get(v, {}).get(paper, [])
            if not runs:
                row.append("—")
                continue
            cm = [r["cov_minor"] for r in runs if r["cov_minor"] is not None]
            row.append(f"{statistics.mean(cm)*100:.0f}%" if cm else "—")
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main()
