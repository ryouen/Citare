"""Pydantic v2 models for Citare entities.

Matches the SQLite schema in docs/design_spec.md §2. JSON columns are
modelled as nested pydantic models and serialised to JSON on persistence.

Principle 4 (design_spec §1.2): one name per concept. Field names here
match both the LLM prompt output fields and the SQL column names, so
there is no mapping layer between extraction and storage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from citare_core.enums import (
    AuthorFraming,
    DesignBasis,
    EquationStatus,
    EvidenceType,
    IncompletenessCategory,
    PaperType,
    RelationType,
    TemplateType,
    TemporalPrecedence,
    VerificationStatus,
)


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ----- Paper -----------------------------------------------------------------

class Paper(_StrictBase):
    """A peer-reviewed paper (Level A), keyed by DOI when available.

    doi is nullable in the pydantic layer because some real extractions
    arrive without a resolvable DOI (pre-prints, 1950s papers, synthetic
    trap papers). The DB layer requires a non-null key and substitutes
    a content-hash surrogate when a real DOI is missing.
    """
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    paper_type: PaperType | None = None
    domain: str | None = None

    default_causal_strength: "CausalStrength | None" = None
    default_method: "MethodMetadata | None" = None


# ----- JSON sub-structures ---------------------------------------------------

class CausalStrength(_StrictBase):
    """Citare's differentiator: four-field metadata on a relation's strength.

    Per design_spec §2.2.5, this is stored as JSON so prompt output lands
    directly in the DB without translation. Fields use str rather than
    the corresponding enum because LLM output uses an open vocabulary
    that extends the enum's canonical values (e.g. 'qualitative_field').
    Canonicalisation happens at a later stage, not at validation time.
    """
    design_basis: str | None = None
    author_framing: str | None = None
    temporal_precedence: str | None = None
    manipulation_of_iv: bool | None = None


class MethodMetadata(_StrictBase):
    """Study-level method fields, per design_spec §2.2.9."""
    sample_size: int | None = None
    unit_of_analysis: str | None = None
    industry: str | None = None
    country: str | None = None
    study_design: str | None = None


# ----- Equation (formal field) ----------------------------------------------

class Equation(_StrictBase):
    """A single equation extracted from a paper, with status classification.

    equation_status was introduced after the T7 tournament (experiments/T7_TOURNAMENT.md).
    Extracting restatements or textbook_background equations as standalone
    entries risks future miscitation; only central_contribution and
    supporting_definition should be kept.
    """
    latex: str
    variables: dict[str, str] = Field(default_factory=dict)
    conditions: str | None = None
    proof_type: str | None = None
    name: str | None = None
    equation_status: EquationStatus | None = None


# ----- L0 payloads per template type ----------------------------------------

class L0Relation(_StrictBase):
    iv: str
    dv: str
    relation: str
    mediator: str | None = None
    moderator: str | None = None
    new_concept_proposed: bool | None = None


class L0Definition(_StrictBase):
    concept: str
    key_elements: list[str] = Field(default_factory=list)
    new_concept_proposed: bool | None = None


class L0Existence(_StrictBase):
    phenomenon: str
    evidence: str | None = None


class L0Meta(_StrictBase):
    integrated_finding: str | None = None
    scope: str | None = None


# ----- L3 structured statistics ---------------------------------------------

class L3Json(_StrictBase):
    effect_size: float | str | None = None
    effect_size_type: str | None = None
    p: str | float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    n: int | None = None
    r_squared: float | None = None
    r_squared_type: str | None = None
    mediation: dict[str, Any] | None = None
    interaction: dict[str, Any] | None = None
    models: list[dict[str, Any]] | None = None
    reliability: dict[str, Any] | None = None
    formal: dict[str, Any] | None = None  # {equations: [Equation, ...]}
    additional: dict[str, Any] | None = None
    incompleteness_category: IncompletenessCategory | None = None


# ----- Claim (the heart of Citare) ------------------------------------------

class Claim(_StrictBase):
    """A single claim extracted from a paper.

    paper_doi is optional on incoming extractions (the Extraction envelope
    carries it at the top) and is populated by the ingestion step before
    DB insertion. evidence_type is intentionally kept as a free-form str
    because LLM output uses a richer open vocabulary than the fixed enum.
    """
    id: str
    paper_doi: str | None = None
    template_type: TemplateType
    l0_json: dict[str, Any] | None = None

    l1_subject: str | None = None
    l1_predicate: str | None = None
    l1_object: str | None = None

    l2_en: str | None = None
    l2_ja: str | None = None
    l3_json: L3Json | None = None

    source_text: str | None = None
    source_page: int | None = None
    source_section: str | None = None
    source_paragraph: str | None = None

    evidence_type: str | None = None
    verification_status: VerificationStatus | None = None

    causal_strength: CausalStrength | None = None
    method_metadata: MethodMetadata | None = None

    model_hub: bool = False
    confidence_level: str | None = None
    confidence_score: float | None = None

    extraction_prompt_version: str | None = None
    status: Literal["active", "deprecated"] = "active"

    created_at: datetime | None = None
    updated_at: datetime | None = None


# ----- Relation / reference / concept / measurement -------------------------

class ClaimRelation(_StrictBase):
    """Edge between two claims, with optional integrity warning."""
    source_id: str
    target_id: str
    relation_type: RelationType
    incompleteness_category: IncompletenessCategory = IncompletenessCategory.none
    context: str | None = None
    confidence_score: float | None = None


class PaperReference(_StrictBase):
    """A bibliographic reference from a paper's References section.

    Written by extraction prompts in one of two modes:
     * **v0.12 and earlier (legacy)**: ``cited_doi`` + ``cited_title``, with
       LLM having compressed/reformatted the original entry.
     * **v0.13+ (verbatim)**: ``raw_reference_text`` holds the entry exactly
       as printed in the References section. Parser fills the rest after.

    All fields are optional to tolerate both modes. The DB layer splits this
    model into ``citation_text`` (raw) + parsed fields; see citare-db.
    """
    citing_doi: str | None = None
    cited_doi: str | None = None
    cited_arxiv: str | None = None
    cited_year: int | None = None
    cited_authors: list[str] = Field(default_factory=list)
    cited_title: str | None = None
    cited_venue: str | None = None
    raw_reference_text: str | None = None
    position_in_refs: int | None = None


class Concept(_StrictBase):
    """Canonical name of an iv/dv / construct, with optional level prefix."""
    canonical_name: str
    level: str | None = None  # individual / team / organization / computational / ...
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)


class MeasurementMethod(_StrictBase):
    """A measurement scale or instrument used in a paper."""
    id: str | None = None
    paper_doi: str | None = None
    measures: str | None = None
    instrument_name: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class Theory(_StrictBase):
    id: str | None = None
    name: str
    description: str | None = None


# ----- Full extraction envelope ---------------------------------------------

class Extraction(_StrictBase):
    """One LLM extraction of a single paper.

    Matches the JSON structure produced by `run_extraction_cli.py` — so
    ingestion is `Extraction.model_validate_json(text)` then walk claims/
    relations/measurement_methods/paper_references into the DB.
    """
    paper: Paper
    claims: list[Claim] = Field(default_factory=list)
    claim_relations: list[ClaimRelation] = Field(default_factory=list)
    measurement_methods: list[MeasurementMethod] = Field(default_factory=list)
    theories: list[Theory] = Field(default_factory=list)
    paper_references: list[PaperReference] = Field(default_factory=list)

    # Extraction metadata
    extraction_prompt_version: str | None = None
    model: str | None = None
    effort: str | None = None

    @field_validator("claims")
    @classmethod
    def _ids_unique(cls, v: list[Claim]) -> list[Claim]:
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            dupes = [x for x in ids if ids.count(x) > 1]
            raise ValueError(f"duplicate claim ids: {set(dupes)}")
        return v
