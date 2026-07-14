"""Pilot runner for the screenshot task suite (generation 2).

Runs the 10 tasks in tasks/pilot_tasks.json on PRISTINE browser-use 0.13.2
(.venv-pilot - see build_pilot_env.sh) in one of three modes:

  on   : use_vision=True    (screenshot attached every step)
  off  : use_vision=False   (never attached)
  auto : use_vision='auto'  (screenshot tool registered; model decides)

Scoring is strictly post-hoc via score_pilot.py (deterministic checker; no
LLM judge anywhere - use_judge=False). Each mode is its own process:

  AWS_PROFILE=prof .venv-pilot/bin/python screenshot_task_suite/run_pilot.py \
      --mode off --repeats 3 --concurrency 3 --run-tag pilot-2026-07-XX

  --dry-run validates the environment and prints the plan; launches nothing.

Output: screenshot_task_suite/results/<run-tag>/<mode>/<task_id>/rep<k>/
        {task_result.json, history.json, steps.jsonl, conversation/, screenshots/}

Safety hard rules honored here: banned-site guard on start_urls; 30s per-URL
polite rate limiter (transition-only); no logins, no purchases; nothing is
scored until test_checker.py passes 50/50.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

SUITE = Path(__file__).resolve().parent
REPO_ROOT = SUITE.parent
TASKS_FILE = SUITE / "tasks" / "pilot_tasks.json"

# --- mode handling (the historical trap: 'auto' silently coerced to False) --
MODE_MAP = {"on": True, "off": False, "auto": "auto"}


def _early_arg(name: str, default: str) -> str:
    for i, a in enumerate(sys.argv):
        if a == f"--{name}" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


MODE = _early_arg("mode", "").strip().lower()
assert MODE in MODE_MAP, f"--mode must be one of {list(MODE_MAP)} (got {MODE!r})"
USE_VISION = MODE_MAP[MODE]
# Identity assertions: exactly True / False / the exact lowercase string 'auto'.
assert USE_VISION is True or USE_VISION is False or USE_VISION == "auto"

# --- environment BEFORE importing browser_use ------------------------------
# The pilot must NEVER run the vision-only DOM suppression.
_had_vo = os.environ.pop("BROWSER_USE_VISION_ONLY", None)
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("AWS_PROFILE", "prof")
os.environ.setdefault("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-west-2"))
os.environ.setdefault("AWS_DEFAULT_REGION", os.environ["AWS_REGION"])
_loopback = "localhost,127.0.0.1,::1"
for _k in ("NO_PROXY", "no_proxy"):
    _cur = os.environ.get(_k, "")
    os.environ[_k] = _loopback if not _cur else f"{_cur},{_loopback}"

sys.path.insert(0, str(REPO_ROOT))  # eval_utils is a repo-root package

from browser_use import Agent  # noqa: E402
from browser_use.browser.profile import BrowserProfile  # noqa: E402
from browser_use.browser.session import BrowserSession  # noqa: E402
from browser_use.llm import ChatAnthropicBedrock  # noqa: E402

from eval_utils.rate_limiter import DomainRateLimiter  # noqa: E402

BANNED_HOST_PARTS = ("google.", "booking.com", "allrecipes.com",
                     "dictionary.cambridge.org", "espn.com", "bbc.com")
INPUT_PRICE_PER_M = {"us.anthropic.claude-sonnet-4-6": 3.00, "anthropic.claude-sonnet-4-6": 3.00}
OUTPUT_PRICE_PER_M = {"us.anthropic.claude-sonnet-4-6": 15.00, "anthropic.claude-sonnet-4-6": 15.00}

RATE_LIMITER = DomainRateLimiter(min_interval_s=30.0)


# --- guards -----------------------------------------------------------------

def assert_pristine_prompt() -> str:
    """Refuse to run if the installed system prompt carries vision_only.patch.

    The patch's system_prompt.md hunks are UNCONDITIONAL (not env-gated), so a
    wheel built from the patched checkout poisons every mode. We extract the
    patch's added lines and require that none appear in the installed prompt.
    """
    import browser_use.agent.system_prompts as sp
    prompt_path = Path(sp.__file__).parent / "system_prompt.md"
    prompt_text = prompt_path.read_text()

    patch_file = REPO_ROOT / "vision_only.patch"
    if not patch_file.exists():
        raise SystemExit(f"FATAL: {patch_file} not found - cannot verify the "
                         "installed prompt is pristine; refusing to run.")
    added: list[str] = []
    if patch_file.exists():
        in_prompt_hunk = False
        for line in patch_file.read_text().splitlines():
            if line.startswith("+++ "):
                in_prompt_hunk = "system_prompt.md" in line
            elif in_prompt_hunk and line.startswith("+") and not line.startswith("+++"):
                s = line[1:].strip()
                if len(s) > 40:  # only distinctive full sentences
                    added.append(s)
    offenders = [s for s in added if s in prompt_text]
    if offenders:
        raise SystemExit(
            "FATAL: installed browser-use system prompt contains vision_only.patch "
            f"text (e.g. {offenders[0][:80]!r}).\nThis env is the PATCHED wheel - "
            "build the pristine one first: bash screenshot_task_suite/build_pilot_env.sh "
            "and run with .venv-pilot/bin/python."
        )
    return str(prompt_path)


def assert_banned_guard(tasks: list[dict]) -> None:
    for t in tasks:
        host = (urlparse(t["start_url"]).hostname or "").lower()
        if any(b in host for b in BANNED_HOST_PARTS):
            raise SystemExit(f"FATAL: banned site in start_url of {t['id']}: {host}")


def _find_chrome_for_testing() -> Optional[str]:
    env = os.environ.get("BROWSER_USE_EXECUTABLE_PATH")
    if env and Path(env).exists():
        return env
    import glob as _glob
    cands = sorted(_glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/"
        "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")))
    return cands[-1] if cands else None


CHROME_EXE = _find_chrome_for_testing()


def load_tasks() -> list[dict]:
    data = json.loads(TASKS_FILE.read_text())
    tasks = data["tasks"]  # ONLY the active gen-2 tasks; never checker.TASKS
    assert len(tasks) == 10, f"expected 10 pilot tasks, got {len(tasks)}"
    return tasks


def build_llm() -> Any:
    return ChatAnthropicBedrock(
        model=os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        aws_region=os.environ["AWS_REGION"], temperature=0.0, max_tokens=4096)


def _extract_usage(result: Any) -> tuple[int, int]:
    cands = []
    for attr in ("usage_metadata", "usage", "response_metadata"):
        v = getattr(result, attr, None)
        if v is not None:
            cands.append(v)
            if isinstance(v, dict):
                for sub in ("token_usage", "usage"):
                    if sub in v:
                        cands.append(v[sub])
    for c in cands:
        if not c:
            continue
        if hasattr(c, "model_dump"):
            c = c.model_dump()
        if isinstance(c, dict):
            in_t = c.get("input_tokens") or c.get("prompt_tokens") or c.get("inputTokens") or 0
            out_t = c.get("output_tokens") or c.get("completion_tokens") or c.get("outputTokens") or 0
            if in_t or out_t:
                return int(in_t), int(out_t)
    return 0, 0


def _action_items(model_output: Any) -> list[dict]:
    items: list[dict] = []
    for a in (getattr(model_output, "action", None) or []):
        try:
            d = a.model_dump(exclude_none=True)
        except Exception:
            d = dict(getattr(a, "__dict__", {}))
        for name, params in d.items():
            items.append({"name": name, "params": params})
    return items


async def run_one(task: dict, rep: int, out_root: Path, max_steps: int,
                  wallclock_s: int) -> dict:
    task_id = task["id"]
    task_dir = out_root / MODE / task_id / f"rep{rep}"
    task_dir.mkdir(parents=True, exist_ok=True)
    step_log = (task_dir / "steps.jsonl").open("w", encoding="utf-8")

    usage = {"in": 0, "out": 0, "calls": 0}
    n_screenshot_requests = 0
    screenshot_request_steps: list[int] = []
    urls_seen: list[str] = []
    prev_url: Optional[str] = None

    llm = None
    session = None

    limiter_errors: list[str] = []

    async def on_step(browser_state: Any, model_output: Any, step_no: int) -> None:
        nonlocal n_screenshot_requests, prev_url
        url = getattr(browser_state, "url", None)
        if url:
            urls_seen.append(url)
            # transition-only, keyed like the v2 runner: fragment-only changes
            # share a page_key and must NOT trigger a wait.
            if prev_url is None or (DomainRateLimiter.page_key(url)
                                    != DomainRateLimiter.page_key(prev_url)):
                try:
                    await RATE_LIMITER.wait_for(url, f"{task_id}:rep{rep}")
                except Exception as le:  # never swallow silently: record once
                    if not limiter_errors:
                        limiter_errors.append(f"{type(le).__name__}: {le}")
                        print(f"[{task_id} rep{rep}] RATE LIMITER ERROR: {le}", flush=True)
            prev_url = url
        acts = _action_items(model_output)
        if any(it["name"] == "screenshot" for it in acts):
            n_screenshot_requests += 1
            screenshot_request_steps.append(step_no)
        step_log.write(json.dumps({
            "step": step_no, "url": url,
            "eval_prev": getattr(model_output, "evaluation_previous_goal", "") or "",
            "next_goal": getattr(model_output, "next_goal", "") or "",
            "actions": acts, "ts": time.time(),
        }, default=str) + "\n")
        step_log.flush()

    started = time.time()
    result: dict = {
        "task_id": task_id, "rep": rep, "mode": MODE,
        "use_vision": repr(USE_VISION), "category": task.get("category"),
        "site": task.get("site"), "prompt": task["prompt"],
        "start_url": task["start_url"], "start_time": str(datetime.now()),
        "success": None,  # scored post-hoc by score_pilot.py
    }
    try:
        llm = build_llm()
        _orig = llm.ainvoke

        async def _counted(*a, **k):
            usage["calls"] += 1
            r = await _orig(*a, **k)
            it, ot = _extract_usage(r)
            usage["in"] += it
            usage["out"] += ot
            return r
        llm.ainvoke = _counted  # ChatAnthropicBedrock is a dataclass; attr set works

        _kw = dict(headless=True, viewport={"width": 1280, "height": 1024})
        if CHROME_EXE:
            _kw["executable_path"] = CHROME_EXE
        session = BrowserSession(browser_profile=BrowserProfile(**_kw))

        # politeness for the very first fetch too (initial_actions navigation
        # happens outside the step callback; arxiv.org is shared by two tasks)
        await RATE_LIMITER.wait_for(task["start_url"], f"{task_id}:rep{rep}")

        await session.start()
        agent = Agent(
            task=task["prompt"],  # verbatim; start page via initial_actions
            llm=llm,
            browser=session,
            use_vision=USE_VISION,
            use_judge=False,  # deterministic checks only; no LLM judge anywhere
            initial_actions=[{"navigate": {"url": task["start_url"], "new_tab": False}}],
            register_new_step_callback=on_step,
            save_conversation_path=str(task_dir / "conversation"),
        )
        history = await asyncio.wait_for(agent.run(max_steps=max_steps),
                                         timeout=wallclock_s)
        try:
            history.save_to_file(task_dir / "history.json")
        except Exception:
            pass
        try:  # persist screenshots out of the purgeable temp dir
            import shutil as _sh
            _hj = json.loads((task_dir / "history.json").read_text())
            _sd = task_dir / "screenshots"; _sd.mkdir(exist_ok=True)
            for _s in _hj.get("history", []):
                _sp = (_s.get("state") or {}).get("screenshot_path")
                if _sp and Path(_sp).exists():
                    _sh.copy2(_sp, _sd / Path(_sp).name)
        except Exception:
            pass
        hist_urls = [u for u in (history.urls() or []) if u]
        result.update({
            "num_steps": len(getattr(history, "history", []) or []),
            "final_answer": history.final_result(),
            "is_done": bool(history.is_done()),
            "is_successful_flag": history.is_successful(),
            "history_urls": hist_urls,
        })
        try:  # native cache-aware token accounting (tokens tracked regardless)
            u = history.usage
            result["usage_native"] = u.model_dump() if hasattr(u, "model_dump") else str(u)
        except Exception:
            pass
    except asyncio.TimeoutError:
        result["error"] = f"wallclock_cap_{wallclock_s}s"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        result["traceback"] = traceback.format_exc()[-2000:]

    mid = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    result.update({
        "end_time": str(datetime.now()),
        "duration_seconds": round(time.time() - started, 1),
        "step_urls": urls_seen,
        "rate_limiter_errors": limiter_errors,
        "rate_limiter_stats": (lambda: (RATE_LIMITER.stats_for(f"{task_id}:rep{rep}")
                                        if hasattr(RATE_LIMITER, "stats_for") else {}))(),
        "screenshot_requests": n_screenshot_requests,
        "screenshot_request_steps": screenshot_request_steps,
        "cost_totals": {
            "input_tokens": usage["in"], "output_tokens": usage["out"],
            "n_llm_calls": usage["calls"], "model_id": mid,
            "cost_usd": usage["in"] / 1e6 * INPUT_PRICE_PER_M.get(mid, 3.0)
                        + usage["out"] / 1e6 * OUTPUT_PRICE_PER_M.get(mid, 15.0),
            "note": "static-price estimate, cache-inclusive; see usage_native for cached split",
        },
    })
    step_log.close()
    (task_dir / "task_result.json").write_text(json.dumps(result, indent=2, default=str))
    if session is not None:
        try:
            await asyncio.wait_for(session.kill(), timeout=20)
        except Exception:
            try:
                await asyncio.wait_for(session.stop(), timeout=10)
            except Exception:
                pass
    print(f"[{MODE}][{task_id} rep{rep}] steps={result.get('num_steps')} "
          f"done={result.get('is_done')} shots_req={n_screenshot_requests} "
          f"tok={usage['in']}/{usage['out']} err={str(result.get('error',''))[:60]}",
          flush=True)
    return result


async def dry_run(tasks: list[dict], out_root: Path) -> None:
    import importlib.metadata as md
    checks: list[tuple[str, bool, str]] = []
    v = md.version("browser-use")
    checks.append(("browser-use == 0.13.2", v == "0.13.2", v))
    checks.append(("BROWSER_USE_VISION_ONLY unset (popped if set)", True,
                   f"was set: {_had_vo!r}" if _had_vo else "clean"))
    try:
        p = assert_pristine_prompt()
        checks.append(("system prompt pristine (no vision_only.patch text)", True, p))
    except SystemExit as e:
        checks.append(("system prompt pristine", False, str(e)[:100]))
    checks.append(("Chrome for Testing found", CHROME_EXE is not None, str(CHROME_EXE)))
    checks.append(("10 tasks loaded, banned guard passed", True, TASKS_FILE.name))
    gate = subprocess.run([sys.executable, str(SUITE / "test_checker.py")],
                          capture_output=True, text=True, cwd=str(SUITE))
    tail = (gate.stdout or "").strip().splitlines()[-1:] or [""]
    checks.append(("checker vector gate (test_checker.py)", gate.returncode == 0, tail[0]))
    checks.append(("resolved use_vision", True, f"{MODE} -> {USE_VISION!r}"))
    checks.append(("judge disabled", True, "use_judge=False"))
    try:
        _t = DomainRateLimiter(min_interval_s=1.0)
        _t0 = time.time()
        await _t.wait_for("https://example.com/a", "dryrun")
        await _t.wait_for("https://example.com/a", "dryrun")
        _elapsed = time.time() - _t0
        _frag_ok = (DomainRateLimiter.page_key("https://x.y/p")
                    == DomainRateLimiter.page_key("https://x.y/p#frag"))
        checks.append(("rate limiter live (2nd same-URL call waits)",
                       _elapsed >= 0.9 and _frag_ok,
                       f"elapsed={_elapsed:.2f}s fragment-invariant={_frag_ok}; run uses 30s"))
    except Exception as _e:
        checks.append(("rate limiter live", False, f"{type(_e).__name__}: {_e}"))
    ok = all(c[1] for c in checks)
    print(f"\n=== DRY RUN ({MODE}) -> {out_root/MODE} ===")
    for name, passed, info in checks:
        print(f"  [{'ok' if passed else 'FAIL'}] {name}: {info}")
    print(f"  plan: {len(tasks)} tasks x --repeats reps, interleaved by site")
    for t in tasks:
        print(f"    {t['id']:15s} start={t['start_url']}")
    sys.exit(0 if ok else 1)


async def main(args: argparse.Namespace) -> None:
    tasks = load_tasks()
    assert_banned_guard(tasks)
    if args.task_id:
        keep = set(x.strip() for x in args.task_id.split(","))
        tasks = [t for t in tasks if t["id"] in keep]
        assert tasks, f"no tasks match --task-id {args.task_id}"
    if args.limit:
        tasks = tasks[: args.limit]

    assert args.mode == MODE, (
        f"--mode disagreement: early-arg saw {MODE!r}, argparse saw {args.mode!r} "
        "(duplicate --mode flags?)")
    import importlib.metadata as _md
    _v = _md.version("browser-use")
    assert _v == "0.13.2", f"wrong env: browser-use {_v}, need pristine 0.13.2 (.venv-pilot)"

    out_root = SUITE / "results" / args.run_tag
    if args.dry_run:
        await dry_run(tasks, out_root)

    assert_pristine_prompt()

    jobs = [(t, rep) for rep in range(1, args.repeats + 1) for t in tasks]
    by_site: dict[str, list] = {}
    for t, rep in jobs:
        by_site.setdefault(urlparse(t["start_url"]).hostname or "?", []).append((t, rep))
    ordered: list[tuple[dict, int]] = []
    while any(by_site.values()):
        for site in list(by_site):
            if by_site[site]:
                ordered.append(by_site[site].pop(0))

    (out_root / MODE).mkdir(parents=True, exist_ok=True)
    manifest = {
        "started_at": datetime.now().isoformat(), "host": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "browser_use": __import__("importlib.metadata", fromlist=["version"]).version("browser-use"),
        "mode": MODE, "resolved_use_vision": repr(USE_VISION),
        "use_judge": False, "repeats": args.repeats, "max_steps": args.max_steps,
        "wallclock_cap_s": args.wallclock_cap_s, "concurrency": args.concurrency,
        "n_tasks": len(tasks), "n_jobs": len(ordered),
        "task_ids": [t["id"] for t in tasks],
        "task_file_sha256": hashlib.sha256(TASKS_FILE.read_bytes()).hexdigest(),
        "bedrock_model_id": os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
        "vision_only_env_was_set": bool(_had_vo),
        "chrome": CHROME_EXE,
    }
    (out_root / MODE / "run_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"[{MODE}] {len(ordered)} jobs ({len(tasks)} tasks x {args.repeats} reps), "
          f"concurrency={args.concurrency} -> {out_root/MODE}", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    done = 0

    async def run_with_sem(job):
        nonlocal done
        t, rep = job
        async with sem:
            try:
                r = await run_one(t, rep, out_root, args.max_steps, args.wallclock_cap_s)
            except Exception as e:
                r = {"task_id": t["id"], "rep": rep, "mode": MODE, "error": f"outer: {e}"}
            done += 1
            print(f"  [{MODE} {done}/{len(ordered)}] {t['id']} rep{rep}", flush=True)
            return r

    await asyncio.gather(*[run_with_sem(j) for j in ordered], return_exceptions=True)
    print(f"\n=== {MODE} done -> {out_root/MODE} ===\nNext: score_pilot.py --run-tag {args.run_tag}",
          flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", required=True, choices=list(MODE_MAP))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--max-steps", type=int, default=30)
    ap.add_argument("--wallclock-cap-s", type=int, default=900)
    ap.add_argument("--run-tag", default=f"pilot-{datetime.now():%Y-%m-%d}")
    ap.add_argument("--task-id", default="", help="comma-separated subset (smoke test)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true", help="validate env + plan, launch nothing")
    asyncio.run(main(ap.parse_args()))
