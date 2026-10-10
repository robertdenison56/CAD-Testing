# PPM-013-Title-Example-J -- redraft

Caltrans PPM example sheet **AB-001** (), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.02-Title-Sheets/PPM-013-Title-Example-J.pdf`.

| File | What it holds |
|---|---|
| `0000000000ab001.rdraft` | Sheet **AB-001**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000ab001.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ab001-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 4 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 3 at the element the published leader touches, 1 at a point).

## Notes

- The border and title block are kept as drawn instead of RoadDraft's Caltrans title block template (a title sheet or other non-standard border, or set so in the sheet's config).
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-013` (pipeline: examples/ppm_redraft/README.md).
