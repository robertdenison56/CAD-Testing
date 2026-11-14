# RoadDraft eval leaderboard: explicit prompts

The benchmark board: every published run on the eval sets, scored by the verifier (`roaddraft.eval`), one ranking per set. The 33 capability probes of Track P are a separate board, closed 2026-10-27: [the probe board](../leaderboard/TRACK_P.md).

The explicit-prompt runs, ranked on their own: a score at the explicit level is not comparable with one at the vague level, which is the main board's focus: [the main board](LEADERBOARD.md).

## Overall: every set, explicit prompt

**Best model overall 82.5/100 ± 1.6 (gpt-6.1-terra (medium) via codex · single · explicit), the weighted mean of its 5 set scores.**

| # | Model · mode · prompt | Effort | Overall | ± | `d1-test` ×1 | `d1-real` ×2 | `hard-pilots` ×2 | `d1-test-hard` ×1 | `d1-real-hard` ×2 | Sets |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **82.5** | 1.6 | 96.2 | 95.4 | 40.2 | 98.5 | 97.1 | 5 of 5 |
| 2 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **74.2** | 2.1 | 88.3 | 89.9 | 33.0 | 90.8 | 84.5 | 5 of 5 |
| 3 | gpt-6-luna (medium) via codex · single · explicit | medium | **61.8** | 2.1 | 91.3 | 84.3 | 5.4 | 56.3 | 83.7 | 5 of 5 |
|  | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | – | – | – | – | 61.6 | 98.5 | 96.1 | 3 of 5 |
|  | gpt-6-luna (medium) via codex · self_correct · explicit | medium | – | – | 94.8 | 84.5 | 7.1 | – | – | 3 of 5 |
|  | gpt-6-luna (medium) via codex · vision · explicit | medium | – | – | 93.7 | 84.9 | 4.5 | – | – | 3 of 5 |
|  | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | – | – | 100.0 | 99.8 | 50.9 | – | – | 3 of 5 |
|  | qwen/qwen3.5-9b · single · explicit | default | – | – | 74.0 | 70.8 | 2.7 | – | – | 3 of 5 |
|  | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | – | – | 100.0 | 100.0 | – | – | – | 2 of 5 |
|  | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | – | – | 91.7 | 92.1 | – | – | – | 2 of 5 |
|  | google/gemma-4-12b · single · explicit | thinking on | – | – | 64.5 | 68.6 | – | – | – | 2 of 5 |
|  | claude-opus-5-5 (medium) via claude-code · vision · explicit | medium | – | – | 100.0 | – | – | – | – | 1 of 5 |
|  | claude-sonnet-5-5 (medium) via claude-code · vision · explicit | medium | – | – | 92.9 | – | – | – | – | 1 of 5 |
|  | gpt-6.1-terra (medium) via codex · vision · explicit | medium | – | – | 100.0 | – | – | – | – | 1 of 5 |
|  | zai-org/glm-4.6v-flash · single · explicit | default | – | – | – | 19.6 | – | – | – | 1 of 5 |

Overall = the weighted mean of the model's effective scores on the 5 sets below, each set's weight beside its name (Robert, 2026-11-13: the real plan sheets and the hard pilots count double the seeded sheets); ± is the sets' 95% half-widths combined with the same weights (root-sum-square). A model ranks here only with a full-set run on every set; cost-subset runs are other tasks and do not count, so a model short of a set is listed unranked with the sets it has. † a text-only `hard-pilots` row, scored on its text pilots alone.

## `d1-test`: seeded sheets

**Best model 100.0/100 on d1-test with the explicit prompt (claude-opus-5-5 (medium) via claude-code · vision · explicit, 95% CI 100.0–100.0, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · vision · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 96% | 0% | $0.410 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-vision` |
| 2 | gpt-6.1-terra (medium) via codex · vision · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 94% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-vision` |
| 3 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 96% | 0% | $0.371 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-self_correct` |
| 4 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 94% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-self_correct` |
| 5 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **96.2** | 93.8–98.1 | 96.2 | 0% | 82% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-single` |
| 6 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **94.8** | 91.5–97.6 | 95.7 | 1% | 79% | 1% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-self_correct-v3` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | medium | **93.7** | 91.6–96.2 | 93.7 | 0% | 78% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-vision-v3` |
| 8 | claude-sonnet-5-5 (medium) via claude-code · vision · explicit | medium | **92.9** | 90.6–95.6 | 92.9 | 0% | 73% | 0% | $0.201 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-vision` |
| 9 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | **91.7** | 88.9–94.5 | 92.5 | 1% | 78% | 0% | $0.219 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 10 | gpt-6-luna (medium) via codex · single · explicit | medium | **91.3** | 87.8–94.6 | 93.6 | 3% | 73% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-single-v3` |
| 11 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **88.3** | 84.0–92.3 | 90.8 | 3% | 69% | 0% | $0.213 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single` |
| 12 | qwen/qwen3.5-9b · single · explicit | default | **74.0** | 68.5–79.6 | 82.0 | 10% | 37% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-v3` |
| 13 | google/gemma-4-12b · single · explicit | thinking on | **64.5** | 59.0–70.3 | 79.1 | 20% | 29% | 5% | – | 100 × 1 | `e3-d1-test-gemma-4-12b-q8-lms-single-v3` |

## `d1-real`: the sample plan sheets

**Best model 100.0/100 on d1-real with the explicit prompt (claude-opus-5-5 (medium) via claude-code · self_correct · explicit, 95% CI 99.9–100.0, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Draft | Letter | Sheet | Notes | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | **100.0** | 99.9–100.0 | 100.0 ± 0.0 (n 25) | 99.9 ± 0.1 (n 25) | 100.0 ± 0.1 (n 25) | 100.0 ± 0.0 (n 25) | 100.0 | 0% | 98% | 0% | $0.658 | 100 × 1 | `e3-d1-real-claude-opus-5-5-claude-code-medium-self_correct` |
| 2 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **99.8** | 99.5–100.0 | 100.0 ± 0.0 (n 25) | 99.8 ± 0.3 (n 25) | 100.0 ± 0.0 (n 25) | 99.4 ± 0.8 (n 25) | 99.8 | 0% | 97% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-self_correct` |
| 3 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **95.4** | 93.0–97.4 | 100.0 ± 0.0 (n 25) | 99.5 ± 0.3 (n 25) | 95.2 ± 3.6 (n 25) | 87.0 ± 7.8 (n 25) | 96.3 | 1% | 72% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-single` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | **92.1** | 88.8–95.0 | 100.0 ± 0.0 (n 25) | 94.2 ± 1.0 (n 25) | 95.8 ± 3.8 (n 25) | 78.4 ± 11.6 (n 25) | 94.1 | 3% | 68% | 0% | $0.334 | 100 × 1 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 5 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **89.9** | 86.3–93.1 | 100.0 ± 0.0 (n 25) | 95.8 ± 1.6 (n 25) | 88.3 ± 7.1 (n 25) | 75.5 ± 11.6 (n 25) | 93.1 | 4% | 58% | 0% | $0.339 | 100 × 1 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single` |
| 6 | gpt-6-luna (medium) via codex · vision · explicit | medium | **84.9** | 81.1–88.8 | 100.0 ± 0.0 (n 25) | 97.9 ± 2.3 (n 25) | 94.1 ± 3.7 (n 25) | 47.6 ± 15.2 (n 25) | 87.0 | 4% | 64% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-vision-v3` |
| 7 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **84.5** | 79.7–88.8 | 96.0 ± 6.0 (n 25) | 94.0 ± 4.7 (n 25) | 93.5 ± 6.7 (n 25) | 54.6 ± 14.6 (n 25) | 87.7 | 6% | 64% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-self_correct-v3` |
| 8 | gpt-6-luna (medium) via codex · single · explicit | medium | **84.3** | 80.2–88.3 | 100.0 ± 0.0 (n 25) | 96.6 ± 1.9 (n 25) | 92.4 ± 5.3 (n 25) | 48.2 ± 15.0 (n 25) | 88.7 | 8% | 53% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-single-v3` |
| 9 | qwen/qwen3.5-9b · single · explicit | default | **70.8** | 66.0–75.7 | 100.0 ± 0.0 (n 25) | 75.4 ± 9.5 (n 25) | 72.8 ± 10.1 (n 25) | 35.3 ± 13.5 (n 25) | 75.5 | 10% | 38% | 0% | – | 100 × 1 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-v3` |
| 10 | google/gemma-4-12b · single · explicit | thinking on | **68.6** | 64.4–72.7 | 100.0 ± 0.0 (n 25) | 75.2 ± 6.6 (n 25) | 68.8 ± 9.4 (n 25) | 30.4 ± 12.0 (n 25) | 74.3 | 11% | 35% | 4% | – | 100 × 1 | `e3-d1-real-gemma-4-12b-q8-lms-single-v3` |
| 11 | zai-org/glm-4.6v-flash · single · explicit | default | **19.6** | 14.3–25.2 | 32.0 ± 18.0 (n 25) | 4.0 ± 6.0 (n 25) | 42.2 ± 10.0 (n 25) | 0.0 ± 0.0 (n 25) | 21.6 | 4% | 14% | 0% | – | 100 × 1 | `e3-d1-real-glm-4.6v-flash-q4km-lms-single-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Draft = draft linework (`real-draw-alignment`); Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Notes = notes and dimensions (`real-construction-callouts`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

## `hard-pilots`: the harder tasks (pass or fail)

**Best model 61.6/100 on hard-pilots with the explicit prompt (claude-opus-5-5 (medium) via claude-code · single · explicit, 95% CI 55.4–67.9, hard-fail 38%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **61.6** | 55.4–67.9 | 93.2 | 38% | 62% | 0% | $1.65 | 112 × 1 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single-v3` |
| 2 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **50.9** | 44.6–57.1 | 92.2 | 49% | 51% | 1% | – | 112 × 1 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-self_correct-v3` |
| 3 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **40.2** | 34.8–45.5 | 87.4 | 60% | 40% | 0% | – | 112 × 1 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single-v3` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **33.0** | 27.7–38.4 | 82.8 | 67% | 33% | 0% | $1.51 | 112 × 1 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 5 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **7.1** | 2.7–11.6 | 51.9 | 93% | 7% | 2% | – | 112 × 1 | `e3-hard-pilots-gpt-6-luna-codex-medium-self_correct-v3` |
| 6 | gpt-6-luna (medium) via codex · single · explicit | medium | **5.4** | 1.8–8.9 | 46.4 | 95% | 5% | 3% | – | 112 × 1 | `e3-hard-pilots-gpt-6-luna-codex-medium-single-v3` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | medium | **4.5** | 0.9–8.0 | 49.4 | 96% | 4% | 2% | – | 112 × 1 | `e3-hard-pilots-gpt-6-luna-codex-medium-vision-v3` |
| 8 | qwen/qwen3.5-9b · single · explicit | default | **2.7** | 0.0–5.4 | 28.0 | 97% | 3% | 0% | – | 112 × 1 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-v3` |

## `d1-test-hard`: seeded sheets, the whole job (3-5 curves, 2-3 sheets)

**Best model 98.5/100 on d1-test-hard with the explicit prompt (claude-opus-5-5 (medium) via claude-code · single · explicit, 95% CI 98.3–98.8, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **98.5** | 98.3–98.8 | 98.5 | 0% | 23% | 0% | $1.26 | 100 × 1 | `e3-d1-test-hard-claude-opus-5-5-claude-code-medium-single-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **98.5** | 98.2–98.9 | 98.5 | 0% | 27% | 0% | – | 100 × 1 | `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **90.8** | 87.8–93.0 | 92.5 | 2% | 8% | 0% | $0.956 | 100 × 1 | `e3-d1-test-hard-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 4 | gpt-6-luna (medium) via codex · single · explicit | medium | **56.3** | 48.4–63.7 | 83.6 | 33% | 12% | 1% | – | 100 × 1 | `e3-d1-test-hard-gpt-6-luna-codex-medium-single-v3` |

## `d1-real-hard`: the sample plan sheets, the whole job

**Best model 97.1/100 on d1-real-hard with the explicit prompt (gpt-6.1-terra (medium) via codex · single · explicit, 95% CI 94.1–99.2, hard-fail 2%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Letter | Sheet | Job | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **97.1** | 94.1–99.2 | 98.5 ± 0.8 (n 20) | 99.5 ± 0.2 (n 41) | 93.8 ± 6.5 (n 39) | 99.0 | 2% | 49% | 0% | – | 100 × 1 | `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-v3` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **96.1** | 92.9–99.0 | 98.3 ± 0.9 (n 20) | 99.5 ± 0.1 (n 41) | 91.3 ± 7.7 (n 39) | 99.0 | 3% | 35% | 0% | $1.24 | 100 × 1 | `e3-d1-real-hard-claude-opus-5-5-claude-code-medium-single-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **84.5** | 79.1–89.5 | 82.5 ± 12.0 (n 20) | 90.1 ± 4.3 (n 41) | 79.7 ± 10.8 (n 39) | 92.3 | 9% | 4% | 0% | $0.578 | 100 × 1 | `e3-d1-real-hard-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 4 | gpt-6-luna (medium) via codex · single · explicit | medium | **83.7** | 78.7–88.1 | 96.1 ± 1.9 (n 20) | 92.5 ± 1.8 (n 41) | 67.9 ± 11.8 (n 39) | 91.3 | 9% | 7% | 1% | – | 100 × 1 | `e3-d1-real-hard-gpt-6-luna-codex-medium-single-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Job = the whole job (`real-sheet-job`, `real-annotate-job`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

Each set is its own ranking: `d1-test` is 100 held-out tasks from the seeded generator (one synthetic centerline per task); `d1-real` is 100 held-out tasks on the redrafted sample plan sheets (Caltrans, WFL, CFL, FDOT), 25 in each of four question groups (draft linework, letter alignment data, produce the sheet, notes and dimensions), each group a column beside the blended score; `hard-pilots` is the 112 harder-task pilots on the sample sheets, each graded pass (100) or fail (0) by its own check, with the share of its items done as the rubric column; `d1-test-hard` is 100 held-out seeded whole-sheet jobs (three to five curves on two or three sheets, a station equation on one in five: the plan sheet with its pavement, the alignment created from stated geometry and then drafted, the sheet file lettered through its base drawing); `d1-real-hard` is 100 tasks on the redrafted sheets, every whole job (a sheet drafted from its base files or annotated from blank, construction callouts included) and the heaviest whole-line tasks `d1-real` did not draw. Within a set the rows rank on that set alone; the overall table at the top is the one place a model's sets are averaged, the real sheets and the hard pilots weighted double.

Each prompt level is its own board (Robert, 2026-11-08): this file ranks the explicit-prompt runs (the full brief, stating every standard the task is graded on); a score at one prompt level is not comparable with a score at the other. Every task has both prompts: a pilot's vague brief keeps what the drafter cannot know (the files, lines, stations and data given) and leaves its drafting standards to the drafter, graded by the lenient rules where the brief no longer states them.

A run that misses a task of its set, or has an episode that ended in error or never finished, is partial and not scored: it is listed on the main board without a score. The one exception is a cost-subset run (`benchmarks/tasksets/cost-subsets.json`: five tasks of each task type, Runpod runs only, to save cost), ranked in a table of its own under its set beside the full runs re-scored on the same tasks; it too is partial and not scored if it misses a task of the subset or has an episode in error or unfinished. A `hard-pilots` run that holds every text pilot of its set or subset and none of the pilots that come with a page (a model that takes no images) is not partial: it stays in its table, marked **text only**, scored on its text pilots alone, which is not the same tasks as the rows beside it.

Effective score: 0 on a hard fail, else the rubric score; per task over its samples, then over tasks; 95% CI a bootstrap over tasks within task type. Rows rank on the effective mean, then hard-fail rate, invalid-call rate and cost. Effort is the level the run set with `--effort`, else what the request body set, else the model's default marked (default), as read from its chat template or catalog (`roaddraft.effort`); plain default is one not looked up. A model run at two efforts is two rows.

_Generated by `scripts/make_leaderboard.py` from `benchmarks/runs/*/summary.json`; do not edit._
