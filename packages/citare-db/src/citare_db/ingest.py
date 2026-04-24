"""Ingest extraction.json files into the Citare SQLite DB.

Philosophy: deduplication is by (paper_doi, claim_id). Re-ingesting the same
extraction is a no-op on the paper side but replaces claims (most recent
extraction wins). We do NOT preserve prior-version claims here — version
history lives in the extraction run directory on disk.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from citare_core import Extraction


def _synthetic_doi(paper_title: str, authors: list[str]) -> str:
    """Stable surrogate DOI for papers lacking a real one."""
    payload = (paper_title + "|" + "|".join(authors)).lower().encode("utf-8")
    return "synthetic:" + hashlib.sha256(payload).hexdigest()[:16]


def _jsonify(obj: Any) -> str | None:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        d = obj.model_dump(exclude_none=True)
        return json.dumps(d, ensure_ascii=False) if d else None
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False) if obj else None
    return json.dumps(obj, ensure_ascii=False)


def ingest_extraction(conn: sqlite3.Connection, extraction: Extraction) -> str:
    """Insert paper + claims + relations + measurements + references.

    Returns the resolved paper DOI used (possibly synthetic).
    """
    paper = extraction.paper
    doi = paper.doi or _synthetic_doi(paper.title, paper.authors)

    # Paper upsert
    conn.execute(
        """
        INSERT INTO papers (doi, title, authors, year, venue, paper_type, domain,
                            default_causal_strength, default_method)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(doi) DO UPDATE SET
          title = excluded.title,
          authors = excluded.authors,
          year = excluded.year,
          venue = excluded.venue,
          paper_type = excluded.paper_type,
          domain = excluded.domain,
          default_causal_strength = excluded.default_causal_strength,
          default_method = excluded.default_method
        """,
        (
            doi,
            paper.title,
            json.dumps(paper.authors, ensure_ascii=False),
            paper.year,
            paper.venue,
            paper.paper_type.value if paper.paper_type else None,
            paper.domain,
            _jsonify(paper.default_causal_strength),
            _jsonify(paper.default_method),
        ),
    )

    # Claims: replace-by-id
    for c in extraction.claims:
        conn.execute(
            """
            INSERT INTO claims (
                id, paper_doi, template_type,
                l0_json, l1_subject, l1_predicate, l1_object,
                l2_en, l2_ja, l3_json,
                source_text, source_page, source_section, source_paragraph,
                evidence_type, verification_status,
                causal_strength, method_metadata,
                model_hub, confidence_level, confidence_score,
                extraction_prompt_version, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              paper_doi = excluded.paper_doi,
              template_type = excluded.template_type,
              l0_json = excluded.l0_json,
              l1_subject = excluded.l1_subject, l1_predicate = excluded.l1_predicate, l1_object = excluded.l1_object,
              l2_en = excluded.l2_en, l2_ja = excluded.l2_ja, l3_json = excluded.l3_json,
              source_text = excluded.source_text, source_page = excluded.source_page,
              source_section = excluded.source_section, source_paragraph = excluded.source_paragraph,
              evidence_type = excluded.evidence_type, verification_status = excluded.verification_status,
              causal_strength = excluded.causal_strength, method_metadata = excluded.method_metadata,
              model_hub = excluded.model_hub, confidence_level = excluded.confidence_level,
              confidence_score = excluded.confidence_score,
              extraction_prompt_version = excluded.extraction_prompt_version,
              updated_at = CURRENT_TIMESTAMP
            """,
            (
                c.id, doi, c.template_type.value,
                _jsonify(c.l0_json), c.l1_subject, c.l1_predicate, c.l1_object,
                c.l2_en, c.l2_ja, _jsonify(c.l3_json),
                c.source_text, c.source_page, c.source_section, c.source_paragraph,
                c.evidence_type,
                c.verification_status.value if c.verification_status else None,
                _jsonify(c.causal_strength), _jsonify(c.method_metadata),
                int(c.model_hub), c.confidence_level, c.confidence_score,
                c.extraction_prompt_version, c.status,
            ),
        )

    # Claim relations
    for r in extraction.claim_relations:
        conn.execute(
            """
            INSERT OR REPLACE INTO claim_relations
                (source_id, target_id, relation_type, incompleteness_category, context, confidence_score)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                r.source_id, r.target_id, r.relation_type.value,
                r.incompleteness_category.value, r.context, r.confidence_score,
            ),
        )

    # Measurement methods
    for m in extraction.measurement_methods:
        mid = m.id or f"{doi}_mm_{hash(m.measures or '')%10000}"
        conn.execute(
            """
            INSERT OR REPLACE INTO measurement_methods
                (id, paper_doi, measures, instrument_name, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (mid, doi, m.measures, m.instrument_name, _jsonify(m.details)),
        )

    # Paper references
    for ref in extraction.paper_references:
        citing = ref.citing_doi or doi
        cited = ref.cited_doi or ""
        title = ref.cited_title or ""
        if not cited and not title:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO paper_references (citing_doi, cited_doi, cited_title)
            VALUES (?, ?, ?)
            """,
            (citing, cited, title),
        )

    conn.commit()
    return doi


def ingest_extraction_file(conn: sqlite3.Connection, path: str | Path) -> str:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    ext = Extraction.model_validate(data)
    return ingest_extraction(conn, ext)
