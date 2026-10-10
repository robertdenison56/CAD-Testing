# WFL-Typical-Sections-p05 -- redraft

WFL sample plan sheet **C.1** (TYPICAL SECTION), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Typical-Sections-p05.pdf`.

| File | What it holds |
|---|---|
| `ida-ada60-5_pln_typ1.rdraft` | Sheet **C.1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `ida-ada60-5_pln_typ1.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `ida-ada60-5_pln_typ1-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 26 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 17 at the element the published leader touches, 9 at a point).

## Notes

- File names: `ida-ada60-5_pln_typ1.rdraft` from the plot stamp (ida-ada60-5_pln_typ1.dgn).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Typical-Sections-p05` (pipeline: examples/wfl_redraft/README.md).
