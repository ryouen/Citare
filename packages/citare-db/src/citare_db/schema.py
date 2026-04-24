"""Citare SQLite schema (v0.2 — identifier-aware).

Changes from v0.1:
 - ``papers.id`` is now the primary key (no longer ``doi``). Population rule:
   DOI-if-present, else ``arxiv:{id}``, else UUID v4. The concrete choice is
   made at ingest time by :func:`citare_db.ingest.assign_paper_id`.
 - ``paper_identifiers`` is a new one-to-many table that records every alias
   by which a paper is known (journal DOI, arXiv DOI, arXiv ID, PMID, ISBN,
   synthetic fallback). Exactly one row per paper has ``is_preferred = 1``.
 - ``claims.paper_doi`` is renamed to ``claims.paper_id``.
 - ``paper_references`` is enriched with ``cited_as_type``/``cited_as_value``
   (what the author wrote) and ``resolved_paper_id`` (where we've linked it
   in this DB; nullable for later resolution).
 - Empty tables added for future use: ``paper_versions``, ``revision_history``,
   ``concept_evolution``, ``theory_concept_roles``.

The CitareMCP learning-doc motivates each of these: identifier multiplicity
(Gap 2), synthetic-DOI rules (Gap 4), audit trail (pattern 9), future
tables (pattern 10).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
-- A paper as an intellectual work. id is DOI | 'arxiv:X' | UUID.
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    authors TEXT NOT NULL,            -- JSON array
    year INTEGER,
    venue TEXT,
    paper_type TEXT,
    domain TEXT,
    content_hash TEXT,                -- normalized_title + first_author + year, for dedup
    default_causal_strength TEXT,     -- JSON
    default_method TEXT,              -- JSON
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_papers_content_hash ON papers(content_hash);
CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(year);

-- Many aliases -> one canonical paper. (type, value) is globally unique.
CREATE TABLE IF NOT EXISTS paper_identifiers (
    identifier_type TEXT NOT NULL
        CHECK(identifier_type IN ('doi','arxiv','arxiv_doi','pmid','isbn','internal_synthetic')),
    identifier_value TEXT NOT NULL,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    is_preferred INTEGER DEFAULT 0,
    source TEXT                       -- LLM-native only: no human input accepted
        CHECK(source IN ('extraction','batch_llm_review','crossref','openalex') OR source IS NULL),
    verified_at TIMESTAMP,
    PRIMARY KEY (identifier_type, identifier_value)
);
CREATE INDEX IF NOT EXISTS idx_ident_paper ON paper_identifiers(paper_id);
-- exactly one preferred alias per paper, enforced by partial unique index
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_preferred_per_paper
    ON paper_identifiers(paper_id) WHERE is_preferred = 1;

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    template_type TEXT NOT NULL
        CHECK(template_type IN ('DEFINITION','RELATION','EXISTENCE_CLAIM','META_CLAIM')),

    l0_json TEXT,
    l1_subject TEXT, l1_predicate TEXT, l1_object TEXT,
    l2_en TEXT, l2_ja TEXT,
    l3_json TEXT,

    source_text TEXT, source_page INTEGER, source_section TEXT, source_paragraph TEXT,

    evidence_type TEXT,
    verification_status TEXT
        CHECK(verification_status IN (
            'verified_in_paper','proposed_in_paper','not_supported',
            'mixed_support','partial_support'
        ) OR verification_status IS NULL),

    causal_strength TEXT,
    method_metadata TEXT,

    model_hub INTEGER DEFAULT 0,
    confidence_level TEXT, confidence_score REAL,

    extraction_prompt_version TEXT,

    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
    author_framing_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL,
    iv_idx TEXT GENERATED ALWAYS AS (json_extract(l0_json, '$.iv')) VIRTUAL,
    dv_idx TEXT GENERATED ALWAYS AS (json_extract(l0_json, '$.dv')) VIRTUAL
);
CREATE INDEX IF NOT EXISTS idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX IF NOT EXISTS idx_claims_author_framing ON claims(author_framing_idx);
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(l1_subject);
CREATE INDEX IF NOT EXISTS idx_claims_object ON claims(l1_object);
CREATE INDEX IF NOT EXISTS idx_claims_template ON claims(template_type);
CREATE INDEX IF NOT EXISTS idx_claims_iv ON claims(iv_idx);
CREATE INDEX IF NOT EXISTS idx_claims_dv ON claims(dv_idx);

-- FTS5 for free-text search across source_text + l2_en
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id UNINDEXED,
    source_text,
    l2_en,
    l1_subject,
    l1_object,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS claim_relations (
    source_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
    target_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    incompleteness_category TEXT DEFAULT 'none'
        CHECK(incompleteness_category IN (
            'effect_disappears_under_control','hub_component',
            'boundary_condition','extends_prior_definition','none')),
    context TEXT,
    confidence_score REAL,
    PRIMARY KEY (source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_incompleteness
    ON claim_relations(incompleteness_category)
    WHERE incompleteness_category != 'none';

-- ===== Citation model (structural split) ==================================
-- (A) citation_text: verbatim bibliographic entries from the citing paper's
--     References section. LLM extractions write here without reformatting.
-- (B) citation_edges: resolved links to canonical papers in this DB. Derived
--     from citation_text by deterministic parser + resolver chain. Can be
--     rebuilt at any time; raw text is immutable.
-- This split is motivated by CitareMCP-style separation-of-concerns and by
-- the T7 finding that extractors reformat References at capture time,
-- losing DOIs. Keeping the raw text protects against extraction-time loss.

CREATE TABLE IF NOT EXISTS citation_text (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    citing_paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    position_in_refs INTEGER,
    raw_reference_text TEXT NOT NULL,

    parsed_doi TEXT,
    parsed_arxiv TEXT,
    parsed_year INTEGER,
    parsed_authors TEXT,              -- JSON array of surnames
    parsed_title TEXT,
    parsed_venue TEXT,
    parser_version TEXT,
    parsed_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cite_text_paper ON citation_text(citing_paper_id);
CREATE INDEX IF NOT EXISTS idx_cite_text_parsed_doi ON citation_text(parsed_doi);
CREATE INDEX IF NOT EXISTS idx_cite_text_parsed_year ON citation_text(parsed_year);

CREATE TABLE IF NOT EXISTS citation_edges (
    citation_text_id INTEGER REFERENCES citation_text(id) ON DELETE CASCADE,
    resolved_paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
    resolution_method TEXT            -- 'doi_match' | 'arxiv_match' | 'year_author_title' | 'crossref' | 'llm_batch'
        CHECK(resolution_method IN (
            'doi_match','arxiv_match','year_author_title','crossref','openalex','llm_batch'
        ) OR resolution_method IS NULL),
    confidence REAL,
    resolved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_by TEXT,                 -- 'ingest-parser' | 'claude-opus-4-7' | ...
    PRIMARY KEY (citation_text_id)
);
CREATE INDEX IF NOT EXISTS idx_cite_edge_paper ON citation_edges(resolved_paper_id);

-- LLM-native review queue: ambiguous cases the mechanical resolver cannot
-- decide. Consumed by a future batch LLM reviewer. Humans never read this.
CREATE TABLE IF NOT EXISTS pending_llm_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type TEXT NOT NULL         -- 'paper_reference_resolution' | 'claim_duplicate' | 'concept_alias' | ...
        CHECK(review_type IN ('paper_reference_resolution','claim_duplicate','concept_alias')),
    context_json TEXT NOT NULL,       -- payload specific to review_type
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    resolved_by_model TEXT,           -- 'claude-opus-4-7' | ...
    resolved_by_prompt TEXT,          -- prompt version for the resolver
    resolution_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_type ON pending_llm_review(review_type, resolved_at);

CREATE TABLE IF NOT EXISTS measurement_methods (
    id TEXT,
    paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
    measures TEXT,
    instrument_name TEXT,
    details TEXT,
    PRIMARY KEY (paper_id, id)
);

CREATE TABLE IF NOT EXISTS concepts (
    canonical_name TEXT PRIMARY KEY,
    level TEXT,
    description TEXT,
    aliases TEXT
);

CREATE TABLE IF NOT EXISTS theories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

-- ===== Future tables (empty for v1, pre-declared per pattern 10) ===========

CREATE TABLE IF NOT EXISTS paper_versions (
    paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
    version_label TEXT,
    published_date DATE,
    source_url TEXT,
    PRIMARY KEY (paper_id, version_label)
);

-- LLM-native audit log. No by_user: Citare is LLM-only; every write is
-- attributed to a model + prompt + extraction run. Populated by future
-- write APIs; MVP does not write to this table, but its shape is frozen.
CREATE TABLE IF NOT EXISTS revision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id TEXT,
    action TEXT,                     -- 'insert' | 'update' | 'deprecate'
    field TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    by_model TEXT,                   -- 'claude-opus-4-7' | 'batch-reviewer-v1' | ...
    prompt_version TEXT,             -- 'v0.12e' | 'v0.13_refs' | ...
    run_id TEXT,                     -- extraction or review run this edit belongs to
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Concept drift over time; populated in batch when enough papers accumulate.
CREATE TABLE IF NOT EXISTS concept_evolution (
    canonical_name TEXT REFERENCES concepts(canonical_name),
    year INTEGER,
    definition_variant TEXT,
    exemplar_claim_id TEXT REFERENCES claims(id),
    PRIMARY KEY (canonical_name, year, definition_variant)
);

-- Theory membership / role of a concept within a theory; future phase.
CREATE TABLE IF NOT EXISTS theory_concept_roles (
    theory_id TEXT REFERENCES theories(id) ON DELETE CASCADE,
    canonical_name TEXT REFERENCES concepts(canonical_name),
    role TEXT,
    PRIMARY KEY (theory_id, canonical_name)
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) a SQLite DB at ``db_path`` and apply the schema.

    Returns a connection with ``foreign_keys`` ON and ``Row`` factory set.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
