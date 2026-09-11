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
| Sheet (inches) + border/title block | Paper-space layout | Sheet model |
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
  formats stations ('12+34.56'), keeps labels upright, and marks PC/PT/PCC.
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
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                      # 410 tests
.venv/bin/python examples/demo_plan_sheet.py   # drafts a full plan sheet
.venv/bin/python -m roaddraft.tasks 42         # generates a D1 task + reference solution
```

The demo drafts C-101 (ANSI D) from a design-model alignment: centerline
drawn from the alignment, pavement edges from station/offset queries,
alignment-mode stationing (ticks, labels, PC/PT), anchored bearing and
mid-curve callouts, the curve data table, north arrow, notes, filled title
block — then renders PNG/PDF, exports DXF and LandXML, and proves the
journal replays byte-identically (26 commands).

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
s.execute("place_label", {"space": "model", "anchor": "PC-1"})        # "PC 16+00.00"
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
  `MC-n`, `T-n`, `EQ-n`, or a station (`18+00`, `1800`), optionally with an
  offset (`PC-1@16`, `18+00@25L`, right positive). `place_label` resolves the
  anchor, infers the label kind (`station`, `pc`, `pt`, `pi`, `mc`, `pcc`,
  `prc`, `bearing`, `begin`, `end`, `equation`, `curve_data`, `custom`),
  writes the conventional wording, places the text on the conventional side
  with the conventional offset, keeps it upright, and — on a sheet — maps it
  through the viewport that shows the point. The text entity records an
  `anchor` (`alignment`, `ref`, `kind`, `station`, `offset`, `side`,
  `label_offset`, `rotation`, `viewport`, `content_auto`): the verifier's
  contract. `resolve_anchor` is the dry run.
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

### Drive it as a human — GUI (PRD M3 thin viewer)

```bash
.venv/bin/roaddraft-web --project "SR 100"
```

…or double-click `RoadDraft.command` in Finder. A browser window opens with a
**Civil 3D-style workspace**: a ribbon (Home / Insert / Annotate / View /
Output) whose panels carry Civil 3D's groupings — Palettes, Draw, Create
Design, Modify, Layers, Annotation; Block, Reference, Sheet; Labels & Tables;
Navigate, Display; Export, Document — each command with its own SVG icon and
a highlighted selected state; a **Toolspace** tree (Layers / Sheets /
References, Prospector-style); a quick-access bar (save/undo/redo);
AutoCAD-style **Model/layout tabs at bottom-left**; the docked command line;
and a status bar with coordinate readout and an **ORTHO** toggle (F8). Model
space renders on the AutoCAD dark canvas (black/white linework flips to
light; sheets stay white paper) — toggle in View ▸ Display.

- **Design tools**: the **Alignment** tool (key G) — click PIs in order, press
  Enter, name it, give the interior PIs a radius, and it is created and drawn;
  the **Toolspace ▸ Alignments** node lists every alignment with its station
  range and curve count (draw / delete glyphs; click to prefill alignment-mode
  stationing); the Station tool's dialog offers *design mode* by alignment;
  **Annotate ▸ Label** opens the anchored-label form (alignment, anchor, kind,
  side, rotation, content); **Curve Table** and **Output ▸ LandXML** are one
  click.
- **Drawing tools** (ribbon or keys V/H/L/P/C/A/T/S/M/E/I/X): Select
  (hit-test pick — the entity itself lights up with a glow traced along its
  actual geometry, not a box; Delete to erase), Pan, Line, Polyline, Circle
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
  ticks, upright '12+34.56' labels rotated along the alignment, and PC/PT/PCC
  labels at tangent-curve junctions.
- **References panel**: attach basefiles (other RoadDraft documents) as
  xrefs / reference attachments — toggle display, gray-out, detach, reload;
  status, resolved path and true-scale factor per attachment; expand a row
  for per-level display toggles. Insert ▸ Reference ▸ Clip picks a polygon
  and applies it as a clip boundary or mask; the Select tool locates
  reference elements read-only.
- Model/sheet tabs, layer manager, log with teaching errors, exports
  (DXF/PDF/save/journal), and an AutoCAD-style command bar speaking the same
  grammar as the terminal REPL (`help` lists everything).

The server is stdlib-only (no framework), binds to 127.0.0.1, serves the same
`Session` over `/api/execute`, `/api/query`, `/api/line`, and
`/api/manifest`, streams change events over SSE, and renders any space at
`/render/<ref>.png` (with pixel→coordinate metadata headers) — so it doubles
as the first slice of the M2 session server: an agent can drive the same HTTP
surface a human sees. Open a saved document with
`roaddraft-web project.rdoc.json`.

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
RD [C-101]> landxml                      # export the design as LandXML
```

`help` lists everything; `help <command>` prints any command's schema and
example. The REPL is a thin skin over the same `Session` — human sessions are
recorded trajectories, and the playtest rule holds: if a PE can't draft a
100-score sheet with these tools, the action space is broken, not the model.

## Outputs

- **PNG** — sheets render at true paper size (WYSIWYG text heights); the
  vision observation for agents. `render_model` renders design space.
- **PDF** — multi-sheet plan set at paper size.
- **DXF** — real layers/linetypes/lineweights, blocks, paper-space layouts,
  and viewports (scale and twist); opens in AutoCAD/Civil 3D and
  MicroStation. DXF is a render target — the JSON document is the truth.
- **LandXML 1.2** (`export_landxml`) — alignments and profiles for Civil 3D / ORD.
- **JSON snapshot** (`save_document`) and **journal** (`save_journal`).

## Layout

```
src/roaddraft/
  core/        units (stations, US survey ft), colors, geometry + viewport transform
  design/      pure roadway math: alignments (PIs, curves, station equations),
               profiles (PVIs, vertical curves), anchors, label placement/wording
  adapters/    LandXML 1.2 reader/writer (stdlib XML only)
  document/    entities (+ design anchors), layers/styles/blocks, sheets/viewports,
               references (+ clipping), the Document (+ the design model)
  commands/    JSON schemas, handlers (+ design_handlers), the command bus
  render/      shared title block template, matplotlib PNG/PDF, ezdxf DXF
  api/         Session (execute/query/manifest) + the shared command-line grammar
  cli/         the terminal REPL
  web/         the GUI: stdlib HTTP/SSE server + single-file browser UI
  tasks/       DRAFT standards + drafting spec, the seeded D1 task generator,
               ground truth, and the reference solution (python -m roaddraft.tasks)
tests/         410 tests: geometry, design math, commands, determinism, LandXML,
               renders, DXF, web server, tasks
examples/      demo_plan_sheet.py — a full sheet drafted from the design model;
               generate_task.py — task seed 42 end to end
benchmarks/    knowledge/ — reference standards behind the drafting spec (Caltrans PPM text + page index; see its README)
scripts/       build_knowledge.py — rebuilds the knowledge base from the raw PDFs
```

## What this is not (yet)

Phase 1 (the design model, anchored labels, LandXML, and the D1 task
generator) is in. Still to come, on top of this bus:

- **Verifier + session server + MCP mode (M2)**: rubric scoring against the
  ground truth (`roaddraft.verify`), the eval harness, and the first agent
  episodes — see `RoadDraft_Eval_Plan.md`.
- **Spirals** (`"spiral"` is reserved and rejected everywhere), asymmetric
  vertical curves, **profile views** on sheets, station-offset labels, match
  lines and multi-sheet sets (D2/D3).
- **PE review** of the DRAFT standards tables and drafting spec before any
  published task set; task ids carry the spec hash so corrections mint new
  ids.
