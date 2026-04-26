"""Ingest champion extractions into Citare DB (script name historical).

Reads experiments/CITARE_REGISTRATION_MANIFEST.json (paper → best run_dir),
loads each extraction.json, and ingests via citare_db.ingest_extraction_file.

The script name "v013d" is from the original 13-paper benchmark batch (v0.13d
era). The current manifest references 81 papers, mostly with v0.13g extractions
after the 2026-04-26 production lock change. The script itself is
prompt-version-agnostic — it ingests whatever the manifest points to.

By default re-creates the DB at data/citare.db.

Usage:
    python scripts/ingest_v013d_champions.py [--db data/citare.db] [--no-reset]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "citare-core" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "citare-db" / "src"))

from citare_db import init_db, ingest_extraction_file, resolve_citations  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "citare.db"))
    ap.add_argument("--no-reset", action="store_true",
                    help="Do not drop existing DB first")
    ap.add_argument("--manifest",
                    default=str(ROOT / "experiments" / "CITARE_REGISTRATION_MANIFEST.json"))
    args = ap.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists() and not args.no_reset:
        db_path.unlink()
        print(f"[ingest] dropped existing DB at {db_path}")

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    print(f"[ingest] loaded manifest: {len(manifest)} papers")

    conn = init_db(db_path)

    ok = fail = 0
    warnings_total = 0
    potential_dupes_total = 0
    failures = []
    for paper, info in manifest.items():
        run_dir = info["dir"]
        ext_path = ROOT / "experiments" / "runs" / run_dir / "extraction.json"
        if not ext_path.exists():
            print(f"  MISS  {paper:32s}  {run_dir} (no extraction.json)")
            fail += 1
            continue
        # Snapshot DB size before ingest so we can report claims_added
        # without depending on the IngestReport carrying the count.
        pre_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        try:
            report = ingest_extraction_file(conn, ext_path)
        except Exception as e:
            failures.append((paper, run_dir, type(e).__name__, str(e)))
            print(f"  FAIL  {paper:32s}  {run_dir}: {type(e).__name__}: {e}")
            fail += 1
            continue
        post_claims = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        ok += 1
        warnings_total += len(report.warnings)
        potential_dupes_total += len(report.potential_duplicate_claims)
        # cov / composite are optional in the new manifest (null for newly
        # added papers without a gold file). Format defensively.
        cov_val = info.get("cov")
        cov_str = f"{cov_val:.2f}" if isinstance(cov_val, (int, float)) else " — "
        added = max(0, post_claims - pre_claims)
        print(f"  OK    {paper:32s}  cov={cov_str}  "
              f"claims_added={added:3d}  warnings={len(report.warnings)}")

    print(f"\n[ingest] ingested: {ok}/{len(manifest)} (failures: {fail})")
    print(f"[ingest] warnings: {warnings_total}, potential_duplicate_claims: {potential_dupes_total}")

    print("\n[ingest] running citation resolver...")
    resv = resolve_citations(conn)
    print(f"  scanned={resv.scanned} by_identifier={resv.resolved_by_identifier} "
          f"by_triple={resv.resolved_by_triple} queued_for_llm={resv.queued_for_llm}")

    print("\n=== DB summary ===")
    pcount = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    ccount = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    rcount = conn.execute("SELECT COUNT(*) FROM claim_relations").fetchone()[0]
    warn_count = conn.execute(
        "SELECT COUNT(*) FROM claim_relations WHERE incompleteness_category != 'none'"
    ).fetchone()[0]
    print(f"  papers:        {pcount}")
    print(f"  claims:        {ccount}")
    print(f"  relations:     {rcount}")
    print(f"  with warnings: {warn_count}")
    print("  by template:")
    for row in conn.execute(
        "SELECT template_type, COUNT(*) FROM claims GROUP BY template_type ORDER BY 2 DESC"
    ):
        print(f"    {row[0]:20s} {row[1]}")
    ct_count = conn.execute("SELECT COUNT(*) FROM citation_text").fetchone()[0]
    ce_count = conn.execute("SELECT COUNT(*) FROM citation_edges").fetchone()[0]
    pending = conn.execute("SELECT COUNT(*) FROM pending_llm_review").fetchone()[0]
    print(f"  citation_text: {ct_count}")
    print(f"  citation_edges:{ce_count} (resolved)")
    print(f"  pending_llm:   {pending}")

    if failures:
        print("\n=== Failures ===")
        for paper, run_dir, exc, msg in failures:
            print(f"  {paper}  {run_dir}  {exc}: {msg[:120]}")


if __name__ == "__main__":
    main()
