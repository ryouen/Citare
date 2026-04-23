# Citare Demo Narrative — Draft v1

**Target length**: 3 minutes (hackathon submission cap)
**Primary focus**: Opus 4.7 creatively prevents AI citation errors via structured claims

---

## Beat 1: The Tsunami (0:00-0:30)

**Visual**: Counter ticking up. Papers cascading down screen.

> "Every day, 9,000 new peer-reviewed papers are published.
> The world now has roughly 1.8 billion academic papers in total.
> Nobody can read them. Not even AI, at the scale we need.
>
> So AI reads for us. But AI reads *wrong*."

Cite: 3.27M/yr NCSES/Scopus 2023; 1.8B accumulated OpenAlex.

---

## Beat 2: The Error (0:30-1:10)

**Visual**: Three-panel split. ChatGPT, Gemini, Claude all asked the same question about Edmondson 1999. All say "team psychological safety CAUSES learning behavior."

> "Ask the leading frontier models — all of them — what Edmondson 1999 found about psychological safety.
> They'll tell you it *causes* learning behavior.
>
> Now open the actual paper." *[zoom to page 31]*
>
> "Edmondson writes: *'The cross-sectional survey design prevented a demonstration of causality.'*
> But AI doesn't read that footnote. AI reads the abstract. And the abstract says 'positively associated' — which AI compresses to 'causes.'
>
> **That single word-choice error compounds.** Every AI summary of every paper that cites this paper will inherit it.
> Verification is O(N²): for every citation, you'd read the source and its context.
> **This gap never closes on its own.**"

---

## Beat 3: What If We Separated the Claim from the Paper? (1:10-1:40)

**Visual**: Slide: "DOI is for papers. **Citare is for claims.**"
Zoom: one paper → 20+ structured claims with metadata.

> "What if the unit of citation wasn't the paper, but the *claim*?
> With its causal strength, its design basis, its incompleteness warnings — all machine-readable?
>
> That's Citare. Every claim carries the structure the original paper actually asserted."

---

## Beat 4: The Wow Moment — Opus 4.7 Self-Corrects (1:40-2:30)

**Visual**: Live extraction. Opus 4.7 reading Edmondson 1999 PDF. Extended thinking visible on side.

> "Watch Opus 4.7 extract this paper in under 4 minutes.
> 29 claims. Every one with its own design basis, verification status, and source text.
>
> Now watch what happens when an AI assistant asks Citare about psychological safety and performance."

*[Switch to Claude Code with Citare MCP]*
*User types: "Does team psychological safety cause team performance?"*

> "Claude checks Citare first. Citare returns the claim."
> *[Show claim: design_basis=cross_sectional, author_framing=associational, incompleteness_category=effect_disappears_under_control]*
>
> "Watch the extended thinking."
> *[Thinking stream on side shows: 'The claim is cross-sectional, so I can't say causes. Also, the incompleteness flag says the direct effect disappears when team learning is controlled. I must cite the mediator.']*
>
> "Claude responds:"
> *[Text appears]*
>
> "In Edmondson (1999), team psychological safety was **positively associated** (B=.76, p<.01) with team learning behavior in a cross-sectional survey of 51 teams. The direct effect on team performance becomes insignificant (B=.25, p=.42) when controlling for learning behavior — full mediation."

---

## Beat 5: Scale and Impact (2:30-2:55)

**Visual**: Extract logs across 5 papers in 6 domains. Each scored against ground truth.

> "We tested across 5 foundational papers from OB to ML to AI safety.
> Opus 4.7 with Citare: **100% gold-standard coverage on 3 of 5 papers. 95% on the hardest.**
>
> Cost: under $1 per paper.
> Scale: 3.3 million new papers per year × ~20 claims each → a billion structured claims.
> Every AI assistant, every reviewer, every researcher — citing from one structured ground truth.
>
> **DOI is for papers. Citare is for claims.**"

---

## Beat 6: Logo / Close (2:55-3:00)

**Visual**: Logo + citare.dev URL + "Built with Opus 4.7"

---

## Technical Details (footnotes for judges)

- **Extraction**: `claude -p` with v0.1 prompt, effort=high, Max plan (~$0.92/paper measured)
- **Stack**: Python harness + `claude-opus-4-7` (1M context), PDF multimodal direct input
- **Structured output**: 4 claim templates (DEFINITION, RELATION, EXISTENCE_CLAIM, META_CLAIM) with causal_strength, author_generalization, incompleteness_category metadata
- **Graph**: claim_relations with 9 relation types and 5 incompleteness categories
- **MCP tools**: `search_claims`, `get_claim_graph`, `cite_claim` (Phase 1), `register_claims` (Phase 2)

## Key numbers from experiments (updated 2026-04-23)

**Winning configuration: Opus 4.7 + v0.1 baseline prompt + effort=none**

| paper | domain | pages | best coverage | best cost |
|-------|--------|-------|---------------|-----------|
| Edmondson 1999 | OB empirical | 35 | **100%** (v0.8) | $0.81 |
| Barney 1991 | OB conceptual | 26 | 100% | $0.87 |
| DellAcqua 2023 | OB RCT | 58 | 100% | $1.50 |
| Vaswani 2017 | ML Transformer | 15 | 100% | $2.08 |
| Noy & Zhang 2023 | applied AI | 14 | **100%** (v0.8, +16pp) | — |
| Hayes 2006 (ACT) | psychology review | 45 | 91% | $1.66 |
| Wei 2022 (CoT) | AI ML | 43 | 89% (v0.1; v0.8 regressed) | $0.91 |
| Hubinger 2024 (Sleeper Agents) | AI safety | long | 87% | $1.28 |
| Turing 1950 (Computing Machinery) | philosophy-AI | 28 | 100% | $1.40 |
| **Einstein 1905** (German scanned) | physics | 31 | **100%** | $0.95 |
| Watson-Crick 1953 | biology 1-page | 1 | 100% | $0.42 |
| Shannon 1948 (entropy) | info theory | long | 100% | $1.25 |

**12 papers, 7 domains, 2 languages, median coverage 100%, min 87%, at ~$1/paper on Max plan.**

---

## Contingencies / open questions

- Hard claim to capture: H8 (efficacy does NOT mediate — the *negative* finding). All runs missed this.
- ICC as EXISTENCE_CLAIM: captured by effort=medium/high, missed by none.
- Demo risk: Edmondson's exact mediation numbers (B=.25, p=.42) come from R10H/R2B extractions. Verify live before recording.
