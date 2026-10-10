# PPM-077-Route-65-Construction-Details-Example-65-C-44 -- redraft

Caltrans PPM example sheet **C-44** (CONSTRUCTION DETAILS), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.06-Construction-Details/PPM-077-Route-65-Construction-Details-Example-65-C-44.pdf`.

| File | What it holds |
|---|---|
| `0000000000ga044.rdraft` | Sheet **C-44**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000ga044.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ga044-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 2 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 2 at the element the published leader touches, 0 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-077` (pipeline: examples/ppm_redraft/README.md).
