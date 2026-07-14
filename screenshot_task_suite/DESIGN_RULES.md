# Screenshot Task Suite: Design Rules

v0.2.3 (see Change Log; originally drafted 2026-07-06). Status: binding spec;
generation-2 pilot tasks proposed 2026-07-11 in tasks/pilot_tasks.json, under
review.
These rules are fixed before task authoring begins. Any later change gets
logged in the Change Log at the bottom with a reason.

## 1. Purpose

A suite of 50 to 100 custom web tasks that stress the screenshot decision in
web agents. The suite exists to answer one question at acceptable cost:

> On tasks where current agents demonstrably want screenshots, does attaching
> them change success, and what does each mode cost?

Primary metrics: cost per successful task (tokens and dollars) and latency.
Success rate is reported as non-inferiority, not superiority (Section 7).

Why custom tasks instead of an existing benchmark: on WebVoyager the signal is
buried under environmental noise we have measured directly (31 of 90 DOM
failures were verified bot walls; further tasks fight recoverable walls or get
silently degraded pages), tasks are stale (2025 dates), and the LLM judge is
modality biased. Sites here are chosen to tolerate automation and every check
is deterministic, so the screenshot variable is isolated.

## 2. Opt-in criterion (what makes a task belong in the suite)

Derived from the labeled analysis of all 91 screenshot requests the model made
in auto mode across 1,841 steps. Per-request ledger:
screenshot_request_analysis.csv (committed 2026-06-12) — the table below is
the 2026-06-14 Notion tally; the two agree exactly on the genuinely
informative categories (overlay 13, form 5, rendered 5) and differ only
within the three rarely-informative ones, where the CSV has nav-reconfirm 34
/ stuck 26 / orientation 8. (Citation corrected 2026-07-09: this section
previously cited auto_screenshot_findings.md, which contains a different,
overlapping stated-reason grouping, not this table.) The observed trigger
categories and counts were:

| Category                                   | Count | Genuinely informative? |
|--------------------------------------------|-------|------------------------|
| Reconfirming a page that had not loaded    | 37    | rarely                 |
| Stuck-interaction loops                    | 22    | rarely                 |
| Blocking overlay the DOM text missed       | 13    | yes                    |
| Start-of-run orientation                   | 9     | no                     |
| Pre-submit form checks                     | 5     | sometimes              |
| Reading rendered output                    | 5     | yes (decisive once)    |

Rule: every task must contain at least one step that falls in a trigger
category, with the suite weighted toward the two categories where screenshots
genuinely revealed hidden state:

- T1 Rendered output: the answer is computed or rendered client-side where
  text extraction is unreliable (the Wolfram Alpha pattern).
- T2 Blocking overlay / dynamic UI state: a popup, modal, or revealed panel
  changes what actions are possible (the Booking sign-in popup pattern).
- T3 Pre-submit verification: a multi-field form where correctness of the
  filled state matters before committing.
- T4 Large-target visual interaction: flows completed by the vision-only agent
  through coordinate clicks (search boxes, result cards, swatches, pickers).
- P0 Positive controls: the answer exists only in an image (e.g., a map or
  chart with no alt text), so vision must beat DOM. If it does not, the
  instrument is broken and null results elsewhere are uninterpretable.

Target mix: roughly 35% T1, 20% T2, 20% T3, 15% T4, 10% P0. The criterion is derived
from the agents' observed behavior, not from our judgment of where vision
"should" help. That is the defense against the charge that tasks were built
for vision to lose.

## 3. Site shortlist

Allowed (clean across our runs; no walls observed): arxiv.org, wikipedia.org,
github.com, wolframalpha.com.

Pilot-gated (usable if 10-task pilot shows no walls): huggingface.co (2 walls
observed in June runs), coursera.org (1), apple.com (2, on login paths only;
tasks must avoid login).

Banned (verified walls or degraded serving in our data): all Google
properties, booking.com, allrecipes.com, dictionary.cambridge.org, espn.com,
bbc.com.

Additional constraints: no login, no purchase, no state mutation on live
sites; content expected stable over at least one month; every task re-runnable
without cleanup.

## 4. Task specification format

Each task is one JSON record: id, site, trigger category (T1-T4 or P0), prompt,
answer spec, check type, authored date, plus a freeform note on why the task
triggers the category. All tasks live in tasks/ in this directory, one file,
version controlled.

## 5. Verification

Deterministic checks only, written at authoring time:

- string match with tolerance rules stated per task (case, whitespace,
  rounding; the WebArena 6.495-vs-$6.50 failure is the cautionary case);
- URL state (final URL contains a specified pattern);
- set match for multi-item answers (order-insensitive unless specified).

No LLM judge in the primary metric. If a judge is ever used for a secondary
analysis, it must receive identical evidence from every arm (the GitHub--33
artifact, where verdicts depended on whether a screenshot existed, is the
cautionary case).

Tolerance policy (added v0.2.2): wide across FORMATS of the one correct
value, strict across VALUES. Mechanically: normalize the final answer, match
the gold with a boundary-aware pattern, list each task's plausible-wrong
distractor values (or a value band) at authoring time, and apply one
pre-stated hedge rule - a competing value asserted after the gold fails the
answer; negated or explicitly-attributed mentions of a distractor are
exempt. The executable form is _meta.check_semantics in
tasks/pilot_tasks.json and is the check runner's contract. Rationale: a
format-brittle check injects noise asymmetrically across arms (the vision
arm transcribes rendered pods verbatim; the DOM arm quotes extracted text),
which is bias in the exact comparison this suite exists to make.

## 6. Run matrix

| Dimension | Values |
|-----------|--------|
| Vision    | on (attach every step), off. Auto runs in the pilot only (Section 9); adding it to the full matrix is a later, optional purchase |
| Repeats   | 3 per cell; 5 where any two repeats disagree |
| Agent     | browser-use 0.13.2 pinned (primary); second agent in a later pass |
| Model     | us.anthropic.claude-sonnet-4-6 (primary); one cheaper model on the final suite if budget allows |

Per-run capture (existing profiler): success, steps, input/output tokens,
cost, think/wait/act timing, per-step log, screenshots where attached.
Wall/anti-bot incidents are logged per run and reported under every arm; a
task that develops a wall mid-study is reported, not silently dropped.

## 7. Statistical framing

At 50 to 100 tasks, superiority claims about success rate are out of reach
(the June benchmark memo's power analysis applies: order of +/-8pp at n=130).
The suite therefore claims:

- Cost and latency: estimated per-arm with confidence intervals; this is the
  headline result and is well powered.
- Success: non-inferiority of vision-off relative to vision-on with a margin
  of 5 percentage points on the paired difference, analyzed on discordant
  pairs (McNemar-style), repeats aggregated per task by majority.

The margin is set here, before any data. If vision-off is worse by more than
the margin, that is the finding and it gets reported as such.

## 8. Reporting commitments

Every authored task is reported, including tasks that turn out broken or
walled; no post-hoc filtering. The failure-classification rubric (agent-limited
vs environment-limited vs task-defect) is written before the full run, as in
the auto-mode analysis. Task authorship, run data, and analysis code are
committed to this directory.

Shortcut contamination (added v0.2.2, defined before the pilot): a run whose
trajectory shows the answer was derived without exercising the task's
trigger surface (e.g., mental arithmetic in the reasoning; the task's
results-URL backstop never satisfied) is logged shortcut-contaminated and
EXCLUDED from trigger-validation analysis (auto opt-in rates); its
success/failure still counts in the success comparison. A compute-then-
confirm run (agent derives the value, then visits the page and verifies)
satisfies the backstop and is NOT contaminated.

## 9. Pilot

10 tasks (mix of T1-T4 plus one P0, at least one per pilot-gated site) through the full
matrix before the remaining tasks are authored. The pilot measures: per-run
cost (replaces the estimate below), check flakiness, wall incidence, and
whether auto mode actually opts in on the trigger steps as the criterion
assumes. Authoring the remaining 40 to 90 tasks proceeds only after pilot
review.

## 10. Cost estimate (to be replaced by pilot numbers)

600 to 1,000 runs (100 tasks x 2 arms x 3-5 repeats; auto adds a third arm
only if purchased later). Observed actual billed cost in the May rerun was
well under token-sheet estimates due to prompt caching (~$250 actual for ~377
runs, ~$0.66/run). Working estimate: $400 to $800 for the full matrix, plus
~$50 for the pilot. Requires sign-off before the full run; the pilot proceeds
within existing budget.

## 11. Timeline (working)

Week 1: rules review + pilot task authoring + pilot run.
Weeks 2-3: author remaining tasks; second-pass fixes from pilot.
Week 4: full matrix run.
Week 5: analysis + writeup.

## Change Log

- v0.1 (2026-07-06): initial draft.
- v0.2 (2026-07-07): auto moved to pilot-only (cost); added P0 positive
  controls; mix reweighted; cost estimate updated for two-arm matrix.
- v0.2.1 (2026-07-09): corrected Section 2's source citation (was
  auto_screenshot_findings.md, which holds a different overlapping grouping;
  the committed per-request ledger is screenshot_request_analysis.csv) and
  noted the CSV/Notion count difference (confined to nav/stuck/orient). No
  change to categories, weighting, or any rule. New authoring rule from
  pilot-task verification: chart-value-reading tasks must verify at
  authoring time that the rendered granularity is viewport-independent — a
  GitHub code-frequency pilot task was retired after its chart proved to
  bin by viewport width (quarterly at 1298px, half-year at 900px), making
  any displayed value environment-dependent.
- v0.2.3 (2026-07-11): generation-2 pilot tasks after advisor feedback of
  2026-07-10 (tasks should require multi-page navigation; specifications say
  what is desired, not how to execute). The three single-query wolframalpha
  tasks were retired to alternates and replaced by two-site chains
  (github -> WA 2020 unemployment; wikipedia -> WA 1923 CPI, dual gold
  17.3/17.1; arxiv -> WA 2018 inflation 1.91); all surviving prompts and
  start_urls de-prescribed (the arxiv advanced-search start page itself
  prescribed a route; huggingface and apple tasks gained locate/storefront
  hops). First use of Section 5's URL-state check type, as a SUCCESS-GATING
  component on the three chained tasks: the logged WA query must contain the
  correct year and topic. Reason: CPI 1924 equals 1923 on both accepted
  values (and Dec 1927 = 17.3), so the answer string alone can never prove
  the right year was queried; and 2020's 8.1% unemployment is memorized, so
  without the gate a memory answer passes without visiting either site.
  Decided before any run (Frank, 2026-07-11). Checker extended
  (decimal/dual golds, url_gate); vector gate green at 38/38.
- v0.2.2 (2026-07-09, after an independent verification pass on the pilot
  tasks): added the Tolerance policy to Section 5 (wide-across-formats /
  strict-across-values, named distractors, pre-stated hedge rule; executable
  form in tasks/pilot_tasks.json _meta.check_semantics) and the shortcut-
  contamination definition to Section 8. Section 4's record format and
  Section 9's pilot mix now name P0 explicitly (Section 2 already defined
  it). Header updated from "Draft v0.1" to track the Change Log. Trigger for
  the policy: the verification pass showed a hand-written tolerance clause
  can fail both directions (false-fail on verbatim pod transcription -
  biased against the vision arm - and word-order-dependent false-pass on
  hedges), and a gold set can silently depend on hidden form state (arXiv's
  date-type radio: default returns 3 papers, the other two radios 4).
