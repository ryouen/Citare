"""Citation-style formatters for cite_claim's `paper_reference` field.

Each formatter takes the paper dict shape that cite_claim returns
(canonical_title, authors, year, venue, identifiers list) and produces a
single string in the requested style. Errors are tolerated — missing year
becomes "n.d.", missing venue is dropped — but the formatters never throw.

Three styles are supported in v1: APA7, Chicago author-date, and BibTeX.
The MCP `style` parameter accepts these three plus aliases ("apa", "harvard"
→ apa7) for client convenience.
"""
from __future__ import annotations

import re
from typing import Any


SUPPORTED_STYLES = ("apa7", "chicago", "bibtex")
_STYLE_ALIASES = {"apa": "apa7", "apa7": "apa7", "harvard": "apa7", "chicago": "chicago", "bibtex": "bibtex"}


def normalise_style(style: str | None) -> str:
    """Map any input ('APA', 'apa7', 'Harvard') to a canonical key. Defaults to apa7."""
    if not style:
        return "apa7"
    return _STYLE_ALIASES.get(style.strip().lower(), "apa7")


def _doi_from_identifiers(identifiers: list[dict[str, Any]] | None) -> str | None:
    """Pull a DOI out of the paper_identifiers list, preferring the canonical one."""
    if not identifiers:
        return None
    # Prefer real DOIs over arxiv DOIs (10.48550/arXiv.X) — both useful
    # but a journal DOI is what citation styles expect first.
    real = [i for i in identifiers if i.get("identifier_type") == "doi"]
    if real:
        return real[0]["identifier_value"]
    arxiv = [i for i in identifiers if i.get("identifier_type") == "arxiv_doi"]
    if arxiv:
        return arxiv[0]["identifier_value"]
    return None


def _arxiv_id_from_identifiers(identifiers: list[dict[str, Any]] | None) -> str | None:
    if not identifiers:
        return None
    a = [i for i in identifiers if i.get("identifier_type") == "arxiv"]
    if a:
        # Stored as "arxiv:2106.09685"; strip prefix for display
        v = a[0]["identifier_value"]
        return v[6:] if v.startswith("arxiv:") else v
    return None


def _format_authors_apa(authors: list[str]) -> str:
    """APA7: 'Last, F. M., Last, F. M., & Last, F. M.'

    The DB stores 'Firstname Lastname' or 'Lastname, F.' inconsistently across
    extractions. We try to detect both forms; when uncertain, return the raw
    string. APA7 with > 20 authors uses an ellipsis; we apply that here.
    """
    if not authors:
        return "Anonymous"
    formatted = [_to_last_first_initials(a) for a in authors]
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]}, & {formatted[1]}"
    if len(formatted) <= 20:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    # APA7 > 20: list first 19, ellipsis, then last author
    return ", ".join(formatted[:19]) + ", … " + formatted[-1]


def _to_last_first_initials(name: str) -> str:
    """Best-effort conversion of 'Firstname M. Lastname' to 'Lastname, F. M.'.

    Already-inverted ('Lastname, F.') strings are passed through. This is
    deliberately conservative — APA correctness on non-Western names is hard
    and we'd rather emit the raw form than mis-invert.
    """
    name = name.strip()
    if not name:
        return ""
    # Already in 'Last, First' form?
    if "," in name:
        return name
    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    last = parts[-1]
    initials = " ".join(p[0].upper() + "." for p in parts[:-1] if p)
    return f"{last}, {initials}"


def _format_authors_chicago(authors: list[str]) -> str:
    """Chicago author-date: 'First Last, First Last, and First Last'.

    First author can be inverted; we keep it natural for simplicity.
    """
    if not authors:
        return "Anonymous"
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return f"{authors[0]} and {authors[1]}"
    if len(authors) <= 10:
        return ", ".join(authors[:-1]) + f", and {authors[-1]}"
    return ", ".join(authors[:7]) + f", et al."


def _format_authors_bibtex(authors: list[str]) -> str:
    """BibTeX uses ' and ' between authors. Order preserved."""
    return " and ".join(a.strip() for a in (authors or []) if a.strip())


def format_apa7(paper: dict[str, Any]) -> str:
    """APA 7th edition reference string."""
    authors = _format_authors_apa(paper.get("authors") or [])
    year = paper.get("year") or "n.d."
    title = (paper.get("canonical_title") or "Untitled").rstrip(".")
    venue = paper.get("venue") or ""
    doi = _doi_from_identifiers(paper.get("identifiers"))
    arxiv = _arxiv_id_from_identifiers(paper.get("identifiers"))

    parts = [f"{authors} ({year}). {title}."]
    if venue:
        parts.append(f"*{venue}*.")
    if doi:
        # Real DOI URL form
        parts.append(f"https://doi.org/{doi}")
    elif arxiv:
        parts.append(f"arXiv:{arxiv}")
    return " ".join(parts)


def format_chicago(paper: dict[str, Any]) -> str:
    """Chicago author-date reference."""
    authors = _format_authors_chicago(paper.get("authors") or [])
    year = paper.get("year") or "n.d."
    title = (paper.get("canonical_title") or "Untitled").rstrip(".")
    venue = paper.get("venue") or ""
    doi = _doi_from_identifiers(paper.get("identifiers"))
    arxiv = _arxiv_id_from_identifiers(paper.get("identifiers"))

    s = f'{authors}. {year}. "{title}."'
    if venue:
        s += f" *{venue}*."
    if doi:
        s += f" https://doi.org/{doi}."
    elif arxiv:
        s += f" arXiv:{arxiv}."
    return s


def _bibtex_key(paper: dict[str, Any]) -> str:
    """Generate a BibTeX cite key: lastnameYEARtitleword."""
    authors = paper.get("authors") or []
    first = authors[0] if authors else "anon"
    last = first.split(",")[0].strip().split()[-1] if first else "anon"
    last = re.sub(r"[^A-Za-z0-9]", "", last).lower() or "anon"
    year = str(paper.get("year") or "nd")
    title = (paper.get("canonical_title") or "untitled").lower()
    word = re.sub(r"[^a-z]", "", (title.split() or ["x"])[0])[:8] or "x"
    return f"{last}{year}{word}"


def format_bibtex(paper: dict[str, Any]) -> str:
    """BibTeX entry. Type is @article when venue is set, @misc otherwise."""
    authors = _format_authors_bibtex(paper.get("authors") or [])
    year = paper.get("year") or "n.d."
    title = (paper.get("canonical_title") or "Untitled").rstrip(".")
    venue = paper.get("venue") or ""
    doi = _doi_from_identifiers(paper.get("identifiers"))
    arxiv = _arxiv_id_from_identifiers(paper.get("identifiers"))
    key = _bibtex_key(paper)
    entry_type = "article" if venue else "misc"

    fields = [
        f"  author    = {{{authors}}}",
        f"  title     = {{{title}}}",
        f"  year      = {{{year}}}",
    ]
    if venue:
        fields.append(f"  journal   = {{{venue}}}")
    if doi:
        fields.append(f"  doi       = {{{doi}}}")
    if arxiv:
        fields.append(f"  archivePrefix = {{arXiv}}")
        fields.append(f"  eprint    = {{{arxiv}}}")
    body = ",\n".join(fields)
    return f"@{entry_type}{{{key},\n{body}\n}}"


def format_paper_reference(paper: dict[str, Any], style: str) -> str:
    """Dispatcher. `style` is normalised; unknown styles fall back to APA7."""
    s = normalise_style(style)
    if s == "chicago":
        return format_chicago(paper)
    if s == "bibtex":
        return format_bibtex(paper)
    return format_apa7(paper)
