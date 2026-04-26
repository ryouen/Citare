# Academic Paper PDF Acquisition Guide (Citare v0.1)

You are collecting PDFs of academic papers so their claims can be extracted into the Citare knowledge graph (or verified against a manuscript). This guide tells you how to obtain each PDF, what fails, and how to recover. The strategies below come from the Citare team's prior collection sessions; success rates are indicative.

---

## Capability requirements

Not every stage works for every LLM client. Check what you can do before starting.

| Capability | Stages it enables | Typical clients |
|---|---|---|
| HTTP fetch | 1, 2, 3, 5 | Claude Code, Codex, agents with web access |
| Web search | 4 | Claude with web_search, ChatGPT with browsing |
| Local file system | 0 | Claude Code, Cursor, local agents |
| Shell | Validation | Claude Code, Codex |
| Cloud storage API (Dropbox / Drive) | 0 (extended) | Agents with the user's auth tokens configured |
| Browser automation | 5 (PMC PoW) | Agents with CDP / Playwright |

If a stage requires a capability you lack, skip it. If no automated stage is available, jump to **Stage 6 — Ask the user**.

---

## Workflow: triage first

Before any download, sort your reference list:

```
Reference list (typical: 20-30 entries)
  │
  ├── ① Already in Citare → search_claims(doi=...) returns hits
  │     → No PDF needed. Proceed to citation check.
  │
  ├── ② Not in Citare, PDF available locally
  │     → Extract → register_claims → done.
  │
  └── ③ Not in Citare, no local PDF
        → This guide (Stages 0-6) → ② → done.
```

Always exhaust ① and ② before downloading anything new.

---

## Stage 0 — Local file search

If you have file system or cloud-storage access, search the user's machine first.

**Common paths:**
```
~/Papers/   ~/Documents/Papers/   ~/Research/   ~/Downloads/   ~/Desktop/
~/Dropbox/  ~/OneDrive/           ~/Google Drive/
```

**Patterns to try:**
```
{FirstAuthorSurname}*{Year}*
*{Year}*{key_title_word}*
*{DOI_fragment}*
```

**Shell example:**
```bash
find ~/Papers ~/Downloads ~/Desktop ~/Dropbox -iname "*edmondson*1999*" 2>/dev/null
```

If a Dropbox API token is configured for the agent (see operator-side setup), files can also be enumerated via `files/list_folder` recursively.

If found → extract via `get_extraction_prompt` and register. Skip the rest of this guide.

---

## Stage 1 — Verify the DOI

DOIs supplied by humans (or by other LLMs) are wrong more often than you'd expect. Downloading the wrong PDF wastes time and silently corrupts citation checks.

```
GET https://api.crossref.org/works/{DOI}
```

Verify that the returned `title` and `author[0].family` match what the citing context says. If they don't, search instead:

```
GET https://api.crossref.org/works?query.bibliographic={author}+{year}+{title_keywords}&rows=3
```

**Common DOI errors:**
- Digit transposition (`a_00422` vs `a_00442`)
- Off-by-one suffix
- Corrigendum DOI cited as the article DOI
- Hallucinated DOI

---

## Stage 2 — Direct HTTP download (open access publishers)

These sites serve PDFs directly. No auth, no tricks. Try first.

| Publisher / host | URL pattern | Reliability |
|---|---|---|
| **arXiv** | `https://arxiv.org/pdf/{ARXIV_ID}.pdf` | very high |
| **bioRxiv** | `https://www.biorxiv.org/content/{DOI}.full.pdf` | very high |
| **Frontiers** | `https://www.frontiersin.org/articles/{DOI}/pdf` | very high |
| **PLOS** (ONE, Biology, …) | `https://journals.plos.org/plosone/article/file?id={DOI}&type=printable` | very high |
| **MDPI** | append `/pdf` to the article URL | very high |
| **ACL Anthology** | `https://aclanthology.org/{ID}.pdf` | very high |
| **Nature Communications** (2016+) | `https://www.nature.com/articles/{article-id}.pdf` | very high |
| **BMC** | direct PDF link from the article page | very high |
| **OpenReview** | `https://openreview.net/pdf?id={ID}` — **must set `Referer: https://openreview.net/`** | high |

For arXiv papers, use the arXiv ID directly (faster + more reliable than the `10.48550/arXiv.{ID}` DOI form).

Some arXiv PDFs are large (10-17 MB). That is normal.

---

## Stage 3 — CrossRef PDF link

Even for non-OA publishers, CrossRef sometimes carries a free PDF link.

```
GET https://api.crossref.org/works/{DOI}
→ response.message.link[] where content-type == "application/pdf"
```

Hit rate is low (~15%) but the API call is free and fast — always try it before Stage 4.

---

## Stage 4 — Unpaywall OA discovery

```
GET https://api.unpaywall.org/v2/{DOI}?email=api@citare.dev
```

If the user's own email has been configured, prefer that over the default.

Check in this order:
1. `best_oa_location.url_for_pdf` — try this first
2. Walk all entries in `oa_locations[]` (each has `url_for_pdf` and `host_type`)

**Where Unpaywall finds copies:**
- Author-uploaded postprints on lab/personal pages (green OA)
- Institutional repositories (e.g., White Rose, CORE.ac.uk)
- Funder-mandated OA archives (NIH PMC, Wellcome)
- Preprint server versions

**Real-world hit rate for paywalled papers: ~40-50%.** Do not skip this stage.

---

## Stage 5 — Web search for hosted copies

Even when Unpaywall returns nothing, the PDF often exists somewhere on the open internet — hosted by a co-author's lab page, a course site, an institutional repository, or an aggregator.

**Search patterns:**
```
"{exact paper title}" filetype:pdf
{first_author_lastname} {year} "{short title fragment}" filetype:pdf
{first_author_lastname} {year} site:researchgate.net
{first_author_lastname} {year} site:academia.edu
```

**Where copies commonly live:**

| Source | Notes |
|---|---|
| Author lab pages | Famous labs (Gatsby UCL, EvLab MIT, Rahnev Lab) almost always host PDFs |
| University repositories | `pure.*`, `eprints.*`, `dspace.*` — green OA mandates |
| CORE.ac.uk | Aggregates 200M+ OA articles; has its own search API |
| Government / funder repos | NSF PAR, Europe PMC, NIH |
| Course material | `.edu/courses/.../readings/` — professors post readings |
| ResearchGate / Academia.edu | Author self-uploads; coverage spotty |
| Preprint servers | arXiv, bioRxiv, PsyArXiv, SSRN, OSF — may be earlier version, still useful |

**CORE API (optional):**
```
GET https://api.core.ac.uk/v3/search/works?q={title}&limit=3
→ check downloadUrl
```

**Empirical observation:** highly-cited Nature/Science-tier papers are MORE likely to have hosted copies (their authors tend to be at major institutions with OA mandates).

---

## Stage 6 — Europe PMC / PMC

```
GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:"{DOI}"&format=json&resultType=core
```

If a PMCID is returned, the PDF *may* be at:
```
https://pmc.ncbi.nlm.nih.gov/articles/{PMCID}/pdf/
```

### CRITICAL — PMC Proof-of-Work challenge (still active 2026)

PMC has deployed a JavaScript Proof-of-Work challenge on every PDF endpoint. `curl`, `wget`, `WebFetch`, and any HTTP client without JS execution receives a ~1.8 KB HTML page with a JS solver, **not the PDF**.

**This means: PMC PDFs cannot be downloaded programmatically without browser automation.**

Workarounds:
- Ask the user to open the URL in a browser, solve the challenge, save the PDF
- Use browser automation (CDP/Playwright) to navigate, wait for PoW completion, download
- Extract the `cloudpmc-viewer-pow` cookie from a logged-in browser session, pass it to curl with `-b`

Also note: **PMC indexed ≠ open access**. Many PMC-listed papers return `idIsNotOpenAccess`.

---

## Stage 7 — Ask the user

When all automated paths fail, report transparently:

```
I could not obtain a PDF for:
  {Author} ({Year}). {Title}. {Journal}.
  DOI: {DOI}

What I tried:
  - Direct download: {result}
  - Unpaywall: {result}
  - Web search for hosted copies: {result}
  - Europe PMC: {result}

This paper appears to require institutional access ({publisher}).
Options:
  a) Download from your institution's library and provide the PDF
  b) Skip this reference for now
  c) I can try browser automation if you have a logged-in browser session
```

---

## Validation — confirm you have a real PDF

Every downloaded file MUST pass these checks before you treat it as acquired:

1. **Magic bytes.** First 4 bytes must be `%PDF` (hex `25 50 44 46`).
2. **Minimum size.** ≥ 5 KB. Smaller files are error pages or login redirects.
3. **Not HTML.** First 1 KB must not contain `<html` or `<!DOCTYPE`. Common offenders: eLife, PMC, UNEP.

Shell:
```bash
head -c 4 paper.pdf | xxd        # → 2550 4446
wc -c paper.pdf                  # → > 5000
head -c 1024 paper.pdf | grep -E '<html|<!DOCTYPE'   # → no match
```

If you lack shell, check the HTTP response: `Content-Type: application/pdf` AND `Content-Length > 5000`.

**Sites that commonly return HTML disguised as PDF:**
- **eLife** — DOI redirect lands on an HTML page; the real PDF URL uses a base64-encoded CDN path. Fetch the landing page, parse out the PDF URL, then download.
- **PMC** — see Stage 6 PoW warning above.
- **UNEP (wedocs.unep.org)** — returns cover-page HTML; the real PDF is often hosted elsewhere (e.g., UN CC Learn).

---

## Site-specific gotchas

| Site | Trap | Symptom | Workaround |
|---|---|---|---|
| **eLife** | DOI/direct URL both return HTML | 89 KB file labelled as PDF | Fetch landing page → parse for the base64-encoded CDN PDF URL → download that |
| **PMC** | PoW JS challenge on PDFs | 1.8 KB HTML with JS solver | Browser automation, OR `cloudpmc-viewer-pow` cookie from logged-in session |
| **PNAS** | Many in PMC → same PoW wall | Same 1.8 KB HTML | Same PoW workaround |
| **Nature** (pre-2016) | Paywall; `.pdf` suffix doesn't bypass | HTML paywall or 403 | Unpaywall → web search → institutional access |
| **Science / AAAS** | Robust paywall; PMC copies hit PoW | Various | Older famous papers sometimes on author pages (Schultz 1997 → Gatsby UCL). Otherwise institutional |
| **Elsevier** (Cell, Neuron, TICS, Cognition) | Strong ScienceDirect paywall | Login redirect | Unpaywall sometimes finds green OA. Otherwise institutional |
| **Wiley** (JEAB, JABA, …) | Paywall on recent | 403 / login redirect | CORE.ac.uk may have author postprint. Pre-2000 sometimes in PMC |
| **OpenReview** | Requires `Referer` header | 403 without correct Referer | Send `Referer: https://openreview.net/` |
| **wedocs.unep.org** | 403 for all programmatic | HTTP 403 | Try alternative hosts (UN CC Learn) or browser |
| **Cloudflare-protected DSpace** | Bot challenge | Challenge HTML page | Browser automation; allow up to 60s for challenge |

---

## Batch strategy

When collecting many papers at once, group by host and parallelise:

```
Round 1 (parallel, ~100% expected):
  arXiv / bioRxiv batch
  Frontiers / PLOS / MDPI / ACL batch
  Nature Communications (2016+) batch

Round 2 (parallel, API-dependent):
  CrossRef PDF links for the rest
  Unpaywall for the rest
  Web search for hosted copies (lab pages, CORE, university repos)

Round 3 (sequential, may need user):
  Europe PMC → PMC (PoW workaround if available)
  Ask user for institutional-only items
```

Sort the reference list by publisher first. Same-publisher papers share the same access path; batching avoids strategy-switching overhead.

---

## File naming

```
{FirstAuthor}_{Year}_{ShortTitle}.pdf
```

- `ShortTitle`: first 4-5 meaningful words, excluding stop words (the, a, of, in, on, for, and), CamelCase
- Same author + year: disambiguate with `_a`, `_b`

Examples:
```
Edmondson_1999_Psychological_Safety_Learning.pdf
Vaswani_2017_Attention_All_You_Need.pdf
DellAcqua_2023_Jagged_Technological_Frontier.pdf
```

---

## Indicative success rates

| Method | Hit rate |
|---|---|
| Local file search | check first — costs nothing |
| arXiv / bioRxiv direct | ~100% |
| Frontiers / PLOS / MDPI direct | ~100% |
| Nature Comms / BMC / ACL direct | ~100% |
| Unpaywall OA discovery | ~75-80% |
| Web search for hosted copies | ~50% |
| PMC with PoW workaround (browser available) | ~100% |
| CrossRef PDF link | ~15% |
| Institutional access (manual) | ~100% (requires user) |

**Typical reference list outcome:**
- Automated (no institutional access): 55-60% acquired
- + Unpaywall + web search: ~75% acquired
- Remaining ~25% genuinely needs institutional access — ask the user

---

## When the PDF is large or has heavy scanned images

If the paper is a JSTOR-style scan with both text and image layers, use the `citare-strip-images` utility before extraction (drops image layer, keeps text — typically reduces input tokens by 90%):

```bash
pip install git+https://github.com/ryouen/citareMCP.git
citare-strip-images paper.pdf paper_stripped.pdf
```

Pass `paper_stripped.pdf` to extraction instead of the original. **Do not strip** when the figures carry the actual information (chemistry papers, anatomy, mathematical proofs as images).
