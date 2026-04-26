# Citare System Design — DB & MCP Server

**Status**: Production-ready for read-path. Last verified 2026-04-26 against `data/citare.db` (13-paper starter seed; manifest references 81 papers total).
**Production prompt** (locked 2026-04-26 by R82 grid n=72): `experiments/prompts/v0.13g_thinking_defensive.md` × `effort=none`. See `experiments/PRODUCTION_CHAMPION.md`.
**Codebase**: `packages/citare-core` (schemas, 280 LOC), `packages/citare-db` (storage, 1240 LOC), `packages/citare-mcp` (server, 373 LOC).

---

## 1. Why Citare exists (the design problem)

LLM-generated citations regularly suffer four predictable failure modes:

1. **Causal silent upgrade**: a cross-sectional finding ("X is associated with Y") gets cited as "X causes Y".
2. **Hub-component miscitation**: a single arrow from a multi-step model gets cited alone (e.g., "psych safety → performance" without mentioning the learning-behavior mediator).
3. **Effect-disappears-under-control occlusion**: a bivariate finding gets cited even though the same paper shows the effect vanishes when control variables are added.
4. **Fabricated quotes / wrong page numbers**: the LLM "remembers" a citation that doesn't exist or attributes it to the wrong section.

Citare is a structured database whose *primary value-add is the metadata that prevents these failures*. The schema, ingestion logic, and MCP API are designed around this single goal: any AI app querying Citare gets back not just a claim, but enough integrity context that mis-citing it becomes unnatural.

---

## 2. Three-layer architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1 — citare-core (Pydantic v2 schemas)                     │
│   Paper · Claim · ClaimRelation · Equation · MeasurementMethod   │
│   CausalStrength · MethodMetadata · L0/L3Json · 8 enum classes    │
│   Single source of truth for shape: prompt output → ingest → DB  │
└──────────────────────────────────────────────────────────────────┘
                                 │ Extraction.model_validate()
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 2 — citare-db (SQLite storage + ingestion + resolver)     │
│   schema.py    272 LOC: 15 tables, FTS5, generated cols, CHECKs  │
│   ingest.py    492 LOC: identifier-aware paper resolution        │
│   parser.py    194 LOC: deterministic bibliographic-string parser│
│   resolver.py  258 LOC: citation_text → citation_edges chain     │
└──────────────────────────────────────────────────────────────────┘
                                 │ sqlite3.Connection
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3 — citare-mcp (MCP stdio server)                         │
│   queries.py   232 LOC: search_claims, cite_claim,               │
│                          get_claim_graph, _safe_verbs            │
│   server.py    138 LOC: MCP protocol wrapper, tool registry      │
└──────────────────────────────────────────────────────────────────┘
```

**Key design property**: The Pydantic schemas in Layer 1 are simultaneously the **prompt output spec** (what v0.13d emits), the **ingestion validator** (`Extraction.model_validate(json)` runs at ingest), and the **DB-column shape** (one name per concept, no mapping layer). This eliminates schema drift between extraction and storage.

---

## 3. Data model deep-dive

### 3.1 Paper identity (the hardest part)

A paper is an *intellectual work*, not a file. The same paper can be referred to by multiple identifiers across time:
- Journal DOI: `10.2307/2666999`
- arXiv DOI: `10.48550/arXiv.1706.03762`
- arXiv id: `arxiv:1706.03762`
- PMID: `pmid:12345678`
- ISBN: `978-...`
- Internal synthetic (when none of the above exist): `_no_doi_edmondson_1999_9f3a2b`

**Resolution model**:

```
papers (id PK)
   ↑ N:1
paper_identifiers (identifier_type + identifier_value PK,
                   paper_id FK, is_preferred 0|1, source, verified_at)
```

Exactly one row per paper has `is_preferred = 1`, enforced by:
```sql
CREATE UNIQUE INDEX idx_one_preferred_per_paper
    ON paper_identifiers(paper_id) WHERE is_preferred = 1;
```

**Priority ladder** (`ingest._IDENTIFIER_PRIORITY`):
```
doi > arxiv_doi > arxiv > pmid > isbn > internal_synthetic
```
Recomputed on every ingest. If a paper that was registered by `internal_synthetic` later gains a DOI from a separate extraction, the DOI becomes the new preferred identifier; the synthetic ID stays as an alias.

**Synthetic ID rule** (when no real identifier is present):
```
_no_doi_{first_author_surname_lower}_{year}_{title_sha256_first_6_hex}
```
Deterministic across re-extractions of the same paper (same surname + year + title → same synthetic ID).

**Content hash** (`title|first_author|year`, SHA-256 first 16 hex chars) lets the ingester catch a possible duplicate even when no identifier overlaps — emits a `paper_possible_duplicate` warning, does NOT auto-merge.

**Starter DB state shipped in repo** (13 benchmark papers; manifest references 81):
```
identifier_type    count  preferred
doi                  6      6     # Edmondson, Einstein, Watson-Crick, Turing,
                                  # Park, T7 (synthetic DOI 10.9999/trap...)
arxiv_doi            3      3     # Vaswani, Wei, Hubinger
internal_synthetic   4      4     # Barney, Hayes, Noy/Zhang, Shannon
```

### 3.2 Claim 4-level abstraction (L0 → L1 → L2 → L3)

```
L0 (structured payload, varies by template_type)
   DEFINITION:      {concept, key_elements[]}
   RELATION:        {iv, dv, relation, mediator?, moderator?}
   EXISTENCE_CLAIM: {phenomenon, evidence?}
   META_CLAIM:      {integrated_finding?, scope?}

L1 (RDF-style triple — UNUSED in MVP)
   l1_subject, l1_predicate, l1_object

L2 (natural-language label, EN/JA — UNUSED in MVP)
   l2_en, l2_ja

L3 (effect-size statistics)
   {effect_size, p, ci_lower, ci_upper, n, r_squared, mediation, models[]}
```

**Current state**: L0 100% populated (419/419 claims). L1/L2 are 0% populated — reserved for a future LLM pass. L3 populated only for RELATION claims with effect statistics.

The MVP queries reach into L0 via SQLite generated columns (no separate table joins):
```sql
iv_idx              GENERATED ALWAYS AS (json_extract(l0_json, '$.iv'))   VIRTUAL
dv_idx              GENERATED ALWAYS AS (json_extract(l0_json, '$.dv'))   VIRTUAL
design_basis_idx    GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL
author_framing_idx  GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL
```
All four are indexed. This is the trick that makes `search_claims(iv="team_psychological_safety")` a B-tree lookup, not a JSON scan.

### 3.3 Causal strength (Citare's core differentiator)

Every claim carries a 4-field block:
```python
class CausalStrength(BaseModel):
    design_basis: str | None        # how the study was built
    author_framing: str | None      # how the author phrases it
    temporal_precedence: str | None # whether time-order is established
    manipulation_of_iv: bool | None # whether IV was controlled by experimenter
```

**Seven canonical `design_basis` values** (open vocabulary, validated against `DesignBasis` enum at write time):
- `rct` — randomised controlled trial
- `longitudinal`
- `quasi_experimental`
- `cross_sectional`
- `meta_analysis`
- `computational_demonstration` — ML benchmarks, simulations
- `theoretical` — pure formal/conceptual work, no empirical test

**Current DB distribution** (across 419 claims, 144 with non-null design_basis):
```
theoretical                    53   (Einstein, Turing, Watson-Crick, Shannon)
computational_demonstration    43   (Vaswani, Wei, Hubinger, Park)
rct                            27   (Hubinger AI safety experiments,
                                      Noy/Zhang field experiment)
cross_sectional                12   (Edmondson)
meta_analysis                   6   (Park)
longitudinal                    2
quasi_experimental              1
```

**The point of design_basis**: it determines `safe_verbs` (see §6.4). A `cross_sectional` claim returns `["is associated with", "correlates with"]` regardless of how the author phrases it. This is the single rule that prevents downstream LLMs from upgrading "associated" → "causes".

### 3.4 Verification status

```python
class VerificationStatus(Enum):
    verified_in_paper      # backed by paper's own data
    proposed_in_paper      # author's hypothesis or theoretical claim
    not_supported
    mixed_support
    partial_support
```

**Current DB**: 218 `verified_in_paper`, 94 `proposed_in_paper`, 107 null (mostly DEFINITIONs which are unverifiable in the empirical sense).

The hedging-gate (introduced in v0.13d, retained in the v0.13g production prompt) is precisely the rule that prevents `verified_in_paper` from being over-applied to theoretical papers — it forces `proposed_in_paper` whenever the source text contains "we assume", "we postulate", "is suggested by", etc.

### 3.5 Five incompleteness categories (the integrity layer)

Stored on `claim_relations.incompleteness_category`:

| Category | Trigger | Why it matters when citing |
|----------|---------|----------------------------|
| `effect_disappears_under_control` | A's effect on B vanishes when control C is added | Citing A→B alone is misleading; mention C |
| `hub_component` | A is part of a multi-step / mediated model | Cite the chain, not just one arrow |
| `boundary_condition` | A holds only under specific conditions / sample / scope | State the boundary when citing |
| `extends_prior_definition` | A redefines or refines a concept from prior work | Note the definitional shift |
| `none` | Clean relation, no warning needed | — |

**Current DB** (340 relations):
```
none                              141
hub_component                     115   (most common — most claims sit in models)
boundary_condition                 73
extends_prior_definition            8
effect_disappears_under_control     3   (rarest, strongest warning)
```

These five categories are the *operationalisation* of "claims that can't safely stand alone" — every miscitation pattern Citare prevents reduces to one of them.

### 3.6 Relation types

`claim_relations.relation_type` (free-form string at the DB layer, validated against `RelationType` enum at the Pydantic layer):

```
supports          112
part_of_model      92
qualifies          65
background         31
extends            22
aggregates          8   # used by META_CLAIM nodes
replicates          7
apparent_tension    3
```

A single edge can carry both a `relation_type` (the structural verb) and an `incompleteness_category` (the integrity warning). E.g., `(rel2 → rel5, qualifies, effect_disappears_under_control)` means "rel5 qualifies rel2 in a way that triggers the effect-disappears warning".

---

## 4. SQLite schema (15 tables)

### 4.1 Core tables (populated)

| Table | Rows | Purpose |
|-------|-----:|---------|
| `papers` | 13 | One row per intellectual work; PK `id` is the preferred identifier value |
| `paper_identifiers` | 13 | All known aliases per paper, exactly one preferred |
| `claims` | 419 | The unit of structured knowledge; FK to papers |
| `claims_fts` | 419 | FTS5 virtual table for free-text search |
| `claim_relations` | 340 | Edges between claims with incompleteness category |
| `citation_text` | 258 | Verbatim References section entries + parser output |
| `citation_edges` | 0 | Resolved cross-paper citations (LLM-batch pending) |
| `pending_llm_review` | 258 | Queue for LLM-resolved citations / dupes / aliases |
| `measurement_methods` | 68 | Per-paper instruments (scales, benchmarks, datasets) |

### 4.2 Future-shape tables (empty in MVP, schema frozen)

| Table | Purpose | Populated by |
|-------|---------|--------------|
| `concepts` | Canonical concept names + aliases | Future canonicalisation pass |
| `theories` | Named theoretical frameworks | Today, theories are emitted but not persisted |
| `paper_versions` | Preprint vs published, etc. | Future versioning support |
| `revision_history` | LLM-native audit log (every write) | Future write APIs |
| `concept_evolution` | Definition drift over years | Batch analysis |
| `theory_concept_roles` | Concept membership in theories | Future phase |

These are pre-declared so the schema doesn't need migrations when those features land.

### 4.3 Key constraints (CHECK enums in SQL)

```sql
template_type IN ('DEFINITION','RELATION','EXISTENCE_CLAIM','META_CLAIM')

verification_status IN ('verified_in_paper','proposed_in_paper','not_supported',
                        'mixed_support','partial_support') OR NULL

incompleteness_category IN ('effect_disappears_under_control','hub_component',
                            'boundary_condition','extends_prior_definition','none')

paper_identifiers.identifier_type IN ('doi','arxiv','arxiv_doi','pmid','isbn',
                                       'internal_synthetic')

paper_identifiers.source IN ('extraction','batch_llm_review','crossref','openalex')
                          OR NULL  -- LLM-native: no human input ever

resolution_method IN ('doi_match','arxiv_match','year_author_title',
                      'crossref','openalex','llm_batch') OR NULL
```

Source field is intentionally restricted to LLM-native channels — there is no `human_review` value. This forces the system to remain machine-auditable.

### 4.4 Indexes

**Paper / claim**:
- `idx_papers_content_hash` — content_hash (dedup)
- `idx_papers_year`
- `idx_ident_paper` — paper_identifiers.paper_id (reverse lookup)
- `idx_one_preferred_per_paper` — partial unique on `is_preferred = 1`
- `idx_claims_paper`, `idx_claims_template`
- `idx_claims_subject`, `idx_claims_object` (currently unused, L1 not populated)
- `idx_claims_iv`, `idx_claims_dv` (generated columns)
- `idx_claims_design_basis`, `idx_claims_author_framing`

**Relations**:
- `idx_relations_incompleteness` — partial index where `incompleteness_category != 'none'` (only the 199 warning edges, not all 340)

**Citations**:
- `idx_cite_text_paper`, `idx_cite_text_parsed_doi`, `idx_cite_text_parsed_year`
- `idx_cite_edge_paper` (resolved_paper_id)
- `idx_pending_type` (review_type, resolved_at)

### 4.5 FTS5 virtual table

```sql
CREATE VIRTUAL TABLE claims_fts USING fts5(
    claim_id UNINDEXED,
    source_text,
    l2_en,
    l1_subject,
    l1_object,
    tokenize = 'unicode61'
);
```

**Currently UNUSED by the MCP query path** — `search_claims(query=...)` does literal `LIKE '%...%'` on source_text + l2_en + l1_subject + l1_object instead of FTS5 MATCH. This is a known production gap; FTS5 is populated at ingest but not queried. See §8.

---

## 5. Ingestion pipeline

`scripts/ingest_v013d_champions.py` → `citare_db.ingest_extraction_file()` → `ingest_extraction()`.

### 5.1 Paper resolution (3-tier)

```
1. Try paper_identifiers match by any (type, value) on incoming Paper.
   ↓ miss
2. Try content_hash match (title|first_author|year SHA-256 prefix).
   On match: WARN "paper_possible_duplicate", do NOT auto-merge.
   ↓ miss
3. Create new paper. choose_paper_id() picks highest-priority identifier
   from the incoming list, or generates a synthetic id if none.
```

**WARNING-not-REJECT policy**: Soft problems (overwrite an existing claim, possible duplicate paper, missing fields) are recorded in `IngestReport.warnings` but do NOT block the insert. Only structural violations (FK fails, CHECK fails) cause SQLite to raise. This makes ingestion resilient to LLM output variability.

### 5.2 Claim ingestion

```python
for c in extraction.claims:
    # (iv, dv) duplicate detection — informational only
    if (iv, dv) seen on existing claim of same paper:
        report.potential_duplicate_claims.append(...)

    if claim.id already exists:
        report.warn("claim_overwrite", claim_id=c.id)

    INSERT INTO claims (...) ON CONFLICT(id) DO UPDATE SET ...
    INSERT INTO claims_fts (...)
```

Claim IDs are deterministic if the extraction prompt uses `claim_id_for(doi, template, seq)` (see `citare-core/claim_id.py`):
```
{doi_sha256_first_8}-{template_letter}-{seq:03d}
e.g.  a3f7c92e-R-012  =  RELATION claim #12 from paper hashing to a3f7c92e
```
However, v0.13d output uses author-year-style IDs like `edmondson1999_rel2`, `wei2022_def1` — same uniqueness guarantee, just human-readable. Either form is accepted.

### 5.3 Relations / methods / references

```
claim_relations:        INSERT OR REPLACE on (source_id, target_id, relation_type) PK
measurement_methods:    INSERT OR REPLACE on (paper_id, id) PK
paper_references:       parser.parse() → INSERT INTO citation_text
                                          (raw + parsed_doi/arxiv/year/authors/title)
```

The `paper_references` step writes ONLY to `citation_text` (the immutable raw layer). Resolution to `citation_edges` is a separate, idempotent post-pass (see §6).

---

## 6. Citation resolver chain

`resolver.resolve_citations()` walks every `citation_text` row and tries to link it to a canonical `papers.id`.

### 6.1 Stage 1 — identifier match

```
IF parsed_doi → look up in paper_identifiers WHERE type='doi'
   confidence = 1.0, method = 'doi_match'

ELIF parsed_arxiv → look up in paper_identifiers WHERE type IN ('arxiv','arxiv_doi')
   confidence = 1.0, method = 'arxiv_match'
```

### 6.2 Stage 2 — (year + first_author_surname + title) triple match

```
candidates = papers WHERE year == parsed_year
             AND first_author_surname == parsed_author[0]
             AND title_jaccard_overlap(parsed_title, paper_title) >= 0.4

IF len(candidates) == 1:
   resolve, method = 'year_author_title', confidence = jaccard

IF len(candidates) > 1:
   IF top_jaccard - second_jaccard >= 0.2:
      resolve to top, method = 'year_author_title', confidence = top_jaccard
   ELSE:
      enqueue to pending_llm_review with reason='ambiguous_triple_match'
```

### 6.3 Stage 3 — queue to pending_llm_review

Anything that survives Stages 1 and 2 lands here with `reason='no_deterministic_match'` and a payload containing the raw text + parsed fields + citing_paper_id. **No LLM is called here** — this is just the queue. A separate batch reviewer service is responsible for consuming it.

### 6.4 Current resolver state

```
total citation_text:     258
parsed_doi present:        6   (2.3% — DOIs rarely appear verbatim in 1950s+
                                style references; modern CS papers fare better)
parsed_year present:     256   (99.2%)
parsed_authors present:   83   (32.2%)
citation_edges resolved:   0
pending_llm_review:      258  (all queued with reason='no_deterministic_match')
```

The resolver is correct but the input data is degraded: most citations in this 13-paper corpus are inside-paper references to *other* canonical works (Bandura 1982, Hackman 1990, etc.) that are NOT in the DB. Stage 2 fails because the cited papers don't exist as `papers` rows. The pipeline is working as designed — it's queuing them up for an LLM batch reviewer that hasn't been built yet.

---

## 7. MCP server (Layer 3)

### 7.1 Transport modes

**Local stdio MCP** (`packages/citare-mcp/src/citare_mcp/server.py`):
```bash
citare-mcp --db data/citare.db
```
Standard MCP stdio protocol. Exposes the read tools and (when not `--read-only`) `register_claims`. Useful for local CI / scripted ingest.

**HTTP/SSE MCP** (`packages/citare-mcp/src/citare_mcp/http_server.py`):
```bash
citare-mcp-http --db data/citare.db --port 8765
```
MCP SSE transport over HTTPS. The public read endpoint runs unauthenticated; an admin endpoint with `--key-registry` exposes write tools (`register_claims`, `extract_and_register`) behind Bearer auth + per-key budget. See §8 for deployment posture.

### 7.2 Tool 1: `search_claims`

```python
search_claims(
    conn,
    query: str | None = None,        # free-text LIKE %...% (substring only)
    doi: str | None = None,          # exact paper_id match
    iv: str | None = None,           # LIKE on l1_subject OR json_extract($.iv)
    dv: str | None = None,           # LIKE on l1_object OR json_extract($.dv)
    template_type: str | None = None,
    limit: int = 20,
) -> list[dict]
```

**Required**: at least one of `query`, `doi`, `iv`, `dv`, `template_type`.
**Sort order**: `confidence_score DESC NULLS LAST`.
**Returns**: list of claim dicts with L0, source_text, source_page, evidence_type, verification_status, causal_strength, method_metadata, confidence_score.

**Index usage**:
- `iv` / `dv` → `idx_claims_iv` / `idx_claims_dv` (B-tree on generated column) → fast
- `template_type` → `idx_claims_template` → fast
- `doi` → `idx_claims_paper` → fast
- `query` → full table scan with LIKE (no FTS5 today) → slow on large DBs

### 7.3 Tool 2: `cite_claim`

```python
cite_claim(conn, claim_id: str) -> dict
```

Returns the **full citation bundle** for one claim:

```python
{
    "id": claim_id,
    "paper_id": ...,
    "template_type": ...,
    "l0_json": {...},
    "source_text": "the verbatim quote",
    "source_page": 355,
    "source_section": "Results",
    "evidence_type": "cross_sectional_field",
    "verification_status": "verified_in_paper",
    "causal_strength": {...},
    "method_metadata": {"sample_size": 51, ...},
    "confidence_score": 0.95,

    "paper": {
        "canonical_title": ...,
        "authors": [...],
        "year": 1999,
        "venue": ...,
        "default_causal_strength": {...},  # paper-level fallback
        "default_method": {...},
        "identifiers": [
            {"identifier_type": "doi", "identifier_value": "10.2307/2666999",
             "is_preferred": 1},
        ],
    },

    "integrity_warnings": [
        {"source_id": ..., "target_id": ..., "relation_type": "qualifies",
         "incompleteness_category": "effect_disappears_under_control",
         "context": null},
        ...
    ],

    "effective_causal_strength": {...},  # claim-level overrides paper-level
    "safe_verbs": ["is associated with", "correlates with"],
}
```

**The `safe_verbs` field is the operative output**. It's derived by `_safe_verbs(effective_causal_strength, template_type)`:

```python
if template_type == "DEFINITION":      return ["defines", "characterises", "operationalises"]
if template_type == "EXISTENCE_CLAIM": return ["reports", "observes", "documents"]
if template_type == "META_CLAIM":      return ["argues", "contends", "proposes"]

else lookup design_basis:
    rct                         → ["causes", "increases", "decreases", "produces"]
    longitudinal                → ["predicts", "precedes", "is associated over time with"]
    quasi_experimental          → ["predicts", "affects"]
    cross_sectional             → ["is associated with", "correlates with"]
    meta_analysis               → ["is associated across studies with", "aggregates to"]
    theoretical                 → ["is claimed to relate to", "is theorised to affect"]
    computational_demonstration → ["is demonstrated computationally to",
                                   "empirically outperforms on"]
```

This is the *single* function that prevents causal upgrade. Any AI app citing through Citare gets `safe_verbs` and is expected to pick from that list, not invent their own verb.

**Inheritance rule**: claim-level `causal_strength` fields override paper-level `default_causal_strength`. If the claim doesn't specify `design_basis` but the paper does, the paper's is used. This lets a Hubinger paper say "RCT" once at the paper level and not repeat it on every RELATION.

### 7.4 Tool 3: `get_claim_graph`

```python
get_claim_graph(conn, claim_id: str, depth: int = 1) -> dict
```

BFS up to `depth` hops along `claim_relations`. Returns:

```python
{
    "claim_id": ...,
    "nodes": [{id, template_type, l1_*, paper_id, verification_status}, ...],
    "edges": [{source_id, target_id, relation_type,
               incompleteness_category, context}, ...],
    "warnings": [{source_id, target_id, category, context}, ...],
}
```

`warnings` is the filtered subset of edges where `incompleteness_category != 'none'`. **Does not synthesise a top-level natural-language summary** — that's a known gap (see §8).

---

## 8. Known production gaps (what's NOT yet built)

### 8.1 Read-path gaps

1. **FTS5 unused**: `claims_fts` is populated but `search_claims(query=...)` uses substring LIKE. Should switch to `claims_fts MATCH ?` for natural-language queries. Easy fix.

2. **No semantic search**: even with FTS5, query "DNA structure" misses Watson-Crick because the source uses "structure of the salt of deoxyribose nucleic acid". Needs synonym expansion or embedding-based retrieval.

3. **L1/L2 fields empty**: `l1_subject`, `l1_predicate`, `l1_object`, `l2_en`, `l2_ja` are 0/419 populated. Indexes exist but never hit. Future LLM pass should canonicalise L0 → L1 triples and L2 natural language labels.

4. **No top-level integrity_warning synthesis**: `get_claim_graph` returns raw edge categories, not phrases like "This claim is part of a mediation model — also cite the mediator (rel2)". The synthesis logic should inspect edges and emit a natural-language warning string the LLM can drop into a citation.

### 8.2 Write-path gaps

5. **`register_claims` not in local server**: only the hosted MCP exposes it (and that's down). Today, ingestion goes through `scripts/ingest_v013d_champions.py` directly, not over MCP.

6. **`citation_edges` 0/258**: the resolver works but every cited paper is outside the corpus. Need either (a) ingest those papers too, or (b) build an LLM batch reviewer that consumes `pending_llm_review`.

7. **`revision_history` empty**: the audit log table is pre-declared but no code writes to it. Adding it requires wrapping every UPDATE in `ingest_extraction` with a history insert.

8. **`concepts` empty**: 419 claims reference concepts via `l0_json.iv`, `l0_json.dv`, `l0_json.concept`, but the `concepts` table is empty. Canonicalisation (mapping `team_psychological_safety` ↔ "psych safety" ↔ "psychological safety in teams") would happen here.

9. **No `register_claims` validation**: the hosted version does CrossRef DOI verification + L1 generation + duplicate detection. The local pipeline skips all three. CrossRef especially matters when a paper-class extraction generates a wrong DOI.

### 8.3 Operational gaps

10. **No backup / migration story**: every re-ingest drops the DB (`db_path.unlink()`). For incremental corpus growth, need an `--no-reset` mode (already wired but untested).

11. **No write APIs at all**: the MCP server is read-only. Any user wanting to edit a claim or add a manual integrity warning has no path.

12. **No LLM batch reviewer**: the 258 pending citation resolutions sit forever unless we build the reviewer.

---

## 9. Production verification (2026-04-26)

The 13-paper champion ingest passes all read-path tests:

```
✅ search_claims(iv="team_psychological_safety")           → edmondson1999_rel2/3
✅ search_claims(template_type="DEFINITION")               → 20 across 5 papers
✅ search_claims(query="chain of thought")                 → wei2022 def1/rel1/def2
✅ search_claims(dv="team_performance")                    → 2 (Edmondson rel1, rel3)
✅ get_claim_graph("edmondson1999_rel3", depth=2)          → 15 edges incl. 4 warnings:
                                                              effect_disappears_under_control,
                                                              hub_component × 7,
                                                              boundary_condition × 5,
                                                              extends_prior_definition × 0
✅ cite_claim("edmondson1999_rel2")                        → safe_verbs=["is associated
                                                              with","correlates with"]
                                                              (cross_sectional → no causal)
                                                            5 integrity_warnings
                                                            source_page=355

❌ search_claims(query="DNA structure")                    → 0 (substring miss; needs FTS5)
❌ search_claims(query="sleeper")                          → 0 (Hubinger source uses
                                                              "sleeper agents" — should hit;
                                                              substring LIKE on l1_*
                                                              fields which are null)
```

`l1_subject`/`l1_object` being empty causes false negatives for free-text query when the term lives in L0 JSON but not source_text. Switching to FTS5 + adding L1 population fixes both.

---

## 10. File map

```
citare-core/
  src/citare_core/
    models.py     # Pydantic schemas (Paper, Claim, Equation, ...)
    enums.py      # 9 enums (TemplateType, VerificationStatus, ...)
    claim_id.py   # deterministic claim ID generator

citare-db/
  src/citare_db/
    schema.py     # SQL DDL (15 tables, FTS5, generated cols, CHECKs)
    ingest.py     # Extraction → DB rows (paper resolution, claim insert)
    parser.py     # raw bibliographic text → ParsedReference
    resolver.py   # citation_text → citation_edges (3 stages)

citare-mcp/
  src/citare_mcp/
    queries.py    # search_claims, cite_claim, get_claim_graph, _safe_verbs
    server.py     # MCP stdio protocol wrapper

scripts/
  seed_citare_db.py            # legacy seeder (uses prompt-priority heuristics)
  ingest_v013d_champions.py    # canonical ingest from CITARE_REGISTRATION_MANIFEST.json (name historical; reads whatever the manifest points to — currently mostly v0.13g)

experiments/
  PRODUCTION_CHAMPION.md       # v0.13d lock decision
  CITARE_INTEGRATION.md        # this session's end-to-end verification
  CITARE_REGISTRATION_MANIFEST.json  # paper → best-run-dir map
  STRATEGIC_FINDINGS.md        # cross-variant analysis

data/
  citare.db                    # 1.48 MB — 13 papers, 419 claims, 340 relations
```
