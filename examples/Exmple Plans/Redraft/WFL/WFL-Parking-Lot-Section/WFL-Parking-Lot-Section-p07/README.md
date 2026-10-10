# WFL-Parking-Lot-Section-p07 -- redraft

WFL sample plan sheet **F.7** (GRANITE CANYON TRAILHEAD LAYOUT PLAN Sheet 1 of 2), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p07.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `WA-NP-FOVA-101_ali.rdraft` | **ALI** Alignments file ("_ali"): alignment(s) MAIN 01 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `WA-NP-FOVA-101_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `WA-NP-FOVA-101_pln_layout.rdraft` | Sheet **F.7** ("_pln_layout"): references the design files through a 1" = 40' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `WA-NP-FOVA-101_pln_layout.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_layout-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 55 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 44 at the element the published leader touches, 11 at a point).

## Notes

- File names: project prefix `WA-NP-FOVA-101` from the plot stamp (WA-NP-FOVA-101_pln_layout.dgn); the sheet's type suffix `_pln_layout` is the manual's.
- Scale: the sheet prints no numeric scale; 1" = 40' comes from the station tick spacing.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: WFL draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p07` (pipeline: examples/wfl_redraft/README.md).
