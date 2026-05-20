# Dockerfile for browser-use-eval on EC2 Ubuntu host.
#
# Build:    docker build -t browser-use-eval .
# Run:      docker run --rm -it \
#               -v "$PWD/results:/app/results" \
#               -v "$PWD/data:/app/data" \
#               -v "$HOME/.aws:/root/.aws:ro" \
#               -e AWS_PROFILE=prof \
#               -e AWS_DEFAULT_REGION=us-east-1 \
#               -e BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6 \
#               browser-use-eval \
#               python run_browser_use_v2.py --use-vision true --max-concurrent 6
#
# Notes:
#  - Xvfb runs in the entrypoint so headed Chromium has a virtual display.
#  - Patchright Chromium binary is downloaded at image-build time.
#  - AWS creds are mounted read-only; the `prof` profile is used.

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-browsers \
    DISPLAY=:99

# OS deps: Xvfb (virtual display), Chromium runtime libs, fonts, build tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git tzdata \
    xvfb x11-utils xauth \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0 \
    fonts-liberation fonts-noto-color-emoji fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps. We pin the key packages but let pip resolve the long tail.
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Install Patchright Chromium (stealth fork of Playwright Chromium).
RUN patchright install chromium --with-deps

# Copy source last so deps stay cached on code edits.
COPY . /app

# Entrypoint launches Xvfb and execs the given command.
RUN printf '#!/bin/sh\nset -e\nXvfb :99 -screen 0 1280x1024x24 -nolisten tcp &\nsleep 1\nexec "$@"\n' > /entrypoint.sh \
    && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "run_browser_use_v2.py", "--help"]
