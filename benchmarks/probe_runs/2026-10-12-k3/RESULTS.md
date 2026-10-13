# 2026-10-12 — all 33 probes at k = 3 on the one-convention-set engine: Haiku 4.5, Sonnet 5.5 (Gemma 4 E4B and Fable 5.1 to follow)

The probe set changed on 2026-10-12 (commit `2697ee5`: the engine's labelers default to the Plans Preparation
Manual's lettering, the probe fixtures sit on Caltrans named levels, the checks read the Caltrans station digit;
probe set `sha256:2fce3b5c1c75`), so every row on the board had to be rerun. This folder holds the reruns; each
model's repeats go under `runs/<model>-r1..r3`. Haiku 4.5 ran first, Sonnet 5.5 next; Gemma 4 E4B is running
through LM Studio as this is written and Fable 5.1 waits for the account's weekly Fable window to reset.

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

## Still to run in this folder

- **Gemma 4 E4B** (`google/gemma-4-e4b`, Q4_K_M, LM Studio on RobertsPC over LM Link, context 65,536, the
  smallest tool-use model LM Studio lists): `--backend openai --lms-context 65536 --budget 30 --repeat 3`, one
  process, the three repeats one after another, started 20:46 PDT. Its first probes took 1 to 2.5 minutes each.
- **Fable 5.1**: the account's weekly Fable window stood at 81% when the Haiku repeats launched and resets at
  midnight PDT; 99 Fable episodes before that would have hit the cap part way through. Same rig as Haiku and
  Sonnet, `--model claude-fable-5-1`.

    python -m roaddraft.runners run --backend claude-code --model claude-haiku-4-5 --claude-bin ~/.local/bin/claude \
        --out benchmarks/probe_runs/2026-10-12-k3 --label haiku-r1 --budget 15 --max-budget-usd 3   # and r2, r3; sonnet-r1..r3 with --model claude-sonnet-5-5
    python -m roaddraft.runners run --backend openai --model google/gemma-4-e4b --base-url http://localhost:1234/v1 \
        --lms-context 65536 --out benchmarks/probe_runs/2026-10-12-k3 --label gemma --repeat 3 --budget 30
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-12-k3/runs/haiku-r1          # scores.json beside it
    python -m roaddraft.runners leaderboard                                                        # benchmarks/leaderboard/
