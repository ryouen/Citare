# Registration paths — `/mcp` (Streamable HTTP), `/sse` (deprecated), `/api/register` (REST)

Citare exposes three paths for writing extracted claims to the database. All
three hit the same code (`citare_db.ingest_extraction`), the same Pydantic
gate, the same WARNING-not-REJECT semantics, and produce the same response
shape. They differ only in transport.

This document is the canonical transport reference. The MCP `INSTRUCTIONS`
block, the `register_claims` tool description, and the public `/api/register`
documentation all link here.

---

## TL;DR — which one should I use?

| Use case | Recommended path |
|---|---|
| Interactive Claude Code | **MCP `/mcp`** (Streamable HTTP) |
| Batch dispatcher (5+ parallel × N papers) | **MCP `/mcp`** or **REST `/api/register`** — both reliable |
| Sub-agent or background worker | **MCP `/mcp`** or **REST `/api/register`** |
| Non-MCP client (curl, requests, fetch) | **REST `/api/register`** |
| Existing client wired to `/sse` | Keep working temporarily, plan to switch to `/mcp` |

Default for everything: **`/mcp`** for MCP-native clients, **`/api/register`**
for everything else. `/sse` is deprecated.

---

## Path A — MCP Streamable HTTP `/mcp` (PRIMARY)

```
client (MCP SDK or fastmcp client)
   └── POST https://citare.dev/mcp           — single endpoint, stateless
       └── server.call_tool("register_claims", {"json_data": "<envelope>"})
           └── citare_db.ingest_extraction(...)
```

**Connection:**

```bash
claude mcp add --transport http citare https://citare.dev/mcp
```

- Auth: none. Public endpoint, all 6 tools (read + register).
- Transport: FastMCP 2.x with `stateless_http=True`. Each request is
  self-contained — no session_id state on the server. Concurrent /
  reconnect / sub-agent scenarios are all safe.
- Payload shape: `{"json_data": "<the entire Extraction JSON, as a string>"}`.
  The wrapper is required by the MCP tool inputSchema.
- Verified by: server logs (`POST /mcp HTTP/1.1 200 OK`) and the response
  payload's `claims_added`, `paper_id`, `warnings`.

This is the path the previous production Citare used (FastMCP 2.10+).
It has no known race conditions under concurrent or reconnect load.

---

## Path B — MCP SSE `/sse` (DEPRECATED — kept for backwards compat)

```
client (MCP SDK)
   └── GET  https://citare.dev/sse           — long-poll event stream
       POST https://citare.dev/messages/...  — JSON-RPC requests
       └── server.call_tool(...)
           └── citare_db.ingest_extraction(...)
```

Why deprecated: the bare `mcp.server.sse` transport in SDK 1.27 has a known
race (upstream issues `python-sdk#1844`, `#2214`, `#423`) where the client's
`initialized` flag desyncs from the server's session table after a `/clear`,
an interrupted call, or a long-idle socket. Symptom: `-32602 Invalid request
parameters` on every subsequent call. Server logs:

```
WARNING:root: Failed to validate request: Received request before initialization was complete
```

We ran into this with the R89 dispatcher (5-parallel register burst). The
fix is structural: move to `/mcp` where there is no per-session state.

`/sse` will be removed once existing clients have migrated. New clients
should not use it.

---

## Path C — REST `/api/register` (transport-agnostic)

```
client (anything that can POST JSON)
   └── POST https://citare.dev/api/register
       └── http_server.api_register
           └── citare_db.ingest_extraction(...)   # same function as Paths A/B
```

- Auth: none.
- Payload shape: the **raw `Extraction` JSON envelope as the request body**.
  Do NOT wrap it in `{"json_data": "..."}` — that wrapper is only for the
  MCP tool form.
- Response shape: identical to MCP — `paper_id`, `created_paper`,
  `claims_added`, `claims_updated`, `warnings`, `next_steps`. HTTP 200 on
  success. HTTP 400 on validation failure with `{"error": "...", "detail": "..."}`.

### Minimal client (curl)

```bash
curl -sS -X POST https://citare.dev/api/register \
  -H "Content-Type: application/json" \
  --data-binary @your_extraction.json
```

### Minimal client (Python)

```python
import json, urllib.request

with open("your_extraction.json", "rb") as f:
    body = f.read()

req = urllib.request.Request(
    "https://citare.dev/api/register",
    data=body,
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=60) as r:
    print(json.loads(r.read()))
```

This path exists primarily for non-MCP clients and as a transport-independent
fallback. With `/mcp` working reliably it is no longer the recommended
default for MCP clients, but it remains a perfectly valid path.

---

## Verifying that a write actually landed

Independent of which path you used:

```
GET https://citare.dev/api/search?q=<doi-or-distinctive-title-fragment>
```

If the paper appears, the write succeeded. This is the recommended sanity
check after every registration — it costs nothing and catches any silent
failure between the response and the FTS index.

---

## History

- **2026-04-26**: First REST `/api/register` endpoint added as an escape
  hatch after `-32602` repeatedly bit a 3-paper register from a remote MCP
  client.
- **2026-04-28 (morning)**: SSE init-race documented in three places after
  a second recurrence (R89 dispatcher). Workaround: REST.
- **2026-04-28 (afternoon)**: Root cause confirmed as the deprecated SSE
  transport. Migrated to FastMCP + Streamable HTTP at `/mcp`. The previous
  production Citare always used this transport — the regression came from
  inheriting the CitareOpus47 prototype's bare-SDK + SSE setup. `/mcp` is
  now the primary path; `/sse` retained temporarily for backwards compat.

## References

- [MCP Specification — Transports (2025-03-26)](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Why MCP Deprecated SSE and Went with Streamable HTTP](https://blog.fka.dev/blog/2025-06-06-why-mcp-deprecated-sse-and-go-with-streamable-http/)
- [python-sdk#1844 — SSE init-race with Claude Code](https://github.com/modelcontextprotocol/python-sdk/issues/1844)
