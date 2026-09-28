# Probe rerun, all 17 probes, after the Sep 20 engine fixes: 2026-09-22

This run uses the same rig (`bridge.py`, one persistent `roaddraft-mcp` per probe, `--autosave --trace`) and the same
prompts as 2026-09-19 (T2) and 2026-09-20-T1. T1 keeps its no-calculator rule. Each model tried each probe once (n = 1), and
every score comes from the document left on disk. The engine is the uncommitted tree (660 tests), which includes the three
fixes made after the T1 run: `station_to_xy` accepts the printed end station, `get_design_data` defaults `kind`, and the
[x, y] = [easting, northing] order is stated. The runners were general-purpose subagents, as before. The orchestrator this
time was Opus 5.5, not Fable, so the Fable runners had `model: fable` set explicitly.

| probe | Fable 5.1 | Haiku 4.5 | Haiku on Sep 19/20 |
|---|---|---|---|
| edge-c102 | pass | pass | pass |
| edge-curve-c102 | pass | pass | pass |
| shoulder-c101 | pass | pass | pass |
| centerline-c103 | pass | pass | pass |
| both-edges-c101 | pass | pass | pass |
| title-blocks | pass | **FAIL** scale typed `1" = 50"` | pass |
| pc-by-station | pass | **FAIL** text `24+05`, not `24+05.27` | pass |
| edge-c102-paper | pass | pass | pass |
| sta-offset-c101-paper | pass | pass | pass |
| draft-tangent-ne | pass | pass | pass |
| draft-pi-curve | pass | pass | pass |
| draft-bearing-distance | pass | **FAIL** deflected LEFT, end 1,262 ft out | FAIL (188 ft) |
| draft-edges-shoulders | pass | pass | pass |
| draft-turn-lane | pass | pass | FAIL |
| draft-cul-de-sac | pass | pass | FAIL |
| draft-building | pass | pass | pass |
| draft-roadway | pass | pass | FAIL (644 ft) |
| **total** | **17 / 17** | **14 / 17** | 13 / 17 |

| calls / faults | Fable find | Fable draft | Haiku find | Haiku draft |
|---|---|---|---|---|
| this run | 81 / 1 (1.2 %) | 68 / 0 | 77 / 9 (11.7 %) | 80 / 12 (15.0 %) |
| before | 106 / 3 (2.8 %) | 92 / 8 (8.7 %) | 84 / 11 (13.1 %) | 87 / 16 (18.4 %) |

## Findings

- **Fable made zero faults across all 8 T1 runs** (8 faults before). It hand-computed every bearing and read the result
  back with `get_design_data`. The `get_design_data` `kind` fault and the end-station fault from the T1 run did not
  come back for either model.
- **Haiku T1 went from 4/8 to 7/8.** The roadway, turn-lane and cul-de-sac probes all passed this time. With n = 1 this is
  mostly run-to-run variance, not proof that the fixes worked: none of the three fixes touches the reasoning Haiku got
  wrong before (the 12 ft vs 24 ft lane, the far root). The COGO gap is unchanged. On bearing-distance Haiku turned 35°
  LEFT (it reports "N 27°29'57" E" and still calls the result correct), and it verified nothing.
- **The two new Haiku T2 failures are precision failures, and one is partly caused by the rig.**
  - *title-blocks*: Haiku wrote the scale as `1" = 50"`. The bridge requires single-quoted JSON, so a foot mark `'`
    cannot appear in it without shell escaping. Haiku swapped the character instead of escaping it. A native MCP
    client would not have this problem. Suggest either an exception in the scorer or a `--json-file` / stdin form in
    the bridge.
  - *pc-by-station*: Haiku labelled the PC as `24+05` instead of `24+05.27`, truncating a station a drafter writes to the
    hundredth. This is a legitimate failure.
- **The `place_callout` `position` fault still happens.** Haiku omitted `position` 6 times, which is 6 of its 9 T2
  faults. The Sep 19 description fix stopped it passing the text point as `at`, but it still leaves `position` out. It
  recovered on the next call every time. Its other repeated faults: `set_current_layer` without `name` (4 times, so it
  never read the schema) and a missing `space` (4 times).
- **Haiku still saved under other names in 6 runs** (ELM-AVE.rdraft, turn_lane.rdraft and others). The files landed
  beside each project because the bridge now sets the server's working directory, and autosave kept the scored file.
- **Fable's only fault** came from `xy_to_station` at the far edge of the C-103 viewport, a point past the end of the
  alignment. The answer was correct.

## What this means

T2 is still saturated for Fable. Haiku's T2 failures come from text precision, not from aiming: all 20 leaders landed
0.00 ft from their targets. T1 still separates the models, but only 1 probe out of 8 did so this time. That probe is
the bearing/distance one, which is the COGO gap again. With n = 1 per probe, this run cannot separate the models
reliably. To get a real number, run each probe several times, or add harder probes.
