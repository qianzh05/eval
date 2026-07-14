#!/usr/bin/env bash
# One-command overnight pilot (runbook steps 5-7 chained):
#   preflight -> smoke (off, T2-3) -> smoke artifact validation
#   -> alt-text probe rep (off, T1-2c) + coarse 17.3 grep (NON-blocking)
#   -> matrix: off, on, auto sequentially (3 reps, concurrency 3)
#   -> score_pilot
# Aborts before the matrix if the smoke artifacts are broken, so a pipeline
# bug costs cents, not the night. The alt-text grep only REPORTS - Type1
# reclassification is a scoring-side decision made in the morning.
#
# Launch (from repo root, leave the terminal open; Mac plugged in):
#   nohup caffeinate -is bash screenshot_task_suite/run_overnight.sh \
#       > screenshot_task_suite/results/overnight.log 2>&1 &
#   tail -f screenshot_task_suite/results/overnight.log   # to watch
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
PY=".venv-pilot/bin/python"
RUN="screenshot_task_suite/run_pilot.py"
TAG="${1:-pilot-$(date +%F)}"
export AWS_PROFILE="${AWS_PROFILE:-prof}"

echo "==> [$(date '+%H:%M:%S')] overnight pilot, run-tag=$TAG, AWS_PROFILE=$AWS_PROFILE"

echo "==> preflight: venv + version + AWS credentials"
[ -x "$PY" ] || { echo "FATAL: .venv-pilot missing - run build_pilot_env.sh"; exit 1; }
"$PY" - <<'PYEOF'
import importlib.metadata as md
v = md.version("browser-use")
assert v == "0.13.2", f"expected browser-use 0.13.2, got {v}"
import boto3, os
ident = boto3.Session(profile_name=os.environ["AWS_PROFILE"],
                      region_name="us-west-2").client("sts").get_caller_identity()
print("browser-use", v, "| AWS account", ident["Account"], "OK")
PYEOF

echo "==> [$(date '+%H:%M:%S')] SMOKE: off mode, 1 rep, pilot-T2-3"
"$PY" "$RUN" --mode off --repeats 1 --task-id pilot-T2-3 --run-tag "$TAG-smoke"

echo "==> validating smoke artifacts"
"$PY" - "screenshot_task_suite/results/$TAG-smoke/off/pilot-T2-3" <<'PYEOF'
import json, pathlib, sys
root = pathlib.Path(sys.argv[1])
reps = sorted(root.glob("rep*/task_result.json"))
assert reps, f"no task_result.json under {root}"
r = json.loads(reps[0].read_text())
u = r.get("usage_native") or {}
assert u.get("total_prompt_tokens"), "no prompt tokens recorded - LLM never ran?"
sj = reps[0].parent / "steps.jsonl"
assert sj.exists() and sj.read_text().strip(), "steps.jsonl missing/empty"
conv = reps[0].parent / "conversation"
assert conv.exists() and any(conv.iterdir()), "conversation/ missing/empty"
print("smoke OK | is_done:", r.get("is_done"),
      "| answer:", (r.get("final_answer") or "")[:80],
      "| error:", r.get("error"))
PYEOF

echo "==> [$(date '+%H:%M:%S')] ALT-TEXT PROBE: off mode, 1 rep, pilot-T1-2c"
"$PY" "$RUN" --mode off --repeats 1 --task-id pilot-T1-2c --run-tag "$TAG-altcheck"
ALT_DIR="screenshot_task_suite/results/$TAG-altcheck/off/pilot-T1-2c"
if grep -rl "17\.3" "$ALT_DIR"/rep*/conversation/ >/dev/null 2>&1; then
  echo "ALT-PROBE: '17.3' PRESENT somewhere in conversation logs" | tee "$ALT_DIR/altcheck_note.txt"
  echo "  (morning review must confirm it sits in the SERIALIZED STATE the" | tee -a "$ALT_DIR/altcheck_note.txt"
  echo "   model received, not only in the model's own output)" | tee -a "$ALT_DIR/altcheck_note.txt"
else
  echo "ALT-PROBE: '17.3' ABSENT from conversation logs - if the run reached" | tee "$ALT_DIR/altcheck_note.txt"
  echo "  the WA result page, alt text is NOT surfaced; Type1 contingency review" | tee -a "$ALT_DIR/altcheck_note.txt"
fi

echo "==> [$(date '+%H:%M:%S')] MATRIX: 10 tasks x 3 reps x {off,on,auto}, sequential modes"
for M in off on auto; do
  echo "==> [$(date '+%H:%M:%S')] matrix mode=$M"
  "$PY" "$RUN" --mode "$M" --repeats 3 --concurrency 3 --run-tag "$TAG" \
    || { echo "FATAL: mode $M exited nonzero - aborting chain"; exit 1; }
done

echo "==> [$(date '+%H:%M:%S')] scoring"
"$PY" screenshot_task_suite/score_pilot.py --run-tag "$TAG"

echo "==> [$(date '+%H:%M:%S')] DONE. Results: screenshot_task_suite/results/$TAG/"
