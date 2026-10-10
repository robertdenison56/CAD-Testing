# WFL-Approach-Section-p01 -- redraft

WFL sample plan sheet **E.1** (TABULATION OF QUANTITIES), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Approach-Section-p01.pdf`.

| File | What it holds |
|---|---|
| `WA-NP-FOVA-101_pln_qtab.rdraft` | Sheet **E.1** ("_pln_qtab"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `WA-NP-FOVA-101_pln_qtab.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `WA-NP-FOVA-101_pln_qtab-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: project prefix `WA-NP-FOVA-101` the project's stamped prefix (WA NP FOVA 10(1)); the sheet's type suffix `_pln_qtab` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Approach-Section-p01` (pipeline: examples/wfl_redraft/README.md).
