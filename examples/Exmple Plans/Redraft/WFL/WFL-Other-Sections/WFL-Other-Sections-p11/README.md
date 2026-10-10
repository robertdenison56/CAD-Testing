# WFL-Other-Sections-p11 -- redraft

WFL sample plan sheet **G.2** (DETOUR PLAN), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p11.pdf`.

| File | What it holds |
|---|---|
| `pfh146-4_pln_ttc.rdraft` | Sheet **G.2**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `pfh146-4_pln_ttc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `pfh146-4_pln_ttc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 6 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 4 at the element the published leader touches, 2 at a point).

## Notes

- File names: `pfh146-4_pln_ttc.rdraft` from the project number (PFH 146(4)).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p11` (pipeline: examples/wfl_redraft/README.md).
