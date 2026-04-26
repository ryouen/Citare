"""PDF input handling for the server-side extraction tool.

Two paths:
  - `fetch_pdf_url(url)` — HTTPS GET with size + content-type validation.
  - `decode_base64_pdf(s)` — accept caller-uploaded PDF as base64 (the MCP
    JSON-RPC envelope can't carry binary directly).

Both return raw bytes ready for `extractor.extract_pdf`. Both validate the
PDF magic bytes and the size cap before returning.
"""
from __future__ import annotations

import base64
import urllib.request
from urllib.parse import urlparse

from citare_mcp.extractor import MAX_PDF_BYTES


_PDF_MAGIC = b"%PDF"
_FETCH_TIMEOUT_S = 60


class PdfFetchError(ValueError):
    """Raised when a PDF cannot be obtained or fails validation."""


def _validate_bytes(data: bytes, source: str) -> None:
    if len(data) < 1024:
        raise PdfFetchError(
            f"PDF from {source} is suspiciously small ({len(data)} bytes) — "
            "likely an error page or login redirect, not a real PDF."
        )
    if len(data) > MAX_PDF_BYTES:
        raise PdfFetchError(
            f"PDF from {source} exceeds size limit ({len(data):,} > {MAX_PDF_BYTES:,} bytes). "
            "Strip image layer first via citare-strip-images."
        )
    if not data.startswith(_PDF_MAGIC):
        # Could be an HTML page disguised as a .pdf URL — surface that.
        first = data[:200].lower()
        if b"<html" in first or b"<!doctype" in first:
            raise PdfFetchError(
                f"{source} returned HTML, not a PDF. Common cause: paywall, "
                "login redirect, or PMC Proof-of-Work challenge. See "
                "get_pdf_acquisition_guide() for site-specific workarounds."
            )
        raise PdfFetchError(
            f"{source} did not return a PDF (no %PDF magic bytes; first bytes: "
            f"{data[:8]!r})."
        )


def fetch_pdf_url(url: str) -> bytes:
    """Download a PDF over HTTPS. Validates magic bytes + size."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PdfFetchError(f"Only http(s) URLs are supported, got scheme {parsed.scheme!r}")
    if not parsed.netloc:
        raise PdfFetchError(f"URL is missing a host: {url!r}")

    req = urllib.request.Request(
        url,
        headers={
            # Generic UA so publishers don't 403 us as a python-urllib bot.
            # Some OA hosts (notably OpenReview) also need a Referer; the
            # acquisition guide tells the LLM to set that on the source side
            # before passing the URL here.
            "User-Agent": "Mozilla/5.0 (compatible; CitareMCP/0.1; +https://citare.dev)",
            "Accept": "application/pdf, */*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_FETCH_TIMEOUT_S) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read(MAX_PDF_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise PdfFetchError(f"HTTP {e.code} from {url}: {e.reason}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise PdfFetchError(f"Network error fetching {url}: {e}") from e

    if "html" in ctype:
        raise PdfFetchError(
            f"{url} responded with Content-Type: {ctype} — that's HTML, not a PDF. "
            "Get the actual PDF URL via get_pdf_acquisition_guide()."
        )

    _validate_bytes(data, source=url)
    return data


def decode_base64_pdf(b64_str: str) -> bytes:
    """Decode a base64-encoded PDF that came in via the MCP JSON-RPC envelope."""
    # Tolerate data-URL prefix and whitespace (LLMs sometimes add them).
    s = b64_str.strip()
    if s.startswith("data:"):
        comma = s.find(",")
        if comma == -1:
            raise PdfFetchError("Malformed data: URL — missing comma after MIME header.")
        s = s[comma + 1 :]
    s = "".join(s.split())  # drop any embedded whitespace / newlines
    try:
        data = base64.b64decode(s, validate=True)
    except Exception as e:
        raise PdfFetchError(f"Invalid base64 input: {e}") from e
    _validate_bytes(data, source="<base64 input>")
    return data


def resolve_pdf_input(
    *, pdf_url: str | None = None, pdf_base64: str | None = None
) -> tuple[bytes, str]:
    """Pick a source and fetch. Exactly one of (url, base64) must be set.

    Returns (pdf_bytes, source_label). source_label is suitable for echoing
    back to the caller in the response ('pdf_url=https://...' or '<base64>').
    """
    if bool(pdf_url) == bool(pdf_base64):
        raise PdfFetchError(
            "Provide exactly one of pdf_url or pdf_base64."
        )
    if pdf_url:
        return fetch_pdf_url(pdf_url), pdf_url
    return decode_base64_pdf(pdf_base64), "<base64 upload>"
