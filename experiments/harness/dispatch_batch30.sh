#!/usr/bin/env bash
# Dispatch v0.13d extractions for batch_30 in 2 waves of 15 (rate-limit safe).
#
# Two-lock skip-check before each launch:
#  1. Disk: any *_v013d_<paperkey>_s1 with extraction.json
#  2. Process: pgrep for an in-flight run
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13g_thinking_defensive.md"
LIST="$ROOT/experiments/_ai_workspace/batch_30.txt"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
WAVE_SIZE=15
INTER_WAVE_SLEEP=30
RUN_PREFIX="R71"

mkdir -p "$LOG_DIR"

paper_key() {
    # Filename → safe paper key (no special chars, lowercase, capped at 40)
    local stem=$(basename "$1" .pdf)
    stem="${stem%_stripped}"
    echo "$stem" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_' | sed 's/__*/_/g; s/^_//; s/_$//' | cut -c1-40
}

# Read batch
mapfile -t PDFS < "$LIST"
echo "[dispatch] ${#PDFS[@]} PDFs to process in waves of ${WAVE_SIZE}"
echo "[dispatch] prompt: $PROMPT"
echo

LAUNCHED_PIDS=()
WAVE_NUM=1
COUNT_IN_WAVE=0

for pdf in "${PDFS[@]}"; do
    key=$(paper_key "$pdf")
    runid="${RUN_PREFIX}_v013d_${key}_s1"

    # === Two-lock skip check ===
    # 1. Disk: any existing dir for this (paper, seed)
    existing=$(ls -d "$ROOT/experiments/runs/"*"_v013d_${key}_s1" 2>/dev/null | head -1)
    if [ -n "$existing" ] && [ -f "$existing/extraction.json" ] && [ "$(stat -c%s "$existing/extraction.json")" -gt 100 ]; then
        echo "  SKIP  $key  (disk lock: $existing)"
        continue
    fi
    # 2. Process: any in-flight run for this exact key
    if pgrep -af "run_extraction_cli.*v013d.*${key}_s1" >/dev/null 2>&1; then
        echo "  SKIP  $key  (process lock)"
        continue
    fi

    # === Launch ===
    log="$LOG_DIR/${runid}.log"
    python "$ROOT/experiments/harness/run_extraction_cli.py" \
        --prompt "$PROMPT" \
        --pdf "$pdf" \
        --model claude-opus-4-7 \
        --effort none \
        --max-budget-usd 3.00 \
        --run-id "$runid" \
        --notes "batch30 wave${WAVE_NUM}" \
        > "$log" 2>&1 &
    pid=$!
    LAUNCHED_PIDS+=($pid)
    echo "  LAUNCH wave${WAVE_NUM} #$((COUNT_IN_WAVE+1))  pid=$pid  $runid"
    COUNT_IN_WAVE=$((COUNT_IN_WAVE+1))

    # End of wave?
    if [ $COUNT_IN_WAVE -ge $WAVE_SIZE ]; then
        echo
        echo "[dispatch] wave ${WAVE_NUM} full (${COUNT_IN_WAVE} jobs). Waiting for completion..."
        wait "${LAUNCHED_PIDS[@]}"
        echo "[dispatch] wave ${WAVE_NUM} done."
        WAVE_NUM=$((WAVE_NUM+1))
        COUNT_IN_WAVE=0
        LAUNCHED_PIDS=()
        if [ $WAVE_NUM -le 2 ]; then
            echo "[dispatch] sleeping ${INTER_WAVE_SLEEP}s before wave ${WAVE_NUM}..."
            sleep $INTER_WAVE_SLEEP
        fi
    fi
done

# Final wave
if [ $COUNT_IN_WAVE -gt 0 ]; then
    echo
    echo "[dispatch] waiting on final ${COUNT_IN_WAVE} jobs..."
    wait "${LAUNCHED_PIDS[@]}"
fi

echo
echo "[dispatch] === ALL DONE ==="
ls -d "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013d_"* 2>/dev/null | wc -l | xargs echo "Run dirs created:"
