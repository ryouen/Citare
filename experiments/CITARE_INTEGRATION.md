# Citare End-to-End Integration Validation (2026-04-26, v1)

> ⚠️ **Audit-trail document.** This v1 was written when v0.13d was the production candidate.
> A revised end-to-end report is at `experiments/CITARE_INTEGRATION_v2.md`.
> The current production prompt is **v0.13g × effort=none** (see `experiments/PRODUCTION_CHAMPION.md`).

After locking v0.13d as the production candidate, the 13 best per-paper extractions were ingested into the Citare SQLite database and the local MCP server's read paths (search/cite/graph) were validated.

## Pipeline summary

```
v0.13d prompt → run_extraction_cli.py → extraction.json
   → ingest_v013d_champions.py → data/citare.db (SQLite)
   → citare-mcp (stdio) → search_claims / cite_claim / get_claim_graph
```

## What was ingested

Source: `experiments/CITARE_REGISTRATION_MANIFEST.json` (best v0.13d run per paper, by composite cov - integrity_penalty)

| Metric | Count |
|--------|------:|
| Papers | 13 |
| Claims | 419 |
| Claim-relations | 340 |
| With integrity warnings (non-`none`) | 199 |
| Citation_text records | 258 |
| Citation edges resolved | 0 (258 queued for LLM batch review) |

**Claim breakdown by template type:**
- EXISTENCE_CLAIM: 150
- RELATION: 144
- DEFINITION: 108
- META_CLAIM: 17

**Verification status:**
- verified_in_paper: 218
- proposed_in_paper: 94
- (null, mostly DEFINITIONs): 107

**Causal strength (design_basis):**
- theoretical: 53 (Einstein, Turing, Watson-Crick, Shannon)
- computational_demonstration: 43 (Vaswani, Wei, Hubinger, Park)
- rct: 27 (Hubinger AI safety experiments, Noy/Zhang field experiment)
- cross_sectional: 12 (Edmondson)
- meta_analysis: 6 (Park)
- longitudinal: 2
- quasi_experimental: 1

**Integrity warning distribution (340 relations):**
- `none`: 141 (clean supports/aggregates)
- **`hub_component`: 115** — mediation/moderation chain pieces (most common warning)
- **`boundary_condition`: 73** — limitations / scope conditions
- `extends_prior_definition`: 8
- **`effect_disappears_under_control`: 3** — the strongest warning class

## MCP read-path verification

All three local Citare MCP tools (stdio-based) work end-to-end against the seeded DB:

### Test 1: `search_claims(iv="team_psychological_safety")`
Returns Edmondson 1999 rel2/rel3 with full L0 JSON, source_text, source_page, causal_strength block, method_metadata. **PASS**

### Test 2: `get_claim_graph("edmondson1999_rel3", depth=2)`
Center claim: psych_safety → performance (mediated by learning_behavior).
Returns 15 edges including:
- `rel1 → rel3 [part_of_model] hub_component`
- `rel2 → rel3 [part_of_model] hub_component`
- `rel2 → rel5 [qualifies] effect_disappears_under_control` ← critical warning
- `exist1 → rel3 [qualifies] boundary_condition` (cross-sectional design caveat)

**PASS** — the integrity warnings that prevent misleading citations are correctly traversed.

### Test 3: `cite_claim("edmondson1999_rel2")`
Returns full citation bundle:
- claim_id, paper_doi, paper_title
- source_text (direct quote), source_page=355
- design_basis="cross_sectional"
- **safe_verbs: ["is associated with", "correlates with"]** ← derived from cross_sectional design
- 5 integrity_warnings (boundary_condition, hub_component × 3, effect_disappears_under_control)

**PASS** — exactly what an AI application needs to cite without overclaiming causality.

### Test 4: cross-paper `search_claims(template_type="DEFINITION")`
Returns 20 DEFINITION claims across 5 papers (Edmondson, Vaswani, Einstein, Barney, Shannon).
**PASS**

### Test 5: `search_claims(query="chain of thought")`
Returns wei2022 def1, rel1, def2.
**PASS**

### Test 6: `search_claims(query="DNA structure")` — known limitation
Returns 0 hits. Watson-Crick uses different wording in source_text ("the structure of the salt of deoxyribose nucleic acid"). The search is **literal substring match**, not semantic.
**KNOWN LIMITATION** — see "Production gaps" below.

### Test 7: `search_claims(dv="team_performance")`
Returns 2 RELATIONS (Edmondson rel1: learning_behavior → performance, rel3: psych_safety → performance via learning).
**PASS**

## Production gaps identified

1. **Citation edges resolution is queued, not resolved**: 258 cross-paper citations are marked `pending_llm_review` after ingest. The resolver only matched 0 by identifier or triple (because the cited papers aren't in the DB yet). Would need either a larger paper corpus or LLM-batch resolution to convert these into typed edges.

2. **Free-text search is substring-only**: `query="DNA structure"` misses Watson-Crick because the source uses "structure of the salt of deoxyribose nucleic acid". Need either FTS5 query expansion (synonyms, stemming) or semantic embedding-based search for natural-language queries to work robustly.

3. **`l1_*` fields are null**: The Pydantic schema reserves L1 triple fields (`l1_subject`, `l1_predicate`, `l1_object`, `l2_en`) but the ingestion pipeline doesn't populate them yet. These would normally be derived from L0 JSON via a separate LLM pass. Today, L1/L2 search is not yet queryable — only L0 JSON, source_text, and structured fields work.

4. **`integrity_warning` synthesis**: `get_claim_graph` returns the raw edges with their categories but does not synthesize a top-level natural-language `integrity_warning` field. The synthesis logic would need to inspect edges, find the strongest warning, and return a phrase like "This claim is part of a mediation model — also cite the mediator (rel2)".

5. **No claims_added field on IngestReport**: The script printed `claims_added=?` because the report object exposes warnings/dupes but not a count. Minor UX issue.

## Demo flow (works today)

```python
import sqlite3, sys
sys.path.insert(0, "packages/citare-mcp/src")
from citare_mcp.queries import search_claims, cite_claim, get_claim_graph

conn = sqlite3.connect("data/citare.db")
conn.row_factory = sqlite3.Row

# Q: "What does the literature say about psychological safety and learning?"
results = search_claims(conn, iv="team_psychological_safety", dv="team_learning_behavior")
# → edmondson1999_rel2 (B=.76, p<.01, n=51)

# Check integrity warnings before citing
graph = get_claim_graph(conn, "edmondson1999_rel2", depth=2)
# → finds: rel2 → rel5 [effect_disappears_under_control] (efficacy effect vanishes when controlling for safety)
# → finds: def1 → rel2 [hub_component] (psych_safety is the IV, also cite the definition)

# Get the full citation
citation = cite_claim(conn, "edmondson1999_rel2")
# → source_text (quote), source_page=355, safe_verbs=["is associated with", "correlates with"]
# → design_basis=cross_sectional → AI must NOT say "causes"
```

## Status: Production-ready for the defined scope

The v0.13d → SQLite → MCP read-path is fully functional. The remaining gaps (cross-paper citation resolution, semantic search, L1 triples, top-level integrity synthesis) are L2 product features, not blockers for the core value proposition: **structured claim extraction with integrity warnings that prevent misleading citations**.

## What to do next (not done in this session)

- [ ] Expand corpus: ingest the user's ZENTech psychological-safety library (~50 papers in `\ZENTech\研究開発\`)
- [ ] Run citation resolver with LLM batch on the 258 pending edges
- [ ] Add FTS5 query expansion for natural-language search
- [ ] Populate L1/L2 triples via a follow-on LLM pass
- [ ] Build the demo UI / one-command CLI wrapper
