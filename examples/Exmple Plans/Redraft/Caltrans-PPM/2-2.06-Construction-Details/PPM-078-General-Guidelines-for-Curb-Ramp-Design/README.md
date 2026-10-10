# PPM-078-General-Guidelines-for-Curb-Ramp-Design -- redraft

Caltrans PPM example sheet **ZZ-001** (CONSTRUCTION DETAILS), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.06-Construction-Details/PPM-078-General-Guidelines-for-Curb-Ramp-Design.pdf`.

| File | What it holds |
|---|---|
| `0000000000zz001.rdraft` | Sheet **ZZ-001**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000zz001.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000zz001-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 1 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 1 at the element the published leader touches, 0 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-078` (pipeline: examples/ppm_redraft/README.md).
