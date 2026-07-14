### Pilot Task Suite 2.0

July 11, 2026

## Task mix and site coverage

| Category | Definition                                                   | Count |
| -------- | ------------------------------------------------------------ | ----- |
| Type1    | Rendered output: answer computed/rendered client-side, text extraction unreliable | 3     |
| Type2    | Blocking overlay / dynamic UI: a popup or revealed panel changes what is possible | 2     |
| Type3    | Pre-submit form verification: multi-field form where the filled state matters | 2     |
| Type4    | Large-target visual interaction: search boxes, cards, pickers | 2     |
| Type5    | Answer exists only in pixels                                 | 1     |

### Type1-1 (github.com -> wolframalpha.com, string match)

Prompt: "Find the year in which the GitHub repository facebookarchive/pop was archived. Then report, according to Wolfram Alpha, the average unemployment rate in the United States for that year."

Answer: 8.1%.

Check: 8.1 as a percentage. Rejects monthly values from the same year, such as 6.7 for December or 14.8 at the April peak, and neighboring years' rates; mentioning those alongside the correct answer still passes.

Trigger of image: the archive year is printed in a banner on the repository page, so the agent must visit GitHub first, and the unemployment figure renders as an image pod on Wolfram Alpha, so the final read is on a rendered surface by construction. Two sites and two pages minimum. The answer was read from the live Wolfram page and matches the official BLS statistics.

### Type1-2 (wikipedia.org -> wolframalpha.com, string match)

Prompt: "Find the year in which the first sod was turned for the Sydney Harbour Bridge. Then report, according to Wolfram Alpha, the United States consumer price index for that year."

Answer: 17.3 (the December 1923 index; 17.1, the annual average, is also accepted).

Check: 17.3 or 17.1. Rejects neighboring years' values such as 16.9. Because 1924 happens to share the same index values, a run whose Wolfram query uses the wrong year fails even if the number matches.

Trigger of image: the first-sod year is obscure enough that the agent must read the Wikipedia article, and the index value renders as an image pod on Wolfram Alpha. Two sites, two pages minimum. The pod value has been frozen in a rendered browser and confirmed against the government data behind it.

### Type1-3 (arxiv.org -> wolframalpha.com, string match)

Prompt: "Find the year in which the arXiv paper 'DARCCC: Detecting Adversaries by Reconstruction from Class Conditional Capsules' was originally submitted. Then report, according to Wolfram Alpha, the inflation rate in the United States for that year."

Answer: 1.91% (1.9 accepted as a rounding).

Check: 1.91 or 1.9. Rejects the 2.4 annual average that a model produces from memory, which is the point: the year-over-year figure lives on the rendered pod, not in the model's head. Also rejects neighboring years' rates.

Trigger of image: the submission year requires finding the paper on arXiv (it has a single version, so "originally submitted" is unambiguous), and the inflation figure renders as an image pod on Wolfram Alpha. Two sites, two pages minimum. The pod value has been frozen in a rendered browser and confirmed against the government data behind it.

### Type2-2 (huggingface.co, string match)

Prompt: "On Hugging Face, find the GGUF version of Llama 3.2 1B Instruct published by bartowski, and report the exact .gguf filename loaded by its ready-made code example for the llama-cpp-python library."

Answer: Llama-3.2-1B-Instruct-IQ3_M.gguf.

Check: the full filename must appear. Rejects a bare quant name and any answer that hedges with a second filename.

Trigger of image: the agent must first locate the model among more than a dozen similarly named repositories, and the code example then sits inside the collapsed "Use this model" panel, which text extraction does not surface until the panel is opened. An answer from memory guesses Q4_K_M and fails, and every look-alike repository's example loads a different filename, so picking the wrong repository cannot accidentally pass. This has been verified against the live page.

### Type2-3 (wikipedia.org, string match)

Prompt: "Find the photographer credited for the main infobox photograph in the English Wikipedia article about the Golden Gate Bridge."

Answer: Frank Schulenburg.

Check: the name must appear, not negated. Rejects any answer without both words.

Trigger of image: the credit appears nowhere in the article text, so the natural route is opening the photograph itself, which brings up a full-screen viewer overlay with the credit in its footer. An agent that reaches the file description page instead still passes, so a blocked overlay cannot fail a correct run. This has been verified against the live page.

### Type3-1 (arxiv.org, set match)

Prompt: "Find every arXiv paper that has Hinton as an author and mentions 'capsule', submitted between 2017-01-01 and 2019-12-31. Report the arXiv identifiers of all matching papers."

Answer: {1710.09829, 1811.06969, 1906.06818}, or those three plus 1907.02957. Both count as correct because arXiv's date handling changes the result and each is a fair reading of "submitted"; searching by most recent submission gives three papers, by original submission or announcement gives four. This has been verified against the live search.

Check: the reported set must exactly match one of the two. Rejects partial sets and mixtures, and an answer from memory tends to miss the obscure DARCCC paper and fail.

Trigger of image: assembling a compound search (author, keyword, date window) is a multi-field state where one wrong field silently returns a confidently wrong larger set. The screenshot moment is checking the assembled search before trusting the results. The prompt no longer prescribes a route; which route each run takes is logged.

### Type3-2 (github.com, set match)

Prompt: "Find all issues in the microsoft/vscode repository on GitHub labeled 'emmet' that were created between 2016-06-01 and 2016-06-30 inclusive. Report the issue numbers as a comma-separated list."

Answer: 8135, 8324, 8454, 8569.

Check: the reported set must exactly match. Rejects extras and partial sets; dates and counts written in the answer do not count as extras.

Trigger of image: the query combines a label with a creation date range, and a malformed date or wrong qualifier silently yields a different but plausible list, so the screenshot moment is verifying the assembled filter state before trusting the results. This has been verified against both the GitHub API and the rendered page, and one API call on run day confirms the labels are unchanged.

### Type4-1 (coursera.org, string match)

Prompt: "On Coursera, find the course titled 'Wind Energy' offered by the Technical University of Denmark (DTU) and report how many modules it contains."

Answer: 16.

Check: the number tied to the word "modules", or a bare 16 on its own. Rejects a different module count; other numbers such as hours or ratings are ignored.

Trigger of image: the natural path runs from the site's search through a result-card grid to the course page, the kind of flow the vision-only agent completed by coordinate clicks. The module count itself is page text, so this is the weakest trigger of the ten, and the pilot logs which step actually makes auto mode look. This has been verified against the live page.

### Type4-2 (apple.com, string match)

Prompt: "On Apple's online store, find the starting ('From') price for a 13-inch MacBook Air in Sky Blue with the chip option that has the 10-core GPU."

Answer: $1,399.

Check: 1399 once currency symbols are stripped. Rejects the neighboring configurations, 1299 for the 8-core chip and 1499 for the 15-inch model, and records which one the agent hit.

Trigger of image: the agent must navigate from the storefront to the MacBook Air buy page, where the picker starts with nothing selected, so the price appears only after actively selecting all three options; confirming which tiles are highlighted before reading the price is the screenshot moment. A price remembered from the older lineup fails the check. This has been verified against the live page. The task ends at reading the price and never goes near checkout.

### Type5 (wikipedia.org, string match)

Prompt: "According to the population pyramid of Japan in 2026 shown in the English Wikipedia article 'Demographics of Japan', what percentage of the total population are females aged 75-79?"

Answer: 3.9%.

Check: 3.9 as a percentage. Rejects the male bar's 3.3, the table-derived values around 3.2, and a population count like "3.9 million"; mentioning those alongside the correct answer still passes.

Trigger of image: the per-sex labels exist only in the pyramid image, with no alt text and no caption data, and the article's own table computes a different value, so a text-derived answer is wrong by construction. This has been verified by reading the image directly. If the text-only arm passes this task consistently the control is broken and the backup control swaps in.

## How the set of tasks was verified

1. Every answer is grounded against the answer on the live site, and verified via a second method. By second method it means each answer is confirmed by directing from a different page, API, or calculating method. This ensures either the incorrect answer cannot be the answer key or there could be one or even more correct answers. (For example, the task that asks how many papers published in a certain time period can be interpreted into 2 search methods that should both be considered to be true).

2. Every task is re-checked in a real rendered browser, since the raw HTML a script downloads is not the same as the page an agent actually sees. This ensures each task behaves the same way in the environment the pilot really runs in. (For example, this round confirmed the Wolfram answer is exposed through the result image's alt text, and it caught one broken task. Originally there was a task that asks agent to find the largest code change from the frequency graph. The GitHub chart draws different numbers at different window sizes, so no value read from it is stable. That task was replaced.)

3. The pass and fail rules are attacked with tricky example answers. By attack it means a reviewer writes answers a correct agent could realistically produce but the rule would fail (like "not 32038 but 32037"), and wrong answers the rule would wrongly pass. The ten hand-written rules kept breaking under this, so they were replaced by one shared rule system stored in the task file, and every tricky example was frozen into a test list together with its expected verdict. The checker program must pass the entire list before it is allowed to score any run. 
