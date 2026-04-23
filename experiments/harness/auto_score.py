"""
Auto-score all unscored runs by matching PDF filename to gold fixtures.

Usage:
    python auto_score.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "experiments" / "runs"
GOLD_DIR = ROOT / "experiments" / "ground_truth" / "real_papers"
SCORER = ROOT / "experiments" / "harness" / "score_against_gold.py"

# Map PDF filename substrings -> gold fixture
PDF_TO_GOLD = [
    ("Edmondson_1999", "edmondson_1999_gold.json"),
    ("Barney_1991", "barney_1991_gold.json"),
    ("DellAcqua_2023", "dellacqua_2023_gold.json"),
    ("Noy_Zhang_2023", "noy_zhang_2023_gold.json"),
    ("Vaswani_2017", "vaswani_2017_gold.json"),
    ("Hayes_2006", "hayes_2006_gold.json"),
    ("Wei_2022", "wei_2022_gold.json"),
    ("Einstein_1905", "einstein_1905_gold.json"),
    ("WatsonCrick1953", "watson_crick_1953_gold.json"),
    ("Computing Machinery", "turing_1950_gold.json"),
    ("Turing", "turing_1950_gold.json"),
    ("entropy", "shannon_1948_gold.json"),
    ("Shannon", "shannon_1948_gold.json"),
    ("Hubinger_2024", "hubinger_2024_gold.json"),
    ("Sleeper_Agents", "hubinger_2024_gold.json"),
]


def find_gold(pdf_name: str) -> Path | None:
    for needle, gold in PDF_TO_GOLD:
        if needle in pdf_name:
            g = GOLD_DIR / gold
            if g.exists():
                return g
    return None


def main():
    force = "--force" in sys.argv
    scored = 0
    skipped = 0
    unscored = 0
    for run_dir in sorted(RUNS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        metrics = run_dir / "metrics.json"
        if not metrics.exists():
            continue
        extraction = run_dir / "extraction.json"
        if not extraction.exists():
            continue
        score_file = run_dir / "score.json"
        if score_file.exists() and not force:
            skipped += 1
            continue
        m = json.loads(metrics.read_text(encoding="utf-8"))
        pdf = m.get("pdf_filename", "")
        gold = find_gold(pdf)
        if not gold:
            print(f"[no-gold] {run_dir.name}  (pdf={pdf})")
            unscored += 1
            continue
        try:
            result = subprocess.run(
                ["python", str(SCORER),
                 "--extraction", str(extraction),
                 "--gold", str(gold),
                 "--save", str(score_file)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={"PYTHONIOENCODING": "utf-8", **__import__("os").environ},
            )
            head = (result.stdout or "").splitlines()[0] if result.stdout else "(no output)"
            print(f"[scored ] {run_dir.name}  {head}")
            scored += 1
        except Exception as e:
            print(f"[error  ] {run_dir.name}  {e}")
            unscored += 1

    print(f"\nScored: {scored}  Skipped (already): {skipped}  Unscored: {unscored}")


if __name__ == "__main__":
    main()
