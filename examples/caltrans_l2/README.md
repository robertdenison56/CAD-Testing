# Caltrans sheet L-2, rebuilt

A recreation of a real plan sheet — **03-3H5404, sheet 6 of 179, "LAYOUT",
Route 70 PM 46.0/47.0 (Bear Creek Bridge replacement)** — as a two-file
RoadDraft plan set.

```bash
python examples/caltrans_l2/build_all.py
```

## The two files

A plan set keeps the design in one document and the sheets in another that
references it, and that is the split here:

| | `SR70-Bear-Creek.model.rdraft` | `SR70-Bear-Creek.sheets.rdraft` |
|---|---|---|
| alignments | `SR70` (4 curves, 569+00 – 593+00) | **none** — reads `DESIGN:SR70` |
| model entities | ~3,000 | **0** |
| sheets | none | `L-2`, ANSI D, Caltrans border |
| holds | roadway linework, stationing, design labels, existing ground | viewport, title block, notes, callouts, tables, symbols |

The sheet file attaches the model as reference `DESIGN`, **clipped to the
match lines**, so it shows 574+50 → 589+50 of a road that runs past both ends —
the way a sheet windows a project.

## What is design data and what was digitised

**Rebuilt from the design data the sheet itself states** — the CURVE DATA
table, the BC/EC stations, the two tangent bearings:

* the `SR70` alignment. Radii are derived as `R = L / Δ`, because the table
  rounds R to whole feet while the stations are given to 0.01 ft; deriving R is
  what makes the rebuilt alignment reproduce every station the plan prints:

  | curve | R | Δ | T | L | BC | EC |
  |---|---|---|---|---|---|---|
  | 2 | 1957' | 16°47'27" | 288.83' | 573.51' | 570+43.42 | 576+16.93 |
  | 3 | 2117' | 11°50'53" | 219.70' | 437.83' | 578+47.69 | 582+85.52 |
  | 4 | 1953' | 8°44'56" | 149.39' | 298.20' | 585+36.75 | 588+34.95 |
  | 5 | 862' | 21°17'31" | 162.04' | 320.33' | 588+34.95 (PCC) | 591+55.28 |

* centerline, 12 ft pavement edges and 20 ft shoulder edges, drawn *from* the
  alignment (`draw_alignment`, `draw_offset`);
* stationing, the BC/EC/PCC callouts, and the `230.76' N 78°30'50" E` /
  `251.23' N 66°39'57" E` tangent labels — every one of them anchored, so the
  numbers are read out of the design model rather than typed;
* the fourteen station-and-offset callouts on the sheet, whose leaders are
  aimed at what `station_to_xy` puts at that station and offset.

**Digitised from the published PDF's vector content** (`extract_existing.py`)
because no design data for it exists anywhere: the existing contours and their
elevation labels, the cut/fill catch line, the right of way, the UPRR, and the
guard railing / MGS symbology. It lands in the model file on survey layers.

## Coordinates

The plan publishes no coordinates, so the alignment sits on a local project
datum with station 569+00 at (10000, 5000). The sheet-to-model transform in
`sr70_geometry.py` was fitted to the published sheet (residual < 0.002 in over
its full 34 in width), so the recreated sheet frames the same ground at the
same 1" = 50' and the same 6.457° view twist — north is 6.457° clockwise of
sheet-up, which is exactly where the plan's own north arrow points.

## Files

| | |
|---|---|
| `sr70_geometry.py` | the design data read off the sheet, and the sheet↔model transform |
| `sheet_content.py` | what sheet L-2 says and where it says it |
| `extract_existing.py` | digitises the existing ground out of the published PDF |
| `build_model.py` | builds the design model file |
| `build_sheet.py` | builds the plan sheet file over it |
| `build_all.py` | all of the above, then PNG / PDF / DXF |

## Not reproduced

The Caltrans logo mark and the curved lettering around the engineer's seal
(the border template letters both as plain text), the signature, and the
lettering font — RoadDraft renders text in the system sans face, not a CAD
stick font.
