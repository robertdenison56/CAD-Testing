# Tier 2 and Tier 3 batch A, Haiku 4.5: 2026-10-06

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
| draft-fix-the-drawing | pass | the 11 ft piece deleted and redrawn at 12 ft, the shoulder piece relayered back to V-ROAD-SHLD, the callout's leader moved from the shoulder to the pavement edge so its text is now true, nothing else touched | 31 / 2 | 38 | 206 | 52 k |
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
- The Fable half of the proposal's step has not run; the batch-A ceiling is still unmeasured.
- The runner has a shell. Every probe was told to run nothing but `rd`, and the traces hold only `rd` calls, but the
  rule is asked for, not enforced, as it was on Sep 20 and 22.
