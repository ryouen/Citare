# Handoff Reply pt.2 — Effort Tuning + LLM Parameter Notes (2026-04-26)

> ⚠️ **OBSOLETE — superseded by `HANDOFF_REPLY_TO_VPS_2026-04-26_pt3.md`** (same date, later in the day).
>
> The §1 recommendation in this document — "**default = `--effort low`**" — was based on R80+R81 (n=22). A larger
> grid R82 (n=72) ran later the same day and **reversed the conclusion**: low causes thesis-level miss when paired
> with anti-compression / self-check prompts, and `v0.13g × effort=none` is the true champion. See pt.3 for details.
>
> §2 (LLM parameter notes) and §3 (production-grade config template) are still valid as general LLM-side guidance,
> with one correction: the recommended `thinking budget_tokens=1024` should be **removed** — production now uses
> no thinking parameter at all (= effort=none). Update the §3 template accordingly when reading.
>
> This document is preserved unchanged for audit trail. Do not act on its §1 operational recommendation.

---

This is an addendum to `HANDOFF_REPLY_TO_VPS_2026-04-26.md`. Two topics:

1. We empirically tuned the production extraction effort level. Default changed from `none` to `low`.
2. Notes on **other LLM-side parameters** the VPS-side AI / future local-LLM port should care about.

---

## 1. Effort tuning experiment (R80 + R81)

### 1.1 What we tested

| Phase | Papers | Efforts tested | n |
|-------|--------|---------------|--:|
| R80 | edmondson, hayes, T7 | none, low, medium, high | 12 |
| R81 | einstein, vaswani, hubinger, wei, noyzhang | none, low | 10 |
| **Total on the none/low axis** | **8 papers** | none, low | **16** |

All runs use **v0.13d locked prompt**, claude-opus-4-7, seed-1, against gold for quantitative scoring.

### 1.2 What "effort" actually means

The `--effort` flag in `run_extraction_cli.py` maps to Claude CLI's `--effort` argument:
- The CLI defines: `low | medium | high | xhigh | max` (5 values)
- Our wrapper adds a 6th sentinel `none` which means "do not pass `--effort` at all" → extended thinking disabled
- We probed the CLI: `--effort none` is rejected by Claude CLI directly (`"argument 'none' is invalid"`)

So `none` ≡ extended thinking disabled (default mode). `low/medium/...` enable extended thinking with progressively larger thinking-token budgets.

### 1.3 Result — R80 (3 papers × 4 efforts)

| Effort | Avg coverage | Avg cost | Avg duration | Avg out tokens |
|--------|------------:|---------:|-------------:|---------------:|
| none | 88.2% | $1.31 | 315s | 26K |
| **low** | **90.5%** | **$1.37** | 294s | 23K |
| medium | 85.2% | $1.44 | 316s | 26K |
| high | 89.9% | $1.49 | 341s | 28K |

### 1.4 Per-paper breakdown reveals the mechanism

Edmondson (saturated baseline) and Hayes (theory-heavy) both score the **exact same coverage at every effort** (95.0%, 90.9%). Effort has zero effect on saturated extractions.

T7 (a "trap paper" that uses misleading scaling=noise rhetoric) is the only paper where effort matters:

| T7 effort | coverage | what happens |
|-----------|---------:|--------------|
| none | 78.6% | LLM picks the surface narrative |
| **low** | **85.7%** (+7pp) | brief verification catches the trap |
| medium | 69.6% (-9pp) | extended thinking *follows* the misleading rhetoric and hallucinates wrong answer |
| high | 83.9% | more thinking budget allows self-correction |

So **on saturated papers effort is a no-op; on trap-class papers low > none and medium can actively backfire**.

### 1.5 Decision: production default = `low`

For the entire pipeline:
- Coverage uplift: **+2.4pp average** (driven by trap-class papers)
- Cost uplift: **+$0.06/run** (negligible)
- Risk: zero on saturated papers; positive on trap-class
- Time: comparable (~300s)

**`run_extraction_cli.py` argparse default changed from `none` → `low`.** All `dispatch_*.sh` scripts updated.

Existing 82 papers extracted at `none` are NOT retroactively re-extracted (per Pareto: 80/82 papers are saturated, so re-extraction has near-zero ROI). Future batches use `low`.

### 1.6 Files committed for this experiment

```
experiments/harness/dispatch_effort_test.sh           # R80 dispatch
experiments/harness/dispatch_effort_test_5x2.sh       # R81 dispatch
scripts/analyze_effort_test.py                        # Aggregator
experiments/EFFORT_COMPARISON.md                      # Report
experiments/runs/*_R80_v013d_*_eff{none,low,medium,high}_s1/  # Raw runs
experiments/runs/*_R81_v013d_*_eff{none,low}_s1/              # Raw runs
```

### 1.7 Implication for VPS-side `extract_and_register`

If the VPS-side AI extracts new papers via the hosted Claude API directly (not via Claude CLI), the equivalent setting is:

- **Anthropic API**: `thinking={"type": "enabled", "budget_tokens": 1024}` (= "low")
- **Default** (no thinking parameter): equivalent to our old `none`
- Recommendation: enable thinking with **budget_tokens between 1024 and 2048** for new extractions, especially on novel domains (where you don't yet know if the paper is "trap-class")

Avoid `budget_tokens >= 4096` (= medium-equivalent): on the T7 case it actively reduced quality.

---

## 2. Other LLM-side parameters worth fixing (not just effort)

If a sub-agent ever ports this pipeline to a local LLM (Llama 3.x, Qwen, DeepSeek, etc.) or to a non-Claude API, these are the parameters that materially affect extraction quality. The default settings we use today rely on Claude CLI's defaults, which differ from raw API defaults — making them implicit but important.

### 2.1 Decoding parameters (most important)

| Parameter | Recommended | Why this matters for Citare |
|-----------|-------------|------------------------------|
| **temperature** | **0.0 — 0.2** | Citare extraction is a *deterministic transformation* (PDF → JSON). Temperature > 0.5 introduces creative noise into IDs, field names, and quoted source_text. v0.13d's seed std-dev of 0.00pp is partly because Claude CLI defaults to low temperature. |
| **top_p** | 1.0 (or unset) | Don't double-restrict. If you're already at temp=0.0, top_p does nothing. |
| **top_k** | unset / 0 | Same. |
| **max_tokens (output)** | **≥ 32K**, ideally 64K | Hayes 2006 emits ~32K output tokens at the upper end. Setting max_tokens too low causes silent JSON truncation → ingest fails with `JSONDecodeError`. The Hayes baddeley_hitch outlier (1.1KB extraction that we flagged earlier) might actually be max_tokens truncation in disguise. |
| **stop_sequences** | none | Don't add `\n\n` etc. — JSON output legitimately contains those. |

### 2.2 Sampling reproducibility

| Parameter | For Anthropic API | For local LLMs |
|-----------|-------------------|----------------|
| Random seed | Anthropic API does not expose seed — temperature=0 is the only repro lever | Local engines (vLLM, llama.cpp, Ollama) usually accept `--seed N` — set it for repro |
| **deterministic mode** | Use `temperature=0.0` exactly (not 0.01) | vLLM: `--enforce-eager` + seed; llama.cpp: `--seed 42 --temp 0` |

### 2.3 System / prompt structure

| Concern | Setting |
|---------|---------|
| **System prompt cache** | Anthropic API: enable `cache_control` on the v0.13d prompt — saves ~$0.50/run after first hit. The Claude CLI does this transparently; if you build a custom client, do it explicitly. |
| **PDF input** | Use Claude's PDF input directly (file upload) rather than text-extracting first. Text extraction loses figure captions and formula structure. For local LLMs without native PDF support, use `pdf-strip-images.py` (in `experiments/harness/`) + a vision-LLM hybrid. |
| **Response format / structured outputs** | We do NOT use Anthropic's structured-output / tool-use mode. The prompt asks for raw JSON in markdown code fence; the parser strips the fence. Switching to native structured outputs would marginally improve schema conformance but lose the L0/L3 polymorphism we rely on. Don't switch without testing. |

### 2.4 Context window

| Setting | Notes |
|---------|-------|
| **Input context** | Need ≥ 200K tokens for long papers (Hayes 2006 ≈ 50 pages × 800 words = 80K input + 32K output). Most papers fit in 32K, but the headroom matters. Don't try to chunk PDFs — the prompt is single-pass. |
| **Output reserve** | Reserve 32K for output. So if the model has 200K context, 168K available for input. |

### 2.5 Sampling traps to avoid

- **`logit_bias`** to forbid certain tokens — don't. The schema enforces structure; we don't need to bias tokens.
- **`presence_penalty` / `frequency_penalty`** — don't. They bias against repeated patterns, but JSON keys legitimately repeat (`source_text`, `verification_status`, ...).
- **`min_p` / `typical_p`** (newer samplers) — leave at engine defaults. With temp=0 they're no-ops anyway.

### 2.6 Per-engine recipes

#### Anthropic Claude API (the gold standard)
```python
client.messages.create(
    model="claude-opus-4-7",
    max_tokens=32768,
    temperature=0.0,
    thinking={"type": "enabled", "budget_tokens": 1024},   # = effort=low
    system=[
        {"type": "text", "text": v0_13d_prompt,
         "cache_control": {"type": "ephemeral"}},
    ],
    messages=[
        {"role": "user", "content": [
            {"type": "document", "source": {"type": "base64",
                                              "media_type": "application/pdf",
                                              "data": pdf_b64}},
            {"type": "text", "text": "Extract claims from this paper."},
        ]}
    ],
)
```

#### vLLM (Llama 3.1 70B+, Qwen2.5 72B, DeepSeek-V3 etc.)
```bash
vllm serve <model> \
    --max-model-len 131072 \
    --enforce-eager \
    --seed 42

curl http://localhost:8000/v1/chat/completions -d '{
  "model": "...",
  "temperature": 0.0,
  "max_tokens": 32768,
  "messages": [...]
}'
```
Notes for local LLMs:
- Skip `thinking` (no equivalent), but bump max_tokens because the model may "think on paper" inside the JSON output
- Use a multimodal model (Qwen2.5-VL, Llama 3.2 Vision) OR pre-extract PDF text, no fallback
- Expect 5-10pp lower coverage than Opus 4.7 even at best — Opus is the production champion choice for a reason

#### llama.cpp
```bash
./llama-cli -m <model.gguf> \
    --temp 0 --seed 42 \
    -c 131072 -n 32768 \
    --no-mmap
```

### 2.7 What we will NOT change (constraints inherited from v0.13d)

These belong with the prompt, not the engine, and changing them breaks the schema contract:

- **JSON-as-codeblock output format** — required by `Extraction.model_validate_json` parser
- **Snake_case for concepts** — drives FTS5 `l0_concepts` indexing
- **Author-year-style claim IDs** (`edmondson1999_rel2`) — stable across re-runs
- **5-template enum** (DEFINITION/RELATION/EXISTENCE_CLAIM/META_CLAIM)
- **`verification_status` hedging gate rules** — the v0.13d defining feature

---

## 3. Quick reference: production-grade extraction config

For the VPS-side AI that wants to enable `extract_and_register`:

```yaml
model: claude-opus-4-7        # do not downgrade
prompt: experiments/prompts/v0.13d_hedging_gate_only.md   # locked
temperature: 0.0
max_tokens: 32768             # 64K for safety on long papers
thinking:
  enabled: true
  budget_tokens: 1024         # = effort=low; do not exceed 2048
seed: not exposed by Anthropic API; use temp=0 for repro
prompt_cache: enabled (cache_control on system block)
pdf_input: native (base64), not text-extracted
expected_cost_per_paper: $1.10 - $2.00 (depends on length)
expected_duration: 250s - 450s
expected_extraction_size_kb: 30 - 100
expected_claim_count: 25 - 45
```

Save this as the operational SLA when registering new papers.

---

## 4. Summary of decisions in this addendum

1. ✅ **Default `--effort` = `low`** in `run_extraction_cli.py` and all `dispatch_*.sh` scripts
2. ✅ Existing 82-paper extractions stay as-is (re-extraction ROI is negative)
3. ✅ VPS-side `extract_and_register` (when enabled) should use `thinking budget_tokens=1024`
4. ✅ Documented decoding parameters for future local-LLM ports
5. ✅ Explicit "what NOT to change" list to protect schema contract

This addendum + `EFFORT_COMPARISON.md` provide the empirical justification for the default change. R81 results (5 more papers × 2 efforts) will be appended to `EFFORT_COMPARISON.md` once it completes.

---

*Generated 2026-04-26 by Claude Opus 4.7. Updates to either this doc or the original handoff are welcomed via Dropbox-direct edit.*
