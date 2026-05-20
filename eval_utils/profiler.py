"""Per-step phase-time and token-usage capture for browser-use Agents.

How it plugs in:
  - Pass `register_new_step_callback=profiler.on_step` to the Agent.
  - browser-use 0.12.x invokes the callback after each step with
    (browser_state, agent_output, step_number) — we read history items off
    the agent's state to get timings and token counts.

The profiler maintains a list of step records and emits:
  - `<task_dir>/steps.jsonl`   — one JSON object per step
  - aggregated phase totals + token totals returned by `.task_summary()`

If browser-use's step API changes between versions, the callback degrades to
"record what we can" and emits None for fields we couldn't extract.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def _get(o: Any, name: str, default: Any = None) -> Any:
    """Defensive attribute/key getter — browser-use models change shape between minor versions."""
    if o is None:
        return default
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


@dataclass
class StepRecord:
    step: int
    t_step_start: float
    t_step_end: float
    t_step_total_s: float = 0.0
    t_llm_s: Optional[float] = None
    t_action_s: Optional[float] = None
    t_dom_extract_s: Optional[float] = None
    t_screenshot_s: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_tokens: Optional[int] = None
    n_actions: int = 0
    action_names: list[str] = field(default_factory=list)
    url_before: Optional[str] = None
    url_after: Optional[str] = None
    page_title: Optional[str] = None
    n_dom_elements: Optional[int] = None
    n_interactive: Optional[int] = None
    captcha_detected: bool = False
    captcha_type: Optional[str] = None
    stuck_consec_run: int = 1
    error: Optional[str] = None


@dataclass
class TaskProfiler:
    task_id: str
    task_dir: Path
    started_at: float = field(default_factory=time.time)
    steps: list[StepRecord] = field(default_factory=list)
    _last_step_end: float = 0.0

    def __post_init__(self) -> None:
        self._last_step_end = self.started_at

    def record_step(
        self,
        step_no: int,
        history_item: Any,
        url_before: Optional[str],
        url_after: Optional[str],
        captcha_detected: bool,
        captcha_type: Optional[str],
        stuck_consec_run: int,
    ) -> StepRecord:
        """Build a StepRecord from a browser-use history item plus context."""
        now = time.time()
        step_total = now - self._last_step_end

        # browser-use history items expose: model_output (with action list),
        # result (list of ActionResult), state (BrowserState), metadata.
        actions = []
        action_names: list[str] = []
        try:
            mo = _get(history_item, "model_output")
            for a in (_get(mo, "action", []) or []):
                if isinstance(a, dict):
                    for k, v in a.items():
                        if v is not None:
                            action_names.append(k)
                            actions.append({k: v})
                            break
        except Exception:
            pass

        # Token + timing from history metadata if present
        meta = _get(history_item, "metadata", {}) or {}
        usage = _get(meta, "usage", {}) or {}

        rec = StepRecord(
            step=step_no,
            t_step_start=self._last_step_end,
            t_step_end=now,
            t_step_total_s=step_total,
            t_llm_s=_get(meta, "llm_duration_s") or _get(meta, "step_llm_time"),
            t_action_s=_get(meta, "action_duration_s") or _get(meta, "step_action_time"),
            t_dom_extract_s=_get(meta, "dom_extract_s"),
            t_screenshot_s=_get(meta, "screenshot_s"),
            input_tokens=_get(usage, "input_tokens") or _get(usage, "prompt_tokens"),
            output_tokens=_get(usage, "output_tokens") or _get(usage, "completion_tokens"),
            cached_tokens=_get(usage, "cached_input_tokens"),
            n_actions=len(action_names),
            action_names=action_names,
            url_before=url_before,
            url_after=url_after,
            page_title=_get(_get(history_item, "state"), "title"),
            n_dom_elements=_get(_get(history_item, "state"), "element_count"),
            n_interactive=_get(_get(history_item, "state"), "interactive_count"),
            captcha_detected=captcha_detected,
            captcha_type=captcha_type,
            stuck_consec_run=stuck_consec_run,
            error=_get((_get(history_item, "result") or [{}])[0], "error"),
        )
        self.steps.append(rec)
        self._last_step_end = now
        return rec

    def flush(self) -> None:
        """Write steps.jsonl to task_dir."""
        self.task_dir.mkdir(parents=True, exist_ok=True)
        with (self.task_dir / "steps.jsonl").open("w") as f:
            for rec in self.steps:
                f.write(json.dumps(rec.__dict__, default=str) + "\n")

    def task_summary(self) -> dict[str, Any]:
        """Aggregated per-task profile."""
        def total(field_name: str) -> float:
            return sum((getattr(s, field_name) or 0.0) for s in self.steps)

        def total_int(field_name: str) -> int:
            return sum((getattr(s, field_name) or 0) for s in self.steps)

        from collections import Counter
        action_hist = Counter()
        for s in self.steps:
            for a in s.action_names:
                action_hist[a] += 1

        wall = (self.steps[-1].t_step_end - self.started_at) if self.steps else 0.0
        llm = total("t_llm_s")
        act = total("t_action_s")
        dom = total("t_dom_extract_s")
        ss = total("t_screenshot_s")
        other = max(0.0, wall - (llm + act + dom + ss))

        return {
            "task_id": self.task_id,
            "n_steps": len(self.steps),
            "wall_clock_s": wall,
            "phase_totals_s": {
                "llm": llm,
                "browser_action": act,
                "dom_extract": dom,
                "screenshot": ss,
                "other": other,
            },
            "tokens": {
                "input": total_int("input_tokens"),
                "output": total_int("output_tokens"),
                "cached_input": total_int("cached_tokens"),
            },
            "n_actions_by_type": dict(action_hist),
            "n_steps_with_captcha": sum(1 for s in self.steps if s.captcha_detected),
            "captcha_types": sorted({s.captcha_type for s in self.steps if s.captcha_type}),
            "max_stuck_run": max((s.stuck_consec_run for s in self.steps), default=1),
        }
