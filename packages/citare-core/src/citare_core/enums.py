"""Controlled vocabularies used across Citare schemas.

These map to CHECK constraints in the SQLite schema (docs/design_spec §2).
"""
from enum import Enum


class TemplateType(str, Enum):
    DEFINITION = "DEFINITION"
    RELATION = "RELATION"
    EXISTENCE_CLAIM = "EXISTENCE_CLAIM"
    META_CLAIM = "META_CLAIM"


class VerificationStatus(str, Enum):
    verified_in_paper = "verified_in_paper"
    proposed_in_paper = "proposed_in_paper"
    not_supported = "not_supported"
    mixed_support = "mixed_support"
    partial_support = "partial_support"


class EvidenceType(str, Enum):
    empirical = "empirical"
    theoretical = "theoretical"
    definitional = "definitional"
    existence_proof = "existence_proof"
    conceptual = "conceptual"
    review = "review"
    meta_analysis = "meta_analysis"


class DesignBasis(str, Enum):
    cross_sectional = "cross_sectional"
    longitudinal = "longitudinal"
    quasi_experimental = "quasi_experimental"
    rct = "rct"
    meta_analysis = "meta_analysis"
    computational_demonstration = "computational_demonstration"
    theoretical = "theoretical"


class AuthorFraming(str, Enum):
    """Stored for retrospective audit ONLY.

    MUST NOT be used to derive safe_verbs or any citation-safety output.
    Authors of cross-sectional studies routinely use causal language;
    using this field for citation derivation re-imports the bias Citare
    exists to filter. The model field has been renamed to
    ``author_framing_observed_only`` to make this audit-only intent
    explicit at the call site.
    """
    causal = "causal"
    associational = "associational"
    suggestive = "suggestive"
    existence_proof = "existence_proof"


class TemporalPrecedence(str, Enum):
    none = "none"
    partial = "partial"
    full = "full"


class RelationType(str, Enum):
    part_of_model = "part_of_model"
    supports = "supports"
    extends = "extends"
    contradicts = "contradicts"
    qualifies = "qualifies"
    replicates = "replicates"
    aggregates = "aggregates"
    background = "background"
    apparent_tension = "apparent_tension"


class IncompletenessCategory(str, Enum):
    """Open-vocabulary incompleteness categories.

    Used on claim_relations to warn citers about claims that cannot safely
    stand alone. See design_spec §2.3. The SQL CHECK constraint has been
    removed; canonical values + severity now live in the
    ``incompleteness_vocabulary`` seeded table so future categories don't
    need a code change.
    """
    effect_disappears_under_control = "effect_disappears_under_control"
    hub_component = "hub_component"
    boundary_condition = "boundary_condition"
    extends_prior_definition = "extends_prior_definition"
    none = "none"
    failed_to_replicate = "failed_to_replicate"
    retracted = "retracted"
    disputed = "disputed"
    underpowered = "underpowered"
    preregistered_confirmed = "preregistered_confirmed"


class ClaimStatus(str, Enum):
    """Claim lifecycle status (Task 64).

    Most claims are ``current``. ``superseded`` points to the replacing
    claim via ``superseded_by_claim_id``. ``retracted``,
    ``failed_to_replicate``, and ``contested`` are negative-integrity
    signals that should propagate as warnings on cite_claim.
    """
    current = "current"
    superseded = "superseded"
    retracted = "retracted"
    failed_to_replicate = "failed_to_replicate"
    contested = "contested"


class PaperType(str, Enum):
    empirical = "empirical"
    conceptual = "conceptual"
    review = "review"
    meta_analysis = "meta_analysis"
    book = "book"
    book_chapter = "book_chapter"


class EquationStatus(str, Enum):
    """Classification of equations by citation-relevance.

    Introduced after the T7 tournament showed that undiscriminated
    equation extraction causes restatements and textbook-background
    forms to pollute the knowledge graph, creating future miscitation
    risk. Only central_contribution and supporting_definition should
    be extracted as standalone equations.
    """
    central_contribution = "central_contribution"
    supporting_definition = "supporting_definition"
    restatement = "restatement"
    textbook_background = "textbook_background"
