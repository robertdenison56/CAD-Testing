# 2026-10-18 — GPT-6.1-Sol at k = 3 through Codex, on the clean help text: 32, 32, 32 of 33 (97.0%, first)

Robert: "run 6.1 sol next" (Oct 18, after the Luna rerun in `2026-10-18-luna-k3`), then "resume" (Oct 19) once
the ChatGPT Plus usage limit had reset.

**Rig.** As the Luna folder: `python -m roaddraft.runners run --backend codex --model gpt-6.1-sol --effort medium
--max-turns 120 --budget 15`, from the pinned worktree `.claude/worktrees/luna-k3` at `4cb5d445` (the engine and
tool surface of `2026-10-17-k3`, tools `sha256:60eeeb21`, instructions `sha256:4dff2849`, plus `roaddraft-mcp
--root`), Codex `0.163.0-alpha.10.2` from the ChatGPT app with RoadDraft its only MCP server. `gpt-6.1-sol` is the
id in Codex's model list, which gives low as Sol's default effort; it ran at medium, the setting of the GPT-6-Astra
and GPT-6-Luna rows. The repeats ran one after another (Astra drew 429s run side by side on Oct 13); the
`edge-c102` smoke ran as r1's episode (passed, 4 turns), so the row has no stray label. The Plus limit stopped the
run at 21:56 PDT on Oct 18 after 53 episodes (r1 whole, r2 at 20); the runner dropped the episode the limit cut off
(r2 `draft-intersection-corner`, 0 turns), and the same command resumed at 14:04 on Oct 19 and finished at 14:27.

**Clean.** All 99 episodes answered (no budget, turn or context stops; the longest took 199.8 s). Every `run.json`
pins `4cb5d445` with no dirty files and the clean tool and instruction hashes. The 99 Codex event streams hold
1,953 tool calls, all to `roaddraft`, and 101 agent messages; nothing else.

| set | r1 | r2 | r3 |
|---|---|---|---|
| Tier 1 (17) | 17 | 17 | 17 |
| Tier 2 (6) | 6 | 6 | 6 |
| Tier 3 (10) | 9 | 9 | 9 |
| **all 33** | **32** | **32** | **32** |

On the board: **97.0% [90.9, 100.0], first of eleven**, and the first row whose interval clears the next one's
(Gemma 4 31B, 74.7% [59.6, 87.9]); hard-fail 3% (1 of 33 never passed), 0.3% invalid calls (6 of 1,953). For
scale, GPT-6-Astra read 31, 32, 32 (96.0%) on Oct 12 on the old help text, whose answers the scrub removed.

**The one miss is `l2-alignment-data`, all three times**, the probe no row on the board has passed. Each repeat
lettered the turned sheet's alignment data and fell short on the same tangent, 576+16.93 to 578+47.69:

- r1: `N 78°30'50" E 230.76'` lettered at 0.00° on the sheet, where the line runs at 5.03° (the sheet's viewport is
  turned; the lettering has to follow the line as the sheet shows it).
- r2: the same lettering 1.37 in from the line; the check takes within 0.6 in as beside it.
- r3: no lettering gives the bearing and distance together; the nearest is the distance alone, `230.76'`.

`l2-match-lines`, the other L-2 probe, passed all three: both match lines square to SR70 on the turned sheet at
574+50 and 589+50, lettered MATCH LINE (L-1) and (L-3).

**Measures (99 episodes).** 1,953 tool calls, 19.7 per episode; 5.5 turns and 28.0 s per episode, 46 minutes of
episode time in all: Sol batches its calls (twice Luna's calls per episode in fewer turns). 21.0M input tokens
(15.8M of them cache reads), 97k output, 12k reported as reasoning. No dollar cost: the Plus subscription carries
it; Luna's 100 episodes (with its smoke) and Sol's first 53 shared the Oct 18 evening window before the limit.

Score each repeat with `python -m roaddraft.runners score <run dir>/runs/gpt61-sol-med-rN`. The board files were
not regenerated with this folder: another session has the generator's effort column uncommitted on main, and
regenerates after it lands.
