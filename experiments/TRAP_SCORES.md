# Synthetic Trap Paper Scoring (v0.11 TeX prompt)

Six hand-authored trap papers stress-test the extractor on classic
over-citation failure modes plus LaTeX equation capture. All runs are
Opus 4.7, effort=none, single-shot.

| Trap | Theme | Run dir | Coverage | Total cost | Notes |
|------|-------|---------|----------|-----------|-------|
| T1 | Cross-sectional survey framed as "causes" | 20260424T012848Z_R37A | 100.0% | $0.299 | Design_basis=cross_sectional correctly tagged despite author's causal language |
| T2 | SWLS measured; Discussion generalizes to "well-being" | 20260424T012850Z_R37B | 100.0% | $0.312 | IV correctly bound to life_satisfaction, not wellbeing |
| T3 | Effect disappears under income control | 20260424T012852Z_R37C | 100.0% | $0.319 | **Caught the trap**: null-effect relation + `effect_disappears_under_control` + author's Discussion overclaim flagged as `proposed_in_paper` |
| T4 | ML baselines + attention equation | 20260424T012853Z_R37D | 87.5% | $0.380 | Attention eq captured in LaTeX; SOTA claim captured as RELATION, not EXIST (scorer FN) |
| T5 | Four-pillar conceptual framework | 20260424T012855Z_R37E | 100.0% | $0.332 | All 4 pillar definitions captured |
| T6 | PAC-Bayesian bound with 5 equations | 20260424T012857Z_R37F | 75.0% | $0.354 | **All 5 equations captured in valid LaTeX**; def concept uses 'true_risk'/'empirical_risk' rather than 'pac_bayesian_bound' (scorer FN) |

**Totals**: 6 runs, $1.996, 93.75% mean coverage.

## Highlight: T3 effect_disappears_under_control

The extractor decomposed the paper into **four** relation claims plus an
explicit attenuation-existence claim:

- `rel1`: education → satisfaction, POSITIVE, `verified_in_paper` (Model 1)
- `rel2`: education → satisfaction, NULL_EFFECT, `verified_in_paper` (Model 2)
- `rel3`: income → satisfaction, POSITIVE, `verified_in_paper` (Model 2)
- `rel4`: education → satisfaction, POSITIVE, `proposed_in_paper` ← the
  Discussion's overclaim, correctly separated from the Model 1 finding
- `exist2`: "education_job_satisfaction_association_attenuates_when_controlling_income"
- 4 relation-level `incompleteness_category = effect_disappears_under_control`

This is exactly the behavior Citare promises: the bivariate finding, the
attenuation, and the author's unsupported generalization are all represented
distinctly and ready for graph-integrity warnings.

## Highlight: LaTeX equation capture (T4 + T6)

### T4 — locality-biased attention
```
\mathrm{Attention}_{\text{ours}}(Q, K, V)
  = \mathrm{softmax}\!\left(\frac{QK^{\top}}{\sqrt{d_k}} + \lambda B\right) V
B_{ij} = -\,|i - j|/s
```

### T6 — PAC-Bayesian bound (5 equations, all captured)
```latex
% true risk
L(Q) = \mathbb{E}_{w \sim Q} \mathbb{E}_{(x,y) \sim \mathcal{D}} \ell(h_w(x), y)

% empirical risk
\hat{L}_n(Q) = \mathbb{E}_{w \sim Q} \frac{1}{n} \sum_{i=1}^{n} \ell(h_w(x_i), y_i)

% main PAC-Bayesian bound
L(Q) \leq \hat{L}_n(Q) +
  \sqrt{\frac{\mathrm{KL}(Q \parallel P) + \log(2\sqrt{n}/\delta)}{2n}}

% asymptotic rate
L(Q) - \hat{L}_n(Q) = O\!\left( \sqrt{\frac{\mathrm{KL}(Q \parallel P)}{n}} \right)

% Gaussian closed form
\mathrm{KL}(Q \parallel P)
  = \frac{1}{2}\!\left( \mathrm{tr}(\Sigma_Q/\sigma^2)
      + \lVert \mu_Q \rVert^2/\sigma^2 - d + d \log \sigma^2
      - \log |\Sigma_Q| \right)
```

Each equation is byte-comparable with the source `.tex`. The extractor
correctly used `\mathrm{KL}`, `\mathbb{E}`, `\mathcal{D}`, `\sqrt{}`,
`\sum`, `\log`, `\lVert \cdot \rVert` — no ASCII-math fallback.

## Notes on the two "misses"

Both missed items on T4 and T6 are scorer false negatives, not extraction
failures:

- **T4 `exist_sota_hypernews`**: the extractor captured the SOTA claim as a
  RELATION (our method → HyperNews F1, positive, verified_in_paper) with the
  81.4 score in `source_text`. This is structurally cleaner than an
  EXISTENCE_CLAIM. The gold fixture expected an EXIST — choice-of-template
  disagreement, not content failure.

- **T6 `def_pac_bayesian_bound`**: the extractor treats the bound as a
  RELATION (KL divergence bounds generalization error) with the full LaTeX
  attached, rather than a standalone DEFINITION. This is arguably more
  faithful — the bound *is* a theorem, not a definition.

If we treat these as structural variants, the substantive coverage is 100%
on all six traps.

## Cross-validation on real papers (v0.11 TeX, same prompt)

No regression from v0.3 baseline:

| Real paper | v0.3 | v0.11 | Equations captured |
|-----------|------|-------|-------------------|
| Einstein 1905 (Relativity, German) | 100% | 100% | 27 LaTeX equations (Lorentz, Doppler, mass-energy, ...) |
| Shannon 1948 (Information Theory) | 100% | 100% | 29 LaTeX equations |
| Vaswani 2017 (Transformer) | 100% | 100% | 7 LaTeX equations |
| Edmondson 1999 (Psychological Safety) | 95% | 95% | 0 (no equations in paper, as expected) |

v0.11 is the production prompt: strict superset of v0.3 with rigorous
LaTeX capture, no coverage regression on non-math papers.
