# FDOT-907-1-RFP-Concept-Plans -- redraft

FDOT sample plan sheet **1** (concept), redrafted as a RoadDraft file set named per the FDOT CADD Manual's standard file names (<type><discipline><sequence>). Source: `Sheets/FDOT-NexGen/FDOT-907-1-RFP-Concept-Plans.pdf`.

| File | What it holds |
|---|---|
| `KEYSRD07.rdraft` | Sheet **1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `KEYSRD07.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `KEYSRD07-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 3 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 3 at a point).

## Notes

- File names: `KEYSRD07.rdraft` is the standard file name stamped in the sheet's margin (KEYSRD07.dgn).
- The published sheet carries 19.3 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- The border and title block are kept as drawn instead of RoadDraft's fdot border template (a portrait or oversize sheet, a non-standard border such as a key sheet, or set so in the sheet's config).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-907-1-RFP-Concept-Plans` (pipeline: examples/fdot_redraft/README.md).
