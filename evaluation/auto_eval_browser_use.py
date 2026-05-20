import base64
import time
from typing import TYPE_CHECKING, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

if TYPE_CHECKING:
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import AzureChatOpenAI

try:
    from langchain_aws import ChatBedrockConverse
    HAS_BEDROCK = True
except ImportError:
    HAS_BEDROCK = False

if TYPE_CHECKING:
    from run_browser_use import EvalResult


class HistoryLike(Protocol):
    def is_done(self) -> bool:
        ...

    def final_result(self) -> str | None:
        ...

    def screenshots(self) -> list[str | None]:
        ...


SYSTEM_PROMPT = """As an evaluator, you will be presented with three primary components to assist you in your role:

1. Web Task Instruction: This is a clear and specific directive provided in natural language, detailing the online activity to be carried out. These requirements may include conducting searches, verifying information, comparing prices, checking availability, or any other action relevant to the specified web service (such as Amazon, Apple, ArXiv, BBC News, Booking etc).

2. Result Screenshots: This is a visual representation of the screen showing the result or intermediate state of performing a web task. It serves as visual proof of the actions taken in response to the instruction, and may not represent everything the agent sees.

3. Result Response: This is a textual response obtained after the execution of the web task. It serves as textual result in response to the instruction.

-- You DO NOT NEED to interact with web pages or perform actions such as booking flights or conducting searches on websites.
-- You SHOULD NOT make assumptions based on information not presented in the screenshot when comparing it to the instructions. If you cannot find any information in the screenshot that matches the instruction, you can believe the information in the response.
-- Your primary responsibility is to conduct a thorough assessment of the web task instruction against the outcome depicted in the screenshot and in the response, evaluating whether the actions taken align with the given instructions.
-- NOTE that the instruction may involve more than one task, for example, locating the garage and summarizing the review. Failing to complete either task, such as not providing a summary, should be considered unsuccessful.
-- NOTE that the screenshot is authentic, but the response provided by LLM is generated at the end of web browsing, and there may be discrepancies between the text and the screenshots.
-- Note the difference: 1) Result response may contradict the screenshot, then the content of the screenshot prevails, 2) The content in the Result response is not mentioned on the screenshot, choose to believe the content.
-- If you are not sure whether you should believe the content in the response, you should choose unknown.

You should elaborate on how you arrived at your final evaluation and then provide a definitive verdict on whether the task has been successfully accomplished, either as 'SUCCESS', 'NOT SUCCESS', or 'UNKNOWN'."""

USER_PROMPT = """TASK: <task>
Result Response: <answer>
<num> screenshot at the end: """


def _resize_screenshot_if_needed(screenshot_b64: str, max_bytes: int = 3_500_000) -> str:
    """Resize a base64-encoded PNG screenshot if it exceeds max_bytes.
    Bedrock has a ~5MB per-image limit; we target 3.5MB to leave headroom.
    Returns base64-encoded JPEG (smaller) if resizing was needed, otherwise original."""
    raw = base64.b64decode(screenshot_b64)
    if len(raw) <= max_bytes:
        return screenshot_b64, "image/png"

    try:
        from io import BytesIO
        from PIL import Image

        img = Image.open(BytesIO(raw))
        # Resize to 50% if too large
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode(), "image/jpeg"
    except ImportError:
        # PIL not available, just return original and hope for the best
        return screenshot_b64, "image/png"


async def auto_eval_by_gpt4o(
    history: HistoryLike,
    task: str,
    openai_client,
) -> tuple["EvalResult", str]:
    if not history.is_done():
        return "failed", ""

    answer = history.final_result()
    if answer is None:
        return "failed", ""

    screenshots = history.screenshots()[-4:]

    # Skip eval if no screenshots available
    if not screenshots:
        return "unknown", "No screenshots available for evaluation"

    # Bedrock Converse needs image_url with data URI (same as OpenAI format)
    # but may fail on very large images, so we resize if needed
    is_bedrock = HAS_BEDROCK and isinstance(openai_client, ChatBedrockConverse)

    screenshot_content = []
    for screenshot in screenshots:
        if not screenshot:
            continue
        if is_bedrock:
            resized, media_type = _resize_screenshot_if_needed(screenshot)
            screenshot_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{resized}"},
            })
        else:
            screenshot_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{screenshot}"},
            })

    if not screenshot_content:
        return "unknown", "All screenshots were empty"

    # Prepare messages
    user_prompt_tmp = USER_PROMPT.replace("<task>", task)
    user_prompt_tmp = user_prompt_tmp.replace("<answer>", answer)
    user_prompt_tmp = user_prompt_tmp.replace("<num>", str(len(screenshot_content)))

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {"type": "text", "text": user_prompt_tmp},
                *screenshot_content,
                {"type": "text", "text": "Your verdict:\n"},
            ]
        ),
    ]

    max_retries = 5
    response = None
    for attempt in range(max_retries):
        try:
            response = await openai_client.ainvoke(messages)
            break
        except Exception as e:
            error_str = str(e)
            print(f"Eval attempt {attempt + 1}/{max_retries} failed: {error_str[:200]}")

            if attempt == max_retries - 1:
                return "unknown", f"Eval failed after {max_retries} retries: {error_str[:500]}"

            # Non-retryable errors — bail immediately
            if "Could not process image" in error_str:
                return "unknown", f"Bedrock image processing error: {error_str[:500]}"
            if type(e).__name__ == "InvalidRequestError":
                return "unknown", f"Invalid request: {error_str[:500]}"
            if "ValidationException" in error_str:
                return "unknown", f"Validation error: {error_str[:500]}"

            # Retryable errors
            if type(e).__name__ == "RateLimitError" or "ThrottlingException" in error_str:
                time.sleep(10 + attempt * 5)  # backoff
            elif type(e).__name__ == "APIError":
                time.sleep(15)
            else:
                time.sleep(5 + attempt * 3)

    if response is None:
        return "unknown", "No response from eval LLM"

    gpt_4v_res = str(response.content)

    if gpt_4v_res is None:
        return "unknown", ""
    elif "NOT SUCCESS" in gpt_4v_res:
        auto_eval_res = "failed"
    elif "SUCCESS" in gpt_4v_res:
        auto_eval_res = "success"
    elif "UNKNOWN" in gpt_4v_res:
        auto_eval_res = "unknown"
    else:
        auto_eval_res = "failed"

    return auto_eval_res, gpt_4v_res
