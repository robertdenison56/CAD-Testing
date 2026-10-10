# Caltrans PPM example sheets, redrafted in RoadDraft

Each PPM example sheet in `examples/Exmple Plans/Sheets/Caltrans-PPM/` has a folder here
under the same PPM section (`2-2.05-Layouts-…/PPM-048-…/`). A folder holds the sheet as a
RoadDraft file set, laid out the way the Caltrans CADD Users Manual lays out a project.

`redraft-manifest.csv` lists every sheet, what was built for it, and the files' names.

## Files in a folder

Names follow the CADD Users Manual (2.2): the 10-digit project number from the title block,
then a two-letter code. The examples print no project number, so most files start
`0000000000`.

| File | What it is |
|---|---|
| `<project>bb01.rdraft` | **Master Topographic** ("bb", 3.8): the existing features. This is the plan's dotted linework (existing roads, edges, fences, railroad, contours) and the contour elevations. |
| `<project>aa01.rdraft` | **Master Design, roadway** ("aa", 3.8): the alignments, rebuilt as design data from the centerline, its 100 ft ticks and its station numbers, with stationing; and the proposed roadway linework. It references bb01. |
| `<project>aa02.rdraft` | **Drainage**: the drainage system that a drainage plan draws heavy (pipes, culverts, inlets). Only drainage plans have one. |
| `<project><code><nnn>.rdraft` | **The contract plan sheet**. `<code>` is the print sequence code for the sheet ID (2.1), and `<nnn>` is the sheet number: `ea004` is L-4, `ia004` is D-4, `ka001` is U-1. The sheet has the border and title block. It references the base files through a viewport at the plan scale. Every note, callout, table, legend, match line, north arrow and tag is placed in sheet view, and callout leaders point at the referenced geometry. |
| `<sheet>.pdf`, `.dxf`, `.png` | The sheet plotted full size (34 × 22), exported to DXF, and rendered. |
| `<sheet>-overlay.png` | A check image: the published sheet in blue, the redraft in red, black where they agree. |
| `README.md` | What was built for that sheet, and its notes. |

Sheets that are not plans have no model to reference, so their folder holds a sheet file
only. This covers typical sections, profiles, superelevation diagrams, construction
details, quantities, legends and title sheets.

### Print sequence codes used

| Sheet ID | Code | Sheet | | Sheet ID | Code | Sheet |
|---|---|---|---|---|---|---|
| (title) | `ab` | Title sheet | | U | `ka` | Utility plan |
| X | `ca` | Typical cross sections | | CS | `la` | Construction area signs |
| K | `da` | Key map | | MI | `lb` | Motorist information |
| L | `ea` | Layout | | SC | `ma` | Stage construction |
| P | `fa` | Profile | | TH | `md` | Traffic handling |
| SE | `fc` | Superelevation diagram | | DE | `mg` | Detour |
| C | `ga` | Construction details | | PD | `na` | Pavement delineation |
| D | `ia` | Drainage plan | | S | `oa` | Sign plan |
| DP | `ib` | Drainage profile | | SQ | `od` | Sign quantities |
| DD | `ic` | Drainage details | | Q | `pa` | Summary of quantities |
| DQ | `id` | Drainage quantities | | IP | `sp` | Irrigation plan |
| E | `ua` | Electrical plan | | PP | `su` | Planting plan |
| ED | `ub` | Electrical details | | EQ | `uc` | Electrical quantities |

A sheet whose ID the pipeline could not read is named with `zz`.

## Opening the files

Open the sheet file (`…ea004.rdraft`) in RoadDraft. It loads its base files from the same
folder, so keep each folder's files together. The base files can be opened on their own
to work in model space.

## How they were made

L-4 (PPM-048) was drafted first, as the trial. Its design data was typed from what the
sheets print: curve data, and BC and EC stations from L-2 and L-5. Its references are
clipped at the match lines.

The other sheets were digitised from the PDFs' vector linework and text layer, by the
pipeline in `examples/ppm_redraft/` (see its README). A sheet is rebuilt with:

```bash
.venv/bin/python examples/ppm_redraft/run_ppm.py PPM-095
```

## Limits

- **Scanned pages:** 40 of the 226 PPM pages are scans, with no vector linework. They are listed in the manifest as not redrafted.
- **No real coordinates:** the examples print none. A plan sheet's model sits on a local datum, with the sheet centre at E 10,000, N 10,000. The model is turned by the view twist, taken from a bearing lettered along a tangent or from the north arrow, so that bearings read true.
- **What is rebuilt as design data:** alignments are rebuilt where a sheet draws a centerline with lettered station ticks. Everything else is linework on the CADD levels: proposed, existing and drainage.
  - Where a line's name label can't be read, the alignment is named `CL1`, `CL2`, ….
  - Some pages' text layer is OCR without the station numbers (stage construction, traffic handling). There the centerline stays as linework.
- **Lettering drawn as strokes:** some pages have a text layer that came from OCR or does not line up, and some letter text without a text layer at all. There the lettering is kept as the drawn strokes, on the sheet.
- **Text size on screen:** text heights are the Caltrans values. RoadDraft's renderer draws a height as the font size, so lettering in the PNG and PDF looks smaller than in the Caltrans font. The DXF carries the true heights.
- **Source duplicates:** PPM-221 and PPM-223 are the same page (ED-49) in the source set, so they give the same redraft.
- **Symbols built from pieces:** a tag or sign-number oval drawn as separate lines and arcs is not recognised as a tag. Its shape and leader stay in the base file as linework. The same goes for a fan of leaders from one label to several plants (planting plans), and for match lines drawn as separate solid dashes. Per-sheet configs keep the clear cases on the sheet.
- **Wipeouts:** white masks that hide linework on the published sheet are dropped (RoadDraft has no wipeout), so the few lines they covered show in the redraft.
- **Two-panel plans:** PPM-227 shows two stretches of road at different stations on one sheet. Its second panel is kept on the sheet as linework, since one viewport can show only one place in the model.
- **Hidden content:** PPM-078 has two lines that the PDF hides (probably optional content), which the redraft draws.
