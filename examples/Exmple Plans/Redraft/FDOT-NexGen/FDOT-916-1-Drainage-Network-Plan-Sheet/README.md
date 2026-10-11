# FDOT-916-1-Drainage-Network-Plan-Sheet -- redraft

FDOT sample plan sheet **1** (DRAINAGE NETWORK 1 PLAN), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-916-1-Drainage-Network-Plan-Sheet.pdf`.

| File | What it holds |
|---|---|
| `ALGNRD01.rdraft` | **ALI** Alignment geometry (ALGNRD01): alignment(s) CL1 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `DSGNRD01.rdraft` | **COR** 2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01. |
| `DRPRRD01.rdraft` | Sheet **1**: references the design files through a 1" = 50' viewport over the plan view (0.80-16.20 x 0.30-10.70 in; twist -148.344°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `DRPRRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `DRPRRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 8 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 1 at the element the published leader touches, 7 at a point).

## Notes

- File names: `DRPRRD01.rdraft` is the standard file name stamped in the sheet's margin (DRPRRD01.dgn).
- No heavy drainage linework was found, so there is no drainage design file.
- Scale: 1" = 50' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- The drainage structures are drawn in this sheet file's own model space rather than a separate design file, as the convention keeps them (the drainage sheets are cut from the drainage design file).
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-916-1-Drainage-Network-Plan-Sheet` (pipeline: examples/fdot_redraft/README.md).
