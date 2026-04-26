"""ContextVar carrier for the authenticated key on the current request.

Set by `_RegistryAuthMiddleware` (http_server.py) on entry, read by tool
handlers in `server.py` that need to know which key called them — for
scope checks, for budget charging, for audit logging.

ContextVars propagate through `await` in the same async task, which is
how the MCP SSE transport dispatches tool calls. Each POST /messages/?...
runs as a separate task whose contextvar is set fresh by the middleware.
"""
from __future__ import annotations

from contextvars import ContextVar

from citare_mcp.auth import KeyInfo

# `None` when the request was unauthenticated (public read endpoint),
# or when scope check is being run from a non-HTTP context (stdio mode).
current_key: ContextVar[KeyInfo | None] = ContextVar("current_key", default=None)
