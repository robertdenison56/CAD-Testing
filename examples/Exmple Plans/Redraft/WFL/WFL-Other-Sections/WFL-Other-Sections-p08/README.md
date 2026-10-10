# WFL-Other-Sections-p08 -- redraft

WFL sample plan sheet **H.19** (DRAINAGE DETAILS), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p08.pdf`.

| File | What it holds |
|---|---|
| `glac10-22_pln_misc.rdraft` | Sheet **H.19**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `glac10-22_pln_misc.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `glac10-22_pln_misc-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 3 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 1 at the element the published leader touches, 2 at a point).

## Notes

- File names: `glac10-22_pln_misc.rdraft` from the project number (PRA GLAC 10(22)).
- The published sheet carries 11.7 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p08` (pipeline: examples/wfl_redraft/README.md).
