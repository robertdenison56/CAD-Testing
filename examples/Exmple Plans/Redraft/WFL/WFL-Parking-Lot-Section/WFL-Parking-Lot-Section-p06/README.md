# WFL-Parking-Lot-Section-p06 -- redraft

WFL sample plan sheet **F.6** (GRANITE CANYON TRAILHEAD SECTION), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p06.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_pln_sec.rdraft` | Sheet **F.6** ("_pln_sec"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `WA-NP-FOVA-101_pln_sec.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_sec-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 20 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 8 at the element the published leader touches, 12 at a point).

## Notes

- File names: project prefix `WA-NP-FOVA-101` from the plot stamp (WA-NP-FOVA-101_pln_Sec.dgn); the sheet's type suffix `_pln_sec` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p06` (pipeline: examples/wfl_redraft/README.md).
