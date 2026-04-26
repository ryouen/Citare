#!/bin/bash
# Dispatch extraction waves with rate-limit-safe pacing.
#
# Empirical learning from Stage C / R55-R64:
#   - <=25 parallel processes: 100% success rate
#   - 30-50 parallel: 50-90% (degraded)
#   - 50+ parallel: 0-87% (frequent rc=1 failures)
#
# WAVE_SIZE=15 (default) keeps us safely under the 25-job ceiling.
# INTER_WAVE_SLEEP=30s ensures the previous wave fully clears before next starts.
#
# Usage: dispatch_waves.sh <prompt_file> <output_prefix> <papers_csv> <seeds_csv>
# Example: dispatch_waves.sh experiments/prompts/v0.13d.md R65 "T7,einstein" "1,2,3"

WAVE_SIZE="${WAVE_SIZE:-15}"
INTER_WAVE_SLEEP="${INTER_WAVE_SLEEP:-30}"

# Paper -> PDF mapping (extend as needed)
declare -A PDF_OF=(
  [T7]="experiments/ground_truth/trap_papers/T7_scaling_noise.pdf"
  [einstein]="pdfs/99_test_extreme/Einstein_1905_Relativity_German.pdf"
  [edmondson]="pdfs/06_Psychological_Safety/Edmondson_1999_Psychological_Safety.pdf"
  [wei]="pdfs/05_AI_Safety/Wei_2022_Chain_of_Thought.pdf"
  [barney]="pdfs/01_OB/Barney_1991_Firm_Resources.pdf"
  [vaswani]="pdfs/02_CS_AI_LLM/Vaswani_2017_Attention_Is_All_You_Need.pdf"
  [shannon]="pdfs/entropy.pdf"
  [turing]="pdfs/Computing Machinery and Intelligence by Alan Turing.pdf"
  [watsoncrick]="pdfs/WatsonCrick1953.pdf"
  [park]="pdfs/02_CS_AI_LLM/Park_2023_Generative_Agents.pdf"
  [noyzhang]="pdfs/01_OB/Noy_Zhang_2023_Productivity_GenAI.pdf"
  [hubinger]="pdfs/05_AI_Safety/Hubinger_2024_Sleeper_Agents.pdf"
  [hayes]="pdfs/04_ACT_RFT/Hayes_2006_ACT_Model.pdf"
)

prompt="$1"
prefix="$2"
IFS=',' read -ra PAPERS <<< "$3"
IFS=',' read -ra SEEDS <<< "$4"

# Build full job list, but SKIP cells that are already done OR currently running.
# A cell is identified by (variant_short, paper, seed). The variant_short is the
# part of run-id between "<prefix>_" and "_<paper>_s<seed>".
# Both checks (file-on-disk + process-running) together prevent the duplicate
# launches that happened between R62/R63/R64 in Stage C (wasted ~$5-10 in
# duplicated token cost).
jobs=()
skipped_done=0
skipped_running=0
variant_match=$(echo "$prefix" | grep -oE 'v[0-9]+[a-z]?' | head -1)
for p in "${PAPERS[@]}"; do
  for s in "${SEEDS[@]}"; do
    cell="${p}_s${s}"
    # 1. already-done check
    done_already=0
    if [ -n "$variant_match" ]; then
      for d in experiments/runs/*_*${variant_match}*_${cell}; do
        if [ -f "$d/extraction.json" ] && [ $(stat -c%s "$d/extraction.json" 2>/dev/null) -gt 100 ]; then
          done_already=1; break
        fi
      done 2>/dev/null
    fi
    if [ $done_already -eq 1 ]; then
      skipped_done=$((skipped_done+1))
      continue
    fi
    # 2. currently-running check (process exists)
    running=0
    if [ -n "$variant_match" ]; then
      pgrep -af "run_extraction_cli.*${variant_match}.*${cell}" 2>/dev/null | grep -q "."  && running=1
    fi
    if [ $running -eq 1 ]; then
      skipped_running=$((skipped_running+1))
      continue
    fi
    jobs+=("$p:$s")
  done
done
echo "[dispatch] skip: $skipped_done already-done, $skipped_running currently-running"

total=${#jobs[@]}
echo "[dispatch] $total jobs in waves of $WAVE_SIZE (sleep ${INTER_WAVE_SLEEP}s between)"

# Dispatch in waves
i=0
while [ $i -lt $total ]; do
  wave_pids=()
  for ((j=0; j<WAVE_SIZE && i+j<total; j++)); do
    job="${jobs[$((i+j))]}"
    paper="${job%%:*}"; seed="${job##*:}"
    pdf="${PDF_OF[$paper]}"
    [ -z "$pdf" ] && { echo "  unknown paper: $paper"; continue; }
    python experiments/harness/run_extraction_cli.py \
      --prompt "$prompt" \
      --pdf "$pdf" \
      --model claude-opus-4-7 \
      --effort none \
      --run-id "${prefix}_${paper}_s${seed}" \
      --notes "wave dispatch ${prefix} ${paper} s${seed}" &
    wave_pids+=("$!")
  done
  echo "[wave] launched ${#wave_pids[@]} jobs starting at index $i"
  for pid in "${wave_pids[@]}"; do wait "$pid"; done
  i=$((i + WAVE_SIZE))
  if [ $i -lt $total ]; then
    echo "[wait] sleeping ${INTER_WAVE_SLEEP}s before next wave"
    sleep "$INTER_WAVE_SLEEP"
  fi
done
echo "[dispatch] all $total jobs done"
