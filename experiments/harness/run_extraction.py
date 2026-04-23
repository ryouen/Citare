"""
Citare extraction experiment harness.

Runs an extraction prompt against a PDF via the Anthropic API and records
everything needed to compare experiments: tokens, duration, cost, raw output,
and schema validation.

Usage:
    python run_extraction.py \
        --prompt experiments/prompts/v0.1_baseline.md \
        --pdf pdfs/06_Psychological_Safety/Edmondson_1999.pdf \
        --model claude-opus-4-7 \
        --thinking-budget 0 \
        --run-id baseline_edmondson \
        --notes "Baseline: v0.1 + no thinking + original PDF"
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "experiments" / "runs"

# Prices per million tokens (USD). Update if Anthropic changes pricing.
# Opus 4.7 estimated at current Opus tier; verify with billing later.
PRICES_PER_MTOK = {
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00, "thinking": 75.00},
    "claude-sonnet-4-6":  {"input":  3.00, "output": 15.00, "thinking": 15.00},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00, "thinking": 4.00},
}


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    keyfile = Path.home() / ".anthropic" / "api_key"
    if keyfile.exists():
        return keyfile.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        "ANTHROPIC_API_KEY not in env and ~/.anthropic/api_key not found"
    )


def encode_pdf(pdf_path: Path) -> str:
    return base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8")


def estimate_cost(model: str, usage: dict) -> float:
    """
    Anthropic prices (at time of writing):
      - input (regular)       = base rate
      - input (cache write)   = base rate × 1.25
      - input (cache read)    = base rate × 0.1
      - output                = output rate
    """
    p = PRICES_PER_MTOK.get(model)
    if not p:
        return 0.0
    regular_in = usage.get("input_tokens", 0)
    cache_write = usage.get("cache_creation_input_tokens", 0)
    cache_read = usage.get("cache_read_input_tokens", 0)
    out = usage.get("output_tokens", 0)
    cost = (
        regular_in * p["input"]
        + cache_write * p["input"] * 1.25
        + cache_read * p["input"] * 0.1
        + out * p["output"]
    ) / 1_000_000
    return round(cost, 6)


def run(args) -> dict:
    prompt_path = Path(args.prompt).resolve()
    pdf_path = Path(args.pdf).resolve()
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    pdf_b64 = encode_pdf(pdf_path)

    client = anthropic.Anthropic(api_key=load_api_key())

    # Build messages: document first, instructions second (per prompt caching best practice)
    user_content = [
        {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": pdf_b64,
            },
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": prompt_text,
        },
    ]

    request_kwargs = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "messages": [{"role": "user", "content": user_content}],
    }

    # Opus 4.7 uses adaptive thinking + output_config.effort
    # Sonnet 4.6 / Haiku 4.5 may still support the older enabled+budget_tokens format.
    if args.effort != "none":
        if "opus-4-7" in args.model:
            request_kwargs["thinking"] = {"type": "adaptive"}
            request_kwargs["output_config"] = {"effort": args.effort}
        else:
            # Legacy models: map effort to budget_tokens
            budget = {"low": 2000, "medium": 5000, "high": 20000, "xhigh": 40000, "max": 60000}.get(args.effort, 0)
            if budget > 0:
                request_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget,
                }

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / f"{timestamp}_{args.run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "prompt_used.md").write_text(prompt_text, encoding="utf-8")
    (run_dir / "meta.json").write_text(json.dumps({
        "prompt_path": str(prompt_path),
        "pdf_path": str(pdf_path),
        "pdf_filename": pdf_path.name,
        "pdf_size_bytes": pdf_path.stat().st_size,
        "model": args.model,
        "effort": args.effort,
        "max_tokens": args.max_tokens,
        "run_id": args.run_id,
        "notes": args.notes,
        "timestamp": timestamp,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[{args.run_id}] model={args.model} effort={args.effort} pdf={pdf_path.name}")

    t0 = time.time()
    error = None
    response = None
    try:
        # Use streaming for long-running requests (required for requests >10min)
        with client.messages.stream(**request_kwargs) as stream:
            response = stream.get_final_message()
    except Exception as e:
        error = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
    duration = round(time.time() - t0, 3)

    if error:
        (run_dir / "error.json").write_text(json.dumps(error, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{args.run_id}] FAILED after {duration}s: {error['message']}")
        return {"run_dir": str(run_dir), "error": error, "duration_sec": duration}

    # Collect blocks
    thinking_blocks = []
    text_blocks = []
    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "thinking":
            thinking_blocks.append(getattr(block, "thinking", ""))
        elif btype == "text":
            text_blocks.append(block.text)

    full_text = "\n".join(text_blocks)
    thinking_text = "\n---\n".join(thinking_blocks)

    (run_dir / "raw_response.txt").write_text(full_text, encoding="utf-8")
    if thinking_text:
        (run_dir / "thinking.txt").write_text(thinking_text, encoding="utf-8")

    # Try to extract JSON from the text
    extraction_json = None
    json_valid = False
    json_error = None
    # First, look for ```json ... ``` blocks
    import re
    match = re.search(r"```(?:json)?\s*\n(.+?)\n```", full_text, re.DOTALL)
    candidate = match.group(1) if match else full_text.strip()
    # If the response starts/ends with braces, try direct parse
    try:
        extraction_json = json.loads(candidate)
        json_valid = True
    except json.JSONDecodeError as e:
        json_error = f"{type(e).__name__}: {e}"
        # Try to find the outermost {...}
        brace_start = candidate.find("{")
        brace_end = candidate.rfind("}")
        if brace_start >= 0 and brace_end > brace_start:
            try:
                extraction_json = json.loads(candidate[brace_start:brace_end + 1])
                json_valid = True
                json_error = None
            except json.JSONDecodeError as e2:
                json_error = f"{type(e2).__name__}: {e2}"

    if extraction_json is not None:
        (run_dir / "extraction.json").write_text(
            json.dumps(extraction_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Usage metrics
    usage = response.usage.model_dump() if hasattr(response.usage, "model_dump") else dict(response.usage)
    cost = estimate_cost(args.model, usage)

    # Quick summary counts
    counts = {"DEFINITION": 0, "RELATION": 0, "EXISTENCE_CLAIM": 0, "META_CLAIM": 0, "total": 0}
    theory_count = 0
    mm_count = 0
    relation_count = 0
    ref_count = 0
    if extraction_json and isinstance(extraction_json, dict):
        claims = extraction_json.get("claims", []) or []
        for c in claims:
            t = c.get("template_type", "")
            if t in counts:
                counts[t] += 1
            counts["total"] += 1
        theory_count = len(extraction_json.get("theories", []) or [])
        mm_count = len(extraction_json.get("measurement_methods", []) or [])
        relation_count = len(extraction_json.get("claim_relations", []) or [])
        ref_count = len(extraction_json.get("paper_references", []) or [])

    metrics = {
        "run_id": args.run_id,
        "timestamp": timestamp,
        "model": args.model,
        "effort": args.effort,
        "prompt_file": prompt_path.name,
        "pdf_filename": pdf_path.name,
        "pdf_size_bytes": pdf_path.stat().st_size,
        "duration_sec": duration,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cost_usd": cost,
        "json_valid": json_valid,
        "json_error": json_error,
        "claim_counts": counts,
        "theory_count": theory_count,
        "measurement_method_count": mm_count,
        "claim_relation_count": relation_count,
        "paper_reference_count": ref_count,
        "notes": args.notes,
        "stop_reason": response.stop_reason,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"[{args.run_id}] done in {duration}s | "
        f"in={metrics['input_tokens']} out={metrics['output_tokens']} "
        f"cost=${cost} claims={counts['total']} json_valid={json_valid}"
    )
    return metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--pdf", required=True)
    p.add_argument("--model", default="claude-opus-4-7")
    p.add_argument(
        "--effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="none",
        help="Opus 4.7: thinking effort level (none=no thinking). low/medium/high/xhigh/max for Opus 4.7.",
    )
    # Backwards-compat alias
    p.add_argument("--thinking-budget", type=int, default=None, help="(legacy alias; prefer --effort)")
    p.add_argument("--max-tokens", type=int, default=32000)
    p.add_argument("--run-id", required=True)
    p.add_argument("--notes", default="")
    args = p.parse_args()
    # Back-compat: if --thinking-budget provided, translate to --effort
    if args.thinking_budget is not None:
        args.effort = (
            "high" if args.thinking_budget >= 10000
            else "medium" if args.thinking_budget > 0
            else "none"
        )
    run(args)


if __name__ == "__main__":
    main()
