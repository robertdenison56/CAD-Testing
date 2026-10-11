# WFL-Parking-Lot-Section-p08 -- redraft

WFL sample plan sheet **F.8** (GRANITE CANYON TRAILHEAD LAYOUT PLAN Sheet 2 of 2), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p08.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `WA-NP-FOVA-101_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `WA-NP-FOVA-101_pln_layout.rdraft` | Sheet **F.8**: references the design files through a 1" = 6.1' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `WA-NP-FOVA-101_pln_layout.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_layout-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 53 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 50 at the element the published leader touches, 3 at a point).

## Notes

- File names: `WA-NP-FOVA-101_pln_layout.rdraft` from the plot stamp (WA-NP-FOVA-101_pln_layout.dgn).
- Scale: 1" = 6.1' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p08` (pipeline: examples/wfl_redraft/README.md).
