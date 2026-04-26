# Citare Strategy

*Last revised 2026-04-27.*

---

## Mission — One person processes a paper. Humanity inherits the result.

Every researcher who reads "Edmondson 1999" reads it from scratch. Every
LLM that cites it re-derives the same claims by re-parsing the same PDF.
Every reviewer who checks a citation re-walks the same logic. The
collective cost — across millions of reads — is staggering, and it
produces nothing reusable.

Citare's commitment: **structured understanding of a paper should be a
one-shot, durable artefact.** When one researcher (or AI) extracts a
paper's claims with the canonical prompt, the result becomes a public
good. The next reader doesn't re-extract. They query.

This is not a literature search engine. It is **post-search
infrastructure** — the place where what a paper *says*, with *what
causal strength*, *under what conditions*, lives in a form an AI can
cite honestly without re-reading the source.

## Vision — A claim graph is the substrate AI needs to discover new theories.

Once enough peer-reviewed claims are structured with their causal
metadata, their boundary conditions, and their relations to other
claims, three things become possible that aren't possible today:

- **Cross-domain pattern detection.** The same structural relation
  ("X moderates Y when Z is high") may appear in psychology, economics,
  and machine learning literature with completely different surface
  vocabulary. A claim graph lets an AI see the isomorphism.
- **Gap detection at scale.** "We have 12 cross-sectional studies of
  A→B but zero longitudinal" becomes a query, not a literature review.
- **Theory generation.** Given a partial claim chain, an AI can
  propose the missing link as a testable hypothesis, with full
  provenance to the claims that constrained the proposal.

We are not building "search papers faster." We are building the
**substrate for AI-driven scientific discovery** — a corpus where the
unit is the claim, not the paper, and where every claim carries enough
metadata that downstream reasoning is honest by construction.

The vision is genuinely speculative. We will not know if AI can really
do these things until the corpus reaches the 10K-claim threshold. But
the substrate must exist before the question can be asked.

---

## Three commitments that follow

### 1. The unit is the claim.

Indexing papers tells you "this paper exists" — useful for discovery,
useless for citation. Indexing claims tells you "this paper says X
under condition Y with strength Z." That's what citation actually
needs. Citare's schema is built around the claim, not the paper.

### 2. Causal strength is metadata, not opinion.

Every claim carries the study design that produced it. From that, the
server derives **safe verbs** — the verbs an honest citation can use.
A cross-sectional finding returns *"is associated with"* or
*"correlates with"* regardless of how the original author framed it.

This single rule prevents the most common citation failure: silently
upgrading "associated with" to "causes."

### 3. The corpus belongs to everyone.

`register_claims` is open. No auth. Anyone with a valid extraction can
contribute. The protection layer is schema validation plus minimum
content checks — not human moderation. This is the only path that
scales to the 10K claims the vision needs.

The reciprocal commitment: the data stays free. Read access is free.
Write access is free. Citare will accept hosting cost rather than
introduce paywalls that fragment the corpus.

---

## What this is *not*

Stating these explicitly so the project doesn't drift into them.

- **Not a literature search engine.** Google Scholar indexes papers.
  Citare indexes claims. Different products, different success metrics.
- **Not a personalised research assistant.** No accounts, no
  per-user state, no recommendations.
- **Not a paper-summary tool.** A summary loses the very metadata that
  makes citation safe.
- **Not a debate platform.** Disputed claims are tagged; we do not host
  the debate.
- **Not a corpus to be sold.** Public good, by design.

---

## How to participate

Two ways:

**Use it.** Connect your AI to `https://citare.dev/sse` (MCP). When
you write a paper or check a citation, your AI can query the graph and
follow the safe verbs. Every honest citation that gets made because of
Citare is a small win for the field.

**Grow it.** When your AI finds that a paper is missing from Citare,
let it run the canonical extraction prompt (also exposed via MCP) and
submit the result. One paper takes about five minutes and roughly $1
of API cost. The result is permanent and benefits every future reader.

The full extraction prompt, the PDF acquisition guide, and the
registration tool are all exposed through the MCP server. No local
install required.

---

## Where we are

84 papers. 2,634 claims. 2,008 relations. 1,115 integrity warnings.

This is enough to validate the design and not nearly enough to enable
the vision. The path from here:

- **200 papers**: contributor loop hardens. Cross-paper queries start
  returning multiple sources with different design bases.
- **1,000 papers**: the discovery surface starts to matter. Citation
  resolution between cited and citing papers becomes the highest-value
  feature.
- **10,000 papers**: the vision becomes testable. Can an AI identify
  cross-domain isomorphisms? Can it propose hypotheses grounded in
  five separate claim chains? We do not yet know.

---

*Citare. AI-native scholarly claim infrastructure.*
*MCP endpoint: <https://citare.dev/sse>*
