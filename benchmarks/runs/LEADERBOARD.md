# RoadDraft eval leaderboard

The benchmark board: every published run on the eval sets, scored by the verifier (`roaddraft.eval`), one ranking per set. The 33 capability probes of Track P are a separate board, closed 2026-10-27: [the probe board](../leaderboard/TRACK_P.md).

Vague prompts only: the request in a sentence, the board's focus. Every other prompt level is ranked on a board of its own: [explicit prompts](LEADERBOARD_EXPLICIT.md).

![Effective score by model on each eval set](leaderboard.svg)

## `d1-test`: seeded sheets

**Best model 91.3/100 on d1-test with the vague prompt (gpt-6.1-terra (medium) via codex · single · vague, 95% CI 89.5–93.1, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **91.3** | 89.5–93.1 | 91.3 | 0% | 47% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague` |
| 2 | gpt-6-luna (medium) via codex · single · vague | medium | **76.1** | 72.7–79.3 | 77.8 | 3% | 31% | 1% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-single-vague-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **70.9** | 67.6–73.8 | 73.1 | 3% | 20% | 0% | $0.159 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague` |
| 4 | google/gemma-4-12b · single · vague | thinking on | **67.2** | 63.6–70.7 | 72.3 | 9% | 32% | 2% | – | 100 × 1 | `e3-d1-test-gemma-4-12b-q8-lms-single-vague-v3` |
| 5 | qwen/qwen3.5-9b · single · vague | default | **62.6** | 57.7–67.6 | 66.3 | 6% | 31% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 6 | zai-org/glm-4.6v-flash · single · vague | default | **25.2** | 21.3–29.4 | 26.8 | 7% | 14% | 0% | – | 100 × 1 | `e3-d1-test-glm-4.6v-flash-q4km-lms-single-vague-v3` |

## `d1-real`: the sample plan sheets

**Best model 90.5/100 on d1-real with the vague prompt (gpt-6.1-terra (medium) via codex · single · vague, 95% CI 87.9–93.1, hard-fail 1%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Draft | Letter | Sheet | Notes | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **90.5** | 87.9–93.1 | 97.0 ± 3.8 (n 25) | 88.2 ± 6.6 (n 25) | 88.1 ± 4.9 (n 25) | 88.9 ± 4.2 (n 25) | 91.0 | 1% | 52% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 2 | gpt-6-luna (medium) via codex · single · vague | medium | **71.8** | 67.2–76.0 | 85.0 ± 7.5 (n 25) | 74.8 ± 4.6 (n 25) | 71.3 ± 6.6 (n 25) | 56.0 ± 13.6 (n 25) | 75.0 | 6% | 22% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-single-vague-v3` |
| 3 | qwen/qwen3.5-9b · single · vague | default | **59.6** | 54.3–64.6 | 95.5 ± 4.5 (n 25) | 53.0 ± 11.0 (n 25) | 49.3 ± 9.8 (n 25) | 40.8 ± 13.3 (n 25) | 61.2 | 7% | 29% | 0% | – | 100 × 1 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-vague-v3` |
| 4 | google/gemma-4-12b · single · vague | thinking on | **59.0** | 54.1–64.2 | 100.0 ± 0.0 (n 25) | 53.2 ± 9.1 (n 25) | 57.1 ± 10.5 (n 25) | 25.8 ± 14.2 (n 25) | 62.7 | 9% | 30% | 2% | – | 100 × 1 | `e3-d1-real-gemma-4-12b-q8-lms-single-vague-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Draft = draft linework (`real-draw-alignment`); Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Notes = notes and dimensions (`real-construction-callouts`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

## `hard-pilots`: the harder tasks (pass or fail)

No vague-prompt run on `hard-pilots` yet; its explicit-prompt runs are ranked on their own board.

## `d1-test-hard`: seeded sheets, the whole job (3-5 curves, 2-3 sheets)

**Best model 92.9/100 on d1-test-hard with the vague prompt (gpt-6.1-terra (medium) via codex · single · vague, 95% CI 90.7–94.3, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **92.9** | 90.7–94.3 | 92.9 | 0% | 11% | 0% | – | 100 × 1 | `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |
| 2 | gpt-6-luna (medium) via codex · single · vague | medium | **43.2** | 37.8–48.4 | 54.7 | 21% | 0% | 3% | – | 100 × 1 | `e3-d1-test-hard-gpt-6-luna-codex-medium-single-vague-v3` |

## `d1-real-hard`: the sample plan sheets, the whole job

**Best model 72.1/100 on d1-real-hard with the vague prompt (gpt-6.1-terra (medium) via codex · single · vague, 95% CI 66.7–77.0, hard-fail 4%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Letter | Sheet | Job | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | gpt-6.1-terra (medium) via codex · single · vague | medium | **72.1** | 66.7–77.0 | 78.9 ± 17.3 (n 20) | 92.2 ± 3.9 (n 41) | 47.5 ± 8.3 (n 39) | 74.9 | 4% | 8% | 0% | – | 100 × 1 | `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-vague-v3` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Job = the whole job (`real-sheet-job`, `real-annotate-job`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

## Published runs that are not ranked

- `e3-d1-test-glm-4.6v-flash-q4km-lms-single-v3` (d1-test, 100 episodes, **partial, not scored: 100 of 100 tasks**): zai-org/glm-4.6v-flash · single · explicit, effort default (99 tasks × 1). Not ranked: partial, not scored: covers 100 of the set's 100 tasks; 1 episode(s) ended in error; a row ranks once the run holds every task with none in error or unfinished.
- `e3-d1-variance-gemma-4-12b-single` (d1-variance, 100 episodes): google/gemma-4-12B-it · single · explicit, effort thinking on 69.3 ± 3.0 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots, d1-test-hard, d1-real-hard).
- `e3-d1-variance-qwen3.6-35b-a3b-single` (d1-variance, 100 episodes): Qwen/Qwen3.6-35B-A3B · single · explicit, effort thinking on (default) 86.7 ± 2.7 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots, d1-test-hard, d1-real-hard).

Each set is its own ranking: `d1-test` is 100 held-out tasks from the seeded generator (one synthetic centerline per task); `d1-real` is 100 held-out tasks on the redrafted sample plan sheets (Caltrans, WFL, CFL, FDOT), 25 in each of four question groups (draft linework, letter alignment data, produce the sheet, notes and dimensions), each group a column beside the blended score; `hard-pilots` is the 112 harder-task pilots on the sample sheets, each graded pass (100) or fail (0) by its own check, with the share of its items done as the rubric column; `d1-test-hard` is 100 held-out seeded whole-sheet jobs (three to five curves on two or three sheets, a station equation on one in five: the plan sheet with its pavement, the alignment created from stated geometry and then drafted, the sheet file lettered through its base drawing); `d1-real-hard` is 100 tasks on the redrafted sheets, every whole job (a sheet drafted from its base files or annotated from blank, construction callouts included) and the heaviest whole-line tasks `d1-real` did not draw. A model's rows on different sets are not averaged.

Each prompt level is its own board (Robert, 2026-11-08): this file ranks the vague-prompt runs (the request in a sentence, the way a PE would ask for it; what belongs on the sheet is the drafter's to know), the main board and its focus; a score at one prompt level is not comparable with a score at the other. Every task has both prompts: a pilot's vague brief keeps what the drafter cannot know (the files, lines, stations and data given) and leaves its drafting standards to the drafter, graded by the lenient rules where the brief no longer states them.

A run that misses a task of its set, or has an episode that ended in error or never finished, is partial and not scored: it is listed on the main board without a score. The one exception is a cost-subset run (`benchmarks/tasksets/cost-subsets.json`: five tasks of each task type, Runpod runs only, to save cost), ranked in a table of its own under its set beside the full runs re-scored on the same tasks; it too is partial and not scored if it misses a task of the subset or has an episode in error or unfinished.

Effective score: 0 on a hard fail, else the rubric score; per task over its samples, then over tasks; 95% CI a bootstrap over tasks within task type. Rows rank on the effective mean, then hard-fail rate, invalid-call rate and cost. Effort is the level the run set with `--effort`, else what the request body set, else the model's default marked (default), as read from its chat template or catalog (`roaddraft.effort`); plain default is one not looked up. A model run at two efforts is two rows.

_Generated by `scripts/make_leaderboard.py` from `benchmarks/runs/*/summary.json`; do not edit._
