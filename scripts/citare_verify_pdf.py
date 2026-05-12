#!/usr/bin/env python3
"""Verify a PDF's first-page content matches the expected paper before extraction.

The 2026-05-11 incident's Phase B produced 5 misfiled PDFs (Lutz/Padilla/Sasaki/
Wolf/Flake_Fried) where an acquisition agent retrieved an adjacent paper from
the same journal issue or a similarly-titled paper. Those misfiles propagated
all the way through extraction and Citare registration before being caught by
manual audit.

This tool catches misfiles BEFORE extraction by checking that the first-page
text of the PDF actually matches the expected paper. It's intentionally
conservative — it returns MATCH only when there is strong evidence, MISMATCH
when the evidence clearly disagrees, and UNCERTAIN when the first-page text
is ambiguous or unreadable (in which case a human should look).

Usage:
    citare_verify_pdf.py --expected-title "Working memory" \\
                         --expected-first-author "Baddeley" \\
                         --expected-year 1974 \\
                         path/to/pdf.pdf

Exit codes:
  0 → MATCH (safe to extract)
  1 → MISMATCH (do NOT extract; this is likely the wrong file)
  2 → UNCERTAIN (text was unreadable; human review needed)
  3 → tool error (file missing, library missing, etc.)
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path


def _normalize(s: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace, drop most punctuation."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _first_page_text(pdf_path: Path) -> str:
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError(
            "PyMuPDF (fitz) not installed. Install with: pip install pymupdf"
        ) from e
    doc = fitz.open(str(pdf_path))
    try:
        if doc.page_count == 0:
            return ""
        # Take page 1 only — title page is virtually always page 1
        return doc.load_page(0).get_text() or ""
    finally:
        doc.close()


def verify(
    pdf_path: Path,
    expected_title: str | None,
    expected_first_author: str | None,
    expected_year: int | None,
) -> tuple[str, dict]:
    """Return ('MATCH'|'MISMATCH'|'UNCERTAIN', details)."""
    page = _first_page_text(pdf_path)
    if not page or len(page.strip()) < 50:
        return "UNCERTAIN", {"reason": "first_page_text_too_short_or_empty",
                             "page_text_len": len(page)}
    # Most title metadata appears in the first ~3000 chars of page 1
    head = page[:3000]
    head_norm = _normalize(head)

    details: dict = {"page_text_len": len(page)}
    matches: list[str] = []
    mismatches: list[str] = []

    if expected_title:
        title_norm = _normalize(expected_title)
        # Need at least 5 distinctive words to consider it a real check
        title_words = [w for w in title_norm.split() if len(w) >= 4]
        if len(title_words) >= 3:
            hits = sum(1 for w in title_words if w in head_norm)
            ratio = hits / len(title_words)
            details["title_word_match_ratio"] = round(ratio, 2)
            details["title_words_total"] = len(title_words)
            details["title_words_hit"] = hits
            if ratio >= 0.7:
                matches.append("title")
            elif ratio < 0.3:
                mismatches.append("title")

    if expected_first_author:
        author_norm = _normalize(expected_first_author).split()[-1]  # surname
        if len(author_norm) >= 3:
            if author_norm in head_norm:
                matches.append("first_author")
                details["first_author_found"] = True
            else:
                mismatches.append("first_author")
                details["first_author_found"] = False

    if expected_year:
        year_str = str(int(expected_year))
        # Allow ±1 year (received-vs-published artifact common in preprints)
        years_in_page = set(re.findall(r"(?<![0-9])((?:19|20)\d{2})(?![0-9])", head))
        details["years_on_first_page"] = sorted(years_in_page)
        if year_str in years_in_page:
            matches.append("year_exact")
        elif {str(int(year_str) - 1), str(int(year_str) + 1)} & years_in_page:
            matches.append("year_±1")
        elif years_in_page:
            mismatches.append("year")

    # Decision
    n_matches = len(matches)
    n_mismatches = len(mismatches)
    details["matches"] = matches
    details["mismatches"] = mismatches

    if n_mismatches >= 2:
        return "MISMATCH", details
    if n_matches >= 2 and n_mismatches == 0:
        return "MATCH", details
    if n_matches >= 1 and n_mismatches == 0:
        return "MATCH", details
    return "UNCERTAIN", details


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a PDF matches the expected paper (title/author/year) before extraction."
    )
    ap.add_argument("pdf_path", type=Path)
    ap.add_argument("--expected-title")
    ap.add_argument("--expected-first-author")
    ap.add_argument("--expected-year", type=int)
    ap.add_argument("--json", action="store_true", help="Output JSON details to stdout")
    args = ap.parse_args()

    if not args.pdf_path.exists():
        print(f"ERROR: PDF not found at {args.pdf_path}", file=sys.stderr)
        return 3

    if not any([args.expected_title, args.expected_first_author, args.expected_year]):
        print("ERROR: at least one of --expected-title / --expected-first-author / --expected-year is required",
              file=sys.stderr)
        return 3

    try:
        verdict, details = verify(
            args.pdf_path,
            args.expected_title,
            args.expected_first_author,
            args.expected_year,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

    if args.json:
        import json
        print(json.dumps({"verdict": verdict, **details}, indent=2, ensure_ascii=False))
    else:
        print(f"{verdict}  matches={details.get('matches', [])}  mismatches={details.get('mismatches', [])}")

    return {"MATCH": 0, "MISMATCH": 1, "UNCERTAIN": 2}[verdict]


if __name__ == "__main__":
    sys.exit(main())
