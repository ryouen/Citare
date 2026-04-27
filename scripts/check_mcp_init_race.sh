#!/usr/bin/env bash
# check_mcp_init_race.sh — alert on Python MCP SDK SSE init-race recurrence.
#
# What it watches for
#   The exact log line emitted by the SDK when its session_id state goes
#   out of sync with the server:
#       Failed to validate request: Received request before initialization was complete
#
#   This is the durable signature of the bug documented in
#   docs/REGISTRATION_PATHS.md. The first occurrence in a 24h window is
#   often noise (a single /clear); sustained occurrences mean a client is
#   stuck in a retry loop and should be redirected to /api/register.
#
# Usage
#   ./check_mcp_init_race.sh                      # last 24h, default threshold
#   ./check_mcp_init_race.sh --since 1h           # last hour
#   ./check_mcp_init_race.sh --threshold 20       # custom threshold
#   ./check_mcp_init_race.sh --container citare-mcp-admin
#
# Cron setup (host crontab)
#   # Daily 09:00 — alert if >5 init-race warnings in last 24h
#   0 9 * * * /home/ubuntu/citare/scripts/check_mcp_init_race.sh \
#       >> /var/log/citare_init_race.log 2>&1
#
# Exit codes
#   0  — count <= threshold (no alert)
#   1  — count >  threshold (alert: log to stderr/stdout, plus exit non-zero
#         so cron emails the output to MAILTO)

set -u

CONTAINER="citare-mcp"
SINCE="24h"
THRESHOLD=5
PATTERN="Failed to validate request: Received request before initialization was complete"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --container)  CONTAINER="$2"; shift 2 ;;
        --since)      SINCE="$2";     shift 2 ;;
        --threshold)  THRESHOLD="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not on PATH" >&2
    exit 2
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
    echo "container '$CONTAINER' is not running" >&2
    exit 2
fi

LOGS=$(docker logs --since "$SINCE" "$CONTAINER" 2>&1)
COUNT=$(printf '%s\n' "$LOGS" | grep -cF "$PATTERN" || true)
TS=$(date '+%Y-%m-%dT%H:%M:%S%z')

printf '[%s] container=%s since=%s init_race_count=%d threshold=%d\n' \
    "$TS" "$CONTAINER" "$SINCE" "$COUNT" "$THRESHOLD"

if [[ "$COUNT" -gt "$THRESHOLD" ]]; then
    echo "ALERT: SDK init-race threshold exceeded — recent occurrences:"
    printf '%s\n' "$LOGS" | grep -F "$PATTERN" | tail -10
    echo
    echo "Action: redirect any active client to https://citare.dev/api/register"
    echo "        See docs/REGISTRATION_PATHS.md for the workaround."
    exit 1
fi

exit 0
