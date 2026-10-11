# CFL-Q-Signing-and-Pavement-Markings-Parking-Lot -- redraft

CFL sample plan sheet **T33** (SIGNING AND PAVEMENT MARKINGS MAIN ROAD PARKING LOT), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-Q-Signing-and-Pavement-Markings-Parking-Lot.pdf`.

| File | What it holds |
|---|---|
| `TERSample.rdraft` | **SUR** Terrain file (TER): existing features -- the sheet's dashed linework and contour elevations. |
| `CORSample.rdraft` | **COR** Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files. |
| `SST(Sample)PKG.rdraft` | Sheet **T33**: references the design files through a 1" = 50' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `SST(Sample)PKG.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SST(Sample)PKG-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 15 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 3 at the element the published leader touches, 12 at a point).

## Notes

- File names: `SST(Sample)PKG.rdraft` is the file name stamped in the sheet's margin (SST(Sample)PKG.dgn); design files take its project descriptor `Sample`.
- Scale: 1" = 50' comes from the graphic scale bar or the lettered scale note.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-Q-Signing-and-Pavement-Markings-Parking-Lot` (pipeline: examples/cfl_redraft/README.md).
