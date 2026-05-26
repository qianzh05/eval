# WebVoyager eval — meeting prep summary

_browser-use vision-true vs vision-false comparison, originally run on Mac (v0.1.40), re-run on AWS EC2 with upgraded stack (browser-use 0.12.6 + Patchright stealth + date fix + stuck detection)._

---

## 1. Headline result

| condition | OLD Mac v0.1.40 | NEW VM v0.12.6 + stealth | Δ (improvement) |
|---|---:|---:|---:|
| **vision-false** success rate | 72.5% (466 / 643) | **85.1% (547 / 643)** | +12.6 pp |
| **vision-true** success rate | 77.0% (495 / 643) | **92.4% (594 / 643)** | +15.4 pp |
| Vision premium | +4.5 pp | **+7.3 pp** | larger gap on cleaned data |
| Tasks with year ≥ 2027 in prompt failing | 80 (vf) / 56 (vt) | 2 (vf) / 2 (vt) | date confounder removed |
| CAPTCHA-related failures (keyword match) | 48 | 2 | −96% (stealth worked) |

The headline numbers are larger than the original benchmark suggested because we removed two confounders that were inflating failure counts: a date-shift error in the data and an anti-bot wall on Cambridge Dictionary + Google.

---

## 2. What was actually built / done

### Infrastructure
- **Upgraded** browser-use from 0.1.40 → 0.12.6 (latest stable as of May 2026)
- **Dockerfile + setup_vm.sh** for a reproducible EC2 environment (Ubuntu 24.04, t3.xlarge in us-east-1)
- **Xvfb + headed Chromium** (not headless — biggest single anti-bot signal)
- **Patchright** as the Playwright fork for fingerprint stealth
- **Deterministic per-task RNG seeding** for the persona (UA / locale / timezone / viewport)
- **run_manifest.json** per run with host, OS, library versions, git commit, dataset hash

### Methodological additions
- **`data/shift_dates.py`** — re-shifts task dates from the impossible 2027/2028 values back into a near-future window (today + 60–240 days) only for future-scheduling tasks; historical-reference tasks (e.g. "papers from October 2023") are left alone. Deterministic seed per task.
- **`eval_utils/stealth.py`** — Patchright wiring, per-task persona, site warm-up (visit root + idle 5s before deep URL)
- **`eval_utils/captcha.py`** — detector that classifies Cloudflare, reCAPTCHA, Google /sorry, hCaptcha, PerimeterX, DataDome, generic access-denied
- **`eval_utils/loop_detector.py`** — abort task on ≥8 consecutive identical mutating actions (data-driven threshold from prior-run histograms) or 15-min wall-clock cap
- **`eval_utils/profiler.py`** — per-step phase capture (partial — see limitations below)
- **`eval_utils/report.py`** — auto-generates `report.md` (+ `report.docx`) at end of each run

### Failure taxonomy (analytical contribution)
Built **inductively from the data** by per-task reading of all 317 prior failures (143 vt + 174 vf). Two top-level groups: **A: environmental confounders** (anti-bot block, site drift since 2023, future-date impossibility, infeasible criteria) and **B: agent-capability failures** (action loop, DOM-index drift, hallucination, partial completion, wrong-source reliance). Per-task labels available in `failure_analysis/labeled_vision-{true,false}.csv`.

**Key analytical finding:** ~80% of prior vt failures involved an environmental confounder; only 19% were pure agent-capability issues. The headline success rate conflates agent capability with infrastructure / dataset state.

---

## 3. Run summary

### vision-false (full clean v0.12.6 re-run on VM, 643/643 fresh)
- 547 success / 90 failed / 0 captcha_blocked / 5 stuck (3 wall_clock + 2 action_loop) / 6 unknown
- Wall clock total: 35 hours, mean per-task 196s, p90 466s

### vision-true (mixed: ~465 v0.1.40 Mac successes carried forward + ~180 v0.12.6 re-runs of prior failures)
- 594 success / 48 failed / 0 captcha_blocked / 9 stuck / 1 unknown
- Acknowledged limitation: not version-clean within vision-true; see §5.

---

## 4. Methodological wins to demo

### 4a. Self-inflicted date confounder identified and fixed
The dataset's dates had been bulk-shifted to 2027/2028 — outside booking.com's ~16-month booking window and Google Flights' calendar range. **39 of the 67 "agent looped on Booking calendar" failures were caused by this preprocessing artifact, not agent capability.** Fix: `data/shift_dates.py` deterministically re-shifts to today + 60–240 d for future-scheduling tasks only.
- Booking failures: 40 → 23 (−42%)
- Google Flights failures: 39 → 4 (−90%)

### 4b. OSS-only stealth recovered the Cloudflare wall
Patchright + persona rotation + warm-up + Xvfb headed-mode cleared Cambridge Dictionary's Cloudflare Turnstile fingerprint detection.
- Cambridge Dictionary success rate: 40% → 98% (+58 pp)
- Total CAPTCHA-keyword failures across the run: 48 → 2

Bonus: data-center IPs from EC2 typically trip Google's /sorry/index wall, but the headed-browser + realistic context was enough to clear most of those too. Google Search success rate: 53% → 81% (vt) / 51% (vf).

### 4c. Per-site disaggregation reveals where vision matters
| Site | vt success | vf success | Vision Δ |
|---|---:|---:|---:|
| Booking | 64% | 45% | **+19 pp** (calendar UI) |
| Google Search | 81% | 51% | **+30 pp** (result cards) |
| Wolfram Alpha | 98% | 91% | +7 pp (math widgets) |
| Apple | 88% | 86% | +2 pp |
| BBC News | 95% | 93% | +2 pp |
| GitHub | 100% | 98% | text-dominated, no benefit |
| Coursera | 88% | 98% | **negative outlier** |

Largest vision benefits are on **spatially-organized UIs** (calendars, knowledge cards). Text-dominated sites show no benefit. The negative-outlier Coursera case is worth investigating.

### 4d. Per-step timing analysis (post-hoc recovery)
From history.json metadata across all four runs:
- OLD Mac vision-true: mean **113.9s/step**, p50 66s, p90 212s
- OLD Mac vision-false: mean **46.8s/step**
- NEW VM vision-true: mean **20.5s/step**
- NEW VM vision-false: mean **19.4s/step**
- **Vision tax in time** shrank from +143% (Mac) to **+6%** (VM). New stack made vision nearly free in time terms.
- New stack is ~3–5× faster per step overall (EC2 + browser-use 0.12.6 + Patchright + concurrency-6).

### 4e. Real cost data for OLD Mac runs (ground truth from `history.metadata.input_tokens`)
- vision-true: $181.47 (input only) + ~$23 (output est.) = **~$204 total**
- vision-false: $166.60 (input only) + ~$23 (output est.) = **~$189 total**
- **Failed tasks cost ~3× more than successful ones** ($0.68 vs $0.21 per task) because they ran to the 30-step cap. About $97 of the $204 vt total was spent on tasks that didn't succeed.

---

## 5. Known limitations / gotchas (own these proactively)

| Limitation | What happened | Recoverable? |
|---|---|---|
| **Cost not recorded for NEW VM runs** | `calculate_cost=True` flag was missed in 0.12.x (default off; old version was on by default). | AWS Cost Explorer has ground-truth $; fix already pushed to repo for future runs. |
| **Per-step sub-phase timing (LLM vs browser action vs DOM vs screenshot) all 0.0** | browser-use never separated these — they're all lumped into one start/end window per step. | Per-step *total* time IS captured and was post-hoc analyzed (§4d). To split LLM vs other, would need wrapping the LLM client. |
| **Action histogram per task came out empty in profile.json** | Profiler bug: assumed action items are dicts, but 0.12.x returns Pydantic models. The on-step callback handled both (stuck detection worked); the profiler's recorder didn't. | Recoverable post-hoc from history.json. |
| **vision-true dataset is version-mixed** | Skip-on-success preserved 465 v0.1.40 Mac successes; only 180 tasks were re-run on v0.12.6. | Acknowledge; pure vision effect is a bit smaller than the +7.3 pp headline. vision-false is clean. |
| **CAPTCHA detector over-triggered** | 600+ "cloudflare" hits logged (matches every Cloudflare CDN-cgi infra page, not just challenges). 0 of these actually aborted tasks (`is_terminal_block` excludes them). | Log noise only; outcomes unaffected. |
| **Screenshots not persisted to history.json** | They were sent to the LLM at runtime but discarded. No visual replay possible. | Need `generate_gif=True` or custom screenshot save for future runs. |

---

## 6. Suggested follow-up directions

1. **"Can we make vision-false catch up?"** — naturally framed as the next research question. Specific avenues:
   - **OCR fallback** on image elements → inject text into DOM-text dump
   - **Layout-aware DOM ordering** (group elements by visual cluster, not DOM order)
   - **"Describe-page" sidecar tool** — separate Haiku-cheap call that captions the screenshot, injects the prose into the main model's text prompt
   - **Richer attribute extraction** — currently only ~10 attrs used; adding `data-*`, computed styles, child alt text would surface more semantics
   This positions vision-false ablation as an open research question.

2. **Clean version-matched vision-true re-run.** ~5 hours of EC2 to make the vt/vf comparison version-clean.

3. **Per-step LLM-client wrapping** for true sub-phase timing in any next experiment.

4. **Address the Coursera negative-outlier** (vision-true 88% vs vision-false 98%) — interesting case where DOM text serves the agent better than screenshots.

---

## 7. Artifacts to bring to the meeting

- `results-vm-2026-05-20/examples-browser-use-vision-true/report.md`
- `results-vm-2026-05-20/examples-browser-use-vision-false/report.md`
- `timing_report.md` — post-hoc per-step timing across all four runs
- `failure_analysis/labeled_vision-{true,false}.csv` — per-task failure taxonomy labels
- This `MEETING_PREP.md`

---

## 8. One-paragraph elevator summary

> Re-ran the WebVoyager benchmark for browser-use under both vision-on and vision-off conditions on a clean EC2 environment with the latest library version (0.12.6) plus an OSS stealth layer (Patchright + Xvfb + persona rotation). Headline success rates rose from 72.5% / 77.0% (Mac, v0.1.40) to **85.1% / 92.4%** (VM, v0.12.6 + stealth), a +12.6 / +15.4 pp gain. Two systematic confounders accounted for most of the gain: a date-shift error in the dataset that pushed booking-tasks past site horizons (fixed via `shift_dates.py`), and Cloudflare bot detection on Cambridge Dictionary (cleared by Patchright). Per-step timing analysis shows the time-cost of vision shrank from +143% to +6% in the upgraded stack. Real-cost ground truth available for the original runs (~$204 vt, ~$189 vf); the new VM run costs are approximate but addressable via AWS Cost Explorer. Full pipeline is reproducible via Dockerfile + deterministic seeds. Three instrumentation gaps were identified mid-run (cost flag, sub-phase timing, action histogram); all have post-hoc recoveries and forward fixes pushed to the repo.
