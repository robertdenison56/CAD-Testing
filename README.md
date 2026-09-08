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
  reference attachment): the host stores path + offset/rotation/scale, the
  basefile's model geometry renders under every space and sheet viewport,
  reloads from disk, exports to DXF on bound `<NAME>$<layer>` layers, and is
  never copied into the host document.

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
.venv/bin/pytest                      # 47 tests
.venv/bin/python examples/demo_plan_sheet.py   # drafts a full plan sheet
```

The demo drafts C-101 (ANSI D): centerline with a 30° curve, pavement edges,
station ticks/labels, PC/PT and bearing callouts, curve data table, north
arrow, notes, filled title block — then renders PNG/PDF, exports DXF, and
proves the journal replays byte-identically.

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
  xrefs / reference attachments — toggle display, detach, reload; status
  shown per attachment.
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
- **JSON snapshot** (`save_document`) and **journal** (`save_journal`).

## Layout

```
src/roaddraft/
  core/        units (stations, US survey ft), colors, geometry + viewport transform
  document/    entities, layers/styles/blocks, sheets/viewports, the Document
  commands/    JSON schemas, handlers, the command bus (validate/apply/journal/undo)
  render/      shared title block template, matplotlib PNG/PDF, ezdxf DXF
  api/         Session (execute/query/manifest) + the shared command-line grammar
  cli/         the terminal REPL
  web/         the GUI: stdlib HTTP/SSE server + single-file browser UI
tests/         59 tests: geometry, commands, determinism, renders, DXF, web server
examples/      demo_plan_sheet.py — a full sheet drafted through the tool surface
benchmarks/    knowledge/ — reference standards behind the drafting spec (Caltrans PPM text + page index; see its README)
scripts/       build_knowledge.py — rebuilds the knowledge base from the raw PDFs
```

## What this is not (yet)

Per the build plan's vertical-slice rule, this milestone is the CAD substrate
(M0 + renderer/M1 slice + human-play early). Coming next, on top of this bus:

- **Geometry core (Phase 1)**: alignments (tangent/curve/spiral), profiles,
  stationing engine, LandXML I/O, the procedural task generator and
  ground-truth label computer. Semantic anchors (`place_label(anchor="PC-3")`)
  arrive with it — today's `place_text` is the coordinate-level primitive it
  will compile down to.
- **Verifier + session server + MCP mode (M2)**: rubric scoring and the
  first agent episodes.
