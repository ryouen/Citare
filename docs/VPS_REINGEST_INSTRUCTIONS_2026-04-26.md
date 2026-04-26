# VPS Re-ingest Instructions (2026-04-26)

After re-extracting 20 papers at the new production prompt **v0.13g × effort=none**
(R83 batch: 15 papers, R84 batch: 5 papers), we need to update the VPS-side DB.

This document tells you exactly:
1. **Which extraction.json files to ingest** (20 new ones)
2. **Whether to delete legacy claims first** (yes — explanation below)
3. **The SQL/Python to do it safely**

---

## 1. The 20 papers to re-ingest

The manifest at `experiments/CITARE_REGISTRATION_MANIFEST.json` has been updated.
For each of these 20 paper_keys, the manifest's `extraction_path` field now points
to the new R83/R84 v0.13g extraction. The legacy v0.13d run is preserved on disk
but recorded under `superseded_run_dir` in the manifest entry (audit trail).

| paper_key | DOI / canonical paper_id | new extraction_path |
|-----------|--------------------------|---------------------|
| amodei_2016_concrete_problems_ai_safety | 10.48550/arXiv.1606.06565 | runs/...R83_v013g_amodei_2016_con*/ |
| attachment_as_moderator_of_treatment_out | 10.1037/0022-006X.74.6.1041 | runs/...R83_v013g_attachment_as_m*/ |
| bai_2022_constitutional_ai | 10.48550/arXiv.2212.08073 | runs/...R83_v013g_bai_2022_consti*/ |
| bernerslee_2001_semantic_web | 10.1038/scientificamerican0501-34 | runs/...R83_v013g_bernerslee_2001*/ |
| change_in_attachment_patterns_and_reflec | 10.1037/0022-006X.74.6.1027 | runs/...R83_v013g_change_in_attac*/ |
| competence_impeding_electronic_games_and | 10.1037/a0034820 | runs/...R83_v013g_competence_impe*/ |
| dellacqua_2023_jagged_technological_fron | 10.2139/ssrn.4573321 | runs/...R83_v013g_dellacqua_2023_*/ |
| dimidjian_2006_randomized_trial_of_behav | 10.1037/0022-006X.74.4.658 | runs/...R83_v013g_dimidjian_2006_*/ |
| dobson_k_s_1989_a_meta_analysis_of_the_e | 10.1037/0022-006X.57.3.414 | runs/...R84_v013g_dobson_k_s_1989*/ |
| efficacy_of_interpersonal_psychotherapy_ | 10.1001/archpsyc.56.6.573 | runs/...R83_v013g_efficacy_of_int*/ |
| experiential_avoidance_and_behavioral_di | 10.1037/0022-006X.64.6.1152 | runs/...R83_v013g_experiential_av*/ |
| hofmann_s_g_sawyer_a_t_witt_a_a_oh_d_201 | 10.1037/a0018555 | runs/...R83_v013g_hofmann_s_g_saw*/ |
| kosinski_2023_theory_of_mind_llms | 10.1073/pnas.2405460121 | runs/...R84_v013g_kosinski_2023_t*/ |
| lewis_2020_rag | 10.48550/arXiv.2005.11401 | runs/...R84_v013g_lewis_2020_rag_*/ |
| miller_1956_magical_number_seven | 10.1037/h0043158 | runs/...R83_v013g_miller_1956_mag*/ |
| prevention_of_relapse_recurrence_in_majo | 10.1037//0022-006X.68.4.615 | runs/...R84_v013g_prevention_of_r*/ |
| rct_of_a_psychological_intervention_for_ | 10.1037/0022-006X.75.6.927 | runs/...R83_v013g_rct_of_a_psycho*/ |
| regional_brain_metabolic_changes_in_pati | 10.1001/archpsyc.58.7.631 | runs/...R83_v013g_regional_brain_*/ |
| tversky_kahneman_1974_heuristics_biases | 10.1126/science.185.4157.1124 | runs/...R84_v013g_tversky_kahnema*/ |
| williams_et_al_2006_mbct_in_suicide | 10.1002/jclp.20223 | runs/...R83_v013g_williams_et_al_*/ |

**All 20 have real DOIs** → paper-level identity is preserved (no synthetic-ID
collisions to worry about).

For the exact paths, query the updated manifest:
```python
import json
m = json.loads(open("experiments/CITARE_REGISTRATION_MANIFEST.json", encoding="utf-8").read())
for pk in [...20 paper_keys above...]:
    print(pk, m[pk]["extraction_path"])
```

---

## 2. Should you delete legacy claims first?

**YES, recommended.** Here's why:

### 2.1 The risk of in-place re-ingest

`citare_db.ingest.ingest_extraction` uses `INSERT INTO claims ... ON CONFLICT(id)
DO UPDATE` — so if R84 emits the same claim_id as legacy, it overwrites cleanly.
But:

- Legacy emitted **23-37 claims per paper** (avg ~28)
- R84 emits **17-51 claims per paper** (avg ~36, +~8 EXIST claims)
- claim_ids in v0.13d/v0.13g are sequentially numbered (`<paper_handle>_def1`,
  `_rel2`, `_exist3`, ...)
- If R84's emission order differs from legacy's (which it does — concept lists
  are normalised differently), then `_exist7` in R84 might be a *different
  phenomenon* than legacy's `_exist7`.
- After in-place re-ingest you would end up with:
  - claim_ids 1..N (where N = max(legacy, R84)) — overwritten with R84 content
  - any **legacy-only claim_ids beyond R84's max** — **stale, wrong content**
  - the SEMANTICS of overwritten ids may have shifted (e.g., legacy's
    `kosinski_exist7` was about "philosophical question", R84's `_exist7` might
    be about "Chinese room limitation" — different concept under same id)

In practice for these 20 papers, R84 ≥ legacy in claim count for most, but
**concept-id alignment is not guaranteed**. The clean fix is delete-then-insert.

### 2.2 The clean approach: delete-then-insert per paper

Because the schema has `ON DELETE CASCADE` on `claims.paper_id` (and on
`claim_relations.{source,target}_id`, `citation_text.citing_paper_id`,
`citation_edges.citation_text_id`, `measurement_methods.paper_id`), deleting
all rows for a paper is safe and atomic.

**Recipe** (run inside a transaction per paper):

```python
import json, sqlite3
from pathlib import Path
import sys
sys.path.insert(0, "packages/citare-db/src")
from citare_db.ingest import ingest_extraction
from citare_core import Extraction

conn = sqlite3.connect("/var/lib/citare/citare.db")
conn.execute("PRAGMA foreign_keys = ON")  # required for CASCADE

PAPERS_TO_REPLACE = [
    ("10.48550/arXiv.1606.06565", "experiments/runs/.../R83_v013g_amodei_..."),
    ("10.1037/0022-006X.74.6.1041", "experiments/runs/.../R83_v013g_attachment_as_m_..."),
    # ... see manifest for full list
]

for paper_id, ext_dir in PAPERS_TO_REPLACE:
    ext_path = Path(ext_dir) / "extraction.json"
    ext = Extraction.model_validate(json.loads(ext_path.read_text(encoding="utf-8")))

    conn.execute("BEGIN")
    try:
        # Delete all claim-level rows for this paper. CASCADE removes
        # claim_relations, measurement_methods, citation_text, citation_edges.
        # The papers row stays (will be UPDATEd by ingest_extraction).
        n_deleted = conn.execute(
            "DELETE FROM claims WHERE paper_id = ?", (paper_id,)
        ).rowcount
        conn.execute(
            "DELETE FROM citation_text WHERE citing_paper_id = ?", (paper_id,)
        )
        conn.execute(
            "DELETE FROM measurement_methods WHERE paper_id = ?", (paper_id,)
        )
        # Now ingest the new extraction. The papers row is preserved and updated;
        # all new claims/relations/methods/citations are inserted fresh.
        report = ingest_extraction(conn, ext)
        conn.commit()
        print(f"  {paper_id}: deleted {n_deleted} legacy claims, ingested {len(report.warnings)} warnings")
    except Exception as e:
        conn.rollback()
        print(f"  FAIL {paper_id}: {e}")
        raise
```

### 2.3 The lazy approach (acceptable but messier)

If you trust that R84's claim_ids cover a superset of legacy's claim_ids
(roughly true for the 17 papers where R84 > legacy claim count, but NOT for
the 3 papers where R84 ≤ legacy: amodei_2016 (37=37), attachment_as_moderator
(29 < 30), tversky_kahneman_1974 (32 < 34)), you can just re-ingest without
deletion:

```python
report = ingest_extraction(conn, ext)
# Will emit "claim_overwrite" warnings for ~28 claim_ids per paper, plus insert
# any new ones. Stale legacy claim_ids beyond R84's count remain.
```

For the 3 papers where R84 emitted FEWER claims, this leaves stale rows. We
recommend AGAINST this approach.

### 2.4 The simplest approach: drop and re-ingest from manifest

If the VPS DB has no curated/manual edits beyond what came from the seed
ingest, the simplest cleanest option is:

```bash
# On VPS
rm /var/lib/citare/citare.db
python scripts/ingest_v013d_champions.py --db /var/lib/citare/citare.db
python scripts/run_heuristic_resolver.py
```

This regenerates the entire DB (81 papers) from the updated manifest. Zero
risk of stale claim_ids. Idempotent. Takes ~30 seconds for 81 papers.

**Note**: `scripts/ingest_v013d_champions.py` reads the manifest field
`extraction_path` (now pointing to v0.13g for the 20 re-extracted papers),
so the script name "v013d" is now historical. The script itself is
prompt-version-agnostic.

---

## 3. Recommendation

| Approach | Risk | Complexity | Recommendation |
|----------|------|------------|----------------|
| **Delete-then-insert per paper** | Low | Medium (per-paper script) | **Best for incremental updates** |
| Lazy in-place re-ingest | Medium (stale rows on 3 papers) | Trivial | Avoid |
| **Drop and rebuild from manifest** | None | Trivial | **Best for first re-ingest after big batch** |

For this specific batch of 20 papers: **drop and rebuild is fine** because
- No VPS-side curation has been mentioned
- 81 papers is small (~30 sec to re-ingest)
- Idempotent → easy to re-run if anything fails
- The updated manifest is now the single source of truth

---

## 4. Smoke test after re-ingest (must pass)

```bash
python scripts/smoke_test_mcp.py
# Expected: 6/6 PASS
```

Plus manual spot-check:
```python
import sys, sqlite3
sys.path.insert(0, "packages/citare-mcp/src")
from citare_mcp.queries import search_claims, cite_claim

conn = sqlite3.connect("/var/lib/citare/citare.db")
conn.row_factory = sqlite3.Row

# After re-ingest of Hubinger (R65, NOT in this batch but classic), confirm thesis is captured
print(search_claims(conn, query="sleeper agents", limit=3))

# After re-ingest of Lewis 2020 RAG (in this batch — R84), confirm new EXIST claims arrived
print(search_claims(conn, query="parametric memory", limit=3))
print(search_claims(conn, doi="10.48550/arXiv.2005.11401", template_type="EXISTENCE_CLAIM"))
# Should return ~12 EXIST claims (vs ~10 before)
```

---

## 5. Files to share with VPS

These are all under the Dropbox tree at `D:/Dropbox/ai/CitareOpus47/`:

| File | Purpose |
|------|---------|
| `experiments/CITARE_REGISTRATION_MANIFEST.json` | **Updated** — points to R83/R84 v013g for 20 papers |
| `experiments/_ai_workspace/reingest_plan.json` | Machine-readable plan (paper_key → old/new run dirs) |
| `experiments/runs/*_R83_v013g_*/extraction.json` | 15 new R83 extractions |
| `experiments/runs/*_R84_v013g_*/extraction.json` | 5 new R84 extractions |
| `scripts/ingest_v013d_champions.py` | Existing ingest script (works with new manifest, name is historical) |
| `scripts/smoke_test_mcp.py` | Post-ingest verification |

The 20 legacy v0.13d run dirs stay on disk untouched (audit trail). They're
referenced in each manifest entry's `superseded_run_dir` field.

---

## 6. After this batch — what's next

There are **61 more papers** in the manifest still at v0.13d × low (or v0.13d ×
none for the 13 benchmark papers). Decision matrix per `experiments/REEXTRACT_PRIORITY.md`:

- **Tier 2 (P3)**: 32 more PASS-at-low papers. Re-extract only if you
  observe shallow integrity_warning queries on them. Cost: ~$32, ~10 min.
- **P4/P5 (saturated benchmark papers at effort=none)**: skip — no expected gain.
- **Baddeley & Hitch 1974**: PDF deleted (was 0 bytes). Needs web re-fetch
  before any extraction.

Your call on whether/when to do another round.
