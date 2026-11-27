# PPM-130-Stage-Construction-and-Traffic-Handling-Plan-Sheet-Example-70-SC-3 -- redraft

Caltrans PPM example sheet **SC-3** (STAGE 1), redrafted as a RoadDraft file set named per the Caltrans CADD Users Manual. Source: `Sheets/Caltrans-PPM/2-2.16-Stage-Construction-Traffic-Handling-and-Detour/PPM-130-Stage-Construction-and-Traffic-Handling-Plan-Sheet-Example-70-SC-3.pdf`.

| File | What it holds |
|---|---|
| `0000000000bb01.rdraft` | **BB01** Master Topographic ("bb"): existing features -- the sheet's dotted linework (existing roads, railroad, fence, contours) and contour elevations. |
| `0000000000aa01.rdraft` | **AA01** Master Design, roadway ("aa"): alignment(s) A rebuilt from the centerline, ticks and station numbers, with stationing; the proposed roadway linework. References BB01. |
| `0000000000ma003.rdraft` | Sheet **SC-3**: references the base files through a 1" = 50' viewport (twist -69.140°); border, title block, notes, callouts, match lines, tables and symbols in sheet view. |
| `0000000000ma003.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `0000000000ma003-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station and offset of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- No drainage is drawn on this sheet, so there is no AA02.
- The PDF's text layer is OCR and does not line up with the drawn lettering, so the lettering is kept as the drawn strokes (S-TEXT-* layers) and leaders as linework; the text layer is only read for the title block.
- Coordinates: the example prints none; the model sits on a local datum (sheet centre at E 10,000 N 10,000), turned by the view twist set in the sheet's config.
- Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, so the PNG/PDF lettering looks smaller than the Caltrans font.

Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-130` (pipeline: examples/ppm_redraft/README.md).
