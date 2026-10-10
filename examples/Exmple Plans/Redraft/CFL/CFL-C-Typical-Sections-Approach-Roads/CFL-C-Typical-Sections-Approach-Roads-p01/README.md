# CFL-C-Typical-Sections-Approach-Roads-p01 -- redraft

CFL sample plan sheet **A6** (TYPICAL SECTION MAINLINE), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-C-Typical-Sections-Approach-Roads-p01.pdf`.

| File | What it holds |
|---|---|
| `TYP(Sample)4R.rdraft` | Sheet **A6**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `TYP(Sample)4R.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `TYP(Sample)4R-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 22 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 10 at the element the published leader touches, 12 at a point).

## Notes

- File names: `TYP(Sample)4R.rdraft` is the file name stamped in the sheet's margin (TYP(Sample)4R.dgn); design files take its project descriptor `Sample`.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-C-Typical-Sections-Approach-Roads-p01` (pipeline: examples/cfl_redraft/README.md).
