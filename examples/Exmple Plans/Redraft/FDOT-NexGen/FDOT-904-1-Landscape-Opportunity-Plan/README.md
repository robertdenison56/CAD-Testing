# FDOT-904-1-Landscape-Opportunity-Plan -- redraft

FDOT sample plan sheet **PLANLD01** (landscape), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-904-1-Landscape-Opportunity-Plan.pdf`.

| File | What it holds |
|---|---|
| `ALGNRD01.rdraft` | **ALI** Alignment geometry (ALGNRD01): alignment(s) CL1, CL2, CL3, CL4, CL5, CL6, CL7, CL8, CL9, CL10 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `DSGNRD01.rdraft` | **COR** 2D plan, proposed (DSGNRD01): the proposed linework (edges, limits, symbols). References ALGNRD01 and SURVRD01. |
| `PLANLD01.rdraft` | Sheet **PLANLD01**: references the design files through a 1" = 100' viewport over the plan view (0.00-48.00 x 0.00-36.00 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `PLANLD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `PLANLD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 29 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 20 at the element the published leader touches, 9 at a point).

## Notes

- File names: `PLANLD01.rdraft` is the table's name for this kind of sheet.
- Scale: 1" = 100' comes from the station tick spacing (the sheet prints no numeric scale).
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- The published sheet carries 16.9 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- The border and title block are kept as drawn instead of RoadDraft's fdot border template (a portrait or oversize sheet, a non-standard border such as a key sheet, or set so in the sheet's config).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-904-1-Landscape-Opportunity-Plan` (pipeline: examples/fdot_redraft/README.md).
