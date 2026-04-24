"""Claim ID generation: {doi_hash8}-{template_letter}-{seq3}.

Design choice rationale in docs/adrs/0002-claim-id-format.md. Example:
  a3f7c92e-R-012  = relation claim #12 from paper with DOI hashing to a3f7c92e

Stable under DOI: the same paper always generates the same hash prefix,
so claim IDs are deterministic given paper DOI + template + ordering.
"""
from __future__ import annotations

import hashlib

from citare_core.enums import TemplateType


_TEMPLATE_LETTER = {
    TemplateType.DEFINITION: "D",
    TemplateType.RELATION: "R",
    TemplateType.EXISTENCE_CLAIM: "E",
    TemplateType.META_CLAIM: "M",
}


def doi_hash8(doi: str) -> str:
    """Compute the 8-hex-char prefix of SHA-256(doi)."""
    if not doi:
        raise ValueError("doi must be non-empty")
    return hashlib.sha256(doi.strip().lower().encode("utf-8")).hexdigest()[:8]


def claim_id_for(doi: str, template: TemplateType | str, seq: int) -> str:
    """Generate a claim id for a given paper + template + sequence number.

    Args:
        doi: Paper DOI (any case, will be normalized).
        template: TemplateType enum or its string name.
        seq: Per-paper, per-template sequence number (>= 1, < 1000).

    Returns:
        A string of the form ``{doi_hash8}-{letter}-{seq3}``.
    """
    if isinstance(template, str):
        template = TemplateType(template)
    if not (1 <= seq < 1000):
        raise ValueError(f"seq must be in [1, 999]; got {seq}")
    letter = _TEMPLATE_LETTER[template]
    return f"{doi_hash8(doi)}-{letter}-{seq:03d}"
