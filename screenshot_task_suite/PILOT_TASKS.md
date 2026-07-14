### Pilot Task Suite

July 10, 2026

## Task mix and site coverage

| Category | Definition                                                   | Count |
| -------- | ------------------------------------------------------------ | ----- |
| Type1    | Rendered output: answer computed/rendered client-side, text extraction unreliable | 3     |
| Type2    | Blocking overlay / dynamic UI: a popup or revealed panel changes what is possible | 2     |
| Type3    | Pre-submit form verification: multi-field form where the filled state matters | 2     |
| Type4    | Large-target visual interaction: search boxes, cards, pickers | 2     |
| Type5    | Answer exists only in pixels                                 | 1     |

### Type1-1 (wolframalpha.com, string match)

Prompt: "Find the 2026th prime number using Wolfram Alpha and report it."

Answer: 17623.

Check: standalone 17623 (commas/sentences fine). Rejects any answer that does not parse to 17623.

Trigger of image: WA serves a JS app shell with no result text and the result renders in a client-side pod, as an image. This has been verified in a browser.

### Type1-2 (wolframalpha.com, string match)

Prompt: "Use Wolfram Alpha to compute the determinant of the 5x5 matrix {{7,3,-2,5,4},{1,8,4,-6,2},{-3,2,9,1,-5},{5,-4,0,6,3},{2,6,-7,3,8}} and report its value."

Answer: -22140.

Check: standalone -22140 with the minus sign required. Rejects any answer that does not parse to -22140, including a sign-dropped 22140.

Trigger of image: same rendered pod as Type1-1, the determinant renders client-side as an image. The matrix is 5x5 so a strong model cannot reliably compute it in its head and skip the site, which would corrupt the opt-in measurement. The prime and date pods have been verified in a browser; the determinant pod gets the same check during the dry run.

### Type1-3 (wolframalpha.com, string match)

Prompt: "Use Wolfram Alpha to find the number of days between April 15, 1912 and January 1, 2000, and report the number."

Answer: 32037.

Check: standalone 32037 (commas/sentences fine). Rejects any answer that does not parse to 32037, including near-miss counts like 32038.

Trigger of image: the value exists only in the pod image's alt text and is absent from the page text entirely, the strongest hidden state of the three. This has been verified in a browser. The task replaces an earlier GitHub chart task that was retired because the chart re-bins with window size, so no value displayed on it is stable.

### Type2-2 (huggingface.co, string match)

Prompt: "The Hugging Face model page for bartowski/Llama-3.2-1B-Instruct-GGUF provides ready-made usage instructions for several libraries. Find the code example for using this model with the llama-cpp-python library, and report the exact .gguf filename that the example passes as the filename argument to Llama.from_pretrained."

Answer: Llama-3.2-1B-Instruct-IQ3_M.gguf.

Check: the full filename must appear. Rejects a bare quant name and any answer that hedges with a second filename.

Trigger of image: the code example sits inside the collapsed "Use this model" panel and text extraction does not surface it until the panel is opened. An answer from memory guesses Q4_K_M and fails, because IQ3_M is an accident of how the site generates the snippet for this repo. This has been verified against the live page.

### Type2-3 (wikipedia.org, string match)

Prompt: "Go to the English Wikipedia article about the Golden Gate Bridge. Open the main infobox photograph at the top of the article in the pop-up image viewer, and report the name of the photographer credited for that photograph."

Answer: Frank Schulenburg.

Check: the name must appear, not negated. Rejects any answer without both words.

Trigger of image: clicking the photo opens the MediaViewer overlay and the credit renders only in the overlay footer, while the name appears nowhere in the article text. An agent that lands on the file description page instead still passes, so a blocked overlay cannot fail a correct run. This has been verified against the live page.

### Type3-1 (arxiv.org, set match)

Prompt: "Use arXiv's advanced search to find every paper that has 'Hinton' in the author field and the term 'capsule' in any field, submitted between 2017-01-01 and 2019-12-31. Report the arXiv identifiers of all matching papers."

Answer: {1710.09829, 1811.06969, 1906.06818}, or those three plus 1907.02957. Both count as correct because arXiv's date-type radio changes the result and each is a fair reading of "submitted"; the default radio gives three papers, the original-submission and announcement radios give four. This has been verified against the live form.

Check: the reported set must exactly match one of the two. Rejects partial sets and mixtures, and an answer from memory tends to miss the obscure DARCCC paper and fail.

Trigger of image: the advanced search is a genuine multi-field form with field dropdowns, a date radio and two date inputs, and a wrong dropdown or an unset date filter silently returns a confidently wrong larger set. The screenshot moment is checking the filled form before submitting.

### Type3-2 (github.com, set match)

Prompt: "In the microsoft/vscode repository on GitHub, use the issue filters to find all issues labeled 'emmet' that were created between 2016-06-01 and 2016-06-30 inclusive. Report the issue numbers as a comma-separated list."

Answer: 8135, 8324, 8454, 8569.

Check: the reported set must exactly match. Rejects extras and partial sets; dates and counts written in the answer do not count as extras.

Trigger of image: the issue filter is a compound query and a malformed date or a wrong qualifier silently yields a different but plausible list, so the screenshot moment is verifying the assembled filter state before trusting the results. This has been verified against both the GitHub API and the rendered page, and one API call on run day confirms the labels are unchanged.

### Type4-1 (coursera.org, string match)

Prompt: "Go to https://www.coursera.org and use the site search to find the course titled 'Wind Energy' offered by the Technical University of Denmark (DTU). Open that course's page and report how many modules the course contains."

Answer: 16.

Check: the number tied to the word "modules", or a bare 16 on its own. Rejects a different module count; other numbers such as hours or ratings are ignored.

Trigger of image: the path runs through the home-page search box and the result-card grid, the kind of flow the vision-only agent completed by coordinate clicks. The module count itself is page text, so this is the weakest trigger of the ten, and the pilot logs which step actually makes auto mode look. This has been verified against the live page.

### Type4-2 (apple.com, string match)

Prompt: "Go to https://www.apple.com/shop/buy-mac/macbook-air. In the model selector, choose the 13-inch size, pick the Sky Blue color, and choose the chip option that has the 10-core GPU. Report the starting ('From') price shown for this selection."

Answer: $1,399.

Check: 1399 once currency symbols are stripped. Rejects the neighboring configurations, 1299 for the 8-core chip and 1499 for the 15-inch model, and records which one the agent hit.

Trigger of image: the picker starts with nothing selected, so the price appears only after the agent actively picks all three options, and confirming which tiles are highlighted before reading the price is the screenshot moment. A price remembered from the older lineup fails the check. This has been verified against the live page. The task ends at reading the price and never goes near checkout.

### Type5 (wikipedia.org, string match)

Prompt: "Go to the English Wikipedia article 'Demographics of Japan'. The infobox at the top of the article shows a population pyramid of Japan in 2026. According to that pyramid, what percentage of the total population are females aged 75-79?"

Answer: 3.9%.

Check: 3.9 as a percentage. Rejects the male bar's 3.3, the table-derived values around 3.2, and a population count like "3.9 million"; mentioning those alongside the correct answer still passes.

Trigger of image: the per-sex labels exist only in the pyramid image, with no alt text and no caption data, and the article's own table computes a different value, so a text-derived answer is wrong by construction. This has been verified by reading the image directly. If the text-only arm passes this task consistently the control is broken and the backup control swaps in.

## How the set of tasks was verified

1. Every answer is grounded against the answer on the live site, and verified via a second method. By second method it means each answer is confirmed by directing from a different page, API, or calculating method. This ensures either the incorrect answer cannot be the answer key or there could be one or even more correct answers. (For example, the task that asks how many papers published in a certain time period can be interpreted into 2 search methods that should both be considered to be true).

2. Every task is re-checked in a real rendered browser, since the raw HTML a script downloads is not the same as the page an agent actually sees. This ensures each task behaves the same way in the environment the pilot really runs in. (For example, this round confirmed the Wolfram answer is exposed through the result image's alt text, and it caught one broken task. Originally there was a task that asks agent to find the largest code change from the frequency graph. The GitHub chart draws different numbers at different window sizes, so no value read from it is stable. That task was replaced.)

3. The pass and fail rules are attacked with tricky example answers. By attack it means a reviewer writes answers a correct agent could realistically produce but the rule would fail (like "not 32038 but 32037"), and wrong answers the rule would wrongly pass. The ten hand-written rules kept breaking under this, so they were replaced by one shared rule system stored in the task file, and every tricky example was frozen into a test list together with its expected verdict. The checker program must pass the entire list before it is allowed to score any run. (This immediately caught two bugs in the first version of the checker, before any data was scored.)
