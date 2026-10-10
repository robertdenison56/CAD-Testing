# Redrafting Caltrans PPM example sheets

This pipeline turns a published PPM example sheet (a vector PDF) into a RoadDraft file set
laid out the way the Caltrans CADD Users Manual describes. Each sheet gets its own folder
under `examples/Exmple Plans/Redraft/` with these files:

- **`<project>bb01.rdraft`** is the Master Topographic file: existing features.
- **`<project>aa01.rdraft`** is the Master Design file for the roadway: alignments as design data, and the proposed linework. It references bb01.
- **`<project>aa02.rdraft`** is the drainage base, created only when the sheet shows drainage.
- **`<project><code><nnn>.rdraft`** is the contract plan sheet. It references the base files, clips them at the match lines, and holds every note, callout, table and symbol in sheet view.
- **Outputs and records:** a full-size PDF plot, a DXF, a PNG, an overlay against the published sheet, and a README listing what was rebuilt and how it differs.

Sheet L-4 (`PPM-048`, "65 LAYOUT-4") is the first one done:

```bash
.venv/bin/python examples/ppm_redraft/make_l4.py
```

## Stages

1. **Extract** (`extract_pdf.py`, needs `pdfplumber`, so run it with the system `python3`). Every path is flattened to polylines in sheet inches, keeping its line width, dash pattern and fill. Every character of the PDF's text layer is kept with its origin, size and angle. The result is checked in gzipped (`ppm048_l4.extract.json.gz`), so the remaining stages run in the RoadDraft venv alone.
2. **Calibrate** (`l4_geometry.py`). The PPM PDFs are 11 × 17 prints shrunk to 95.4 % of half size. The border lines give the scale and offset back to a 34 × 22 sheet. The design data the sheet prints (and its neighbours' BC/EC stations) give the alignments. The station ticks and the fitted curve fix the sheet↔model transform and view twist.
3. **Digitise** (`digitize_l4.py`; helpers `sheetgeom.py`, `textruns.py`, `leaders.py`). Each stroke and string is sorted by where it belongs:
   - **Glyph strokes** are dropped; the PDF's text layer gives the strings instead. A few corrupt text-layer strings are re-entered by hand in `BROKEN`.
   - **Callouts:** each one's text block, landing, leader branches, tip squiggles and arrowheads are found by following the thin leader linework from a text's underline or landing.
   - **Rebuilt from design or as sheet objects:** match lines, curve bubbles, station ticks, POT/POC/EC marks, the table and the north arrow.
   - **Existing vs proposed:** what is left goes by Caltrans line style. Dotted linework is existing (bb01). Solid and dashed linework is proposed (aa01). Small symbols follow the line they sit on.
4. **Build** (`build_l4.py`). The three files are written through the RoadDraft command bus, the same commands an agent sends over MCP:
   - **Alignments and annotation:** `create_alignment`, `draw_alignment`, `annotate_stationing` and `place_label` build the alignments and their lettering.
   - **Base-file linework:** `draw_polyline` puts the digitised linework into model space on its layers.
   - **The sheet:** `attach_reference` (with clip), `create_sheet`, `fill_title_block` and `create_viewport` set it up.
   - **Callouts:** `place_callout` is aimed by `target_anchor` where the text states a station and offset, by `target_entity` (found with `hit_test` on the clipped reference) where the leader touches an element, or by point where it ends on an area. The callout's shoulder is the Caltrans underline, and its text is returned to its published position.
5. **Check** (`make_l4.py`, `overlay.py`). The driver reloads the sheet file, plots it, exports DXF, and overlays the result on the published sheet registered to the same paper.

`examples/output/ppm_redraft/` (git-ignored) holds the intermediate `l4_digitized.json`.

## Taking it to the other sheets

The `l4_*` modules hold everything specific to L-4:
- the calibration and design data;
- the broken text-layer strings;
- the match-line polylines;
- the text classes: which names are topo, which are design labels.

The extract, glyph, leader, callout and build machinery is general. Each further sheet needs its own small geometry module and a check of the overlay.
