#!/usr/bin/env bash
# Dispatch v0.13d on 30 academic papers from 日本認知科学研究所 (sliding-window).
# Paths contain Japanese, spaces, commas, parens — careful quoting throughout.
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13g_thinking_defensive.md"
LIST="$ROOT/experiments/_ai_workspace/cogsci_batch1.txt"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
MAX_PARALLEL=15
RUN_PREFIX="R73"

mkdir -p "$LOG_DIR"

paper_key() {
    # ASCII-safe key. For Japanese filenames, fall back to numbered sequence.
    local stem
    stem=$(basename "$1" .pdf)
    stem="${stem%.PDF}"
    stem="${stem%_stripped}"
    # Lowercase + non-alnum to underscore. Multi-byte chars get tr-c'd to underscores; that's fine.
    local key
    key=$(echo "$stem" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//' | cut -c1-40)
    if [ -z "$key" ] || [ "$key" = "_" ]; then
        # Fallback: use stable hash of the path
        key="cogsci_$(echo -n "$1" | md5sum | cut -c1-12)"
    fi
    echo "$key"
}

# Read with newline delimiter only (no IFS issue with spaces)
mapfile -t PDFS < "$LIST"
echo "[dispatch R73] ${#PDFS[@]} cogsci papers, sliding window MAX_PARALLEL=${MAX_PARALLEL}"
echo

LAUNCHED=0
SKIPPED=0
TOTAL=${#PDFS[@]}

for pdf in "${PDFS[@]}"; do
    [ -z "$pdf" ] && continue
    if [ ! -f "$pdf" ]; then
        echo "  MISS  $(basename "$pdf")  (file not found)"
        SKIPPED=$((SKIPPED+1))
        continue
    fi
    key=$(paper_key "$pdf")
    runid="${RUN_PREFIX}_v013d_${key}_s1"

    # Two-lock skip
    existing=$(ls -d "$ROOT/experiments/runs/"*"_v013d_${key}_s1" 2>/dev/null | head -1)
    if [ -n "$existing" ] && [ -f "$existing/extraction.json" ] && [ "$(stat -c%s "$existing/extraction.json")" -gt 100 ]; then
        echo "  SKIP  $key  (disk lock)"
        SKIPPED=$((SKIPPED+1))
        continue
    fi
    if pgrep -af "run_extraction_cli.*v013d.*${key}_s1" >/dev/null 2>&1; then
        echo "  SKIP  $key  (process lock)"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    # Wait for slot if at capacity
    while [ "$(jobs -rp | wc -l)" -ge $MAX_PARALLEL ]; do
        wait -n 2>/dev/null
    done

    log="$LOG_DIR/${runid}.log"
    python "$ROOT/experiments/harness/run_extraction_cli.py" \
        --prompt "$PROMPT" \
        --pdf "$pdf" \
        --model claude-opus-4-7 \
        --effort none \
        --max-budget-usd 3.00 \
        --run-id "$runid" \
        --notes "cogsci batch1" \
        > "$log" 2>&1 &
    LAUNCHED=$((LAUNCHED+1))
    echo "  LAUNCH ${LAUNCHED}/${TOTAL}  in_flight=$(jobs -rp | wc -l)/${MAX_PARALLEL}  $runid"
done

echo
echo "[dispatch R73] all ${LAUNCHED} launched. Waiting for in-flight..."
wait

echo
echo "[dispatch R73] === COGSCI BATCH 1 DONE ==="
done_count=0
err_count=0
for d in "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013d_"*; do
    if [ -f "$d/extraction.json" ] && [ "$(stat -c%s "$d/extraction.json")" -gt 100 ]; then
        done_count=$((done_count+1))
    elif [ -f "$d/error.json" ]; then
        err_count=$((err_count+1))
    fi
done
echo "  launched: $LAUNCHED, skipped: $SKIPPED, completed: $done_count, errored: $err_count"
