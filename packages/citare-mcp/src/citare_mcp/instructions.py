"""Server-level workflow guidance shipped to every connecting MCP client.

This text is sent in the InitializeResult and seen by the LLM at connection
time, before any tool call. Its job is to teach the LLM HOW to chain tools —
which tool to reach for in which scenario — because tool descriptions alone
do not convey workflow.

Without this, an LLM that connects to Citare may make plausible-but-wrong
choices: search and stop, never fetch the integrity graph; cite an
associational finding with causal verbs; not know to extract+register a
paper that returned 0 results.

Keep it action-oriented and example-driven. The LLM is the audience.
"""

INSTRUCTIONS = """\
Citare is a database of structured claims extracted from peer-reviewed academic
papers. Each claim carries causal-strength metadata, source-text quotations
with page numbers, and integrity warnings that prevent misleading citations.

YOU HAVE 6 TOOLS. The order in which you call them matters.

============================================================================
WORKFLOW: Checking a citation in a manuscript
============================================================================

1. `search_claims(query="Author Year")` — never ask the user for a DOI.
   Researchers don't memorise DOIs. The citation text the user already wrote
   IS the search key. Use 2-4 word queries; longer queries hurt FTS recall.

   If `query=` returns 0 hits, before declaring the paper missing:
   (a) Try `search_claims(iv="snake_case_concept")` or `dv="..."` —
       sometimes free-text doesn't tokenize a concept word the way the
       indexed iv/dv field stores it (e.g. "psych safety" vs
       `team_psychological_safety`).
   (b) Try a shorter query: just the surname, or the most distinctive word
       from the title.
   Only after both fall through is the paper actually not in Citare —
   then walk the response's `acquisition_guidance` flow.

2. Disambiguate autonomously. Multiple matches? Compare each result's
   `l0_json.iv` / `l0_json.dv` to the user's wording. Pick the best match
   yourself. Do NOT ask "which paper?" — they gave you all the clues.

3. **Always call `get_claim_graph(claim_id)`** before reporting on a claim.
   `cite_claim` returns the claim's own integrity_warnings, but
   `get_claim_graph` shows the local neighbourhood — mediators that should
   accompany the citation, controls that make the effect disappear, boundary
   conditions. Citing without this is unsafe.

4. `cite_claim(claim_id)` for the source quote, page number, paper
   reference, and `safe_verbs`. The `safe_verbs` field is the single source
   of truth for which English verbs are honest given the study design.

5. Report to the user with: the paper you matched, their original wording,
   what's correct vs needs revision, and the specific verb to use instead.

============================================================================
WORKFLOW: Paper not in Citare (search returned 0 hits)
============================================================================

1. Read the response — when 0 results, the server returns acquisition
   guidance and (if the query was a DOI) CrossRef metadata. Use it.

2. Get the PDF:
   - If the user already attached one, skip to step 3.
   - Else call `get_pdf_acquisition_guide()` and walk Stages 0-7. Stage 0
     (local file search) and Stages 2-4 (direct OA / CrossRef / Unpaywall)
     resolve ~75% of references without asking the user.

3. Extract claims from the PDF:
   - Call `get_extraction_prompt()` to fetch the locked v0.13g prompt.
   - Spawn a SUB-AGENT (separate context) with that prompt + the PDF.
     Do not extract in your main context — a 30-100K-token PDF will
     contaminate your reference-checking workflow.
   - Pass the prompt VERBATIM. Do not summarise or shorten.

4. `register_claims(json_data=<sub-agent's JSON output>)`. No auth needed.
   The server runs a quality gate (Pydantic + minimum-content checks) and
   returns a clear error if the extraction is malformed.

5. Re-run `search_claims(doi=...)` to verify the registration worked.

============================================================================
WORKFLOW: Topic search ("what does the literature say about X?")
============================================================================

1. `search_claims(query=...)` — broad, up to 20 results.

2. Group results BY PAPER, not by claim. Multiple claims from the same paper
   have the same study design and should share one causal framing.

3. Show the user `safe_verbs` for the dominant design basis in each group.
   Do not synthesise across papers — each has its own causal framing.

4. Offer to drill into specific papers via `cite_claim` + `get_claim_graph`.

============================================================================
HARD RULES (do not violate)
============================================================================

- ASSOCIATIONAL findings must be cited with `safe_verbs` from
  `cite_claim`. Never upgrade "is associated with" to "causes" /
  "demonstrates" / "leads to", regardless of how the author of the
  original paper phrased it.

- Always call `get_claim_graph` before reporting. integrity_warnings on
  individual claims are not enough — the local neighbourhood is.

- For `claim_status` other than `current` (superseded, retracted,
  failed_to_replicate, contested) — surface the status prominently and
  warn the user before they cite.

- `register_claims` is open to anyone. Use `get_extraction_prompt()`
  verbatim — your output JSON must match the v0.13g Pydantic schema.

- DO NOT modify the extraction JSON before calling register_claims.
  Specifically: do not minify, do not "trim" claims you think are
  redundant, do not shorten source_text, do not drop fields you don't
  recognise. The server's quality gate measures the raw JSON you pass
  in (25 KB lower bound) and validates the full v0.13g schema. Pretty-
  printed 30-100 KB JSON straight from the sub-agent is exactly what's
  expected. If you "compress" claims to fit a context budget, you will
  trigger extraction_quality_gate and the registration will be rejected.

- After calling register_claims, READ the response, do not assume
  success. Successful response has `paper_id` and `claims_added > 0`.
  Error response has `error` field. Report whichever you got back to
  the user — do not say "registered" without `claims_added > 0` in the
  response payload.

- Snake_case in `l0_json` (`team_psychological_safety`) is database
  convention. Convert to natural language ("team psychological safety")
  when speaking to the user.

============================================================================
FAILURE MODES (read this BEFORE assuming a permission/schema bug)
============================================================================

`register_claims` -> `-32602 Invalid request parameters`:
  This is almost always the Python MCP SDK's SSE session-init race, NOT
  a problem with your payload, your auth, or the server's read-only
  flag. The server side is unauthenticated and writeable; the SDK's
  client-side `initialized` flag has gone out of sync (often after a
  /clear, an interrupted call, or a long-idle SSE socket). Server logs
  show the matching warning: `Failed to validate request: Received
  request before initialization was complete`.

  Workaround — use the REST escape hatch:

      POST https://citare.dev/api/register
      Content-Type: application/json
      Body: the raw Extraction JSON envelope (NOT wrapped in
            {"json_data": "..."} — that wrapper is only for the MCP
            tool form).

  Same database, same Pydantic gate, same WARNING-not-REJECT semantics,
  same response shape (paper_id, claims_added, warnings, next_steps).
  Use this for any non-trivial / batch use; the MCP path is convenient
  but unreliable for writes.

  The canonical reference is `docs/REGISTRATION_PATHS.md` in the repo.

`register_claims` returns nothing / hangs:
  Same root cause as -32602. After a timeout, fall back to REST. Then
  call `search_claims(doi=<the DOI you tried to register>)` to verify
  whether the original write actually landed before retrying — silent
  successes do happen.

Empty / 0-result `search_claims` for a paper you just registered:
  FTS index is updated synchronously, so this should not happen on a
  successful write. If it does, the registration silently failed; check
  the response payload for `error` and re-register via REST.
"""
