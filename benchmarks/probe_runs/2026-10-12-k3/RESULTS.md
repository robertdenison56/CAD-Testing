# 2026-10-12 — all 33 probes at k = 3 on the one-convention-set engine: Haiku 4.5, Sonnet 5.5, Gemma 4 E4B, Fable 5.1, Qwen3.5-9B, GPT-6-Luna, GPT-6-Astra

The probe set changed on 2026-10-12 (commit `2697ee5`: the engine's labelers default to the Plans Preparation
Manual's lettering, the probe fixtures sit on Caltrans named levels, the checks read the Caltrans station digit;
probe set `sha256:2fce3b5c1c75`), so every row on the board had to be rerun. This folder holds the reruns; each
model's repeats go under `runs/<model>-r1..r3`. Haiku 4.5 ran first, Sonnet 5.5 next, Gemma 4 E4B overnight
through LM Studio; Fable 5.1 waited for the account's weekly Fable window to reset and ran its three repeats one per
5-hour window on Oct 13. Qwen3.5-9B ran overnight Oct 13 to 14 on the Runpod serverless endpoint (bf16 on vLLM).

**Rig.** The same as `2026-10-08-k3`: `python -m roaddraft.runners run --backend claude-code` on the standalone
CLI (2.1.296) signed in to claude.ai, so a subscription, no API key. One `roaddraft-mcp` per probe, started by
the CLI from the generated config, with autosave and a trace; the server's instructions as the whole system
prompt, no built-in tools, the probe's task text as the prompt. 15 minutes and a $3 CLI cap per probe, 120
turns. Each model's three repeats ran as three processes in parallel: Haiku 20:21 to 20:57 PDT, Sonnet 20:45
to 20:59. The 30,000-character result cap is still the runner's own client's, not the server's, so on this
backend an oversized result still reaches the model as the CLI's file pointer (see the Oct 8 writeup); both
models here ran under the same condition.

## Result: Haiku 23, 27, 24 of 33; Sonnet 32, 32, 31 of 33

| set | Haiku r1 | r2 | r3 | Sonnet r1 | r2 | r3 | Haiku on Oct 8 (old probe set) |
|---|---|---|---|---|---|---|---|
| the 17 (9 find, 8 draft) | 16 | 17 | 16 | 17 | 17 | 17 | 16, 15, 15 |
| Tier 2 (6) | 4 | 5 | 3 | 6 | 6 | 6 | 3, 4, 1 |
| Tier 3 batch A (4) | 2 | 2 | 2 | 4 | 4 | 4 | 2, 0, 1 |
| Tier 3 batches B and C (6) | 1 | 3 | 3 | 5 | 5 | 4 | 0, 1, 0 |
| **all 33** | **23** | **27** | **24** | **32** | **32** | **31** | 21, 20, 17 |

| probe | Haiku r1 r2 r3 | Sonnet r1 r2 r3 | what a failing repeat left on disk (the first one) |
|---|---|---|---|
| the 9 find probes | P P P | P P P | |
| draft-tangent-ne, draft-pi-curve, draft-bearing-distance, draft-edges-shoulders, draft-cul-de-sac, draft-building, draft-roadway | P P P | P P P | |
| draft-turn-lane | . P . | P P P | Haiku: the full-width edge 24 ft right has no linework on any of its 25 check points |
| sheet-set-callouts, station-callouts | P P P | P P P | |
| clean-callouts | P P . | P P P | Haiku: 'EDGE OF PAVEMENT' sits over linework (less than 0.05 in of air) |
| draft-intersection-corner | . P P | P P P | Haiku: the 50 ft curb return is not drawn where it belongs (worst point 61.8 ft off) |
| draft-fix-the-drawing | . . . | P P P | Haiku r1, r2: the 12 ft edge only partly redrawn (49 of 189 check points bare); r3: the EDGE OF PAVEMENT callout still points at the shoulder |
| draft-roadway-sheets | P P . | P P P | Haiku: the left edge of pavement is 1.00 ft from where it belongs on all 85 check points |
| line-data | . . . | P P P | Haiku r1: T-2's lettering runs at 71.56° on the sheet, the bearing's own number, where the line runs at 18.43°; r2: T-1's lettering runs over linework; r3: T-1's lettering sits 1.66 in from its line |
| curve-points | P P P | P P P | |
| curve-data | . . . | P P P | Haiku r1, r3: no bubble numbered 1 on the curve; r2: the table runs outside the drawing area |
| stationing | P P P | P P P | |
| width-dims | P P P | P P . | Sonnet r3: the left shoulder is not dimensioned at 17+00 |
| row-data | . P . | P P P | Haiku: the tag C1 is on the left right-of-way line; the task is the right-hand one |
| equation-data | . P P | P P P | Haiku r1: T-2's lettering reads `N 71°33'54\" E\n1240.36'`, the escape characters typed into the text |
| qa-alignment-data | . . P | P P P | Haiku: no bubble numbered 1 on the curve |
| l2-match-lines | . . . | P P P | Haiku r1: the match line at 574+50 runs at 166.94° where square to SR70 is 90.14°; r2: 'MATCH LINE (L-1)' not lettered along its line; r3: the match line is not lettered at all |
| l2-alignment-data | . . . | . . . | Haiku r1: the PCC at 588+34.95 lettered EC; r2: tangent data at 11.50° where the line runs at 5.03° (parallel in the model; the viewport is turned −6.457°); r3: the EC at 576+16.93 not lettered. Sonnet r1: the table has no row for curve 2; r2: no bubble numbered 2 (bubbles 3, 4, 5); r3: '585+36.75 BC' overlaps the sheet's '1450' |

Haiku: 21 probes pass every time, 5 fail every time, 7 split. Sonnet: 31 pass every time, 1 fails every time,
1 splits. The one probe nobody passes is `l2-alignment-data`, the whole-job Tier 3 probe on the Caltrans L-2
sheet with its turned viewport.

## What moved for Haiku since Oct 8, and why

This is not the same test, so the Oct 8 row is not a baseline for the model: the fixtures, the checks and the
engine all changed. Where a probe's marks moved, the cause is on record:

| probe | Oct 8 | Oct 12 | cause |
|---|---|---|---|
| draft-bearing-distance | . . . | P P P | the COGO input the Sep 22 writeup named as the T1 gap (`draw_traverse`, bearing-distance legs) landed Oct 8 and merged Oct 9; Haiku now draws RAMP-B from its description |
| stationing, curve-points, width-dims | . . . | P P P | the labelers (`annotate_stationing`, `place_label`, `place_dimension`) default to the PPM's forms, which are what the checks read: 7 ft ticks, the Caltrans digit below the line, BC/EC square to the line. A model that takes the default route now matches without knowing the convention |
| equation-data, row-data | . . . | . P P / . P . | the same default route; the remaining failures are the model's (the escaped text above; the tag on the wrong right-of-way line) |
| station-callouts, sheet-set-callouts | . P . / P P . | P P P | split probes on Oct 8 that happened to pass three times; variance, not a change |
| line-data | P . P | . . . | the check now wants the bearing *and* the length above the tangent; Haiku rotated the text by the bearing's number once, set it over linework once, and 1.66 in off once |
| curve-data | P . . | . . . | the check now wants the curve number in a bubble on the curve and the No./R/Δ/T/L table; Haiku lettered the number bare twice and put the table off the drawing area once |
| qa-alignment-data | . P . | . . P | the same bubble requirement |

So Haiku's gain (21, 20, 17 → 23, 27, 24) is mostly the engine's: the default route now draws what the office
expects, and the checks reward it. Its losses are the two Tier 3 probes whose checks now ask for the full PPM
form. Sonnet passes both forms almost every time, which is the result that matters for the ranking: on this
probe set the gap between the two Claude models is 21 points of pass rate, and Sonnet's only hard fail is the
L-2 whole-job probe.

## Measures (99 episodes each)

| | Haiku 4.5 | Sonnet 5.5 |
|---|---|---|
| stops | 99 answered | 99 answered |
| tool calls | 1,375 (13.9 per episode), 58 faulted: 4.2% invalid | 904 (9.1 per episode), 18 faulted: 2.0% invalid |
| wall clock | 36 min for the three repeats in parallel; 1.7 h of episode time | 14 min; 0.6 h of episode time |
| cost at list price | $11.15 by the CLI's figure ($9.71 by the runner's estimate): $0.11 per episode | $9.60 by the CLI's figure ($10.64 by the runner's): $0.10 per episode |

Sonnet is cheaper per episode than Haiku here because it makes a third fewer calls and answers in a third of
the turns; both are billed to the subscription, not per token. The Oct 8 Haiku run had 6.4% invalid calls; the
fall to 4.2% is the labelers accepting the referenced-alignment names the models reach for (`DESIGN:SR-100`)
instead of faulting on them.

## Gemma 4 E4B: 9, 11, 9 of 33

The smallest tool-use model LM Studio lists (`google/gemma-4-e4b`, Q4_K_M, 4B effective parameters), on
RobertsPC over LM Link, loaded at a 65,536 context, through `--backend openai` with the LM Studio guard. One
process ran the three repeats one after another, 20:46 to 04:31 PDT (7 h 45 min; 140, 170 and 154 minutes of
episode time per repeat). 30 minutes and 120 turns per probe; renders replaced by a note, as on Oct 7. The
guard fired twice at the start and never again: Gemma's chat template refused the list-valued schema `type`
(rewritten to `anyOf`, the Oct 7 fix), and LM Studio had JIT-loaded the model at a smaller context than the
first request needed (reloaded at 65,536). One result was cut at the 30,000-character cap.

| set | r1 | r2 | r3 | Gemma on Oct 7 (Tier 3 B and C only, old probe set) |
|---|---|---|---|---|
| the 17 (9 find, 8 draft) | 9 | 11 | 9 | not run |
| Tier 2 (6) | 0 | 0 | 0 | not run |
| Tier 3 batch A (4) | 0 | 0 | 0 | not run |
| Tier 3 batches B and C (6) | 0 | 0 | 0 | 0 |
| **all 33** | **9** | **11** | **9** | |

Seven probes pass every time (edge-c102, edge-curve-c102, both-edges-c101, pc-by-station, edge-c102-paper,
sta-offset-c101-paper, draft-edges-shoulders), twenty fail every time, six split. Nothing above Tier 1 passes.

| probe | r1 r2 r3 | what a failing repeat left on disk (the first one) |
|---|---|---|
| shoulder-c101 | . . . | the leader lands 4.69 ft from the shoulder line, on nothing |
| centerline-c103 | P P . | the leader lands 2,996 ft from the centerline on C-103: a point from another sheet |
| title-blocks | . . . | every scale reads `1\" = 50'`: the escape character typed into the field, all three times |
| draft-tangent-ne | . . P | MAIN-ST ends 1,697 ft from where it was described |
| draft-pi-curve | . . P | SR-9 begins at 0+00, not the 50+00 the task gives |
| draft-bearing-distance | P P . | nothing drawn for the centerline |
| draft-turn-lane | . P . | the full-width edge 24 ft right has no linework on any check point |
| draft-cul-de-sac | . . . | the 45 ft bulb is drawn, but on layers `0` and `align_MAIN`, not `rd_EP` |
| draft-building | . P . | 20 of 44 footprint check points bare; the worst 40 ft off |
| draft-roadway | . . . | the left edge of shoulder not drawn (85 of 85 check points bare) |
| sheet-set-callouts | . . . | the callouts went into the model, not onto the sheet |
| station-callouts | . . . | 11 of 15 stations have no leader |
| clean-callouts | . . . | the leader for the right edge of shoulder lands 20 ft off, on the centerline |
| draft-intersection-corner, draft-fix-the-drawing, draft-roadway-sheets | . . . | the curb return not drawn; the 12 ft edge not redrawn; ELM-AVE begins at 0+00 |
| the 10 Tier 3 probes | . . . | nothing lettered where the check looks: `stationing` added nothing to C-102; `curve-data`'s table lists the wrong curve; `row-data` tags the wrong right-of-way line |

**Measures (99 episodes).** 99 answered: no budget, turn-cap or context stops. 865 tool calls (8.7 per
episode), 413 faulted: **47.7% invalid**, with 145 recovered and 5 fault loops. The longest episode was 20
minutes (`clean-callouts`, r2). The faults are the schema, not the drawing: `place_callout` named an alignment
without a `target_anchor` 38 times and gave no `position` 16 times, `place_label` omitted its `anchor` 24 times
and sent `content: null` 14 times, `annotate_stationing` was asked to draw on a sheet 21 times, and
`create_alignment` was given a start without legs 15 times. Half of its calls are the engine teaching it the
schema, and on the probes beyond Tier 1 it never gets to the drawing. The escaped quote in every title block is
the same failure Haiku showed once in `equation-data`: the model types JSON escapes into a text field.

On Tier 1 Gemma's 9 to 11 of 17 sits where Qwen3.5-9B stood on Sep 29 (11 of 17, the shell-bridge rig, so not
a comparison on the board); on Tier 2 and 3 it is where every local model was on Oct 7: nothing.

**Engine under the run: the pins are wrong for 82 of the 99 episodes.** The runner process loaded its code at
20:45, but every probe starts a fresh `roaddraft-mcp`, and that server imports the checkout's working-tree
`src/` (an editable install). At 21:38:44 another session's uncommitted real-sheet work changed
`commands/schemas.py`, `commands/design_schemas.py`, `commands/design_handlers.py` and `design/labels.py` (an
optional `view_rotation` on `place_label` and `annotate_stationing`; committed later as 6bf396e). Every
episode that started after that, from r1's `sheet-set-callouts` at 21:40:40 through all of r2 and r3, was
served that tool list (`sha256:20fe0603…`, the 6bf396e surface) and engine; r1's first 17 probes had the
2697ee5 surface (`sha256:97c51a24…`) the Haiku and Sonnet rows ran on. `run.json` cannot show it: `pins()` is
computed once per process, so all 99 record commit 2697ee5 and tools `97c51a24…`. The parameter is optional
and defaults to the old behaviour, no Gemma episode passed it, and r1 scores the same 9 of 33 as r3, so the
scores are very unlikely to have moved; but the tool schemas the model read differ in those two descriptions
from the other rows'.

## Fable 5.1: 32, 32, 32 of 33 on disk; 29, 29, 31 on the board

The three repeats ran on the Haiku/Sonnet rig, one per 5-hour window, after the weekly Fable window reset at
midnight: r3 04:35 to 05:08 PDT, r1 09:32 to 10:08, r2 14:33 to 15:08. 99 episodes: 92 answered, **7 stopped by
the $3 CLI spend cap, every one of them with a passing sheet on disk**. 1,445 calls (14.6 per episode), 15
faulted: **1.0% invalid**, the lowest of any model here. $136.09 by the CLI's figure, **$1.37 per episode**,
fourteen times Sonnet; one repeat is about 42% of the account's 5-hour window.

| probe | r1 r2 r3 | what it left on disk |
|---|---|---|
| 29 probes | P P P | |
| sheet-set-callouts | B B B | all 15 callouts on paper across the three sheets, each on its edge, the title blocks numbered: a pass on disk all three times, capped at 36 to 39 turns ($3.16 to $3.24) |
| line-data | B B P | passing sheets, capped at 36 and 28 turns ($4.08, $3.85) |
| curve-data | B B P | passing sheets, capped at 53 and 55 turns ($3.90, $4.93) |
| l2-alignment-data | . . . | r1: bubble 2's leader stops 2.74 ft off its curve; r2: bubble 2 has no leader reaching its curve; r3: '585+36.75 BC' overlaps the sheet's '1450' (Sonnet's r3 failed the same way) |

On disk the three repeats agree exactly: everything but the L-2 whole-job probe, 96 of 99. The board reads
89 of 99, 89.9%, second to Sonnet's 96.0%, because it counts a budget stop as a failure whatever the document
shows, and `sheet-set-callouts` capped out in every repeat, which the board calls a hard fail. **The cap, not
the drawing, decides first place:** without it Fable's 97.0% would sit above Sonnet.

The $3 cap was set for Haiku's cost profile on Oct 8; at Fable's prices it binds on the three long probes and
nowhere else (the costliest answered episode was `l2-alignment-data` at $2.72). The decision is whether the
cap is part of the rig (keep $3, and the board stands as generated) or a spend guard (raise it, say
`--max-budget-usd 6`, for the Fable rows, rerun the seven capped episodes with `--force` under the new cap,
and record the reruns here). The 15-minute budget and 120 turns are the capability limits and stay as they
are either way. Recommended: the spend guard. The cap measures the account's price list, not the model.

## Qwen3.5-9B (bf16, vLLM on Runpod): 17, 14, 16 of 33

Robert's go on Oct 13 ("run Qwen 3.5 9B"). The endpoint set up on Oct 9 (`benchmarks/runpod/README.md`:
`Qwen/Qwen3.5-9B` at bf16 on vLLM v0.31.0, context 65,536, prefix caching on, the model card's sampling sent with
every request) on one A40 in Montreal; `--backend openai --budget 30`, 120 turns, renders replaced by a note.
A smoke probe first (`edge-c102`, passed, 367 s including a 5 min 7 s cold start), then the three repeats as three
parallel processes sharing the one worker, 21:29 to 01:45 PDT (190, 235 and 222 minutes of episode time). The
label carries `bf16-vllm` so the row cannot be read as the deleted Q4_K_M LM Studio rows.

| set | r1 | r2 | r3 | Qwen3.5-9B Q4_K_M, local, earlier rigs |
|---|---|---|---|---|
| the 17 (9 find, 8 draft) | 13 | 14 | 13 | 11 of 17 on Sep 29 (shell bridge) |
| Tier 2 (6) | 2 | 0 | 1 | 0 of 6 on Oct 4 |
| Tier 3 batch A (4) | 1 | 0 | 1 | not run |
| Tier 3 batches B and C (6) | 1 | 0 | 1 | 0 of 6 on Oct 7 |
| **all 33** | **17** | **14** | **16** | 14 of 33 on the Oct 9 r1 (deleted) |

Twelve probes pass every time, twelve fail every time, nine split. The twelve that always pass are the nine
find probes less `pc-by-station`, plus `title-blocks`, four of the drafting probes (tangent, PI curve,
bearing-distance, roadway) and nothing above Tier 1 except what the splits give.

| probe | r1 r2 r3 | what a failing repeat left on disk (the first one) |
|---|---|---|
| pc-by-station | . P P | no leader, so nothing points at the PC |
| draft-edges-shoulders | . P . | nothing drawn for the left edge of pavement (3 turns) |
| draft-turn-lane | . . . | the 120 ft taper has no linework on 23 of 26 check points |
| draft-cul-de-sac | . B B | the left edge up to the bulb not drawn; r2 and r3 ran out the 30 minutes |
| draft-building | P B . | r2: nothing drawn in 33 minutes; r3: the footprint wrong |
| sheet-set-callouts | . . . | the title block's sheet number reads `C-101`, not `1` (the same miss Haiku made on Oct 8) |
| station-callouts | P B . | 7 of 15 stations have no leader; r2 filled the context at 55 turns |
| clean-callouts | P . . | the right-edge-of-shoulder leader lands on nothing |
| draft-intersection-corner | B . . | the curb return not drawn; r1 ran out the budget at 21 turns |
| draft-fix-the-drawing, draft-roadway-sheets | . . . / . . P | the 12 ft edge not redrawn; the left edge of pavement 5 ft off |
| line-data | B . . | T-1's lettering at 90° where the line runs at 0°: the azimuth typed as the rotation; r1 filled the context at 72 turns |
| curve-points, curve-data, qa-alignment-data | . . P / . B . / . . . | no `24+05.27 BC` lettering; no bubble numbered 1 |
| stationing | P . . | nothing added to C-102 |
| width-dims, row-data, equation-data | . . . / B . . / P . P | the left shoulder not dimensioned; no L1/C1 tags (context full at 17 turns); the equation not lettered |
| l2-match-lines, l2-alignment-data | . B . / . . . | no match line at 574+50; no tangent data |

**Measures (99 episodes).** 90 answered, 4 stopped by the 30-minute budget, 5 by a full 65k context
(`stop: length`). 1,668 tool calls (16.8 per episode), 112 faulted: **6.7% invalid**, between Haiku and Gemma;
three results cut at the 30,000-character cap. 79.0M input tokens counted (the schema resent every turn, served
from the prefix cache), 900k output of which 766k reasoning: the model thinks about five times as much as it
says. Its commonest faults are a guessed NCS layer (`V-ANNO-TEXT` does not exist, six times: the fixtures sit on
Caltrans levels now), callouts and labels asked to anchor on an alignment the sheet file does not own (eight
times), stationing asked to draw on a sheet (five), and creating an alignment that already exists (four).

**Infrastructure.** Two r3 episodes ended on the client side rather than the model's: `draft-turn-lane` on a
connection reset at 11 minutes and `draft-intersection-corner` on Runpod's 570-second limit for one streamed
turn at 20 minutes. Both were rerun with `--force` after the repeats finished (both answered, both fail on the
drawing; the errored attempts' metadata is in `run-qwen-r3.log`). The endpoint served 1,689 turns with 14
failed on the proxy side across the night. Cost: **$4.22 billed to the endpoint** (GPU $4.19 at $1.22/h on the
A40, disk $0.03), $5.35 off the balance at the time of reading, against the $6 to $10 estimate; nothing bills
once the worker scales to zero.

Against the local Q4_K_M rows this is the same model told the same things with a 65k context it could use:
the Tier 1 score rises from 11 to 13-14 of 17, and Tier 2 and 3 move off zero only on the splits. Not
comparable row to row (precision, engine, probe set all differ); the direction is the point.

## GPT-6-Luna and GPT-6-Astra (medium effort) through Codex: Astra 31, 32, 32 of 33 (96.0%, first); Luna 22, 21, 23 of 33 (66.7%, fifth)

Robert's go on Oct 12 ("run probes through codex GPT-6 Asta Med and GPT-6 Luna"): `gpt-6-astra` at reasoning
effort medium and `gpt-6-luna` at its default, medium, on Robert's ChatGPT Plus account.

**Rig.** A new backend, `python -m roaddraft.runners run --backend codex` (`runners/codex_cli.py`, commits
`1f6a634`, `555bf49`, `442800d`): Codex headless (`codex exec --json --ephemeral --ignore-user-config`), the
copy bundled with the ChatGPT app (`codex-cli 0.162.0-alpha.17.2`, recorded per episode; the npm install, 0.145,
was refused `gpt-6-luna` by the service). The one `roaddraft-mcp` per probe is Codex's only MCP server, its
tools pre-approved; the server's instructions replace Codex's base instructions, the environment, permissions
and collaboration messages are off, the shell, web search, sub-agents and plugins are disabled, and the sandbox
is read-only, so the drawing can change only through the server. What Codex keeps regardless (`apply_patch`,
`view_image`, a clock, the MCP resource listers) was never used. 15 minutes and 120 model turns per probe, as
for the Claude rows. The episodes ran from a worktree pinned at `555bf49`, then `442800d` (the same tool
surface, `sha256:20fe0603`, the view_rotation one Fable ran on, and the same instructions and probe set), so
other sessions' edits on main could not reach them. Unlike Claude Code, Codex shows the model tool results
under its own output limit rather than the runner's 30,000 characters.

**The account set the pace.** ChatGPT Plus stopped the six parallel processes after about three minutes on
Oct 13 (35 episodes, all find probes) and again after three minutes that evening (44 more); a usage reset
Robert bought at 21:36 carried Luna to the end and Astra r1 to 20 of 33 before the limit returned at 21:49.
Run in parallel, Astra drew `429 Too Many Requests` within a second of each start while one process at a time
ran clean, so its repeats run one after another (a scratchpad chain that resumes after each limit). A Plus
window holds roughly 40 find probes or 10-15 drafting and Tier 3 ones. On a limit the runner deletes the probe
it was on and stops (exit 3), so the same command resumes it. On Oct 14 the chain finished Astra r1 and r2 and
ran r3 to 26 of 33 before the limit stopped it at `stationing` at 18:02 ("try again at 10:44 PM"); the
last seven ran from 22:46 to 22:53.

**Two episodes set aside, in `runs/_superseded/`.** Astra r1 `stationing` hit the turn cap after 122 calls in
40 seconds: the backend counted tool calls, and Astra had made 96 `station_to_xy` calls in one response, so
the cap was far tighter than Claude Code's `--max-turns`, which counts responses. `442800d` counts model
turns (read from the event order and timing; it can undercount, never overcount) and keeps Codex's own event
stream as `codex.jsonl`; the episode reruns under it. Luna r3 `draft-fix-the-drawing` was stopped by OpenAI's
input filter ("your prompt was flagged as potentially violating our usage policy") on a drafting task, an
infrastructure stop the board excludes; it reruns so Luna's row can rank.

| set | Luna r1 | r2 | r3 | Astra r1 | r2 | r3 |
|---|---|---|---|---|---|---|
| the 17 (9 find, 8 draft) | 15 | 14 | 17 | 17 | 17 | 17 |
| Tier 2 (6) | 3 | 4 | 2 | 5 | 6 | 6 |
| Tier 3 batch A and batches B and C (10) | 4 | 3 | 4 | 9 | 9 | 9 |
| **all 33** | **22** | **21** | **23** | **31** | **32** | **32** |

Luna: 16 probes pass every time, 6 fail every time (`draft-fix-the-drawing` failed its r3 rerun too), 11 split.
On the board: **66.7% [52.5, 80.8], fifth**, below Haiku and above Qwen, the intervals overlapping on both sides.

| probe | Luna r1 r2 r3 | what a failing repeat left on disk (the first one) |
|---|---|---|
| shoulder-c101 | . . P | the callout's leader lands 32 ft, then 2.9 ft, off the left shoulder |
| draft-edges-shoulders, draft-turn-lane | P . P / P . P | r2: the left edge of pavement 6 ft off; the 24 ft full-width edge not drawn |
| draft-cul-de-sac | . P P | linework runs through the bulb where there should be none |
| sheet-set-callouts | P P . | the title block's sheet number reads `C-101`, not `1` (the miss Haiku and Qwen made) |
| station-callouts | . P P | 5 of 15 stations have no leader |
| clean-callouts | . . . | two leaders cross ('EDGE OF PAVEMENT' and 'SR-100') |
| draft-fix-the-drawing | . . . | the 12 ft edge only partly redrawn (49 of 189 check points bare) |
| draft-roadway-sheets | P P . | the viewport runs outside the sheet's drawing area |
| line-data | . . . | the bearing lettered without the length (`N 90°00'00" E`) |
| curve-data, qa-alignment-data | P . . / . . . | no bubble numbered 1 on the curve; no `24+05.27 BC` |
| stationing | . . P | no tick at 26+00 |
| width-dims, row-data | P P . / . . P | the right shoulder not dimensioned; no L1/C1 tags |
| l2-match-lines, l2-alignment-data | . . . / . . . | the match line stops at ±40 ft, not 40 ft past the edges; the PCC lettered EC |

Astra: 95 of 99 pass, **96.0% [87.9, 100.0], first**: the same rate and the same one never-passed probe as
Sonnet, ahead on the next tie-break, invalid calls (0.4% to 2.0%); the intervals overlap, so the two are not
separated. 31 probes pass every time. `draft-roadway-sheets` r1 lettered none of the 21 stations, and
`l2-alignment-data` failed all three, setting the tangent data level on the sheet where the line runs at 5.03°
(the turned viewport every model has missed); nothing else failed.

**`view_rotation`, read from the traces.** The surface these rows ran on (`sha256:20fe0603`) gives `place_label`
and `annotate_stationing` a `view_rotation`: the twist of the viewport the labels are read through, so they letter
upright on that sheet. Sonnet's and Haiku's surface (`97c51a`) has no such argument, but the difference did not
carry Astra: it never passed `view_rotation` in any of its 1,942 calls, and neither did Fable. Luna passed it 35
times in three episodes, 15 `place_label` calls at −6.457° in r1 `l2-alignment-data` and 0° (no turn) in r2
`curve-points` and r3 `stationing`. It was not the deciding step either way: Luna lettered both turned tangents
in r1 (with it) and in r2 (without it) and still failed on the PCC, the CURVE DATA table and the bubbles, while
Astra's three `l2-alignment-data` failures all missed the two tangents and, in r2 and r3, nothing else.

**Measures, Luna (99 episodes).** 99 answered. 1,149 tool calls (11.6 per episode), 57 faulted: **5.0%
invalid**, between Haiku and Qwen; 74% of faults recovered within three calls. 22 seconds per episode, 0.6 h in
all, as quick as Haiku. 266k input tokens per episode (cache reads included), 1k output. Report
fidelity is the weak point: 20 of its 33 failed episodes' reports said the task was done (60 claims the check
contradicts), though none cited an id that never existed. Astra (99 episodes): 1,942 calls (19.6 per
episode), 8 faulted (**0.4% invalid**, the lowest on the board), 39 s per episode, 1.1 h in all; 438 of 450
items asked done (97%); all 4 of its failed episodes' reports said the task was done. Cost: none recorded, both on the subscription.

## Still to run in this folder

- GPT-6-Astra and GPT-6-Luna: done (Oct 14). They ran with:

        python -m roaddraft.runners run --backend codex --model gpt-6-astra --effort medium \
            --out benchmarks/probe_runs/2026-10-12-k3 --label gpt6-astra-med-r2 --budget 15   # r1, r3 the same; gpt-6-luna as gpt6-luna-rN
- The seven Fable `--force` reruns, if the cap is raised: `sheet-set-callouts` in r1, r2, r3; `line-data` and
  `curve-data` in r1 and r2. About $30 at list price, one 5-hour window.

    python -m roaddraft.runners run --backend claude-code --model claude-haiku-4-5 --claude-bin ~/.local/bin/claude \
        --out benchmarks/probe_runs/2026-10-12-k3 --label haiku-r1 --budget 15 --max-budget-usd 3   # and r2, r3; sonnet-r1..r3 with --model claude-sonnet-5-5; fable-r1..r3 with --model claude-fable-5-1
    python -m roaddraft.runners run --backend openai --model Qwen/Qwen3.5-9B --base-url https://api.runpod.ai/v2/zee0sos76mivwk/openai/v1 \
        --api-key-env RUNPOD_API_KEY --extra-body '{"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}' \
        --out benchmarks/probe_runs/2026-10-12-k3 --label qwen3.5-9b-bf16-vllm-r1 --budget 30   # and r2, r3
    python -m roaddraft.runners run --backend openai --model google/gemma-4-e4b --base-url http://localhost:1234/v1 \
        --lms-context 65536 --out benchmarks/probe_runs/2026-10-12-k3 --label gemma --repeat 3 --budget 30
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-12-k3/runs/haiku-r1          # scores.json beside it
    python -m roaddraft.runners leaderboard                                                        # benchmarks/leaderboard/
