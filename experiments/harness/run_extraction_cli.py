"""
Citare extraction harness — Max-plan-native version.

Uses `claude -p --output-format json` subprocess (billed against Claude Max
subscription via OAuth), NOT direct Anthropic API calls. Preserves full
metrics, effort control, and model selection.

Usage:
    python run_extraction_cli.py \
        --prompt experiments/prompts/v0.1_baseline.md \
        --pdf pdfs/06_Psychological_Safety/Edmondson_1999_Psychological_Safety.pdf \
        --model claude-opus-4-7 \
        --effort medium \
        --run-id R_cli_test \
        --notes "CLI-based extraction test"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "experiments" / "runs"


def find_claude_binary() -> str:
    """Locate the claude CLI across platforms (Windows npm global installs use .cmd)."""
    candidates = ["claude"]
    if os.name == "nt":
        candidates = ["claude.cmd", "claude.exe", "claude"]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    # Last-ditch: common Windows npm global path
    if os.name == "nt":
        fallback = Path.home() / "AppData/Roaming/npm/claude.cmd"
        if fallback.exists():
            return str(fallback)
    raise FileNotFoundError("claude CLI not found in PATH")


def build_user_message(prompt_path: Path, pdf_path: Path) -> str:
    """Instruction telling Claude to Read the prompt + PDF and output only the extraction JSON."""
    return (
        f"You are running a Citare extraction task. Do the following:\n\n"
        f"1. Use the Read tool to read the extraction prompt file at:\n"
        f"   {prompt_path}\n\n"
        f"2. Use the Read tool to read the target PDF (all pages) at:\n"
        f"   {pdf_path}\n\n"
        f"3. Apply the extraction prompt to the PDF and produce the full structured JSON "
        f"output exactly as the prompt specifies.\n\n"
        f"OUTPUT RULES (strict):\n"
        f"- Your final message must be the JSON object ONLY.\n"
        f"- No commentary before or after the JSON.\n"
        f"- No markdown code fences around the JSON. Raw JSON starting with {{ and ending with }}.\n"
        f"- If the JSON is long, output the complete JSON in a single response.\n"
    )


def extract_json_from_result(result_text: str) -> tuple[dict | None, str | None]:
    """Try several strategies to parse the JSON extraction output."""
    stripped = result_text.strip()
    # Try direct parse
    try:
        return json.loads(stripped), None
    except json.JSONDecodeError as e:
        err = f"{type(e).__name__}: {e}"

    # Strip markdown fences
    m = re.search(r"```(?:json)?\s*\n(.+?)\n```", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1)), None
        except json.JSONDecodeError as e:
            err = f"{type(e).__name__}: {e}"

    # Find outermost {...}
    s = stripped.find("{")
    e = stripped.rfind("}")
    if s >= 0 and e > s:
        try:
            return json.loads(stripped[s:e + 1]), None
        except json.JSONDecodeError as e2:
            err = f"{type(e2).__name__}: {e2}"

    return None, err


def run(args) -> dict:
    prompt_path = Path(args.prompt).resolve()
    pdf_path = Path(args.pdf).resolve()
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    user_message = build_user_message(prompt_path, pdf_path)

    claude_bin = find_claude_binary()
    # Pass user_message via stdin to avoid Windows command-line argument quirks.
    cmd = [
        claude_bin, "-p",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--max-budget-usd", str(args.max_budget_usd),
    ]
    if args.effort != "none":
        cmd += ["--effort", args.effort]
    if args.model:
        cmd += ["--model", args.model]
    if args.bare:
        cmd.append("--bare")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / f"{timestamp}_{args.run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "prompt_used.md").write_text(prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
    (run_dir / "user_message.txt").write_text(user_message, encoding="utf-8")
    (run_dir / "meta.json").write_text(json.dumps({
        "prompt_path": str(prompt_path),
        "pdf_path": str(pdf_path),
        "pdf_filename": pdf_path.name,
        "pdf_size_bytes": pdf_path.stat().st_size,
        "model_requested": args.model or "(default)",
        "effort": args.effort,
        "max_budget_usd": args.max_budget_usd,
        "cmd": cmd[:8] + ["<user_message omitted>"] + cmd[9:] if len(cmd) > 8 else cmd,
        "run_id": args.run_id,
        "notes": args.notes,
        "timestamp": timestamp,
        "harness_mode": "cli (Max plan via claude -p)",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[{args.run_id}] model={args.model or 'default'} effort={args.effort} pdf={pdf_path.name}")

    t0 = time.time()
    error = None
    proc = None
    try:
        proc = subprocess.run(
            cmd,
            input=user_message,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=args.timeout_sec,
        )
    except subprocess.TimeoutExpired:
        error = {"type": "TimeoutExpired", "message": f"claude -p exceeded {args.timeout_sec}s"}
    except Exception as e:
        error = {"type": type(e).__name__, "message": str(e), "traceback": traceback.format_exc()}
    duration = round(time.time() - t0, 3)

    if error:
        (run_dir / "error.json").write_text(json.dumps(error, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{args.run_id}] FAILED after {duration}s: {error['message']}")
        return {"run_dir": str(run_dir), "error": error, "duration_sec": duration}

    (run_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")

    if proc.returncode != 0:
        (run_dir / "error.json").write_text(json.dumps({
            "type": "ClaudeCliError",
            "returncode": proc.returncode,
            "stderr_head": (proc.stderr or "")[:2000],
            "stdout_head": (proc.stdout or "")[:2000],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{args.run_id}] claude -p failed rc={proc.returncode}")
        return {"run_dir": str(run_dir), "returncode": proc.returncode}

    # Parse the top-level JSON from claude -p --output-format json
    top_level = None
    try:
        top_level = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        (run_dir / "raw_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
        (run_dir / "error.json").write_text(json.dumps({
            "type": "TopLevelJSONDecodeError",
            "message": str(e),
            "stdout_head": (proc.stdout or "")[:2000],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{args.run_id}] FAILED to parse claude -p output")
        return {"run_dir": str(run_dir), "error": "top-level JSON parse failed"}

    (run_dir / "claude_p_response.json").write_text(
        json.dumps(top_level, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # The extraction JSON is inside result field as a string
    result_text = top_level.get("result", "") or ""
    (run_dir / "raw_response.txt").write_text(result_text, encoding="utf-8")

    extraction_json, json_error = extract_json_from_result(result_text)
    json_valid = extraction_json is not None

    if extraction_json:
        (run_dir / "extraction.json").write_text(
            json.dumps(extraction_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Summary metrics
    counts = {"DEFINITION": 0, "RELATION": 0, "EXISTENCE_CLAIM": 0, "META_CLAIM": 0, "total": 0}
    theory_count = mm_count = rel_count = ref_count = 0
    if isinstance(extraction_json, dict):
        for c in (extraction_json.get("claims") or []):
            t = c.get("template_type", "")
            if t in counts:
                counts[t] += 1
            counts["total"] += 1
        theory_count = len(extraction_json.get("theories", []) or [])
        mm_count = len(extraction_json.get("measurement_methods", []) or [])
        rel_count = len(extraction_json.get("claim_relations", []) or [])
        ref_count = len(extraction_json.get("paper_references", []) or [])

    usage = top_level.get("usage") or {}
    model_usage = top_level.get("modelUsage") or {}
    # Pick primary model (largest cost share)
    primary_model = None
    primary_cost = 0.0
    for mname, m in model_usage.items():
        if m.get("costUSD", 0) > primary_cost:
            primary_cost = m["costUSD"]
            primary_model = mname

    metrics = {
        "run_id": args.run_id,
        "timestamp": timestamp,
        "harness_mode": "cli",
        "model": primary_model or args.model or "(default)",
        "effort": args.effort,
        "prompt_file": prompt_path.name,
        "pdf_filename": pdf_path.name,
        "pdf_size_bytes": pdf_path.stat().st_size,
        "duration_sec": duration,
        "duration_api_ms": top_level.get("duration_api_ms"),
        "num_turns": top_level.get("num_turns"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cost_usd": top_level.get("total_cost_usd", 0),
        "json_valid": json_valid,
        "json_error": json_error,
        "claim_counts": counts,
        "theory_count": theory_count,
        "measurement_method_count": mm_count,
        "claim_relation_count": rel_count,
        "paper_reference_count": ref_count,
        "notes": args.notes,
        "stop_reason": top_level.get("stop_reason"),
        "terminal_reason": top_level.get("terminal_reason"),
        "model_usage": model_usage,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(
        f"[{args.run_id}] done in {duration}s | "
        f"in={metrics['input_tokens']}+{metrics['cache_creation_input_tokens']}c "
        f"out={metrics['output_tokens']} "
        f"cost=${metrics['cost_usd']:.3f} "
        f"claims={counts['total']} json_valid={json_valid}"
    )
    return metrics


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", required=True)
    p.add_argument("--pdf", required=True)
    p.add_argument("--model", default=None, help="e.g. claude-opus-4-7 (omit for default)")
    p.add_argument(
        "--effort",
        choices=["none", "low", "medium", "high", "xhigh", "max"],
        default="none",
    )
    p.add_argument("--max-budget-usd", type=float, default=2.00)
    p.add_argument("--timeout-sec", type=int, default=1200, help="subprocess timeout")
    p.add_argument("--run-id", required=True)
    p.add_argument("--notes", default="")
    p.add_argument("--bare", action="store_true", help="pass --bare to claude (no session context)")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
