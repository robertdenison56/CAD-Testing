# WFL-Plan-Profile-Sheets-p10 -- redraft

WFL sample plan sheet **D.1** (SURVEY CONTROL), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Plan-Profile-Sheets-p10.pdf`.

| File | What it holds |
|---|---|
| `SamplePlan_pln_ctrl.rdraft` | Sheet **D.1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `SamplePlan_pln_ctrl.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SamplePlan_pln_ctrl-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `SamplePlan_pln_ctrl.rdraft` the project's stamped prefix (AK NPS SAMP 14(1)); its type is not in the convention's table (none is listed for this kind of sheet).
- The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font sizes and the cap height is taken as 0.72 of the size.

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p10` (pipeline: examples/wfl_redraft/README.md).
