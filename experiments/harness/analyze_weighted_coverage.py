"""Re-analyse existing v0.13 / v0.13d / v0.13e extractions:
  - Split coverage into "core" (gold weight >= 2) vs "minor" (weight == 1)
  - Pull cost, duration, tokens from each run's metrics.json
  - Aggregate per-paper, per-variant, then cross-paper

NO new extractions. Reads disk only.
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

VARIANT_PATTERNS = {
    "v0.13": {
        "T7":         ["*_R43[ABC]_v13_T7_s*", "*_R50_v13_T7_s*"],
        "einstein":   ["*_R43[GHI]_v13_einstein_s*"],
        "edmondson":  ["*_R42B_v13_edmondson*", "*_R43[JK]_v13_edmondson_s*"],
        "wei":        ["*_R45_v0.13_refs_verbatim_wei_s*"],
        "barney":     ["*_R45_v0.13_refs_verbatim_barney_s*"],
        "vaswani":    ["*_R55_v13_vaswani_s*"],
        "shannon":    ["*_R55_v13_shannon_s*"],
        "turing":     ["*_R55_v13_turing_s*"],
        "watsoncrick":["*_R55_v13_watsoncrick_s*"],
        "park":       ["*_R55_v13_park_s*"],
        "noyzhang":   ["*_R55_v13_noyzhang_s*"],
        "hubinger":   ["*_R55_v13_hubinger_s*", "*_R58_v13_hubinger_s*", "*_R59_v13_hubinger_s*"],
        "hayes":      ["*_R55_v13_hayes_s*"],
    },
    "v0.13d": {p: [f"*_R6[01234]_v013d_{p}_s*"] for p in GOLDS},
    "v0.13e": {p: [f"*_R6[678]_v013e_{p}_s*"] for p in GOLDS},
}


def score_weighted(extraction_path: Path, gold_path: Path) -> dict:
    res = score(extraction_path, gold_path)
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
        "core_total": core_total,
        "minor_total": minor_total,
    }


def get_metrics(rd: Path) -> dict | None:
    p = rd / "metrics.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def aggregate(variant: str, paper: str) -> list[dict]:
    rds = []
    for pat in VARIANT_PATTERNS[variant].get(paper, []):
        rds.extend(sorted((ROOT / "experiments" / "runs").glob(pat)))
    cells = []
    for rd in rds:
        ext = rd / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            continue
        try:
            sw = score_weighted(ext, ROOT / GOLDS[paper])
            m = get_metrics(rd)
            if m is None:
                continue
            cells.append({
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
        except Exception:
            continue
    return cells


def main() -> None:
    print("# Weighted-coverage re-analysis (no new extractions)")
    print()
    print("## Legend")
    print("- **Core cov**: gold weight ≥ 2 must-catch items (paper's central claims)")
    print("- **Minor cov**: gold weight = 1 must-catch items (auxiliary facts)")
    print("- All numbers are means across N=2-5 seeds per cell")
    print()
    print("## Per-paper × variant")
    print()
    print("| Paper | Variant | N | Cov(all) | **Cov(core)** | Cov(minor) | Cost ($) | Time (s) | Tokens (K) | Claims |")
    print("|-------|---------|---|----------|---------------|------------|----------|----------|-----------|--------|")

    paper_summary: dict[str, dict[str, dict]] = {}
    for paper in GOLDS:
        paper_summary[paper] = {}
        for variant in ("v0.13", "v0.13d", "v0.13e"):
            cells = aggregate(variant, paper)
            if not cells:
                continue
            n = len(cells)
            cov_all = statistics.mean([c["cov_overall"] for c in cells])
            cc = [c["cov_core"] for c in cells if c["cov_core"] is not None]
            cm = [c["cov_minor"] for c in cells if c["cov_minor"] is not None]
            cov_core = statistics.mean(cc) if cc else None
            cov_minor = statistics.mean(cm) if cm else None
            cost = statistics.mean([c["cost"] for c in cells])
            dur = statistics.mean([c["duration_s"] for c in cells])
            tok = statistics.mean([c["in_tok"] + c["out_tok"] for c in cells])
            cl = statistics.mean([c["claims"] for c in cells])
            paper_summary[paper][variant] = {
                "cov_all": cov_all, "cov_core": cov_core, "cov_minor": cov_minor,
                "cost": cost, "dur": dur, "tok": tok, "n": n, "claims": cl,
            }
            cc_s = f"{cov_core*100:.0f}%" if cov_core is not None else "—"
            cm_s = f"{cov_minor*100:.0f}%" if cov_minor is not None else "—"
            print(f"| {paper:11s} | {variant:7s} | {n} | "
                  f"{cov_all*100:.1f}% | **{cc_s}** | {cm_s} | "
                  f"${cost:.2f} | {dur:.0f} | {tok/1000:.0f} | {cl:.0f} |")

    print()
    print("## Cross-paper aggregate per variant (means over 13 papers)")
    print()
    print("| Variant | Avg Cov(all) | **Avg Cov(core)** | Avg Cov(minor) | Avg Cost | Avg Time | Avg Tokens (K) | Avg Claims |")
    print("|---------|--------------|--------------------|------------------|----------|----------|----------------|-----------|")
    for variant in ("v0.13", "v0.13d", "v0.13e"):
        all_c = []; core_c = []; minor_c = []
        costs = []; durs = []; toks = []; claims = []
        for paper in GOLDS:
            s = paper_summary.get(paper, {}).get(variant)
            if not s:
                continue
            all_c.append(s["cov_all"])
            if s["cov_core"] is not None:
                core_c.append(s["cov_core"])
            if s["cov_minor"] is not None:
                minor_c.append(s["cov_minor"])
            costs.append(s["cost"])
            durs.append(s["dur"])
            toks.append(s["tok"])
            claims.append(s["claims"])
        if not all_c:
            continue
        print(f"| {variant} | "
              f"{statistics.mean(all_c)*100:.1f}% | "
              f"**{statistics.mean(core_c)*100:.1f}%** | "
              f"{statistics.mean(minor_c)*100:.1f}% | "
              f"${statistics.mean(costs):.2f} | "
              f"{statistics.mean(durs):.0f}s | "
              f"{statistics.mean(toks)/1000:.0f}K | "
              f"{statistics.mean(claims):.0f} |")

    print()
    print("## Where coverage drops are core vs minor")
    print()
    print("Compare v0.13 → v0.13d / v0.13e for each paper, splitting by core vs minor:")
    print()
    print("| Paper | v0.13 → v0.13d (core) | v0.13 → v0.13d (minor) | v0.13 → v0.13e (core) | v0.13 → v0.13e (minor) |")
    print("|-------|------------------------|--------------------------|------------------------|--------------------------|")
    for paper in GOLDS:
        ps = paper_summary.get(paper, {})
        if "v0.13" not in ps:
            continue
        b = ps["v0.13"]
        def fmt_delta(other_var, key):
            o = ps.get(other_var)
            if not o or o[key] is None or b[key] is None:
                return "—"
            d = (o[key] - b[key]) * 100
            return f"{b[key]*100:.0f}→{o[key]*100:.0f} ({d:+.0f}pp)"
        print(f"| {paper:11s} | "
              f"{fmt_delta('v0.13d', 'cov_core')} | "
              f"{fmt_delta('v0.13d', 'cov_minor')} | "
              f"{fmt_delta('v0.13e', 'cov_core')} | "
              f"{fmt_delta('v0.13e', 'cov_minor')} |")


if __name__ == "__main__":
    main()
