"""Seed the Citare SQLite DB from experiments/runs/ extractions.

Usage:
    python scripts/seed_citare_db.py [--db data/citare.db]

Selects one extraction per paper (preferring v0.11 > v0.3 > newest) and
ingests it into the DB. Prints a summary of papers, claims, and integrity
warnings per paper_type.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "citare-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from citare_db import init_db, ingest_extraction_file  # noqa: E402


def _prompt_priority(prompt_version: str | None) -> int:
    """Higher is better. Prefer v0.11 (equations) > v0.3 (text) > others."""
    if not prompt_version:
        return 0
    v = prompt_version.lower()
    if "v0.12e" in v or "v0.12" in v:
        return 5
    if "v0.11" in v or "v11" in v:
        return 4
    if "v0.3" in v or "v0_3" in v or "v03" in v:
        return 3
    if "v0.10" in v or "v0_10" in v:
        return 2
    return 1


def pick_best_per_paper() -> list[Path]:
    """For each paper DOI, return the best extraction to ingest."""
    runs = sorted((ROOT / "experiments" / "runs").glob("*/extraction.json"))
    by_doi: dict[str, tuple[int, Path]] = {}
    for fp in runs:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        paper = d.get("paper") or {}
        doi = paper.get("doi") or ("__synth:" + (paper.get("title") or fp.parent.name))
        version = None
        meta = d.get("paper") or {}
        version = (
            meta.get("extraction_prompt_version")
            or d.get("extraction_prompt_version")
            or fp.parent.name
        )
        prio = _prompt_priority(str(version))
        if doi not in by_doi or prio > by_doi[doi][0]:
            by_doi[doi] = (prio, fp)
    return [fp for _, fp in by_doi.values()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "citare.db"))
    args = ap.parse_args()
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    print(f"[seed] initialising DB at {db_path}")
    conn = init_db(db_path)
    picks = pick_best_per_paper()
    print(f"[seed] {len(picks)} extractions selected (one per paper)")

    ok = fail = 0
    for fp in picks:
        try:
            doi = ingest_extraction_file(conn, fp)
            ok += 1
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {fp.parent.name}: {type(e).__name__}: {e}")
            fail += 1
    print(f"[seed] ingested: {ok}/{len(picks)} (failures: {fail})")

    # Summary
    print("\n=== DB summary ===")
    pcount = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    ccount = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    rcount = conn.execute("SELECT COUNT(*) FROM claim_relations").fetchone()[0]
    warn_count = conn.execute(
        "SELECT COUNT(*) FROM claim_relations WHERE incompleteness_category != 'none'"
    ).fetchone()[0]
    print(f"  papers:          {pcount}")
    print(f"  claims:          {ccount}")
    print(f"  relations:       {rcount}")
    print(f"  with warnings:   {warn_count}")
    print("  by template:")
    for row in conn.execute(
        "SELECT template_type, COUNT(*) FROM claims GROUP BY template_type ORDER BY 2 DESC"
    ):
        print(f"    {row[0]:20s} {row[1]}")
    print("  by design_basis:")
    for row in conn.execute(
        "SELECT COALESCE(design_basis_idx,'(null)'), COUNT(*) FROM claims GROUP BY 1 ORDER BY 2 DESC LIMIT 8"
    ):
        print(f"    {row[0]:30s} {row[1]}")


if __name__ == "__main__":
    main()
