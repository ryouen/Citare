# Citare Production Champion: v0.13g × effort=none (locked 2026-04-26)

After ~700 extraction runs, $700+ of API spend, 30+ prompt variants, and a final
4-prompt × 3-effort × 6-paper grid (R82, n=72), the canonical extraction config is:

- **Prompt**: `experiments/prompts/v0.13g_thinking_defensive.md`
- **Effort**: `--effort none` (extended thinking disabled — canonical Claude CLI default mode)
- **Model**: `claude-opus-4-7`

Everything below is the rationale. The code defaults already point here.

---

## TL;DR — what changed and why

We previously locked `v0.13d × effort=low` (HANDOFF_REPLY_TO_VPS_2026-04-26_pt2.md).
That decision was based on R80 (n=12) + R81 (n=10) which suggested low > none on average.

R82 (n=72, 4 prompts × 3 efforts × 6 papers) **overturned that conclusion** by surfacing
two findings the smaller experiments missed:

1. **`low` causes thesis-level miss in concert with anti-compression / self-check prompts.**
   `v013g × low` and `v013h × low` each lost 2 thesis-level claims (Hubinger persistence,
   Edmondson H3 mediation). `v013d × low` happened to escape this, but the failure pattern
   is structural and would surface on new papers unpredictably.
2. **`v013g × none` Pareto-dominates the previous champion on every quality axis.**
   Coverage 97.4% vs 93.6%, EXIST claims 16.7 vs 9.2 per paper, zero thesis-level miss,
   and EXIST surplus content on hubinger/park/wei is all genuine boundary scaffolding
   (limitations, ethical risks, methodological notes) — not garbage.

Cost penalty for switching: +$0.18/run (+18%, $1.01 → $1.19). Buys: noyzhang heterogeneity
recovery, Edmondson cross-sectional limitation captured, T7 R1+R2 chain links captured,
+7.5 EXIST claims for the integrity_warning layer.

---

## Performance summary on the 6-paper R82 panel

| Cell | Coverage ± SD | Cost ± SD | Duration ± SD | EXIST claims | Thesis-level losses |
|------|--------------:|----------:|--------------:|-------------:|--------------------:|
| **v013g × none (LOCKED)** | **97.4 ± 4.4%** | $1.19 ± 0.27 | 312 ± 54s | **16.7** | **0** |
| v013d × low (PREVIOUS) | 93.6 ± 8.3% | $1.01 ± 0.34 | 233 ± 51s | 9.2 | 0 |
| v013g × low | 88.0 ± 10.1% | $1.03 ± 0.28 | 251 ± 67s | 11.8 | **2** ← Hubinger thesis, Edmondson H3 |
| v013h × low | 92.9 ± 7.8% | $1.01 ± 0.22 | 241 ± 46s | 14.2 | **2** ← same pattern |
| v013f × none | 96.8 ± 5.8% | $1.32 ± 0.41 | 328 ± 82s | 16.5 | 0 |
| v013h × none | 92.9 ± 13.2% | $1.22 ± 0.40 | 310 ± 77s | 15.6 | 1 ← T7 R5 |
| v013d × none | 90.0 ± 9.4% | $1.16 ± 0.30 | 301 ± 83s | 12.8 | 1 ← Wei CoT |

Per-paper coverage for v013g × none: noyzhang 100%, hubinger 100%, park 100%,
edmondson 95%, wei 100%, t7 89%. Two missed items both from t7 (R6/R7 trap-class
items that none of the tested prompts captured — LLM limitation, not effort/prompt).

---

## What v0.13g changes vs v0.13d

`v0.13g_thinking_defensive.md` is `v0.13d_hedging_gate_only.md` plus one additional
section in EXISTENCE_CLAIM guidance:

```
**Anti-compression rule for extended thinking (critical — read carefully):**

If you are reasoning with an extended thinking budget, your thinking process may
suggest "consolidating" or "deduplicating" findings to produce a more concise
output. Reject these suggestions for EXISTENCE_CLAIM. Specifically:

- If thinking proposes "this can be folded into META_CLAIM" → keep as EXISTENCE_CLAIM
- If thinking proposes "these three findings are aspects of the same phenomenon" → emit all three
- If thinking proposes "the abstract already implies this" → emit the limitation as its own EXISTENCE_CLAIM
- If thinking proposes "this null result is uninteresting" → emit it (null results are integrity-critical)
- Bias toward over-extraction. A redundant EXISTENCE_CLAIM costs nothing downstream;
  a missed boundary condition or null finding silently breaks citation safety.
```

**Why this works at effort=none even though it's about thinking:** the rule also
acts as a general "do not compress" instruction in the model's normal reasoning,
without the actual thinking-token consumption that triggers the noyzhang regression
when paired with `low/medium`.

**Why this fails at effort=low:** when extended thinking is active, the model
*does* try to compress, and the rule isn't always sufficient to prevent the loss
of 1-2 thesis-level claims (Sleeper persistence, H3 mediation). Hence the
combination `v013g × none` rather than `v013g × low`.

---

## Why none > low (the headline finding)

Earlier reports (HANDOFF pt2) recommended low based on R80+R81 averaging, which had
small n and didn't decompose by claim severity. R82 with severity-tagged scoring
showed:

| Effort axis | Thesis-level losses across 4 prompts × 6 papers |
|-------------|--:|
| **none** | **2** (1 in v013d wei, 1 in v013h t7) |
| low | **4** (Hubinger × 2, Edmondson H3 × 2) |
| medium | (mixed, also 2-3) |

Low thinking budgets cause the model to compress EXIST_CLAIMs as if they were
duplicates of nearby RELATIONs. That compression occasionally elides claims that
ARE the paper's thesis. Effort=none, paradoxically, is more faithful to the
prompt's "list everything" instructions because there is no thinking-stage
optimization pass running on top.

---

## Cost & ops envelope

For 1000-paper extraction at v013g × none:

- Total cost: ~$1,190
- Total time at 15-parallel sliding window: ~3.5 hours
- Total tokens: ~210K input + cache + ~25K output per paper
- Total claims emitted: ~38,000 (avg 38/paper)
- Total EXIST claims (the integrity scaffolding): ~16,700

Compare v013d × low for same 1000 papers: ~$1,010, ~28,000 claims, ~9,200 EXIST.
The +$180 buys +10K total claims and +7,500 EXIST.

---

## Files committed for this decision

- `experiments/prompts/v0.13g_thinking_defensive.md` — locked production prompt
- `experiments/R82_GRID_RESULTS.md` — full 72-run grid data
- `experiments/EFFORT_COMPARISON.md` — original R80/R81 narrative (now superseded by R82)
- `experiments/runs/*_R82_v013g_*_effnone_s1/` — 6 raw winning runs
- `experiments/harness/run_extraction_cli.py` — default `--effort none`
- `experiments/harness/dispatch_*.sh` — production dispatchers updated to v0.13g + none
- `docs/HANDOFF_REPLY_TO_VPS_2026-04-26_pt3.md` — the corrigendum to pt2 sent to VPS

---

## Production lock decision

**No further prompt or effort tuning is justified at this point.**
- v013g × none has zero thesis-level miss across 6 papers
- Subsequent improvements (v013f, v013h) showed lower mean coverage AND introduced
  thesis-level loss when paired with low — instability is worse than current ceiling
- The 3 papers where v013g × none doesn't reach 100% (edmondson 95%, t7 89%) miss
  S/T-class items (null results, trap-softening) that no tested combination caught

Future work should target:
- Real-corpus expansion (ZENTech psych safety library, additional cogsci batches)
- Sub-agent paper-class router (RCT vs computational vs theoretical) if quality
  varies enough on a domain we haven't yet tested
- L2 natural-language label population (would unlock semantic FTS5 search)

## Reference

- Strategic findings: `experiments/STRATEGIC_FINDINGS.md`
- Cross-variant data: `experiments/WEIGHTED_ALL_VARIANTS_v3.md`
- Seed variance: `experiments/SEED_VARIANCE.md`
- R82 grid: `experiments/R82_GRID_RESULTS.md`
- Original effort tuning report: `experiments/EFFORT_COMPARISON.md` (now superseded)
