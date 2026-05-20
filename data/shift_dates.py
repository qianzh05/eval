"""Deterministically shift FUTURE-SCHEDULING dates in WebVoyager tasks.

Reads `WebVoyager_data.jsonl.bak` (original WebVoyager prompts) and writes
`WebVoyager_data.jsonl` with dates shifted to a near-future window
[today + MIN_DAYS, today + MAX_DAYS] for tasks that ASK the agent to schedule
or book something in the future. Historical-reference tasks (e.g. "papers
announced in October 2023", "books released in 2024") are left unchanged
because their dates are real past data the site still has.

The shift is deterministic per task_id (sha256-seeded RNG), so re-running the
script produces identical output.

Policy:
  - Force-shift web_names: Booking, Google Flights, ESPN (date-specific games)
  - Force-shift if prompt matches future-scheduling cues (schedule/pickup,
    reserve, leaving on, departing, return on, available for, stay from, etc.)
  - Otherwise: keep original dates

When a task has a date RANGE (e.g. "Jan 5 to Jan 10, 2027"), the start date is
shifted to the target and the end date is shifted by the same duration so the
range length is preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "WebVoyager_data.jsonl.bak"
DEST = HERE / "WebVoyager_data.jsonl"

# Target shift window — every shifted date lands in [today + MIN, today + MAX].
# Picked to stay inside booking.com's ~16-month and Google Flights' ~330-day caps.
MIN_DAYS = 60
MAX_DAYS = 240

# Web names whose tasks are inherently future-scheduling.
FUTURE_WEBS = {"Booking", "Google Flights"}

# Cue phrases that signal a future-scheduling task even on other sites.
FUTURE_CUES = [
    "leaving on", "departing", "depart on", "returning on", "return on",
    "available for", "available on",
    "stay from", "stay starting", "for a ", "-night stay",
    "schedule", "pickup for", "in-store pickup",
    "reserve", "book a ",
    "for these dates", "for the dates",
    "leaving ", "available bookings",
    "valentine", "for the week of",
]

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
MONTH_IDX = {m: i + 1 for i, m in enumerate(MONTHS)}


def is_future_task(t: dict) -> bool:
    if t.get("web_name") in FUTURE_WEBS:
        return True
    q = (t.get("ques") or "").lower()
    return any(c in q for c in FUTURE_CUES)


def seed_for(task_id: str) -> random.Random:
    h = hashlib.sha256(task_id.encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def pick_target(rng: random.Random, today: datetime) -> datetime:
    return today + timedelta(days=rng.randint(MIN_DAYS, MAX_DAYS))


# --- date extraction ---------------------------------------------------------

DATE_PATTERNS = [
    # 1. "Month dd, yyyy" or "Month dd yyyy"
    (re.compile(
        r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<year>20[12]\d)\b",
        re.IGNORECASE), "month_day_year"),
    # 2. "dd/mm/yyyy" or "dd-mm-yyyy"  (assumed day-first like in WebVoyager UK-style prompts)
    (re.compile(
        r"\b(?P<day>\d{1,2})[/-](?P<month>\d{1,2})[/-](?P<year>20[12]\d)\b"), "dmy_slash"),
    # 3. "yyyy-mm-dd" ISO
    (re.compile(
        r"\b(?P<year>20[12]\d)-(?P<month>\d{2})-(?P<day>\d{2})\b"), "iso"),
    # 4. "Month yyyy"
    (re.compile(
        r"\b(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)\s+(?P<year>20[12]\d)\b",
        re.IGNORECASE), "month_year"),
    # 5. "in/for/by/during/until/before/after yyyy"
    (re.compile(
        r"\b(?P<prep>in|for|by|during|until|before|after)\s+(?P<year>20[12]\d)\b",
        re.IGNORECASE), "prep_year"),
]


def parse_anchor_date(text: str) -> Optional[date]:
    """Return the first parseable specific (day,month,year) date in text, else None."""
    for pat, kind in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if kind == "month_day_year":
                mo = MONTH_IDX[m.group("month").lower()]
                return date(int(m.group("year")), mo, int(m.group("day")))
            if kind == "dmy_slash":
                return date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
            if kind == "iso":
                return date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
        except ValueError:
            continue
    return None


# --- per-task shifting -------------------------------------------------------

def shift_task(text: str, rng: random.Random, today: datetime) -> tuple[str, bool]:
    """Shift dates inside `text`. Returns (new_text, changed?).

    Strategy:
      1. Pick a target date T = today + uniform(MIN_DAYS, MAX_DAYS).
      2. Find the first ANCHOR date in the prompt (most specific form first).
         The shift delta = T - anchor. Every other date in the prompt gets that
         same delta applied (preserving ranges and gaps).
      3. If no anchor (only bare "in YYYY"), set delta = T.year - matched_year
         and only rewrite the year.
    """
    target = pick_target(rng, today).date()
    anchor = parse_anchor_date(text)

    if anchor is not None:
        delta = target - anchor  # timedelta
        return _apply_full_shift(text, delta, target.year), True

    # No full date — only year refs. Shift year to target.year.
    new_text = _apply_year_only_shift(text, target.year)
    return new_text, new_text != text


def _apply_full_shift(text: str, delta: timedelta, target_year: int) -> str:
    """Shift every recognized date by delta; year-only refs become target_year."""

    def _sub_month_day_year(m: re.Match) -> str:
        try:
            d = date(int(m.group("year")), MONTH_IDX[m.group("month").lower()], int(m.group("day")))
        except ValueError:
            return m.group(0)
        nd = d + delta
        # preserve "th"/"st"/"nd"/"rd" if present
        return f"{MONTHS[nd.month - 1].capitalize()} {nd.day}, {nd.year}"

    text = DATE_PATTERNS[0][0].sub(_sub_month_day_year, text)

    def _sub_dmy(m: re.Match) -> str:
        try:
            d = date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
        except ValueError:
            return m.group(0)
        nd = d + delta
        return f"{nd.day:02d}/{nd.month:02d}/{nd.year}"

    text = DATE_PATTERNS[1][0].sub(_sub_dmy, text)

    def _sub_iso(m: re.Match) -> str:
        try:
            d = date(int(m.group("year")), int(m.group("month")), int(m.group("day")))
        except ValueError:
            return m.group(0)
        nd = d + delta
        return f"{nd.year}-{nd.month:02d}-{nd.day:02d}"

    text = DATE_PATTERNS[2][0].sub(_sub_iso, text)

    # For "Month yyyy" without a day, shift to (anchor.month + delta_months, target_year-ish).
    # Approximate by adding delta.days to a synthetic day=15 of that month.
    def _sub_month_year(m: re.Match) -> str:
        try:
            d = date(int(m.group("year")), MONTH_IDX[m.group("month").lower()], 15)
        except ValueError:
            return m.group(0)
        nd = d + delta
        return f"{MONTHS[nd.month - 1].capitalize()} {nd.year}"

    text = DATE_PATTERNS[3][0].sub(_sub_month_year, text)

    # "in YYYY" → "in target_year"
    def _sub_prep_year(m: re.Match) -> str:
        return f"{m.group('prep')} {target_year}"

    text = DATE_PATTERNS[4][0].sub(_sub_prep_year, text)

    return text


def _apply_year_only_shift(text: str, target_year: int) -> str:
    """When no anchor date is parseable, only rewrite year references."""
    def _sub(m: re.Match) -> str:
        return f"{m.group('prep')} {target_year}"
    return DATE_PATTERNS[4][0].sub(_sub, text)


# --- main --------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=SOURCE)
    p.add_argument("--dest", type=Path, default=DEST)
    p.add_argument("--today", type=str, default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    today = (datetime.strptime(args.today, "%Y-%m-%d") if args.today else datetime.now())

    if not args.source.exists():
        raise SystemExit(f"source not found: {args.source}")

    n_total = n_future = n_changed = n_skipped_historical = 0
    out_lines: list[str] = []
    examples: list[tuple[str, str, str, str]] = []

    with args.source.open() as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            t = json.loads(line)
            n_total += 1
            original = t["ques"]
            if is_future_task(t):
                n_future += 1
                rng = seed_for(t["id"])
                new_q, changed = shift_task(t["ques"], rng, today)
                if changed:
                    n_changed += 1
                    if len(examples) < 8:
                        examples.append(("shift", t["id"], original, new_q))
                t["ques"] = new_q
            else:
                # Historical-reference task — leave dates alone.
                if any(re.search(r"\b20[12]\d\b", original) for _ in [0]):
                    n_skipped_historical += 1
            out_lines.append(json.dumps(t, ensure_ascii=False))

    print(f"total tasks:                  {n_total}")
    print(f"future-scheduling tasks:      {n_future}")
    print(f"  → dates shifted:            {n_changed}")
    print(f"historical tasks with dates:  {n_skipped_historical} (left unchanged)")
    print(f"window: today + {MIN_DAYS}..{MAX_DAYS} days  (today={today:%Y-%m-%d})")
    if examples:
        print("\nfirst 8 shifts:")
        for kind, tid, before, after in examples:
            print(f"  [{tid}]")
            print(f"    BEFORE: {before}")
            print(f"    AFTER:  {after}")

    if args.dry_run:
        print("\n(dry-run; not writing destination)")
        return

    args.dest.write_text("\n".join(out_lines) + "\n")
    print(f"\nwrote {n_total} tasks to {args.dest}")


if __name__ == "__main__":
    main()
