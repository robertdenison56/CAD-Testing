# CFL-Amend-Plan-Sheets-p02 -- redraft

CFL sample plan sheet **T17** (SPECIAL 609-A CURB DETAILS REVISED 2/15/2024), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-Amend-Plan-Sheets-p02.pdf`.

| File | What it holds |
|---|---|
| `SP609-A.rdraft` | Sheet **T17**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `SP609-A.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SP609-A-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 9 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 6 at the element the published leader touches, 3 at a point).

## Notes

- File names: `SP609-A.rdraft` is the file name stamped in the sheet's margin (SP609-A.dgn); design files take its project descriptor `609`.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-Amend-Plan-Sheets-p02` (pipeline: examples/cfl_redraft/README.md).
