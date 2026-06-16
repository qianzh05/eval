#!/bin/bash
# Build a patched browser-use for the VISION-ONLY experiment.
#   - pins browser-use to tag 0.13.2 (matches VISION_ONLY_PLAN.txt)
#   - applies vision_only.patch (Layer B: clean-screenshot prompt + form-field-only DOM)
#   - builds the wheel and installs it into a dedicated venv (.venv-vision-only)
# Re-run safe: removes any prior ./browser-use checkout first.
set -euo pipefail

# go to location of this script (the eval repo root)
cd "$(dirname "$0")"
REPO_ROOT="$(pwd)"

# fresh checkout
rm -rf browser-use
git clone https://github.com/browser-use/browser-use.git
cd browser-use

echo "Checking out tag 0.13.2"
git checkout 0.13.2          # NOTE: tag is '0.13.2' (no leading 'v'); not yet on PyPI

echo "Applying vision_only.patch"
git apply "${REPO_ROOT}/vision_only.patch"
git --no-pager diff --stat   # show what was patched

# build + install into a dedicated venv so it doesn't clobber .venv-v2 (0.12.6)
cd "${REPO_ROOT}"
uv venv --python=3.11 .venv-vision-only
source .venv-vision-only/bin/activate
cd browser-use
uv pip install build
python -m build

echo "Installing patched browser-use"
uv pip install dist/browser_use-*.whl
# Bedrock provider deps used by the eval runner
uv pip install "botocore[crt]" boto3

echo "Installing playwright browsers"
playwright install chromium

echo "Done. Activate with:  source ${REPO_ROOT}/.venv-vision-only/bin/activate"
