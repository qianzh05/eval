"""WebVoyager runner v2 — browser-use 0.12.6 with stealth + profiling + auto-report.

Differences from `run_browser_use.py`:
  - Targets browser-use 0.12.6 (new BrowserProfile/BrowserSession API).
  - Patchright Chromium as the driver (if installed) for stealth.
  - Realistic per-task persona (UA / locale / timezone / viewport).
  - Site warm-up (visit root + idle) before each task.
  - Per-step CAPTCHA detection; aborts with `success="captcha_blocked"`.
  - Stuck/loop detection: ≥8 consecutive identical mutating actions → abort
    with `stuck=True`, `stuck_reason="action_loop"`.
  - Hard wall-clock cap per task (default 15 min) → stuck_reason="wall_clock".
  - Per-step profiling (LLM / action / DOM / screenshot) saved to steps.jsonl.
  - Per-task profile.json with phase totals and token counts.
  - run_manifest.json with config, versions, host info, dataset hash.
  - Auto-generates report.md / report.docx at the end.
  - Smart skip: keeps prior `success=='success'` results IF the prompt hasn't
    changed; re-runs tasks whose prompt was edited by `shift_dates.py`.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import platform
import random
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, TypedDict

# Patchright monkey-patch — must happen before browser_use is imported.
def _enable_patchright() -> bool:
    try:
        import patchright  # noqa: F401
        import patchright.async_api as _pw_async
        import patchright.sync_api as _pw_sync
        sys.modules.setdefault("playwright", patchright)
        sys.modules["playwright.async_api"] = _pw_async
        sys.modules["playwright.sync_api"] = _pw_sync
        return True
    except Exception:
        return False


USING_PATCHRIGHT = _enable_patchright()

# --- now import browser-use ---
from browser_use import Agent  # type: ignore  # noqa: E402

try:
    from browser_use.browser.profile import BrowserProfile  # type: ignore
    from browser_use.browser.session import BrowserSession  # type: ignore
    NEW_API = True
except Exception:
    NEW_API = False

# LLM imports.
#   - Agent uses browser-use's native ChatAnthropicBedrock (browser-use 0.12.x
#     rejects langchain LLMs in its token_cost_service.register_llm).
#   - Evaluator (auto_eval_browser_use.py) still uses langchain ChatBedrockConverse
#     because it constructs prompts with langchain HumanMessage/SystemMessage.
try:
    from browser_use.llm import ChatAnthropicBedrock  # type: ignore
    HAS_BEDROCK = True
except Exception:
    HAS_BEDROCK = False

try:
    from langchain_aws import ChatBedrockConverse  # type: ignore
    HAS_LC_BEDROCK = True
except Exception:
    HAS_LC_BEDROCK = False

from dotenv import load_dotenv

from eval_utils import captcha as _captcha
from eval_utils import stealth as _stealth
from eval_utils.loop_detector import LoopDetector
from eval_utils.profiler import TaskProfiler
from eval_utils.report import write as write_report

from evaluation.auto_eval_browser_use import auto_eval_by_gpt4o

load_dotenv()
log = logging.getLogger("eval")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")


# ---------------------------------------------------------------------------
# constants & types
# ---------------------------------------------------------------------------

class TaskData(TypedDict):
    id: str
    web: str
    ques: str
    web_name: str


DEFAULT_WALLCLOCK_CAP_S = 15 * 60   # 15 min/task
DEFAULT_STUCK_CONSEC = 8
DEFAULT_MAX_STEPS = 30


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()[:16]


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def build_agent_llm(provider: str) -> Any:
    """LLM used BY THE AGENT — must be browser-use native."""
    if provider == "bedrock":
        if not HAS_BEDROCK:
            raise RuntimeError("browser_use.llm.ChatAnthropicBedrock not importable")
        return ChatAnthropicBedrock(
            model=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
            aws_region=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            temperature=0.0,
            max_tokens=4096,
        )
    raise ValueError(f"unsupported provider: {provider}")


def build_eval_llm(provider: str) -> Any:
    """LLM used BY THE EVALUATOR — uses langchain message protocol."""
    if provider == "bedrock":
        if not HAS_LC_BEDROCK:
            raise RuntimeError("langchain_aws.ChatBedrockConverse not importable")
        return ChatBedrockConverse(
            model=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            temperature=0.0,
            max_tokens=4096,
        )
    raise ValueError(f"unsupported provider: {provider}")


def should_skip(task: TaskData, task_dir: Path) -> bool:
    """Skip iff prior result exists, is success, and prompt is byte-identical."""
    f = task_dir / "task_result.json"
    if not f.exists():
        return False
    try:
        prev = json.loads(f.read_text())
    except Exception:
        return False
    if prev.get("success") != "success":
        return False
    prior_prompt = (prev.get("task_prompt") or "").strip()
    cur_prompt = f"{task['ques']} on {task['web']}".strip()
    return prior_prompt == cur_prompt


def load_tasks(jsonl: Path) -> list[TaskData]:
    out: list[TaskData] = []
    for line in jsonl.read_text().splitlines():
        if not line.strip():
            continue
        out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# per-task execution
# ---------------------------------------------------------------------------

async def run_one_task(
    task: TaskData,
    agent_llm: Any,
    eval_llm: Any,
    results_dir: Path,
    use_vision: bool,
    max_steps: int,
    wallclock_cap_s: float,
    stuck_consec: int,
) -> dict[str, Any]:
    task_id = task["id"]
    task_dir = results_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    task_str = f"{task['ques']} on {task['web']}"
    start_dt = datetime.now()
    started_at = time.time()

    profiler = TaskProfiler(task_id=task_id, task_dir=task_dir)
    loop = LoopDetector(consec_abort=stuck_consec)

    persona = _stealth.pick_persona(task_id)
    log.info(f"[{task_id}] starting · persona ua={persona['user_agent'][:30]}… vp={persona['viewport']}")

    # --- build browser session
    session: Optional[Any] = None
    captcha_kind: Optional[str] = None
    captcha_blocked = False
    stuck = False
    stuck_reason: Optional[str] = None
    error_text: Optional[str] = None
    history = None
    eval_result: str = "unknown"
    gpt_4v_res: str = ""
    final_answer: str = "<NO FINAL ANSWER>"
    num_steps = 0

    try:
        if not NEW_API:
            raise RuntimeError("browser-use 0.12.x API not found; reinstall browser-use==0.12.6")

        profile = _stealth.build_browser_profile(persona, headless=False)
        session = BrowserSession(browser_profile=profile)
        await session.start()

        # Warm-up: navigate to site root, idle, then to deep URL.
        # We get the underlying page from the session.
        try:
            page = await session.get_current_page()
            await _stealth.warm_up(page, task["web"], idle_seconds=6.0)
            kind = await _captcha.looks_like_captcha(page)
            if kind is not None:
                # Wait it out once for Cloudflare-class challenges before deciding it's terminal
                if not _captcha.is_terminal_block(kind):
                    await asyncio.sleep(10.0)
                    kind = await _captcha.looks_like_captcha(page)
            if kind is not None and _captcha.is_terminal_block(kind):
                captcha_kind = kind
                captcha_blocked = True
                raise _CaptchaAbort(kind)
        except _CaptchaAbort:
            raise
        except Exception as e:
            log.warning(f"[{task_id}] warm-up error: {e}")

        # --- per-step callback wires CAPTCHA + stuck detection + profiler
        async def on_step(browser_state: Any, model_output: Any, step_no: int) -> None:
            nonlocal captcha_kind, captcha_blocked, stuck, stuck_reason
            page = None
            try:
                page = await session.get_current_page()
            except Exception:
                pass
            url_after = None
            if page is not None:
                try: url_after = page.url
                except Exception: pass

            # Captcha check
            kind = None
            if page is not None:
                try: kind = await _captcha.looks_like_captcha(page)
                except Exception: kind = None
            if kind is not None and _captcha.is_terminal_block(kind):
                captcha_kind = kind
                captcha_blocked = True
                raise _CaptchaAbort(kind)

            # Stuck check
            actions = []
            try:
                for a in (getattr(model_output, "action", []) or []):
                    if isinstance(a, dict):
                        actions.append(a)
                    else:
                        # pydantic model — dump
                        d = a.model_dump() if hasattr(a, "model_dump") else {}
                        actions.append(d)
            except Exception:
                pass
            if loop.observe(actions):
                stuck = True
                stuck_reason = "action_loop"
                raise _StuckAbort(loop.summary())

            # Wall-clock cap
            if (time.time() - started_at) > wallclock_cap_s:
                stuck = True
                stuck_reason = "wall_clock"
                raise _StuckAbort({"reason": "wall_clock"})

            # Record this step (read the last item off the agent's history when available)
            try:
                hist = getattr(browser_state, "history", None) or []
                last_item = hist[-1] if hist else None
                profiler.record_step(
                    step_no=step_no,
                    history_item=last_item,
                    url_before=None,
                    url_after=url_after,
                    captcha_detected=kind is not None,
                    captcha_type=kind,
                    stuck_consec_run=loop.cur_run,
                )
            except Exception:
                pass

        agent = Agent(
            task=task_str,
            llm=agent_llm,
            browser=session,
            use_vision=use_vision,
            max_failures=3,
            register_new_step_callback=on_step,
        )

        history = await agent.run(max_steps=max_steps)
        history.save_to_file(task_dir / "history.json")
        num_steps = len(getattr(history, "history", []) or [])
        final_answer = history.final_result() or "<NO FINAL ANSWER>"

        # Auto-evaluator uses the langchain LLM (it constructs HumanMessage/SystemMessage).
        eval_result, gpt_4v_res = await auto_eval_by_gpt4o(
            task=task_str, openai_client=eval_llm, history=history,
        )

    except _CaptchaAbort as e:
        captcha_blocked = True
        captcha_kind = str(e)
        eval_result = "captcha_blocked"
        error_text = f"captcha_blocked:{captcha_kind}"
        log.info(f"[{task_id}] aborted (captcha:{captcha_kind})")
    except _StuckAbort as e:
        stuck = True
        eval_result = "failed"
        error_text = f"stuck:{stuck_reason}"
        log.info(f"[{task_id}] aborted (stuck:{stuck_reason})")
    except Exception as e:
        eval_result = "failed"
        error_text = f"{type(e).__name__}: {e}"
        log.warning(f"[{task_id}] crashed: {error_text}\n{traceback.format_exc(limit=3)}")
    finally:
        if session is not None:
            try: await session.stop()
            except Exception: pass

    end_dt = datetime.now()
    duration = (end_dt - start_dt).total_seconds()

    # --- write task_result.json (extended schema)
    task_result = {
        "task_id": task_id,
        "web_name": task["web"],
        "start_time": str(start_dt),
        "end_time": str(end_dt),
        "duration_seconds": duration,
        "num_steps": num_steps,
        "success": eval_result,
        "task_prompt": task_str,
        "final_answer": final_answer,
        "gpt_4v_res": gpt_4v_res,
        # extended fields
        "stuck": stuck,
        "stuck_reason": stuck_reason,
        "captcha_blocked": captcha_blocked,
        "captcha_type": captcha_kind,
        "error": error_text,
        "persona": persona,
        "loop_summary": loop.summary(),
        "patchright": USING_PATCHRIGHT,
        "browser_use_version": _bu_version(),
    }
    (task_dir / "task_result.json").write_text(json.dumps(task_result, indent=2, default=str))

    profiler.flush()
    (task_dir / "profile.json").write_text(json.dumps(profiler.task_summary(), indent=2, default=str))
    return task_result


def _bu_version() -> str:
    try:
        import browser_use
        return getattr(browser_use, "__version__", "unknown")
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# abort exceptions
# ---------------------------------------------------------------------------

class _CaptchaAbort(RuntimeError):
    pass


class _StuckAbort(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# orchestrator
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    tasks = load_tasks(Path(args.tasks))
    if args.limit:
        tasks = tasks[: args.limit]
    if args.shuffle:
        random.seed(args.seed)
        random.shuffle(tasks)

    vision_tag = "vision-true" if args.use_vision else "vision-false"
    results_dir = Path(f"results/examples-browser-use-{vision_tag}")
    results_dir.mkdir(parents=True, exist_ok=True)

    # manifest
    manifest = {
        "started_at": datetime.now().isoformat(),
        "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "python": sys.version.split()[0],
        "browser_use": _bu_version(),
        "patchright": USING_PATCHRIGHT,
        "config": {
            "use_vision": args.use_vision,
            "max_steps": args.max_steps,
            "max_concurrent": args.max_concurrent,
            "wallclock_cap_s": args.wallclock_cap_s,
            "stuck_consec": args.stuck_consec,
            "model_provider": args.model_provider,
            "bedrock_model_id": os.getenv("BEDROCK_MODEL_ID"),
        },
        "tasks_file": str(args.tasks),
        "tasks_file_hash": file_hash(Path(args.tasks)),
        "git_commit": git_commit(),
    }
    (results_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))

    agent_llm = build_agent_llm(args.model_provider)
    eval_llm = build_eval_llm(args.model_provider)
    sem = asyncio.Semaphore(args.max_concurrent)
    skip_count = 0
    done_count = 0

    async def run_with_sem(t: TaskData) -> None:
        nonlocal skip_count, done_count
        async with sem:
            if should_skip(t, results_dir / t["id"]):
                skip_count += 1
                log.info(f"[{t['id']}] skip (prior success, prompt unchanged)  [{done_count + skip_count}/{len(tasks)}]")
                return
            res = await run_one_task(
                t, agent_llm, eval_llm, results_dir,
                use_vision=args.use_vision,
                max_steps=args.max_steps,
                wallclock_cap_s=args.wallclock_cap_s,
                stuck_consec=args.stuck_consec,
            )
            done_count += 1
            log.info(f"[{t['id']}] done outcome={res['success']} steps={res['num_steps']} "
                     f"dur={res['duration_seconds']:.0f}s  [{done_count + skip_count}/{len(tasks)}]")

    await asyncio.gather(*[run_with_sem(t) for t in tasks], return_exceptions=False)

    log.info(f"run complete. skipped={skip_count} run={done_count} total={len(tasks)}")
    report_path = write_report(results_dir)
    log.info(f"report written: {report_path}")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-provider", default="bedrock", choices=["bedrock"])
    ap.add_argument("--use-vision", type=lambda s: s.lower() == "true", default=True)
    ap.add_argument("--max-concurrent", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
    ap.add_argument("--wallclock-cap-s", type=float, default=DEFAULT_WALLCLOCK_CAP_S)
    ap.add_argument("--stuck-consec", type=int, default=DEFAULT_STUCK_CONSEC)
    ap.add_argument("--tasks", default="data/WebVoyager_data.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N tasks")
    ap.add_argument("--shuffle", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
