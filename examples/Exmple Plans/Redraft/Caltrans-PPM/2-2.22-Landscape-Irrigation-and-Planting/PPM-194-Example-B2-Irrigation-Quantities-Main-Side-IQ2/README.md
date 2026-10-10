# PPM-194-Example-B2-Irrigation-Quantities-Main-Side-IQ2 -- redraft

Caltrans PPM example sheet **IQ-2** (IRRIGATION QUANTITIES), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.22-Landscape-Irrigation-and-Planting/PPM-194-Example-B2-Irrigation-Quantities-Main-Side-IQ2.pdf`.

| File | What it holds |
|---|---|
| `0000000000sr002.rdraft` | Sheet **IQ-2**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000sr002.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000sr002-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-194` (pipeline: examples/ppm_redraft/README.md).
