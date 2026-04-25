"""For each paper in the Stage C panel, pick the highest-quality extraction
across all v0.13/v0.16b/v0.16c/v0.16d/v0.16e seeds.

Quality score = coverage × (1 + 0.3 × eq_capture_indicator) × (1 + 0.2 × discipline)
where eq_capture_indicator is 1 if the paper has gold equations and the run captured ≥ half of them.

Outputs a JSON manifest mapping paper_id -> {run_dir, extraction_json_path, prompt, scores}.
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from score_against_gold import score  # type: ignore


PAPER_TO_GOLD = {
    "T7": "experiments/ground_truth/trap_papers/T7_gold.json",
    "einstein": "experiments/ground_truth/real_papers/einstein_1905_gold.json",
    "edmondson": "experiments/ground_truth/real_papers/edmondson_1999_gold.json",
    "wei": "experiments/ground_truth/real_papers/wei_2022_gold.json",
    "barney": "experiments/ground_truth/real_papers/barney_1991_gold.json",
    "vaswani": "experiments/ground_truth/real_papers/vaswani_2017_gold.json",
    "shannon": "experiments/ground_truth/real_papers/shannon_1948_gold.json",
    "turing": "experiments/ground_truth/real_papers/turing_1950_gold.json",
    "watsoncrick": "experiments/ground_truth/real_papers/watson_crick_1953_gold.json",
    "park": "experiments/ground_truth/real_papers/park_2023_gold.json",
    "noyzhang": "experiments/ground_truth/real_papers/noy_zhang_2023_gold.json",
    "hubinger": "experiments/ground_truth/real_papers/hubinger_2024_gold.json",
    "hayes": "experiments/ground_truth/real_papers/hayes_2006_gold.json",
}

PAPER_TO_PDF = {
    "T7": "experiments/ground_truth/trap_papers/T7_scaling_noise.pdf",
    "einstein": "pdfs/99_test_extreme/Einstein_1905_Relativity_German.pdf",
    "edmondson": "pdfs/06_Psychological_Safety/Edmondson_1999_Psychological_Safety.pdf",
    "wei": "pdfs/05_AI_Safety/Wei_2022_Chain_of_Thought.pdf",
    "barney": "pdfs/01_OB/Barney_1991_Firm_Resources.pdf",
    "vaswani": "pdfs/02_CS_AI_LLM/Vaswani_2017_Attention_Is_All_You_Need.pdf",
    "shannon": "pdfs/entropy.pdf",
    "turing": "pdfs/Computing Machinery and Intelligence by Alan Turing.pdf",
    "watsoncrick": "pdfs/WatsonCrick1953.pdf",
    "park": "pdfs/02_CS_AI_LLM/Park_2023_Generative_Agents.pdf",
    "noyzhang": "pdfs/01_OB/Noy_Zhang_2023_Productivity_GenAI.pdf",
    "hubinger": "pdfs/05_AI_Safety/Hubinger_2024_Sleeper_Agents.pdf",
    "hayes": "pdfs/04_ACT_RFT/Hayes_2006_ACT_Model.pdf",
}


def quality_score(axes: dict, eq_count: int, has_gold_equations: bool) -> float:
    """Composite score for picking best extraction per paper."""
    cov = axes.get("coverage", 0)
    disc = axes.get("eq_discipline") or 0
    core_eq = axes.get("core_eq_fidelity", 0)

    # Paper-type aware weights:
    # - if the paper has gold equations, core_eq matters
    # - otherwise, coverage and discipline drive the score
    if has_gold_equations:
        return cov * 0.5 + core_eq * 0.4 + (disc * 0.1 if eq_count > 0 else 0)
    return cov * 0.7 + (disc * 0.3 if eq_count > 0 else 0.3)  # text-only papers don't penalize 0 eqs


def main() -> None:
    manifest: dict[str, dict] = {}

    for paper_id, gold_rel in PAPER_TO_GOLD.items():
        gold = ROOT / gold_rel
        if not gold.exists():
            continue

        # Read gold once to know if it has equations
        gold_data = json.loads(gold.read_text(encoding="utf-8"))
        has_gold_eq = bool(gold_data.get("equations"))

        # Collect all candidate runs for this paper across R-series
        # New papers (vaswani/shannon/turing/etc): R55-R59 are the Stage C series
        # Existing papers (T7/einstein/etc): also include earlier R3x-R5x which had v0.13/v0.16b
        candidates = []
        for rd in sorted((ROOT / "experiments" / "runs").glob(f"*_*_{paper_id}_s*")):
            ext = rd / "extraction.json"
            if not ext.exists() or ext.stat().st_size < 100:
                continue
            try:
                res = score(ext, gold)
                axes = res["axes"]
                eq_count = res.get("equations_captured", 0)
                q = quality_score(axes, eq_count, has_gold_eq)
                candidates.append({
                    "run_dir": rd.name,
                    "extraction_path": str(ext),
                    "axes": axes,
                    "eq_count": eq_count,
                    "quality_score": q,
                })
            except Exception as e:
                continue

        if not candidates:
            print(f"  WARN no candidates for {paper_id}")
            continue

        candidates.sort(key=lambda x: x["quality_score"], reverse=True)
        best = candidates[0]
        # Identify variant from run dir name
        variant = "?"
        for v in ("v0.16e", "v16e", "v0.16d", "v16d", "v0.16c", "v16c",
                  "v0.16b", "v16b", "v0.13", "v13", "v0.12e", "v12e",
                  "v0.11", "v11", "v0.3", "v03"):
            if "_" + v + "_" in best["run_dir"] or "_" + v + "_" in best["run_dir"].replace("v0.","v"):
                variant = v
                break
        manifest[paper_id] = {
            "best_run_dir": best["run_dir"],
            "extraction_path": best["extraction_path"],
            "pdf_path": str(ROOT / PAPER_TO_PDF[paper_id]),
            "gold_path": str(gold),
            "variant": variant,
            "axes": best["axes"],
            "eq_count": best["eq_count"],
            "quality_score": round(best["quality_score"], 4),
            "n_candidates": len(candidates),
        }
        print(f"{paper_id:14s} → {variant} {best['run_dir']}  q={best['quality_score']:.3f}  "
              f"cov={best['axes'].get('coverage',0)*100:.1f}% (chose from {len(candidates)} runs)")

    out = ROOT / "experiments" / "VERIFICATION_MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nManifest -> {out}")


if __name__ == "__main__":
    main()
