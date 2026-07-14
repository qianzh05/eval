#!/usr/bin/env python3
"""Post-hoc scorer for pilot runs. Deterministic only - checker.py, no LLM.

Usage:
    python3 score_pilot.py --run-tag pilot-2026-07-XX          # score + summary
    python3 score_pilot.py --run-tag pilot-2026-07-XX --dry    # score, write nothing

Hard gate: test_checker.py must exit 0 (all frozen vectors green) before any
run is scored; refuses otherwise.

Per rep it builds the URL list the checker contract requires - steps.jsonl
urls plus history urls, TRUNCATED at the answer (done) step - and calls
check(task_id, answer, urls). The answer is final_answer only when is_done
is true; otherwise the rep is scored as an empty answer (FAIL) and the error/
truncation is preserved for rubric classification. Writes verdict fields back
into each task_result.json and a summary.json per run-tag.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

SUITE = Path(__file__).resolve().parent
sys.path.insert(0, str(SUITE))
from checker import check  # noqa: E402

MODES = ("on", "off", "auto")

# Bedrock list prices for us.anthropic.claude-sonnet-4-6 (USD per 1M tokens).
# Cache multipliers follow Anthropic's standard structure (write 1.25x base,
# read 0.1x base) - VERIFY against the current Bedrock price page before any
# cache-adjusted number goes into a doc or the paper.
PRICE_IN_PER_M = 3.00
PRICE_OUT_PER_M = 15.00
CACHE_WRITE_MULT = 1.25   # cache-creation input tokens
CACHE_READ_MULT = 0.10    # cached input tokens


def cache_adjusted_cost(u: dict) -> float | None:
    """Estimated real bill from usage_native's cached/uncached split.

    browser-use 0.13.2 (llm/anthropic/chat.py) defines prompt_tokens as
    input_tokens + cache_read ONLY - cache-creation tokens are additive,
    not a component of prompt_tokens. So uncached = prompt - cached, and
    creation is priced on top (subtracting creation too went negative on
    56/90 pilot reps and silently clamped to 0, undercounting real cost).
    KNOWN GAP (2026-07-14 pilot): vision-on reps report 0 cache-creation
    tokens despite 67% cache-read share - accounting bug in that invocation
    path; on-mode cache-adjusted cost is therefore a lower bound."""
    try:
        prompt = u.get("total_prompt_tokens") or 0
        cached = u.get("total_prompt_cached_tokens") or 0
        created = u.get("total_prompt_cache_creation_tokens") or 0
        out = u.get("total_completion_tokens") or 0
        uncached = max(prompt - cached, 0)
        return (uncached * PRICE_IN_PER_M
                + created * PRICE_IN_PER_M * CACHE_WRITE_MULT
                + cached * PRICE_IN_PER_M * CACHE_READ_MULT) / 1e6             + out * PRICE_OUT_PER_M / 1e6
    except Exception:
        return None


def vector_gate() -> None:
    r = subprocess.run([sys.executable, str(SUITE / "test_checker.py")],
                       capture_output=True, text=True, cwd=str(SUITE))
    if r.returncode != 0:
        print(r.stdout)
        raise SystemExit("REFUSING TO SCORE: test_checker.py gate is red.")
    print("vector gate:", (r.stdout.strip().splitlines() or ["?"])[-1])


def answer_step_index(steps: list[dict]) -> int | None:
    """Index of the LAST step containing a done action, else None.

    Why last: 0.13.2 skips a done that is packed with other actions ("Done
    action is allowed only as a single action"), so an early logged done may
    never have executed and the run continued. An EXECUTED done always ends
    the run, so the last done is provably the true answer step; truncating at
    the first one can drop the answer-critical WA query URL and false-fail a
    correct run at the gate (execution-confirmed by review)."""
    last = None
    for i, s in enumerate(steps):
        for a in s.get("actions", []):
            if a.get("name") == "done":
                last = i
    return last


def build_urls(rep_dir: Path, result: dict) -> list[str]:
    steps: list[dict] = []
    sj = rep_dir / "steps.jsonl"
    if sj.exists():
        for line in sj.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    steps.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    cut = answer_step_index(steps)
    kept = steps if cut is None else steps[: cut + 1]
    urls = [s.get("url") for s in kept if s.get("url")]
    # history_urls are merged WITHOUT truncation: history cannot extend past an
    # executed done, and it is NOT 1:1 aligned with steps.jsonl (initial_actions
    # add a step-0 item; error steps have history items but no callback), so an
    # index cut on it would be wrong. steps.jsonl carries the post-answer
    # leakage risk and is the one that gets truncated.
    for u in (result.get("history_urls") or []):
        if u and u not in urls:
            urls.append(u)
    return urls


def score_rep(rep_dir: Path, dry: bool) -> dict | None:
    trf = rep_dir / "task_result.json"
    if not trf.exists():
        return None
    result = json.loads(trf.read_text())
    task_id = result.get("task_id")
    answer = (result.get("final_answer") or "") if result.get("is_done") else ""
    urls = build_urls(rep_dir, result)
    try:
        verdict = check(task_id, answer, urls)
    except KeyError:
        return None  # unknown/retired id - never score silently
    result["checker"] = verdict
    result["success"] = "success" if verdict.get("verdict") == "PASS" else "failed"
    result["scored_with_urls"] = len(urls)
    if not dry:
        trf.write_text(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-tag", required=True)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    vector_gate()
    root = SUITE / "results" / args.run_tag
    if not root.exists():
        raise SystemExit(f"no such run dir: {root}")

    rows: list[dict] = []
    skipped: list[str] = []
    for mode in MODES:
        mdir = root / mode
        if not mdir.exists():
            continue
        for task_dir in sorted(p for p in mdir.iterdir() if p.is_dir()):
            for rep_dir in sorted(p for p in task_dir.iterdir()
                                  if p.is_dir() and p.name.startswith("rep")):
                r = score_rep(rep_dir, args.dry)
                if r:
                    rows.append(r)
                else:
                    skipped.append(str(rep_dir.relative_to(root)))
    if skipped:
        print(f"SKIPPED (no task_result.json or unknown/retired task id): {len(skipped)}")
        for x in skipped:
            print("  -", x)

    if not rows:
        raise SystemExit("nothing scored - no task_result.json files found")

    # ---- summary -----------------------------------------------------------
    agg: dict = defaultdict(lambda: {"pass": 0, "n": 0, "cost": 0.0, "steps": 0,
                                     "dur": 0.0, "shots": 0, "gate_fails": 0,
                                     "errors": 0})
    for r in rows:
        key = (r["task_id"], r["mode"])
        a = agg[key]
        a["n"] += 1
        a["pass"] += r["success"] == "success"
        a["cost"] += (r.get("cost_totals") or {}).get("cost_usd", 0.0)
        a["steps"] += r.get("num_steps", 0)
        a["dur"] += r.get("duration_seconds", 0.0)
        a["shots"] += r.get("screenshot_requests", 0)
        a["gate_fails"] += (r.get("checker") or {}).get("final_assertion") == "url-gate"
        a["errors"] += bool(r.get("error"))

    print(f"\n{'task':16s} {'mode':5s} {'pass':>6s} {'cost$':>7s} {'steps':>6s} "
          f"{'dur_s':>7s} {'shots':>5s} {'gate':>4s} {'err':>3s}")
    for (tid, mode) in sorted(agg):
        a = agg[(tid, mode)]
        n = max(a["n"], 1)
        print(f"{tid:16s} {mode:5s} {a['pass']}/{a['n']:<4d} {a['cost']:7.2f} "
              f"{a['steps']/n:6.1f} {a['dur']/n:7.1f} {a['shots']:5d} "
              f"{a['gate_fails']:4d} {a['errors']:3d}")

    total_cost = sum((r.get("cost_totals") or {}).get("cost_usd", 0.0) for r in rows)
    adj = [cache_adjusted_cost(r["usage_native"]) for r in rows
           if isinstance(r.get("usage_native"), dict)]
    adj_total = sum(a for a in adj if a is not None) if adj else None
    cached_tok = sum((r.get("usage_native") or {}).get("total_prompt_cached_tokens") or 0
                     for r in rows if isinstance(r.get("usage_native"), dict))
    print(f"\ntotal reps scored: {len(rows)}")
    print(f"  list-price estimate (cache-blind, comparable to May-run numbers): ${total_cost:.2f}")
    if adj_total is not None and adj:
        print(f"  cache-adjusted bill estimate ({len(adj)}/{len(rows)} reps had native usage, "
              f"{cached_tok/1e6:.1f}M cached tokens): ${adj_total:.2f}  "
              f"[rates assume write x{CACHE_WRITE_MULT}, read x{CACHE_READ_MULT} - verify]")

    if not args.dry:
        summary = {
            "run_tag": args.run_tag, "n_reps": len(rows),
            "per_cell": {f"{t}|{m}": v for (t, m), v in agg.items()},
            "total_cost_estimate_usd": round(total_cost, 2),
        }
        (root / "summary.json").write_text(json.dumps(summary, indent=2))
        print(f"summary -> {root/'summary.json'}")


if __name__ == "__main__":
    main()
