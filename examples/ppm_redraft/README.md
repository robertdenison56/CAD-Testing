# Redrafting Caltrans PPM example sheets

This pipeline turns a published PPM example sheet (a vector PDF) into a RoadDraft file set
laid out the way the Caltrans CADD Users Manual describes. Each sheet gets its own folder
under `examples/Exmple Plans/Redraft/Caltrans-PPM/<section>/<sheet>/`.

**Plan sheets** (a plan view at an engineering scale) get base files in model space, and a
sheet file that references them:

| File | Contents |
|---|---|
| `<project>bb01.rdraft` | Master Topographic ("bb"): existing features, meaning the sheet's dotted linework, and contour elevations. |
| `<project>aa01.rdraft` | Master Design, roadway ("aa"): alignments rebuilt as design data, with stationing; the proposed linework. It references bb01. |
| `<project>aa02.rdraft` | Drainage. Only where a drainage plan draws a drainage system. |
| `<project><code><nnn>.rdraft` | The contract plan sheet, named with the CADD manual's print sequence code (`ea` Layout, `ia` Drainage Plan, `ka` Utility Plan, `ma` Stage Construction, `na` Pavement Delineation, …) and sheet number. It holds the border, title block, viewport, and every note, callout, table and symbol in sheet view. |

**Other sheets** (typical sections, profiles, details, quantities, legends, title sheets) have
no model, so they are a sheet file only.

**Every folder also holds:**
- a full-size PDF plot, a DXF and a PNG render;
- `-overlay.png`: the published sheet in blue, the redraft in red, black where they agree;
- a README.

`examples/Exmple Plans/Redraft/Caltrans-PPM/redraft-manifest.csv` lists every PPM sheet, what was built for it, and why scanned pages were not redrafted.

```bash
.venv/bin/python examples/ppm_redraft/run_ppm.py --all --workers 8   # every vector sheet
.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-095 PPM-112       # some sheets
.venv/bin/python examples/ppm_redraft/review.py PPM-095 --bases        # review images
.venv/bin/python examples/ppm_redraft/make_l4.py                       # PPM-048 (L-4), hand-built
```

## Stages

1. **Extract** (`extract_pdf.py` and `pdfclip.py`; needs `pdfplumber`, so run it with the system `python3`).
   - Every path is flattened to polylines, keeping its line width, dash pattern and fill colour.
   - Linework drawn inside a clipping path, such as a hatch clipped to its area, is cut to the clip. pdfminer itself ignores clipping.
   - Every character of the PDF's text layer is kept with its origin, size and angle.
     - Text turned a quarter turn takes its size from its box.
     - On other rotated or skewed text the reported size can't be trusted. There, the size comes from the character's advance and its width in ems, measured on the same character set upright.
   - `run_ppm.py` caches the results in `examples/output/ppm_redraft/extract/`.
2. **Calibrate** (`calibrate.py`). The PPM PDFs are reduced prints, and different pages are reduced differently. The Caltrans border's heavy frame gives the scale and offset back to a 34 × 22 sheet.
3. **Digitise** (`ppmsheet.py`; helpers `sheetgeom.py`, `textruns.py`, `leaders.py`, `alignfit.py`). Each stroke and string is sorted by where it belongs:
   - **Lettering:**
     - Characters join into a string while each starts a little further along than the last. Kerning often pulls a letter well inside the previous one's advance.
     - Glyph strokes are dropped, and the text layer gives the strings.
     - Text-layer strings with corrupt matrices are recovered from their own strokes, or kept as strokes.
     - Where a sheet's text layer is OCR, the strokes are kept (`text_mode: strokes`).
   - **Title block:** values are read where RoadDraft's Caltrans template puts them (Dist, County, Route, post miles, sheet title, scale, sheet ID, unit, project number, user and DGN names, plot date). A non-standard border is kept as drawn.
   - **Callouts:** each one's text block, landing, leader and branches, and the tip squiggles and arrowheads, are found by following the thin leader linework from a text's underline or landing.
   - **Alignments (plan sheets):**
     - The centerline is chained and split into tangents and curves. A line drawn twice is kept once, and a chain that doubles back on itself is split where it turns.
     - Its 100 ft ticks and the station numbers beside them (`675`, `6`, `7`, …) give the stationing. A tick may be drawn whole, as two halves (one each side of the line), or in the centerline's dash pattern.
     - Pieces that meet end to start, with the stationing running on, are one alignment: a centerline breaks where three lines meet.
     - A `"NAME" LINE` label names it, even when the text layer letters it in pieces. A name belongs to the nearest line only.
     - A bearing lettered along a tangent gives the view twist, so the model reads true bearings. Without one, the north arrow gives it. The arrow is a circle with a shaft through it; the head's hatch strokes are graded and the tail's feathers are all one length.
     - Where the lettering stays as strokes, the sheet's own ticks and numbers stay as drawn, and the stationing is not lettered again.
   - **Plan sheets: what each line is.**
     - **On the sheet:** tags (circles and hexagons round a number), north arrows, travel arrows, match lines, and `sheet_regions` (tables, legends, insets).
     - **Existing (BB01):** dotted linework.
     - **Drainage (AA02):** on drainage plans, the heavy non-centerline linework.
     - **Proposed (AA01):** everything else.
     - **Small symbols** follow the line they sit on.
4. **Build** (`ppmbuild.py`). Files are written through the RoadDraft command bus:
   - **Alignments:** `create_alignment` (elements), `draw_alignment`, `annotate_stationing`.
   - **The sheet:** `attach_reference`, `create_sheet`, `fill_title_block`, `create_viewport`.
   - **Callouts:** `place_callout` is aimed by `target_anchor` at a stated station and offset of a rebuilt alignment, by `target_entity` (found with `hit_test`) at the element the leader touches, or by point.
   - **Bulk linework and lettering** run the drawing commands' handlers directly. The bus would snapshot the whole document for undo on every one of tens of thousands of strokes.
5. **Check** (`overlay.py`, `review.py`). The sheet is plotted and overlaid on the published sheet, registered to the same paper.

Per-sheet settings are in `configs/` (see `configs/README.md`).

## PPM-048 (L-4), hand-built

L-4 was the trial sheet, built from sheet-specific modules: `l4_geometry.py`, `digitize_l4.py` and `build_l4.py`, driven by `make_l4.py`. There, the design data was typed from what the sheets print (curve data, BC/EC stations from L-2 and L-5), and the references are clipped at the match lines. The extract it reads is checked in as `ppm048_l4.extract.json.gz`.

## Known limits

- **Scanned pages** (40 of the 226) are raster images with no vector linework. They are listed in the manifest as not redrafted.
- **Text size:** text heights are the Caltrans values, but RoadDraft's renderer draws a height as the font size, so the PNG and PDF lettering looks smaller than the Caltrans font. The DXF carries the true heights.
- **Coordinates:** the examples print none. Each plan sheet's model sits on a local datum (sheet centre at E 10,000, N 10,000), turned by the view twist.
