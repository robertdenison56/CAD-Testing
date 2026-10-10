# WFL-Other-Sections-p12 -- redraft

WFL sample plan sheet **I.25** (SPECIAL SIGN PANEL DETAILS), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p12.pdf`.

| File | What it holds |
|---|---|
| `pfh247-1_pln_misc.rdraft` | Sheet **I.25**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `pfh247-1_pln_misc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh247-1_pln_misc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 1 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 1 at a point).

## Notes

- File names: `pfh247-1_pln_misc.rdraft` from the project number (PFH 247(1)).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p12` (pipeline: examples/wfl_redraft/README.md).
