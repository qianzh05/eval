import argparse
import asyncio
import json
import logging
import os
import random
import re
import shutil
from asyncio import Semaphore
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Literal, Set, TypedDict

from browser_use import Agent, Browser, BrowserConfig
from browser_use.browser.context import BrowserContextConfig
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_openai import AzureChatOpenAI

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False
from pydantic import BaseModel, Field, SecretStr

# Bedrock imports
try:
    from langchain_aws import ChatBedrockConverse
    HAS_BEDROCK = True
except ImportError:
    HAS_BEDROCK = False

from evaluation.auto_eval_browser_use import auto_eval_by_gpt4o

load_dotenv()


def shift_past_dates(text: str) -> str:
    """Shift past dates in task text to equivalent future dates.

    Replaces years 2023/2024/2025 with a future year that preserves the
    day-of-week alignment where possible. Also handles date formats like
    20/12/2024 and standalone year references in booking/flight contexts.
    """
    now = datetime.now()
    current_year = now.year

    def replace_year(match: re.Match) -> str:
        full = match.group(0)
        year_str = match.group("year")
        year = int(year_str)
        if year < current_year:
            # Shift forward by the smallest multiple of years to make it future
            new_year = current_year + 1
            return full.replace(year_str, str(new_year))
        return full

    # Match patterns: "January 10, 2025", "February 28, 2025", "March 2025"
    text = re.sub(
        r'(?P<prefix>(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s*)(?P<year>202[345])',
        replace_year,
        text,
        flags=re.IGNORECASE,
    )
    # Match dd/mm/yyyy format like 20/12/2024
    text = re.sub(
        r'(?P<prefix>\d{1,2}/\d{1,2}/)(?P<year>202[345])',
        replace_year,
        text,
        flags=re.IGNORECASE,
    )
    # Match standalone year references like "in 2024", "for 2024"
    # but NOT season formats like "2024-25" where both parts are year fragments
    text = re.sub(
        r'(?P<prefix>\b)(?P<year>202[345])(?!-\d{2}\b)',
        replace_year,
        text,
    )
    return text


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
    """Clean up webdriver cache directories."""
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
    """Create task result object."""
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


def save_results(
    task_result: TaskResult,
    task_dir: Path,
) -> None:
    """Save results to files."""
    # Save interaction messages

    with open(task_dir / "task_result.json", "w") as f:
        json.dump(task_result.model_dump(), f, indent=2, default=str)


def print_task_progress(
    task_id: str, steps: int, success: EvalResult, stats: RunStats
) -> None:
    """Print concise task progress."""
    status = "✓" if success == "success" else "✗" if success == "failed" else "?"
    print(
        f"Task {task_id} [{stats.current_task}/{stats.total_tasks}] "
        f"Steps: {steps} Status: {status} Score: {stats.get_success_rate()}"
    )


def save_experiment_results(experiment_results: ExperimentResults, results_dir: Path) -> None:
    """Save experiment results to file."""
    with open(results_dir / "experiment_results.json", "w") as f:
        json.dump(experiment_results.model_dump(), f, indent=2, default=str)


@dataclass
class LLMModel:
    model: AzureChatOpenAI
    token_limit: int


def get_llm_model_generator(
    model_provider: str,
) -> Generator[AzureChatOpenAI | ChatAnthropic, None, None]:
    """Generator that creates fresh model instances each time"""
    while True:
        # Force reload environment variables
        load_dotenv(override=True)

        if model_provider == "anthropic":
            # Create fresh instances each time, reading current env vars
            yield ChatAnthropic(
                model_name="claude-3-5-sonnet-20240620",
                timeout=25,
                stop=None,
                temperature=0.0,
            )

        elif model_provider == "azure":
            # Create fresh instances each time, reading current env vars
            west_eu = LLMModel(
                model=AzureChatOpenAI(
                    model="gpt-4o",
                    api_version="2024-10-21",
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT_WEST_EU", ""),
                    api_key=SecretStr(os.getenv("AZURE_OPENAI_API_KEY_WEST_EU", "")),
                ),
                token_limit=900,
            )
            east_us = LLMModel(
                model=AzureChatOpenAI(
                    model="gpt-4o",
                    api_version="2024-10-21",
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT_EAST_US", ""),
                    api_key=SecretStr(os.getenv("AZURE_OPENAI_API_KEY_EAST_US", "")),
                ),
                token_limit=450,
            )
            east_us_2 = LLMModel(
                model=AzureChatOpenAI(
                    model="gpt-4o",
                    api_version="2024-10-21",
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT_EAST_US_2", ""),
                    api_key=SecretStr(os.getenv("AZURE_OPENAI_API_KEY_EAST_US_2", "")),
                ),
                token_limit=450,
            )
            west_us = LLMModel(
                model=AzureChatOpenAI(
                    model="gpt-4o",
                    api_version="2024-10-21",
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT_WEST_US", ""),
                    api_key=SecretStr(os.getenv("AZURE_OPENAI_API_KEY_WEST_US", "")),
                ),
                token_limit=450,
            )

            # Yield fresh instances in the same pattern
            yield west_eu.model  # First 900
            yield west_eu.model  # Second 900
            yield east_us.model  # 450
            yield east_us_2.model  # 450
            yield west_us.model  # 450
        elif model_provider.startswith("google/"):
            if not HAS_GOOGLE:
                raise ImportError("langchain-google-genai is required for Google models. Install: pip install langchain-google-genai")
            model_name = model_provider.split("/", 1)[1]
            yield ChatGoogleGenerativeAI(model=model_name)
        elif model_provider == "bedrock":
            if not HAS_BEDROCK:
                raise ImportError("langchain-aws is required for Bedrock. Install: pip install langchain-aws")
            model_id = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6")
            region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            yield ChatBedrockConverse(
                model=model_id,
                region_name=region,
                temperature=0.0,
                max_tokens=4096,
            )
        else:
            raise ValueError(f"Invalid model provider: {model_provider}")


async def process_single_task(
    task: TaskData,
    client: AzureChatOpenAI | ChatAnthropic,
    stats: RunStats,
    results_dir: Path,
    experiment_results: ExperimentResults,
    browser: Browser,
    use_vision: bool = True,
) -> None:
    """Process a single task asynchronously."""
    task_str = f"{task['ques']} on {task['web']}"
    start_time = datetime.now()
    task_dir = results_dir / f"{task['id']}"
    task_dir.mkdir(exist_ok=True)

    try:
        if not (task_dir / "task_result.json").exists():
            logging.getLogger("browser_use").setLevel(logging.INFO)

            agent = Agent(
                task=task_str,
                llm=client,
                browser=browser,
                validate_output=True,
                generate_gif=False,
                use_vision=use_vision,
            )

            history = await agent.run(max_steps=30)
            history.save_to_file(task_dir / "history.json")

            eval_result, gpt_4v_res = await auto_eval_by_gpt4o(
                task=task_str,
                openai_client=client,
                history=history,
            )

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

        # Update experiment results
        experiment_results.all_tasks.append(task_result)
        experiment_results.total_tasks += 1
        experiment_results.total_success += int(eval_result == "success")
        experiment_results.total_failed += int(eval_result == "failed")
        experiment_results.total_unknown += int(eval_result == "unknown")
        # save curent stats to file
        print(f"Saving stats to file {stats.current_task} {stats.get_success_rate()}")
        # with open(file="results/examples-browser-use/aaa_stats.txt", mode="a") as f:
        #     # in one line
        #     f.write(f"{stats.current_task}\n")
        #     f.write(f"{stats.get_success_rate()}\n")

    except Exception as e:
        logging.error(f"Error processing task {task['id']}: {str(e)}")
        stats.update(task["id"], "failed")  # Mark as failed instead of crashing
        return

    finally:
        await browser.close()


async def main(max_concurrent_tasks: int, model_provider: str, use_vision: bool = True) -> None:
    try:
        # Setup
        cleanup_webdriver_cache()
        semaphore = Semaphore(max_concurrent_tasks)

        # Load tasks
        tasks: List[TaskData] = []
        with open("data/WebVoyager_data.jsonl", "r") as f:
            for line in f:
                tasks.append(json.loads(line))

        # randomize the order of tasks
        random.seed(42)
        random.shuffle(tasks)

        # Initialize

        experiment_results = ExperimentResults()
        stats = RunStats(total_tasks=len(tasks))
        vision_tag = "vision-true" if use_vision else "vision-false"
        results_dir = Path(f"results/examples-browser-use-{vision_tag}")
        results_dir.mkdir(parents=True, exist_ok=True)

        # Process tasks concurrently with semaphore
        async def process_with_semaphore(
            task: TaskData, client: AzureChatOpenAI | ChatAnthropic
        ) -> None:
            async with semaphore:
                print(f"\n=== Now at task {task['id']} ===")

                # Create browser instance inside the semaphore block
                browser = Browser(
                    config=BrowserConfig(
                        headless=True,
                        disable_security=True,
                        new_context_config=BrowserContextConfig(
                            disable_security=True,
                            wait_for_network_idle_page_load_time=5,
                            maximum_wait_page_load_time=20,
                            # no_viewport=True,
                            browser_window_size={
                                "width": 1280,
                                "height": 1100,
                            },
                            # trace_path=str(results_dir / f"{task['id']}"),
                        ),
                    )
                )

                await process_single_task(
                    task,
                    client,
                    stats,
                    results_dir,
                    experiment_results,
                    browser,  # Pass browser instance
                    use_vision=use_vision,
                )
                stats.current_task += 1

                # Add this to ensure browser is always closed
                try:
                    await browser.close()
                except Exception as e:
                    logging.error(f"Error closing browser: {e}")

                print(f"Current task: {stats.current_task}")
                print(f"Total tasks: {stats.total_tasks}")
                print(f"Success rate: {stats.get_success_rate()}")
                # if stats.current_task % max_concurrent_tasks == 0:
                stats.print_periodic_summary()
                save_experiment_results(experiment_results, results_dir)

        # Create and run all tasks
        all_tasks = []
        for i, task in enumerate(tasks):
            model = next(get_llm_model_generator(model_provider))
            all_tasks.append(process_with_semaphore(task, model))

        # Add timeout and better error handling
        await asyncio.gather(*all_tasks, return_exceptions=True)
    except Exception as e:
        logging.error(f"Main loop error: {e}")
    finally:
        # Cleanup code here
        logging.info("Shutting down...")
        stats.print_periodic_summary()


if __name__ == "__main__":
    try:
        parser = argparse.ArgumentParser(
            description="Run browser tasks with concurrent execution"
        )
        parser.add_argument(
            "--max-concurrent",
            type=int,
            default=3,
            help="Maximum number of concurrent tasks (default: 3)",
        )
        parser.add_argument(
            "--model-provider",
            type=str,
            default="azure",
            help="Model provider (default: azure)",
            choices=[
                "azure",
                "anthropic",
                "bedrock",
                "google/gemini-1.5-flash",
                "google/gemini-1.5-flash-8b",
                "google/gemini-1.5-pro",
            ],
        )
        parser.add_argument(
            "--use-vision",
            type=str,
            default="true",
            choices=["true", "false"],
            help="Whether to send screenshots to the LLM (default: true)",
        )
        args = parser.parse_args()

        use_vision = args.use_vision == "true"
        logging.info(f"Running with {args.max_concurrent} concurrent tasks, use_vision={use_vision}")

        asyncio.run(main(args.max_concurrent, args.model_provider, use_vision=use_vision))
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, shutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.exception("Fatal error occurred")
