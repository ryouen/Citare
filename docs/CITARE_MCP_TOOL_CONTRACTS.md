# Citare MCP Tool Contracts

Formal per-tool contracts for the MCP tools exposed by the Citare server. The /mcp surface (`packages/citare-mcp/src/citare_mcp/fastmcp_server.py`) exposes **8 tools** as of 2026-05-13. This document covers the original four in depth; the four added since are covered briefly at the end, with source code as the canonical contract.

**Companion docs**: `CITARE_MCP_DEPLOYMENT_BRIEF.md` (deployment posture), `CITARE_SYSTEM_DESIGN.md` (full design), `REGISTRATION_PATHS.md` (the three register paths /sse, /mcp, /api/register).

**Tool catalogue** (all exposed on `/mcp` Streamable HTTP):

| Tool | Kind | Section in this doc |
|------|------|---------------------|
| `search_claims` | Read | §1 |
| `cite_claim` | Read | §2 |
| `get_claim_graph` | Read | §3 |
| `register_claims` | Write | §4 |
| `get_extraction_prompt` | Read | §5 |
| `get_pdf_acquisition_guide` | Read | §6 |
| `audit_papers` | Read (new 2026-05-13) | §7 |
| `report_extraction_failure` | Write (new 2026-05-13) | §8 |

**Read-vs-write convention**: Read tools (`search_claims`, `cite_claim`, `get_claim_graph`, `get_extraction_prompt`, `get_pdf_acquisition_guide`, `audit_papers`) are side-effect-free. Write tools (`register_claims`, `report_extraction_failure`) mutate state (the DB and the incident log respectively). The HTTP server's `--read-only` flag hides `register_claims` from `tools/list` and rejects it at `tools/call`. Public deployments should set `--read-only`; trusted ingest goes through a separate non-read-only instance (or local stdio).

---

## 1. `search_claims`

### Brief
Search claims by free-text query, exact paper DOI, IV/DV concept name, or template type. Returns up to `limit` matching claims with their full inline payload (no per-row joins to `papers`).

### When to call
- Discovery: "find all claims about psychological safety" → `iv="team_psychological_safety"`
- Browsing a paper: "show all RELATIONs from Edmondson 1999" → `doi="10.2307/2666999", template_type="RELATION"`
- Free-text from a draft sentence: "what evidence is there for chain-of-thought prompting?" → `query="chain of thought"`
- Always call this BEFORE `cite_claim` — `cite_claim` requires a `claim_id` you got from search.

### Input schema (JSON Schema)
```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "description": "Free-text FTS5 search on source_text"},
    "doi": {"type": "string", "description": "Exact paper DOI (the canonical paper_id)"},
    "iv": {"type": "string", "description": "Independent variable concept name, substring match"},
    "dv": {"type": "string", "description": "Dependent variable concept name, substring match"},
    "template_type": {"type": "string", "enum": ["DEFINITION","RELATION","EXISTENCE_CLAIM","META_CLAIM"]},
    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
  }
}
```

At least one of `query | doi | iv | dv | template_type` must be provided. The server raises `ValueError` (becomes a JSON-RPC error) if all are absent.

### Output schema (descriptive)
Array of claim objects:
```
[{
  id: str,
  paper_id: str,
  template_type: "DEFINITION" | "RELATION" | "EXISTENCE_CLAIM" | "META_CLAIM",
  l0_json: object,           // template-specific payload (parsed)
  source_text: str | null,
  source_page: int | null,
  source_section: str | null,
  evidence_type: str | null,
  verification_status: enum | null,
  causal_strength: object | null,
  method_metadata: object | null,
  confidence_score: float | null
}, ...]
```

### Idempotency / side effects
Pure read. Safe to retry. No DB writes.

### Authentication
Any authenticated request. Standard read-scoped Bearer key.

### Sort order
- With `query`: FTS5 `bm25(claims_fts)` ascending (most relevant first).
- Without `query`: `confidence_score DESC NULLS LAST`.

### Example request
```json
{"name": "search_claims", "arguments": {"iv": "team_psychological_safety", "limit": 2}}
```

### Example response (truncated)
```json
[
  {
    "id": "edmondson1999_rel2",
    "paper_id": "10.2307/2666999",
    "template_type": "RELATION",
    "l0_json": {
      "iv": "team_psychological_safety",
      "dv": "team_learning_behavior",
      "relation": "positive",
      "mediator": null,
      "moderator": null
    },
    "source_text": "Hypothesis 2 (H2): Team psychological safety is positively associated with learning behavior in organizational work teams. ... regressing psychological safety on self-reported team learning behavior shows a significant positive relationship ...",
    "source_page": 355,
    "source_section": "Results: Team Psychological Safety, Efficacy, Learning Behavior, and Performance",
    "evidence_type": "cross_sectional_field",
    "verification_status": "verified_in_paper",
    "causal_strength": {
      "design_basis": "cross_sectional",
      "author_framing_observed_only": "associational",
      "temporal_precedence": "none",
      "manipulation_of_iv": false
    },
    "method_metadata": {"sample_size": 51, "unit_of_analysis": "team", "industry": "manufacturing"},
    "confidence_score": 0.95
  },
  {
    "id": "edmondson1999_rel3",
    "paper_id": "10.2307/2666999",
    "template_type": "RELATION",
    "l0_json": {"iv": "team_psychological_safety", "dv": "team_performance", "relation": "positive", "mediator": "team_learning_behavior"},
    "source_text": "Hypothesis 3 (H3): Team learning behavior mediates between team psychological safety and team performance. ...",
    "source_page": 355,
    "verification_status": "verified_in_paper",
    "causal_strength": {"design_basis": "cross_sectional", "author_framing_observed_only": "associational"},
    "confidence_score": 0.9
  }
]
```

### Failure modes (HTTP)
| Condition | HTTP | JSON-RPC payload |
|---|---|---|
| All inputs absent | `400` | `{"error": "at least one of query / doi / iv / dv / template_type is required"}` |
| Bad bearer | `401` | `{"error": "unauthorized"}` |
| Malformed FTS5 query (e.g. unbalanced quote) | `500` | sqlite3.OperationalError surfaced — caller should retry without quoting |
| `limit > 100` | `400` | inputSchema rejects |

### Performance contract
On the 13-paper / 419-claim DB:
- `iv`, `dv`, `template_type`, `doi` searches: <10 ms p95 (B-tree index on generated columns).
- `query` searches: <30 ms p95 (FTS5 MATCH).

At 10K papers / 300K claims, expect:
- Indexed searches: <50 ms p95.
- FTS5 queries: <200 ms p95.

---

## 2. `cite_claim`

### Brief
Return the **full citation bundle** for one claim by ID. This is the single tool an AI app should call BEFORE producing a citation in user-visible text. It returns the safe-verb whitelist, integrity warnings, paper bibliography, and the verbatim source quote with page number.

### When to call
- Always before writing a citation. The claim row alone (from `search_claims`) does not include integrity warnings or `safe_verbs`.
- When you have a `claim_id` from any source (search result, link from another paper's reference list, prior conversation context).

### Input schema
```json
{
  "type": "object",
  "properties": {"claim_id": {"type": "string"}},
  "required": ["claim_id"]
}
```

### Output schema (descriptive)
```
{
  // Claim columns (parsed JSON for l0_json, l3_json, causal_strength, method_metadata):
  id, paper_id, template_type, l0_json, l3_json,
  source_text, source_page, source_section, source_paragraph,
  evidence_type, verification_status, causal_strength, method_metadata,
  confidence_score, claim_status, superseded_by_claim_id,

  // Joined paper bundle:
  paper: {
    id, canonical_title, authors, year, venue, paper_type, domain,
    default_causal_strength, default_method, inclusion_policy_tier,
    identifiers: [{identifier_type, identifier_value, is_preferred}, ...]
  },

  // Filtered subset of claim_relations where incompleteness_category != 'none':
  integrity_warnings: [
    {source_id, target_id, relation_type, incompleteness_category, context}, ...
  ],

  // CRITICAL — derived server-side, the citation-safety contract:
  effective_causal_strength: { ... merged paper-default and claim-specific ... },
  safe_verbs: [str, ...],

  // True if there are unresolved citation references for this claim's paper.
  // Indicates that integrity_warnings may not include all cross-paper signals.
  integrity_warnings_partial: bool
}
```

### Side effects
Pure read.

### Authentication
Any authenticated request.

### Example request
```json
{"name": "cite_claim", "arguments": {"claim_id": "edmondson1999_rel2"}}
```

### Example response (truncated)
```json
{
  "id": "edmondson1999_rel2",
  "paper_id": "10.2307/2666999",
  "template_type": "RELATION",
  "l0_json": {"iv": "team_psychological_safety", "dv": "team_learning_behavior", "relation": "positive"},
  "l3_json": {
    "effect_size": 0.76, "effect_size_type": "B", "p": 0.01, "n": 51, "r_squared": 0.63,
    "models": [
      {"label": "Table 5 Panel A Model 1 (self-report learning DV)", "effect_size": 0.76, "p_marker": "p<.01"},
      {"label": "Table 5 Panel B Model 1 (observer-assessed learning DV)", "effect_size": 0.46, "p_marker": "p<.01"}
    ]
  },
  "source_text": "Hypothesis 2 (H2): Team psychological safety is positively associated with learning behavior ...",
  "source_page": 355,
  "source_section": "Results: Team Psychological Safety, Efficacy, Learning Behavior, and Performance",
  "verification_status": "verified_in_paper",
  "causal_strength": {"design_basis": "cross_sectional", "author_framing_observed_only": "associational", "manipulation_of_iv": false},
  "claim_status": "current",
  "paper": {
    "id": "10.2307/2666999",
    "canonical_title": "Psychological Safety and Learning Behavior in Work Teams",
    "authors": ["Amy Edmondson"],
    "year": 1999,
    "venue": "Administrative Science Quarterly",
    "default_causal_strength": {"design_basis": "cross_sectional", "author_framing_observed_only": "associational"},
    "identifiers": [{"identifier_type": "doi", "identifier_value": "10.2307/2666999", "is_preferred": 1}]
  },
  "integrity_warnings": [
    {"source_id": "edmondson1999_exist1", "target_id": "edmondson1999_rel2", "relation_type": "qualifies", "incompleteness_category": "boundary_condition"},
    {"source_id": "edmondson1999_rel2", "target_id": "edmondson1999_rel5", "relation_type": "qualifies", "incompleteness_category": "effect_disappears_under_control"},
    {"source_id": "edmondson1999_def1", "target_id": "edmondson1999_rel2", "relation_type": "part_of_model", "incompleteness_category": "hub_component"},
    {"source_id": "edmondson1999_rel2", "target_id": "edmondson1999_rel3", "relation_type": "part_of_model", "incompleteness_category": "hub_component"},
    {"source_id": "edmondson1999_rel2", "target_id": "edmondson1999_rel8", "relation_type": "supports", "incompleteness_category": "hub_component"}
  ],
  "effective_causal_strength": {"design_basis": "cross_sectional", "author_framing_observed_only": "associational", "manipulation_of_iv": false},
  "safe_verbs": ["is associated with", "correlates with"],
  "integrity_warnings_partial": true
}
```

### How to use the response
- **`safe_verbs`**: pick one. The list is the union of grammatically honest verbs for this claim's `(template_type, design_basis)`. For this Edmondson cross-sectional finding, "causes" is NOT in the list and the citing AI must not introduce it.
- **`integrity_warnings`**: if non-empty, the citation is unsafe to stand alone. Each warning category implies a specific remedial action — see `CITARE_MCP_DEPLOYMENT_BRIEF.md §3` for the severity table. For this claim, the `effect_disappears_under_control` warning means the citation must mention that controlling for `team_efficacy` (`rel5`) attenuates the effect.
- **`effective_causal_strength`**: the merged value. If the claim itself doesn't specify `design_basis` (which is common — papers usually set it once at the paper level), this field shows what was inherited from `paper.default_causal_strength`. The `safe_verbs` derivation uses this merged value, not the raw claim field.
- **`integrity_warnings_partial: true`**: there exist unresolved cross-paper references for this claim's paper. The integrity warnings shown are intra-paper only; cross-paper signals (replication, retraction, etc.) may be missing.

### Failure modes (HTTP)
| Condition | HTTP | Payload |
|---|---|---|
| `claim_id` not found | `200` | `{"error": "claim not found: <id>", "claim_id": "<id>"}` (200 not 404 — JSON-RPC convention; check `error` field) |
| Missing `claim_id` arg | `400` | inputSchema rejects |
| Bad bearer | `401` | `{"error": "unauthorized"}` |

### Performance contract
- 13-paper DB: <20 ms p95 (one PK lookup, one join, one filter).
- 10K-paper DB: <100 ms p95.

---

## 3. `get_claim_graph`

### Brief
BFS the local neighborhood of a claim along `claim_relations` edges, up to `depth` hops. Returns nodes, all edges traversed, and the integrity-warning subset (edges where `incompleteness_category != 'none'`).

### When to call
- After `cite_claim` returns `hub_component` or `effect_disappears_under_control` warnings, call this to enumerate the related claims that must also be cited.
- For visualizing or auditing a claim's full intellectual context.

### Input schema
```json
{
  "type": "object",
  "properties": {
    "claim_id": {"type": "string"},
    "depth": {"type": "integer", "minimum": 1, "maximum": 3, "default": 1}
  },
  "required": ["claim_id"]
}
```

`depth = 1` returns immediate neighbors. `depth = 2` follows edges from those neighbors as well. `depth = 3` is the hard cap (BFS is exponential in graph density).

### Output schema (descriptive)
```
{
  claim_id: str,           // the seed claim
  nodes: [{id, template_type, l0_json, paper_id, verification_status}, ...],
  edges: [{source_id, target_id, relation_type, incompleteness_category, context}, ...],
  warnings: [{source_id, target_id, category, context}, ...]   // edges with incompleteness_category != 'none'
}
```

`nodes` includes the seed claim. `edges` includes both inbound and outbound.

### Side effects
Pure read.

### Authentication
Any authenticated request.

### Example request
```json
{"name": "get_claim_graph", "arguments": {"claim_id": "edmondson1999_rel3", "depth": 2}}
```

### Example response (truncated to first 5 nodes / 4 edges)
```json
{
  "claim_id": "edmondson1999_rel3",
  "nodes": [
    {"id": "edmondson1999_def1", "template_type": "DEFINITION", "paper_id": "10.2307/2666999", "verification_status": null,
     "l0_json": {"concept": "team_psychological_safety", "key_elements": [...]}},
    {"id": "edmondson1999_def2", "template_type": "DEFINITION", "paper_id": "10.2307/2666999",
     "l0_json": {"concept": "team_learning_behavior", ...}},
    {"id": "edmondson1999_exist1", "template_type": "EXISTENCE_CLAIM", "paper_id": "10.2307/2666999", "verification_status": "verified_in_paper",
     "l0_json": {"phenomenon": "study_design_limitation_cross_sectional_no_causality", "evidence": "Author explicitly states ..."}},
    {"id": "edmondson1999_rel2", "template_type": "RELATION", "paper_id": "10.2307/2666999"},
    {"id": "edmondson1999_rel1", "template_type": "RELATION", "paper_id": "10.2307/2666999"}
  ],
  "edges": [
    {"source_id": "edmondson1999_rel1", "target_id": "edmondson1999_rel3", "relation_type": "part_of_model", "incompleteness_category": "hub_component"},
    {"source_id": "edmondson1999_rel2", "target_id": "edmondson1999_rel3", "relation_type": "part_of_model", "incompleteness_category": "hub_component"},
    {"source_id": "edmondson1999_exist1", "target_id": "edmondson1999_rel3", "relation_type": "qualifies", "incompleteness_category": "boundary_condition"},
    {"source_id": "edmondson1999_meta1", "target_id": "edmondson1999_rel3", "relation_type": "aggregates", "incompleteness_category": "none"}
  ],
  "warnings": [
    {"source_id": "edmondson1999_rel1", "target_id": "edmondson1999_rel3", "category": "hub_component"},
    {"source_id": "edmondson1999_rel2", "target_id": "edmondson1999_rel3", "category": "hub_component"},
    {"source_id": "edmondson1999_exist1", "target_id": "edmondson1999_rel3", "category": "boundary_condition"},
    {"source_id": "edmondson1999_def1", "target_id": "edmondson1999_rel2", "category": "hub_component"}
  ]
}
```

### Failure modes (HTTP)
| Condition | HTTP | Payload |
|---|---|---|
| `claim_id` has no edges | `200` | `{"claim_id": "...", "nodes": [<just the seed>], "edges": [], "warnings": []}` |
| `depth < 1` | `400` | `{"error": "depth must be >= 1"}` |
| `depth > 3` | `400` | inputSchema rejects |
| Bad bearer | `401` | `{"error": "unauthorized"}` |

### Performance contract
- 13-paper DB, depth=2: <30 ms p95.
- 10K-paper DB with average claim degree ~3, depth=2: <200 ms p95. depth=3 may grow to seconds on hub claims; the API caps at 3 to bound the worst case.

---

## 4. `register_claims`

### Brief
Register an LLM-extracted claim bundle (as Pydantic `Extraction` JSON) into the database. The single write tool. WARNING-not-REJECT semantics: soft problems land in `IngestReport.warnings` and the row is still inserted; only structural violations error.

### When to call
- After running the v0.13d extraction prompt against a new PDF and receiving the JSON output.
- Idempotent: re-registering the same `Extraction` updates existing rows (claim IDs are stable). No "already exists" error.
- NOT for partial updates. Send the whole envelope per paper.

### Input schema
```json
{
  "type": "object",
  "properties": {
    "json_data": {"type": "string", "description": "Extraction JSON envelope as string"}
  },
  "required": ["json_data"]
}
```

The `json_data` string must validate against the `citare_core.Extraction` Pydantic model:
```
{
  paper: {doi?, title, authors[], year?, venue?, paper_type?, default_causal_strength?, default_method?, ...},
  claims: [{id, template_type, l0_json, source_text?, source_page?, ...}, ...],
  claim_relations: [{source_id, target_id, relation_type, incompleteness_category?, context?}, ...],
  measurement_methods: [{id, measures, instrument_name, ...}, ...],
  paper_references: [{raw_reference_text, ...}, ...],
  extraction_prompt_version?: str
}
```

### Output schema
```
{
  paper_id: str,                  // canonical paper identifier (from the 5-tier ladder)
  created_paper: bool,            // true if a new papers row was inserted
  warnings: [str, ...],           // soft problems (overwrite, dupes, etc.)
  potential_duplicate_claims: [{existing_id, incoming_id, iv, dv}, ...]
}
```

### Side effects
- Inserts/updates rows in `papers`, `paper_identifiers`, `claims`, `claims_fts`, `claim_relations`, `measurement_methods`, `citation_text`, optionally `pending_llm_review`.
- Recomputes `is_preferred` flags on `paper_identifiers` if a higher-priority identifier arrived in this extraction.
- Idempotent: same `Extraction.json` → same DB state.

### Authentication
**Write-scoped Bearer key only.** When the server is started with `--read-only`, this tool is filtered out of `tools/list` and the `tools/call` returns `{"error": "register_claims disabled (read-only mode)"}`. The recommended deployment is two endpoints:
- Public read-only on a public port.
- Private write-enabled on a localhost-bound port or behind tighter auth.

### Example request (minimal valid extraction)
```json
{
  "name": "register_claims",
  "arguments": {
    "json_data": "{\"paper\": {\"doi\": \"10.9999/smoke_test_2026\", \"title\": \"Smoke Test Paper\", \"authors\": [\"Test Author\"], \"year\": 2026, \"paper_type\": \"empirical\", \"default_causal_strength\": {\"design_basis\": \"rct\", \"author_framing\": \"causal\"}}, \"claims\": [{\"id\": \"smoketest_2026_rel1\", \"template_type\": \"RELATION\", \"l0_json\": {\"iv\": \"smoketest_input\", \"dv\": \"smoketest_output\", \"relation\": \"increases\"}, \"source_text\": \"In our randomised experiment, the input increased the output by 50%.\", \"source_page\": 1}], \"extraction_prompt_version\": \"smoke_test_v1\"}"
  }
}
```

### Example response
```json
{
  "paper_id": "10.9999/smoke_test_2026",
  "created_paper": true,
  "warnings": [],
  "potential_duplicate_claims": []
}
```

After re-running the same call, response becomes:
```json
{
  "paper_id": "10.9999/smoke_test_2026",
  "created_paper": false,
  "warnings": ["claim_overwrite: smoketest_2026_rel1"],
  "potential_duplicate_claims": []
}
```

### Failure modes (HTTP)
| Condition | HTTP | Payload |
|---|---|---|
| `json_data` not valid JSON | `200` | `{"error": "Expecting value: line 1 column 1 (char 0)"}` (JSON-RPC convention) |
| Pydantic validation fails (e.g. duplicate claim ids in one envelope, missing required field, bad enum value) | `200` | Pydantic ValidationError surfaced — caller should fix the extraction and retry |
| FK violation (e.g. `claim_relations.source_id` references a claim not in this envelope and not in DB) | `500` | sqlite3.IntegrityError — extraction is structurally broken, do not retry without fixing |
| `--read-only` mode | `200` | `{"error": "register_claims disabled (read-only mode)"}` |
| Bad bearer | `401` | `{"error": "unauthorized"}` |

### Performance contract
No SLA. A typical paper (~30 claims, ~25 relations, ~20 references) takes 50-200 ms. Very large extractions (200+ claims) may take seconds. Long-tail latency dominated by FTS5 index updates.

---

## 5. `get_extraction_prompt`

Returns the canonical v0.13g extraction prompt verbatim, plus sub-agent invocation guidance and SHA-256 (for Pattern 2 / Pattern 3 transcription verification). No input parameters. See `packages/citare-mcp/src/citare_mcp/guides.py:get_extraction_prompt` for the response shape; the prompt itself is at `packages/citare-mcp/src/citare_mcp/assets/extraction_prompt_v0.13g.md` (Pattern 1: sub-agent fetches via MCP — recommended). The response includes a `downstream_impact_note` and `usage` field describing how to dispatch a sub-agent.

## 6. `get_pdf_acquisition_guide`

Returns the PDF acquisition playbook (Stages 0-7: local search → direct OA → CrossRef → Unpaywall → web search → site-specific gotchas). No input parameters. Used when `search_claims` returns 0 hits and the orchestrator needs to acquire a PDF before extraction.

## 7. `audit_papers`

**Added 2026-05-13.** Batch-checks Citare registration status for up to 200 DOIs in a single call. Replaces N round-trip `search_claims` calls for citation-checking workflows.

### Input
```json
{"dois": ["10.xxx/yyy", "10.aaa/bbb", ...]}
```

### Output
```json
{
  "results": [{
    "doi": "10.xxx/yyy",
    "status": "REGISTERED" | "NOT_REGISTERED",
    "paper_id": "...",        // if REGISTERED
    "claim_count": 47,
    "confidence_tier": "HIGH" | "MEDIUM" | "LOW",
    "recommended_action": "RE_EXTRACT" | "ACQUIRE_AND_REGISTER" | null,
    "flags_count": 0,
    "paper_versions": { ... }  // only if a paper_equivalence is registered
  }, ...],
  "summary": {
    "total": 47,
    "by_tier": {"HIGH": 31, "MEDIUM": 8, "LOW": 4, "NOT_REGISTERED": 4},
    "action_required_count": 8
  }
}
```

Quality tier and recommended action use the same `compute_paper_quality_from_db` logic as `register_claims`' response, including SILENT_DAMAGE_SUSPECTED (added 2026-05-14) which compares current claim_count to the paper's all-time peak.

## 8. `report_extraction_failure`

**Added 2026-05-13.** Third option for a sub-agent that has run out of context budget mid-extraction. Lets the agent report the failure structurally instead of compressing claims (anti-pattern) or abandoning silently (anti-pattern).

### Input
```json
{
  "paper_doi": "10.xxx/yyy",
  "stage": "extracting_section_4_discussion",
  "claims_completed": 23,
  "reason": "context budget exhausted at page 19/30",
  "partial_extraction_available": false
}
```

### Output
```json
{
  "acknowledged": true,
  "incident_id": "I-2026-05-13-0042",
  "no_partial_registration": true,
  "advice_for_parent": {
    "retry_strategy_code": "SECTION_FILTERED" | "SMALLER_PAPER" | "NO_RETRY",
    "retry_parameters": {...},
    "estimated_tokens_for_retry": 50000
  }
}
```

Records the incident to `data/extraction_incidents.jsonl` (bind-mounted, persists across container restarts). No partial DB writes are made — all-or-nothing semantics of `register_claims` are preserved.

## Additions to `register_claims` responses (2026-05-13 / 2026-05-14)

The `register_claims` response gained a `paper_quality` block since the original contract above:

```json
"paper_quality": {
  "confidence_tier": "HIGH" | "MEDIUM" | "LOW",
  "observation_count": 1,
  "claim_count": 47,
  "flags": [
    {"code": "LOW_CLAIM_COUNT" | "LOW_MEAN_CONFIDENCE" | "LOW_DENSITY" |
              "DISPUTED_CLAIMS" | "SILENT_DAMAGE_SUSPECTED",
     "severity": "WARN" | "STRONG", ...numerical context...}
  ],
  "recommended_action": "RE_EXTRACT" | "ACQUIRE_AND_REGISTER" |
                        "REVIEW_DISPUTED_CLAIMS" | null
}
```

Additional `warnings` codes that may appear (all non-blocking, server-side normalisations):
- `claim_id_cross_paper_collision_renamed`: incoming claim_id collided with another paper; renamed to `<id>_<paper-hash>`
- `paper_type_synonym_coerced`, `incompleteness_category_misuse_coerced`: enum normalisation
- `source_page_string_coerced`, `sample_size_string_coerced`, `l3_additional_string_coerced`: type coercion

`paper_versions` block (since 2026-05-13): if the paper has a registered `paper_equivalence` (preprint/published pair, duplicate, reissue), the response — and `search_claims` / `cite_claim` / `audit_papers` results — include a `paper_versions` field with `this_paper_role`, `canonical_paper_id`, `alternate_versions`, and an `advisory` string for the consumer to surface.

---

## Cross-tool notes

### Concurrency
SQLite is single-writer; concurrent `register_claims` calls serialise. Concurrent reads parallelise. The default journal mode is WAL — readers don't block writers.

### Caching
Read responses are safe to cache by request hash. `cite_claim` and `get_claim_graph` responses change only on `register_claims` writes; suggest 5-minute TTL on a public endpoint with low write volume.

### Versioning
This contract is implicit version 1. Any change to a tool's input schema, output structure, or auth requirement requires a new tool name (e.g., `cite_claim_v2`) — do not break the contract in place. Adding a new optional field to a response is non-breaking.

### Logging recommendations
Per request, log: tool name, claim_id (if applicable), paper_id (for writes), warning count, latency. Do NOT log: full source_text (PII for some corpora), bearer token, full JSON payloads of writes (use a hash).
