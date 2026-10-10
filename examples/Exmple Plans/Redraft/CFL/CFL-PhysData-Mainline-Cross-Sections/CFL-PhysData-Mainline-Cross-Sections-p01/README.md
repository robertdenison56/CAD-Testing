# CFL-PhysData-Mainline-Cross-Sections-p01 -- redraft

CFL sample plan sheet **1500** (xs), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-PhysData-Mainline-Cross-Sections-p01.pdf`.

| File | What it holds |
|---|---|
| `XSS_Sample.rdraft` | Sheet **1500**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `XSS_Sample.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `XSS_Sample-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `XSS_Sample.rdraft` is the file name stamped in the sheet's margin (XSS_Sample.dgn); design files take its project descriptor `Sample`.
- The border and title block are kept as drawn instead of RoadDraft's FLH (wfl) border template (a portrait cross-section sheet, a non-standard border, or set so in the sheet's config).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-PhysData-Mainline-Cross-Sections-p01` (pipeline: examples/cfl_redraft/README.md).
