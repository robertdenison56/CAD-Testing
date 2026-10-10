# WFL-Parking-Lot-Section-p05 -- redraft

WFL sample plan sheet **F.5** (GRANITE CANYON TRAILHEAD CB1 PLAN AND PROFILE), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p05.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_pln_drainage.rdraft` | Sheet **F.5**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `WA-NP-FOVA-101_pln_drainage.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_drainage-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 13 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 6 at the element the published leader touches, 7 at a point).

## Notes

- File names: `WA-NP-FOVA-101_pln_drainage.rdraft` from the plot stamp (WA-NP-FOVA-101_pln_Drainage.dgn).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p05` (pipeline: examples/wfl_redraft/README.md).
