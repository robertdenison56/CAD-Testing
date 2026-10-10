# CFL-R-Temporary-Traffic-Control-Detour-Signing -- redraft

CFL sample plan sheet **Untitled** (TEMPORARY TRAFFIC CONTROL DETOUR SIGNING), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-R-Temporary-Traffic-Control-Detour-Signing.pdf`.

| File | What it holds |
|---|---|
| `TCP(Sample).rdraft` | Sheet **Untitled**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `TCP(Sample).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `TCP(Sample)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 18 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 18 at the element the published leader touches, 0 at a point).

## Notes

- File names: `TCP(Sample).rdraft` is the file name stamped in the sheet's margin (TCP(Sample).dgn); design files take its project descriptor `Sample`.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-R-Temporary-Traffic-Control-Detour-Signing` (pipeline: examples/cfl_redraft/README.md).
