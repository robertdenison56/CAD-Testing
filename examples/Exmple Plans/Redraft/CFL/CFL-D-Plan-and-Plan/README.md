# CFL-D-Plan-and-Plan -- redraft

CFL sample plan sheet **PLA(SAMPLE)** (DAVIS DAM ROAD 29+67.45 to 41+00), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-D-Plan-and-Plan.pdf`.

| File | What it holds |
|---|---|
| `COR(MAIN)Sample.rdraft` | **COR** Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files. |
| `PLA(Sample).rdraft` | Sheet **PLA(SAMPLE)**: references the design files through a 1" = 50' viewport over the plan view (0.70-16.30 x 6.00-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `PLA(Sample).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `PLA(Sample)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 8 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 1 at the element the published leader touches, 7 at a point).

## Notes

- File names: `PLA(Sample).rdraft` is the file name stamped in the sheet's margin (PLA(Sample).dgn); design files take its project descriptor `Sample`.
- The profile grid below the plan view is sheet linework; the viewport covers the plan view only.
- Scale: the sheet prints no numeric scale; 1" = 50' comes from the graphic scale bar or the config.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- The published sheet carries 668.1 sq in of raster images (an aerial photograph or logos); the redraft holds the vector linework and lettering only.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-D-Plan-and-Plan` (pipeline: examples/cfl_redraft/README.md).
