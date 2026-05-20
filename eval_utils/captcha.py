"""CAPTCHA / bot-wall detection and classification.

We don't try to solve CAPTCHAs (no paid services). We detect them so a task
can exit with `success="captcha_blocked"` instead of burning 30 steps on a
wall we can't cross. The runner calls `looks_like_captcha(page)` after the
warm-up and after each agent step.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Optional

CaptchaType = Literal[
    "cloudflare",       # Cloudflare Turnstile / "Verify you are human"
    "recaptcha",        # Google reCAPTCHA (v2 checkbox, v3 score, /sorry/index)
    "google_sorry",     # Google "/sorry/index" rate-limit page
    "hcaptcha",         # hCaptcha widget
    "press_and_hold",   # PerimeterX "Press & Hold" behavioral
    "datadome",         # DataDome block page
    "unknown_block",    # access-denied / 403 / "blocked" with no specific vendor
]


# URL substrings → captcha type. Checked first because they're cheap and certain.
_URL_SIGNATURES: list[tuple[str, CaptchaType]] = [
    ("google.com/sorry", "google_sorry"),
    ("/sorry/index", "google_sorry"),
    ("challenges.cloudflare.com", "cloudflare"),
    ("cdn-cgi/challenge-platform", "cloudflare"),
    ("hcaptcha.com", "hcaptcha"),
    ("captcha-delivery.com", "datadome"),
    ("perimeterx.net", "press_and_hold"),
]

# DOM/text signatures (lower-cased). Each list is a set of phrases ANY of which
# triggers the type. Order matters — first hit wins.
_DOM_SIGNATURES: list[tuple[CaptchaType, list[str]]] = [
    ("cloudflare", [
        "verify you are human",
        "cloudflare to review",
        "checking your browser before accessing",
        "ray id:",
        "needs to review the security of your connection",
    ]),
    ("recaptcha", [
        "i'm not a robot",
        "recaptcha",
        "google.com/recaptcha",
    ]),
    ("hcaptcha", [
        "hcaptcha-checkbox",
        "please verify you are a human",
    ]),
    ("press_and_hold", [
        "press & hold",
        "press and hold to confirm",
    ]),
    ("google_sorry", [
        "our systems have detected unusual traffic",
        "this page appears when google automatically detects requests",
    ]),
    ("datadome", [
        "blocked by datadome",
        "you have been blocked",
    ]),
    ("unknown_block", [
        "access denied",
        "403 forbidden",
        "you don't have permission",
        "request blocked",
        "too many requests",
    ]),
]


async def looks_like_captcha(page: Any) -> Optional[CaptchaType]:
    """Inspect the current page and return a CaptchaType if one is present.

    Cheap: checks URL first, then a small text snippet (<= 8 KB).
    """
    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""

    for sig, kind in _URL_SIGNATURES:
        if sig in url:
            return kind

    # Cheap DOM check — read a bounded chunk of innerText so we don't slurp
    # huge pages every step.
    try:
        text = await page.evaluate(
            "() => (document.body && document.body.innerText) "
            "? document.body.innerText.slice(0, 8000).toLowerCase() : ''"
        )
    except Exception:
        return None
    if not text:
        return None

    for kind, phrases in _DOM_SIGNATURES:
        for ph in phrases:
            if ph in text:
                return kind

    # Iframe sniff for Cloudflare challenge embedded inside an iframe
    try:
        has_cf_iframe = await page.evaluate(
            "() => !!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')"
        )
    except Exception:
        has_cf_iframe = False
    if has_cf_iframe:
        return "cloudflare"

    return None


def is_terminal_block(kind: Optional[CaptchaType]) -> bool:
    """True if we should abort the task (vs. wait-and-retry).

    `cloudflare` and `recaptcha` *checkbox* challenges sometimes auto-pass
    after a few seconds — the runner will idle and re-check before aborting.
    `google_sorry`, `datadome`, `press_and_hold` and `unknown_block` are
    effectively terminal for an OSS stack with no paid solver/proxy.
    """
    if kind is None:
        return False
    return kind in {"google_sorry", "datadome", "press_and_hold", "unknown_block"}
