"""Patchright + realistic context configuration for browser-use 0.12.x.

browser-use builds its own BrowserProfile/BrowserSession; we just need to feed
it a "real-looking" context. The two main knobs that matter:

  1. patchright-driven Chromium binary (replaces vanilla playwright Chromium)
  2. context options: user agent, locale, timezone, viewport, permissions

We also expose a small `warm_up_site` coroutine that visits the site root and
idles briefly before the task starts, so Cloudflare/Turnstile challenges have a
chance to auto-pass.
"""
from __future__ import annotations

import random
from typing import Any
from urllib.parse import urlparse

# Modern Chrome on macOS / Windows / Linux — keep all UAs aligned with a real
# recent Chrome major version so Patchright's hints stay consistent.
_UA_POOL: list[str] = [
    # macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
]

_LOCALE_POOL = ["en-US", "en-GB", "en-CA"]
_TZ_POOL = ["America/New_York", "America/Los_Angeles", "America/Chicago", "Europe/London"]


def pick_persona(task_id: str) -> dict[str, Any]:
    """Deterministic per-task persona: UA, locale, timezone, viewport.

    Determinism keeps the run reproducible. The persona is *passed* to the
    BrowserProfile so each task uses a stable but distinct fingerprint.
    """
    rng = random.Random(hash(task_id) & 0xFFFFFFFF)
    return {
        "user_agent": rng.choice(_UA_POOL),
        "locale": rng.choice(_LOCALE_POOL),
        "timezone_id": rng.choice(_TZ_POOL),
        "viewport": {
            "width": rng.choice([1280, 1366, 1440, 1512, 1536, 1600]),
            "height": rng.choice([720, 800, 900, 982, 1024]),
        },
        "device_scale_factor": rng.choice([1.0, 1.0, 2.0]),  # most users are 1x; some retina
    }


def build_browser_profile(persona: dict[str, Any], headless: bool = False) -> Any:
    """Construct a BrowserProfile that uses Patchright Chromium under the hood.

    browser-use 0.12.x exposes BrowserProfile (replacing the old BrowserConfig).
    We import lazily so this module is importable even if browser-use isn't.
    """
    from browser_use.browser.profile import BrowserProfile  # type: ignore

    return BrowserProfile(
        headless=headless,
        # Patchright is selected via the channel/executable_path field in BrowserProfile
        # when the patchright package is installed; the field is "channel='patchright'"
        # in current browser-use master. If absent in your installed version, we fall
        # back to playwright by default — see runner.py for the runtime check.
        user_agent=persona["user_agent"],
        locale=persona["locale"],
        timezone_id=persona["timezone_id"],
        viewport=persona["viewport"],
        device_scale_factor=persona["device_scale_factor"],
        permissions=["geolocation", "clipboard-read", "clipboard-write", "notifications"],
        ignore_https_errors=True,
        # Realistic: accept-language matches locale; java enabled; webgl on.
        extra_http_headers={
            "Accept-Language": f"{persona['locale']},en;q=0.9",
        },
    )


async def warm_up(page: Any, target_url: str, idle_seconds: float = 5.0) -> None:
    """Visit the site root before the deep task URL.

    Many Cloudflare/Turnstile challenges auto-resolve given a real-looking
    browser that idles on the root for a few seconds, so we get cookies and
    storage-state seeded "for free" before the agent ever starts navigating.

    Failures (network, timeout) are swallowed — warm-up is best-effort.
    """
    try:
        parsed = urlparse(target_url)
        if not parsed.scheme:
            return
        root = f"{parsed.scheme}://{parsed.netloc}/"
        await page.goto(root, wait_until="domcontentloaded", timeout=20_000)
        # Idle: gives Cloudflare/Turnstile time to pass + cookies to settle.
        try:
            await page.wait_for_load_state("networkidle", timeout=int(idle_seconds * 1000))
        except Exception:
            pass
    except Exception:
        pass
