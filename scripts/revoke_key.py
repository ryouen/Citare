"""Revoke a Citare admin key by label or key-prefix.

Usage:
    python scripts/revoke_key.py --label alice
    python scripts/revoke_key.py --prefix 608adf29
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "citare-mcp" / "src"))

from citare_mcp.auth import KeyRegistry  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Revoke a Citare admin key.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--label", help="Exact label match")
    g.add_argument("--prefix", help="Key prefix (first ~8 chars from list_keys output)")
    p.add_argument(
        "--registry",
        default=os.environ.get("CITARE_KEY_REGISTRY", str(_REPO / "data" / "api_keys.json")),
    )
    args = p.parse_args()

    registry = KeyRegistry(args.registry)
    target = args.label if args.label else args.prefix
    ki = registry.revoke(target)
    if ki is None:
        print(f"No active key matching '{target}'", file=sys.stderr)
        return 1
    print(f"Revoked: label={ki.label} preview={ki.key[:8]}... at {ki.revoked_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
