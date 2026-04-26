# L8 Final Tournament on T7 (with N=3)

## Per-variant means (N=up to 3)

| Variant | pos | len | struct | ex | disc | N | Coverage | Middle | Core eq | Discipline | Eqs |
|---------|-----|-----|--------|----|----- |---|----------|--------|---------|------------|-----|
| V1_TOP_PRIME | top | short | prose | no | none | 3 | 84.5%±5.5 | 77.2%±8.0 | 58.8%±51.0 | 66.7%±33.3 | 13.0 |
| V2_TOP_LONG_SCHEMA | top | long | schema | yes | both | 3 | 91.7%±7.4 | 87.7%±11.0 | 89.1%±6.9 | 66.7%±0.0 | 5.7 |
| V3_END_SCHEMA | end | long | schema | yes | none | 3 | 79.2%±1.0 | 69.3%±1.5 | 87.2%±6.6 | 55.6%±19.2 | 10.7 |
| V4_DISCIPLINE | end | long | prose | no | both | 3 | 89.3%±7.1 | 84.2%±10.5 | 60.4%±52.4 | 77.8%±19.2 | 6.0 |
| V5_APX_2PASS | apx | short | two_pass | yes | both | 3 | 77.4%±7.4 | 66.7%±11.0 | 87.0%±9.5 | 66.7%±0.0 | 9.0 |
| V6_TRIAGE | apx | long | triage | no | none | 3 | 85.7%±6.2 | 78.9%±9.1 | 93.8%±2.4 | 66.7%±0.0 | 9.7 |
| V7_TOP_TRIAGE | top | short | triage | no | schema | 3 | 88.1%±2.1 | 82.5%±3.0 | 0.0%±0.0 | 100.0%±0.0 | 0.0 |
| V8_2PASS_END | end | long | two_pass | yes | schema | 3 | 86.9%±5.5 | 80.7%±8.0 | 82.1%±0.0 | 66.7%±33.3 | 8.0 |
| v0.3_BASELINE | -- | -- | text_only | no | -- | 3 | 91.7%±7.4 | 87.7%±11.0 | 0.0%±0.0 | 100.0%±0.0 | 0.0 |
| v0.12e_STATUS | end | long | schema | no | schema | 3 | 84.5%±4.1 | 77.2%±6.1 | 89.1%±6.1 | 88.9%±19.2 | 6.3 |
| v0.13_VERBATIM | end | long | schema+refs | yes | schema | 3 | 82.1%±3.6 | 73.7%±5.3 | 92.1%±4.3 | 77.8%±19.2 | 6.0 |

## Main-effect analysis (L8 axis marginals)

For each axis level, average the metric across all L8 variants at that level.

### Axis: pos

| pos level | Coverage | Core eq | Discipline |
|--------|--------|--------|--------|
| apx | 81.5% | 90.4% | 66.7% |
| end | 85.1% | 76.6% | 66.7% |
| top | 88.1% | 49.3% | 77.8% |

### Axis: len

| len level | Coverage | Core eq | Discipline |
|--------|--------|--------|--------|
| long | 86.5% | 82.5% | 66.7% |
| short | 83.3% | 48.6% | 77.8% |

### Axis: struct

| struct level | Coverage | Core eq | Discipline |
|--------|--------|--------|--------|
| prose | 86.9% | 59.6% | 72.2% |
| schema | 85.4% | 88.2% | 61.1% |
| triage | 86.9% | 46.9% | 83.3% |
| two_pass | 82.1% | 84.5% | 66.7% |

### Axis: ex

| ex level | Coverage | Core eq | Discipline |
|--------|--------|--------|--------|
| no | 86.9% | 53.2% | 77.8% |
| yes | 83.8% | 86.3% | 63.9% |

### Axis: disc

| disc level | Coverage | Core eq | Discipline |
|--------|--------|--------|--------|
| both | 86.1% | 78.8% | 70.4% |
| none | 83.1% | 79.9% | 63.0% |
| schema | 87.5% | 41.0% | 83.3% |

## Winner check (coverage≥90% AND core_eq≥85% AND discipline≥50%)

- **V2_TOP_LONG_SCHEMA** (cov=91.7%, core=89.1%, disc=66.7%)

## Raw per-seed scores (for noise inspection)

| Variant | seed | cov | middle | core_eq | discipline |
|---------|------|-----|--------|---------|------------|
| V1_TOP_PRIME | R39G2_v12g_top_prime_T7 | 78.6% | 68.4% | 90.0% | 33.3% |
| V1_TOP_PRIME | 2 | 89.3% | 84.2% | 86.5% | 66.7% |
| V1_TOP_PRIME | 3 | 85.7% | 79.0% | 0.0% | 100.0% |
| V2_TOP_LONG_SCHEMA | 1 | 100.0% | 100.0% | 95.9% | 66.7% |
| V2_TOP_LONG_SCHEMA | 2 | 85.7% | 79.0% | 82.1% | 66.7% |
| V2_TOP_LONG_SCHEMA | 3 | 89.3% | 84.2% | 89.2% | 66.7% |
| V3_END_SCHEMA | R38D_v11_trap_T7 | 80.4% | 71.0% | 86.9% | 66.7% |
| V3_END_SCHEMA | 2 | 78.6% | 68.4% | 94.0% | 66.7% |
| V3_END_SCHEMA | 3 | 78.6% | 68.4% | 80.8% | 33.3% |
| V4_DISCIPLINE | R39F_v12f_discipline_T7 | 82.1% | 73.7% | 94.0% | 66.7% |
| V4_DISCIPLINE | 2 | 89.3% | 84.2% | 87.2% | 66.7% |
| V4_DISCIPLINE | 3 | 96.4% | 94.7% | 0.0% | 100.0% |
| V5_APX_2PASS | 1 | 75.0% | 63.2% | 98.0% | 66.7% |
| V5_APX_2PASS | 2 | 71.4% | 57.9% | 82.1% | 66.7% |
| V5_APX_2PASS | 3 | 85.7% | 79.0% | 80.8% | 66.7% |
| V6_TRIAGE | R39B_v12b_triage_T7 | 78.6% | 68.4% | 91.3% | 66.7% |
| V6_TRIAGE | 2 | 89.3% | 84.2% | 94.0% | 66.7% |
| V6_TRIAGE | 3 | 89.3% | 84.2% | 96.0% | 66.7% |
| V7_TOP_TRIAGE | 1 | 85.7% | 79.0% | 0.0% | 100.0% |
| V7_TOP_TRIAGE | 2 | 89.3% | 84.2% | 0.0% | 100.0% |
| V7_TOP_TRIAGE | 3 | 89.3% | 84.2% | 0.0% | 100.0% |
| V8_2PASS_END | 1 | 92.9% | 89.5% | 82.1% | 33.3% |
| V8_2PASS_END | 2 | 82.1% | 73.7% | 82.1% | 100.0% |
| V8_2PASS_END | 3 | 85.7% | 79.0% | 82.1% | 66.7% |
| v0.3_BASELINE | R38B_v03_trap_T7 | 100.0% | 100.0% | 0.0% | 100.0% |
| v0.3_BASELINE | 2 | 89.3% | 84.2% | 0.0% | 100.0% |
| v0.3_BASELINE | 3 | 85.7% | 79.0% | 0.0% | 100.0% |
| v0.12e_STATUS | tatus_T7 | 82.1% | 73.7% | 92.1% | 100.0% |
| v0.12e_STATUS | 2 | 89.3% | 84.2% | 82.1% | 66.7% |
| v0.12e_STATUS | 3 | 82.1% | 73.7% | 93.2% | 100.0% |
| v0.13_VERBATIM | 1 | 78.6% | 68.4% | 94.0% | 66.7% |
| v0.13_VERBATIM | 2 | 85.7% | 79.0% | 87.2% | 100.0% |
| v0.13_VERBATIM | 3 | 82.1% | 73.7% | 95.2% | 66.7% |

