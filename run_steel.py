import argparse
import asyncio
import json
import logging
import os
import random
import shutil
import signal
from asyncio import Semaphore
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Literal, Set, TypedDict

from browser_use import Agent, BrowserSession
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from evaluation.auto_eval_browser_use import auto_eval_by_gpt4o

load_dotenv()

# Steel imports
try:
    from steel import Steel
except ImportError:
    raise ImportError("Install steel-sdk: pip install steel-sdk")

# Bedrock imports — uses browser_use native if available, falls back to langchain
try:
    from browser_use.llm import ChatAnthropicBedrock
    USE_BROWSER_USE_BEDROCK = True
except ImportError:
    USE_BROWSER_USE_BEDROCK = False

try:
    from langchain_aws import ChatBedrockConverse
    USE_LANGCHAIN_BEDROCK = True
except ImportError:
    USE_LANGCHAIN_BEDROCK = False


def get_eval_llm():
    """Create a langchain-compatible LLM for evaluation (auto_eval_by_gpt4o)."""
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if USE_LANGCHAIN_BEDROCK:
        return ChatBedrockConverse(
            model=model_id,
            region_name=region,
            temperature=0.0,
        )
    else:
        raise ImportError(
            "langchain-aws is required for evaluation. Install: pip install langchain-aws"
        )


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

    def update(self, task_id: str, success: "EvalResult") -> None:
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
        print(
            f"Successful tasks ({len(self.successful_tasks)}): {sorted(list(self.successful_tasks))}"
        )
        print(
            f"Failed tasks ({len(self.failed_tasks)}): {sorted(list(self.failed_tasks))}"
        )
        print(
            f"Unknown tasks ({len(self.unknown_tasks)}): {sorted(list(self.unknown_tasks))}"
        )
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


def cleanup_webdriver_cache() -> None:
    cache_paths = [
        Path.home() / ".wdm",
        Path.home() / ".cache" / "selenium",
        Path.home() / "Library" / "Caches" / "selenium",
    ]
    for path in cache_paths:
        if path.exists():
            print(f"Removing cache directory: {path}")
            shutil.rmtree(path, ignore_errors=True)


def create_task_result(
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


def save_results(task_result: TaskResult, task_dir: Path) -> None:
    with open(task_dir / "task_result.json", "w") as f:
        json.dump(task_result.model_dump(), f, indent=2, default=str)


def print_task_progress(
    task_id: str, steps: int, success: EvalResult, stats: RunStats
) -> None:
    status = "✓" if success == "success" else "✗" if success == "failed" else "?"
    print(
        f"Task {task_id} [{stats.current_task}/{stats.total_tasks}] "
        f"Steps: {steps} Status: {status} Score: {stats.get_success_rate()}"
    )


def save_experiment_results(experiment_results: ExperimentResults, results_dir: Path) -> None:
    with open(results_dir / "experiment_results.json", "w") as f:
        json.dump(experiment_results.model_dump(), f, indent=2, default=str)


def get_bedrock_llm():
    """Create a Bedrock Claude Sonnet 4.6 LLM instance for the agent."""
    model_id = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

    if USE_BROWSER_USE_BEDROCK:
        return ChatAnthropicBedrock(
            model=model_id,
            aws_region=region,
            temperature=0.0,
        )
    elif USE_LANGCHAIN_BEDROCK:
        return ChatBedrockConverse(
            model=model_id,
            region_name=region,
            temperature=0.0,
        )
    else:
        raise ImportError(
            "No Bedrock LLM available. Install either:\n"
            "  pip install 'browser-use[aws]'  (for ChatAnthropicBedrock)\n"
            "  pip install langchain-aws       (for ChatBedrockConverse)"
        )


def create_steel_session(steel_client: Steel) -> tuple[str, str]:
    """Create a Steel browser session and return (cdp_url, session_id)."""
    steel_api_key = os.getenv("STEEL_API_KEY", "")
    session = steel_client.sessions.create()
    cdp_url = f"wss://connect.steel.dev?apiKey={steel_api_key}&sessionId={session.id}"
    print(f"Created Steel session: {session.id}")
    return cdp_url, session.id


def release_steel_session(steel_client: Steel, session_id: str) -> None:
    """Release a Steel browser session."""
    try:
        steel_client.sessions.release(session_id)
        print(f"Released Steel session: {session_id}")
    except Exception as e:
        logging.error(f"Error releasing Steel session {session_id}: {e}")


def release_all_steel_sessions(steel_client: Steel) -> None:
    """Release all active Steel sessions (cleanup on shutdown)."""
    try:
        for s in steel_client.sessions.list():
            try:
                steel_client.sessions.release(s.id)
                print(f"Cleanup: released Steel session {s.id}")
            except Exception:
                pass
    except Exception as e:
        logging.error(f"Error during Steel session cleanup: {e}")


# Per-task timeout: 10 minutes max for agent + eval
TASK_TIMEOUT_SECONDS = 600


async def process_single_task(
    task: TaskData,
    llm,
    stats: RunStats,
    results_dir: Path,
    experiment_results: ExperimentResults,
    steel_client: Steel,
) -> None:
    task_str = f"{task['ques']} on {task['web']}"
    start_time = datetime.now()
    task_dir = results_dir / f"{task['id']}"
    task_dir.mkdir(exist_ok=True)

    steel_session_id = None
    browser = None

    try:
        if not (task_dir / "task_result.json").exists():
            logging.getLogger("browser_use").setLevel(logging.INFO)

            # Create a Steel browser session for this task
            try:
                cdp_url, steel_session_id = create_steel_session(steel_client)
            except Exception as e:
                logging.error(f"Failed to create Steel session for {task['id']}: {e}")
                # Wait before retrying (likely rate limit)
                await asyncio.sleep(30)
                try:
                    cdp_url, steel_session_id = create_steel_session(steel_client)
                except Exception as e2:
                    logging.error(f"Steel session retry failed for {task['id']}: {e2}")
                    stats.update(task["id"], "failed")
                    return

            browser = BrowserSession(
                cdp_url=cdp_url,
                wait_for_network_idle_page_load_time=5,
            )

            agent = Agent(
                task=task_str,
                llm=llm,
                browser_session=browser,
                validate_output=True,
                generate_gif=False,
            )

            # Run agent with timeout
            try:
                history = await asyncio.wait_for(
                    agent.run(max_steps=30),
                    timeout=TASK_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logging.error(f"Task {task['id']} timed out after {TASK_TIMEOUT_SECONDS}s")
                stats.update(task["id"], "failed")
                return

            history.save_to_file(task_dir / "history.json")

            # Eval with a separate timeout
            try:
                eval_llm = get_eval_llm()
                eval_result, gpt_4v_res = await asyncio.wait_for(
                    auto_eval_by_gpt4o(
                        task=task_str,
                        openai_client=eval_llm,
                        history=history,
                    ),
                    timeout=120,  # 2 min max for eval
                )
            except asyncio.TimeoutError:
                logging.error(f"Eval timed out for task {task['id']}")
                eval_result = "unknown"
                gpt_4v_res = "Eval timed out"
            except Exception as e:
                logging.error(f"Eval error for task {task['id']}: {e}")
                eval_result = "unknown"
                gpt_4v_res = f"Eval error: {str(e)[:500]}"

            task_result = create_task_result(
                task,
                start_time,
                eval_result,
                len(history.history),
                history.final_result() or "<NO FINAL ANSWER>",
                gpt_4v_res,
            )
            save_results(task_result, task_dir)
        else:
            task_result = TaskResult(**json.load(open(task_dir / "task_result.json")))
            eval_result = task_result.success

        stats.update(task["id"], eval_result)
        print_task_progress(task["id"], task_result.num_steps, eval_result, stats)

        experiment_results.all_tasks.append(task_result)
        experiment_results.total_tasks += 1
        experiment_results.total_success += int(eval_result == "success")
        experiment_results.total_failed += int(eval_result == "failed")
        experiment_results.total_unknown += int(eval_result == "unknown")

    except Exception as e:
        logging.error(f"Error processing task {task['id']}: {str(e)}")
        stats.update(task["id"], "failed")
        return

    finally:
        # Always clean up browser + Steel session
        if browser:
            try:
                await browser.stop()
            except Exception as e:
                logging.error(f"Error stopping browser for {task['id']}: {e}")
        if steel_session_id:
            release_steel_session(steel_client, steel_session_id)


async def main(max_concurrent_tasks: int, num_tasks: int) -> None:
    steel_client = Steel(steel_api_key=os.getenv("STEEL_API_KEY"))
    stats = None

    try:
        cleanup_webdriver_cache()
        semaphore = Semaphore(max_concurrent_tasks)

        # Load tasks
        tasks: List[TaskData] = []
        with open("data/WebVoyager_data.jsonl", "r") as f:
            for line in f:
                tasks.append(json.loads(line))

        # Remove impossible tasks
        with open("data/WebVoyagerImpossibleTasks.json", "r") as f:
            impossible_tasks = set(json.load(f))
        tasks = [task for task in tasks if task["id"] not in impossible_tasks]

        # Randomize and select num_tasks
        random.seed(42)
        random.shuffle(tasks)
        tasks = tasks[:num_tasks]

        print(f"Running {len(tasks)} tasks with Steel + Bedrock Sonnet 4.6")
        print(f"Max concurrent: {max_concurrent_tasks}")

        experiment_results = ExperimentResults()
        stats = RunStats(total_tasks=len(tasks))
        results_dir = Path("results/steel-bedrock-sonnet-4.6")
        results_dir.mkdir(parents=True, exist_ok=True)

        async def process_with_semaphore(task: TaskData) -> None:
            async with semaphore:
                print(f"\n=== Now at task {task['id']} ===")

                llm = get_bedrock_llm()

                await process_single_task(
                    task,
                    llm,
                    stats,
                    results_dir,
                    experiment_results,
                    steel_client,
                )
                stats.current_task += 1

                print(f"Current task: {stats.current_task}")
                print(f"Total tasks: {stats.total_tasks}")
                print(f"Success rate: {stats.get_success_rate()}")
                stats.print_periodic_summary()
                save_experiment_results(experiment_results, results_dir)

        # Run tasks sequentially when max_concurrent=1 for cleaner execution
        if max_concurrent_tasks == 1:
            for task in tasks:
                print(f"\n=== Now at task {task['id']} ===")
                llm = get_bedrock_llm()
                await process_single_task(
                    task, llm, stats, results_dir, experiment_results, steel_client
                )
                stats.current_task += 1
                print(f"Current task: {stats.current_task}")
                print(f"Total tasks: {stats.total_tasks}")
                print(f"Success rate: {stats.get_success_rate()}")
                stats.print_periodic_summary()
                save_experiment_results(experiment_results, results_dir)
        else:
            all_tasks = [process_with_semaphore(task) for task in tasks]
            results = await asyncio.gather(*all_tasks, return_exceptions=True)
            # Log any exceptions that were returned
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logging.error(f"Task {tasks[i]['id']} raised exception: {result}")

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving current results...")
    except Exception as e:
        logging.error(f"Main loop error: {e}")
    finally:
        print("\nShutting down...")
        if stats:
            stats.print_periodic_summary()
        # Clean up any lingering Steel sessions
        print("Cleaning up Steel sessions...")
        release_all_steel_sessions(steel_client)
        print("Done.")


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Run WebVoyager eval with Steel browser + Bedrock Sonnet 4.6"
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            default=1,  # Default to 1 for hobby plan
            help="Maximum number of concurrent tasks (default: 1)",
        )
        parser.add_argument(
            "--num-tasks",
            type=int,
            default=50,
            help="Number of random tasks to run (default: 50)",
        )
        args = parser.parse_args()

        print(f"Running {args.num_tasks} tasks with max {args.max_concurrent} concurrent")
        asyncio.run(main(args.max_concurrent, args.num_tasks))

    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.exception("Fatal error occurred")
