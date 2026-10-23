# Real-sheet D1 tasks

D1 tasks set on real plan sheets instead of the seeded generator's single
synthetic centerline. The sheets are the sample plan sets redrafted into
RoadDraft files under `examples/Exmple Plans/Redraft/` (Caltrans PPM, FHWA
Western and Central Federal Lands, FDOT NexGen). Each sheet file references
its own base files (alignments, corridor, survey) through a viewport at the
published scale and twist, and carries the published border, title block,
notes, legend and callouts.

Eleven task types cover a plan sheet's jobs. `catalog.json` lists every task
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

The first five letter one alignment around everything the published sheet already
shows. `real-attach-reference` and `real-title-block` are one task per sheet; the rest
are one per alignment.

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
   midpoints, and a curve data table or block (Caltrans grid, FDOT and CFL
   stacked lines) that lists one of its radii. Leaders of what is removed go too.
   Everything else on the sheet stays.
4. **Poses.** Each label takes the spec's side and offset unless that lands on
   the sheet's own text, a referenced base's text or a label already placed; then
   the other side of the line, then further off. Station numbers move as a set.
   Side and offset are not graded, so a model may make the same moves.
5. **Table spot.** The clear space nearest the published table it replaces, else
   the lower right, on an occupancy grid of everything the finished sheet shows.
   A sheet with no room starts without a table when the table is not the task.
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

## The eval sets drawn from it

The harness runs two task sets from this catalogue (`src/roaddraft/eval/taskset.py`,
manifests under `benchmarks/tasksets/`):

- **`d1-real`**: 99 held-out tasks, nine of each type. Within a type every agency
  that has the type is drawn once before any is drawn again, then the sheet the set
  has used least, so it holds 66 Caltrans tasks and 11 each of WFL, CFL and FDOT,
  on 42 sheets. Ranked on its own board beside the seeded `d1-test`.
- **`d1-real-dev`**: 22 tasks, two of each type, on three Caltrans sheets that
  `d1-real` never uses. For smoke runs; never reported.

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
- Each sample sheet has its own copy of its base files, so real tasks are
  one sheet each; consecutive sheets do not share one continuous alignment.
- The base alignments' curves store ends a few hundredths of a foot off their own
  circles (L-1's TB1: 0.056 ft). The verifier takes a curve to be its circle, so a
  drawn arc matches it.
- Still seeded only: pavement edges and widths (the real corridors have varying
  widths, curbs and tapers, not one typical section), create-alignment (the rebuilt
  alignments store no PIs to dictate), two-sheet layouts, and layer setup.
