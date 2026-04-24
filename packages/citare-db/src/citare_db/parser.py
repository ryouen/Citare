"""Deterministic parser for raw bibliographic reference text.

No AI. Pure regex + string ops. Given the verbatim text of one References
section entry, returns the structured fields (DOI, arXiv id, year, authors,
title, venue). Designed to be run at ingest time and after any upgrade so
that re-parsing yields improved coverage retroactively.

Coverage targets (from the 2,446 references in the existing 115 extractions):
 - DOI present in raw text: typically 30-60% of modern references
 - arXiv id: 5-15% of CS/ML references
 - year: ~100% (parenthesised 4-digit number; almost every reference has one)
 - first author surname: ~100% (first word / first comma-separated token)
 - title: ~90% (varies with reference format — APA vs numbered vs inline)
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PARSER_VERSION = "v0.1"


_DOI_RE = re.compile(
    r"(?:https?://(?:dx\.)?doi\.org/|doi:\s*|DOI:\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)
_ARXIV_DOI_RE = re.compile(r"10\.48550/arXiv\.\d{4}\.\d{4,5}(?:v\d+)?", re.IGNORECASE)
_ARXIV_ID_RE = re.compile(
    r"(?:arXiv[:\s]*)?(\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"(?<![\d.])(19|20)\d{2}(?![\d])")
_AUTHOR_YEAR_RE = re.compile(r"\(([^()]*?,\s*\d{4})\)")

# LLM-extraction shorthand form:  "Title (Author, 1999)"  or  "Title (A & B, 2001)"  or  "Title (A et al., 2020)"
_AUTHOR_IN_PARENS_RE = re.compile(
    r"\(([^()]+?),\s*(\d{4})\)\s*$"
)


@dataclass
class ParsedReference:
    """Structured view of a raw bibliographic string."""
    doi: str | None = None
    arxiv: str | None = None
    year: int | None = None
    authors: list[str] | None = None
    title: str | None = None
    venue: str | None = None
    parser_version: str = PARSER_VERSION


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    return m.group(1) if m.groups() else m.group(0)


def extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if m:
        doi = m.group(1).rstrip(".,;)")
        return doi
    return None


def extract_arxiv(text: str) -> str | None:
    # Prefer the DataCite DOI form if printed
    mdoi = _ARXIV_DOI_RE.search(text)
    if mdoi:
        return mdoi.group(0)
    # Else look for a bare arXiv id — but only when context mentions arxiv,
    # to avoid confusing "2020.1234" year-like strings with arxiv IDs.
    if "arxiv" in text.lower() or "arXiv" in text:
        m = _ARXIV_ID_RE.search(text)
        if m:
            return "arxiv:" + m.group(1)
    return None


def extract_year(text: str) -> int | None:
    # Prefer a year that sits next to an author in parentheses
    m = _AUTHOR_IN_PARENS_RE.search(text)
    if m:
        try:
            return int(m.group(2))
        except ValueError:
            pass
    # Else any 4-digit year in range
    m = _YEAR_RE.search(text)
    if m:
        try:
            y = int(m.group(0))
            if 1800 <= y <= 2100:
                return y
        except ValueError:
            pass
    return None


def _split_authors(author_text: str) -> list[str]:
    """Split 'Smith, J.', 'Smith, J., & Jones, K.', 'Smith et al.', 'A & B' etc
    into a list of surnames."""
    t = author_text.strip()
    # LLM-shorthand form: "Edmondson", "Hackman & Oldham", "Argote et al."
    # APA form: "Smith, J.", "Smith, J., & Jones, K."
    if "et al" in t.lower():
        first = re.split(r"\s*et al", t, maxsplit=1, flags=re.IGNORECASE)[0]
        return [first.rstrip(",. ").split(",")[0].strip()] if first else []
    # Try "A & B" or "A and B" pattern (LLM shorthand)
    parts = re.split(r"\s*[&]\s*|\s+and\s+|,\s*&\s*", t)
    # If each part is short (≤ 2 words), treat as surname list
    if all(len(p.strip().split()) <= 3 for p in parts):
        surnames = [p.strip().rstrip(".") for p in parts if p.strip()]
        # Drop trailing initials like "J." or "J. W."
        surnames = [s for s in surnames if s and not re.fullmatch(r"[A-Z]\.?(?:\s*[A-Z]\.?)*", s)]
        # If there's a mix, take the first (surname) in each group
        out = []
        for s in surnames:
            # APA "Smith, J." → "Smith"
            if "," in s:
                out.append(s.split(",", 1)[0].strip())
            else:
                out.append(s.strip())
        return [o for o in out if o]
    return []


def extract_authors(text: str) -> list[str] | None:
    # LLM shorthand form: "Title (Author1 & Author2, Year)"
    m = _AUTHOR_IN_PARENS_RE.search(text)
    if m:
        return _split_authors(m.group(1)) or None
    # APA head form: "Smith, J., & Jones, K. (2020). Title..."
    head = text.split("(", 1)[0] if "(" in text else text.split(".", 1)[0]
    authors = _split_authors(head)
    return authors or None


def extract_title(text: str) -> str | None:
    """Extract the title portion.

    Two formats handled:
      (a) LLM shorthand "<Title> (Author, Year)" — strip the trailing parens
      (b) APA "Author (Year). Title. Venue..." — take the second sentence
    """
    # shorthand
    m = _AUTHOR_IN_PARENS_RE.search(text)
    if m and m.start() > 5:
        title = text[: m.start()].strip().rstrip(".,")
        return title or None
    # APA / numbered: after "(YEAR)." take the next sentence
    apa = re.search(r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)\s*[.:]\s*([^.]+?)\s*[.\n]", text)
    if apa:
        title = apa.group(1).strip()
        # strip common prefixes
        return title or None
    return None


def extract_venue(text: str) -> str | None:
    """Best-effort venue extraction. Very noisy; used only as a hint."""
    # After the title in APA form: "... Title. Venue, volume(issue), pages."
    apa = re.search(
        r"\(\s*(?:19|20)\d{2}[a-z]?\s*\)\s*[.:]\s*[^.]+\.\s*([A-Z][^.,(]+)",
        text,
    )
    if apa:
        return apa.group(1).strip() or None
    return None


def parse(raw_reference_text: str) -> ParsedReference:
    """Parse one raw reference entry into structured fields.

    All fields may be None; an empty result is a valid (degenerate) parse.
    """
    if not raw_reference_text:
        return ParsedReference()
    t = raw_reference_text.strip()
    return ParsedReference(
        doi=extract_doi(t),
        arxiv=extract_arxiv(t),
        year=extract_year(t),
        authors=extract_authors(t),
        title=extract_title(t),
        venue=extract_venue(t),
    )
