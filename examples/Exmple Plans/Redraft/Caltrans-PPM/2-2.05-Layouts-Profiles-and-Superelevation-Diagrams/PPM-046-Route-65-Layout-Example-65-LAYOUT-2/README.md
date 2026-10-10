# PPM-046-Route-65-Layout-Example-65-LAYOUT-2 -- redraft

Caltrans PPM example sheet **L-2** (LAYOUT), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.05-Layouts-Profiles-and-Superelevation-Diagrams/PPM-046-Route-65-Layout-Example-65-LAYOUT-2.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) D13 rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000ea002.rdraft` | Sheet **L-2**: references the base files through a 1" = 50' viewport (twist -92.357°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000ea002.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ea002-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 16 placed in sheet view with `place_callout` (1 at a stated station and offset of a rebuilt alignment, 14 at the element the published leader touches, 1 at a point).

## Notes

- No drainage is drawn on this sheet, so there is no AA02.
- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-046` (pipeline: examples/ppm_redraft/README.md).
