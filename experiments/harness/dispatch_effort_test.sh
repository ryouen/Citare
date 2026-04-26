#!/usr/bin/env bash
# Effort comparison: 3 papers × 4 effort levels (none/low/medium/high) = 12 runs
# All using v0.13d, seed-1 only.
#
# Goals:
#   1. Determine which effort level maximizes (coverage - integrity_penalty)
#   2. Quantify cost vs quality trade-off
#   3. Provide a reproducible answer for "what effort should we use?"
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13d_hedging_gate_only.md"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
RUN_PREFIX="R80"
MAX_PARALLEL=12   # all 12 in parallel — small batch

mkdir -p "$LOG_DIR"

# Test set: papers with gold so we can score quantitatively
declare -A PDFS=(
    ["edmondson"]="$ROOT/pdfs/06_Psychological_Safety/Edmondson_1999_Psychological_Safety.pdf"
    ["hayes"]="$ROOT/pdfs/04_ACT_RFT/Hayes_2006_ACT_Model.pdf"
    ["t7"]="$ROOT/experiments/ground_truth/trap_papers/T7_scaling_noise.pdf"
)

# Verify all PDFs exist
for paper in "${!PDFS[@]}"; do
    pdf="${PDFS[$paper]}"
    if [ ! -f "$pdf" ]; then
        echo "MISS: $paper -> $pdf"
        exit 1
    fi
done

EFFORTS=("none" "low" "medium" "high")
echo "[effort-test] 3 papers x ${#EFFORTS[@]} efforts = $((3 * ${#EFFORTS[@]})) runs"
echo

LAUNCHED=0
for paper in edmondson hayes t7; do
    pdf="${PDFS[$paper]}"
    for effort in "${EFFORTS[@]}"; do
        runid="${RUN_PREFIX}_v013d_${paper}_eff${effort}_s1"
        log="$LOG_DIR/${runid}.log"

        # Skip if already done
        existing=$(ls -d "$ROOT/experiments/runs/"*"_${runid}" 2>/dev/null | head -1)
        if [ -n "$existing" ] && [ -f "$existing/extraction.json" ] && [ "$(stat -c%s "$existing/extraction.json")" -gt 100 ]; then
            echo "  SKIP  $runid"
            continue
        fi

        while [ "$(jobs -rp | wc -l)" -ge $MAX_PARALLEL ]; do
            wait -n 2>/dev/null
        done

        python "$ROOT/experiments/harness/run_extraction_cli.py" \
            --prompt "$PROMPT" \
            --pdf "$pdf" \
            --model claude-opus-4-7 \
            --effort "$effort" \
            --max-budget-usd 5.00 \
            --run-id "$runid" \
            --notes "effort comparison" \
            > "$log" 2>&1 &
        LAUNCHED=$((LAUNCHED+1))
        echo "  LAUNCH ${LAUNCHED}/12  $paper × effort=$effort"
    done
done

echo
echo "[effort-test] all $LAUNCHED launched, waiting..."
wait
echo
echo "[effort-test] === DONE ==="
ls -d "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013d_"* 2>/dev/null | wc -l | xargs echo "Total R80 dirs:"
