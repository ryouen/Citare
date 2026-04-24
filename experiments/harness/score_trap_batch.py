"""Batch score the 6 trap paper runs against their gold fixtures.

Usage:
    python experiments/harness/score_trap_batch.py

Emits markdown to experiments/TRAP_SCORES.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))

from score_against_gold import score  # type: ignore

TRAP_DIR = ROOT / "experiments" / "ground_truth" / "trap_papers"
RUNS_DIR = ROOT / "experiments" / "runs"

# (trap_id, gold file, run_id prefix to match)
PAIRS = [
    ("T1", "T1_gold.json", "R37A_v11_trap_T1"),
    ("T2", "T2_gold.json", "R37B_v11_trap_T2"),
    ("T3", "T3_gold.json", "R37C_v11_trap_T3"),
    ("T4", "T4_gold.json", "R37D_v11_trap_T4"),
    ("T5", "T5_gold.json", "R37E_v11_trap_T5"),
    ("T6", "T6_gold.json", "R37F_v11_trap_T6"),
]


def find_run_dir(run_id_suffix: str) -> Path | None:
    matches = sorted(RUNS_DIR.glob(f"*_{run_id_suffix}"))
    return matches[-1] if matches else None


def main():
    rows = []
    for trap_id, gold_name, run_id in PAIRS:
        gold_path = TRAP_DIR / gold_name
        run_dir = find_run_dir(run_id)
        if run_dir is None:
            rows.append((trap_id, run_id, None, "RUN_NOT_FOUND", []))
            continue
        ext_path = run_dir / "extraction.json"
        if not ext_path.exists():
            rows.append((trap_id, run_id, run_dir.name, "NO_EXTRACTION", []))
            continue
        res = score(ext_path, gold_path)
        missed = [r["key"] for r in res["results"] if not r["matched"]]
        rows.append((trap_id, run_id, run_dir.name, res["coverage_score"], missed))

    out = ["# Trap paper scoring (v0.11 TeX)\n"]
    out.append("| Trap | Run dir | Coverage | Missed |")
    out.append("|------|---------|----------|--------|")
    for trap_id, run_id, run_name, cov, missed in rows:
        cov_s = f"{cov*100:.1f}%" if isinstance(cov, float) else str(cov)
        missed_s = ", ".join(missed) if missed else "-"
        rn = run_name or "-"
        out.append(f"| {trap_id} | {rn} | {cov_s} | {missed_s} |")
    report = "\n".join(out) + "\n"
    out_path = ROOT / "experiments" / "TRAP_SCORES.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"saved -> {out_path}")


if __name__ == "__main__":
    main()
