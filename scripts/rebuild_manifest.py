"""Rebuild CITARE_REGISTRATION_MANIFEST.json to include all v0.13d s1 best-picks.

For each (paper_key, R-series), pick the run dir whose:
  - extraction.json exists and is non-empty
  - cov is highest (if gold available); else just first valid one

Output: experiments/CITARE_REGISTRATION_MANIFEST.json with one entry per paper.

Run from repo root:
    python scripts/rebuild_manifest.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

# Gold-paper to gold-file mapping (only used for paper_key → gold scoring)
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

PAPER_PATTERNS = {
    "T7": r"_T7_",
    "einstein": r"_einstein_",
    "edmondson": r"_edmondson_",
    "wei": r"_wei_",
    "barney": r"_barney_",
    "vaswani": r"_vaswani_",
    "shannon": r"_shannon_",
    "turing": r"_turing_",
    "watsoncrick": r"_watsoncrick_",
    "park": r"_park_",
    "noyzhang": r"_noyzhang_",
    "hubinger": r"_hubinger_",
    "hayes": r"_hayes_",
}


def main() -> None:
    runs = sorted((ROOT / "experiments" / "runs").iterdir())
    # Filter to v0.13d runs only with non-empty extraction.json
    valid = []
    for d in runs:
        if not d.is_dir():
            continue
        if "_v013d_" not in d.name:
            continue
        ext = d / "extraction.json"
        if not ext.exists() or ext.stat().st_size < 100:
            continue
        valid.append(d)

    # Group by paper_key (last segment after _v013d_ before _s\d+)
    by_paper: dict[str, list[Path]] = defaultdict(list)
    for d in valid:
        m = re.search(r"_v013d_(.+?)_s\d+$", d.name)
        if not m:
            continue
        key = m.group(1)
        # Strip trailing _pdf if accidentally present (early R72 had this bug)
        key = re.sub(r"_pdf$", "", key)
        by_paper[key].append(d)

    # Score each paper's candidates
    try:
        from score_against_gold import score
        score_available = True
    except ImportError:
        score_available = False
        print("WARN: score_against_gold not importable, gold scoring skipped", file=sys.stderr)

    manifest: dict[str, dict] = {}
    for paper_key, dirs in sorted(by_paper.items()):
        # Determine if a gold exists for this paper key
        gold_paper = None
        for g in GOLDS:
            if g.lower() in paper_key.lower() or paper_key.lower() in g.lower():
                gold_paper = g
                break
        # Score each candidate (if gold present), pick best
        candidates = []
        for d in dirs:
            entry = {
                "dir": d.name,
                "extraction_path": f"experiments/runs/{d.name}/extraction.json",
                "cov": None,
                "ip": None,
                "composite": None,
            }
            if gold_paper and score_available:
                try:
                    res = score(d / "extraction.json", ROOT / GOLDS[gold_paper])
                    entry["cov"] = res["axes"].get("coverage")
                    entry["ip"] = res["axes"].get("integrity_penalty")
                    entry["composite"] = (entry["cov"] or 0) - (entry["ip"] or 0)
                except Exception as e:
                    entry["cov"] = None
                    entry["score_error"] = str(e)[:120]
            candidates.append(entry)

        # Pick best: by composite if available, else first
        if any(c.get("composite") is not None for c in candidates):
            candidates.sort(key=lambda x: -(x.get("composite") or -1))
        best = candidates[0]
        # Optional: include other s2/s3 dirs for reproducibility (NOT for ingest)
        manifest[paper_key] = {
            "dir": best["dir"],
            "extraction_path": best["extraction_path"],
            "cov": best.get("cov"),
            "ip": best.get("ip"),
            "composite": best.get("composite"),
            "gold_paper": gold_paper,
            "alternate_seeds": [c["dir"] for c in candidates[1:] if c["dir"] != best["dir"]],
        }

    # Write
    out = ROOT / "experiments" / "CITARE_REGISTRATION_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(manifest)} papers to {out}")
    print()
    # Stats
    with_gold = sum(1 for v in manifest.values() if v.get("gold_paper"))
    cov_100 = sum(1 for v in manifest.values() if (v.get("cov") or 0) >= 0.99)
    cov_unscored = sum(1 for v in manifest.values() if v.get("cov") is None)
    print(f"  with gold:         {with_gold}")
    print(f"  unscored (no gold):{cov_unscored}")
    print(f"  cov >= 99%:        {cov_100}")
    print()
    # Print summary table
    print(f"{'paper_key':<45s} {'cov':>5s} {'ip':>5s} {'composite':>9s}  dir")
    for k in sorted(manifest):
        v = manifest[k]
        cov_s = f"{v['cov']*100:.0f}%" if v['cov'] is not None else " N/A"
        ip_s = f"{v['ip']*100:.0f}%" if v['ip'] is not None else " N/A"
        comp_s = f"{v['composite']:.3f}" if v['composite'] is not None else "  N/A"
        print(f"{k[:45]:<45s} {cov_s:>5s} {ip_s:>5s} {comp_s:>9s}  {v['dir']}")


if __name__ == "__main__":
    main()
