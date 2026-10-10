# Redrafting the WFL sample plan sheets

This pipeline turns a WFL (FHWA Western Federal Lands) sample plan sheet, a vector PDF split
out of the sample plan sets in `examples/Exmple Plans/WFL Sample Plans`, into a RoadDraft
file set laid out the way the FLH OpenRoads Designer User Manual (chapter 3C, the WFLHD ORD
file naming convention) organises a project. It is the WFL counterpart of
`examples/ppm_redraft` (the Caltrans PPM sheets) and shares its extraction and digitising
helpers. Each sheet gets its own folder under
`examples/Exmple Plans/Redraft/WFL/<source set>/<sheet>/`.

**Plan sheets** (a plan view at an engineering scale) get design files in model space and a
sheet file that references them:

| File | Contents |
|---|---|
| `<prefix>_sur.rdraft` | Survey file: existing features, meaning the sheet's thin dashed linework, and contour elevations. |
| `<prefix>_ali.rdraft` | Alignments: the centerlines rebuilt as design data from their station ticks and station numbers, with stationing lettered the WFL way (a number square to the line at every 100 ft). |
| `<prefix>_cor.rdraft` | Corridor: the proposed linework (edges of pavement, construction and slope stake limits, symbols). References `_ali` and `_sur`. |
| `<prefix>_hyd_cor.rdraft` | Drainage design (functional code `hyd`). Only on drainage plans that draw a drainage system heavy. |
| `<prefix>_pln_<type>.rdraft` | The plan sheet (a `_pln` file): border, title block, viewport over the plan view, and every note, callout, table, the profile grid and symbol in sheet view. |

The prefix is the project's, as stamped in the published sheet's margin
(`SamplePlan_pln_pp1.dgn` → `SamplePlan`); sheets with an older stamp take the prefix their
project's other sheets stamp, else one made from the project number (`PFH 46-1(4)` →
`pfh46-1-4`). The sheet's type suffix is the stamped one (`_pln_pp1`, `_pln_typ`,
`_pln_qtab1`, `_pln_layout`), else the manual's for that kind of sheet (`_pln_gen`,
`_pln_typ`, `_pln_pp`, `_pln_qtab`, `_pln_ec`, `_pln_ttc`, `_pln_ptc`, `_pln_wall`,
`_pln_demo`, `_pln_misc`, `_xs`). Summary-of-quantities and survey-control sheets have no
suffix in the manual's table and get `_pln_soq` and `_pln_ctrl`.

**Other sheets** (title and index sheets, summaries and tabulations of quantities, typical
sections, cross sections, details, line graphs) have no model, so they are a sheet file only.

**Every folder also holds:**
- a full-size PDF plot, a DXF and a PNG render;
- `-overlay.png`: the published sheet in blue, the redraft in red, black where they agree;
- a README.

`examples/Exmple Plans/Redraft/WFL/redraft-manifest.csv` lists every WFL sheet, what was built
for it, and why a page was not redrafted.

```bash
.venv/bin/python examples/wfl_redraft/run_wfl.py --all --workers 6         # every sheet
.venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p14  # some sheets
.venv/bin/python examples/wfl_redraft/review.py WFL-Plan-Profile-Sheets-p14 --bases
```

## Stages

1. **Extract** (`ppm_redraft/extract_pdf.py`; needs `pdfplumber`, so it runs with the system
   `python3`). Every path is flattened to polylines with its line width, dash pattern and
   fill; every character of the text layer is kept with its origin, size and angle. The split
   WFL pages are full-size 17 × 11 prints, so the extract is in sheet inches as it stands.
   `run_wfl.py` caches the results in `examples/output/wfl_redraft/extract/`.
2. **Calibrate** (`wflsheet.calibrate`). The border's heavy frame (0.7 / 0.3 in from the
   sheet edges) gives the scale and offset; one reduced page (F.8, a 13.3 × 8.6 in print whose
   second-font copies of bold letters carry garbage sizes and are dropped) needs it, the rest
   are 1 : 1.
3. **Digitise** (`wflsheet.py`). Each stroke and string is sorted by where it belongs:
   - **Lettering.** The text layer is real text (TrueType, printed over its own filled
     outlines), so it is trusted: the outlines are dropped. MicroStation sizes text by its
     capital height, so a character's size is its cap height, and the outlines confirm it.
     A sheet whose lettering is not outlined (a summary of quantities or a survey control
     table made from a spreadsheet) carries ordinary PDF font sizes, so there the cap height
     is taken as 0.72 of the size. Bold strings are printed two or three times a hair apart,
     and once more in a second font, and bold linework twice over itself; one copy of each
     character and stroke stays (a leader drawn twice has no free end to follow).
   - **Title block.** Values are read where RoadDraft's WFL template puts them: the PROJECT
     and SHEET NUMBER block at the top right (and a STATE column on the older border), the
     NPS PMIS and drawing numbers above the frame, the plot stamp up the left margin (date and
     time, file name, `[description]`, and the designed-by / checked-by note on the older
     border), the sheet title box at the bottom right and the NO SCALE note beside it.
     Plan-profile sheets have no title box. A portrait cross-section sheet keeps its border as
     drawn.
   - **Callouts:** each one's text block, landing, leader and branches, and the arrowhead, are
     found by following the thin leader linework from a text's underline or landing
     (`ppm_redraft/leaders.py`). WFL draws the landing and the leader as separate strokes, a
     bold note's underline in a heavier pen, and its blanks (a table's `____`) as bare
     underlines; the thin pens are passed through, and a landing with no leader is not a
     callout. The lines of one note sit at the engine's line spacing; a wider gap (past an
     underline) starts a separate note that stays where it is lettered. The callout is placed
     with the whole note (so a `"MAIN 01" 110+05.00` line finds its station anchor), then
     its text is cut to the head line and the lines under it are lettered at their own
     sizes and places, so a note whose station line is smaller than its title reads as
     published.
   - **Alignments (plan sheets).** The heavy solid linework is chained and split into
     tangents and curves. WFL draws its 100 ft ticks from the centerline out to one side, and
     letters the station number ("111", "112") square to the line at a fixed offset, often
     well clear of it; both are found that way. Nothing prints a numeric scale, so the scale
     is the one, of the usual engineering scales, that letters the most ticks; a plan without
     an alignment takes its scale from the graphic scale bar ("Scale in feet"). A
     `"NAME" Line to be constructed` callout names the alignment, a bare `"NAME"` failing that.
     A bearing lettered along a tangent gives the view twist.
   - **Plan sheets: what each line is.** The profile grid below the plan view (and anything
     in a configured `sheet_regions` box) stays on the sheet, as do tags and symbols. Thin
     dashed linework is existing (`_sur`). On a drainage plan the heavy solid linework is the
     drainage system (`_hyd_cor`). Everything else is proposed (`_cor`). Small symbols follow
     the line they sit on.
4. **Build** (`wflbuild.py`). Files are written through the RoadDraft command bus:
   `create_alignment`, `draw_alignment`, `annotate_stationing` (then each station label is
   relettered as the sheet letters it); `attach_reference`, `create_sheet` (ANSI B, the `wfl`
   title block template), `fill_title_block`, `create_viewport` over the plan view;
   `place_callout` aimed by `target_anchor` at a stated station of a rebuilt alignment, by
   `target_entity` (found with `hit_test`) at the element the leader touches, or by point.
   Bulk linework and lettering run the drawing commands' handlers directly.
5. **Check** (`run_wfl.overlay`, `review.py`). The sheet is plotted and overlaid on the
   published sheet, registered to the same paper.

Per-sheet settings are in `configs/` (see `configs/README.md`).

## Known limits

- **Station ticks:** WFL draws them to one side of the line; `annotate_stationing` centres
  them on it, at the same length.
- **Coordinates:** the sample sheets print survey coordinates only in callouts and the survey
  control table, not for their linework, so each plan sits on a local datum (plan view centre
  at E 10,000, N 10,000), turned by the view twist.
- **Profiles** are kept as sheet linework in the profile grid, not as RoadDraft profiles.
- **Raster pages** (one, F.11 of the parking lot set) have no vector linework and are listed
  in the manifest as not redrafted.
- **Sheets with several plan panels** (the three approach roads on E.1 of the other-sections
  set, the two panels of the erosion control plan F.2) get one viewport over the whole plan
  band, so their panels sit side by side in one model on the local datum; E.1's panels carry
  no station ticks the fit can read, so that sheet is a sheet drawing.
- **Alignments without a name** on the sheet are called CL1, CL2, ...; FLH's ORD feature
  names (ALI_MAIN_01) are not lettered on the plans.
- **Fonts:** the sheets letter in Times, Arial and Verdana; RoadDraft's renderer has one font,
  so the plotted lettering runs a little wider than the published.
