"""Weekly: verify the most recent Dropbox backup can be restored.

A backup that can't restore is worse than no backup — it's a false sense of
safety. This script proves the round-trip works: download the latest .db.gz,
decompress, open with SQLite, run integrity_check, count rows in the key
tables, and compare to the live production DB.

Run via cron (weekly is plenty — daily is overkill for a daily backup):
    20 4 * * 0  python3 /home/ubuntu/citare/scripts/verify_backup_restore.py \
        >> /home/ubuntu/citare/data/restore_verify.log 2>&1

Exit codes:
  0  — backup verified (integrity OK, row counts within sane range vs prod)
  1  — backup verifies as a SQLite file but row counts look wrong
        (e.g. production has 89 papers, backup has 0 — something is off)
  2  — backup is unreadable, corrupted, or download failed
        (catastrophic; the backup chain is broken)

The Phase β plan is to wire exit !=0 into a Claude Code spawn so an agent
can investigate; for now the script just logs and exits.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.local/lib"))
import dbx  # noqa: E402

DBX_BACKUP_DIR = "/ai/CitareOpus47/backups"
PROD_DB = Path(os.environ.get("CITARE_DB", "/home/ubuntu/citare/data/citare.db"))

# Key tables we care about. If any of these is missing or empty in the
# backup while the production DB has rows, treat it as anomaly.
KEY_TABLES = ["papers", "claims", "claim_relations", "paper_identifiers"]

# A backup is "sane" if its row count is at least this fraction of production.
# Backups are up to 24h old, so they should be slightly behind production but
# in the same ballpark. 0.3 = "backup has at least 30% of what prod has" —
# tolerates aggressive growth bursts (e.g. R89 dispatcher adding 30+ papers
# in a few hours), still flags catastrophic loss (e.g. backup at 5% of prod).
# An anomaly here is exit-1 (informational), separate from integrity failures
# which are exit-2 (catastrophic).
COUNT_RATIO_FLOOR = 0.3


def _latest_backup_meta() -> dict:
    """Find the most recent citare.YYYY-MM-DD.db.gz on Dropbox."""
    entries = dbx.list_folder(DBX_BACKUP_DIR)
    backups = [
        e for e in entries
        if e.get(".tag") == "file"
        and e["name"].startswith("citare.")
        and e["name"].endswith(".db.gz")
    ]
    if not backups:
        raise SystemExit("FAIL: no backups found in " + DBX_BACKUP_DIR)
    backups.sort(key=lambda e: e["name"])
    return backups[-1]


def _download(dbx_path: str, local: Path) -> int:
    at = dbx.get_access_token()
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/files/download", method="POST"
    )
    req.add_header("Authorization", f"Bearer {at}")
    req.add_header("Dropbox-API-Arg", json.dumps({"path": dbx_path}))
    with urllib.request.urlopen(req, timeout=180) as r:
        body = r.read()
    local.write_bytes(body)
    return len(body)


def _row_counts(db: sqlite3.Connection) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for t in KEY_TABLES:
        try:
            out[t] = db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except sqlite3.OperationalError:
            out[t] = None
    return out


def main() -> int:
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    print(f"[{started}] verify start")

    # 1. Find latest backup ----------------------------------------------
    meta = _latest_backup_meta()
    name = meta["name"]
    dbx_path = meta["path_display"]
    backup_size = meta.get("size", 0)
    print(f"  latest backup: {name} ({backup_size}b)")

    # 2. Download to tmp + decompress ------------------------------------
    with tempfile.TemporaryDirectory(prefix="citare_verify_") as tmp:
        tmp_path = Path(tmp)
        gz = tmp_path / name
        try:
            _download(dbx_path, gz)
        except Exception as e:
            print(f"FAIL: download failed: {e}", file=sys.stderr)
            return 2

        db_file = tmp_path / name.removesuffix(".gz")
        try:
            with gzip.open(gz, "rb") as fi, open(db_file, "wb") as fo:
                shutil.copyfileobj(fi, fo, length=1 << 20)
        except Exception as e:
            print(f"FAIL: gunzip failed (corrupted backup?): {e}", file=sys.stderr)
            return 2

        # 3. Open + integrity_check --------------------------------------
        try:
            with sqlite3.connect(str(db_file)) as db:
                integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    print(f"FAIL: integrity_check returned {integrity!r}", file=sys.stderr)
                    return 2
                bk_counts = _row_counts(db)
        except sqlite3.DatabaseError as e:
            print(f"FAIL: SQLite refused to open: {e}", file=sys.stderr)
            return 2

        # 4. Compare to production ---------------------------------------
        if not PROD_DB.exists():
            print(f"WARN: production DB not at {PROD_DB} — skipping ratio check")
            prod_counts = {}
        else:
            with sqlite3.connect(f"file:{PROD_DB}?mode=ro", uri=True) as p:
                prod_counts = _row_counts(p)

        anomalies: list[str] = []
        for t in KEY_TABLES:
            bk = bk_counts.get(t)
            pr = prod_counts.get(t)
            if bk is None:
                anomalies.append(f"{t}: missing from backup")
                continue
            if pr is None or pr == 0:
                continue  # nothing to compare against
            ratio = bk / pr if pr else 0
            print(f"  {t}: backup={bk} prod={pr} ratio={ratio:.2f}")
            if bk > pr:
                # Backup ahead of prod is impossible unless prod was rolled
                # back since the backup was taken. Worth flagging.
                anomalies.append(f"{t}: backup ({bk}) > prod ({pr})")
            elif ratio < COUNT_RATIO_FLOOR:
                anomalies.append(
                    f"{t}: backup ({bk}) is {ratio:.0%} of prod ({pr}) — below {COUNT_RATIO_FLOOR:.0%} floor"
                )

    finished = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if anomalies:
        print(f"[{finished}] verify ANOMALY:")
        for a in anomalies:
            print(f"  ! {a}")
        return 1
    print(f"[{finished}] verify OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
