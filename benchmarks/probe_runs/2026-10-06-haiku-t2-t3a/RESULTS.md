# Tier 2 and Tier 3 batch A, Haiku 4.5 (2026-10-06) and Fable 5.1 (2026-10-07)

**Haiku 4.5 6 of 10, Fable 5.1 10 of 10.** Fable first scored 9 of 10: `draft-fix-the-drawing` failed its correct fix
because the check did not count a callout's arrowhead as part of the callout. The check was fixed on 2026-10-07 and
both runs rescored from disk (Haiku unchanged; Qwen's 2026-10-04 Tier-2 run unchanged at 0 of 6). The Haiku half
follows; the Fable half is [at the end](#fable-51-2026-10-07).

The six Tier-2 probes (`python -m roaddraft.probes list --tag tier2`) had one data point, Qwen3.5-9B at 0 of 6
(`2026-10-04-lmstudio-tier2`), so their ceiling was unmeasured; the ten Tier-3 probes (built 2026-10-05, `97a0f86`)
had never been run by any model. `docs/Probes_Tier3_Proposal.md` says to run batch A (`line-data`, `curve-points`,
`curve-data`, `stationing`) on Fable and Haiku before building batch C. This is the Haiku half: the six Tier-2 probes
and batch A, ten probes, one attempt each (n = 1), Haiku 4.5 through the `rd` shell bridge, scored from the
documents left on disk. Engine at `5d4ab4a` (787 tests).

**6 of 10: Tier 2 5 of 6, batch A 1 of 4.** Tier 2 is nearly a ceiling for Haiku: the one failure is the mirrored
curb-return centre, the same trap Qwen fell into. Batch A discriminates the way the proposal hoped: three of the four
fail on Caltrans lettering conventions (above the line, square to the line, below the line) after the data itself was
read correctly every time.

| probe | Haiku 4.5 | what the document on disk shows | calls / faults | shell turns | s | tokens |
|---|---|---|---|---|---|---|
| sheet-set-callouts | pass | 15 callouts on paper across 3 sheets, each on its edge, the centerline named, title blocks numbered 1 to 3 | 38 / 4 | 48 | 168 | 52 k |
| station-callouts | pass | all 15 stations 11+00 to 25+00 called out on C-101, each leader on its station, each text reading it | 43 / 1 | 37 | 162 | 45 k |
| clean-callouts | pass | 3 callouts on C-102 on their lines, text clear of all linework by 0.05 in, leaders clear of each other, all inside the drawing area | 11 / 1 | 16 | 76 | 31 k |
| draft-intersection-corner | **FAIL** | the arc is centred at [4982, 4994], inside the intersection, the mirror of the right centre [5082, 5094]; 19 of 19 check points on the true return have no linework within 0.5 ft (worst 61.8 ft); both curb lines were cut back toward the wrong centre | 12 / 3 | 17 | 144 | 38 k |
| draft-fix-the-drawing | pass | the 11 ft piece deleted and redrawn at 12 ft, the shoulder piece relayered back to V-ROAD-SHLD, the callout's leader moved from the shoulder to the pavement edge so its text is now true, nothing else touched; its arrowhead `PL-001` stayed on the shoulder, 8 ft from the new tip, which the check does not test | 31 / 2 | 38 | 206 | 52 k |
| draft-roadway-sheets | pass | ELM-AVE drafted by hand-computed PIs, edges and shoulders offset, C-101 shows all of it through a 1"=100' viewport, title block filled | 16 / 2 | 28 | 165 | 41 k |
| line-data | **FAIL** | the three bearings and lengths are all right (T-1 1405.27', T-2 1240.36', T-3 1353.95', not the PI-to-PI distances), but each is a `place_callout` with a leader, horizontal, and the first checked (T-1 on C-101) sits below the line; line data goes above it, parallel, no leader | 24 / 4 | 29 | 118 | 43 k |
| curve-points | **FAIL** | all four stations right to the hundredth and lettered BC/EC, each a callout anchored to its point; every text runs at 0.00° where square to the line is 90.00°. Haiku's report says it rotated them 90° by moving the text below the point; the document has no rotation on any of them | 32 / 2 | 50 | 234 | 59 k |
| curve-data | pass | each sheet's CURVE DATA table lists exactly the curves it shows, numbered along SR-100 with the design's R, Δ, T and L; every curve has its numbered bubble (a defined block) with a leader to the arc | 32 / 4 | 43 | 187 | 56 k |
| stationing | **FAIL** | every 100 ft station on C-102 has a 7 ft tick, and the lettering alternates whole numbers at 500 ft with single digits between (6 7 8 9 30 1 2 ...), but it all sits above the line; 26+00 has no number under it. To get there Haiku copied the referenced alignment into the sheet file's own design (`create_alignment` from `get_design_data`) and stationed the whole 47-station copy | 112 / 50 | 29 | 240 | 55 k |
| **total** | **6 / 10** | | **351 / 73** | 335 | | 472 k |

Calls and faults are from `trace.jsonl` as the server saw them. Shell turns are the runner's Bash calls (several `rd`
calls can share one); seconds and tokens are the harness's per-runner figures. The ten ran in parallel; the pass took
4 minutes of wall clock.

## Findings

- **Tier 2 is close to a ceiling for Haiku, 5 of 6 against Qwen's 0 of 6.** The three paper probes passed clean:
  the far side of the sheet set, the fifteen-item loop and the text-over-linework check, which no earlier probe had
  measured and which Haiku handled by reading the `place_callout` warning and moving the text. The `draft-roadway-sheets`
  bearing-and-distance description came out right under the no-calculator rule (the Sep 22 Haiku run turned 35° the
  wrong way on `draft-bearing-distance`), so the COGO gap did not show this time; n = 1.
- **The curb return is the same failure as Qwen's: the mirrored centre.** Haiku reasoned "50 ft inward from each curb"
  toward the intersection centre and got [4982, 4994] instead of [5082, 5094], then trimmed both curbs toward it. The
  probe's note predicted exactly this trap. With the arc 100 ft from where it belongs the check finds nothing within
  0.5 ft of any of its 19 points.
- **Batch A discriminates, and on the thing it was built to measure.** In all four probes the data was right: the
  tangent lengths rather than the PI-to-PI distances, the four curve-point stations to the hundredth, R/Δ/T/L per
  sheet with the numbering kept across sheets, the 500 ft / single-digit lettering rhythm. What failed is where the
  text goes and which way it reads. Haiku reached for `place_callout` for everything (line data with a leader, curve
  points with a leader) and never set a rotation; the engine's `annotate_stationing` default put the digits above the
  line. These are lettering conventions a drafter knows and the prompt states; they were read and not followed.
- **`curve-data` is the one batch-A pass, and the one that needed the most engine features:** three `place_table`
  calls, a `define_block` for each numbered bubble, `insert_block`, and a `place_callout` leader per bubble. Haiku
  worked out the block format from the schema after three faults and placed C-102's table with both curves and
  C-103's with curve 2 still numbered 2.
- **The stationing run copied the design.** `annotate_stationing` refused `DESIGN:SR-100` (an attached reference),
  so Haiku rebuilt SR-100 in the sheet file's own design from `get_design_data` and stationed that. The sheet now
  owns a second alignment whose geometry duplicates the reference; the probe check does not look at the design
  fingerprint, but the eval-plan verifier would (§3.5). The lettering then took 94 `modify_entity` calls, 47 of which
  were the same fault (`'changes' is a required property`) made once per label before the correct call: it never
  learned the shape of the call it was repeating.
- **One report claims work the document does not hold.** The `curve-points` report says the labels were rotated to
  read bottom to top by placing them below their points; all four are at 0°. The other nine reports match their
  documents. Scoring from disk, not from the report, is what catches this (the gpt-oss finding of 2026-09-24).
- **Faults are first-call schema misses, as on Sep 22.** 73 faults in 351 calls (20.8 %); 26 in 239 (10.9 %) without
  the stationing loop. Nearly all are a required property missing on a tool's first use (`position`, `content`,
  `fields`, `path`, `name`, `space`, `changes`, `id`, `block_name`), recovered on the next call. Haiku reads the
  schema only after the engine tells it to.
- **Stray saves, as before.** `line-data` saved `sheet.rdraft`, `stationing` saved `SR-100-Stationing.rdraft`, and
  `sheet-set-callouts` saved to `project/SR-100.sheets.rdoc.json` relative to the project folder, which made a
  nested `project/project/`. All three landed beside the project because the bridge sets the server's working
  directory; autosave kept the scored files. None were moved.

## How the pass was run

The rig is the 2026-09-22 Claude rig (`bridge.py`, one persistent `roaddraft-mcp` per probe over stdio,
`--autosave --trace`) with the scorer and `make_deliverables.py` from the Tier-2 rig, plus four changes:

- `bridge.py`: `rd call TOOL -` reads the JSON arguments from stdin. The Sep 22 writeup asked for this after Haiku
  wrote `1" = 50"` because the single-quoted-JSON form cannot hold a foot mark; every text with `'` or `"` in this
  batch (bearings, lengths, the title-block scale) went through the stdin form without trouble.
- `setup_runs.py LABEL SELECTOR...` takes tags or probe ids, and writes `prompt.txt` per probe: the exact text the
  runner was handed, the LM Studio runner's RULES / T1_REPORT / T2_REPORT with the `rd` bridge in place of native
  tools. Draft probes carry the no-calculator line; every probe is told the bridge is its entire tool surface.
- The runners are `.claude/agents/probe-runner.md` (tools `Bash`, `Read`) with `model: haiku`, not general-purpose
  subagents, per the token-cost note of 2026-09-21. The orchestrator was Fable 5.1 in a fresh session. Each runner's
  final report is kept as `report.txt`.
- `make_deliverables.py` expands "C-101 through C-103" to all three sheets; the Tier-2 copy read it as two.

Scores: `python score_runs.py haiku`. Plots: `python make_deliverables.py haiku`, which prints each probe's document
and its scripted reference to `runs/haiku/deliverables/` with the reference as a finished RoadDraft project beside
each PDF, and `OVERVIEW.png` for the grid.

## Caveats

- n = 1 per probe. The Sep 22 rerun moved Haiku's T1 score by three probes with no change to the reasoning, so a
  single pass says which traps a model falls into, not how often.
- The Fable half ran on 2026-10-07; see below.
- The runner has a shell. Every probe was told to run nothing but `rd`, and the traces hold only `rd` calls, but the
  rule is asked for, not enforced, as it was on Sep 20 and 22.

## Fable 5.1, 2026-10-07

The same ten probes, prompts byte-identical to Haiku's (`prompt.txt` diffed per probe), same rig and the same lean
`probe-runner` agent with `model: fable`, ten runners in parallel from a fresh orchestrator session. Engine at
`0adb6f9` plus the uncommitted Oct 6 work (`--trace` carries results, probe families); the checker changes since
`5d4ab4a` are refactors, and Haiku's documents rescore 6 of 10 on today's code. Scores: `python score_runs.py fable`;
plots and references: `runs/fable/deliverables/`.

**10 of 10: Tier 2 6 of 6, batch A 4 of 4.** First scored 9 of 10; the one failure was a checker defect, not a
drafting error, fixed and rescored the same night (first finding). Fable passed the two probes that had beaten every earlier model: the curb return (Qwen and Haiku both
took the mirrored centre) and batch A's lettering conventions (Haiku 1 of 4).

| probe | Fable 5.1 | what the document on disk shows | calls / faults | shell turns | s | tokens |
|---|---|---|---|---|---|---|
| sheet-set-callouts | pass | 15 callouts on paper across 3 sheets, each aimed at its referenced edge, left side above the road and right side below; title blocks `1`..`3` with `total_sheets` 3 | 37 / 0 | 19 | 188 | 68 k |
| station-callouts | pass | 15 callouts 11+00 to 25+00 on C-101, each aimed with `target_anchor` on `DESIGN:SR-100`; 10+00 left out because it sits on the viewport edge and the task's list starts at 11+00 | 43 / 0 | 15 | 135 | 50 k |
| clean-callouts | pass | 3 callouts on C-102, text clear of all linework, leaders apart, the shoulder callout aimed at the outermost line so its leader crosses nothing | 14 / 0 | 15 | 138 | 48 k |
| draft-intersection-corner | pass | the arc centred at [5082, 5094], tangent at [5082, 5044] and [5032, 5094], both curbs trimmed to it and their anchor stations moved to match (18+82, 27+94) | 16 / 1 | 21 | 147 | 37 k |
| draft-fix-the-drawing | pass | all three mistakes fixed: the 11 ft piece deleted and redrawn at 12 ft by `draw_offset`, the shoulder relayered, the callout re-placed by `place_callout` on the pavement edge with all four old pieces deleted, arrowhead included (failed before the check fix) | 23 / 0 | 12 | 225 | 55 k |
| draft-roadway-sheets | pass | ELM-AVE from hand trig under the no-calculator rule (8-place sines; total 2080.16 ft against 2080.15 by hand), 11 ft lanes and 5 ft shoulders, stationing at 1"=100', C-101 shows all of it | 15 / 0 | 19 | 165 | 48 k |
| line-data | pass | `place_text`, no leader: bearing and length parallel to each tangent (T-2 at 18.43°) in the band between the centerline and the left edge | 23 / 0 | 29 | 200 | 61 k |
| curve-points | pass | `place_text` rotated square to the line (90° and 108.43°), reading bottom to top, `24+05.27 BC` form, 16 ft left of the point | 30 / 0 | 34 | 310 | 68 k |
| curve-data | pass | `place_curve_table` refused the referenced alignment, so three `place_table`s from `get_design_data`, numbered bubbles built from `place_callout` + `draw_circle`, leaders trimmed to the circles | 47 / 1 | 35 | 239 | 67 k |
| stationing | pass | 16 ticks drawn as lines between the ±3.5 ft points `station_to_xy` gave on the sheet, lettered below the line (`6 7 8 9 30 1 ...`) at 0.08 in to fit above the pavement edge; no design copied | 98 / 2 | 20 | 305 | 82 k |
| **total** | **10 / 10** | | **346 / 4** | 219 | | 583 k |

The ten ran in parallel; the pass took about 5 minutes of wall clock (the slowest runner 310 s; Haiku: 4 min).

### Findings

- **`draft-fix-the-drawing` failed a correct fix, and passes a drawing that leaves an arrowhead behind.** `planted()`
  finds the mislabelled callout through `callouts()`, whose `ids` are the text, leader and landing (`LN-017`,
  `LN-018`, `TX-001`) but not the arrowhead polyline `PL-001`. `_nothing_else_changed` therefore requires `PL-001` to
  stay where it was, on the shoulder at [1702.63, 980.00]. Fable deleted the whole old callout and placed a new one,
  arrowhead `PL-002` at the new tip [1702.63, 988.00]: failed. Haiku moved the leader's tip to 988 and left `PL-001` on
  the shoulder, 8 ft from its own leader: passed. The reference solver (`_solve_fix`) deletes the same three ids, so
  the tracked reference in `benchmarks/probe_references/draft-fix-the-drawing` carries the same stray arrowhead.
  **Fixed 2026-10-07 (`5e143ea`):** `tier2.callouts()` now counts a closed polyline with a vertex on the tip as the callout's
  arrowhead, so it is part of the planted callout (`ids` 3 -> 4), `_solve_fix` deletes it, and the regenerated
  reference has no stray arrowhead (its journal's one change: `PL-001` joins the delete). New test
  `test_replacing_the_callout_takes_its_arrowhead_with_it`. Rescored: Fable passes, Haiku still passes. **Still
  open (Robert's call):** a test that the fixed callout's arrowhead sits at its tip. It would fail Haiku's drawing,
  and the existing test `test_the_callout_may_be_re_aimed_...` deliberately accepts re-aiming by the leader's tip alone.
- **Batch A, 4 of 4, on exactly the conventions Haiku missed.** Fable read `place_label`'s refusal for a referenced
  alignment and chose plain `place_text` with the paper point and heading from `station_to_xy(sheet=...)`, so no
  viewport trig was done by hand. It set rotations itself (parallel for line data, square for curve points) and kept
  station lettering below the line. Where Haiku copied SR-100 into the sheet file to unlock `annotate_stationing`,
  Fable drew the 16 ticks and numbers by hand on the sheet and copied nothing. The sheet files keep no design anchor
  for any of this text, which the eval-plan verifier may want (§3.5); the probe checks judge as plotted.
- **The curb return is right first time.** Corner [5032, 5044], centre 50 ft outward along both faces, tangent points
  as feet of the perpendiculars, checked against the existing returns' angle conventions before drawing.
- **4 faults in 346 calls (1.2 %), against Haiku's 73 in 351 (20.8 %).** Fable read `describe` for the tools it was
  about to use, so no first-call schema misses. Three of the four faults are `measure {from: ID}` (two runners; the
  description says `from` takes an entity id, but a single entity needs `entity`, a wording fix worth making). The
  fourth is `place_curve_table` refusing the referenced alignment, the same refusal Haiku met.
- **Reports match the documents.** No report claims work the scorer could not find. `station-callouts` volunteered a
  slip of its own (text 0.5 in left of where it meant to put it, left in place).
- **Rule edges, not breaches of the drawing.** Eight runners opened their render PNGs with the `Read` tool to look at
  their work; the bridge strips images, and `Read` is in the agent's tool list. `curve-data` put a shell `echo` between
  `rd` calls. No file outside `rd` was written: no stray saves this time (Haiku left three).

### Token cost and plan usage

The session was set up to measure this first, after the Sep 20 T1 run hit the 5-hour limit.

- **Runners: about $16.60 at list price** (Fable $10 / $50 per M, cache writes counted at the 1 h rate): 558 k
  cache-write, 3.0 M cache-read, about 48 k output, $1.03 to $2.24 per probe. Each runner opened at 7.8 k tokens of
  context (the lean agent), against about 59 k for the Sep 22 general-purpose Fable runners, which cost about $1.70
  each on easier probes.
- **Plan meter:** the 5-hour window went from 26 % at launch to 52 % at the end; four other sessions were active
  throughout and accounted for part of that. Weekly Fable went from 52 % to 58 %. Measured from the transcripts, 1 %
  of the 5-hour window was roughly $0.90 to $1.10 of list-price usage that evening.
- A spend alarm (a monitor on the runner transcripts) was armed at $15 / $25 / $35 / $45 and $6 per runner; it fired
  once, at $15.78.
