"""Minimal browser-profile builder.

This module used to do persona rotation + warm-up + Patchright wiring as a
stealth layer. Methodology changed (per professor): we are openly a bot and
rate-limit politely instead of trying to evade detection. This now just
constructs a plain BrowserProfile with sensible defaults.

If the run hits anti-bot walls (Cloudflare / Google /sorry/index), they're
recorded as `captcha_blocked` outcomes — clean methodology data points,
no attempt to bypass.
"""
from __future__ import annotations

from typing import Any


def build_browser_profile(headless: bool = True) -> Any:
    """Construct a vanilla BrowserProfile.

    No spoofed user-agent, no spoofed locale/timezone, no spoofed viewport.
    Whatever Chromium ships with by default.
    """
    from browser_use.browser.profile import BrowserProfile  # type: ignore

    return BrowserProfile(
        headless=headless,
        viewport={"width": 1280, "height": 1024},
        ignore_https_errors=True,
    )
