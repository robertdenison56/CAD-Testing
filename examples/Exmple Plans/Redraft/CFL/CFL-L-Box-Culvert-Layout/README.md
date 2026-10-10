# CFL-L-Box-Culvert-Layout -- redraft

CFL sample plan sheet **H1** (SITE 1 BOX CULVERT), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-L-Box-Culvert-Layout.pdf`.

| File | What it holds |
|---|---|
| `TERSample.rdraft` | **SUR** Terrain file (TER): existing features -- the sheet's dashed linework and contour elevations. |
| `DRNSample.rdraft` | **HYD** Drainage design file (DRN): the drainage system drawn heavy on the plan. |
| `CORSample.rdraft` | **COR** Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files. |
| `DRG(Sample).rdraft` | Sheet **H1**: references the design files through a 1" = 20' viewport over the plan view (0.70-16.30 x 6.00-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `DRG(Sample).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `DRG(Sample)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 20 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 7 at the element the published leader touches, 13 at a point).

## Notes

- File names: `DRG(Sample).rdraft` is the file name stamped in the sheet's margin (DRG(Sample).dgn); design files take its project descriptor `Sample`.
- The profile grid below the plan view is sheet linework; the viewport covers the plan view only.
- Scale: the sheet prints no numeric scale; 1" = 20' comes from the graphic scale bar or the config.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-L-Box-Culvert-Layout` (pipeline: examples/cfl_redraft/README.md).
