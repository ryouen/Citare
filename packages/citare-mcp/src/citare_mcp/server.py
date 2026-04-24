"""MCP server entry point for Citare.

Exposes three tools over stdio:
 - search_claims(query?, doi?, iv?, dv?, template_type?, limit=20)
 - cite_claim(claim_id)
 - get_claim_graph(claim_id, depth=1)

Run: citare-mcp --db /path/to/citare.db

Environment overrides: CITARE_DB sets the DB path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from citare_mcp.queries import cite_claim, get_claim_graph, search_claims


def _ensure_conn(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"Citare DB not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _make_server(db_path: Path) -> Server:
    server: Server = Server("citare")

    @server.list_tools()
    async def _list_tools() -> list[Tool]:
        return [
            Tool(
                name="search_claims",
                description=(
                    "Search claims in the Citare knowledge graph. At least one of "
                    "query, doi, iv, dv, or template_type must be provided. Returns "
                    "a list of claims with source_text, causal_strength, and verification_status."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Free-text search on source_text and l2_en"},
                        "doi": {"type": "string", "description": "Paper DOI"},
                        "iv": {"type": "string", "description": "Independent variable (substring match)"},
                        "dv": {"type": "string", "description": "Dependent variable (substring match)"},
                        "template_type": {
                            "type": "string",
                            "enum": ["DEFINITION", "RELATION", "EXISTENCE_CLAIM", "META_CLAIM"],
                        },
                        "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                },
            ),
            Tool(
                name="cite_claim",
                description=(
                    "Return a full citation bundle for one claim by ID. Includes the "
                    "paper's bibliographic info, source_text, integrity warnings from "
                    "related claims, and a safe_verbs hint based on the design basis. "
                    "Use this whenever an AI application is about to cite a claim."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {"claim_id": {"type": "string"}},
                    "required": ["claim_id"],
                },
            ),
            Tool(
                name="get_claim_graph",
                description=(
                    "Return the local neighbourhood of a claim with integrity "
                    "warnings. Use this to check if a claim has mediation, "
                    "moderation, or effect-disappears-under-control warnings "
                    "before citing."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "claim_id": {"type": "string"},
                        "depth": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1},
                    },
                    "required": ["claim_id"],
                },
            ),
        ]

    @server.call_tool()
    async def _call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        conn = _ensure_conn(db_path)
        try:
            if name == "search_claims":
                result = search_claims(conn, **arguments)
            elif name == "cite_claim":
                result = cite_claim(conn, arguments["claim_id"])
            elif name == "get_claim_graph":
                result = get_claim_graph(
                    conn,
                    arguments["claim_id"],
                    depth=arguments.get("depth", 1),
                )
            else:
                return [TextContent(type="text", text=json.dumps({"error": f"unknown tool: {name}"}))]
        finally:
            conn.close()
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]

    return server


async def _run(db_path: Path) -> None:
    server = _make_server(db_path)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    p = argparse.ArgumentParser(description="Citare MCP server (stdio)")
    p.add_argument("--db", default=os.environ.get("CITARE_DB", "citare.db"), help="Path to SQLite DB")
    args = p.parse_args()
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Citare DB not found at {db_path}. Run the ingest script first.")
    asyncio.run(_run(db_path))


if __name__ == "__main__":
    main()
