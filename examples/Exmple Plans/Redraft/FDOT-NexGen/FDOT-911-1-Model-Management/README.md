# FDOT-911-1-Model-Management -- redraft

FDOT sample plan sheet **7** (MODEL MANAGEMENT), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-911-1-Model-Management.pdf`.

| File | What it holds |
|---|---|
| `MDMGRD01.rdraft` | Sheet **7**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `MDMGRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `MDMGRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 7 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 6 at the element the published leader touches, 1 at a point).

## Notes

- File names: `MDMGRD01.rdraft` is the table's name for this kind of sheet; its type is not in the convention's table (none is listed for this kind of sheet).
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-911-1-Model-Management` (pipeline: examples/fdot_redraft/README.md).
