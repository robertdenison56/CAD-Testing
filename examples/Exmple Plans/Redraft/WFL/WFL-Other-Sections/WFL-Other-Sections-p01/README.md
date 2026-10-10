# WFL-Other-Sections-p01 -- redraft

WFL sample plan sheet **D.4** (LINE GRAPH), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p01.pdf`.

| File | What it holds |
|---|---|
| `pfh46-1-4_pln_misc.rdraft` | Sheet **D.4** ("_pln_misc"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `pfh46-1-4_pln_misc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh46-1-4_pln_misc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 4 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 2 at the element the published leader touches, 2 at a point).

## Notes

- File names: project prefix `pfh46-1-4` from the project number (PFH 46-1(4)); the sheet's type suffix `_pln_misc` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p01` (pipeline: examples/wfl_redraft/README.md).
