"""Quick unit test for DomainRateLimiter — verifies wait behavior without
needing to launch the browser or hit Bedrock. Runs in < 15 seconds.

Usage:  python verify_rate_limiter.py
"""
import asyncio
import time
import sys
from eval_utils.rate_limiter import DomainRateLimiter


def assert_close(actual: float, expected: float, tol: float = 0.5, label: str = "") -> bool:
    ok = abs(actual - expected) <= tol
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: got {actual:.2f}s, expected ~{expected:.1f}s (±{tol}s)")
    return ok


async def main() -> int:
    failures = 0
    INTERVAL = 3.0   # 3-second window for quick testing
    print(f"DomainRateLimiter test (min_interval = {INTERVAL}s)\n")

    # --- Test 1: same URL twice from same task → second call should wait ---
    print("Test 1: hitting the same URL twice → second call must wait")
    rl = DomainRateLimiter(min_interval_s=INTERVAL)
    t0 = time.monotonic()
    w1 = await rl.wait_for("https://www.allrecipes.com/", "task-a")
    w2 = await rl.wait_for("https://www.allrecipes.com/", "task-a")
    total = time.monotonic() - t0
    failures += not assert_close(w1, 0.0, 0.2, "first call (no prior hit)")
    failures += not assert_close(w2, INTERVAL, 0.5, "second call (within window)")
    failures += not assert_close(total, INTERVAL, 0.5, "total elapsed wall-clock")

    # --- Test 2: different URLs on same domain → no wait (per-page semantics) ---
    print("\nTest 2: different URLs on same domain → NO wait (per-page, not per-domain)")
    rl = DomainRateLimiter(min_interval_s=INTERVAL)
    w1 = await rl.wait_for("https://www.allrecipes.com/page-a", "task-a")
    w2 = await rl.wait_for("https://www.allrecipes.com/page-b", "task-a")
    failures += not assert_close(w1, 0.0, 0.2, "first URL")
    failures += not assert_close(w2, 0.0, 0.2, "different URL on same domain")

    # --- Test 3: concurrent tasks racing the same URL ---
    print("\nTest 3: two concurrent tasks hit the same URL → second waits")
    rl = DomainRateLimiter(min_interval_s=INTERVAL)
    t0 = time.monotonic()
    results = await asyncio.gather(
        rl.wait_for("https://www.example.com/", "task-a"),
        rl.wait_for("https://www.example.com/", "task-b"),
    )
    waits = sorted(results)
    failures += not assert_close(waits[0], 0.0, 0.5, "first to arrive (winner)")
    failures += not assert_close(waits[1], INTERVAL, 0.7, "second to arrive (waits)")

    # --- Test 4: wait_time_s + n_rate_limit_waits accounting per task_id ---
    print("\nTest 4: per-task profiling counters")
    rl = DomainRateLimiter(min_interval_s=INTERVAL)
    await rl.wait_for("https://x.com/", "task-X")
    await rl.wait_for("https://x.com/", "task-X")  # should wait ~INTERVAL
    stats = rl.stats_for("task-X")
    failures += not assert_close(stats["wait_time_s"], INTERVAL, 0.5,
                                  "wait_time_s accumulated for task-X")
    failures += not assert_close(float(stats["n_rate_limit_waits"]), 1.0, 0.0,
                                  "n_rate_limit_waits incremented")

    # --- Test 5: URL canonicalization (fragments stripped, query preserved) ---
    print("\nTest 5: URL canonicalization (fragments ignored, query kept)")
    rl = DomainRateLimiter(min_interval_s=INTERVAL)
    w1 = await rl.wait_for("https://example.com/path?q=1", "t")
    w2 = await rl.wait_for("https://example.com/path?q=1#fragment", "t")  # same with fragment
    w3 = await rl.wait_for("https://example.com/path?q=2", "t")  # different query
    failures += not assert_close(w2, INTERVAL, 0.5, "fragment ignored → SAME page → waits")
    failures += not assert_close(w3, 0.0, 0.2, "different query → DIFFERENT page → no wait")

    print(f"\n{'-'*60}")
    if failures == 0:
        print(f"✅ All checks passed — rate limiter is working as intended.")
        return 0
    else:
        print(f"❌ {failures} check(s) failed — see above.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
