# RoadDraft eval leaderboard

The benchmark board: every published run on the eval sets, scored by the verifier (`roaddraft.eval`), one ranking per set. The 33 capability probes of Track P are a separate board, closed 2026-10-27: [the probe board](../leaderboard/TRACK_P.md).

![Effective score by model on each eval set](leaderboard.svg)

## `d1-test`: seeded sheets

**Best model 100.0/100 on d1-test (claude-opus-5-5 (medium) via claude-code · vision · explicit, 95% CI 100.0–100.0, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · vision · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 96% | 0% | $0.410 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-vision` |
| 2 | gpt-6.1-terra (medium) via codex · vision · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 94% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-vision` |
| 3 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 96% | 0% | $0.371 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-self_correct` |
| 4 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **100.0** | 100.0–100.0 | 100.0 | 0% | 94% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-self_correct` |
| 5 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **96.2** | 93.8–98.1 | 96.2 | 0% | 82% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-single` |
| 6 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **93.1** | 91.5–95.1 | 93.1 | 0% | 72% | 0% | $0.415 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-single` |
| 7 | claude-sonnet-5-5 (medium) via claude-code · vision · explicit | medium | **92.9** | 90.6–95.6 | 92.9 | 0% | 73% | 0% | $0.201 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-vision` |
| 8 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | **91.7** | 88.9–94.5 | 92.5 | 1% | 78% | 0% | $0.219 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 9 | gpt-6.1-terra (medium) via codex · single · vague | medium | **91.3** | 89.5–93.1 | 91.3 | 0% | 47% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague` |
| 10 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **90.5** | 87.1–94.1 | 91.2 | 1% | 68% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-self_correct` |
| 11 | claude-opus-5-5 (medium) via claude-code · single · vague | medium | **88.4** | 87.0–89.6 | 88.4 | 0% | 53% | 0% | $0.405 | 100 × 1 | `e3-d1-test-claude-opus-5-5-claude-code-medium-single-vague` |
| 12 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **88.3** | 84.0–92.3 | 90.8 | 3% | 69% | 0% | $0.213 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single` |
| 13 | gpt-6-luna (medium) via codex · vision · explicit | medium | **86.1** | 82.2–89.9 | 88.7 | 4% | 66% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-vision` |
| 14 | gpt-6-luna (medium) via codex · single · explicit | medium | **83.8** | 79.8–87.4 | 84.6 | 1% | 57% | 0% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-single` |
| 15 | claude-sonnet-5-5 (medium) via claude-code · single · vague | medium | **70.9** | 67.6–73.8 | 73.1 | 3% | 20% | 0% | $0.159 | 100 × 1 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague` |
| 16 | gpt-6-luna (medium) via codex · single · vague | medium | **67.7** | 64.4–70.9 | 68.2 | 1% | 25% | 1% | – | 100 × 1 | `e3-d1-test-gpt-6-luna-codex-medium-single-vague` |
| 17 | qwen/qwen3.5-9b · self_correct · explicit | default | **67.0** | 62.0–71.8 | 70.5 | 6% | 31% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-self_correct` |
| 18 | google/gemma-4-12b · self_correct · explicit | thinking on | **66.2** | 61.0–71.6 | 72.7 | 10% | 40% | 18% | – | 100 × 1 | `e3-d1-test-gemma-4-12b-q8-lms-self_correct` |
| 19 | qwen/qwen3.5-9b · single · explicit | default | **62.5** | 57.2–67.8 | 69.6 | 15% | 30% | 0% | – | 100 × 1 | `e3-d1-test-qwen3.5-9b-q4km-lms-single` |
| 20 | google/gemma-4-12b · single · explicit | thinking on | **56.6** | 52.4–61.1 | 66.4 | 15% | 33% | 28% | – | 100 × 1 | `e3-d1-test-gemma-4-12b-q8-lms-single` |
| 21 | zai-org/glm-4.6v-flash · self_correct · explicit | default | **28.9** | 25.1–32.7 | 32.0 | 7% | 17% | 0% | – | 100 × 1 | `e3-d1-test-glm-4.6v-flash-q4km-lms-self_correct` |
| 22 | zai-org/glm-4.6v-flash · single · explicit | default | **28.5** | 23.4–33.7 | 30.6 | 9% | 13% | 1% | – | 100 × 1 | `e3-d1-test-glm-4.6v-flash-q4km-lms-single` |

## `d1-real`: the sample plan sheets

**Best model 100.0/100 on d1-real (claude-opus-5-5 (medium) via claude-code · self_correct · explicit, 95% CI 99.9–100.0, hard-fail 0%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Draft | Letter | Sheet | Notes | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | **100.0** | 99.9–100.0 | 100.0 ± 0.0 (n 25) | 99.9 ± 0.1 (n 25) | 100.0 ± 0.1 (n 25) | 100.0 ± 0.0 (n 25) | 100.0 | 0% | 98% | 0% | $0.658 | 100 × 1 | `e3-d1-real-claude-opus-5-5-claude-code-medium-self_correct` |
| 2 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **99.8** | 99.5–100.0 | 100.0 ± 0.0 (n 25) | 99.8 ± 0.3 (n 25) | 100.0 ± 0.0 (n 25) | 99.4 ± 0.8 (n 25) | 99.8 | 0% | 97% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-self_correct` |
| 3 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **95.4** | 93.0–97.4 | 100.0 ± 0.0 (n 25) | 99.5 ± 0.3 (n 25) | 95.2 ± 3.6 (n 25) | 87.0 ± 7.8 (n 25) | 96.3 | 1% | 72% | 0% | – | 100 × 1 | `e3-d1-real-gpt-6.1-terra-codex-medium-single` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | **92.1** | 88.8–95.0 | 100.0 ± 0.0 (n 25) | 94.2 ± 1.0 (n 25) | 95.8 ± 3.8 (n 25) | 78.4 ± 11.6 (n 25) | 94.1 | 3% | 68% | 0% | $0.334 | 100 × 1 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 5 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **89.9** | 86.3–93.1 | 100.0 ± 0.0 (n 25) | 95.8 ± 1.6 (n 25) | 88.3 ± 7.1 (n 25) | 75.5 ± 11.6 (n 25) | 93.1 | 4% | 58% | 0% | $0.339 | 100 × 1 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single` |
| 6 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **89.0** | 86.1–91.4 | 100.0 ± 0.0 (n 25) | 78.5 ± 0.6 (n 25) | 92.1 ± 3.6 (n 25) | 85.4 ± 10.0 (n 25) | 90.8 | 2% | 59% | 0% | $0.716 | 100 × 1 | `e3-d1-real-claude-opus-5-5-claude-code-medium-single` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | medium | **83.7** | 79.0–88.0 | 96.0 ± 6.0 (n 25) | 76.6 ± 9.6 (n 25) | 95.8 ± 2.9 (n 25) | 66.4 ± 12.4 (n 25) | 86.4 | 4% | 55% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-vision` |
| 8 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **81.7** | 77.6–85.3 | 96.0 ± 6.0 (n 25) | 75.8 ± 2.3 (n 25) | 90.5 ± 6.4 (n 25) | 64.4 ± 12.0 (n 25) | 84.4 | 4% | 55% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-self_correct` |
| 9 | gpt-6-luna (medium) via codex · single · explicit | medium | **77.7** | 73.5–81.9 | 100.0 ± 0.0 (n 25) | 74.3 ± 2.1 (n 25) | 81.2 ± 9.0 (n 25) | 55.2 ± 14.4 (n 25) | 81.0 | 6% | 50% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-single` |
| 10 | qwen/qwen3.5-9b · single · explicit | default | **64.0** | 59.4–68.2 | 100.0 ± 0.0 (n 9) | 56.4 ± 7.5 (n 45) | 64.3 ± 6.5 (n 45) | – | 66.8 | 4% | 31% | 0% | – | 99 × 1 | `e3-d1-real-qwen3.5-9b-q4km-lms-single` |
| 11 | gpt-6-luna (medium) via codex · single · vague | medium | **60.4** | 54.9–65.5 | 73.0 ± 12.5 (n 25) | 57.2 ± 4.6 (n 25) | 64.0 ± 6.7 (n 25) | 47.3 ± 14.4 (n 25) | 65.7 | 9% | 17% | 1% | – | 100 × 1 | `e3-d1-real-gpt-6-luna-codex-medium-single-vague` |
| 12 | google/gemma-4-12b · single · explicit | thinking on | **55.0** | 50.9–59.6 | 100.0 ± 0.0 (n 25) | 41.9 ± 9.1 (n 25) | 54.8 ± 9.1 (n 25) | 23.4 ± 12.4 (n 25) | 61.6 | 16% | 34% | 21% | – | 100 × 1 | `e3-d1-real-gemma-4-12b-q8-lms-single` |

Question groups (`tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers; `d1-real` draws 25 tasks a group): Draft = draft linework (`real-draw-alignment`); Letter = letter alignment data (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`); Sheet = produce the sheet (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`); Notes = notes and dimensions (`real-construction-callouts`). Each cell is the effective mean over the row's tasks in that group ± its 95% half-width, with the number of tasks it rests on.

## `hard-pilots`: the harder tasks (pass or fail)

**Best model 84.8/100 on hard-pilots (claude-opus-5-5 (medium) via claude-code · self_correct · explicit, 95% CI 78.8–93.9, hard-fail 15%).**

| # | Model · mode · prompt | Effort | Effective | 95% CI | Rubric | Hard-fail | Clean | Invalid calls | Cost / sheet | Tasks × k | Run |
|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|---|
| 1 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | medium | **84.8** | 78.8–93.9 | 96.4 | 15% | 85% | 0% | $2.05 | 33 × 1 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-self_correct` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · explicit | medium | **66.7** | 60.6–75.8 | 92.2 | 33% | 67% | 0% | $1.93 | 33 × 1 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single` |
| 3 | gpt-6.1-terra (medium) via codex · self_correct · explicit | medium | **54.5** | 45.5–63.6 | 87.6 | 45% | 55% | 1% | – | 33 × 1 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-self_correct` |
| 4 | gpt-6.1-terra (medium) via codex · single · explicit | medium | **51.5** | 42.4–60.6 | 84.3 | 48% | 52% | 0% | – | 33 × 1 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single` |
| 5 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | medium | **42.4** | 30.3–54.5 | 82.9 | 58% | 42% | 0% | $1.48 | 33 × 1 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single` |
| 6 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | medium | **36.4** | 27.3–45.5 | 77.9 | 64% | 36% | 0% | $1.72 | 33 × 1 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | medium | **12.1** | 6.1–18.2 | 47.6 | 88% | 12% | 1% | – | 33 × 1 | `e3-hard-pilots-gpt-6-luna-codex-medium-vision` |
| 8 | gpt-6-luna (medium) via codex · single · explicit | medium | **12.1** | 5.0–20.2 | 47.0 | 88% | 12% | 2% | – | 33 × 3 | `e3-hard-pilots-gpt-6-luna-codex-medium-single` |
| 9 | gpt-6-luna (medium) via codex · self_correct · explicit | medium | **9.1** | 4.0–14.1 | 45.4 | 91% | 9% | 1% | – | 33 × 3 | `e3-hard-pilots-gpt-6-luna-codex-medium-self_correct` |

## Published runs that are not ranked

- `e3-d1-variance-gemma-4-12b-single` (d1-variance, 100 episodes): google/gemma-4-12B-it · single · explicit, effort thinking on 69.3 ± 3.0 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots).
- `e3-d1-variance-qwen3.6-35b-a3b-single` (d1-variance, 100 episodes): Qwen/Qwen3.6-35B-A3B · single · explicit, effort thinking on (default) 86.7 ± 2.7 (20 tasks × 5). Not ranked: run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots).
- `e3-hard-pilots-qwen3.5-9b-q4km-lms-single` (hard-pilots, 24 episodes, **partial: 24 of 33 tasks**): qwen/qwen3.5-9b · single · explicit, effort default 8.7 ± 8.7 (23 tasks × 1). Not ranked: scored under an older spec or verifier: verifier_version d1-verify-v6 (current pilot-check-a6cca462de35); partial: covers 24 of the set's 33 tasks; a row ranks once the run holds every task of the current set.

Each set is its own ranking: `d1-test` is 100 held-out tasks from the seeded generator (one synthetic centerline per task); `d1-real` is 100 held-out tasks on the redrafted sample plan sheets (Caltrans, WFL, CFL, FDOT), 25 in each of four question groups (draft linework, letter alignment data, produce the sheet, notes and dimensions), each group a column beside the blended score; `hard-pilots` is the 33 harder-task pilots on the sample sheets, each graded pass (100) or fail (0) by its own check, with the share of its items done as the rubric column. A model's rows on different sets are not averaged.

Effective score: 0 on a hard fail, else the rubric score; per task over its samples, then over tasks; 95% CI a bootstrap over tasks within task type. Rows rank on the effective mean, then hard-fail rate, invalid-call rate and cost. Effort is the level the run set with `--effort`, else what the request body set, else the model's default marked (default), as read from its chat template or catalog (`roaddraft.effort`); plain default is one not looked up. A model run at two efforts is two rows.

_Generated by `scripts/make_leaderboard.py` from `benchmarks/runs/*/summary.json`; do not edit._
