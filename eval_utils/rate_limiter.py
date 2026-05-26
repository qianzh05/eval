"""Per-PAGE polite rate limiter (prof's interpretation).

Methodology: we don't try to evade detection. We do rate-limit so we never
re-fetch the same URL within a short window. The limit applies per-page
(full URL, fragment stripped) — not per-domain — so an agent can navigate
freely between different pages on the same site without waiting.

The intent (per the professor): "make sure there is a time in between two
crawls of the same page." We treat "page" as URL; a navigation to a
different URL is a different crawl.

Default min interval: 30s per URL.

Used together with `interleave_by_site`, which spreads concurrent tasks
across different domains at startup, the cumulative wait per task is
typically 0 — the limiter only fires when two concurrent tasks happen to
load the same URL (rare — usually a site root) or when an agent revisits
a URL it just saw (also rare; usually only inside action loops, which the
stuck-detector catches anyway).
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse


class DomainRateLimiter:
    """Name kept for backwards compatibility; semantics are now per-URL."""

    def __init__(self, min_interval_s: float = 30.0):
        self.min_interval = float(min_interval_s)
        self._last_hit: dict[str, float] = {}
        self._lock = asyncio.Lock()
        # per-task profiling (cumulative across whole task)
        self.wait_total_s: dict[str, float] = defaultdict(float)
        self.wait_count: dict[str, int] = defaultdict(int)

    @staticmethod
    def page_key(url: str) -> str:
        """Canonicalize a URL for rate-limit keying. Strips fragments; keeps
        scheme + netloc + path + query, lowercased."""
        if not url:
            return ""
        try:
            p = urlparse(url)
            netloc = p.netloc.lower()
            if not netloc:
                return ""
            path = p.path or "/"
            qs = f"?{p.query}" if p.query else ""
            return f"{p.scheme.lower()}://{netloc}{path}{qs}"
        except Exception:
            return url

    @staticmethod
    def domain_of(url: str) -> str:
        """Kept for compatibility with callers that want just the domain."""
        if not url:
            return ""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""

    async def wait_for(self, url: str, task_id: str) -> float:
        """Block until it's polite to crawl this URL again. Returns seconds waited."""
        key = self.page_key(url)
        if not key:
            return 0.0
        wait = 0.0
        async with self._lock:
            now = time.monotonic()
            last = self._last_hit.get(key, 0.0)
            wait = max(0.0, self.min_interval - (now - last))
            # Reserve the slot so concurrent callers don't both see "0s wait" and
            # race the same URL.
            self._last_hit[key] = now + wait
        if wait > 0:
            self.wait_total_s[task_id] += wait
            self.wait_count[task_id] += 1
            await asyncio.sleep(wait)
        return wait

    def stats_for(self, task_id: str) -> dict[str, float]:
        return {
            "wait_time_s": self.wait_total_s.get(task_id, 0.0),
            "n_rate_limit_waits": self.wait_count.get(task_id, 0),
        }


def interleave_by_site(tasks: list[dict]) -> list[dict]:
    """Reorder tasks round-robin across sites so concurrent slots hit
    different domains at startup. Stable within a site."""
    by_site: dict[str, list[dict]] = defaultdict(list)
    site_order: list[str] = []
    for t in tasks:
        site = t.get("web_name") or t.get("id", "").split("--")[0]
        if site not in by_site:
            site_order.append(site)
        by_site[site].append(t)
    out: list[dict] = []
    indices = {s: 0 for s in site_order}
    while any(indices[s] < len(by_site[s]) for s in site_order):
        for s in site_order:
            i = indices[s]
            if i < len(by_site[s]):
                out.append(by_site[s][i])
                indices[s] = i + 1
    return out
