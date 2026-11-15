# Harder-task pilots

*2026-10-19. Status: built and self-tested; no model has run them yet.* *2026-11-03: grown from 33 to 112 pilots (Robert: "expand the hard pilots to a set of at least 100"); see [the expansion](#the-expansion-to-112-2026-11-03).*

On the 33 Track P probes the frontier has run out of room: GPT-6.1-Sol 32/33 (97.0%), GPT-6-Astra and
Sonnet 96%. Sol's one miss was a bearing lettered at 0° on a sheet where its line ran at 5.03° through a
twisted viewport. The probes mostly test whether a model picks the right command and fills its
parameters, because the engine does the geometry: `create_alignment` takes bearings as written,
`place_callout` lands on the entity, `annotate_stationing` letters a whole alignment.

These pilots try tasks where the engine does less of the work: input that is not clean data, layout
decisions with competing constraints, changes that ripple through a sheet, and problems nobody named.
Each is two or three hand-built instances, every one set on the real example sheets
(`examples/Exmple Plans/Redraft` and `Sheets`), so we can see what a frontier model fails before
anyone builds a generator. The ones it fails become benchmark families; the ones it passes are dropped.

## Where they live

- `src/roaddraft/probes/pilot/`: one module per family, plus `common.py`, which copies a redrafted
  sheet's file set into a probe's project folder.
- **Off the board.** `tasks.PROBES`, the probe-set hash and the Track P leaderboard are unchanged. A
  pilot is reached by id (`tasks.get`) or with `runners run --pilot`; its runs go under
  `benchmarks/pilot_runs/`.
- `benchmarks/pilot_references/<id>/`: each scripted solution kept as a finished project: the
  completed `.rdraft` set, journal, PDF, DXF and `reference.json`.
- Tests: `tests/test_pilot_*.py` and `tests/test_mcp_profiles.py` (463 tests, a few minutes).

```bash
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot list
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot selftest
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot reference --out benchmarks/pilot_references
```

`selftest`: every scripted solution passes its check read back from disk, and every untouched start
fails it (112/112 since 2026-11-03). Each family's tests also feed the check at least one plausible wrong answer and
confirm it fails.

## The pilots

Numbers are the brainstorm's. Brainstorm items 7–9 (constraint-fitted design, best-fit an existing
road, contours) were left out.

| # | Pilot | Instances (sheet) | What makes it hard | Graded on |
|---|---|---|---|---|
| 1 | Redraw an alignment from a scanned sheet | `p01-redraw-alignment-ppm045` (Caltrans L-1, TB1), `-fdot915` (FDOT sheet 12, CL1) | Reads bearings, curve data and stations off a raster with no text layer; L-1's tie is a station equation to D13 | Bearings to 2", Δ to 3", R, PC/PT stations to 0.10 ft, position to 0.10 ft every 25 ft, drawn |
| 15 | Plan reading | `p15-plan-reading-ppm046` (Caltrans L-2), `-wflp14` (WFL D.5), `-cflpla` (CFL Davis Dam Rd) | Six reviewer questions per scan; some need arithmetic (an EC off the sheet, an unlettered PT), one a clipped quadrant, one a scale read off the bar | Each answer exact after normalizing format, truth read from the redraft |
| 14 | Open-ended QA review | `p14-qa-review-ppm045a` (clean control), `-ppm045b` (6 errors), `-wfl19` (3 errors) | Unknown count and kinds, visual ones included (north arrow, upside-down text); mark, don't fix; the control punishes false alarms | Each plant hit by a QA-REVIEW leader within 0.5 in; at most 1 false alarm; control needs NO ERRORS FOUND and no marks |
| 2 | Sources that disagree | `p02-sources-wfl19a` (table R wrong), `-wfl19b` (design wrong, in the base file), `-ppm045` (a tangent length wrong) | Deciding which source is wrong from the rest of the evidence, and fixing it where it lives | The wrong source corrected; every other entity in every file unchanged; a finding recorded |
| 11 | Redlines with knock-on edits | `p11-radius-ppm160` (PD-1, R = 1500' hold PI), `-station-ppm045` (L-1, restation TB1 +25 ft) | The engine does not regenerate labels; every downstream station, BC/EC, table cell and two callouts that cite TB1 stations must follow | E1 verifier on truth from the revised design; nothing stale or doubled; revision recorded; redline removed; nothing unrelated changed |
| 12 | A small full plan set | `p12-route65-d13` (Route 65 L-1 to L-3 joined) | Five sheets that must agree: index, numbering, match lines, coverage, and a quantity takeoff | Index = sheets present; 1 to 5 of 5; match lines agree and sit at their station; every 10 ft shown; SY and LF within 1% |
| 4 | Crowded annotation | `p04-crowded-ppm045` (L-1, 3 lines, twist -89.94°), `-ppm050` (L-7 interchange, 5 lines, twist -131.21°) | Lettering every line at once on a crowded, turned sheet without collisions | E1 per line, plus legibility across all lines (any overlap of new work fails), labels along their lines and reading upright |
| 17 | Twisted variants | `p17-twist-ppm160` (PD-1 turned 180°), `-fdot916` (FDOT re-cut at -113°) | The failure mode of Sol's one miss: text orientation through a twist | E1 verifier at the new twist; every label along its line, reading from the bottom or right |
| 5 | The model picks the sheet breaks | `p05-breaks-fdot904` (SR 50, 472+00–490+00), `-cfl` (CFL CL1, 10+00–25+00) | Choosing sheet count, breaks and twists; match lines square and lettered alike | Coverage, left-to-right on every sheet, match lines within 1 ft and 1°, at most fewest + 1 sheets |
| 3 | Survey traps | `p03-misclosure-ppm045` (deed off by 1:6,534), `p03-grid-ground-wfl20` (CSF 0.999649), `p03-intl-feet-ppm047` (international feet and metres at state-plane size) | A traverse to balance by the compass rule; a scale factor to apply the right way; a 2 ppm unit difference worth 13 ft | Corners within 0.02 ft, points within 0.05 ft, closure numbers recorded |
| 10 | Typical section from a description | `p10-typical-cfl01` (CFL A6), `-wfl07` (WFL C.1) | Slopes, crown, layers and catch points against a given ground line, then a viewport at 1" = 10' | Grade breaks and catch points within 0.05 ft, layer bottoms within 0.03 ft, dims and slope labels present, the viewport |
| 6 | Plan and profile on one sheet | `p06-plan-profile-cflpnp` (CFL Plan 1), `-wfl14` (WFL D.5) | No profile-view command: the grid and grade line built by hand at 10:1, stations lined up with the plan | Grade line within 0.10 ft every 10 ft, PVI/L/K/high-low labels, plan-profile alignment; D.5 has no high point, and lettering one fails |
| 13 | Striping with no-passing zones | `p13-striping-wfl15` (D.6, 55 mph), `-wfl16` (D.7, 50 mph) | Passing sight distance from the profile per MUTCD, per direction | Zone ends within 25 ft, 10/30 dashes, edge lines, nothing in the wrong zone |
| 18 | Redline understanding | `p18-redline-pdf-ppm045` (Caltrans L-1, 6 marks), `-wfl19` (WFL D.10, 5), `-cflpla` (CFL Davis Dam Road, 5), `-fdot915` (FDOT sheet 12, 6) | The brief is a marked-up PDF and nothing else: handwriting on a render of the sheet, read through `view_attachment`; a key says red = revise, green = delete, blue = comment only; each mark sits on one of several look-alike texts | One item per mark: the revised text reads the new wording at its spot, the deleted one is gone, the moved one sits where the arrow points (0.5 in), the added note lies within 1 in of the tip, the clouded entities are byte-for-byte as they were, the struck field reads the new value; nothing else changed and none of the handwriting lettered |
| 16 | Basic tools | the 33 probes on `--profile basic` | The model computes coordinates itself | The probes' own checks |

### 16: the basic profile

`roaddraft-mcp --profile basic` (`src/roaddraft/mcp/profiles.py`) hides 30 commands that work out
geometry for the caller: offsets, fillets, trims, the traverse, station and viewport conversions,
`key_points` and `snap`, the labelers and `draw_alignment`. It also removes the engine-aimed
parameters from `place_callout` and `find_entities` and the bearing-and-distance route from
`create_alignment`, which keeps its PI-coordinate route because a design alignment is the only thing
the six drafting probes' checks can read. It serves its own instructions.

All 33 probes stay passable on basic: each reference solution's document, with every anchor the engine
stamped removed, still passes its check. A run on basic records `"profile": "basic"` in `run.json`,
and the leaderboard skips such episodes, so they can never become a board row.

```bash
python -m roaddraft.runners run --profile basic --backend codex --model MODEL \
    --out benchmarks/pilot_runs/<date>-basic --label <label>
```

## In the eval harness: the `hard-pilots` set (2026-10-22)

Robert, 2026-10-22: "the harder tasks should make it into the eval set as well." All 33 pilots are
the eval task set `hard-pilots` (`benchmarks/tasksets/hard-pilots.json`), ranked on its own board
beside `d1-test` and `d1-real`. They stay pilots too: the `--pilot` route below is unchanged.
How a run is held to the set (2026-10-27, Robert): by its task ids, each of which carries the hash of
its task text, so adding a family does not unrank the rows run before it, while a changed or removed
text shows as an id the set no longer has; its verifier version is the pilot checks' source hash
(`probe_tasks.check_version`, re-scored with `report --reverify`); and a row ranks only when the run
covers every task of the current set, a run on part of the set being published as **partial** and
listed on the board, not ranked (the first local row, Qwen3.5-9B on the 24 text-only pilots, is one).

- **How an episode runs** (`src/roaddraft/eval/probe_tasks.py`): the pilot's start project is
  built in the episode folder, the model gets the pilot's task text as the probe runner sends it,
  the server's instructions as its system prompt, and the MCP server's own tools served in-process
  (autosave, `open_document`, `view_attachment` for the nine pilots that come with a page image), with paths
  shown and resolved relative to the project folder and file access held to the episode folder.
- **Grading** is the pilot's own check, read back from disk as `runners score` does: 100 on a
  pass, 0 on a fail. The rubric column is the share of the check's items the document has. An
  episode with no engine call fails and is credited no items.
- **Re-grading.** The files an episode changed are kept under `<run>/projects/<episode>/`, and
  `report --reverify` grades them again under the current checks.
- **Budgets.** Track P's, unless the run sets its own: 600 steps, 12 faults in a row, 200,000
  output tokens, 30 minutes.
- **`run_check`** (self-correct mode) answers pass or fail and how many items are done, never the
  check's words, which name expected values.
- **The oracle** is each pilot's scripted solution recorded as tool calls. A second session the
  solution opens on a base file is recorded as `open_document` of that file. Oracle 100 and null 0
  on all 33 through the loop.
- **Images.** The five scanned-sheet pilots and the four redline pilots hand the model their page through
  `view_attachment`, and every provider of the harness passes it on: the Anthropic provider inside the tool
  result, the OpenAI-compatible provider (Runpod, LM Studio) as an `image_url` data URL in a user message after
  the tool messages. What they need is a model that takes images; LM Studio lists which of the local files do
  (`lms ls --json`, `vision`), and `benchmarks/lmstudio/lms_campaign.py vision NAME` sends one lettered image
  through that route to see that it reads it. A text-only model gets the page's JSON and no picture.

```bash
.venv/bin/python -m roaddraft.eval run --taskset hard-pilots --agent oracle --agent null --steps 5000
.venv/bin/python -m roaddraft.eval run --taskset hard-pilots --model MODEL [--samples 3]
```

**`pilot-dev`** (2026-11-13, training plan §8 and decision 7) is the pilots' validation split,
built apart: 18 instances of p17, p04, p05 and p11 on the eight sample sheets with an alignment
that no pilot, real-sheet set or dev set uses and whose design none of them carries, registered in `src/roaddraft/probes/pilot_dev.py`
(outside this package, so the 112 and their hashes do not move; the module docstring says what
each sheet could and could not carry). For choosing a checkpoint only: never trained on, not on the
board. It runs the same way, `--taskset pilot-dev`, and
`python -m roaddraft.probes.pilot_dev selftest` checks every instance's scripted solution and
naive answers.

## What the first model run found (2026-10-23)

GPT-6-Astra (Codex, medium) ran six pilots before the ChatGPT Plus usage limit stopped the run;
Robert cancelled the rest until the harness defects it exposed were fixed. The two WFL sources
pilots passed. The three QA-review fails were all the harness's: Astra found every planted error
(6 of 6 on L-1, 3 of 3 on D.10) and lost on marks that were right.

- **Labels laid out again through no twist.** The pilot gap-fix branch's `follow_design` re-posed
  a stationing set after a design change with `view_rotation` 0 when the labels (lettered before
  the anchor recorded it) carried none, so L-1's TB1 numbers, on a line running 93.96° in the
  model under a -89.94° twist, turned round: upside down on the paper, nine marks on the clean
  control. `label_updates._view_rotation` now reads the twist off the label's pose.
- **The redraft's leftovers**, repaired at staging by `probes/pilot/repairs.py` for every pilot
  on the sheet (`common.stage`), the example files themselves unchanged: stroke lettering under
  real text (PD-1's notes and title printed twice) and the notes' second lines set over their
  first; "Orchard Creek" in seven pieces, one 0.5 in tall; TB1's bearing and length digitised as
  strokes, stale against the design (L-1); two "See Section X for details" placeholders, a leader
  landing drawn twice and the 153+00 station number under the plan/profile divider (D.10).
- **What stripping a line left** (`layout._strip`): the published BC callout of L-7's F3 that
  survives only as strokes. (Curve bubbles digitised as rings of vertices, which the strip did not
  see, were the other leftover until 2026-10-31, when the strip fix took them with their digit and
  leader; `layout._strip_rings` then found nothing to do and went.)
- **The L-1 redline start** (`redlines._restore_tb2`): the real task's strip keeps TB2's row of
  the CURVE DATA table that held both lines' curves, reading No. 1 as published, while the
  reference's TB1 bubble and table say 1 too; the start numbers TB2's row and its empty ring 2.
  (Until 2026-10-31 the strip took the whole table, and the start placed TB2's table and number
  back and deleted TB1's ring.) The E1 real-task starts of every sheet whose table tabulates
  several lines keep the other lines' rows the same way since that strip fix.

- **No way back from a base file** (2026-10-26 rerun, p11-radius-ppm160). Astra opened
  AA01 with `open_document` to revise the curve, then could not reopen PD-1: nothing named the
  sheet's file, and it guessed 38 names. `get_document_state` now names the open file
  (`document`), and `open_document` with a path that is no document lists the project's
  documents, the one handed to the model marked.

- **The server ran another engine** (2026-10-27, the 2:48 AM window). The resume script set
  `PYTHONPATH=src`, relative; the Codex CLI starts `roaddraft-mcp` in the episode's `project/`
  folder, where that names nothing, so the server imported the editable install -- the main
  checkout's engine -- while the runner traced and pinned this branch. Twelve episodes ran that
  way (kept under `void-main-engine/`, rerun with `--force`). The codex backend now hands the
  server an absolute `PYTHONPATH`, `roaddraft-mcp --where` says which package a server would
  serve from, and `runners run` asks it before the first episode and refuses to start on a
  mismatch (`runners.core.check_engine`).

- **A working route abandoned** (2026-10-26, p04-crowded-ppm050): the first failure that is
  the model's own. Astra ticked D13 the anchored way (`annotate_stationing` in model space with
  the sheet's `view_rotation`), deleted the nineteen entities, and hand-drew ticks as sheet lines
  for all five lines over 3,110 calls; D1-02 credits no unanchored tick. The refusal it met on
  the sheet-space attempt ("alignment-mode stationing draws in model space; use place_label for
  sheet labels") points at a command with no tick kind; a hint naming the model-space route with
  `view_rotation` would serve better. Not changed during the run (it would move the tool digest).
  *Changed 2026-11-03: issue 10 below.*

Left as the sample has it: blank title-block fields, the match line with no sheet number, FLH's
leaders without arrowheads, a plan with no scale note (D.10). Astra's marks on these count against
the one false alarm allowed, which is the family's whole difficulty so far.

## Running the pilots on a model (not done; waits on Robert's go)

```bash
python -m roaddraft.runners run --pilot --backend codex --model gpt-6.1-sol --effort medium \
    --out benchmarks/pilot_runs/<date>-sol --label sol-pilot
```

Pilots 1 and 15 hand the model a scan through `view_attachment` (served only to probes that ask for
it with `--attachments`). On this Track P runner the scan reaches the model on the codex and claude-code
backends always, and on the anthropic backend only with `--vision`; the runner's openai-compatible backend
(LM Studio, Runpod) never passes images, so it cannot run pilots 1 and 15. The eval harness's provider of
the same name does pass them (above), so on `hard-pilots` the local models run every pilot.

`python -m roaddraft.runners score benchmarks/pilot_runs/<run>/runs/<label>` scores a pilot run as it
does a probe run.

## Caveats, by pilot

- **1:**
  - The truth is the lettered design held at the tie, not the redraft's fitted alignment, which
    differs slightly (R 3243 against the lettered 3280'). A test confirms it stays within 0.3 ft of
    the redraft wherever the sheet shows it.
  - Small traced strokes near the stripped line were removed by a size-and-distance heuristic.
- **15:**
  - The CFL bearing question depends on a quadrant letter that the plan edge clips; it is a
    deliberate trap.
  - The scale question needs the scale bar measured in pixels plus the stated paper size.
  - The grader reads the first number in an answer.
- **14 and 2:**
  - The sheets are normalized before planting (fitted-curve kinks removed, lettering re-made from the
    design), so they are not the published sheets letter for letter.
  - On L-1 the construction callouts are excluded only by the prompt; some of their leaders miss the
    station they state.
  - The WFL north-arrow plant is defined in the redraft's frame.
  - wfl19b's error is easy to see; the test is the fix route (the base file, then a redraw).
- **11:**
  - E1 credits only anchored lettering, and the prompt says so.
  - The Caltrans revision-block keys are not discoverable through `fill_title_block`, so the revision
    check accepts a note anywhere.
  - The radius redline is on PD-1, because L-1's base keeps traced glyphs of TB1's published bearing
    that no edit can fix.
- **12:**
  - The joined Route 65 base and its V-ROAD-EP edges are constructed for the pilot.
  - The HMA area works out to 80 × 3,200 / 9 without measuring; the fence takeoff still needs
    clipping to the station range.
- **4 and 17:**
  - Pass or fail on perfection: one overlap fails the probe.
  - On PD-1 the labelers' default poses with the right twist pass, so that instance tests the twist
    alone. On FDOT-916 the published twist happens to letter correctly too, so only one of the two
    twist mistakes is caught there.
- **5:** title blocks, north arrows and sheet names are not checked. On the CFL stretch three
  north-up sheets pass, because the line heads NNE.
- **3:**
  - The grid-ground georeference is constructed: only YRB3 is tied to a drawn feature.
  - California defines state plane in US survey feet, so the international-feet setting is contrived,
    though the trap is real.
  - `traverse` with `close=true` reports the misclosure directly; the balance is the real test.
- **10:** the sources are NO SCALE, so some numbers are invented (the fill and back slopes, the
  profile-grade elevations, the ground lines). Slope labels must be written V:H.
- **18 (redline understanding, 2026-10-26):**
  - Robert, 2026-10-26: "some of the tasks should be prompted by editing a pdf with redlines/markups and
    having the LLM address these based only on that." The page is `markups/<sheet>-redlines.pdf`,
    with the same page as a PNG beside it for `view_attachment`, drawn by `redline_pdf.draw_markups`
    on a 200 dpi render of the sheet in a handwriting face (Bradley Hand, falling back to
    Chalkboard or Comic Sans; the check never needs the font). A key strip under the sheet gives
    the colour convention.
  - The sheet file the model opens is the staged redraft, untouched: no layer, entity or text
    carries the instruction, and the task text names no edit.
  - The marks sit on texts that have look-alikes elsewhere on the sheet (two FENCE (TYPE CL-6),
    two REMOVE FENCE, two See Section X for details, four TYPE F / E curb callouts, three
    sidewalk callouts): the mark's place decides which one.
  - The title block marks are found by rendering the sheet with the field blanked and taking the
    pixels that differ; the model fills the field with `fill_title_block`.
  - Tolerances: a revised or deleted text is judged within 0.6 in of its old spot, a moved one
    within 0.5 in of where the arrow put it (the whole group for the FDOT BEGIN PROJECT block), an
    added note by its box within 1 in of the tip. A new leader line within 1.2 in of an added or
    moved note is allowed; any other new entity but text fails.
  - Lettering the checker's own words (DELETE, MOVE, OK PER SURVEY) onto the sheet fails.
  - Needs a model that takes images, like pilots 1 and 15 (the harness passes the page to any provider).
- **6 and 13:**
  - No redraft carries a design profile; each was entered from the published PVIs. The WFL profile is
    pieced together from sheets D.5 to D.12.
  - A referenced file's profile cannot be read, so these starts own their alignment and profile
    instead of referencing them.
  - The WFL base files still hold the published profile drawing as linework.
  - Both striping instances sit on the same crest, one direction each.

## Engine and harness issues the pilots turned up

1. A referenced file's profile is invisible: `get_design_data` reads only the host's profiles, and
   `create_profile` refuses a referenced alignment.
2. `modify_alignment` does not regenerate anchored labels; it warns, or says nothing when the labels
   anchor through a reference.
3. `fill_title_block` lists only the standard keys, not an agency border's revision-block keys.
4. `render_model` crashes at very low dpi (30) with a matplotlib font-size error.
5. `reference.write` loads the baseline lazily from the folder the solve edits, so a solve that
   changes a base file changes what the baseline shows. Scoring a run is unaffected, since its start
   is built fresh. The pilots that edit bases grade against a fresh build.
6. Reference journals record only the opened document's commands, not edits saved to a base file.
7. Some published lettering was digitized as linework (glyph outlines) in the redraft base files, so
   stripping a line's annotation can leave traced text behind.
8. On the anthropic backend, a text-only run replaces a `view_attachment` image with a note saying
   "the text above carries the file path", which is not true for an attachment.
9. Two defects of the real-task strip (`tasks.real.strip_alignment`) that the first model run on
   the pilots showed (2026-10-23) are fixed in the catalogue itself: a CURVE DATA table that
   tabulates several lines' curves (L-1 lists TB2's and TB1's) now loses only the stripped line's
   rows and stays, closed up, with the reference's table placed below it; and curve bubbles
   digitised as rings of vertices (S-ANNO-TAG polylines) go with their digit and leader like
   circles. The `pilot-astra` branch worked around both at staging (`layout._strip_rings`,
   `redlines._restore_tb2`); once it takes this fix, `_strip_rings` finds nothing to do and can
   go, and `_restore_tb2` should keep only its renumbering (TB2's kept row still reads No. 1, as
   published, while TB1's anchored bubble and table say 1 too) and no longer place a second
   table or delete TB1's ring, which the strip now does. *Done 2026-10-31 with the merge of the
   three engine branches into main (Robert: "merge all engine branches"): `_strip_rings` removed,
   `_restore_tb2` keeps the renumbering alone; the catalogue was rebuilt and `d1-real` redrawn.*
10. `annotate_stationing` refused a sheet as `space` with "use place_label for sheet labels", and
   `place_label` has no tick kind: Astra (p04, 2026-10-26) and Terra (p04 and p17, 2026-11-03,
   0 of 2 each) followed the hint and hand-drew ticks on the sheet with `draw_line` +
   `station_to_xy`, which D1-02 does not credit. *Fixed 2026-11-03 under Robert's rule that
   stationing is always drawn in the model file, never on a sheet (the sheet-space mode built that
   day was dropped): the refusal stays, and its message and hint, the tool's description, its
   served example and the neutral system prompt now say that stationing is drawn in model space
   with the alignment's own stations (`space: "model"` with the alignment's name,
   `'BASE:ALIGN-1'` for a referenced one) and shows on every sheet through its viewport, scale
   and twist included; the annotation scale sizes it and `view_rotation` letters it upright on a
   twisted sheet. The tool surface moves 0334fd4aaade -> 9db020d9af1e; every board row ran on the
   old one.*

## The first full pass (GPT-6-Astra, medium, 2026-10-26 to 27)

All 29 pilots answered, in six ChatGPT Plus windows, on the branch engine (987e2c21; the twelve episodes one window ran on main's engine were voided and rerun). Run folder `benchmarks/pilot_runs/2026-10-26-astra/runs/astra-pilot`. **26 of 29 passed.**

The three failures:

- **p04-crowded-ppm050** (layout, crowded). The one hard failure: Astra had anchored D13 ticks in model space, deleted them, and hand-drew unanchored ticks on the sheet after 3,110 calls; nine ticks get no credit. The engine's "use place_label for sheet labels" hint sent it the wrong way (place_label has no tick kind).
- **p14-qa-review-wfl19** (QA). Marked two leftovers of the sample sheet (a leader without an arrowhead, a station label over limit linework) where one false alarm is allowed. Whether sample-sheet leftovers count is open.
- **p15-plan-reading-wflp14** (plan reading). Read one station off the scan as 119+45.98 for 119+46.48; an earlier (voided) attempt read it right, so this is scan-reading variance.

Families where every pilot passed: redraw alignment, sources, survey (grid/ground, international feet, misclosure), sheet breaks, plan-profile, typical sections, redline pick-up, plan set, striping, twist. Faults seen on passes were recoverable: the annotate_stationing sheet-space hint (p04, p06, p17), a create_alignment leg with no distance (p01), measure with too many points (p03).

## The expansion to 112 (2026-11-03)

Robert, 2026-11-03, after the Track D review found the frontier at 100 on `d1-test` and `d1-real` and
`hard-pilots` the only set with headroom, but too small to rank inside ±5: "expand the hard pilots to a
set of at least 100". 79 instances were added to twelve of the fourteen families, every one on a real
sample sheet, most of them on sheets the family had not used, across all four agencies. The 33 earlier
pilots keep their prompts and ids (byte-identical text; their checks grade them as before). Every pilot
passes `selftest` (112/112), every family's tests feed each new instance at least one naive answer and
see it fail, and every reference builds. The set's generator is `probe-b34493be3004`, 112 tasks, 23 with
a page. The pilot checks' source hash moved with the modules, so earlier rows are held to the old
checks until rerun; the 33-pilot rows on the board are published runs and keep their place (a re-report
would list them as partial, 33 of 112).

| # | Family | Added | The new instances | What the new ones add |
|---|---|---:|---|---|
| 4 | Crowded annotation | 11 | `p04-crowded-ppm051` (L-38, 3 lines, untwisted), `-ppm052` (L-39, 2 side by side), `-ppm155` (Route 65 PD-2), `-ppm156` (PD-3, 3), `-ppm157` (PD-11 interchange, 4), `-ppm158` (PD-32, 4), `-ppm160`, `-ppm161` (Route 78 PD-1/PD-2, 3 each), `-ppm230` (E-18, 3), `-fdot915` (FDOT sheet 12, 2), `-ppm047` (L-3, IN4 among published lettering) | The catalogue's other multi-line sheets where the labelers' default poses fail D1-08 (each note names the overlaps); most also read upside down without the twist |
| 17 | Twisted variants | 13 | `p17-twist-ppm209`, `-ppm161`, `-ppm111`, `-ppm156`, `-ppm158`, `-ppm155` (a 175° loop), `-ppm230` (a 244° loop), `-ppm046`, `-fdot915`, `-fdot923`, `-wfl04` (1" = 40', 3 curves), `-wfl21` (D.12 half a turn), `-cflpla` | Twists chosen by scanning every label's plotted angle: lettering without the twist reads from the wrong side on all thirteen, and with the published twist on all but FDOT sheet 12 |
| 5 | The model picks the sheet breaks | 6 | `p05-breaks-fdot918` (CL2, reverse curves), `-fdot904cl2` (4 sheets), `-fdot904cl4`, `-fdot904cl9` (1" = 40'), `-ppm048` (Route 65 D13 at 1" = 40' on the Caltrans 22 x 34 border), `-cflswppp` (1" = 40') | Strict (`spare: 0`): only the fewest sheets pass, three or four on five of the six; north-up fails all but the CFL stretch, the level cut all but Route 65's |
| 11 | Redlines with knock-on edits | 10 | `p11-radius-ppm048` (L-4, IN4 R = 250'), `-radius-ppm230` (E-18, D R = 350'), `-radius-wfl07` (WFL F.7, curve 1 R = 600'), `-radius-ppm158` (PD-32, SB10 R = 4000'), `-pi-ppm161` (PD-2, ENRA's PI 30 ft ahead on its back tangent), `-pi-ppm154` (PD-1 Route 65, R1's PI 30 ft back), `-station-fdot916` (FDOT sheet 1, CL1 -41 ft), `-station-ppm046` (L-2, D13 +38 ft), `-station-ppm050` (L-7, F3 -53 ft), `-station-ppm111` (U-1, IND1 +62 ft) | A new revision kind, `pi`; tangents a change opens at a line's end (a new bearing, a BC or EC off BEGIN or END); the next curve pushed; a tie restationed by the line's new length; structure callouts that cite stations without the line's name; ties whose other line must not move; a location table and a general note citing stations |
| 14 | Open-ended QA review | 6 | `p14-qa-review-fdot916a` (FDOT sheet 1, clean control, north pointing down the paper), `-fdot916b` (6 plants), `-ppm048a` (L-4, clean control), `-ppm048b` (6), `-wfl19b` (D.10, 5 others than `-wfl19`'s), `-cflpla` (CFL Davis Dam Rd, 6, two of them in a plan with no design in the files) | Visual plants (a north arrow turned, a missing tick, upside-down numbers), a table cell, a plant found only from the sheet's own data; the new checks compare model space too |
| 2 | Sources that disagree | 5 | `p02-sources-ppm048a` (L-4 table T), `-ppm048b` (IN4's R wrong in the base file), `-cflpla` (the PT lettering wrong against both the curve data and the design), `-fdot916` (the PC lettered wrong), `-ppm045b` (D13's bearing wrong in the base file) | The fix may live in a table cell or a base file, and the obvious "fit" (bend the design, change L) fails |
| 18 | Redline understanding | 6 | `p18-redline-pdf-ppm051` (L-38, 6 marks), `-ppm049` (L-5, 6), `-fdot916` (FDOT sheet 1, 6), `-fdot923` (FDOT sheet 102, 6), `-wflp04` (WFL F.4, 7), `-cfld1` (CFL D1, 6) | Look-alikes a table row apart, one callout of four or six, a blue comment cloud on every page, a struck title-block field on five |
| 13 | Striping | 4 | `p13-striping-wfl17` (D.8, 65 mph), `-wfl19` (D.10, 60 mph, a sag then a climb), `-wfl20` (D.11, 55 mph, both directions), `-cflpnp` (CFL Plan 1, 55 mph, a summit that restricts one direction) | Zones caused by a crest whose PVC is off the sheet, a sag that restricts nothing, both directions on one sheet |
| 6 | Plan and profile | 3 | `p06-plan-profile-wfl18` (D.9, a low point with no PVI on the sheet), `-wfl21` (D.12 at 1" = 10' vertical), `-fdot915` (FDOT sheet 12, a grade break with no curve, the low point just off the sheet) | Grade drawn PVI to PVI fails; lettering a high or low point that is not on the sheet fails |
| 10 | Typical section | 3 | `p10-typical-fdot9132` (FDOT 913-2, four-lane divided, 1" = 20'), `-wfl04` (WFL JEFF, a sidehill whose slopes come from height tables), `-wfl05` (WFL ADA, 6 % superelevation with widening) | Profile grade off the centerline, slopes that depend on the catch they decide, rotation about the centerline with the high shoulder breaking over |
| 3 | Survey traps | 4 | `p03-misclosure-ppm049` (10 courses, 1:4,840), `-misclosure-fdot915` (a tangent curve on the R/W, 1:4,259), `p03-grid-ground-cflpnp` (a ground drawing with grid data: the factor divided out about CP-1), `p03-intl-feet-wfl15` (an international-feet drawing with US-foot and metre data) | A curve course kept on its balanced arc (a new item, 0.05 ft at mid-curve); the factor applied the other way |
| 1 | Redraw from a scan | 3 | `p01-redraw-alignment-ppm050` (L-7, the F6 loop), `-cflpnp` (CFL Plan 1, CL1), `-wfl20` (WFL D.11, MAIN 01) | Two-curve lines; a loop whose table R (55 m rounded) must come from L/Δ; a tangent lettered against the stationing; a last bearing lettered nowhere; ties at a staked PI and at an equation that falls on a curve |
| 15 | Plan reading | 5 | `p15-plan-reading-fdot916`, `-ppm052` (L-39), `-ppm049` (L-5), `-wflp16` (WFL D.7), `-wflp21` (WFL D.12) | Mostly worked out: off-sheet BC, PI and PT, a bearing ahead, grade elevations, coordinates carried back from End Project, an arc along an offset, the scale of an 11 x 17 print of a 22 x 34 sheet or off the profile grid; a trap each |

p12 (the plan set) keeps its one instance.

### Caveats of the new instances

- **4 and 17:** on L-3 the curve-only lines (D13, IN3) cannot be built as a lettering task and keep their published lettering. PD-3 and PD-11 take 20 s and 80 s to build. The labeler's bearing slide is held to the tangent's middle (`BEARING_SLIDE = (0.5,)`) because of the verifier issue below; the four earlier solves come out identical. Five Caltrans sheets appear in both p04 (every line at the published twist) and p17 (one line re-cut); no sheet repeats within a family.
- **5:** no WFL alignment is long enough (the longest is 838 ft), so the Federal Lands border is covered by the CFL stretch alone. `-ppm048` covers the same Route 65 line as p12.
- **11:** rebuilding an element-built line in PI form moves bearings, the next curve's Δ and the end station by seconds and hundredths; the truth is built from the design the model saved. E-18's "D" has an angle point that `key_points` does not list (`angle_points` holds it). WFL F.7 has no room for a curve table, so it is graded on D1-02 to D1-05, and the FLH border has no revision block, so the revision is a note. FDOT records it in `rev_date_N` / `rev_desc_N`. Bare station pluses (`+46 BEGIN MBGR`) name no line, so the new instances let them be re-lettered without asking for it.
- **14 and 2:** the new sheets are normalized before planting (FDOT sheet 1's PC lettered from the design, its structure and pipe tags numbered as published, pieced lettering joined; L-4's curve 36 R lettered 328.08', IND1's design run out to the 4833.49' its bearing letters, IN4 given 25 ft of back tangent; CFL PLA's lower curve rebuilt from its curve data). On L-4, "+96.28" and "+59.6" belong to lines the base file does not carry. `p02-sources-ppm048b` allows any change to IN4-anchored entities, which a redraw re-places.
- **18:** a replacement much longer than its original would move its centre past the 0.6 in limit, so new wordings stay about the same length. CFL D1 has no title-block mark.
- **13:** the profile extensions are constructed, as the earlier 104+00 one was (MAIN 01 carried at +0.97 % to 172+00; CFL back to 0+00 at +0.50 % and on to 30+00 at -0.50 %), and the prompt says so. No sample profile has a summit that restricts both directions, so there is no overlapping-zones instance.
- **6:** the FDOT leaving grade (+0.30 %) is worked out from the lettered L and K, the next sheet not being in the samples. No second high point could be used: CFL's 22+00 crest sits on CL1's reverse curves, where the plan-to-profile line-up check cannot pass.
- **10:** ground lines and some numbers are invented, as before; the JEFF slope tables stand in for the published "Varies (1:10 to 1:2)"; FDOT's cross slopes may be written as bare decimals.
- **3:** the PPM-049 fence courses, the FDOT deed's off-R/W courses, the CFL datum note, factor and control, and the Montana re-georeference are constructed; the FDOT R/W curve uses the redraft's R 878.86'.
- **1:** the later redraws strip only strokes within 3 ft of the line and on trace layers (CFL and WFL draw their plans in short segments, which L-1's 13-ft rule would take by the thousand). F6's truth runs up to 0.32 ft from the redraft's F6, whose stations lag the lettered ones by about 0.2 ft. The CFL and D.11 ties are local-datum points fitted to the redraft (worst 0.16 and 0.14 ft).
- **15:** answers are graded against truth computed from the redraft's lettering and design, and some deliberately differ from lettering elsewhere when the question asks for the worked value (D.7's bearing ahead, 25" against the next sheet's 24"; L-39's tangent from its end stations, 453.28 against the lettered 453.29').

### Found on the way, not changed (Robert's call)

1. **The verifier marks a bearing slid along its tangent as misplaced** (`verify/match.py`: `_as_tangent_bearing` reads a bearing anchored inside a tangent as `T-n`, and `_expected_pose` expects it at the tangent's middle), while the p04 and p17 prompts tell the model to re-place a label "along its tangent" to clear something. A model that slides a bearing to clear a callout loses D1-07 on every D1 set. Fixing it is a verifier bump (every run re-verified).
2. **p04's two earlier prompts list too few whole stations:** `-ppm045` says "640, 645" where the truth also letters 650 whole, `-ppm050` says "705, 710" where it also has 715. Fixing the text changes their ids. The new instances derive the list from the truth (`_whole()`, tested).
3. **The earlier p14 and p02 checks never compared model space:** `qa.changed_outside` read the key `"model_entities"`, but a document keeps model space under `"model"`, so a model that fixes the TB1 bearing in AA01 instead of marking it still passes `p14-qa-review-ppm045b` (a test records it), and `p02-sources-wfl19b`'s "stationing unchanged" item checks nothing. Left as it was so past grades do not move; the new instances compare model space. Fixing the earlier six would only make them stricter (their solutions still pass).
4. **`p11-station-ppm045`'s sheet has five bare pluses** (`+31 END MBGR`, `+93.5 BEGIN MBGR`, ...): if they are TB1's, a model that correctly restations them fails "nothing unrelated changed".
5. **Engine issue 2 above may be stale:** `modify_alignment` with `redraw` now re-places labels anchored to the line and regenerates its stationing.
