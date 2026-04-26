"""Precise R83 cost / token / time analysis (no estimates).

Reads each R83 run's metrics.json directly. Reports:
  - Per-run table (paper, claims, EXIST, in_tok, out_tok, cost, duration)
  - Aggregate (sum, mean, ±SD)
  - Wall clock time (start/end from filesystem ctime of meta.json)
  - Compared to previous run's metrics for the same papers (R71-R73)

Output: experiments/R83_REEXTRACT_REPORT.md
"""
from __future__ import annotations

import json
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_r83_runs():
    runs = []
    for d in sorted((ROOT / "experiments" / "runs").glob("*_R83_v013g_*")):
        if not d.is_dir(): continue
        ext = d / "extraction.json"
        metr = d / "metrics.json"
        meta = d / "meta.json"
        if not (ext.exists() and metr.exists() and meta.exists()): continue
        if ext.stat().st_size < 100: continue
        m = re.search(r"_R83_v013g_(.+?)_s\d+$", d.name)
        if not m: continue
        paper_key = m.group(1)
        metr_data = json.loads(metr.read_text(encoding="utf-8"))
        meta_data = json.loads(meta.read_text(encoding="utf-8"))
        runs.append({
            "paper_key": paper_key,
            "dir": d.name,
            "ts_start": d.name.split("_", 1)[0],   # ISO compact
            "ctime": d.stat().st_ctime,
            "ext_mtime": ext.stat().st_mtime,
            "claims": metr_data.get("claim_counts", {}).get("total", 0),
            "exist_claims": metr_data.get("claim_counts", {}).get("EXISTENCE_CLAIM", 0),
            "rel_claims": metr_data.get("claim_counts", {}).get("RELATION", 0),
            "input_tok": metr_data.get("input_tokens", 0),
            "cache_create_tok": metr_data.get("cache_creation_input_tokens", 0),
            "cache_read_tok": metr_data.get("cache_read_input_tokens", 0),
            "output_tok": metr_data.get("output_tokens", 0),
            "cost_usd": metr_data.get("cost_usd", 0),
            "duration_sec": metr_data.get("duration_sec", 0),
            "pdf_path": meta_data.get("pdf_path", ""),
            "pdf_size_bytes": meta_data.get("pdf_size_bytes", 0),
        })
    return runs


def load_legacy_runs(paper_keys):
    """For each R83 paper_key, find the previous R71/R72/R73 run for comparison."""
    legacy = {}
    for paper_key in paper_keys:
        # Match any run dir whose suffix after _v013d_ equals paper_key (with truncation)
        for d in (ROOT / "experiments" / "runs").glob(f"*_v013d_{paper_key}_s1"):
            if not d.is_dir(): continue
            metr = d / "metrics.json"
            if not metr.exists(): continue
            data = json.loads(metr.read_text(encoding="utf-8"))
            legacy[paper_key] = {
                "dir": d.name,
                "claims": data.get("claim_counts", {}).get("total", 0),
                "exist_claims": data.get("claim_counts", {}).get("EXISTENCE_CLAIM", 0),
                "rel_claims": data.get("claim_counts", {}).get("RELATION", 0),
                "cost_usd": data.get("cost_usd", 0),
                "duration_sec": data.get("duration_sec", 0),
                "input_tok": data.get("input_tokens", 0),
                "cache_create_tok": data.get("cache_creation_input_tokens", 0),
                "cache_read_tok": data.get("cache_read_input_tokens", 0),
                "output_tok": data.get("output_tokens", 0),
            }
            break
    return legacy


def main():
    runs = load_r83_runs()
    if not runs:
        print("No R83 runs found.")
        return

    paper_keys = [r["paper_key"] for r in runs]
    legacy = load_legacy_runs(paper_keys)

    md = ["# R83 re-extraction report (v0.13g × effort=none)", "",
          f"Run count: **{len(runs)}** of 15 expected",
          ""]

    # Wall clock
    if runs:
        starts = [r["ctime"] for r in runs]
        ends = [r["ext_mtime"] for r in runs]
        wall_start = min(starts)
        wall_end = max(ends)
        wall_sec = wall_end - wall_start
        md += ["## Wall clock", "",
               f"- batch start (earliest meta.json ctime):  {wall_start:.0f} epoch",
               f"- batch end   (latest extraction.json mtime): {wall_end:.0f} epoch",
               f"- **wall duration: {wall_sec:.0f}s = {wall_sec/60:.1f} min**",
               ""]

    # Aggregate ±SD
    md += ["## Aggregate (n=" + str(len(runs)) + ")", "",
           "| metric | mean ± SD | min | max | sum |",
           "|--------|----------|----:|----:|----:|"]
    for label, key, fmt in [
        ("claims (total)", "claims", "{:.1f}"),
        ("claims (EXIST)", "exist_claims", "{:.1f}"),
        ("claims (RELATION)", "rel_claims", "{:.1f}"),
        ("input_tok (incl. cache)", "input_total", "{:.0f}"),
        ("output_tok", "output_tok", "{:.0f}"),
        ("cost_usd", "cost_usd", "${:.4f}"),
        ("duration_sec", "duration_sec", "{:.1f}"),
    ]:
        if key == "input_total":
            vals = [r["input_tok"] + r["cache_create_tok"] + r["cache_read_tok"] for r in runs]
        else:
            vals = [r[key] for r in runs]
        m = st.mean(vals)
        sd = st.stdev(vals) if len(vals) > 1 else 0
        if "{:.4f}" in fmt:
            md.append(f"| {label} | ${m:.4f} ± ${sd:.4f} | ${min(vals):.4f} | ${max(vals):.4f} | ${sum(vals):.2f} |")
        else:
            md.append(f"| {label} | {fmt.format(m)} ± {fmt.format(sd)} | "
                      f"{fmt.format(min(vals))} | {fmt.format(max(vals))} | {fmt.format(sum(vals))} |")
    md.append("")

    # Per-run table
    md += ["## Per-run detail", "",
           "| paper_key | dur (s) | in_tok | out_tok | claims | EXIST | REL | cost |",
           "|-----------|--------:|-------:|--------:|-------:|------:|----:|-----:|"]
    for r in sorted(runs, key=lambda x: -x["cost_usd"]):
        in_total = r["input_tok"] + r["cache_create_tok"] + r["cache_read_tok"]
        md.append(f"| {r['paper_key'][:38]} | {r['duration_sec']:.0f} | "
                  f"{in_total:,} | {r['output_tok']:,} | "
                  f"{r['claims']} | {r['exist_claims']} | {r['rel_claims']} | "
                  f"${r['cost_usd']:.4f} |")
    md.append("")

    # Comparison vs legacy (R71-R73 v0.13d × low) — same papers
    md += ["## Comparison: R83 (v0.13g × none) vs legacy (v0.13d × low) on the same papers", "",
           "| paper_key | EXIST(R83) vs (legacy) | total claims R83 vs legacy | cost R83 vs legacy |",
           "|-----------|-----------------------:|---------------------------:|--------------------:|"]
    delta_exist_total = 0
    delta_cost_total = 0
    delta_dur_total = 0
    legacy_cost_total = 0
    r83_cost_total = 0
    for r in sorted(runs, key=lambda x: x["paper_key"]):
        legacy_r = legacy.get(r["paper_key"])
        if not legacy_r:
            md.append(f"| {r['paper_key'][:38]} | {r['exist_claims']} (no legacy) | {r['claims']} (no legacy) | ${r['cost_usd']:.2f} (no legacy) |")
            continue
        exist_delta = r["exist_claims"] - legacy_r["exist_claims"]
        claims_delta = r["claims"] - legacy_r["claims"]
        cost_delta = r["cost_usd"] - legacy_r["cost_usd"]
        delta_exist_total += exist_delta
        delta_cost_total += cost_delta
        delta_dur_total += r["duration_sec"] - legacy_r["duration_sec"]
        legacy_cost_total += legacy_r["cost_usd"]
        r83_cost_total += r["cost_usd"]
        md.append(f"| {r['paper_key'][:38]} | "
                  f"**{r['exist_claims']}** vs {legacy_r['exist_claims']} (Δ{exist_delta:+d}) | "
                  f"**{r['claims']}** vs {legacy_r['claims']} (Δ{claims_delta:+d}) | "
                  f"**${r['cost_usd']:.2f}** vs ${legacy_r['cost_usd']:.2f} (Δ${cost_delta:+.2f}) |")

    md += ["",
           f"**Total Δ EXIST: {delta_exist_total:+d}**  ",
           f"**Total Δ duration: {delta_dur_total:+.0f}s**  ",
           f"**Total Δ cost: ${delta_cost_total:+.2f}** (legacy ${legacy_cost_total:.2f} → R83 ${r83_cost_total:.2f})  ",
           ""]

    out = ROOT / "experiments" / "R83_REEXTRACT_REPORT.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print(f"Wrote {out}")
    print()
    for line in md:
        print(line)


if __name__ == "__main__":
    main()
