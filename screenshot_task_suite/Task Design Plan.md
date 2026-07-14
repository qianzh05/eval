## Screenshot Task Design

### Purpose and Background

Planning to design a suite of 100 web tasks that focus on the screenshot decision in web agents. The goal of running this test suite is to answer this question: On tasks where current agents want screenshots, does attaching them change rate of success, and at how much additional cost?

The metrics that will be primarily collected are cost per successful task (both in tokens and dollars) and task latency. And of course success rate. Since 100 tasks is not enough to statistically prove a small success rate difference in either direction, success will be compared against a threshold decided in advance. Vision off counts as matching vision on only if the results rule out it being more than 5 points worse. The threshold is set now, before running, so it cannot be adjusted to fit the outcome.

In addition, on WebVoyager, there are a large number of failures that are verified to be CAPTCHAs, and a number of tasks with stale instructions, creating a higher level of noise throughout the whole test suite. The sites chosen in the custom designed suite aim to be more bot tolerating and have deterministic checks at the LLM evaluation phase such that the screenshot (on/off) as an variable can be isolated.

Based on the 91 screenshot requests throughout the "auto" run, here are the observed trigger categories:

| Category                                | Number | Informative? |
| --------------------------------------- | ------ | ------------ |
| Reconfirming a page that had not loaded | 37     | rarely       |
| Stuck-interaction loops                 | 22     | rarely       |
| Blocking overlay the DOM text missed    | 13     | yes          |
| Start-of-run orientation                | 9      | no           |
| Pre-submit form checks                  | 5      | sometimes    |
| Reading rendered output                 | 5      | yes and very |

### Rule

Every task should contain at least one step that falls in one of the trigger categories above, weighted towards the categories where screenshots tend to be more useful. Following are the possible hidden states where screenshots are more likely to be required and helpful:

- Type 1: Rendered output. The answer is presented client-side and text extraction is unreliable (as in the Wolfram Alpha site)
- Type 2: Overlay / dynamic UI state such as a popup, modal or a panel.
- Type 3: Pre-submit verification such as a multi field form where the correctness of the form state matters for submission 
- Type 4: Interactions involving large targets
- Type 5: The answer exists only in an image, now alt text, where vision is definitely required.

### Site Shortlist

Throughout the runs, it is observed that certain sites are clean and present little to no bot walls, which include: arxiv.org, wikipedia.org, github.com, wolframalpha.com.

There are also some sites that can be attempted with a slight chance of bot wall: hugingface.co, coursear.org, apple.com. Should be fine if the task does not include logging in.

### Task Format

Each task is written as one JSON record: id, site, trigger category included, prompt, answer spec, check type, authored date, and a note that can be empty.

### Verification

Despite the LLM used as the evaluation model in WebVoyager, the suite would lean towards deterministic checks where answers can be written at authored time.

### Run

| Dimension | Values                                                       |
| --------- | ------------------------------------------------------------ |
| Vision    | on (attach every step) and off. Run with auto for the first 10 tasks to see if the task design is working as intended |
| Repeats   | 2. More if the 2 results disagree.                           |
| Agent     | Latest version of browser-use                                |
| Model     | sonnet 4.6                                                   |