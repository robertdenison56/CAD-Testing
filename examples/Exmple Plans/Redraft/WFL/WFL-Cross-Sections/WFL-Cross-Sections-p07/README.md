# WFL-Cross-Sections-p07 -- redraft

WFL sample plan sheet **XS.6** (xs), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Cross-Sections-p07.pdf`.

| File | What it holds |
|---|---|
| `yell12-2_xs.rdraft` | Sheet **XS.6**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `yell12-2_xs.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `yell12-2_xs-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 3 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 3 at the element the published leader touches, 0 at a point).

## Notes

- File names: `yell12-2_xs.rdraft` from the plot stamp (yell12-2_xs.dgn).
- The border and title block are kept as drawn instead of RoadDraft's wfl border template (a portrait or oversize sheet, a non-standard border such as a key sheet, or set so in the sheet's config).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Cross-Sections-p07` (pipeline: examples/wfl_redraft/README.md).
