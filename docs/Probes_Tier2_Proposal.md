# Harder probes: a second tier

*Proposal, 2026-10-02. Evidence: `benchmarks/probe_runs/`.*

*Status, 2026-10-03: the recommended batch of six is built, in `src/roaddraft/probes/tier2.py` (`python -m roaddraft.probes list --tag tier2`), with two new fixture starts (`intersection`, `flawed`), scripted solutions that pass their own checks, and trap tests in `tests/test_probes_tier2.py`. The three not built are curve-data, draft-widening and the L-2 redlines. No model has run the six yet.*

## What the four runs say about the first 17

| | T2 find-and-annotate (9) | T1 draft-from-description (8) |
|---|---|---|
| Fable 5.1 | 9/9 | 8/8 |
| Haiku 4.5 | 9/9, 7/9 | 4/8, 7/8 |
| gpt-oss:120b (3 passes) | 17 of 18 | 7 of 16, then 6/8 |
| Qwen3.5-9B (local) | 8/9 | 3/8 |

T2 is saturated: a 9B model aims every callout by name at 0.00 ft, and the only misses anywhere are a wording
slip and one aimed-at-the-wrong-edge. T1 separates models, but Fable passes all of it, and the misses cluster in
four places: hand arithmetic (the COGO gap, a tool gap as much as a reasoning one), width-vs-offset, stopping an
offset at a station, and losing track of one's own entities. Nothing yet measures the quality of what is placed
(text over linework, leaders across the road), the scope of a job that spans sheets, geometry that involves two
alignments, checking an existing drawing, or carrying a design through to a plotted sheet. Those are the second
tier.

The rules stay the same: scored from the document on disk, never from the report; each probe has a scripted
`solve` that passes its own check and an untouched fixture that fails it; checks judge geometry and text, not
vocabulary, so an alternate correct route passes.

## Candidate probes

Effort is for probe + check + solve + the tests that prove the trap fails: S = an afternoon, M = a day, L = several.

### T2, harder: a sheet set, not a callout

**1. `sheet-set-callouts` (M).** *Annotate sheets C-101 through C-103: call out both edges of pavement and both
outside shoulder edges on every sheet where they appear, label the centerline SR-100 on each sheet, and fill every
title block: project SR-100 WIDENING, a sheet title, sheet N of 3, scale 1" = 50'.* The Sep 10 T2 statement as one
task. Check per sheet with the existing `aimed_at` and `on_sheet`, then counts and title-block fields. Traps: the
first curve lies 62% on C-102 and 38% on C-101, the shoulders are not in view on every sheet, N of 3 changes per
sheet. Separates scope discipline: Haiku skipped sheets on Sep 22, and every model so far has been asked for one
thing at a time.

**2. `clean-callouts` (L, the biggest measurement gap).** *On C-102 call out the left edge of pavement, the right
shoulder and the centerline. Text must not sit over any linework or another callout; leaders must not cross the
roadway; everything must lie inside the border.* New checks, all in sheet space through the viewport:
text-box-vs-linework using `viewmap.visible_spans`, leader-segment-vs-roadway intersection, inside-the-border. No
model has yet been judged on whether its annotation is legible. A text-only model has to reason about where the
road is on paper; a vision model can `render_sheet` and look, which is exactly the capability a plan sheet needs.

**3. `station-callouts` (S).** *On C-101, call out every even 100 ft station of SR-100 that falls on the sheet,
text = the station.* One `aimed_at_point` per station from `station_to_xy` with `sheet=`, text must carry the
printed station (`24+00`, not `2400`). Traps: which stations are actually in the window, eleven near-identical calls
without drift, the station format. Separates loop discipline and format fidelity; pc-by-station already caught
Haiku writing `24+05` for `24+05.27`.

**4. `curve-data` (M).** *On C-101, place SR-100's curve table and label the PC, PI and PT of the first curve with
their stations.* `place_curve_table` and `resolve_anchor` on `DESIGN:SR-100`. Check: a table on the sheet whose
rows match `get_design_data`, three labels aimed at the resolved points with the right station text. Separates
reading design data through a reference and writing it back correctly, with no arithmetic.

**5. `l2-redlines` (L, the capstone).** Start from the Caltrans L-2 sheet file with the model attached and the
annotation stripped; the prompt is a drafter's redline list of the 14 callouts, notes and the curve table (the
content is already in `examples/caltrans_l2/sheet_content.py`). Check: each of the 14 aimed within 1 ft, text
present, table rows right. A real sheet: clipped reference, a twisted viewport at -6.457 deg, 3,000 model
entities to search. This is what a plan-sheet agent is for.

### T1, harder: a design, not an element

**6. `draft-intersection-corner` (M).** Start from the MAIN ST / CROSS AVE fixture with both centerlines and
curb lines drawn (`examples/intersection`). *Draw the 50 ft curb return at the northeast corner, tangent to the
MAIN ST curb at 44 ft and the CROSS AVE curb at 32 ft, and trim both curb lines back to the return.* Right angle, so
the arc center and tangent points come out by addition, not trig. Check: an arc of R 50 within 0.5 ft of the
expected one (`covered`), the curb lines `covered` up to the tangent points and `clear` past them. Traps: which
quadrant, trimming (a `station_range` redraw or delete-and-redraw), two alignments at once. Nothing so far has
involved two alignments.

**7. `draft-fix-the-drawing` (M, new kind).** Start from the SR-100 model with planted errors: one edge segment at
11 ft, a shoulder on V-ROAD-EOP, a callout aimed at the shoulder that says EP. *QA this drawing against the typical
section (12 ft lanes, 8 ft shoulders) and fix what is wrong. Change nothing else.* Check: each planted error gone,
and the diff against the fixture contains nothing but those fixes. Separates inspection (`measure`, `get_entity`,
`find_entities` with `anchor`) and restraint. Every probe so far adds; drafters mostly correct.

**8. `draft-widening` (S).** *Widen SR-100 from two lanes to four between 20+00 and 30+00, 12 ft lanes, with 15:1
tapers at each end, both sides.* The turn-lane trap at full strength: offsets of 24 and the taper length (180 ft)
derived from the ratio, four edges with `station_range`. Check along the expected path with `covered`/`clear`.
Separates the same thing turn-lane does, with more arithmetic and more pieces.

**9. `draft-roadway-sheets` (M).** The roadway probe carried to paper: *...then create a 1" = 50' sheet showing the
whole of ELM-AVE, with stationing every 100 ft and the title block filled.* Check: `alignment_runs` and the offsets
as now, plus a viewport whose window covers the whole alignment (`visible_spans`), stationing ticks present, title
block. This is the parked D1 job in one prompt; only Fable has done roadway reliably, so it is a ceiling probe.

### Not probes, but cheap difficulty

- **n = 3** for anything that matters: Haiku's T1 gains on Sep 22 were probably variance at n = 1.
- **Report scoring beside disk scoring:** ask each probe for one number only a query can give (the station where
  the edge meets the bulb) and compare it to the truth. gpt-oss fabricated three reports; Qwen put eleven in the
  thinking channel. This measures it instead of noticing it.
- **A no-instructions condition:** the same probes with the MCP `instructions` stripped, to see how much the
  teaching prompt carries.

## Decisions for Robert

1. **COGO input** (`create_alignment` from start + bearing/distance legs, and a forward query). Still recommended,
   still not built. Without it every bearing-and-distance probe measures sine tables as much as drafting; with it,
   roadway-style descriptions become fair for every model and bearing-distance can be retired or made harder.
2. **Whitespace in text checks.** title-blocks fails Qwen on `1"=50'` vs `1" = 50'`. Keep literal, or normalise
   spaces and keep the stricter form for a wording probe?
3. **Scope of the first batch.** Recommended: 1, 2, 3, 6, 7, then 9; the L-2 redlines once the clearance checks
   from 2 exist, since the L-2 needs them to be fair.

## Recommended first batch

| order | probe | why first |
|---|---|---|
| 1 | `sheet-set-callouts` | the T2 statement as written, mostly existing checks |
| 2 | `station-callouts` | small, and it loops |
| 3 | `clean-callouts` | the one quality nobody has measured; its checks are reused by the L-2 |
| 4 | `draft-intersection-corner` | two alignments, no trig |
| 5 | `draft-fix-the-drawing` | correction, not addition |
| 6 | `draft-roadway-sheets` | the whole job, the ceiling |

All six fit the existing rig unchanged: `probes list --tag tier2`, `setup`, `score`, `selftest`, and the LM Studio
and Ollama runners pick them up from `tasks.PROBES`.
