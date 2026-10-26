# Harder-task pilots

*2026-10-19. Status: built and self-tested; no model has run them yet.*

On the 33 Track P probes the frontier has run out of room: GPT-6.1-Sol 32/33 (97.0%), GPT-6-Astra and
Sonnet 96%. Sol's one miss was a bearing lettered at 0° on a sheet where its line ran at 5.03° through a
twisted viewport. The probes mostly test whether a model picks the right command and fills its
parameters, because the engine does the geometry: `create_alignment` takes bearings as written,
`place_callout` lands on the entity, `annotate_stationing` letters a whole alignment.

These pilots try tasks where the engine does less of the work: input that is not clean data, layout
decisions with competing constraints, changes that ripple through a sheet, and problems nobody named.
Each is two or three hand-built instances, every one set on the real example sheets
(`examples/Exmple Plans/Redraft` and `Sheets`), so we can see what a frontier model fails before
anyone builds a generator. The ones it fails become benchmark families; the ones it passes are dropped.

## Where they live

- `src/roaddraft/probes/pilot/`: one module per family, plus `common.py`, which copies a redrafted
  sheet's file set into a probe's project folder.
- **Off the board.** `tasks.PROBES`, the probe-set hash and the Track P leaderboard are unchanged. A
  pilot is reached by id (`tasks.get`) or with `runners run --pilot`; its runs go under
  `benchmarks/pilot_runs/`.
- `benchmarks/pilot_references/<id>/`: each scripted solution kept as a finished project: the
  completed `.rdraft` set, journal, PDF, DXF and `reference.json`.
- Tests: `tests/test_pilot_*.py` (108 tests, about a minute) and `tests/test_mcp_profiles.py`.

```bash
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot list
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot selftest
PYTHONPATH=src .venv/bin/python -m roaddraft.probes.pilot reference --out benchmarks/pilot_references
```

`selftest`: every scripted solution passes its check read back from disk, and every untouched start
fails it (33/33). Each family's tests also feed the check at least one plausible wrong answer and
confirm it fails.

## The pilots

Numbers are the brainstorm's. Brainstorm items 7–9 (constraint-fitted design, best-fit an existing
road, contours) were left out.

| # | Pilot | Instances (sheet) | What makes it hard | Graded on |
|---|---|---|---|---|
| 1 | Redraw an alignment from a scanned sheet | `p01-redraw-alignment-ppm045` (Caltrans L-1, TB1), `-fdot915` (FDOT sheet 12, CL1) | Reads bearings, curve data and stations off a raster with no text layer; L-1's tie is a station equation to D13 | Bearings to 2", Δ to 3", R, PC/PT stations to 0.10 ft, position to 0.10 ft every 25 ft, drawn |
| 15 | Plan reading | `p15-plan-reading-ppm046` (Caltrans L-2), `-wflp14` (WFL D.5), `-cflpla` (CFL Davis Dam Rd) | Six reviewer questions per scan; some need arithmetic (an EC off the sheet, an unlettered PT), one a clipped quadrant, one a scale read off the bar | Each answer exact after normalizing format, truth read from the redraft |
| 14 | Open-ended QA review | `p14-qa-review-ppm045a` (clean control), `-ppm045b` (6 errors), `-wfl19` (3 errors) | Unknown count and kinds, visual ones included (north arrow, upside-down text); mark, don't fix; the control punishes false alarms | Each plant hit by a QA-REVIEW leader within 0.5 in; at most 1 false alarm; control needs NO ERRORS FOUND and no marks |
| 2 | Sources that disagree | `p02-sources-wfl19a` (table R wrong), `-wfl19b` (design wrong, in the base file), `-ppm045` (a tangent length wrong) | Deciding which source is wrong from the rest of the evidence, and fixing it where it lives | The wrong source corrected; every other entity in every file unchanged; a finding recorded |
| 11 | Redlines with knock-on edits | `p11-radius-ppm160` (PD-1, R = 1500' hold PI), `-station-ppm045` (L-1, restation TB1 +25 ft) | The engine does not regenerate labels; every downstream station, BC/EC, table cell and two callouts that cite TB1 stations must follow | E1 verifier on truth from the revised design; nothing stale or doubled; revision recorded; redline removed; nothing unrelated changed |
| 12 | A small full plan set | `p12-route65-d13` (Route 65 L-1 to L-3 joined) | Five sheets that must agree: index, numbering, match lines, coverage, and a quantity takeoff | Index = sheets present; 1 to 5 of 5; match lines agree and sit at their station; every 10 ft shown; SY and LF within 1% |
| 4 | Crowded annotation | `p04-crowded-ppm045` (L-1, 3 lines, twist -89.94°), `-ppm050` (L-7 interchange, 5 lines, twist -131.21°) | Lettering every line at once on a crowded, turned sheet without collisions | E1 per line, plus legibility across all lines (any overlap of new work fails), labels along their lines and reading upright |
| 17 | Twisted variants | `p17-twist-ppm160` (PD-1 turned 180°), `-fdot916` (FDOT re-cut at -113°) | The failure mode of Sol's one miss: text orientation through a twist | E1 verifier at the new twist; every label along its line, reading from the bottom or right |
| 5 | The model picks the sheet breaks | `p05-breaks-fdot904` (SR 50, 472+00–490+00), `-cfl` (CFL CL1, 10+00–25+00) | Choosing sheet count, breaks and twists; match lines square and lettered alike | Coverage, left-to-right on every sheet, match lines within 1 ft and 1°, at most fewest + 1 sheets |
| 3 | Survey traps | `p03-misclosure-ppm045` (deed off by 1:6,534), `p03-grid-ground-wfl20` (CSF 0.999649), `p03-intl-feet-ppm047` (international feet and metres at state-plane size) | A traverse to balance by the compass rule; a scale factor to apply the right way; a 2 ppm unit difference worth 13 ft | Corners within 0.02 ft, points within 0.05 ft, closure numbers recorded |
| 10 | Typical section from a description | `p10-typical-cfl01` (CFL A6), `-wfl07` (WFL C.1) | Slopes, crown, layers and catch points against a given ground line, then a viewport at 1" = 10' | Grade breaks and catch points within 0.05 ft, layer bottoms within 0.03 ft, dims and slope labels present, the viewport |
| 6 | Plan and profile on one sheet | `p06-plan-profile-cflpnp` (CFL Plan 1), `-wfl14` (WFL D.5) | No profile-view command: the grid and grade line built by hand at 10:1, stations lined up with the plan | Grade line within 0.10 ft every 10 ft, PVI/L/K/high-low labels, plan-profile alignment; D.5 has no high point, and lettering one fails |
| 13 | Striping with no-passing zones | `p13-striping-wfl15` (D.6, 55 mph), `-wfl16` (D.7, 50 mph) | Passing sight distance from the profile per MUTCD, per direction | Zone ends within 25 ft, 10/30 dashes, edge lines, nothing in the wrong zone |
| 18 | Redline understanding | `p18-redline-pdf-ppm045` (Caltrans L-1, 6 marks), `-wfl19` (WFL D.10, 5), `-cflpla` (CFL Davis Dam Road, 5), `-fdot915` (FDOT sheet 12, 6) | The brief is a marked-up PDF and nothing else: handwriting on a render of the sheet, read through `view_attachment`; a key says red = revise, green = delete, blue = comment only; each mark sits on one of several look-alike texts | One item per mark: the revised text reads the new wording at its spot, the deleted one is gone, the moved one sits where the arrow points (0.5 in), the added note lies within 1 in of the tip, the clouded entities are byte-for-byte as they were, the struck field reads the new value; nothing else changed and none of the handwriting lettered |
| 16 | Basic tools | the 33 probes on `--profile basic` | The model computes coordinates itself | The probes' own checks |

### 16: the basic profile

`roaddraft-mcp --profile basic` (`src/roaddraft/mcp/profiles.py`) hides 30 commands that work out
geometry for the caller: offsets, fillets, trims, the traverse, station and viewport conversions,
`key_points` and `snap`, the labelers and `draw_alignment`. It also removes the engine-aimed
parameters from `place_callout` and `find_entities` and the bearing-and-distance route from
`create_alignment`, which keeps its PI-coordinate route because a design alignment is the only thing
the six drafting probes' checks can read. It serves its own instructions.

All 33 probes stay passable on basic: each reference solution's document, with every anchor the engine
stamped removed, still passes its check. A run on basic records `"profile": "basic"` in `run.json`,
and the leaderboard skips such episodes, so they can never become a board row.

```bash
python -m roaddraft.runners run --profile basic --backend codex --model MODEL \
    --out benchmarks/pilot_runs/<date>-basic --label <label>
```

## In the eval harness: the `hard-pilots` set (2026-10-22)

Robert, 2026-10-22: "the harder tasks should make it into the eval set as well." All 33 pilots are
the eval task set `hard-pilots` (`benchmarks/tasksets/hard-pilots.json`), ranked on its own board
beside `d1-test` and `d1-real`. They stay pilots too: the `--pilot` route below is unchanged.

- **How an episode runs** (`src/roaddraft/eval/probe_tasks.py`): the pilot's start project is
  built in the episode folder, the model gets the pilot's task text as the probe runner sends it,
  the server's instructions as its system prompt, and the MCP server's own tools served in-process
  (autosave, `open_document`, `view_attachment` for the nine pilots that come with a page image), with paths
  shown and resolved relative to the project folder and file access held to the episode folder.
- **Grading** is the pilot's own check, read back from disk as `runners score` does: 100 on a
  pass, 0 on a fail. The rubric column is the share of the check's items the document has. An
  episode with no engine call fails and is credited no items.
- **Re-grading.** The files an episode changed are kept under `<run>/projects/<episode>/`, and
  `report --reverify` grades them again under the current checks.
- **Budgets.** Track P's, unless the run sets its own: 600 steps, 12 faults in a row, 200,000
  output tokens, 30 minutes.
- **`run_check`** (self-correct mode) answers pass or fail and how many items are done, never the
  check's words, which name expected values.
- **The oracle** is each pilot's scripted solution recorded as tool calls. A second session the
  solution opens on a base file is recorded as `open_document` of that file. Oracle 100 and null 0
  on all 33 through the loop.
- **Images.** The five scanned-sheet pilots and the four redline pilots need a provider that passes images. The
  OpenAI-compatible route (Runpod, LM Studio) does not, so those models fail them.

```bash
.venv/bin/python -m roaddraft.eval run --taskset hard-pilots --agent oracle --agent null --steps 5000
.venv/bin/python -m roaddraft.eval run --taskset hard-pilots --model MODEL [--samples 3]
```

## Running the pilots on a model (not done; waits on Robert's go)

```bash
python -m roaddraft.runners run --pilot --backend codex --model gpt-6.1-sol --effort medium \
    --out benchmarks/pilot_runs/<date>-sol --label sol-pilot
```

Pilots 1 and 15 hand the model a scan through `view_attachment` (served only to probes that ask for
it with `--attachments`). The scan reaches the model on the codex and claude-code backends always,
and on the anthropic backend only with `--vision`. The openai-compatible backend (LM Studio, Runpod)
never passes images, so it cannot run pilots 1 and 15.

`python -m roaddraft.runners score benchmarks/pilot_runs/<run>/runs/<label>` scores a pilot run as it
does a probe run.

## Caveats, by pilot

- **1:**
  - The truth is the lettered design held at the tie, not the redraft's fitted alignment, which
    differs slightly (R 3243 against the lettered 3280'). A test confirms it stays within 0.3 ft of
    the redraft wherever the sheet shows it.
  - Small traced strokes near the stripped line were removed by a size-and-distance heuristic.
- **15:**
  - The CFL bearing question depends on a quadrant letter that the plan edge clips; it is a
    deliberate trap.
  - The scale question needs the scale bar measured in pixels plus the stated paper size.
  - The grader reads the first number in an answer.
- **14 and 2:**
  - The sheets are normalized before planting (fitted-curve kinks removed, lettering re-made from the
    design), so they are not the published sheets letter for letter.
  - On L-1 the construction callouts are excluded only by the prompt; some of their leaders miss the
    station they state.
  - The WFL north-arrow plant is defined in the redraft's frame.
  - wfl19b's error is easy to see; the test is the fix route (the base file, then a redraw).
- **11:**
  - E1 credits only anchored lettering, and the prompt says so.
  - The Caltrans revision-block keys are not discoverable through `fill_title_block`, so the revision
    check accepts a note anywhere.
  - The radius redline is on PD-1, because L-1's base keeps traced glyphs of TB1's published bearing
    that no edit can fix.
- **12:**
  - The joined Route 65 base and its V-ROAD-EP edges are constructed for the pilot.
  - The HMA area works out to 80 × 3,200 / 9 without measuring; the fence takeoff still needs
    clipping to the station range.
- **4 and 17:**
  - Pass or fail on perfection: one overlap fails the probe.
  - On PD-1 the labelers' default poses with the right twist pass, so that instance tests the twist
    alone. On FDOT-916 the published twist happens to letter correctly too, so only one of the two
    twist mistakes is caught there.
- **5:** title blocks, north arrows and sheet names are not checked. On the CFL stretch three
  north-up sheets pass, because the line heads NNE.
- **3:**
  - The grid-ground georeference is constructed: only YRB3 is tied to a drawn feature.
  - California defines state plane in US survey feet, so the international-feet setting is contrived,
    though the trap is real.
  - `traverse` with `close=true` reports the misclosure directly; the balance is the real test.
- **10:** the sources are NO SCALE, so some numbers are invented (the fill and back slopes, the
  profile-grade elevations, the ground lines). Slope labels must be written V:H.
- **18 (redline understanding, 2026-10-26):**
  - Robert, 2026-10-26: "some of the tasks should be prompted by editing a pdf with redlines/markups and
    having the LLM address these based only on that." The page is `markups/<sheet>-redlines.pdf`,
    with the same page as a PNG beside it for `view_attachment`, drawn by `redline_pdf.draw_markups`
    on a 200 dpi render of the sheet in a handwriting face (Bradley Hand, falling back to
    Chalkboard or Comic Sans; the check never needs the font). A key strip under the sheet gives
    the colour convention.
  - The sheet file the model opens is the staged redraft, untouched: no layer, entity or text
    carries the instruction, and the task text names no edit.
  - The marks sit on texts that have look-alikes elsewhere on the sheet (two FENCE (TYPE CL-6),
    two REMOVE FENCE, two See Section X for details, four TYPE F / E curb callouts, three
    sidewalk callouts): the mark's place decides which one.
  - The title block marks are found by rendering the sheet with the field blanked and taking the
    pixels that differ; the model fills the field with `fill_title_block`.
  - Tolerances: a revised or deleted text is judged within 0.6 in of its old spot, a moved one
    within 0.5 in of where the arrow put it (the whole group for the FDOT BEGIN PROJECT block), an
    added note by its box within 1 in of the tip. A new leader line within 1.2 in of an added or
    moved note is allowed; any other new entity but text fails.
  - Lettering the checker's own words (DELETE, MOVE, OK PER SURVEY) onto the sheet fails.
  - Needs an image-capable route, like pilots 1 and 15.
- **6 and 13:**
  - No redraft carries a design profile; each was entered from the published PVIs. The WFL profile is
    pieced together from sheets D.5 to D.12.
  - A referenced file's profile cannot be read, so these starts own their alignment and profile
    instead of referencing them.
  - The WFL base files still hold the published profile drawing as linework.
  - Both striping instances sit on the same crest, one direction each.

## Engine and harness issues the pilots turned up

1. A referenced file's profile is invisible: `get_design_data` reads only the host's profiles, and
   `create_profile` refuses a referenced alignment.
2. `modify_alignment` does not regenerate anchored labels; it warns, or says nothing when the labels
   anchor through a reference.
3. `fill_title_block` lists only the standard keys, not an agency border's revision-block keys.
4. `render_model` crashes at very low dpi (30) with a matplotlib font-size error.
5. `reference.write` loads the baseline lazily from the folder the solve edits, so a solve that
   changes a base file changes what the baseline shows. Scoring a run is unaffected, since its start
   is built fresh. The pilots that edit bases grade against a fresh build.
6. Reference journals record only the opened document's commands, not edits saved to a base file.
7. Some published lettering was digitized as linework (glyph outlines) in the redraft base files, so
   stripping a line's annotation can leave traced text behind.
8. On the anthropic backend, a text-only run replaces a `view_attachment` image with a note saying
   "the text above carries the file path", which is not true for an attachment.
