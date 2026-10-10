# Per-sheet settings

`<sheet>.json` (the split PDF's stem, e.g. `WFL-Plan-Profile-Sheets-p14.json`) adjusts how
`run_wfl.py` digitises and builds one sheet. Every key is optional. Without a file, a sheet
gets the defaults below.

| Key | Meaning | Default |
|---|---|---|
| `kind` | `"plan"`: design files plus a sheet file with a viewport. `"sheet"`: a sheet file only. | `plan` when the family is a plan family and an alignment with station ticks or a graphic scale bar in feet is found; else `sheet` |
| `family` | general, soq, typical, survey, qtab, plan-profile, approach, parking, site, layout, demolition, erosion, drainage, wall, detour, traffic, signing, details, xs, other | from the source PDF's name and the sheet title |
| `fpi` | Plan scale in feet per inch. | from the station tick spacing (the scale that letters the most ticks), else the graphic scale bar |
| `twist` | View twist, degrees CCW. | from a bearing lettered along a rebuilt alignment, else 0 |
| `calibration` | `[scale, ox, oy]`. A published point e (page inches) maps to (e − o) / scale. | fitted to the border frame; 1 : 1 for the full-size pages |
| `template` | `true` uses RoadDraft's WFL border and title block. `false` keeps the border as drawn. | `true` when the PROJECT / SHEET NUMBER block is where the template puts it |
| `sheet_regions` | `[[x0, y0, x1, y1], …]` in sheet inches (17 × 11, origin bottom left). Linework wholly inside stays on the sheet: insets, details, legends, tables on a plan sheet. | the profile grid below the plan view on plan-profile sheets |
| `plan_rect` | `[x0, y0, x1, y1]`: the plan view the viewport shows. | the frame above the profile divider, else the whole frame |
| `fields` | Title block values to use instead of what is read, e.g. `{"sheet_number": "D.5"}`. | read from the title block and the plot stamp |
| `no_alignments` | `true` skips rebuilding alignments from centerlines. | false |
| `drop_fonts` | Font name prefixes whose text-layer characters are dropped, e.g. `["*Times New Roman"]` for a page whose symbol glyphs come through as stray characters. | none |
| `skip` + `reason` | Leave the sheet out, with the reason in the manifest. | — |

Example:

```json
{"sheet_regions": [[10.5, 6.0, 16.3, 10.3]], "fpi": 40}
```
