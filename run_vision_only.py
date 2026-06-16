"""VISION-ONLY runner (Layer A) — browser-use 0.13.2 + vision_only.patch.

Reruns the DOM-failure subset (the auto-vf-failures task ids) with targeting
driven by the CLEAN screenshot instead of the DOM index list:

  - use_vision=True                       (screenshot attached every step)
  - BROWSER_USE_VISION_ONLY=1             (patch: DOM text shows ONLY form fields)
  - agent.tools.set_coordinate_clicking(True)   (force coord clicks; don't rely on model-name gate)
  - exclude find_elements / dropdown / upload_file   (drop DOM crutches)

The prompt edit (clean-screenshot + click-by-coordinate) is baked into the
patched wheel (Layer B), so no override_system_message is needed here.

Key pilot output: per-step coordinate-click telemetry written to
results/vision-only/<task>/vision_only_steps.jsonl and a run-level
coord_click_summary.json, so we can answer "do coordinate clicks land?".

Usage:
    BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 AWS_REGION=us-west-2 \
        .venv-vision-only/bin/python run_vision_only.py --only Apple--9 --max-steps 25
    .venv-vision-only/bin/python run_vision_only.py --limit 8        # pilot
    .venv-vision-only/bin/python run_vision_only.py                  # full vf subset
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# CRITICAL: activate the Layer-B DOM suppression BEFORE browser_use is imported/used.
os.environ.setdefault("BROWSER_USE_VISION_ONLY", "1")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])

# Local browser must reach its own CDP endpoint over localhost. If a corporate
# HTTP(S) proxy is set, exclude loopback so the CDP /json/version fetch isn't
# routed through the proxy (symptom otherwise: "did not receive a valid HTTP response").
_loopback = "localhost,127.0.0.1,::1"
for _k in ("NO_PROXY", "no_proxy"):
    _cur = os.environ.get(_k, "")
    os.environ[_k] = _loopback if not _cur else f"{_cur},{_loopback}"


def _find_chrome_for_testing() -> Optional[str]:
    """Locate the isolated Playwright 'Chrome for Testing' binary so we don't try to
    launch the user's already-running system Chrome (whose --remote-debugging-port
    won't bind when Chrome is already open). Override with BROWSER_USE_EXECUTABLE_PATH."""
    env = os.environ.get("BROWSER_USE_EXECUTABLE_PATH")
    if env and Path(env).exists():
        return env
    import glob as _glob
    cands = sorted(_glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
        "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")))
    return cands[-1] if cands else None


CHROME_EXE = _find_chrome_for_testing()

from browser_use import Agent  # noqa: E402
from browser_use.browser.profile import BrowserProfile  # noqa: E402
from browser_use.browser.session import BrowserSession  # noqa: E402
from browser_use.llm import ChatAnthropicBedrock  # noqa: E402

ROOT = Path(__file__).resolve().parent
VF_DIR = ROOT / "auto-vf-failures"
OUT_DIR = ROOT / "results" / "vision-only"
TASKS_FILE = ROOT / "data" / "WebVoyager_data.jsonl"

# Actions to drop so the model can't fall back to DOM-driven targeting.
# Names verified against browser-use 0.13.2 registry.
EXCLUDE_ACTIONS = ["find_elements", "select_dropdown", "dropdown_options", "upload_file"]


def load_tasks() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in TASKS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out[d["id"]] = d
    return out


def vf_task_ids() -> list[str]:
    return sorted(p.name for p in VF_DIR.iterdir() if p.is_dir())


def build_llm() -> Any:
    return ChatAnthropicBedrock(
        model=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        aws_region=os.environ["AWS_REGION"],
        temperature=0.0,
        max_tokens=4096,
    )


def _action_items(model_output: Any) -> list[dict]:
    """Return [{name, params}] for the actions in a step's model_output."""
    items: list[dict] = []
    actions = getattr(model_output, "action", None) or []
    for a in actions:
        try:
            d = a.model_dump(exclude_none=True)
        except Exception:
            d = dict(getattr(a, "__dict__", {}))
        for name, params in d.items():
            items.append({"name": name, "params": params})
    return items


async def run_one(task: dict, llm: Any, max_steps: int) -> dict:
    task_id = task["id"]
    task_dir = OUT_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    task_str = f"{task['ques']} on {task['web']}"

    step_log_path = task_dir / "vision_only_steps.jsonl"
    step_log = step_log_path.open("w", encoding="utf-8")

    # telemetry accumulators
    n_coord_clicks = 0
    n_index_clicks = 0
    n_input_actions = 0
    step_rows: list[dict] = []

    _profile_kw = dict(headless=True, viewport={"width": 1280, "height": 1024})
    if CHROME_EXE:
        _profile_kw["executable_path"] = CHROME_EXE
    session = BrowserSession(browser_profile=BrowserProfile(**_profile_kw))

    async def on_step(browser_state: Any, model_output: Any, step_no: int) -> None:
        nonlocal n_coord_clicks, n_index_clicks, n_input_actions
        url = getattr(browser_state, "url", None)
        acts = _action_items(model_output)
        for it in acts:
            nm, p = it["name"], (it["params"] or {})
            if nm == "click":
                if p.get("coordinate_x") is not None or p.get("coordinate_y") is not None:
                    n_coord_clicks += 1
                elif p.get("index") is not None:
                    n_index_clicks += 1
            elif nm == "input":
                n_input_actions += 1
        row = {
            "step": step_no,
            "url": url,
            "eval_prev": getattr(model_output, "evaluation_previous_goal", "") or "",
            "next_goal": getattr(model_output, "next_goal", "") or "",
            "actions": acts,
        }
        step_rows.append(row)
        step_log.write(json.dumps(row, default=str) + "\n")
        step_log.flush()

    started = time.time()
    result: dict = {
        "task_id": task_id, "web": task["web"], "task_prompt": task_str,
        "vision_only": True, "start_time": str(datetime.now()),
    }
    try:
        await session.start()
        agent = Agent(
            task=task_str,
            llm=llm,
            browser=session,
            use_vision=True,
            register_new_step_callback=on_step,
        )
        # Force coordinate clicking on (don't rely on the model-name gate) and drop DOM crutches.
        agent.tools.set_coordinate_clicking(True)
        registered = set(agent.tools.registry.registry.actions.keys())
        excluded, missing = [], []
        for name in EXCLUDE_ACTIONS:
            if name in registered:
                agent.tools.exclude_action(name)
                excluded.append(name)
            else:
                missing.append(name)
        result["excluded_actions"] = excluded
        result["exclude_not_found"] = missing

        history = await agent.run(max_steps=max_steps)
        try:
            history.save_to_file(task_dir / "history.json")
        except Exception:
            pass
        result["num_steps"] = len(getattr(history, "history", []) or [])
        result["final_answer"] = history.final_result() or "<NO FINAL ANSWER>"
        result["is_done"] = bool(history.is_done())
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-2000:]

    # Write the result + telemetry BEFORE browser teardown, so a hanging
    # session.kill() (browser-use shutdown can block) can't lose the result.
    result["duration_seconds"] = round(time.time() - started, 1)
    result["coord_clicks"] = n_coord_clicks
    result["index_clicks"] = n_index_clicks
    result["input_actions"] = n_input_actions
    step_log.close()
    (task_dir / "task_result.json").write_text(json.dumps(result, indent=2, default=str))

    # Best-effort teardown with a hard timeout so it can never hang the run.
    try:
        await asyncio.wait_for(session.kill(), timeout=20)
    except Exception:
        try:
            await asyncio.wait_for(session.stop(), timeout=10)
        except Exception:
            pass
    print(f"[{task_id}] steps={result.get('num_steps','?')} "
          f"coord_clicks={n_coord_clicks} index_clicks={n_index_clicks} "
          f"input={n_input_actions} done={result.get('is_done')} "
          f"err={result.get('error','')[:60]}")
    return result


async def main(args: argparse.Namespace) -> None:
    all_tasks = load_tasks()
    ids = vf_task_ids()
    if args.only:
        want = set(args.only.split(","))
        ids = [t for t in ids if t in want]
    if args.limit:
        # ensure Apple--9 is in the pilot if present
        head = [t for t in ids if t == "Apple--9"]
        rest = [t for t in ids if t != "Apple--9"]
        ids = (head + rest)[: args.limit]

    missing = [t for t in ids if t not in all_tasks]
    ids = [t for t in ids if t in all_tasks]
    print(f"vision-only: running {len(ids)} task(s) -> {OUT_DIR}")
    if missing:
        print(f"  (skipped {len(missing)} ids not found in dataset: {missing[:5]}...)")
    print(f"  BROWSER_USE_VISION_ONLY={os.environ.get('BROWSER_USE_VISION_ONLY')}  "
          f"model={os.getenv('BEDROCK_MODEL_ID','us.anthropic.claude-sonnet-4-6')}  region={os.environ['AWS_REGION']}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    llm = build_llm()

    summary = []
    for tid in ids:
        r = await run_one(all_tasks[tid], llm, args.max_steps)
        summary.append({k: r.get(k) for k in
                        ("task_id", "num_steps", "coord_clicks", "index_clicks",
                         "input_actions", "is_done", "final_answer", "error")})

    totals = {
        "n_tasks": len(summary),
        "total_coord_clicks": sum(s["coord_clicks"] or 0 for s in summary),
        "total_index_clicks": sum(s["index_clicks"] or 0 for s in summary),
        "tasks_with_any_coord_click": sum(1 for s in summary if (s["coord_clicks"] or 0) > 0),
        "tasks_done": sum(1 for s in summary if s["is_done"]),
        "per_task": summary,
    }
    (OUT_DIR / "coord_click_summary.json").write_text(json.dumps(totals, indent=2, default=str))
    print("\n=== coord-click summary ===")
    print(f"  tasks: {totals['n_tasks']}  coord_clicks(total): {totals['total_coord_clicks']}  "
          f"index_clicks(total): {totals['total_index_clicks']}  "
          f"tasks_with_coord_click: {totals['tasks_with_any_coord_click']}  done: {totals['tasks_done']}")
    print(f"  wrote {OUT_DIR / 'coord_click_summary.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated task ids (subset of vf failures)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of tasks (pilot); includes Apple--9 first")
    ap.add_argument("--max-steps", type=int, default=25)
    asyncio.run(main(ap.parse_args()))
