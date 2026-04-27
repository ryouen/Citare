# Registration paths — MCP `register_claims` vs REST `/api/register`

Citare exposes two paths for writing extracted claims to the database. Both
hit the same code, the same Pydantic gate, the same WARNING-not-REJECT
semantics, and produce the same response shape. They differ only in how the
request reaches the server and in their tolerance for client-side
infrastructure problems.

This document is the canonical reference. The MCP `INSTRUCTIONS` block, the
`register_claims` tool description, and the public `/api/register`
documentation all link here.

---

## TL;DR — which one should I use?

| Use case | Recommended path |
|---|---|
| Interactive Claude Code, occasional registration | MCP `register_claims` |
| Batch dispatcher (R89-style: 5+ parallel × N papers) | **REST `/api/register`** |
| Anything called from a sub-agent or background worker | **REST `/api/register`** |
| Long-running session that has done a `/clear` since connect | **REST `/api/register`** |
| You hit `-32602` once and want to recover | **REST `/api/register`** |

Rule of thumb: MCP is for the human-in-the-loop, casual case. REST is for
anything you want to actually trust.

---

## Path A — MCP `register_claims`

```
client (MCP SDK)
   └── /sse (SSE long-poll on https://citare.dev/sse)
       └── server.call_tool("register_claims", {"json_data": "<envelope>"})
           └── citare_db.ingest_extraction(...)
```

- Auth: none. The public MCP endpoint is unauthenticated.
- Read-only mode: not enabled. `register_claims` is exposed.
- Payload shape: `{"json_data": "<the entire Extraction JSON, as a string>"}`.
  The wrapper is required by the MCP tool inputSchema.
- Verified by: server logs (`[tool] name='register_claims' args=...`) and
  the response payload's `claims_added`, `paper_id`, `warnings`.

### Known failure mode

The Python MCP SDK's SSE transport has a long-standing race between the
client's `initialized` flag and the server's session table. Symptoms:

- Client sees `-32602 Invalid request parameters` on every call after the
  first or two, regardless of payload.
- Server logs show:
  `WARNING:root: Failed to validate request: Received request before initialization was complete`

Triggers we have observed:

1. `/clear` in Claude Code while an SSE socket is held open.
2. An interrupted call (Ctrl-C, network blip).
3. A long-idle session reused after the underlying socket has half-closed.
4. Sub-agents inheriting an SSE handle from the parent.

Recovery via the MCP path takes a `claude mcp remove citare` →
`claude mcp add --transport sse citare https://citare.dev/sse` → Claude
Code restart cycle. This usually buys one or two more registrations before
the race recurs. **It is not a durable fix.** Use REST.

---

## Path B — REST `/api/register`

```
client (anything that can POST JSON)
   └── POST https://citare.dev/api/register
       └── http_server.api_register
           └── citare_db.ingest_extraction(...)   # same function as Path A
```

- Auth: none. Same posture as the MCP endpoint.
- Payload shape: the **raw `Extraction` JSON envelope as the request body**.
  Do NOT wrap it in `{"json_data": "..."}` — that wrapper is only for the
  MCP tool form.
- Response shape: identical to MCP — `paper_id`, `created_paper`,
  `claims_added`, `claims_updated`, `warnings`, `next_steps`. HTTP 200 on
  success. HTTP 400 with `{"error": "...", "detail": "..."}` on validation
  failure.

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

### Why REST is more reliable for writes

- No long-lived session state on the wire — every request is
  self-contained.
- HTTP status codes are first-class, so failure modes are observable
  without parsing JSON-RPC envelopes.
- No SDK in the loop. The Python `mcp` SDK's SSE client is the bug
  surface; REST sidesteps it entirely.

---

## Verifying that a write actually landed

Independent of which path you used:

```
GET https://citare.dev/api/search?q=<doi-or-distinctive-title-fragment>
```

If the paper appears, the write succeeded. This is the recommended sanity
check after every registration — it costs nothing and catches silent SDK
failures.

---

## Operational signals

The server logs the SDK init-race warning to stdout. The repo ships a
log-monitor at `scripts/check_mcp_init_race.sh` — see its header for
threshold/cron setup.

---

## History

- **2026-04-26**: First REST endpoint added as an escape hatch after we
  hit `-32602` repeatedly during a 3-paper register from a remote client.
- **2026-04-28**: This doc and the `INSTRUCTIONS` failure-mode section
  added after a second occurrence (R89 dispatcher hit the same race).
  Decision: REST is now the recommended path for non-interactive use; MCP
  remains for casual interactive use.
