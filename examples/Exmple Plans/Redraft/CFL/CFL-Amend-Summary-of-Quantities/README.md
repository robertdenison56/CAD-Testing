# CFL-Amend-Summary-of-Quantities -- redraft

CFL sample plan sheet **NSUHMEBEET** (soq), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-Amend-Summary-of-Quantities.pdf`.

| File | What it holds |
|---|---|
| `TAB(Sample).rdraft` | Sheet **NSUHMEBEET**: a sheet drawing with no plan view (no model, so no design files); every line, table and note is in sheet view. |
| `TAB(Sample).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `TAB(Sample)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 0 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 0 at a point).

## Notes

- File names: `TAB(Sample).rdraft` is the convention's descriptor for this kind of sheet (no usable stamp in the margin).
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font sizes and the cap height is taken as 0.72 of the size.

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-Amend-Summary-of-Quantities` (pipeline: examples/cfl_redraft/README.md).
