# Citare MCP Deployment Brief (for the VPS-side AI)

**Audience**: an AI agent (Claude / GPT) running on the VPS that will host Citare as a long-running HTTP/SSE MCP service.
**Companion docs**: `CITARE_MCP_TOOL_CONTRACTS.md` (per-tool contracts), `CITARE_SYSTEM_DESIGN.md` (full design rationale), `scripts/smoke_test_mcp.py` (validation script).
**Last updated**: 2026-04-26 against `data/citare.db` starter snapshot (13 benchmark papers, 419 claims, 340 relations). The shipped manifest references **81 papers total** — VPS should run `scripts/ingest_v013d_champions.py` to grow the DB on initial deployment.
**Production prompt**: `experiments/prompts/v0.13g_thinking_defensive.md` × `effort=none` (locked 2026-04-26 by R82 grid n=72; see `experiments/PRODUCTION_CHAMPION.md`).

---

## §1 Mission

Citare is a structured database of claims extracted from peer-reviewed academic papers, exposed as an MCP server. Its single value-add is the *integrity metadata* attached to every claim — design basis, verification status, and incompleteness warnings — that lets a downstream LLM cite a finding without silently upgrading "is associated with" to "causes", without dropping the mediator from a hub-component model, and without missing the boundary condition under which the effect disappears. You are deploying the public-facing endpoint that any third-party AI app can hit to retrieve safe-to-cite claim bundles.

---

## §2 What you are receiving

| Item | Path | Notes |
|------|------|-------|
| Repo root | `/srv/citare/` (suggested) | Whole CitareOpus47 tree, or just `packages/` + `data/` + `scripts/` |
| Starter DB | `data/citare.db` (~1.5 MB) | 13 papers, 419 claims, 340 relations, 199 with integrity warnings. **Starter corpus only** — you will receive a larger ingest later. |
| DB backup | `data/citare.db.bak.YYYYMMDD_HHMMSS` | Roll-forward reference if a re-ingest goes wrong |
| Python packages | `packages/citare-core/`, `packages/citare-db/`, `packages/citare-mcp/` | Install with `pip install -e packages/citare-core packages/citare-db packages/citare-mcp` |
| Stdio MCP entry point | `citare-mcp --db /var/lib/citare/citare.db` | The local-only stdio transport (defined in `packages/citare-mcp/src/citare_mcp/server.py`) |
| HTTP/SSE MCP entry point | `citare-mcp-http --db ... --port 8765 --api-key SECRET` | Built by sibling agent in `http_server.py`. Exposes `/sse`, `/messages/`, `/health`. Bearer-auth on every path except `/health`. Set `--read-only` to hide `register_claims`. |
| Ingest scripts | `scripts/ingest_v013d_champions.py`, `scripts/seed_citare_db.py` | Use `ingest_v013d_champions.py` to regenerate the DB from `experiments/runs/*/extraction.json` after a schema migration |
| Smoke test | `scripts/smoke_test_mcp.py` | Direct-import logic test — see §6 |

The four MCP tools are: `search_claims`, `cite_claim`, `get_claim_graph`, `register_claims`. Their formal contracts are in `CITARE_MCP_TOOL_CONTRACTS.md`.

---

## §3 Invariants — DO NOT CHANGE

These contracts are load-bearing. Changing any of them silently breaks downstream AI consumers or degrades citation safety. The line between "deployment configuration" (which you may freely change — see §4) and these invariants is hard.

1. **Pydantic schemas in `citare-core`** (`Paper`, `Claim`, `CausalStrength`, `ClaimRelation`, `Extraction`, the eight `*` enums). These are simultaneously the prompt-output spec, the ingestion validator, and the DB column shape. Editing a field name here breaks every extraction prompt and every existing extraction.json on disk. If a real bug forces a change, regenerate `data/citare.db` from `experiments/runs/*/extraction.json` so the on-disk corpus matches the new schema.

2. **The `_safe_verbs(causal_strength, template_type)` function in `packages/citare-mcp/src/citare_mcp/queries.py`**. This is the single function that prevents "associated with" from being upgraded to "causes". Its mapping from `design_basis` to verb list IS the operational core of Citare:
   - `cross_sectional` → `["is associated with", "correlates with"]` (never "causes")
   - `rct` → `["causes", "increases", "decreases", "produces"]` (only here)
   - `theoretical` → `["is claimed to relate to", "is theorised to affect"]` (never empirical)
   - etc. (see `_VERBS_BY_DESIGN` for the full table)
   - `template_type` overrides: `DEFINITION` → `["defines", "characterises", "operationalises"]`, `EXISTENCE_CLAIM` → `["reports", "observes", "documents"]`, `META_CLAIM` → `["argues", "contends", "proposes"]`.
   - Do not add new verbs without an integration test that asserts the new verb is honest for every design_basis it appears under.

3. **`incompleteness_category` semantics — 5 original + 5 added** (see `enums.IncompletenessCategory` and the `incompleteness_vocabulary` seeded table). Severity is the citation-warning intensity (1 = clean, 5 = strongest negative signal):

   | category | severity | meaning |
   |---|---|---|
   | `none` | 1 | clean relation, no warning |
   | `preregistered_confirmed` | 1 | positive integrity signal |
   | `extends_prior_definition` | 2 | refines a prior concept |
   | `boundary_condition` | 3 | holds only under specific scope |
   | `hub_component` | 3 | part of a multi-step model — cite the chain |
   | `underpowered` | 3 | sample size below recommended |
   | `disputed` | 4 | field actively disputes |
   | `effect_disappears_under_control` | 5 | effect vanishes with controls |
   | `failed_to_replicate` | 5 | original effect did not replicate |
   | `retracted` | 5 | citing paper is retracted |

   The vocabulary is open (no SQL CHECK constraint) — adding a new category is `INSERT OR IGNORE INTO incompleteness_vocabulary` plus an enum entry. Renaming or removing one is forbidden: every category appears in extraction outputs already on disk.

4. **`claim_status` lifecycle states**: `current` (default), `superseded`, `retracted`, `failed_to_replicate`, `contested`. These have a SQL CHECK constraint AND a Pydantic enum. Any addition requires a code-and-schema co-change. The `superseded_by_claim_id` FK chains forward through versions; it must always point to a claim of status `current`.

5. **WARNING-not-REJECT ingestion policy**. Soft problems (overwriting a claim, possible duplicate paper, missing optional field) land in `IngestReport.warnings` and the row is still inserted. Only structural violations (FK fail, CHECK fail) raise. This makes ingestion resilient to LLM output variability. Do not "fix" this by adding `if warnings: raise`. The warnings are observability, not gates.

6. **The 5-tier paper identifier ladder** (`ingest._IDENTIFIER_PRIORITY`): `doi > arxiv_doi > arxiv > pmid > isbn > internal_synthetic`. Recomputed on every ingest. Exactly one preferred identifier per paper enforced by `idx_one_preferred_per_paper`. The synthetic ID rule (`_no_doi_{surname_lower}_{year}_{title_sha256_first_6}`) is deterministic and must not be reordered or replaced with a UUID, else re-extracting the same paper would produce a different paper row and break alias-tracking.

7. **`paper_identifiers.source` excludes `human_review` but reserves `human_expert`** (machine-auditable invariant). Allowed values: `extraction | batch_llm_review | crossref | openalex | human_expert | NULL`. The exclusion of `human_review` is intentional — Citare is LLM-native by design, so there is no curator-edit path. `human_expert` is reserved for the future case of a Nobel-laureate equivalent emailing a correction; it is allowed as a one-way door but unused today.

---

## §4 Allowed and expected changes

Anything not listed in §3 is yours to configure for the deployment. Specifically:

- **HTTP transport details**: pick a port (default 8765), bind host (default `0.0.0.0`), terminate TLS at a reverse proxy (Caddy / nginx). The MCP server itself speaks plain HTTP; do not enable HTTPS in the Python process.
- **Authentication scheme**: the sibling agent shipped Bearer-API-key auth on `Authorization: Bearer <key>`. You may swap this for OAuth (claude.ai-compatible flow) or mTLS if your deployment requires it. The middleware is in `_BearerAuthMiddleware` in `http_server.py`; replace it cleanly rather than chaining schemes.
- **Database location**: move `data/citare.db` to `/var/lib/citare/citare.db`, set the path via `--db` flag or `CITARE_DB` env var.
- **Read-only mode**: set `--read-only` (or `CITARE_READ_ONLY=1`) on the public endpoint to hide `register_claims`. Run a separate stdio or local-bound HTTP instance for trusted ingest. This is the recommended posture: writes happen via a secured admin channel, reads are public.
- **Logging / observability**: stdlib logging or structlog or your preferred shape. The MCP layer doesn't emit logs today; instrument at the middleware boundary in `http_server.py`. Do not log the bearer key. Do log: tool name, claim_id (for reads), paper_id and warning count (for writes), 401/403 events.
- **Process supervision**: systemd unit, Docker, k8s — your call. The process is a single uvicorn worker today; multiple workers are safe because every request opens its own SQLite connection (see `_ensure_conn`). Do not switch to a connection pool — it adds no value for SQLite single-file IO.

---

## §5 Tool contract reference

See `docs/CITARE_MCP_TOOL_CONTRACTS.md` for per-tool input/output schemas, side-effect semantics, authentication scope, example requests and responses, failure modes, HTTP status codes, and performance contracts. That document is the source of truth for what each tool returns; this brief covers the deployment posture only.

---

## §6 Smoke test

`scripts/smoke_test_mcp.py` is the validation gate. Run it BEFORE flipping the public endpoint live:

```bash
cd /srv/citare
python scripts/smoke_test_mcp.py --db /var/lib/citare/citare.db
# Should print PASS for all 5 tests and exit 0.
```

The default mode imports `citare_mcp.queries` directly — it tests the **logic**, not the MCP wire protocol. This is sufficient to catch any deployment error in package install, DB schema mismatch, or accidentally-broken queries. The HTTP wire protocol test is documented inside the script as a `TODO` because exercising SSE + JSON-RPC end-to-end requires a running server and a second process; the direct-import path catches every defect that has bitten this codebase to date.

If you want a wire-protocol smoke test against the running HTTP endpoint, the pattern is: POST a JSON-RPC `tools/call` envelope to `/messages/` with the `Authorization: Bearer` header, and `GET /sse` for the response stream. The MCP SDK's `sse_client` helper does this; the smoke test script has a stub showing how. Implementing it fully is a future-work item (see §8).

---

## §7 Operational concerns

**Backup**. SQLite is a single file. Daily `rsync data/citare.db <off-vps>:backups/citare.$(date +%F).db` is sufficient. Use `sqlite3 data/citare.db ".backup data/citare.db.consistent"` if you need a consistent snapshot of an in-flight DB; otherwise rsync of the file is fine because the WAL mode makes torn writes self-recovering on next open. Keep at least 30 daily snapshots.

**Schema migration**. When `citare-core` or `citare-db` is updated, the migration path is:
1. `cp data/citare.db data/citare.db.pre-migration`
2. `rm data/citare.db`
3. `python scripts/ingest_v013d_champions.py` (re-runs the canonical ingest from `experiments/runs/*/extraction.json` — idempotent, claim IDs are stable)

This works because every claim ID is deterministic from `(paper_doi, template, seq)` or author-year (`edmondson1999_rel2`). Re-ingesting the same extraction.json files produces the same DB rows. There is no per-row migration path for production data — the source of truth is the `extraction.json` files in `experiments/runs/`.

**Monitoring**. Useful metrics:
- 200 vs 401 ratio on `/sse` (auth health)
- claim insert rate over time (write-path health, only if `--read-only` is off)
- `pending_llm_review` queue depth (`SELECT COUNT(*) FROM pending_llm_review WHERE resolved_at IS NULL`) — currently 258, growing slowly. If it explodes, the citation resolver upstream broke.
- p95 latency on `cite_claim` and `get_claim_graph`. On the 13-paper DB, both should be <50 ms. On 10K papers, both should still be <500 ms.

**Rate limiting**. Do this at the reverse proxy layer (nginx `limit_req`, Caddy `rate_limit`). Don't add rate-limiting middleware to the Python process — it's the wrong layer. Suggested initial limit: 60 requests / minute / API key.

---

## §8 Future work the VPS-side AI MAY but need not implement

These are improvements the team would welcome but does not require for the VPS deployment to be considered live:

1. **Background batch resolver for `pending_llm_review`**. Today, 258 entries sit in this queue with no consumer. A worker that wakes every hour, batches 50 entries, calls Claude/GPT to resolve each citation against `papers`, and writes back `citation_edges` rows. The heuristic resolver in `scripts/run_heuristic_resolver.py` already handles the easy cases.
2. **L2 natural-language label population**. The `claims.l2_en` column was dropped (Task 65) along with the unused L1 fields. If you want semantic search overlay, add it back as a separate table — do not re-add to `claims`.
3. **Embedding-based search overlay**. `sentence-transformers` to embed `source_text`, `sqlite-vec` extension to store and query vectors. Layer this *after* the FTS5 results, not as a replacement.
4. **OAuth integration for claude.ai direct registration**. The hosted `register_claims` flow on `claude.ai/mcp/CitareMCP` works today via OAuth; the VPS endpoint uses Bearer keys. Adding OAuth lets users register claims without a pre-shared key.
5. **Wire-protocol smoke test**. Promote the `TODO` block in `scripts/smoke_test_mcp.py` to a real SSE round-trip test.

None of §8 is on the critical path. Ship the read-path first, ship `register_claims` second (gated by `--read-only`), and add §8 items as user demand surfaces.
