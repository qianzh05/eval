"""Per-step + per-task timing and metadata recorder.

What this captures (independent of browser-use's internal fields):
  - **think_s** — time spent in the LLM call(s) during the step
  - **wait_s**  — time spent waiting on the per-domain rate limiter
  - **act_s**   — residual: step total minus think and wait → browser ops
  - **step_total_s** — wall-clock between consecutive on_step callbacks
  - Per-step action names, url before/after, captcha flag, stuck counter
  - Tokens (if browser-use's history exposes them)

Aggregates exported as:
  - steps.jsonl  — one row per step
  - profile.json — per-task totals and per-step distributions (mean/p50/p90/p95)

All derived from values WE measure (LLM wrapper counter, rate-limiter counter,
wall-clock timestamps) rather than browser-use's internal metadata, so this is
robust across browser-use minor version changes.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


def _get(o: Any, name: str, default: Any = None) -> Any:
    if o is None:
        return default
    if isinstance(o, dict):
        return o.get(name, default)
    return getattr(o, name, default)


@dataclass
class StepRecord:
    step: int
    t_step_start: float = 0.0
    t_step_end: float = 0.0
    step_total_s: float = 0.0
    # The "think / wait / act" decomposition for this step
    think_s: float = 0.0    # LLM call time
    wait_s: float = 0.0    # rate-limit wait
    act_s: float = 0.0    # residual = step_total − think − wait
    # Step content
    n_actions: int = 0
    action_names: list[str] = field(default_factory=list)
    url_before: Optional[str] = None
    url_after: Optional[str] = None
    page_title: Optional[str] = None
    n_dom_elements: Optional[int] = None
    n_interactive: Optional[int] = None
    # Token info if browser-use happens to expose it
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    # Signals
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

    def record_step(
        self,
        *,
        step_no: int,
        history_item: Any = None,
        model_output: Any = None,
        url_before: Optional[str] = None,
        url_after: Optional[str] = None,
        captcha_detected: bool = False,
        captcha_type: Optional[str] = None,
        stuck_consec_run: int = 1,
        step_start: float = 0.0,
        step_end: float = 0.0,
        think_s: float = 0.0,
        wait_s: float = 0.0,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ) -> StepRecord:
        step_total = max(0.0, step_end - step_start)
        act_s = max(0.0, step_total - think_s - wait_s)

        # Extract action names. Prefer the directly-passed model_output (most
        # reliable); fall back to history_item.model_output if not given.
        mo = model_output if model_output is not None else _get(history_item, "model_output")
        action_names: list[str] = []
        try:
            for a in (_get(mo, "action", []) or []):
                if isinstance(a, dict):
                    for k, v in a.items():
                        if v is not None:
                            action_names.append(k); break
                else:
                    d = a.model_dump() if hasattr(a, "model_dump") else {}
                    for k, v in d.items():
                        if v is not None:
                            action_names.append(k); break
        except Exception:
            pass

        # Tokens: prefer explicit values passed in (from our LLM wrapper).
        # Fall back to history_item.metadata if the wrapper didn't have data.
        in_tok = input_tokens
        out_tok = output_tokens
        if in_tok is None or out_tok is None:
            meta = _get(history_item, "metadata", {}) or {}
            usage = _get(meta, "usage", {}) or {}
            if in_tok is None:
                in_tok = (_get(usage, "input_tokens") or _get(usage, "prompt_tokens")
                          or _get(meta, "input_tokens") or 0)
            if out_tok is None:
                out_tok = _get(usage, "output_tokens") or _get(usage, "completion_tokens") or 0

        state = _get(history_item, "state")
        first_result = (_get(history_item, "result") or [{}])
        err = _get(first_result[0] if first_result else {}, "error")

        rec = StepRecord(
            step=step_no,
            t_step_start=step_start,
            t_step_end=step_end,
            step_total_s=step_total,
            think_s=think_s,
            wait_s=wait_s,
            act_s=act_s,
            n_actions=len(action_names),
            action_names=action_names,
            url_before=url_before,
            url_after=url_after,
            page_title=_get(state, "title"),
            n_dom_elements=_get(state, "element_count"),
            n_interactive=_get(state, "interactive_count"),
            input_tokens=in_tok,
            output_tokens=out_tok,
            captcha_detected=captcha_detected,
            captcha_type=captcha_type,
            stuck_consec_run=stuck_consec_run,
            error=err,
        )
        self.steps.append(rec)
        return rec

    def flush(self) -> None:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        with (self.task_dir / "steps.jsonl").open("w") as f:
            for rec in self.steps:
                f.write(json.dumps(asdict(rec), default=str) + "\n")

    @staticmethod
    def _stats(xs: list[float]) -> dict[str, float]:
        if not xs:
            return {"n": 0, "sum": 0.0, "mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
        s = sorted(xs)

        def p(q: int) -> float:
            return s[min(len(s) - 1, max(0, int(round(q / 100 * (len(s) - 1)))))]
        return {"n": len(xs), "sum": sum(xs), "mean": statistics.mean(xs),
                "p50": p(50), "p90": p(90), "p95": p(95), "max": max(xs)}

    def task_summary(self) -> dict[str, Any]:
        steps = self.steps
        think = [s.think_s for s in steps]
        wait = [s.wait_s for s in steps]
        act = [s.act_s for s in steps]
        total = [s.step_total_s for s in steps]

        from collections import Counter
        action_hist: Counter[str] = Counter()
        for s in steps:
            for a in s.action_names:
                action_hist[a] += 1

        wall = (steps[-1].t_step_end - self.started_at) if steps else 0.0

        return {
            "task_id": self.task_id,
            "n_steps": len(steps),
            "wall_clock_s": wall,
            # Per-task totals (sum across steps)
            "phase_totals_s": {
                "think": sum(think),
                "wait": sum(wait),
                "act": sum(act),
                "step_total": sum(total),
            },
            # Per-step distributions
            "per_step_stats": {
                "think_s": self._stats(think),
                "wait_s": self._stats(wait),
                "act_s": self._stats(act),
                "step_total_s": self._stats(total),
            },
            "n_actions_by_type": dict(action_hist),
            "n_steps_with_captcha": sum(1 for s in steps if s.captcha_detected),
            "captcha_types": sorted({s.captcha_type for s in steps if s.captcha_type}),
            "max_stuck_run": max((s.stuck_consec_run for s in steps), default=1),
            # Tokens if present
            "tokens": {
                "input_total": sum((s.input_tokens or 0) for s in steps),
                "output_total": sum((s.output_tokens or 0) for s in steps),
            },
        }
