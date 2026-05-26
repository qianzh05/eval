# Post-hoc timing analysis

_Generated from saved history.json metadata. Per-step durations are real (step_end_time − step_start_time). Sub-phase breakdown (LLM vs browser action vs DOM vs screenshot) is **not** recoverable — browser-use never separated those._


## Cross-run comparison

| metric | OLD Mac vision-true | OLD Mac vision-false | NEW VM vision-true | NEW VM vision-false |
|---|---|---|---|---|
| tasks with history | 643 | 643 | 189 | 640 |
| step samples (total) | 8956 | 9595 | 2375 | 5653 |
| mean step duration (s) | 113.9 | 46.8 | 20.5 | 19.4 |
| p50 step duration (s) | 66.2 | 37.5 | 17.5 | 16.9 |
| p90 step duration (s) | 212.2 | 81.3 | 34.7 | 32.9 |
| input tokens (total) | 60,488,569 | 55,533,265 | — | — |
| input cost $ (real) | $181.47 | $166.60 | — | — |

## OLD Mac vision-true

- tasks with history: **643**
- total per-step samples: **8,956**
- step duration (s): mean **113.9** · p50 **66.2** · p90 **212.2** · p95 **348.4** · max **3378**
- input tokens per step: mean **6,754** · p50 **6,075** · p90 **10,689**
- **total input tokens: 60,488,569**  →  **input cost ≈ $181.47**

### Per-site step duration

| site | n_steps | mean_s | p50_s | p90_s | mean_tok |
|---|---|---|---|---|---|
| Booking | 1261 | 136.5 | 65.7 | 318.2 | 7,462 |
| Google Flights | 1115 | 120.3 | 72.2 | 190.9 | 7,807 |
| Google Search | 901 | 85.6 | 58.0 | 142.3 | 6,431 |
| Cambridge Dictionary | 827 | 86.0 | 54.6 | 133.2 | 6,331 |
| Google Map | 599 | 152.1 | 79.6 | 216.7 | 6,526 |
| Huggingface | 542 | 80.5 | 57.2 | 122.0 | 6,919 |
| BBC News | 528 | 182.1 | 102.6 | 366.1 | 6,589 |
| Apple | 463 | 77.3 | 53.7 | 153.5 | 5,312 |
| ArXiv | 446 | 85.0 | 66.0 | 148.8 | 6,534 |
| Wolfram Alpha | 437 | 72.9 | 41.1 | 134.1 | 5,969 |
| Amazon | 425 | 114.4 | 81.7 | 217.2 | 7,809 |
| Allrecipes | 384 | 177.6 | 83.4 | 380.0 | 5,819 |
| Coursera | 371 | 128.5 | 82.7 | 236.6 | 5,526 |
| ESPN | 346 | 125.9 | 80.2 | 203.6 | 7,079 |
| GitHub | 311 | 67.5 | 55.7 | 106.2 | 6,981 |

### Step duration by outcome

| outcome | n_steps | mean_s | p50_s | p90_s |
|---|---|---|---|---|
| success | 4844 | 119.7 | 70.7 | 213.1 |
| failed | 4035 | 108.2 | 61.7 | 213.6 |
| unknown | 77 | 52.0 | 47.3 | 73.9 |

### 10 slowest tasks (by total step time)

| task_id | outcome | n_steps | mean_step_s | total_step_s |
|---|---|---|---|---|
| Google Flights--13 | success | 23 | 869.5 | 20000 |
| BBC News--29 | failed | 30 | 620.7 | 18620 |
| Booking--39 | failed | 28 | 561.9 | 15733 |
| Google Flights--38 | failed | 29 | 533.7 | 15476 |
| Google Map--1 | success | 8 | 1926.9 | 15415 |
| Booking--5 | failed | 29 | 437.5 | 12688 |
| Booking--31 | failed | 26 | 475.9 | 12373 |
| Google Map--12 | success | 11 | 969.9 | 10669 |
| Booking--37 | failed | 27 | 376.7 | 10170 |
| Google Search--11 | failed | 30 | 305.8 | 9173 |

## OLD Mac vision-false

- tasks with history: **643**
- total per-step samples: **9,595**
- step duration (s): mean **46.8** · p50 **37.5** · p90 **81.3** · p95 **103.7** · max **843**
- input tokens per step: mean **5,788** · p50 **5,088** · p90 **9,570**
- **total input tokens: 55,533,265**  →  **input cost ≈ $166.60**

### Per-site step duration

| site | n_steps | mean_s | p50_s | p90_s | mean_tok |
|---|---|---|---|---|---|
| Booking | 1273 | 44.7 | 29.7 | 84.7 | 6,074 |
| Google Flights | 1253 | 42.3 | 36.4 | 70.9 | 6,018 |
| Cambridge Dictionary | 988 | 47.4 | 42.9 | 75.2 | 4,739 |
| Google Search | 930 | 39.6 | 32.9 | 69.4 | 6,004 |
| Google Map | 573 | 51.1 | 42.8 | 87.5 | 5,895 |
| Huggingface | 547 | 37.7 | 32.5 | 62.9 | 6,728 |
| ArXiv | 534 | 52.4 | 38.7 | 90.8 | 6,216 |
| BBC News | 529 | 59.5 | 46.4 | 102.8 | 5,938 |
| Amazon | 503 | 52.9 | 43.1 | 89.1 | 6,867 |
| Apple | 492 | 44.2 | 34.5 | 73.2 | 4,596 |
| Wolfram Alpha | 488 | 32.3 | 25.0 | 59.8 | 4,712 |
| Coursera | 440 | 51.5 | 43.3 | 87.2 | 5,184 |
| Allrecipes | 383 | 68.2 | 46.2 | 120.3 | 4,959 |
| GitHub | 334 | 37.8 | 35.0 | 61.3 | 6,536 |
| ESPN | 328 | 62.6 | 57.0 | 103.2 | 6,398 |

### Step duration by outcome

| outcome | n_steps | mean_s | p50_s | p90_s |
|---|---|---|---|---|
| success | 4544 | 50.4 | 39.7 | 86.7 |
| failed | 4990 | 43.6 | 35.2 | 76.6 |
| unknown | 61 | 39.1 | 35.3 | 71.9 |

### 10 slowest tasks (by total step time)

| task_id | outcome | n_steps | mean_step_s | total_step_s |
|---|---|---|---|---|
| Cambridge Dictionary--3 | failed | 30 | 123.1 | 3692 |
| Booking--31 | failed | 30 | 107.5 | 3226 |
| Booking--1 | failed | 30 | 107.4 | 3222 |
| Apple--1 | success | 20 | 157.3 | 3147 |
| BBC News--29 | failed | 30 | 99.1 | 2973 |
| Coursera--38 | failed | 30 | 96.8 | 2905 |
| BBC News--20 | failed | 30 | 94.6 | 2838 |
| Google Flights--29 | failed | 30 | 93.8 | 2814 |
| Booking--30 | failed | 30 | 93.7 | 2811 |
| Booking--37 | failed | 30 | 93.3 | 2799 |

## NEW VM vision-true

- tasks with history: **189**
- total per-step samples: **2,375**
- step duration (s): mean **20.5** · p50 **17.5** · p90 **34.7** · p95 **42.3** · max **151**

### Per-site step duration

| site | n_steps | mean_s | p50_s | p90_s | mean_tok |
|---|---|---|---|---|---|
| Booking | 742 | 23.9 | 21.9 | 38.6 | — |
| Google Flights | 635 | 13.6 | 12.3 | 20.0 | — |
| Apple | 179 | 21.3 | 19.8 | 32.2 | — |
| Cambridge Dictionary | 151 | 17.3 | 14.6 | 31.9 | — |
| Allrecipes | 103 | 20.4 | 19.3 | 31.9 | — |
| Coursera | 97 | 43.1 | 36.6 | 67.5 | — |
| Google Search | 80 | 17.8 | 17.6 | 30.2 | — |
| Huggingface | 78 | 19.9 | 19.3 | 29.0 | — |
| ESPN | 62 | 32.4 | 30.0 | 52.0 | — |
| Amazon | 61 | 28.4 | 24.9 | 43.0 | — |
| ArXiv | 60 | 15.1 | 15.2 | 20.5 | — |
| Wolfram Alpha | 57 | 13.9 | 10.9 | 20.9 | — |
| BBC News | 43 | 17.9 | 16.6 | 30.2 | — |
| GitHub | 17 | 21.6 | 20.8 | 32.1 | — |
| Google Map | 10 | 13.7 | 12.5 | 17.9 | — |

### Step duration by outcome

| outcome | n_steps | mean_s | p50_s | p90_s |
|---|---|---|---|---|
| success | 1522 | 18.2 | 15.4 | 30.7 |
| failed | 829 | 25.1 | 21.8 | 41.6 |
| unknown | 24 | 10.8 | 9.5 | 16.4 |

### 10 slowest tasks (by total step time)

| task_id | outcome | n_steps | mean_step_s | total_step_s |
|---|---|---|---|---|
| Coursera--3 | failed | 17 | 59.8 | 1016 |
| Coursera--17 | failed | 27 | 37.2 | 1004 |
| Coursera--8 | failed | 20 | 49.5 | 990 |
| Amazon--30 | failed | 23 | 38.0 | 875 |
| Coursera--28 | failed | 23 | 37.3 | 857 |
| Booking--13 | failed | 29 | 28.6 | 829 |
| Booking--15 | success | 28 | 28.0 | 783 |
| Booking--12 | failed | 28 | 27.8 | 779 |
| Booking--5 | failed | 29 | 25.9 | 751 |
| Apple--4 | failed | 28 | 26.6 | 745 |

## NEW VM vision-false

- tasks with history: **640**
- total per-step samples: **5,653**
- step duration (s): mean **19.4** · p50 **16.9** · p90 **32.9** · p95 **40.0** · max **100**

### Per-site step duration

| site | n_steps | mean_s | p50_s | p90_s | mean_tok |
|---|---|---|---|---|---|
| Booking | 963 | 23.5 | 20.9 | 39.1 | — |
| Google Flights | 812 | 14.5 | 13.3 | 22.7 | — |
| Wolfram Alpha | 669 | 12.8 | 10.8 | 21.3 | — |
| Apple | 372 | 20.0 | 18.2 | 30.5 | — |
| Huggingface | 318 | 24.8 | 22.7 | 39.5 | — |
| Coursera | 295 | 24.8 | 21.1 | 41.5 | — |
| ArXiv | 293 | 20.2 | 16.8 | 32.0 | — |
| BBC News | 283 | 16.7 | 14.2 | 31.0 | — |
| Amazon | 276 | 27.6 | 25.1 | 41.0 | — |
| Google Map | 267 | 15.6 | 14.3 | 23.6 | — |
| Allrecipes | 249 | 16.6 | 15.0 | 25.5 | — |
| ESPN | 230 | 26.2 | 23.4 | 42.4 | — |
| Google Search | 217 | 19.9 | 18.4 | 36.0 | — |
| Cambridge Dictionary | 212 | 15.4 | 12.7 | 26.3 | — |
| GitHub | 197 | 20.8 | 19.8 | 32.5 | — |

### Step duration by outcome

| outcome | n_steps | mean_s | p50_s | p90_s |
|---|---|---|---|---|
| success | 4106 | 18.6 | 16.1 | 31.7 |
| failed | 1454 | 21.9 | 19.3 | 37.4 |
| unknown | 93 | 19.1 | 16.8 | 32.6 |

### 10 slowest tasks (by total step time)

| task_id | outcome | n_steps | mean_step_s | total_step_s |
|---|---|---|---|---|
| Amazon--11 | failed | 30 | 30.8 | 925 |
| Google Search--11 | failed | 30 | 29.8 | 893 |
| ArXiv--1 | failed | 24 | 37.0 | 888 |
| Booking--6 | success | 29 | 27.8 | 805 |
| Coursera--28 | failed | 29 | 27.4 | 796 |
| ESPN--35 | failed | 28 | 27.9 | 782 |
| Booking--9 | failed | 29 | 26.8 | 777 |
| Booking--3 | success | 29 | 26.4 | 764 |
| Huggingface--20 | failed | 25 | 30.4 | 760 |
| Huggingface--0 | failed | 29 | 25.9 | 752 |