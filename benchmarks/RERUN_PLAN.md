# Rerun plan: Track D under harness e3-v3 (drafted 2026-11-03)

Robert, Nov 3: review the tree, wipe the board rows the harness fixes no longer apply to, and lay out the time
on the PC against Runpod and the models to go through. The wipe is `runs/RETIRED.md` (34 rows out, 15 kept).
This file is the time and the list. Nothing here starts a run: the Oct 24 local-only rule, the Oct 28 order
(the PC first, Runpod after Stage 0) and "frontier rows on Robert's word" all stand.

## Nov 8 evening: explicit on its own board, a vague prompt on every task, every model rerun at vague

Robert, Nov 8 20:1x: "Move all explicit prompts to there own board. Main focus is now on vague. Rerun all models on
the vague prompts. Check if any of the eval tasks do not have a vague prompt style first, add them if needed".

**The check.** Every D1 task already had its own vague prompt: all seven D1 sets (d1-dev 50, d1-test 100,
d1-variance 20, d1-real 100, d1-real-dev 24, d1-test-hard 100, d1-real-hard 100) build both levels per task type
(`tasks/prompts.py`), and no task's vague text equals its explicit text. The 112 hard-pilots had one fixed brief
each, so each pilot was given a vague brief (`Probe.vague`): the request the way a PE asks for it, keeping what the
drafter cannot know (files, lines, stations, the data handed over, the answer format a check reads) and leaving
out the drafting standards the fixed brief spelled out. Where a pilot's check graded a standard the vague brief no
longer states, the pilot also has a vague check (`Probe.vague_check`) grading it by the spec's lenient rules (any
layer but 0, legible heights, any standard scale, values read by meaning).

By family (vague brief length against the fixed brief; a vague check where marked):

| family | pilots | vague brief | vague check |
|---|---:|---|---|
| p04 crowded annotation, p17 twisted sheet | 13, 15 | "Sheet 12 ... has lost the alignment data of its two lines ... Letter them again ... anchored through the reference. The sheet is crowded" (about 15% of the fixed brief) | all: E1 at the vague level (any layer but 0, lenient heights and tick, values by meaning, core table columns); station numbers and BC/EC along or square to the line, still reading from the bottom or right; a table titled with its line only where the sheet holds another |
| p05 sheet breaks | 8 | the stretch, scale and border kept (the fewest-sheets count is taken at that scale), "as few sheets as the stretch needs, with a match line at each break" | all: a match line at least 1.0 in on paper (D1-00's vague rule), lettered by meaning near it |
| p06 plan and profile | 5 | "Lay out sheet Plan 1 as a plan and profile sheet for CL1 from 10+00 to 17+50, with the design profile CL1 PGL." | all: any standard plan scale; the grid found where it is drawn and its datum read from its elevation lettering; a standard exaggeration; curve data read in more forms |
| p10 typical section | 5 | the whole design description kept; the drafting list and the viewport scale dropped | all: any standard scale for the detail; the cross slope as a percent or a decimal |
| p11 redlines | 12 | the sheet, base file, revision record (RD, 10-19-26), "keep it anchored" | all: a revision note quoting the redline accepted on every sheet |
| p12 plan set | 1 | the set's parts and the two quantities with their layers and units; border, scale, sheet count and lettering forms dropped | any standard scale and the layout count it needs; index, sheet numbers and match lines read by meaning; the quantities as a table or text |
| p13 striping | 6 | "per the MUTCD", the speed, profile and lanes kept; the marking pattern dropped | all: the MUTCD's own ranges (pair 0.20-0.60 ft off the centerline, a 10/30-like ratio, edge lines within 0.35 ft of 12 ft); the zones graded as before |
| p03 survey traps | 7 | the data kept (lists, systems, factors); explanations a surveyor knows dropped | the 3 deed pilots: the parcel on any layer but 0 |
| p01, p02, p14, p15, p18 | 5, 8, 9, 8, 10 | tool hints, enumerations and the markup key dropped; the files, lines, questions and answer formats kept | none: their checks grade values and edits, nothing the vague brief stops stating |

All 112 pass the selftest at both levels (each scripted solution passes its level's check, each untouched start
fails it); every explicit brief, explicit check and scripted solution is unchanged.

**How the set holds it.** A vague pilot is its own task id (`PR-<probe>-<hash of the vague text>`); the explicit
ids are unchanged, so every published pilot row still matches the set. The manifest row carries both ids
(`vague_task_id`), the episode is graded by the check of its level, and the board holds a run to the ids of its
level. `hard-pilots` now splits by level like the D1 sets (`report.ONE_PROMPT_SETS` is empty). The pilot selftest
checks both levels (`python -m roaddraft.probes.pilot selftest`).

**The boards.** `runs/LEADERBOARD.md`, the README block and `leaderboard.svg` rank the vague-prompt runs only, the
main board; `runs/LEADERBOARD_EXPLICIT.md` ranked every explicit-prompt run, set by set
(`report.LEVEL_BOARD_FILES`), the eight hard-pilots rows among them, until that board was retired on 2026-11-16 at
the Track D close-out (`runs/RETIRED.md`, `report.RETIRED_BOARDS`). No row was dropped or re-scored. The eval
dashboard (Vr9ftxKwjEbAEfiqnPjxqi) follows: vague tables and grids first, the explicit board in a section of its own
(page v3, datasets v5).

**The reruns.** Every model gets a vague row on all five sets, all at the v3 pin (3b7e7fe9: harness e3-v3, tools
0334fd4aaade, instructions 4dff2849). The D1 queues of 14:4x carry on; added: the vague pilots for every model, and
the two vague rows that ran before the v3 fixes (Terra d1-test 91.3, Sonnet d1-test 70.9), rerun at the pin. The
pilot runs come from the worktree `vague-pilots`: 3b7e7fe9 with the vague-pilot code applied uncommitted
(`results/e3-lms/vague-pilots.patch`; episodes record dirty).

| model | d1-test | d1-real | d1-test-hard | d1-real-hard | hard-pilots | queue |
|---|---|---|---|---|---|---|
| GPT-6.1 Terra (codex) | rerun at v3 (follow-on) | ranked 90.5 | 13/100, paused | queued | follow-on | `e3-codex/queue-2026-11-08-vague-codex.sh`, then `...-vague-pilots-codex.sh` |
| GPT-6 Luna (codex) | ranked 76.1 | ranked 71.8 | queued | queued | follow-on | same |
| Claude Sonnet 5.5 (claude-code) | rerun at v3 (added) | queued | queued | queued | added | `e3-claude-code/queue-2026-11-08-vague-claude-code.sh` |
| Claude Opus 5.5 (claude-code) | queued | queued | queued | queued | added | same |
| Qwen3.5-9B, Gemma 4 12B, GLM-4.6V-Flash (PC) | 9B running | queued | queued | queued | follow-on | `e3-lms/queue-2026-11-08-vague-local.sh`, then `...-vague-pilots-local.sh` |

Nov 10 20:40: GLM dropped from the three hard sets (Robert); the PC's rest (Gemma d1-test-hard in flight, then the 9B
and Gemma on d1-real-hard and hard-pilots) moved to `e3-lms/queue-2026-11-10-vague-hard-local.sh`; see `lmstudio/PLAN.md`.
| Qwen3.6, Gemma 4 31B, GLM-5.3, gpt-oss-120b (Runpod) | set up | cost5 | Qwen3.6 cost5 | Qwen3.6 cost5 | Qwen3.6 cost5 (back) | `runpod/queue-trackd-v3.sh`, not launched (top-up + go) |

The codex queue was paused by hand at 20:31 (SIGSTOP on its own processes): ChatGPT's weekly usage limit holds
until Nov 11 9:17 PM, and each 30-minute retry spent one of its 40 tries, so it would have given up long before the
reset. A sleeper sends CONT at Nov 11 21:20. The claude-code queue still waits on the `claude` CLI sign-in.

## Nov 8: the vague prompt is the board's focus

Robert, Nov 8: the explicit D1 prompts read too detailed (a natural-language rewrite was still "too long, give me
the vague version"), then "make sure the vague runs are seperated from explicit runs for all test sets" and "i think
we need to focus on the vague prompts only". The board now ranks each prompted set once per prompt level, vague
first: the vague ranking is the set's headline (and d1-test's is the board's top line), the explicit rows follow
as a table of their own with their own ranks (`report.BOARD_LEVELS`, `LEVEL_NOTES`). A vague score and an explicit
score are not compared row against row; the paired prompt gap of the eval plan (§5) stays the comparison.
`hard-pilots` keeps one ranking, since a pilot's brief is the same at either level (`report.ONE_PROMPT_SETS`). A
cost subset is ranked per level too. No score moved and no row left the board; the explicit tables were kept, not
dropped.

The board at the split:

| set | vague rows | explicit rows |
|---|---|---|
| d1-test | 3: GPT-6.1 Terra 91.3, GPT-6 Luna 76.1, Sonnet 5.5 70.9 | 13 |
| d1-real | 1: GPT-6 Luna 71.8 | 11 |
| d1-test-hard | none | 4 |
| d1-real-hard | none | 4 |
| hard-pilots | one ranking, 8 rows | |

**Nov 8 14:4x PST, the queues switched to vague** (Robert: "Stop all runs with explicit prompts and start the vague
ones", then "Update the runpod batches with vague prompts only"). Queue 10 (local, explicit) was stopped by hand on
Gemma's hard-pilots (36 of 112 episodes on disk, resumable under its run id; GLM's pilots, the six local hard-set
singles and the 15 self-correct / vision nights were never started). Every run below is single mode, k = 1, vague,
run id `...-single-vague-v3`, from a worktree at 3b7e7fe9 (harness e3-v3, tools 0334fd4aaade, the pin of every v3
row); hard-pilots has no vague run (a pilot's brief is fixed text), so no queue holds one now.

| model | d1-test | d1-real | d1-test-hard | d1-real-hard | queue |
|---|---|---|---|---|---|
| GPT-6.1 Terra (codex, medium) | ranked 91.3 | queued (first) | queued | queued | `results/e3-codex/queue-2026-11-08-vague-codex.sh` |
| GPT-6 Luna (codex, medium) | ranked 76.1 | ranked 71.8 | queued | queued | same |
| Claude Sonnet 5.5 (claude-code, medium) | ranked 70.9 | queued (first) | queued | queued | `results/e3-claude-code/queue-2026-11-08-vague-claude-code.sh` |
| Claude Opus 5.5 (claude-code, medium) | queued | queued | queued | queued | same |
| Qwen3.5-9B, Gemma 4 12B, GLM-4.6V-Flash (local) | queued (9B first) | queued | queued | queued | `results/e3-lms/queue-2026-11-08-vague-local.sh` |
| Qwen3.6, Gemma 4 31B, GLM-5.3, gpt-oss-120b (Runpod) | vague, set up | vague, cost5 | Qwen3.6 cost5 | Qwen3.6 cost5 | `runpod/queue-trackd-v3.sh`, not launched (top-up + go) |

The codex and claude-code queues publish each run with main's report and board code, so the board keeps its vague
and explicit tables; the local queue writes its reports unpublished (a look first, then publish from main). The
claude-code queue sits behind a waiter: the headless `claude` CLI it runs reported "OAuth session expired" on its
first episode, so it starts once `claude auth status` reads signed in. Times: codex about 0.5-0.7 h a d1 set, the
hard sets 2-4x; claude-code paced by `sonnet-caps.env` (50% of the 5-hour window, 85% of the week); the PC 10-20 h a
night, 12 nights.

### Do vague prompts fail on drafting standards?

Robert, Nov 8: "Important to know if any of these prompts fail due to not knowing drafting standards".
`python -m roaddraft.eval standards <vague run>` splits a vague run's lost points into a drafting standard not
applied (an element a plan sheet carries left off, lettering on layer 0 or at an illegible height, labels over
linework, a non-standard scale), the work done wrong (wrong values, doubled or hand-typed labels), hard fails and
early ends; paired with the same model's explicit run on the same tasks, each part splits again into what the
explicit episode earned back when told the standard and what it lost too. On the four vague rows that have an
explicit twin:

| vague row | lost a task | a standard not applied | of it, recovered when told | the largest standard |
|---|---:|---:|---:|---|
| GPT-6.1 Terra, d1-test (91.3) | 8.7 | 8.6 | 7.4 | lettering on layer 0, 3.2 |
| GPT-6 Luna, d1-test (76.1) | 23.9 | 20.8 | 18.2 | lettering on layer 0, 8.2 (52 of 89 tasks) |
| Claude Sonnet 5.5, d1-test (70.9) | 29.1 | 26.6 | 22.6 | lettering on layer 0, 13.1 (68 of 89 tasks) |
| GPT-6 Luna, d1-real (71.8) | 28.2 | 20.9 | 15.1 | lettering on layer 0, 8.2 |

So yes: most of what a vague prompt costs is drafting standards, and most of it comes back when the standard is
stated. The largest single one is layer 0: every start document's current layer is `0`, a label command without
`layer` lands there, and at the vague level the models leave `layer` off (Sonnet: 110 of 115 `place_label` calls in
its layer-0 episodes) although 77 of the 89 start documents offer annotation layers; told the layer, they pass it.
"Nothing is drafted on layer 0" is a CAD standard the vague prompt leaves to the drafter, so the verifier's lenient
rule (any layer but 0) is working as written. Robert, Nov 10: "The layer 0 standard must remain": it stays graded,
and the start documents keep layer `0` current. Next come
labels set over linework or each other (1.3-5.3 points, about half recovered when told) and elements left off:
bearings, BC/EC and curve numbers, station ticks and numbers, title-block fields (0.5-3.3 each, mostly
recovered when told). Wrong values and early ends are small (each 0-4 points). k = 1: per task the split is noisy, the
set totals are the read. The report goes in each run's `report/standards.md`; run it on each vague run as it lands
(the local hard sets have no explicit twin, so theirs split by finding code alone).

### Why each model fails: the cause analysis, once the runs are complete

Robert, Nov 10: "all failures should be analyzed once complete to determine if models were failing due not knowing
the standards or failing the tool use, thinking, etc." When the last rows land (the local hard sets, then any Runpod
queue 2 rows), every lost point and every failed episode on the vague board gets one cause:

- **a standard not known**: the `standard` part of `eval standards`, split by its explicit twin where there is one
  (recovered when told = the model did not know it);
- **tool use**: invalid or erroring calls left unrecovered, labels typed by hand where a label command draws them,
  a point computed by hand where the command takes the entity or anchor, the wrong command or label kind;
- **reasoning**: a wrong value from right tool use, the wrong target, the brief or the sheet misread, a job stopped
  short and submitted unfinished;
- **budget or harness**: the step, time or context limit, an engine stall, a provider error (not the model's skill).

Built Nov 10: `python -m roaddraft.eval causes RUN [RUN ...] --table benchmarks/runs/FAILURE_CAUSES.md`
(`roaddraft.eval.causes`; the rules are in its docstring, 17 tests). It reads only the episode files: the
verifier's findings, each call and what it made, and the start document's own entities (findings on those are
left out). A standard counts as *confirmed* only when the same model's explicit run on the same harness and tool
surface earned it back when told; one it lost even when told goes to reasoning. hard-pilots is pass or fail, so a
failed pilot takes one cause. Each run's detail (sub-causes, task types, example tasks, the pilot items most
often missed) is in its `report/causes.md`.

**First pass, Nov 10, on the 35 published vague runs** (benchmarks/runs/FAILURE_CAUSES.md; points a task):

- The frontier on the D1 sets loses almost only standards: d1-test Opus 4.3 of 4.5, Terra 6.4 of 7.2; d1-real
  Terra 8.6 of 9.5. On the paired hard sets the confirmed standards are Opus 16.1 of 22.4 and Terra 14.8 of 27.9
  (d1-real-hard), and Sonnet and Luna 28-33 of 45-57. Runpod's open-weight rows look the same on d1-test (Gemma 4
  31B 17.4 of 19.9, Qwen3.6 21.7 of 23.7, GLM-5.3 32.1 of 33.5), but none has an explicit run, so unconfirmed.
- The local three lose most to reasoning: d1-real the 9B 22.5 of 40.3 and Gemma 4 12B 24.0 of 41.0 (mostly
  overlaps left even when told, and labels drawn where no sheet shows them or at the wrong place). GLM-4.6V-Flash
  submits with nothing drawn on about a fifth of its tasks (19-22 points of reasoning) and loses 35-52 to tool use,
  mostly tasks where every drawing call it made failed.
- Tool use is mostly one hint: `annotate_stationing` refused a sheet and said "use place_label for sheet labels",
  which has no tick kind, so the ticks were never drawn. It is 82 of the 93 tool-use points summed over the
  hard-pilots runs and 36 of 50 on d1-test-hard. That refusal is fixed on main (4d135e7d: stationing is drawn in
  model space, the hint says how), after the runs' pin 3b7e7fe9, so these rows measure the old hint. Terra's 11.6
  on d1-real-hard is mostly the fault budget: the same failing call repeated (a layer it never created).
- hard-pilots loses most to reasoning: a pilot failed even when told, with no tool fault (Opus 33.9 of 59.8,
  Sonnet 56.3 of 75.9, Luna 75.0 of 97.3); the vague brief leaving out what a pilot needed is 12.5-15.2 for Opus,
  Terra and Sonnet. Qwen3.6's 66 have no explicit run: 42.4 unresolved.

Hand-checked on 7 episodes before this pass; three rules came from them (a submit with nothing drawn; text escaped
wrong in a call, which is tool use; a curve table listing another sheet's curves, which is a standard). Open:
Opus, Sonnet and Terra have no explicit run at the v3 pin on d1-test or d1-real, so those rows' standards are
unconfirmed; a failed pilot's single cause is coarse (its missed items are in the run report); k = 1. Rerun the
command, with its `--table`, as the local hard sets and any Runpod queue 2 rows land.

## What changed under the rows

| change | commit | what it moves |
|---|---|---|
| `place_label` kind help names `mc` as the curve callout | d485d7e1 | tool surface `379e02f1` -> `0334fd4aaade`; every row that lettered the curve number as `custom` scored 0 on `curve-callouts` / `real-callouts` (about 5 points of a d1-test row) |
| harness `e3-v3` | d485d7e1 | the D1 clock 20 -> 45 min, a pilot's 30 -> 120; a one-item list read as its value (repaired, not invalid); the faults budget counts turns, not calls |
| `hard-pilots` 33 -> 112, `d1-test-hard`, `d1-real-hard` | 0036060b | the pilot checks' hash moved; two new sets with no row |
| `d1-verify-v8` | bb9cd7ef | D1-16 through the drafter's viewport; the kept rows score the same as under v7 |
| `d1-test-hard` redrawn | this tree | a station equation on one task in five (`taskset.hard_equation`), 75 of 100 ids moved; no row was published |

A rerun is a new run id from a worktree at main bb9cd7ef or later (or this tree once the redraw is committed).

## Time: the PC against Runpod

Measured from the episode files (`results/e3-*/<run>/episodes`). Episode time is the sum of the episodes'
own clocks; wall is first start to last end, which on the PC includes stalls, reloads and the queue's retries.

### RobertsPC through LM Studio (two RTX 4060, one episode at a time)

| model | d1-test x 1 (100) | d1-real x 1 (100) | hard-pilots (33) | other d1-test rows | gen tok/s |
|---|---|---|---|---|---|
| Qwen3.5-9B Q4_K_M, 131k | 10.4 h episodes, 10.5 h wall (a clean night) | 11.0 h episodes (wall five days over the Oct 23-26 server saga) | 8.4 h / 8.4 h | self-correct 11.6 h / 35 h wall (LM Link drops); vision 11.7 / 11.7; vague 6.1 / 6.1 | 21-28 |
| Gemma 4 12B Q8_0, 98k | 6.1 h episodes, 24 h wall (a five-hour engine stall, nine zero-step episodes) | 7.4 h / 7.5 h | 7.5 h / 7.5 h | self-correct 12.2 h / 12.9 h | 7-10 |
| GLM-4.6V-Flash Q4_K_M, 131k | 6.2 h episodes, 45 h wall (six silent-turn stalls, six attempts) | 4.0 h / 8.1 h | 4.5 h / 5.2 h | self-correct 5.2 h / 13.7 h | 12-14 |

Under e3-v3 the clock-stopped episodes run on: up to 25 minutes longer each on D1 (or to 60,000 output tokens,
about 35-40 minutes at the 9B's rate), up to 90 minutes longer on a pilot. The 9B lost 4 to 14 episodes a D1
set and 8 of 33 pilots to the old clocks, Gemma 2 to 5, GLM 2, so a 9B set grows by 2 to 6 hours and its
pilots by up to 12.

Projected episode time per set, single mode, under e3-v3 (the hard sets from GPT-6.1 Terra's five-episode
samples, which ran 4x its d1-test episode time on `d1-test-hard` and 2x on `d1-real-hard`; a budget-bound
local episode caps at 45 minutes, so the local ratio is likely lower):

| set | Qwen3.5-9B | Gemma 4 12B | GLM-4.6V-Flash |
|---|---|---|---|
| d1-test x 1 | 12-16 h | 7-9 h | 7-8 h |
| d1-real x 1 | 13-17 h | 8-10 h | 5-6 h |
| hard-pilots x 1, 112 (3.4x the 33) | 30-40 h | 25-30 h | 15-18 h |
| d1-test-hard x 1 | 40-55 h | 25-35 h | 25-30 h |
| d1-real-hard x 1 | 25-35 h | 15-20 h | 10-12 h |
| **five sets, single** | **120-160 h** | **80-105 h** | **60-75 h** |

So the three local models through the five sets in single mode are about 260-340 hours of episode time,
11 to 14 days of the PC running without a break, or 26 to 34 ten-hour nights. Self-correct, vision and vague
on d1-test add about 1.2-1.5x a single set each (the 9B's eight queue-9 runs were the earlier push's size).
Wall time has run 1x to 7x the episode time depending on the night: the 9B's clean nights match, Gemma's and
GLM's stalls did not. The 9B at k = 5 on d1-test (the training baseline) is four more nights.

### Runpod (vLLM on the Hub worker, four episodes at once on one worker)

| run | episodes | episode time | wall | bill |
|---|---|---|---|---|
| Qwen3.6-35B-A3B bf16, d1-variance x 5 (BLACKWELL_96, $3.49/h) | 100 | 4.6 h | 1.2 h | about $5 (the two d1-variance runs were $10.36 together) |
| Gemma 4 12B bf16, d1-variance x 5 (AMPERE_48, $1.22/h) | 100 | 4.1 h | 1.1 h | about $5; 10 episodes lost to the 570 s proxy cut-off |
| Qwen3.5-9B bf16, Track P k = 3 (A40) | 99 | – | 4.3 h | $4.22 |

A 100-episode D1 set is 1-2 hours of wall time and $2-8 (the pool's rate times the wall plus a five-minute
cold start); hard-pilots at 112 about 4-6 hours and $5-20; a hard set 2-5 hours and $3-18. Five sets for one
model in single mode: 10-18 hours of wall time and $15-70, the A40 rungs at the low end and the Blackwell and
H200 rungs at the high end. The public GLM-5.3 endpoint bills per token: $20-35 a d1-test row with the resent
prefix cached, $50-85 without, capped at $40 in the plan. The whole set-A spread (seven models) is $65-101 on
d1-test alone, as planned, and about $150-350 over all five sets. The balance read about $12 on Oct 20; the
Oct 23 rule (no more Runpod spend until Robert says so) stands.

Against the PC: Runpod runs a set 6-10x faster in wall time (four concurrent episodes at 2-3x the token rate)
for about $5 per hundred episodes where the PC spends a night. The PC's rungs cost nothing but time; the two
sides do not overlap by Robert's rule (a model with a local row gets no Runpod row). Before any Runpod row:
score the 570 s cut-off as a budget trip, re-pin the campaign worktree, and set the window to 131,072 where
the card has room (`runpod/PLAN.md`, "Before a go").

### The frontier CLIs (subscriptions, the Mac)

Codex (GPT-6.1 Terra, GPT-6 Luna, medium): 100 D1 episodes in 0.5-0.7 hours of wall time, 4.5-5 hours when a
usage cap paced it; 33 pilots in 0.4-0.5 hours. Claude Code (Opus 5.5, Sonnet 5.5, medium): Opus 1.1-1.6 hours
per 100, Sonnet 0.5-0.9; 33 pilots 0.9-2.4 hours. Opus's notional cost is $0.41 a sheet on d1-test, $0.66-0.72
on d1-real and about $2 a pilot, so a 112-pilot run reads about $225 and the two hard sets about $100-120 each
at 2-3x a d1-test sheet; the Max plan's caps, not dollars, are what paces it (50% of each 5-hour window, 85% a
week, `results/e3-claude-code/sonnet-caps.env`).

## The models to go through

Every model runs the same way: a one-episode smoke (`d1-dev` or `d1-real-dev`), then single mode with explicit
prompts on `d1-test`, `d1-real`, `hard-pilots` (112), `d1-test-hard`, `d1-real-hard` in that order; then
self-correct, vision and vague on d1-test (and self-correct on d1-real and the pilots) as the Track D plan has
them. k = 1 is ranked; k = 5 only for the 9B on d1-test. Reports are written and published only after a look.

**1. Local, LM Studio on RobertsPC (first, by the Oct 24 and Oct 28 rules).** Their old rows are retired, so
every set is a rerun: Qwen3.5-9B Q4_K_M (131k), Gemma 4 12B Q8_0 (98k), GLM-4.6V-Flash Q4_K_M (131k).
Robert's call: Gemma 4 E4B Q4_K_M (131k; no submit on its one smoke episode). Not run: Qwen3.5-4B (Robert,
Oct 31), Devstral Small 2, Ministral 3 14B and Llama 3.1 8B (dropped, no window or no tool calls).

**2. The frontier through the CLI route (on Robert's word; the subscriptions).** Rows to redo and the sets
no frontier model has:

| model | redo (retired) | new |
|---|---|---|
| GPT-6 Luna (medium, codex) | d1-test single, self-correct, vision, vague; d1-real single, self-correct, vision, vague; hard-pilots single, self-correct, vision | d1-test-hard, d1-real-hard |
| Claude Opus 5.5 (medium, claude-code) | d1-test single and vague; d1-real single; hard-pilots single and self-correct | d1-test-hard, d1-real-hard |
| GPT-6.1 Terra (medium, codex) | hard-pilots single and self-correct (its 112-pilot, d1-test-hard and d1-real-hard samples of Nov 3 sit unpublished in `results/e3-codex`; the d1-test-hard one predates the redraw) | d1-test-hard, d1-real-hard |
| Claude Sonnet 5.5 (medium, claude-code) | hard-pilots single and self-correct | d1-test-hard, d1-real-hard |

Not run: GPT-6.1-Sol (Robert, Oct 31), GPT-6-Astra (pilot rig only).

**3. Runpod, self-hosted bf16 on the parked endpoints (after Stage 0; `runpod/PLAN.md` set A).**
Qwen3.6-35B-A3B, Gemma 4 31B, Qwen3.8-27B, Gemma 4 26B-A4B, GLM-4.7-Flash, gpt-oss-20b; with budget to spare,
gpt-oss-120b and Qwen3.5-122B-A10B-FP8 (redeploy from the Hub first).

**4. Runpod public endpoint.** GLM-5.3 (`b1dd8hy2hqo1nb`), a five-episode smoke for the cached share first,
then d1-test under `--cost-cap 40`.

## Open for Robert

- Queue 9 is paused (SIGSTOP, Nov 3 13:33) inside the 9B's k = 5 run at 132 of 400 on the old pin 97469b45.
  Under e3-v3 it feeds no board row: kill it, or let it finish as a record.
- The four frontier models' hard-pilots and hard-set runs are the costliest reruns (Opus about $550-600 notional
  for the three sets); the local push comes first by the standing rule.
