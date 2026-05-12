#!/usr/bin/env python3
"""Scan all papers in the Citare DB for Phase-D-class under-registration.

Applies the paper_quality flags retroactively to every paper. Emits two
outputs:

  - phase_d_candidates.json: papers with confidence_tier=LOW and a
    recommended_action of RE_EXTRACT (these are the strong candidates
    for re-extraction)
  - phase_d_full_report.json: full quality breakdown for every paper
    (useful for tier-distribution analysis)

Usage:
    python scripts/scan_phase_d_candidates.py [--db PATH] [--out-dir DIR]

Default DB: /home/ubuntu/citare/data/citare.db
Default out dir: /home/ubuntu/citare/data/
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "packages/citare-mcp/src"
sys.path.insert(0, str(SRC))

from citare_mcp.quality_flags import compute_paper_quality_from_db


def scan(db_path: str, out_dir: str) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    papers = conn.execute(
        "SELECT id, canonical_title, paper_type, year, "
        "(SELECT COUNT(*) FROM claims WHERE paper_id = papers.id) AS claim_count "
        "FROM papers "
        "ORDER BY id"
    ).fetchall()

    full_report: list[dict] = []
    candidates: list[dict] = []
    tier_counts: Counter = Counter()
    action_counts: Counter = Counter()

    for p in papers:
        quality = compute_paper_quality_from_db(conn, p["id"])
        tier_counts[quality["confidence_tier"]] += 1
        action_counts[quality["recommended_action"] or "none"] += 1

        entry = {
            "paper_id": p["id"],
            "title": p["canonical_title"],
            "paper_type": p["paper_type"],
            "year": p["year"],
            "claim_count": quality["claim_count"],
            "confidence_tier": quality["confidence_tier"],
            "flags": quality["flags"],
            "recommended_action": quality["recommended_action"],
        }
        full_report.append(entry)

        if quality["confidence_tier"] == "LOW" and quality["recommended_action"] == "RE_EXTRACT":
            candidates.append(entry)

    conn.close()

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    cand_path = out_path / "phase_d_candidates.json"
    full_path = out_path / "phase_d_full_report.json"

    cand_path.write_text(json.dumps({
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "db_path": db_path,
        "total_papers_scanned": len(papers),
        "low_tier_count": tier_counts.get("LOW", 0),
        "re_extract_recommended_count": len(candidates),
        "candidates": candidates,
    }, indent=2, ensure_ascii=False))

    full_path.write_text(json.dumps({
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "db_path": db_path,
        "tier_distribution": dict(tier_counts),
        "action_distribution": dict(action_counts),
        "papers": full_report,
    }, indent=2, ensure_ascii=False))

    # Summary
    print(f"Scanned {len(papers)} papers from {db_path}")
    print()
    print("Tier distribution:")
    for tier in ("HIGH", "MEDIUM", "LOW"):
        n = tier_counts.get(tier, 0)
        pct = (100 * n / len(papers)) if papers else 0
        print(f"  {tier:6s} {n:4d}  ({pct:.1f}%)")
    print()
    print("Recommended action distribution:")
    for action, n in sorted(action_counts.items(), key=lambda x: -x[1]):
        print(f"  {action or 'none':25s} {n:4d}")
    print()
    print(f"RE_EXTRACT candidates: {len(candidates)}")
    print(f"  → {cand_path}")
    print(f"Full report: {full_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/home/ubuntu/citare/data/citare.db")
    ap.add_argument("--out-dir", default="/home/ubuntu/citare/data")
    args = ap.parse_args()
    if not Path(args.db).exists():
        print(f"ERROR: DB not found at {args.db}", file=sys.stderr)
        return 1
    return scan(args.db, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
