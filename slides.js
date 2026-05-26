const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10" x 5.625"
pres.title = "Browser Agent Evaluation Report";

// ── Palette: pure B&W ────────────────────────────────────────────────────────
const BLACK  = "000000";
const WHITE  = "FFFFFF";
const GRAY1  = "111111";   // near-black text
const GRAY3  = "333333";   // body text
const GRAY5  = "555555";   // secondary/caption
const GRAY9  = "999999";   // muted / borders
const GRAYF  = "F2F2F2";   // light fill (table rows, callout bg)
const GRAYE  = "E0E0E0";   // divider lines / table header fill

// ── Helpers ──────────────────────────────────────────────────────────────────
function title(slide, text) {
  slide.addText(text, {
    x: 0.5, y: 0.28, w: 9, h: 0.65,
    fontSize: 26, bold: true, fontFace: "Calibri", color: BLACK,
    margin: 0,
  });
  // thin bottom rule under title
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 0.96, w: 9, h: 0,
    line: { color: GRAY9, width: 1 },
  });
}

function sub(slide, text, y) {
  slide.addText(text, {
    x: 0.5, y, w: 9, h: 0.3,
    fontSize: 11, italic: true, fontFace: "Calibri", color: GRAY5, margin: 0,
  });
}

function body(slide, items, y, h, opts = {}) {
  // items: array of { text, bold?, indent? } OR plain string
  const runs = items.map((item, i) => {
    const isLast = i === items.length - 1;
    if (typeof item === "string") {
      return { text: item, options: { bullet: true, breakLine: !isLast, fontSize: 14, fontFace: "Calibri", color: GRAY3 } };
    }
    return {
      text: item.text,
      options: {
        bullet: !item.noBullet,
        breakLine: !isLast,
        fontSize: item.small ? 12 : 14,
        bold: item.bold || false,
        italic: item.italic || false,
        fontFace: "Calibri",
        color: item.muted ? GRAY5 : GRAY3,
        indentLevel: item.indent || 0,
      },
    };
  });
  slide.addText(runs, { x: 0.5, y, w: 9, h, margin: 0, ...opts });
}

function footnote(slide, text) {
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 5.3, w: 9, h: 0, line: { color: GRAYE, width: 0.75 },
  });
  slide.addText(text, {
    x: 0.5, y: 5.32, w: 9, h: 0.27,
    fontSize: 9, fontFace: "Calibri", color: GRAY9, margin: 0,
  });
}

function tbl(slide, headers, rows, colW, y, h) {
  const totalW = colW.reduce((a, b) => a + b, 0);
  const data = [
    headers.map(h => ({
      text: h,
      options: { bold: true, fontSize: 11, fontFace: "Calibri", color: BLACK,
                 fill: { color: GRAYE }, align: "center", valign: "middle" },
    })),
    ...rows.map((row, ri) =>
      row.map((cell, ci) => ({
        text: cell,
        options: {
          fontSize: 11, fontFace: "Calibri", color: GRAY3,
          fill: { color: ri % 2 === 0 ? GRAYF : WHITE },
          align: ci === 0 ? "left" : "center", valign: "middle",
        },
      }))
    ),
  ];
  slide.addTable(data, {
    x: 0.5, y, w: totalW, h,
    border: { pt: 0.5, color: GRAY9 },
    colW,
  });
}

function pageNum(slide, n, total) {
  slide.addText(`${n} / ${total}`, {
    x: 8.5, y: 5.37, w: 1, h: 0.2,
    fontSize: 9, fontFace: "Calibri", color: GRAY9, align: "right", margin: 0,
  });
}

const TOTAL = 16;

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 1 — Title
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };

  // thick top bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 10, h: 0.12, fill: { color: BLACK }, line: { color: BLACK, width: 0 },
  });

  s.addText("Browser Agent Evaluation Report", {
    x: 0.6, y: 1.2, w: 8.8, h: 1.1,
    fontSize: 38, bold: true, fontFace: "Calibri", color: BLACK, margin: 0,
  });
  s.addText("browser-use  ·  BrowserGym  ·  WebVoyager  ·  WebArena  ·  Architecture  ·  Efficiency", {
    x: 0.6, y: 2.4, w: 8.8, h: 0.5,
    fontSize: 18, fontFace: "Calibri", color: GRAY5, margin: 0,
  });
  s.addText("claude-sonnet-4.6 via AWS Bedrock  —  April 2026", {
    x: 0.6, y: 3.05, w: 8.8, h: 0.4,
    fontSize: 13, fontFace: "Calibri", color: GRAY9, italic: true, margin: 0,
  });

  // bottom bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 5.47, w: 10, h: 0.155, fill: { color: BLACK }, line: { color: BLACK, width: 0 },
  });
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 2 — Agenda
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Agenda");
  pageNum(s, 2, TOTAL);

  const items = [
    { text: "Agent architectures — how each agent is built and why it matters", bold: false },
    { text: "Observation strategy — screenshots vs. DOM, SoM grounding", bold: false },
    { text: "Results — cross-benchmark success rates with calculations", bold: false },
    { text: "Efficiency cliff — why tasks beyond ~12 steps universally fail", bold: false },
    { text: "Tips vs. No-Tips — head-to-head comparison with log-level evidence", bold: false },
    { text: "Token & time efficiency — cost breakdown", bold: false },
    { text: "Failure modes — what goes wrong and why", bold: false },
    { text: "Recommendations — architecture, evaluation, rerun design", bold: false },
  ];
  body(s, items, 1.1, 4.1);
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 3 — Architecture Overview
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Architecture Overview — Two Agents, One Model");
  pageNum(s, 3, TOTAL);

  sub(s, "browser-use (WebVoyager benchmark) vs BrowserGym (WebArena benchmark). Same model — claude-sonnet-4.6. Structural differences drive performance.", 1.0);

  tbl(s,
    ["Dimension", "browser-use  (WebVoyager)", "BrowserGym  (WebArena)"],
    [
      ["LLM calls / step", "1", "2  (progress summary + action)"],
      ["Actions / step", "Multiple (chained)", "Single — enforced by prompt"],
      ["Element grounding", "DOM node_id (axtree text)", "Set-of-Marks index (visual overlay)"],
      ["Memory model", "Inline scratchpad in model_output", "Progress summary as separate call"],
      ["Termination", "Self-reported done(success=True/False)", "send_msg_to_user → external evaluator"],
      ["Chain-of-thought", "evaluation_previous_goal field", "Explicit <think> tags"],
      ["Avg step duration", "~22s  (real web latency included)", "~28.6s  (self-hosted, 2-call overhead)"],
    ],
    [2.5, 3.0, 3.0], 1.3, 3.85
  );

  footnote(s, "BrowserGym single-action constraint hardcoded: 'Only a SINGLE action is allowed in this tag, which will be executed by the program.'");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 4 — The Two-Call Architecture
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "BrowserGym — The Two-Call Architecture");
  pageNum(s, 4, TOTAL);

  sub(s, "BrowserGym makes two sequential LLM calls per step. browser-use makes one. The difference has a measurable cost.", 1.0);

  // step diagram: boxes with arrows
  const bx = [0.5, 3.3, 6.1];
  const labels = ["Observation\n(axtree + SoM screenshot)", "Call 1 — Progress Summary\n'What have I done? What's the page state?'", "Call 2 — Action Selection\n'Given summary, what single action next?'"];
  for (let i = 0; i < 3; i++) {
    s.addShape(pres.shapes.RECTANGLE, {
      x: bx[i], y: 1.3, w: 2.5, h: 1.0,
      fill: { color: i === 0 ? GRAYE : GRAYF },
      line: { color: GRAY9, width: 1 },
    });
    s.addText(labels[i], {
      x: bx[i] + 0.07, y: 1.3, w: 2.36, h: 1.0,
      fontSize: 11, fontFace: "Calibri", color: GRAY1, align: "center", valign: "middle", margin: 0,
    });
    if (i < 2) {
      s.addShape(pres.shapes.LINE, {
        x: bx[i] + 2.5, y: 1.8, w: 0.3, h: 0, line: { color: BLACK, width: 1.5 },
      });
      s.addText("→", { x: bx[i] + 2.5, y: 1.6, w: 0.3, h: 0.4, fontSize: 14, color: BLACK, align: "center", margin: 0 });
    }
  }

  // cost breakdown
  s.addText("Cost breakdown (sonnet_rerun, 48 tasks):", {
    x: 0.5, y: 2.55, w: 9, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0,
  });

  const items = [
    "Total LiteLLM calls confirmed from logs: ~2 × steps  (e.g. 41 calls for a 20-step task)",
    "LLM inference time: 5,422s  |  Environment time: 6,739s  →  LLM = 44.6% of total wall-clock",
    "Avg LLM time per step: 12.76s  ·  Avg total step duration: ~28.6s",
    { text: "For a 20-step failing task: ~255s of pure LLM inference before inevitable truncation", italic: true, muted: true },
  ];
  body(s, items, 2.9, 2.2);

  footnote(s, "Calc: 5,422 / (5,422 + 6,739) = 44.6%.  browser-use makes 1 call/step, scratchpad is inline — no separate inference pass.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 5 — Observation: SoM vs. DOM
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Observation Space — Set-of-Marks vs. DOM-Indexed Screenshots");
  pageNum(s, 5, TOTAL);

  sub(s, "Same raw inputs (screenshot + axtree), fundamentally different presentation to the LLM.", 1.0);

  tbl(s,
    ["Dimension", "BrowserGym  (WebArena)", "browser-use  (WebVoyager)"],
    [
      ["Screenshot type", "Set-of-Marks: element indices overlaid on rendered page", "Plain render (1400×850)"],
      ["Element selection", "SoM index — visible in screenshot AND in axtree", "DOM node_id — axtree text only"],
      ["Grounding robustness", "Robust to axtree gaps (visual fallback exists)", "Breaks if element absent from axtree"],
      ["Conditional screenshots", "No — sent every step", "No — hardcoded include_screenshot=True"],
      ["Avg axtree tokens/task", "39,248 (sonnet_rerun)", "~20,000 (estimated)"],
      ["Chain-of-thought style", "Explicit <think> tags before action", "evaluation_previous_goal inline field"],
    ],
    [2.2, 3.4, 3.0], 1.25, 3.6
  );

  body(s, [
    { text: "Empirical finding: BrowserGym's SoM grounding shows no clear accuracy advantage over browser-use's DOM-indexed approach at current task complexity (gitlab 100%, shopping ~47% in both agents). Grounding method is not the primary differentiator.", italic: true, noBullet: false, muted: true, small: true },
  ], 5.0, 0.28);

  footnote(s, "Yang et al. (2023): Set-of-Mark Prompting Unleashes Extraordinary Visual Grounding in GPT-4V. arXiv:2310.11441");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 6 — When Screenshots Are the Primary Signal
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "When Screenshots Are the Only Signal");
  pageNum(s, 6, TOTAL);

  sub(s, "Both agents send a screenshot on every step, unconditionally. Four cases where the screenshot carries information the DOM cannot.", 1.0);

  tbl(s,
    ["Case", "What DOM shows", "What screenshot shows", "Observed in"],
    [
      ["Anti-bot / CAPTCHA", "Empty or minimal — page appears blank", "Cloudflare challenge, visual block page", "browser-use: Cambridge Dict (3 tasks failed)"],
      ["Hover-revealed menus", "Static — sub-menu not yet in tree", "Sub-menu visually appears on hover", "BrowserGym: hover used 11× in sonnet_rerun"],
      ["Canvas / dynamic UI", "Calendar structure present in DOM", "Date cells visually disabled — not in axtree", "browser-use: Google Flights (6 failures)"],
      ["Page load state", "DOM may already be populated", "Spinner, partial render, blank area visible", "Both agents confirm load from screenshot before acting"],
    ],
    [1.6, 2.4, 2.5, 2.9], 1.2, 3.5
  );

  body(s, [
    { text: "Shared inefficiency: neither agent conditionally skips screenshots. On DOM-deterministic steps — fill a known field, navigate to a known URL — the screenshot adds tokens and latency with no decision value. Estimated 30–50% per-step cost reduction if skipped on those steps.", small: true, muted: true, italic: true },
  ], 4.83, 0.35);

  footnote(s, "Google Flights: agent clicks DOM-valid date nodes that are visually greyed out. SoM grounding would not fix this — dates appear disabled in the screenshot regardless of grounding method.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 7 — Results Overview
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Results — Cross-Benchmark Success Rates");
  pageNum(s, 7, TOTAL);

  sub(s, "Calculations: success rate = tasks passed / total tasks evaluated. Truncated = hit step limit without terminating.", 1.0);

  tbl(s,
    ["Agent / Run", "Tasks", "Passed", "Rate", "Avg Steps", "Avg Duration", "Truncated"],
    [
      ["browser-use  (WebVoyager)", "50", "30", "30/50 = 60.0%", "8.02", "219s", "0%"],
      ["BrowserGym — no_tips", "48", "29", "29/48 = 60.4%", "6.60", "103s", "16.7%"],
      ["BrowserGym — no_tips_30_steps", "48", "24", "24/48 = 50.0%", "8.50", "129s", "12.5%"],
      ["BrowserGym — sonnet_rerun (WITH tips)", "48", "30", "30/48 = 62.5%", "7.85", "140s", "18.8%"],
      ["BrowserGym — sonnet46_concurrent", "12", "6", "6/12  = 50.0%", "9.92", "303s", "25.0%"],
      ["BrowserGym — with_tips_v2", "27", "11", "11/27 = 40.7%", "9.00", "217s", "14.8%"],
    ],
    [2.6, 0.75, 0.75, 1.65, 1.1, 1.25, 1.05], 1.2, 3.8
  );

  body(s, [
    { text: "no_tips and sonnet_rerun both converge near 60–62.5%, matching WebVoyager. Likely a model-capability ceiling for claude-sonnet-4.6 at current task complexity, not an architecture or prompting effect.", italic: true, muted: true, small: true, noBullet: false },
  ], 5.1, 0.28);

  footnote(s, "cum_reward (LLM-evaluated, 0 or 1.0) is the correct metric. cum_raw_reward = 0 for all tasks (unused). Zhou et al. (2023) WebArena. arXiv:2307.13854");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 7 — Efficiency Cliff
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "The Efficiency Cliff — 0% Success Past ~12 Steps");
  pageNum(s, 8, TOTAL);

  sub(s, "Success rate by step bucket. BrowserGym (sonnet_rerun) vs browser-use (WebVoyager). Pattern is consistent across both agents and both benchmarks.", 1.0);

  tbl(s,
    ["Step Bucket", "BrowserGym — sonnet_rerun", "browser-use — WebVoyager"],
    [
      ["1–3 steps", "16 tasks → 15/16 = 94% success", "6 tasks →  4/6  = 67% success"],
      ["4–7 steps", "15 tasks → 12/15 = 80% success", "21 tasks → 16/21 = 76% success"],
      ["8–12 steps", "5 tasks →   3/5  = 60% success", "13 tasks →  9/13 = 69% success"],
      ["13–20 steps", "12 tasks →  0/12 = 0%  success", "4 tasks →   0/4  =  0% success"],
      ["21+ steps", "0 tasks (none in this run)", "6 tasks →   1/6  = 17%*"],
    ],
    [1.8, 3.6, 3.6], 1.2, 3.2
  );

  body(s, [
    "An agent that has not succeeded by step 12 should be considered failed. Continuing beyond step 12 costs tokens and time with zero expected return.",
    { text: "* The sole 21+ step WebVoyager success: Google Maps with 21 explicit wait actions — structurally different from a stuck agent.", italic: true, muted: true, small: true },
  ], 4.5, 0.85);

  footnote(s, "Calc: step buckets derived from steps_info JSON per task. success rate = sum(reward==1) / count(tasks_in_bucket).");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 9 — Trajectory Shapes: Success vs Failure
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Trajectory Shapes — What Success and Failure Look Like");
  pageNum(s, 9, TOTAL);

  sub(s, "Repeated action sequences are a near-universal failure signature in both agents. Numbers below are from actual trajectory logs.", 1.0);

  // top: two-column shape comparison
  // Left — success shape
  s.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 1.25, w: 4.1, h: 0.28, fill: { color: GRAYE }, line: { color: GRAY9, width: 0.5 } });
  s.addText("Successful trajectory (typical: 3–7 steps)", { x: 0.5, y: 1.25, w: 4.1, h: 0.28, fontSize: 11, bold: true, fontFace: "Calibri", color: BLACK, align: "center", margin: 0 });
  body(s, [
    { text: "Step 1–2: orient to page, identify target element", small: true, noBullet: false },
    { text: "Step 3–5: direct interaction — fill, click, navigate", small: true },
    { text: "Step 6–7: verify result, issue done / send_msg_to_user", small: true },
    { text: "No repeated action types. Each step advances state.", small: true, italic: true, muted: true },
  ], 1.56, 1.55, { x: 0.5, w: 4.1 });

  // Right — failure shape
  s.addShape(pres.shapes.RECTANGLE, { x: 5.1, y: 1.25, w: 4.4, h: 0.28, fill: { color: GRAYE }, line: { color: GRAY9, width: 0.5 } });
  s.addText("Failing trajectory (typical: 13–20 steps)", { x: 5.1, y: 1.25, w: 4.4, h: 0.28, fontSize: 11, bold: true, fontFace: "Calibri", color: BLACK, align: "center", margin: 0 });
  body(s, [
    { text: "Step 1–4: orient and begin task — appears normal", small: true },
    { text: "Step 5–8: first failed action, agent retries same element", small: true },
    { text: "Step 9–12: click loop begins — identical action type repeats", small: true },
    { text: "Step 13–20: loop continues until step limit. No progress.", small: true, italic: true, muted: true },
  ], 1.56, 1.55, { x: 5.1, w: 4.4 });

  // divider
  s.addShape(pres.shapes.LINE, { x: 4.85, y: 1.22, w: 0, h: 2.0, line: { color: GRAYE, width: 1 } });

  // Wasted steps table
  s.addText("Repeated sequences by run — failures hold 67–83% of all repeats:", {
    x: 0.5, y: 3.3, w: 9, h: 0.28, fontSize: 12, bold: true, fontFace: "Calibri", color: BLACK, margin: 0,
  });

  tbl(s,
    ["Agent / Run", "Tasks w/ repeats", "Total repeats", "In successes", "In failures", "Failures %"],
    [
      ["browser-use  (WebVoyager)", "34/50  (68%)", "100", "~32", "~68", "~68%"],
      ["BrowserGym — no_tips", "37/48  (77%)", "152", "48", "104", "68%"],
      ["BrowserGym — sonnet_rerun", "42/48  (88%)", "176", "58", "118", "67%"],
      ["BrowserGym — no_tips_30s", "32/48  (67%)", "202", "40", "162", "80%"],
      ["BrowserGym — concurrent", "11/12  (92%)", "70", "12", "58", "83%"],
    ],
    [2.2, 1.5, 1.1, 1.1, 1.1, 1.0], 3.65, 1.75
  );

  footnote(s, "Repeated sequence = same action type on consecutive steps. no_tips_30_steps accumulates 202 repeats vs 152 in no_tips despite identical tasks — extra steps extend loops, not solutions.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 10 — Tips: Setup & Calculation
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Tips vs. No-Tips — Setup & Calculation");
  pageNum(s, 10, TOTAL);

  sub(s, "BrowserGym on WebArena. no_tips (no Task Tips in prompt) vs sonnet_rerun (WITH Task Tips). Same 48-task set, same model.", 1.0);

  // What tips are
  s.addText("What 'Task Tips' are:", { x: 0.5, y: 1.3, w: 9, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    "General tips (benchmark quirks) present in ALL runs",
    "Task Tips (# Task Tips section) injected only in sonnet_rerun, sonnet46_concurrent, with_tips_v2",
    { text: "Verified via: grep -l '# Task Tips' */full_prompt_0.txt — absent in no_tips, present in sonnet_rerun", italic: true, muted: true, small: true },
  ], 1.6, 1.0);

  s.addText("Results:", { x: 0.5, y: 2.7, w: 9, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });

  tbl(s,
    ["Metric", "no_tips (WITHOUT tips)", "sonnet_rerun (WITH tips)", "Δ"],
    [
      ["Success rate", "29/48 = 60.4%", "30/48 = 62.5%", "+1 task  (+2.1 pp)"],
      ["Avg steps/task", "6.60", "7.85", "+1.25 steps"],
      ["Avg axtree tokens/task", "26,872", "39,248", "+12,376  (+46%)"],
      ["Avg task duration", "103s", "140s", "+37s  (+36%)"],
      ["Truncated tasks", "8/48  (16.7%)", "9/48  (18.8%)", "+1 task truncated"],
    ],
    [2.5, 2.2, 2.5, 1.5], 3.0, 2.4
  );

  footnote(s, "Token calc: (39,248 − 26,872) / 26,872 = 46.1%.  Duration calc: (140 − 103) / 103 = 35.9%.  All from summary_info.json per-task axtree_tokens field.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 9 — Tips: Mechanism from Logs
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Tips vs. No-Tips — What the Logs Show");
  pageNum(s, 11, TOTAL);

  sub(s, "5 BrowserGym tasks diverged between no_tips and sonnet_rerun. Logs inspected: full_prompt_0.txt (tip content) + experiment.log (action sequences).", 1.0);

  // Left column: helped
  s.addText("Tips HELPED (3 tasks):", { x: 0.5, y: 1.3, w: 4.4, h: 0.3, fontSize: 12, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    { text: "reddit/webarena.603 — Vocabulary bridging: tip mapped 'forum' → subreddit. Agent without tip searched for a 'forum' link and failed. With tip: direct to subreddit on step 1.", small: true },
    { text: "map/webarena.223 — Domain context: tip injected 'WebArena is set in Pittsburgh, PA'. Without tip: 4 steps disambiguating city. With tip: correct on step 1.", small: true },
    { text: "shopping/webarena.225 — Starting orientation: tip pointed to correct page, saving 2 navigation steps.", small: true },
  ], 1.62, 2.1, { w: 4.4, x: 0.5 });

  // divider
  s.addShape(pres.shapes.LINE, { x: 5.1, y: 1.25, w: 0, h: 3.5, line: { color: GRAYE, width: 1 } });

  // Right column: hurt
  s.addText("Tips HURT (2 tasks):", { x: 5.25, y: 1.3, w: 4.25, h: 0.3, fontSize: 12, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    { text: "reddit/webarena.618 — Navigation prescription: tip prescribed UI path through sidebar. Agent without tip used goto(url), succeeded in 6 steps. With tip: followed sidebar path, looped, truncated at 20 steps.", small: true },
    { text: "shopping/webarena.228 — Element selection interference: tip changed price-range filter behavior, agent selected wrong tier and returned incorrect results.", small: true },
  ], 1.62, 2.1, { w: 4.25, x: 5.25 });

  // Pattern summary
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: 4.82, w: 9, h: 0.62, fill: { color: GRAYF }, line: { color: GRAYE, width: 1 },
  });
  s.addText("Pattern: tips help when bridging vocabulary gaps or injecting domain context the agent genuinely lacks. Tips hurt when they prescribe navigation strategies — the agent's own path-finding is often more efficient.", {
    x: 0.6, y: 4.87, w: 8.8, h: 0.52, fontSize: 11, italic: true, fontFace: "Calibri", color: GRAY3, valign: "middle", margin: 0,
  });
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 10 — Token & Time Efficiency
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Token & Time Efficiency");
  pageNum(s, 12, TOTAL);

  sub(s, "Successful tasks use far fewer tokens — not because they observe less, but because they complete in fewer steps.", 1.0);

  // Token gap callout boxes
  const boxes = [
    { label: "sonnet_rerun\nSUCCESS", val: "14,947", sub2: "avg axtree tokens" },
    { label: "sonnet_rerun\nFAILURE", val: "79,748", sub2: "avg axtree tokens" },
    { label: "Ratio", val: "5.3×", sub2: "failure / success" },
  ];
  const bxX = [0.5, 3.4, 6.3];
  for (let i = 0; i < 3; i++) {
    s.addShape(pres.shapes.RECTANGLE, {
      x: bxX[i], y: 1.45, w: 2.7, h: 1.35,
      fill: { color: GRAYF }, line: { color: GRAY9, width: 1 },
    });
    s.addText(boxes[i].label, { x: bxX[i], y: 1.45, w: 2.7, h: 0.42, fontSize: 11, fontFace: "Calibri", color: GRAY5, align: "center", valign: "middle", margin: 0 });
    s.addText(boxes[i].val, { x: bxX[i], y: 1.85, w: 2.7, h: 0.55, fontSize: 26, bold: true, fontFace: "Calibri", color: BLACK, align: "center", margin: 0 });
    s.addText(boxes[i].sub2, { x: bxX[i], y: 2.38, w: 2.7, h: 0.26, fontSize: 10, fontFace: "Calibri", color: GRAY5, align: "center", margin: 0 });
  }

  // Calculation
  s.addText("Calculation: 79,748 / 14,947 = 5.33×  gap  |  Across no_tips: 45,165 / 14,888 = 3.03×  gap", {
    x: 0.5, y: 2.95, w: 9, h: 0.28, fontSize: 11, italic: true, fontFace: "Calibri", color: GRAY5, margin: 0,
  });

  tbl(s,
    ["Run", "Avg axtree tokens/task", "Avg tokens — success", "Avg tokens — failure"],
    [
      ["no_tips", "26,872", "14,888", "45,165"],
      ["sonnet_rerun (WITH tips)", "39,248", "14,947", "79,748"],
      ["with_tips_v2", "95,978", "54,086", "124,779"],
    ],
    [2.8, 2.4, 2.4, 1.9], 3.3, 1.8
  );

  footnote(s, "HTML tokens (pruned_html) tracked internally but not sent to LLM. sonnet_rerun avg: 387,635 HTML tokens/task. Compression ratio axtree/HTML ≈ 10:1.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 11 — Per-Site Breakdown
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "BrowserGym — Per-Site Performance (WebArena)");
  pageNum(s, 13, TOTAL);

  sub(s, "BrowserGym across 5 WebArena sites and 5 runs. Rates shown as passed/total and %. Notable anomalies flagged.", 1.0);

  tbl(s,
    ["Site", "no_tips", "no_tips_30s", "sonnet_rerun", "concurrent", "Notes"],
    [
      ["gitlab", "4/4 = 100%", "0/4 = 0%  ⚠", "4/4 = 100%", "4/4 = 100%", "30-step: env crash — 0 steps taken, not agent failure"],
      ["map", "3/8 = 38%", "3/8 = 38%", "4/8 = 50%", "1/2 = 50%", "Hardest site; spatial reasoning + visual interpretation"],
      ["reddit", "7/9 = 78%", "7/9 = 78%", "7/9 = 78%", "0/2 = 0%", "Stable; concurrent 0% likely env failure under load"],
      ["shopping", "8/17 = 47%", "7/17 = 41%", "8/17 = 47%", "1/2 = 50%", "Largest set; consistent ~47% across all runs"],
      ["shopping_admin", "7/10 = 70%", "7/10 = 70%", "7/10 = 70%", "0/2 = 0%", "Consistent 70%; concurrent failure same pattern"],
    ],
    [1.4, 1.35, 1.35, 1.35, 1.35, 2.2], 1.2, 3.8
  );

  body(s, [
    { text: "gitlab/no_tips_30_steps crash: all 4 tasks show TimeoutError on Locator.fill('Username or email') before agent takes any steps — infrastructure failure, not a model or tip effect.", muted: true, small: true, italic: true },
  ], 5.1, 0.28);

  footnote(s, "Crash evidence: experiment.log shows TimeoutError pre-step for all 4 gitlab tasks in no_tips_30_steps. reward=0, steps=0, trunc=None.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 12 — Failure Modes
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Failure Mode Analysis");
  pageNum(s, 14, TOTAL);

  sub(s, "5 reproducible failure categories, observed in both browser-use and BrowserGym. Repeats are the dominant signal.", 1.0);

  tbl(s,
    ["Failure Type", "BrowserGym (WebArena)", "browser-use (WebVoyager)", "Pattern"],
    [
      ["Click / action loops", "37–42/48 tasks have repeats (77–88%)", "34/50 (68%)", "Failing tasks: ~2/3 of all repeats"],
      ["Step budget exhaustion", "8–12/48 truncated per run (17–25%)", "0 truncated", "30-step limit doesn't help — just longer loops"],
      ["Infrastructure / env crash", "gitlab/no_tips_30_steps: 4 tasks (0 steps)", "2 tasks (Cambridge Dict, GitHub)", "Silent accuracy hit — exclude from denominator"],
      ["Wrong answer, correct execution", "Caught by programmatic evaluator", "Allrecipes-14: 'exactly 30 min' ≠ '<30 min'", "WebArena evaluator more precise than GPT-4V judge"],
      ["Site blocking", "None (self-hosted env)", "Cambridge Dict: Cloudflare CAPTCHA (3 tasks)", "DOM shows nothing; screenshot-only detection"],
    ],
    [2.2, 2.7, 2.5, 2.1], 1.2, 3.8
  );

  footnote(s, "Repeated sequence: identical action type on consecutive steps. no_tips_30_steps: 202 repeats vs 152 in no_tips — longer budget = more looping, not more solving.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 13 — Recommendations
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Recommendations");
  pageNum(s, 15, TOTAL);

  // Left: architecture
  s.addText("Architecture", { x: 0.5, y: 1.1, w: 4.4, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    { text: "Merge progress summary into action call — eliminates 44.6% LLM wall-clock overhead with no accuracy loss", small: true },
    { text: "Early termination at 3 consecutive identical actions — prevents majority of wasted steps in both architectures", small: true },
    { text: "Conditional screenshot — skip screenshot for DOM-deterministic steps (fill on known node, goto known URL). Est. 30–50% reduction in per-step observation cost on those steps", small: true },
    { text: "Inject step budget into prompt — agents with budget awareness terminate more gracefully than agents that loop to truncation", small: true },
  ], 1.45, 2.3, { w: 4.4, x: 0.5 });

  s.addShape(pres.shapes.LINE, { x: 5.1, y: 1.08, w: 0, h: 3.6, line: { color: GRAYE, width: 1 } });

  // Right: rerun design
  s.addText("Rerun Design", { x: 5.25, y: 1.1, w: 4.25, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    { text: "Tips: optional. +1 task (+2.1 pp) for +46% tokens. Prefer no-tips + vocabulary notes over strategy-prescribing tips", small: true },
    { text: "Step limit: keep at 20. Extending to 30 steps added loops, not successes (50% vs 60.4% for no_tips)", small: true },
    { text: "Validate gitlab infrastructure before full run — a single crashed site costs ~8 pp on 48-task eval", small: true },
    { text: "Primary metric: success rate with infra failures excluded. Secondary: SPL (success-weighted path length) using min steps as baseline", small: true },
    { text: "Wasted-step ratio (repeats / total steps) as diagnostic — detects stuck agents before truncation", small: true },
  ], 1.45, 2.8, { w: 4.25, x: 5.25 });

  footnote(s, "SPL = (1/N) Σ S_i × (L* / max(L_i, L*)) where L* = min steps observed per task, L_i = agent steps. Pan et al. (2024) AgentOccam.");
}

// ════════════════════════════════════════════════════════════════════════════
// SLIDE 14 — References
// ════════════════════════════════════════════════════════════════════════════
{
  const s = pres.addSlide();
  s.background = { color: WHITE };
  title(s, "Data Sources & References");
  pageNum(s, 16, TOTAL);

  s.addText("Experimental Data", { x: 0.5, y: 1.1, w: 9, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    "browser-use on WebVoyager: 50 task trajectories, steel-bedrock-sonnet-4.6, March 2026. Full step history, GPT-4V post-hoc evaluation.",
    "BrowserGym on WebArena: 183 task-run pairs across 5 runs (no_tips, no_tips_30_steps, sonnet_rerun, sonnet46_concurrent, with_tips_v2) and 5 sites. Per-step steps_info JSON, summary_info JSON, experiment logs, paired SoM + plain screenshots.",
  ], 1.45, 0.9);

  s.addText("Key References", { x: 0.5, y: 2.5, w: 9, h: 0.3, fontSize: 13, bold: true, fontFace: "Calibri", color: BLACK, margin: 0 });
  body(s, [
    "Zhou et al. (2023). WebArena: A Realistic Web Environment for Building Autonomous Agents. ICLR 2024. arXiv:2307.13854",
    "Yang et al. (2023). Set-of-Mark Prompting Unleashes Extraordinary Visual Grounding in GPT-4V. arXiv:2310.11441",
    "Pan et al. (2024). AgentOccam: A Simple Yet Strong Baseline for LLM-Based Web Agents. ICLR 2025. Amazon Science.",
    "ServiceNow (2024). WebArena Verified: Reliable Evaluation for Web Agents. OpenReview: CSIo4D7xBG",
    "Koh et al. (2024). VisualWebArena: Evaluating Multimodal Agents on Realistic Visually Grounded Web Tasks. arXiv:2401.13649",
    "BrowserArena: Evaluating LLM Agents on Real-World Web Navigation Tasks. arXiv:2510.02418",
    "ActionEngine: From Reactive to Programmatic GUI Agents via State Machine Memory. arXiv:2602.20502",
  ], 2.85, 2.55);
}

// ── Write file ───────────────────────────────────────────────────────────────
pres.writeFile({ fileName: "/sessions/wonderful-gifted-brown/browser_agent_slides.pptx" })
  .then(() => console.log("Done"))
  .catch(e => { console.error(e); process.exit(1); });
