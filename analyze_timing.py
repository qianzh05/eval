"""Post-hoc per-step timing analysis from saved history.json files.

What this recovers that the in-run profiler missed:
  - Per-step elapsed time (delta between step_start_time / step_end_time
    in each history entry's metadata)
  - For runs whose history.json also includes input_tokens (browser-use v0.1.40
    behavior), token-per-step stats and a real cost estimate

What it cannot recover:
  - Sub-phase breakdown (LLM vs browser-action vs DOM vs screenshot).
    browser-use never separated these, in any version.

Usage:
    python analyze_timing.py                    # analyzes all 4 known runs
    python analyze_timing.py <results_dir>      # analyzes one
    python analyze_timing.py --md OUT.md ...    # write markdown to OUT.md
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# Claude Sonnet 4.6 Bedrock pricing (us-east-1, May 2026 approx)
INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00

DEFAULT_RUNS = [
    ("OLD Mac vision-true",  "results/examples-browser-use-vision-true"),
    ("OLD Mac vision-false", "results/examples-browser-use-vision-false"),
    ("NEW VM vision-true",   "results-vm-2026-05-20/examples-browser-use-vision-true"),
    ("NEW VM vision-false",  "results-vm-2026-05-20/examples-browser-use-vision-false"),
]


def percentiles(xs: list[float], qs=(50, 90, 95)) -> dict[str, float]:
    if not xs:
        return {f"p{q}": 0.0 for q in qs}
    s = sorted(xs)
    return {f"p{q}": s[min(len(s) - 1, max(0, int(round(q / 100 * (len(s) - 1)))))] for q in qs}


def summarize(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    p = percentiles(xs)
    return {"n": len(xs), "mean": statistics.mean(xs), "max": max(xs), **p}


def per_step_data(base: Path) -> dict:
    """Walk a run directory; return per-task and per-step data."""
    tasks = []
    step_durations: list[float] = []
    step_tokens: list[int] = []
    site_steps: dict[str, list[float]] = defaultdict(list)
    site_tokens: dict[str, list[int]] = defaultdict(list)
    by_outcome_steps: dict[str, list[float]] = defaultdict(list)

    if not base.is_dir():
        return {"available": False, "tasks": []}

    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        hp = d / "history.json"
        tp = d / "task_result.json"
        if not hp.is_file() or not tp.is_file():
            continue
        try:
            h = json.loads(hp.read_text())
            t = json.loads(tp.read_text())
        except Exception:
            continue
        site = d.name.split("--")[0]
        outcome = t.get("success") or "?"
        per_task_steps: list[float] = []
        per_task_tokens: list[int] = []
        for entry in h.get("history", []):
            m = entry.get("metadata") or {}
            s, e = m.get("step_start_time"), m.get("step_end_time")
            if s is None or e is None:
                continue
            dur = e - s
            if dur < 0.01 or dur > 3600:   # filter init-step zeros and pathological maxes (1h)
                continue
            per_task_steps.append(dur)
            step_durations.append(dur)
            site_steps[site].append(dur)
            by_outcome_steps[outcome].append(dur)
            tk = m.get("input_tokens")
            if tk:
                per_task_tokens.append(tk)
                step_tokens.append(tk)
                site_tokens[site].append(tk)
        tasks.append({
            "task_id": d.name, "site": site, "outcome": outcome,
            "n_steps": len(per_task_steps),
            "total_step_s": sum(per_task_steps),
            "mean_step_s": statistics.mean(per_task_steps) if per_task_steps else 0,
            "wall_clock_s": t.get("duration_seconds", 0),
            "input_tokens": sum(per_task_tokens) if per_task_tokens else None,
        })
    return {
        "available": True,
        "tasks": tasks,
        "all_step_durations": step_durations,
        "all_step_tokens": step_tokens,
        "site_steps": dict(site_steps),
        "site_tokens": dict(site_tokens),
        "outcome_steps": dict(by_outcome_steps),
    }


def md_table(headers, rows):
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def render_run(label: str, data: dict) -> str:
    if not data.get("available"):
        return f"\n## {label}\n\n_(directory not present; skipped)_\n"
    md = [f"\n## {label}\n"]
    overall = summarize(data["all_step_durations"])
    md.append(f"- tasks with history: **{len(data['tasks'])}**")
    md.append(f"- total per-step samples: **{overall['n']:,}**")
    md.append(f"- step duration (s): mean **{overall['mean']:.1f}** · p50 **{overall['p50']:.1f}** · "
              f"p90 **{overall['p90']:.1f}** · p95 **{overall['p95']:.1f}** · max **{overall['max']:.0f}**")
    if data["all_step_tokens"]:
        tk = summarize([float(x) for x in data["all_step_tokens"]])
        total_in = sum(data["all_step_tokens"])
        cost_in = total_in / 1_000_000 * INPUT_COST_PER_M
        md.append(f"- input tokens per step: mean **{tk['mean']:,.0f}** · p50 **{tk['p50']:,.0f}** · "
                  f"p90 **{tk['p90']:,.0f}**")
        md.append(f"- **total input tokens: {total_in:,}**  →  **input cost ≈ ${cost_in:,.2f}**")

    # Per-site
    md.append("\n### Per-site step duration\n")
    rows = []
    for site, xs in sorted(data["site_steps"].items(), key=lambda kv: -len(kv[1])):
        s = summarize(xs)
        tok_mean = (statistics.mean(data["site_tokens"][site])
                    if data["site_tokens"].get(site) else None)
        rows.append([site, s["n"], f"{s['mean']:.1f}", f"{s['p50']:.1f}",
                     f"{s['p90']:.1f}", f"{tok_mean:,.0f}" if tok_mean else "—"])
    md.append(md_table(["site", "n_steps", "mean_s", "p50_s", "p90_s", "mean_tok"], rows))

    # Per-outcome
    md.append("\n### Step duration by outcome\n")
    rows = []
    for oc in ("success", "failed", "captcha_blocked", "stuck", "unknown"):
        xs = data["outcome_steps"].get(oc) or []
        if not xs: continue
        s = summarize(xs)
        rows.append([oc, s["n"], f"{s['mean']:.1f}", f"{s['p50']:.1f}", f"{s['p90']:.1f}"])
    md.append(md_table(["outcome", "n_steps", "mean_s", "p50_s", "p90_s"], rows))

    # Top 10 slowest tasks
    md.append("\n### 10 slowest tasks (by total step time)\n")
    top = sorted(data["tasks"], key=lambda t: -t["total_step_s"])[:10]
    md.append(md_table(
        ["task_id", "outcome", "n_steps", "mean_step_s", "total_step_s"],
        [[t["task_id"], t["outcome"], t["n_steps"],
          f"{t['mean_step_s']:.1f}", f"{t['total_step_s']:.0f}"] for t in top]))
    return "\n".join(md)


def render_comparison(named: list[tuple[str, dict]]) -> str:
    md = ["\n## Cross-run comparison\n"]
    headers = ["metric"] + [n for n, _ in named]
    metrics = [
        ("tasks with history", lambda d: len(d.get("tasks", []))),
        ("step samples (total)", lambda d: len(d.get("all_step_durations") or [])),
        ("mean step duration (s)",
         lambda d: f"{statistics.mean(d['all_step_durations']):.1f}" if d.get("all_step_durations") else "—"),
        ("p50 step duration (s)",
         lambda d: f"{percentiles(d['all_step_durations'])['p50']:.1f}" if d.get("all_step_durations") else "—"),
        ("p90 step duration (s)",
         lambda d: f"{percentiles(d['all_step_durations'])['p90']:.1f}" if d.get("all_step_durations") else "—"),
        ("input tokens (total)",
         lambda d: f"{sum(d['all_step_tokens']):,}" if d.get("all_step_tokens") else "—"),
        ("input cost $ (real)",
         lambda d: f"${sum(d['all_step_tokens'])/1_000_000*INPUT_COST_PER_M:,.2f}" if d.get("all_step_tokens") else "—"),
    ]
    rows = [[name] + [str(fn(d)) for _, d in named] for name, fn in metrics]
    md.append(md_table(headers, rows))
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="*", help="results directories to analyze")
    ap.add_argument("--md", default="timing_report.md", help="output markdown path")
    args = ap.parse_args()

    runs = []
    if args.dirs:
        for d in args.dirs:
            p = Path(d)
            runs.append((p.name, p))
    else:
        runs = [(label, Path(p)) for label, p in DEFAULT_RUNS]

    collected: list[tuple[str, dict]] = []
    for label, p in runs:
        data = per_step_data(p)
        collected.append((label, data))

    out = [f"# Post-hoc timing analysis\n",
           f"_Generated from saved history.json metadata. Per-step durations are real "
           f"(step_end_time − step_start_time). Sub-phase breakdown (LLM vs browser action "
           f"vs DOM vs screenshot) is **not** recoverable — browser-use never separated those._\n"]
    out.append(render_comparison(collected))
    for label, data in collected:
        out.append(render_run(label, data))
    Path(args.md).write_text("\n".join(out))
    print(f"wrote {args.md}")


if __name__ == "__main__":
    main()
