"""Ingest Extraction objects into the identifier-aware Citare DB.

Ingestion policy (CitareMCP learnings applied):

 * **WARNING not REJECT.** Problems are logged; data is inserted. Rejection
   is reserved for structural violations (FK fails, CHECK fails) that SQLite
   raises itself.
 * **Paper resolution.** Try these in order to find an existing paper row:
     1. any identifier on the incoming paper matches paper_identifiers
     2. content_hash (normalised title + first author + year) matches
   On match: merge claims into that paper. On miss: create a new paper.
   A content-hash match with no identifier overlap emits a "possible
   duplicate" WARNING.
 * **Preferred identifier.** Chosen by fixed priority:
   ``doi > arxiv_doi > arxiv > pmid > isbn > internal_synthetic``. The ``is_preferred``
   flag is recomputed on every ingest for papers that gain new identifiers.
 * **Claim clash.** A claim id that already exists is overwritten, with an
   "overwrite" WARNING. An (iv, dv) match on an existing claim of the same
   paper is recorded in the returned report as a ``potential_duplicate_claims``
   entry — insertion is NOT skipped.

Returns an :class:`IngestReport` with the resolved paper_id and all warnings.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from citare_core import Extraction


_IDENTIFIER_PRIORITY = ("doi", "arxiv_doi", "arxiv", "pmid", "isbn", "internal_synthetic")


@dataclass
class IngestReport:
    """Result of ingesting one extraction."""
    paper_id: str
    created_paper: bool
    warnings: list[dict[str, Any]] = field(default_factory=list)
    potential_duplicate_claims: list[dict[str, Any]] = field(default_factory=list)

    def warn(self, code: str, **ctx: Any) -> None:
        self.warnings.append({"code": code, **ctx})


# ---------- identifier utilities ------------------------------------------------


_ARXIV_DOI_PREFIX = "10.48550/arXiv."


def classify_identifier(raw: str) -> tuple[str, str] | None:
    """Classify a raw identifier string into (type, normalised_value).

    Returns None if the string is empty / not recognisable.
    """
    if not raw:
        return None
    s = raw.strip()
    if s.lower().startswith("synthetic:"):
        return ("internal_synthetic", s)
    if s.startswith(_ARXIV_DOI_PREFIX):
        return ("arxiv_doi", s)
    if s.lower().startswith("arxiv:"):
        return ("arxiv", s.lower())
    if s.lower().startswith("arxiv."):
        return ("arxiv", "arxiv:" + s[len("arxiv."):])
    # plain arXiv like "2202.07799" (YYMM.NNNNN) or "cs.CL/0501001"
    if re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", s):
        return ("arxiv", "arxiv:" + s)
    if s.lower().startswith("pmid:"):
        return ("pmid", s.lower())
    if re.fullmatch(r"\d{7,9}", s) and len(s) <= 9:
        return ("pmid", f"pmid:{s}")
    if re.fullmatch(r"(?:97[89])?\d{9,13}[Xx]?", s):
        return ("isbn", s)
    # default: treat as DOI
    if "/" in s and s.lower().startswith("10."):
        return ("doi", s)
    # last-resort internal
    return ("internal_synthetic", "synthetic:" + s)


def _preferred_priority(identifier_type: str) -> int:
    try:
        return len(_IDENTIFIER_PRIORITY) - _IDENTIFIER_PRIORITY.index(identifier_type)
    except ValueError:
        return 0


def _normalise_title(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def _content_hash(title: str, authors: list[str], year: int | None) -> str:
    first_author = (authors[0] if authors else "").strip().lower()
    payload = f"{_normalise_title(title)}|{first_author}|{year or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _synthetic_id(paper_title: str, authors: list[str], year: int | None) -> str:
    """Stable synthetic internal ID per the CitareMCP G4 rule.

    Pattern: ``_no_doi_{FirstAuthorSurname}_{Year}_{titlehash}``. The title
    hash disambiguates multiple papers by the same first-author in the same year.
    """
    surname = "anon"
    if authors:
        first = authors[0].strip()
        # Best-effort last-name extraction: last whitespace-separated token
        if " " in first:
            surname = first.rsplit(" ", 1)[-1]
        else:
            surname = first
    surname = re.sub(r"[^A-Za-z0-9]", "", surname).lower() or "anon"
    yr = year or "nd"
    titlehash = hashlib.sha256(_normalise_title(paper_title).encode("utf-8")).hexdigest()[:6]
    return f"_no_doi_{surname}_{yr}_{titlehash}"


def collect_paper_identifiers(extraction: Extraction) -> list[tuple[str, str]]:
    """Extract all known identifiers from an Extraction object.

    Looks at paper.doi, plus any identifier-like fields the LLM may have
    emitted in pydantic-extra attributes. Returns a list of ``(type, value)``
    tuples.
    """
    p = extraction.paper
    out: list[tuple[str, str]] = []
    if p.doi:
        cls = classify_identifier(p.doi)
        if cls:
            out.append(cls)
    # Tolerate "identifiers": [...] or "arxiv_id" in extra fields
    extra = getattr(p, "__pydantic_extra__", None) or {}
    for key in ("arxiv_id", "arxiv", "pmid", "identifier"):
        val = extra.get(key)
        if isinstance(val, str):
            cls = classify_identifier(val)
            if cls:
                out.append(cls)
    idents_list = extra.get("identifiers")
    if isinstance(idents_list, list):
        for v in idents_list:
            if isinstance(v, str):
                cls = classify_identifier(v)
                if cls:
                    out.append(cls)
    # Dedup preserving order
    seen: set[tuple[str, str]] = set()
    unique: list[tuple[str, str]] = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
    return unique


def choose_paper_id(identifiers: list[tuple[str, str]], fallback_title: str,
                     authors: list[str], year: int | None) -> str:
    """Pick the canonical paper.id from the list of identifiers.

    Rule: highest-priority identifier's value. If no identifier at all,
    generate a synthetic internal id.
    """
    if not identifiers:
        return _synthetic_id(fallback_title, authors, year)
    # Sort by priority, take value of highest-priority
    identifiers_sorted = sorted(
        identifiers, key=lambda x: _preferred_priority(x[0]), reverse=True
    )
    return identifiers_sorted[0][1]


# ---------- paper resolution ----------------------------------------------------


def _find_paper_by_identifiers(conn: sqlite3.Connection,
                                idents: list[tuple[str, str]]) -> str | None:
    for it, iv in idents:
        row = conn.execute(
            "SELECT paper_id FROM paper_identifiers "
            "WHERE identifier_type = ? AND identifier_value = ?",
            (it, iv),
        ).fetchone()
        if row is not None:
            return row["paper_id"]
    return None


def _find_paper_by_content_hash(conn: sqlite3.Connection, h: str) -> str | None:
    row = conn.execute(
        "SELECT id FROM papers WHERE content_hash = ? LIMIT 1", (h,)
    ).fetchone()
    return row["id"] if row else None


def _upsert_paper_identifier(conn: sqlite3.Connection,
                              ident_type: str, ident_value: str,
                              paper_id: str, source: str = "extraction") -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO paper_identifiers
            (identifier_type, identifier_value, paper_id, is_preferred, source)
        VALUES (?, ?, ?, 0, ?)
        """,
        (ident_type, ident_value, paper_id, source),
    )


def _recompute_preferred(conn: sqlite3.Connection, paper_id: str) -> None:
    rows = conn.execute(
        "SELECT identifier_type, identifier_value FROM paper_identifiers "
        "WHERE paper_id = ?",
        (paper_id,),
    ).fetchall()
    if not rows:
        return
    best = max(rows, key=lambda r: _preferred_priority(r["identifier_type"]))
    conn.execute(
        "UPDATE paper_identifiers SET is_preferred = 0 WHERE paper_id = ?",
        (paper_id,),
    )
    conn.execute(
        "UPDATE paper_identifiers SET is_preferred = 1 "
        "WHERE paper_id = ? AND identifier_type = ? AND identifier_value = ?",
        (paper_id, best["identifier_type"], best["identifier_value"]),
    )


# ---------- main ingest --------------------------------------------------------


def _jsonify(obj: Any) -> str | None:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        d = obj.model_dump(exclude_none=True)
        return json.dumps(d, ensure_ascii=False) if d else None
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False) if obj else None
    return json.dumps(obj, ensure_ascii=False)


def ingest_extraction(conn: sqlite3.Connection, extraction: Extraction) -> IngestReport:
    p = extraction.paper
    idents = collect_paper_identifiers(extraction)
    chash = _content_hash(p.title, p.authors, p.year)

    existing_paper_id = _find_paper_by_identifiers(conn, idents)
    report_created = False
    if existing_paper_id is None:
        hash_match = _find_paper_by_content_hash(conn, chash)
        if hash_match is not None:
            existing_paper_id = hash_match
            report = IngestReport(paper_id=existing_paper_id, created_paper=False)
            report.warn(
                "paper_possible_duplicate",
                detail=(
                    "No identifier overlap, but content_hash (title + first author + year) "
                    "matched an existing paper."
                ),
                matched_paper_id=existing_paper_id,
                incoming_title=p.title,
            )
        else:
            # New paper
            new_id = choose_paper_id(idents, p.title, p.authors, p.year)
            conn.execute(
                """
                INSERT INTO papers (id, canonical_title, authors, year, venue, paper_type,
                                    domain, content_hash,
                                    default_causal_strength, default_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id, p.title,
                    json.dumps(p.authors, ensure_ascii=False),
                    p.year, p.venue,
                    p.paper_type.value if p.paper_type else None,
                    p.domain,
                    chash,
                    _jsonify(p.default_causal_strength),
                    _jsonify(p.default_method),
                ),
            )
            existing_paper_id = new_id
            report_created = True
            report = IngestReport(paper_id=new_id, created_paper=True)
    else:
        # Existing paper — update bibliographic fields (title/year may have
        # improved with a better extraction). Authors / defaults only overwrite
        # if the new value is non-null.
        report = IngestReport(paper_id=existing_paper_id, created_paper=False)
        conn.execute(
            """
            UPDATE papers
               SET canonical_title = COALESCE(?, canonical_title),
                   year = COALESCE(?, year),
                   venue = COALESCE(?, venue),
                   paper_type = COALESCE(?, paper_type),
                   domain = COALESCE(?, domain),
                   default_causal_strength = COALESCE(?, default_causal_strength),
                   default_method = COALESCE(?, default_method),
                   content_hash = ?
             WHERE id = ?
            """,
            (
                p.title, p.year, p.venue,
                p.paper_type.value if p.paper_type else None,
                p.domain,
                _jsonify(p.default_causal_strength),
                _jsonify(p.default_method),
                chash,
                existing_paper_id,
            ),
        )

    # Insert identifier rows (ignore conflicts — identifier may already exist)
    for (it, iv) in idents:
        _upsert_paper_identifier(conn, it, iv, existing_paper_id)
    if not idents:
        # Register an internal_synthetic identifier for this paper_id so the
        # identifiers table is never empty for a paper.
        _upsert_paper_identifier(conn, "internal_synthetic", existing_paper_id,
                                  existing_paper_id)
    _recompute_preferred(conn, existing_paper_id)

    # Claims
    existing_claim_ids = {
        r[0] for r in conn.execute(
            "SELECT id FROM claims WHERE paper_id = ?", (existing_paper_id,)
        ).fetchall()
    }
    existing_iv_dv = {}
    for r in conn.execute(
        "SELECT id, iv_idx, dv_idx FROM claims WHERE paper_id = ? AND template_type = 'RELATION'",
        (existing_paper_id,),
    ).fetchall():
        if r["iv_idx"] and r["dv_idx"]:
            existing_iv_dv.setdefault((r["iv_idx"], r["dv_idx"]), []).append(r["id"])

    for c in extraction.claims:
        # (iv, dv) duplicate detection (informational, not blocking)
        l0 = c.l0_json or {}
        if c.template_type.value == "RELATION":
            iv = l0.get("iv"); dv = l0.get("dv")
            if iv and dv and (iv, dv) in existing_iv_dv:
                prev_ids = [cid for cid in existing_iv_dv[(iv, dv)] if cid != c.id]
                if prev_ids:
                    report.potential_duplicate_claims.append({
                        "incoming_claim_id": c.id,
                        "iv": iv, "dv": dv,
                        "existing_claim_ids": prev_ids,
                    })

        if c.id in existing_claim_ids:
            report.warn("claim_overwrite", claim_id=c.id)

        conn.execute(
            """
            INSERT INTO claims (
                id, paper_id, template_type,
                l0_json, l1_subject, l1_predicate, l1_object,
                l2_en, l2_ja, l3_json,
                source_text, source_page, source_section, source_paragraph,
                evidence_type, verification_status,
                causal_strength, method_metadata,
                model_hub, confidence_level, confidence_score,
                extraction_prompt_version, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              paper_id = excluded.paper_id,
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
                c.id, existing_paper_id, c.template_type.value,
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
        # FTS5 index
        conn.execute(
            "INSERT INTO claims_fts (claim_id, source_text, l2_en, l1_subject, l1_object) "
            "VALUES (?, ?, ?, ?, ?)",
            (c.id, c.source_text or "", c.l2_en or "", c.l1_subject or "", c.l1_object or ""),
        )

    # Relations
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
        mid = m.id or f"{existing_paper_id}_mm_{hash(m.measures or '')%10000}"
        conn.execute(
            """
            INSERT OR REPLACE INTO measurement_methods
                (id, paper_id, measures, instrument_name, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (mid, existing_paper_id, m.measures, m.instrument_name, _jsonify(m.details)),
        )

    # Paper references — write to citation_text (verbatim + parsed fields).
    # Resolution to citation_edges is done separately by resolver.resolve_citations.
    from citare_db.parser import parse as parse_reference, PARSER_VERSION

    for idx, ref in enumerate(extraction.paper_references):
        # Prefer raw_reference_text if v0.13+ prompt captured it; else fall
        # back to cited_title (legacy shorthand form).
        raw = (ref.raw_reference_text or "").strip()
        if not raw:
            raw = (ref.cited_title or "").strip()
        if not raw:
            continue

        parsed = parse_reference(raw)
        # If the Extraction carries a structured cited_doi but the parser
        # missed it, trust the structured field.
        parsed_doi = parsed.doi or (ref.cited_doi or None)
        parsed_arxiv = parsed.arxiv or (ref.cited_arxiv or None)
        parsed_year = parsed.year or ref.cited_year
        parsed_authors = parsed.authors or (list(ref.cited_authors) if ref.cited_authors else None)
        parsed_title = parsed.title or ref.cited_title

        conn.execute(
            """
            INSERT INTO citation_text
                (citing_paper_id, position_in_refs, raw_reference_text,
                 parsed_doi, parsed_arxiv, parsed_year, parsed_authors,
                 parsed_title, parsed_venue, parser_version, parsed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                existing_paper_id,
                ref.position_in_refs if ref.position_in_refs is not None else idx,
                raw,
                parsed_doi,
                parsed_arxiv,
                parsed_year,
                json.dumps(parsed_authors, ensure_ascii=False) if parsed_authors else None,
                parsed_title,
                parsed.venue or ref.cited_venue,
                PARSER_VERSION,
            ),
        )

    conn.commit()
    return report


def ingest_extraction_file(conn: sqlite3.Connection, path: str | Path) -> IngestReport:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    ext = Extraction.model_validate(data)
    return ingest_extraction(conn, ext)
