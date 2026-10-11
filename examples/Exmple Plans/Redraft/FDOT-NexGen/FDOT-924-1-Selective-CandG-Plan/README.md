# FDOT-924-1-Selective-CandG-Plan -- redraft

FDOT sample plan sheet **1371** (SELECTIVE CLEARING AND GRUBBING PLAN (1)), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-924-1-Selective-CandG-Plan.pdf`.

| File | What it holds |
|---|---|
| `ALGNRD01.rdraft` | **ALI** Alignment geometry (ALGNRD01): alignment(s) CL1 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `DSGNRD01.rdraft` | **COR** 2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01. |
| `SCGPRD01.rdraft` | Sheet **1371**: references the design files through a 1" = 69' viewport over the plan view (0.80-16.20 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `SCGPRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SCGPRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 4 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 4 at the element the published leader touches, 0 at a point).

## Notes

- File names: `SCGPRD01.rdraft` is the table's name for this kind of sheet.
- Scale: 1" = 69' comes from how far apart the station numbers are lettered (the sheet is not at the scale its note states, or a usual one).
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-924-1-Selective-CandG-Plan` (pipeline: examples/fdot_redraft/README.md).
