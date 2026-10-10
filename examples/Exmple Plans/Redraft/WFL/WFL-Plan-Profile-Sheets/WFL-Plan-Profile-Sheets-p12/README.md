# WFL-Plan-Profile-Sheets-p12 -- redraft

WFL sample plan sheet **D.3** (TABULATION OF QUANTITIES (SHEET 2 OF 3)), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Plan-Profile-Sheets-p12.pdf`.

| File | What it holds |
|---|---|
| `SamplePlan_pln_qtab1.rdraft` | Sheet **D.3**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `SamplePlan_pln_qtab1.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SamplePlan_pln_qtab1-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `SamplePlan_pln_qtab1.rdraft` from the plot stamp (SamplePlan_pln_qtab1.dgn).
- The published sheet carries 70.7 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p12` (pipeline: examples/wfl_redraft/README.md).
