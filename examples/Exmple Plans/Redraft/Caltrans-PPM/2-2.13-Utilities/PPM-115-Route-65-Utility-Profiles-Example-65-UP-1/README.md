# PPM-115-Route-65-Utility-Profiles-Example-65-UP-1 -- redraft

Caltrans PPM example sheet **UP-1** (UTILITY PROFILES), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.13-Utilities/PPM-115-Route-65-Utility-Profiles-Example-65-UP-1.pdf`.

| File | What it holds |
|---|---|
| `0000000000kb001.rdraft` | Sheet **UP-1**: a sheet drawing with no plan view (no model, so no base files); every line, table and note is in sheet view. |
| `0000000000kb001.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000kb001-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 33 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 32 at the element the published leader touches, 1 at a point).

## Notes

- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-115` (pipeline: examples/ppm_redraft/README.md).
