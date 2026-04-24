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
    search uses LIKE on source_text + l2_en + l1_subject + l1_object.
    """
    if not any([query, doi, iv, dv, template_type]):
        raise ValueError("at least one of query / doi / iv / dv / template_type is required")

    where: list[str] = []
    params: list[Any] = []

    if doi:
        where.append("paper_id = ?")
        params.append(doi)
    if iv:
        where.append("(l1_subject LIKE ? OR json_extract(l0_json, '$.iv') LIKE ?)")
        params.extend([f"%{iv}%", f"%{iv}%"])
    if dv:
        where.append("(l1_object LIKE ? OR json_extract(l0_json, '$.dv') LIKE ?)")
        params.extend([f"%{dv}%", f"%{dv}%"])
    if template_type:
        where.append("template_type = ?")
        params.append(template_type)
    if query:
        like = f"%{query}%"
        where.append("(source_text LIKE ? OR l2_en LIKE ? OR l1_subject LIKE ? OR l1_object LIKE ?)")
        params.extend([like, like, like, like])

    sql = (
        "SELECT id, paper_id, template_type, l0_json, l1_subject, l1_predicate, l1_object, "
        "l2_en, source_text, source_page, source_section, evidence_type, verification_status, "
        "causal_strength, method_metadata, confidence_score "
        "FROM claims WHERE " + " AND ".join(where) +
        " ORDER BY confidence_score DESC NULLS LAST LIMIT ?"
    )
    params.append(limit)
    return [_row_to_claim(r) for r in conn.execute(sql, params).fetchall()]


def cite_claim(conn: sqlite3.Connection, claim_id: str) -> dict[str, Any]:
    """Return a full citation bundle for one claim.

    Includes: the claim fields, the paper's bibliographic info, and a
    list of integrity warnings from any claim_relation edges this claim
    participates in. This is the endpoint designed for use inside AI
    applications that need a safe-to-cite unit.
    """
    row = conn.execute(
        "SELECT * FROM claims WHERE id = ?", (claim_id,)
    ).fetchone()
    if row is None:
        return {"error": f"claim not found: {claim_id}", "claim_id": claim_id}
    claim = _row_to_claim(row)

    paper = conn.execute(
        "SELECT id, canonical_title, authors, year, venue, paper_type, domain "
        "FROM papers WHERE id = ?",
        (claim["paper_id"],),
    ).fetchone()
    if paper is not None:
        paper_dict = dict(paper)
        try:
            paper_dict["authors"] = json.loads(paper_dict["authors"])
        except (TypeError, json.JSONDecodeError):
            pass
        # Include all known identifiers for this paper
        idents = conn.execute(
            "SELECT identifier_type, identifier_value, is_preferred "
            "FROM paper_identifiers WHERE paper_id = ? ORDER BY is_preferred DESC",
            (paper_dict["id"],),
        ).fetchall()
        paper_dict["identifiers"] = [dict(r) for r in idents]
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

    # Produce a citation-safe verbs hint from causal_strength
    cs = claim.get("causal_strength") or {}
    claim["safe_verbs"] = _safe_verbs(cs, claim.get("template_type"))

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
        f"SELECT id, template_type, l1_subject, l1_predicate, l1_object, l2_en, paper_id, verification_status "
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
