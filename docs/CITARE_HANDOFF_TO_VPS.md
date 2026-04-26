# Citare VPS Handoff — Read This First

**Audience**: the AI/engineer deploying Citare onto a VPS.
**Read order**: this file first. Everything else is a deeper reference.
**Repo state at handoff**: 2026-04-26, schema changes landed, 81-paper extractions ready
to ingest, smoke tests pass, MCP server (stdio + HTTP/SSE) ready, **production prompt
locked at v0.13g × effort=none**.

---

## 1. Mission in one paragraph

You are deploying Citare — a structured-claim database with an MCP server (read +
write tools). Its value is *citation-safety metadata* (`safe_verbs`, integrity
warnings, lifecycle states) that prevents downstream LLMs from over-citing or
causally upgrading claims. Read-path serves AI applications that need to cite
academic papers honestly. Write-path lets new extractions land into the graph.
The original team has finished v1; your job is to expose it as a public-or-tenant
MCP service over HTTP/SSE, with auth, TLS, and operational hygiene.

---

## 2. What you are receiving (file inventory)

### 2.1 Required (must ship)

```
packages/citare-core/         # Pydantic schemas (Paper, Claim, Equation, …)
packages/citare-db/           # SQLite schema + ingest + parser + resolver
packages/citare-mcp/          # MCP server (stdio + http_server.py for SSE)

data/citare.db                # 1.5 MB starter seed: 13 benchmark papers ingested.
                              # Manifest references 81 papers total; run
                              # scripts/ingest_v013d_champions.py to grow DB to 81.

scripts/ingest_v013d_champions.py    # Reads manifest, ingests all listed extractions
scripts/rebuild_manifest.py          # Scans runs/, rebuilds CITARE_REGISTRATION_MANIFEST.json
scripts/run_heuristic_resolver.py    # Consume pending_llm_review heuristically
scripts/smoke_test_mcp.py            # 6 logic-level tests, no live server needed

experiments/prompts/v0.13g_thinking_defensive.md
                              # THE production prompt. Use this if you re-extract papers.
                              # v0.13d (older) is preserved for comparison; do not use it.

experiments/CITARE_REGISTRATION_MANIFEST.json
                              # 81 papers (13 benchmark + 68 batched). Each entry's
                              # extraction_path is RELATIVE to repo root.

experiments/runs/*_v013d_*/extraction.json
                              # All 81 extractions. NOT in git but read via Dropbox.

docs/                         # 8 design + handoff docs (see §3 for read order)
```

### 2.2 Optional but useful

```
experiments/runs/*_R8[012]_v013*_*/extraction.json
                              # Effort-tuning experiment runs (R80/R81/R82).
                              # Useful only if you want to reproduce the
                              # v0.13g × none decision audit (~$170 of API spend).
```

### 2.3 Don't bother shipping

```
experiments/prompts/v0.{1..21}*.md, v0.13a/b/c/d/e/f/h*.md, v0.16*.md
                              # ~30 rejected/superseded prompt variants. Confusing if shipped.
                              # Only v0.13g_thinking_defensive.md is the production prompt.

experiments/runs/*_R*_v0{1..12}*  experiments/runs/*_R*_v016*_*  experiments/runs/*_R8[012]*
                              # Old variant runs and effort-test runs.

experiments/_ai_workspace/    # Build logs, internal scratch.
_ai_workspace/                # External review download cache.
pdfs/                         # ~hundreds of MB. Only needed if you re-extract.
```

---

## 3. Reading order (do this first, in this order)

| # | File | Why | Length |
|---|------|-----|-------:|
| 1 | `docs/CITARE_MCP_DEPLOYMENT_BRIEF.md` | Defines what you do and what you must NOT change | ~1900 words |
| 2 | `docs/CITARE_SYSTEM_DESIGN.md` | The architecture (10 sections, schema, query paths, gaps) | ~10 sections |
| 3 | `docs/CITARE_MCP_TOOL_CONTRACTS.md` | Per-tool I/O contracts with real example responses | ~2400 words |
| 4 | `docs/CITARE_VPS_DEPLOYMENT.md` | Concrete steps: install, systemd, nginx/caddy, claude.ai | walkthrough |
| 5 | `experiments/PRODUCTION_CHAMPION.md` | Why v0.13g × effort=none is the locked combo | ~1 page |
| 6 | `docs/HANDOFF_REPLY_TO_VPS_2026-04-26.md` (pt.1) | Manifest + git/Dropbox file-flow policy | ~600 lines |
| 7 | `docs/HANDOFF_REPLY_TO_VPS_2026-04-26_pt3.md` | Final lock decision (supersedes pt.2) | ~400 lines |
| ⚠ | `docs/HANDOFF_REPLY_TO_VPS_2026-04-26_pt2.md` | **OBSOLETE** — corrected by pt.3. Audit-trail only. |

**Optional deeper reads** (only if a question needs it):
- `experiments/R82_GRID_RESULTS.md` — full empirical data behind the prompt/effort lock
- `experiments/EFFORT_COMPARISON.md` — earlier (smaller-n) effort tuning report
- `experiments/STRATEGIC_FINDINGS.md` — the 30-prompt tournament that produced v0.13d/g
- `_ai_workspace/external_review/CITARE_DESIGN_REVIEW_FOR_BUILDERS.md` — outside critique

---

## 4. The locked extraction config (do not negotiate)

**Prompt**: `experiments/prompts/v0.13g_thinking_defensive.md`
**Effort**: `none` (= no `--effort` flag to Claude CLI = no `thinking` parameter to Anthropic API)
**Model**: `claude-opus-4-7`

Performance envelope on the 6-paper R82 test panel:
- Coverage: 97.4 ± 4.4%
- Cost: $1.19 ± 0.27 per paper
- Duration: 312 ± 54s per paper
- EXIST claims (the integrity scaffolding): 16.7 per paper average
- Thesis-level losses across 6 papers: **0**

Full Anthropic API call template:
```python
client.messages.create(
    model="claude-opus-4-7",
    max_tokens=32768,                                # 64K for safety on long papers
    temperature=0.0,
    # NO `thinking` parameter — extended thinking is disabled
    system=[{"type": "text",
             "text": Path("experiments/prompts/v0.13g_thinking_defensive.md").read_text(),
             "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": [
        {"type": "document", "source": {"type": "base64",
                                          "media_type": "application/pdf",
                                          "data": pdf_b64}},
        {"type": "text", "text": "Extract claims from this paper."},
    ]}],
)
```

Why this config (one-paragraph version):
- **v0.13g** = v0.13d (the prior production prompt) + an "anti-compression rule" in the
  EXISTENCE_CLAIM section that tells the model not to fold sub-findings into META_CLAIMs.
- **effort=none** = no extended thinking, because extended thinking introduces a
  compression failure mode that costs thesis-level claims (Hubinger Sleeper Agents'
  "persists through training", Edmondson's H3 mediation) on a small but important
  fraction of papers. R82 grid (n=72) confirmed this.

---

## 5. Schema ↔ prompt ↔ DB integrity (load-bearing concept)

This is the most important architectural fact. Internalise it before changing anything.

```
                  ┌──────────────────────────┐
                  │  citare-core/models.py    │  ← 1 Pydantic class plays
                  │  Pydantic v2 schemas      │
                  └────────────┬─────────────┘     three roles:
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
   Prompt output spec   Ingest validator     DB column shape
   (what LLM emits)     (Extraction.         (the SQL columns
                         model_validate())    are these fields)
```

**Implication**: changing the prompt = changing Pydantic = changing SQL = a migration.
All three live in lock-step. There is no mapping or translation layer between them.
See `CITARE_SYSTEM_DESIGN.md §1` for the rationale and the bug class this prevents.

**Therefore**:
- Don't tweak prompts in production. Use v0.13g.
- If you ever must change the prompt, change Pydantic and SQL in the same PR and re-ingest.
- The prompt's JSON output shape **is** the DB shape. They are not separately maintained.

---

## 6. Five gotchas you'll hit

| # | Symptom | Why | What to do |
|---|---------|-----|------------|
| 1 | Some extraction.json has `extraction_prompt_version: v0.12e` or `v0.13d` | Two are legacy; new ones say v0.13g. The string is cosmetic, the body matters | Ignore. Pydantic doesn't read this field for routing |
| 2 | Old extraction JSONs have `"author_framing"` (not `"author_framing_observed_only"`) | Schema rename happened mid-project | Already handled: `Field(alias="author_framing")` accepts both names |
| 3 | Old extraction JSONs include `l1_subject`, `l1_predicate`, `l2_en`, etc. | These columns were dropped in the recent schema cleanup | Already handled: Pydantic `extra="allow"` accepts and discards them |
| 4 | Old extraction JSONs lack `claim_status`, `inclusion_policy_tier` | Added in recent schema | Already handled: Pydantic defaults to `current` and tier `3` |
| 5 | SSE connection from claude.ai mysteriously disconnects after ~30s | Reverse-proxy buffering kills long-lived SSE | Set `proxy_buffering off;` in nginx, or use caddy which handles SSE by default. See `CITARE_VPS_DEPLOYMENT.md` |

---

## 7. First-day deployment smoke (run these in order)

```bash
# 0. Verify Python (3.11+ recommended)
python --version

# 1. Editable install of the three packages
pip install -e packages/citare-core packages/citare-db packages/citare-mcp

# 2. Logic smoke test (no server needed) — must pass 6/6
python scripts/smoke_test_mcp.py

# 3. (Optional) Re-create DB from scratch — proves the ingest path works
cp data/citare.db data/citare.db.bak       # safety
python scripts/ingest_v013d_champions.py   # drops and re-ingests from manifest
python scripts/run_heuristic_resolver.py   # consumes pending_llm_review

# 4. Start HTTP server in foreground (one terminal)
export CITARE_API_KEY=changeme
export CITARE_DB=data/citare.db
python -m citare_mcp.http_server --port 8765

# 5. From another terminal, hit it
curl http://localhost:8765/health
# → {"status":"ok","db":"...","auth_required":true,"read_only":false}

curl http://localhost:8765/sse --max-time 2
# → 401 unauthorized (correct)

curl -H "Authorization: Bearer changeme" http://localhost:8765/sse --max-time 3
# → SSE handshake: "event: endpoint\ndata: /messages/?session_id=…"
```

If all five steps pass, the local stack is healthy. From here it's pure VPS-ops:
systemd unit, TLS termination, claude.ai connector configuration. All in
`CITARE_VPS_DEPLOYMENT.md`.

---

## 8. What you may decide on your own

VPS-operational details are yours to choose:
- Port, bind address, TLS termination
- Auth scheme (default: Bearer API key; OAuth is acceptable for claude.ai connector)
- Whether to expose `register_claims` publicly (recommend `--read-only` for public,
  write only via private endpoint)
- Database path (`/var/lib/citare/citare.db` is conventional)
- Reverse proxy choice (nginx, caddy, traefik)
- Logging stack, metrics endpoint, alerting
- Backup strategy (SQLite is a single file; daily rsync is sufficient)

---

## 9. What you must NOT change (invariants)

These are load-bearing for citation safety. Changing them breaks the product.

| Invariant | Where it lives | Why |
|-----------|----------------|-----|
| Pydantic schemas | `packages/citare-core/src/citare_core/models.py` | Three-role contract (§5) |
| `_safe_verbs(causal_strength, template_type)` function | `packages/citare-mcp/src/citare_mcp/queries.py` | The single function preventing causal upgrade |
| 10 incompleteness categories | `packages/citare-db/.../schema.py` `incompleteness_vocabulary` | Operationalises "claims that can't safely stand alone" |
| `claim_status` 5-state lifecycle | `claims.claim_status` | Retraction / supersedence / replication tracking |
| WARNING-not-REJECT ingestion | `packages/citare-db/.../ingest.py` | Soft errors don't block ingest; only structural errors raise |
| 5-tier paper identifier ladder | `_IDENTIFIER_PRIORITY` in `ingest.py` | Resolves DOI/arXiv/PMID/synthetic to one canonical |
| `paper_identifiers.source` excludes `'human_review'` | `schema.py` CHECK constraint | LLM-native invariant; `'human_expert'` is reserved instead |
| `author_framing_observed_only` is NEVER used by `_safe_verbs` | `queries.py` | This field is a bias-vector; do not let it influence citation |
| **Production extraction prompt = v0.13g** | `experiments/prompts/v0.13g_thinking_defensive.md` | Locked after R82 grid. Do not regress to v0.13d. |
| **Production extraction effort = none** | (no `--effort` flag) | Locked after R82. `low/medium` cause thesis-level miss with v0.13g |

If you have a reason to change one of these, escalate first. Don't silent-rewrite invariants.

---

## 10. Future work (you may, but need not, implement)

In rough priority order:

1. **L2 / paper-title indexing in FTS5** — `sleeper` (Hubinger title) fails because FTS only
   indexes source_text + l0 concepts. A `papers_fts` table would help.
2. **LLM-batch resolver for `pending_llm_review`** — currently 258 entries with no consumer.
3. **Embedding-based search overlay** — sentence-transformers + sqlite-vec for true
   synonym retrieval ("Turing machine" ↔ "halting problem")
4. **OAuth integration** — for direct claude.ai connector use without API-key sharing
5. **Per-field provenance in `cite_claim`** — currently `effective_causal_strength` is
   computed from claim+paper inheritance, but the API doesn't expose which field came
   from which level
6. **R74: cogsci 残り46本 expansion** — extracts via v0.13g × none, registers through
   HTTP `register_claims`. Lets the graph grow beyond the seed.
7. **Auto re-extract trigger for hed-claim audit FAILs** — currently the audit is
   one-shot Python; could be wired into the ingest pipeline as an "auto-flag
   low-confidence extractions" gate.

---

## 11. Where to escalate

- **System design questions**: `docs/CITARE_SYSTEM_DESIGN.md` (10 sections cover most)
- **Tool I/O contracts**: `docs/CITARE_MCP_TOOL_CONTRACTS.md`
- **Production champion rationale**: `experiments/PRODUCTION_CHAMPION.md`
- **Strategic decisions log**: `experiments/STRATEGIC_FINDINGS.md`
- **Effort/prompt audit trail**: `docs/HANDOFF_REPLY_TO_VPS_2026-04-26_pt3.md` (final),
  pt.2 (obsolete), pt.1 (manifest + flow policy)
- **External critique**: `_ai_workspace/external_review/CITARE_DESIGN_REVIEW_FOR_BUILDERS.md`

If a question isn't answered in the docs, ask the original team. Don't guess at invariants.

---

*Generated 2026-04-26 by the original Citare team. Docs are honest about gaps;
ship Citare like that, not as a marketing document.*
