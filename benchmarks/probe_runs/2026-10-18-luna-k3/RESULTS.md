# 2026-10-18 — GPT-6-Luna at k = 3 through Codex, on the clean help text: 23, 20, 17 of 33 (60.6%, fourth)

Robert: "run the test using GPT Luna through codex" (Oct 18 evening). The frontier rows came off the board with the
runs from before the help-text scrub (`fe26ce2`), so this is Luna's row again, on the surface the nine Runpod rows
ran on.

**Rig.** `python -m roaddraft.runners run --backend codex --model gpt-6-luna --effort medium --max-turns 120
--budget 15`, the settings of Luna's Oct 12 row, from the pinned worktree `.claude/worktrees/luna-k3` at
`4cb5d445` (`PYTHONPATH` on its `src`): the engine and tool surface of `2026-10-17-k3` (tools `sha256:60eeeb21`,
instructions `sha256:4dff2849`) plus `roaddraft-mcp --root`, which holds the server's reads and writes to each
episode's folder. The engine's stationing fix (`3daef52`, an `annotate_stationing` fault for a path in another
space) came after and is not in this row, so it compares with the Runpod rows. Codex is the ChatGPT app's copy, now
`codex-cli 0.163.0-alpha.10.2` (0.162 on Oct 12), recorded in every `run.json`; shell, web search and the other
Codex tools off, read-only sandbox, RoadDraft the only MCP server. Three repeats side by side on Robert's ChatGPT
Plus account, 20:59 to 21:12 PDT: 13 minutes, no usage-limit stop (the Oct 12 run needed four 5-hour windows).
The `edge-c102` smoke (passed, 4 turns) is kept in `runs/_smoke/`, outside the row; the 21:04 snapshot commit
`df96b8f3` had it at `runs/gpt6-luna-smoke`, where the board counted it as a fourth attempt.

**Clean.** All 99 episodes answered (no budget, turn or context stops; the longest took 50.9 s, so the 15-minute
budget never bound where the Runpod rows have 30). Every `run.json` pins `4cb5d445` with no dirty files. The 99
Codex event streams hold 1,041 tool calls, all to `roaddraft`, and 111 agent messages; nothing else.

| set | r1 | r2 | r3 | Oct 12 row (old help text) |
|---|---|---|---|---|
| Tier 1 (17) | 15 | 16 | 12 | 46 of 51 |
| Tier 2 (6) | 4 | 2 | 3 | 9 of 18 |
| Tier 3 (10) | 4 | 2 | 2 | 11 of 30 |
| **all 33** | **23** | **20** | **17** | 22, 21, 23 |

On the board: **60.6% [45.5, 75.8], fourth of ten**, below Qwen3.8-27B (64.6%) and above Gemma 4 26B-A4B (49.5%),
the intervals overlapping both; hard-fail 24% (8 of 33 never passed), 4.4% invalid calls. The Oct 12 row read
66.7%; the leak audit (Oct 14) put Luna at about 62% with the probes whose answers the old help text held taken
out, and this row lands there.

**Per-probe marks**, the 19 probes not passed every time (the other 14 passed three of three):

| probe | r1 r2 r3 | probe | r1 r2 r3 |
|---|---|---|---|
| clean-callouts | . . . | l2-alignment-data | . . . |
| curve-data | P . . | l2-match-lines | . . . |
| curve-points | P . P | line-data | . . . |
| draft-building | P P . | qa-alignment-data | . . . |
| draft-cul-de-sac | P P . | row-data | . . . |
| draft-edges-shoulders | . P . | station-callouts | P . . |
| draft-fix-the-drawing | . . . | stationing | . . . |
| draft-pi-curve | P P . | width-dims | P P . |
| draft-roadway | P . P | | |
| draft-roadway-sheets | P . P | | |
| draft-turn-lane | . P . | | |

Against Oct 12: `shoulder-c101` now passes all three (one of three then); `row-data` and `stationing`, one pass each
then, now never pass; `draft-turn-lane`, `draft-edges-shoulders` and `station-callouts` fell from two of three to
one; `draft-pi-curve`, `draft-building`, `draft-roadway` and `curve-points`, three of three then, lost one each.
The never-passed set grew from six to eight; the six from Oct 12
(`clean-callouts`, `draft-fix-the-drawing`, `line-data`, `qa-alignment-data`, `l2-match-lines`,
`l2-alignment-data`) are all still in it.

**Measures (99 episodes).** 1,041 tool calls, 10.5 per episode; 7.8 turns and 21.0 s per episode, 35 minutes of
episode time in all. 25.1M input tokens (21.1M of them cache reads), 94k output, 9k reported as reasoning. No
dollar cost: the Plus subscription carries it.

Score each repeat with `python -m roaddraft.runners score <run dir>/runs/gpt6-luna-rN` (the runner writes no
`scores.json`), and regenerate the board after this folder changes.
