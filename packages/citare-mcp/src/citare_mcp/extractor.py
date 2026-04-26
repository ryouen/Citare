"""Server-side PDF → claim extraction via Anthropic API.

This is the cost-bearing path: the MCP server itself calls Claude with the
v0.13g production prompt and a user-supplied PDF, parses the resulting JSON
into an Extraction object, and returns it along with the actual cost (computed
from response.usage at Opus 4.7 pricing).

Why prompt caching: the v0.13g prompt is ~5500 tokens and identical across
every extraction. Caching it makes the second-and-onwards extraction roughly
50% cheaper. The PDF and the user prompt go after the cache breakpoint so
they vary per request without invalidating the cached prefix.

Why streaming: max_tokens is 64K (extraction JSON can be large for empirical
papers), and non-streaming requests at that size hit SDK HTTP timeouts.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass
from typing import Any

import anthropic

from citare_core import Extraction
from citare_mcp.guides import EXTRACTION_PROMPT_VERSION, _load_asset, EXTRACTION_PROMPT_ASSET


# Opus 4.7 pricing (USD per 1M tokens), verified against shared/models.md
# in the claude-api skill on 2026-04-26.
OPUS_4_7_INPUT_PER_M = 5.00
OPUS_4_7_OUTPUT_PER_M = 25.00
# Cache writes: 1.25x base for 5-minute TTL. Cache reads: ~0.1x base.
CACHE_WRITE_MULTIPLIER = 1.25
CACHE_READ_MULTIPLIER = 0.10

# Conservative ceiling on a single PDF — anything larger should be stripped
# of its image layer first via citare-strip-images.
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB

# Output budget. R82 grid validated 32K as sufficient for v0.13g × none
# (avg output ~25K tokens for the heaviest 6-paper panel). Bumping higher
# is harmless but unnecessary; lower truncates dense papers mid-JSON.
DEFAULT_MAX_TOKENS = 32768

DEFAULT_MODEL = "claude-opus-4-7"


@dataclass
class ExtractionResult:
    """Result of a server-side extraction call.

    `extraction` is the parsed Pydantic envelope; ingest_extraction can
    consume it directly. `cost_usd` and the per-token-bucket breakdown
    let the caller charge the user's per-key budget accurately.
    """
    extraction: Extraction
    raw_json: dict[str, Any]
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    model: str
    stop_reason: str | None


def _compute_cost_usd(usage: anthropic.types.Usage, model: str) -> float:
    """Total $USD for one request, given Anthropic's reported usage.

    Currently only Opus 4.7 is priced here — that is the locked production
    model for v0.13g. Adding another model means adding its $/M rates and
    routing on `model`.
    """
    if model != "claude-opus-4-7":
        raise ValueError(
            f"Unpriced model: {model}. Only claude-opus-4-7 has pricing wired up."
        )
    in_per_token = OPUS_4_7_INPUT_PER_M / 1_000_000
    out_per_token = OPUS_4_7_OUTPUT_PER_M / 1_000_000
    cache_write_per_token = in_per_token * CACHE_WRITE_MULTIPLIER
    cache_read_per_token = in_per_token * CACHE_READ_MULTIPLIER
    return (
        (usage.input_tokens or 0) * in_per_token
        + (usage.cache_creation_input_tokens or 0) * cache_write_per_token
        + (usage.cache_read_input_tokens or 0) * cache_read_per_token
        + (usage.output_tokens or 0) * out_per_token
    )


_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_to_json(text: str) -> str:
    """Best-effort extraction of a JSON object from a free-form response.

    v0.13g explicitly tells the model to emit only JSON, but caching the
    prompt does not guarantee the model never wraps it in a code fence
    or prefixes a confirmation sentence. Strip both defensively.
    """
    s = text.strip()
    m = _FENCE.search(s)
    if m:
        return m.group(1).strip()
    # Fall back: take from the first '{' to the matching last '}'.
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        return s[first : last + 1]
    return s


def _build_system_prompt() -> str:
    """The v0.13g production prompt, loaded from the package asset."""
    return _load_asset(EXTRACTION_PROMPT_ASSET)


def extract_pdf(
    pdf_bytes: bytes,
    *,
    pdf_filename: str | None = None,
    user_hint: str | None = None,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> ExtractionResult:
    """Extract claims from one PDF using the locked production prompt.

    Returns an ExtractionResult with the parsed Extraction object and the
    actual API cost. Raises:
      ValueError — PDF too large, or response could not be parsed as JSON.
      anthropic.* — propagated SDK errors (rate limit, auth, etc.).
      pydantic.ValidationError — the JSON parsed but didn't match the schema.

    The caller is responsible for charging cost_usd against the user's
    budget. Charge it even on Pydantic validation failure: the API call
    happened, the tokens were billed, and the budget should reflect that.
    """
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(
            f"PDF too large: {len(pdf_bytes):,} bytes (limit {MAX_PDF_BYTES:,})."
        )
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("Input does not look like a PDF (missing %PDF magic bytes).")

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    system_prompt = _build_system_prompt()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("ascii")

    # The user message: PDF + size guidance + a one-line nudge. The PDF
    # varies per request so it sits AFTER the cached prompt; nothing here
    # invalidates the cache.
    user_text = (
        "Extract claims from the attached PDF following the system prompt above.\n"
        "Output ONLY a single JSON object — no markdown fences, no preamble.\n\n"
        "Expected output size (rule of thumb from the 80-paper benchmark):\n"
        "  - typical paper:           30-100 KB (~30 claims × ~2 KB each)\n"
        "  - heavy paper (Shannon-, Hayes-, Hubinger-class):  90-100 KB\n"
        "  - short / focused paper:   30-40 KB\n"
        "If your output is < 25 KB, you are almost certainly missing claims — "
        "re-scan the paper for findings, definitions, observations, and "
        "limitations. If > 150 KB, you are inventing detail; tighten."
    )
    if user_hint:
        user_text += f"\n\nCaller hint (advisory, not authoritative): {user_hint}"

    # CALIBRATED MODEL CONFIG (pt.3 lock, 2026-04-26) — do not change.
    #
    # 30+ prompt variants × ~700 runs × $700+ spend × R82 grid (n=72) lock
    # in v0.13g × effort=none. Pareto-dominates prior champion on coverage
    # (97.4% vs 93.6%), EXIST claims (16.7 vs 9.2), zero thesis-level miss.
    # See experiments/PRODUCTION_CHAMPION.md.
    #
    # Empirical failure modes if you "tune":
    #   - effort >= "low"  → thinking-stage compression drops thesis claims
    #                        (Hubinger persistence, Edmondson H3, etc.)
    #   - any `thinking` parameter → same effect
    #   - max_tokens < 32K → truncates dense papers mid-JSON
    #
    # The Anthropic SDK has no literal "none" for effort; the way to
    # express it is to omit `output_config` (and `thinking`) entirely,
    # which leaves Opus 4.7 in its default no-extended-thinking mode —
    # exactly what the R82 grid validated.
    # Stream is required at this max_tokens to avoid SDK HTTP timeouts.
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        # Intentionally NOT passing `thinking` or `output_config.effort`.
        # That is the calibrated configuration; do not add them back.
        system=[
            {
                "type": "text",
                "text": system_prompt,
                # 5-minute TTL: cheap repeat extractions of the same prompt
                # within a session. The prompt is fixed across every call,
                # so the cache hit rate after the first call is ~100%.
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        **({"title": pdf_filename} if pdf_filename else {}),
                    },
                    {"type": "text", "text": user_text},
                ],
            }
        ],
    ) as stream:
        final = stream.get_final_message()

    # Concatenate all text blocks (thinking blocks are skipped).
    response_text = "".join(b.text for b in final.content if getattr(b, "type", "") == "text")
    if not response_text.strip():
        raise ValueError(
            f"Model returned no text content. stop_reason={final.stop_reason}"
        )

    json_str = _strip_to_json(response_text)
    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model output was not valid JSON. stop_reason={final.stop_reason}, "
            f"first 200 chars: {json_str[:200]!r}, error: {e}"
        )

    # Pydantic validation — this can raise; caller's responsibility to handle
    # and to still charge for the API call (which already happened).
    extraction = Extraction.model_validate(raw)

    return ExtractionResult(
        extraction=extraction,
        raw_json=raw,
        cost_usd=_compute_cost_usd(final.usage, model),
        input_tokens=final.usage.input_tokens or 0,
        output_tokens=final.usage.output_tokens or 0,
        cache_creation_input_tokens=final.usage.cache_creation_input_tokens or 0,
        cache_read_input_tokens=final.usage.cache_read_input_tokens or 0,
        model=model,
        stop_reason=final.stop_reason,
    )


# Re-exported for callers that want to know which prompt was used.
__all__ = [
    "ExtractionResult",
    "extract_pdf",
    "MAX_PDF_BYTES",
    "DEFAULT_MODEL",
    "EXTRACTION_PROMPT_VERSION",
]
