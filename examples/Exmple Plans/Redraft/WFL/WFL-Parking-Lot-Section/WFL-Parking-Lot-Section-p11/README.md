# WFL-Parking-Lot-Section-p11 -- redraft

WFL sample plan sheet **PLN_PP** (parking), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Parking-Lot-Section-p11.pdf`.

| File | What it holds |
|---|---|
| `wfl_pln_pp.rdraft` | Sheet **PLN_PP** ("_pln_pp"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `wfl_pln_pp.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `wfl_pln_pp-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: project prefix `wfl` no project number on the sheet; the sheet's type suffix `_pln_pp` is the manual's.
- The border and title block are kept as drawn instead of RoadDraft's WFL border template (a portrait cross-section sheet, a non-standard border, or set so in the sheet's config).
- Text heights are the drawn cap heights, measured off the lettering's outlines.

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Parking-Lot-Section-p11` (pipeline: examples/wfl_redraft/README.md).
