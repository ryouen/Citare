# Seed-to-seed variance analysis: top broad-panel variants

Variants analyzed: v0.16b, v0.13d, v0.13 (bare), v0.12e, v0.16e
Metric: std-dev of `cov_core` across seeds within each (variant, paper) cell.
Threshold for 'HIGH variance' (noisy): std-dev > 0.10

## Per-cell std-dev of cov_core (cells with N >= 3 seeds)

| Variant | Paper | N seeds | Mean cov_core | Std-dev | Min | Max | Range | Status |
|---------|-------|--------:|--------------:|--------:|----:|----:|------:|--------|
| v0.12e | T7 | 11 | 83.6% | 8.1pp | 80% | 100% | 20.0pp | **med** |
| v0.12e | barney | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.12e | edmondson | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.12e | einstein | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.12e | wei | 3 | 83.3% | 28.9pp | 50% | 100% | 50.0pp | **HIGH** |
| v0.13 | T7 | 17 | 78.8% | 11.1pp | 60% | 100% | 40.0pp | **HIGH** |
| v0.13 | barney | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | edmondson | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | einstein | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | hayes | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | noyzhang | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | park | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | shannon | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | turing | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | vaswani | 4 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | watsoncrick | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13 | wei | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | T7 | 3 | 80.0% | 0.0pp | 80% | 80% | 0.0pp | **low** |
| v0.13d | barney | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | edmondson | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | einstein | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | hayes | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | hubinger | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | noyzhang | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | park | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | shannon | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | turing | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | vaswani | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | watsoncrick | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.13d | wei | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | T7 | 3 | 93.3% | 11.5pp | 80% | 100% | 20.0pp | **HIGH** |
| v0.16b | barney | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | edmondson | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | einstein | 6 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | hayes | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | noyzhang | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | park | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | turing | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | vaswani | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | watsoncrick | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16b | wei | 6 | 91.7% | 20.4pp | 50% | 100% | 50.0pp | **HIGH** |
| v0.16e | barney | 3 | 66.7% | 57.7pp | 0% | 100% | 100.0pp | **HIGH** |
| v0.16e | edmondson | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | einstein | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | hayes | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | noyzhang | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | park | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | shannon | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | turing | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | vaswani | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | watsoncrick | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |
| v0.16e | wei | 3 | 100.0% | 0.0pp | 100% | 100% | 0.0pp | **low** |

## (1) HIGH-variance cells (std-dev > 0.10) - noisy, mean unreliable

| Variant | Paper | N | Mean | Std-dev |
|---------|-------|--:|-----:|--------:|
| v0.16e | barney | 3 | 66.7% | **57.7pp** |
| v0.12e | wei | 3 | 83.3% | **28.9pp** |
| v0.16b | wei | 6 | 91.7% | **20.4pp** |
| v0.16b | T7 | 3 | 93.3% | **11.5pp** |
| v0.13 | T7 | 17 | 78.8% | **11.1pp** |

## (2) Is the v0.16b vs v0.13d 0.3pp gap within noise?

- Across all 52 (variant, paper) cells with N>=3 seeds:
  - **Median seed std-dev: 0.00pp**
  - Mean seed std-dev: 2.65pp
  - Max seed std-dev: 57.74pp
  - Min seed std-dev: 0.00pp

### Per-paper v0.16b vs v0.13d head-to-head (cov_core)

| Paper | v0.16b mean (N) | v0.16b std | v0.13d mean (N) | v0.13d std | Delta (16b-13d) | Pooled std | |Delta|/pooled |
|-------|------------------|-----------:|------------------|-----------:|----------------:|-----------:|---------------:|
| T7 | 93.3% (3) | 11.5pp | 80.0% (3) | 0.0pp | +13.3pp | 8.2pp | 1.63 |
| barney | 100.0% (6) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| edmondson | 100.0% (6) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| einstein | 100.0% (6) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| hayes | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| hubinger | 100.0% (2) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| noyzhang | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| park | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| shannon | 100.0% (2) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| turing | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| vaswani | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| watsoncrick | 100.0% (3) | 0.0pp | 100.0% (3) | 0.0pp | +0.0pp | 0.0pp | 0.00 |
| wei | 91.7% (6) | 20.4pp | 100.0% (3) | 0.0pp | -8.3pp | 14.4pp | 0.58 |

- **Aggregate per-paper-mean cov_core**: v0.16b=98.85% vs v0.13d=98.46% -> delta = +0.38pp
- Mean per-paper delta (16b - 13d): +0.38pp
- Mean |per-paper delta|: 1.67pp
- **Verdict**: |aggregate delta| (0.38pp) vs median seed std (0.00pp) -> **EXCEEDS MEDIAN NOISE**
- Per-paper interpretation: MARGINAL (delta >= median noise)

## (3) Per-paper stability classification

For each paper, average the seed std-dev across all 5 target variants (only cells with N>=3). Classify:
- **stable**: avg std-dev <= 0.05 (5pp). Trust the mean.
- **moderate**: 0.05 < avg <= 0.10. Caution; means probably ok but small deltas suspect.
- **unstable**: avg std-dev > 0.10. NEED more seeds.

| Paper | Variants w/ N>=3 | Avg std-dev | Max std-dev | Status |
|-------|-----------------:|------------:|------------:|--------|
| barney | 5 | 11.55pp | 57.74pp | **unstable** |
| wei | 5 | 9.86pp | 28.87pp | moderate |
| T7 | 4 | 7.69pp | 11.55pp | moderate |
| edmondson | 5 | 0.00pp | 0.00pp | stable |
| einstein | 5 | 0.00pp | 0.00pp | stable |
| hayes | 4 | 0.00pp | 0.00pp | stable |
| hubinger | 1 | 0.00pp | 0.00pp | stable |
| noyzhang | 4 | 0.00pp | 0.00pp | stable |
| park | 4 | 0.00pp | 0.00pp | stable |
| shannon | 3 | 0.00pp | 0.00pp | stable |
| turing | 4 | 0.00pp | 0.00pp | stable |
| vaswani | 4 | 0.00pp | 0.00pp | stable |
| watsoncrick | 4 | 0.00pp | 0.00pp | stable |

## Per-variant stability (mean seed std across covered papers)

| Variant | Cells w/ N>=3 | Avg std-dev | Max std-dev |
|---------|--------------:|------------:|------------:|
| v0.13d | 13 | 0.00pp | 0.00pp |
| v0.13 | 12 | 0.93pp | 11.11pp |
| v0.16b | 11 | 2.91pp | 20.41pp |
| v0.16e | 11 | 5.25pp | 57.74pp |
| v0.12e | 5 | 7.39pp | 28.87pp |

## Strategic conclusion

The aggregate v0.16b vs v0.13d delta (0.38pp) **exceeds the median seed std-dev (0.00pp)**. The gap is unlikely to be pure noise, but it is small relative to the worst-case per-cell variance. Treat as suggestive, not decisive.

