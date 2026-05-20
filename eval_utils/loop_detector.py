"""Per-task loop / stuck detection.

After each agent step, the runner pushes the executed action signature(s) into
`LoopDetector.observe(...)`. The detector tracks consecutive identical mutating
actions and decides whether the task is stuck.

Default policy (from the prior-run analysis):

  - Same `(action_name, canonical_args)` appearing **CONSEC_ABORT** times in
    a row triggers abort with stuck_reason="action_loop".
  - Read-only / benign-to-repeat actions (scroll, wait, extract_content,
    done, switch_tab, open_tab, close_tab, scroll_to_text) are tracked but
    their repetition alone does NOT trigger the abort signal.
  - Wall-clock cap is enforced at the runner level, not here.

The detector reports the max consecutive run reached during the task and the
action that caused it, for later reporting.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

# Actions whose repetition is normal user behavior.
_BENIGN = {
    "scroll_down", "scroll_up", "scroll", "scroll_to_text",
    "wait", "extract_content", "extract_page_content",
    "done", "switch_tab", "open_tab", "close_tab",
}


def signature(action: dict[str, Any]) -> Optional[tuple[str, str]]:
    """Return (name, canonical_args) for a single browser-use action dict."""
    if not isinstance(action, dict):
        return None
    for k, v in action.items():
        if v is None:
            continue
        try:
            return (k, json.dumps(v, sort_keys=True, default=str)[:200])
        except Exception:
            return (k, str(v)[:200])
    return None


@dataclass
class LoopDetector:
    consec_abort: int = 8         # ≥ this many consecutive identical mutating actions → abort
    last_sig: Optional[tuple[str, str]] = None
    cur_run: int = 1
    max_run: int = 1
    looped_action_name: Optional[str] = None
    looped_action_args: Optional[str] = None
    benign_runs: list[tuple[str, int]] = field(default_factory=list)  # for reporting only

    def observe(self, actions: list[dict[str, Any]]) -> bool:
        """Feed the actions executed during one agent step. Returns True if stuck."""
        for a in actions:
            sig = signature(a)
            if sig is None:
                continue
            if self.last_sig is not None and sig == self.last_sig:
                self.cur_run += 1
                if self.cur_run > self.max_run:
                    self.max_run = self.cur_run
                    self.looped_action_name = sig[0]
                    self.looped_action_args = sig[1]
            else:
                self.cur_run = 1
            self.last_sig = sig

            if sig[0] in _BENIGN:
                # Benign repetition doesn't trip the stuck flag, but we still
                # update max_run for reporting completeness above.
                continue
            if self.cur_run >= self.consec_abort:
                return True
        return False

    def summary(self) -> dict[str, Any]:
        return {
            "max_consec_run": self.max_run,
            "looped_action_name": self.looped_action_name,
            "looped_action_args": self.looped_action_args,
        }
