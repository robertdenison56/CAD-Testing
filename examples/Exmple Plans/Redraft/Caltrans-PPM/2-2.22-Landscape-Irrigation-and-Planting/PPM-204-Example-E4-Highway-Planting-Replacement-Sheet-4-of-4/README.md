# PPM-204-Example-E4-Highway-Planting-Replacement-Sheet-4-of-4 -- redraft

Caltrans PPM example sheet **PP-4** (PLANTING PLAN), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.22-Landscape-Irrigation-and-Planting/PPM-204-Example-E4-Highway-Planting-Replacement-Sheet-4-of-4.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) CL1, JC rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000su004.rdraft` | Sheet **PP-4**: references the base files through a 1" = 50' viewport (twist -105.913°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000su004.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000su004-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 19 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 19 at the element the published leader touches, 0 at a point).

## Notes

- No drainage is drawn on this sheet, so there is no AA02.
- No bearing is lettered along a rebuilt alignment, so the view twist is read off the north arrow.
- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist read off the north arrow.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-204` (pipeline: examples/ppm_redraft/README.md).
