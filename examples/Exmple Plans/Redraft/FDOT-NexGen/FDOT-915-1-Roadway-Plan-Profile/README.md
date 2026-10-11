# FDOT-915-1-Roadway-Plan-Profile -- redraft

FDOT sample plan sheet **12** (ROADWAY PLAN-PROFILE), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-915-1-Roadway-Plan-Profile.pdf`.

| File | What it holds |
|---|---|
| `ALGNRD01.rdraft` | **ALI** Alignment geometry (ALGNRD01): alignment(s) CL1, CL2 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `DSGNRD01.rdraft` | **COR** 2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01. |
| `PLPRRD02.rdraft` | Sheet **12**: references the design files through a 1" = 50' viewport over the plan view (0.80-16.20 x 5.30-10.70 in; twist -149.210°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `PLPRRD02.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `PLPRRD02-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 19 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 12 at the element the published leader touches, 7 at a point).

## Notes

- File names: `PLPRRD02.rdraft` is the standard file name stamped in the sheet's margin (PLPRRD02.dgn).
- The profile grid below the plan view is sheet linework; the viewport covers the plan view only.
- Scale: 1" = 50' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-915-1-Roadway-Plan-Profile` (pipeline: examples/fdot_redraft/README.md).
