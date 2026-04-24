"""Citare SQLite schema.

Matches design_spec §2 with one compromise: Paper.doi is a TEXT PRIMARY KEY
but we allow synthetic DOIs of the form ``synthetic:{hash}`` for papers
that don't have a real DOI yet. The synthetic marker is conventional
(not enforced by CHECK) so downstream tooling can filter.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS papers (
    doi TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,        -- JSON array
    year INTEGER,
    venue TEXT,
    paper_type TEXT,
    domain TEXT,
    default_causal_strength TEXT, -- JSON
    default_method TEXT           -- JSON
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    paper_doi TEXT NOT NULL REFERENCES papers(doi) ON DELETE CASCADE,
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

    causal_strength TEXT, -- JSON
    method_metadata TEXT, -- JSON

    model_hub INTEGER DEFAULT 0,
    confidence_level TEXT, confidence_score REAL,

    extraction_prompt_version TEXT,

    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
    author_framing_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing')) VIRTUAL
);

CREATE INDEX IF NOT EXISTS idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX IF NOT EXISTS idx_claims_author_framing ON claims(author_framing_idx);
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_doi);
CREATE INDEX IF NOT EXISTS idx_claims_subject ON claims(l1_subject);
CREATE INDEX IF NOT EXISTS idx_claims_object ON claims(l1_object);
CREATE INDEX IF NOT EXISTS idx_claims_template ON claims(template_type);

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

CREATE TABLE IF NOT EXISTS paper_references (
    citing_doi TEXT REFERENCES papers(doi) ON DELETE CASCADE,
    cited_doi TEXT,
    cited_title TEXT,
    PRIMARY KEY (citing_doi, cited_doi, cited_title)
);

CREATE TABLE IF NOT EXISTS measurement_methods (
    id TEXT,
    paper_doi TEXT REFERENCES papers(doi) ON DELETE CASCADE,
    measures TEXT,
    instrument_name TEXT,
    details TEXT, -- JSON
    PRIMARY KEY (paper_doi, id)
);

CREATE TABLE IF NOT EXISTS concepts (
    canonical_name TEXT PRIMARY KEY,
    level TEXT,
    description TEXT,
    aliases TEXT -- JSON array
);

CREATE TABLE IF NOT EXISTS theories (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);
"""


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) a SQLite DB at ``db_path`` and apply the schema.

    Returns a connection with ``foreign_keys`` and ``row_factory`` set up.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn
