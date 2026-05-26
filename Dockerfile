# Dockerfile for browser-use-eval on EC2 Ubuntu host.
#
# Methodology: vanilla Playwright Chromium running headless. No Xvfb,
# no Patchright, no stealth. Politeness via per-domain rate-limiter
# in the runner code instead.
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

FROM python:3.12-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-browsers

# OS deps: Chromium runtime libs, fonts. No Xvfb — headless mode only.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget git tzdata \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0 \
    fonts-liberation fonts-noto-color-emoji fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# Install vanilla Playwright Chromium (browser-use ships playwright transitively).
RUN python -m playwright install chromium --with-deps

COPY . /app

CMD ["python", "run_browser_use_v2.py", "--help"]
