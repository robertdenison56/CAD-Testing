# FDOT-920-1-Roadway-Soil-Survey -- redraft

FDOT sample plan sheet **GR-1** (SOIL SURVEY), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-920-1-Roadway-Soil-Survey.pdf`.

| File | What it holds |
|---|---|
| `SSUVRD01.rdraft` | Sheet **GR-1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `SSUVRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SSUVRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `SSUVRD01.rdraft` is the table's name for this kind of sheet.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-920-1-Roadway-Soil-Survey` (pipeline: examples/fdot_redraft/README.md).
