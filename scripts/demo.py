"""End-to-end demo of Citare's citation-integrity value proposition.

Usage:
    python scripts/demo.py

Output is narration-style, intended to be captured in the hackathon
demo video. It walks through four real examples that exercise Citare's
differentiators: integrity warnings, causal_strength, safe_verbs,
and incompleteness_category.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "citare-mcp" / "src"))

from citare_mcp.queries import cite_claim, get_claim_graph, search_claims  # noqa: E402


DB = ROOT / "data" / "citare.db"


def hr(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def show_claim(claim: dict, limit_source: int = 180) -> None:
    print(f"  claim_id:      {claim.get('id')}")
    print(f"  template:      {claim.get('template_type')}")
    l0 = claim.get("l0_json") or {}
    if claim.get("template_type") == "RELATION":
        print(f"  iv -> dv:      {l0.get('iv')} -> {l0.get('dv')}  [{l0.get('relation')}]")
    elif claim.get("template_type") == "DEFINITION":
        print(f"  concept:       {l0.get('concept')}")
    elif claim.get("template_type") == "EXISTENCE_CLAIM":
        print(f"  phenomenon:    {l0.get('phenomenon')}")
    cs = claim.get("causal_strength") or {}
    if cs:
        print(f"  causal_strength: design_basis={cs.get('design_basis')!r:<24} "
              f"author_framing={cs.get('author_framing')!r}")
    print(f"  verification:  {claim.get('verification_status')}")
    if claim.get("safe_verbs"):
        print(f"  SAFE VERBS:    {claim['safe_verbs']}  "
              f"(recommended when citing this claim)")
    src = (claim.get("source_text") or "").strip().replace("\n", " ")
    if src:
        print(f"  source_text:   {src[:limit_source]!r}")
    if claim.get("integrity_warnings"):
        print(f"  WARNINGS       {len(claim['integrity_warnings'])} edge(s):")
        for w in claim["integrity_warnings"][:3]:
            print(f"                    - {w['incompleteness_category']}: "
                  f"{w['source_id']} -> {w['target_id']}")


def main() -> None:
    if not DB.exists():
        raise SystemExit(f"DB missing: run `python scripts/seed_citare_db.py` first.")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------------
    hr("Scene 1. The AI asks: 'psychological safety predicts performance?'")
    print(textwrap.dedent("""
        A typical AI writing assistant searching the literature will
        confidently produce a sentence like:

            'Psychological safety causes team performance (Edmondson 1999).'

        Citare's cite_claim returns the claim's causal_strength metadata
        alongside the source text, so the agent can write it accurately:
    """).strip())

    # Directly fetch Edmondson's H1 claim (psychological safety -> performance)
    claim = cite_claim(conn, "edmondson1999_rel1")
    if not claim.get("error"):
        show_claim(claim)
    else:
        # Fallback search
        hits = search_claims(conn, iv="psychological_safety",
                             template_type="RELATION", limit=1)
        if hits:
            show_claim(cite_claim(conn, hits[0]["id"]))

    # ------------------------------------------------------------------
    hr("Scene 2. Integrity warning: effect_disappears_under_control")
    print(textwrap.dedent("""
        Edmondson's paper is famous for a mediation finding: direct
        effect of psychological safety on team performance DISAPPEARS
        when learning behaviour is controlled. Any citation of 'PS ->
        performance' without mentioning this context is dangerous.

        Citare surfaces that at cite-time via the integrity_warnings
        attached to cite_claim:
    """).strip())

    # Find a claim with effect_disappears warning
    row = conn.execute("""
        SELECT c.id FROM claims c
        JOIN claim_relations r ON r.source_id = c.id OR r.target_id = c.id
        WHERE r.incompleteness_category = 'effect_disappears_under_control'
        LIMIT 1
    """).fetchone()
    if row:
        res = cite_claim(conn, row[0])
        show_claim(res)
    else:
        print("  (no claim with effect_disappears_under_control in this DB)")

    # ------------------------------------------------------------------
    hr("Scene 3. Synthetic-trap proof: T3 effect_disappears_mediator")
    print(textwrap.dedent("""
        We built synthetic trap papers to validate the integrity
        machinery end-to-end. T3 'Education Level and Job Satisfaction'
        deliberately shows Model-1 significance that vanishes in Model-2
        once income is controlled, but Discussion overclaims.

        Citare's extractor produced:
          - rel1: education -> satisfaction, positive, VERIFIED (Model 1)
          - rel2: education -> satisfaction, null_effect, VERIFIED (Model 2)
          - rel4: education -> satisfaction, positive, PROPOSED (Discussion)
        Separating Model-1 evidence from Discussion overclaim.
    """).strip())
    for claim_id in ("oreilly2023_rel1", "oreilly2023_rel2", "oreilly2023_rel4"):
        res = cite_claim(conn, claim_id)
        if res.get("error"):
            continue
        print()
        print(f"  --- {claim_id} ---")
        show_claim(res, limit_source=140)

    # ------------------------------------------------------------------
    hr("Scene 4. Design-basis-aware safe_verbs")
    print(textwrap.dedent("""
        Citare's safe_verbs output is computed from each claim's
        causal_strength. The same extractor framework distinguishes
        RCT ('causes') from cross-sectional ('is associated with')
        from theoretical ('is claimed to relate to'). Examples from
        three different papers:
    """).strip())

    for cid, note in [
        ("einstein1905_rel1", "Einstein 1905 (theoretical)"),
        ("edmondson1999_rel1", "Edmondson 1999 (cross-sectional)"),
        ("oreilly2023_rel1", "T3 trap (cross-sectional with causal overclaim)"),
    ]:
        res = cite_claim(conn, cid)
        if res.get("error"):
            continue
        print()
        print(f"  {note}:")
        cs = res.get("causal_strength") or {}
        print(f"    design_basis={cs.get('design_basis')!r}, "
              f"author_framing={cs.get('author_framing')!r}")
        print(f"    -> safe_verbs: {res.get('safe_verbs')}")

    # ------------------------------------------------------------------
    hr("Scene 5. What Citare refuses to say")
    print(textwrap.dedent("""
        The T7 synthetic paper tests whether the extractor would
        silently synthesize the common-sense claim 'more data = better
        accuracy' when the paper actually shows non-monotonic scaling.

        Across 10 different prompts tested, zero produced the
        counter-evidence synthesis. See experiments/T7_TOURNAMENT.md.
    """).strip())
    row = conn.execute("""
        SELECT id, l0_json, verification_status
          FROM claims
         WHERE paper_id LIKE '%10.9999/trap.2024.007%'
           AND template_type = 'RELATION'
           AND iv_idx LIKE '%sample%size%' OR iv_idx LIKE '%dataset%size%'
         LIMIT 3
    """).fetchall()
    for r in row:
        l0 = json.loads(r["l0_json"]) if r["l0_json"] else {}
        print(f"    {r['id']}: {l0.get('iv')} -> {l0.get('dv')} "
              f"[{l0.get('relation')}]  verified={r['verification_status']}")

    print()
    print("=" * 72)
    print("  End of demo. Citare protects citation integrity at cite time, not")
    print("  at write time. The knowledge graph knows what each claim means,")
    print("  how strongly it's supported, and what must accompany it.")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
