# T7 Tournament — 8 prompts × 1 paper (More Data, Worse Models, 21p)

## Five independent axes — no composite

| # | Prompt | Coverage | Middle | Integrity penalty | Core eq fidelity | Eq discipline | All eqs | Decorative extracted |
|---|--------|----------|--------|-------------------|------------------|---------------|---------|---------------------|
| 1 | v0.1 baseline | 92.9% | 89.5% | 0.0% | 0.0% | 100% | 0 | 0/3 |
| 2 | v0.3 overlooked | 100.0% | 100.0% | 0.0% | 0.0% | 100% | 0 | 0/3 |
| 3 | v0.10 combined | 92.9% | 89.5% | 0.0% | 0.0% | 100% | 0 | 0/3 |
| 4 | v0.11 TeX | 80.4% | 71.0% | 0.0% | 86.9% | 33% | 12 | 2/3 |
| 5 | v0.12a TERSE | 96.4% | 100.0% | 0.0% | 82.1% | 0% | 12 | 3/3 |
| 6 | v0.12b TRIAGE | 78.6% | 68.4% | 0.0% | 91.3% | 33% | 5 | 2/3 |
| 7 | v0.12d ORDER | 85.7% | 79.0% | 0.0% | 82.1% | 33% | 11 | 2/3 |
| 8 | v0.12e STATUS | 82.1% | 73.7% | 0.0% | 92.1% | 67% | 7 | 1/3 |
| 9 | v0.12f DISCIPLINE | 82.1% | 73.7% | 0.0% | 94.0% | 33% | 8 | 2/3 |
| 10 | v0.12g TOP-PRIME | 78.6% | 68.4% | 0.0% | 90.0% | 33% | 17 | 2/3 |

## Winner check (coverage>=95 AND core_eq>=85 AND discipline>=80)

No variant passes all three thresholds. Fallback: v0.3 + v0.11 parallel dual-run.

## By-template coverage

| Prompt | DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM |
|--------|------------|----------|-----------------|------------|
| v0.1 baseline | 100% | 92% | 75% | 100% |
| v0.3 overlooked | 100% | 100% | 100% | 100% |
| v0.10 combined | 100% | 85% | 100% | 100% |
| v0.11 TeX | 100% | 58% | 100% | 100% |
| v0.12a TERSE | 86% | 100% | 100% | 100% |
| v0.12b TRIAGE | 100% | 62% | 75% | 100% |
| v0.12d ORDER | 100% | 69% | 100% | 100% |
| v0.12e STATUS | 100% | 62% | 100% | 100% |
| v0.12f DISCIPLINE | 100% | 62% | 100% | 100% |
| v0.12g TOP-PRIME | 100% | 62% | 75% | 100% |

## Per-equation fidelity (with status)

| Equation | Status | Weight | v0.1 baseline | v0.3 overlooked | v0.10 combined | v0.11 TeX | v0.12a TERSE | v0.12b TRIAGE | v0.12d ORDER | v0.12e STATUS | v0.12f DISCIPLINE | v0.12g TOP-PRIME |
|----------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| eq1_intro_scaling | textbook_background | 0.5 | 0% | 0% | 0% | 100% | 100% | 67% | 67% | 33% | 67% | 67% |
| eq2_noise_model | supporting_definition | 1.0 | 0% | 0% | 0% | 100% | 67% | 67% | 67% | 100% | 100% | 100% |
| eq3_main_bound | central_contribution | 2.5 | 0% | 0% | 0% | 80% | 80% | 100% | 80% | 100% | 100% | 100% |
| eq4_n_eff | supporting_definition | 1.0 | 0% | 0% | 0% | 86% | 86% | 100% | 86% | 100% | 86% | 86% |
| eq5_crossover_condition | central_contribution | 2.5 | 0% | 0% | 0% | 89% | 89% | 89% | 89% | 78% | 89% | 78% |
| eq6_discussion_simplified | restatement | 0.5 | 0% | 0% | 0% | 75% | 100% | 50% | 75% | 50% | 75% | 100% |
| eq7_appendix_rademacher | textbook_background | 1.5 | 0% | 0% | 0% | 29% | 100% | 29% | 29% | 29% | 29% | 29% |

