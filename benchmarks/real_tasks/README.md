# Real-sheet D1 tasks

D1 tasks set on real plan sheets instead of the seeded generator's single
synthetic centerline. The sheets are the sample plan sets redrafted into
RoadDraft files under `examples/Exmple Plans/Redraft/` (Caltrans PPM, FHWA
Western and Central Federal Lands, FDOT NexGen). Each sheet file references
its own base files (alignments, corridor, survey) through a viewport at the
published scale and twist, and carries the published border, title block,
notes, legend and callouts.

Twelve task types cover a plan sheet's jobs. `catalog.json` lists every task
that validates, and every candidate left out with the reason.

## Task types

| Type | The drafter starts with | Asks for |
|---|---|---|
| `real-stationing` | the sheet file, the alignment's published annotation removed, its bearings, callouts and table drafted to the spec | ticks, station numbers, BC/EC |
| `real-bearings` | the same, its stationing, callouts and table drafted | the bearing and length of each tangent |
| `real-callouts` | the same, its stationing, bearings and table drafted | the curve number bubbles |
| `real-curve-table` | the same, its stationing, bearings and callouts drafted | the CURVE DATA table |
| `real-alignment-data` | the sheet file, the alignment unannotated | all of the above |
| `real-draw-alignment` | the alignment base file, the alignment in its design but not drawn | the centerline |
| `real-attach-reference` | the sheet file as published, its base files beside it but detached | the base files attached at their own coordinates |
| `real-title-block` | the sheet file as published, its title block's project fields empty | the agency border's fields filled |
| `real-sheet-setup` | the base files attached, the alignment annotated in the model to read on the published twist, no sheet | the sheet on the agency border and a viewport at the published scale and twist |
| `real-annotate-sheet` | the sheet set up on its border at the published scale and twist, but blank | the alignment's data, the table, a north arrow pointing north, the title block |
| `real-plan-sheet` | the base files attached and nothing else | the sheet and viewport, then all of the above |
| `real-construction-callouts` | the sheet file as published with a spread of its construction callouts removed (note, leader, arrowhead) | each note back on the sheet as a callout, its leader tip on the station and offset called out |

The first five letter one alignment around everything the published sheet already
shows. `real-attach-reference`, `real-title-block` and `real-construction-callouts`
are one task per sheet; the rest are one per alignment.

### The whole job (2026-11-03)

Two composite types, `tasks.types.REAL_JOB_TYPES`, the `job` question group, kept out of `REAL_TASK_TYPES` so this catalogue, `d1-real` and `d1-real-dev` stay as they are. They have a catalogue of their own, `catalog-jobs.json` (`scripts/real_tasks.py --jobs`), and only `d1-real-hard` draws them.

| Type | The drafter starts with | Asks for |
|---|---|---|
| `real-sheet-job` | the base files attached and nothing else (as `real-plan-sheet`) | the sheet and viewport, the alignment's data, the table, the north arrow, the title block, and the sheet's construction callouts |
| `real-annotate-job` | the sheet set up but blank (as `real-annotate-sheet`) | all of that but the sheet, construction callouts included |

Built like their single-group counterparts, with the construction callouts of `real-construction-callouts` asked for too (the sheet is cleared, so they go with it). After the rest of the sheet is placed, the reference places the notes; a note it cannot place clear of its own labels, table or north arrow leaves the task (the sheet starts blank, so there is no published note to leave in its place), and a job left with fewer than three notes is not built. 43 tasks validate (100 / 0 at both levels) on 16 sheets, 22 alignments: 34 Caltrans, 4 WFL, 3 FDOT, 2 CFL.

## How a lettering task is made (`src/roaddraft/tasks/real.py`)

1. **Design.** The base file's alignment, as rebuilt by the redraft. The sheet
   file does not own it, so labels anchor through the reference, for example
   `AA01:TB1`.
2. **Truth.** `compute_ground_truth` on that alignment at the sheet's own scale,
   viewport and twist: the same code the seeded tasks use.
3. **Strip.** The alignment's own published annotation is removed from the copies
   the task ships: stationing anchored to it in the base, plain-text station
   numbers and ticks at its stations, BC/EC labels, bearings and tangent lengths
   that match its values and stand beside it, curve bubbles at its curve
   midpoints (circles; on the sheet also the rings of vertices the Caltrans sheets
   digitised them as, one per curve, when a leader runs from the ring to the curve,
   since the sheets' note tags are rings too), and its rows of a curve data table
   or block (Caltrans grid, FDOT and CFL stacked lines). A table that tabulates other lines' curves too (L-1 lists
   TB1's and TB2's, L-7 four lines') keeps their rows: the alignment's rows go,
   the rows below close up, and the table stays. A row is the alignment's when its
   R is within 5 % of one of its curves; where the sheet's lines have curves of
   nearly one radius (L-3's ramps, 4,850 to 5,000 ft), each curve takes the row it
   fits best by radius, then by length. Leaders of what is removed go too.
   Everything else on the sheet stays.
4. **Poses.** Each label takes the spec's side and offset unless that lands on
   the sheet's own text, a referenced base's text or a label already placed; then
   the other side of the line, then further off. Station numbers move as a set.
   Side and offset are not graded, so a model may make the same moves.
5. **Table spot.** The clear space nearest the published table it replaces, else
   the lower right, on an occupancy grid of everything the finished sheet shows;
   when the published table stays for the other lines' rows, the clear space
   below it (`curve_table_replaces` is then false). A sheet with no room starts
   without a table when the table is not the task.
6. **Start.** The stripped sheet file with the spec layers and the given phases
   drafted on it.

The other types cut the same files differently (`START_KIND`). Their checks needed
three additions, each read only from a real truth sheet:

- **Title block.** Each agency border has its own fields: Caltrans Dist, County,
  Route, Post miles, Project number and phase, Sheet title, Sheet and Scale; WFL and
  CFL Project and Sheet number; FDOT Road no., County, Financial project ID, Sheet
  no. and the engineer of record. The explicit prompt gives every value and grades it
  exactly; the vague prompt gives two and the rest need only be filled, as on the
  seeded sheets.
- **Twist.** A laid-out sheet must keep the published viewport twist, or the
  labels lettered for it read upside down; a viewport turned otherwise loses the fit
  credit.
- **North arrow.** On a turned sheet it must point to north, so it is inserted turned
  by the twist; one pointing up the paper earns half.

## How a callout task is made (`src/roaddraft/tasks/real_callouts.py`, 2026-10-24)

The redraft pipelines placed every published note with `place_callout` on a layer of
its own (`S-ANNO-CALL`, `S_ANNO_CALLOUT`) and then lettered it as the sheet does, so the
files record no target. The builder reads it back from the geometry:

1. **Leaders.** The strokes on the callout layer are grouped by the ends they share (or
   an end on another stroke). A group's free end nearest a text is the note's end; the
   arrowhead's apex, or the free end farthest from the note, is the tip. Lines of a note
   lettered under its head (same left edge, a line's gap below) belong to it. A leader
   with two arrowheads or no text is left alone.
2. **Targets.** The tip goes through the viewport to the model and onto every referenced
   alignment at identity; the nearest gives the station and offset. A note counts when
   its tip is inside the plan view, within 200 ft of a line, reads as words and is not
   lettered at an angle. Traced centerlines count here too (a note may point at the WFL
   `MAIN 01`), which is why this type is catalogued on sheets the lettering types skip.
3. **Spread.** Up to twelve notes a sheet, spread in station order (an episode has 150
   steps); at least three, or the sheet makes no task. The rest stay on the sheet.
4. **Fit.** The reference places the chosen notes on the stripped sheet; a note whose
   leader runs through the sheet's own text, or that lands on another note, goes back on
   the sheet as given (the published layout's doing, not the drafter's).
5. **Start.** The sheet file with those notes, leaders and arrowheads removed. The brief
   gives each note's text, line, station and offset (to the hundredth and the tenth of a
   foot); the oracle re-places it with `place_callout`, `target_anchor` and the line named
   through the reference, at the box the published note stood in.

The 2026-10-24 catalogue holds 32 callout tasks with 238 notes (Caltrans 14, WFL 13, FDOT
3, CFL 2); 24 more plan sheets carry fewer than three qualifying notes. Every pairing that
reached validation passed.

Graded by the verifier's own check **D1-16** (`verify/checks.py`, `EXTRA_CHECKS`, weight
14, hard fail) beside D1-08. The spec's frozen v1 check list is untouched, so its hash and
every task id stand; D1-16 joins a rubric only through the `notes` group, which only this
type asks for. Credit per note: a text carrying the `callout` record `place_callout` now
writes (kind, what it was aimed at, where the tip landed), reading the note as given
(whitespace and quotes folded), visible on the sheet, its leader tip read from the drawn
lines within 0.05 in of the station and offset. A note typed as text is `unanchored`; a
tip off its point or a note dragged off its leader is `misplaced`; a callout on one of
the points that reads none of the notes is `wrong_value`, a hard fail. The point called
out is seen through the viewport the drafter's sheet is drawn through
(`checks.expected_callout_tip`, d1-verify-v8 of 2026-11-03), so a whole-job sheet
(`real-sheet-job`, where the prompt leaves the viewport's centre to the drafter) is
judged as drawn; under v7 the sample sheet's own viewport was the frame, and a job
centred elsewhere lost every note (Terra's CFL job, 130 ft off, 82.7 instead of 96.2).
On a sheet handed over with its viewport (this type) the two frames are the same.

## The eval sets drawn from it

The harness runs two task sets from this catalogue (`src/roaddraft/eval/taskset.py`,
manifests under `benchmarks/tasksets/`):

- **`d1-real`**: 100 held-out tasks, 25 from each of the four question groups of
  `tasks.types.REAL_GROUPS` (draft linework: `real-draw-alignment`; letter alignment
  data: the five lettering types; produce the sheet: the five sheet types; notes and
  dimensions: `real-construction-callouts`), the way the probe board splits its tiers
  (Robert, 2026-10-24). A group's quota is split evenly over its types (5 each in the
  five-type groups), so every question type weighs the same in the blended score and
  the board shows a column per group beside it. Within a type every agency that has
  the type is drawn once before any is drawn again, then the sheet the set has used
  least. Ranked on its own board beside the seeded `d1-test`. (Until 2026-10-27 it
  was nine of each type: 99 tasks of eleven types from Oct 22, 108 of twelve from
  Oct 24; the 9B's first row ran the 99-task draw.)
- **`d1-real-dev`**: 24 tasks, two of each type, on a few Caltrans sheets that
  `d1-real` never uses. For smoke runs, so it covers every type; never reported.

```bash
.venv/bin/python -m roaddraft.eval run --taskset d1-real-dev --agent oracle --agent null --level explicit --level vague
.venv/bin/python -m roaddraft.eval taskset --check d1-real d1-real-dev   # rebuilds every task; fails on a stale catalogue
```

## Validation

A pairing is kept only when its reference solution verifies 100 and its starting
file 0, at both prompt levels. Rebuild the catalogue whenever the redrafts, the
spec, the generator or the verifier change:

```bash
PYTHONPATH=src .venv/bin/python scripts/real_tasks.py
```

The prompt workbook (`scripts/export_prompts.py`) has a "Real-sheet tasks" sheet
with each task's prompts and links to its start and finished files.

## Engine and verifier changes these tasks needed

- **A callout's record.** `place_callout` now stamps its text with an anchor record
  (`kind` callout, the alignment, station and offset or entity it was aimed at, the
  tip's point) and its leader, shoulder and arrowhead with `callout_leader`, as a label
  carries its anchor; the bus stamps `placed_by`. The verifier credits a construction
  callout only through that record, as it credits labels only through theirs.
- **`view_rotation`** on `place_label` and `annotate_stationing`. Most real
  viewports are twisted (Route 65 L-1 is turned -89.94°), and model-space labels
  were lettered upright in the model, so they printed upside down on the sheet.
  The new optional parameter letters them upright as plotted. It defaults to 0,
  and an untwisted label's anchor record is unchanged.
- **`upside_down`** finding in D1-08: text that reads upside down on the sheet as
  plotted costs legibility like an off-sheet label.
- **Given entities.** Each real truth sheet lists what the start file already
  holds. D1-08 counts no overlap between two given items and no given item off
  the sheet, so the original drafters' overlaps are not charged to the model; an
  overlap between new work and the sheet still counts, and referenced base text
  joins as context. Given lines never earn tick credit, and neither do a curve
  bubble's leader or circle.

## Known gaps

- Some published annotation was redrafted as outlined linework, not text (Route 65
  L-1's "N 01°05'14" W" and "328.15'"), and a few labels were split into fragments
  ("W" apart from its bearing, "PC STA. +70.32" without its hundreds). These stay on
  the start sheet. They are not anchored, so they earn nothing and cost nothing.
- The base alignments are rebuilt from the published linework, so their values
  drift slightly from what the sheet letters (L-1's TB1: BC 642+81.10 against
  642+81.23 published). The truth is the rebuilt design in the base file.
- Station numbers move only as a set, so a sheet where one station number would
  land on existing text is left out rather than hand-placed.
- A kept shared table still numbers the other lines' curves as published (L-1's
  TB2 curve is No. 1 there) while the reference numbers the stripped line's own
  curves from 1, so a sheet can show two curves numbered 1; the digits inside the
  published ring bubbles were lost in the redraft, so no bubble on the start says
  which. The pilot probes renumber (`probes/pilot/redlines.py` on the
  `pilot-astra` branch); the catalogue does not.
- Rows of a shared table that the redraft fitted differently from the published
  values (L-7's curve 44, R 3280' published against 3175' rebuilt) are matched by
  the 5 % radius rule with the length as tie-break; a published row whose curve the
  redraft does not have at all (L-3's curve 30 when IN3 is stripped) stays.
- Each sample sheet has its own copy of its base files, so real tasks are
  one sheet each; consecutive sheets do not share one continuous alignment.
- The base alignments' curves store ends a few hundredths of a foot off their own
  circles (L-1's TB1: 0.056 ft). The verifier takes a curve to be its circle, so a
  drawn arc matches it.
- A callout task hands back at most twelve notes, spread along the lines; the rest of the
  sheet's callouts stay as given, so a crowded sheet is never asked for in full.
- Still seeded only: pavement edges and widths (the real corridors have varying
  widths, curbs and tapers, not one typical section), create-alignment (the rebuilt
  alignments store no PIs to dictate), two-sheet layouts, and layer setup.
