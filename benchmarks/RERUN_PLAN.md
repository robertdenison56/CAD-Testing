# Rerun plan: Track D under harness e3-v3 (drafted 2026-11-03)

Robert, Nov 3: review the tree, wipe the board rows the harness fixes no longer apply to, and lay out the time
on the PC against Runpod and the models to go through. The wipe is `runs/RETIRED.md` (34 rows out, 15 kept).
This file is the time and the list. Nothing here starts a run: the Oct 24 local-only rule, the Oct 28 order
(the PC first, Runpod after Stage 0) and "frontier rows on Robert's word" all stand.

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

The vague rows the headlines wait on (single mode, k = 1; none of them is queued except the local d1-test three):

| model | d1-test | d1-real | d1-test-hard | d1-real-hard |
|---|---|---|---|---|
| GPT-6.1 Terra (codex, medium) | ranked | to run | to run | to run |
| GPT-6 Luna (codex, medium) | ranked | ranked | to run | to run |
| Claude Sonnet 5.5 (claude-code, medium) | ranked | to run | to run | to run |
| Claude Opus 5.5 (claude-code, medium) | to run (its 88.4 row was retired Nov 3) | to run | to run | to run |
| Qwen3.5-9B, Gemma 4 12B, GLM-4.6V-Flash (local) | queue 10 steps 22-24, behind about 15 explicit nights | to run | to run | to run |
| the Runpod $100 queue (`runpod/PLAN.md`) | explicit as set up | explicit (cost5) | explicit (cost5) | explicit (cost5) |

A frontier vague row is the same run with `--level vague` (run id `...-single-vague-v3`) through the CLI route at
the same caps: 0.5-1.6 hours of wall time a d1 set on the subscriptions, the hard sets 2-4x that. Queue 10 (local,
at Gemma's hard-pilots on Nov 8, 31 of 112) and the Runpod queue run explicit prompts as set up, and their rows land
in the explicit tables. Moving the vague nights ahead, or setting `--level vague` on the Runpod queue, is Robert's
call; nothing here starts a run. A queue that publishes from a worktree older than this change rebuilds the board
in the old one-table layout, so regenerate it from main afterwards (`scripts/make_leaderboard.py`).

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
