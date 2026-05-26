import json
import re
from pathlib import Path
from urllib.parse import urlparse

BASE = Path("results/examples-browser-agent-webvoyager")
EXP = json.loads((BASE / "experiment_results.json").read_text())


def normalize_action(action: str) -> str:
    if not isinstance(action, str):
        action = str(action)
    m = re.search(r"```(.*?)```", action, flags=re.DOTALL)
    if m:
        return m.group(1).strip()
    return action.strip()


def parse_expected_domain(task_prompt: str) -> str:
    m = re.search(r"on\s+(https?://[^\s]+)", task_prompt)
    if not m:
        return ""
    url = m.group(1)
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def parse_goto_domain(action: str) -> str:
    m = re.search(r"goto\(['\"](https?://[^'\"]+)['\"]\)", action)
    if not m:
        return ""
    try:
        return urlparse(m.group(1)).netloc.lower()
    except Exception:
        return ""


def classify_task(task: dict) -> dict:
    tid = task["task_id"]
    prompt = task.get("task_prompt", "")
    expected_domain = parse_expected_domain(prompt)
    bgym = BASE / tid / "bgym"

    summary = {}
    sp = bgym / "summary_info.json"
    if sp.exists():
        summary = json.loads(sp.read_text())

    step_files = sorted(
        bgym.glob("steps_info_*.json"),
        key=lambda p: int(re.search(r"(\d+)$", p.stem).group(1)) if re.search(r"(\d+)$", p.stem) else -1,
    )

    actions = []
    for sf in step_files:
        step_idx = int(re.search(r"(\d+)$", sf.stem).group(1)) if re.search(r"(\d+)$", sf.stem) else -1
        try:
            payload = json.loads(sf.read_text())
        except Exception:
            payload = {}
        raw_action = payload.get("action")
        action = normalize_action(raw_action)
        actions.append((step_idx, action))

    first_wrong_step = None
    reason = ""

    err = (summary.get("err_msg") or "").strip()
    if err:
        first_wrong_step = actions[0][0] if actions else 0
        reason = "runtime_error"

    # Repetition/loop heuristic.
    if not reason:
        for i in range(2, len(actions)):
            a0 = actions[i - 2][1]
            a1 = actions[i - 1][1]
            a2 = actions[i][1]
            if a0 and a0 == a1 == a2:
                first_wrong_step = actions[i - 2][0]
                reason = "repeated_action_loop"
                break

    # Off-domain detour heuristic (excluding common search engines).
    if not reason and expected_domain:
        for step_idx, action in actions:
            gd = parse_goto_domain(action)
            if not gd:
                continue
            if gd in expected_domain or expected_domain in gd:
                continue
            if any(sd in gd for sd in ["google.", "bing.", "duckduckgo."]):
                continue
            first_wrong_step = step_idx
            reason = f"off_domain_goto:{gd}"
            break

    # No final answer and truncation indicates never converged.
    final_answer = (task.get("final_answer") or "").strip()
    truncated = summary.get("truncated") is True
    if not reason and truncated and final_answer == "<NO FINAL ANSWER>":
        first_wrong_step = actions[-1][0] if actions else task.get("num_steps", -1)
        reason = "step_budget_exhausted_without_answer"

    # Unknown from evaluator payload errors.
    gpt = (task.get("gpt_4v_res") or "").lower()
    if not reason and "validationexception" in gpt and "image.source.bytes" in gpt:
        first_wrong_step = actions[-1][0] if actions else task.get("num_steps", -1)
        reason = "evaluator_payload_error"

    # Near miss: final answer exists but judged failed.
    near_miss = final_answer not in ("", "<NO FINAL ANSWER>") and task.get("success") == "failed"

    if not reason:
        first_wrong_step = actions[-1][0] if actions else task.get("num_steps", -1)
        reason = "incomplete_or_ambiguous"

    return {
        "task_id": tid,
        "status": task.get("success"),
        "num_steps": task.get("num_steps"),
        "expected_domain": expected_domain,
        "first_wrong_step": first_wrong_step,
        "reason": reason,
        "near_miss": near_miss,
        "truncated": summary.get("truncated"),
        "err_msg": (summary.get("err_msg") or "")[:220],
        "final_answer_preview": final_answer[:160],
        "actions": [a for _, a in actions[:12]],
    }


problem_tasks = [t for t in EXP.get("all_tasks", []) if t.get("success") in ("failed", "unknown")]
analyses = [classify_task(t) for t in problem_tasks]

# Save machine-readable report.
(Path("results") / "step_track_report.json").write_text(json.dumps(analyses, indent=2))

# Print concise human summary.
print(f"Analyzed problematic tasks: {len(analyses)}")

# Top 20 with strongest signals first.
priority = sorted(
    analyses,
    key=lambda x: (
        0 if x["reason"].startswith("runtime_error") else 1,
        0 if x["reason"].startswith("step_budget") else 1,
        x["first_wrong_step"] if isinstance(x["first_wrong_step"], int) else 999,
    ),
)

for item in priority[:20]:
    print(
        f"{item['task_id']:28} {item['status']:7} "
        f"wrong@{item['first_wrong_step']:<2} reason={item['reason']} "
        f"steps={item['num_steps']} trunc={item['truncated']} near_miss={item['near_miss']}"
    )
    if item["actions"]:
        print("  step_actions:", " || ".join(item["actions"][:5]))
    if item["err_msg"]:
        print("  err:", item["err_msg"])
    if item["final_answer_preview"]:
        print("  final:", item["final_answer_preview"])
