# CFL-C-Typical-Sections-Approach-Roads-p04 -- redraft

CFL sample plan sheet **A8** (TYPICAL SECTION APPROACH ROADS Sheet 2 of 2), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-C-Typical-Sections-Approach-Roads-p04.pdf`.

| File | What it holds |
|---|---|
| `TYP(Sample)APPR.rdraft` | Sheet **A8**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `TYP(Sample)APPR.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `TYP(Sample)APPR-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 8 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 4 at the element the published leader touches, 4 at a point).

## Notes

- File names: `TYP(Sample)APPR.rdraft` is the file name stamped in the sheet's margin (TYP(Sample)APPR.dgn); design files take its project descriptor `Sample`.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-C-Typical-Sections-Approach-Roads-p04` (pipeline: examples/cfl_redraft/README.md).
