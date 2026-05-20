#!/usr/bin/env bash
# One-shot setup for a fresh Ubuntu 22.04 EC2 instance.
#
# Usage on the VM (as a sudo-capable user):
#   curl -fsSL <raw-url-of-this-script> | bash
#   # OR
#   git clone <repo> && cd browser-use-eval && bash setup_vm.sh
#
# After completion, AWS credentials must be present in ~/.aws/credentials with
# the `prof` profile (or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars).

set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/browser-use-eval}"
GIT_URL="${GIT_URL:-}"  # set if you want this script to clone for you

log() { printf '\033[1;34m[setup]\033[0m %s\n' "$*"; }

# 1. base packages
log "installing base packages"
sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
    ca-certificates curl git tmux htop unzip jq

# 2. docker
if ! command -v docker >/dev/null 2>&1; then
    log "installing Docker"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    log "added $USER to docker group; you may need to re-login for it to take effect"
fi

# 3. AWS CLI v2 (used to verify the profile works)
if ! command -v aws >/dev/null 2>&1; then
    log "installing AWS CLI v2"
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    (cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install) && rm -rf /tmp/aws /tmp/awscliv2.zip
fi

# 4. clone repo if URL provided and not already present
if [[ -n "${GIT_URL}" && ! -d "${REPO_DIR}" ]]; then
    log "cloning repo to ${REPO_DIR}"
    git clone "${GIT_URL}" "${REPO_DIR}"
fi

# 5. build the docker image
if [[ -d "${REPO_DIR}" ]]; then
    log "building docker image"
    cd "${REPO_DIR}"
    sudo docker build -t browser-use-eval .
else
    log "no repo at ${REPO_DIR}; skipping docker build"
fi

# 6. verify AWS creds (non-fatal)
log "verifying AWS access (using AWS_PROFILE=${AWS_PROFILE:-prof})"
AWS_PROFILE="${AWS_PROFILE:-prof}" AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}" \
    aws sts get-caller-identity 2>&1 || log "WARNING: could not verify AWS creds — make sure ~/.aws/credentials has profile [prof]"

cat <<EOF

[setup] done.

next steps:
  cd ${REPO_DIR}
  # smoke-test with 10 tasks:
  sudo docker run --rm -it \\
    -v "\$PWD/results:/app/results" \\
    -v "\$PWD/data:/app/data" \\
    -v "\$HOME/.aws:/root/.aws:ro" \\
    -e AWS_PROFILE=prof \\
    -e AWS_DEFAULT_REGION=us-east-1 \\
    -e BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 \\
    browser-use-eval \\
    python run_browser_use_v2.py --use-vision true --max-concurrent 6 --limit 10

  # full re-run (long, use tmux):
  tmux new -s eval
  sudo docker run --rm \\
    -v "\$PWD/results:/app/results" -v "\$PWD/data:/app/data" \\
    -v "\$HOME/.aws:/root/.aws:ro" \\
    -e AWS_PROFILE=prof -e AWS_DEFAULT_REGION=us-east-1 \\
    -e BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 \\
    browser-use-eval \\
    python run_browser_use_v2.py --use-vision true --max-concurrent 6
  # Ctrl-b d to detach; tmux attach -t eval to come back.
EOF
