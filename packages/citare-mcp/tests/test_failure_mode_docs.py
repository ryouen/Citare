"""Parity test: transport / registration documentation is consistent across surfaces.

Run from the repo root with no dependencies:

    python packages/citare-mcp/tests/test_failure_mode_docs.py

Why a string-grep test rather than an import test: this is intentionally a
docs-and-tool-description sanity check. We want to fail loudly if someone
edits any one of the surfaces (INSTRUCTIONS, register_claims tool description,
REGISTRATION_PATHS.md, fastmcp_server, log monitor) without keeping the others
in sync.

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
            "TRANSPORT",
            "/mcp",
            "Streamable HTTP",
            "/api/register",
            "json_data",
        ],
    ),
    (
        "register_claims tool description (legacy server.py)",
        REPO_ROOT / "packages/citare-mcp/src/citare_mcp/server.py",
        [
            'name="register_claims"',
            "/api/register",
        ],
    ),
    (
        "fastmcp_server module exists with all 6 tools",
        REPO_ROOT / "packages/citare-mcp/src/citare_mcp/fastmcp_server.py",
        [
            "from fastmcp import FastMCP",
            "stateless_http=True",
            "@mcp.tool",
            "search_claims",
            "cite_claim",
            "get_claim_graph",
            "get_extraction_prompt",
            "get_pdf_acquisition_guide",
            "register_claims",
        ],
    ),
    (
        "REGISTRATION_PATHS.md",
        REPO_ROOT / "docs/REGISTRATION_PATHS.md",
        [
            "/mcp` (Streamable HTTP)",
            "/sse` (DEPRECATED",
            "/api/register",
            "FastMCP",
            "stateless_http=True",
            "before initialization was complete",
        ],
    ),
    (
        "docker-compose has the fastmcp service",
        REPO_ROOT / "docker-compose.yml",
        [
            "citare-mcp-fastmcp",
            "citare-mcp-fastmcp-http",
            "8767",
        ],
    ),
    (
        "pyproject declares fastmcp dep + entry point",
        REPO_ROOT / "packages/citare-mcp/pyproject.toml",
        [
            "fastmcp>=2.10",
            "citare-mcp-fastmcp-http",
        ],
    ),
]


def main() -> int:
    failures: list[str] = []
    for name, path, needles in CHECKS:
        if not path.exists():
            failures.append(f"  X {name}: file not found at {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle not in text:
                failures.append(f"  X {name} ({path.name}): missing substring {needle!r}")

    if failures:
        print("Transport / docs parity test FAILED:")
        for f in failures:
            print(f)
        print()
        print("If you intentionally renamed or moved something, update this test")
        print("and docs/REGISTRATION_PATHS.md to match.")
        return 1

    total = sum(len(c[2]) for c in CHECKS)
    print(f"Transport / docs parity: OK ({total} substring checks across {len(CHECKS)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
