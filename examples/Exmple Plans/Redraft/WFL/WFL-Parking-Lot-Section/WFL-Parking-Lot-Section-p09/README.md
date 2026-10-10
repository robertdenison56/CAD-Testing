# WFL-Parking-Lot-Section-p09 -- redraft

WFL sample plan sheet **F.9** (GRANITE CANYON TRAILHEAD GRANITE CANYON TRAILHEAD LAYOUT POINT TABLES), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p09.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_pln_layout.rdraft` | Sheet **F.9**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `WA-NP-FOVA-101_pln_layout.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_layout-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `WA-NP-FOVA-101_pln_layout.rdraft` from the plot stamp (WA-NP-FOVA-101_pln_layout.dgn).
- The published sheet carries 216.4 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font sizes and the cap height is taken as 0.72 of the size.

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p09` (pipeline: examples/wfl_redraft/README.md).
