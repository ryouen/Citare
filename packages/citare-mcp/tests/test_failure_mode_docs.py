"""Parity test: FAILURE MODES guidance is present in all three places.

Run from the repo root with no dependencies:

    python packages/citare-mcp/tests/test_failure_mode_docs.py

Why a string-grep test rather than an import test: this is intentionally a
docs-and-tool-description sanity check. We want to fail loudly if someone
edits any one of the three surfaces (INSTRUCTIONS, register_claims tool
description, REGISTRATION_PATHS.md) without keeping the others in sync.

Exits 0 on success, 1 on any check failure with a human-readable diagnosis.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

CHECKS: list[tuple[str, Path, list[str]]] = [
    (
        "INSTRUCTIONS",
        REPO_ROOT / "packages/citare-mcp/src/citare_mcp/instructions.py",
        [
            "FAILURE MODES",
            "/api/register",
            "json_data",
            "before initialization was complete",
        ],
    ),
    (
        "register_claims tool description",
        REPO_ROOT / "packages/citare-mcp/src/citare_mcp/server.py",
        [
            'name="register_claims"',
            "/api/register",
            "-32602",
        ],
    ),
    (
        "REGISTRATION_PATHS.md",
        REPO_ROOT / "docs/REGISTRATION_PATHS.md",
        [
            "MCP `register_claims`",
            "REST `/api/register`",
            "before initialization was complete",
            "scripts/check_mcp_init_race.sh",
        ],
    ),
    (
        "log monitor script",
        REPO_ROOT / "scripts/check_mcp_init_race.sh",
        [
            "Failed to validate request: Received request before initialization was complete",
            "REGISTRATION_PATHS.md",
        ],
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, path, needles in CHECKS:
        if not path.exists():
            failures.append(f"  ✗ {name}: file not found at {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                failures.append(f"  ✗ {name} ({path.name}): missing substring {needle!r}")

    if failures:
        print("FAILURE MODES parity test FAILED:")
        for f in failures:
            print(f)
        print()
        print("If you intentionally renamed something, update both this test")
        print("and docs/REGISTRATION_PATHS.md to match.")
        return 1

    print(f"FAILURE MODES parity: OK ({sum(len(c[2]) for c in CHECKS)} substring checks across {len(CHECKS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
