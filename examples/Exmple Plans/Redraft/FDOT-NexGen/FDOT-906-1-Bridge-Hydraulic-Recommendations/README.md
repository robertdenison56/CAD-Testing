# FDOT-906-1-Bridge-Hydraulic-Recommendations -- redraft

FDOT sample plan sheet **SHE1E5T NO.** (hydraulics), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-906-1-Bridge-Hydraulic-Recommendations.pdf`.

| File | What it holds |
|---|---|
| `BHRSRD01.rdraft` | Sheet **SHE1E5T NO.**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `BHRSRD01.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `BHRSRD01-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 22 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 20 at the element the published leader touches, 2 at a point).

## Notes

- File names: `BHRSRD01.rdraft` is the table's name for this kind of sheet.
- The published sheet carries 167.6 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- The border and title block are kept as drawn instead of RoadDraft's fdot border template (a portrait or oversize sheet, a non-standard border such as a key sheet, or set so in the sheet's config).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-906-1-Bridge-Hydraulic-Recommendations` (pipeline: examples/fdot_redraft/README.md).
