# WFL-General-Information-p06 -- redraft

WFL sample plan sheet **A.1** (general), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-General-Information-p06.pdf`.

| File | What it holds |
|---|---|
| `glac10-22_pln_gen.rdraft` | Sheet **A.1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `glac10-22_pln_gen.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `glac10-22_pln_gen-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 1 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 1 at the element the published leader touches, 0 at a point).

## Notes

- File names: `glac10-22_pln_gen.rdraft` the project's stamped prefix (MT NPS GLAC 10(22)).
- The published sheet carries 10.5 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-General-Information-p06` (pipeline: examples/wfl_redraft/README.md).
