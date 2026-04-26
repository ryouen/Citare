"""Issue a new Citare admin key.

Usage:
    python scripts/issue_key.py --label "ishii" --scopes write_local,server_extract --budget 100
    python scripts/issue_key.py --label "alice" --scopes write_local --budget 0

The new key is printed ONCE to stdout. Store it carefully — it cannot be
recovered later.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running before `pip install -e`.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "packages" / "citare-mcp" / "src"))

from citare_mcp.auth import ALL_SCOPES, KeyRegistry  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Issue a new Citare admin Bearer key.")
    p.add_argument("--label", required=True, help="Human-readable handle (e.g. 'ishii', 'alice@example.com')")
    p.add_argument(
        "--scopes",
        default="write_local",
        help=f"Comma-separated. Allowed: {','.join(ALL_SCOPES)} (default: write_local)",
    )
    p.add_argument(
        "--budget",
        type=float,
        default=0.0,
        help="Monthly budget in USD (only meaningful for server_extract scope; default 0)",
    )
    p.add_argument("--notes", default=None, help="Optional free-form note")
    p.add_argument(
        "--registry",
        default=os.environ.get("CITARE_KEY_REGISTRY", str(_REPO / "data" / "api_keys.json")),
        help="Registry JSON path (default: data/api_keys.json or $CITARE_KEY_REGISTRY)",
    )
    args = p.parse_args()

    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    for s in scopes:
        if s not in ALL_SCOPES:
            print(f"Error: unknown scope '{s}'. Allowed: {','.join(ALL_SCOPES)}", file=sys.stderr)
            return 2

    registry = KeyRegistry(args.registry)
    ki = registry.issue(
        label=args.label,
        scopes=scopes,
        monthly_budget_usd=args.budget,
        notes=args.notes,
    )
    print()
    print("=" * 60)
    print(f"Issued: {ki.label}")
    print(f"Scopes: {','.join(ki.scopes)}")
    print(f"Budget: ${ki.monthly_budget_usd:.2f}/month")
    print(f"Created: {ki.created_at}")
    print()
    print("KEY (save now — cannot be recovered):")
    print(f"  {ki.key}")
    print()
    print("Connection example (claude.ai web):")
    print(f"  URL:  https://citare.dev/admin/sse")
    print(f"  Auth: Bearer {ki.key}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
