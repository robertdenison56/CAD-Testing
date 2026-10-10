# PPM-043-Route-65-KEY-MAP-Line-Index-Sheet-Example-65-Key-Map -- redraft

Caltrans PPM example sheet **K-1** (KEY MAP AND LINE INDEX), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.04-Project-Orientation/PPM-043-Route-65-KEY-MAP-Line-Index-Sheet-Example-65-Key-Map.pdf`.

| File | What it holds |
|---|---|
| `0000000000da001.rdraft` | Sheet **K-1**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000da001.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000da001-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 13 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 10 at the element the published leader touches, 3 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-043` (pipeline: examples/ppm_redraft/README.md).
