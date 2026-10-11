# FDOT-918-1-Drainage-Map -- redraft

FDOT sample plan sheet **5** (DRAINAGE MAP), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-918-1-Drainage-Map.pdf`.

| File | What it holds |
|---|---|
| `ALGNRD01.rdraft` | **ALI** Alignment geometry (ALGNRD01): alignment(s) CL1, CL2 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `DSGNRD01.rdraft` | **COR** 2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01. |
| `DRMPRD01.rdraft` | Sheet **5**: references the design files through a 1" = 200' viewport over the plan view (0.80-16.20 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `DRMPRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `DRMPRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 3 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 3 at a point).

## Notes

- File names: `DRMPRD01.rdraft` is the table's name for this kind of sheet.
- Scale: 1" = 200' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- The published sheet carries 187 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-918-1-Drainage-Map` (pipeline: examples/fdot_redraft/README.md).
