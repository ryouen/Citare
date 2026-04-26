#!/usr/bin/env bash
# R83: re-extract 15 papers at v0.13g × effort=none (the new production lock).
# 15 in parallel, single sliding-window batch.
#
# Records exact start/stop wall time + per-run metrics for cost analysis.
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13g_thinking_defensive.md"
LIST="$ROOT/experiments/_ai_workspace/reextract_15_pdfs.txt"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
RUN_PREFIX="R83"
MAX_PARALLEL=15

mkdir -p "$LOG_DIR"

# Wall time tracking
START_EPOCH=$(date -u +%s)
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[R83] START $START_ISO"
echo "[R83] re-extract 15 papers at v0.13g × none, MAX_PARALLEL=$MAX_PARALLEL"
echo

paper_key() {
    local stem
    stem=$(basename "$1" .pdf)
    stem="${stem%.PDF}"
    stem="${stem%_stripped}"
    local key
    key=$(echo "$stem" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//' | cut -c1-40)
    if [ -z "$key" ] || [ "$key" = "_" ]; then
        key="r83_$(echo -n "$1" | md5sum | cut -c1-12)"
    fi
    echo "$key"
}

mapfile -t PDFS < "$LIST"

LAUNCHED=0
for pdf in "${PDFS[@]}"; do
    [ -z "$pdf" ] && continue
    if [ ! -f "$pdf" ]; then
        echo "  MISS $(basename "$pdf")"
        continue
    fi
    key=$(paper_key "$pdf")
    runid="${RUN_PREFIX}_v013g_${key}_s1"
    log="$LOG_DIR/${runid}.log"

    # Skip lock (this batch should NOT skip — we want fresh v013g extractions)
    # Don't check disk lock for legacy runs since they used v013d

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
        --notes "R83 re-extract: P0+P1+RCT-P3 at v0.13g × none" \
        > "$log" 2>&1 &
    LAUNCHED=$((LAUNCHED+1))
    echo "  LAUNCH ${LAUNCHED}/15  in_flight=$(jobs -rp | wc -l)/${MAX_PARALLEL}  $runid"
done

echo
echo "[R83] all $LAUNCHED launched, waiting for completion..."
wait

END_EPOCH=$(date -u +%s)
END_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
WALL_SEC=$((END_EPOCH - START_EPOCH))

# Tally results
done_count=0
err_count=0
for d in "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013g_"*; do
    if [ -f "$d/extraction.json" ] && [ "$(stat -c%s "$d/extraction.json")" -gt 100 ]; then
        done_count=$((done_count+1))
    elif [ -f "$d/error.json" ]; then
        err_count=$((err_count+1))
    fi
done

echo
echo "[R83] === COMPLETE ==="
echo "[R83] start:  $START_ISO"
echo "[R83] end:    $END_ISO"
echo "[R83] wall:   ${WALL_SEC}s ($((WALL_SEC / 60))m $((WALL_SEC % 60))s)"
echo "[R83] launched: $LAUNCHED, completed: $done_count, errored: $err_count"
echo
echo "(Run scripts/analyze_r83_costs.py for full token/time/cost breakdown)"
