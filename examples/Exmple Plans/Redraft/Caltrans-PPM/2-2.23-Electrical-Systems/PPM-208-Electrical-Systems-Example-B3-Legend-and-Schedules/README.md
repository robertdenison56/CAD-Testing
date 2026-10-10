# PPM-208-Electrical-Systems-Example-B3-Legend-and-Schedules -- redraft

Caltrans PPM example sheet **E-11** (SIGNAL AND LIGHTING SYSTEM), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.23-Electrical-Systems/PPM-208-Electrical-Systems-Example-B3-Legend-and-Schedules.pdf`.

| File | What it holds |
|---|---|
| `1300010110ua011.rdraft` | Sheet **E-11**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `1300010110ua011.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `1300010110ua011-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-208` (pipeline: examples/ppm_redraft/README.md).
