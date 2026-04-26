#!/usr/bin/env bash
# Dispatch the remaining 9 PDFs (after batch_30) using sliding-window concurrency.
# Run this AFTER dispatch_batch30_sliding.sh has completed.
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13g_thinking_defensive.md"
LIST="$ROOT/experiments/_ai_workspace/batch_remaining.txt"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
MAX_PARALLEL=15
RUN_PREFIX="R72"

mkdir -p "$LOG_DIR"

paper_key() {
    local stem=$(basename "$1" .pdf)
    stem="${stem%_stripped}"
    echo "$stem" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//' | cut -c1-40
}

mapfile -t PDFS < "$LIST"
echo "[dispatch] ${#PDFS[@]} remaining PDFs, sliding window MAX_PARALLEL=${MAX_PARALLEL}"
echo

LAUNCHED=0
SKIPPED=0
TOTAL=${#PDFS[@]}

for pdf in "${PDFS[@]}"; do
    key=$(paper_key "$pdf")
    runid="${RUN_PREFIX}_v013d_${key}_s1"

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
        --notes "remaining 9 sliding" \
        > "$log" 2>&1 &
    LAUNCHED=$((LAUNCHED+1))
    echo "  LAUNCH ${LAUNCHED}/${TOTAL}  in_flight=$(jobs -rp | wc -l)/${MAX_PARALLEL}  $runid"
done

echo
echo "[dispatch] all ${LAUNCHED} jobs launched. Waiting for in-flight..."
wait
echo
echo "[dispatch] === REMAINING DONE ==="
echo "  launched: $LAUNCHED, skipped: $SKIPPED"
done_count=0
for d in "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013d_"*; do
    if [ -f "$d/extraction.json" ] && [ "$(stat -c%s "$d/extraction.json")" -gt 100 ]; then
        done_count=$((done_count+1))
    fi
done
echo "  with extraction.json: $done_count"
