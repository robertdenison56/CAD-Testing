# PPM-051-Route-65-Layout-Example-65-LAYOUT-38 -- redraft

Caltrans PPM example sheet **L-38** (LAYOUT), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.05-Layouts-Profiles-and-Superelevation-Diagrams/PPM-051-Route-65-Layout-Example-65-LAYOUT-38.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) WIS1, SB10, NB10 rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000ea038.rdraft` | Sheet **L-38**: references the base files through a 1" = 50' viewport (twist 0.000°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000ea038.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ea038-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 15 placed in sheet view with `place_callout` (2 at a stated station and offset of a rebuilt alignment, 7 at the element the published leader touches, 6 at a point).

## Notes

- No drainage is drawn on this sheet, so there is no AA02.
- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-051` (pipeline: examples/ppm_redraft/README.md).
