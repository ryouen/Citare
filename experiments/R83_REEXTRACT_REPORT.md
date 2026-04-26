# R83 re-extraction report (v0.13g × effort=none)

Run count: **15** of 15 expected

## Wall clock

- batch start (earliest meta.json ctime):  1777218304 epoch
- batch end   (latest extraction.json mtime): 1777218652 epoch
- **wall duration: 348s = 5.8 min**

## Aggregate (n=15)

| metric | mean ± SD | min | max | sum |
|--------|----------|----:|----:|----:|
| claims (total) | 35.7 ± 8.3 | 17.0 | 51.0 | 536.0 |
| claims (EXIST) | 14.0 ± 3.4 | 7.0 | 21.0 | 210.0 |
| claims (RELATION) | 12.3 ± 4.8 | 3.0 | 21.0 | 185.0 |
| input_tok (incl. cache) | 145391 ± 43100 | 98141 | 251992 | 2180864 |
| output_tok | 23746 ± 5172 | 14585 | 32825 | 356183 |
| cost_usd | $1.0285 ± $0.2238 | $0.6574 | $1.3156 | $15.43 |
| duration_sec | 275.2 ± 52.7 | 176.3 | 343.4 | 4127.3 |

## Per-run detail

| paper_key | dur (s) | in_tok | out_tok | claims | EXIST | REL | cost |
|-----------|--------:|-------:|--------:|-------:|------:|----:|-----:|
| dellacqua_2023_jagged_technological_fr | 298 | 185,597 | 21,992 | 35 | 15 | 10 | $1.3156 |
| hofmann_s_g_sawyer_a_t_witt_a_a_oh_d_2 | 343 | 251,992 | 32,825 | 45 | 14 | 21 | $1.2941 |
| rct_of_a_psychological_intervention_fo | 338 | 208,114 | 28,725 | 44 | 15 | 18 | $1.2446 |
| competence_impeding_electronic_games_a | 339 | 137,729 | 31,212 | 51 | 21 | 20 | $1.2417 |
| experiential_avoidance_and_behavioral_ | 307 | 160,747 | 24,893 | 42 | 17 | 14 | $1.2283 |
| bai_2022_constitutional_ai | 312 | 158,106 | 24,814 | 41 | 17 | 14 | $1.2092 |
| amodei_2016_concrete_problems_ai_safet | 258 | 152,250 | 21,292 | 37 | 12 | 12 | $1.0851 |
| regional_brain_metabolic_changes_in_pa | 298 | 109,755 | 27,377 | 36 | 12 | 13 | $1.0844 |
| change_in_attachment_patterns_and_refl | 302 | 132,344 | 26,034 | 33 | 15 | 9 | $0.9479 |
| efficacy_of_interpersonal_psychotherap | 247 | 98,141 | 22,990 | 31 | 12 | 14 | $0.9023 |
| attachment_as_moderator_of_treatment_o | 245 | 130,255 | 22,988 | 29 | 12 | 11 | $0.8678 |
| dimidjian_2006_randomized_trial_of_beh | 250 | 128,742 | 22,418 | 35 | 18 | 9 | $0.8440 |
| williams_et_al_2006_mbct_in_suicide | 218 | 100,035 | 18,466 | 28 | 12 | 7 | $0.8011 |
| bernerslee_2001_semantic_web | 176 | 100,847 | 14,585 | 32 | 11 | 10 | $0.7041 |
| miller_1956_magical_number_seven | 196 | 126,210 | 15,572 | 17 | 7 | 3 | $0.6574 |

## Comparison: R83 (v0.13g × none) vs legacy (v0.13d × low) on the same papers

| paper_key | EXIST(R83) vs (legacy) | total claims R83 vs legacy | cost R83 vs legacy |
|-----------|-----------------------:|---------------------------:|--------------------:|
| amodei_2016_concrete_problems_ai_safet | **12** vs 12 (Δ+0) | **37** vs 37 (Δ+0) | **$1.09** vs $1.09 (Δ$-0.00) |
| attachment_as_moderator_of_treatment_o | **12** vs 10 (Δ+2) | **29** vs 30 (Δ-1) | **$0.87** vs $0.93 (Δ$-0.06) |
| bai_2022_constitutional_ai | **17** vs 10 (Δ+7) | **41** vs 24 (Δ+17) | **$1.21** vs $1.27 (Δ$-0.06) |
| bernerslee_2001_semantic_web | **11** vs 7 (Δ+4) | **32** vs 24 (Δ+8) | **$0.70** vs $0.70 (Δ$+0.01) |
| change_in_attachment_patterns_and_refl | **15** vs 10 (Δ+5) | **33** vs 31 (Δ+2) | **$0.95** vs $0.87 (Δ$+0.08) |
| competence_impeding_electronic_games_a | **21** vs 9 (Δ+12) | **51** vs 41 (Δ+10) | **$1.24** vs $1.21 (Δ$+0.03) |
| dellacqua_2023_jagged_technological_fr | **15** vs 10 (Δ+5) | **35** vs 27 (Δ+8) | **$1.32** vs $1.32 (Δ$-0.00) |
| dimidjian_2006_randomized_trial_of_beh | **18** vs 14 (Δ+4) | **35** vs 35 (Δ+0) | **$0.84** vs $0.90 (Δ$-0.05) |
| efficacy_of_interpersonal_psychotherap | **12** vs 10 (Δ+2) | **31** vs 29 (Δ+2) | **$0.90** vs $0.78 (Δ$+0.12) |
| experiential_avoidance_and_behavioral_ | **17** vs 13 (Δ+4) | **42** vs 31 (Δ+11) | **$1.23** vs $1.21 (Δ$+0.02) |
| hofmann_s_g_sawyer_a_t_witt_a_a_oh_d_2 | **14** vs 9 (Δ+5) | **45** vs 40 (Δ+5) | **$1.29** vs $1.30 (Δ$-0.01) |
| miller_1956_magical_number_seven | **7** vs 6 (Δ+1) | **17** vs 17 (Δ+0) | **$0.66** vs $0.64 (Δ$+0.02) |
| rct_of_a_psychological_intervention_fo | **15** vs 10 (Δ+5) | **44** vs 31 (Δ+13) | **$1.24** vs $1.07 (Δ$+0.18) |
| regional_brain_metabolic_changes_in_pa | **12** vs 8 (Δ+4) | **36** vs 33 (Δ+3) | **$1.08** vs $1.02 (Δ$+0.07) |
| williams_et_al_2006_mbct_in_suicide | **12** vs 7 (Δ+5) | **28** vs 23 (Δ+5) | **$0.80** vs $0.74 (Δ$+0.06) |

**Total Δ EXIST: +65**  
**Total Δ duration: +136s**  
**Total Δ cost: $+0.39** (legacy $15.04 → R83 $15.43)  
