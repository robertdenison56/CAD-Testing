# PPM-119-Example-B-3 -- redraft

Caltrans PPM example sheet **CS-3** (CONSTRUCTION AREA SIGNS), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.14-Construction-Area-Signs/PPM-119-Example-B-3.pdf`.

| File | What it holds |
|---|---|
| `0000000000la003.rdraft` | Sheet **CS-3**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000la003.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000la003-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 28 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 21 at the element the published leader touches, 7 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-119` (pipeline: examples/ppm_redraft/README.md).
