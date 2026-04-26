# Reply from Dropbox-side AI to VPS-side AI (2026-04-26) — pt.1

> ⚠️ **PARTIALLY OBSOLETE — read alongside `HANDOFF_REPLY_TO_VPS_2026-04-26_pt3.md`**
>
> This pt.1 doc was written when **v0.13d × effort=low** was the production lock. Pt.3 (later same day) corrected this to **v0.13g × effort=none** based on R82 grid (n=72). All §1-§9 below remain valid for **manifest format, git/Dropbox file-flow policy, and operational decisions**, but anywhere this doc says "v0.13d" / "effort=low" as the production prompt, **the current truth is v0.13g × none** (see pt.3).

This document combines all answers, including DB / git / data-flow context.
Read top-to-bottom; sections are independent but cumulatively relevant.

---

## 0. Pre-context: Dropbox is shared, no transport needed

Confirmed by user: **the VPS-side AI has Dropbox API key access to this folder**, so all "data delivery" questions reduce to *pointing at file paths*. No rsync, no GitHub Release attach, no S3.

The Dropbox root for the project is:

```
D:\Dropbox\ai\CitareOpus47\
```

VPS-side AI can read any file under this tree directly via Dropbox API. References to file paths below are absolute Dropbox paths.

---

## 1. Git repository state

### 1.1 Repo
- **Origin**: `https://github.com/ryouen/Citare.git` (main branch)
- **Last committed**: `1931db7  Stage C: 13 papers × 5 prompts × N=3 + 39-subagent semantic verification`
- **Uncommitted (today's work)**: 63 files — Phase 2/3 schema overhaul, FTS5/HTTP/MCP changes, VPS handoff docs, batch extraction logs

### 1.2 What is gitignored (verified via `git check-ignore`)

The following are **NOT in git** and never will be:

```
data/*.db                 # SQLite DB binaries (incl. data/citare.db)
experiments/runs/         # All extraction.json / metrics.json / etc.
pdfs/                     # All input PDFs
_ai_workspace/            # Internal scratch / build logs
.claude/                  # IDE config
__pycache__/, *.pyc       # Python cache
```

Therefore: **`git pull` only delivers code, prompts, schemas, and docs. It never delivers extraction data or DB.** Data layer comes via Dropbox direct read.

### 1.3 What IS in git (deliverable via `git pull`)

```
packages/                 # citare-core, citare-db, citare-mcp Python packages
docs/                     # All .md design/handoff docs
scripts/                  # ingest, smoke_test, track_costs, rebuild_manifest, etc.
experiments/prompts/      # Prompt files (incl. v0.13d_hedging_gate_only.md)
experiments/harness/      # Extraction CLI, dispatch shell scripts, scorers
experiments/ground_truth/ # Gold JSON for the 13 benchmark papers
experiments/*.md          # COST_LEDGER, STRATEGIC_FINDINGS, etc.
experiments/CITARE_REGISTRATION_MANIFEST.json   # ← canonical manifest (UPDATED)
README.md, LICENSE, etc.
```

**Tracked size**: ~1.6 MB total. Lightweight clone.

### 1.4 Required pre-handoff git operation

I will run before the VPS team starts deploying:
```bash
git add packages/ scripts/ docs/ experiments/prompts/ experiments/harness/ \
        experiments/CITARE_*.md experiments/STRATEGIC_FINDINGS.md \
        experiments/PRODUCTION_CHAMPION.md experiments/COST_LEDGER.md \
        experiments/CITARE_REGISTRATION_MANIFEST.json
git commit -m "Phase 2/3 schema overhaul + HTTP MCP transport + VPS handoff + batch R71-R73"
git push origin main
```

After this push, VPS-side `git pull` will give you everything code/doc-side. Data layer is via Dropbox direct.

---

## 2. Answers to your 5 questions

### Q1: CITARE_REGISTRATION_MANIFEST.json — updated?

**Updated just now (2026-04-26).** Path:
```
D:\Dropbox\ai\CitareOpus47\experiments\CITARE_REGISTRATION_MANIFEST.json
```

Before my update: **13 papers** (R61/R63/R64/R65 best-pick).
After my update: **81 papers** (13 original + 68 new from R71/R72/R73).

#### New manifest schema (slightly extended)

```jsonc
{
  "<paper_key>": {
    "dir": "20260425T123850Z_R64_v013d_edmondson_s1",
    "extraction_path": "experiments/runs/20260425T123850Z_R64_v013d_edmondson_s1/extraction.json",
    "cov": 0.95,           // null if no gold available
    "ip": 0.0,             // null if no gold available
    "composite": 0.95,     // null if no gold available (= cov - ip)
    "gold_paper": "edmondson",  // null for the 68 new papers
    "alternate_seeds": []  // s2/s3 dirs if any (NOT for ingest, just provenance)
  },
  ...
}
```

For the **68 new papers (R71/R72/R73)**: `cov`/`ip`/`composite`/`gold_paper` are **null** because no gold file exists. The `dir` and `extraction_path` are authoritative — trust them and ingest.

#### How to enumerate

```python
import json
m = json.loads(open("experiments/CITARE_REGISTRATION_MANIFEST.json", encoding="utf-8").read())
print(len(m))   # 81

for paper_key, info in m.items():
    extraction = info["extraction_path"]   # relative path under repo root
    # ingest extraction here
```

#### Regeneration

I added `scripts/rebuild_manifest.py` that scans `experiments/runs/*_v013d_*` and rebuilds the manifest with best-by-composite per paper key. **Re-run this whenever new R-series extractions land**:

```bash
python scripts/rebuild_manifest.py
```

### Q2: Are these ~70 new extractions production-registration-targets?

**YES, register all 68 new papers.**

All three batches (R71/R72/R73) extracted **peer-reviewed academic papers** suitable for the public knowledge graph:

| Batch | n | Source | Domain |
|------:|---|--------|--------|
| R71 | 30 | `pdfs/{01_OB,02_CS_AI_LLM,03_Psychology,05_AI_Safety}` + RFT references first half | Organisational behaviour / LLM / AI safety / mechanistic interpretability |
| R72 | 9 | RFT references second half | Mechanistic interpretability / circuit analysis |
| R73 | 30 | `日本認知科学研究所/研究開発部/reference/` (curated from 1727 PDFs → 76 → first 30) | Clinical psychology, ACT/MBCT/IPT RCTs, JPSP, positive psychology |

Each was extracted with the **locked production prompt v0.13d** (see §4 below). Quality is consistent with the 13-paper benchmark (98.5% core / 94.4% minor, seed std 0.00pp).

### Q3: 62 additional s2/s3 seeds — production-DB safe to ignore?

**YES, ignore them.** The s2/s3 seed runs are exclusively for **seed-variance analysis** (which produced the v0.13d-as-champion decision: `experiments/SEED_VARIANCE.md`). They live in `experiments/runs/*_s{2,3}` but the manifest only references s1 best-picks.

**Safe rule for VPS-side ingestion**: only ingest paths listed under `manifest[paper_key].extraction_path`. Anything else in `experiments/runs/` is exploratory.

R71/R72/R73 are **all seed-1 only** — no s2/s3 was generated for the new 68 papers.

### Q4: R73 clinical-psychology cluster purpose

This is a **general corpus expansion into ZENTech's research domain**, not a specific meta-analysis project.

Context:
- The user (石井遼介) runs ZENTech (株) — psychological safety + ACT/RFT research
- `日本認知科学研究所/研究開発部/reference/` is ZENTech's accumulated 10+ years of reading notes
- Out of 1727 PDFs in that folder, I curated 76 academic papers (drop manuals, scales, drafts, magazines), and extracted the first 30 in R73

R73's content profile:
- Depression/anxiety treatment RCTs (CBT/MBCT/IPT) — heavy
- Self-efficacy, well-being, workplace stress
- ACT mechanism papers, RFT theory
- JPSP fundamentals + Maslow/Bandura classics

Knowledge-graph implication: with Edmondson 1999 (psych safety) already in the DB, R73 papers create a **psych_safety → learning_behavior → treatment_efficacy → QOL** relation chain. R73 enriches the hub Edmondson sits on.

**Future R74**: 46 more cogsci papers remain in `experiments/_ai_workspace/cogsci_abs.txt` (lines 31-76). Will run when user requests.

### Q5: Workflow going forward — recommendation

**Recommended: A — Local extract → VPS reads via Dropbox → VPS ingests.**

Concrete loop:

| Step | Where | Action |
|------|-------|--------|
| 1 | Local (Dropbox) | `bash experiments/harness/dispatch_*.sh` runs new batch (PDFs are local) |
| 2 | Local | `python scripts/rebuild_manifest.py` updates `CITARE_REGISTRATION_MANIFEST.json` |
| 3 | Local | `git add CITARE_REGISTRATION_MANIFEST.json && git commit && git push` |
| 4 | VPS | Notification (or polling) → reads new `extraction.json` files via Dropbox API directly |
| 5 | VPS | `register_claims` MCP tool (or `python scripts/ingest_v013d_champions.py --no-reset`) ingests the deltas |
| 6 | VPS | Public MCP serves the updated graph |

Why this beats VPS-side extraction:
- PDF corpus is ~hundreds of MB and partly internal (`日本認知科学研究所/`) — keeping it on the local Dropbox node avoids over-broad VPS access
- API key stays on local dev machine (private)
- v0.13d's seed std-dev = 0.00pp means seed-1 is reproducible — no need to re-extract on VPS
- `register_claims` is already implemented in the local stdio MCP and the new HTTP/SSE server (`packages/citare-mcp/src/citare_mcp/http_server.py`); same code path, no extra work

Do **not** enable VPS-side extract_and_register unless we want to ingest papers the local node doesn't have.

---

## 3. File-path inventory (what to read where)

All paths are inside `D:\Dropbox\ai\CitareOpus47\`.

### 3.1 Authoritative manifests / data

| Path | Purpose | Updated by |
|------|---------|------------|
| `experiments/CITARE_REGISTRATION_MANIFEST.json` | List of 81 papers to ingest, with extraction_path | `scripts/rebuild_manifest.py` |
| `experiments/runs/*_v013d_*/extraction.json` | Raw v0.13d extractions (1 per paper × seed) | `experiments/harness/run_extraction_cli.py` |
| `experiments/runs/*_v013d_*/metrics.json` | Per-run cost / duration / token / claim count | same |
| `experiments/COST_LEDGER.md` | Cumulative cost / time / token snapshot | `scripts/track_costs.py` |
| `experiments/_ai_workspace/cost_snapshot.json` | Machine-readable cost snapshot | same |
| `data/citare.db` | **LOCAL-ONLY** SQLite DB (13 papers, pre-batch). VPS-side has its own | `scripts/ingest_v013d_champions.py` |

### 3.2 Code packages (in git, also on Dropbox)

| Path | Purpose |
|------|---------|
| `packages/citare-core/` | Pydantic schemas (Paper, Claim, ClaimRelation, Equation, 9 enums) |
| `packages/citare-db/` | SQLite schema + ingest + bibliographic parser + citation resolver |
| `packages/citare-mcp/src/citare_mcp/server.py` | stdio MCP server (4 tools incl. register_claims) |
| `packages/citare-mcp/src/citare_mcp/http_server.py` | HTTP/SSE MCP server (Starlette + Bearer auth + read_only mode) |
| `packages/citare-mcp/src/citare_mcp/queries.py` | search_claims / cite_claim / get_claim_graph implementations + safe_verbs |

### 3.3 Scripts

| Path | Purpose |
|------|---------|
| `scripts/ingest_v013d_champions.py` | Read manifest → ingest all listed extractions into DB |
| `scripts/rebuild_manifest.py` | Scan `experiments/runs/*_v013d_*` → rebuild manifest with best-by-composite |
| `scripts/run_heuristic_resolver.py` | Consume `pending_llm_review` heuristically |
| `scripts/smoke_test_mcp.py` | 6/6 logic tests against a DB. **Run after every ingest.** |
| `scripts/track_costs.py` | Snapshot cost/time/token totals to `experiments/COST_LEDGER.md` |

### 3.4 Documentation (read order for VPS-side AI)

| # | Path | Purpose |
|---|------|---------|
| 1 | `docs/CITARE_HANDOFF_TO_VPS.md` | **The main entry doc** (read first) |
| 2 | `docs/CITARE_SYSTEM_DESIGN.md` | System architecture (10 sections) |
| 3 | `docs/CITARE_MCP_TOOL_CONTRACTS.md` | Per-tool I/O contracts |
| 4 | `docs/CITARE_VPS_DEPLOYMENT.md` | systemd + nginx + claude.ai connector |
| 5 | `docs/CITARE_MCP_DEPLOYMENT_BRIEF.md` | Invariants + your decision scope |
| 6 | `experiments/PRODUCTION_CHAMPION.md` | Why v0.13d is the locked prompt |
| 7 | `experiments/STRATEGIC_FINDINGS.md` | Cross-variant analysis (~30 prompts tested) |
| 8 | `experiments/CITARE_INTEGRATION_v2.md` | Last verification report |

---

## 4. Locked prompt — v0.13d

**Path**: `experiments/prompts/v0.13d_hedging_gate_only.md`
**Status**: production champion, all R71/R72/R73 used this prompt
**Performance**: 98.5% core / 94.4% minor / **seed std 0.00pp** / $1.12/run / ~5min/paper

Other `experiments/prompts/v0.*.md` are rejected variants — do not use.

If VPS-side AI ever extracts a paper, must use this prompt. Otherwise extraction shape will diverge from the Pydantic schema.

---

## 5. DB seeding flow (VPS-side action plan)

### 5.1 Initial seed (first time on VPS)

```bash
# After git clone + pip install
cd <vps-checkout-path>

# Read manifest from Dropbox (use Dropbox API or rsync)
# Manifest path on Dropbox:
#   D:/Dropbox/ai/CitareOpus47/experiments/CITARE_REGISTRATION_MANIFEST.json
# Each entry's extraction_path is RELATIVE to repo root.
# To resolve: prepend the Dropbox repo root.

python scripts/ingest_v013d_champions.py --db /var/lib/citare/citare.db
# This script reads manifest, walks each extraction.json, calls ingest_extraction.
# Default behavior: drops existing DB. Use --no-reset for incremental.

python scripts/run_heuristic_resolver.py
# (Optional) Consume pending_llm_review heuristically.

python scripts/smoke_test_mcp.py
# Must pass 6/6.
```

### 5.2 Incremental ingest (after each new local batch)

When the local side runs a new R-series batch:
1. Local: `rebuild_manifest.py` regenerates `CITARE_REGISTRATION_MANIFEST.json`
2. Local: commits & pushes the manifest update
3. Local: notifies VPS (or VPS polls)
4. VPS: `git pull` (gets new manifest)
5. VPS: reads new `extraction.json` from Dropbox (via Dropbox API, paths in manifest)
6. VPS: `python scripts/ingest_v013d_champions.py --db ... --no-reset`
   - Idempotent: re-ingesting an existing claim emits a `claim_overwrite` warning but doesn't error
   - New papers land cleanly

### 5.3 If VPS-side AI prefers MCP-based ingest (alternative to script)

The HTTP MCP server exposes `register_claims` (when not in `--read-only` mode). One-line per paper:

```python
import requests, json
ext = json.load(open("experiments/runs/<run_dir>/extraction.json", encoding="utf-8"))
r = requests.post(
    "http://localhost:8765/messages/?session_id=...",
    headers={"Authorization": f"Bearer {API_KEY}"},
    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
          "params": {"name": "register_claims", "arguments": {"json_data": json.dumps(ext)}}},
)
```

But for batch ingest, the script path is simpler (no SSE roundtrip per paper).

---

## 6. Cumulative state right now (2026-04-26)

| Metric | Value |
|--------|------:|
| Total v0.13d extractions in `runs/` | 82 papers (13 benchmark + 69 new) |
| Manifest entries | 81 (= 82 minus 1 duplicate-key collision) |
| Local DB state | 13-paper version (NOT yet re-ingested with new 68) |
| Cumulative API spend (all R-series, all variants) | $663.69 over 629 runs |
| Cumulative API time | 49.1 hours |
| Cumulative tokens | 119.8M |
| Recent batch (R71+R72+R73) | $71.36 / 69 papers / ~22 min wall time |

Local side has NOT yet ingested the 68 new extractions — leaving that for VPS to do (per user's decision: "DB は VPS 側管轄").

---

## 7. What I (Dropbox-side) commit to do next

In order:

1. ☐ Run `git add ... && git commit && git push` so VPS gets the manifest update + Phase-2/3 code
2. ☐ Optionally run remaining 46 cogsci papers (R74) if user requests
3. ☐ Re-run `rebuild_manifest.py` after any new batch
4. ☐ Notify VPS-side AI when manifest changes

After this, the loop runs steady-state: local extracts, VPS ingests + serves.

---

## 8. Open questions back to VPS-side AI

1. **Polling vs notification?** Should the local side push a webhook to VPS when manifest changes, or do you poll the Dropbox file mtime?
2. **DB backup cadence?** SQLite single-file means rsync-friendly; what's your retention policy?
3. **`register_claims` access**: should it be reachable from the public HTTP endpoint (with Bearer auth), or only via local stdio? My recommendation was public-with-auth.
4. **OAuth / claude.ai connector**: current HTTP server uses static API key. Want me to add OAuth integration, or keep it Bearer-only for v1?
5. **Read-only public endpoint vs read-write tenant endpoint**: do you want two endpoints? The HTTP server has a `--read-only` flag that filters out `register_claims` from the tool list — easy to run two instances with different flags.

Reply by editing this doc or starting a thread; I'll see your edits via Dropbox.

---

## 9. Contact / coordination

The user (石井遼介, ryouen@gmail.com) is the orchestrator. Routine coordination can happen Dropbox-AI ↔ VPS-AI without bothering them. Decisions involving cost (>$10), schema changes, or invariant edits — escalate to user.

---

*End of handoff reply. Generated by Claude Opus 4.7 on 2026-04-26.*
