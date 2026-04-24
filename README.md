# Citare

> *DOI is for papers. Citare is for claims.*

Citare is a knowledge-graph database for **scholarly claims** — the atomic units of scientific argument that AI systems quote, summarise, and combine every day. Built during the *Built with Opus 4.7* hackathon (April 2026).

## The problem

Modern AI applications cite academic work at scale. Three failure modes are common:

1. **Silent causal upgrade.** A paper says *"X is associated with Y (cross-sectional, N=150)"*. The citing AI says *"X causes Y"*. The paper's own caveats about design basis and temporal precedence evaporate.
2. **Mediation dropout.** A paper shows *"X → M → Y, direct effect X→Y becomes null with M controlled"*. Citation extracts only the bivariate headline and loses the attenuation.
3. **Restatement propagation.** A paper introduces a complex theorem and later restates it in simpler form for a Discussion section. Downstream citations chase the simplified form and lose the theorem's actual conditions.

None of these are hallucinations of non-existent content — they are selective readings of real content. Which makes them harder to detect than pure fabrication.

## What Citare does

Citare extracts claims with enough structured metadata that a citing agent can tell itself *"this is a cross-sectional association, don't write it as causal"* or *"this effect disappears when X is controlled, mention that"* at citation time. The core data model:

```
Paper (peer-reviewed, DOI-keyed)
   └─ Claim (DEFINITION | RELATION | EXISTENCE_CLAIM | META_CLAIM)
         ├─ L0 (structured — iv/dv for RELATION)
         ├─ L1 (triple — for graph traversal)
         ├─ L2 (natural language)
         ├─ L3 (statistics + equations with equation_status)
         ├─ source_text (fair-use quote)
         ├─ causal_strength (design_basis, author_framing, temporal_precedence, manipulation_of_iv)
         ├─ verification_status (verified_in_paper | proposed_in_paper | not_supported | ...)
         └─ ClaimRelation edges with incompleteness_category
                            (effect_disappears_under_control | hub_component | boundary_condition | ...)
```

The `causal_strength` JSON and the `incompleteness_category` edges are the two features no other academic infrastructure carries. Together they let an AI answer not just *what does this paper say*, but *what is it safe to say this paper says*.

## Evidence that it works

The heart of Citare is the extraction prompt. We ran 13 real papers and 7 synthetic trap papers through a 9-prompt tournament (`experiments/T7_TOURNAMENT.md`) scored on 5 independent axes:

- `coverage` — weighted recall on must-catch claims
- `middle_coverage` — Lost-in-the-Middle check, same measure on middle-of-document claims
- `integrity_penalty` — fraction of *must-NOT-synthesize* patterns the extractor produced
- `core_eq_fidelity` — token-set LaTeX match on equations classified as `central_contribution` or `supporting_definition`
- `eq_discipline` — fraction of decorative equations (restatements, textbook citations) the extractor correctly skipped

Numbers from the v0.1 tournament on T7 (Opus 4.7, single-shot, effort=none, **N=1**):

| | Text coverage | Middle | Core eq | Eq discipline |
|---|---|---|---|---|
| v0.3 overlooked (text champion) | 100% | 100% | 0% | n/a |
| v0.11 TeX | 80% | 71% | 87% | 33% |
| v0.12e STATUS | 82% | 74% | 92% | **67%** |

**Caveat (from the subsequent N=2 pilot, `experiments/PILOT_V2.md`)**: the single-point estimates above are high-variance on T7. Re-running with two seeds showed v0.3's T7 coverage is **94.6% ± 7.6%** (the 100% was a lucky run), v0.12e vs v0.11 core_eq difference is within within-cell noise, and only the **eq_discipline advantage of v0.12e over v0.11 (50% vs 33%, std=0) is robustly supported**. We are honest about this in `PILOT_V2.md` rather than retrofitting nicer numbers.

No single prompt wins all three axes — LaTeX instructions inherently consume attention that would otherwise go to RELATION extraction. The production config is therefore a **dual-run merge**: v0.3 for claim coverage, v0.12e STATUS for equations, combined at claim-id level. The rationale for v0.12e over v0.11 is the robust discipline advantage (rejects restatements and textbook citations at capture time), NOT the eq_fidelity difference (which is within noise).

The synthetic trap papers directly test classic failure modes:

- `T3_effect_disappears_mediator` — cross-sectional data, author generalises. **Extractor caught the attenuation 100%** and correctly flagged the author's Discussion overclaim as `proposed_in_paper` rather than `verified_in_paper`.
- `T7_scaling_noise` (30p target, 21p compiled) — two counterintuitive findings buried in the middle (more data hurts; larger models fail earlier). **0/9 tested prompts synthesized the common-sense inversion**. Opus 4.7 is faithful to source over its priors.

Full tournament methodology and per-equation breakdowns in `experiments/T7_TOURNAMENT.md`.

## Repository layout

```
citare/
├── packages/
│   ├── citare-core/        # pydantic v2 schemas for Paper, Claim, Relation, CausalStrength, ...
│   ├── citare-db/          # SQLite schema + ingestion from extraction.json
│   └── citare-mcp/         # MCP server — search_claims, cite_claim, get_claim_graph
├── experiments/
│   ├── prompts/            # v0.1 ... v0.13 extraction prompts (10 + a v2 refs-verbatim)
│   ├── harness/            # runner + scorer (5 axes: coverage/middle/integrity/core_eq/discipline)
│   ├── ground_truth/
│   │   ├── real_papers/    # 13 Gold fixtures (Edmondson, Einstein, Vaswani, ...)
│   │   └── trap_papers/    # 7 synthetic traps (T1..T7) authored Gold-first
│   ├── runs/               # 130+ extraction runs with metrics
│   ├── T7_TOURNAMENT.md    # 10-prompt bracket on T7 (N=1, exploratory)
│   ├── PILOT_V2.md         # 3 variants × 3 papers × N=2 noise estimation
│   ├── TRAP_SCORES.md      # T1-T6 small-trap scoring
│   └── STATS_FAIR.md       # apples-to-apples prompt comparison
├── docs/
│   ├── design_spec.md           # full design in 10 parts
│   ├── experiments_v2_plan.md   # rigorous L8 factorial post-hackathon plan
│   └── adrs/                    # 7 Architecture Decision Records
├── scripts/
│   └── seed_citare_db.py   # builds data/citare.db from the runs/
└── pdfs/                   # seed-paper PDFs (fair-use)
```

## Quick start

```bash
# 1. Install the packages
pip install -e packages/citare-core packages/citare-db packages/citare-mcp

# 2. Seed the DB from existing extractions
python scripts/seed_citare_db.py --db data/citare.db

# 3. Run the MCP server
citare-mcp --db data/citare.db
```

With the seeded database you have 28 papers, 580+ claims, and 350+ claim-relations with integrity warnings.

## Three MCP tools

```python
# search_claims: find claims by query, doi, iv, dv, or template_type
search_claims(query="psychological safety", template_type="RELATION", limit=10)

# cite_claim: full citation bundle — source_text, paper info, integrity warnings, safe_verbs
cite_claim(claim_id="edmondson1999_rel3")
#   → includes "effect_disappears_under_control" warnings on the direct path
#   → safe_verbs based on design_basis: ["predicts", "precedes", ...] for longitudinal
#                                       ["is associated with", ...] for cross-sectional

# get_claim_graph: local neighbourhood with integrity warnings
get_claim_graph(claim_id="edmondson1999_rel3", depth=1)
#   → nodes + edges + warnings[] listing hub_component / mediation edges
```

## License

MIT — see [LICENSE](./LICENSE). All code, prompts, and synthetic trap papers in this repository were written from scratch during the Built-with-Opus-4.7 hackathon (2026-04-21 through 2026-04-26).

## Hackathon status

- **Model**: Opus 4.7 (1M-context) for every extraction and every tournament run
- **Cost so far**: ~$130 across 100+ prompt-experiment runs, ~$10 for final tournament + cross-validation
- **Seed data**: 28 papers ingested from tournament runs (14 real peer-reviewed + 7 synthetic traps + duplicates across prompt versions)
- **Status**: MVP complete — citare-core + citare-db + citare-mcp all functional end-to-end
