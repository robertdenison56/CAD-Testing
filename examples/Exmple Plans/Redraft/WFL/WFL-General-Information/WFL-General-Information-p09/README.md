# WFL-General-Information-p09 -- redraft

WFL sample plan sheet **A.4** (VICINITY MAP), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-General-Information-p09.pdf`.

| File | What it holds |
|---|---|
| `glac10-22_pln_gen.rdraft` | Sheet **A.4** ("_pln_gen"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `glac10-22_pln_gen.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `glac10-22_pln_gen-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 7 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 5 at the element the published leader touches, 2 at a point).

## Notes

- File names: project prefix `glac10-22` the project's stamped prefix (MT NPS GLAC 10(22)); the sheet's type suffix `_pln_gen` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-General-Information-p09` (pipeline: examples/wfl_redraft/README.md).
