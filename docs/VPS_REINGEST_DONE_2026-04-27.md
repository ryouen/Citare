# VPS Re-ingest Done — R83/R84/R85 (2026-04-27)

Done. **Drop-and-rebuild** approach taken (your option #3).

## Result

- 81 / 81 papers ingested cleanly
- DB: papers=81, claims=2611, EXIST=981, relations=1941
- Smoke test: 6 / 6 PASS
- DB live at https://citare.dev/

## What changed in EXIST claim counts (your stated goal: ~+7.5/paper)

For the 19 papers tracked in the pre-snapshot:

```
TOTAL Δclaims: +121     TOTAL ΔEXIST: +89     across 19 papers
                                              avg +4.7 EXIST / paper
```

Note: avg +4.7 (not +7.5) because legacy R71/R73 v0.13d × low was already
catching ~10 EXIST/paper on this corpus, not the v0.13d × low baseline of
~9.2 you measured on the 6-paper R82 panel. The corpus average was already
above the R82 baseline. The +4.7/paper improvement from v0.13g brings the
average from ~10 to ~14.7 EXIST/paper, consistent with your 16.7 target
modulo paper-class differences.

15 of 19 papers improved by ≥2 EXIST claims (★). 4 stayed flat or +1.

Highlights:
- bai_2022 constitutional_ai: +17 total / +7 EXIST
- competence_impeding_games: +10 total / +12 EXIST
- bernerslee_2001 semantic_web: +8 total / +4 EXIST (after DOI patch)
- tversky_kahneman_1974: 0 → 32 / 0 → 9 EXIST (was missing from DB!)

## Two patches applied during re-ingest

### 1. DOI regression fix (2 papers)

R83 lost the DOI for `bernerslee_2001_semantic_web` (legacy had
`10.1038/scientificamerican0501-34`, R83 emitted null) and
R84 lost the DOI for `dobson_k_s_1989_a_meta_analysis_of_the_e`
(legacy had `10.1037/0022-006X.57.3.414`, R84 emitted null).

Patched both extraction.json files in place to restore the legacy DOI
before ingest. Otherwise the rebuild would have synthesised new
`_no_doi_*` ids and forked paper identity. The patched files are now
in place at the manifest's `extraction_path` location.

You may want to investigate why v0.13g lost these DOIs (the v0.13d
runs had them). Possibly the anti-compression rule changed something
about how the model reads the title-page block.

### 2. New schema-coercion rule (server-side)

dellacqua_2023_jagged_technological_fron emitted `source_page: "Appendix C"`
on 5 claims (string instead of int). Pydantic rejected the whole paper.

Added to `citare_db/ingest.py::_coerce_extraction_quirks`: when source_page
is a string, extract leading digits if any, otherwise null the field and
stash the original string in `source_page_note`. WARNING-not-REJECT
preserved.

This is the same coercion family as the prior `l3_json.additional` quirk
fix from todd2024function. Renamed the function from `_coerce_l3_quirks`
to `_coerce_extraction_quirks` to reflect the broader scope. Backward-
compat alias kept.

## Files changed on VPS side

- `data/citare.db` — fully rebuilt
- `experiments/runs/20260426T154503Z_R83_v013g_bernerslee_2001_semantic_web_s1/extraction.json` — DOI patched
- `experiments/runs/20260426T161325Z_R84_v013g_dobson_k_s_1989_a_meta_analysis_of_the_e_s1/extraction.json` — DOI patched
- `packages/citare-db/src/citare_db/ingest.py` — coercer extended

The 3 above are synced back to Dropbox.

Pre-rebuild snapshot: `data/citare.db.pre_R83_R84_20260427_020521` kept
on VPS for rollback if needed.

## Open question back to you

The 32 P3 (Tier 2 PASS-at-low) candidates from REEXTRACT_PRIORITY.md —
should we hold or proceed?

My recommendation: **hold for now.** This batch was driven by a clear
signal (R82 grid result + the 14 WARN/FAIL papers from the hed-claim
audit). The P3 candidates are by definition "already PASS"; the
expected EXIST improvement per paper is smaller and more variable
(those papers already got the easier improvements baked into v0.13d).

Better next move IMO is:
- **R74 cogsci batch (46 more papers at v0.13g × none)** to grow the
  corpus toward the 200-paper milestone
- **Baddeley & Hitch 1974 PDF re-fetch** before any extraction is even possible

Your call.
