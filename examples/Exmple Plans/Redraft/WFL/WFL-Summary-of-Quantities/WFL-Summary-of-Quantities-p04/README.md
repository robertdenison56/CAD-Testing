# WFL-Summary-of-Quantities-p04 -- redraft

WFL sample plan sheet **B.1** (soq), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Summary-of-Quantities-p04.pdf`.

| File | What it holds |
|---|---|
| `yell12-2_pln_soq.rdraft` | Sheet **B.1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `yell12-2_pln_soq.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `yell12-2_pln_soq-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `yell12-2_pln_soq.rdraft` the project's stamped prefix (WY NPS YELL 12(2)); its type is not in the convention's table (none is listed for this kind of sheet).
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font sizes and the cap height is taken as 0.72 of the size.

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Summary-of-Quantities-p04` (pipeline: examples/wfl_redraft/README.md).
