# 2026-10-08 — all 33 probes at k = 3 through `roaddraft.runners`: Haiku 4.5

The research plan's step A-k3: every probe, three times, on every model, through the one native runner, so the
rows compare and n = 1 noise stops deciding the ranking. This folder holds all of it; each model's repeats go
under `runs/<model>-r1..r3`. Haiku 4.5 ran first.

**Rig.** `python -m roaddraft.runners run --backend claude-code --model claude-haiku-4-5` on the standalone CLI
(2.1.295) signed in to claude.ai, so a subscription, no API key. One `roaddraft-mcp` per probe, started by the CLI
from the generated config, with autosave and a trace; the server's instructions as the whole system prompt, no
built-in tools, the probe's task text as the prompt. 15 minutes and a $3 CLI cap per probe, 120 turns. The three
repeats ran as three processes in parallel, 14:29 to 15:10.

## Result: 21, 20 and 17 of 33

| set | r1 | r2 | r3 | earlier Haiku runs, n = 1, through the shell bridge |
|---|---|---|---|---|
| the 17 (9 find, 8 draft) | 16 | 15 | 15 | 14/17 on Sep 22, 13/17 on Sep 19/20 |
| Tier 2 (6) | 3 | 4 | 1 | 5/6 on Oct 6 |
| Tier 3 batch A (4) | 2 | 0 | 1 | 1/4 on Oct 6 |
| Tier 3 batches B and C (6) | 0 | 1 | 0 | first Claude run; the local models 0/24 |
| **all 33** | **21** | **20** | **17** | |

| probe | r1 r2 r3 | what a failing repeat left on disk (the first one) |
|---|---|---|
| the 9 find probes | P P P | |
| draft-tangent-ne, draft-pi-curve, draft-edges-shoulders, draft-cul-de-sac, draft-building, draft-roadway | P P P | |
| draft-bearing-distance | . . . | RAMP-B ends 1339 ft from where it was described: the COGO gap, unchanged |
| draft-turn-lane | P . . | the full-width edge 24 ft right has no linework on any of its 25 check points |
| sheet-set-callouts | P P . | C-101's title block reads `C-101`, not `1` or `1 of 3` |
| station-callouts | . P . | 8 of 15 stations have no leader on them |
| clean-callouts | P P . | two leaders cross |
| draft-intersection-corner | P P . | the 50 ft curb return is not drawn where it belongs (worst point 61.8 ft off) |
| draft-fix-the-drawing | . . . | r1 and r3: the EDGE OF PAVEMENT callout still points at the shoulder; r2: the 12 ft edge only partly redrawn (49 of 189 check points bare) |
| draft-roadway-sheets | . . P | ELM-AVE ends 1210 ft from where it was described |
| line-data | P . P | T-1's line data runs over linework |
| curve-points | . . . | the BC at 24+05.27 sits 8.95 in off the line square to the centerline through its point |
| curve-data | P . . | curve 1's delta is missing from the table |
| stationing | . . . | the tick at 26+00 is not square to the line |
| width-dims | . . . | the left shoulder is not dimensioned at 17+00 |
| row-data | . . . | the tag C1 sits 0.86 in from its right-of-way line, not beside its piece |
| equation-data | . . . | no lettering gives the equation at its point |
| qa-alignment-data | . P . | curve 2's T reads 289.58, which is its length; T is 146.05 |
| l2-match-lines | . . . | MATCH LINE (L-1) not lettered along its line |
| l2-alignment-data | . . . | tangent data lettered at 0° where the line runs at 5.03° |

**What k = 3 shows that n = 1 could not.** 15 probes pass every time and 9 fail every time; the other 9 split.
A single run of this model could have scored anywhere from 15 to 24 on the same prompts. The spread here is
four probes (17 to 21), and r3 alone would have put Haiku's Tier 2 at 1/6 where r2 says 4/6.

**The runner changed, so the earlier rows do not compare.** The Sep and Oct 6 Haiku runs went through the shell
bridge inside a Claude Code agent with its own system prompt; this one gives the model nothing but the server's
instructions and the task. Haiku now spends less on each probe (17.5 calls and 73 s on average; on Oct 6 its
Tier 2 probes took 11 to 43 calls and 76 to 206 s) and gives up sooner on the hard ones:
`draft-fix-the-drawing`, a pass on Oct 6, failed all three times in 8 to 16 calls. Whether that is the harness or
the variance cannot be separated with one bridge run, which is why every leaderboard row now comes from this
runner.

## Measures (all 99 episodes)

| | |
|---|---|
| stops | 99 answered; no budget, turn-limit or CLI-cap stops |
| tool calls | 1,728, of which 111 faulted: 6.4% invalid. `stationing` alone made 50 (33 in r1), `curve-points` 16 |
| wall clock | 41 min for the three repeats in parallel; 2.0 h of episode time |
| cost at list price | $10.94 by the CLI's figure, $9.38 by the runner's estimate (it prices cache writes at the five-minute rate; the CLI writes a one-hour cache). About $0.11 per episode. Billed to the subscription, not per token |

## One result the CLI did not pass on

In `haiku-r3/l2-alignment-data` Haiku called `get_model_state {include_references: true}`; the server returned
748,312 characters. The CLI does not truncate an MCP result past its own token limit: it saved the result to a
file under `~/.claude/projects/` and told the model to read it in spans with Python. This model has no file
tools, so it saw only that error (1,635 characters). The other backends cut every result at `core.RESULT_CAP`, so
a model there sees the first 30,000 characters. It is one call in 1,728, in a probe Haiku failed in every repeat,
but the backends differ here. Before the next model runs, the cap belongs in the server, so every client gets the
same cut result.

    python -m roaddraft.runners run --backend claude-code --model claude-haiku-4-5 \
        --out benchmarks/probe_runs/2026-10-08-k3 --label haiku-r1 --budget 15 --max-budget-usd 3   # and r2, r3
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-08-k3/runs/haiku-r1          # score.txt beside it
