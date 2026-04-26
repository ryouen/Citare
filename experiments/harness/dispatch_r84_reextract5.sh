#!/usr/bin/env bash
# R84: re-extract next 5 papers at v0.13g × effort=none.
# Strategic mix: cognitive psych iconic, AI capability, RCT, meta-analysis.
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13g_thinking_defensive.md"
LIST="$ROOT/experiments/_ai_workspace/reextract_5_pdfs.txt"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
RUN_PREFIX="R84"
MAX_PARALLEL=5

mkdir -p "$LOG_DIR"

START_EPOCH=$(date -u +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[R84] START $START_ISO"
echo "[R84] re-extract 5 papers at v0.13g × none, MAX_PARALLEL=$MAX_PARALLEL"
echo

paper_key() {
    local stem
    stem=$(basename "$1" .pdf)
    stem="${stem%.PDF}"
    stem="${stem%_stripped}"
    local key
    key=$(echo "$stem" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//' | cut -c1-40)
    [ -z "$key" ] || [ "$key" = "_" ] && key="r84_$(echo -n "$1" | md5sum | cut -c1-12)"
    echo "$key"
}

mapfile -t PDFS < "$LIST"

LAUNCHED=0
for pdf in "${PDFS[@]}"; do
    [ -z "$pdf" ] && continue
    [ ! -f "$pdf" ] && { echo "  MISS $(basename "$pdf")"; continue; }
    key=$(paper_key "$pdf")
    runid="${RUN_PREFIX}_v013g_${key}_s1"
    log="$LOG_DIR/${runid}.log"

    while [ "$(jobs -rp | wc -l)" -ge $MAX_PARALLEL ]; do
        wait -n 2>/dev/null
    done

    python "$ROOT/experiments/harness/run_extraction_cli.py" \
        --prompt "$PROMPT" \
        --pdf "$pdf" \
        --model claude-opus-4-7 \
        --effort none \
        --max-budget-usd 5.00 \
        --run-id "$runid" \
        --notes "R84 next-5 at v0.13g × none" \
        > "$log" 2>&1 &
    LAUNCHED=$((LAUNCHED+1))
    echo "  LAUNCH ${LAUNCHED}/5  in_flight=$(jobs -rp | wc -l)/${MAX_PARALLEL}  $runid"
done

echo
echo "[R84] all $LAUNCHED launched, waiting..."
wait

END_EPOCH=$(date -u +%s)
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
WALL_SEC=$((END_EPOCH - START_EPOCH))

done_count=0; err_count=0
for d in "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013g_"*; do
    [ -f "$d/extraction.json" ] && [ "$(stat -c%s "$d/extraction.json")" -gt 100 ] && done_count=$((done_count+1))
    [ -f "$d/error.json" ] && err_count=$((err_count+1))
done

echo
echo "[R84] === COMPLETE ==="
echo "[R84] start: $START_ISO  end: $END_ISO  wall: ${WALL_SEC}s ($((WALL_SEC/60))m $((WALL_SEC%60))s)"
echo "[R84] launched: $LAUNCHED, completed: $done_count, errored: $err_count"
