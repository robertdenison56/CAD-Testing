# What else the real sheets can carry (review of 2026-10-23)

*A review of the eval task sets against the redrafted example sheets: which task types run on
real sheets today, which seeded-only types could, and what new jobs the sheets hold a truth for.
Numbers come from a sweep of the 313 redrafted sheet files and the 584-task real catalogue
(`benchmarks/real_tasks/catalog.json`); nothing here is built yet.*

## Where the sets stand

| Set | Tasks | Types | Sheets |
|---|---|---|---|
| `d1-test` / `d1-dev` / `d1-variance` | 100 / 50 / 20 | 16 seeded types on one synthetic centerline | generated |
| `d1-real` / `d1-real-dev` | 100 / 24 | 12 real types (`real-*`) in 4 question groups, 25 a group (since 2026-10-27) | 51 + 3 of the 45 catalogue sheets |
| `hard-pilots` | 29 | 13 pilot families, hand-built | real sheets, 24 text-only + 5 scans |

Seeded types with no real counterpart: `pavement-edges`, `pavement-widths`, `pavement`,
`create-alignment`, `layer-setup`, and the two-sheet layouts (`annotate-base` is the five real
lettering types in another coat). No model has run `d1-real` yet, so growing it costs no reruns.

## What the redrafts actually hold

The constraint on every candidate is what the redraft pipeline recovered from the PDFs:

- **Design objects exist only for alignments.** The alignment base files (`aa01`, `_ali`, `ALI`,
  `ALGN`) hold rebuilt alignments with `draw_alignment` and `annotate_stationing` anchors. No file
  in the set holds a design profile; 7 of the 17 Caltrans profile sheets and 3 stage-quantity sheets
  are outlined glyphs with zero text entities.
- **Corridors and survey are traced linework.** `bb01`, `_cor`, `COR`, `DSGN` carry Lines and
  Polylines on pen layers (`V-ROAD`, `V-ROAD-EDGE`, `P_ROAD_THIN`, `E-TOPO`) with no anchors and no
  typical section behind them.
- **Sheet annotation is Text plus leaders.** Every note, callout, table and match line is Text and
  Lines in sheet space. The whole set has one `Table` entity and no `Dimension` entities.
- **Callouts were placed with `place_callout`.** The redraft READMEs record 2,274 callouts on 166
  sheets: 1,687 aimed at the base element the published leader touches, 35 at a stated station and
  offset, 552 at a point. Callouts carry no anchor record.

## Candidates, in the order worth building

### 1. Construction callouts (`real-construction-callouts`)

*Built 2026-10-24 (Robert: "build real-construction-callouts first"): `tasks/real_callouts.py`,
the `notes` start in `tasks/real.py`, the verifier's D1-16 (`verify/checks.py`), a twelfth real
type in `d1-real` and `d1-real-dev`; see `benchmarks/real_tasks/README.md`.*

The largest real-sheet job not yet in any set. Start: the sheet with its callouts removed (they
sit on their own layer, `S-ANNO-CALL` / `S_ANNO_CALLOUT`, so the strip is a layer). Brief: the
notes as published, each with what it points at, given as a station and offset on the sheet's
alignment (read from the published tip with `xy_to_station`) or as the referenced element. Grade:
tip within tolerance of the published tip, text as given, placed in sheet space, leader not through
text (D1-08 v4 already charges that). Needs a callout check in the verifier (none exists) and a
truth row per callout. Volume: 166 sheets, about 14 callouts a sheet; the 45 catalogue plan
sheets alone carry several hundred.

### 2. Create the alignment from its description (`real-create-alignment`)

The README's gap ("the rebuilt alignments store no PIs") is not real: `pis_from_elements`
recovers PIs from any tangent-curve-tangent run, and `compile_pis` round-trips 40 of the 85
catalogue alignments within 0.05 ft (the spec's position tolerance). The other 45 start or stop
inside a curve or at a kink, which no PI list describes. Brief: begin station, PIs and radii, or
the same as bearings and distances through `legs`. Start: the alignment base file with the
alignment, its drawn elements and its stationing removed (the `draw` start plus the design).
Grade: D1-15 as it stands, D1-01 for the linework. Effort: a `START_KIND`, a truth from the
existing alignment, a filter for the 40 that round-trip.

### 3. Match lines (`real-match-line`)

30 redrafted sheets letter a match line, about 18 of them catalogue plan sheets at 1" = 40' or
50' (the ten Route 65 layouts, four drainage plans, four delineation plans). Start: the sheet
with its match line and label removed (`S-ANNO-MTCH`). Truth: the station where the published
line crosses the alignment, the published label. The verifier's `_match_line` already grades a
line square to the centerline at a station and a label beside it; it is wired only to two-sheet
truths through `check_groups`, so a one-sheet truth with `matches` filled needs that wiring
loosened. Caltrans labels mostly carry no station ("MATCH LINE (L-5)"), so the explicit prompt
states the published text and the geometry gives the station.

### 4. Pavement edges and widths on the real corridors (`real-pavement-edges`, `real-pavement-widths`)

**Scrapped by Robert on Oct 27 2026.** His Oct 24 reading of this candidate (station-and-offset
callouts at every break in the edge of pavement, with the total-width dimensions as the companion;
tracker step B10) was designed and never built, and is not to be. The notes below stay as the
survey of what the redrafts hold.

67 of the 85 catalogue alignments have traced linework running 150 ft or more at a constant
offset (D13's traveled way at 34.8 ft each side over 400 to 800 ft on L-2, L-4 and L-5; its EP
at 39.7 ft; FDOT CL1 at 40 ft; CFL CL1 at 13 ft). Truth: `offset_pieces` already takes a station
range, and D1-12 grades piece by piece, so a task can ask for one edge at one width over the
stations where the traced edge runs at it, with the traced line removed from the corridor copy.
D1-13 then covers the width dimension. Caveats: the widths are measured, not the typical
section's round numbers (34.8 ft, not 35); the edges sit on mixed layers, so the brief must name
the layer role (EP or ETW); the detection of constant-offset runs is new code. Lower priority
than 1 to 3 because the real corridors have tapers and turnouts that the task has to cut around.

### 5. Control points and point tables (`real-control-points`)

Three sheets carry coordinate tables as text: WFL D.1 survey control (12 points with N, E,
elevation, lat/long, combined factor), FDOT sheet 10 project control (14 points with station,
offset and description), and the WFL parking-lot layout table (70 layout points). Brief: the
published list; `create_points` takes it as PNEZD text and `place_point_table` lays it out.
Grade: point coordinates within 0.05 ft, table cells. Needs a point check (none exists). Small
in volume, but the only COGO skill a real sheet offers. The FDOT sheet attaches no alignment, so
its station and offset columns cannot be graded against a design.

### 6. Quantity and tabulation tables (`real-table`), later

21 Caltrans quantity sheets with text, 5 WFL summaries and 4 WFL tabulations, 3 CFL summaries
and one FDOT tabulation hold their tables as traced grids: Text at cell positions and Lines for
the rules, no `Table` entities. A task would give the rows and ask for `place_table` at the
published spot. Needs the grid parsed into rows and columns and a table check (`place_table` is
raw text in the audit and earns nothing today). Low drafting value for the work: it tests typing.

### Not recommended as a real type

- **Layer setup.** The redraft layers are the pipeline's pen names (`S-LINE-035`,
  `P_ROAD_THIN`), not an agency standard; the spec's Caltrans level set is already the seeded
  `layer-setup` task.

### Only as pilots or with vision

Profiles and superelevation diagrams (no design profile anywhere; pilot 6 hand-built the PVIs),
typical sections and cross sections (28 and 12 sheets of traced lines and text with no model
geometry; pilot 10 covers two by hand), striping and delineation (pilot 13), stage construction,
electrical, signs and planting (traced, no design truth: QA-review and plan-reading pilots only),
and the 41 scanned pages never redrafted.

## Widening the eleven types already built

22 plan sheets with alignments are outside the catalogue:

| Why | Sheets | What would bring them in |
|---|---|---|
| Scale not 40 or 50 | 12 (1" = 20': PPM-206, -207, -214, -215, WFL wall; 1" = 100': CFL plan-profile, CFL SWPPP, WFL erosion, FDOT landscape with ten usable lines; 1" = 200': FDOT drainage map; 1" = 69': FDOT clearing) | a spec decision; the 40/50 rule is Robert's and frozen in v1 |
| Centerline traced as 7 to 44 short tangents | 8 (WFL SamplePlan pp1 to pp7 `MAIN 01`, CFL parking `CL1` twice, PPM-218) | refit those alignments as tangents and curves in the redraft, as pilots 1 and 14 did for L-1; the WFL series is eight consecutive sheets of one line, the only real two-sheet or plan-set material in the set |
| Under 200 ft, or 5 curves | 3 | leave |

The catalogue also holds 32 to 85 tasks per type against the 5 to 25 per type `d1-real` draws (25 a question group since 2026-10-27), so the
set can grow without a new type.
