# Redrafting the FDOT NexGen exhibit sheets

This pipeline turns an FDOT FDM 900-series exhibit sheet (the NexGen plans examples, split
one sheet per PDF out of `examples/Exmple Plans/2026fdmpart9nexgenplans.pdf`) into a
RoadDraft file set named per the FDOT CADD Manual's standard file names. It is the WFL
pipeline (`examples/wfl_redraft`) run under an FDOT standard: `wflsheet.digitise` and
`wflbuild.build` do the work, and this folder holds what FDOT does differently. Each sheet
gets its own folder under `examples/Exmple Plans/Redraft/FDOT-NexGen/<sheet>/`.

**Plan sheets** (a plan view at an engineering scale) get design files in model space and a
sheet file that references them, named `<type><discipline><sequence>` from the FDOT CADD
Standard File Name table (30 Sep 2021):

| File | Contents |
|---|---|
| `SURVRD01.rdraft` | Survey development model: existing features, meaning the sheet's thin dashed linework, and contour elevations. |
| `ALGNRD01.rdraft` | Alignment geometry: the centerlines rebuilt as design data from their station ticks and station numbers, with stationing lettered the FDOT way (the hundreds, `702`, beside each 100 ft tick). |
| `DSGNRD01.rdraft` | 2D plan, proposed: the proposed linework. References ALGNRD01 and SURVRD01. |
| `DRPRRD01.rdraft` | Drainage structures, proposed. FDOT cuts the drainage sheets from this file, so a drainage sheet stamped `DRPRRD01` owns the structures in its own model instead. |
| `<stamped name>.rdraft` | The plan sheet, named as the published sheet's margin stamps its own file (`PLPRRD02`, `DRPRRD01`, `RDXSRD03`, `KEYSRD06`, `PLANLD01`): border, title strip, viewport over the plan view, and every note, callout, table, the profile grid and symbol in sheet view. |

A sheet whose margin stamps the FDM's exhibit master file instead takes the table's name
for its kind: `TYPSRD01` typical sections, `GNNTRD01` general notes, `DRMPRD01` drainage
map, `UTADRD01` utility adjustments, `SSUVRD01` soil survey, `RPTBRD01` report of borings,
`SCGPRD01` / `SCGDRD01` selective clearing and grubbing, `CTLSRD01` project control,
`BHRSRD01` bridge hydraulics, `DROMRD01` optional materials, `SIGNRD01` signature sheets.
The model management sheet has no entry in the table and is `MDMGRD01`.

**Other sheets** (typical sections, notes, key and signature sheets, tabulations, profiles,
cross sections, borings) have no model, so they are a sheet file only. Key and signature
sheets carry their own border and keep it as drawn.

**Every folder also holds** a full-size PDF plot, a DXF, a PNG render, `-overlay.png` (the
published sheet in blue, the redraft in red, black where they agree) and a README.
`examples/Exmple Plans/Redraft/FDOT-NexGen/redraft-manifest.csv` lists every sheet and what
was built for it.

```bash
.venv/bin/python examples/fdot_redraft/run_fdot.py --all --workers 6             # every sheet
.venv/bin/python examples/fdot_redraft/run_fdot.py FDOT-915-1-Roadway-Plan-Profile  # some
.venv/bin/python examples/fdot_redraft/review.py FDOT-915-1-Roadway-Plan-Profile --bases
```

## What FDOT does differently

- **The border** is FDOT's 11 × 17 frame (0.8 in side margins, 0.3 in top and bottom) with
  the title strip across its foot: the revision block, the engineer of record, STATE OF
  FLORIDA / DEPARTMENT OF TRANSPORTATION with ROAD NO., COUNTY and FINANCIAL PROJECT ID,
  the sheet title and the SHEET NO.; the digital-signature rule runs up the right margin and
  the plot stamp (file and model, user, date, time) sits under the frame. RoadDraft's `fdot`
  title block template draws it, and the strip is read cell by cell.
- **Sheet families** come from the FDM exhibit number in the file name (913 typical
  sections, 915 plan-profile, 916 drainage network, 918 drainage map, 920 soils, 923
  utilities, 924 selective clearing and grubbing, 925 cross sections).
- **The centerline** is drawn at 0.6 pt, the same pen as the curb lines and finer than the
  FLH sheets' 1.2 to 1.56, so every solid line is a candidate and only the one with ticks and
  station numbers beside it fits. It is drawn in dashes 0.075 in apart, which are bridged.
- **The scale** is lettered beside the north arrow as `1"=50'` (or `1"=50`), and read from
  there when no graphic bar is drawn. An exhibit placed at an odd scale (the selective
  clearing plan says 1" = 80' but its station numbers sit 1.45 in apart) takes the scale
  its station numbers are lettered at.
- **Station numbers** (`702`) are lettered along the line just below each 100 ft tick, and
  the ticks straddle the line; a number is claimed only from within half an inch of it, since
  the curb lines run close by at 1" = 50'.
- **Bearings** are lettered in pieces whose italic advances overlap (`N59°59'28"` and its `W`
  as separate strings), joined before the view twist is read from them.
- **A straight centerline a leader's end touches** would be walked into the leader; a line
  over 5 in long is never a leader.
- **Screened references** (the roadway shown gray on a drainage sheet) letter in gray; that
  lettering is kept, where the WFL pipeline dropped only white lettering.
- **The profile grid** starts at a 0.48 pt line, not a heavy one; the divider is found as the
  top of a grid of full-width lines.
- **One oversize sheet** (the 48 × 36 landscape opportunity plan) keeps its own size and
  border.

Everything else is as in `examples/wfl_redraft/README.md`. Per-sheet settings are in
`configs/` (the keys are `examples/wfl_redraft/configs/README.md`'s).
