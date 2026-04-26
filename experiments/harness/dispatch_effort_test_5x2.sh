#!/usr/bin/env bash
# Effort comparison expansion: 5 papers × 2 efforts (none, low) = 10 runs
# All-parallel. Adds to R80 (3 papers × 4 efforts) for n=8 papers × 2 efforts on the none/low axis.
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
PROMPT="$ROOT/experiments/prompts/v0.13d_hedging_gate_only.md"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
RUN_PREFIX="R81"
MAX_PARALLEL=10

mkdir -p "$LOG_DIR"

declare -A PDFS=(
    ["einstein"]="$ROOT/pdfs/1905_17_891-921.pdf"
    ["vaswani"]="$ROOT/pdfs/02_CS_AI_LLM/Vaswani_2017_Attention_Is_All_You_Need.pdf"
    ["hubinger"]="$ROOT/pdfs/05_AI_Safety/Hubinger_2024_Sleeper_Agents.pdf"
    ["wei"]="$ROOT/pdfs/05_AI_Safety/Wei_2022_Chain_of_Thought.pdf"
    ["noyzhang"]="$ROOT/pdfs/01_OB/Noy_Zhang_2023_Productivity_GenAI.pdf"
)
EFFORTS=("none" "low")
echo "[effort-test 5x2] launching 5 papers x 2 efforts = 10 runs"
echo

LAUNCHED=0
for paper in einstein vaswani hubinger wei noyzhang; do
    pdf="${PDFS[$paper]}"
    for effort in "${EFFORTS[@]}"; do
        runid="${RUN_PREFIX}_v013d_${paper}_eff${effort}_s1"
        log="$LOG_DIR/${runid}.log"

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
            --notes "effort 5x2 expansion" \
            > "$log" 2>&1 &
        LAUNCHED=$((LAUNCHED+1))
        echo "  LAUNCH ${LAUNCHED}/10  $paper × effort=$effort"
    done
done

echo
echo "[effort-test 5x2] all $LAUNCHED launched, waiting..."
wait
echo
echo "[effort-test 5x2] === DONE ==="
ls -d "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_v013d_"* 2>/dev/null | wc -l | xargs echo "Total R81 dirs:"
