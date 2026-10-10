# Redrafting the CFL sample plan sheets

This pipeline turns a CFL (FHWA Central Federal Lands) sample plan sheet, a vector PDF split
out of the sample plan sets in `examples/Exmple Plans/CFL Example Plans`, into a RoadDraft
file set named per the CFL file naming convention. It is the WFL pipeline
(`examples/wfl_redraft`) run under a CFL standard: the CFL border is the same FLH 11 × 17
frame, so `wflsheet.digitise` and `wflbuild.build` do the work, and this folder holds only
what CFL does differently. Each sheet gets its own folder under
`examples/Exmple Plans/Redraft/CFL/<source set>/<sheet>/`.

**Plan sheets** (a plan view at an engineering scale) get design files in model space and a
sheet file that references them, named `XXX(YYYY)ZZZZZ`: the three-letter file type, the
alignment descriptor (the first four letters of the alignment's name, where one was
rebuilt), and the project descriptor:

| File | Contents |
|---|---|
| `TER<project>.rdraft` | Terrain and survey (TER): existing features, meaning the sheet's thin dashed linework, and contour elevations. |
| `ALI(<algn>)<project>.rdraft` | Alignments (ALI): the centerlines rebuilt as design data from their station ticks and station numbers, with stationing lettered the CFL way (the whole station, `15+00`, square to the line). |
| `COR(<algn>)<project>.rdraft` | Corridor (COR): the proposed linework. References the ALI and TER files. |
| `DRN<project>.rdraft` | Drainage design (DRN). Only on drainage plans that draw a drainage system heavy. |
| `<stamped name>.rdraft` | The plan sheet, named as the published sheet's margin stamps its own file (`PNP(Sample)`, `TYP(Sample)4R`, `WAL(Sample)`, `SST(Sample)PKG`, ...): border, title block, viewport over the plan view, and every note, callout, table, the profile grid and symbol in sheet view. |

The project descriptor is the stamp's (`Sample`, `PKG`). A sheet without a usable stamp
takes the convention's descriptor for its kind (PNP, TYP, TAB, PRK, ECP, WAL, DRN, SST, TCP,
XSS, XST). The alignment descriptor is the first four letters of the alignment's lettered
name; the CFL samples letter none, so it is taken from the road a note names (`Main Road`
on the plan-profile sheet gives `ALI(MAIN)Sample`), and left off where no note names one.

**Other sheets** (typical sections, summaries, cross sections, special drawings) have no
model, so they are a sheet file only.

**Every folder also holds** a full-size PDF plot, a DXF, a PNG render, `-overlay.png` (the
published sheet in blue, the redraft in red, black where they agree) and a README.
`examples/Exmple Plans/Redraft/CFL/redraft-manifest.csv` lists every CFL sheet and what was
built for it.

```bash
.venv/bin/python examples/cfl_redraft/run_cfl.py --all --workers 6      # every sheet
.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-D-Plan-and-Profile  # some sheets
.venv/bin/python examples/cfl_redraft/review.py CFL-D-Plan-and-Profile --bases
```

## What CFL does differently

- **Sheet families** come from the sample set's file names (`CFL-D-Plan-and-Profile`,
  `CFL-I-MSE-Wall-Layout`, ...), since the sample title blocks carry placeholders.
- **The title block's value cell** letters the project number over the project name; the
  `wfl` template draws both when a `project_name` is given.
- **Station ticks** are drawn every 500 ft and labelled with the whole station (`15+00`),
  lettered square to the line at the top of the plan band, up to 3 in off it. The rebuilt
  stationing follows: a tick and a label every 500 ft, lettered the same way.
- **Aerial photographs** under the plan-and-plan and parking-lot layout sheets are raster
  images; the redraft holds the vector linework and lettering, and the README says how much
  of the sheet was raster.
- **The graphic scale bar** letters its numbers with feet marks (`0  50'  100'`).
- **The superelevation diagram** under the profile grid reaches into the sheet title's
  corner on plan-profile sheets; a title box is only read where a title-sized line is
  lettered in it.

Everything else (lettering as cap heights with outlines dropped, bold copies deduplicated,
leaders followed from landings, one-sided ticks, the scale from the tick spacing or the
scale bar, existing features as thin dashed lines, the profile grid kept on the sheet) is
as in `examples/wfl_redraft/README.md`. Per-sheet settings are in `configs/` (the keys are
`examples/wfl_redraft/configs/README.md`'s).
