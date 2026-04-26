# Citare MCP — VPS deployment (HTTP/SSE)

This document describes how to run the Citare MCP server over HTTP/SSE on a
remote VPS, so that hosted AI clients (claude.ai, etc.) can call its tools.

The same `Server` instance and the same tool implementations back both
transports. `citare-mcp` is the legacy stdio entry point (unchanged);
`citare-mcp-http` is the new HTTP/SSE entry point.

## Transport choice

The HTTP entry point uses the **MCP SDK SSE transport**
(`mcp.server.sse.SseServerTransport`), wrapped in a Starlette/uvicorn ASGI
app. Endpoints:

- `GET  /health`   – unauthenticated liveness probe
- `GET  /sse`      – SSE event stream (server → client)
- `POST /messages/?session_id=…` – client → server JSON-RPC

Auth: a single `Authorization: Bearer <api_key>` header, enforced by raw ASGI
middleware (not `BaseHTTPMiddleware`, which buffers SSE responses and breaks
streaming). `/health` is exempt so external monitors can probe it.

## Install

```bash
git clone <repo> citare && cd citare
python -m pip install -e packages/citare-core packages/citare-db packages/citare-mcp
```

This installs both `citare-mcp` (stdio) and `citare-mcp-http` (HTTP/SSE)
console scripts.

## Seed the DB

```bash
mkdir -p /var/lib/citare
python scripts/ingest_v013d_champions.py  # writes ./data/citare.db
sudo cp data/citare.db /var/lib/citare/citare.db
sudo chown citare:citare /var/lib/citare/citare.db
sudo chmod 640 /var/lib/citare/citare.db
```

## Run

```bash
export CITARE_DB=/var/lib/citare/citare.db
export CITARE_API_KEY=$(openssl rand -hex 32)   # store securely
citare-mcp-http --port 8765 --read-only         # public read endpoint
```

CLI flags (all also available as env vars):

| Flag | Env | Default | Notes |
|------|-----|---------|-------|
| `--db` | `CITARE_DB` | `data/citare.db` | SQLite file, must exist |
| `--host` | `CITARE_HOST` | `0.0.0.0` | bind address |
| `--port` | `CITARE_PORT` | `8765` | TCP port |
| `--api-key` | `CITARE_API_KEY` | unset | **required for prod**; if unset, server runs unauthenticated and prints a warning |
| `--read-only` | `CITARE_READ_ONLY` | off | hides the `register_claims` write tool (also rejects calls if reached). Recommended for the public VPS endpoint — register only via local stdio or a private CI pipe. |

## systemd unit

`/etc/systemd/system/citare-mcp.service`:

```ini
[Unit]
Description=Citare MCP HTTP/SSE server
After=network-online.target
Wants=network-online.target

[Service]
User=citare
Group=citare
Environment=CITARE_DB=/var/lib/citare/citare.db
EnvironmentFile=/etc/citare/citare.env       # contains CITARE_API_KEY=...
ExecStart=/opt/citare/venv/bin/citare-mcp-http --port 8765 --read-only
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/citare
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now citare-mcp
sudo systemctl status citare-mcp
curl -s http://127.0.0.1:8765/health    # {"status":"ok",...}
```

## TLS reverse proxy

Terminate TLS in front of citare-mcp; do **not** expose port 8765 directly.

### nginx

```nginx
server {
    listen 443 ssl http2;
    server_name citare.example.com;

    ssl_certificate     /etc/letsencrypt/live/citare.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/citare.example.com/privkey.pem;

    location / {
        proxy_pass         http://127.0.0.1:8765;
        proxy_http_version 1.1;

        # SSE essentials
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 1h;
        proxy_set_header   Connection "";
        proxy_set_header   Host $host;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

### Caddy

```caddy
citare.example.com {
    reverse_proxy 127.0.0.1:8765 {
        flush_interval -1   # disable buffering for SSE
    }
}
```

## claude.ai MCP client config

Register a remote MCP server (claude.ai → Settings → Connectors → Add):

- URL: `https://citare.example.com/sse`
- Auth: Bearer token, value = your `CITARE_API_KEY`

Once added, claude.ai discovers `search_claims`, `cite_claim`,
`get_claim_graph` (and `register_claims` if `--read-only` is not set).

## Read-only deployment pattern

Recommended split for production:

- **VPS**: `citare-mcp-http --read-only` exposes `search_claims`, `cite_claim`,
  `get_claim_graph` to the world (behind TLS + bearer key). Cannot mutate DB.
- **Local / CI**: `citare-mcp` over stdio with full permissions, used by
  trusted extraction pipelines to call `register_claims`. The resulting
  `citare.db` is rsynced to the VPS.

## Test the live endpoint

```bash
# Health
curl -s https://citare.example.com/health

# SSE handshake (auth required)
curl -s -H "Authorization: Bearer $CITARE_API_KEY" \
     https://citare.example.com/sse --max-time 3
# Expected: "event: endpoint\ndata: /messages/?session_id=…"

# Wrong/missing key
curl -s -o /dev/null -w "%{http_code}\n" https://citare.example.com/sse
# Expected: 401
```

## Troubleshooting

- **Streaming hangs / proxy drops connection** → ensure `proxy_buffering off`
  (nginx) or `flush_interval -1` (caddy) on the reverse proxy. SSE breaks
  if the proxy buffers.
- **`AssertionError: Unexpected message: http.response.start`** in uvicorn
  logs → you reintroduced `BaseHTTPMiddleware` somewhere. The auth middleware
  must remain raw ASGI (`__call__(scope, receive, send)`).
- **`DB not found`** → check `CITARE_DB` path against the service `User`'s
  filesystem permissions.
- **Stdio server unaffected** → `citare-mcp` is unchanged; both entry points
  reuse `_make_server(db_path, read_only=…)`.
