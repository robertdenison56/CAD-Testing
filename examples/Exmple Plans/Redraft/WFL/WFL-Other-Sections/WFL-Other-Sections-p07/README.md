# WFL-Other-Sections-p07 -- redraft

WFL sample plan sheet **I.3** (945+82 CULVERT PLAN AND PROFILE), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Other-Sections-p07.pdf`.

| File | What it holds |
|---|---|
| `glac10-22_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `glac10-22_hyd_cor.rdraft` | **HYD** Drainage design file ("_hyd_cor"): the drainage system drawn heavy on the plan. |
| `glac10-22_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `glac10-22_hyd_pln_pp.rdraft` | Sheet **I.3** ("_hyd_pln_pp"): references the design files through a 1" = 10' viewport over the plan view (0.70-16.30 x 0.30-10.70 in; twist 0.000°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `glac10-22_hyd_pln_pp.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `glac10-22_hyd_pln_pp-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 17 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 13 at the element the published leader touches, 4 at a point).

## Notes

- File names: project prefix `glac10-22` from the project number (PRA GLAC 10(22)); the sheet's type suffix `_hyd_pln_pp` is the manual's.
- Scale: the sheet prints no numeric scale; 1" = 10' comes from the graphic scale bar or the config.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up).
- Station ticks: WFL draws them to one side of the line; RoadDraft's are centred on it, the same length.
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Other-Sections-p07` (pipeline: examples/wfl_redraft/README.md).
