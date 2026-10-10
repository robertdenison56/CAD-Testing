# WFL-Typical-Sections-p06 -- redraft

WFL sample plan sheet **C.2** (TYPICAL SECTION), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Typical-Sections-p06.pdf`.

| File | What it holds |
|---|---|
| `ida-ada60-5_pln_typ.rdraft` | Sheet **C.2** ("_pln_typ"): a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `ida-ada60-5_pln_typ.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `ida-ada60-5_pln_typ-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 15 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 7 at the element the published leader touches, 8 at a point).

## Notes

- File names: project prefix `ida-ada60-5` the project's stamped prefix (ID FLAP ADA 60(5)); the sheet's type suffix `_pln_typ` is the manual's.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Typical-Sections-p06` (pipeline: examples/wfl_redraft/README.md).
