# Caltrans CADD Users Manual (sections behind the drafting spec's layers)

Four sections of the Caltrans *Computer Aided Design & Drafting (CADD) Users Manual*, the
document the Plans Preparation Manual defers to for levels, text sizes and line weights
(ppm-text p. 2-83 (pdf 112): "Line weights and line styles must conform to the requirements
in Section 2.7 of the CADD Users Manual. Refer to Section 2.6 ... for text sizes and fonts").
Added 2026-10-10 when the drafting spec's layers became Caltrans named levels (Robert, PE:
"set up more layers per Caltrans PPM standards"). Publisher page:
https://dot.ca.gov/programs/design/manual-cadd-users-manual (each section is its own PDF).

| id | section | date | pages | what it gives the spec |
|---|---|---|---|---|
| `cadd-appx-a10` | Appendix A10 Named Level Libraries | April 12, 2021 | 75 | every named level by dgn library: number, name, description, color-table index |
| `cadd-ch2-sect4` | 2.4 Drawing Data Levels | February 25, 2019 | 135 | the naming convention and the group names |
| `cadd-ch2-sect6` | 2.6 Text | October 23, 2017 | 4 | fonts; the text-size table at 1"=50' |
| `cadd-ch2-sect7` | 2.7 Lines | October 23, 2017 | 6 | line weights by feature; line codes and styles |

Cite as `cadd-appx-a10 p. A10-2`, `cadd-ch2-sect7 p. 2.7-1` (the manual's own page numbers, carried
on the separator lines; `pdf_page` is the PDF page).

## The naming convention (2.4, pp. 2.4-3 – 2.4-4)

`groupname_TASKNAME-subtaskname_plotstyle`: a lower-case group name (`align`, `rd`, `pp`,
`border`, ...), an upper-case task name with optional lower-case sub-task after a hyphen, and an
optional plot-style part. `-anno` levels carry the annotation of the item on the matching level
(`align_MAIN` / `align_MAIN-anno`). Named levels superseded the numbered V8 levels in 2017; the
PPM's checklists still print the old number in parentheses (`align_MAIN-anno (16)`). "The Default
Level (Level 0) should not be used to store elements in any Caltrans MicroStation design file"
(p. 2.4-1).

## Levels the drafting spec uses (`DRAFTING_SPEC_V1["layer_set"]`)

| level | A10 number | library | color | WT | spec role | A10 page |
|---|---|---|---|---|---|---|
| `align_MAIN` | 9017 | Ct_Alignments | 0 | 3 (main-route alignment, 2.7-1) | alignment | A10-2 |
| `align_MAIN-anno` | 9018 | Ct_Alignments | 0 | 1 (stations for alignment lines, 2.7-1) | ticks, labels | A10-2 |
| `align_CURVE-DATA` | 9010 | Ct_Alignments | 0 | 1 | tables | A10-2 |
| `rd_EP` | 9112 | Ct_Roadway | 0 | 2 (PPM p. 2-90: EP "usually WT=2"; 2.7-2 lists WT 1) | edges | A10-18 |
| `rd_ETW` | 9114 | Ct_Roadway | 0 | 1 | — | A10-18 |
| `rd_ES` | 9113 | Ct_Roadway | 0 | 1 | — | A10-18 |
| `rd_LAYOUT-NOTE-anno` | 9129 | Ct_Roadway | 0 | 0 (dimension lines, 2.7-1) | dims **(PE review)** | A10-18 |
| `rd_RIGHT-OF-WAY` | 9143 | Ct_Roadway | 6 | 1 | — | A10-18 |
| `rd_RIGHT-OF-WAY-anno` | 9144 | Ct_Roadway | 6 | 1 | — | A10-18 |
| `pp_PRESENTATION` | 10232 | Ct_ProjectPlans_BorderSheetInfo | 0 | 1 (north arrow, PPM p. 2-89) | symbols | A10-16 |
| `pp_LEGEND-anno` | 10225 | Ct_ProjectPlans_BorderSheetInfo | 0 | 1 | — | A10-16 |
| `border_SHEET` | 10210 | Ct_ProjectPlans_BorderSheetInfo | 0 | 4 (sheet border, 2.7-1) | — | A10-16 |
| `border_PROJ-ID-BLOCK-anno` | 10208 | Ct_ProjectPlans_BorderSheetInfo | 13 | 1 | — | A10-17 |
| `border_INSIDE-BORDER-anno` | 10206 | Ct_ProjectPlans_BorderSheetInfo | 13 | 2 (scale text, PPM p. 2-89) | match **(PE review)** | A10-17 |
| `border_SEAL` | 10209 | Ct_ProjectPlans_BorderSheetInfo | 4 | 1 | — | A10-17 |
| `border_SIGNATURE` | 10211 | Ct_ProjectPlans_BorderSheetInfo | 4 | 1 | — | A10-17 |

The PPM's layout-sheet checklist (ppm-text pp. 2-89 – 2-91 (pdf 118–120)) names these directly:
`border_PROJ-ID-BLOCK-anno`, `border_SHEET`, `border_SIGNATURE`, `border_SEAL`,
`border_INSIDE-BORDER-anno` (scale), `pp_PRESENTATION` (north arrow cell NARR), `align_MAIN-anno`
(route identification) and `pp_LEGEND-anno`. The rest are the A10 rows for the work the D1 tasks
draw.

**Spec readings flagged for PE review** (neither manual says where these go):

- *Width dimensions* on `rd_LAYOUT-NOTE-anno` ("Annotation for construction shown in Master
  Design"), at WT 0 as 2.7-1 gives dimension lines. The PPM checklist asks for the traveled-way
  width to be dimensioned on layouts (p. 2-90) without a level.
- *Match lines and their labels* on `border_INSIDE-BORDER-anno`, the level the PPM gives the scale
  text. The PPM has match lines at +50 and the optional "MATCH LINE" callout (p. 2-4, p. 2-82) with
  no level.
- *Display colors* in `layer_props` are RoadDraft's nearest named color for the A10 color-table
  index (0 → black, 4 → yellow, 6 → cyan, 13 → magenta); the Caltrans color table itself is not
  in this collection. The index is kept in `caltrans_levels`.
- *Weights in millimetres* (`lineweight_mm_by_wt`: WT 0–4 → 0.18, 0.25, 0.35, 0.50, 0.70 mm) are
  this spec's rendering of the MicroStation weight; the manual shows appearance, not widths.
- The alignment line is drawn solid: 2.7-3 gives line code 0 (solid) for proposed design elements
  and reserves the long-dash–short-dash code 7 for *object* centerlines.

## Text (2.6, pp. 2.6-1 – 2.6-2), for the text-size review

At the 1"=50' base scale: 7 (0.14 in) for "the majority of text, including text with drawings,
tables and dimensioning", font 3 (CTFONT1) weight 1; 8.75 for route and line names, table
headings and subtitles (font 3, weight 2); 10 and 12 for titles (font 43 bold, weight 0); 14.5
for the sheet name. The spec's 0.10 in labels and 0.12 in table text remain a recorded departure
(see `../caltrans-ppm/README.md`).
