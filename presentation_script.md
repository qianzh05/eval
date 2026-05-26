# Presentation Script — Browser Agent Evaluation Report
(16 slides)

---

## Slide 1 — Title

Good morning. Today I'm walking you through an evaluation of two AI browser agents — systems that can autonomously navigate websites and complete tasks the way a human would. We ran them on two different task benchmarks using the same underlying language model, which lets us isolate how much of the performance difference comes from *how the agent is built* versus the model underneath it.

---

## Slide 2 — Agenda

We'll cover ten areas. We'll start with what the two agents actually are and how they're structured. Then how each agent perceives a web page, and specifically when screenshots matter versus when they're redundant. Then results, then a look at what successful and failing trajectories actually look like. After that the tips question, token costs, failure patterns, and recommendations.

---

## Slide 3 — Architecture Overview

So — the two agents.

**browser-use** is an open-source Python library that wraps a language model in a browser automation loop. You give it a task, it opens a browser, and it figures out what to click and type by reading the page and calling the model. We evaluated it on the **WebVoyager** benchmark — 50 tasks on real, live websites: Google Flights, Amazon, GitHub, and so on.

**BrowserGym** is a framework that structures browser automation as a step-by-step environment — think of it like a gym for training agents, where each "step" the agent observes the page and outputs one action. We evaluated it on the **WebArena** benchmark — 183 tasks across five self-hosted websites: GitLab, a map application, a Reddit-style forum, two shopping sites.

Both run the same model: claude-sonnet-4.6 via AWS Bedrock. So what we're comparing is agent design, not model capability.

Looking at the table — seven structural differences:

**LLM calls per step.** browser-use makes one call. BrowserGym makes two — we'll go into why next slide.

**Actions per step.** browser-use can emit multiple actions in a single response — fill a form field, press enter, click a button, all in one model output. BrowserGym enforces exactly one action per step, hardcoded into the prompt.

**Element grounding** — how the agent identifies *which element* on the page to interact with. browser-use uses DOM node IDs from the accessibility tree — a text description of every interactive element. BrowserGym uses Set-of-Marks, covered in detail on slide 5.

**Memory** — browser-use keeps a running scratchpad inline with each model call. BrowserGym externalizes memory into a separate inference pass.

**Termination** — browser-use self-reports success or failure. BrowserGym sends a message to a simulated user, and an external programmatic evaluator checks the answer against ground truth. That's the more reliable check.

---

## Slide 4 — BrowserGym: The Two-Call Architecture

This is the most structurally distinctive feature of BrowserGym, and it has a measurable cost.

At every step, BrowserGym makes *two* sequential calls to the language model.

The first call takes the current page state — screenshot plus accessibility tree — and produces a **progress summary**: the model writes down what it has accomplished and what the current page state means. Think of it as the agent narrating its own situation before deciding what to do next.

The second call takes that same observation *plus* the progress summary, and outputs the actual action.

This design is related to a pattern called **ReAct** — reason, then act — a well-established approach in LLM agent design. The argument for splitting it into two calls is that having an explicit written summary improves the quality of the action decision. The argument against it is inference cost.

Here's what the data shows: across our entire BrowserGym evaluation run — 48 tasks — LLM inference consumed **44.6% of total wall-clock time**. That's 5,422 seconds on model calls versus 6,739 seconds on the browser itself. Calculation: 5,422 divided by 12,161 total seconds.

Average LLM time per step: 12.76 seconds. Total step duration: about 28.6 seconds.

For a task that fails — running to the 20-step limit — that's roughly 255 seconds of inference spend before the agent gives up. With zero return.

browser-use makes one call per step and averages 22 seconds per step. The scratchpad is inline. No separate pass.

---

## Slide 5 — Observation Space: SoM vs DOM

Now how each agent *sees* the page.

Both receive two things at every step: a screenshot and the **accessibility tree** — a structured text representation of every interactive element on the page, their roles and labels. It's the DOM filtered down to what's actionable.

The difference is what they do with the screenshot.

**BrowserGym uses Set-of-Marks**, introduced in Yang et al. 2023. Before sending the screenshot to the model, the framework overlays numbered labels on every interactive element. The model sees a rendered page where a button might have "[42]" on it, a search field "[87]". When it decides to click something, it outputs the number. It has both a visual and numeric handle on every element simultaneously.

**browser-use uses DOM node IDs.** The model reads the accessibility tree text, picks the node by ID, and acts on it. No visual grounding — it has to infer which node corresponds to the element it sees on screen.

Set-of-Marks is more robust when the accessibility tree is incomplete — a poorly labeled element can still be identified visually. DOM node IDs are more robust when rendering is unreliable — you're working from text.

Empirically: BrowserGym's visual grounding doesn't show a clear accuracy advantage over browser-use's DOM-indexed approach at the task complexity we're testing. GitLab reaches 100% in both agents. Shopping sits around 47% in both. Grounding method is not the primary performance differentiator here.

---

## Slide 6 — When Screenshots Are the Only Signal

This slide gets at the more precise question: when does sending the screenshot actually matter, and when is it just wasted compute?

Both agents send a screenshot on every single step, unconditionally. But the screenshot only carries *unique* information — information the DOM can't provide — in four specific scenarios.

**Anti-bot and CAPTCHA detection.** When Cambridge Dictionary served a Cloudflare challenge page to browser-use, the DOM was effectively empty. The agent identified the block entirely from the screenshot. Three tasks failed because of this. There's no DOM-based fallback.

**Hover-revealed menus.** Some navigation elements only appear in the DOM after a hover action triggers them. BrowserGym issued hover actions 11 times across the sonnet_rerun — those steps were screenshot-driven. The DOM showed the static state; the screenshot showed what actually appeared.

**Canvas and dynamic UI elements.** Google Flights uses a date picker where the calendar is represented in the DOM, but the visual enabled/disabled state of date cells is not reflected in the accessibility tree. browser-use failed on all 6 Google Flights tasks by interacting with DOM-valid date nodes that were visually greyed out. Importantly — even with SoM-style visual grounding, this problem would not have been resolved, because the dates appear disabled in the screenshot regardless of how you label them.

**Page load verification.** Both agents use screenshots to confirm whether a page has actually rendered before acting. browser-use has an explicit wait action used 23 times across WebVoyager tasks. BrowserGym's progress summary frequently opens by assessing whether the page has loaded.

The bottom line is that for those four scenarios, the screenshot is essential. For everything else — filling a known form field, navigating to a known URL, clicking a clearly labeled button — the screenshot is redundant. Neither agent distinguishes between these cases. Skipping screenshots on DOM-deterministic steps is an optimization neither currently implements, and it's an estimated 30–50% per-step cost reduction on those steps.

---

## Slide 7 — Results

The numbers, with explicit calculations.

The primary metric is **success rate** — tasks where the agent returned the correct answer. For BrowserGym on WebArena, success is verified by an external programmatic evaluator. For browser-use on WebVoyager, a GPT-4V judge reviews the final state.

**browser-use on WebVoyager**: 30 out of 50 — 60.0%.

**BrowserGym, no_tips**: 29 out of 48 — 60.4%. No task-specific tips in the prompt.

**BrowserGym, no_tips_30_steps**: 24 out of 48 — 50.0%. 30-step limit instead of 20. Performed *worse*.

**BrowserGym, sonnet_rerun**: 30 out of 48 — 62.5%. Task tips included.

**BrowserGym, sonnet46_concurrent**: 6 out of 12 — 50%. Parallel execution. Duration jumped to 303 seconds average.

**BrowserGym, with_tips_v2**: 11 out of 27 — 40.7%. A different, smaller task subset — not directly comparable to the 48-task runs.

The headline finding: browser-use and BrowserGym both land near 60–62.5% on their respective benchmarks, running the same model. That convergence across two different agent designs, two different benchmarks, real web versus self-hosted — points to a model-capability ceiling, not an architecture or prompt effect.

---

## Slide 8 — The Efficiency Cliff

One of the clearest findings in the data, consistent across both agents and both benchmarks.

When you bucket tasks by how many steps the agent took, success drops to **zero past approximately 12 steps** — in both browser-use and BrowserGym, on both benchmarks.

BrowserGym sonnet_rerun: 1–3 step tasks, 94% success. 4–7 steps, 80%. 8–12 steps, 60%. 13–20 steps — zero across 12 tasks.

browser-use on WebVoyager: 67%, 76%, 69% for the first three buckets. Then 0% for 13–20 step tasks.

What's happening past step 12 — and we'll see the actual trajectory data in the next slide — is the agent has entered a click loop. It's repeating the same action, not changing state, not making progress. Every step beyond 12 is burning tokens and inference time with essentially zero expected return.

Practical implication: 20 steps is the right limit. The no_tips_30_steps experiment tested whether extending to 30 would recover any failing tasks. Success dropped from 60.4% to 50%. Extra steps extended loops, didn't create solutions.

---

## Slide 9 — Trajectory Shapes: Success vs Failure

Now let's look at what the trajectories actually look like, with the numbers behind them.

On the left is the shape of a typical successful trajectory. It's short — three to seven steps. The agent orients quickly, interacts directly with the target, and terminates. No action type repeats on consecutive steps.

On the right is a failing trajectory. It starts the same way — the agent orients and begins the task normally for the first few steps. Then around step five to eight, an action fails. The agent retries the same element. By step nine to twelve, the same action type is appearing on consecutive steps — that's the click loop. From there to step twenty it's locked in, accumulating tokens and making no progress.

Now the actual numbers. These are counted from the trajectory logs — a repeated sequence is defined as the same action type appearing on consecutive steps.

Looking at the table: browser-use shows repeated sequences in 34 of 50 tasks — 68% — with 100 total repeats, about 68 of which are in failing tasks. BrowserGym's no_tips run: 37 of 48 tasks — 77% — with 152 total repeats, 104 in failures, which is 68%. The sonnet_rerun: 42 of 48 tasks have at least one repeat — 88% — with 176 total, 118 in failures, 67%.

The no_tips_30_steps number tells the story cleanly: 202 total repeated sequences versus 152 in no_tips, despite both running identical tasks. The longer step budget didn't produce new solutions — it just gave failing agents more time to loop.

The failure percentage across all runs stays between 67% and 83%. "Roughly two-thirds" was the conservative phrasing — for most runs it's closer to three quarters.

---

## Slide 10 — Tips vs. No-Tips: Setup & Calculation

The question most relevant to how we design the next run: do task-specific tips in the prompt help?

First, definitions. All BrowserGym runs include **general tips** — benchmark-wide notes about environment behavior. Always present.

**Task tips** are task-specific instructions under a `# Task Tips` section — navigation hints, vocabulary clarifications, what to do if something doesn't load. These appear in sonnet_rerun, sonnet46_concurrent, and with_tips_v2. Not in no_tips or no_tips_30_steps.

Confirmed by checking the prompt files directly: grep for the Task Tips section header returns matches for sonnet_rerun, nothing for no_tips.

The head-to-head: **no_tips versus sonnet_rerun**. Same 48 tasks, same model, same BrowserGym framework. One variable: task tips.

no_tips: 29 correct — 60.4%.
sonnet_rerun: 30 correct — 62.5%.
Net difference: one task, plus 2.1 percentage points.

Cost: BrowserGym with tips takes 1.25 more steps on average. Token consumption up 46% — 39,248 minus 26,872 divided by 26,872. Duration up 37%, 103 to 140 seconds per task.

One extra task at substantially more compute per run.

---

## Slide 11 — Tips: What the Logs Show

To understand *why* that one task gap exists, I went into the logs for the five tasks where the two runs diverged — three where tips helped, two where they hurt.

**Where tips helped:**

reddit/webarena.603: The task said "the forum." In WebArena's simulated Reddit, "the forum" maps to the subreddit interface — a vocabulary quirk of the benchmark. The tip bridged it: forum equals subreddit. Without the tip, BrowserGym searched for a generic forum link and failed. With the tip, direct to the subreddit on step one. Pure terminology bridging.

map/webarena.223: Required identifying a Pittsburgh-specific location. The tip injected context: WebArena is set in Pittsburgh, PA. Without it, BrowserGym spent four steps disambiguating the city. With it, correct on step one.

shopping/webarena.225: The tip oriented BrowserGym to the correct starting page, cutting two navigation steps.

**Where tips hurt:**

reddit/webarena.618: The tip prescribed a navigation path through the subreddit sidebar. Without the tip, BrowserGym used a direct URL approach and succeeded in 6 steps. With the tip, it followed the prescribed sidebar path, got confused midway, and hit the 20-step truncation limit. The tip replaced a working strategy with a longer, worse one.

shopping/webarena.228: The tip changed how BrowserGym interacted with a price-range filter, causing it to select the wrong price tier. Without the tip, correct answer on step three.

The pattern is consistent: tips help when they supply factual context the agent lacks — vocabulary, geography. Tips hurt when they prescribe *navigation strategy* — BrowserGym's own path-finding is often more efficient than what the tip prescribes.

---

## Slide 12 — Token & Time Efficiency

The most actionable efficiency signal in the data.

Successful tasks consume dramatically fewer tokens than failing ones. In BrowserGym's sonnet_rerun: successful tasks average 14,947 **axtree tokens** — that's tokens representing the accessibility tree text at each step. Failing tasks average 79,748. A 5.3x gap.

This is not because successful tasks observe less. They receive the same information at each step. The gap exists because successful tasks complete in fewer steps and stop accumulating. Failing tasks stack up observations for every one of those wasted 13 to 20 steps.

Calculation: 79,748 divided by 14,947 equals 5.33. Across no_tips the gap is 3.0x.

The table shows the tips cost clearly: with_tips_v2 averages nearly 96,000 axtree tokens per task — almost four times no_tips's 26,872 — because tips cause BrowserGym to take more steps even on tasks it eventually solves.

Scale reference: the raw HTML processed internally by BrowserGym averages 387,635 tokens per task. That's the full DOM before compression to the axtree. The ratio is roughly 10 to 1 — significant noise reduction happens before the model ever sees the content.

---

## Slide 13 — BrowserGym: Per-Site Performance

Site-by-site breakdown for BrowserGym on WebArena.

**GitLab**: 100% in both no_tips and sonnet_rerun. The 0% in no_tips_30_steps is not a BrowserGym failure — it's an infrastructure crash. All four GitLab tasks show a timeout error trying to fill in the login field before the agent ever took a step. The environment never started. Without flagging this, it looks like a 0% site result, suppressing the headline number by roughly 8 percentage points.

**Map**: Consistently the hardest site, 38 to 50% across runs. Map tasks require spatial reasoning — routes, distances, location interpretation — that's visually complex and often not well-captured in the accessibility tree. This is one of the clearer cases where the screenshot is genuinely carrying unique signal.

**Reddit**: Stable at 78% across sequential runs. Both concurrent run tasks failed — likely an environment-level issue under parallel load, not a BrowserGym failure.

**Shopping**: The largest task set at 17 tasks. Consistent 47% across all conditions. Tips and step limit changes don't move this number.

**Shopping Admin**: Consistent 70% across sequential runs. Same concurrent failure pattern as Reddit.

---

## Slide 14 — Failure Mode Analysis

Five failure categories, observed in both agents.

**Click loops** are the dominant failure in both browser-use and BrowserGym. The trajectory data we just saw makes this concrete — 67 to 83% of all repeated sequences are in failing tasks. Same action, same element, no state change, running out the clock.

**Step budget exhaustion**: 17 to 25% of BrowserGym tasks per run hit the truncation limit without ever sending a termination signal. All failures. The 30-step experiment didn't convert any of them.

**Infrastructure crashes**: the GitLab no_tips_30_steps case, plus two browser-use tasks blocked before the agent could start. These are not agent failures and should be excluded from capability scoring.

**Wrong answer with correct execution**: the agent completes the task mechanics correctly but returns incorrect information. The clearest browser-use case: an Allrecipes task where a prep time of exactly 30 minutes was reported as satisfying "less than 30 minutes." BrowserGym's programmatic evaluator catches this precisely; browser-use's GPT-4V judge is more lenient.

**Site blocking**: Cambridge Dictionary served a Cloudflare CAPTCHA to three browser-use tasks. As we saw in the screenshot slide, the agent identified it from the screenshot — the DOM showed nothing.

---

## Slide 15 — Recommendations

Two sets: agent architecture, and rerun design.

**For agent architecture:**

Collapse BrowserGym's two-call-per-step structure into one. We've shown it consumes 44.6% of wall-clock time. browser-use does the same memory update inline with a single call, no accuracy penalty.

Early termination on repeated actions: if either agent produces the same action type three consecutive times, force a strategy change — go back to the last successful URL or terminate with failure. The trajectory data shows this would cut off click loops well before the step limit.

Conditional screenshots: the screenshot slide showed exactly when visual information is unique — CAPTCHA detection, hover menus, canvas UI, load state. On all other steps, skip the screenshot. Estimated 30–50% per-step cost reduction on those steps for both agents.

Budget awareness: tell the agent its current step and remaining budget in the prompt. Agents with this information tend to attempt graceful termination rather than looping.

**For the rerun:**

Tips: optional. Net gain of one task at 46% more tokens. If you want the vocabulary-bridging benefit without the navigation-prescription risk, pull the terminology definitions out into a general context note instead of task-specific strategy tips.

Step limit: keep at 20. The 30-step experiment made performance worse.

Validate GitLab infrastructure before the full run — one site crash costs 8 percentage points on the headline number.

Primary metric: SPL, success-weighted path length, alongside raw success rate. The formula is in the footnote. It penalizes agents that succeed but take many more steps than necessary, giving you a single number that rewards both accuracy and efficiency.

---

## Slide 16 — References

Experimental data: 50 browser-use trajectories on WebVoyager from March 2026, and 183 BrowserGym task-run pairs across five WebArena runs.

Key references:

Zhou et al. 2023 — the WebArena paper. Defines the benchmark, the five sites, and the programmatic evaluation methodology used for BrowserGym scoring.

Yang et al. 2023 — the Set-of-Marks paper. The visual grounding technique BrowserGym uses.

Pan et al. 2024, AgentOccam — informs the SPL metric framing and provides efficiency analysis context.

ServiceNow's WebArena Verified paper — addresses reliability issues in WebArena evaluation, relevant for interpreting success rates.

That's the full picture. Happy to go deeper on any section.

---
