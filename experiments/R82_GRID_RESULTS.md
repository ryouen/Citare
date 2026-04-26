# R82 Grid Results: 6 papers × 3 efforts × 4 prompts (72 runs)

Test: which prompt × effort combo recovers noyzhang regression while preserving hubinger/wei gains?

**Prompt axis:**
- v013d: baseline (current production)
- v013f: pre-extraction declarative rule (EXISTENCE preservation)
- v013g: extended-thinking-specific anti-compression rule
- v013h: post-extraction self-check + completeness verification

## Coverage by paper (prompt × effort)

### noyzhang

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 84.2% | 84.2% | 100.0% |
| v013f | 100.0% | 84.2% | 100.0% |
| v013g | 100.0% | 84.2% | 89.5% |
| v013h | 100.0% | 100.0% | 89.5% |

### hubinger

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 100.0% | 100.0% | 100.0% |
| v013f | 100.0% | 100.0% | 100.0% |
| v013g | 100.0% | 86.7% | 100.0% |
| v013h | 100.0% | 86.7% | 86.7% |

### park

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 100.0% | 100.0% | 100.0% |
| v013f | 100.0% | 100.0% | 100.0% |
| v013g | 100.0% | 100.0% | 100.0% |
| v013h | 100.0% | 100.0% | 100.0% |

### edmondson

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 95.0% | 95.0% | 90.0% |
| v013f | 95.0% | 95.0% | 95.0% |
| v013g | 95.0% | 75.0% | 95.0% |
| v013h | 95.0% | 85.0% | 95.0% |

### wei

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 79.0% | 100.0% | 79.0% |
| v013f | 100.0% | 79.0% | 100.0% |
| v013g | 100.0% | 100.0% | 89.5% |
| v013h | — | 100.0% | 100.0% |

### t7

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 82.1% | 82.1% | 92.9% |
| v013f | 85.7% | 82.1% | 73.2% |
| v013g | 89.3% | 82.1% | 78.6% |
| v013h | 69.6% | 85.7% | 89.3% |

## Cross-paper aggregate per prompt × effort

| prompt | none | low | medium |
|--------|-----:|----:|-------:|
| v013d | 90.0% | 93.6% | 93.6% |
| v013f | 96.8% | 90.0% | 94.7% |
| v013g | 97.4% | 88.0% | 92.1% |
| v013h | 92.9% | 92.9% | 93.4% |

## Per-prompt grand mean (across all efforts × papers)

| prompt | avg cov | avg cost | avg duration | avg claims | avg EXIST | avg REL |
|--------|--------:|---------:|-------------:|-----------:|----------:|--------:|
| **v013d** | 92.4% | $1.09 | 267s | 29.7 | 11.3 | 10.7 |
| **v013f** | 93.8% | $1.19 | 293s | 35.4 | 16.3 | 10.1 |
| **v013g** | 92.5% | $1.12 | 281s | 33.8 | 14.4 | 10.3 |
| **v013h** | 93.1% | $1.10 | 267s | 31.9 | 14.4 | 9.2 |

## Per-effort grand mean (across all prompts × papers)

| effort | avg cov | avg cost | avg claims | avg EXIST |
|--------|--------:|---------:|-----------:|----------:|
| **none** | 94.3% | $1.22 | 35.7 | 15.4 |
| **low** | 91.1% | $1.03 | 30.5 | 12.6 |
| **medium** | 93.5% | $1.12 | 32.1 | 14.3 |

## noyzhang regression analysis (the headline question)

Baseline: v013d × none = 100%, v013d × low = 73.7% (R81 finding).
Did any prompt × effort combo restore noyzhang to 100% while keeping low's other benefits?

| prompt | none | low | medium | low recovery? |
|--------|-----:|----:|-------:|---------------|
| v013d | 84.2% | 84.2% | 100.0% | 🔴 still regressed (84.2%) |
| v013f | 100.0% | 84.2% | 100.0% | 🔴 still regressed (84.2%) |
| v013g | 100.0% | 84.2% | 89.5% | 🔴 still regressed (84.2%) |
| v013h | 100.0% | 100.0% | 89.5% | ✅ recovered (100.0%) |

## Pareto picks

Top 5 by mean coverage:

| rank | combo | mean cov | mean cost | n |
|-----:|-------|---------:|----------:|--:|
| 1 | v013g × none | 97.4% | $1.19 | 6 |
| 2 | v013f × none | 96.8% | $1.32 | 6 |
| 3 | v013f × medium | 94.7% | $1.17 | 6 |
| 4 | v013d × medium | 93.6% | $1.09 | 6 |
| 5 | v013d × low | 93.6% | $1.01 | 6 |
