# PPM-093-Route-65-Drainage-Plan-Example-65-D-1 -- redraft

Caltrans PPM example sheet **D-1** (DRAINAGE PLAN), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.10-Drainage/PPM-093-Route-65-Drainage-Plan-Example-65-D-1.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa02.rdraft` | **AA02** Drainage: the drainage system drawn heavy on the plan (pipes, culverts, inlets). |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) D13, TBR1, CL3 rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000ia001.rdraft` | Sheet **D-1**: references the base files through a 1" = 50' viewport (twist -90.000°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000ia001.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ia001-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 1 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 1 at the element the published leader touches, 0 at a point).

## Notes

- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist set in the sheet's config.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-093` (pipeline: examples/ppm_redraft/README.md).
