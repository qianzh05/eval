# Pilot matrix analysis — run-tag pilot-2026-07-14

Run executed 02:12-03:08 PT, 2026-07-14, launched via run_overnight.sh (smoke +
alt-probe gates passed before matrix). 90/90 reps completed, zero infrastructure
errors, zero rate-limiter errors, zero bot walls observed. Vector gate 50/50.
Cost: $25.62 list-price (cache-blind; May-comparable), ~$14.10 cache-adjusted
bill estimate. Budget envelope was ~$50.

Every claim below was derived from per-rep artifacts by six parallel analysis
agents at ~03:10 and spot-verified; rep paths cited in the workflow output
(session scratchpad tasks/w42t41zzw.output) and reproducible from
results/pilot-2026-07-14/<mode>/<task>/rep<k>/.

## Headline table (passes out of 3 per cell)

| task    | off | on | auto | auto shots | note |
|---------|-----|----|------|------------|------|
| T1-1c   | 0   | 0  | 3    | 9          | WA query-interpretation trap (see story 1) |
| T1-2c   | 3   | 3  | 3    | 3          | off passes via DOM title attr, at 3x steps |
| T1-3c   | 2   | 3  | 3    | 3          | off rep1: honest DOM-blind surrender, 30 steps |
| T2-2    | 3   | 3  | 3    | 0          | locate hop bypassed by memory (all modes) |
| T2-3    | 3   | 3  | 3    | 0          | overlay credit was DOM-readable |
| T3-1    | 3   | 2  | 2    | 1          | 1 real agent failure + 1 checker artifact |
| T3-2    | 3   | 3  | 3    | 0          | agents URL-composed the query, skipping the form UI |
| T4-1    | 3   | 3  | 3    | 4          | shots were SPA-loading diagnosis, not the designed trigger |
| T4-2    | 3   | 1  | 3    | 0          | both on-mode FAILs are a checker artifact |
| P0-2    | 1   | 3  | 3    | 3          | control COMPROMISED — DOM route exists (story 4) |
| **total** | **24/30** | **24/30** | **29/30** | 17 | |

If the two checker artifacts (stories 2a/2b) are fixed: off 24, on 26, auto 30.
Per pre-commitment these corrections go through checker review + new frozen
vectors, not ad-hoc regrading.

## Story 1 — T1-1c (0/0/3): a real WA ambiguity, three mode-specific behaviors

All 9 reps found year=2020 on GitHub and passed the URL gate. The terse query
`average US unemployment rate 2020` renders the MONTHLY series (Result pod:
"6.7% (December 2020)"), not the annual 8.1 pod.
- **off** (3 FAIL): cannot see the pod; the only textual value is a tooltip
  anchor title="6.7 percent" after clicking the Result section. All three
  asserted 6.7 (an enumerated distractor). Two reps first wrote the memorized
  8.1 and then *self-corrected to the observed wrong value* — grounding
  overriding correct memory.
- **on** (3 FAIL): saw "6.7% (December 2020)" on the screenshot, correctly
  rejected it as monthly, then all three clicked WA's "referring to
  socioeconomic data" assumption link and reported the World Bank/ILO pod value
  **8.06%** — non-enumerated, so FAIL with final_assertion null.
- **auto** (3 PASS): reps 2/3 phrased the query naturally-verbosely
  ("average unemployment rate in the United States in 2020") which WA
  interprets as the annual pod (8.1), then read it from one requested
  screenshot. Rep1 started with the same terse query as the failures but
  recovered by re-querying (7 screenshots, 23 steps) until the annual pod
  rendered.

Classification: agent-limited (query formulation + recovery) on a genuine
environment ambiguity. OPEN POLICY QUESTION for Frank/Harsha: is 8.06 (World
Bank 2020 estimate, reached via WA's own assumption toggle) a defensible
second gold? Current spec says no; the pre-commitment says such cases go to
task-defect review. n=3 caveat: the terse-vs-verbose phrasing split across
modes is partly sampling luck; auto/rep1 shows mode-independent recovery is
possible.

## Story 2 — two checker defects found by the pilot (both survived the 50-vector gate)

**(2a) T4-2 trailing-reference false-FAIL (2 reps).** Both failing on-mode
answers assert the gold: "starts at **From $1,399**" — then append "For
reference, the other chip option (10-core CPU, 8-core GPU) starts at $1,299."
Checker recorded final_assertion='1299'. This contradicts the task's own
tolerance spec: gold was present, and the v3 attribution tokens ('8-core'
scoped to 1299, "trailing comparisons pass") should exempt exactly this
phrasing. Off/rep1 phrased the same comparison with 1399 last and PASSed —
last-price-wins is doing the work, not the attribution exemption. NOT a
vision effect. Serialized final-page state confirms the agents read the
correct tile (Sky Blue checked, $1399 on the 10-core tile).
→ Checker owner: fix attribution-token scoping for T4-2-style trailing
  references; freeze both failing answers as new PASS vectors.

**(2b) T3-1 excluded-IDs false-FAIL (1 rep, auto/rep1).** The answer states
exactly gold SET-A as the in-range result, then transparently lists the four
out-of-range API hits "submitted 2020/2021, outside the requested range."
The whole-answer regex extraction counted those as extras → set-mismatch.
Semantically this is a correct, well-evidenced answer.
→ Checker owner: decide whether set-extraction should exempt IDs inside
  explicit exclusion clauses (mirrors the string-rule negation exemption);
  freeze this answer as a vector either way.

**(2c) T3-1 on/rep2 is a REAL failure worth keeping**: the arXiv API route
never rendered 1906.06818's ID into extractable text; after 7 failed
scroll/extract attempts the agent FABRICATED the identifier "1905.11027" for
the right paper (correct title/authors/date, wrong ID) and submitted it.
DOM-occlusion-induced hallucination — the same mechanism as May's ArXiv--39
confabulation finding. This one is legitimately agent-limited.

## Story 3 — auto opt-in mapping (trigger validation, the pilot's core question)

16/17 screenshot requests fired where the answer was literally not in
extractable DOM text (15 on WA image pods incl. T1-1c's 7-shot recovery loop,
3 on the pyramid PNG; T4-1's 4 were blank-SPA loading diagnosis); 1 was a
reactive form-state check on arXiv advanced search. ZERO requests fired at
any DOM-solvable designed trigger:
- T2-2: "Use this model" panel — snippet was in the serialized DOM without
  driving the UI, AND all reps navigated straight to bartowski's repo from
  memory (the gen-2 locate hop never happened).
- T2-3: MediaViewer overlay reached as designed, but the credit was
  DOM-readable in the overlay.
- T3-2: agents composed the full filter query in the URL bar, collapsing the
  compose-then-verify window (exactly the trigger note's stated caveat).
- T4-2: read per-tile DOM prices after one swatch click; never confirmed the
  visual selection ring.

Interpretation: auto-mode opt-in is need-driven (pixels-only content), not
uncertainty-driven. The T2/T3/T4 trigger *moments* exist but the model
solves them from DOM and does not look. For full-suite design: T1/P0-style
rendered-value tasks reliably provoke requests; overlay/form/picker tasks
measure *ability to skip*, which is itself the paper's point — but they will
not generate opt-in events at scale.

## Story 4 — P0-2 positive control is COMPROMISED (task-defect, swap it)

The off-mode PASS (rep2, 19 steps) was not parametric memory: Wikipedia's
media viewer exposes the image's source link (ingldata.com/jp/) in the DOM;
the agent followed it, set the year slider to 2026 via JS, and read the SVG
text nodes — female 75-79 = "3.9%" verbatim (the site generated the PNG, so
values match exactly). A deterministic DOM route to the gold value exists one
hop from the article. Corroboration that memory alone does NOT pass: rep3
guessed from memory and produced 4.0 (FAIL); rep1 tried genuine canvas pixel
analysis and honestly declined to answer. Vision arms (on/auto) passed 3/3 by
reading the rendered pyramid.
→ Per the task's own pre-commitment: swap in backup pilot-P0-1 (arXiv
  2312.10997v5 Figure 2) for the full run, or restrict the control's domain
  scope. Decision belongs to Frank (+ checker owner for the record).

## Story 5 — cost/efficiency (the May-comparable numbers)

- Mode totals (list-price): off $12.18, on $6.40, auto $7.04.
  Cache-adjusted: off $7.25, on $2.84*, auto $4.01 (*on-mode lower bound —
  its reps report 0 cache-creation tokens despite 67% cache-read share; an
  accounting gap in browser-use 0.13.2's vision invocation path).
- Steps/duration means: off 10.6 steps / 128s; on 4.6 / 74s; auto 6.5 / 83s.
- Per step, vision costs MORE (+24%: 14.1k vs 11.2k input tokens/step) but
  finishes in 56% fewer steps — on this suite the efficiency win is entirely
  step-count reduction (extraction attempts, scrolling, and retry loops that
  vision skips).
- Both-succeed on/off cost ratio (5 cells where both are 3/3): mean of
  per-task ratios 0.96 list-price (median 0.94; range 0.20-1.54), 0.71
  cache-adjusted. **May's number on WebVoyager was 1.46x.** On tasks built
  around screenshot-trigger moments, the vision premium disappears and
  reverses.
- Auto: 29/30 success at 0.58x off's list cost — best success, near-best cost.
- P0-2 exclusion from the success pool is moot for the ratios (off never got
  3/3 there).

Scoring-side note: score_pilot.py's cache-cost formula was corrected post-run
(uncached = prompt - cached; creation additive, matching browser-use 0.13.2's
prompt_tokens definition) — verdicts unaffected, summary.json regenerated;
independent recomputation matches ($14.10).

## Run-day evidence trail

- One-GET rechecks + phrasing sweep (pre-launch, all green):
  artifacts/phrasing_sweep_2026-07-13.json
- Smoke + alt-probe: results/pilot-2026-07-14-smoke/, -altcheck/. Type1
  alt-text question RESOLVED: pod value reaches the no-vision arm via
  `<a title=17.3>` in the serialized DOM (a-title, not img-alt as frozen) —
  Type1 stands per pre-commitment; contingency not fired.
- The night was event-monitored; no interventions were needed.

## Recommended next steps (for Frank)

1. Checker review with the other session: fix 2a (attribution scoping) and
   decide 2b (exclusion-clause exemption); add ≥3 new frozen vectors from
   tonight's real answers. Re-score (deterministic, free).
2. Decide the P0 swap (P0-1 backup) and the T1-1c 8.06 policy before the
   full run.
3. Full-suite design implications: (a) rendered-value tasks are the reliable
   opt-in generators; (b) memory-recallable URLs collapse locate hops — pick
   obscurer targets or verify the hop actually happens; (c) URL-composable
   filter tasks will skip form UIs; that is data, not failure.
4. Draft Harsha update: pilot ran end-to-end for ~$26 list / ~$14 actual,
   9 of 10 tasks behaved, headline = vision premium inverts on trigger-built
   tasks (0.96x vs May's 1.46x) and auto is the efficiency frontier
   (29/30 at 0.58x cost) — with the caveats above and n=3 per cell.
