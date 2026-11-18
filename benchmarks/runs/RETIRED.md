# Board rows retired on 2026-11-03

Robert, Nov 3 2026: wipe from the Track D leaderboard every run that no longer applies after the harness fixes of the day. Every published row ran on harness `e3-v2` and the tool surface `379e02f1` (the `place_label` kind help before d485d7e1). A row left the board where one of those fixes measurably changes what it recorded:

- **the kind help** (d485d7e1): a callout task at 0 because the curve number was lettered as kind `custom` or `curve_data`, the help never saying that `mc` draws the bubble;
- **harness e3-v3** (d485d7e1): an episode the 20-minute clock stopped (now 45 minutes on D1, 120 on a pilot), a call the serving template wrapped in a one-item list (now repaired, not invalid), or a faults stop inside one many-call turn (the budget now counts turns);
- **the hard-pilots set** (0036060b): grown from 33 to 112 pilots, the checks' source hash moved, so a 33-pilot row is partial and ranks no more.

34 runs retired, 17 kept. The published folders moved to `results/_retired-e3-v2/published/<run id>/` (not tracked); the raw episodes stay under `results/e3-*/<run id>/`. To restore a row, move its folder back under `benchmarks/runs/` and run `scripts/make_leaderboard.py`. A rerun takes a new run id on the current surface (`0334fd4aaade`) under harness `e3-v3`; d1-verify-v8 (bb9cd7ef) scores the kept rows the same as v7.

## `d1-test` (13 rows)

| Row | Effective | Tasks | Run | Retired because |
|---|---:|---:|---|---|
| claude-opus-5-5 (medium) via claude-code · single · explicit | 93.1 | 100 | `e3-d1-test-claude-opus-5-5-claude-code-medium-single` | the place_label kind help (d485d7e1): curve-callouts 14.5 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · self_correct · explicit | 90.5 | 100 | `e3-d1-test-gpt-6-luna-codex-medium-self_correct` | the place_label kind help (d485d7e1): curve-callouts 33.3 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| claude-opus-5-5 (medium) via claude-code · single · vague | 88.4 | 100 | `e3-d1-test-claude-opus-5-5-claude-code-medium-single-vague` | the place_label kind help (d485d7e1): curve-callouts 0.0 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · vision · explicit | 86.1 | 100 | `e3-d1-test-gpt-6-luna-codex-medium-vision` | the place_label kind help (d485d7e1): curve-callouts 33.3 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · single · explicit | 83.8 | 100 | `e3-d1-test-gpt-6-luna-codex-medium-single` | the place_label kind help (d485d7e1): curve-callouts 0.0 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · single · vague | 67.7 | 100 | `e3-d1-test-gpt-6-luna-codex-medium-single-vague` | the place_label kind help (d485d7e1): curve-callouts 0.0 on 6 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| qwen/qwen3.5-9b · self_correct · explicit | 67.0 | 100 | `e3-d1-test-qwen3.5-9b-q4km-lms-self_correct` | harness e3-v3 (d485d7e1) was measured on this row: 14 episodes stopped by the 20-minute clock, 1 on an over-long turn; invalid calls 0.0%; curve-callouts 0.0 on 6 tasks (the kind help) |
| google/gemma-4-12b · self_correct · explicit | 66.2 | 100 | `e3-d1-test-gemma-4-12b-q8-lms-self_correct` | harness e3-v3 (d485d7e1) was measured on this row: 11 episodes stopped on the faults budget (the list-wrapped calls), 2 by the 20-minute clock, 5 on an over-long turn; invalid calls 17.8%; curve-callouts 16.7 on 6 tasks (the kind help) |
| qwen/qwen3.5-9b · single · explicit | 62.5 | 100 | `e3-d1-test-qwen3.5-9b-q4km-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 6 episodes stopped by the 20-minute clock; invalid calls 0.0%; curve-callouts 0.0 on 6 tasks (the kind help) |
| qwen/qwen3.5-9b · single · vague | 57.1 | 100 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-vague` | harness e3-v3 (d485d7e1) was measured on this row: 4 episodes stopped by the 20-minute clock, 1 on an over-long turn; invalid calls 0.1%; curve-callouts 13.7 on 6 tasks (the kind help) |
| google/gemma-4-12b · single · explicit | 56.6 | 100 | `e3-d1-test-gemma-4-12b-q8-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 12 episodes stopped on the faults budget, every one an eight-turn loop of one list-wrapped call the harness now repairs; invalid calls 28.2%; curve-callouts 0.0 on 6 tasks (the kind help) |
| zai-org/glm-4.6v-flash · self_correct · explicit | 28.9 | 100 | `e3-d1-test-glm-4.6v-flash-q4km-lms-self_correct` | harness e3-v3 (d485d7e1) was measured on this row: 33 episodes stopped on the faults budget, most inside a single 16-call turn; 2 by the clock, 2 on an over-long turn; invalid calls 0.1%; curve-callouts 0.0 on 6 tasks (the kind help) |
| zai-org/glm-4.6v-flash · single · explicit | 28.5 | 100 | `e3-d1-test-glm-4.6v-flash-q4km-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 19 episodes stopped on the faults budget, 15 of them inside a single 16-call turn; 2 by the clock, 1 on an over-long turn; invalid calls 0.5%; curve-callouts 0.0 on 6 tasks (the kind help) |

## `d1-real` (8 rows)

| Row | Effective | Tasks | Run | Retired because |
|---|---:|---:|---|---|
| claude-opus-5-5 (medium) via claude-code · single · explicit | 89.0 | 100 | `e3-d1-real-claude-opus-5-5-claude-code-medium-single` | the place_label kind help (d485d7e1): real-callouts 0.0 on 5 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · vision · explicit | 83.7 | 100 | `e3-d1-real-gpt-6-luna-codex-medium-vision` | the place_label kind help (d485d7e1): real-callouts 20.0 on 5 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · self_correct · explicit | 81.7 | 100 | `e3-d1-real-gpt-6-luna-codex-medium-self_correct` | the place_label kind help (d485d7e1): real-callouts 0.0 on 5 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| gpt-6-luna (medium) via codex · single · explicit | 77.7 | 100 | `e3-d1-real-gpt-6-luna-codex-medium-single` | the place_label kind help (d485d7e1): real-callouts 0.0 on 5 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| qwen/qwen3.5-9b · single · explicit | 64.0 | 99 | `e3-d1-real-qwen3.5-9b-q4km-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 10 episodes stopped by the 20-minute clock; the 99-task draw of Oct 22, 58 tasks shared with the current d1-real; invalid calls 0.0%; real-callouts 0.0 on 9 tasks (the kind help) |
| gpt-6-luna (medium) via codex · single · vague | 60.4 | 100 | `e3-d1-real-gpt-6-luna-codex-medium-single-vague` | the place_label kind help (d485d7e1): real-callouts 0.0 on 5 tasks, the curve number lettered as kind custom or curve_data for want of the help that now names mc; tool surface 379e02f1 -> 0334fd4a |
| google/gemma-4-12b · single · explicit | 55.0 | 100 | `e3-d1-real-gemma-4-12b-q8-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 11 episodes stopped on the faults budget (the list-wrapped calls), 2 by the 20-minute clock, 2 on an over-long turn; invalid calls 20.8%; real-callouts 0.0 on 5 tasks (the kind help) |
| zai-org/glm-4.6v-flash · single · explicit | 19.1 | 100 | `e3-d1-real-glm-4.6v-flash-q4km-lms-single` | harness e3-v3 (d485d7e1) was measured on this row: 26 episodes stopped on the faults budget, 24 of them inside a single turn; 2 by the clock; invalid calls 1.2%; real-callouts 0.0 on 5 tasks (the kind help) |

## `hard-pilots` (13 rows)

| Row | Effective | Tasks | Run | Retired because |
|---|---:|---:|---|---|
| claude-opus-5-5 (medium) via claude-code · self_correct · explicit | 84.8 | 33 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-self_correct` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| claude-opus-5-5 (medium) via claude-code · single · explicit | 66.7 | 33 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| gpt-6.1-terra (medium) via codex · self_correct · explicit | 54.5 | 33 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-self_correct` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| gpt-6.1-terra (medium) via codex · single · explicit | 51.5 | 33 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| claude-sonnet-5-5 (medium) via claude-code · single · explicit | 42.4 | 33 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | 36.4 | 33 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-self_correct` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| gpt-6-luna (medium) via codex · single · explicit | 12.1 | 99 | `e3-hard-pilots-gpt-6-luna-codex-medium-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| gpt-6-luna (medium) via codex · vision · explicit | 12.1 | 33 | `e3-hard-pilots-gpt-6-luna-codex-medium-vision` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| gpt-6-luna (medium) via codex · self_correct · explicit | 9.1 | 99 | `e3-hard-pilots-gpt-6-luna-codex-medium-self_correct` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| qwen/qwen3.5-9b · single · explicit | 8.7 | 24 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| qwen/qwen3.5-9b · single · explicit | 6.1 | 33 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-main` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| google/gemma-4-12b · single · explicit | 3.0 | 33 | `e3-hard-pilots-gemma-4-12b-q8-lms-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |
| zai-org/glm-4.6v-flash · single · explicit | 0.0 | 33 | `e3-hard-pilots-glm-4.6v-flash-q4km-lms-single` | the set grew from 33 to 112 pilots and the checks' source hash moved (0036060b): a 33-pilot row covers 33 of the set's 112 tasks and ranks no more; the full set wants a rerun |

## Kept

The rows below stay ranked. They ran on the same `e3-v2` harness and `379e02f1` surface, but none of the fixes touches what they recorded: every episode ended by submit (no clock, turn or faults stop), no call was list-wrapped, and the curve number was lettered as `mc` unprompted (callout tasks near 100). The board shows the harness per row.

| Set | Row | Effective | Callout tasks | Run |
|---|---|---:|---|---|
| `d1-real` | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | 100.0 | real-callouts 100.0 on 5 tasks | `e3-d1-real-claude-opus-5-5-claude-code-medium-self_correct` |
| `d1-real` | gpt-6.1-terra (medium) via codex · self_correct · explicit | 99.8 | real-callouts 100.0 on 5 tasks | `e3-d1-real-gpt-6.1-terra-codex-medium-self_correct` |
| `d1-real` | gpt-6.1-terra (medium) via codex · single · explicit | 95.4 | real-callouts 100.0 on 5 tasks | `e3-d1-real-gpt-6.1-terra-codex-medium-single` |
| `d1-real` | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | 92.1 | real-callouts 100.0 on 5 tasks | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-self_correct` |
| `d1-real` | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 89.9 | real-callouts 100.0 on 5 tasks | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single` |
| `d1-test` | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | 100.0 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-claude-opus-5-5-claude-code-medium-self_correct` |
| `d1-test` | claude-opus-5-5 (medium) via claude-code · vision · explicit | 100.0 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-claude-opus-5-5-claude-code-medium-vision` |
| `d1-test` | gpt-6.1-terra (medium) via codex · self_correct · explicit | 100.0 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-gpt-6.1-terra-codex-medium-self_correct` |
| `d1-test` | gpt-6.1-terra (medium) via codex · vision · explicit | 100.0 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-gpt-6.1-terra-codex-medium-vision` |
| `d1-test` | gpt-6.1-terra (medium) via codex · single · explicit | 96.2 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-gpt-6.1-terra-codex-medium-single` |
| `d1-test` | claude-sonnet-5-5 (medium) via claude-code · vision · explicit | 92.9 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-vision` |
| `d1-test` | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | 91.7 | curve-callouts 100.0 on 6 tasks | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-self_correct` |
| `d1-test` | gpt-6.1-terra (medium) via codex · single · vague | 91.3 | curve-callouts 97.1 on 6 tasks | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague` |
| `d1-test` | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 88.3 | curve-callouts 83.3 on 6 tasks | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single` |
| `d1-test` | claude-sonnet-5-5 (medium) via claude-code · single · vague | 70.9 | curve-callouts 68.6 on 6 tasks | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague` |
| `d1-variance` | Qwen/Qwen3.6-35B-A3B · single · explicit | 86.7 | curve-callouts 20.0 on 5 tasks | `e3-d1-variance-qwen3.6-35b-a3b-single` |
| `d1-variance` | google/gemma-4-12B-it · single · explicit | 69.3 | curve-callouts 17.4 on 5 tasks | `e3-d1-variance-gemma-4-12b-single` |

# Board rows retired on 2026-11-10

Robert, Nov 10 2026: retire the pre-v3 runs that a v3 rerun has superseded on the board. Both ranked rows below ran on the older surface (`379e02f1`) under harness `e3-v2`, and were kept on Nov 3 because the day's fixes did not touch what they recorded. They have since been re-run at the v3 pin (`0334fd4aaade`, harness `e3-v3`, run id `…-single-vague-v3`), so the old folder was a duplicate second row for the same model × set × prompt level and ranks no more.

The published folders moved to `results/_retired-e3-v2/published/<run id>/`; the raw episodes stay under `results/e3-*/<run id>/`. To restore a row, move its folder back under `benchmarks/runs/` and run `scripts/make_leaderboard.py`.

| Set | Row | Effective | Superseded by | Run |
|---|---|---:|---|---|
| `d1-test` | gpt-6.1-terra (medium) via codex · single · vague | 91.3 | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague-v3` (92.8) | `e3-d1-test-gpt-6.1-terra-codex-medium-single-vague` |
| `d1-test` | claude-sonnet-5-5 (medium) via claude-code · single · vague | 70.9 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague-v3` (76.0) | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single-vague` |

(Both were in the Nov-3 "Kept" list above; the v3 reruns now replace them.)

# Board rows retired on 2026-11-13

Robert, Nov 13 2026 ("Drop duplicates"): drop the `hard-pilots` cost5 rows that a full-set run now duplicates. Each model's cost5 run held 66 of the 112 pilots; Runpod queue v7 (`benchmarks/runpod/queue-trackd-v7.sh`, Nov 12-13) copied those 66 finished episodes into a full-set run id and ran the other 46, so the full run re-scored on the subset's 66 is the same 66 episodes with the same score. The cost5 table listed each model twice, once as the subset run and once as the full run re-scored. Nothing was wrong with these rows; they are retired as duplicates only.

The published folders moved to `results/_retired-e3-v3/published/<run id>/` (not tracked); the raw episodes stay under `results/e3-runpod/<run id>/`. To restore a row, move its folder back under `benchmarks/runs/` and run `scripts/make_leaderboard.py`. `gpt-oss-120b`'s cost5 text run (`e3-hard-pilots-gpt-oss-120b-single-vague-cost5-text-v3`, 3.9 on 51 text pilots) stays: its full text-only run is not re-scored into the cost5 table, so that row is not duplicated.

| Set | Row | Effective (66) | Duplicated by (full set, 112) | Run |
|---|---|---:|---|---|
| `hard-pilots` | Qwen/Qwen3.6-35B-A3B · single · vague | 9.1 | `e3-hard-pilots-qwen3.6-35b-a3b-single-vague-v3` (8.0) | `e3-hard-pilots-qwen3.6-35b-a3b-single-vague-cost5-v3` |
| `hard-pilots` | nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4 · single · vague | 6.1 | `e3-hard-pilots-nemotron-3.5-super-vl-single-vague-v3` (4.5) | `e3-hard-pilots-nemotron-3.5-super-vl-single-vague-cost5-v3` |
| `hard-pilots` | google/gemma-4-31B-it · single · vague | 3.0 | `e3-hard-pilots-gemma-4-31b-single-vague-v3` (1.8) | `e3-hard-pilots-gemma-4-31b-single-vague-cost5-v3` |
| `hard-pilots` | mistralai/Mistral-Small-4-119B-2603-NVFP4 · single · vague | 3.0 | `e3-hard-pilots-mistral-small-4-single-vague-v3` (2.7) | `e3-hard-pilots-mistral-small-4-single-vague-cost5-v3` |
| `hard-pilots` | google/gemma-4-26B-A4B-it · single · vague | 1.5 | `e3-hard-pilots-gemma-4-26b-a4b-single-vague-v3` (0.9) | `e3-hard-pilots-gemma-4-26b-a4b-single-vague-cost5-v3` |

# The explicit-prompt board, retired on 2026-11-16

Robert, Nov 16 2026, at the Track D close-out: "retire the explicit board". The board's focus has been the vague prompt since Nov 8 (the request in a sentence, the drafting standards left to the drafter); the explicit-prompt rows (the full brief, stating every standard the task is graded on) ranked on a board of their own, `LEADERBOARD_EXPLICIT.md`, which is no longer generated (`report.RETIRED_BOARDS`). Nothing was wrong with these rows: they are retired with their board, not for a fix that changed what they recorded. The 40 ranked rows below are the board's last state (a785b2d7); one explicit run that was published but partial, and so never ranked, went with them.

The published folders moved to `results/_retired-explicit/published/<run id>/` (not tracked), with the board's last file beside them (`results/_retired-explicit/LEADERBOARD_EXPLICIT.md`); the raw episodes stay under `results/e3-*/<run id>/`, where `eval causes` and `eval standards` still pair a vague run with its explicit twin. The two `d1-variance` runs (explicit prompts, Oct 20) stay published: they size the interval and were never on a board. To restore the board: move the folders back under `benchmarks/runs/`, put `"explicit": "LEADERBOARD_EXPLICIT.md"` back in `report.LEVEL_BOARD_FILES`, and run `scripts/make_leaderboard.py`. An explicit-prompt run published from now on is listed on the main board, not ranked.

Overall at the explicit prompt, the three models with a full-set run on all five sets (the weighted mean of the set scores, the real sheets and the hard pilots double): gpt-6.1-terra (medium) via codex · single · explicit 82.5 ± 1.6; claude-sonnet-5-5 (medium) via claude-code · single · explicit 74.2 ± 2.1; gpt-6-luna (medium) via codex · single · explicit 61.8 ± 2.1.

## `d1-test` (13 rows)

| # | Row | Effective | 95% CI | Hard-fail | Tasks | Run |
|---:|---|---:|---|---:|---:|---|
| 1 | claude-opus-5-5 (medium) via claude-code · vision · explicit | 100.0 | 100.0–100.0 | 0% | 100 | `e3-d1-test-claude-opus-5-5-claude-code-medium-vision` |
| 2 | gpt-6.1-terra (medium) via codex · vision · explicit | 100.0 | 100.0–100.0 | 0% | 100 | `e3-d1-test-gpt-6.1-terra-codex-medium-vision` |
| 3 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | 100.0 | 100.0–100.0 | 0% | 100 | `e3-d1-test-claude-opus-5-5-claude-code-medium-self_correct` |
| 4 | gpt-6.1-terra (medium) via codex · self_correct · explicit | 100.0 | 100.0–100.0 | 0% | 100 | `e3-d1-test-gpt-6.1-terra-codex-medium-self_correct` |
| 5 | gpt-6.1-terra (medium) via codex · single · explicit | 96.2 | 93.8–98.1 | 0% | 100 | `e3-d1-test-gpt-6.1-terra-codex-medium-single` |
| 6 | gpt-6-luna (medium) via codex · self_correct · explicit | 94.8 | 91.5–97.6 | 1% | 100 | `e3-d1-test-gpt-6-luna-codex-medium-self_correct-v3` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | 93.7 | 91.6–96.2 | 0% | 100 | `e3-d1-test-gpt-6-luna-codex-medium-vision-v3` |
| 8 | claude-sonnet-5-5 (medium) via claude-code · vision · explicit | 92.9 | 90.6–95.6 | 0% | 100 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-vision` |
| 9 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | 91.7 | 88.9–94.5 | 1% | 100 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 10 | gpt-6-luna (medium) via codex · single · explicit | 91.3 | 87.8–94.6 | 3% | 100 | `e3-d1-test-gpt-6-luna-codex-medium-single-v3` |
| 11 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 88.3 | 84.0–92.3 | 3% | 100 | `e3-d1-test-claude-sonnet-5-5-claude-code-medium-single` |
| 12 | qwen/qwen3.5-9b · single · explicit | 74.0 | 68.5–79.6 | 10% | 100 | `e3-d1-test-qwen3.5-9b-q4km-lms-single-v3` |
| 13 | google/gemma-4-12b · single · explicit | 64.5 | 59.0–70.3 | 20% | 100 | `e3-d1-test-gemma-4-12b-q8-lms-single-v3` |

## `d1-real` (11 rows)

| # | Row | Effective | 95% CI | Hard-fail | Tasks | Run |
|---:|---|---:|---|---:|---:|---|
| 1 | claude-opus-5-5 (medium) via claude-code · self_correct · explicit | 100.0 | 99.9–100.0 | 0% | 100 | `e3-d1-real-claude-opus-5-5-claude-code-medium-self_correct` |
| 2 | gpt-6.1-terra (medium) via codex · self_correct · explicit | 99.8 | 99.5–100.0 | 0% | 100 | `e3-d1-real-gpt-6.1-terra-codex-medium-self_correct` |
| 3 | gpt-6.1-terra (medium) via codex · single · explicit | 95.4 | 93.0–97.4 | 1% | 100 | `e3-d1-real-gpt-6.1-terra-codex-medium-single` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · self_correct · explicit | 92.1 | 88.8–95.0 | 3% | 100 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-self_correct` |
| 5 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 89.9 | 86.3–93.1 | 4% | 100 | `e3-d1-real-claude-sonnet-5-5-claude-code-medium-single` |
| 6 | gpt-6-luna (medium) via codex · vision · explicit | 84.9 | 81.1–88.8 | 4% | 100 | `e3-d1-real-gpt-6-luna-codex-medium-vision-v3` |
| 7 | gpt-6-luna (medium) via codex · self_correct · explicit | 84.5 | 79.7–88.8 | 6% | 100 | `e3-d1-real-gpt-6-luna-codex-medium-self_correct-v3` |
| 8 | gpt-6-luna (medium) via codex · single · explicit | 84.3 | 80.2–88.3 | 8% | 100 | `e3-d1-real-gpt-6-luna-codex-medium-single-v3` |
| 9 | qwen/qwen3.5-9b · single · explicit | 70.8 | 66.0–75.7 | 10% | 100 | `e3-d1-real-qwen3.5-9b-q4km-lms-single-v3` |
| 10 | google/gemma-4-12b · single · explicit | 68.6 | 64.4–72.7 | 11% | 100 | `e3-d1-real-gemma-4-12b-q8-lms-single-v3` |
| 11 | zai-org/glm-4.6v-flash · single · explicit | 19.6 | 14.3–25.2 | 4% | 100 | `e3-d1-real-glm-4.6v-flash-q4km-lms-single-v3` |

## `hard-pilots` (8 rows)

| # | Row | Effective | 95% CI | Hard-fail | Tasks | Run |
|---:|---|---:|---|---:|---:|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · explicit | 61.6 | 55.4–67.9 | 38% | 112 | `e3-hard-pilots-claude-opus-5-5-claude-code-medium-single-v3` |
| 2 | gpt-6.1-terra (medium) via codex · self_correct · explicit | 50.9 | 44.6–57.1 | 49% | 112 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-self_correct-v3` |
| 3 | gpt-6.1-terra (medium) via codex · single · explicit | 40.2 | 34.8–45.5 | 60% | 112 | `e3-hard-pilots-gpt-6.1-terra-codex-medium-single-v3` |
| 4 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 33.0 | 27.7–38.4 | 67% | 112 | `e3-hard-pilots-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 5 | gpt-6-luna (medium) via codex · self_correct · explicit | 7.1 | 2.7–11.6 | 93% | 112 | `e3-hard-pilots-gpt-6-luna-codex-medium-self_correct-v3` |
| 6 | gpt-6-luna (medium) via codex · single · explicit | 5.4 | 1.8–8.9 | 95% | 112 | `e3-hard-pilots-gpt-6-luna-codex-medium-single-v3` |
| 7 | gpt-6-luna (medium) via codex · vision · explicit | 4.5 | 0.9–8.0 | 96% | 112 | `e3-hard-pilots-gpt-6-luna-codex-medium-vision-v3` |
| 8 | qwen/qwen3.5-9b · single · explicit | 2.7 | 0.0–5.4 | 97% | 112 | `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-v3` |

## `d1-test-hard` (4 rows)

| # | Row | Effective | 95% CI | Hard-fail | Tasks | Run |
|---:|---|---:|---|---:|---:|---|
| 1 | claude-opus-5-5 (medium) via claude-code · single · explicit | 98.5 | 98.3–98.8 | 0% | 100 | `e3-d1-test-hard-claude-opus-5-5-claude-code-medium-single-v3` |
| 2 | gpt-6.1-terra (medium) via codex · single · explicit | 98.5 | 98.2–98.9 | 0% | 100 | `e3-d1-test-hard-gpt-6.1-terra-codex-medium-single-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 90.8 | 87.8–93.0 | 2% | 100 | `e3-d1-test-hard-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 4 | gpt-6-luna (medium) via codex · single · explicit | 56.3 | 48.4–63.7 | 33% | 100 | `e3-d1-test-hard-gpt-6-luna-codex-medium-single-v3` |

## `d1-real-hard` (4 rows)

| # | Row | Effective | 95% CI | Hard-fail | Tasks | Run |
|---:|---|---:|---|---:|---:|---|
| 1 | gpt-6.1-terra (medium) via codex · single · explicit | 97.1 | 94.1–99.2 | 2% | 100 | `e3-d1-real-hard-gpt-6.1-terra-codex-medium-single-v3` |
| 2 | claude-opus-5-5 (medium) via claude-code · single · explicit | 96.1 | 92.9–99.0 | 3% | 100 | `e3-d1-real-hard-claude-opus-5-5-claude-code-medium-single-v3` |
| 3 | claude-sonnet-5-5 (medium) via claude-code · single · explicit | 84.5 | 79.1–89.5 | 9% | 100 | `e3-d1-real-hard-claude-sonnet-5-5-claude-code-medium-single-v3` |
| 4 | gpt-6-luna (medium) via codex · single · explicit | 83.7 | 78.7–88.1 | 9% | 100 | `e3-d1-real-hard-gpt-6-luna-codex-medium-single-v3` |

## Published, partial, never ranked (1 run)

- `e3-d1-test-glm-4.6v-flash-q4km-lms-single-v3` (d1-test, 100 episodes; 100 of 100 tasks): zai-org/glm-4.6v-flash · single · explicit. partial, not scored: covers 100 of the set's 100 tasks; 1 episode(s) ended in error; a row ranks once the run holds every task with none in error or unfinished.
