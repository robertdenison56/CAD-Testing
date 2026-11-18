# RoadDraft eval leaderboard

The benchmark board: every published run on the eval sets, scored by the verifier (`roaddraft.eval`), one ranking per set. The 33 capability probes of Track P are a separate board, closed 2026-10-27: [the probe board](../leaderboard/TRACK_P.md).

Vague prompts only: the request in a sentence, the board's focus. The explicit-prompt board was retired on 2026-11-16; its rows are listed in [RETIRED.md](RETIRED.md).

Track D closed on 2026-11-16: what the board found is written up in `docs/Track_D_Findings.md`. Still to come: GPT-6 Astra's remaining sets, appended as they finish.

![Effective score by model on each eval set](leaderboard.svg)

## Overall: every set, vague prompt

**Best model overall 74.8/100 ± 2.2 (claude-opus-5-5 (medium) via claude-code · single · vague), the weighted mean of its 5 set scores.**

| # | Model · mode · prompt | Effort | Overall | ± | `d1-test` ×1 | `d1-real` ×2 | `hard-pilots` ×2 | `d1-test-hard` ×1 | `d1-real-hard` ×2 | Sets |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **74.8** | 2.2 | 95.5 | 86.7 | 40.2 | 93.7 | 77.6 | 5 of 5 |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **71.0** | 2.0 | 92.8 | 90.5 | 28.6 | 92.9 | 72.1 | 5 of 5 |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **53.8** | 1.9 | 76.0 | 75.1 | 24.1 | 54.5 | 50.8 | 5 of 5 |
| 4 | gpt-6-luna (medium) via codex · single · vague | medium | **46.3** | 1.7 | 76.1 | 71.8 | 2.7 | 43.2 | 51.0 | 5 of 5 |
| 5 | google/gemma-4-12b · single · vague | thinking on | **32.9** | 1.5 | 67.2 | 59.0 | 0.0 | 3.0 | 37.5 | 5 of 5 |
| 6 | qwen/qwen3.5-9b · single · vague | default | **32.5** | 1.7 | 62.6 | 59.6 | 0.9 | 9.4 | 33.5 | 5 of 5 |
|  | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | – | – | 76.3 | – | 8.0 | – | – | 2 of 5 |
|  | google/gemma-4-31B-it · single · vague | thinking on | – | – | 80.1 | – | 1.8 | – | – | 2 of 5 |
|  | mistralai/Mistral-Small-4-119B-2603-NVFP4 · single · vague | high | – | – | 64.0 | – | 2.7 | – | – | 2 of 5 |
|  | nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 · single · vague | thinking on | – | – | 82.4 | – | 4.5 | – | – | 2 of 5 |
|  | openai/gpt-oss-120b · single · vague | medium (default) | – | – | 70.3 | – | 3.4 † | – | – | 2 of 5 |
|  | qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471 | default | – | – | 64.3 | 65.3 | – | – | – | 2 of 5 |
|  | zai-org/glm-4.6v-flash · single · vague | default | – | – | 25.2 | 13.6 | – | – | – | 2 of 5 |
|  | glm-5.3 · single · vague | default | – | – | 66.5 | – | – | – | – | 1 of 5 |
|  | google/gemma-4-26B-A4B-it · single · vague | thinking on | – | – | – | – | 0.9 | – | – | 1 of 5 |
|  | gpt-6-astra (medium) via codex · single · vague | medium | – | – | 96.6 | – | – | – | – | 1 of 5 |

Overall = the weighted mean of the model's effective scores on the 5 sets below, each set's weight beside its name (Robert, 2026-11-13: the real plan sheets and the hard pilots count double the seeded sheets); ± is the sets' 95% half-widths combined with the same weights (root-sum-square). A model ranks here only with a full-set run on every set; cost-subset runs are other tasks and do not count, so a model short of a set is listed unranked with the sets it has. † a text-only `hard-pilots` row, scored on its text pilots alone.

## `d1-test`: seeded sheets

**Best model 96.6/100 on d1-test with the vague prompt (gpt-6-astra (medium) via codex · single · vague, 95% CI 96.1–97.1, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6-astra (medium) via codex · single · vague | medium | **96.6** | 96.1–97.1 | 96.6 | 0% | 64% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-astra-codex-medium-single-vague-v3` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **95.5** | 93.6–96.9 | 95.5 | 0% | 66% | 0% | $0.371 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 3 | gpt-6.1-terra (medium) via codex · single · vague | medium | **92.8** | 90.7–94.8 | 92.8 | 0% | 58% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 4 | nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 · single · vague | thinking on | **82.4** | 78.5–85.9 | 85.3 | 4% | 42% | 0% | – | 100 × 1 | `e3-d1-test-nemotron-3.5-super-vl-single-vague-v3` |
| 5 | google/gemma-4-31B-it · single · vague | thinking on | **80.1** | 77.1–82.7 | 80.7 | 1% | 35% | 0% | – | 100 × 1 | `e3-d1-test-gemma-4-31b-single-vague-v3` |
| 6 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **76.3** | 73.4–79.1 | 77.6 | 2% | 22% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.6-35b-a3b-single-vague-v3` |
| 7 | gpt-6-luna (medium) via codex · single · vague | medium | **76.1** | 72.7–79.3 | 77.8 | 3% | 31% | 1% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-single-vague-v3` |
| 8 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **76.0** | 74.1–77.8 | 76.0 | 0% | 23% | 0% | $0.181 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 9 | openai/gpt-oss-120b · single · vague | medium (default) | **70.3** | 65.0–75.5 | 75.5 | 8% | 39% | 2% | – | 100 × 1 | `e3-d1-test-gpt-oss-120b-single-vague-v3` |
| 10 | google/gemma-4-12b · single · vague | thinking on | **67.2** | 63.6–70.7 | 72.3 | 9% | 32% | 2% | – | 100 × 1 | `e3-d1-test-gemma-4-12b-q8-lms-single-vague-v3` |
| 11 | glm-5.3 · single · vague | default | **66.5** | 62.5–70.2 | 71.5 | 9% | 22% | 2% | $0.042 | 100 × 1 | `e3-d1-test-glm-5.3-single-vague-v3` |
| 12 | qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471 | default | **64.3** | 57.5–70.9 | 69.7 | 7% | 33% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-t0-pin1` |
| 13 | mistralai/Mistral-Small-4-119B-2603-NVFP4 · single · vague | high | **64.0** | 58.6–69.4 | 69.8 | 10% | 27% | 1% | – | 100 × 1 | `e3-d1-test-mistral-small-4-single-vague-v3` |
| 14 | qwen/qwen3.5-9b · single · vague | default | **62.6** | 57.7–67.6 | 66.3 | 6% | 31% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 15 | zai-org/glm-4.6v-flash · single · vague | default | **25.2** | 21.3–29.4 | 26.8 | 7% | 14% | 0% | – | 100 × 1 | `e3-d1-test-glm-4.6v-flash-q4km-lms-single-vague-v3` |

Notes on `d1-test`:

- Every row on this set ran on the pinned run code (3b7e7fe9; the Runpod rows ad6bf5e3), from before the seeded documents carried the title block's four names and date (designed by, drawn by, checked by, date: 234773ec, 2026-11-12). A vague prompt does not state them, so a drafter had nothing to read them from and left them blank or made them up. The rows stay ranked: the blank fields cost a row 0.3 to 0.95 points on the 19 tasks with a title block, and with each row's shortfall added back the order did not change (checked 2026-11-13, before GPT-6 Astra's row, which leads by 1.1).
- gpt-6-astra (medium) via codex · single · vague (`e3-d1-test-gpt-6-astra-codex-medium-single-vague-v3`): as of 2026-11-16 this is GPT-6 Astra's only finished set. Its `d1-real` run stopped at 49 of 100 on the ChatGPT account's weekly limit (not published) and resumes when the limit resets on Nov 20, with `d1-test-hard` after it; it has no overall score until all five sets are in.

## `d1-real`: the sample plan sheets

**Best model 90.5/100 on d1-real with the vague prompt (gpt-6.1-terra (medium) via codex · single · vague, 95% CI 87.9–93.1, hard-fail 1%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Draft | Letter | Sheet | Notes | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **90.5** | 87.9–93.1 | 97.0 ± 3.8 (n 25) | 88.2 ± 6.6 (n 25) | 88.1 ± 4.9 (n 25) | 88.9 ± 4.2 (n 25) | 91.0 | 1% | 52% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **86.7** | 82.8–90.3 | 100.0 ± 0.0 (n 25) | 71.0 ± 11.5 (n 25) | 88.2 ± 5.3 (n 25) | 87.6 ± 7.5 (n 25) | 89.3 | 4% | 48% | 0% | $0.763 | 100 × 1 | `e3-d1-real-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **75.1** | 70.9–79.1 | 85.0 ± 7.5 (n 25) | 68.1 ± 8.2 (n 25) | 73.1 ± 5.4 (n 25) | 74.2 ± 11.5 (n 25) | 78.1 | 5% | 25% | 0% | $0.329 | 100 × 1 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 4 | gpt-6-luna (medium) via codex · single · vague | medium | **71.8** | 67.2–76.0 | 85.0 ± 7.5 (n 25) | 74.8 ± 4.6 (n 25) | 71.3 ± 6.6 (n 25) | 56.0 ± 13.6 (n 25) | 75.0 | 6% | 22% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-single-vague-v3` |
| 5 | qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471 | default | **65.3** | 58.7–71.2 | 80.0 ± 14.0 (n 25) | 75.5 ± 11.4 (n 25) | 60.9 ± 9.6 (n 25) | 44.7 ± 12.1 (n 25) | 68.0 | 4% | 26% | 0% | – | 100 × 1 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-t0-pin1` |
| 6 | qwen/qwen3.5-9b · single · vague | default | **59.6** | 54.3–64.6 | 95.5 ± 4.5 (n 25) | 53.0 ± 11.0 (n 25) | 49.3 ± 9.8 (n 25) | 40.8 ± 13.3 (n 25) | 61.2 | 7% | 29% | 0% | – | 100 × 1 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 7 | google/gemma-4-12b · single · vague | thinking on | **59.0** | 54.1–64.2 | 100.0 ± 0.0 (n 25) | 53.2 ± 9.1 (n 25) | 57.1 ± 10.5 (n 25) | 25.8 ± 14.2 (n 25) | 62.7 | 9% | 30% | 2% | – | 100 × 1 | `e3-d1-real-gemma-4-12b-q8-lms-single-vague-v3` |
| 8 | zai-org/glm-4.6v-flash · single · vague | default | **13.6** | 8.5–19.2 | 20.0 ± 16.0 (n 25) | 7.8 ± 8.8 (n 25) | 23.1 ± 9.0 (n 25) | 3.4 ± 5.1 (n 25) | 13.6 | 0% | 6% | 0% | – | 100 × 1 | `e3-d1-real-glm-4.6v-flash-q4km-lms-single-vague-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Draft = draft linework (`real-draw-alignment`); Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Notes = notes and dimensions (`real-construction-callouts`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

**Cost subset `cost5` on `d1-real`, vague prompt: partial runs, to save cost.** 60 of the set's 100 tasks, 5 of each task type (every task of a smaller type), the fixed draw in `benchmarks/tasksets/cost-subsets.json`; only Runpod runs rank here, and only when they hold every task of the subset with none in error or unfinished. Each full run of the set is re-scored on the same 60 tasks so the rows compare; a subset score is not comparable with a full-set score above.

| # | Model · mode · prompt | Effort | Effective | 95% CI | Tasks × k | Scored as | Run |
|---:|---|---|---:|---|---|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **88.7** | 84.7–92.2 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **82.4** | 76.8–87.5 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 3 | google/gemma-4-31B-it · single · vague | thinking on | **76.8** | 72.2–81.2 | 60 × 1 | subset run (60 of 100) | `e3-d1-real-gemma-4-31b-single-vague-cost5-v3` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **72.8** | 68.4–76.9 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 5 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **70.5** | 65.5–75.2 | 60 × 1 | subset run (60 of 100) | `e3-d1-real-qwen3.6-35b-a3b-single-vague-cost5-v3` |
| 6 | qwen/qwen3.5-9b · single · vague · system extra conventions-v1@89b9a471 | default | **64.2** | 56.5–71.2 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-t0-pin1` |
| 7 | google/gemma-4-12b · single · vague | thinking on | **55.5** | 49.5–61.2 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-gemma-4-12b-q8-lms-single-vague-v3` |
| 8 | qwen/qwen3.5-9b · single · vague | default | **53.2** | 46.3–59.7 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 9 | zai-org/glm-4.6v-flash · single · vague | default | **12.9** | 7.6–18.1 | 60 × 1 | full run, re-scored on the subset's 60 | `e3-d1-real-glm-4.6v-flash-q4km-lms-single-vague-v3` |

## `hard-pilots`: the harder tasks (pass or fail)

**Best model 40.2/100 on hard-pilots with the vague prompt (claude-opus-5-5 (medium) via claude-code · single · vague, 95% CI 33.9–46.4, hard-fail 60%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **40.2** | 33.9–46.4 | 85.8 | 60% | 40% | 0% | $1.20 | 112 × 1 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **28.6** | 23.2–33.9 | 80.3 | 71% | 29% | 0% | – | 112 × 1 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **24.1** | 18.8–28.6 | 69.0 | 76% | 24% | 0% | $0.643 | 112 × 1 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 4 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **8.0** | 4.5–12.5 | 45.5 | 92% | 8% | 0% | – | 112 × 1 | `e3-hard-pilots-qwen3.6-35b-a3b-single-vague-v3` |
| 5 | nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 · single · vague | thinking on | **4.5** | 1.8–8.0 | 43.8 | 96% | 4% | 1% | – | 112 × 1 | `e3-hard-pilots-nemotron-3.5-super-vl-single-vague-v3` |
| 6 | openai/gpt-oss-120b · single · vague · text only (89 of 112 pilots) | medium (default) | **3.4** | 1.1–6.7 | 35.9 | 97% | 3% | 2% | – | 89 × 1 | `e3-hard-pilots-gpt-oss-120b-single-vague-text-v3` |
| 7 | gpt-6-luna (medium) via codex · single · vague | medium | **2.7** | 0.0–5.4 | 39.8 | 97% | 3% | 1% | – | 112 × 1 | `e3-hard-pilots-gpt-6-luna-codex-medium-single-vague-v3` |
| 8 | mistralai/Mistral-Small-4-119B-2603-NVFP4 · single · vague | high | **2.7** | 0.0–5.4 | 30.2 | 97% | 3% | 1% | – | 112 × 1 | `e3-hard-pilots-mistral-small-4-single-vague-v3` |
| 9 | google/gemma-4-31B-it · single · vague | thinking on | **1.8** | 0.0–4.5 | 40.9 | 98% | 2% | 0% | – | 112 × 1 | `e3-hard-pilots-gemma-4-31b-single-vague-v3` |
| 10 | qwen/qwen3.5-9b · single · vague | default | **0.9** | 0.0–2.7 | 25.4 | 99% | 1% | 0% | – | 112 × 1 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 11 | google/gemma-4-26B-A4B-it · single · vague | thinking on | **0.9** | 0.0–2.7 | 28.0 | 99% | 1% | 1% | – | 112 × 1 | `e3-hard-pilots-gemma-4-26b-a4b-single-vague-v3` |
| 12 | google/gemma-4-12b · single · vague | thinking on | **0.0** | 0.0–0.0 | 26.9 | 100% | 0% | 3% | – | 112 × 1 | `e3-hard-pilots-gemma-4-12b-q8-lms-single-vague-v3` |

**Cost subset `cost5` on `hard-pilots`, vague prompt: partial runs, to save cost.** 66 of the set's 112 tasks, 5 of each task type (every task of a smaller type), the fixed draw in `benchmarks/tasksets/cost-subsets.json`; only Runpod runs rank here, and only when they hold every task of the subset with none in error or unfinished. Each full run of the set is re-scored on the same 66 tasks so the rows compare; a subset score is not comparable with a full-set score above.

| # | Model · mode · prompt | Effort | Effective | 95% CI | Tasks × k | Scored as | Run |
|---:|---|---|---:|---|---|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **48.5** | 42.4–56.1 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **36.4** | 30.3–42.4 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **30.3** | 24.2–36.4 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 4 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **9.1** | 3.0–15.2 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-qwen3.6-35b-a3b-single-vague-v3` |
| 5 | nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 · single · vague | thinking on | **6.1** | 1.5–10.6 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-nemotron-3.5-super-vl-single-vague-v3` |
| 6 | gpt-6-luna (medium) via codex · single · vague | medium | **4.5** | 0.0–9.1 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-gpt-6-luna-codex-medium-single-vague-v3` |
| 7 | openai/gpt-oss-120b · single · vague · text only (51 of 66 pilots) | medium (default) | **3.9** | 0.0–7.8 | 51 × 1 | subset run, its 51 text pilots (no image pilot run) | `e3-hard-pilots-gpt-oss-120b-single-vague-cost5-text-v3` |
| 8 | google/gemma-4-31B-it · single · vague | thinking on | **3.0** | 0.0–7.6 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-gemma-4-31b-single-vague-v3` |
| 9 | mistralai/Mistral-Small-4-119B-2603-NVFP4 · single · vague | high | **3.0** | 0.0–6.1 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-mistral-small-4-single-vague-v3` |
| 10 | google/gemma-4-26B-A4B-it · single · vague | thinking on | **1.5** | 0.0–4.5 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-gemma-4-26b-a4b-single-vague-v3` |
| 11 | qwen/qwen3.5-9b · single · vague | default | **1.5** | 0.0–4.5 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 12 | google/gemma-4-12b · single · vague | thinking on | **0.0** | 0.0–0.0 | 66 × 1 | full run, re-scored on the subset's 66 | `e3-hard-pilots-gemma-4-12b-q8-lms-single-vague-v3` |

Notes on `hard-pilots`:

- Pass or fail on 112 pilots at one sample each: the leading row's 95% interval is 33.9 to 46.4, a half-width of 6.2 points, over the 5-point target the leading rows of the four D1 sets meet. It is left so; a set of 112 pass-or-fail tasks cannot reach 5 points at k = 1.
- google/gemma-4-12b · single · vague (`e3-hard-pilots-gemma-4-12b-q8-lms-single-vague-v3`): eight pilots ended on the provider's 30-minute turn limit and were rerun once (the stall rule); four did so again and stand as fails (p01-redraw-alignment-cflpnp, p01-redraw-alignment-wfl20, p10-typical-fdot9132, p10-typical-wfl05). Four more episodes were rerun after an engine or harness error. The final record is 96 submits and 16 budget stops (8 context, 4 turn limit, 3 clock, 1 faults), with no pass.

## `d1-test-hard`: seeded sheets, the whole job (3-5 curves, 2-3 sheets)

**Best model 93.7/100 on d1-test-hard with the vague prompt (claude-opus-5-5 (medium) via claude-code · single · vague, 95% CI 93.1–94.3, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **93.7** | 93.1–94.3 | 93.7 | 0% | 6% | 0% | $1.09 | 100 × 1 | `e3-d1-test-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **92.9** | 90.7–94.3 | 92.9 | 0% | 11% | 0% | – | 100 × 1 | `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **54.5** | 49.4–59.5 | 72.5 | 23% | 0% | 0% | $0.584 | 100 × 1 | `e3-d1-test-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 4 | gpt-6-luna (medium) via codex · single · vague | medium | **43.2** | 37.8–48.4 | 54.7 | 21% | 0% | 3% | – | 100 × 1 | `e3-d1-test-hard-gpt-6-luna-codex-medium-single-vague-v3` |
| 5 | qwen/qwen3.5-9b · single · vague | default | **9.4** | 6.4–12.7 | 37.7 | 65% | 0% | 0% | – | 100 × 1 | `e3-d1-test-hard-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 6 | google/gemma-4-12b · single · vague | thinking on | **3.0** | 1.2–5.2 | 52.9 | 90% | 0% | 2% | – | 100 × 1 | `e3-d1-test-hard-gemma-4-12b-q8-lms-single-vague-v3` |

**Cost subset `cost5` on `d1-test-hard`, vague prompt: partial runs, to save cost.** 25 of the set's 100 tasks, 5 of each task type (every task of a smaller type), the fixed draw in `benchmarks/tasksets/cost-subsets.json`; only Runpod runs rank here, and only when they hold every task of the subset with none in error or unfinished. Each full run of the set is re-scored on the same 25 tasks so the rows compare; a subset score is not comparable with a full-set score above.

| # | Model · mode · prompt | Effort | Effective | 95% CI | Tasks × k | Scored as | Run |
|---:|---|---|---:|---|---|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **94.4** | 92.9–95.7 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **90.2** | 82.0–95.0 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **51.1** | 41.2–61.4 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 4 | gpt-6-luna (medium) via codex · single · vague | medium | **47.2** | 38.7–55.0 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-gpt-6-luna-codex-medium-single-vague-v3` |
| 5 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **41.7** | 29.1–54.2 | 25 × 1 | subset run (25 of 100) | `e3-d1-test-hard-qwen3.6-35b-a3b-single-vague-cost5-v3` |
| 6 | qwen/qwen3.5-9b · single · vague | default | **13.4** | 8.4–18.1 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 7 | google/gemma-4-12b · single · vague | thinking on | **3.3** | 0.0–8.0 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-test-hard-gemma-4-12b-q8-lms-single-vague-v3` |

Notes on `d1-test-hard`:

- Every row on this set ran on the pinned run code (3b7e7fe9; the Runpod row ad6bf5e3), from before the seeded documents carried the title block's four names and date (234773ec, 2026-11-12). 80 of the 100 tasks letter a title block and every model left the four fields blank on all of them: 1.3 to 1.55 points a row, which reorders nothing. The rows stay ranked.

## `d1-real-hard`: the sample plan sheets, the whole job

**Best model 77.6/100 on d1-real-hard with the vague prompt (claude-opus-5-5 (medium) via claude-code · single · vague, 95% CI 72.7–82.3, hard-fail 7%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Letter | Sheet | Job | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **77.6** | 72.7–82.3 | 81.9 ± 11.7 (n 20) | 91.7 ± 4.2 (n 41) | 60.6 ± 9.3 (n 39) | 83.0 | 7% | 1% | 0% | $0.958 | 100 × 1 | `e3-d1-real-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **72.1** | 66.7–77.0 | 78.9 ± 17.3 (n 20) | 92.2 ± 3.9 (n 41) | 47.5 ± 8.3 (n 39) | 74.9 | 4% | 8% | 0% | – | 100 × 1 | `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | gpt-6-luna (medium) via codex · single · vague | medium | **51.0** | 47.8–54.4 | 60.3 ± 7.0 (n 20) | 69.1 ± 3.6 (n 41) | 27.3 ± 6.4 (n 39) | 54.3 | 7% | 0% | 2% | – | 100 × 1 | `e3-d1-real-hard-gpt-6-luna-codex-medium-single-vague-v3` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **50.8** | 47.2–54.0 | 60.9 ± 6.5 (n 20) | 65.2 ± 4.1 (n 41) | 30.4 ± 6.8 (n 39) | 56.1 | 11% | 0% | 0% | $0.465 | 100 × 1 | `e3-d1-real-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 5 | google/gemma-4-12b · single · vague | thinking on | **37.5** | 34.8–40.2 | 51.6 ± 3.7 (n 20) | 45.8 ± 4.8 (n 41) | 21.6 ± 4.6 (n 39) | 39.3 | 7% | 0% | 3% | – | 100 × 1 | `e3-d1-real-hard-gemma-4-12b-q8-lms-single-vague-v3` |
| 6 | qwen/qwen3.5-9b · single · vague | default | **33.5** | 30.6–36.2 | 50.9 ± 6.1 (n 20) | 42.5 ± 4.8 (n 41) | 15.0 ± 3.8 (n 39) | 34.2 | 3% | 0% | 0% | – | 100 × 1 | `e3-d1-real-hard-qwen3.5-9b-q4km-lms-single-vague-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Job = the whole job (`real-sheet-job`, `real-annotate-job`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

**Cost subset `cost5` on `d1-real-hard`, vague prompt: partial runs, to save cost.** 25 of the set's 100 tasks, 5 of each task type (every task of a smaller type), the fixed draw in `benchmarks/tasksets/cost-subsets.json`; only Runpod runs rank here, and only when they hold every task of the subset with none in error or unfinished. Each full run of the set is re-scored on the same 25 tasks so the rows compare; a subset score is not comparable with a full-set score above.

| # | Model · mode · prompt | Effort | Effective | 95% CI | Tasks × k | Scored as | Run |
|---:|---|---|---:|---|---|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **72.2** | 60.5–83.1 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-claude-opus-5-5-claude-code-medium-single-vague-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · vague | medium | **59.2** | 48.3–70.4 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 3 | Qwen/Qwen3.6-35B-A3B · single · vague | thinking on (default) | **50.6** | 46.3–55.6 | 25 × 1 | subset run (25 of 100) | `e3-d1-real-hard-qwen3.6-35b-a3b-single-vague-cost5-v3` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **47.6** | 39.7–55.0 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-claude-sonnet-5-5-claude-code-medium-single-vague-v3` |
| 5 | gpt-6-luna (medium) via codex · single · vague | medium | **47.4** | 42.0–52.6 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-gpt-6-luna-codex-medium-single-vague-v3` |
| 6 | google/gemma-4-12b · single · vague | thinking on | **38.3** | 34.6–42.1 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-gemma-4-12b-q8-lms-single-vague-v3` |
| 7 | qwen/qwen3.5-9b · single · vague | default | **26.9** | 22.2–32.2 | 25 × 1 | full run, re-scored on the subset's 25 | `e3-d1-real-hard-qwen3.5-9b-q4km-lms-single-vague-v3` |

## Published runs that are not ranked

- `e3-d1-variance-gemma-4-12b-single` (d1-variance, 100 episodes): google/gemma-4-12B-it · single · explicit, effort thinking on 69.3 ± 3.0 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots, d1-test-hard, d1-real-hard).
- `e3-d1-variance-qwen3.6-35b-a3b-single` (d1-variance, 100 episodes): Qwen/Qwen3.6-35B-A3B · single · explicit, effort thinking on (default) 86.7 ± 2.7 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots, d1-test-hard, d1-real-hard).
- `e3-hard-pilots-glm-5.3-single-vague-cost5-text-v3` (hard-pilots, 17 episodes, **partial, not scored: 17 of 66 tasks**): glm-5.3 · single · vague, effort default (17 tasks × 1). Not ranked: partial, not scored: covers 17 of its cost subset's 66 tasks; a row ranks once the run holds every task with none in error or unfinished.

Each set is its own ranking: `d1-test` is 100 held-out tasks from the seeded generator (one synthetic centerline per task); `d1-real` is 100 held-out tasks on the redrafted sample plan sheets (Caltrans, WFL, CFL, FDOT), 25 in each of four question groups (draft linework, letter alignment data, produce the sheet, notes and dimensions), each group a column beside the blended score; `hard-pilots` is the 112 harder-task pilots on the sample sheets, each graded pass (100) or fail (0) by its own check, with the share of its items done as the rubric column; `d1-test-hard` is 100 held-out seeded whole-sheet jobs (three to five curves on two or three sheets, a station equation on one in five: the plan sheet with its pavement, the alignment created from stated geometry and then drafted, the sheet file lettered through its base drawing); `d1-real-hard` is 100 tasks on the redrafted sheets, every whole job (a sheet drafted from its base files or annotated from blank, construction callouts included) and the heaviest whole-line tasks `d1-real` did not draw. Within a set the rows rank on that set alone; the overall table at the top is the one place a model's sets are averaged, the real sheets and the hard pilots weighted double.

Each prompt level ranks apart (Robert, 2026-11-08): this file ranks the vague-prompt runs (the request in a sentence, the way a PE would ask for it; what belongs on the sheet is the drafter's to know), the main board and its focus; a score at one prompt level is not comparable with a score at the other. The explicit-prompt runs (the full brief, stating every standard the task is graded on) had a board of their own until it was retired on 2026-11-16 (`RETIRED.md`). Every task has both prompts: a pilot's vague brief keeps what the drafter cannot know (the files, lines, stations and data given) and leaves its drafting standards to the drafter, graded by the lenient rules where the brief no longer states them.

A run that misses a task of its set, or has an episode that ended in error or never finished, is partial and not scored: it is listed on the main board without a score. The one exception is a cost-subset run (`benchmarks/tasksets/cost-subsets.json`: five tasks of each task type, Runpod runs only, to save cost), ranked in a table of its own under its set beside the full runs re-scored on the same tasks; it too is partial and not scored if it misses a task of the subset or has an episode in error or unfinished. A `hard-pilots` run that holds every text pilot of its set or subset and none of the pilots that come with a page (a model that takes no images) is not partial: it stays in its table, marked **text only**, scored on its text pilots alone, which is not the same tasks as the rows beside it.

Effective score: 0 on a hard fail, else the rubric score; per task over its samples, then over tasks; 95% CI a bootstrap over tasks within task type. Rows rank on the effective mean, then hard-fail rate, invalid-call rate and cost. Effort is the level the run set with `--effort`, else what the request body set, else the model's default marked (default), as read from its chat template or catalog (`roaddraft.effort`); plain default is one not looked up. A model run at two efforts is two rows.

_Generated by `scripts/make_leaderboard.py` from `benchmarks/runs/*/summary.json`; do not edit._
