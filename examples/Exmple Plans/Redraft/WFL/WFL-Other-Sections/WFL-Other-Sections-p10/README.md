# WFL-Other-Sections-p10 -- redraft

WFL sample plan sheet **N.2** (TEMPORARY TRAFFIC CONTROL SIGNING), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p10.pdf`.

| File | What it holds |
|---|---|
| `pfh216-1-1_pln_ptc.rdraft` | Sheet **N.2** ("_pln_ptc"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `pfh216-1-1_pln_ptc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh216-1-1_pln_ptc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 3 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 2 at the element the published leader touches, 1 at a point).

## Notes

- File names: project prefix `pfh216-1-1` from the project number (PFH 216-1(1)); the sheet's type suffix `_pln_ptc` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p10` (pipeline: examples/wfl_redraft/README.md).
