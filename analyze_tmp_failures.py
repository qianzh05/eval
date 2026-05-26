import json
import re
from pathlib import Path

base = Path("results/examples-browser-agent-webvoyager")
exp = json.loads((base / "experiment_results.json").read_text())

rows = []
for t in exp.get("all_tasks", []):
    if t.get("success") not in ("failed", "unknown"):
        continue

    tid = t["task_id"]
    d = base / tid / "bgym"

    summary = {}
    sp = d / "summary_info.json"
    if sp.exists():
        try:
            summary = json.loads(sp.read_text())
        except Exception:
            summary = {}

    step_files = sorted(
        d.glob("steps_info_*.json"),
        key=lambda p: int(re.search(r"(\d+)$", p.stem).group(1)) if re.search(r"(\d+)$", p.stem) else -1,
    )

    last = {}
    if step_files:
        try:
            last = json.loads(step_files[-1].read_text())
        except Exception:
            last = {}

    action = last.get("action") if isinstance(last, dict) else ""
    if not isinstance(action, str):
        action = str(action)

    rows.append(
        {
            "task_id": tid,
            "success": t.get("success"),
            "num_steps": t.get("num_steps", -1),
            "terminated": summary.get("terminated"),
            "truncated": summary.get("truncated"),
            "err": summary.get("err_msg"),
            "final_answer": t.get("final_answer") or "",
            "gpt": t.get("gpt_4v_res") or "",
            "last_action": action,
        }
    )

b = {
    "count_problem_tasks": len(rows),
    "truncated_true": 0,
    "no_final_answer": 0,
    "captcha_or_block": 0,
    "runtime_err_msg_present": 0,
    "has_send_msg_action": 0,
}

for r in rows:
    txt = " ".join([r["gpt"], r["final_answer"], r["last_action"], str(r["err"])]).lower()
    if r["truncated"] is True:
        b["truncated_true"] += 1
    if r["final_answer"].strip() == "<NO FINAL ANSWER>":
        b["no_final_answer"] += 1
    if any(k in txt for k in ["captcha", "unusual traffic", "blocked", "access denied"]):
        b["captcha_or_block"] += 1
    if r["err"]:
        b["runtime_err_msg_present"] += 1
    if "send_msg_to_user" in txt:
        b["has_send_msg_action"] += 1

print("SUMMARY_BUCKETS")
print(json.dumps(b, indent=2))

print("\nTOP_20_PROBLEMS")
for r in rows[:20]:
    print(
        f"{r['task_id']:28} {r['success']:7} steps={r['num_steps']:2} "
        f"trunc={r['truncated']} term={r['terminated']} err={'Y' if r['err'] else 'N'}"
    )
    print("  action:", (r["last_action"] or "").strip().replace("\n", " ")[:180])
    print("  eval  :", (r["gpt"] or "").strip().replace("\n", " ")[:180])
