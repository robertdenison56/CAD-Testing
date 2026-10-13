# Real-sheet D1 tasks

D1 tasks set on real plan sheets instead of the seeded generator's single
synthetic centerline. The sheets are the sample plan sets redrafted into
RoadDraft files under `examples/Exmple Plans/Redraft/` (Caltrans PPM, FHWA
Western and Central Federal Lands, FDOT NexGen). Each sheet file references
its own base files (alignments, corridor, survey) through a viewport at the
published scale and twist, and carries the published border, title block,
notes, legend and callouts.

A task letters **one alignment** of a sheet to the drafting spec, around
everything else the sheet already shows. `catalog.json` lists every task that
validates, and every candidate left out with the reason.

## Task types

| Type | Asks for | Already done on the start sheet |
|---|---|---|
| `real-stationing` | ticks, station numbers, BC/EC | its bearings, curve callouts, curve table (spec style) |
| `real-bearings` | the bearing and length of each tangent | its stationing, callouts, table |
| `real-callouts` | the curve number bubbles | its stationing, bearings, table |
| `real-curve-table` | the CURVE DATA table | its stationing, bearings, callouts |
| `real-alignment-data` | all of the above | none of it |

## How a task is made (`src/roaddraft/tasks/real.py`)

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
