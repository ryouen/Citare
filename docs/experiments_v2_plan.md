# Experiments v2 — Rigorous prompt-tuning plan

**Status**: specification (not yet executed beyond the pilot in §8).
**Authors**: Citare team.
**Date**: 2026-04-24, written after v0.1 ad-hoc tournament concluded.

## 0. Why v2 is needed

The v0.1 tournament (`experiments/T7_TOURNAMENT.md`) tested 9 prompts on 1 paper (T7) with N=1 each. Useful as exploration, but has six methodological gaps:

1. **Ad-hoc variant design**: each v0.12X prompt tested a different idea (TERSE, TRIAGE, ORDER, STATUS, DISCIPLINE, TOP-PRIME). No two variants differed along a single controlled axis.
2. **No interaction tests**: combinations like "TOP-PRIME × STATUS" or "TERSE × TRIAGE" were never tried.
3. **Single paper** (T7) covers most variants. Cross-paper generalisation was only spot-checked.
4. **N=1 per cell**: Opus 4.7 has non-zero run-to-run variance; single measurements don't separate signal from noise.
5. **Post-hoc success criteria**: the *coverage ≥ 95% ∧ core_eq ≥ 85% ∧ discipline ≥ 80%* threshold was defined after runs had started.
6. **Gold provenance**: 13 real-paper Gold fixtures were written by the PI after chapter-read subagent reading. Only T1–T7 were Gold-first. This creates asymmetric confidence in scores across papers.

v2 addresses each gap with a pre-registered factorial design, noise estimation, and cross-paper evaluation.

## 1. Orthogonal axes of prompt variation

Five independent axes, each with 2–4 levels, identified from the v0.1 tournament's observed effects:

| Axis | Levels | Rationale |
|------|--------|-----------|
| **A. Position** | `top` / `end` / `schema-appendix` | v0.12g showed position matters; never tested systematically. |
| **B. Length** | `1-line` / `5-line` / `15-line` / `35-line-with-examples` | v0.11→v0.12a collapse evidence suggests length-vs-coverage tradeoff. |
| **C. Structure** | `prose` / `schema-mandatory` / `two-pass-order` / `triage-categories` | v0.12e STATUS outperformed v0.12b TRIAGE with same discipline intent — structure matters independent of content. |
| **D. Example presence** | `none` / `one-shot` / `multi-shot` | Examples prime behaviour but consume attention; effect never isolated. |
| **E. Discipline mechanism** | `none` / `prose-filter` / `schema-status-field` / `both` | v0.12f vs v0.12e directly tested; need wider coverage. |

Full factorial is `3 × 4 × 4 × 3 × 4 = 576` cells — infeasible. We use a fractional design (§2).

## 2. Fractional factorial via Taguchi L8

L8 orthogonal array gives 8 variants that recover all main effects for 7 two-level factors. Collapsing some axes to 2 levels:

| Variant | A Position | B Length | C Structure | D Example | E Discipline |
|---------|-----------|----------|-------------|-----------|--------------|
| V1 | top | short (≤5) | prose | none | none |
| V2 | top | long (≥15) | schema-mandatory | present | schema+prose |
| V3 | end | short | schema-mandatory | present | none |
| V4 | end | long | prose | none | schema+prose |
| V5 | schema-appendix | short | two-pass-order | present | schema+prose |
| V6 | schema-appendix | long | triage-categories | none | none |
| V7 | top | short | triage-categories | none | schema-mandatory |
| V8 | end | long | two-pass-order | present | schema-mandatory |

Each variant is a clean L8 cell. Writing conventions:
- All variants are derivatives of `v0.3_overlooked.md` (the text-coverage champion)
- Equations are the subject of all new instruction; claim-extraction body is identical across variants
- Variants are named `v0.2XA.md` where X ∈ {1..8} and A is a suffix describing the cell (e.g. `v0.21a_top_short_prose_none_none.md`)

## 3. Paper panel

Five papers covering the space of (content type × equation density):

| Paper | Length | Content | Equations | Lost-in-the-middle? |
|-------|--------|---------|-----------|---------------------|
| Einstein 1905 (Relativity, German scan) | 30 p | physics theory | dense (~27) | no |
| T7 (More Data, Worse Models, synthetic) | 21 p | ML theory + experiment | dense (7 of varying status) | yes |
| Wei 2022 (Chain-of-Thought) | 12 p | ML empirical + examples | sparse | mild |
| Edmondson 1999 (Psychological Safety) | 33 p | psychology empirical | none | yes (mediation) |
| Barney 1991 (Resource-based view) | 19 p | management conceptual | none | no |

Selection criteria:
- Einstein + T7 stress equation capture at opposite ends of domain (physics vs ML)
- Edmondson stresses middle-coverage + mediation/hub_component detection
- Wei stresses mixed content (examples of CoT reasoning are pseudo-data)
- Barney stresses pure DEFINITION extraction

Why not more: N × M × R = runs × cost. With M=5 and R=3, N=8 already hits 120 extractions / $144. Adding T1–T6 traps quadruples cost for diminishing diversity return.

## 4. Repetition and noise estimation

Each cell runs N=3. Same prompt, same paper, same model (Opus 4.7, effort=none), different runs. This produces:

- Per-cell mean ± std of each metric
- 95% confidence intervals via student-t (df=2 is loose; use as weak signal only)
- Run-to-run correlation check: if two runs with the same prompt produce very different claims lists, something is wrong upstream

**Total run count**: 8 variants × 5 papers × 3 runs = **120 extractions**. Cost estimate $144–180.

## 5. Metrics

Five **independent** axes, reported raw. No composite:

1. `coverage` — weighted recall on must-catch gold claims
2. `middle_coverage` — same, restricted to claims in pages designated as middle
3. `integrity_penalty` — fraction of forbidden synthesis patterns produced
4. `core_eq_fidelity` — token-set match on `central_contribution` + `supporting_definition` equations
5. `eq_discipline` — `1 − decorative_extracted / decorative_expected`

Plus auxiliary (reported, not used in decision):
- Run-time, token cost, claim count
- Per-template coverage (DEFINITION / RELATION / EXISTENCE_CLAIM / META_CLAIM)

## 6. Pre-registered analysis

**Before** running any variant on the panel:

1. Commit `experiments/registered_plan_v2.yaml` listing:
   - All 8 variants (with prompt file paths)
   - All 5 papers (with gold file paths)
   - All 5 metrics (with scorer function names)
   - Success criteria: *"V is a winner if it Pareto-dominates v0.3 on at least 2 of {coverage, core_eq, discipline} and is not dominated on any"*

2. Then run. No modifications to the YAML until all runs complete.

3. Analysis pipeline (deterministic):
   - Per-cell mean/std table
   - Main-effect analysis: for each axis, compute the marginal mean of each metric across the 4 cells containing that level (L8 property)
   - Pareto-frontier plot: scatter (coverage, core_eq) with discipline as colour
   - Interaction check: pair-plot showing A×B, A×E, B×E (most likely interactions)

4. Gold-bias check: compute correlation of v0.3 coverage across the 5 papers. If correlation is very high (>0.8), golds are too similar; scores reflect gold design not prompt effect.

## 7. What would change the production recommendation

Current recommendation (from v0.1): `v0.3 + v0.12e STATUS` parallel dual-run.

v2 would change this recommendation if:

- Any single L8 variant achieves coverage ≥ 95% AND core_eq ≥ 85% AND discipline ≥ 80% **averaged over all 5 papers, with lower-bound of 95% CI above each threshold**
- OR a two-axis combination we hadn't tested (e.g. top + schema-status) emerges as dominant
- OR the noise analysis shows that v0.3 vs v0.12e differences are within-run variance (i.e. the ranking is unreliable)

## 8. Pilot (executed)

Before the full v2 run, a pilot addresses the most acute v0.1 gaps at low cost:

**Design**: 3 variants × 3 papers × 2 runs = **18 extractions** (~$22).

- Variants: v0.3 overlooked, v0.11 TeX, v0.12e STATUS (the three baseline champions)
- Papers: T7, Einstein, Edmondson (the three content extremes)
- Runs: N=2 per cell (enough to spot large variance; not enough for CI)

**What the pilot answers**:

1. Is v0.12e > v0.11 on core_eq a real effect or within-run noise? (key for production config)
2. Does the 100% coverage of v0.3 hold across all papers, or is it T7-specific?
3. How much run-to-run variance does Opus 4.7 exhibit on extraction tasks?

Results of the pilot are in `experiments/PILOT_V2.md` (produced after execution).

## 9. Timeline

| Phase | Duration | Prerequisites |
|-------|----------|---------------|
| Write plan (this doc) | 1 h | — |
| Pilot execution | ~1 h (parallel) | plan |
| Pilot analysis | 30 min | pilot done |
| Full L8 design + 4 new prompts | 2–3 h | pilot insights |
| L8 pre-registration | 30 min | prompts done |
| L8 execution | ~6 h wall-clock (parallel) | registration |
| L8 analysis + write-up | 2–3 h | execution done |

**Not executed in hackathon**: the full L8 + analysis. Hackathon scope is plan + pilot only. The L8 is a post-hackathon research agenda.

## 10. Reporting as Citare claims (dogfooding)

All v2 findings should be represented as claims in Citare itself:

- Per-variant per-paper metric values → `EXISTENCE_CLAIM` (e.g. `"v0.12e STATUS on T7 achieved core_eq=0.92"`)
- Main effects → `RELATION` (e.g. `"prompt_length → RELATION_coverage [negative]"`, verification `verified_in_paper`, design_basis `computational_demonstration`)
- Incompleteness warnings on conclusions that hold only for specific paper types
- Integrity reviews: flag the ad-hoc v0.1 tournament as `not_supported` for any claim beyond what N=1 justifies

This makes the experiment programme its own integrity test — if Citare can't represent our own findings faithfully, something is wrong in the schema.
