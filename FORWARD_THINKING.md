# Forward-thinking: what comes next and why

_Companion to MEETING_PREP.md. The point of this doc is to demonstrate that the current run isn't an endpoint — it opens specific, falsifiable research questions, and there's a reasoned plan for which to pursue first._

---

## The intellectual position the current data puts us in

Three findings from this round, taken together, frame an unresolved research question:

1. **Vision adds about +7.3 pp success on this benchmark.** Real but modest.
2. **The vision benefit isn't uniform** — it concentrates on a small number of spatially-organized sites (Booking +19 pp, Google Search +30 pp). Most sites show 0–3 pp.
3. **The new stack made vision nearly free in time terms** (+6% per step vs +143% in the old stack), but vision still ~doubles per-task token cost.

This raises a question that the current data **doesn't answer**: is vision **fundamentally necessary** for the sites where it helps, or is current vision-false performance just **bottlenecked by poor text extraction**?

If the answer is "fundamentally necessary," the path forward is to optimize vision (cheaper image tokens, smarter sampling). If the answer is "bottlenecked text extraction," the path forward is to improve the DOM-text representation — potentially achieving vision-comparable scores at a fraction of the cost.

This is a falsifiable, publishable question. The current run is the **baseline** for testing it.

---

## Three concrete next experiments, prioritized

### Experiment 1 (highest priority): "Can vision-false catch up via richer text?"

**Hypothesis:** for at least half of the sites where vision currently helps, the gap is closeable through better text-only context, not fundamental visual reasoning.

**Design:**
- Implement three text-enrichment interventions, ablated independently:
  1. **OCR fallback** — for every image element in the page, extract any text in it (Tesseract is fine for v1, ~$0 per page)
  2. **Layout-aware DOM ordering** — instead of dumping interactive elements in DOM order, cluster them by visual position (top-left, top-right, center, sidebar, etc.) using their bounding-box coordinates from `buildDomTree.js` (browser-use already collects this; we just don't use it)
  3. **Describe-page sidecar** — a separate cheap LLM call (Haiku) gets the screenshot once per step and outputs a 200-word natural-language description; this prose gets injected into the main model's text prompt. The main model never sees the image.
- Run each ablation + their combination on the 7 sites where vision-true currently beats vision-false by ≥3 pp.
- Compare: ablation success rate vs vision-false baseline vs vision-true ceiling.

**What we'd learn:** which mechanism (visual signal, spatial layout, image content) is doing the work. If layout-aware ordering alone closes 60% of the gap, that's a huge finding — it means most of vision's benefit is spatial, not content-based, and is achievable with cheap geometric reasoning rather than image tokens.

**Cost & timeline:** ~4 hours of EC2 + ~$30 in Bedrock for the targeted re-run. 1 week of implementation work.

**Risk-mitigation:** start with just 50 tasks (the highest-impact sites) before committing to a full re-run. Hold the main run constant.

### Experiment 2: Understand the Coursera anomaly

**Observation:** Coursera is the only site where vision-false **outperforms** vision-true (98% vs 88%). That's a 10 pp negative effect of vision.

**Hypothesis:** Coursera's screenshots contain elements that confuse the model (heavy ad/product imagery diverts attention from the search-result list).

**Design:** read all 5 vision-true Coursera failures by hand; check what the agent was attending to in its reasoning trace; identify whether the model was distracted by visual content vs. the DOM elements it should have been clicking. Then test a hypothesis: if we serve a *cropped* screenshot (just the search-result area), does vision-true recover?

**What we'd learn:** when vision actively hurts. This is an interesting result for the field — most "vision helps" papers don't characterize when it hurts.

**Cost & timeline:** 2 days of qualitative analysis + ~$2 of EC2 for the cropped re-run. Could be a section of a future paper.

### Experiment 3: Cross-model generalization

**Hypothesis:** the size of the vision benefit depends on the model's text-reasoning strength. Stronger text reasoners may need vision less.

**Design:** repeat the cleanest comparison (vision-true vs vision-false) with three other models:
- Claude Haiku 4.5 (cheaper)
- Claude Opus 4.6 (stronger)
- GPT-4o or Gemini Pro 2 (different family)

**What we'd learn:** whether vision is a "compensating" or "amplifying" capability — does it help weak models more (compensation) or strong models more (amplification)? Either result is publishable; the answer informs deployment economics.

**Cost & timeline:** ~$1500 in API costs at full 643 tasks × 3 models × 2 vision conditions. **Don't do this yet** — gate on Experiment 1 first.

---

## Risks I've already thought through and would call out

| Risk | Mitigation |
|---|---|
| Re-running with new code may regress on tasks that worked before | Smart-skip logic preserves successful-prior-with-same-prompt results; comparison stays anchored on a baseline. We already use this. |
| 0.12.6 → 0.12.7 might break the pipeline mid-experiment | Pin the exact version (`browser-use==0.12.6`). Don't upgrade mid-experiment. Already done. |
| Anti-bot vendors update their detectors — what passed today may fail in 3 months | Reproducible Dockerfile + manifest means re-runs can be done; results are timestamped. Treat each run as a snapshot of the time period. |
| Free-tier OSS stealth eventually breaks against enterprise Cloudflare / Akamai | We deliberately scoped this run to OSS-only. If the gap to "real-world deployment" becomes the research focus, residential proxy + paid solver layer can be added in ~1 day of work. Pricing already scoped (~$30-50/month). |
| LLM cost growth makes 4-model ablation expensive | Run smaller (100-task) subsets first to establish whether the effect even exists before committing to full benchmark. |

---

## What this work positions me to do next

A coherent ~3-month research arc:

- **Now → 2 weeks:** Experiment 1 (text-enrichment ablation). This is the highest-novelty, lowest-cost direction. If it works, it changes the cost calculus for deploying web-browsing agents.
- **2-4 weeks:** Experiment 2 (Coursera anomaly + qualitative analysis). Cheap to do; produces a methodological observation that strengthens a paper.
- **5-8 weeks:** Build out the failure taxonomy work into a stand-alone methodology contribution. The taxonomy I built (A1-A4 confounders, B1-B6 capability failures, C1-C2 evaluator artifacts) is itself novel — most web-agent benchmark papers don't separate these. Could be a methods paper for benchmark studies.
- **8-12 weeks:** If Experiment 1 produced a positive result, Experiment 3 (cross-model generalization) validates it. If it produced a null result, the conclusion ("vision is genuinely needed for sites X, Y, Z") becomes itself the finding.

Net: this run is the **baseline experiment** for at least one publishable paper, possibly two (a methodology paper on benchmark confounders + an empirical paper on vision-vs-text trade-offs).

---

## One paragraph the prof will remember

> "The current run gave us a solid baseline — 85% (vision-off) and 92% (vision-on) success after stealth and date-confounder fixes — but the methodological contribution I'm more excited about is the failure taxonomy: 80% of the failures in the original benchmark were environmental confounders, not agent-capability gaps. That changes how to interpret all WebVoyager numbers in the literature. The natural next experiment is whether the +7 pp vision benefit is genuine or whether it's an artifact of impoverished DOM-text extraction — a clean ablation against OCR + layout-aware ordering + a describe-page sidecar would tell us. That's a $30, one-week experiment, and the result either way is publishable."
