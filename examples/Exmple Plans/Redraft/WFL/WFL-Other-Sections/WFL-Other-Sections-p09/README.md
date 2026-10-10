# WFL-Other-Sections-p09 -- redraft

WFL sample plan sheet **H.5** (MSE WALL 109+90 to 110+75), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p09.pdf`.

| File | What it holds |
|---|---|
| `olym11-9_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `olym11-9_ali.rdraft` | **ALI** Alignments file ("_ali"): alignment(s) CL1 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `olym11-9_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `olym11-9_pln_wall.rdraft` | Sheet **H.5**: references the design files through a 1" = 20' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `olym11-9_pln_wall.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `olym11-9_pln_wall-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 8 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 2 at the element the published leader touches, 6 at a point).

## Notes

- File names: `olym11-9_pln_wall.rdraft` from the project number (NPS OLYM 11(9)).
- Scale: the sheet prints no numeric scale; 1" = 20' comes from the station tick spacing.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- The published sheet carries 52.2 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p09` (pipeline: examples/wfl_redraft/README.md).
