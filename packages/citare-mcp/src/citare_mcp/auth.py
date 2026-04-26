"""Per-key authentication + scope registry for Citare MCP.

The registry is a single JSON file (chmod 600 expected) holding all issued
Bearer keys with their labels, scopes, and (for Phase 2) cost ledgers. The
file is shared between the read and admin containers via a bind-mount so
that revocation propagates without restart — every request reloads the
registry from disk (cheap; tens of KB at most).

Bearer keys are stored in plaintext; the file's filesystem permissions are
the security boundary. Hashing the key would buy nothing here (the file
already contains all auth state, including budgets).
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---- Scopes ----------------------------------------------------------------

SCOPE_WRITE_LOCAL = "write_local"        # call register_claims with locally-extracted JSON
SCOPE_SERVER_EXTRACT = "server_extract"  # call extract_and_register (Phase 2)

ALL_SCOPES = (SCOPE_WRITE_LOCAL, SCOPE_SERVER_EXTRACT)


@dataclass
class KeyInfo:
    """A single issued API key.

    `key` is the secret material; never log it. `label` is a human-readable
    handle ("ishii", "alice@example.com") used for audit and revocation.
    """
    key: str
    label: str
    scopes: list[str]
    created_at: str
    revoked_at: str | None = None
    monthly_budget_usd: float = 0.0
    spent_this_month_usd: float = 0.0
    month_started: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m"))
    notes: str | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def has_scope(self, scope: str) -> bool:
        return self.is_active and scope in self.scopes

    def remaining_budget_usd(self) -> float:
        return max(0.0, self.monthly_budget_usd - self.spent_this_month_usd)

    def to_public_dict(self) -> dict[str, Any]:
        """Serialise WITHOUT the secret key, for list/audit output."""
        return {
            "label": self.label,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "revoked_at": self.revoked_at,
            "monthly_budget_usd": self.monthly_budget_usd,
            "spent_this_month_usd": self.spent_this_month_usd,
            "month_started": self.month_started,
            "notes": self.notes,
            "key_preview": self.key[:8] + "..." if self.key else None,
        }


class KeyRegistry:
    """Thread-safe in-memory + on-disk registry of Bearer keys.

    Concurrency model: every mutation reloads-from-disk → mutates → atomic-rename
    on save. Two containers (read + admin) sharing the file each see fresh
    revocations within one request because lookup() rereads the file.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    # ---- I/O ---------------------------------------------------------------

    def _read(self) -> dict[str, KeyInfo]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        out: dict[str, KeyInfo] = {}
        for k, v in (data.get("keys") or {}).items():
            out[k] = KeyInfo(
                key=k,
                label=v.get("label", ""),
                scopes=list(v.get("scopes", [])),
                created_at=v.get("created_at", ""),
                revoked_at=v.get("revoked_at"),
                monthly_budget_usd=float(v.get("monthly_budget_usd", 0.0)),
                spent_this_month_usd=float(v.get("spent_this_month_usd", 0.0)),
                month_started=v.get("month_started", datetime.now(timezone.utc).strftime("%Y-%m")),
                notes=v.get("notes"),
            )
        return out

    def _write(self, keys: dict[str, KeyInfo]) -> None:
        payload = {
            "version": 1,
            "keys": {
                k: {
                    "label": ki.label,
                    "scopes": ki.scopes,
                    "created_at": ki.created_at,
                    "revoked_at": ki.revoked_at,
                    "monthly_budget_usd": ki.monthly_budget_usd,
                    "spent_this_month_usd": ki.spent_this_month_usd,
                    "month_started": ki.month_started,
                    "notes": ki.notes,
                }
                for k, ki in keys.items()
            },
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        # 0o644: owner rw, group/other r. The file lives under /home/ubuntu
        # (parent dir 0o750) on the VPS, so "other" cannot reach it from the
        # filesystem; mode 0o644 is needed so the container user (different
        # UID) can read via the bind-mount. Do NOT relax parent dir.
        os.chmod(tmp, 0o644)
        tmp.replace(self.path)

    # ---- public API --------------------------------------------------------

    def lookup(self, bearer: str) -> KeyInfo | None:
        """Return the KeyInfo for a Bearer value, or None if invalid/revoked."""
        if not bearer:
            return None
        keys = self._read()
        ki = keys.get(bearer)
        if ki is None or not ki.is_active:
            return None
        # Lazy month rollover — keep budget per calendar month
        cur_month = datetime.now(timezone.utc).strftime("%Y-%m")
        if ki.month_started != cur_month:
            ki.spent_this_month_usd = 0.0
            ki.month_started = cur_month
            with self._lock:
                fresh = self._read()
                if bearer in fresh:
                    fresh[bearer].spent_this_month_usd = 0.0
                    fresh[bearer].month_started = cur_month
                    self._write(fresh)
        return ki

    def issue(
        self,
        label: str,
        scopes: list[str],
        monthly_budget_usd: float = 0.0,
        notes: str | None = None,
    ) -> KeyInfo:
        for s in scopes:
            if s not in ALL_SCOPES:
                raise ValueError(f"unknown scope: {s} (allowed: {ALL_SCOPES})")
        with self._lock:
            keys = self._read()
            new_key = secrets.token_urlsafe(32)
            while new_key in keys:  # near-impossible, defensive
                new_key = secrets.token_urlsafe(32)
            ki = KeyInfo(
                key=new_key,
                label=label,
                scopes=list(scopes),
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                monthly_budget_usd=monthly_budget_usd,
                notes=notes,
            )
            keys[new_key] = ki
            self._write(keys)
            return ki

    def revoke(self, label_or_prefix: str) -> KeyInfo | None:
        """Revoke by exact label OR by key-preview prefix. Returns the revoked key, or None."""
        with self._lock:
            keys = self._read()
            target_key: str | None = None
            for k, ki in keys.items():
                if ki.label == label_or_prefix or k.startswith(label_or_prefix):
                    if ki.is_active:
                        target_key = k
                        break
            if target_key is None:
                return None
            keys[target_key].revoked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._write(keys)
            return keys[target_key]

    def list_active(self) -> list[KeyInfo]:
        return [ki for ki in self._read().values() if ki.is_active]

    def list_all(self) -> list[KeyInfo]:
        return list(self._read().values())

    def charge(self, bearer: str, amount_usd: float) -> tuple[bool, float]:
        """Charge a key. Returns (ok, remaining_budget). Phase 2 uses this."""
        with self._lock:
            keys = self._read()
            ki = keys.get(bearer)
            if ki is None or not ki.is_active:
                return False, 0.0
            new_spent = ki.spent_this_month_usd + amount_usd
            if new_spent > ki.monthly_budget_usd:
                return False, max(0.0, ki.monthly_budget_usd - ki.spent_this_month_usd)
            keys[bearer].spent_this_month_usd = new_spent
            self._write(keys)
            return True, max(0.0, ki.monthly_budget_usd - new_spent)
