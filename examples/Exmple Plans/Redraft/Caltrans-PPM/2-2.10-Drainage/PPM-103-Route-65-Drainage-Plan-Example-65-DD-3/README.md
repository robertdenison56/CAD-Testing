# PPM-103-Route-65-Drainage-Plan-Example-65-DD-3 -- redraft

Caltrans PPM example sheet **DD-3** (DRAINAGE DETAILS), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.10-Drainage/PPM-103-Route-65-Drainage-Plan-Example-65-DD-3.pdf`.

| File | What it holds |
|---|---|
| `0000000000ic003.rdraft` | Sheet **DD-3**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000ic003.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ic003-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 54 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 52 at the element the published leader touches, 2 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-103` (pipeline: examples/ppm_redraft/README.md).
