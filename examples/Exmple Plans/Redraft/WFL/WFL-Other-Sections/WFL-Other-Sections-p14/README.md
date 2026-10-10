# WFL-Other-Sections-p14 -- redraft

WFL sample plan sheet **I.5** (PERMANENT TRAFFIC CONTROL PLAN), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p14.pdf`.

| File | What it holds |
|---|---|
| `pfh247-1_pln_ptc.rdraft` | Sheet **I.5** ("_pln_ptc"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `pfh247-1_pln_ptc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh247-1_pln_ptc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 42 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 27 at the element the published leader touches, 15 at a point).

## Notes

- File names: project prefix `pfh247-1` from the project number (PFH 247(1)); the sheet's type suffix `_pln_ptc` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p14` (pipeline: examples/wfl_redraft/README.md).
