# CFL-D-Plan-and-Profile -- redraft

CFL sample plan sheet **Plan 1** (plan-profile), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-D-Plan-and-Profile.pdf`.

| File | What it holds |
|---|---|
| `TERSample.rdraft` | **SUR** Terrain file (TER): existing features -- the sheet's dashed linework and contour elevations. |
| `ALI(MAIN)Sample.rdraft` | **ALI** Alignment design file (ALI): alignment(s) CL1 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `COR(MAIN)Sample.rdraft` | **COR** Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files. |
| `PNP(Sample).rdraft` | Sheet **Plan 1**: references the design files through a 1" = 100' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist -70.147°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `PNP(Sample).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `PNP(Sample)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 14 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 9 at the element the published leader touches, 5 at a point).

## Notes

- File names: `PNP(Sample).rdraft` is the file name stamped in the sheet's margin (PNP(Sample).dgn); design files take its project descriptor `Sample`.
- Scale: 1" = 100' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-D-Plan-and-Profile` (pipeline: examples/cfl_redraft/README.md).
