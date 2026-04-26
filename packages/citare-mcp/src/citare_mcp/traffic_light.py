"""Per-claim cite-safety judgment: green / yellow / red.

This is a derived signal — there is no single ``traffic_light`` column in
the schema. The colour is computed from existing fields:

  - claim_status          (Task 64 lifecycle)
  - verification_status   (in-paper vs proposed)
  - causal_strength       (design_basis vs author_framing mismatch)
  - integrity_warnings    (incompleteness_category on related edges)

The function returns both the colour and an ordered list of human-readable
reasons. The MCP / REST clients render the colour as a badge and reveal
the reasons on click.

Threshold philosophy: **strict**. Any single red-class condition turns the
light red. This biases the system toward "warn the user" over "let
borderline cites slide" — Citare's value is preventing miscitation, not
maximising green badges.
"""
from __future__ import annotations

from typing import Any


# What each colour means in plain English (not localised — that's the UI's job)
COLOR_DEFINITIONS: dict[str, str] = {
    "green":  "Safe to cite as-is, provided you use safe_verbs.",
    "yellow": "Citable with caveats. Mention the related context.",
    "red":    "Do not cite this claim alone — the field flags it.",
}


# Edge-category severity buckets. Keep aligned with
# incompleteness_vocabulary.severity but stricter where appropriate.
_RED_CATS = {
    "effect_disappears_under_control",
    "disputed",
    "retracted",
    "failed_to_replicate",
}
_YELLOW_CATS = {
    "hub_component",
    "boundary_condition",
    "underpowered",
}
_GREEN_CATS = {
    "none",
    "preregistered_confirmed",
    "extends_prior_definition",
}


def compute_traffic_light(
    claim: dict[str, Any],
    integrity_warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute the colour + reasons for one claim.

    `claim` is the row dict from cite_claim (parsed JSON fields).
    `integrity_warnings` is the list returned alongside it (each entry has
    `source_id`, `target_id`, `incompleteness_category` (or `category`),
    `relation_type`, optional `context`).
    """
    reds: list[str] = []
    yellows: list[str] = []

    # ---- R1: claim_status (lifecycle) ------------------------------------
    cs = claim.get("claim_status")
    if cs in ("retracted", "failed_to_replicate"):
        reds.append(f"claim_status = {cs} — the claim itself has been flagged at the field level.")
    elif cs in ("superseded", "contested"):
        yellows.append(f"claim_status = {cs} — the field has moved past or actively disputes this claim.")

    # ---- R2: verification_status -----------------------------------------
    vs = claim.get("verification_status")
    if vs == "not_supported":
        reds.append("verification_status = not_supported — the paper itself does not back this claim.")
    elif vs in ("proposed_in_paper", "mixed_support", "partial_support"):
        yellows.append(f"verification_status = {vs} — the paper hedges or only partially supports this.")

    # ---- R3: integrity warnings on incident edges ------------------------
    for w in integrity_warnings or []:
        cat = w.get("incompleteness_category") or w.get("category")
        if not cat:
            continue
        edge_str = f"{w.get('source_id','?')} → {w.get('target_id','?')}"
        if cat in _RED_CATS:
            reds.append(f"related edge ({edge_str}) flagged {cat} — controlling for / replicating shifts the conclusion.")
        elif cat in _YELLOW_CATS:
            yellows.append(f"related edge ({edge_str}) flagged {cat} — citing alone misses required context.")
        # GREEN cats produce no signal (clean relations don't add reasons)

    # ---- R4: design_basis vs author_framing mismatch ---------------------
    # Use effective_causal_strength if the caller already merged paper+claim,
    # otherwise fall back to the per-claim causal_strength.
    cs_data = claim.get("effective_causal_strength") or claim.get("causal_strength") or {}
    if isinstance(cs_data, str):
        # JSON column was passed through as raw text — try once
        try:
            import json as _json
            cs_data = _json.loads(cs_data)
        except Exception:
            cs_data = {}
    db = (cs_data or {}).get("design_basis")
    af = (cs_data or {}).get("author_framing_observed_only") or (cs_data or {}).get("author_framing")
    if db in ("cross_sectional", "theoretical") and af == "causal":
        yellows.append(
            f"design_basis = {db} but author framed as causal — only safe_verbs (associational language) are honest."
        )
    elif db == "cross_sectional" and (claim.get("template_type") == "RELATION"):
        # Even without explicit causal framing, a bivariate cross-sectional
        # RELATION claim is a cite-safety risk if pulled out of the paper.
        # Soft yellow only if no other reason already pushed yellow/red.
        if not (reds or yellows):
            yellows.append(
                "design_basis = cross_sectional — by design cannot establish causation; safe_verbs apply."
            )

    # ---- aggregate -------------------------------------------------------
    if reds:
        color = "red"
    elif yellows:
        color = "yellow"
    else:
        color = "green"
    return {
        "color": color,
        "summary": COLOR_DEFINITIONS[color],
        "reasons": reds + yellows,
    }


def compute_lightweight_color(
    claim_status: str | None,
    verification_status: str | None,
    design_basis: str | None,
    author_framing: str | None,
    *,
    template_type: str | None = None,
    has_red_edge: bool = False,
    has_yellow_edge: bool = False,
) -> str:
    """Cheap colour-only judgment for search-results bulk pre-fetch.

    Skips the per-edge reasons; just returns 'green' / 'yellow' / 'red'.
    Kept aligned with compute_traffic_light so the badge in search results
    matches the expanded reasons drawer.
    """
    if claim_status in ("retracted", "failed_to_replicate"):
        return "red"
    if verification_status == "not_supported":
        return "red"
    if has_red_edge:
        return "red"
    if claim_status in ("superseded", "contested"):
        return "yellow"
    if verification_status in ("proposed_in_paper", "mixed_support", "partial_support"):
        return "yellow"
    if has_yellow_edge:
        return "yellow"
    if design_basis in ("cross_sectional", "theoretical") and author_framing == "causal":
        return "yellow"
    # Bivariate cross-sectional RELATION claims default to yellow even when
    # no warnings exist — by design they cannot establish causation, and
    # naive cites routinely upgrade them to causal.
    if design_basis == "cross_sectional" and template_type == "RELATION":
        return "yellow"
    return "green"
