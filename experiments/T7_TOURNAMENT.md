# T7 Prompt Tournament — 9 prompts on "More Data, Worse Models" (21p, synthetic ML trap)

## TL;DR

**No single prompt wins all three axes (coverage ≥ 95%, core_eq_fidelity ≥ 85%, eq_discipline ≥ 80%).**
The tradeoff is inherent: LaTeX instructions consume attention that would otherwise go to RELATIONs.

**Production config: `v0.3 overlooked` + `v0.12e STATUS` parallel dual-run and merge.**

This beats the previously-planned `v0.3 + v0.11` fallback on both equation axes:

| Axis | v0.3 + v0.11 (old plan) | v0.3 + v0.12e STATUS (new) |
|------|------------------------|----------------------------|
| Text coverage | 100% (from v0.3) | 100% (from v0.3) |
| Core eq fidelity | 86.9% (v0.11) | **92.1%** (v0.12e) |
| Eq discipline | 33.3% (v0.11) | **66.7%** (v0.12e) |
| Decorative equations polluted | 2/3 | **1/3** |
| Cost | 2 × $1.2 | 2 × $1.1 |

## Gold (what we're scoring against)

T7 Gold was authored *before* the paper. 20 must-catch claims, 3 must-NOT-synthesize, 7 equations classified:

- `central_contribution`: eq3 (main PAC-Bayes bound), eq5 (crossover condition). These ARE the paper's theorems.
- `supporting_definition`: eq2 (noise model), eq4 (n_eff). Define constructs used by the theorems.
- `restatement`: eq6 (Discussion simplified form of eq5). Should NOT be extracted — extracting it risks future miscitation.
- `textbook_background`: eq1 (textbook scaling law cited from Kaplan 2020), eq7 (Rademacher from Shalev-Shwartz). Not this paper's contribution.

## Five independent axes — no composite

| # | Prompt | Coverage | Middle | Integrity penalty | Core eq fidelity | Eq discipline | All eqs captured | Decorative extracted |
|---|--------|----------|--------|-------------------|------------------|---------------|---------|---------------------|
| 1 | v0.1 baseline         | 92.9% |  89.5% | 0.0% |  0.0% | 100% |  0 | 0/3 |
| 2 | v0.3 overlooked       | **100.0%** | **100.0%** | 0.0% |  0.0% | 100% |  0 | 0/3 |
| 3 | v0.10 combined        | 92.9% |  89.5% | 0.0% |  0.0% | 100% |  0 | 0/3 |
| 4 | v0.11 TeX             | 80.4% |  71.0% | 0.0% | 86.9% |  33% | 12 | 2/3 |
| 5 | v0.12a TERSE          | 96.4% | 100.0% | 0.0% | 82.1% |   0% | 12 | 3/3 |
| 6 | v0.12b TRIAGE         | 78.6% |  68.4% | 0.0% | 91.3% |  33% |  5 | 2/3 |
| 7 | v0.12d ORDER          | 85.7% |  79.0% | 0.0% | 82.1% |  33% | 11 | 2/3 |
| 8 | **v0.12e STATUS**     | 82.1% |  73.7% | 0.0% | **92.1%** | **67%** |  7 | 1/3 |
| 9 | v0.12f DISCIPLINE     | 82.1% |  73.7% | 0.0% | **94.0%** |  33% |  8 | 2/3 |

## By-template coverage

| Prompt | DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM |
|--------|------------|----------|-----------------|------------|
| v0.1 baseline    | 100% |  92% |  75% | 100% |
| v0.3 overlooked  | 100% | **100%** | 100% | 100% |
| v0.10 combined   | 100% |  85% | 100% | 100% |
| v0.11 TeX        | 100% |  58% | 100% | 100% |
| v0.12a TERSE     |  86% | **100%** | 100% | 100% |
| v0.12b TRIAGE    | 100% |  62% |  75% | 100% |
| v0.12d ORDER     | 100% |  69% | 100% | 100% |
| v0.12e STATUS    | 100% |  62% | 100% | 100% |
| v0.12f DISCIPLINE| 100% |  62% | 100% | 100% |

The pattern is consistent: **the more prescriptive the TeX instruction, the more RELATION coverage collapses**. v0.12a TERSE is the one variant that preserves RELATION 100% — because its TeX instruction is minimal — but pays for it by extracting all 3 decorative equations (0% discipline).

## Per-equation fidelity (with status)

| Equation | Status | Weight | v0.1 | v0.3 | v0.10 | v0.11 | v0.12a | v0.12b | v0.12d | v0.12e | v0.12f |
|----------|--------|--------|------|------|-------|-------|--------|--------|--------|--------|--------|
| eq1 intro scaling | textbook_background | 0.5 | 0% | 0% | 0% | 100% | 100% | 67% | 67% | **33%** | 67% |
| eq2 noise model | supporting_definition | 1.0 | 0% | 0% | 0% | 100% | 67% | 67% | 67% | 100% | 100% |
| eq3 main bound | central_contribution | 2.5 | 0% | 0% | 0% | 80% | 80% | 100% | 80% | 100% | 100% |
| eq4 n_eff | supporting_definition | 1.0 | 0% | 0% | 0% | 86% | 86% | 100% | 86% | 100% | 100% |
| eq5 crossover | central_contribution | 2.5 | 0% | 0% | 0% | 89% | 89% | 89% | 89% | 78% | 89% |
| eq6 discussion simplified | restatement | 0.5 | 0% | 0% | 0% | 75% | 100% | 50% | 75% | **50%** | 50% |
| eq7 appendix Rademacher | textbook_background | 1.5 | 0% | 0% | 0% | 29% | 100% | 29% | 29% | **29%** | 29% |

## Interpretation

1. **v0.3 dominates text coverage (100%, 100% middle)** but ignores equations entirely. Solo text champion.

2. **v0.12a TERSE** nearly hit the coverage threshold (96.4%) but captured all 3 decorative equations at full fidelity — worst discipline in the tournament. A short mention of TeX was enough to tell Opus "extract equations" but not enough to tell it "be selective".

3. **v0.12b TRIAGE, v0.12d ORDER, v0.12e STATUS, v0.12f DISCIPLINE** all cluster around 80–85% coverage. RELATION coverage drops to 62–69%. The more LaTeX instruction, the more the model's attention shifts to formal content at the expense of verbal claims in the middle of the paper.

4. **v0.12e STATUS is the one variant that achieves discipline**. By making `equation_status` a mandatory schema field and requiring the model to justify each equation's inclusion, it rejected eq7 (textbook Rademacher), mostly rejected eq1 (intro scaling), and partially rejected eq6 (restatement, scored 50% — i.e., model hedged by capturing loosely). Best eq_discipline (67%) and best core_eq_fidelity (92%).

5. **v0.12f DISCIPLINE** has the highest core_eq (94%) because prose instruction focused the model on central equations, but the model still extracted decorative ones (discipline 33%). Prose instruction is too soft; schema enforcement (v0.12e) is what actually works.

## Cross-validation on real papers

To confirm v0.12e STATUS is safe for production, we ran it on two diverse real papers:

| Paper | Type | v0.12e coverage | v0.12e eqs | v0.3 coverage (baseline) | v0.11 coverage (baseline) |
|-------|------|-----------------|-----------|--------------------------|----------------------------|
| Einstein 1905 Relativity (German scan, heavy-math) | conceptual | **100%** | 21 | 100% | 100% |
| Edmondson 1999 Psychological Safety (hypothesis-heavy, no math) | empirical | **95.0%** | 0 | 100% | 95.0% |

No regression on either extreme. v0.12e extracts 21 equations on Einstein (v0.11 extracted 27; the 6-eq gap is precisely where discipline kicks in — Einstein's paper contains re-statements in later sections, which STATUS correctly filtered).

On Edmondson (no equations), v0.12e scored 95% coverage identical to v0.11 baseline — the discipline language didn't harm hypothesis extraction.

## Integrity — no sanitization in any prompt

Under the `must_not_synthesize` check, **all 9 prompts scored 0% integrity penalty**. No prompt produced:
- "dataset_size → test_accuracy, positive, verified" (the standard scaling-law sanitization)
- "larger models are more noise-robust" (common-sense inversion of R5)
- "bound empirically validated" without divergence qualifier (Discussion sanitization)

Opus 4.7's faithfulness to source is stronger than its priors. The counterintuitive T7 findings (more data hurts; bigger models fail sooner) survived every prompt.

## Production spec

```
For papers with formal content (equations, theorems, algorithms):
  Extract twice, in parallel:
    Pass A: v0.3 overlooked      → defines the claim set (RELATION/DEFINITION/EXISTENCE/META)
    Pass B: v0.12e STATUS        → provides formal field (equations with equation_status)
  Merge: take Pass A's claims as canonical; attach Pass B's equations
         where Pass B provides formal.equations on matching claim IDs.

For papers with no formal content (psychology, social science without derivations):
  Extract once with v0.3.
```

Cost: 2× per math paper, 1× per text paper. Same order as v0.3+v0.11 plan but with better discipline and higher core_eq.

## Tournament cost

- 4 old baselines (v0.1/v0.3/v0.10/v0.11): already in the previous run, reused
- 5 new variants (v0.12a/b/d/e/f): 5 × $1.1 = $5.50
- Cross-validation (Einstein + Edmondson with v0.12e): 2 × $1.0 = $2.00

**Total marginal cost: $7.50** to find and validate the production config.

## Next steps

1. Implement the dual-run merge logic in `packages/citare-extract/`
2. Lock `v0.3_overlooked.md` and `v0.12e_status.md` as production prompts
3. Document the `equation_status` convention in Citare's data model (promote to schema-level field)
4. Single-prompt solution (v0.12g+) could still be explored if the Pareto frontier needs to be broken — likely requires either a chain-of-thought variant that does triage internally, or a finetune, neither of which fits this benchmark's scope
