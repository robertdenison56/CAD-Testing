# WFL-Parking-Lot-Section-p16 -- redraft

WFL sample plan sheet **F.16** (FIXTURE, VAULT TOILET (CXT DOUBLE CASCADIAN WITH CHASE) DETAIL Sheet 2 of 2), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p16.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_pln_details.rdraft` | Sheet **F.16** ("_pln_details"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `WA-NP-FOVA-101_pln_details.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_details-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 23 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 21 at the element the published leader touches, 2 at a point).

## Notes

- File names: project prefix `WA-NP-FOVA-101` from the plot stamp (WA-NP-FOVA-101_pln_details.dgn); the sheet's type suffix `_pln_details` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p16` (pipeline: examples/wfl_redraft/README.md).
