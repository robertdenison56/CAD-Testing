# WFL-Other-Sections-p03 -- redraft

WFL sample plan sheet **E.4** (TURNOUT DETAILS), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p03.pdf`.

| File | What it holds |
|---|---|
| `sal040727-1_pln_misc.rdraft` | Sheet **E.4** ("_pln_misc"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `sal040727-1_pln_misc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `sal040727-1_pln_misc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 15 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 6 at the element the published leader touches, 9 at a point).

## Notes

- File names: project prefix `sal040727-1` from the project number (BLM SAL 040727(1)); the sheet's type suffix `_pln_misc` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p03` (pipeline: examples/wfl_redraft/README.md).
