"""Two MCP read-tools that hand back the prompts an LLM needs to grow Citare.

`get_extraction_prompt` returns the locked production prompt (v0.13g) plus
sub-agent invocation guidance. `get_pdf_acquisition_guide` returns the PDF
collection playbook. Both ship as package data so they survive packaging
without depending on the source repo layout.

Why these are TOOLS, not MCP prompts: some MCP clients (notably some
non-Claude clients) do not implement `prompts/get`. Exposing the same
content as a tool keeps everyone working.
"""
from __future__ import annotations

from importlib import resources
from typing import Any


# Pinned versions. Bumping `EXTRACTION_PROMPT_VERSION` requires also bumping
# the corresponding asset filename and re-validating with the production
# benchmark — the prompt is an integration contract, not a content tweak.
#
# pt.3 lock (2026-04-26): v0.13g × effort=none won the R82 grid (n=72,
# 4 prompts × 3 efforts × 6 papers) and superseded the prior v0.13d × low
# recommendation. See experiments/PRODUCTION_CHAMPION.md.
EXTRACTION_PROMPT_VERSION = "v0.13g"
EXTRACTION_PROMPT_ASSET = "extraction_prompt_v0.13g.md"
PDF_ACQUISITION_GUIDE_VERSION = "v0.1"
PDF_ACQUISITION_GUIDE_ASSET = "pdf_acquisition_guide.md"


def _load_asset(name: str) -> str:
    return resources.files("citare_mcp.assets").joinpath(name).read_text(encoding="utf-8")


_SUB_AGENT_TEMPLATE = """\
## Sub-agent invocation template

Extracting claims from a PDF requires reading the entire paper (typically
30K-100K tokens). If you do this in your main conversation context, the
PDF content will contaminate your reference-checking workflow — you'll
confuse what the user wrote with what the paper says, and your context
window fills up fast.

**Always spawn a separate agent / context for extraction.**

## ⚠ DO NOT TUNE — these are calibrated values, not defaults

The v0.13g prompt and the model-config below are the **pt.3 production
lock** (2026-04-26), the result of **30+ prompt variants × ~700
extraction runs × $700+ of API spend** culminating in the R82 grid
(n=72, 4 prompts × 3 efforts × 6 papers). v0.13g × effort=none Pareto-
dominates the prior champion (v0.13d × low) on every quality axis:

| Axis | v0.13g × none (LOCKED) | v0.13d × low (prior) |
|------|--:|--:|
| Coverage | **97.4 ± 4.4%** | 93.6 ± 8.3% |
| Cost / paper | $1.19 ± 0.27 | $1.01 ± 0.34 |
| Duration / paper | 312 ± 54s | 233 ± 51s |
| EXIST claims / paper | **16.7** | 9.2 |
| Thesis-level losses | **0** | 0 |
| Per-paper coverage on R82 panel | noyzhang 100, hubinger 100, park 100, edmondson 95, wei 100, t7 89 | varies |

The +18% cost ($0.18 / paper) buys 7.5 extra EXIST claims per paper —
real boundary-condition / null-result / ethical-risk scaffolding that
was being silently dropped by `low` thinking-stage compression.

### What was empirically tested and rejected

- **effort=low / medium / high / xhigh / max** — every level above `none`
  introduces thesis-level claim loss when paired with anything stronger
  than the bare baseline prompt. Two of the four `low` losses on the
  R82 grid were on the most-cited findings in their respective papers
  (Hubinger sleeper-agent persistence, Edmondson H3 mediation).
- **adaptive thinking** — same failure mode; thinking-stage tries to
  "consolidate" EXIST claims and drops thesis-level items.
- **max_tokens < 32768** — truncates dense papers mid-JSON.

### Required settings

- **`effort: "none"`** — omit the parameter entirely on raw API calls
  (no `thinking` block at all). On the Claude CLI, pass `--effort none`.
- **`thinking`** — DO NOT include this parameter. Specifically not
  `{type: "enabled", budget_tokens: N}` and not `{type: "adaptive"}`.
- **`max_tokens: 32768`** — this is what the R82 grid validated; 64K is
  also fine but unnecessary.
- **stream the response** at 32K+ tokens to avoid SDK HTTP timeouts.

If you change these, you are not tuning — you are reverting a tuned
setting back to something that was already proven worse.

## Expected output size (rule of thumb from 80-paper benchmark)

Use this as a sanity check on the sub-agent's output:

| Paper kind | Expected JSON output |
|---|---|
| Typical empirical / conceptual paper | 30-100 KB (~30 claims × ~2 KB each) |
| Heavy paper (Shannon, Hayes, Hubinger) | 90-100 KB |
| Short / focused paper | 30-40 KB |

- **< 25 KB** → almost certainly missing claims. Re-prompt the sub-agent
  to re-scan the paper for findings, definitions, observations, and
  limitations.
- **> 150 KB** → likely inventing detail / over-extracting. Tighten.

## How to invoke

System message for the sub-agent:

```
You are a Citare claim extraction specialist. Read the attached PDF and
output ONLY a single valid JSON object following the Citare extraction
prompt provided by the user. No commentary, no markdown fences — just
the JSON.

Extract ALL claims comprehensively. Empirical papers >= 5 claims;
conceptual papers >= 8. Consider at least one claim per section and per
Table/Figure. Typical well-analysed papers produce 15-30 claims. When in
doubt, include the claim with a lower confidence_score rather than
omit it.
```

User message for the sub-agent: the PDF + the FULL extraction prompt
returned by this tool, **passed verbatim**. Do not summarise, shorten,
or reinterpret the prompt. The version below has been validated over
30+ variants and 550+ runs; modifying it breaks the validated pipeline.

## After extraction

1. **Validate locally.** Confirm `paper.doi` is present (or that you have
   `paper.title + paper.authors + paper.year` as a fallback) and that
   the `claims` array is non-empty.
2. **Register.** Call `register_claims(json_data=<the JSON>)`.
3. **Inspect the response.** Look at `created_paper`, `claims_added`,
   `warnings`, and `potential_duplicate_claims`. WARNING-not-REJECT
   semantics apply — a non-empty `warnings` list does not mean the
   ingest failed; it usually means a claim was overwritten or a
   reference resolution was queued.
4. **Verify.** `search_claims(doi=<paper.doi>)` should now return the
   new claims.

## Schema notes (v0.13d → current Citare DB)

The v0.13d prompt JSON is accepted as-is. The DB does the following
transparent mapping during ingest, so you do not need to adjust your
output:

- `causal_strength.author_framing` is stored as
  `causal_strength.author_framing_observed_only` (Pydantic alias).
  This field is **never** used by `safe_verbs`; it is audit-only.
- Old prompt fields `l1_subject`, `l1_predicate`, `l1_object`,
  `l2_en`, `l2_ja` are silently dropped if present.
- `claim_status` defaults to `"current"` if absent. Other allowed
  values: `superseded`, `retracted`, `failed_to_replicate`, `contested`.
- `inclusion_policy_tier` defaults to `3` (ungated) if absent. Other
  allowed values: `1` (curated), `2` (verified).
- `incompleteness_category` accepts the original 5 plus 5 added:
  `none`, `extends_prior_definition`, `boundary_condition`,
  `hub_component`, `effect_disappears_under_control`,
  `preregistered_confirmed`, `underpowered`, `disputed`,
  `failed_to_replicate`, `retracted`. New categories may be added
  via `INSERT OR IGNORE` into the `incompleteness_vocabulary` seed
  table — they do not require code changes.
"""


def get_extraction_prompt() -> dict[str, Any]:
    """Return the locked v0.13g extraction prompt with sub-agent guidance."""
    return {
        "version": EXTRACTION_PROMPT_VERSION,
        "prompt": _load_asset(EXTRACTION_PROMPT_ASSET),
        "sub_agent_template": _SUB_AGENT_TEMPLATE,
        "usage": (
            "Pass the 'prompt' field VERBATIM to a sub-agent reading the PDF. "
            "After the sub-agent returns JSON, call register_claims(json_data=...). "
            "The 'sub_agent_template' field explains how to invoke the sub-agent and "
            "what to do with the output."
        ),
        "rationale": (
            "v0.13g × effort=none is the pt.3 production lock (2026-04-26). "
            "R82 grid (n=72): 97.4% coverage, 16.7 EXIST claims/paper, zero "
            "thesis-level miss across the 6-paper panel. Pareto-dominates the "
            "prior champion (v0.13d × low). Do not deviate."
        ),
    }


def get_pdf_acquisition_guide() -> dict[str, Any]:
    """Return the PDF acquisition playbook (Stages 0-7 + validation)."""
    return {
        "version": PDF_ACQUISITION_GUIDE_VERSION,
        "guide": _load_asset(PDF_ACQUISITION_GUIDE_ASSET),
        "usage": (
            "Walk Stages 0 through 7 in order. Skip stages that require "
            "capabilities you lack. Validate every download (magic bytes + "
            "minimum size + not-HTML)."
        ),
    }
