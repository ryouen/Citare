"""Core query functions behind the three MCP tools.

These are pure Python and take a SQLite connection; the MCP server layer
in server.py wraps them in the protocol. This separation lets the same
functions be reused by a REST API or a CLI later.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def _row_to_claim(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in ("l0_json", "l3_json", "causal_strength", "method_metadata"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def search_claims(
    conn: sqlite3.Connection,
    query: str | None = None,
    doi: str | None = None,
    iv: str | None = None,
    dv: str | None = None,
    template_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search claims by free-text, DOI, iv/dv pair, or template type.

    At least one of (query, doi, iv, dv) must be provided. Free-text
    search uses FTS5 MATCH against the ``claims_fts`` virtual table
    (source_text only — l1/l2 fields dropped in Task 65). Multi-word
    queries are joined as implicit-AND (FTS5 default with unicode61
    tokenizer); callers wanting a phrase should quote it.
    """
    if not any([query, doi, iv, dv, template_type]):
        raise ValueError("at least one of query / doi / iv / dv / template_type is required")

    where: list[str] = []
    params: list[Any] = []
    use_fts = bool(query)

    if doi:
        where.append("claims.paper_id = ?")
        params.append(doi)
    if iv:
        # Task 65 — l1_* columns dropped; use the JSON-virtual indexed column.
        where.append("claims.iv_idx LIKE ?")
        params.append(f"%{iv}%")
    if dv:
        where.append("claims.dv_idx LIKE ?")
        params.append(f"%{dv}%")
    if template_type:
        where.append("claims.template_type = ?")
        params.append(template_type)
    if use_fts:
        # FTS5 MATCH parses the query string with its own tiny grammar — bare
        # punctuation (DOIs, arXiv IDs, emails) is a syntax error.
        # Strategy: quote whole tokens that contain anything outside word /
        # CJK / dash, so a DOI like 10.1037/0033-295X.84.2.191 is treated as a
        # phrase rather than parsed as operators. Multi-word natural-language
        # queries still get implicit-AND semantics on plain tokens.
        import re as _re
        q = query.strip()
        if q.startswith('"') and q.endswith('"'):
            fts_query = q
        else:
            _safe = _re.compile(r"^[\w぀-ヿ一-鿿]+$")
            tokens = q.split()
            if not tokens:
                fts_query = q
            else:
                fts_query = " ".join(
                    t if _safe.match(t) else '"' + t.replace('"', '""') + '"'
                    for t in tokens
                )
        where.append("claims_fts MATCH ?")
        params.append(fts_query)

    # Task 65 — l1_subject/predicate/object and l2_en/l2_ja have been dropped;
    # callers needing structured fields should parse l0_json.
    select_cols = (
        "claims.id, claims.paper_id, claims.template_type, claims.l0_json, "
        "claims.source_text, claims.source_page, claims.source_section, "
        "claims.evidence_type, claims.verification_status, "
        "claims.causal_strength, claims.method_metadata, claims.confidence_score"
    )
    if use_fts:
        from_clause = "claims JOIN claims_fts ON claims_fts.claim_id = claims.id"
        order_clause = "ORDER BY bm25(claims_fts) ASC"
    else:
        from_clause = "claims"
        order_clause = "ORDER BY claims.confidence_score DESC NULLS LAST"

    sql = (
        f"SELECT {select_cols} FROM {from_clause} "
        "WHERE " + " AND ".join(where) + " " +
        order_clause + " LIMIT ?"
    )
    params.append(limit)
    try:
        return [_row_to_claim(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError as e:
        # FTS5 has a strict tiny grammar — any unhandled punctuation in the
        # query (rare after the token-quoting above) lands here. Treat as
        # zero hits so the MCP-layer 0-result enrichment can still fire.
        if use_fts and "fts5" in str(e).lower():
            return []
        raise


def cite_claim(
    conn: sqlite3.Connection,
    claim_id: str,
    style: str = "apa7",
) -> dict[str, Any]:
    """Return a full citation bundle for one claim.

    Includes: the claim fields, the paper's bibliographic info, a
    formatted reference string in the requested style (apa7 / chicago /
    bibtex; defaults to apa7), and a list of integrity warnings from any
    claim_relation edges this claim participates in.
    """
    row = conn.execute(
        "SELECT * FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return {"error": f"claim not found: {claim_id}", "claim_id": claim_id}
    claim = _row_to_claim(row)

    paper_default_cs: dict[str, Any] = {}
    paper = conn.execute(
        "SELECT id, canonical_title, authors, year, venue, paper_type, domain, "
        "default_causal_strength, default_method, inclusion_policy_tier "
        "FROM papers WHERE id = ?",
        (claim["paper_id"],),
    ).fetchone()
    if paper is not None:
        paper_dict = dict(paper)
        try:
            paper_dict["authors"] = json.loads(paper_dict["authors"])
        except (TypeError, json.JSONDecodeError):
            pass
        for k in ("default_causal_strength", "default_method"):
            if paper_dict.get(k):
                try:
                    paper_dict[k] = json.loads(paper_dict[k])
                except (TypeError, json.JSONDecodeError):
                    pass
        # Capture paper default for safe_verbs fallback
        if isinstance(paper_dict.get("default_causal_strength"), dict):
            paper_default_cs = paper_dict["default_causal_strength"]
        # Include all known identifiers for this paper
        idents = conn.execute(
            "SELECT identifier_type, identifier_value, is_preferred "
            "FROM paper_identifiers WHERE paper_id = ? ORDER BY is_preferred DESC",
            (paper_dict["id"],),
        ).fetchall()
        paper_dict["identifiers"] = [dict(r) for r in idents]
        # Formatted reference string per requested style (apa7 / chicago / bibtex).
        # Done here instead of client-side because (a) we have full identifier
        # context, (b) avoiding re-implementation across every MCP client.
        from citare_mcp.formatters import format_paper_reference, normalise_style
        paper_dict["paper_reference"] = format_paper_reference(paper_dict, style)
        paper_dict["paper_reference_style"] = normalise_style(style)
        claim["paper"] = paper_dict

    warnings = conn.execute(
        """
        SELECT source_id, target_id, relation_type, incompleteness_category, context
          FROM claim_relations
         WHERE (source_id = ? OR target_id = ?)
           AND incompleteness_category != 'none'
        """,
        (claim_id, claim_id),
    ).fetchall()
    claim["integrity_warnings"] = [dict(w) for w in warnings]

    # Produce a citation-safe verbs hint from causal_strength.
    # Design_spec §2.2.5: paper-level default_causal_strength is inherited
    # by claims that don't override. If claim.causal_strength is missing
    # a field, fall back to the paper's default.
    claim_cs = claim.get("causal_strength") or {}
    effective_cs = {**paper_default_cs, **{k: v for k, v in claim_cs.items() if v is not None}}
    claim["effective_causal_strength"] = effective_cs
    claim["safe_verbs"] = _safe_verbs(effective_cs, claim.get("template_type"))

    claim["integrity_warnings_partial"] = bool(conn.execute(
        "SELECT 1 FROM pending_llm_review p "
        "WHERE json_extract(p.context_json, '$.citing_paper_id') = ? "
        "  AND p.review_type = 'paper_reference_resolution' "
        "  AND p.resolved_at IS NULL LIMIT 1",
        (claim["paper_id"],),
    ).fetchone())

    # Traffic-light cite-safety judgment derived from claim_status,
    # verification_status, design_basis vs author_framing, and the
    # incompleteness_category on every incident edge. See
    # citare_mcp.traffic_light for the rule set.
    from citare_mcp.traffic_light import compute_traffic_light
    claim["traffic_light"] = compute_traffic_light(claim, claim["integrity_warnings"])

    return claim


def get_claim_graph(conn: sqlite3.Connection, claim_id: str, depth: int = 1) -> dict[str, Any]:
    """Return the local neighbourhood of a claim up to ``depth`` hops.

    Output: {"claim_id": id, "neighbors": [...], "warnings": [...]}
    Warnings summarise integrity issues that should accompany any citation
    of ``claim_id`` — effect-disappears-under-control, hub-component, etc.
    """
    if depth < 1:
        raise ValueError("depth must be >= 1")
    visited = {claim_id}
    frontier = {claim_id}
    edges: list[dict[str, Any]] = []
    for _ in range(depth):
        if not frontier:
            break
        marks = ",".join("?" for _ in frontier)
        rows = conn.execute(
            f"""
            SELECT source_id, target_id, relation_type, incompleteness_category, context
              FROM claim_relations
             WHERE source_id IN ({marks}) OR target_id IN ({marks})
            """,
            list(frontier) + list(frontier),
        ).fetchall()
        next_frontier: set[str] = set()
        for r in rows:
            d = dict(r)
            edges.append(d)
            next_frontier.add(d["source_id"])
            next_frontier.add(d["target_id"])
        next_frontier -= visited
        visited.update(next_frontier)
        frontier = next_frontier

    # Collect minimal info for each visited claim
    marks = ",".join("?" for _ in visited)
    nodes = []
    for r in conn.execute(
        f"SELECT id, template_type, l0_json, paper_id, verification_status "
        f"FROM claims WHERE id IN ({marks})",
        list(visited),
    ).fetchall():
        nodes.append(dict(r))

    warnings = [
        {
            "source_id": e["source_id"],
            "target_id": e["target_id"],
            "category": e["incompleteness_category"],
            "context": e.get("context"),
        }
        for e in edges
        if e.get("incompleteness_category") and e["incompleteness_category"] != "none"
    ]

    return {
        "claim_id": claim_id,
        "nodes": nodes,
        "edges": edges,
        "warnings": warnings,
    }


_VERBS_BY_DESIGN = {
    "rct": ["causes", "increases", "decreases", "produces"],
    "longitudinal": ["predicts", "precedes", "is associated over time with"],
    "quasi_experimental": ["predicts", "affects"],
    "cross_sectional": ["is associated with", "correlates with"],
    "meta_analysis": ["is associated across studies with", "aggregates to"],
    "theoretical": ["is claimed to relate to", "is theorised to affect"],
    "computational_demonstration": ["is demonstrated computationally to", "empirically outperforms on"],
    "qualitative_field": ["is reported in the field to relate to"],
}


def _safe_verbs(cs: dict[str, Any], template_type: str | None) -> list[str]:
    """Suggest verbs that are safe given the claim's causal_strength.

    This is Citare's answer to "associated with" being silently upgraded to
    "causes" by downstream AI. A cross-sectional study should be cited with
    associational verbs, not causal ones, regardless of the author's framing.
    """
    if template_type == "DEFINITION":
        return ["defines", "characterises", "operationalises"]
    if template_type == "EXISTENCE_CLAIM":
        return ["reports", "observes", "documents"]
    if template_type == "META_CLAIM":
        return ["argues", "contends", "proposes"]
    design = (cs or {}).get("design_basis")
    return _VERBS_BY_DESIGN.get(design, ["is associated with"])
