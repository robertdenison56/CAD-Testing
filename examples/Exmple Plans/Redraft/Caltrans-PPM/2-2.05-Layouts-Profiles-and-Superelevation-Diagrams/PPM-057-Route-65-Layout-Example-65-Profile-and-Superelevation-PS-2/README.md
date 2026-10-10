# PPM-057-Route-65-Layout-Example-65-Profile-and-Superelevation-PS-2 -- redraft

Caltrans PPM example sheet **PS-2** (), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.05-Layouts-Profiles-and-Superelevation-Diagrams/PPM-057-Route-65-Layout-Example-65-Profile-and-Superelevation-PS-2.pdf`.

| File | What it holds |
|---|---|
| `0000000000fb002.rdraft` | Sheet **PS-2**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000fb002.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000fb002-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- The PDF's text layer is OCR and does not line up with the drawn lettering, so the lettering is kept as the drawn strokes (S-TEXT-* layers) and leaders as linework; the text layer is only read for the title block.
- The border and title block are kept as drawn instead of RoadDraft's Caltrans title block template (a title sheet or other non-standard border, or set so in the sheet's config).
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-057` (pipeline: examples/ppm_redraft/README.md).
