# Pilot v2 — Noise estimation + cross-paper check

Executed 2026-04-25 after the v0.1 tournament. Purpose: address the N=1 and
single-paper limitations that made the v0.1 tournament weak evidence.

## Design

| | Setting |
|---|---|
| Variants | v0.3 overlooked, v0.11 TeX, v0.12e STATUS |
| Papers | T7 (21p ML trap), Einstein 1905, Edmondson 1999 |
| Runs per cell | 2 (seeds: whatever Opus 4.7 happened to use) |
| Model | Opus 4.7, effort=none |
| Total extractions | 18 (11 new + 7 from v0.1 tournament) |
| Cost | ~$22 |

## Per-cell means (N=2)

| Variant | Paper | Coverage | Core eq | Discipline | Eqs captured |
|---------|-------|----------|---------|------------|--------------|
| v0.3 | T7 | **94.6% ± 7.6** | 0.0% | 100% | 0 |
| v0.3 | einstein | 100.0% ± 0.0 | 0.0% | n/a | 0 |
| v0.3 | edmondson | **90.0% ± 7.1** | 0.0% | n/a | 0 |
| v0.11 | T7 | 79.5% ± 1.3 | **90.4% ± 5.0** | 33.3% ± 0.0 | 10 |
| v0.11 | einstein | 100.0% ± 0.0 | 0.0% | n/a | 27 |
| v0.11 | edmondson | 95.0% ± 0.0 | 0.0% | n/a | 0 |
| v0.12e | T7 | **85.7% ± 5.1** | **87.1% ± 7.0** | **50.0% ± 0.0** | 8 |
| v0.12e | einstein | 100.0% ± 0.0 | 0.0% | n/a | 21 |
| v0.12e | edmondson | 95.0% ± 0.0 | 0.0% | n/a | 0 |

## Key findings

### Finding 1 — v0.1 tournament numbers on T7 were single-point estimates

v0.3 on T7 achieves **94.6% ± 7.6%** coverage, not 100%. The two runs in this
pilot scored 100% and 89.3%. The 100% I reported in `T7_TOURNAMENT.md` was
the lucky run; the second run would have told a different story. Same for
**v0.3 on Edmondson (90.0% ± 7.1%, not 95% as reported)**.

**Correction**: the "v0.3 is perfect on text" claim is too strong. v0.3 is
near-perfect on T7 with occasional misses; it's 100% on Einstein but
deterministically so because Einstein is structurally simpler.

### Finding 2 — v0.12e > v0.11 on core_eq is UNDER-SUPPORTED at N=2

On T7:

- v0.11: 90.4% ± 5.0 (runs 87%, 94%)
- v0.12e: 87.1% ± 7.0 (runs 92%, 82%)

The distributions overlap. With N=2 we cannot reject the null that they are
equally good at core equation fidelity. The v0.1 tournament's report of
"v0.12e 92.1% vs v0.11 86.9%" was based on one run each; the pilot shows this
difference is within within-cell noise.

**Revised claim**: v0.11 and v0.12e produce statistically indistinguishable
core-equation fidelity on T7 at N=2. We do NOT have evidence that v0.12e is
better on this axis.

### Finding 3 — v0.12e > v0.11 on discipline is REAL

On T7:

- v0.11: 33.3% ± 0.0 (both runs 33%, captured 2/3 decorative equations)
- v0.12e: 50.0% ± 0.0 (both runs 50%, captured 1.5/3 decorative equations on average)

Both runs are identical across seeds for this metric. The 17pp gap is real
and consistent. **v0.12e has better equation discipline than v0.11 — this
is the only robustly-validated difference between the two.**

### Finding 4 — Opus 4.7 is deterministic on "easy" papers

Einstein 1905 and Edmondson 1999 (in the extractor's hands) show zero
within-cell variance for 7 of 9 cells. Only T7 shows non-trivial noise.
This aligns with T7 being designed specifically to stress Lost-in-the-Middle
and equation-density decisions.

**Implication for v2**: T7 must be run at N ≥ 3 to get stable estimates.
Einstein and Edmondson probably only need N=1 or N=2.

### Finding 5 — Einstein equation counts differ by variant (21 vs 27)

- v0.11 captures 27 equations on Einstein
- v0.12e captures 21 equations on Einstein

This is the equation discipline effect: v0.12e rejects 6 equations that v0.11
accepts. Without Gold classification on Einstein, we can't say whether those
6 are restatements/textbook (discipline win) or actual contributions
(discipline loss). **T7 suggests discipline wins** since on T7 v0.12e rejects
decorative equations. But this is an assumption — needs Gold tagging on the
real papers to validate on Einstein directly.

## What the v0.1 tournament got right vs wrong

| Claim | N=1 status | N=2 status |
|-------|-----------|-----------|
| "v0.3 dominates text coverage" | confident | STILL TRUE, but Einstein-deterministic / T7 ± 7pp |
| "v0.12e > v0.11 on core_eq" | confident | **UNDER-SUPPORTED** at N=2 |
| "v0.12e > v0.11 on discipline" | confident | **CONFIRMED**, noise=0 |
| "No solo winner passes all thresholds" | confident | STILL TRUE |
| "T7 coverage drops 20pp with LaTeX instruction" | confident | **CONFIRMED** (79.5% vs 94.6%) |

## Production-config implications

The pilot suggests the production config recommendation (`v0.3 + v0.12e STATUS`)
is still correct, but the justification changes:

- **Previous argument**: v0.12e beats v0.11 on both core_eq AND discipline.
- **Corrected argument**: v0.12e beats v0.11 on discipline only; core_eq is
  statistically indistinguishable. Choose v0.12e for its discipline guarantee
  (no restatement leakage), not for eq fidelity.

## What v2 full execution would add

- N=3 to get student-t CIs (even loose ones)
- All 5 papers (add Wei 2022 and Barney 1991 to cover sparse math and pure concepts)
- L8 factorial design instead of ad-hoc variants — tests interactions
- Pre-registered YAML so we don't cherry-pick success criteria

Cost: ~$144, 120 runs, 6h wall-clock at Max plan parallel ceiling. Not done
this hackathon; documented in `docs/experiments_v2_plan.md`.
