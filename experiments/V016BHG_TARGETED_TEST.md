# v0.16b-hg targeted-test (R70) scoring + Pareto comparison

Generated from 9 runs: `20260425T144301Z_R70_v016bhg_<paper>_s<1..3>` for paper in ['T7', 'wei', 'noyzhang'].

v0.16b-hg = v0.16b base + hedging-language additions intended to recover
minor coverage on noyzhang (effect heterogeneity / qualitative findings).

## Per-paper means (3 seeds each)

| Paper | seeds | core mean | core seeds | minor mean | minor seeds | claims | duration (s) | cost ($) |
|-------|------:|----------:|------------|-----------:|-------------|-------:|-------------:|---------:|
| T7 | 3 | **80%** | 80% / 80% / 80% | **79%** | 86% / 79% / 71% | 28.3 | 296 | $1.107 |
| wei | 3 | **83%** | 50% / 100% / 100% | **93%** | 100% / 100% / 80% | 35.0 | 281 | $1.188 |
| noyzhang | 3 | **100%** | 100% / 100% / 100% | **73%** | 80% / 60% / 80% | 33.7 | 234 | $0.790 |

## Pareto comparison: v0.16b vs v0.13d vs v0.16b-hg

| Paper | v0.16b core | v0.13d core | **v0.16b-hg core** | v0.16b minor | v0.13d minor | **v0.16b-hg minor** |
|-------|------------:|------------:|-------------------:|-------------:|-------------:|--------------------:|
| T7 | 93% | 80% | **80%** | 88% | 88% | **79%** |
| wei | 92% | 100% | **83%** | 97% | 93% | **93%** |
| noyzhang | 100% | 100% | **100%** | 73% | 93% | **73%** |

### Delta vs v0.16b (positive = v0.16b-hg better)

| Paper | core delta | minor delta |
|---|---:|---:|
| T7 | -13pp | -9pp |
| wei | -9pp | -4pp |
| noyzhang | +0pp | +0pp |

### Delta vs v0.13d (positive = v0.16b-hg better)

| Paper | core delta | minor delta |
|---|---:|---:|
| T7 | +0pp | -9pp |
| wei | -17pp | +0pp |
| noyzhang | +0pp | -20pp |

## Items of interest: v0.16b-hg catches what v0.16b missed?

| Paper | Item | seed1 | seed2 | seed3 | hit rate |
|-------|------|:-----:|:-----:|:-----:|---------:|
| T7 | `rel_R1_dataset_size_to_tail_coverage` | [+] | [-] | [-] | 33% (1/3) |
| noyzhang | `exist_effect_heterogeneity` | [-] | [-] | [-] | 0% (0/3) |

## Aggregate cost / duration / tokens (9 runs)

- **Total cost**: $9.253
- **Total duration**: 2434s (40.6 min)
- **Total input tokens** (incl cache create + cache read): 1,552,141
- **Total output tokens**: 195,443
- **Total tokens**: 1,747,584
- **Mean per-run cost**: $1.028
- **Mean per-run duration**: 270s

## Strategic verdict

### Q1: Did v0.16b-hg close the noyzhang minor gap?

- v0.16b minor on noyzhang (baseline being patched): **73%**
- v0.13d minor on noyzhang (ceiling target): **93%**
- v0.16b-hg minor on noyzhang: **73.3%**
- Delta vs v0.16b: **+0.3 pp**
- Delta vs v0.13d: **-19.7 pp**
- Gap closed? **NO** — essentially flat vs v0.16b; the 20pp gap to v0.13d remains

### Q2: Pareto-better than v0.16b on these 3 papers?

- Weakly Pareto-dominates v0.16b (no axis worse): **NO**
- Strictly Pareto-better (>=1 axis strictly higher, none lower): **NO**

### Q3: Pareto-better than v0.13d on these 3 papers?

- Weakly Pareto-dominates v0.13d: **NO**
- Strictly Pareto-better: **NO**

### Where does v0.16b-hg underperform?

- T7: core is **-13pp** vs v0.16b
- T7: minor is **-9pp** vs v0.16b
- T7: minor is **-9pp** vs v0.13d
- wei: core is **-9pp** vs v0.16b
- wei: minor is **-4pp** vs v0.16b
- wei: core is **-17pp** vs v0.13d
- noyzhang: minor is **-20pp** vs v0.13d

## Appendix: per-run detail


### T7

- **20260425T144301Z_R70_v016bhg_T7_s1**: cov_overall=86%, core=80%, minor=86%, claims=28, dur=267s, cost=$1.051
- **20260425T144301Z_R70_v016bhg_T7_s2**: cov_overall=82%, core=80%, minor=79%, claims=28, dur=304s, cost=$1.098
- **20260425T144301Z_R70_v016bhg_T7_s3**: cov_overall=79%, core=80%, minor=71%, claims=29, dur=318s, cost=$1.170

### wei

- **20260425T144301Z_R70_v016bhg_wei_s1**: cov_overall=79%, core=50%, minor=100%, claims=36, dur=248s, cost=$1.032
- **20260425T144301Z_R70_v016bhg_wei_s2**: cov_overall=100%, core=100%, minor=100%, claims=35, dur=335s, cost=$1.573
- **20260425T144301Z_R70_v016bhg_wei_s3**: cov_overall=89%, core=100%, minor=80%, claims=34, dur=261s, cost=$0.958

### noyzhang

- **20260425T144301Z_R70_v016bhg_noyzhang_s1**: cov_overall=89%, core=100%, minor=80%, claims=32, dur=205s, cost=$0.722
- **20260425T144301Z_R70_v016bhg_noyzhang_s2**: cov_overall=74%, core=100%, minor=60%, claims=34, dur=248s, cost=$0.827
- **20260425T144301Z_R70_v016bhg_noyzhang_s3**: cov_overall=89%, core=100%, minor=80%, claims=35, dur=248s, cost=$0.821
