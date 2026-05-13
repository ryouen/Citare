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
    -- Task 71 — inclusion policy tier:
    --   1 = curated (hand-picked gold standard)
    --   2 = verified (passed batch LLM review)
    --   3 = ungated (default — extracted but not yet promoted)
    inclusion_policy_tier INTEGER NOT NULL DEFAULT 3
        CHECK(inclusion_policy_tier IN (1,2,3)),
    -- Silent-damage detection (Task 2026-05-14).
    --   peak_claim_count tracks the highest claim count this paper has
    --   ever held in this DB, monotonically. If a subsequent registration
    --   takes the claim count significantly below the peak (e.g., due to
    --   a cross-paper claim_id collision, a truncated extraction, or an
    --   accidental upsert with a smaller payload), the quality_flags layer
    --   surfaces SILENT_DAMAGE_SUSPECTED so the consumer doesn't trust the
    --   degraded entry blindly. Updated by ingest_extraction only when
    --   the post-ingest count exceeds the prior peak.
    peak_claim_count INTEGER NOT NULL DEFAULT 0,
    peak_claim_count_recorded_at TIMESTAMP,
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
    source TEXT                       -- LLM-native + curator-driven equivalences only
        CHECK(source IN ('extraction','batch_llm_review','crossref','openalex','human_expert') OR source IS NULL),
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

    -- Task 65 — l1_subject/predicate/object and l2_en/l2_ja have been
    -- dropped. They were never populated by v0.13+ extractions.
    l0_json TEXT,
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
    -- Task 64 — claim lifecycle. ``current`` is the default; other states
    -- carry negative-integrity signals propagated by cite_claim.
    claim_status TEXT NOT NULL DEFAULT 'current'
        CHECK(claim_status IN ('current','superseded','retracted','failed_to_replicate','contested')),
    superseded_by_claim_id TEXT REFERENCES claims(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    design_basis_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.design_basis')) VIRTUAL,
    -- Task 66 — JSON path now reads the renamed audit-only field. The
    -- old ``author_framing`` key is no longer written by ingest.
    author_framing_observed_only_idx TEXT GENERATED ALWAYS AS (json_extract(causal_strength, '$.author_framing_observed_only')) VIRTUAL,
    iv_idx TEXT GENERATED ALWAYS AS (json_extract(l0_json, '$.iv')) VIRTUAL,
    dv_idx TEXT GENERATED ALWAYS AS (json_extract(l0_json, '$.dv')) VIRTUAL
);
CREATE INDEX IF NOT EXISTS idx_claims_design_basis ON claims(design_basis_idx);
CREATE INDEX IF NOT EXISTS idx_claims_author_framing ON claims(author_framing_observed_only_idx);
CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claims_template ON claims(template_type);
CREATE INDEX IF NOT EXISTS idx_claims_iv ON claims(iv_idx);
CREATE INDEX IF NOT EXISTS idx_claims_dv ON claims(dv_idx);
-- Partial index on lifecycle — most claims are 'current'.
CREATE INDEX IF NOT EXISTS idx_claims_status
    ON claims(claim_status) WHERE claim_status != 'current';

-- FTS5 for free-text search. Three indexed columns:
--   source_text — verbatim quote from the paper
--   l0_concepts — flattened conceptual fields from l0_json (concept, iv,
--     dv, phenomenon, key_elements, ...) with snake_case normalised to
--     space-separated words so the unicode61 tokenizer can match natural-
--     language queries like "DNA structure" against "double_helix_dna_structure".
--   paper_meta  — paper-level metadata (authors + year + title) so the
--     common research-flow query "Author Year" finds every claim from
--     that paper. Without this column, "Edmondson 1999" returns 0 hits
--     because year tokens rarely appear in source_text.
-- A bare ``MATCH ?`` query searches all three columns (FTS5 default).
CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
    claim_id UNINDEXED,
    source_text,
    l0_concepts,
    paper_meta,
    tokenize = 'unicode61'
);

CREATE TABLE IF NOT EXISTS claim_relations (
    source_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
    target_id TEXT REFERENCES claims(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    -- Task 67 — open vocabulary. Canonical values + severity live in
    -- the ``incompleteness_vocabulary`` seeded table; new categories
    -- can be added without a code change.
    incompleteness_category TEXT NOT NULL DEFAULT 'none',
    context TEXT,
    confidence_score REAL,
    PRIMARY KEY (source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_relations_incompleteness
    ON claim_relations(incompleteness_category)
    WHERE incompleteness_category != 'none';

-- Task 67 — open vocabulary for incompleteness categories. Severity drives
-- citation-warning intensity. Seeded by init_db with canonical values.
CREATE TABLE IF NOT EXISTS incompleteness_vocabulary (
    category TEXT PRIMARY KEY,
    severity INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
    description TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task 70 — paper equivalence (preprint <-> published, translations,
-- duplicates). Canonical ordering enforced via the ``paper_a_id <
-- paper_b_id`` CHECK so the relation is stored once per pair.
CREATE TABLE IF NOT EXISTS paper_equivalence (
    paper_a_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    paper_b_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    equivalence_type TEXT NOT NULL
        CHECK(equivalence_type IN ('preprint_published','translation','reissue','duplicate','related_version')),
    confidence REAL,
    discovered_by TEXT,                   -- 'ingest-dedup' | 'llm-review' | 'human_expert'
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (paper_a_id, paper_b_id, equivalence_type),
    CHECK (paper_a_id < paper_b_id)
);
CREATE INDEX IF NOT EXISTS idx_equiv_a ON paper_equivalence(paper_a_id);
CREATE INDEX IF NOT EXISTS idx_equiv_b ON paper_equivalence(paper_b_id);

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


# Task 67 — canonical seed values for incompleteness_vocabulary. Severity
# 1 = clean / positive integrity, 5 = strongest negative-integrity signal.
# New categories may be added by INSERT OR IGNORE without code changes.
_INCOMPLETENESS_SEED: tuple[tuple[str, int, str], ...] = (
    ("none", 1, "Clean relation, no warning"),
    ("preregistered_confirmed", 1, "Positive integrity: preregistered + confirmed"),
    ("extends_prior_definition", 2, "Refines a concept from prior work"),
    ("boundary_condition", 3, "Holds only under specific scope"),
    ("hub_component", 3, "Part of a multi-step model — cite the chain"),
    ("underpowered", 3, "Sample size below recommended for effect"),
    ("disputed", 4, "Field actively disputes this claim"),
    ("effect_disappears_under_control", 5, "Effect vanishes under control variables"),
    ("failed_to_replicate", 5, "Original effect did not replicate"),
    ("retracted", 5, "Citing paper is retracted"),
)


def init_db(db_path: str | Path) -> sqlite3.Connection:
    """Open (or create) a SQLite DB at ``db_path`` and apply the schema.

    Returns a connection with ``foreign_keys`` ON and ``Row`` factory set.
    Also seeds the ``incompleteness_vocabulary`` table with canonical
    categories (idempotent via INSERT OR IGNORE).
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.executemany(
        "INSERT OR IGNORE INTO incompleteness_vocabulary "
        "(category, severity, description) VALUES (?, ?, ?)",
        _INCOMPLETENESS_SEED,
    )
    conn.commit()
    return conn
