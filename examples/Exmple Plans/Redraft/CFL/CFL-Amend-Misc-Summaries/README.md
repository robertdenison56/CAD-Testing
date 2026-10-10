# CFL-Amend-Misc-Summaries -- redraft

CFL sample plan sheet **B12** (MISCELLANEOUS SUMMARIES Sheet 2 of 6 REVISED 04/01/24), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-Amend-Misc-Summaries.pdf`.

| File | What it holds |
|---|---|
| `B_Sheets.rdraft` | Sheet **B12**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `B_Sheets.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `B_Sheets-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `B_Sheets.rdraft` is the file name stamped in the sheet's margin (B_Sheets.dgn); design files take its project descriptor `Sample`.
- The published sheet carries 31.2 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-Amend-Misc-Summaries` (pipeline: examples/cfl_redraft/README.md).
