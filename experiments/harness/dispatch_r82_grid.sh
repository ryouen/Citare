#!/usr/bin/env bash
# R82: 6 papers × 3 efforts × 2 prompts = 36 runs
# Tests:
#   - Does v0.13f (EXISTENCE preservation rule) fix the noyzhang regression?
#   - Does effort × prompt interact differently across paper types?
set -u

ROOT="D:/Dropbox/ai/CitareOpus47"
LOG_DIR="$ROOT/experiments/_ai_workspace/logs"
RUN_PREFIX="R82"
MAX_PARALLEL=18

mkdir -p "$LOG_DIR"

declare -A PDFS=(
    ["noyzhang"]="$ROOT/pdfs/01_OB/Noy_Zhang_2023_Productivity_GenAI.pdf"
    ["hubinger"]="$ROOT/pdfs/05_AI_Safety/Hubinger_2024_Sleeper_Agents.pdf"
    ["park"]="$ROOT/pdfs/99_test_extreme/Park_2023_Generative_Agents.pdf"
    ["edmondson"]="$ROOT/pdfs/06_Psychological_Safety/Edmondson_1999_Psychological_Safety.pdf"
    ["wei"]="$ROOT/pdfs/05_AI_Safety/Wei_2022_Chain_of_Thought.pdf"
    ["t7"]="$ROOT/experiments/ground_truth/trap_papers/T7_scaling_noise.pdf"
)

declare -A PROMPTS=(
    ["v013d"]="$ROOT/experiments/prompts/v0.13d_hedging_gate_only.md"
    ["v013f"]="$ROOT/experiments/prompts/v0.13f_existence_preservation.md"
)

EFFORTS=("none" "low" "medium")

# Verify all PDFs and prompts exist
for paper in "${!PDFS[@]}"; do
    [ -f "${PDFS[$paper]}" ] || { echo "MISS PDF: $paper -> ${PDFS[$paper]}"; exit 1; }
done
for promptkey in "${!PROMPTS[@]}"; do
    [ -f "${PROMPTS[$promptkey]}" ] || { echo "MISS PROMPT: $promptkey"; exit 1; }
done

echo "[R82] grid: 6 papers × 3 efforts × 2 prompts = 36 runs"
echo "[R82] sliding-window MAX_PARALLEL=$MAX_PARALLEL"
echo

LAUNCHED=0
for paper in noyzhang hubinger park edmondson wei t7; do
    pdf="${PDFS[$paper]}"
    for effort in "${EFFORTS[@]}"; do
        for promptkey in v013d v013f; do
            prompt="${PROMPTS[$promptkey]}"
            runid="${RUN_PREFIX}_${promptkey}_${paper}_eff${effort}_s1"
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
                --prompt "$prompt" \
                --pdf "$pdf" \
                --model claude-opus-4-7 \
                --effort "$effort" \
                --max-budget-usd 5.00 \
                --run-id "$runid" \
                --notes "R82 grid" \
                > "$log" 2>&1 &
            LAUNCHED=$((LAUNCHED+1))
            echo "  LAUNCH ${LAUNCHED}/36  in_flight=$(jobs -rp | wc -l)/${MAX_PARALLEL}  $runid"
        done
    done
done

echo
echo "[R82] all $LAUNCHED launched, waiting..."
wait
echo
echo "[R82] === DONE ==="
done_count=0; err_count=0
for d in "$ROOT/experiments/runs/"*"_${RUN_PREFIX}_"*; do
    if [ -f "$d/extraction.json" ] && [ "$(stat -c%s "$d/extraction.json")" -gt 100 ]; then
        done_count=$((done_count+1))
    elif [ -f "$d/error.json" ]; then
        err_count=$((err_count+1))
    fi
done
echo "  completed: $done_count, errored: $err_count"
