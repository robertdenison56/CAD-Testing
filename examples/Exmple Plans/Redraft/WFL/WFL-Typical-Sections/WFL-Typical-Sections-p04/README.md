# WFL-Typical-Sections-p04 -- redraft

WFL sample plan sheet **C.1** (TYPICAL SECTION), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Typical-Sections-p04.pdf`.

| File | What it holds |
|---|---|
| `waa-jeff1-23_pln_typ.rdraft` | Sheet **C.1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `waa-jeff1-23_pln_typ.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `waa-jeff1-23_pln_typ-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 17 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 9 at the element the published leader touches, 8 at a point).

## Notes

- File names: `waa-jeff1-23_pln_typ.rdraft` from the plot stamp (waa-jeff1-23_pln_typ.dgn).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Typical-Sections-p04` (pipeline: examples/wfl_redraft/README.md).
