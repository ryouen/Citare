"""List Citare admin keys (without revealing the secret material).

Usage:
    python scripts/list_keys.py
    python scripts/list_keys.py --include-revoked
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "citare-mcp" / "src"))

from citare_mcp.auth import KeyRegistry  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="List Citare admin keys (audit view).")
    p.add_argument("--include-revoked", action="store_true")
    p.add_argument(
        "--registry",
        default=os.environ.get("CITARE_KEY_REGISTRY", str(_REPO / "data" / "api_keys.json")),
    )
    p.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = p.parse_args()

    registry = KeyRegistry(args.registry)
    keys = registry.list_all() if args.include_revoked else registry.list_active()

    if args.json:
        print(json.dumps([ki.to_public_dict() for ki in keys], indent=2))
        return 0

    if not keys:
        print("(no keys)")
        return 0
    print(f"{'LABEL':<25} {'PREVIEW':<12} {'SCOPES':<35} {'BUDGET':>10} {'SPENT':>10} STATUS")
    print("-" * 110)
    for ki in keys:
        status = "revoked" if ki.revoked_at else "active"
        scopes = ",".join(ki.scopes)[:34]
        print(
            f"{ki.label[:24]:<25} {ki.key[:8]+'...':<12} {scopes:<35} "
            f"${ki.monthly_budget_usd:>8.2f}  ${ki.spent_this_month_usd:>8.2f}  {status}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
