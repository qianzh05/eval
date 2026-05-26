import json
from collections import Counter
from pathlib import Path

base = Path("results/examples-browser-agent-webvoyager")
exp_path = base / "experiment_results.json"
track_path = Path("results/step_track_report.json")
out_path = Path("results/failed_task_analysis.md")

exp = json.loads(exp_path.read_text())
track = json.loads(track_path.read_text()) if track_path.exists() else []
track_by_id = {x["task_id"]: x for x in track}

failed = [t for t in exp.get("all_tasks", []) if t.get("success") == "failed"]


def categorize(track_item: dict, task_result: dict):
    reason = (track_item or {}).get("reason", "unknown")
    gpt = (task_result.get("gpt_4v_res") or "").lower()
    err = ((track_item or {}).get("err_msg") or "").lower()
    text = f"{reason} {gpt} {err}".lower()

    if "runtime_error" in reason:
        if any(k in text for k in ["serviceunavailable", "too many connections", "bedrock is unable"]):
            return "infra_runtime", "Infrastructure (model service reliability/throttling)"
        if any(k in text for k in ["timeout", "decompressionbomberror"]):
            return "platform_env", "Benchmark/platform environment constraint"
        if any(k in text for k in ["nameerror", "send_msg_to_user", "special token"]):
            return "agent_runtime_bug", "Agent/runtime integration bug"
        return "infra_runtime", "Infrastructure/runtime error"

    if "step_budget_exhausted_without_answer" in reason or "repeated_action_loop" in reason:
        return "agent_behavior", "Agent policy/planning issue"
    if "off_domain_goto" in reason:
        return "agent_behavior", "Agent navigation strategy issue"
    if "evaluator_payload_error" in reason:
        return "evaluator_platform", "Evaluation platform/integration issue"
    if "incomplete_or_ambiguous" in reason:
        return "agent_behavior", "Agent execution incomplete"
    return "unknown", "Mixed/undetermined"


def one_line_reason(track_item: dict):
    reason = (track_item or {}).get("reason", "unknown")
    err = ((track_item or {}).get("err_msg") or "").strip()
    if reason == "step_budget_exhausted_without_answer":
        return "Reached max steps before producing a final answer."
    if reason == "repeated_action_loop":
        return "Repeated the same interaction pattern and failed to progress."
    if reason.startswith("off_domain_goto"):
        return f"Navigated off target domain ({reason.split(':', 1)[1]}) and diverged."
    if reason == "evaluator_payload_error":
        return "Task trajectory appears completed/near-complete but evaluator failed on payload validation."
    if reason == "runtime_error":
        if err:
            return err.split("\n")[0]
        return "Runtime exception interrupted the task."
    return "Incomplete trajectory or ambiguous completion state."


summary_counter = Counter()
lines = []
lines.append("# Failed Task Analysis Report")
lines.append("")
lines.append(f"Source run: {exp_path}")
lines.append(f"Generated from: {track_path}")
lines.append("")
lines.append(f"Total failed tasks analyzed: {len(failed)}")
lines.append("")

for t in failed:
    tr = track_by_id.get(t["task_id"], {})
    cls, _ = categorize(tr, t)
    summary_counter[cls] += 1

lines.append("## Failure Buckets")
lines.append("")
for k, v in sorted(summary_counter.items(), key=lambda kv: (-kv[1], kv[0])):
    lines.append(f"- {k}: {v}")
lines.append("")

lines.append("## Per-Failed-Task Analysis")
lines.append("")

for t in sorted(failed, key=lambda x: x["task_id"]):
    tid = t["task_id"]
    tr = track_by_id.get(tid, {})
    cls, owner = categorize(tr, t)
    first_wrong = tr.get("first_wrong_step", "n/a")
    truncated = tr.get("truncated", "n/a")
    steps = t.get("num_steps", "n/a")
    near_miss = tr.get("near_miss", False)
    actions = tr.get("actions") or []
    action_preview = " -> ".join(actions[:4]) if actions else ""
    gpt_preview = (t.get("gpt_4v_res") or "").replace("\n", " ")[:220]

    lines.append(f"### {tid}")
    lines.append("- Status: failed")
    lines.append(f"- First Wrong Step: {first_wrong}")
    lines.append(f"- Steps Executed: {steps}")
    lines.append(f"- Truncated: {truncated}")
    lines.append(f"- Root Cause Category: {cls}")
    lines.append(f"- Ownership: {owner}")
    lines.append(
        f"- Benchmark/Platform Related: {'Yes' if ('platform' in cls or 'infra' in cls or 'evaluator' in cls) else 'No'}"
    )
    lines.append(f"- Near Miss: {'Yes' if near_miss else 'No'}")
    lines.append(f"- Reasoning: {one_line_reason(tr)}")
    if action_preview:
        lines.append(f"- Early Action Trace: {action_preview}")
    if gpt_preview:
        lines.append(f"- Evaluator Snippet: {gpt_preview}")
    lines.append("")

out_path.write_text("\n".join(lines))
print(str(out_path))
