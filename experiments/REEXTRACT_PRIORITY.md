# Re-extraction priority list (target: v0.13g × effort=none)

Generated 2026-04-26 after locking v0.13g × none as production champion.

## Categorisation logic

For each of the 81 papers in `CITARE_REGISTRATION_MANIFEST.json`:

- **P0 (FAIL)** — hed-claim audit flagged headline missingness. Re-extract if the
  PDF is sound; for `baddeley_hitch` the PDF itself is broken (0 bytes both copies).
- **P1 (WARN at low)** — audit found partial headline capture, AND the current
  manifest entry was extracted at `effort=low` (R71/R72/R73 batches). Most likely
  to benefit from v0.13g × none re-extraction.
- **P2 (WARN at none)** — audit warning, but current entry already at `effort=none`
  (mostly R55-R65 benchmark papers). Marginal expected gain.
- **P3 (PASS at low)** — audit passed, but extracted at `low` with v0.13d. The
  EXIST-claim improvement of v0.13g × none (avg +7.5/paper) might add boundary
  scaffolding even though headline is fine.
- **P4 (PASS at none)** — saturated. Skip.
- **P5 (unaudited)** — fell outside the audit grep but in manifest. Reviewed
  individually; most are R64 benchmark papers (effort=none, gold-scored 95-100%).

## Cost summary

| Tier | n | Est. cost | Est. time (15-parallel) |
|------|--:|----------:|------------------------:|
| P0 | 2 | $2 | 5 min |
| P1 | 9 | $11 | 5 min |
| P2 | 0 | $0 | — |
| P3 | 37 | $44 | 15 min |
| P5 | 33 (mixed) | depends | depends |

**Recommended action**: re-extract P0 + P1 immediately (~$13, ~5 min). Defer P3
to a separate decision. P5 is mostly fine as-is.

---

## P0 — FAIL: must re-extract (2 papers, ~$2)

| paper_key | current run | issue |
|-----------|-------------|-------|
| `baddeley_hitch_1974_working_memory` | R71 eff=low | **0-byte PDFs DELETED 2026-04-26** (both `pdfs/03_Psychology/` and `D:/Dropbox/ai/CitareMCP/pdfs/03_Psychology/`). Needs fresh web fetch into `pdfs/03_Psychology/Baddeley_Hitch_1974_Working_Memory.pdf` BEFORE re-extract |
| `bernerslee_2001_semantic_web` | R71 eff=low | No integrative META_CLAIM; headline scattered across pairwise RELATIONs |

**Action**:
- Web-fetch a sound Baddeley & Hitch 1974 PDF, save to `pdfs/03_Psychology/`, then
  run `python experiments/harness/run_extraction_cli.py --prompt
  experiments/prompts/v0.13g_thinking_defensive.md --pdf <path> --model
  claude-opus-4-7 --effort none --run-id R83_v013g_baddeley_s1`
- bernerslee: same command with the existing PDF at `pdfs/02_CS_AI_LLM/`

---

## P1 — WARN at effort=low (9 papers, ~$11)

These were extracted in R71/R72/R73 at `effort=low` and audit flagged partial
headline capture. v0.13g × none should improve EXIST coverage and may capture
the missing thesis-level synthesis.

| paper_key | current run | audit note |
|-----------|-------------|------------|
| `amodei_2016_concrete_problems_ai_safety` | R71 eff=low | Safe-exploration / distributional-shift under-represented |
| `bai_2022_constitutional_ai` | R71 eff=low | Novelty framing under-captured |
| `change_in_attachment_patterns_and_reflective_function` | R73 eff=low | Comparator differentiation thin |
| `competence_impeding_electronic_games` | R73 eff=low | Distributed across 22 RELATIONs (no integrative META) |
| `experiential_avoidance_and_behavioral_disorders` | R73 eff=low | Headline lives mostly in META_CLAIM, scattered RELATIONs |
| `miller_1956_magical_number_seven` | R71 eff=low | "≈seven" convergence captured, chunking/recoding only relational |
| `rct_of_a_psychological_intervention_for_cancer` | R73 eff=low | Cohesion-and-utilization captured, but mechanism statement only as EXISTENCE_CLAIM |
| `regional_brain_metabolic_changes_in_patients_with_major_depression` | R73 eff=low | Baseline abnormalities captured, but convergent metabolic normalization only partially |
| `williams_et_al_2006_mbct_in_suicide` | R73 eff=low | Conceptual/mechanistic headline; META_CLAIM prose is OK but iv/dv structure thin |

---

## P2 — WARN at effort=none (0 papers)

(empty — no WARN cases were extracted at none)

---

## P3 — PASS at effort=low (37 papers, ~$44)

Audit said headline is fine, but current extraction is `effort=low` so likely
missing 5-7 EXIST claims per paper compared to v0.13g × none. The marginal value
is real but each individual paper is already operationally OK.

**Recommendation**: skip for now. If we ever measure that integrity_warning
queries are returning shallow results on these papers, re-extract then.

```
arnulf_2014_predicting_survey_responses, arnulf_2024_measuring_menu_food,
attachment_as_moderator_of_treatment_outcome, better_living_with_illness,
binz_schulz_2023_cognitive_psychology_gpt3, building_social_resilience_in_soldiers,
burns_2022_discovering_latent_knowledge, comparing_the_process_in_psychodynamic,
deflecting_the_trajectory, dellacqua_2023_jagged_technological_frontier,
dimidjian_2006_randomized_trial, dobson_1989_meta_analysis_cbt,
effects_of_responses_to_depression, efficacy_of_interpersonal_psychotherapy,
facilitating_relational_framing, hofmann_2010_meta_analysis_mindfulness,
iit_geiger2021, interpbench_gupta2024, jakesch_2023_cowriting_opinionated_lms,
kosinski_2023_theory_of_mind_llms, lewis_2020_rag,
low_and_decreasing_self_esteem, mindfulness_and_self_compassion,
multiple_identity_enactments, munkhdalai_2024_infini_attention,
on_the_perpetuation_of_ignorance, pilot_of_acceptance_and_commitment_therapy,
prevention_of_relapse_recurrence, put_your_plan_into_action,
randomized_controlled_trial_of_acceptance, rising_income_and_subjective_wellbeing,
the_chronic_illness_acceptance_questionnaire, the_utility_of_the_valuing_questionnaire,
tversky_kahneman_1974_heuristics_biases, uher_2025_statistics_measurement,
wulff_2025_semantic_embeddings, zhou_2024_self_discover
```

---

## P4 — PASS at effort=none (0 papers)

(audit happened to pass these mostly into the unaudited bucket due to format
parsing; see P5 for the actual baseline papers).

---

## P5 — unaudited / mixed (33 papers)

| paper_key | current run | cov | priority |
|-----------|-------------|----:|----------|
| `T7` | R61 eff=none | 89% | **P0-equivalent**: never reaches 100% on any prompt; trap paper, leave as-is |
| `barney` | R64 eff=none | 100% | skip (saturated) |
| `edmondson` | R64 eff=none | 95% | skip (saturated; H8 null result is the missing 5pp) |
| `einstein` | R64 eff=none | 100% | skip |
| `hayes` | R61 eff=none | 91% | skip (theoretical, saturated for v0.13d/g) |
| `hubinger` | R65 eff=none | 100% | skip |
| `noyzhang` | R64 eff=none | 100% | skip |
| `park` | R64 eff=none | 100% | skip |
| `shannon` | R64 eff=none | 100% | skip |
| `turing` | R64 eff=none | 100% | skip |
| `vaswani` | R64 eff=none | 100% | skip |
| `watsoncrick` | R61 eff=none | 100% | skip |
| `wei` | R64 eff=none | 100% | skip |
| `2_shapiro_mechanisms_of_mindfulness2006` | R73 eff=low | no-gold | P3-equivalent (treat as PASS at low) |
| `berko1958childs` | R71 eff=low | no-gold | P3-equivalent |
| `conmy2023towards` | R71 eff=low | no-gold | P3-equivalent |
| `elazar2021measuring` | R71 eff=low | no-gold | P3-equivalent |
| `geiger2025causal` | R71 eff=low | no-gold | P1-equivalent (audit said WARN: theorems flattened) |
| `grant2025representational` | R71 eff=low | no-gold | P3-equivalent |
| `hanna2023how`, `hanna2024faith` | R71 eff=low | no-gold | P3-equivalent |
| `heimersheim2024how` | R71 eff=low | no-gold | P3-equivalent |
| `li2024optimal`, `makelov2023is` | R71 eff=low | no-gold | P3-equivalent |
| `marks2025sparse`, `meng2023locating`, `miller2024circuit`, `olsson2022context`, `syed2023attribution`, `todd2024function`, `vig2020causal`, `wang2022interpretability`, `zhang2024towards` | R72 eff=low | no-gold | P3-equivalent (RFT references batch) |

---

## Recommended re-extraction order

### Tier 1 — Run now (~$13, 5 min, 11 papers)

1. P0 baddeley_hitch — **block on** sound PDF re-fetch first
2. P0 bernerslee_2001 — re-extract immediately
3. P1 all 9 papers — single batch dispatch

Total: 11 papers × $1.19 = ~$13. Single sliding-window batch with MAX_PARALLEL=11
finishes in ~5 minutes.

### Tier 2 — Defer pending operational signal (~$44, 15 min, 37 papers)

P3 papers (PASS at low). Re-extract only if VPS-side observations show that
integrity_warning queries return shallow results on these papers.

### Tier 3 — Optional one-shot upgrade (~$48, 17 min)

P3 + P5 (PASS-equivalent at low) = 37 + 18 = 55 papers. If we ever decide "all
batch papers should be re-extracted at v0.13g × none for consistency", this is
the cost.

### Skip permanently

P5 benchmark papers (R55-R65 effort=none) and T7. Those are saturated or
trap-class limitations. v0.13g × none won't change them.

---

## Dispatcher template (when ready to run)

```bash
# Tier 1: P0 + P1 = 11 papers
cat > experiments/_ai_workspace/reextract_tier1.txt <<'EOF'
D:/Dropbox/ai/CitareOpus47/pdfs/<path>/<baddeley_pdf_after_refetch>.pdf
D:/Dropbox/ai/CitareOpus47/pdfs/02_CS_AI_LLM/BernersLee_2001_Semantic_Web.pdf
D:/Dropbox/ai/CitareOpus47/pdfs/02_CS_AI_LLM/Amodei_2016_Concrete_Problems_AI_Safety.pdf
D:/Dropbox/ai/CitareOpus47/pdfs/05_AI_Safety/Bai_2022_Constitutional_AI.pdf
... (the 9 P1 PDFs from 日本認知科学研究所 + CitareOpus47/pdfs)
EOF

bash experiments/harness/dispatch_*.sh <takes the file list>
```

(A specific re-extract dispatcher can be generated when needed.)
