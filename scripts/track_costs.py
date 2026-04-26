"""Cost / time / token tracker for Citare extractions.

Two outputs:
  1. experiments/COST_LEDGER.md — human-readable, append-friendly
  2. experiments/_ai_workspace/cost_snapshot.json — machine-readable, latest snapshot

Usage:
  python scripts/track_costs.py                   # snapshot now
  python scripts/track_costs.py --batch R71       # filter by R-series prefix
  python scripts/track_costs.py --since 2026-04-25  # filter by run date
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "experiments" / "runs"


def collect(filter_prefix: str | None = None, since: str | None = None) -> list[dict]:
    runs = []
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir():
            continue
        if filter_prefix and f"_{filter_prefix}_" not in d.name:
            continue
        if since:
            ts = d.name.split("_", 1)[0]  # 20260425T123456Z
            try:
                run_date = datetime.strptime(ts[:8], "%Y%m%d").date().isoformat()
                if run_date < since:
                    continue
            except (ValueError, IndexError):
                pass
        m = d / "metrics.json"
        if not m.exists():
            continue
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            continue
        runs.append({
            "dir": d.name,
            "ts": d.name.split("_", 1)[0],
            "cost_usd": data.get("cost_usd", 0),
            "duration_sec": data.get("duration_sec", 0),
            "input_tok": data.get("input_tokens", 0),
            "cache_create_tok": data.get("cache_creation_input_tokens", 0),
            "cache_read_tok": data.get("cache_read_input_tokens", 0),
            "output_tok": data.get("output_tokens", 0),
            "claims": data.get("claim_counts", {}).get("total", 0),
            "errored": (d / "error.json").exists(),
        })
    return runs


def variant_from_name(name: str) -> str:
    m = re.search(r"_v0?(?:\.)?13([a-z])_", name)
    if m: return f"v0.13{m.group(1)}"
    if re.search(r"_v0?(?:\.)?13_", name): return "v0.13"
    m = re.search(r"_v0?(?:\.)?16([a-z])_", name)
    if m: return f"v0.16{m.group(1)}"
    if re.search(r"_v0?(?:\.)?12([a-z])_", name):
        m = re.search(r"_v0?(?:\.)?12([a-z])_", name); return f"v0.12{m.group(1)}"
    m = re.search(r"_v0\.(\d+[a-z]?)_", name)
    if m: return f"v0.{m.group(1)}"
    m = re.search(r"_v3(\d)(?:[a-z]+)?_", name)
    if m: return f"v3.{m.group(1)}"
    m = re.search(r"_v(\d+[a-z]?)_", name)
    if m: return f"v0.{m.group(1)}"
    return "unknown"


def summarize(runs: list[dict]) -> dict:
    if not runs:
        return {"n": 0}
    total_cost = sum(r["cost_usd"] for r in runs)
    total_dur = sum(r["duration_sec"] for r in runs)
    total_in = sum(r["input_tok"] + r["cache_create_tok"] + r["cache_read_tok"] for r in runs)
    total_out = sum(r["output_tok"] for r in runs)
    return {
        "n": len(runs),
        "n_errored": sum(1 for r in runs if r["errored"]),
        "total_cost_usd": round(total_cost, 4),
        "avg_cost_usd": round(total_cost / len(runs), 4),
        "total_duration_sec": round(total_dur, 1),
        "avg_duration_sec": round(total_dur / len(runs), 1),
        "wall_hours": round(total_dur / 3600, 2),
        "total_input_tok": total_in,
        "total_output_tok": total_out,
        "avg_total_tok_K": round((total_in + total_out) / len(runs) / 1000, 1),
        "total_claims": sum(r["claims"] for r in runs),
        "avg_claims": round(sum(r["claims"] for r in runs) / len(runs), 1),
    }


def write_ledger(out: Path, snapshots: dict) -> None:
    """Append-friendly markdown ledger. Snapshots dict has cumulative + per-batch."""
    lines = ["# Citare Cost / Time / Token Ledger", "",
             f"Last snapshot: {datetime.now(timezone.utc).isoformat(timespec='seconds')}", ""]

    cumulative = snapshots["cumulative"]
    lines += [
        "## Cumulative (all R-series, all variants)",
        "",
        f"- Runs (with metrics):   **{cumulative['n']}**",
        f"- Failed runs:           {cumulative['n_errored']}",
        f"- **Total cost:**        **${cumulative['total_cost_usd']:.2f} USD**",
        f"- Total wall time:       {cumulative['wall_hours']:.1f} hours of API time",
        f"- Total input tokens:    {cumulative['total_input_tok']:,} ({cumulative['total_input_tok']/1e6:.1f}M)",
        f"- Total output tokens:   {cumulative['total_output_tok']:,} ({cumulative['total_output_tok']/1e6:.1f}M)",
        f"- Average cost / run:    ${cumulative['avg_cost_usd']:.4f}",
        f"- Average duration / run:{cumulative['avg_duration_sec']:.0f}s",
        f"- Average tokens / run:  {cumulative['avg_total_tok_K']:.0f}K",
        "",
    ]

    if "by_variant" in snapshots:
        lines += ["## Cost by variant (top 10 by total spend)", "",
                  "| Variant | Runs | Total cost | Avg cost | Avg time | Avg tokens |",
                  "|---------|-----:|-----------:|---------:|---------:|-----------:|"]
        for v, s in snapshots["by_variant"][:10]:
            lines.append(f"| {v} | {s['n']} | ${s['total_cost_usd']:.2f} | ${s['avg_cost_usd']:.2f} | "
                         f"{s['avg_duration_sec']:.0f}s | {s['avg_total_tok_K']:.0f}K |")
        lines.append("")

    for batch_name, batch in snapshots.get("batches", {}).items():
        lines += [f"## Batch: {batch_name}", "",
                  f"- Runs: {batch['n']} (errored: {batch['n_errored']})",
                  f"- Cost: **${batch['total_cost_usd']:.2f}** (avg ${batch['avg_cost_usd']:.2f}/run)",
                  f"- Duration: {batch['wall_hours']:.2f}h wall-summed (avg {batch['avg_duration_sec']:.0f}s/run)",
                  f"- Tokens: {(batch['total_input_tok']+batch['total_output_tok'])/1e6:.2f}M total "
                  f"(avg {batch['avg_total_tok_K']:.0f}K/run)",
                  f"- Claims emitted: {batch['total_claims']} (avg {batch['avg_claims']:.1f}/paper)",
                  ""]

    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", help="Filter to one R-series prefix (e.g. R71)")
    ap.add_argument("--since", help="ISO date YYYY-MM-DD; only runs since this date")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    cumulative_runs = collect()
    cumulative = summarize(cumulative_runs)

    by_variant = defaultdict(list)
    for r in cumulative_runs:
        by_variant[variant_from_name(r["dir"])].append(r)
    by_variant_summary = sorted(
        ((v, summarize(rs)) for v, rs in by_variant.items()),
        key=lambda x: -x[1]["total_cost_usd"]
    )

    batches = {}
    # always include R71 if present
    for batch_id in ("R71", "R72"):
        rs = collect(filter_prefix=batch_id)
        if rs:
            batches[batch_id] = summarize(rs)

    if args.batch:
        rs = collect(filter_prefix=args.batch)
        batches[args.batch] = summarize(rs)

    snapshots = {
        "snapshot_at": datetime.now(timezone.utc).isoformat(),
        "cumulative": cumulative,
        "by_variant": by_variant_summary,
        "batches": batches,
    }

    # Write JSON snapshot
    snap_path = ROOT / "experiments" / "_ai_workspace" / "cost_snapshot.json"
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(snapshots, indent=2, default=str), encoding="utf-8")

    # Write Markdown ledger
    ledger_path = ROOT / "experiments" / "COST_LEDGER.md"
    write_ledger(ledger_path, snapshots)

    if not args.quiet:
        print(f"Snapshot at {snapshots['snapshot_at']}")
        print(f"  Cumulative:  {cumulative['n']} runs, ${cumulative['total_cost_usd']:.2f}, "
              f"{cumulative['wall_hours']:.1f}h, {cumulative['total_input_tok']/1e6:.1f}M+{cumulative['total_output_tok']/1e6:.1f}M tok")
        for batch_name, batch in batches.items():
            print(f"  Batch {batch_name}:  {batch['n']} runs, ${batch['total_cost_usd']:.2f}, "
                  f"{batch['wall_hours']:.2f}h, avg {batch['avg_total_tok_K']:.0f}K tok")
        print(f"  → {ledger_path}")
        print(f"  → {snap_path}")


if __name__ == "__main__":
    main()
