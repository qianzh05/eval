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

# Methodology note: no Patchright, no stealth shim. We run vanilla Playwright
# Chromium openly; sites that block us get recorded as `captcha_blocked`.
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
from eval_utils.rate_limiter import DomainRateLimiter, interleave_by_site
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
DEFAULT_RATE_LIMIT_S = 30.0         # per-domain politeness window


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
    rate_limiter: DomainRateLimiter,
) -> dict[str, Any]:
    task_id = task["id"]
    task_dir = results_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)

    task_str = f"{task['ques']} on {task['web']}"
    start_dt = datetime.now()
    started_at = time.time()

    profiler = TaskProfiler(task_id=task_id, task_dir=task_dir)
    loop = LoopDetector(consec_abort=stuck_consec)

    log.info(f"[{task_id}] starting · domain={DomainRateLimiter.domain_of(task['web'])}")

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
    cost_totals: dict[str, Any] = {}
    llm_time_s = 0.0  # accumulated LLM-call wall time, populated by the wrapper

    # Pre-declare so the finally block can clean up even if the try body errors early
    _bu_logger: Optional[logging.Logger] = None
    _task_handler: Optional[logging.FileHandler] = None

    try:
        if not NEW_API:
            raise RuntimeError("browser-use 0.12.x API not found; reinstall browser-use==0.12.6")

        profile = _stealth.build_browser_profile(headless=True)
        session = BrowserSession(browser_profile=profile)
        await session.start()

        # Initial captcha check after the agent's first navigation will happen
        # in the on_step callback; no warm-up — we don't pretend to be a returning user.

        # LLM-call timer state. Populated by the wrapper we install below;
        # snapshotted per step inside on_step to derive per-step think_s.
        _llm_state = {"total": 0.0, "n_calls": 0}

        # Per-step delta-tracking snapshots, used to derive think/wait/act per step.
        _step_snap = {
            "prev_step_end": started_at,  # wall time of end of previous step (or task start)
            "prev_llm_total": 0.0,
            "prev_wait_total": 0.0,
        }

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

            # Politeness: wait if we've recently hit this domain.
            if url_after:
                try:
                    await rate_limiter.wait_for(url_after, task_id)
                except Exception:
                    pass

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

            # --- Per-step think / wait / act decomposition ---
            now = time.time()
            step_total = max(0.0, now - _step_snap["prev_step_end"])
            cur_llm_total = _llm_state["total"]
            think_s = max(0.0, cur_llm_total - _step_snap["prev_llm_total"])
            cur_wait_total = rate_limiter.wait_total_s.get(task_id, 0.0)
            wait_s = max(0.0, cur_wait_total - _step_snap["prev_wait_total"])
            _step_snap["prev_step_end"] = now
            _step_snap["prev_llm_total"] = cur_llm_total
            _step_snap["prev_wait_total"] = cur_wait_total

            # Record the step with per-phase timing
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
                    step_start=now - step_total,
                    step_end=now,
                    think_s=think_s,
                    wait_s=wait_s,
                )
            except Exception:
                pass

        # LLM-timing wrapper: monkey-patch the most likely entry point names
        # on this task's LLM instance so each call records elapsed time.
        # Per-task patching means concurrent tasks don't double-count.
        # (_llm_state is initialized above so on_step can read it.)
        for method_name in ("ainvoke", "acomplete", "agenerate", "complete", "invoke"):
            orig = getattr(agent_llm, method_name, None)
            if orig is None or not callable(orig):
                continue
            async def _timed(*args, _orig=orig, _state=_llm_state, **kwargs):
                _t = time.monotonic()
                try:
                    return await _orig(*args, **kwargs)
                finally:
                    _state["total"] += time.monotonic() - _t
                    _state["n_calls"] += 1
            setattr(agent_llm, method_name, _timed)

        # Per-task agent.log: pipe browser-use's runtime stdout into a file
        # for this specific task. Independent from the global tee'd log.
        per_task_log_path = task_dir / "agent.log"
        _bu_logger = logging.getLogger("browser_use")
        _task_handler = logging.FileHandler(per_task_log_path, mode="w", encoding="utf-8")
        _task_handler.setLevel(logging.DEBUG)
        _task_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s"))
        _bu_logger.addHandler(_task_handler)

        agent_kwargs: dict[str, Any] = dict(
            task=task_str,
            llm=agent_llm,
            browser=session,
            use_vision=use_vision,
            max_failures=3,
            calculate_cost=True,    # opt-in token/cost tracking
            save_conversation_path=str(task_dir / "conversation"),  # full LLM IO
            include_attributes=[    # richer DOM attribute capture in the agent's text dump
                "title", "type", "name", "role", "aria-label", "aria-describedby",
                "placeholder", "value", "alt", "aria-expanded", "data-testid",
                "data-date-format", "data-state", "id",
            ],
            register_new_step_callback=on_step,
        )
        # GIF only makes sense when screenshots exist (vision-true)
        if use_vision:
            agent_kwargs["generate_gif"] = str(task_dir / "task.gif")

        agent = Agent(**agent_kwargs)

        history = await agent.run(max_steps=max_steps)
        history.save_to_file(task_dir / "history.json")
        num_steps = len(getattr(history, "history", []) or [])
        final_answer = history.final_result() or "<NO FINAL ANSWER>"
        llm_time_s = _llm_state["total"]

        # Pull token + cost totals from browser-use's token-cost service.
        # Field names vary between minor releases, so probe defensively.
        cost_totals: dict[str, Any] = {}
        try:
            tcs = getattr(agent, "token_cost_service", None)
            if tcs is not None:
                for getter in ("get_totals", "totals", "get_total_cost"):
                    fn = getattr(tcs, getter, None)
                    if fn is None: continue
                    v = fn() if callable(fn) else fn
                    if v is not None:
                        cost_totals = v if isinstance(v, dict) else {"raw": str(v)}
                        break
        except Exception as e:
            cost_totals = {"_error": str(e)}

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
        # Detach + close the per-task log handler so it doesn't leak into other tasks
        try:
            if _bu_logger is not None and _task_handler is not None:
                _bu_logger.removeHandler(_task_handler)
                _task_handler.close()
        except Exception:
            pass

    end_dt = datetime.now()
    duration = (end_dt - start_dt).total_seconds()

    rl_stats = rate_limiter.stats_for(task_id)
    wait_time_s = rl_stats["wait_time_s"]
    n_rate_limit_waits = rl_stats["n_rate_limit_waits"]
    # Browser-action / DOM / screenshot time isn't separately measurable, so
    # we report it as the residual: total - LLM - wait.
    other_time_s = max(0.0, duration - llm_time_s - wait_time_s)

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
        "loop_summary": loop.summary(),
        "browser_use_version": _bu_version(),
        "cost_totals": cost_totals,
        # politeness + timing breakdown
        "wait_time_s": wait_time_s,
        "n_rate_limit_waits": n_rate_limit_waits,
        "llm_time_s": llm_time_s,
        "browser_time_s": other_time_s,
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
    # Interleave by site so concurrent slots can run on different domains
    # without all stalling on the same per-domain rate-limit window.
    tasks = interleave_by_site(tasks)

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
        "config": {
            "use_vision": args.use_vision,
            "max_steps": args.max_steps,
            "max_concurrent": args.max_concurrent,
            "wallclock_cap_s": args.wallclock_cap_s,
            "stuck_consec": args.stuck_consec,
            "rate_limit_s": args.rate_limit_s,
            "model_provider": args.model_provider,
            "bedrock_model_id": os.getenv("BEDROCK_MODEL_ID"),
            "headless": True,
            "stealth": False,
        },
        "tasks_file": str(args.tasks),
        "tasks_file_hash": file_hash(Path(args.tasks)),
        "task_order": "interleave_by_site",
        "git_commit": git_commit(),
    }
    (results_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2))

    agent_llm = build_agent_llm(args.model_provider)
    eval_llm = build_eval_llm(args.model_provider)
    rate_limiter = DomainRateLimiter(min_interval_s=args.rate_limit_s)
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
                rate_limiter=rate_limiter,
            )
            done_count += 1
            log.info(f"[{t['id']}] done outcome={res['success']} steps={res['num_steps']} "
                     f"dur={res['duration_seconds']:.0f}s  wait={res['wait_time_s']:.0f}s  "
                     f"llm={res['llm_time_s']:.0f}s  [{done_count + skip_count}/{len(tasks)}]")

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
    ap.add_argument("--rate-limit-s", type=float, default=DEFAULT_RATE_LIMIT_S,
                    help="min seconds between requests to the same domain (politeness)")
    ap.add_argument("--tasks", default="data/WebVoyager_data.jsonl")
    ap.add_argument("--limit", type=int, default=None, help="run only the first N tasks")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
