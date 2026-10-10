# PPM-168-Example-65-SDS-2-Route-65-Special-Design-Signs -- redraft

Caltrans PPM example sheet **SDS-2** (), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.18-Signs/PPM-168-Example-65-SDS-2-Route-65-Special-Design-Signs.pdf`.

| File | What it holds |
|---|---|
| `0000000000oc002.rdraft` | Sheet **SDS-2**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000oc002.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000oc002-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 7 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 3 at the element the published leader touches, 4 at a point).

## Notes

- The border and title block are kept as drawn instead of RoadDraft's Caltrans title block template (a title sheet or other non-standard border, or set so in the sheet's config).
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-168` (pipeline: examples/ppm_redraft/README.md).
