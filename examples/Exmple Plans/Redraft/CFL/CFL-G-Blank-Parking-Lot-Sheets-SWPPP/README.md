# CFL-G-Blank-Parking-Lot-Sheets-SWPPP -- redraft

CFL sample plan sheet **ECP(PKG)** (PARKING LOT SWPPP), redrafted as a RoadDraft file set named per the CFL file naming convention (XXX(YYYY)ZZZZZ_NN: file type, alignment, project, counter). Source: `Sheets/CFL/CFL-G-Blank-Parking-Lot-Sheets-SWPPP.pdf`.

| File | What it holds |
|---|---|
| `TERPKG.rdraft` | **SUR** Terrain file (TER): existing features -- the sheet's dashed linework and contour elevations. |
| `ALIPKG.rdraft` | **ALI** Alignment design file (ALI): alignment(s) CL1 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `CORPKG.rdraft` | **COR** Corridor file (COR): the proposed linework (edges, limits, slope stakes, symbols). References the ALI and TER files. |
| `ECP(PKG).rdraft` | Sheet **ECP(PKG)**: references the design files through a 1" = 50' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `ECP(PKG).pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `ECP(PKG)-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 1 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 0 at the element the published leader touches, 1 at a point).

## Notes

- File names: `ECP(PKG).rdraft` is the file name stamped in the sheet's margin (ECP(PKG).dgn); design files take its project descriptor `PKG`.
- Scale: the sheet prints no numeric scale; 1" = 50' comes from the station tick spacing.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/cfl_redraft/run_cfl.py CFL-G-Blank-Parking-Lot-Sheets-SWPPP` (pipeline: examples/cfl_redraft/README.md).
