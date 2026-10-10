# CFL-PhysData-Cross-Section-Title-Sheet -- redraft

CFL sample plan sheet **X1** (xst), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-PhysData-Cross-Section-Title-Sheet.pdf`.

| File | What it holds |
|---|---|
| `XXS_TTL.rdraft` | Sheet **X1**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `XXS_TTL.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `XXS_TTL-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `XXS_TTL.rdraft` is the file name stamped in the sheet's margin (XXS_TTL.dgn); design files take its project descriptor `TTL`.
- The published sheet carries 3.9 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-PhysData-Cross-Section-Title-Sheet` (pipeline: examples/cfl_redraft/README.md).
