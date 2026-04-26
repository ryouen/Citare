# Strategic Findings — Cross-Variant Re-analysis

> ⚠️ **Audit-trail document.** Written 2026-04-25 when v0.13d was the production candidate.
> This analysis correctly identified v0.13d as the winner of the cross-variant tournament at the time.
> A subsequent **R82 grid (n=72, 2026-04-26)** then introduced and tested v0.13f/g/h prompt-level interventions and found that **v0.13g × effort=none is the true production champion**, superseding v0.13d.
> See `experiments/PRODUCTION_CHAMPION.md` and `experiments/R82_GRID_RESULTS.md` for the current lock decision. This doc preserved unchanged for audit trail.

---

Date: 2026-04-25 (post-Stage C, 550 successful runs, $583.08 total spend, 43.1 hours of cumulative API time)

This consolidates the all-variant weighted-coverage re-analysis (`analyze_weighted_coverage_v2.py`),
seed-variance audit, statistical significance test, Pareto frontier, and per-paper drilldowns.

---

## 1. Consolidated cross-paper summary (Papers ≥ 11)

Sorted by Cov(core). Variants on smaller panels (v0.02, v0.04, v0.10–0.15, v0.18, v0.20) are useful
for diagnostics but excluded from the production-champion comparison since the panels differ.

| Variant | Papers | Runs | Cov(core) | Cov(minor) | Cost | Tokens | Seed std | Notes |
|---------|-------:|-----:|----------:|-----------:|-----:|-------:|---------:|-------|
| v0.16b (eq-cap-5) | 13 | 49 | **98.8%** | 93.0% | $1.02 | 188K | **2.91pp** | wins T7 (+13pp), unstable on wei (std 20pp) |
| v0.13d (hedging-gate) | 13 | 39 | **98.5%** | 94.4% | $1.12 | 225K | **0.00pp** | perfectly reproducible, best minor on broad panel |
| v0.13 (bare baseline) | 13 | 65 | 98.4% | 92.5% | $1.10 | 198K | 0.93pp | the actual baseline, was hidden inside v0.12e bucket |
| v0.03 | 12 | 25 | 98.2% | 95.3% | $1.03 | 186K | — | best minor (95.3%), missing 1 paper |
| v0.16d (skeleton inv.) | 13 | 39 | 97.6% | 92.2% | $0.98 | 177K | — | cheapest tokens of the broad panel |
| v0.16e (forbidden-eq) | 13 | 37 | 95.1% | 95.7% | $1.10 | 202K | 5.25pp | best minor of broad panel, but core collapsed |
| v0.16c (purpose-first) | 13 | 37 | 94.2% | 91.0% | $1.04 | 185K | — | underperforms |

**Note on v3.x prompt family** (separate from v0.x and now correctly labeled in `WEIGHTED_ALL_VARIANTS_v3.md`):
- v3.8 hypothesis-aware (= v0.8): 100% core on 11 papers, 12 runs at $0.96/run. Body byte-identical to
  `v0.8_hypothesis_aware.md`; the title differs only. The "100% core" claim is robust across all 12 runs but
  most papers have N=1, and Edmondson's N=4 already shows minor variance (0.90-1.00). Worth re-testing as
  N=3 × 13 papers (~$37) if the hypothesis-aware approach is to be a candidate champion in a future round.
- v3.9 adaptive hypothesis coverage: 100% core on 6 papers, 6 runs at $1.00/run. Same caveats.
- These v3.x prompts predate the v0.x re-numbering and live with `_v3<digit>_` directory tokens; they are NOT
  comparable to the v0.x panel without further testing.
- v0.12e (real, 23 runs) was correctly separated from v0.13 in the v2 analysis.

**Bug fixed (2026-04-25)**: `analyze_weighted_coverage_v2.py` rule 6 was blindly prepending `v0.` to any
`_v\d+_` token, mislabeling v3.x as v0.3x. Patched to detect `_v3<digit>(letters)?_` → `v3.<digit>` first
(also handles `_v35terse_`, `_v36fewshot_`). Re-run output is at `experiments/WEIGHTED_ALL_VARIANTS_v3.md`.

---

## 2. Statistical reality check

Wilcoxon signed-rank, paired by paper (n=13), 1000-bootstrap 95% CI:

| Pair | Δ core | 95% CI | p | Δ minor | 95% CI | p |
|------|-------:|--------|---|--------:|--------|---|
| v0.16b − v0.13d | +0.38pp | [-1.92, +2.44] | 1.00 | -1.42pp | [-4.93, +0.97] | 0.63 |
| v0.16b − v0.13   | +0.48pp | [-1.92, +2.71] | 1.00 | +0.50pp | [-1.53, +2.99] | 0.63 |
| v0.13d − v0.13   | +0.09pp | [+0.00, +0.27] | 1.00 | +1.93pp | [-1.70, +6.38] | 0.58 |

**No pair is significant at α=0.05.** Treat the top three (v0.16b, v0.13d, v0.13) as **coverage-tied**.
Differentiation must come from cost, stability, or non-coverage axes.

---

## 3. Where the variants actually differ

**T7** is the only paper with a meaningful core gap: v0.16b 93% vs v0.13d 80%. Across the other 12 papers,
all three variants tie at 100% core. So the "v0.16b > v0.13d" mean is driven entirely by T7 + wei swings.

**wei** is unstable for v0.16b: 6 seeds, mean 91.7%, std 20.4pp, range 50–100%. v0.13d holds 100% perfectly.

**noyzhang minor**: v0.16b drops 20pp on `exist_effect_heterogeneity` consistently (3/3 seeds). v0.13d catches it 2/3.
This is the one item where the hedging gate clearly helps.

**turing minor / T7 minor**: v0.16b drops single weight-1 items (`lady_lovelace_objection`, `dataset_size_to_tail_coverage`)
that are NOT hedging-shaped. A hedging-gate addition would not recover these.

---

## 4. Pareto frontier (Papers ≥ 11)

**Frontier A — Cov(core) vs cost**:
- v0.38 (100% / $0.96) — but N=1 per paper, fragile
- v0.16d (97.6% / $0.98) — token-cheapest broad-panel
- v0.16b (98.8% / $1.02) — formally dominated by v0.38 if N=1 100% is real, otherwise frontier-leading

**Frontier B — (core+minor)/2 vs tokens**:
- v0.16d (94.9% / 177K) — token-cheapest
- v0.03 (96.75% / 186K) — best balanced

**Strictly dominated**: v0.13d (by v0.03 if 1 paper missing acceptable), v0.16e, v0.16c.

But: stability is a third axis the Pareto chart ignores. **v0.13d's 0.00pp std is unmatched.**

---

## 5. Was v0.13 the right base for divergent micro-tuning?

**Short answer: yes, v0.13 was the right base — but only if the divergence is _minimal additive_.**

### The data

- v0.13 (bare): 98.4% core / 92.5% minor / 0.93pp std / $1.10
- **v0.13d (+ hedging gate only)**: 98.5% / 94.4% / **0.00pp std** / $1.12 — strict Pareto improvement on minor + stability
- v0.13a/b/c (+ paper-class default + skeleton + verification rules): 95.0% / 86.9% / unstable / $1.25 — degraded
- v0.16b (+ eq-cap, "v0.13 + cap-5"): 98.8% / 93.0% / 2.91pp std / $1.02 — same coverage means, lower cost, but worse stability

### Two divergent tactics tested

**v0.13d's tactic** (port one orthogonal rule into v0.13's body): worked — gained +1.9pp on minor coverage, drove
seed std-dev to 0.00pp, kept cost flat. **The hedging-gate is the one v0.13-derived addition worth keeping.**

**v0.16b's tactic** (port a different orthogonal rule into v0.13's body): worked on cost (saved $0.10/run, 17% fewer
tokens) but introduced instability. The eq-cap turns out NOT to be free — it creates lottery dynamics on T7 and
wei where the model occasionally cracks the paper and occasionally collapses.

**v0.13a/b/c** (port multiple structural rules at once): failed. Three of the four micro-tunes I built degraded
core to 95% — exactly the over-engineering risk the "minimal additive" principle exists to avoid.

### Was a different base better?

**v0.16b as a base**: Plausible alternative. v0.16b-hg (combining eq-cap + hedging-gate) is the only experiment
that could potentially Pareto-dominate v0.13d. But the hypothesis test on the per-paper drilldown shows that
2 of the 3 v0.16b minor losses (turing's `lady_lovelace_objection`, T7's `dataset_size→tail_coverage`) are
NOT hedging-shaped, so v0.16b-hg won't fully close the gap. And v0.16b's own instability on wei is unrelated
to hedging.

**v0.03 as a base**: Untested as a divergence base. v0.03 has the best minor coverage (95.3%) on the broad
panel, but only 12 papers. Worth investigating if the next round of micro-tunes is to be done.

### Verdict on the original question

> 細部の異なる Divergent を本当はつくるべきだったヴァージョンは v0.13 なのか、そうではないのかについて

**Answer: v0.13 WAS the right base — but only for ONE direction (the hedging-gate that became v0.13d).**

Three lines of evidence:

1. **v0.13d (hedging-gate only)** is the production champion: 98.5% core / 94.4% minor, **0.00pp seed std-dev
   across all 13 papers** (perfect reproducibility), $1.12/run. The directional improvement over v0.13 bare
   (98.4% / 92.5%) is small in mean but materially better on stability and minor coverage.

2. **v0.13a/b/c failed**: by piling 2-3 structural rules into single forks, all three degraded core to 95%.
   The right framework was minimal additive divergence (one rule per fork), which v0.13d demonstrated.

3. **v0.16b's eq-cap was NOT a missed opportunity for v0.13**: The post-hoc test (v0.16b-hg = eq-cap +
   hedging-gate) regressed on every paper tested. The eq-cap idea works WITHIN v0.16b's prompt structure but
   cannot be cleanly merged with v0.13d's hedging gate — they compete for attention budget. So the v0.13/v0.16
   split was actually **inevitable**, not a missed integration.

**What I'd do differently**: not "diverge from v0.16b instead of v0.13", but "limit each v0.13 fork to ONE
rule" (which I violated with v0.13a/b/c). The v0.13d branch alone followed this discipline and won.

---

## 6. Recommendation: production champion

**For maximum safety/reproducibility (knowledge-graph use case)**: **v0.13d**.
- 0.00pp seed std-dev across all 13 papers
- 98.5% core / 94.4% minor (broad-panel best on minor of any reproducible variant)
- $1.12/run, 225K tokens

**For maximum cost-efficiency (when seed-stability is acceptable)**: **v0.16b**.
- 98.8% core / 93.0% minor mean
- $1.02/run, 188K tokens (-9% cost, -17% tokens vs v0.13d)
- BUT 2.91pp std-dev, with 20pp std-dev specifically on wei

**For best coverage on minor**: **v0.03** (95.3%, but 12 papers only) — investigate filling the 1-paper gap.

**Tested and rejected**: **v0.16b-hg** (= v0.16b + hedging gate). 9 runs at $9.25 on T7+wei+noyzhang × 3 seeds.

| Paper | v0.16b core | v0.13d core | **v0.16b-hg core** | v0.16b minor | v0.13d minor | **v0.16b-hg minor** |
|---|---:|---:|---:|---:|---:|---:|
| T7 | 93% | 80% | **80%** | 88% | 88% | **79%** |
| wei | 92% | 100% | **83%** | 97% | 93% | **93%** |
| noyzhang | 100% | 100% | **100%** | 73% | 93% | **73%** |

The hedging-gate addition did NOT recover `exist_effect_heterogeneity` on noyzhang (0/3 seeds) and regressed
T7 core by 13pp and wei core by 9-17pp. The hedging rules interact badly with v0.16b's eq-cap-driven attention
budget. Hypothesis falsified — eq-cap and hedging-gate are NOT cleanly orthogonal. The mechanism is plausibly
that the hedging-gate's verbosity (12 lines on verification_status) competes for the same attention budget the
eq-cap was meant to free up, so the model under-extracts on T7's central content and wei's relations.

**Implication**: v0.13d remains the production champion. The eq-cap idea from v0.16b cannot be cleanly merged
into v0.13d's structure either — it would face the same attention-budget conflict against the hedging gate.
The two prompt families (v0.13/d and v0.16b) genuinely have different optima.

---

## 7. What I'd do differently in retrospect

1. **Always confirm prompt-file titles match the version in the filename** before running batches. The
   v0.13 → v0.12e mis-titling caused two weeks of merged-bucket analysis until the v2 fix.
2. **Limit each fork to ONE additive rule.** v0.13d (hedging-gate only) succeeded; v0.13b (gate + paper-class
   default) failed; v0.13a (override→always-emit + title fix) was ambiguous. Single-knob ablations are the only
   way to attribute performance.
3. **Track seed std-dev as a first-class axis** alongside coverage, integrity, cost. Stability is more valuable
   than a 0.3pp coverage uplift in production.
4. **Cross-pollinate idea-stems**, don't let v0.13 and v0.16 evolve as separate trees. The eq-cap (v0.16) and
   hedging-gate (v0.13) are orthogonal and should have been combined two weeks earlier as v0.16b-hg or v0.13f.
