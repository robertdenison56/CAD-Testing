# WFL-Plan-Profile-Sheets-p16 -- redraft

WFL sample plan sheet **D.7** (plan-profile), redrafted as a RoadDraft file set named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). Source: `Sheets/WFL/WFL-Plan-Profile-Sheets-p16.pdf`.

| File | What it holds |
|---|---|
| `SamplePlan_sur.rdraft` | **SUR** Survey file ("_sur"): existing features -- the sheet's dashed linework and contour elevations. |
| `SamplePlan_ali.rdraft` | **ALI** Alignments file ("_ali"): alignment(s) MAIN 01 rebuilt from the centerline, ticks and station numbers, with stationing. |
| `SamplePlan_cor.rdraft` | **COR** Corridor file ("_cor"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files. |
| `SamplePlan_pln_pp3.rdraft` | Sheet **D.7**: references the design files through a 1" = 50' viewport over the plan view (0.70-16.30 x 5.94-10.70 in; twist -34.287°); border, title block, notes, callouts, tables and the profile grid in sheet view. |
| `SamplePlan_pln_pp3.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |
| `SamplePlan_pln_pp3-overlay.png` | Check: published sheet blue, redraft red, black where they agree |

Callouts: 12 placed in sheet view with `place_callout` (0 at a stated station of a rebuilt alignment, 8 at the element the published leader touches, 4 at a point).

## Notes

- File names: `SamplePlan_pln_pp3.rdraft` from the plot stamp (SamplePlan_pln_pp3.dgn).
- The profile grid below the plan view is sheet linework; the viewport covers the plan view only.
- Scale: the sheet prints no numeric scale; 1" = 50' comes from the station tick spacing.
- Coordinates: the sample prints none for its linework; the model sits on a local datum (plan view centre at E 10,000 N 10,000), turned by the view twist so the lettered bearings read true.
- Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.
- No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).
- Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the drawn outlines agree).

Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p16` (pipeline: examples/wfl_redraft/README.md).
