# FDOT-913-5-4-Lane-High-Speed-Curbed -- redraft

FDOT sample plan sheet **8** (TYPICAL SECTION), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-913-5-4-Lane-High-Speed-Curbed.pdf`.

| File | What it holds |
|---|---|
| `TYPSRD01.rdraft` | Sheet **8**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `TYPSRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `TYPSRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 11 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 5 at the element the published leader touches, 6 at a point).

## Notes

- File names: `TYPSRD01.rdraft` is the table's name for this kind of sheet.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-913-5-4-Lane-High-Speed-Curbed` (pipeline: examples/fdot_redraft/README.md).
