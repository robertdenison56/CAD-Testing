# RoadDraft CAD Engine

The headless 2D CAD application under the RoadDraft RL environment (see
[RoadDraft_Build_Plan.md](RoadDraft_Build_Plan.md), section 5). It gives an AI
agent — and a human through the same interface — a real drafting program:
model space + sheets, layers, styles, blocks, viewports, and title blocks,
with **every element exposed as JSON** and **every mutation flowing through a
serializable command bus**.

No CAD license required; Python only.

## Structure: the AutoCAD / MicroStation mental model

The document is organized the way both production platforms are, so workflows
learned here transfer (PRD section 4):

| RoadDraft | AutoCAD / Civil 3D | MicroStation / ORD |
|---|---|---|
| Model space (US survey feet) | Model space | Design model |
| Sheet (inches) + border/title block (`standard`, `caltrans`, `none`) | Paper-space layout | Sheet model |
| Viewport (scale = feet/inch, view twist) | Layout viewport (MVIEW) | Referenced view / named boundary |
| Layer | Layer | Level |
| Block | Block (INSERT) | Cell |
| Text style | Text style | Text style |
| Reference (basefile: path, placement, true scale, level display, symbology, clip) | Xref (XATTACH / XCLIP) | Reference attachment |
| Command + aliases | Command line (`LINE`, `ERASE`…) | Key-in (`place line`…) |

Design geometry lives in model space at real-world coordinates; annotation and
sheet composition live on sheets in paper inches; viewports window model space
onto paper at a plot scale (1"=50' → `feet_per_inch: 50`). Commands carry
C3D-style and ORD-style aliases (`LINE`, `place line`) as the seed of the
dialect skins.

## Roadway drafting commands

Beyond the 2D primitives, the bus carries roadway-semantic actions:

- `annotate_stationing` — the stationing engine. Give it connected
  line/polyline/arc entities (the centerline), a begin station, and an
  interval; it computes length along tangents and curves, draws ticks,
  formats stations ('12+34.56'), keeps labels upright, and letters BC/EC/PCC
  the Caltrans way.
- `attach_reference` / `detach_reference` / `modify_reference` /
  `reload_references` — external basefiles (AutoCAD xref / MicroStation
  reference attachment): the host stores path + offset/rotation/scale plus
  display settings, the basefile's model geometry renders under every space
  and sheet viewport, reloads from disk, exports to DXF on bound
  `<NAME>$<layer>` layers, and is never copied into the host document.
  The MicroStation reference dialog is covered: relative paths resolve
  against the host file's folder; `true_scale` converts the basefile's
  declared `model_units` into the host space's units (a metric survey lands
  at the right size in a survey-foot host, 1"=50' on a sheet is
  `scale: 1/600`); `levels_off` hides basefile levels per attachment;
  `symbology` overrides color / linetype / lineweight or grays the whole
  attachment out; `clip` (boundary polygon) and `masks` (mask polygons) clip
  the geometry itself, so render, DXF, extents and `hit_test` agree.
  `hit_test` locates reference elements (`SURVEY:LN-001`, read-only) and
  `get_entity` reads them back in host coordinates. `model` attaches the
  basefile's design model or one of its sheet models (border and title
  block included); `nest_depth` turns on live nesting, so the basefile's own
  references display too (`SURVEY:UTIL:LN-001`, levels `UTIL$layer`), with
  circular attachments skipped.
- `place_dimension` — dimensioning: `linear` (along one axis), `aligned`
  (the true distance between two points), `angular`, `radius`, `diameter`
  and `arc_length`. What the document stores is the *measurement* — the
  points, the arc, and where the dimension line was dragged to — so the
  number is derived, never typed: move a measured point and the text
  follows. Name what to measure rather than computing points (`of_entity`
  for one entity end to end or a curve's own centre/radius,
  `from_entity`/`to_entity` for two, two lines for the angle between them),
  and reference geometry works as a target. See
  [Dimensioning](#dimensioning) below.
- **Design model (Phase 1)** — `create_alignment` / `modify_alignment` /
  `delete_alignment`, `create_profile` / `delete_profile`, `draw_alignment`,
  `place_label`, `place_curve_table`, `import_landxml`, plus
  `annotate_stationing alignment=NAME`: alignments and profiles live in the
  document as design data (not linework), and every tick, label, and table
  drawn from them records the design anchor it came from. See
  [Design model](#design-model-phase-1) below.

## The load-bearing decision: the command bus

Every state change is a named JSON command (PRD section 5.1):

- **Validated** against a JSON Schema; invalid calls return *teaching errors*
  (what's wrong + the schema + a working example).
- **Atomic**: a failed command restores the pre-command snapshot.
- **Journaled**: the command log is the action trajectory; `save_journal` +
  `Session.replay_journal` reproduce the document deterministically.
- **Undoable**: `undo`/`redo` are themselves journaled commands.
- **Feedback-rich**: every result carries a diff (`created/modified/deleted`)
  plus warnings (text overlap, off-sheet placement, viewport outside the
  usable area) — dense learning signal.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"     # add ,desktop for the app window
.venv/bin/pytest                      # 787 tests
.venv/bin/python examples/demo_plan_sheet.py   # drafts a full plan sheet
.venv/bin/python examples/caltrans_l2/build_all.py  # rebuilds a real Caltrans sheet
.venv/bin/python -m roaddraft.tasks 42         # generates a D1 task + reference solution
```

The demo drafts C-101 (ANSI D) from a design-model alignment: centerline
drawn from the alignment, pavement edges from station/offset queries,
alignment-mode stationing (ticks, labels, BC/EC), anchored bearing and
mid-curve callouts, the curve data table, north arrow, notes, filled title
block — then renders PNG/PDF, exports DXF and LandXML, and proves the
journal replays byte-identically (26 commands).

### A real plan sheet, rebuilt

`examples/caltrans_l2/` recreates a published Caltrans plan sheet — 03-3H5404
sheet 6, "LAYOUT", Route 70 PM 46.0/47.0 — as the two-file plan set the
platform is built around: a design model file that owns the `SR70` alignment,
the roadway linework, the stationing and the existing ground, and a sheet file
that owns **no geometry at all** and composes sheet L-2 over a clipped
reference to it at 1"=50' with a 6.457° view twist. Its four curves are
rebuilt from the sheet's own CURVE DATA table and BC/EC stations, so the plan's
every printed station comes back out of the design model; its fourteen
station-and-offset callouts are aimed through that model rather than at typed
points; its BC, EC and PCC stations read bottom to top, as the published sheet
letters them. The builders live in the package (`roaddraft.probes.l2`), because
the tier-3 probes start from this sheet. See
[examples/caltrans_l2/README.md](examples/caltrans_l2/README.md).

### Drive it as an agent (JSON in, JSON out)

```python
from roaddraft import Session

s = Session(project_name="SR 100")
s.manifest()                          # every command & query: schema + example + aliases
s.execute("create_layer", {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center"})
s.execute("draw_line", {"space": "model", "start": [1000, 1000], "end": [1600, 1000],
                        "layer": "V-ALIGN-CNTR"})
s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
s.execute("create_viewport", {"sheet": "C-101", "center_paper": [17, 12],
                              "width_in": 31, "height_in": 18,
                              "model_center": [1300, 1000], "feet_per_inch": 50})
s.query("get_document_state", {"detail": "full"})   # the entire file as JSON
s.query("render_sheet", {"sheet": "C-101", "include_base64": True})  # vision obs
```

Nothing is hidden from the model: full state (`get_document_state`), per-sheet
state with what each viewport can see (`get_sheet_state`), entity lookups,
extents, the journal, and the self-describing manifest (`list_commands`).

## Design model (Phase 1)

Roadway design lives in the document as **data**, separate from the linework
drawn from it — the Civil 3D alignment / ORD geometry-model idea:

```python
s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                               "pis": [[1000, 1000], [1814.359354, 1000, 800],
                                       [2433.012702, 1357.179677]],
                               "equations": [{"back": "20+00", "ahead": "25+00"}]})
s.execute("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                             "pvis": [[1000, 100], [2000, 120, 400], [2500, 90]]})
s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
s.execute("place_label", {"space": "model", "anchor": "PC-1"})        # "BC 16+00.00"
s.execute("place_label", {"space": "model", "anchor": "T-2"})         # bearing N 60°00'00" E
s.execute("place_label", {"space": "C-101", "anchor": "MC-1", "kind": "curve_data"})
s.execute("place_curve_table", {"space": "C-101", "position": [24, 8.5]})
s.query("get_design_data", {"kind": "curves"})     # Δ, R, T, L, E, M, C, bearings, stations
s.query("station_to_xy", {"station": "18+00", "offset": 25})
s.query("xy_to_station", {"point": [1300, 1012]})  # -> 13+00.00, 12.00' LT
```

- **Alignments** are PI-based (`[x, y]` at BEGIN/END, `[x, y, R]` interior)
  or built from CoordGeom elements; the engine compiles tangents and circular
  curves, checks that curves fit their tangents, and carries a begin station
  plus **station equations** (`STA 20+00 BK = STA 25+00 AH`, gaps and
  overlaps). Every station in the API is a *display* station (`1600` or
  `"16+00"`); results carry the raw value and the printed text.
- **Profiles** are PVIs with symmetric parabolic vertical curves; the engine
  validates fit/overlap and reports PVC/PVT, grades, A, K, and high/low points.
- **Anchors** name design points: `BEGIN`, `END`, `PC-n`, `PT-n`, `PI-n`,
  `MC-n`, `T-n`, `EQ-n` (`BC-n`/`EC-n` name the PC/PT), or a station (`18+00`, `1800`), optionally with an
  offset (`PC-1@16`, `18+00@25L`, right positive). `place_label` resolves the
  anchor, infers the label kind (`station`, `pc`, `pt`, `pi`, `mc`, `pcc`,
  `prc`, `bearing`, `begin`, `end`, `equation`, `curve_data`, `custom`),
  writes the conventional wording, places the text on the conventional side
  with the conventional offset, keeps it upright (text square to the line reads
  bottom to top, as Caltrans letters BC and EC), and — on a sheet — maps it
  through the viewport that shows the point. The text entity records an
  `anchor` (`alignment`, `ref`, `kind`, `station`, `offset`, `side`,
  `label_offset`, `rotation`, `viewport`, `content_auto`, `placed_by`): the
  verifier's contract. `resolve_anchor` is the dry run.
- **Anchor provenance**: the bus stamps `anchor.placed_by` with the command
  that created the entity (`draw_alignment`, `annotate_stationing`,
  `place_label`, `place_curve_table`), and nothing else writes it —
  `modify_entity` drops a supplied `placed_by` and keeps the entity's own, so
  an anchor bolted onto hand-placed text carries no provenance while a real
  label survives a rename, a move or a layer fix. A verifier can then tell
  drafted work from decorated work.
- **Reading a referenced design** — a plan set keeps the design in one file and
  the sheets in another that references it, so the sheet file owns no alignments
  at all. `list_alignments include_references=true` lists them as
  `DESIGN:SR-100`, and `station_to_xy`, `xy_to_station`, `resolve_anchor` and
  `get_design_data` all accept that name, so "where is station 25+00" and "where
  is the PC of the first curve" work from the sheet file. **Points come back in
  host coordinates** — they land on the geometry as drawn even when the
  attachment is moved, turned or scaled — while stations, lengths, radii and
  bearings stay as designed, because those describe the road rather than this
  sheet; a `placement` block reports the mapping so the difference is never
  hidden. Reading is not owning: `draw_alignment`, `draw_offset`, `place_label`,
  `modify_alignment` and `delete_alignment` all refuse a referenced alignment
  and say to call it out instead.
- **Finding things** (`find_entities`) selects by what something *is* — layer,
  type, design anchor, text content, a bounding box, or what a given sheet
  shows — instead of dumping the document and filtering downstream:
  `{anchor: {kind: "offset", offset: [-12, 12]}, visible_on: "C-102"}` is the
  pavement edges that sheet displays. It searches attachments too, so it is how
  to locate geometry in a sheet file whose design is referenced in, and the
  basefile's anchors travel through, so a pavement edge announces itself as
  ±12 ft of `SR-100`. Every row carries **a point that is on the entity**;
  `point_on_entity` gives the same for `start`/`mid`/`end` or any fraction,
  with the direction it runs there.
- **Callouts** (`place_callout target_entity="DESIGN:AR-003" at="mid"`) place an
  arrowhead, a leader, a shoulder and text as ordinary entities — the way a
  drafter annotates geometry that has no design model of its own. Name the
  entity and the engine computes the tip; that matters most on curves, where
  the midpoint of an arc's endpoints sits 15.5 ft off the arc on the demo
  alignment. A raw `target=[x,y]` still works, and the result says what the tip
  actually landed on (`DESIGN:AR-007 (arc on V-ROAD-SHLD, 20.00' LT of
  SR-100)`) — worth reading, because roadway linework runs parallel a few feet
  apart, so a hand-computed point that misses usually lands on the *wrong* line
  rather than on nothing. A station and offset is a target too:
  `target_anchor="586+57.73@20.83L" alignment="DESIGN:SR70"` takes the anchor
  grammar (`PC-1`, `18+00@12R`, `{station, offset}`), because most plan callouts
  point at a place on the alignment where there is no entity to find. A
  referenced alignment is read, not owned, so the callout carries no anchor.
- **Callouts on the sheet.** Plan annotation belongs in paper space, where it
  neither scales nor turns with the view — but what it points at is in the
  model, usually in a referenced basefile, and only *seen* on the sheet through
  a viewport. So `place_callout space="C-102"` still takes a model
  `target_entity` or `target_anchor`, and the engine carries the tip through
  the viewport's centre, scale and twist (`viewport=` picks one; otherwise the
  first that shows the target, as `place_label` does). `at` then runs along
  **the part of the entity that sheet shows**: a pavement edge runs the length
  of the project and a sheet shows one stretch of it, so on the demo project
  the first curve is 62 % on C-102 and 38 % on C-101, and `mid` lands on a
  visible point of each. Asking for something the sheet does not show is a
  fault that names the sheets that do. `find_entities visible_on=` keeps only
  what the viewports really show (a twisted window is not its bounding box) and
  gives each row the `sheet_point` the tip will land on, so the text can be put
  clear of the linework.
- **Model ↔ sheet** (`model_to_sheet`, `sheet_to_model`) convert between model
  feet and paper inches through a viewport, so nobody re-derives one by hand;
  `sheet_to_model` also names the nearest entity under that spot on the paper.
  `station_to_xy`, `resolve_anchor` and `point_on_entity` take a `sheet` and
  answer in paper inches as well. A raw `target` on a sheet is checked the same
  way — against the design the tip is looking at through the viewport, not
  against whatever lettering sits nearby on the paper. The Caltrans L-2 rebuild
  places its 14 station-and-offset callouts by `target_anchor` on a viewport
  twisted −6.457°; the tips agree with the example's own independent trig to
  1e-13 in.
- **Constant offsets** (`draw_offset offsets=[-12, 12]`) draw pavement edges,
  shoulders and right of way as anchored lines and arcs. Offsets are feet, right
  of the direction of stationing positive (`"12L"` says the side out loud), so a
  24 ft pavement is `[-12, 12]`. The offset is exact, not a polyline
  approximation: tangents shift sideways keeping direction and length, curves
  keep their center and change radius (`R + offset × sign`, so a 800 ft left
  curve offsets to 812 ft outside / 788 ft inside), and because the radial
  lines at the PC and PT are shared the pieces meet end to end with no fillet.
  An offset that reaches the center of a curve is a teaching error.
- **Alignment-mode stationing** (`annotate_stationing alignment=NAME`) walks
  the true stations through the equations, so ticks and labels are anchored
  and equation-aware; the original entity-chain mode is unchanged.
- **LandXML 1.2** in and out (`import_landxml`, `export_landxml`): alignments
  with Line/Curve geometry and station equations, profiles with PVI/ParaCurve;
  units (USSurveyFoot / foot / meter) are converted; spirals are rejected
  with a teaching error.
- **Tasks**: `python -m roaddraft.tasks SEED [--equations] [--curves N]`
  generates a deterministic D1 plan-sheet task — a brief (design pre-seeded,
  deliverable, DRAFT drafting spec), the verifier ground truth computed by
  the same label functions, and the reference solution (15 commands) whose
  document matches the truth exactly and whose journal replays. Task ids
  pin the generator version and the spec hash. The AASHTO-derived standards
  tables and the drafting spec are DRAFT, for PE review.
- **Annotation scales** (AutoCAD annotation scale / Civil 3D drawing scale):
  the document carries a scale list (`1"=10'` … `1"=500'`, editable with
  `add_annotation_scale` / `delete_annotation_scale`), a current scale, and
  paper-unit defaults (0.10 in text, 0.20 in ticks, 0.32 in label offsets;
  `set_annotation_defaults`). With `set_annotation_scale 50` on, stationing
  and labels that omit sizes are drafted at paper size × scale (5 / 10 / 16 ft)
  and stamped `annotative`; `set_annotation_scale 100` then re-sizes every
  annotative model entity for the new plot scale — text heights from their
  paper heights, ticks about their midpoints, design-anchored labels re-placed
  at their paper offset through the design model, plain text about its
  insertion point. `adopt=true` stamps pre-existing annotation; `off` restores
  the fixed feet defaults. `create_viewport` warns when a viewport's plot
  scale differs from the annotation scale; `list_annotation_scales` reports
  the list and sizes. The GUI has the scale selector in the status bar.

## Dimensioning

A dimension is a measurement, not a picture of one. `place_dimension` stores
what is being measured and derives the linework — extension lines, dimension
line, arrowheads, the number — every time it is drawn, which is what keeps
the text and the geometry from drifting apart:

```python
s.execute("place_dimension", {"space": "model", "kind": "linear",
                              "from_entity": "LN-003", "to_entity": "LN-005",
                              "line_point": [1450, 1000], "layer": "V-ANNO-DIMS"})
# -> linear dimension DM-001 ("24.00'") placed in model space, measured vertically
s.execute("modify_entity", {"id": "DM-001", "changes": {"p2": [1450, 1020]}})
# -> the dimension now reads 32.00'
```

**What to measure.** Give the points (`p1`/`p2`, `center`, `radius`), or name
the geometry and let the engine find them: `of_entity` dimensions a line,
polyline or arc end to end, or reads an arc/circle's own centre and radius;
`from_entity`/`to_entity` (with `from_at`/`to_at`: `start|mid|end` or a
fraction) measure between points that are genuinely *on* each entity, curves
included; and two lines handed to an angular dimension are intersected for
the vertex. Ids come from `find_entities` and `hit_test`, so geometry seen
through a reference attachment (`SURVEY:LN-001`) can be dimensioned like
anything else.

**`line_point` is where the dimension line goes** — the point a drafter
drags to — and it is also how the command says which measurement was meant,
exactly as dragging does in AutoCAD: clear above or below a pair of points is
a horizontal dimension and out to the side a vertical one (two points
separated along one axis only are simply measured that way); on an angular
dimension it picks which of the four angles between the rays is being called
out; on a radius or diameter it is where the text sits, inside the circle
drawing across it and outside drawing a leader.

**Appearance** follows the annotation scale. One number — the text height —
sizes the whole dimension: arrowheads, text gap and extension line offsets
default to fixed multiples of it (AutoCAD's DIMASZ / DIMGAP / DIMEXO /
DIMEXE), and each can be overridden. `set_annotation_scale` re-sizes the
annotation for a new plot scale *without moving the measured points*, so the
reading never changes. Text sits above the dimension line and reads left to
right; arrowheads sit inside the extension lines and flip outside, with a
warning, when the text will not fit. `arrow` selects `arrow`, `tick` (the
oblique civil slash), `dot` or `none`.

**The number** reads `120.00'` by default, `12'-6"` with
`unit_format: "feet_inches"`, or bare with `decimal`; an angular dimension
reads DMS (`28°15'30"`). `prefix`/`suffix` wrap it (radius, diameter and arc
length come with `R=`, `Ø` and `L=`), `precision` sets the decimals, and
`text` overrides the value outright (`""` hides it). `measure_scale` is
AutoCAD's DIMLFAC: on a sheet, set it to the viewport's plot scale to
dimension in model feet — which is exactly what the viewport transform does
for you when a model-space dimension is shown on paper, so the same
dimension reads `24.00'` in model space and through a 1"=50' viewport.

**`measure`** is the read-only half (AutoCAD's DIST / MEASUREGEOM): the
distance, dx/dy, bearing and azimuth between two points or entities, or one
entity's own length, radius and sweep — formatted with the same string
`place_dimension` would draw.

### Drive it as an agent — MCP mode (natural language)

`roaddraft-mcp` serves the whole command surface to any MCP client as tools, so
an agent can be told *"draft a 2,000 ft alignment from station 10+00 with a
1,200 ft curve, then draw 12 ft pavement edges"* and work it out through the
same bus a human uses.

**Claude Code finds it on its own in this repository.** The checked-in
[`.mcp.json`](.mcp.json) registers the server as `roaddraft` through
`${CLAUDE_PROJECT_DIR}`, so the file is the same on every machine and carries
nobody's path. Claude Code asks once per project to approve it; from then on
the tools are there as `mcp__roaddraft__<tool>` (`claude mcp list` shows the
state, `claude mcp reset-project-choices` asks again). The server starts on a
new document; `open_document` opens one, and `save_document` keeps the work.

**Every other client is one command.** The server's own command line is the
registration: `--config CLIENT` prints it for exactly the server invocation the
other flags describe, with the venv's executable and every path absolute, and
`--write` merges it into the client's file beside the servers already there (a
file in your home folder is backed up first). Paths with spaces are quoted;
this repository's own path has one.

```bash
.venv/bin/roaddraft-mcp --config lmstudio --write          # ~/.lmstudio/mcp.json
.venv/bin/roaddraft-mcp --config claude-desktop --write    # claude_desktop_config.json
.venv/bin/roaddraft-mcp --config codex --write             # [mcp_servers.roaddraft] in ~/.codex/config.toml
.venv/bin/roaddraft-mcp --config claude-code --doc /path/to/SR-100.sheets.rdoc.json --autosave --name roaddraft-sheets
```

The last one is a second server for Claude Code pointed at an existing document
(this is how a sheet file with the model referenced in gets annotated); its
output also names the `claude mcp add --scope user` line for a registration
that follows you across projects. Clients: `claude-code` (the project
`.mcp.json`), `claude-desktop`, `lmstudio`, `codex`, `cursor`, `vscode`
(`.vscode/mcp.json`) and `json`, the bare entry for anything else with an
`mcpServers` table. `python -m roaddraft.probes setup` prints the same line
for a probe's fresh project.

- **78 tools**: 45 commands + 32 queries straight from `Session.manifest()` —
  the same descriptions, JSON Schemas and worked examples the REPL and the web
  GUI use, so there is no second copy to drift — plus `open_document`.
- **`--autosave`** writes the document, and its journal beside it, back to the
  file it was opened from after every command. An agent is asked to do a
  drafting job, not to remember to save; without this its work is in memory and
  gone when the client hangs up. It stays with the opened file even if the agent
  saves a copy elsewhere, which real models do. **`--trace FILE`** appends one
  JSON line per tool call — queries and faults included, which the journal does
  not keep — so a run can be read back for what the agent tripped on rather than
  taken from what it says it did.
- **Faults teach instead of failing**: a bad call comes back as a tool error
  carrying the message, the hint, the schema and a valid example, so the model
  corrects itself rather than guessing.
- **Renders come back as images** (`render_sheet`, `render_model`), so an agent
  can look at the sheet it just drew.
- Everything still goes through the bus: validated, atomic, journaled,
  undoable. An agent session leaves the same replayable journal a human one
  does.
- `--only` / `--exclude` trim the surface; `--list-tools` prints it.

Protocol is newline-delimited JSON-RPC 2.0 on stdio, implemented on the
standard library (the official MCP SDK needs Python 3.10 and this runs on 3.9).

### Find-probes — can an agent locate the right thing?

`roaddraft.probes` holds four small sets of capability probes. The find-probes
are for the skill an agent needs before anything else: finding the object it
was asked about and putting the work on it. Deliberately *not* the scored benchmark in
`RoadDraft_Eval_Plan.md` — no rubric, no spec hash, no task ids.

```bash
python -m roaddraft.probes list
python -m roaddraft.probes setup edge-curve-c102 --out /tmp/probe --force
python -m roaddraft.probes score edge-curve-c102 --doc /tmp/probe/SR-100.sheets.rdoc.json
```

`setup` writes a fresh copy of the SR-100 project, prints the instruction to
give the model and the `claude mcp add` line that points at it; `score` grades
the document the model leaves behind. Scoring diffs against the untouched
fixture and asks one question — did the work land within 1 ft of the thing it
was supposed to land on — so a callout composed by hand out of `draw_line` and
`place_text` scores exactly like one from `place_callout`. Aim is what is being
measured, not vocabulary.

`python -m roaddraft.probes selftest` runs a scripted solution for every probe,
scores the file it saves, and checks that the untouched project fails, which is
what keeps the checks honest. `pc-by-station` is the one that needs a *referenced* design: a PC is
not an entity, so there is nothing to find — only a station to ask for.

Aim is always judged in the model, in feet: a leader tip drawn on a sheet is
carried back through the viewport it sits in before it is measured, so
paper-space and model-space work are held to the same 1 ft (0.02 in at
1" = 50'). The two `-paper` probes are the T2 shape — `edge-c102-paper` by
entity, `sta-offset-c101-paper` by station and offset — and additionally
require the callout to be on the sheet itself; a correct callout drawn in the
model does not satisfy them.

### Drafting-probes — can an agent draft from a description?

The other half of the job: nothing is there yet, and an engineer says what to
draw, the way engineers say it — northings and eastings, bearings and
distances, deflections, stations and offsets, lane and shoulder widths.

```bash
python -m roaddraft.probes list --tag draft
python -m roaddraft.probes setup draft-turn-lane --out /tmp/probe --force
```

Eight probes, each built around one way of getting it wrong: a swapped northing
and easting (`draft-tangent-ne`), lines from PI to PI that are neither the road
nor an alignment (`draft-pi-curve`), a bearing and a deflection to turn into
coordinates (`draft-bearing-distance`), an 8 ft shoulder drawn 8 ft from the
centerline instead of 20 (`draft-edges-shoulders`), a turn lane whose edge runs
on past its stations (`draft-turn-lane`), pavement edges through a cul-de-sac
bulb (`draft-cul-de-sac`), a building turned off-axis on a layer that does not
exist yet (`draft-building`), and the whole job in one instruction
(`draft-roadway`). Each starts from its own document — a blank design file, the
SR-100 centerline, or the full SR-100 model — and `setup` hands over the right one.

They judge what was drafted, not how. An alignment counts if the design model
carries one that *runs where it was described*, whether it was built from PIs
or from elements. Linework counts if it *lies where it should*: the expected
path is sampled every few feet and each sample needs added linework within
0.5 ft, on the layer that was asked for — so an edge from `draw_offset` scores
like one composed of lines and arcs by hand, and a curve faked with chords does
not. Where a description says where something stops, the check also looks past
the end for linework that should not be there. `tests/test_probes_drafting.py`
spends most of its effort proving that each trap fails and says why.

Runs of both sets by real models — Fable 5.1 and Haiku 4.5 through an MCP
bridge, gpt-oss:120b through Ollama as a native MCP client — are kept under
`benchmarks/probe_runs/`, one folder per run: the writeup, the rig that drove
it, every tool call as the server saw it, and the documents the models left
behind, which is what was scored. See its README.

### Tier-2 probes — harder, one gap each

For the agents that pass the first seventeen. Six probes, each aimed at
something the first two sets do not measure: the scope of a job that spans
sheets, legibility, geometry between two alignments, QA of an existing
drawing, and a design carried through to a plotted sheet.

```bash
python -m roaddraft.probes list --tag tier2
```

| probe | opens | asks for | the trap |
|---|---|---|---|
| `sheet-set-callouts` | sheets | every edge and shoulder and the named centerline on all three sheets, title blocks numbered | stopping after one sheet; `CENTERLINE` instead of `SR-100` |
| `station-callouts` | sheets | a callout on every even station C-101 shows, text reading the station | fifteen calls without drift; `1100` for `11+00` |
| `clean-callouts` | sheets | three callouts with text clear of linework, clear of each other, inside the border | text dropped beside the tip lands on the shoulder line |
| `draft-intersection-corner` | intersection | a 50 ft curb return at the open corner, curbs trimmed to it | the wrong corner; an arc centred on the corner; curbs left running |
| `draft-fix-the-drawing` | flawed | find and fix three planted mistakes, touch nothing else | fixing by adding; relayering one piece and not the other; orphaned leaders |
| `draft-roadway-sheets` | blank | the whole roadway, then a 1" = 100' sheet that shows all of it | a viewport that misses an end; the wrong scale; a sheet with no title block |

Two checks carry the new weight. `tier2.callouts` pairs each text with the
chain of lines leaving it and finds the tip, so a check can ask what *this*
callout says and where *it* points — for `place_callout`'s three pieces and for
a hand-drawn line alike. `tier2.paper_linework` samples everything a reader
sees on a sheet in paper inches, the model through each viewport included,
and `clean-callouts` wants 0.05 in of air between text and any of it. Aim is
still 1 ft and linework 0.5 ft; a curb trimmed by moving its endpoint scores
like one deleted and redrawn. The design notes behind the set are in
`docs/Probes_Tier2_Proposal.md`. First run, 2026-10-04: Qwen3.5-9B, which
passes 8 of the 9 find-probes, gets 0 of 6 here, each on the gap it was
built to measure (`benchmarks/probe_runs/2026-10-04-lmstudio-tier2/`).

### Tier-3 probes — a layout's line and curve data

What every Caltrans layout must carry for its station lines (PPM 2-2.5):
bearings and distances of the tangents, the stations of the curve points, curve
data, stationing, equations — and the work around them. Ten probes; every sheet
file here *references* its design, so the engine's labelers (`place_label`,
`place_curve_table`, `annotate_stationing`) refuse it and an agent either
composes the lettering from `get_design_data` or copies the design into the
sheet file first.

```bash
python -m roaddraft.probes list --tag tier3
```

| probe | opens | asks for | the trap |
|---|---|---|---|
| `line-data` | sheets | bearing and length of every tangent, above the line, parallel | PI-to-PI lengths; the back bearing; text across the edge of pavement |
| `curve-points` | sheets | every BC and EC station, square to the line, reading bottom to top | upright-folded text reading top to bottom; `24+05` for `24+05.27` |
| `curve-data` | sheets | a CURVE DATA table (No., R, Δ, T, L) per sheet for the curves it shows, numbered bubbles | both curves on every sheet; numbering restarted; E or M as T |
| `stationing` | sheets | Caltrans stationing on C-102: 7 ft ticks, ones digits, whole numbers at 500s, below | `26+00` lettering; labels above; 7 in ticks |
| `width-dims` | sheets | 8' 12' 12' 8' across the road at 17+00, every number readable | a paper dimension reading `0.24`; four numbers piled at one station |
| `row-data` | sheets-row | right of way tagged L1…/C1… with LINE and CURVE TABLES | the centerline's radius; the visible length; a jog left untagged |
| `equation-data` | sheets-eq | an equation, the tangent it falls on, the next BC | 1290.35' from stations for a 1240.36' tangent; the BC without the equation |
| `qa-alignment-data` | sheets-qa | find and fix five planted errors, touch nothing else | fixing by adding; missing the restarted curve number |
| `l2-match-lines` | l2 | both match lines on Caltrans L-2, square to the turned line | vertical lines; square to the model, not the sheet |
| `l2-alignment-data` | l2 | L-2's stripped alignment data, curves numbered 2 to 5 | the design's C-1..C-4; lettering parallel to the model; EC at the PCC |

The checks read the sheet **as it plots** (`probes.plotted`): paper space and
the sheet file's own model space through each viewport, text as oriented boxes,
tables by their rows and dimensions by their measured points — so the copy
route and the compose route score alike. They read **values, not spellings**
(`probes.notation`): `N71°33'54"E` and `N 71-33-54 E` are the bearing
`N 71°33'54" E`; `1581.14'` fails wherever it is written. The words are the
standard's: BC, EC, PCC, BK, AH. `tests/test_probes_tier3.py` proves each trap
fails with a message saying why and each alternate route passes; it builds L-2
once (about 20 s) and caches it. The design notes are in
`docs/Probes_Tier3_Proposal.md`.

### The reference solutions, as finished projects

Every probe's scripted solution drafts through the command bus, with the
commands an agent sends over MCP, and is kept as a finished project in
`benchmarks/probe_references/<probe>/`: the start project with the document
the agent is handed completed under its own name (open it in RoadDraft; it
reads its design through the reference beside it), the journal of every
command the solution ran, the sheets plotted to PDF, and a DXF for AutoCAD,
Civil 3D or MicroStation. Each is scored the way a model's document is, read
back from disk against a fresh start; the folder's README lists the verdicts.

```bash
python -m roaddraft.probes reference --out benchmarks/probe_references
python -m roaddraft.probes reference curve-data --out /tmp/refs
```

`tests/test_probes_reference.py` fails when a probe has no kept reference or
its reference no longer passes. The run deliverables in
`benchmarks/probe_runs/` keep each `<probe>.reference.pdf` beside the same
solution as a project, `<probe>.reference/`.

### Drive it as a human — GUI (PRD M3 thin viewer)

```bash
.venv/bin/pip install -e ".[dev,desktop]"         # once: pywebview, for the window
.venv/bin/roaddraft-desktop --project "SR 100"    # in a window of its own
.venv/bin/roaddraft-web --project "SR 100"        # or in your browser
```

…or double-click `RoadDraft.command` in Finder (`RoadDraft.command --browser`
for the browser). The desktop window runs the same server inside the app, on
a free loopback port, and both end when the window closes: nothing to start
first, nothing left running. Closing it over unsaved changes asks Save /
Don't Save / Cancel first, the title bar names the drawing ("— Edited" while
it has unsaved changes), Open and Save As use the window's own macOS panels,
and it logs to `~/Library/Logs/RoadDraft/roaddraft.log`. The app bundle is
built from a separate environment, `.venv-build` (uv's Python 3.13 with
PyInstaller, apart from the development `.venv`); `scripts/build_env.sh`
makes or refreshes it. The icons come from the artwork in
`packaging/icon/`: `packaging/make_icons.py` cuts its rounded square out of
the black, sets it on Apple's icon grid, and writes the app and `.rdraft`
document icons to `build/icons/` (the window also shows the app icon in the
Dock when run from `.venv`). Either way the page
is a **Civil 3D-style workspace**: a ribbon (Home / Insert / Annotate / View /
Output) whose panels carry Civil 3D's groupings — Palettes, Draw, Create
Design, Modify, Layers, Annotation; Block, Reference, Sheet; Labels & Tables;
Navigate, Display; Print, Export, Document — each command with its own SVG icon and
a highlighted selected state; a **Toolspace** tree (Layers / Sheets /
References, Prospector-style); a quick-access bar (new/open/save/save
as/undo/redo);
AutoCAD-style **Model/layout tabs at bottom-left**; the docked command line;
and a status bar with coordinate readout and an **ORTHO** toggle (F8). Model
space renders on the AutoCAD dark canvas (black/white linework flips to
light; sheets stay white paper) — toggle in View ▸ Display.

- **Design tools**: the **Alignment** tool (key G) lays an alignment out by
  PI — click PIs in order (curves of the last radius used preview as you go,
  a PI circled red where one would not fit), press Enter, name it and give
  the interior PIs a radius, or 0 to lay out tangents only and add curves
  later. Clicking a drawn alignment (or its Toolspace row, or **Edit
  Alignment…**) selects the alignment itself, Civil 3D style: drag a
  triangle to move a PI, a curve's circle to change its radius (onto the PI
  to remove it), a hollow square in a corner to add a curve, or one on a leg
  to add a PI; the Properties panel lists every PI's X, Y and radius, with ✕
  to delete one. Each edit is one `modify_alignment` (angle points allowed,
  `redraw` on) that redraws the centerline on its own layer, so one Undo
  takes it back; labels and stationing anchored to the alignment are named
  in a warning, to re-run. The **Toolspace ▸ Alignments** node lists every
  alignment with its station range and curve count (draw / delete glyphs);
  the Station tool's dialog offers *design mode* by alignment;
  **Annotate ▸ Label** opens the anchored-label form (alignment, anchor, kind,
  side, rotation, content); **Curve Table** and **Output ▸ LandXML** are one
  click.
- **Drawing tools** (ribbon or keys V/H/L/P/C/A/T/S/M/E/I/X): Select
  (hit-test pick — the entity itself lights up with a glow traced along its
  actual geometry, not a box, and its grips appear; Delete to erase), Pan, Line, Polyline, Circle
  (center+radius point), 3-point Arc, Text, **Station**, **Move** (entity →
  base point → destination, with the true shape as the drag ghost),
  **Erase** (click to delete), **Insert Block**
  (pick from the document's block library), and **Edit Text** — with
  crosshair, rubber-band previews, Shift/ORTHO constraint, wheel zoom (true
  re-render at the new window, not pixel scaling), and a live coordinate
  readout in feet/inches. Every click emits the same journaled command an AI
  would send.
- **Properties panel**: selecting an entity docks an AutoCAD-style
  Properties palette under the Toolspace — Layer, Color (named colors, a
  custom picker, or back to ByLayer), and Linetype dropdowns plus the
  entity's own fields (line endpoints with live length/angle, circle/arc
  center-radius-angles, text content/height/rotation/justification/style,
  block position/scale/rotation, table title/text height). Each change
  applies instantly and the panel re-syncs from the document.
- **Grips**: a selected entity shows AutoCAD's grips — small blue squares on
  the points that can be edited. Drag one, or click it to pick it up (it
  turns red and follows the cursor) and click again to set it; Esc lets go. A
  line gets both endpoints plus a midpoint that moves the whole line; a
  polyline gets every vertex plus hollow midpoint grips that *add* one; a
  circle gets its center and four quadrant grips that re-radius it; an arc
  gets center, radius and end-angle grips; text, blocks and tables get their
  insertion point; a dimension gets the points it measures and the place its
  line was dragged to — move a measured point and the number re-derives. A
  dashed ghost of the real shape shows the edit before it lands, Shift/ORTHO
  constrains the drag, and the grab radius is the same few pixels at any
  zoom. Every grip commits the same journaled `modify_entity` the Properties
  panel sends, so it validates and undoes identically; reference elements are
  read-only and get none.
- **Editing**: double-click any entity with the Select tool (or select it and
  press Enter) for the full in-place editor. Text gets
  a full editor — multiline content, height, rotation, justification, style,
  layer; tables get a cell editor (headers and rows as `A | B | C` lines);
  everything else gets a generic Properties form covering every field,
  including clearing color/linetype back to ByLayer. All edits flow through
  the journaled `modify_entity` command, which validates geometry, enums,
  positive dimensions, row/column consistency, and field names with teaching
  errors — a bad edit can never corrupt the document.
- **The Station tool** is the roadway feature: click the centerline elements
  in order (line–arc–line…), press Enter, set begin station/interval, and the
  `annotate_stationing` command walks the path and generates perpendicular
  ticks, upright '12+34.56' labels rotated along the alignment, and BC/EC/PCC
  labels at the curve points.
- **References panel**: attach basefiles (other RoadDraft documents) as
  xrefs / reference attachments — toggle display, gray-out, detach, reload;
  status, resolved path and true-scale factor per attachment; expand a row
  for per-level display toggles. Insert ▸ Reference ▸ Clip picks a polygon
  and applies it as a clip boundary or mask; the Select tool locates
  reference elements read-only.
- **Output ▸ Print…** (or Ctrl/Cmd+P) opens the plot dialog over `print_pdf`:
  what to print (the space you are in, model space, one sheet, all sheets),
  paper, orientation, scale, whether a model print takes the current view or
  the extents, and monochrome. The log says what each page was plotted at.
- **File ▸ New / Open… / Save / Save As…** (the quick-access bar, Output ▸
  Document, or ⌘N / ⌘O / ⌘S / ⇧⌘S from anywhere, the command line
  included). Open and Save As show the standard macOS file dialogs. The
  title bar names the file and marks unsaved changes with ●, and opening
  or starting a drawing over unsaved work asks Save / Don't Save / Cancel
  first. A drawing's files follow it: exports, the journal and any relative
  path typed on the command line land beside the drawing. A drawing that has
  never been saved keeps them in `~/Documents/RoadDraft`. `--out-dir`
  sends exports somewhere else.
- Model/sheet tabs, layer manager, log with teaching errors, exports
  (DXF/PDF/journal), and an AutoCAD-style command bar speaking the same
  grammar as the terminal REPL (`help` lists everything).

The server is stdlib-only (no framework), binds to 127.0.0.1, serves the same
`Session` over `/api/execute`, `/api/query`, `/api/line`, and
`/api/manifest`, opens and saves drawings over `/api/file`, streams change
events over SSE, and renders any space at
`/render/<ref>.png` (with pixel→coordinate metadata headers) — so it doubles
as the first slice of the M2 session server: an agent can drive the same HTTP
surface a human sees. Open a saved document with
`roaddraft-web project.rdraft`.

### Build the Mac app

```bash
scripts/build_app.sh                 # -> dist/RoadDraft.app, about 70 MB
```

One script does the whole build: it makes or refreshes `.venv-build`, rebuilds
the icons, and runs PyInstaller on `packaging/RoadDraft.spec`. The app carries
its own Python and opens like any Mac app, so drag it to Applications. Built
and signed for local use on this Mac, it opens here without a Gatekeeper
prompt; another Mac needs it signed with a Developer ID and notarized. The
first launch builds matplotlib's font list (about 10 s, kept in
`~/Library/Caches/RoadDraft`); later launches are ready in about a second.
`.rdraft` files show RoadDraft's document icon in Finder but open from inside
the app (File ▸ Open): RoadDraft declares the type without claiming to open it.

### Drive it as a human — terminal REPL (PRD 5.4)

```bash
.venv/bin/roaddraft --project "SR 100"
```

```
RD [model]> mklayer V-ALIGN-CNTR color=red linetype=center
RD [model]> line 1000,1000 1600,1000
RD [model]> sheet C-101 size=ANSI_D
RD [model]> viewport sheet=C-101 center_paper=17,12 width_in=31 height_in=18 model_center=1300,1000 feet_per_inch=50
RD [model]> space C-101
RD [C-101]> text 1,20.5 "GENERAL NOTES:" height=0.15
RD [C-101]> titleblock C-101 project="SR 100" sheet_title="ROADWAY PLAN"
RD [C-101]> render C-101 open
RD [C-101]> journal session.jsonl        # a replayable expert trajectory
RD [C-101]> space model
RD [model]> alignment ALIGN-1 1000,1000 1814.359354,1000,800 2433.012702,1357.179677 begin_station=10+00
RD [model]> drawalign ALIGN-1 layer=V-ALIGN-CNTR
RD [model]> station alignment=ALIGN-1
RD [model]> label PC-1
RD [model]> label T-2 kind=bearing
RD [model]> sta2xy 16+00 ALIGN-1        design curves        anchor MC-1
RD [model]> space C-101
RD [C-101]> curvetable 24,8.5 ALIGN-1
RD [C-101]> print paper=ANSI_B scale=1:2 open   # half-size check print of this sheet
RD [C-101]> print model paper=ANSI_D scale=50   # the design at 1"=50'
RD [C-101]> landxml                      # export the design as LandXML
RD [C-101]> annoscale 100                # 1"=100': re-size annotative model annotation
RD [C-101]> annoscales                   # the scale list, paper defaults, model sizes
```

`help` lists everything; `help <command>` prints any command's schema and
example. The REPL is a thin skin over the same `Session` — human sessions are
recorded trajectories, and the playtest rule holds: if a PE can't draft a
100-score sheet with these tools, the action space is broken, not the model.

## Outputs

- **PNG** — sheets render at true paper size (WYSIWYG text heights); the
  vision observation for agents. `render_model` renders design space.
- **PDF** — two ways out. `export_pdf` dumps every sheet at its own paper
  size; `print_pdf` is the **plot dialog**: print one space (a sheet or a
  window of model space), a set of sheets, or the lot, onto the paper you
  choose at the scale you choose — fit-to-page, a half-size set
  (`scale="1:2"` on a D sheet lands exactly on ANSI_B), or a true plot scale
  in model space (`scale=50` is 1"=50'), with margins, portrait/landscape and
  monochrome. A plot that would run off the paper fails with the scale that
  would fit, and the result says what each page was plotted at.
- **DXF** — real layers/linetypes/lineweights, blocks, paper-space layouts,
  and viewports (scale and twist); opens in AutoCAD/Civil 3D and
  MicroStation. DXF is a render target — the JSON document is the truth.
- **LandXML 1.2** (`export_landxml`) — alignments and profiles for Civil 3D / ORD.
- **The document itself** (`save_document`) and its **journal** (`save_journal`).

### The document file

A drawing is `Document.to_dict()` serialized as JSON. Two file shapes carry it:

| | | |
|---|---|---|
| `.rdraft` | the application document | what a person saves, sends and (once the desktop build lands) double-clicks — the extension RoadDraft registers with the OS as its own filetype |
| `.rdoc.json` | the open interchange form | plain JSON, diffable in git; task fixtures, probe fixtures and `examples/output/` stay here |

They hold identical bytes today, and a reader picks between them by **content,
not extension** — so a renamed or extension-less file still opens, and either
shape can be attached as a reference from the other. `save_document` appends
`.rdraft` to a path that carries neither, and returns the path it wrote.

They are separate names because the application document is meant to grow a zip
container (document + journal + embedded references + thumbnail, so a project
travels as one file) while the interchange form is not: a container would cost
the line-by-line diffs the fixtures rely on. Every read and write goes through
`document/fileformat.py`, so that change lands in one file.

## Layout

```
src/roaddraft/
  core/        units (stations, US survey ft), colors, geometry + viewport transform
  design/      pure roadway math: alignments (PIs, curves, station equations),
               profiles (PVIs, vertical curves), anchors, label placement/wording
  adapters/    LandXML 1.2 reader/writer (stdlib XML only)
  document/    entities (+ design anchors, dimensions), layers/styles/blocks,
               sheets/viewports, references (+ clipping), the Document (+ the
               design model), dimgeom (how a dimension is drawn),
               fileformat (what a drawing is on disk: .rdraft / .rdoc.json)
  commands/    JSON schemas, handlers (+ design_, annotation_, dimension_handlers),
               the command bus
  render/      shared border/title block templates (standard, Caltrans plan
               sheet, none), matplotlib PNG/PDF, ezdxf DXF
  api/         Session (execute/query/manifest) + the shared command-line grammar
  cli/         the terminal REPL
  web/         the GUI: stdlib HTTP/SSE server + single-file browser UI
  desktop/     the GUI in a window of its own (pywebview), its log and close guard
  tasks/       DRAFT standards + drafting spec, the seeded D1 task generator,
               ground truth, and the reference solution (python -m roaddraft.tasks)
  probes/      capability probes (find, drafting, tier 2, tier 3), their fixture
               documents, the plotted-sheet reader and the notation parsers;
               l2/ builds Caltrans sheet L-2 (python -m roaddraft.probes)
tests/         787 tests: geometry, design math, commands, dimensions,
               determinism, LandXML, renders, DXF, web server, tasks
examples/      demo_plan_sheet.py — a full sheet drafted from the design model;
               caltrans_l2/ — a published Caltrans plan sheet rebuilt as a
               model file + a sheet file that references it;
               generate_task.py — task seed 42 end to end
benchmarks/    knowledge/ — reference standards behind the drafting spec (Caltrans PPM text + page index; see its README)
               probe_runs/ — real-model probe runs: writeups, rigs, traces and the documents scored (see its README)
               probe_references/ — every probe's scripted solution as a finished project: document, journal, PDF, DXF
scripts/       build_knowledge.py — rebuilds the knowledge base from the raw PDFs
```

## What this is not (yet)

Phase 1 (the design model, anchored labels, LandXML, and the D1 task
generator) is in. Still to come, on top of this bus:

- **Verifier + eval harness (M2/M3)**: rubric scoring against the ground truth
  (`roaddraft.verify`), the harness, and scored agent episodes — see
  `RoadDraft_Eval_Plan.md`. Parked until an agent can draft and annotate from
  natural language at all; MCP mode (above) is the front door for that.
- **Spirals** (`"spiral"` is reserved and rejected everywhere), asymmetric
  vertical curves, **profile views** on sheets, station-offset labels, match
  lines and multi-sheet sets (D2/D3).
- **PE review** of the DRAFT standards tables and drafting spec before any
  published task set; task ids carry the spec hash so corrections mint new
  ids.
