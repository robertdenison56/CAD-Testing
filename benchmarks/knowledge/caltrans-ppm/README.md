# Caltrans Plans Preparation Manual (PPM)

The presentation standard for Caltrans contract plans: "how Caltrans presents a project for
bidding and construction" (foreword). It is the source the RoadDraft drafting spec was flavored
from, so it is the first collection in the eval knowledge base. Two volumes:

| id | what | pages | edition |
|---|---|---|---|
| `ppm-text` | the manual: policies, drafting standards, per-sheet-type content and checklists | 285 | compiled PDF "last updated April 14, 2023", foreword May 2026; each section carries its own revision date (2008 to 2022) |
| `ppm-examples` | one annotated example plan sheet per page (22 × 34 borders, Caltrans cell library) | 264 | "Examples - Revised December 2024"; each sheet carries its RELEASED date |

Source: https://dot.ca.gov/programs/design/manual-plans-preparation-manual-ppm (Caltrans Division of
Design, Office of CADD & Engineering GIS Support). Copyright Caltrans; held for reference only.

Reading them here: `ppm-text.txt` is the manual in reading order with a separator line per page;
`ppm-examples.txt` is the annotation text of every example sheet (searchable, not viewable). To
see a sheet, read the page from the PDF in `raw/` (for example page 45 for "65 LAYOUT-1"), or

```bash
pdftoppm -f 45 -l 45 -r 100 -png benchmarks/knowledge/caltrans-ppm/raw/ppm-examples-all-with-titlesheet.pdf /tmp/layout1
```

Citation form used in the spec and plans: `ppm-text p. 2-8 (pdf 21)`, `ppm-examples pdf 45 "65 LAYOUT-1"`.

## Section map, text volume

PPM pages are chapter-relative ("2-8"); PDF pages are absolute. Chapter 2 was renumbered section by
section, so 2-2.6 onward still carries the old page numbers (the TOC on pdf 3 explains the overlap).

| PPM section | PPM pages (pdf) | revised | covers |
|---|---|---|---|
| Foreword, TOC | pdf 1–7 | May 2026 / Sept 2018 | scope; blue text marks changes |
| 1-1 General | 1-1 – 1-6 (pdf 8–13) | March 2018 | boldface / underlined / permissive standards; **1-1.3 line work, uppercase text, "Caltrans does not draw to scale, it only plots to a given scale"**; CADD file conventions |
| 2-1.1 Composition of project plans | 2-1 – 2-3 (pdf 14–16) | Sept 2018 | what a plan set contains; right of way; railroad |
| **2-1.2 Drafting standards** | 2-4 – 2-5 (pdf 17–18) | Sept 2018 | line weights, abbreviations, **text placement and reading direction (Figure 2-1)**, match lines at +50, leaders, begin/end of bid items by plus station and offset |
| **2-1.3 U.S. customary unit standards** | 2-6 – 2-8 (pdf 19–21) | Sept 2018 | dimensions, **bearings (DMS plus direction)**, cross slopes, **scales (only 1"=20', 50', 100' for plan view)**, contour intervals, **stationing (100 ft stations, 500 ft full annotation, tick length, annotation below the line)**, units |
| 2-1.4 Standard plans | 2-8 – 2-10 (pdf 21–23) | Sept 2018 | standard plan sections A, P, C, D, H, T, B, RS, S, ES |
| **2-1.5 Plan border sheets** | 2-11 – 2-20 (pdf 24–33) | Sept 2018 | Figures 2-2A to 2-2J: title, generic and plan-and-profile borders; **22" × 34" border, nothing outside it, sheet name and ID code lower right, ~1500 ft of stationing per sheet at 1"=50'** |
| 2-1.6 Signatures and development names | 2-21 – 2-36 (pdf 34–49) | Sept 2018 | title-sheet and plan-sheet signature blocks (Figures 2-3 to 2-11) |
| 2-1.7 Project identification block | 2-37 – 2-51 (pdf 50–64) | Sept 2018 | Dist / County / Route / Post Miles block; project case designations 1A–4; county abbreviations |
| **2-1.8 Sheet ID codes and plan order** | 2-52 – 2-53 (pdf 65–66) | Sept 2018 | **sheet name + ID code (L-1, L-2 …) required on every sheet but the title sheet, lower right inside the border**; "APPROVED FOR … WORK ONLY" |
| 2-1.9, 2-1.10 Submittals, file formats | 2-54 – 2-55 (pdf 67–68) | Sept 2018 | |
| 2-2.1, 2-2.2 Title sheets | 2-57 – 2-70 (pdf 70–99) | June 2020 | title sheet mapping, location map, index of plans, project descriptions, begin/end of construction, title sheet checklist (pdf 96–98) |
| 2-2.3 Typical cross sections | 2-71 – 2-76 (pdf 100–105) | | checklist pdf 103–104 |
| 2-2.4 Project orientation | 2-77 – 2-80 (pdf 106–109) | Dec 2016 | key map and line index, project control, monumentation |
| **2-2.5 Layouts, profiles, superelevation** | 2-81 – 2-97 (pdf 110–126) | June 2020 | **general (pdf 110–111), preparation (111–112), plan content (112–114), profile content (114–116), superelevation (116–117); checklists: layout sheet (pdf 118–120), profile (122–123), superelevation diagram (125)** |
| 2-2.6 – 2-2.24 per sheet type | old numbering (pdf 127–227) | 2016–2022 | construction details, water pollution control, erosion control, contour grading, drainage, subsurface drains, sanitary sewer, utilities, construction area signs, motorist information, stage construction / traffic handling, pavement delineation, signs, summary of quantities, retaining walls, sound walls, landscape, electrical, structures |
| 2-3 Processing after PS&E | 2-145 – 2-148 (pdf 228–231) | | draft contract ready, RTL, as-awarded, CCO, as-builts |
| 3 Preliminary drawings | 3-1 – 3-10 (pdf 232–241) | July 2015 | strip maps, route adoption, freeway agreement exhibits, PUC exhibits |
| 4 Right of way engineering mapping | 4-1 – 4-44 (pdf 242–285) | Jan 2008 | map types 4-2 to 4-16; Appendix 4A abbreviations |

## Section map, examples volume

| group | pdf pages | sheets |
|---|---|---|
| Title sheets | 2–33 | Examples A (basic format), A1 (signatures), B (consultant), C–Y (project cases), state location maps (6), locations-of-construction sheets; ab-65 title, ac-65 index |
| Typical cross sections | 34–40 | generic sheet with instructions, tapered edge, Example A, 65 XSEC-1/2/3/16 |
| Project orientation | 41–44 | Examples A, B, 65 key map / line index, **Project Control Sheet Example A (44)** |
| **Layouts, profiles, superelevation** | 45–71 | **Route 65 layouts LAYOUT-1, 2, 3, 4, 5, 7, 38, 39, 40, 80 (45–54)**; Profile P-8 (55); Profile and Superelevation PS-1, 2, 3, 46, 47, 48 (56–61); **Generic Project Border Sheet (62)**; **Generic Project Plan View Sheet, basic required information (63)**; generic superelevation diagrams 1–5 (64–68); grade separation plan sheets (69–70); Layout Example A, indeterminate R/W (71) |
| Construction details | 72–83 | curb ramp standards, 65 C-1 / C-22 / C-44 |
| Erosion control | 84–92 | legend basics, EC examples A–C |
| Drainage | 93–109 | 65 D, DP, DD, DQ sheets; basic required information (108–109) |
| Utilities | 110–115 | generic sheet with instructions, 65 U and UP sheets |
| Construction area signs, motorist information | 116–126 | |
| Stage construction, traffic handling | 127–153 | generic basics, 70 SC-1…17, 121 TH-1…6, quantities |
| Pavement delineation, signs | 154–185 | 65 PD sheets, delineation and sign examples |
| Summary of quantities | 186–191 | |
| Landscape, irrigation, planting | 192–204 | |
| Electrical systems | 205–231 | |
| Chapter 3 maps and exhibits, R/W samples | 232–264 | pages 249–259 have no bookmark; 19 pages are scanned images with no extractable text (listed in the manifest) |

The "Route 65 Bypass" sheets are one project drawn across every sheet type, so a layout, its
profile, its drainage plan and its delineation plan can be compared for the same stationing.

## What the PPM says about the D1 deliverable

The D1 task is a single plan sheet: alignment linework, station ticks and labels, PC/PT labels,
tangent bearings, a curve table, title block, north arrow (`DRAFTING_SPEC_V1`, eval plan §3.4).
Each row cites where the PPM states the corresponding requirement.

| spec element (draft-v1) | PPM | where |
|---|---|---|
| `sheet.size` ANSI D | 22" × 34" outside border line for a full-size plot; never extend drawing, tables or notes beyond the border or into the margin | ppm-text p. 2-20 (pdf 33), Figure 2-2J |
| `allowed_feet_per_inch` [50, 100] | plan view sheets use 1"=50' (Caltrans base scale) in urban and some rural areas, 1"=100' in rural areas, 1"=20' for detail; "the only scales to be used for plan view sheets" | p. 2-7 (pdf 20) "Scales"; p. 2-81 (pdf 110) |
| `scale_text_format`, D1-10 | `SCALE: 1" = 50'` with a colon, centered below the sheet name, TX=8.75 FT=3 WT=2 on border_INSIDE-BORDER-anno | p. 2-89 (pdf 118); ppm-examples pdf 63 |
| `north_arrow`, D1-11 | standard north arrow cell AC=NARR on pp_PRESENTATION; preferred location upper right of the sheet within the clip frame | p. 2-89 (pdf 118); ppm-examples pdf 63 |
| `stationing`, D1-02, D1-03 | 100 ft per station; **full annotation at 500-ft stations (multiples of 5), a single digit (the ones column) at 100-ft stations, no "+00" on whole stations**; precise stations at equations, BCs, ECs and POCs to 0.01 ft; **ticks centered on the alignment line, 7.0 ft long at 1"=50' and 14.0 ft at 1"=100' (0.14 in on paper), no minor ticks; annotation below the line, about half the text height below the tick**, moved further down or above only to avoid a feature | p. 2-8 (pdf 21) "Stationing"; ppm-examples pdf 63; drawn on pdf 45 |
| `labels.pc_pt`, D1-04 | curve points are labeled **BC / EC** (begin / end of curve), station plus line designation, reading bottom to top along a line perpendicular to the alignment: `"TB1" 644+45.25 EC` | p. 2-4 (pdf 17) "Placement of text"; ppm-examples pdf 45 |
| `labels.bearing`, D1-05 | bearings for all alignments in degree-minute-second plus direction; **bearing and distance of every tangent** on all stationed lines, typically above the alignment line: `N 04°56'15" E 426.51'` | p. 2-6 (pdf 19) "Bearings"; p. 2-89 (pdf 118); ppm-examples pdf 45 |
| `labels.mc`, `curve_table`, D1-06 | alignment data for every stationing line must be shown: equations, tangent distances and bearings, stations of all curve points, curve data. A **CURVE DATA** table with columns **No., R, Δ, T, L**; curve numbers consecutive per station line, never restarted on the next sheet, never duplicated; on the plan each curve carries its circled number. Northing/easting of BCs and ECs optional in the table | p. 2-85 (pdf 114); checklist p. 2-90 (pdf 119); ppm-examples pdf 45, 63 |
| `labels.equation` | station equations are required plan content | p. 2-85 (pdf 114); p. 2-89 (pdf 118) |
| line designation | the station line is named on the plan (`"D13" LINE`, `ROUTE 65`) above the line, TX=8.75 FT=3 WT=2 on align_MAIN-anno (16) | p. 2-89 (pdf 118); ppm-examples pdf 45 |
| `text` heights | uppercase text throughout; sizes are given as **TX values in feet at the 1"=50' base scale**: TX=7.0 (0.14 in) for station and project-ID text, 8.75 (0.175 in) for scale, route and line names, 10 (0.20 in) for emphasized routes, 14.5 (0.29 in) for the sheet name. Fonts FT=3 (normal) and FT=43 (bold) | p. 1-1 (pdf 8); p. 2-4 (pdf 17); p. 2-89 – 2-90 (pdf 118–119); ppm-examples pdf 2 (TX / AS note), 63 |
| D1-08 legibility | text placement must not break line work or shapes or interfere with other text; text goes above the line work when no leader is used; leader text reads left to right; match lines never on a full station | p. 2-4 (pdf 17) |
| `layers` | Caltrans levels, not NCS layers: align_MAIN-anno (16), border_INSIDE-BORDER-anno (10), border_PROJ-ID-BLOCK-anno (10), border_SHEET (10), border_SIGNATURE (63), border_SEAL (10), pp_PRESENTATION (10), rd_RIGHT-OF-WAY-anno (23) | p. 2-89 (pdf 118); ppm-examples pdf 63 |
| `required_title_fields`, D1-10 | the Caltrans border carries Dist / County / Route / Post Miles and Sheet No. / Total Sheets (upper right), engineer signature and seal (upper right), sheet name, ID code and scale (lower right), Unit and Project Number & Phase (bottom right), development names in the left margin, plot stamp along the bottom | p. 2-52 (pdf 65); p. 2-89 (pdf 118); ppm-examples pdf 62 |
| `sheet_number` (C-101) | layout sheets are named LAYOUT with ID codes L-1, L-2 …; the code is required on every sheet except the title sheet, lower right inside the border, not boxed | p. 2-52 (pdf 65); p. 2-20 (pdf 33) |
| match lines (D2+) | perpendicular to the alignment at +50, never on a full station; "MATCH LINE" callout optional between consecutive sheets | p. 2-4 (pdf 17); p. 2-82 (pdf 111) |
| profiles (D2+) | H:V = 10 typical; vertical scales 1"=10', 5', 2'; PG grade to two decimals (three when matching existing); elevations at BVC, EVC, VPI, equations; profile checklist | p. 2-7 (pdf 20); p. 2-85 – 2-87 (pdf 114–116); pdf 122–123 |

## Where draft-v1 departs from the PPM

Observations for the PE review in eval plan §3.7 (item 9). None of these is applied to the spec
here: any change to `DRAFTING_SPEC_V1` changes `spec_hash` and mints new task ids, so they are
batched with the other pre-freeze decisions. The genericized values were chosen on purpose (the
neutral benchmark is not a Caltrans skin); the question per item is whether the neutral spec
should follow the PPM, keep its value, or push the PPM value into a Caltrans / ORD dialect.

| item | draft-v1 | PPM | citation |
|---|---|---|---|
| curve-point wording | `PC 16+00.00` / `PT …` (AASHTO, Civil 3D) | `BC` / `EC` with the line designation, e.g. `"TB1" 644+45.25 EC` | p. 2-8 (pdf 21); ppm-examples pdf 45 |
| station annotation | every 100-ft station labeled in full, `12+34.56` | full annotation only at 500-ft stations; single digit at the 100-ft stations between; no `+00` | p. 2-8 (pdf 21) |
| tick length | `tick_half_len_in` 0.20 (0.40 in total) | 7.0 ft at 1"=50' = 0.14 in total, centered on the line | p. 2-8 (pdf 21) |
| station label side and offset | `label_side` left, `label_offset_in` 0.32 (left of the direction of stationing is above the line when stationing runs left to right) | below the alignment line, about half a text height below the tick | p. 2-8 (pdf 21) |
| text height | labels 0.10 in, table 0.12 in | TX=7.0 → 0.14 in for station text; 8.75 → 0.175 in for names and scale | p. 2-89 (pdf 118) |
| tangent labels | bearing only | bearing **and distance** of each tangent | p. 2-89 (pdf 118); pdf 45 |
| curve table | 9 columns: curve, PI sta, Δ, direction, R, T, L, chord, chord bearing | 5 columns: No., R, Δ, T, L (N/E optional); PI station, chord and chord bearing are not shown | ppm-examples pdf 45 |
| curve callout | `C-1` text label at the mid-curve anchor | a circled curve number on the plan keyed to the table | ppm-examples pdf 45 |
| layer names | NCS-style `V-ALIGN-CNTR`, `V-ROAD-STA`, `V-ANNO-TEXT`, `V-ANNO-TABL` | Caltrans named levels (`align_MAIN-anno` …) | p. 2-89 (pdf 118) |
| title block fields | generic `project`, `agency`, `designed_by`, `drawn_by`, `checked_by`, `date`, `scale` … | Caltrans project-ID block, signature and seal, sheet name + ID code, unit / project number, development names | p. 2-52 (pdf 65); pdf 62 |
| sheet naming | `C-101` | `LAYOUT` with `L-1` | p. 2-52 (pdf 65) |

Consistent with the PPM as-is: 22 × 34 sheet, 1"=50' and 1"=100' plotting scales, north arrow upper
right, `SCALE: 1" = 50'` text under the sheet name (add the colon), uppercase text, DMS bearings
with direction, station equations required, precise stations to 0.01 ft, curve numbers
consecutive and unique.

Not in this collection: the CADD Users Manual (text sizes §2.6, levels §2.4, line weights §2.7,
sheet naming §2.1) and the Standard Plans (abbreviations and symbols A3A–A3C), both cited
throughout the PPM. Add them as further collections when a check depends on them.
