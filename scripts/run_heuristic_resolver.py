"""Run the second-pass heuristic resolver over pending_llm_review entries.

Usage:
    python scripts/run_heuristic_resolver.py [--db data/citare.db]

This calls citare_db.resolver.resolve_pending_heuristic, which scans every
unresolved 'paper_reference_resolution' pending row and tries a relaxed
triple match (year + any-surname-overlap + title Jaccard >= 0.3) against the
papers table. Single-candidate rows with title overlap >= 0.5 are auto-
resolved into citation_edges with method='llm_batch', confidence=0.7. The
remainder is left for a future LLM pass.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from citare_db.resolver import resolve_pending_heuristic  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(ROOT / "data" / "citare.db"),
                    help="Path to the Citare SQLite database")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        report = resolve_pending_heuristic(conn)
    finally:
        conn.close()

    print(f"DB: {db_path}")
    print(f"scanned        : {report.scanned}")
    print(f"auto_resolved  : {report.resolved_by_triple}")
    print(f"already_resolved: {report.already_resolved}")
    print(f"still_pending  : {report.unresolved_after_chain}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
