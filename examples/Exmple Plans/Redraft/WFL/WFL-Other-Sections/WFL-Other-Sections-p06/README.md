# WFL-Other-Sections-p06 -- redraft

WFL sample plan sheet **F.2** (EROSION CONTROL PLANS), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p06.pdf`.

| File | What it holds |
|---|---|
| `pfh247-1_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `pfh247-1_ali.rdraft` | **ALI** Alignments file ("_ali"): alignment(s) CL1, CL2 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `pfh247-1_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `pfh247-1_pln_ec.rdraft` | Sheet **F.2**: references the design files through a 1" = 100' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `pfh247-1_pln_ec.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh247-1_pln_ec-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 10 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 7 at the element the published leader touches, 3 at a point).

## Notes

- File names: `pfh247-1_pln_ec.rdraft` from the project number (PFH 247(1)).
- Scale: 1" = 100' comes from the station tick spacing (the sheet prints no numeric scale).
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p06` (pipeline: examples/wfl_redraft/README.md).
