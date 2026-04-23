# Citare Extraction Campaign — Statistics

**Total runs attempted**: 104  (DONE: 98, FAIL: 6)

## Grand totals

| metric | value |
|--------|-------|
| Successful runs | 98 |
| Failed runs | 6 |
| **Input tokens (regular)** | 43,327 |
| **Output tokens** | 1,968,500 |
| **Cache creation tokens** | 7,363,922 |
| **Cache read tokens** | 8,126,410 |
| **Total tokens processed** | 17,502,159 |
| **Total cost (shown)** | $110.31 |
| **Total wall-clock (successful)** | 410.8 min (6.8 hours) |
| Mean cost per successful run | $1.126 |
| Mean duration per run | 251.5 sec |

## By prompt

| prompt | runs | total $ | mean $ | mean dur | mean claims | JSON valid | n scored |
|--------|------|---------|--------|----------|-------------|------------|----------|
| v0.1 | 30 | $39.74 | $1.325 | 274s | 26.1 | 28/30 | 28 |
| v0.10 | 5 | $6.08 | $1.215 | 284s | 36.2 | 5/5 | 5 |
| v0.2 | 5 | $5.65 | $1.129 | 296s | 32.6 | 5/5 | 5 |
| v0.3 | 23 | $23.29 | $1.013 | 253s | 33.7 | 23/23 | 23 |
| v0.4 | 5 | $4.94 | $0.988 | 249s | 22.2 | 4/5 | 4 |
| v0.5 | 2 | $3.67 | $1.837 | 166s | 24.5 | 2/2 | 2 |
| v0.6 | 4 | $3.75 | $0.938 | 217s | 25.0 | 4/4 | 4 |
| v0.7 | 3 | $2.87 | $0.956 | 204s | 23.0 | 3/3 | 3 |
| v0.8 | 15 | $14.31 | $0.954 | 220s | 26.7 | 15/15 | 15 |
| v0.9 | 6 | $6.02 | $1.003 | 224s | 29.3 | 6/6 | 6 |

## By model

| model | runs | total $ | mean $ | mean dur | JSON valid |
|-------|------|---------|--------|----------|------------|
| haiku-4.5 | 1 | $0.20 | $0.199 | 86s | 1/1 |
| opus-4.7 | 94 | $106.52 | $1.133 | 234s | 93/94 |
| sonnet-4.6 | 3 | $3.59 | $1.197 | 846s | 1/3 |

## By effort level

| effort | runs | total $ | mean $ | mean dur | mean claims |
|--------|------|---------|--------|----------|-------------|
| none | 72 | $80.29 | $1.115 | 266s | 29.1 |
| low | 1 | $2.65 | $2.652 | 128s | 19.0 |
| medium | 11 | $11.64 | $1.058 | 200s | 27.2 |
| high | 11 | $12.33 | $1.121 | 219s | 28.2 |
| xhigh | 1 | $1.04 | $1.040 | 270s | 31.0 |
| max | 1 | $1.15 | $1.147 | 325s | 30.0 |
| ? | 1 | $1.21 | $1.211 | 179s | 20.0 |

## By paper

| paper | runs | total $ | mean $ | mean claims | mean score |
|-------|------|---------|--------|-------------|------------|
| Barney | 5 | $5.66 | $1.131 | 36.6 | 100.0% |
| DellAcqua | 7 | $9.57 | $1.367 | 21.6 | 100.0% |
| Edmondson | 33 | $38.78 | $1.175 | 27.9 | 89.4% |
| Einstein | 4 | $3.76 | $0.939 | 26.2 | 100.0% |
| Hayes | 6 | $10.87 | $1.812 | 46.5 | 90.9% |
| Hubinger | 2 | $2.83 | $1.415 | 28.5 | 86.7% |
| Noy-Zhang | 8 | $6.76 | $0.845 | 26.9 | 89.5% |
| Park | 1 | $0.98 | $0.980 | 36.0 | 100.0% |
| Shannon | 4 | $5.71 | $1.427 | 37.5 | 100.0% |
| Turing | 8 | $6.97 | $0.871 | 29.1 | 90.4% |
| Vaswani | 5 | $5.08 | $1.017 | 21.2 | 100.0% |
| Watson-Crick | 3 | $1.25 | $0.418 | 13.7 | 100.0% |
| Wei | 12 | $12.10 | $1.008 | 27.4 | 94.7% |

## By harness (API vs Max-plan CLI)

- API (pay-per-use): 10 runs, $21.76 total
- CLI (Max plan): 88 runs, $88.55 total

## Failed runs

- 6 total

