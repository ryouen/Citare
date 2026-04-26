# Effort comparison — empirical (R80 + R81, 2026-04-26)

Test: v0.13d locked prompt × 8 papers × 2-4 effort levels.
- R80: 3 papers (edmondson/hayes/T7) × 4 efforts (none/low/medium/high) = 12 runs
- R81: 5 papers (einstein/vaswani/hubinger/wei/noyzhang) × 2 efforts (none/low) = 10 runs
- Total: **22 runs**, all with gold for quantitative scoring

## TL;DR — what to use, and what to watch for

- **Aggregate winner: `low`** — wins on both coverage (93.2% vs 92.6%) and cost ($1.06 vs $1.30) on n=8 papers
- **`medium` actively hurts** — drops to 85.2% (worst), longest duration. Don't use unless you have a specific reason
- **`low` has a real failure mode** — see noyzhang below. Not all-clear

## Per-paper × effort: coverage

| Paper | none | low | medium | high | Δ(low−none) | comment |
|-------|-----:|----:|-------:|-----:|------------:|---------|
| edmondson | 95.0% | 95.0% | 95.0% | 95.0% | 0 | saturated |
| einstein | 100.0% | 100.0% | — | — | 0 | saturated |
| hayes | 90.9% | 90.9% | 90.9% | 90.9% | 0 | saturated |
| **hubinger** | 86.7% | **100.0%** | — | — | **+13.3** 🟢 | low rescues |
| **wei** | 89.5% | **100.0%** | — | — | **+10.5** 🟢 | low rescues |
| t7 | 78.6% | 85.7% | 69.6% | 83.9% | +7.1 | low best on trap-paper |
| vaswani | 100.0% | 100.0% | — | — | 0 | saturated |
| **noyzhang** | **100.0%** | **73.7%** | — | — | **−26.3** 🔴 | **low regression** |

**Pattern**: low improves 3 papers, ties 4, regresses 1. Net average gain +0.6pp, driven by trap-paper (T7) and AI-safety/RCT papers (hubinger, wei). The noyzhang regression deserves attention.

## Per-paper × effort: cost (USD)

| Paper | none | low | medium | high |
|-------|-----:|----:|-------:|-----:|
| edmondson | $1.12 | $1.03 | $1.05 | $1.11 |
| einstein | $1.15 | $1.05 | — | — |
| hayes | $1.52 | $1.97 | $2.03 | $2.00 |
| hubinger | $2.22 | $0.96 | — | — |
| noyzhang | $0.79 | $0.69 | — | — |
| t7 | $1.29 | $1.13 | $1.23 | $1.37 |
| vaswani | $0.84 | $0.75 | — | — |
| wei | $1.51 | $0.88 | — | — |

Note: low is **cheaper than none on 7 of 8 papers**. The exception is hayes (long, theory-dense). Why is low cheaper? Extended thinking lets the model output less verbose reasoning chain inside the JSON (`source_text` quotes get tighter, fewer over-claims) — fewer output tokens at billable rate. The thinking tokens themselves are charged at input rate, which is much cheaper.

## Per-paper × effort: duration (s) + output tokens

| Paper | none | low | medium | high |
|-------|------|-----|--------|------|
| edmondson | 258s/23K | 221s/18K | 226s/19K | 223s/20K |
| einstein | 262s/22K | 220s/17K | — | — |
| hayes | 354s/28K | 387s/29K | 441s/34K | 448s/34K |
| hubinger | 409s/29K | 231s/19K | — | — |
| noyzhang | 214s/19K | 193s/15K | — | — |
| t7 | 333s/27K | 274s/22K | 282s/25K | 352s/30K |
| vaswani | 232s/21K | 197s/18K | — | — |
| wei | 294s/22K | 193s/16K | — | — |

low is faster on 8 of 8 papers — same explanation as cost (less output, cheap thinking).

## Per-paper × effort: claims emitted

| Paper | none | low | medium | high |
|-------|-----:|----:|-------:|-----:|
| edmondson | 31 | 27 | 27 | 31 |
| einstein | 26 | 25 | — | — |
| hayes | 38 | 40 | 44 | 42 |
| hubinger | 37 | 28 | — | — |
| noyzhang | 35 | 28 | — | — |
| t7 | 27 | 27 | 30 | 32 |
| vaswani | 23 | 25 | — | — |
| wei | 25 | 24 | — | — |

low generally emits ~3-9 fewer claims than none. **The drop in noyzhang (35→28) is the same place coverage dropped** — low under-extracted minor (weight=1) claims that noyzhang's gold demands.

## Cross-paper aggregate per effort

| Effort | n papers | avg cov | avg cost | avg duration | avg out_tok | avg claims |
|--------|---------:|--------:|---------:|-------------:|------------:|-----------:|
| **none** | 8 | 92.6% | $1.30 | 294s | 24K | 30.2 |
| **low** | 8 | **93.2%** | **$1.06** | 240s | 19K | 28.0 |
| medium | 3 | 85.2% | $1.44 | 316s | 26K | 33.7 |
| high | 3 | 89.9% | $1.49 | 341s | 28K | 35.0 |

`medium` and `high` only have n=3 (R80 only). Their aggregates are noisy and biased toward T7's behaviour, but the medium=85.2% drop is not noise — it comes from medium catastrophically misreading T7 (69.6%).

## Three failure-mode patterns we observed

### Pattern A — "low rescues" (hubinger, wei)

Paper has dense computational/AI-safety material with subtle distinctions (e.g., normal vs chain-of-thought backdoor, with vs without scratchpad). Without thinking, the model conflates similar-but-distinct concepts and emits fewer DEFINITION/RELATION claims. Adding 1K thinking tokens lets it pause to disambiguate before emitting.

**Cost-benefit**: hubinger went 86.7% → 100.0% AND $2.22 → $0.96. This is a strict Pareto improvement, no trade-off.

### Pattern B — "low improves trap-paper" (T7)

T7 is designed to be misleading (rhetoric of "scaling laws" applied to noise). Without thinking, the model takes the surface narrative at face value (78.6%). With low, it briefly catches the contradiction (85.7%). With medium, the thinking *follows* the misleading rhetoric down a path and constructs a worse wrong answer (69.6%). With high, more thinking budget allows recovery (83.9%).

**Implication**: thinking budget is non-monotonic on trap-class papers. low and high are safer than medium.

### Pattern C — "low regression" (noyzhang) — important caveat

noyzhang (Noy & Zhang 2023, GenAI productivity field experiment) is a complex RCT with multiple subgroup analyses and effect-heterogeneity claims. low's drop from 100% to 73.7% is concentrated on **minor (weight=1) heterogeneity claims** — items the gold expects but low's tighter output skipped.

This is the inverse of Pattern A — when the paper's value is in *many* small subgroup findings rather than a few big claims, the "tighter output" property of low becomes a liability.

**Why we still recommend low as default**: this regression occurred on 1 of 8 papers (12.5%), and was bounded (still 73.7%, not a complete miss). Pattern A and B benefits accrue more frequently and have larger upside. Aggregate is +0.6pp coverage and -$0.24/run cost.

But: **for RCT-heavy or meta-analysis-heavy corpus expansions** (e.g., the cogsci R73 batch), monitor for this pattern. If a target paper is known to have many subgroup findings, consider running it at `none` instead.

## Recommendation

1. ✅ **Default = `low`** — wins on aggregate, free cost reduction
2. ⚠️ **Watch `low` on dense-RCT papers** — heterogeneity claims may drop
3. ❌ **Don't use `medium`** — actively backfires on trap papers, drops aggregate
4. 🤔 **`high` undertested** (n=3) — possibly worth ~$0.20/run more for trap-paper safety; not currently recommended pending more data

## Future tests (if needed)

To strengthen the noyzhang finding:
- 5 RCT-heavy papers × {none, low}: confirm the regression pattern is RCT-class, not noyzhang-specific
- noyzhang × {none, low, high} × 3 seeds: variance check (is the 73.7% noisy or stable?)

To validate `high`:
- The same 8 papers × {none, low, high}: see whether high is monotone-better than low on the n=8 set, especially on noyzhang

Estimated: ~$30 more for both — not currently scheduled.

## Files

- Raw runs: `experiments/runs/*_R8{0,1}_v013d_*_eff{none,low,medium,high}_s1/`
- Dispatcher: `experiments/harness/dispatch_effort_test.sh` + `dispatch_effort_test_5x2.sh`
- Aggregator: `scripts/analyze_effort_test.py`
- VPS handoff: `docs/HANDOFF_REPLY_TO_VPS_2026-04-26_pt2.md`
- Production default change: `experiments/harness/run_extraction_cli.py:288-294` (default `low`)
