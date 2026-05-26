"""Polite per-domain rate limiter for the WebVoyager runner.

Methodology: we don't try to hide that this is a bot. We do rate-limit our
requests so we're not hammering any one site. Politeness measure, not stealth.

Behavior:
  - Global across all concurrent tasks (one shared instance)
  - Per netloc (full hostname including subdomain — www.allrecipes.com)
  - Minimum interval between requests to the same domain (default 30s)
  - Deterministic: no jitter; if `min_interval=30` and last hit was 18s ago,
    we wait exactly 12s
  - Records cumulative wait time per task_id for later profiling

Usage:
    limiter = DomainRateLimiter(min_interval_s=30.0)
    ...
    # inside on_step callback, before letting the agent take its next step:
    wait = await limiter.wait_for(page.url, task_id)
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from urllib.parse import urlparse


class DomainRateLimiter:
    def __init__(self, min_interval_s: float = 30.0):
        self.min_interval = float(min_interval_s)
        self._last_hit: dict[str, float] = {}
        self._lock = asyncio.Lock()
        # per-task profiling
        self.wait_total_s: dict[str, float] = defaultdict(float)
        self.wait_count: dict[str, int] = defaultdict(int)

    @staticmethod
    def domain_of(url: str) -> str:
        if not url:
            return ""
        return urlparse(url).netloc.lower()

    async def wait_for(self, url: str, task_id: str) -> float:
        """Block until it's polite to hit this URL's domain. Returns seconds waited."""
        domain = self.domain_of(url)
        if not domain:
            return 0.0
        wait = 0.0
        async with self._lock:
            now = time.monotonic()
            last = self._last_hit.get(domain, 0.0)
            wait = max(0.0, self.min_interval - (now - last))
            # Reserve the slot now — this stops two concurrent tasks from both
            # measuring "0s wait" and racing into the same domain.
            self._last_hit[domain] = now + wait
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
    """Reorder tasks so consecutive items hit different sites — round-robin.

    With per-domain rate limiting, this lets max-concurrent slots actually be
    parallel across different domains instead of all stalling on one site's
    30s cooldown.

    Stable within a site (preserves dataset order for tasks of the same site).
    """
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
