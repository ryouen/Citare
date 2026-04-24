"""Mechanical (non-LLM) resolver chain over citation_text -> citation_edges.

Stages, applied in order to each unresolved citation_text row:

  **Stage 1 — identifier match.**  parsed_doi or parsed_arxiv matches a row
  in paper_identifiers. Resolution method: 'doi_match' or 'arxiv_match'.

  **Stage 2 — (year + first_author_surname + title) triple match.**  All
  three signals must agree with a candidate paper's year, first-author
  surname, and a non-trivial title overlap. Resolution method:
  'year_author_title'.

  **Stage 3 — queue to pending_llm_review.**  Any row that has ambiguous
  stage-2 candidates (multiple matches) or no deterministic match is
  enqueued for a future LLM batch reviewer. No human ever reads this queue.

Deterministic, idempotent, retroactive: re-running after new papers are
ingested upgrades resolution for previously-unresolved entries.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any


_PUNCT_RE = re.compile(r"[^\w\s]+")
_WS_RE = re.compile(r"\s+")


def _normalise_title(t: str) -> str:
    t = (t or "").strip().lower()
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t)
    return t.strip()


def _title_overlap(a: str, b: str) -> float:
    """Return a symmetric overlap score in [0, 1] between two normalised titles.

    Uses unigram Jaccard over the tokenised titles. Returns 0 for very short
    strings (<3 tokens) to avoid false positives.
    """
    na, nb = _normalise_title(a), _normalise_title(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    if len(ta) < 3 or len(tb) < 3:
        # Very short titles — accept only exact match
        return 1.0 if na == nb else 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _first_author_surname(paper_authors_json: str | None) -> str | None:
    if not paper_authors_json:
        return None
    try:
        authors = json.loads(paper_authors_json)
    except json.JSONDecodeError:
        return None
    if not authors:
        return None
    first = authors[0].strip()
    # "Edmondson, A." -> "Edmondson"
    if "," in first:
        return first.split(",", 1)[0].strip().lower()
    parts = first.split()
    if not parts:
        return None
    # Last token is the surname in most Western formats
    return parts[-1].strip().lower()


@dataclass
class ResolverReport:
    """Summary of a resolver run."""
    scanned: int = 0
    resolved_by_identifier: int = 0
    resolved_by_triple: int = 0
    queued_for_llm: int = 0
    already_resolved: int = 0
    unresolved_after_chain: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _has_edge(conn: sqlite3.Connection, citation_text_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM citation_edges WHERE citation_text_id = ?",
        (citation_text_id,),
    ).fetchone()
    return row is not None


def _insert_edge(
    conn: sqlite3.Connection,
    citation_text_id: int,
    resolved_paper_id: str,
    method: str,
    confidence: float,
    resolved_by: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO citation_edges
            (citation_text_id, resolved_paper_id, resolution_method,
             confidence, resolved_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (citation_text_id, resolved_paper_id, method, confidence, resolved_by),
    )


def _enqueue_review(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO pending_llm_review (review_type, context_json)
        VALUES ('paper_reference_resolution', ?)
        """,
        (json.dumps(payload, ensure_ascii=False),),
    )


def resolve_citations(conn: sqlite3.Connection) -> ResolverReport:
    """Run the resolver chain over all citation_text rows.

    Stage 3 enqueues unresolved rows; it does NOT call any LLM — that is the
    responsibility of the batch reviewer service (not part of this module).
    """
    report = ResolverReport()
    rows = conn.execute(
        """
        SELECT id, citing_paper_id, raw_reference_text,
               parsed_doi, parsed_arxiv, parsed_year, parsed_authors, parsed_title
          FROM citation_text
        """
    ).fetchall()

    # Cache canonical paper index: id -> (title, year, first_author_surname)
    paper_rows = conn.execute(
        "SELECT id, canonical_title, year, authors FROM papers"
    ).fetchall()
    paper_index: list[tuple[str, str, int | None, str | None]] = []
    for p in paper_rows:
        paper_index.append((
            p["id"],
            p["canonical_title"] or "",
            p["year"],
            _first_author_surname(p["authors"]),
        ))

    for r in rows:
        report.scanned += 1
        ctid = r["id"]

        if _has_edge(conn, ctid):
            report.already_resolved += 1
            continue

        # Stage 1 — identifier match
        resolved = None
        method = None
        if r["parsed_doi"]:
            hit = conn.execute(
                "SELECT paper_id FROM paper_identifiers "
                "WHERE identifier_type = 'doi' AND identifier_value = ?",
                (r["parsed_doi"],),
            ).fetchone()
            if hit:
                resolved = hit["paper_id"]
                method = "doi_match"
        if resolved is None and r["parsed_arxiv"]:
            # Try arxiv / arxiv_doi
            for t in ("arxiv", "arxiv_doi"):
                hit = conn.execute(
                    "SELECT paper_id FROM paper_identifiers "
                    "WHERE identifier_type = ? AND identifier_value = ?",
                    (t, r["parsed_arxiv"]),
                ).fetchone()
                if hit:
                    resolved = hit["paper_id"]
                    method = "arxiv_match"
                    break

        if resolved is not None:
            # Avoid self-citation
            if resolved != r["citing_paper_id"]:
                _insert_edge(conn, ctid, resolved, method, 1.0, "ingest-parser")
                report.resolved_by_identifier += 1
                continue

        # Stage 2 — year + first_author_surname + title triple match
        if r["parsed_year"] and r["parsed_authors"] and r["parsed_title"]:
            try:
                cited_authors = json.loads(r["parsed_authors"])
            except json.JSONDecodeError:
                cited_authors = []
            cited_first = (cited_authors[0].lower() if cited_authors else "").strip()

            candidates = []
            for pid, ptitle, pyear, psurname in paper_index:
                if pid == r["citing_paper_id"]:
                    continue
                if pyear != r["parsed_year"]:
                    continue
                if psurname != cited_first:
                    continue
                overlap = _title_overlap(r["parsed_title"], ptitle)
                if overlap >= 0.4:
                    candidates.append((pid, overlap))

            if len(candidates) == 1:
                best = candidates[0]
                _insert_edge(conn, ctid, best[0], "year_author_title",
                             best[1], "ingest-parser")
                report.resolved_by_triple += 1
                continue
            if len(candidates) > 1:
                # Pick the highest overlap if it's unambiguously best, else queue
                candidates.sort(key=lambda x: x[1], reverse=True)
                if candidates[0][1] - candidates[1][1] >= 0.2:
                    _insert_edge(conn, ctid, candidates[0][0],
                                 "year_author_title", candidates[0][1],
                                 "ingest-parser")
                    report.resolved_by_triple += 1
                    continue
                # Ambiguous — queue for LLM review
                _enqueue_review(conn, {
                    "citation_text_id": ctid,
                    "citing_paper_id": r["citing_paper_id"],
                    "raw_reference_text": r["raw_reference_text"],
                    "parsed_title": r["parsed_title"],
                    "parsed_year": r["parsed_year"],
                    "parsed_authors": cited_authors,
                    "candidate_paper_ids": [c[0] for c in candidates],
                    "reason": "ambiguous_triple_match",
                })
                report.queued_for_llm += 1
                continue

        # Stage 3 — no deterministic match: queue for LLM review
        _enqueue_review(conn, {
            "citation_text_id": ctid,
            "citing_paper_id": r["citing_paper_id"],
            "raw_reference_text": r["raw_reference_text"],
            "parsed_title": r["parsed_title"],
            "parsed_year": r["parsed_year"],
            "parsed_authors": json.loads(r["parsed_authors"]) if r["parsed_authors"] else [],
            "reason": "no_deterministic_match",
        })
        report.queued_for_llm += 1
        report.unresolved_after_chain += 1

    conn.commit()
    return report
