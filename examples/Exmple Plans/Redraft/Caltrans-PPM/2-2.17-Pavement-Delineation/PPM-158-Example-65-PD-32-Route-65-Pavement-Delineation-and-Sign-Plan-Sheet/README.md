# PPM-158-Example-65-PD-32-Route-65-Pavement-Delineation-and-Sign-Plan-Sheet -- redraft

Caltrans PPM example sheet **PD-32** (PAVEMENT DELINEATION AND SIGN PLAN), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.17-Pavement-Delineation/PPM-158-Example-65-PD-32-Route-65-Pavement-Delineation-and-Sign-Plan-Sheet.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) NB10, SB10, WIS1, CL4 rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000na032.rdraft` | Sheet **PD-32**: references the base files through a 1" = 50' viewport (twist -85.000°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000na032.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000na032-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 7 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 7 at the element the published leader touches, 0 at a point).

## Notes

- No drainage is drawn on this sheet, so there is no AA02.
- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist set in the sheet's config.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-158` (pipeline: examples/ppm_redraft/README.md).
