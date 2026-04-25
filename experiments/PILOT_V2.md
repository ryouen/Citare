# Pilot v2 Results (3 variants × 3 papers × up to 2 runs)

Addresses v0.1 tournament's N=1 and single-paper limitations.

## Per-cell means

| Variant | Paper | N | coverage | core_eq | discipline | eqs |
|---------|-------|---|----------|---------|------------|-----|
| v0.3 | T7 | 3 | 91.7%±7.4 | 0.0%±0.0 | 100.0%±0.0 | 0 |
| v0.3 | einstein | 3 | 100.0%±0.0 | 0.0%±0.0 | n/a | 0 |
| v0.3 | edmondson | 3 | 91.7%±5.8 | 0.0%±0.0 | n/a | 0 |
| v0.11 | T7 | 3 | 79.2%±1.0 | 87.2%±6.6 | 33.3%±0.0 | 11 |
| v0.11 | einstein | 3 | 100.0%±0.0 | 0.0%±0.0 | n/a | 26 |
| v0.11 | edmondson | 3 | 95.0%±0.0 | 0.0%±0.0 | n/a | 0 |
| v0.12e | T7 | 3 | 84.5%±4.1 | 89.1%±6.1 | 55.6%±0.0 | 6 |
| v0.12e | einstein | 3 | 100.0%±0.0 | 0.0%±0.0 | n/a | 19 |
| v0.12e | edmondson | 3 | 95.0%±0.0 | 0.0%±0.0 | n/a | 0 |
| v0.13 | T7 | 3 | 82.1%±3.6 | 92.1%±4.3 | 44.4%±0.0 | 6 |
| v0.13 | einstein | 3 | 100.0%±0.0 | 0.0%±0.0 | n/a | 18 |
| v0.13 | edmondson | 3 | 95.0%±0.0 | 0.0%±0.0 | n/a | 0 |

## Per-variant aggregate (averaged across papers)

| Variant | coverage | core_eq | discipline | runs total |
|---------|----------|---------|------------|------------|
| v0.3 | 94.4%±6.3 | 0.0%±0.0 | 100.0%±0.0 | 9 |
| v0.11 | 91.4%±9.4 | 29.1%±43.7 | 33.3%±0.0 | 9 |
| v0.12e | 93.2%±7.1 | 29.7%±44.7 | 55.6%±19.2 | 9 |
| v0.13 | 92.4%±8.2 | 30.7%±46.1 | 44.4%±19.2 | 9 |

## Noise check: within-cell std

If within-cell std is small relative to between-variant mean differences, rankings are reliable.

| Cell | cov std | core_eq std | rank-stable? |
|------|---------|-------------|--------------|
| v0.3/T7 | 7.4pp | 0.0pp | HIGH VARIANCE |
| v0.3/einstein | 0.0pp | 0.0pp | OK |
| v0.3/edmondson | 5.8pp | 0.0pp | HIGH VARIANCE |
| v0.11/T7 | 1.0pp | 6.6pp | HIGH VARIANCE |
| v0.11/einstein | 0.0pp | 0.0pp | OK |
| v0.11/edmondson | 0.0pp | 0.0pp | OK |
| v0.12e/T7 | 4.1pp | 6.1pp | HIGH VARIANCE |
| v0.12e/einstein | 0.0pp | 0.0pp | OK |
| v0.12e/edmondson | 0.0pp | 0.0pp | OK |
| v0.13/T7 | 3.6pp | 4.3pp | OK |
| v0.13/einstein | 0.0pp | 0.0pp | OK |
| v0.13/edmondson | 0.0pp | 0.0pp | OK |

