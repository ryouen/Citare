"""Tournament: score v0.1 / v0.3 / v0.10 / v0.11 / v0.12a-e on T7, emit markdown.

Reports 5 independent axes (no composite):
 - coverage, middle_coverage, integrity_penalty
 - core_eq_fidelity  (central_contribution + supporting_definition only)
 - eq_discipline     (1 - decorative_extracted / decorative_expected)

Winner pick: coverage>=95 AND core_eq>=85 AND eq_discipline>=80.
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
    ("v0.1 baseline",    "R38A_v01_trap_T7"),
    ("v0.3 overlooked",  "R38B_v03_trap_T7"),
    ("v0.10 combined",   "R38C_v10_trap_T7"),
    ("v0.11 TeX",        "R38D_v11_trap_T7"),
    ("v0.12a TERSE",     "R39A_v12a_terse_T7"),
    ("v0.12b TRIAGE",    "R39B_v12b_triage_T7"),
    ("v0.12d ORDER",     "R39D_v12d_order_T7"),
    ("v0.12e STATUS",    "R39E_v12e_status_T7"),
    ("v0.12f DISCIPLINE","R39F_v12f_discipline_T7"),
    ("v0.12g TOP-PRIME", "R39G2_v12g_top_prime_T7"),
]


def find_run_dir(suffix: str):
    matches = sorted(RUNS_DIR.glob(f"*_{suffix}"))
    return matches[-1] if matches else None


def main():
    rows = []
    details = {}
    for label, run_id in PAIRS:
        rd = find_run_dir(run_id)
        if rd is None:
            rows.append({"label": label, "run_id": run_id, "status": "RUN_NOT_FOUND"})
            continue
        ext = rd / "extraction.json"
        if not ext.exists():
            rows.append({"label": label, "run_id": run_id, "status": "NO_EXTRACTION"})
            continue
        res = score(ext, GOLD)
        rows.append({
            "label": label,
            "run_id": run_id,
            "run_dir": rd.name,
            "axes": res["axes"],
            "eqs_captured": res["equations_captured"],
            "dec_extracted": res.get("decorative_extracted", 0),
            "dec_expected": res.get("decorative_expected", 0),
            "by_template": res["by_template"],
        })
        details[label] = res

    out = []
    out.append("# T7 Tournament — 8 prompts × 1 paper (More Data, Worse Models, 21p)\n")
    out.append("## Five independent axes — no composite\n")
    out.append("| # | Prompt | Coverage | Middle | Integrity penalty | Core eq fidelity | Eq discipline | All eqs | Decorative extracted |")
    out.append("|---|--------|----------|--------|-------------------|------------------|---------------|---------|---------------------|")
    for i, r in enumerate(rows, 1):
        if "axes" not in r:
            out.append(f"| {i} | {r['label']} | — | — | — | — | — | — | {r['status']} |")
            continue
        a = r["axes"]
        disc = a.get("eq_discipline")
        disc_s = f"{disc*100:.0f}%" if disc is not None else "n/a"
        out.append(
            f"| {i} | {r['label']} | {a['coverage']*100:.1f}% | {a['middle_coverage']*100:.1f}% | "
            f"{a['integrity_penalty']*100:.1f}% | {a['core_eq_fidelity']*100:.1f}% | {disc_s} | "
            f"{r['eqs_captured']} | {r['dec_extracted']}/{r['dec_expected']} |"
        )
    out.append("")

    # Winner picks
    winners = []
    for r in rows:
        if "axes" not in r:
            continue
        a = r["axes"]
        disc = a.get("eq_discipline") or 0
        if a["coverage"] >= 0.95 and a["core_eq_fidelity"] >= 0.85 and disc >= 0.80:
            winners.append(r["label"])
    out.append("## Winner check (coverage>=95 AND core_eq>=85 AND discipline>=80)\n")
    if winners:
        out.append("**Passes all three thresholds:** " + ", ".join(f"`{w}`" for w in winners))
    else:
        out.append("No variant passes all three thresholds. Fallback: v0.3 + v0.11 parallel dual-run.")
    out.append("")

    # By-template
    out.append("## By-template coverage\n")
    out.append("| Prompt | DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM |")
    out.append("|--------|------------|----------|-----------------|------------|")
    for r in rows:
        if "by_template" not in r:
            continue
        bt = r["by_template"]
        def _fmt(key):
            e = bt.get(key)
            if not e or e["total_w"] == 0:
                return "—"
            return f"{e['scored_w']/e['total_w']*100:.0f}%"
        out.append(f"| {r['label']} | {_fmt('DEFINITION')} | {_fmt('RELATION')} | {_fmt('EXISTENCE_CLAIM')} | {_fmt('META_CLAIM')} |")
    out.append("")

    # Equation triage table
    out.append("## Per-equation fidelity (with status)\n")
    first_details = next(iter(details.values()), None)
    if first_details:
        eq_specs = first_details.get("eq_results", [])
        header = "| Equation | Status | Weight |" + "".join(f" {lbl} |" for lbl, _ in PAIRS if lbl in details)
        sep = "|----------|--------|--------|" + "--------|" * len([l for l, _ in PAIRS if l in details])
        out.append(header)
        out.append(sep)
        for eq_spec in eq_specs:
            eq_id = eq_spec["eq_id"]
            status = eq_spec.get("equation_status", "?")
            weight = eq_spec.get("weight")
            row = f"| {eq_id} | {status} | {weight} |"
            for label, _ in PAIRS:
                if label not in details:
                    continue
                er = next((e for e in details[label].get("eq_results", []) if e["eq_id"] == eq_id), None)
                if er is None:
                    row += " — |"
                else:
                    row += f" {er['fraction']*100:.0f}% |"
            out.append(row)
    out.append("")

    report = "\n".join(out) + "\n"
    out_path = ROOT / "experiments" / "T7_TOURNAMENT.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nsaved -> {out_path}")


if __name__ == "__main__":
    main()
