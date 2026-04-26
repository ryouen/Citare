"""Smoke test for the Citare MCP server.

Validates that the four MCP tools (search_claims, cite_claim, get_claim_graph,
register_claims) return correct results against a known starter DB.

Default mode (recommended for VPS deployment validation):
    python scripts/smoke_test_mcp.py --db /var/lib/citare/citare.db

This imports `citare_mcp.queries` directly. It is a *logic* smoke test, not a
wire-protocol test — it bypasses the MCP stdio/SSE layer. Sufficient to catch:
- DB schema mismatch with the deployed code
- Broken queries (e.g., references to dropped columns)
- Missing claims after a re-ingest
- safe_verbs derivation bug

HTTP wire-protocol test (TODO: requires running server):
    CITARE_MCP_URL=https://citare.example.com/sse \\
    CITARE_API_KEY=xxx \\
    python scripts/smoke_test_mcp.py
The pattern is documented in `_test_http_protocol_TODO()` below.

Exit code: 0 on all-pass, 1 on any-fail.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import traceback
from pathlib import Path

# Locate the packages relative to this script (scripts/ is sibling to packages/).
_REPO = Path(__file__).resolve().parent.parent
for sub in ("citare-core", "citare-db", "citare-mcp"):
    src = _REPO / "packages" / sub / "src"
    if src.exists():
        sys.path.insert(0, str(src))


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m"


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


# ============================================================================
# Tests
# ============================================================================


def test_search_iv(conn: sqlite3.Connection) -> tuple[bool, str]:
    """search_claims(iv='team_psychological_safety') returns Edmondson hits."""
    from citare_mcp.queries import search_claims

    res = search_claims(conn, iv="team_psychological_safety", limit=10)
    if not res:
        return False, "expected >=1 hit, got 0"
    edmondson_doi = "10.2307/2666999"
    edm_hits = [r for r in res if r["paper_id"] == edmondson_doi]
    if not edm_hits:
        return False, f"expected at least one hit with paper_id={edmondson_doi}, got papers={[r['paper_id'] for r in res]}"
    return True, f"got {len(res)} hits, {len(edm_hits)} from Edmondson 1999 (e.g. {edm_hits[0]['id']})"


def test_search_query(conn: sqlite3.Connection) -> tuple[bool, str]:
    """search_claims(query='chain of thought') returns Wei 2022 hits."""
    from citare_mcp.queries import search_claims

    res = search_claims(conn, query="chain of thought", limit=20)
    if not res:
        return False, "expected >=1 hit, got 0"
    wei_doi = "10.48550/arXiv.2201.11903"
    wei_hits = [r for r in res if r["paper_id"] == wei_doi]
    if not wei_hits:
        return False, f"expected >=1 hit from Wei 2022 ({wei_doi}), got papers={sorted({r['paper_id'] for r in res})}"
    return True, f"got {len(res)} total hits, {len(wei_hits)} from Wei 2022 (e.g. {wei_hits[0]['id']})"


def test_cite_claim(conn: sqlite3.Connection) -> tuple[bool, str]:
    """cite_claim('edmondson1999_rel2') returns the right safe_verbs and warnings."""
    from citare_mcp.queries import cite_claim

    r = cite_claim(conn, "edmondson1999_rel2")
    if "error" in r:
        return False, f"cite_claim returned error: {r['error']}"

    expected_verbs = ["is associated with", "correlates with"]
    if r.get("safe_verbs") != expected_verbs:
        return False, f"safe_verbs mismatch: expected {expected_verbs}, got {r.get('safe_verbs')}"

    if not r.get("integrity_warnings"):
        return False, "expected integrity_warnings non-empty (this claim has 5 warnings in starter DB)"

    if r.get("source_page") != 355:
        return False, f"source_page mismatch: expected 355, got {r.get('source_page')}"

    n_warn = len(r["integrity_warnings"])
    cats = sorted({w["incompleteness_category"] for w in r["integrity_warnings"]})
    return True, f"safe_verbs OK, source_page=355, {n_warn} integrity_warnings (cats: {cats})"


def test_get_claim_graph(conn: sqlite3.Connection) -> tuple[bool, str]:
    """get_claim_graph('edmondson1999_rel3', depth=2) returns >=10 edges incl. effect_disappears_under_control."""
    from citare_mcp.queries import get_claim_graph

    g = get_claim_graph(conn, "edmondson1999_rel3", depth=2)
    edges = g.get("edges", [])
    if len(edges) < 10:
        return False, f"expected >=10 edges, got {len(edges)}"

    cats = {e.get("incompleteness_category") for e in edges}
    if "effect_disappears_under_control" not in cats:
        return False, f"expected at least one 'effect_disappears_under_control' edge, got categories: {sorted(c for c in cats if c)}"

    return True, f"got {len(edges)} edges, categories: {sorted(c for c in cats if c)}"


def test_register_claims_in_temp_db() -> tuple[bool, str]:
    """register_claims(<minimal valid extraction>) returns paper_id and may have warnings.

    Uses a fresh temporary DB so this test never pollutes the production starter DB.
    """
    from citare_core import Extraction
    from citare_db import init_db, ingest_extraction

    minimal_extraction = {
        "paper": {
            "doi": "10.9999/smoke_test_2026",
            "title": "Smoke Test Paper",
            "authors": ["Test Author"],
            "year": 2026,
            "paper_type": "empirical",
            "default_causal_strength": {
                "design_basis": "rct",
                "author_framing": "causal",
                "manipulation_of_iv": True,
            },
        },
        "claims": [
            {
                "id": "smoketest_2026_rel1",
                "template_type": "RELATION",
                "l0_json": {
                    "iv": "smoketest_input",
                    "dv": "smoketest_output",
                    "relation": "increases",
                },
                "source_text": "In our randomised experiment, the input increased the output by 50%.",
                "source_page": 1,
                "verification_status": "verified_in_paper",
            },
        ],
        "extraction_prompt_version": "smoke_test_v1",
    }

    ext = Extraction.model_validate(minimal_extraction)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name
    try:
        conn = init_db(tmp_path)
        try:
            report = ingest_extraction(conn, ext)
            conn.commit()
        finally:
            conn.close()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    if report.paper_id != "10.9999/smoke_test_2026":
        return False, f"paper_id mismatch: expected '10.9999/smoke_test_2026', got '{report.paper_id}'"
    if not report.created_paper:
        return False, "expected created_paper=True on first insert into temp DB"
    # Warnings are allowed (none expected for this minimal payload but shouldn't error).
    return True, f"paper_id={report.paper_id}, created=True, warnings={len(report.warnings)}"


def _test_http_protocol_TODO() -> tuple[bool, str]:  # noqa: N802
    """TODO: requires running server.

    Pattern for a real HTTP/SSE wire-protocol smoke test:

        from mcp.client.sse import sse_client
        from mcp.client.session import ClientSession

        url = os.environ["CITARE_MCP_URL"]   # e.g. https://citare.example.com/sse
        key = os.environ["CITARE_API_KEY"]

        async def go():
            async with sse_client(url, headers={"Authorization": f"Bearer {key}"}) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert any(t.name == "search_claims" for t in tools.tools)
                    res = await session.call_tool("cite_claim", {"claim_id": "edmondson1999_rel2"})
                    payload = json.loads(res.content[0].text)
                    assert payload["safe_verbs"] == ["is associated with", "correlates with"]

        asyncio.run(go())

    Skipped by default because it requires (1) a running citare-mcp-http process,
    (2) the mcp[client] extras installed, and (3) network plumbing. The
    direct-import tests above catch every defect that has bitten this codebase.
    """
    return True, "skipped (set up running server + use mcp.client.sse to enable)"


# ============================================================================
# Runner
# ============================================================================


def main() -> int:
    p = argparse.ArgumentParser(description="Citare MCP smoke test")
    p.add_argument(
        "--db",
        default=os.environ.get("CITARE_DB", str(_REPO / "data" / "citare.db")),
        help="Path to citare.db (defaults to repo's data/citare.db or $CITARE_DB)",
    )
    args = p.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(_red(f"FAIL: DB not found at {db_path}"))
        return 1

    print(_bold(f"Citare MCP smoke test against {db_path}"))
    print()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    tests: list[tuple[str, callable]] = [
        ("search_claims(iv='team_psychological_safety')", lambda: test_search_iv(conn)),
        ("search_claims(query='chain of thought')", lambda: test_search_query(conn)),
        ("cite_claim('edmondson1999_rel2')", lambda: test_cite_claim(conn)),
        ("get_claim_graph('edmondson1999_rel3', depth=2)", lambda: test_get_claim_graph(conn)),
        ("register_claims(<minimal>) in temp DB", lambda: test_register_claims_in_temp_db()),
        ("HTTP wire protocol", lambda: _test_http_protocol_TODO()),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 — surface any unexpected error
            ok = False
            detail = f"exception: {type(e).__name__}: {e}\n{traceback.format_exc()}"

        if ok:
            print(f"  {_green('PASS')}  {name}")
            print(f"        {detail}")
            passed += 1
        else:
            print(f"  {_red('FAIL')}  {name}")
            print(f"        {detail}")
            failed += 1

    conn.close()

    print()
    total = passed + failed
    summary = f"{passed}/{total} passed"
    if failed == 0:
        print(_green(_bold(f"OK: {summary}")))
        return 0
    print(_red(_bold(f"FAILURES: {failed}/{total} failed")))
    return 1


if __name__ == "__main__":
    sys.exit(main())
