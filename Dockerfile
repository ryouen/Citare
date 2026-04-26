FROM python:3.12-slim

WORKDIR /app

# Install build deps. Lock to slim image; we don't need OS-level packages.
RUN pip install --no-cache-dir --upgrade pip

# Install the three packages. Copy source first so install doesn't redo on
# every code change (would be true if we cached pip; here it's just a clean
# layer order).
COPY packages/ ./packages/
RUN pip install --no-cache-dir \
        ./packages/citare-core \
        ./packages/citare-db \
        ./packages/citare-mcp

# Scripts (smoke test, ingest, resolver) — useful for ops + container exec
COPY scripts/ ./scripts/

# Experiments dir is needed at runtime ONLY if you re-ingest from extraction.json.
# We bind-mount it from host instead of baking into the image (smaller image,
# faster rebuild on doc/manifest tweaks).

# Non-root user
RUN groupadd -r citare && useradd -r -g citare -d /app -s /sbin/nologin citare && \
    chown -R citare:citare /app

USER citare

EXPOSE 8765

# Default command runs the HTTP/SSE server. The compose layer supplies
# CITARE_DB, CITARE_API_KEY, and (optionally) --read-only.
CMD ["citare-mcp-http", "--host", "0.0.0.0", "--port", "8765"]
