# Plan: the Track D eval sets on RobertsPC (drafted 2026-10-23 evening)

Robert's decision of Oct 23: no more Runpod spend on the evals beyond what has run; run whatever models the
PC can hold through LM Studio instead. The currency here is PC hours, not dollars: the PC runs one model and
one episode at a time, so every set is a night or more per model. This file is the order of work; the rig
itself (specs, commands, guards) is `README.md` and `models.json` next door, and nothing starts without
Robert's go (`lms_campaign.py e3 NAME --taskset ... --samples ...`).

**2026-11-08: vague prompts only on the PC** (Robert: "focus on the vague prompts only", then "Stop all runs with
explicit prompts and start the vague ones"; `../RERUN_PLAN.md`, top). Queue 10 (`results/e3-lms/
queue-2026-11-04-v3-local.sh`, explicit) was stopped by hand at 14:4x PST on Gemma's hard-pilots (36 of 112 on disk,
resumable under its run id). `results/e3-lms/queue-2026-11-08-vague-local.sh` took the PC at 14:45: the three models
at the vague level, single, k = 1, set by set (d1-test, d1-real, d1-test-hard, d1-real-hard; 12 nights, the 9B
first), from rerun-v3 at 3b7e7fe9, same watcher and retries as queue 10, reports written unpublished. Not queued:
the explicit hard-set singles and the self-correct / vision nights. Evening (Robert: "Rerun all models on the vague
prompts. Check if any of the eval tasks do not have a vague prompt style first, add them if needed"): every pilot
now has a vague brief, so `results/e3-lms/queue-2026-11-08-vague-pilots-local.sh` follows the D1 vague queue with
three more nights, hard-pilots vague for the 9B, Gemma and GLM (all 112, `--pilots all`), from the worktree
vague-pilots (3b7e7fe9 + `results/e3-lms/vague-pilots.patch`). Explicit rows rank on their own board since then
(`runs/LEADERBOARD_EXPLICIT.md`).

## What is running right now

**Nothing since 04:06 PDT on 2026-10-28: the Track D queue of Oct 27 is through** (`results/e3-lms/queue-2026-10-27.sh`,
log beside it; Robert, Oct 27 13:00: "do steps 1-4", Gemma as the Q8_0 on the PC). It ran one model at a time from the
worktree `.claude/worktrees/lms-d1-test` (main 291ae711):

- **Step 1, the 9B on d1-test x 1: DONE and PUBLISHED.** `e3-d1-test-qwen3.5-9b-q4km-lms-single`, 16:14 Oct 27 to
  02:42 Oct 28; 100 of 100 episodes scored, no error and no engine death in 10.4 hours of episode time (6.3 minutes an
  episode mean, 2.7 median, 39.7 max). **62.5 effective [57.2-67.8]**, rubric 69.4, hard-fail 15%, clean 30%, submit
  90%, one invalid call in 2,886. Rankable as run (spec v1, generator d1-v6, verifier d1-verify-v7, clean pins): the
  first `d1-test` row, published 11:08 Oct 28 to `benchmarks/runs/e3-d1-test-qwen3.5-9b-q4km-lms-single` and on the
  board. Terminations: 90 submits, 6 at the 20-minute clock, 4 on an over-long turn; the 15 hard fails are 12 submitted
  sheets with a hard-fail finding and 3 of the budget trips; 30 sheets at 100, 27 at 0. Weakest checks: pavement width
  dimensions 0.27, north arrow 0.42, station ticks 0.50, BC/EC lettering 0.51, bearings 0.52; strongest: alignment
  linework, reference attached and alignment created 1.00, curve table 0.92. Prompts: 17 episodes peaked past 65,536
  tokens (max 104,370, p90 70,589, median 35,248), all inside the 131k window and the harness budget, no context trip.
  The row reads 1.1 below the 9B's d1-real row (63.6), the intervals overlapping.
- **Step 3, Gemma 4 12B Q8_0: NOT RUN.** The `check` at 131,072 failed both ways LM Studio tries (`--gpu max`: "failed
  to allocate buffer for kv cache"; the default split: "failed to allocate compute pp buffers"), so the queue skipped
  its d1-test night as written. The 12.8 GB file loaded at 65k on Oct 20 (12.8 tok/s, partly on the CPU); it is the
  131k KV cache that does not fit beside it on the two 16 GB cards.
- **Step 4, the five smokes (one d1-dev episode each, 02:43 to 04:06):** GLM-4.6V-Flash Q4_K_M ran and submitted
  (43.8 effective, 32 steps in 4 turns, 10 faults, no invalid calls, 3.4 minutes): a keeper by the rule. Gemma 4 E4B
  Q4_K_M ran 7 steps in 8 turns and never submitted (0, hard fail; 9,400 reasoning tokens; the wall clock took it after
  44 minutes that included one engine death and reload mid-episode): not a keeper on this episode. Devstral Small 2
  24B Q3_K_L, Ministral 3 14B Q6_K and Llama 3.1 8B Q4_K_M did not load at 131,072 ("failed to allocate buffer for kv
  cache", twice each), so their episodes never ran.

**Robert, Oct 28 about 11:30: "have the models run at the highest context possible that will fit on my local
machine, if a model is unable to run with enough context for these tasks remove it from the list of local tested
models."** Built the same hour (committed on main Oct 28, on Robert's go): each model has its own window. `lms_campaign.py fit NAME` walks the
ladder 131,072, 114,688, 98,304, 81,920, 65,536 from the ceiling (`CONTEXT`, the Oct 26 decision) down to the floor
(`FLOOR_CONTEXT` 65,536: the hosted vLLM rows' window, taken as "enough context for these tasks"; at it about 17 in
100 d1-test episodes trip on the 9B's transcript sizes), records the first rung LM Studio loads the model at as
`context` in `models.json` (every load, the runner guard, `--lms-context` and `--context-tokens` use it; the window
is on the card), and below the floor marks the model `dropped` with the reason, which `e3`, `check`, `smoke`, `k3`
and `vision` then refuse. Tests in `tests/test_lms_campaign.py`. The 9B, GLM-4.6V-Flash and Gemma 4 E4B are
recorded at 131,072 (they loaded there). **Queue 2** (`results/e3-lms/queue-2026-10-28.sh`, log beside it, started
right after): `fit` for Gemma 4 12B Q8_0, Devstral Small 2, Ministral 3 14B and Llama 3.1 8B in turn, then the
three smokes that never ran (one d1-dev episode each, for the ones that fit), then Gemma 4 12B's d1-test x 1 night
at its window if it fit (report written, not published). A dropped model leaves the list below and the board.
**The fits (11:57 to 12:08):** Gemma 4 12B Q8_0 loads at **98,304** (131k and 114k: "failed to allocate compute pp
buffers"); Llama 3.1 8B Q4_K_M loads at **65,536**, the floor, and at no rung above it; Devstral Small 2 24B Q3_K_L and
Ministral 3 14B Q6_K load at none of the five rungs (KV cache at 65,536 too) and are **DROPPED from the local list**.
Llama's smoke episode at 65,536 (12:08 to 12:10) ended as an error at step 0: LM Studio could not parse the model's
tool-call output (500 "does not match the expected peg-native format", three samples), as in the Oct 7-8 Tier-3 pass,
so Llama 3.1 8B is **DROPPED** by step 5's rule (a model that never calls a tool) and marked so in `models.json`.
**Gemma 4 12B Q8_0's d1-test x 1 night RUNS since 12:10 at 98,304** (`e3-d1-test-gemma-4-12b-q8-lms-single`,
100 episodes; report written, not published). Its first 15 episodes ran 12:10 to 12:49, one to seven minutes each
(five at 100, then 94.2, 93.7, 77.3, 53.8 and six at 0). **Then the engine stalled:** at 12:53 the 18th turn of
D1-001014 (its first 17 turns had taken seven seconds each) streamed empty chunks until the provider's 30-minute
turn limit, and so did the first turn of every episode after it, nine in a row (D1-001015 to 001023, 13:23 to
17:54), each scored 0 with 0 steps while LM Studio listed the model GENERATING and answered the harness's one-token
probe before every episode, so the dead-engine guard saw a live model. Found at the 18:13 check-in: the eval
process was stopped at 18:17 (the queue's `run_e3` loop retries after ten minutes, and `e3` reloads the model alone
first; the model went IDLE the moment the client died), the nine zero-step episodes were moved into
`errored-2026-10-28/` under the run so the resume runs them again (1014 keeps its 93.7 on 17 steps), and
`lms_campaign.py watch RUN_ID` now watches both of tonight's runs (a stall is `turn_time` with 0 steps: it stops
the run for the queue's retry, sets the episode aside once, and records it in `watch.json`; README, "Stalls"). The
resume, attempt 2 of 6, started 18:27:39 with 85 episodes to run: the reload cured it, the nine set-aside episodes
ran again inside 36 minutes (75, 0, 0, 100, 0, 100, 0, 0, 100, all submitted) and the run went on. Five hours of
the afternoon went to the stall.
The local list after today: Qwen3.5-9B (131k), GLM-4.6V-Flash (131k), Gemma 4 12B Q8_0 (98k), Gemma 4 E4B (131k, no
submit on its smoke: Robert's call), the 4B once downloaded; off it: Devstral, Ministral (no window), Llama (no tool calls).
**Queue 3** (Robert, 12:25: "Yes, queue it"; `results/e3-lms/queue-2026-10-28b.sh`, log beside it, started 12:36)
waits for queue 2's "queue done" and an idle server, then runs **GLM-4.6V-Flash Q4_K_M on d1-test x 1 at 131,072**
(`e3-d1-test-glm-4.6v-flash-q4km-lms-single`, step 6's first keeper; its smoke episode took 3.4 minutes, so about
six hours) and writes its report, not published. A `watch` for its run id waits for the run's folder to appear.

From the stall (Robert, 18:40: "Yes, build it"): the harness now has a stall guard of its own (committed 31774181 at 22:19 on Robert's go; README,
"Stalls"): a stream whose chunks carry nothing for 300 s, 50 chunks at least, is reloaded once and asked again, and a
second stall ends the turn as `turn_limit` with the stall on record; it reaches a run only through a worktree at a
commit that holds it, so tonight's two nights rely on `watch`. The same shape sits in the 9B's published rows: four
d1-test episodes (D1-001032, 001034, 001069, 001071, after 57, 6, 13 and 1 steps) and one d1-real episode ended on a
silent 30-minute turn, scored on what they had done; Robert, 21:20: "Yes, rerun them" (queue 4 below). Next in the plan after queues 2 to 4: step 2's 4B download (the PC alone can start it; then `fit`, `check`, its
night), Gemma 4 E4B's place on the list (Robert's call), the image pilots on the 9B after the pilot-astra merge (step 9).
The 9B's published d1-test row, the regenerated board, the window rule and this section were committed on main on Oct 28 (Robert's go).

**Queue 4** (Robert, 21:20: "Yes, rerun them"; `results/e3-lms/queue-2026-10-28c.sh`, log beside it, started 21:32, restarted 22:21)
waits for queue 3's "queue done" and an idle server, then reruns the 9B's silent-turn episodes inside their published
runs: `clear-errors RUN --apply --turn-time` (new: every `turn_time` trip, after steps too) sets them aside, a `watch`
starts, and `e3 qwen3.5-9b ... --run-id RUN --worktree WT` resumes the run from the worktree at its own pin. d1-test
(`e3-d1-test-qwen3.5-9b-q4km-lms-single`): D1-001032, 001034, 001069, 001071 from `lms-d1-test` (291ae711). d1-real
(`e3-d1-real-qwen3.5-9b-q4km-lms-single`): D1-000000-8e8d02fad1d1 (silent, 6 steps) and the one errored episode of
Oct 26, D1-000000-f1825a08b736 (died mid-stream, left out of the published row; the rerun fills the row to 99), from
`lms-9b-resume` (d98e7025, whose harness has no `--context-tokens`: `e3` now leaves the flag out for such a worktree,
and the run keeps its own budgets). Neither pin held the harness stall guard, so on Robert's "Yes, commit" (22:19) the
guard went in as its own commit (31774181) and was cherry-picked onto each pin in its rerun worktree: `lms-9b-rerun-test`
at 97469b45 (291ae711 + the guard, so the nights' `lms-d1-test` stays untouched) and `lms-9b-resume` at c1719489
(d98e7025 + the guard; its 77 tests pass), tagged `pin/e3-d1-test-qwen3.5-9b-rerun` and `pin/e3-d1-real-qwen3.5-9b-rerun`;
queue 4 was stopped in its wait and restarted at 22:21 pointing at them. A five-minute stall now reloads the model and
asks again once; the `watch` stays for the zero-step kind. Both reports are written, d1-real's
with `--reverify` (d98e7025 scores under d1-verify-v6, the published row is v7), neither published: the two rows
change only after a look at the numbers, then `report --publish` (d1-real: `--reverify --publish`) and
`scripts/make_leaderboard.py`. Expected start Oct 29 morning (Gemma at 45 of 100 at 21:27, about 6 min an
episode, so ~03:00; GLM about six hours after), then an hour or two of episodes.

**Queue 5** (Robert, 22:45: "Yes, queue it"; `results/e3-lms/queue-2026-10-28d.sh`, log beside it, started 22:51)
waits for queue 4's "queue done" and an idle server, then completes and cleans Gemma 4 12B's d1-test run inside its run
id: `clear-errors --turn-time` sets aside the errored episode (D1-001009, 12:41, LM Studio's 500 "Unexpected empty
grammar stack", the Oct 27 kind) and the silent turns after steps (D1-001014 after 17 steps, 001025 after 42, 001040
after 3, and any the rest of the night adds), the abandoned D1-001041 reruns on its own as an incomplete episode, and
`e3 gemma-4-12b` resumes from the worktree `lms-gemma-fixup` at 7d694792 = 291ae711 + the stall guard 31774181 + the
harness fix below, at the run's 98,304, under a `watch`; the report is written, not published, and the row changes
after a look. **The harness fix** (on main since Oct 29; first on the pin as 7d694792, tag
`pin/e3-d1-test-gemma-4-12b-q8-lms-fixup`): D1-001041 was abandoned at 21:05 when the harness raised
`TypeError: unhashable type: 'list'` inside a tool call. Only the agent's own exceptions were caught, so the exception
escaped the episode loop, the runner logged a one-line cell failure without a traceback, and the file was left with no
end record (the d1-variance cell D1-001010 s4 went the same way on Oct 25, on `'NoneType' object is not iterable`).
Now `Episode.execute` guards the tool bridge: the call's result names the failure, the traceback goes to the run log,
and the episode ends as `error` with its end record and no step counted, the harness's outcome rather than the
model's, so the report leaves it out and `clear-errors` reruns it; scoring has the same cover (an `UnscoredReport`
when the verifier fails), the probe episode's bridge sits under the guard, and a cell failure in the runner keeps its
traceback. Three tests. The 9B's rerun (queue 4) runs without this fix, at the pins already set; the crash is rare
(two in about a thousand local episodes).

**Queues 3 to 5 ran through by 12:15 PDT Oct 29**, reports written, none published. GLM-4.6V-Flash's night (queue 3,
from 291ae711, which has no stall guard) hit six stalls the watcher caught (03:39 to 11:30, each a
30-minute silent turn, a kill and a 10-minute retry) and used all six attempts, ending at 11:30 with 91 of its 100
cells scored: effective 29.18 [24.3-34.2]. The 9B's silent-turn rerun (queue 4) ended 11:54: d1-test 62.50 [57.2-67.8] over 100, the published
figure unchanged, since its four reruns scored as before (0, 100, 0, 100) but each ended by submit; d1-real 63.98
[59.4-68.2] over 99 after `--reverify`, and Gemma's fix-up (queue 5) 12:15 (56.65 [52.4-61.1] over 100). D1-001041
(pavement, seed 1041) is the task that crashed the harness on Gemma, and on GLM it sat silent through its first turn
on both of its tries, so it reads as the task, not the engine: a look after the nights.
Published 13:15 Oct 29 (Robert, 13:1x: "Yes, publish them"; committed that evening on his "Yes, commit"): Gemma 4 12B's d1-test row, 56.6
[52.4-61.1], rank 2 on d1-test behind the 9B (invalid calls 28%, the 9B's 0%), and the 9B's two rows again from their
rerun reports (d1-test 62.5 unchanged, rubric 69.6; d1-real 64.0 [59.4-68.2] over 99, was 63.6 over 98); the board,
leaderboard.json/.svg and the README block regenerated by `scripts/make_leaderboard.py`. Each summary now pins its
fix-up commit (7d694792, 97469b45, c1719489), which lives on a local `pin/...` tag, not on main; push the tags with
the board when it is pushed. GLM's row waits for queue 7.

**Queue 7** (Robert, 13:0x Oct 29: "Yes, queue it"; `results/e3-lms/queue-2026-10-29-glm-fixup.sh`, log beside it,
started 13:04) completes and cleans GLM's d1-test run inside its run id. The ask was to slot it into queue 5 ahead of
the self-correct nights, but queue 5 was through and queue 6 had started them at 12:22, so it waits for queue 6's
"queue done" and then 15 idle minutes in a row (longer than any queue's 10-minute retry gap, so it cannot start
inside another queue's retry). `clear-errors --turn-time` sets aside the silent turns (D1-001041 at 0 steps, 001045
and 001046 at 16), the resume runs the nine cells the night never finished, and `e3 glm-4.6v-flash` runs from
`lms-gemma-fixup` at 7d694792 (GLM's night has the same base, 291ae711, so the pin is that plus the stall guard and
the harness fix; tag `pin/e3-d1-test-glm-4.6v-flash-q4km-lms-fixup`) at 131,072 under a `watch`; the report is
written, not published. Queue 6 ended at 20:37 Oct 30 and queue 7 started at 20:52.

**Queue 8** (Robert, 22:2x Oct 30: "Yes, queue it"; `results/e3-lms/queue-2026-10-30-sc-fixup.sh`, log beside it,
started 22:25) completes two of queue 6's self-correct nights inside their run ids, from their own worktree
`lms-selfcorrect` (d2ac876b), after queue 7's "queue done" and 15 idle minutes. First the 9B's three episodes lost
to LM Link drops (D1-001012, 001030, 001064; `clear-errors`, errors only, so the silent turn after 16 steps on
D1-001024 stays the model's outcome), about 20 minutes; then GLM's 38 unfinished tasks (its night used all six
attempts on silent-turn stalls and stopped at 62 of 100, 29.5 effective; D1-001062 aside for its one rerun, D1-001063
and D1-001064 to D1-001099 left to the resume), with ten attempts, about 4 to 5 hours with its stalls. Gemma 4 12B's
night ended clean and is not touched. Reports written, not published; the 9B's row, already on the board since
17:10 Oct 30, republishes in place after a look.

Queue 7 ended at 22:52 Oct 30: GLM's single row is complete, 28.50 [23.4-33.7] over 100, no errors. Queue 8 ended at
02:44 Oct 31. The 9B's self-correct row is 67.03 [62.0-71.8] over 100. GLM's self-correct row is 28.87 [25.1-32.7]
over 100, on attempt 4 of 10, with two more watcher-caught stalls. Three of its cells (D1-001065, 001091, 001098) hit a
harness crash, `unhashable type: 'dict'`, which d2ac876b leaves without a traceback because it predates the crash fix;
each finished on the next attempt. The three rows were published at 09:3x Oct 31 on Robert's "Yes, publish". Paired
self-correct gaps over all 100 tasks: the 9B +4.5 [-2.8, +12.3], Gemma +9.6 [+1.3, +17.9], GLM +0.4 [-5.7, +6.4].

**Queue 9** (Robert, 09:3x Oct 31: "finish out the eval set for the local models";
`results/e3-lms/queue-2026-10-31-trackd.sh`, log beside it, launched 09:35) runs the rest of the local push below for
the three local models on the board. The 4B is off the list (Robert, Oct 31 21:00: "dont run the qwen 4B"). It runs from a new worktree,
`lms-trackd`, at main 3424132d: the commit the Luna and Terra rows ran from, with tools 60eeeb21 and instructions
4dff2849, and with the stall guard, the rig and the harness crash fix in. Step 3's engine-branch merges were not done
before the frontier rows ran d1-real and hard-pilots on this engine, so the local rows run on it too and stay
comparable with them. The steps, in order:

1. A one-episode smoke (Gemma, d1-real-dev). The queue stops for a look unless the episode ends by submit or budget
   with at least one step.
2. d1-real x 1 for Gemma 4 12B, then GLM-4.6V-Flash.
3. `vision NAME` for each of the three models. A model that does not read the image runs only the 24 text pilots,
   and the 9B's vision night is skipped if the 9B does not read it.
4. hard-pilots x 1, all 33, for the 9B, Gemma and GLM. The 9B's run takes a new id,
   `e3-hard-pilots-qwen3.5-9b-q4km-lms-single-main`, because its old 24-pilot row ran on the pilot-astra engine.
5. The 9B's d1-test vague and vision runs, x 1 each.
6. The 9B's d1-test single row to k = 5: samples 1-4, 400 episodes, from that row's own pin 97469b45 (worktree
   `lms-9b-rerun-test`).

Each run has a `watch` beside it and retries 10 minutes apart. Episodes that ended in error (LM Link drops and harness
crashes, which are not the model's) are then set aside with `clear-errors` and resumed once. Silent turns after steps
stay the model's. Reports are written, not published, until Robert looks. About 4 to 5 days in all.

**The 9B's hard-pilots run ended 16:01 PDT on 2026-10-27**: 2 of the 24 text-only pilots passed (p02-sources-wfl19a,
p14-qa-review-ppm045a), effective 8.7 [0.0-17.4] over 23 scored, rubric 31.4 (the share of each pilot's items done),
four pilots at the 30-minute clock, one lost to an LM Studio server error ("Unexpected empty grammar stack", left out as
the report leaves out errored episodes), 5.7 hours of episode time. GPT-6-Astra passed 22 of the same 24 through the
pilot rig. Published with `--allow-unrankable` to `benchmarks/runs/e3-hard-pilots-qwen3.5-9b-q4km-lms-single` and listed
on the board under the runs that are not ranked: the run is pinned to the worktree's 29-pilot set (generator
probe-d1e6c7398d83, verifier d1-verify-v6) while main's set is 33 pilots (probe-de3257064ca0, the redline family) under
v7, although the 24 task texts are the same in both (each id carries its text hash). Robert, Oct 27 17:00: the rule
changed (committed that night with B9 as 2cce1ef6 by the other session, pushed Oct 28 on Robert's go): a hard-pilots run is held to its task ids, not the set's hash; its verifier version is
the pilot checks' source hash (`probe_tasks.check_version`); and a row ranks only when the run covers every task of
the current set, a run on part of it being published as partial. Under it the 9B's row reads "partial: 24 of 33
tasks" and stays unranked on one count only, its verifier stamp (d1-verify-v6 against the checks' hash), which a
`report --reverify --publish` clears once the pilot-astra branch is merged (main's checker lacks the p14 repairs the run
used); then the nine image pilots under the same run id complete the row.

The 9B's d1-real x 1 run ended 21:18 PDT on 2026-10-26 and is published as the first ranked Track D row
(`benchmarks/runs/e3-d1-real-qwen3.5-9b-q4km-lms-single`, 63.6 effective [59.0-67.8] over 98 scored episodes).

## Time per episode on the PC

| model | file | fits | gen tok/s | minutes per episode | 100 episodes |
|---|---|---|---|---|---|
| Qwen3.5-9B | Q4_K_M 6.6 GB, on the PC | fully on the cards | 35.8 measured | 8-20 (test hit the 20-min cap) | 13-33 h |
| Gemma 4 12B | Q8_0 12.8 GB, on the PC (Robert, Oct 27: in place of the Q6_K pick) | **window 98,304** (`fit`, Oct 28: 131k and 114k refused), partly on the CPU | 12.8 measured at 65k | 6-10 (Gemma writes little: 1.8k out tokens an episode on Runpod) | 10-17 h |
| Qwen3.5-4B | BF16 8.4 GB, to download | fully on the cards | not measured, ~2x the 9B | 5-12 | 8-20 h |
| Devstral Small 2 24B | Q3_K_L 13.3 GB, on the PC | **DROPPED Oct 28**: loads at no rung from 131k down to 65k (kv cache) | not measured | smoke not run | off the list |
| Ministral 3 14B reasoning | Q6_K 12.0 GB, on the PC | **DROPPED Oct 28**: loads at no rung from 131k down to 65k (kv cache) | not measured | smoke not run | off the list |
| GLM-4.6V-Flash 9.4B | Q4_K_M 8.0 GB, on the PC | fully, at 131k | fast | 3.4 on its smoke episode (submitted, 43.8) | 6-13 h |
| Gemma 4 E4B | Q4_K_M 6.3 GB, on the PC | fully, at 131k | slow with thinking (9.4k reasoning tokens in 7 steps) | cap-bound on its smoke episode (no submit) | 33 h |
| Llama 3.1 8B | Q4_K_M 4.9 GB, on the PC | window 65,536, the floor; **DROPPED Oct 28**: its smoke errored at step 0 (LM Studio cannot parse its tool calls) | fast | smoke: 0 steps, error | off the list |
| Qwen3.6-35B-A3B, Gemma 4 26B-A4B, gpt-oss-20b | Q4_K_M 21 / 16 / 12 GB, to download | experts in the PC's RAM only | 3-5x slower than Runpod | likely cap-bound | 25-35 h |

The minutes are from the measured token rates and the Runpod rows' tokens per episode (`results/e3-runpod`):
the 9B wrote 9-13k output tokens an episode with thinking on, Qwen3.6 12.8k, Gemma 12B 1.8k. Prefill is
3,157 tok/s on the 9B with llama.cpp's prompt cache taking most of each turn's repeated prefix.

## The wall-clock question (Robert's call before the first ranked run)

The harness budget is 150 steps or 20 minutes an episode (`eval/budget.py`). On Runpod's vLLM that was never
the binding limit for Qwen3.6 (0 cut-offs) and bound Gemma 12B ten times in 100 episodes; on the PC the 9B hit
it in its one test episode. Two ways to run the local rows:

1. **Same budget as every other row** (`--wall-clock` left at 20). The rows are comparable on paper, and the
   PC's speed becomes part of the score: a slow local file loses points a vLLM row of the same weights keeps.
2. **A longer wall clock for local rows** (e.g. `--wall-clock 45`), the step budget unchanged. The score then
   measures the model, not the cards; the row's card records the budget, and the board already keeps the
   local GGUF rows apart from the bf16 vLLM rows (different model ids, "local small" class). Episodes run up
   to 45 minutes, so 100 episodes can take two nights.

Recommendation: option 2 for the ranked runs, recorded in the run id (`...-wc45`), and the 9B test episode
repeated under it first to see whether the 122 steps were the model flailing or the clock.

**Outcome (2026-11-03, Robert: "fix these issues").** Neither option as written: the harness default moved to
45 minutes for every D1 row (`Budgets.wall_clock_s` 2,700 s, harness e3-v3) and 120 for a pilot (Track P's
`probe_tasks.BUDGETS`, 7,200 s, was 30), so the board keeps one budget a set and no run id carries a suffix.
The clock is a backstop behind the output-token budget (60,000 on D1, 200,000 on the pilots), sized so the
slowest stack in use (the 9B at ~33 tok/s on the PC) reaches the token budget first. The ranked local rows
lost episodes to the old clocks (9B d1-test single 6, self_correct 14, vague 4, d1-real 10, hard-pilots 8 of
33; Gemma 2 to 5; GLM 2 a set); no hosted, codex or claude-code row ever reached a clock, so those rows are
the same under the new ones. Two more stack effects went with it, both measured on the queue-9 rows:

- *The Gemma template.* The Q8_0 file through LM Studio sent 465 of its 1,800 d1-test calls with a one-item
  list round an enum value (`get_design_data {kind: ["curves"]}`, place_label `kind`/`side`/`rotation`,
  annotate_stationing `lettering`/`point_side`); the same weights under vLLM (d1-variance, 1,312 calls) sent
  none. The harness now reads such a list as its value where the schema takes one (`eval/tools.repair_params`),
  tells the model so in the result's warnings, and counts the call as *repaired* (the run report's line under
  the rows table), not invalid. Invalid-call rate 28.2% / 20.8% on Gemma's d1-test / d1-real rows; 12 and 11
  of its episodes ended on the faults budget, every one an eight-turn loop of the same wrapped call.
- *GLM's turns.* GLM-4.6V-Flash sent 16 calls a turn in 113 of its 172 d1-test turns, mostly copies of one call,
  and 15 of its 19 fault stops (24 of 26 on d1-real) fell inside a single turn: the model never saw an error
  before the budget ended it. The faults budget now counts turns in which every call failed, reset by any
  success (`BudgetState.note_turn`). The nine frontier fault stops on the board all ran one call a turn for
  eight turns, so they are unchanged.

What a rerun needs: a worktree at main past this change (the tool surface moved with the `mc` label-kind help,
see the board's pins), `e3 NAME ...` as before with no extra flag; the run id scheme is unchanged, so an old
row's id must not be resumed under the new harness (a new run id, the old row delisted when the new one lands).
Rows most worth rerunning, in order: Gemma 4 12B d1-test single and self_correct (template + faults), GLM-4.6V-Flash
d1-test single (faults), the 9B d1-test self_correct and d1-real (clock).

## Order of work

Each line is one model-night (10 to 20 hours) unless marked. `d1-test` x 1 (100 episodes) gives a ranked row
inside ±5 for a strong model and ±6 or so for a noisy one; k = 3 is three nights and only worth it for a row
that lands near another.

1. **Qwen3.5-9B, d1-test x 1.** The file is loaded, the harness is proven on it. First ranked local row.
2. **Downloads on the PC** (they land where `lms get` runs, so from the PC, not the Mac): Qwen3.5-4B BF16 only, since Gemma 4 12B
   runs as the Q8_0 already there (Robert, Oct 27); the old text named Gemma 4 12B Q6_K and
   Qwen3.5-4B BF16 as `README.md` step 1 says; then `lms_campaign.py check NAME` for each (one 29k prompt at
   65k, writes `measured`).
3. **Gemma 4 12B Q8_0, d1-test x 1** (a `check` at 131k first; FAILED Oct 28: no fit at 131k, see above; the window question is Robert's). Its Runpod row is 69.3; the local row shows what Q8_0 on a CPU split and llama.cpp's
   Gemma template cost it.
4. **Qwen3.5-4B BF16, d1-test x 1.** Bottom of the ladder at the board row's precision.
5. **Smoke the models already on the PC** (one d1-dev episode each, `e3 NAME --taskset d1-dev --limit 1
   --samples 1`, ~2 hours in all): Devstral Small 2, Ministral 3 14B reasoning, GLM-4.6V-Flash, Gemma 4 E4B,
   Llama 3.1 8B. Keep a model if the episode makes valid tool calls and submits; drop it if it never calls a
   tool (GLM-4.6V-Flash, E4B and Llama scored 0 of 24 on the Tier-3 probes in October, so expect to drop them).
   Mistral 7B v0.3 stays out: LM Studio strips its tools and 32k of context is under the schema.
   Each needs a `models.json` entry (lms_key, variant, quantization, extra_body) before `e3` will take it.
   DONE Oct 28 (see above): GLM-4.6V-Flash submitted (keeper); E4B never submitted; Devstral and Ministral DROPPED by
   the window rule (no rung from 131k to 65k loads); Llama smoked at 65,536 from queue 2 and errored at step 0 (LM
   Studio cannot parse its tool calls, as in October): DROPPED by this step's rule. Keepers: GLM-4.6V-Flash; E4B open.
   GLM's d1-test night is queue 3 (Robert, Oct 28 12:25), behind Gemma's.
6. **Keepers from step 5, d1-test x 1**, one night each: GLM-4.6V-Flash so far (Devstral Small 2 is dropped, Oct 28:
   it does not load with 65k of context on the cards). It was the one to hope for: an agentic
   coding model with tool calling, the largest dense model the cards hold.
7. **The MoE rows, if the PC's RAM allows** (needs about 24 GB free RAM beside the cards for Qwen3.6-35B-A3B
   Q4_K_M; Robert to confirm the PC's RAM). Qwen3.6-35B-A3B is the best open model on the board (86.7 on
   d1-variance), so a local row for it matters most; Q4_K_M keeps the earlier quantization rule. gpt-oss-20b
   stays out (Robert, Oct 20). A `check` first; expect a cap-bound run that takes a weekend.
8. **d1-real x 1 (99 episodes) for the two best local rows.** The first real-sheet rows on the board. Real
   sheets carry more linework, so allow 1.3x the d1-test time.
9. **hard-pilots for the best local row**, k = 1, under Track P's budgets: the 24 text pilots (done on the 9B
   Oct 27: 2 of 24, published, not ranked; see above), then the nine that come with a page (`e3 NAME --taskset hard-pilots --pilots images`,
   same run id, so the run fills out to 33). The page reaches the model through the harness's own route (a
   `view_attachment` result with the PNG as a data URL, which LM Studio takes for a model with vision: the 9B,
   Gemma 4 12B and E4B, GLM-4.6V-Flash, Devstral and Ministral all are, Llama 3.1 is not); `lms_campaign.py vision
   NAME` first, one lettered image through that route to see that the model reads it and what an image costs in
   prompt tokens (Robert's go: it loads the model, so not while a run is going). The 9B's run is pinned to the
   lms-hard-pilots worktree (pilot-astra + guard), whose harness predates `--pilots` and `--context-tokens`; the nine
   image pilots under the same run id wait for the pilot-astra merge (or a cherry-pick onto that worktree).

Total: about six model-nights for the d1-test rows that exist today (steps 1, 3, 4, and two or three keepers),
two more for d1-real, a weekend for Qwen3.6 if it fits. Nothing else is needed for the board except the
`NAMES` entries in `src/roaddraft/runners/leaderboard.py` the README names, so the rows read "Qwen3.5-9B
(Q4_K_M, LM Studio)" and so on.

## The local push through Track D (Robert, Oct 28 22:45: "lets push through track D locally before any runpod runs")

Runpod waits: the model tree (`benchmarks/runpod/PLAN.md`) and the cost plan (`RoadDraft_Cost_Plan.md`) stand, and nothing
runs there until Track D has gone as far as the PC takes it. One run at a time, each night on Robert's go, pinned to a
worktree at main 31774181 or later (the stall guard is in). In order, once queues 2, 3 and 4 (Gemma 4 12B's d1-test, GLM's
d1-test, the 9B's silent-turn reruns) are through and published:

1. **The 4B.** `lms get` on the PC (only the PC can start it), `fit`, `check`, then d1-test x 1 (5-7 h). Four local
   d1-test rows. *Dropped 2026-10-31 21:00 (Robert: "dont run the qwen 4B"): no 4B row on any set; the download was never
   started; `models.json` marks it dropped so the rig refuses it.*
2. **Self-correct on d1-test**, x 1, for the 9B, Gemma 12B, GLM-4.6V-Flash and the 4B: `e3 NAME --taskset d1-test
   --samples 1 --mode self_correct` (the rig passes the mode through; `run_check` x 3 and `render_sheet` join the
   whitelist). About 1.4 x a single night, 8-15 h each. A one-episode smoke first (`--taskset d1-dev --limit 1`), since no
   self-correct run has been made on any rig. The board pairs each with its single row by task: the self-correct gap.
   **Queue 6, the self-correct nights, LAUNCHED 23:15 Oct 28 and waiting** (Robert, 22:50: "Yes, build queue 5";
   23:14: "Go, launch it"): `results/e3-lms/queue-2026-10-28e.sh`, log beside it, from the worktree `lms-selfcorrect` at
   main d2ac876b (the stall guard plus the rig commit; a clean checkout). It was written first as queue-2026-10-28d.sh at
   22:47; the queue session wrote its own queue 5 (Gemma 4 12B's fix-up, above) over that file at 22:50 and launched it
   at 22:51, so the self-correct queue is queue 6 and waits for queue 5's "queue done" and an idle server (a duplicate
   launch of the fix-up script at 23:14 was stopped at once). It runs the one-episode smoke
   (`e3-smoke-self-correct-d1-dev-qwen3.5-9b-lms`) and stops for a look unless that episode ends by submit or budget with
   a step, then the three nights in turn (`e3-d1-test-qwen3.5-9b-q4km-lms-self_correct`,
   `e3-d1-test-gemma-4-12b-q8-lms-self_correct`, `e3-d1-test-glm-4.6v-flash-q4km-lms-self_correct`), a `watch` beside
   each, six attempts a run, reports written and not published. The 4B is not in it (its download has not started).
   The tool-call exception fix on the fix-up worktree is not committed and not in this worktree: an episode it would
   save ends without an end record and the retry's resume runs it again.
3. **The engine branch merges** (recursing-chaum, then jolly-borg, then pilot-astra; tracker step a-pilot-gaps), the
   catalogue rebuild and the trajectory re-recording (CPU on the Mac, in parallel with the nights above), then a new
   worktree at the merged main for everything below. Runs in flight keep their pins. Before the d1-real nights, since the
   shared-table strip redraws d1-real. *MERGED 2026-10-31 21:00 to 21:45 (Robert: "merge all engine branches"): the three
   branches in that order (d1bfc6ca, 1ecb9451, ac4878f0), the catalogue rebuilt (616 tasks, 50 pairings left out) and
   `d1-real` redrawn from it: 95 of the 100 pairings keep their ids, 5 are new (one each of bearings, alignment-data,
   callouts, curve-table, draw-alignment; dropped: PPM-045 TB2 curve-table, PPM-051 WIS1, PPM-047 IN4, PPM-050 F3,
   PPM-048 IND1). The real-sheet rows keep ranking (held to the builder's version, real-v1, unchanged). The served tool
   surface is now sha256:379e02f199 (104 tools; instructions unchanged, 4dff2849). The pilot checks' source hash moved
   (pilot-check-a6cca462de35 to 684c78211b52), and `report --reverify` of the nine hard-pilots rows is NOT sound: a replay
   runs on starts the models never saw (the branch's sheet repairs on L-1 and D.10 shift entity ids), and every row fell
   (Opus 5.5 self-correct 84.8 to 57.6) with the changes confined to the PPM-045 and WFL19 pilots; the rows keep their
   scores and their a6cca462de35 stamp (the re-scored reports sit beside each run as `report-rescored-684c78211b52-2026-10-31`).
   Queue 9's hard-pilots nights run at 3424132d and stamp the same way. The trajectory re-recording is not done.*
4. **d1-real x 1** for Gemma 12B, GLM and the 4B (about 14 h each). The 9B's row stands as a draw of the set.
5. **hard-pilots.** The 9B: `report --reverify --publish` after the merge, then `vision qwen3.5-9b` and its nine image
   pilots under the same run id. Gemma 12B and GLM on all 33 (half a night each; both take images).
6. **k = 5 on d1-test for the 9B**: four more nights. The training baseline, and RQ3's interval.
7. **The paired gaps on the 9B**: the vague level (one night), vision mode (one). *The `c3d` and `ord` skins were dropped 2026-10-30 (Robert: no run renames the tools).*
8. **Frontier rows through the CLI route** (`--provider claude-code` / `codex`), on the Mac in parallel with the PC's
   nights, on the subscriptions: Sonnet 5.5, Opus 5.5, GPT-6.1-Sol on d1-test x 1, days each, one at a time. Only on
   Robert's word, since the Oct 24 rule named local models. *Done Oct 29 to 31 for GPT-6 Luna, Sonnet 5.5, GPT-6.1 Terra
   and Opus 5.5, each through all eight runs (Opus's d1-test vague the last, Oct 31 evening); GPT-6.1-Sol is not run
   (Robert, Oct 31 21:00: "dont run sol").*

*2026-11-03, the retirement (Robert: wipe the board rows the harness fixes no longer apply to).* All ten local rows on `d1-test` and `d1-real` and the three local `hard-pilots` rows left the board (`benchmarks/runs/RETIRED.md`; the folders sit in `results/_retired-e3-v2/published/`, the episodes stay under `results/e3-lms/`): the e3-v3 rules were measured on them (the 20-minute clock stopped 4 to 14 of the 9B's episodes a set, Gemma's template wrapped 28% of its calls, GLM's fault stops fell inside one 16-call turn) and every one lettered the curve number as `custom` under the old kind help (curve-callouts 0 to 17). The reruns are this push again under `e3-v3` on surface `0334fd4aaade`, from a worktree at main bb9cd7ef or later, with the two hard sets added: about 120-160 PC-hours of episode time for the 9B, 80-105 for Gemma 4 12B and 60-75 for GLM-4.6V-Flash in single mode alone, before the stall retries that have stretched a 6-hour night to 24 or 45 hours (`benchmarks/RERUN_PLAN.md`). Queue 9 is paused (SIGSTOP on process group 96382, Nov 3 13:33) inside the 9B's k = 5 run at 132 of 400 on the old pin 97469b45; under e3-v3 that run feeds no board row, so whether it is killed or finished as a record is Robert's call.

About 22 model-nights, five to six weeks at one run a night. What stays out of reach locally: the open rungs above 12B
(Qwen3.6-35B-A3B at Q4 with its experts in PC RAM is the one maybe, a weekend and likely cap-bound), GLM-5.3, and GRPO.
Those are the Runpod spread's Stage 0 onward, after this.

## Rules carried over

- The PC must not sleep during a run (Windows power settings); the Mac holds itself awake with `caffeinate -i`.
- One local run at a time: the campaign script refuses while another is going.
- Quantization stays as recorded in `models.json`; a precision change is asked first (Qwen = Q4_K_M).
- Each model loads at the highest window that fits the PC (`lms_campaign.py fit NAME`: 131,072 down to 65,536,
  recorded as `context` in `models.json`); a model that does not load at 65,536 is dropped from the local list
  (Robert, Oct 28). Nothing loads a model at any other size.
- Runs are pinned to the campaign worktree (`lms_campaign.py pins`); a pin change between a model's episodes
  makes a new row, not a resume.
- A `lms_campaign.py watch RUN_ID` runs beside every night (detached, from the queue's launch): an episode that ends
  on the 30-minute turn limit with 0 steps is a stall of the engine, not the model's result; the watch stops the
  run so the queue's retry reloads the model and resumes, and sets that episode aside once (Oct 28, Gemma 4 12B:
  nine such episodes, five hours, with the one-token probe passing throughout).
- A rerun inside a published run (Robert, Oct 28: the 9B's silent-turn episodes) goes from the run's own pin plus
  only the harness fix it needs, cherry-picked into a worktree of its own and tagged `pin/<run id>-rerun` so the
  detached commit stays reachable; the task set, tools and instructions stay the run's. `clear-errors RUN --apply
  --turn-time` sets the episodes aside, `e3 ... --run-id RUN --worktree WT` resumes, and the report is written,
  not published, until a look at the numbers.
- After each run: `lms_campaign.py score NAME`, then `report --publish` and `python scripts/make_leaderboard.py`
  as `benchmarks/runs/LEADERBOARD.md` describes; the episodes stay in `results/e3-lms/` (gitignored).

## Resuming the 9B's d1-real run (set up 2026-10-26; resumed and finished the same day)

**What happened.** `e3-d1-real-qwen3.5-9b-q4km-lms-single` ran 20:21 PDT Oct 23 to 09:08 Oct 24 and lost 61 of its
99 episodes to the server, not the model (`results/e3-lms/<run>.log`, LM Studio's `~/.lmstudio/server-logs`):

1. 22:27:52 Oct 23: "LM Link client transport disposed" mid-stream. The guard reloaded; `lms load` came back
   with rc=1 while the load was still going, and the next request met HTTP 400 "No models loaded", which was not
   a reload marker. That episode and the next 40 died on it in ten seconds (22:27:58 to 22:28:07), one request
   each, until the load finished on its own and episode 53 ran normally.
2. About 01:50 Oct 24: generation stopped mid-prompt on the PC with nothing in LM Studio's log (the engine hung).
   The harness waited its 30-minute read timeout (client disconnect 02:20:49), then every request took the
   server five minutes to answer "Engine protocol predict request failed: fetch failed" while the model stayed
   listed as loaded, so the guard "asked again" instead of reloading: four attempts, 20 minutes an episode, 20
   episodes, seven hours, until the task list ran out. Why the engine hung is still open; the Mac's log shows
   nothing, so the PC's LM Studio log (and its GPU state at 01:50) is the place to look.

The 38 episodes that ran scored 63.8 effective (median 75.6; 30 submitted, 8 at the budget, no hard fails).

**What is built (2026-10-26, committed fed5f4d1).**

- `runners/openai_compat.py`: "No models loaded" is a reload marker; `LmStudioGuard.reload` waits until the
  server lists the model at the run's context (`LOAD_WAIT` 180 s) instead of trusting the CLI's exit;
  `probe()` is a one-token unstreamed completion with a 90 s timeout; `ensure_alive()` reloads and probes every
  30 s for up to 30 min and returns False when the engine never answers; `post_chat` asks again once on a
  reload marker with the model still listed and reloads on the next such error.
- `eval/providers` and `eval/agents`: `ready()` on providers and agents (the openai-compatible provider's calls
  `ensure_alive`); `eval/runner.py` asks it before every episode and stops the run (`stopped = "engine"`)
  without writing the episode when it says no, and stops after three episodes in a row that errored before
  their first step (`stopped = "errors"`). Stopped episodes have no end record, so the resume runs them.
- `lms_campaign.py`: `clear-errors RUN_ID [--apply]` and `e3 --worktree PATH`.
- Tests: four in `tests/test_runners.py`, two in `tests/test_eval_runner.py`.

**Done already.** The 61 errored episode files are in `results/e3-lms/<run>/errored-2026-10-26/`; `episodes/`
holds the 38 good ones. A detached worktree `.claude/worktrees/lms-9b-resume` is checked out at the run's pin
3777cb00 (its d1-real is the run's 99-task draw; main's d1-real at 9dd9af1e has 108 tasks and 14 of the run's
ids are gone from it, so a resume from main would not be the same run).

**To resume (each step waits on Robert's go).**

1. Commit the guard on main, then put it on the worktree:
   `git -C .claude/worktrees/lms-9b-resume cherry-pick <that commit>` (the worktree must be clean in `src` and
   `tests` for preflight). The resumed episodes then carry that commit in their pins; tools, instructions and
   verifier (d1-verify-v6) are the same as the first 38.
2. Load the model alone at 65k and start the resume (the campaign script does both):
   `python benchmarks/lmstudio/lms_campaign.py e3 qwen3.5-9b --taskset d1-real --samples 1 --run-id
   e3-d1-real-qwen3.5-9b-q4km-lms-single --worktree .claude/worktrees/lms-9b-resume`
   (`--print` shows the command; `--dry-run` lists the 99 cells, of which 38 are complete). It keeps the run's
   20-minute wall clock; a 45-minute clock would be a new run id, not a resume.
3. When it ends: `python -m roaddraft.eval report results/e3-lms/<run>` then `--publish`, and
   `scripts/make_leaderboard.py`. `run.json` is rewritten by the resume (its `started_at` and pins are the
   resume's); the per-episode headers keep each episode's own pins.

### Outcome (2026-10-26, written 2026-10-27)

The resume started 13:36 PDT on Robert's go from the `lms-9b-resume` worktree (d98e7025), was relaunched at
14:57 so the harness's own guard reloads at 131,072, and ended 21:18: 99 episodes, 98 scored. The PC's engine
died five more times that day (13:51, 17:16, 17:22, 18:35, 18:40, each a `predict request failed: fetch
failed` with the model still listed as loaded); the guard reloaded at 131k each time and the run lost one
episode, which died mid-stream at 18:40 and which the report leaves out of the score (termination `error`),
instead of the sixty-one the first attempt lost. Re-scored under d1-verify-v7 before publishing (the same
numbers as the run's v6): 63.6 effective [59.0-67.8], rubric 66.5, hard-fail 4%, clean 31%, submit 87%, no
invalid calls. Since the relaunch a third of the episodes sent a prompt over 65,536 (peak 93,893), all inside
131k. The run's window history is in `results/e3-lms/<run>/NOTES.md`; the worktree can be removed.

## The context window (decided 2026-10-26, Robert)

Local rows load at **131,072** tokens, parallel 1, from now on (`CONTEXT` in `lms_campaign.py`): the largest the
two 4060s hold for the 9B by LM Studio's estimate (13.3 of 16 GiB; 164k is at the edge, 262k spills to the CPU).
The 65,536 of the first runs matched the hosted vLLM rows' `MAX_MODEL_LEN`, but LM Studio does not refuse a prompt
past its window the way vLLM does: it truncates the middle and answers. Eight of the 9B's first 38 d1-real episodes
sent prompts over 65k (up to 159k) and ran on cut transcripts; vLLM would have ended them as context trips. The
window is a per-row setting now, recorded on the card: hosted rows 65,536 (refused past it), local rows 131,072
(truncated past it). The 9B's d1-real run: episodes 1 to 38 at 65,536; after the engine death at 13:51 on Oct 26
LM Studio brought the model back at its own 108,032 / parallel 4 (resumed episodes 1 and 2, and part of 3); from
14:31 on Oct 26 at 131,072 / parallel 1, reloaded by hand with the harness paused.

**The harness holds the window itself now (built 2026-10-27, committed 291ae711).** `Budgets.context_tokens`
(`--context-tokens N`, defaulting to `--lms-context N`; the campaign script passes both at `CONTEXT`): the LLM
agent ends an episode whose reply reports a prompt at or past the budget as a `context` budget trip before any of
that turn's calls run, as vLLM's refusal ends one on the hosted rows, and does not send a next request that cannot
fit by the transcript's own size (the last prompt count plus a floor of one token per 4.5 characters appended).
The budget is recorded with every episode. The queue of Oct 27 (`queue-2026-10-27.sh`) ran from a worktree at 291ae711, so the
9B's d1-test row is the first under the budget (no context trip; 17 of its 100 episodes peaked past 65k, the largest
prompt 104,370 tokens); the 9B's hard-pilots run predates it and relied on the window alone. Oct 28: at 131,072 the
two 16 GB cards hold the 9B Q4, GLM-4.6V-Flash Q4 and E4B Q4 and refuse Gemma 4 12B Q8_0, Devstral Small 2 Q3_K_L,
Ministral 3 14B Q6_K and Llama 3.1 8B Q4 ("failed to allocate buffer for kv cache"); what window those load at is
Robert's call (see the top of this file).

**Decided 2026-10-28 (Robert): each model loads at the highest window that fits**, `lms_campaign.py fit NAME` walking
131,072, 114,688, 98,304, 81,920, 65,536 and writing the first rung that loads to `models.json` as `context`; the
ceiling stays 131,072 and the floor is 65,536 (the hosted rows' window; a model that does not load there has too
little for these tasks and is dropped from the local list). The hosted vLLM rows keep their recorded 65,536. The fits
of Oct 28: Gemma 4 12B Q8_0 98,304; Llama 3.1 8B 65,536; Devstral Small 2 and Ministral 3 14B dropped (no rung loads).
