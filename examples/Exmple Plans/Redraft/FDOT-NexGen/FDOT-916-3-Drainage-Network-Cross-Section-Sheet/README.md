# FDOT-916-3-Drainage-Network-Cross-Section-Sheet -- redraft

FDOT sample plan sheet **3** (DRAINAGE NETWORK 1 CROSS SECTIONS), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-916-3-Drainage-Network-Cross-Section-Sheet.pdf`.

| File | What it holds |
|---|---|
| `DRPRRD01.rdraft` | Sheet **3**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `DRPRRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `DRPRRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 12 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 12 at the element the published leader touches, 0 at a point).

## Notes

- File names: `DRPRRD01.rdraft` is the standard file name stamped in the sheet's margin (DRPRRD01.dgn).
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-916-3-Drainage-Network-Cross-Section-Sheet` (pipeline: examples/fdot_redraft/README.md).
