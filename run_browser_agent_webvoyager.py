import argparse
import asyncio
import base64
import json
import os
import random
import re
import shutil
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Literal, Set, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Make repo root importable so we can reuse BrowserAgent implementation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.agent import BroswerAgentArgs
from browsergym.experiments import EnvArgs, ExpArgs
from evaluation.auto_eval_browser_use import auto_eval_by_gpt4o


load_dotenv()


class TaskData(TypedDict):
    id: str
    web: str
    ques: str


EvalResult = Literal["success", "failed", "unknown"]


@dataclass
class RunStats:
    total_tasks: int
    current_task: int = 0
    successful_tasks: Set[str] = field(default_factory=set)
    failed_tasks: Set[str] = field(default_factory=set)
    unknown_tasks: Set[str] = field(default_factory=set)

    def update(self, task_id: str, success: EvalResult) -> None:
        if success == "success":
            self.successful_tasks.add(task_id)
        elif success == "failed":
            self.failed_tasks.add(task_id)
        else:
            self.unknown_tasks.add(task_id)

    def get_success_rate(self) -> str:
        if self.current_task == 0:
            return "0/0=0.00"
        return f"{len(self.successful_tasks)}/{self.current_task}={len(self.successful_tasks) / self.current_task:.2f}"

    def print_periodic_summary(self) -> None:
        print("\n=== Task Summary ===")
        print(f"Successful tasks ({len(self.successful_tasks)}): {sorted(list(self.successful_tasks))}")
        print(f"Failed tasks ({len(self.failed_tasks)}): {sorted(list(self.failed_tasks))}")
        print(f"Unknown tasks ({len(self.unknown_tasks)}): {sorted(list(self.unknown_tasks))}")
        print(f"Current success rate: {self.get_success_rate()}")
        print("==================\n")


class TaskResult(BaseModel):
    task_id: str
    web_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    num_steps: int
    success: EvalResult
    task_prompt: str
    final_answer: str
    gpt_4v_res: str


class ExperimentResults(BaseModel):
    total_tasks: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_unknown: int = 0
    all_tasks: List[TaskResult] = Field(default_factory=list)


class BgymHistoryShim:
    """Compatibility shim so we can reuse WebVoyager evaluator unchanged."""

    def __init__(self, screenshots_b64: List[str], final_answer: str, done: bool = True):
        self._screenshots = screenshots_b64
        self._final_answer = final_answer
        self._done = done

    def is_done(self) -> bool:
        return self._done

    def final_result(self) -> str:
        return self._final_answer

    def screenshots(self) -> List[str]:
        return self._screenshots


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run BrowserAgent on WebVoyager tasks with WebVoyager-native evaluation outputs"
    )

    parser.add_argument("--num-tasks", type=int, default=50, help="Number of tasks to run")
    parser.add_argument(
        "--task-id",
        type=str,
        default=None,
        help="Run a single specific WebVoyager task id (overrides --num-tasks)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Deterministic task shuffle seed")
    parser.add_argument("--max-steps", type=int, default=30, help="Max agent steps per task")
    parser.add_argument("--results-subdir", type=str, default="examples-browser-agent-webvoyager")
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip WebVoyager auto-eval and mark task result as unknown (useful for env/debug validation)",
    )

    parser.add_argument("--retry", action="store_true", help="Retry only non-successful existing tasks")
    parser.add_argument("--rerun", action="store_true", help="Rerun all selected tasks")

    # Keep these aligned with BrowserAgent knobs.
    parser.add_argument("--model_name", type=str, default="anthropic.claude-sonnet-4-6")
    parser.add_argument("--visual_effects", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=True)
    parser.add_argument("--use_html", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=False)
    parser.add_argument("--use_axtree", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=True)
    parser.add_argument("--use_screenshot", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=True)
    parser.add_argument("--use_som", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=True)
    parser.add_argument("--mode", type=str, default="bid", choices=["bid", "demo"])
    parser.add_argument("--headless", type=lambda x: x.lower() in ("1", "true", "yes", "y"), default=True)
    parser.add_argument(
        "--use_full_action_history",
        type=lambda x: x.lower() in ("1", "true", "yes", "y"),
        default=True,
    )

    return parser.parse_args()


def _get_eval_llm():
    try:
        from langchain_aws import ChatBedrockConverse
    except ImportError as exc:
        raise ImportError(
            "langchain-aws is required for Bedrock evaluation. Install: pip install langchain-aws"
        ) from exc

    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    return ChatBedrockConverse(model=model_id, region_name=region, temperature=0.0)


def _load_tasks(script_dir: Path, seed: int, num_tasks: int, task_id: str | None) -> List[TaskData]:
    tasks: List[TaskData] = []
    with open(script_dir / "data" / "WebVoyager_data.jsonl", "r") as f:
        for line in f:
            tasks.append(json.loads(line))

    with open(script_dir / "data" / "WebVoyagerImpossibleTasks.json", "r") as f:
        impossible_tasks = set(json.load(f))

    tasks = [task for task in tasks if task["id"] not in impossible_tasks]

    if task_id is not None:
        selected = [task for task in tasks if task["id"] == task_id]
        if not selected:
            raise ValueError(f"Task id not found or filtered as impossible: {task_id}")
        return selected

    random.seed(seed)
    random.shuffle(tasks)

    return tasks[:num_tasks]


def _task_result_exists(task_dir: Path) -> bool:
    return (task_dir / "task_result.json").exists()


def _load_existing_task_result(task_dir: Path) -> TaskResult:
    return TaskResult(**json.load(open(task_dir / "task_result.json", "r")))


def _extract_final_answer(bgym_task_dir: Path) -> str:
    steps_files = sorted(
        bgym_task_dir.glob("steps_info_*.json"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)) if re.search(r"(\d+)", p.stem) else -1,
    )

    send_msg_pattern = re.compile(r"send_msg_to_user\((?P<arg>.*)\)", re.DOTALL)

    for step_file in reversed(steps_files):
        try:
            payload = json.load(open(step_file, "r"))
        except Exception:
            continue

        action = payload.get("action") or ""
        if not isinstance(action, str):
            action = str(action)
        match = send_msg_pattern.search(action)
        if not match:
            continue

        raw_arg = match.group("arg").strip()
        if not raw_arg:
            continue

        # Attempt to decode quoted Python string safely.
        try:
            import ast

            parsed = ast.literal_eval(raw_arg)
            if isinstance(parsed, str) and parsed.strip():
                return parsed.strip()
        except Exception:
            pass

        # Fallback: remove wrapping quotes if present.
        if (raw_arg.startswith("\"") and raw_arg.endswith("\"")) or (
            raw_arg.startswith("'") and raw_arg.endswith("'")
        ):
            return raw_arg[1:-1].strip()
        return raw_arg

    return "<NO FINAL ANSWER>"


def _load_last_screenshots_b64(bgym_task_dir: Path, limit: int = 4) -> List[str]:
    screenshot_files = sorted(
        bgym_task_dir.glob("screenshot_step_*.png"),
        key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)) if re.search(r"(\d+)", p.stem) else -1,
    )

    screenshots_b64: List[str] = []
    for screenshot_file in screenshot_files[-limit:]:
        with open(screenshot_file, "rb") as f:
            screenshots_b64.append(base64.b64encode(f.read()).decode("utf-8"))

    return screenshots_b64


def _create_task_result(
    task: TaskData,
    start_time: datetime,
    eval_result: EvalResult,
    num_steps: int,
    final_answer: str,
    gpt_4v_res: str,
) -> TaskResult:
    end_time = datetime.now()
    return TaskResult(
        task_id=task["id"],
        web_name=task["web"],
        start_time=start_time,
        end_time=end_time,
        duration_seconds=(end_time - start_time).total_seconds(),
        num_steps=num_steps,
        success=eval_result,
        task_prompt=f"{task['ques']} on {task['web']}",
        final_answer=final_answer,
        gpt_4v_res=gpt_4v_res,
    )


def _save_task_result(task_result: TaskResult, task_dir: Path) -> None:
    with open(task_dir / "task_result.json", "w") as f:
        json.dump(task_result.model_dump(), f, indent=2, default=str)


def _save_experiment_results(experiment_results: ExperimentResults, results_dir: Path) -> None:
    with open(results_dir / "experiment_results.json", "w") as f:
        json.dump(experiment_results.model_dump(), f, indent=2, default=str)


def _print_task_progress(task_id: str, steps: int, success: EvalResult, stats: RunStats) -> None:
    status = "✓" if success == "success" else "✗" if success == "failed" else "?"
    print(
        f"Task {task_id} [{stats.current_task}/{stats.total_tasks}] "
        f"Steps: {steps} Status: {status} Score: {stats.get_success_rate()}"
    )


def _run_async_blocking(coro_factory: Callable[[], Any]) -> Any:
    """Run an async coroutine in sync code, even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _thread_runner() -> None:
        try:
            result["value"] = asyncio.run(coro_factory())
        except BaseException as exc:
            error["exc"] = exc

    t = threading.Thread(target=_thread_runner, daemon=True)
    t.start()
    t.join()

    if "exc" in error:
        raise error["exc"]
    return result.get("value")


def _run_single_task(
    task: TaskData,
    args: argparse.Namespace,
    eval_llm,
    stats: RunStats,
    results_dir: Path,
    experiment_results: ExperimentResults,
) -> None:
    task_dir = results_dir / task["id"]
    bgym_task_dir = task_dir / "bgym"
    task_dir.mkdir(parents=True, exist_ok=True)

    if _task_result_exists(task_dir):
        existing = _load_existing_task_result(task_dir)
        if args.rerun:
            pass
        elif args.retry and existing.success == "success":
            stats.update(task["id"], existing.success)
            _print_task_progress(task["id"], existing.num_steps, existing.success, stats)
            experiment_results.all_tasks.append(existing)
            experiment_results.total_tasks += 1
            experiment_results.total_success += int(existing.success == "success")
            experiment_results.total_failed += int(existing.success == "failed")
            experiment_results.total_unknown += int(existing.success == "unknown")
            return
        elif not args.retry:
            stats.update(task["id"], existing.success)
            _print_task_progress(task["id"], existing.num_steps, existing.success, stats)
            experiment_results.all_tasks.append(existing)
            experiment_results.total_tasks += 1
            experiment_results.total_success += int(existing.success == "success")
            experiment_results.total_failed += int(existing.success == "failed")
            experiment_results.total_unknown += int(existing.success == "unknown")
            return

    start_time = datetime.now()
    task_str = f"{task['ques']} on {task['web']}"

    agent_args = BroswerAgentArgs(
        model_name=args.model_name,
        chat_mode=False,
        demo_mode="default" if args.visual_effects else "off",
        use_html=args.use_html,
        use_axtree=args.use_axtree,
        use_screenshot=args.use_screenshot,
        mode=args.mode,
        use_som=args.use_som,
        nav_multipages=False,
        tips_path=None,
        task_type="webvoyager",
        use_full_action_history=args.use_full_action_history,
    )

    env_args = EnvArgs(
        task_name="openended",
        task_seed=None,
        max_steps=args.max_steps,
        headless=args.headless,
        wait_for_user_message=False,
        task_kwargs={"start_url": task["web"], "goal": task["ques"]},
    )

    exp_args = ExpArgs(env_args=env_args, agent_args=agent_args, save_som=args.use_som, save_json=True)
    # BrowserGym's ExpArgs expects a non-existing exp root in this repository version.
    # Clean stale rerun artifacts so prepare() can recreate it deterministically.
    if bgym_task_dir.exists():
        shutil.rmtree(bgym_task_dir)
    exp_args.prepare(str(bgym_task_dir))
    exp_args.run()

    summary_info_path = bgym_task_dir / "summary_info.json"
    summary_info = json.load(open(summary_info_path, "r")) if summary_info_path.exists() else {}
    n_steps = int(summary_info.get("n_steps", 0))
    err_msg = summary_info.get("err_msg")
    stack_trace = summary_info.get("stack_trace")

    final_answer = _extract_final_answer(bgym_task_dir)
    screenshots_b64 = _load_last_screenshots_b64(bgym_task_dir)

    run_failed = bool(err_msg) or bool(stack_trace) or (n_steps == 0 and len(screenshots_b64) == 0)
    if run_failed:
        exp_log_path = bgym_task_dir / "experiment.log"
        fail_reason = err_msg or "BrowserGym run ended with 0 steps"
        if stack_trace:
            fail_reason = f"{fail_reason}\n{stack_trace}"
        print(f"Task {task['id']} BrowserGym failure: {fail_reason}")
        print(f"Inspect log: {exp_log_path}")

    history = BgymHistoryShim(
        screenshots_b64=screenshots_b64,
        final_answer=final_answer,
        done=not run_failed,
    )

    if run_failed:
        eval_result, gpt_4v_res = "failed", f"Runner failure: {err_msg or '0-step BrowserGym run'}"
    elif eval_llm is None:
        eval_result, gpt_4v_res = "unknown", "Evaluation skipped (--skip-eval)"
    else:
        eval_result, gpt_4v_res = _run_async_blocking(
            lambda: auto_eval_by_gpt4o(
                task=task_str,
                openai_client=eval_llm,
                history=history,
            )
        )

    task_result = _create_task_result(
        task=task,
        start_time=start_time,
        eval_result=eval_result,
        num_steps=n_steps,
        final_answer=final_answer,
        gpt_4v_res=gpt_4v_res,
    )
    _save_task_result(task_result, task_dir)

    stats.update(task["id"], eval_result)
    _print_task_progress(task["id"], task_result.num_steps, eval_result, stats)

    experiment_results.all_tasks.append(task_result)
    experiment_results.total_tasks += 1
    experiment_results.total_success += int(eval_result == "success")
    experiment_results.total_failed += int(eval_result == "failed")
    experiment_results.total_unknown += int(eval_result == "unknown")


def main() -> None:
    args = _parse_args()
    script_dir = Path(__file__).resolve().parent

    tasks = _load_tasks(
        script_dir=script_dir,
        seed=args.seed,
        num_tasks=args.num_tasks,
        task_id=args.task_id,
    )
    results_dir = script_dir / "results" / args.results_subdir
    results_dir.mkdir(parents=True, exist_ok=True)

    eval_llm = None if args.skip_eval else _get_eval_llm()
    stats = RunStats(total_tasks=len(tasks))
    experiment_results = ExperimentResults()

    print(f"Running BrowserAgent on {len(tasks)} WebVoyager tasks")
    print(f"Results dir: {results_dir}")

    for task in tasks:
        print(f"\n=== Now at task {task['id']} ===")
        try:
            _run_single_task(
                task=task,
                args=args,
                eval_llm=eval_llm,
                stats=stats,
                results_dir=results_dir,
                experiment_results=experiment_results,
            )
        except Exception as exc:
            print(f"Task {task['id']} failed with exception: {exc}")
            stats.update(task["id"], "failed")

        stats.current_task += 1
        print(f"Current task: {stats.current_task}")
        print(f"Total tasks: {stats.total_tasks}")
        print(f"Success rate: {stats.get_success_rate()}")
        stats.print_periodic_summary()
        _save_experiment_results(experiment_results, results_dir)


if __name__ == "__main__":
    main()
