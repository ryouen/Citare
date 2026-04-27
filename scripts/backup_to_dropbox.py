"""Daily Citare DB backup to Dropbox.

Steps:
 1. Use sqlite3 conn.backup() to produce a consistent snapshot (safe under
    concurrent writes; no file locking needed).
 2. gzip the snapshot.
 3. Upload to /ai/CitareOpus47/backups/citare.YYYY-MM-DD.db.gz
 4. Prune remote backups older than $RETAIN_DAYS (default 30).

Run via cron:
    30 3 * * *  python3 /home/ubuntu/citare/scripts/backup_to_dropbox.py >> /home/ubuntu/citare/data/backup.log 2>&1

Exits 0 on success, non-zero on any failure (so cron failure mail / monitoring
can notice).

Excludes: anything under *_old paths (per user's directive — old archives are
local-only references, not synced).
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import sqlite3
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/.local/lib"))
import dbx  # noqa: E402

SRC_DB = Path(os.environ.get("CITARE_DB", "/home/ubuntu/citare/data/citare.db"))
DBX_BACKUP_DIR = "/ai/CitareOpus47/backups"
RETAIN_DAYS = int(os.environ.get("CITARE_BACKUP_RETAIN_DAYS", "30"))


def _safety_check(path: Path) -> None:
    """Refuse to backup anything under a *_old directory."""
    parts = path.resolve().parts
    if any(p.endswith("_old") or "_old" in p for p in parts):
        raise SystemExit(f"REFUSE: source path is under an _old directory: {path}")


def _consistent_snapshot(src: Path, dst: Path) -> None:
    """Copy `src` to `dst` using SQLite's online backup API."""
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(str(dst)) as dst_conn:
            src_conn.backup(dst_conn)


def _gzip(plain: Path, gz: Path) -> None:
    with open(plain, "rb") as fi, gzip.open(gz, "wb", compresslevel=6) as fo:
        while True:
            chunk = fi.read(1 << 20)
            if not chunk:
                break
            fo.write(chunk)


def _upload(local: Path, dbx_path: str) -> dict:
    at = dbx.get_access_token()
    with open(local, "rb") as f:
        body = f.read()
    req = urllib.request.Request(
        "https://content.dropboxapi.com/2/files/upload", data=body, method="POST"
    )
    req.add_header("Authorization", f"Bearer {at}")
    req.add_header("Content-Type", "application/octet-stream")
    req.add_header(
        "Dropbox-API-Arg",
        json.dumps({"path": dbx_path, "mode": "overwrite", "autorename": False, "mute": True}),
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def _retention_decision(d: _dt.date, today: _dt.date) -> tuple[bool, str]:
    """Tiered retention: should the backup taken on date `d` be kept today?

    Tiers (a backup is kept if ANY tier wants it):
      - daily   : last 30 days
      - weekly  : Sunday backups, last 12 weeks (84 days)
      - monthly : 1st-of-month backups, last 12 months (365 days)
      - yearly  : Jan 1 backups, kept indefinitely

    Rationale: storage of one Citare backup is ~5 MB compressed, so a year
    of weekly + monthly + the yearly anchors costs <100 MB total — trivial
    on Dropbox. The point of tiering isn't to save bytes; it's to give us
    a useful timeline for "go back N months" recovery without storing 365
    daily files. The current uniform 30-day retention loses everything
    older than a month, which is the wrong cliff.
    """
    age = (today - d).days
    if age <= 30:
        return True, "daily"
    if d.weekday() == 6 and age <= 84:        # Sunday=6 in Python's calendar
        return True, "weekly"
    if d.day == 1 and age <= 365:
        return True, "monthly"
    if d.day == 1 and d.month == 1:
        return True, "yearly"
    return False, "expired"


def _prune(retain_days: int) -> int:
    """Apply the tiered retention policy to remote backups. Returns count deleted.

    `retain_days` is kept as the function arg for backward compat with the env
    var, but it no longer drives the policy directly — the tier table above
    does. The 30-day daily tier is the spiritual successor of `retain_days`.
    """
    today = _dt.date.today()
    try:
        entries = dbx.list_folder(DBX_BACKUP_DIR)
    except Exception:
        return 0
    deleted = 0
    kept_summary: dict[str, int] = {"daily": 0, "weekly": 0, "monthly": 0, "yearly": 0}
    for e in entries:
        if e[".tag"] != "file":
            continue
        name = e["name"]
        if not (name.startswith("citare.") and name.endswith(".db.gz")):
            continue
        try:
            datepart = name[len("citare."):-len(".db.gz")]
            d = _dt.date.fromisoformat(datepart)
        except ValueError:
            continue
        keep, tier = _retention_decision(d, today)
        if keep:
            kept_summary[tier] = kept_summary.get(tier, 0) + 1
            continue
        try:
            dbx.rpc("files/delete_v2", {"path": e["path_display"]})
            deleted += 1
            print(f"  pruned ({tier}): {name}")
        except Exception as ex:
            print(f"  prune failed for {name}: {ex}", file=sys.stderr)
    print(f"  retention kept: " + ", ".join(f"{k}={v}" for k, v in kept_summary.items()))
    return deleted


def main() -> int:
    started = _dt.datetime.now(_dt.timezone.utc).isoformat()
    print(f"[{started}] backup start: src={SRC_DB}")

    _safety_check(SRC_DB)
    if not SRC_DB.exists():
        print(f"FAIL: source DB does not exist: {SRC_DB}", file=sys.stderr)
        return 2

    today = _dt.date.today().isoformat()
    with tempfile.TemporaryDirectory(prefix="citare_bk_") as tmp:
        tmp_path = Path(tmp)
        snap = tmp_path / f"citare.{today}.db"
        gz = tmp_path / f"citare.{today}.db.gz"

        _consistent_snapshot(SRC_DB, snap)
        _gzip(snap, gz)
        size = gz.stat().st_size

        dbx_path = f"{DBX_BACKUP_DIR}/citare.{today}.db.gz"
        meta = _upload(gz, dbx_path)
        print(f"  uploaded: {dbx_path} ({size} bytes, rev={meta.get('rev')})")

    deleted = _prune(RETAIN_DAYS)
    print(f"  pruned {deleted} old backups (retain={RETAIN_DAYS}d)")

    finished = _dt.datetime.now(_dt.timezone.utc).isoformat()
    print(f"[{finished}] backup OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
