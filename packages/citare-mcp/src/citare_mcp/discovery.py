"""Helpers that fire when search_claims returns 0 hits.

Two jobs:
  1. If the query / doi argument LOOKS like a real identifier, ask CrossRef
     whether the paper exists (and grab its title/authors/year). This lets
     the LLM tell the user "Citare doesn't have this paper but it does
     exist; here's the metadata we need to register it."
  2. Always emit a short acquisition_guidance object pointing at the right
     next-step tool (`get_pdf_acquisition_guide`, `get_extraction_prompt`,
     `register_claims`).

Network call to CrossRef is best-effort with a tight timeout — we never
want a 0-result search to hang the MCP session.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any


_DOI_PAT = re.compile(r"^10\.\d{4,9}/\S+$")
_ARXIV_PAT = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5})(?:v\d+)?$", re.IGNORECASE)
_CROSSREF_TIMEOUT_S = 6


def _looks_like_doi(s: str) -> bool:
    return bool(s and _DOI_PAT.match(s.strip()))


def _looks_like_arxiv(s: str) -> bool:
    return bool(s and _ARXIV_PAT.match(s.strip()))


def _crossref_lookup_by_doi(doi: str) -> dict[str, Any] | None:
    """Fetch the canonical CrossRef record for a DOI. None on any failure."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='/.()')}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CitareMCP/0.1 (+https://citare.dev; mailto:api@citare.dev)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_CROSSREF_TIMEOUT_S) as r:
            payload = json.loads(r.read())
    except Exception:
        return None
    msg = payload.get("message") or {}
    title_list = msg.get("title") or []
    container_list = msg.get("container-title") or []
    authors = []
    for a in (msg.get("author") or [])[:20]:
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if given or family:
            authors.append((given + " " + family).strip())
    issued = (msg.get("issued") or {}).get("date-parts") or [[]]
    year = (issued[0] or [None])[0] if issued and issued[0] else None
    return {
        "source": "crossref",
        "doi": msg.get("DOI") or doi,
        "title": title_list[0] if title_list else None,
        "authors": authors,
        "year": year,
        "venue": container_list[0] if container_list else None,
        "type": msg.get("type"),
        "url": msg.get("URL") or f"https://doi.org/{doi}",
    }


def _crossref_lookup_arxiv(arxiv_id: str) -> dict[str, Any] | None:
    """Try the auto-DOI form first (10.48550/arXiv.<id>); fall back to None."""
    return _crossref_lookup_by_doi(f"10.48550/arXiv.{arxiv_id}")


def enrich_zero_result(
    *,
    query: str | None = None,
    doi: str | None = None,
    iv: str | None = None,
    dv: str | None = None,
) -> dict[str, Any]:
    """Build the rich-response payload that wraps an empty search result.

    Always returns a dict with `paper_status`, `acquisition_guidance`, and
    `registration_instructions`. Includes `crossref_metadata` only when a
    DOI / arXiv ID was probed AND CrossRef returned a hit.
    """
    out: dict[str, Any] = {
        "paper_status": "not_in_citare",
        "registration_available": True,
        "registration_instructions": (
            "1) Acquire the PDF (see get_pdf_acquisition_guide). "
            "2) Get the locked production prompt (get_extraction_prompt). "
            "3) Run extraction in a sub-agent — do NOT extract in this context. "
            "4) Submit the JSON to register_claims. No auth required."
        ),
        "extraction_prompt_version": "v0.13d",
        "acquisition_guidance": {
            "next_tool": "get_pdf_acquisition_guide",
            "summary": "Walk Stages 0-7. Most papers resolve via Unpaywall + direct OA without asking the user.",
        },
    }

    # Probe CrossRef when we have a real-looking identifier
    probe = None
    if doi and _looks_like_doi(doi):
        probe = _crossref_lookup_by_doi(doi)
    elif query:
        q = query.strip()
        if _looks_like_doi(q):
            probe = _crossref_lookup_by_doi(q)
        else:
            m = _ARXIV_PAT.match(q)
            if m:
                probe = _crossref_lookup_arxiv(m.group(1))

    if probe:
        out["crossref_metadata"] = probe
        out["acquisition_guidance"]["pdf_url_hint"] = (
            f"https://arxiv.org/pdf/{_ARXIV_PAT.match((query or '').strip()).group(1)}.pdf"
            if (query and _ARXIV_PAT.match(query.strip()))
            else probe.get("url")
        )
    elif (query and _looks_like_doi(query.strip())) or (doi and _looks_like_doi(doi)):
        out["crossref_metadata"] = {
            "source": "crossref",
            "result": "not_found",
            "detail": (
                "CrossRef returned no record for this DOI. The DOI may be wrong, "
                "or the publisher hasn't deposited it yet. Verify with the user."
            ),
        }

    # If the caller searched by iv/dv (concept terms), point them at search_hint
    if (iv or dv) and not query:
        out["search_hint"] = (
            "iv/dv are snake_case database keys (e.g. team_psychological_safety). "
            "If you're searching by natural language, use `query` instead."
        )

    return out
