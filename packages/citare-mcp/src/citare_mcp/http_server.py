"""HTTP/SSE transport for Citare MCP.

Same Server instance and same tool implementations as stdio (server.py).

Two authentication modes:

1. **No auth** — `--api-key` unset and `--key-registry` unset. Any client
   can connect. Use this for the public read endpoint where every tool is
   read-only (set `--read-only` so `register_claims` is hidden).

2. **Per-key registry** — `--key-registry /path/to/keys.json` set. Every
   request requires `Authorization: Bearer <key>` and the key must exist
   (and not be revoked) in the registry. Use this for the admin endpoint.

A simpler single-key mode (`--api-key SOMESECRET` without a registry) is
also supported for development and small deployments.

Run::

    # Public read endpoint
    citare-mcp-http --db /var/lib/citare/citare.db --port 8765 --read-only

    # Admin endpoint with multi-user keys
    citare-mcp-http --db /var/lib/citare/citare.db --port 8766 \\
        --key-registry /var/lib/citare/api_keys.json

Environment overrides: ``CITARE_DB``, ``CITARE_API_KEY``,
``CITARE_KEY_REGISTRY``, ``CITARE_HOST``, ``CITARE_PORT``,
``CITARE_READ_ONLY``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from citare_mcp.auth import KeyRegistry
from citare_mcp.auth_context import current_key
from citare_mcp.server import _make_server  # reuse stdio server's tool definitions


def _bearer_from_scope(scope: Scope) -> str:
    """Extract Bearer token from raw ASGI scope; '' if absent or malformed."""
    headers = dict(scope.get("headers") or [])
    auth = headers.get(b"authorization", b"").decode("latin-1")
    return auth[7:] if auth.startswith("Bearer ") else ""


class _SingleKeyAuthMiddleware:
    """Single-shared-key Bearer auth. Used for dev / small deployments where a
    full per-user key registry is overkill."""

    def __init__(self, app: ASGIApp, api_key: str, health_path: str = "/health") -> None:
        self.app = app
        self._api_key = api_key
        self._health_path = health_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == self._health_path:
            await self.app(scope, receive, send)
            return
        if _bearer_from_scope(scope) != self._api_key:
            await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
            return
        await self.app(scope, receive, send)


class _RegistryAuthMiddleware:
    """Per-key Bearer auth backed by a KeyRegistry JSON file.

    Implemented as raw ASGI middleware (not ``BaseHTTPMiddleware``) so SSE
    streaming responses pass through without being buffered — ``BaseHTTPMiddleware``
    breaks streaming for the MCP SSE transport.

    Validates `Authorization: Bearer <key>` on every path except /health.
    Per-tool scope checks happen inside the MCP tool handlers (server.py),
    not here — the middleware only proves the caller has a valid key.
    """

    def __init__(self, app: ASGIApp, registry: KeyRegistry, health_path: str = "/health") -> None:
        self.app = app
        self._registry = registry
        self._health_path = health_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == self._health_path:
            await self.app(scope, receive, send)
            return
        bearer = _bearer_from_scope(scope)
        if not bearer:
            await JSONResponse(
                {"error": "unauthorized", "detail": "Authorization: Bearer <key> required"},
                status_code=401,
            )(scope, receive, send)
            return
        ki = self._registry.lookup(bearer)
        if ki is None:
            await JSONResponse(
                {"error": "unauthorized", "detail": "key invalid or revoked"},
                status_code=401,
            )(scope, receive, send)
            return
        # Make the authenticated key visible to tool handlers via contextvar.
        # Tool handlers downstream can read citare_mcp.auth_context.current_key
        # to gate per-scope tools (e.g. extract_and_register requires
        # server_extract scope) and to charge per-key budget.
        token = current_key.set(ki)
        try:
            await self.app(scope, receive, send)
        finally:
            current_key.reset(token)


def build_app(
    db_path: Path,
    api_key: str | None = None,
    key_registry_path: Path | None = None,
    read_only: bool = False,
    mount_prefix: str = "",
) -> Starlette:
    """Build the Starlette ASGI app exposing Citare MCP over SSE.

    Auth precedence (mutually exclusive):
        key_registry_path > api_key > no auth

    `mount_prefix` controls the URL surface. With ``""`` the app exposes
    ``/sse``, ``/messages/``, ``/health`` (the public read default). With
    ``"/admin"`` it exposes ``/admin/sse``, ``/admin/messages/``,
    ``/admin/health`` — useful when nginx terminates both endpoints under
    a single hostname (citare.dev/sse vs citare.dev/admin/sse).
    """
    server = _make_server(db_path, read_only=read_only)
    prefix = mount_prefix.rstrip("/")
    messages_path = f"{prefix}/messages/"
    sse = SseServerTransport(messages_path)

    registry = KeyRegistry(key_registry_path) if key_registry_path else None
    auth_mode = "registry" if registry else ("single_key" if api_key else "none")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(
            request.scope, request.receive, request._send  # noqa: SLF001 — required by SDK
        ) as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )
        # SSE transport already wrote the response; this is just to satisfy
        # Starlette's Route contract (it expects a Response). Status 200 is
        # never actually sent — the SSE stream has already closed the channel.
        return Response(status_code=200)

    async def health(request: Request) -> JSONResponse:
        body: dict[str, object] = {
            "status": "ok",
            "db": str(db_path),
            "auth_mode": auth_mode,
            "read_only": read_only,
        }
        if registry is not None:
            body["active_keys"] = len(registry.list_active())
        return JSONResponse(body)

    async def stats(request: Request) -> JSONResponse:
        """Public counters for the landing page. Cheap; no auth.

        Reads in 5 small COUNT queries; safe to call frequently. CORS-open
        because the landing page fetches it from the browser.
        """
        import sqlite3 as _sql
        conn = _sql.connect(str(db_path))
        try:
            cur = conn.execute("SELECT COUNT(*) FROM papers")
            papers = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(*) FROM claims")
            claims = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(*) FROM claim_relations")
            relations = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT COUNT(*) FROM claim_relations WHERE incompleteness_category != 'none'"
            )
            warnings = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT COUNT(*) FROM papers "
                "WHERE created_at >= datetime('now', '-7 days')"
            )
            recent_papers = cur.fetchone()[0]
            cur = conn.execute(
                "SELECT COUNT(*) FROM claims "
                "WHERE created_at >= datetime('now', '-7 days')"
            )
            recent_claims = cur.fetchone()[0]
        finally:
            conn.close()
        return JSONResponse(
            {
                "papers": papers,
                "claims": claims,
                "relations": relations,
                "integrity_warnings": warnings,
                "recent_7d": {"papers": recent_papers, "claims": recent_claims},
            },
            headers={"Cache-Control": "public, max-age=60", "Access-Control-Allow-Origin": "*"},
        )

    async def api_search(request: Request) -> JSONResponse:
        """Tiny REST shim for the landing-page demo box.

        Mirrors search_claims(query=..., limit<=5) and enriches each hit
        with a lightweight `traffic_light` colour (green/yellow/red).
        """
        import sqlite3 as _sql
        from citare_mcp.queries import search_claims as _search_claims
        from citare_mcp.traffic_light import compute_lightweight_color as _tl
        q = (request.query_params.get("q") or "").strip()
        if not q:
            return JSONResponse(
                {"error": "missing query parameter 'q'"},
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        try:
            limit = max(1, min(5, int(request.query_params.get("limit", "3"))))
        except ValueError:
            limit = 3
        conn = _sql.connect(str(db_path))
        conn.row_factory = _sql.Row
        try:
            hits = _search_claims(conn, query=q, limit=limit)
            # Bulk-fetch the worst incompleteness_category per hit's
            # incident edges so traffic_light can be computed without
            # one query per claim per category.
            ids = [h["id"] for h in hits]
            edge_cats: dict[str, set[str]] = {i: set() for i in ids}
            if ids:
                marks = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"SELECT source_id, target_id, incompleteness_category "
                    f"FROM claim_relations "
                    f"WHERE source_id IN ({marks}) OR target_id IN ({marks})",
                    ids + ids,
                ).fetchall()
                for r in rows:
                    cat = r["incompleteness_category"] or "none"
                    if r["source_id"] in edge_cats:
                        edge_cats[r["source_id"]].add(cat)
                    if r["target_id"] in edge_cats:
                        edge_cats[r["target_id"]].add(cat)
        finally:
            conn.close()

        from citare_mcp.traffic_light import _RED_CATS, _YELLOW_CATS
        out = []
        for h in hits:
            cs = h.get("causal_strength") or {}
            cats = edge_cats.get(h["id"], set())
            color = _tl(
                claim_status=h.get("claim_status"),
                verification_status=h.get("verification_status"),
                design_basis=cs.get("design_basis"),
                author_framing=cs.get("author_framing_observed_only") or cs.get("author_framing"),
                template_type=h.get("template_type"),
                has_red_edge=bool(cats & _RED_CATS),
                has_yellow_edge=bool(cats & _YELLOW_CATS),
            )
            out.append({
                "id": h.get("id"),
                "paper_id": h.get("paper_id"),
                "template_type": h.get("template_type"),
                "l0_json": h.get("l0_json"),
                "source_text_preview": (h.get("source_text") or "")[:240],
                "source_page": h.get("source_page"),
                "design_basis": cs.get("design_basis"),
                "traffic_light": color,
            })
        return JSONResponse(
            {"query": q, "count": len(out), "results": out},
            headers={"Cache-Control": "public, max-age=10", "Access-Control-Allow-Origin": "*"},
        )

    async def api_graph(request: Request) -> JSONResponse:
        """Graph payload for the landing-page SVG viewer.

        Two modes:
          claim_id=...&depth=1|2 — local neighbourhood of a single claim
          paper_id=...           — every claim from one paper + all the
                                    relations linking them (for visualising
                                    a paper's full argument structure;
                                    sparse-by-design papers like Shannon
                                    1948 only become interesting at this
                                    scope).

        Returns nodes + edges shaped for a node-link renderer.
        """
        import sqlite3 as _sql
        from citare_mcp.queries import get_claim_graph as _get_claim_graph
        cid = (request.query_params.get("claim_id") or "").strip()
        pid = (request.query_params.get("paper_id") or "").strip()
        if not cid and not pid:
            return JSONResponse(
                {"error": "missing query parameter: 'claim_id' or 'paper_id'"},
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        try:
            depth = max(1, min(2, int(request.query_params.get("depth", "2"))))
        except ValueError:
            depth = 2

        conn = _sql.connect(str(db_path))
        conn.row_factory = _sql.Row
        try:
            if pid:
                # Paper mode: every claim of this paper + every relation
                # whose source AND target are both in the paper.
                claim_rows = conn.execute(
                    "SELECT id, template_type, l0_json, paper_id, causal_strength "
                    "FROM claims WHERE paper_id = ?",
                    (pid,),
                ).fetchall()
                claim_ids = [r["id"] for r in claim_rows]
                if not claim_ids:
                    g = {"nodes": [], "edges": []}
                else:
                    marks = ",".join("?" for _ in claim_ids)
                    edges = conn.execute(
                        f"SELECT source_id, target_id, relation_type, incompleteness_category, context "
                        f"FROM claim_relations "
                        f"WHERE source_id IN ({marks}) AND target_id IN ({marks})",
                        claim_ids + claim_ids,
                    ).fetchall()
                    g = {
                        "nodes": [dict(r) for r in claim_rows],
                        "edges": [dict(e) for e in edges],
                    }
                center = pid
            else:
                g = _get_claim_graph(conn, cid, depth=depth)
                center = cid
        except Exception as e:
            conn.close()
            return JSONResponse(
                {"error": "graph_failed", "detail": str(e)},
                status_code=500,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        conn.close()

        # Trim node payloads to what the renderer actually shows. snake_case
        # iv/dv get normalised to space-separated for label readability.
        def _label(node: dict) -> str:
            l0 = node.get("l0_json") or {}
            if isinstance(l0, str):
                import json as _json
                try:
                    l0 = _json.loads(l0)
                except _json.JSONDecodeError:
                    l0 = {}
            iv = (l0.get("iv") or "").replace("_", " ")
            dv = (l0.get("dv") or "").replace("_", " ")
            if iv and dv:
                return f"{iv} → {dv}"
            return (l0.get("concept") or l0.get("phenomenon")
                    or node.get("template_type") or "?").replace("_", " ")

        def _design_basis(node: dict) -> str | None:
            cs = node.get("causal_strength")
            if isinstance(cs, str):
                import json as _json
                try:
                    cs = _json.loads(cs)
                except _json.JSONDecodeError:
                    return None
            if isinstance(cs, dict):
                return cs.get("design_basis")
            return None

        # Pre-compute incident edge categories per node so each node gets a
        # traffic_light. Walks g.edges twice — cheap.
        from citare_mcp.traffic_light import (
            compute_lightweight_color as _tl, _RED_CATS, _YELLOW_CATS,
        )
        node_cats: dict[str, set[str]] = {n["id"]: set() for n in g.get("nodes", [])}
        for e in g.get("edges", []):
            cat = e.get("incompleteness_category") or "none"
            for k in (e.get("source_id"), e.get("target_id")):
                if k in node_cats:
                    node_cats[k].add(cat)

        # We don't have claim_status/verification on the get_claim_graph
        # nodes (it returns minimal fields), so traffic_light from the
        # graph endpoint is design-basis + edge-category only. Search/cite
        # have access to richer signals.
        def _node_color(n: dict) -> str:
            cs_raw = n.get("causal_strength")
            cs = cs_raw
            if isinstance(cs_raw, str):
                try:
                    import json as _json
                    cs = _json.loads(cs_raw)
                except Exception:
                    cs = {}
            cs = cs or {}
            cats = node_cats.get(n["id"], set())
            return _tl(
                claim_status=n.get("claim_status"),
                verification_status=n.get("verification_status"),
                design_basis=cs.get("design_basis"),
                author_framing=cs.get("author_framing_observed_only") or cs.get("author_framing"),
                template_type=n.get("template_type"),
                has_red_edge=bool(cats & _RED_CATS),
                has_yellow_edge=bool(cats & _YELLOW_CATS),
            )

        nodes = [
            {
                "id": n["id"],
                "label": _label(n),
                "template_type": n.get("template_type"),
                "design_basis": _design_basis(n),
                "traffic_light": _node_color(n),
                "is_center": (cid != "" and n["id"] == cid),
            }
            for n in g.get("nodes", [])
        ]
        edges = [
            {
                "source": e.get("source_id"),
                "target": e.get("target_id"),
                "relation": e.get("relation_type"),
                "category": e.get("incompleteness_category") or "none",
            }
            for e in g.get("edges", [])
        ]
        return JSONResponse(
            {
                "center": center,
                "mode": "paper" if pid else "claim",
                "depth": depth if cid else None,
                "nodes": nodes,
                "edges": edges,
            },
            headers={"Cache-Control": "public, max-age=30", "Access-Control-Allow-Origin": "*"},
        )

    async def api_cite(request: Request) -> JSONResponse:
        """Tiny REST shim around cite_claim, used by the landing page when
        the user clicks a traffic-light badge to expand reasons. No auth."""
        import sqlite3 as _sql
        from citare_mcp.queries import cite_claim as _cite_claim
        cid = (request.query_params.get("claim_id") or "").strip()
        if not cid:
            return JSONResponse(
                {"error": "missing claim_id"}, status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        conn = _sql.connect(str(db_path))
        conn.row_factory = _sql.Row
        try:
            r = _cite_claim(conn, cid, style="apa7")
        finally:
            conn.close()
        return JSONResponse(
            r,
            headers={"Cache-Control": "public, max-age=30", "Access-Control-Allow-Origin": "*"},
        )

    async def api_register(request: Request) -> JSONResponse:
        """REST escape hatch for register_claims when MCP SDK SSE bites.

        The MCP /sse path is the primary surface; this exists because the
        Python MCP SDK's SSE client occasionally enters a "session decay"
        state where every RPC returns -32602 and only a process restart
        clears it. When that happens, callers can POST the same JSON body
        here and bypass the broken SDK entirely.

        Same backing logic as the MCP register_claims tool — including the
        Pydantic validation, the 25 KB / claim-count / source_text quality
        gate, the WARNING-not-REJECT semantics, and the rich response with
        next_steps. No auth (matches the MCP path).
        """
        import json as _json
        import sqlite3 as _sql
        from citare_core import Extraction
        from citare_db import ingest_extraction
        try:
            raw_body = await request.body()
        except Exception as e:
            return JSONResponse(
                {"error": "body_read_failed", "detail": str(e)},
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        body_bytes = raw_body or b""
        body_str = body_bytes.decode("utf-8", errors="replace")
        if not body_str.strip():
            return JSONResponse(
                {"error": "empty_body",
                 "detail": "POST the v0.13g extraction JSON as the request body."},
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )
        try:
            payload = _json.loads(body_str)
        except _json.JSONDecodeError as e:
            return JSONResponse(
                {"error": "invalid_json", "detail": str(e)},
                status_code=400,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Pydantic validate
        try:
            ext = Extraction.model_validate(payload)
        except Exception as e:
            return JSONResponse(
                {"error": "schema_validation_failed", "detail": str(e)[:600]},
                status_code=422,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Quality gate — single source of truth, shared with /sse and /mcp paths.
        from citare_mcp.quality_gate import evaluate_quality
        kb = len(body_str) / 1024
        problems, warnings = evaluate_quality(ext, kb)
        if problems:
            return JSONResponse(
                {"error": "extraction_quality_gate", "problems": problems,
                 "warnings": warnings,
                 "see": "Re-run extraction with v0.13g + omit `thinking` and `effort` parameters."},
                status_code=422,
                headers={"Access-Control-Allow-Origin": "*"},
            )

        # Ingest
        conn = _sql.connect(str(db_path))
        conn.row_factory = _sql.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            pre = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE paper_id = ?",
                (ext.paper.doi or "",),
            ).fetchone()[0] if ext.paper.doi else 0
            report = ingest_extraction(conn, ext)
            post = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE paper_id = ?", (report.paper_id,)
            ).fetchone()[0]
        finally:
            conn.close()

        claims_added = max(0, post - pre)
        next_steps = []
        if report.created_paper:
            next_steps.append(f"Verify with: GET /api/search?q={report.paper_id}")
        else:
            next_steps.append(f"Existing paper updated; {claims_added} new claims.")
        for w in warnings:
            next_steps.append(f"⚠ {w}")

        # Audit log so we can see this hit (parallel to [tool] for MCP path)
        print(f"[rest] /api/register paper_id={report.paper_id!r} "
              f"created={report.created_paper} added={claims_added} "
              f"warnings={len(report.warnings)}", flush=True)

        return JSONResponse(
            {
                "via": "rest",
                "paper_id": report.paper_id,
                "created_paper": report.created_paper,
                "claims_added": claims_added,
                "claims_total_for_paper": post,
                "warnings": report.warnings,
                "potential_duplicate_claims": report.potential_duplicate_claims,
                "next_steps": next_steps,
            },
            headers={"Access-Control-Allow-Origin": "*"},
        )

    routes = [
        Route(f"{prefix}/health", endpoint=health),
        Route(f"{prefix}/stats", endpoint=stats),
        Route(f"{prefix}/api/search", endpoint=api_search),
        Route(f"{prefix}/api/graph", endpoint=api_graph),
        Route(f"{prefix}/api/cite", endpoint=api_cite),
        Route(f"{prefix}/api/register", endpoint=api_register, methods=["POST"]),
        Route(f"{prefix}/sse", endpoint=handle_sse),
        Mount(messages_path, app=sse.handle_post_message),
    ]
    health_path = f"{prefix}/health"
    middleware = []
    if registry is not None:
        middleware.append(Middleware(_RegistryAuthMiddleware, registry=registry, health_path=health_path))
    elif api_key:
        middleware.append(Middleware(_SingleKeyAuthMiddleware, api_key=api_key, health_path=health_path))
    return Starlette(routes=routes, middleware=middleware)


def main() -> None:
    p = argparse.ArgumentParser(description="Citare MCP server (HTTP/SSE)")
    p.add_argument("--db", default=os.environ.get("CITARE_DB", "data/citare.db"))
    p.add_argument("--host", default=os.environ.get("CITARE_HOST", "0.0.0.0"))
    p.add_argument(
        "--port", type=int, default=int(os.environ.get("CITARE_PORT", "8765"))
    )
    p.add_argument(
        "--api-key",
        default=os.environ.get("CITARE_API_KEY"),
        help="Single shared Bearer key. For multi-user deployments use --key-registry instead.",
    )
    p.add_argument(
        "--key-registry",
        default=os.environ.get("CITARE_KEY_REGISTRY"),
        help="Path to a JSON file holding per-user issued keys (recommended for write endpoint).",
    )
    p.add_argument(
        "--read-only",
        action="store_true",
        default=os.environ.get("CITARE_READ_ONLY", "").lower() in ("1", "true", "yes"),
        help="Disable the register_claims write tool (recommended for public VPS).",
    )
    p.add_argument(
        "--mount-prefix",
        default=os.environ.get("CITARE_MOUNT_PREFIX", ""),
        help="URL prefix for routes (default: ''). Set to '/admin' for the admin endpoint.",
    )
    args = p.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    registry_path: Path | None = None
    if args.key_registry:
        registry_path = Path(args.key_registry).resolve()
        if not registry_path.exists():
            print(
                f"NOTE: key registry {registry_path} does not exist yet — "
                "no keys will be accepted until it is created.",
                file=sys.stderr,
            )
        if args.api_key:
            print(
                "WARNING: both --api-key and --key-registry set; --key-registry takes precedence.",
                file=sys.stderr,
            )

    if not args.api_key and not registry_path:
        print(
            "WARNING: no auth configured. Server is UNAUTHENTICATED.",
            file=sys.stderr,
        )
    if args.read_only:
        print("read-only mode: register_claims tool is disabled", file=sys.stderr)

    app = build_app(
        db_path,
        api_key=args.api_key,
        key_registry_path=registry_path,
        read_only=args.read_only,
        mount_prefix=args.mount_prefix,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
