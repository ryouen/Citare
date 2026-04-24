"""Batch score 4 T7 runs (v0.1, v0.3, v0.10, v0.11) and emit report.

3 independent axes + middle_coverage + by-template breakdown.
No composition — each axis reported raw.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "harness"))

from score_against_gold import score  # type: ignore

TRAP_DIR = ROOT / "experiments" / "ground_truth" / "trap_papers"
RUNS_DIR = ROOT / "experiments" / "runs"

GOLD = TRAP_DIR / "T7_gold.json"

PAIRS = [
    ("v0.1 baseline", "R38A_v01_trap_T7"),
    ("v0.3 overlooked", "R38B_v03_trap_T7"),
    ("v0.10 combined", "R38C_v10_trap_T7"),
    ("v0.11 TeX", "R38D_v11_trap_T7"),
]


def find_run_dir(suffix: str):
    matches = sorted(RUNS_DIR.glob(f"*_{suffix}"))
    return matches[-1] if matches else None


def main():
    if not GOLD.exists():
        raise SystemExit(f"Gold not found: {GOLD}")

    rows = []
    details = {}
    for label, run_id in PAIRS:
        rd = find_run_dir(run_id)
        if rd is None:
            rows.append({"label": label, "run_id": run_id, "status": "RUN_NOT_FOUND"})
            continue
        ext = rd / "extraction.json"
        if not ext.exists():
            rows.append({"label": label, "run_id": run_id, "run_dir": rd.name, "status": "NO_EXTRACTION"})
            continue
        res = score(ext, GOLD)
        rows.append({
            "label": label,
            "run_id": run_id,
            "run_dir": rd.name,
            "axes": res["axes"],
            "eqs_captured": res["equations_captured"],
            "by_template": res["by_template"],
        })
        details[label] = res

    # Build report
    out = []
    out.append("# T7 Scoring — 4 prompts × 1 paper (More Data, Worse Models)\n")
    out.append("## Independent axes (no composite)\n")
    out.append("| Prompt | Coverage | Middle coverage | Integrity penalty | Equation fidelity | Equations captured |")
    out.append("|--------|----------|-----------------|-------------------|-------------------|---------------------|")
    for r in rows:
        if "axes" not in r:
            out.append(f"| {r['label']} | — | — | — | — | {r['status']} |")
            continue
        a = r["axes"]
        out.append(
            f"| {r['label']} | {a['coverage']*100:.1f}% | {a['middle_coverage']*100:.1f}% | "
            f"{a['integrity_penalty']*100:.1f}% | {a['equation_fidelity']*100:.1f}% | {r['eqs_captured']} |"
        )
    out.append("")

    out.append("## By-template coverage\n")
    out.append("| Prompt | DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM | paper.* |")
    out.append("|--------|-----------|----------|-----------------|------------|---------|")
    for r in rows:
        if "by_template" not in r:
            continue
        bt = r["by_template"]

        def _fmt(key):
            e = bt.get(key)
            if not e or e["total_w"] == 0:
                return "—"
            return f"{e['scored_w']/e['total_w']*100:.0f}%"

        out.append(
            f"| {r['label']} | {_fmt('DEFINITION')} | {_fmt('RELATION')} | {_fmt('EXISTENCE_CLAIM')} | "
            f"{_fmt('META_CLAIM')} | {_fmt('paper.paper_type')}/{_fmt('paper.default_causal_strength')} |"
        )
    out.append("")

    out.append("## Integrity (must-NOT-synthesize) — per prompt\n")
    for label, res in details.items():
        out.append(f"### {label}")
        for r in res.get("forbidden_results", []) or []:
            marker = "**HIT**" if r["synthesized"] else "clean"
            out.append(f"- `{r['key']}` ({marker}): {r['detail']}")
        out.append("")

    out.append("## Equation fidelity — per equation × prompt\n")
    eq_ids = [e["eq_id"] for e in (details[list(details)[0]].get("eq_results") or []) if details]
    header = "| Equation | Page |" + "".join(f" {lbl} |" for lbl, _ in PAIRS)
    sep = "|----------|------|" + "--------|" * len(PAIRS)
    out.append(header)
    out.append(sep)
    for eq_id in eq_ids:
        row = f"| {eq_id} |"
        first = True
        page = "?"
        for label, _ in PAIRS:
            res = details.get(label)
            if not res:
                row += " — |"
                continue
            eq_res = next((e for e in res.get("eq_results", []) if e["eq_id"] == eq_id), None)
            if not eq_res:
                row += " — |"
                continue
            if first:
                page = eq_res.get("expected_source_page")
                first = False
            row += f" {eq_res['fraction']*100:.0f}% |"
        row = row.replace("| — |", f" {page} |", 1) if "| — |" in row else f"| {eq_id} | {page} |" + row.split("|", 2)[2]
        out.append(row)
    out.append("")

    # Write
    report = "\n".join(out) + "\n"
    out_path = ROOT / "experiments" / "T7_SCORES.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nsaved -> {out_path}")


if __name__ == "__main__":
    main()
