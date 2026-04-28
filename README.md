# Citare — Citation Integrity for AI Research

> **PDF reading is not claim infrastructure.** Citare turns papers into reusable claim graphs with source quotes, page numbers, safe citation verbs, boundary conditions, and integrity warnings.
>
> Other tools return metadata; **Citare returns the actual claim** — verbatim, with the design-basis context an AI needs to cite it without lying.
>
> *DOI is for papers. Citare is for claims.*

Live MCP endpoint: **`https://citare.dev/mcp`** (Streamable HTTP, no auth required).
Built during the *Built with Opus 4.7* hackathon (April 2026); now in active production.

## The problem

Modern AI applications cite academic work at scale. Three failure modes recur:

1. **Silent causal upgrade.** A paper says *"X is associated with Y (cross-sectional, N=150)"*. The citing AI says *"X causes Y"*. The paper's own caveats about design basis and temporal precedence evaporate.
2. **Mediation dropout.** A paper shows *"X → M → Y, direct effect X→Y becomes null with M controlled"*. The citation extracts only the bivariate headline and loses the attenuation.
3. **Restatement propagation.** A paper introduces a complex theorem and later restates it in simpler form for a Discussion section. Downstream citations chase the simplified form and lose the theorem's actual conditions.

None of these are hallucinations of non-existent content — they are selective readings of real content. Which makes them harder to detect than pure fabrication, and lets them propagate at internet scale.

## What Citare does

Citare extracts claims with enough structured metadata that a citing agent can tell itself *"this is a cross-sectional association, don't write it as causal"* or *"this effect disappears when X is controlled, mention that"* at citation time. The core data model:

```
Paper (peer-reviewed, DOI-keyed)
   └─ Claim (DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM)
         ├─ L0 (structured — iv/dv for RELATION, concept/key_elements for DEFINITION, ...)
         ├─ L3 (statistics + equations with equation_status)
         ├─ source_text (verbatim quote)
         ├─ source_page
         ├─ causal_strength (design_basis, author_framing, temporal_precedence, manipulation_of_iv)
         ├─ verification_status (verified_in_paper | proposed_in_paper | not_supported | ...)
         ├─ traffic_light (green | yellow | red — derived from study design + integrity warnings)
         └─ ClaimRelation edges with incompleteness_category
                            (effect_disappears_under_control | hub_component | boundary_condition | ...)
```

The `causal_strength` JSON, the `traffic_light` derivation, and the `incompleteness_category` edges are the three features no other academic infrastructure carries. Together they let an AI answer not just *what does this paper say*, but *what is it safe to say this paper says*.

## How extraction works (production)

**Locked production config (since 2026-04-26):** prompt **v0.13g** × Claude **Opus 4.7** × `effort=none` (omit both `thinking` and `output_config.effort`). This combination won an N=72 grid (R82) where it Pareto-dominated every other cell on the corpus average of 16.7 EXIST claims/paper with 0 thesis-level misses across 24 cells. The `experiments/` directory carries the full grid + the corrigenda that overturned the prior recommendations.

The prompt itself is shipped as a tool: `get_extraction_prompt()` returns the verbatim ~5,500-token instruction that any LLM can pass to a sub-agent reading a PDF.

## Live MCP tools (6 read+write)

```python
# READ
search_claims(query=..., iv=..., dv=..., doi=..., template_type=..., limit=20)
cite_claim(claim_id, style="apa7"|"chicago"|"harvard"|"vancouver"|"bibtex")
get_claim_graph(claim_id, depth=1)
get_extraction_prompt()             # returns the locked v0.13g prompt
get_pdf_acquisition_guide()         # Stages 0-7 PDF resolution playbook

# WRITE
register_claims(json_data)          # ingest LLM-extracted claims (no auth)
```

`cite_claim` returns the source quote, page number, statistics, the `paper_reference` formatted in five styles, and the `safe_verbs` for the underlying study design. `get_claim_graph` returns the local neighbourhood with integrity warnings (mediation that should be cited together, controls that erase the effect, boundary conditions).

There is also a REST escape hatch at `POST /api/register` (raw `Extraction` body, no `json_data` wrapper) for non-MCP clients and batch dispatchers — see `docs/REGISTRATION_PATHS.md`.

## Repository layout

```
citare/
├── packages/
│   ├── citare-core/        # pydantic v2 schemas — Paper/Claim/Relation/CausalStrength/...
│   ├── citare-db/          # SQLite + FTS5 schema, ingestion with WARNING-not-REJECT
│   └── citare-mcp/         # MCP server (FastMCP + Streamable HTTP) + REST shim
├── experiments/
│   ├── prompts/            # v0.1 → v0.13g extraction prompts (43 revisions tracked)
│   ├── harness/            # runner + scorer (5 axes: coverage / middle / integrity / core_eq / discipline)
│   ├── ground_truth/
│   │   ├── real_papers/    # 13 Gold fixtures (Edmondson, Einstein, Vaswani, Shannon, ...)
│   │   └── trap_papers/    # 7 synthetic traps (T1..T7) authored Gold-first
│   ├── runs/               # 743 extraction runs with metrics (cost, tokens, scores)
│   ├── R82_GRID_RESULTS.md # final 72-cell production-config grid
│   ├── PRODUCTION_CHAMPION.md  # locked config + reasoning
│   ├── CITARE_REGISTRATION_MANIFEST.json  # 81-paper run-to-paper audit trail
│   └── ground_truth/, T7_TOURNAMENT.md, PILOT_V2.md, ...  # tournament + variance studies
├── docs/
│   ├── design_spec.md            # full design in 10 parts
│   ├── REGISTRATION_PATHS.md     # /mcp vs /sse vs /api/register
│   ├── CITARE_SYSTEM_DESIGN.md   # production architecture
│   └── adrs/                     # 7 Architecture Decision Records
├── resources/
│   └── index.html          # citare.dev landing page (i18n EN/JA)
├── scripts/
│   ├── seed_citare_db.py            # build data/citare.db from runs/
│   ├── ingest_v013d_champions.py    # bulk-register from manifest
│   ├── backup_to_dropbox.py         # daily snapshot with tiered retention
│   └── verify_backup_restore.py     # weekly restore verification
└── data/
    └── citare.db           # production SQLite (gitignored)
```

## Quick start

```bash
# Use the live service:
claude mcp add --transport http citare https://citare.dev/mcp

# Or run locally:
pip install -e packages/citare-core packages/citare-db packages/citare-mcp
python scripts/seed_citare_db.py --db data/citare.db
citare-mcp-fastmcp-http --db data/citare.db --port 8765
```

## Hackathon status (current as of 2026-04-28)

- **Model**: Opus 4.7 (1M-context) for every extraction and every tournament run
- **Prompt revisions**: 43 tracked versions (v0.1 → v0.13g), production locked at **v0.13g**
- **Total extraction runs**: 743 (T7 tournament + R61–R85 grids + production registers)
- **Tokens consumed**: 150M+ across all runs
- **Production corpus**: **131 papers, 4,632 claims, 4,651 claim-relations** with integrity warnings (live counts at https://citare.dev/stats)
- **Live endpoints**: `https://citare.dev/mcp` (primary), `https://citare.dev/sse` (deprecated, kept for backwards compat), `https://citare.dev/api/register` (REST)
- **Status**: production — citare-core + citare-db + citare-mcp all functional end-to-end, MCP server serving live traffic, daily backups to Dropbox with weekly restore-verification

## Evidence that the extraction works

The heart of Citare is the extraction prompt. We ran 13 real papers and 7 synthetic trap papers through tournaments scored on 5 independent axes:

- `coverage` — weighted recall on must-catch claims
- `middle_coverage` — Lost-in-the-Middle check on middle-of-document claims
- `integrity_penalty` — fraction of *must-NOT-synthesize* patterns the extractor produced
- `core_eq_fidelity` — token-set LaTeX match on equations classified as `central_contribution` or `supporting_definition`
- `eq_discipline` — fraction of decorative equations correctly skipped (restatements, textbook citations)

The synthetic trap papers directly test classic failure modes:

- `T3_effect_disappears_mediator` — cross-sectional data, author generalises. **Extractor caught the attenuation 100%** and correctly flagged the author's Discussion overclaim as `proposed_in_paper` rather than `verified_in_paper`.
- `T7_scaling_noise` — two counterintuitive findings buried in the middle (more data hurts; larger models fail earlier). **0/9 tested prompts synthesized the common-sense inversion**. Opus 4.7 is faithful to source over its priors.

The R82 production-config grid (n=72, paper × prompt × effort) showed v0.13g × `effort=none` Pareto-dominates all other cells, with 16.7 EXIST claims/paper average and 0 thesis-level misses. Full methodology in `experiments/R82_GRID_RESULTS.md` and `experiments/PRODUCTION_CHAMPION.md`.

## License

MIT — see [LICENSE](./LICENSE). All code, prompts, and synthetic trap papers in this repository were written from scratch during the Built-with-Opus-4.7 hackathon (2026-04-21 → 2026-04-26) and have continued to evolve in production since.
