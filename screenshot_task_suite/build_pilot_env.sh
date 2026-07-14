#!/usr/bin/env bash
# Build a PRISTINE browser-use 0.13.2 env for the pilot (.venv-pilot).
#
# Why this exists: .venv-vision-only's wheel was built AFTER vision_only.patch
# was applied, and the patch's system_prompt.md hunks are UNCONDITIONAL (not
# env-gated) - so that env tells the model "the screenshot is clean, click by
# pixel coordinates" in EVERY mode. The pilot needs stock 0.13.2 prompting.
# This script clones fresh at tag 0.13.2, applies NO patch, builds a wheel,
# and installs it into .venv-pilot. run_pilot.py refuses to run against a
# patched prompt (it checks the installed prompt against vision_only.patch).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d /tmp/bu-pilot-build.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "==> cloning browser-use @ 0.13.2 (pristine, no patch) into $WORK"
git clone --quiet --depth 1 --branch 0.13.2 https://github.com/browser-use/browser-use "$WORK/browser-use"
cd "$WORK/browser-use"
[ "$(git describe --tags)" = "0.13.2" ] || { echo "FATAL: not at tag 0.13.2"; exit 1; }

echo "==> building wheel"
python3 -m pip install --quiet build 2>/dev/null || true
python3 -m build --wheel >/dev/null
WHEEL="$(ls dist/browser_use-*.whl)"

command -v uv >/dev/null || { echo "FATAL: uv not found (install: brew install uv)"; exit 1; }
echo "==> creating $REPO_ROOT/.venv-pilot (python 3.11, like the vision-only env)"
cd "$REPO_ROOT"
uv venv --python 3.11 .venv-pilot
uv pip install --python .venv-pilot/bin/python "$WORK/browser-use/$WHEEL" 'botocore[crt]' boto3

echo "==> sanity"
.venv-pilot/bin/python - <<'PY'
import importlib.metadata as md
v = md.version("browser-use")
assert v == "0.13.2", f"expected 0.13.2, got {v}"
import browser_use.agent.system_prompts as sp, pathlib
p = pathlib.Path(sp.__file__).parent / "system_prompt.md"
txt = p.read_text()
assert "bounding box" in txt.lower(), "stock prompt should mention bounding boxes"
# mirror the runner's guard: no vision_only.patch sentence may be present
import re
patch = pathlib.Path("vision_only.patch").read_text()
added = [l[1:].strip() for l in patch.splitlines()
         if l.startswith("+") and not l.startswith("+++") and len(l) > 41]
bad = [a for a in added if a in txt]
assert not bad, f"patched prompt text found: {bad[0][:60]!r}"
print("browser-use", v, "| stock system prompt confirmed (patch-free):", p)
PY
.venv-pilot/bin/python -m pip freeze > .venv-pilot.freeze.txt 2>/dev/null || \
  uv pip freeze --python .venv-pilot/bin/python > .venv-pilot.freeze.txt
echo "==> dependency freeze -> .venv-pilot.freeze.txt"
echo "==> done. Chrome for Testing is shared via ~/Library/Caches/ms-playwright (no reinstall needed)."
