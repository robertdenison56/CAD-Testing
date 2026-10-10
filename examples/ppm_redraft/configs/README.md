# Per-sheet settings

`<PPM-nnn>.json` adjusts how `run_ppm.py` digitises and builds one sheet. Every key is
optional. Without a file, a sheet gets the defaults below.

| Key | Meaning | Default |
|---|---|---|
| `kind` | `"plan"`: base files plus a sheet file with a viewport. `"sheet"`: a sheet file only. | `plan` when the title block prints `SCALE: 1" = N'` and the family is a plan family; else `sheet` |
| `family` | layout, drainage, utility, stage, delineation, signs, electrical, planting, title, sections, orientation, profile, details, quantities | from the section and file name |
| `fpi` | Plan scale in feet per inch. | the printed scale |
| `twist` | View twist, degrees CCW. | from bearings lettered along a rebuilt alignment, else from the north arrow, else 0 |
| `calibration` | `[scale, ox, oy]`. A published point e (2 × page inches) maps to (e − o) / scale. | fitted to the border |
| `template` | `true` uses RoadDraft's Caltrans border and title block. `false` keeps the border as drawn. | `true` when the title block box is where the template puts it |
| `sheet_regions` | `[[x0, y0, x1, y1], …]` in sheet inches (34 × 22, origin bottom left). Linework wholly inside stays on the sheet: insets, details, legends, tables on a plan sheet. | none |
| `text_mode` | `"layer"` uses the PDF's text layer. `"strokes"` keeps the lettering as drawn strokes, for when the text layer is OCR and does not line up. | `layer` |
| `stroke_lettering` | `true` also finds lettering the text layer leaves out (clusters of letter-sized strokes) and keeps it on the sheet. | false |
| `fields` | Title block values to use instead of what is read, e.g. `{"sheet_id": "IP-4"}`. | read from the title block |
| `lw_scale` | Factor on every line width and dash, for PDFs drawn with inflated widths. | when the median width is over 3 (device units), 0.4 / the thinnest common width; else 1 |
| `char_map` | Extra text-layer character replacements, e.g. `{"Ã": "°"}`. | none |
| `no_alignments` | `true` skips rebuilding alignments from centerlines. | false |
| `skip` + `reason` | Leave the sheet out, with the reason in the manifest. | — |

Example (`PPM-130.json`):

```json
{"sheet_regions": [[3.2, 2.0, 12.5, 6.4]], "text_mode": "strokes"}
```
