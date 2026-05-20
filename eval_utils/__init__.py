"""Utilities for the browser-use-eval v2 runner.

Modules:
  stealth        — Patchright + realistic browser context + UA pool + warm-up.
  captcha        — detection and classification of bot-walls.
  loop_detector  — track consecutive identical actions; flag stuck tasks.
  profiler       — per-step phase-time and token capture via Agent callback.
  report         — generate the final markdown + docx report from results dir.
"""
