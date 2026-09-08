I have verified the codebase facts and the hand-calc numbers. One correction to the brief stands: for R=800, Δ=30°, **E = 28.221** (the brief's 28.211 is a typo; all three proposals caught it). Other verified numbers: T=214.359, L=418.879, M=27.259, C=414.110, D_c=7.162; VC A=5, K=80, high point x=160 (STA 19+60, elev 117.6 for PVI 20+00 @ 120.0). Below is the judgment and the final spec.

# Part (a) — Proposal review

## Proposal A (geometry-first)
Strongest ideas: the `_Piece` seam analysis is right; `E/M/C/D_c` formulas and every hand calc (except two typos) are correct; the region-based tick enumeration for station equations; the reverse-curve and compound-curve test fixtures with exact stations; PI recovery on LandXML import; the `xy_to_station` "no valid projection is a teaching error" design; disjoint WP layout with function-local import to break the `handlers ↔ design_handlers` cycle.
Errors: (1) MC-1 point is (1807.055, **1027.259**), not 1027.262. (2) Sag hand calc wrong: PVC (750, 77.5), low point at x=300 gives **73.0**, not 70.75 (r/2·x² = 4.5, not 2.25). (3) Its equation test claims `"20+00.00"` is labelled at the region-1 end — contradicts half-open regions (the equation point reads AHEAD). (4) Always emitting `"anchor": null` changes the serialized shape of every existing Text and Table. (5) Puts `anchor` only on Text/Table, so ticks and drawn linework cannot carry provenance. (6) Numeric station inputs = raw is counter-intuitive for humans.

## Proposal B (agent-interface-first)
Strongest ideas: `anchor` on the `Entity` base with sparse emission + `known` set edit; `content_auto` recorded on the entity; kind inference from the anchor ref; `resolve_anchor` dry-run query; `replace` on `draw_alignment`; duplicate-label warning; number and string station inputs both DISPLAY stations; one shared placement/wording module used by commands and ground truth; a "details" idea (dropped, see below); the verifier `checks` name list in the spec.
Errors: (1) `set_annotation_scale`, `get_task_brief`, `alignments_visible` in `get_sheet_state`, `_diff(details)` bus change — scope creep beyond the brief. (2) `label_content` reads a `tasks` spec dict from `core` — wrong dependency direction. (3) Metric example "x = 999.998 ft for 304.8 m" is correct, but its `sag` example mixes two PVI sets. (4) Stage plan tests handlers by direct calls without the bus until Stage 4 — weak. (5) C3D alias `ALIGNMENT` collides with nothing but is not a real command; `ADDLABEL` is generic.

## Proposal C (integration-first)
Strongest ideas: `from_dict` trusts stored elements (no silent recompute; exact `from_dict(to_dict())`); `anchor` on `Entity` base; `<ref>[@<offset>]` anchor grammar (single token, REPL-safe, no `+` ambiguity); half-open region semantics with the equation point reading AHEAD; "commit the working tree first"; `spec_hash` inside `task_id`; explicit DO-NOT-TOUCH lists; `station_range` on stationing; the observation that `_path_eval` returns the incoming element at junctions.
Errors: (1) `mid_ordinate: 27.258994` — correct value is 27.259339. (2) Metric test "R=243.84 m → 800.000 ft" is wrong: 243.84 m = 800 international ft = **799.998** US survey ft. (3) Its overlap-fault fixture `[0,0],[400,0,800],[800,400]` does NOT fault (T=331.4 ≤ 400). (4) Curve table row uses `"C1"` while anchors use `C-1`. (5) Sheet viewport selection by `visible_model_bbox` (AABB) is not twist-safe. (6) `A = g2−g1` signed conflicts with the brief's "A=5".

# Part (b) — Conflict resolutions

| # | Conflict | Decision | Rationale |
|---|---|---|---|
| 1 | Package name `design/` vs `core/*` vs `io/` vs `adapters/` | `roaddraft/design/` (math), `roaddraft/adapters/landxml.py` (I/O), `roaddraft/tasks/` | `io` shadows a stdlib name in readers' heads; `design` matches the PRD vocabulary; `core/` stays untouched so no WP touches it. |
| 2 | `anchor` on Text/Table (A) vs `Entity` base (B, C) | `Entity` base, sparse emission, `"anchor"` added to `modify_entity`'s `known` literal | Ticks and linework need provenance; sparse emission keeps every existing entity's JSON byte-identical. |
| 3 | `from_dict` recompiles from PIs (A) vs trusts stored elements (C) | Trust stored elements | Exact round trip, cheapest snapshot restore, no silent re-derivation across math versions. |
| 4 | Numeric station input = raw (A) vs display (B, C) | Display everywhere at the API; raw internally; outputs carry both | Humans type printed stations; D1 defaults to zero equations so raw == display. |
| 5 | Anchor grammar `18+00 R25` (A) / `STA 12+34 R 25 @2` (B) / `PC-1@16` (C) | `REF[@OFFSET[L\|R]]`, dict form for region | Single shlex token; `+` stays station notation; region only via dict (D1 never needs it). |
| 6 | Equation region closed at the end (A test) vs half-open (B, C) | Half-open `[start, end)`; last region closed; equation point reads AHEAD | Matches LandXML `staAhead` semantics and makes ticks at the equation point unambiguous. |
| 7 | Annotation scale setting (B) | Dropped | The task brief states model text heights in feet; engine defaults 8/10/16 ft are unchanged. |
| 8 | `curve_data` as label kind (A) vs fault → table (B) | Both: `place_curve_table` is the table; `place_label kind=curve_data` is a multi-line callout at MC-n | Cheap, conventional, and the brief allows either. |
| 9 | Element-list JSON stores derived T/E/M/C (B, C) vs geometry only (A) | Geometry only + `length`/`start_dist`; derived values via `curve_data()` and `get_design_data` | One source of truth; smaller per-command snapshots. |
| 10 | Stationing refactor: adapter to `_Piece` (A) / lifted emitter (C) / duplicate loop | Early branch in `annotate_stationing` to `design_handlers.annotate_stationing_alignment`; entity mode untouched; alignment mode materialises a `design.labels.stationing_plan()` | Zero risk to entity mode; ground truth calls the same `stationing_plan`. |
| 11 | Sheet viewport selection: paper-frame containment (A) vs AABB (C) | `to_paper(point)` inside `vp.paper_bbox()` | Twist-safe. |
| 12 | Delete alignment cascades profiles (B, C) vs faults (A) | Fault unless `cascade: true` | Explicit teaching error over hidden cascade. |
| 13 | `_upright` side-flip gotcha | Kept in both modes, flagged for PE review | Byte-identical entity mode; ground truth mirrors the engine. |
| 14 | Design pre-seeded in task baseline (B) vs `create_alignment` in trajectory (A, C) | Pre-seeded in the baseline document | D1 is a *drafting* task; the design is given; `get_design_data` is the agent's source. |
| 15 | Task id form | `D1-{seed:06d}-{sha256[:12]}`, hash covers generator_version + spec_hash + project + design + deliverable | Seed visible, content pinned. |
| 16 | `A` signed (C) vs absolute (A, B) | `A = |g2−g1|·100`, `type` carries crest/sag | Brief says A=5. |
| 17 | Stage plan | 4 stages, tests through the bus from Stage 3 | Disjoint files, bus-level acceptance. |

---

# RoadDraft Phase 1 — FINAL BUILD SPEC (Design Model, Anchored Labels, LandXML, D1 Task Generator)

All paths are relative to `/Volumes/RobertsExternalSSD/repos/CAD Testing/`. Python 3.9: `from __future__ import annotations`, `typing.Optional/List/Dict/Tuple`, no `match`, no `X | Y`, no dataclass `slots`. Only stdlib + ezdxf/matplotlib/jsonschema. No CAD-program imports anywhere. Every new command follows the three-file recipe (schema + example, handler, `CommandSpec`).

**Stage 0 (before any WP starts):** commit the current working tree as the Phase 1 baseline (`git add -A && git commit -m "Phase 1 baseline"`). Every WP branches from that commit. Baseline: 91 tests pass with `.venv/bin/pytest -q`.

## 0. Global conventions (normative)

| Item | Convention |
|---|---|
| Points | `[x, y]` lists, US survey feet in model space; x = easting, y = northing |
| `direction_deg` | math heading, degrees CCW from +X (same as `Arc`, `_line_piece`) |
| `azimuth_deg` | clockwise from north = `(90 − direction_deg) % 360` |
| Quadrant bearing | `N 45°30'15" E`; degrees zero-padded to 2 digits; integer seconds by default; az∈[0,90]→`N az E`; (90,180]→`S (180−az) E`; (180,270]→`S (az−180) W`; (270,360)→`N (360−az) W` |
| DMS (deltas) | `30°00'00"` — degrees NOT padded; seconds rounded with carry (59.6" → next minute) |
| Δ | `delta_deg` always positive in (0, 180); turn sense in `direction` = `"L"` (CCW ahead) / `"R"` |
| Raw station | `begin_station + distance_along` (continuous). Stored everywhere internally (PVIs, anchor records) |
| Display station | raw mapped through equations; what labels print. **All API station inputs are display** (number or `"12+34.56"`); outputs carry `station` (raw) and `station_text` (display) |
| Offsets | feet, **positive = right of increasing station**; `right_normal(θ) = [sin θ, −cos θ]`, `left_normal(θ) = [−sin θ, cos θ]` |
| Grades | stored as ratio (0.02); reported as percent (`2.0`) with key suffix `_pct` |
| Element kinds | `ELEMENT_KINDS = ("tangent", "curve", "spiral")`; `"spiral"` is reserved and **rejected** by `element_from_dict` / LandXML with `"spiral elements are not supported in this version"` |
| Tolerances | `GEOM_EPS = 1e-6` ft, `ANGLE_EPS = 1e-9` deg, `STATION_EPS = 1e-6` ft, `CONNECT_TOL = 1e-3` ft (LandXML continuity) |
| Diff entries | `"alignment:NAME"`, `"profile:NAME"`, entity ids |
| Errors | `design.errors.DesignError(message, hint)`; handlers re-raise as `CommandFault(str(e), hint=e.hint)`; queries as `_QueryFault` |
| Curve numbering | `C-n`, `PC-n`, `PT-n`, `PI-n`, `MC-n`: n = 1-based index of the curve in travel order. `T-n`: 1-based tangent index. `EQ-n`: 1-based equation index |

## 1. File layout and ownership

| Path | Status | WP |
|---|---|---|
| `src/roaddraft/design/__init__.py` | NEW | WP1 |
| `src/roaddraft/design/errors.py` | NEW | WP1 |
| `src/roaddraft/design/angles.py` | NEW | WP1 |
| `src/roaddraft/design/stations.py` | NEW | WP1 |
| `src/roaddraft/design/horizontal.py` | NEW | WP1 |
| `src/roaddraft/design/vertical.py` | NEW | WP1 |
| `src/roaddraft/design/anchors.py` | NEW | WP1 |
| `src/roaddraft/design/labels.py` | NEW | WP1 |
| `src/roaddraft/design/model.py` | NEW | WP1 |
| `tests/test_design_angles.py`, `tests/test_design_stations.py`, `tests/test_design_horizontal.py`, `tests/test_design_vertical.py`, `tests/test_design_anchors.py`, `tests/test_design_labels.py` | NEW | WP1 |
| `src/roaddraft/tasks/__init__.py` (docstring only, never edited later) | NEW | WP2 |
| `src/roaddraft/tasks/standards.py` | NEW | WP2 |
| `src/roaddraft/tasks/spec_v1.py` | NEW | WP2 |
| `tests/test_spec_v1.py` | NEW | WP2 |
| `src/roaddraft/commands/design_schemas.py` | NEW | WP3 |
| `tests/test_design_schemas.py` | NEW | WP3 |
| `src/roaddraft/document/document.py` | MOD | WP4 |
| `src/roaddraft/document/entities.py` | MOD | WP4 |
| `tests/test_design_document.py`, `tests/fixtures/legacy_v01.rdoc.json` | NEW | WP4 |
| `src/roaddraft/adapters/__init__.py`, `src/roaddraft/adapters/landxml.py` | NEW | WP5 |
| `tests/test_landxml.py`, `tests/fixtures/landxml/{demo_cl.xml, metric_line.xml, spiral_cl.xml, gap_cl.xml}` | NEW | WP5 |
| `src/roaddraft/commands/design_handlers.py` | NEW | WP6 |
| `src/roaddraft/commands/handlers.py` | MOD | WP6 |
| `src/roaddraft/commands/schemas.py` | MOD | WP6 |
| `src/roaddraft/commands/bus.py` | MOD | WP6 |
| `tests/test_design_commands.py`, `tests/test_design_labels_cmd.py`, `tests/test_stationing_alignment.py` | NEW | WP6 |
| `src/roaddraft/api/session.py` | MOD | WP7 |
| `src/roaddraft/api/lines.py` | MOD | WP7 |
| `src/roaddraft/cli/repl.py` | MOD | WP7 |
| `tests/test_design_queries.py` | NEW | WP7 |
| `src/roaddraft/web/server.py` | MOD | WP8 |
| `src/roaddraft/web/static/index.html` | MOD | WP8 |
| `tests/test_web_design.py` | NEW | WP8 |
| `src/roaddraft/tasks/brief.py`, `tasks/generator.py`, `tasks/ground_truth.py`, `tasks/reference.py`, `tasks/__main__.py` | NEW | WP9 |
| `tests/test_tasks.py`, `tests/fixtures/task_ids_d1_v1.json`, `examples/generate_task.py` | NEW | WP9 |
| `README.md`, `examples/demo_plan_sheet.py` | MOD | WP10 |
| `tests/test_design_integration.py` | NEW | WP10 |

Never modified by anyone: `src/roaddraft/core/*`, `src/roaddraft/render/*`, `src/roaddraft/document/sheets.py`, `document/references.py`, all existing `tests/test_*.py`.

Import direction (enforced by a grep test in WP1 and WP5): `design` → `core` only. `adapters` → `core`, `design` only. `document` → `design.model`. `commands` → everything below. `tasks` → `design`, `api`, `document`, `tasks.*`. Nothing in `design`, `adapters`, `document` imports `commands`, `api`, `web`, `tasks`.

## 2. Data model

### 2.1 `design/errors.py`
```python
class DesignError(Exception):
    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message); self.hint = hint
```

### 2.2 `design/stations.py`
```python
@dataclass
class StationEquation:
    raw_station: float   # raw station where the equation sits (== LandXML staInternal)
    back: float          # display station reading just before it (== staBack)
    ahead: float         # display station reading at and after it (== staAhead)
    def to_dict(self) -> dict            # {"raw_station", "back", "ahead"}
    @classmethod
    def from_dict(cls, d) -> "StationEquation"

@dataclass
class Region:            # derived, never serialized
    index: int           # 1-based
    raw_start: float; raw_end: float          # raw range; [raw_start, raw_end) except last region closed
    display_start: float; display_end: float
    shift: float         # display = raw + shift within this region
```
Semantics: region 1 covers raw `[begin, eq1.raw)` with shift 0. Region k+1 covers raw `[eq_k.raw, eq_{k+1}.raw)` with `shift = eq_k.ahead − eq_k.raw`. The last region is closed at `begin + length`. Validation (`build_equations`): `raw_station` strictly increasing and strictly inside `(begin, begin+length)`; `back` must equal the display value of `raw_station` computed from the preceding equations within `STATION_EPS`, else `DesignError("equation 2: back station 22+00.00 does not match 20+00.00 computed from the preceding equations", hint="back = the station reading just before the equation point")`. `ahead > back` is a gap, `ahead < back` an overlap; both legal.

### 2.3 `design/horizontal.py`
```python
ELEMENT_KINDS = ("tangent", "curve", "spiral")

@dataclass
class PI:
    point: List[float]
    radius: float = 0.0          # 0 at first/last PI (required); > 0 at every interior PI
    def to_dict(self) -> dict    # {"point": [x, y], "radius": R}
    @classmethod from_dict(cls, d)

@dataclass
class TangentElement:
    start: List[float]; end: List[float]
    length: float; direction_deg: float; start_dist: float
    kind = "tangent"             # class attribute

@dataclass
class CurveElement:
    pc: List[float]; pt: List[float]; pi: List[float]; center: List[float]
    radius: float; delta_deg: float; direction: str      # "L" | "R"
    length: float; start_dist: float
    direction_in_deg: float; direction_out_deg: float
    kind = "curve"

@dataclass
class Alignment:
    name: str
    elements: List[object]                       # Tangent/Curve elements in travel order, never empty
    pis: List[PI] = field(default_factory=list)  # [] when source == "elements"
    begin_station: float = 0.0
    equations: List[StationEquation] = field(default_factory=list)
    description: str = ""
    source: str = "pis"                          # "pis" | "elements"
```
`Alignment.to_dict()` (exact key order):
```json
{"name": "ALIGN-1", "description": "", "source": "pis", "begin_station": 1000.0,
 "pis": [{"point": [1000.0, 1000.0], "radius": 0.0},
         {"point": [1814.359354, 1000.0], "radius": 800.0},
         {"point": [2433.012702, 1357.179677], "radius": 0.0}],
 "equations": [{"raw_station": 2000.0, "back": 2000.0, "ahead": 2500.0}],
 "elements": [
   {"kind": "tangent", "start": [1000.0, 1000.0], "end": [1600.0, 1000.0],
    "length": 600.0, "direction_deg": 0.0, "start_dist": 0.0},
   {"kind": "curve", "pc": [1600.0, 1000.0], "pt": [2000.0, 1107.179677],
    "pi": [1814.359354, 1000.0], "center": [1600.0, 1800.0], "radius": 800.0,
    "delta_deg": 30.0, "direction": "L", "length": 418.87902047863906,
    "start_dist": 600.0, "direction_in_deg": 0.0, "direction_out_deg": 30.0},
   {"kind": "tangent", "start": [2000.0, 1107.179677], "end": [2433.012702, 1357.179677],
    "length": 500.0, "direction_deg": 30.0, "start_dist": 1018.87902047863906}]}
```
`Alignment.from_dict(d)`: reads elements as stored (no recompute); `element_from_dict` raises `DesignError` for unknown kinds and for `"spiral"`; `name` required; missing `pis`/`equations`/`description` default to `[]`/`""`; `source` defaults to `"pis"` if `pis` non-empty else `"elements"`. `from_dict(to_dict())` must be exact.

### 2.4 `design/vertical.py`
```python
@dataclass
class PVI:
    station: float        # RAW station on the parent alignment
    elevation: float
    length: float = 0.0   # symmetric parabolic VC length; MUST be 0 at first/last PVI; 0 at interior = grade break
    def to_dict / from_dict   # {"station", "elevation", "length"}

@dataclass
class Profile:
    name: str
    alignment: str        # alignment name (existence validated by handlers, not here)
    pvis: List[PVI]
    description: str = ""
```
`Profile.to_dict()`: `{"name", "alignment", "description", "pvis": [{"station","elevation","length"}, ...]}`.
Validation (`Profile.validate()`, raised by `from_dict` and by handlers): ≥ 2 PVIs; stations strictly increasing (gap > `GEOM_EPS`); first/last `length == 0`; interior PVI with `length > 0` and equal grades → `DesignError("PVI-2: grades in (+2.00%) and out (+2.00%) are equal; set length to 0 or change the elevation")`; VC must fit: `length/2 <= min(S_k − S_{k−1}, S_{k+1} − S_k) + GEOM_EPS` else `"PVI-2: vertical curve L=800.00 does not fit (300.00 ft to PVI-1)"`; adjacent VCs must not overlap: `PVC_{k+1} >= PVT_k − GEOM_EPS` else `"vertical curves at PVI-2 and PVI-3 overlap by 100.00 ft"`. Asymmetric VCs are out of scope (field stays singular `length`; `length_in/length_out` can be added later).

### 2.5 `design/model.py`
```python
@dataclass
class DesignModel:
    alignments: Dict[str, Alignment] = field(default_factory=dict)
    profiles: Dict[str, Profile] = field(default_factory=dict)
    def to_dict(self) -> dict     # {"alignments": {name: a.to_dict()}, "profiles": {name: p.to_dict()}}
    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "DesignModel"   # d may be None or {} or missing keys
    def profiles_of(self, alignment_name: str) -> List[Profile]
    def fingerprint(self) -> str  # "sha256:" + sha256(json.dumps(to_dict(), sort_keys=True, separators=(",",":")))
```

### 2.6 Document (`document/document.py`, WP4)
- `SCHEMA_VERSION = "0.2"` (still never read).
- `Document.__init__`: `self.design: DesignModel = DesignModel()` after `self.references`.
- `to_dict`: `"design": self.design.to_dict()` after `"references"`, before `"id_counters"`.
- `from_dict`: `doc.design = DesignModel.from_dict(d.get("design", {}))`.
- No `ID_PREFIXES` entry. Snapshot/undo/journal/save cover `design` with zero bus changes.

`.rdoc.json` shape (top level): `schema_version, meta, settings, layers, text_styles, blocks, model, sheets, references, design, id_counters`.

### 2.7 Entity anchor (`document/entities.py`, WP4)
- `Entity` gains `anchor: Optional[dict] = None` (last field).
- `_base_dict`: emit `"anchor"` only when not None (sparse, like color/linetype).
- `_base_kwargs`: `"anchor": as_anchor(d.get("anchor"))`.
- New validator `as_anchor(value)`: returns `None` for None; for a dict, requires string keys `alignment`, `ref`, `kind` (each non-empty); optional keys with types: `station` (number|None), `offset` (number|None), `side` ("left"|"right"|None), `label_offset` (number|None), `rotation` (`"along"|"perpendicular"|"horizontal"`|None), `viewport` (str|None), `content_auto` (bool). Any other key or wrong type → `ValueError("anchor: ...")`. Returns a plain dict copy.
- Every `transformed()` (Line, Polyline, Arc, Circle, Text, BlockRef, Table) passes `anchor=self.anchor`.
- Renderers ignore it (no changes).

**Anchor record shape** (the verifier contract):
```json
{"alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc", "station": 1600.0, "offset": 0.0,
 "side": "right", "label_offset": 16.0, "rotation": "along", "viewport": null, "content_auto": true}
```
Per producer:
- `place_label` Text: all keys; `viewport` = viewport id on sheets else null; `label_offset` in the target space's units (feet in model, inches on sheets).
- `annotate_stationing` (alignment mode) station Text: `{alignment, ref: "18+00.00", kind: "station", station, offset: 0.0, side: "left", label_offset, rotation: "along", viewport: null, content_auto: true}`; tick Line: `{alignment, ref: "18+00.00", kind: "tick", station, offset: 0.0}`; junction Text: `ref "PC-n"/"PT-n"`, `kind "pc"/"pt"/"pcc"/"prc"`, side right; equation Text: `ref "EQ-n"`, `kind "equation"`, side right.
- `draw_alignment` Line/Arc: `{alignment, ref: "T-1" | "C-1", kind: "element", station: <raw start station>, offset: 0.0}`.
- `place_curve_table` Table: `{alignment, ref: "CURVES", kind: "curve_table", content_auto: true}`.

### 2.8 Anchor resolution types (`design/anchors.py`)
```python
@dataclass
class AnchorRef:                 # parsed, unresolved
    ref: str                     # canonical: "PC-1", "BEGIN", "18+00.00" (display text), ...
    kind_hint: str               # "begin"|"end"|"pi"|"pc"|"pt"|"mc"|"tangent"|"equation"|"station"
    index: Optional[int]         # for -n forms
    station_display: Optional[float]   # for station form
    offset: float = 0.0          # right +
    region: Optional[int] = None

@dataclass
class AnchorPoint:               # resolved
    alignment: str
    ref: str                     # canonical
    kind_hint: str
    station: float               # raw
    station_text: str            # display, 2 decimals
    region: int
    offset: float
    on_point: List[float]        # centerline point (offset 0)
    point: List[float]           # including offset
    direction_deg: float         # heading ahead at the station (PI: heading of the back tangent)
    element_index: int           # 0-based into alignment.elements (PI: the curve's index)
    curve_index: Optional[int]   # 1-based, for pi/pc/pt/mc
    tangent_index: Optional[int] # 1-based, for tangent (T-n) and station anchors that land on a tangent
    def to_record(self) -> dict  # {"alignment","ref","station","offset"}
```

### 2.9 Label types (`design/labels.py`)
```python
LABEL_KINDS = ("station", "pc", "pt", "pi", "mc", "pcc", "prc", "bearing", "begin", "end",
               "equation", "curve_data", "custom")
ROTATION_MODES = ("along", "perpendicular", "horizontal")
SIDES = ("left", "right")
DEFAULT_SIDE = {"station": "left", "bearing": "left", "begin": "left", "end": "left",
                "pc": "right", "pt": "right", "pi": "right", "mc": "right", "pcc": "right",
                "prc": "right", "equation": "right", "curve_data": "right", "custom": "left"}
DEFAULT_VALIGN = {"left": "bottom", "right": "top"}
MODEL_LABEL_OFFSET = 16.0; MODEL_TEXT_HEIGHT = 8.0; MODEL_TICK_HALF = 10.0
SHEET_LABEL_OFFSET = 0.32; SHEET_TEXT_HEIGHT = 0.10

@dataclass
class LabelSpec:
    kind: str; alignment: str; ref: str
    station: float; offset: float; region: int
    anchor_point: List[float]; direction_deg: float
    side: str; label_offset: float; rotation: str
    content: str; content_auto: bool
    position: List[float]        # model space, after side offset
    rotation_deg: float          # model space, uprighted
    halign: str; valign: str
    def anchor_record(self, viewport: Optional[str] = None) -> dict   # §2.7 shape

@dataclass
class TickSpec:
    station: float; station_text: str; region: int
    point: List[float]; direction_deg: float
    start: List[float]; end: List[float]
    def anchor_record(self, alignment: str) -> dict

@dataclass
class StationingPlan:
    items: List[object]          # interleaved [TickSpec, LabelSpec, TickSpec, LabelSpec, ...] in creation order,
                                 # then junction LabelSpecs, then equation LabelSpecs
    n_ticks: int; n_junctions: int; n_equations: int
    begin_text: str; end_text: str
```

## 3. Math API

### 3.1 `design/angles.py` (pure)
```python
def norm_deg(a: float) -> float                          # into [0, 360)
def signed_delta_deg(d_in: float, d_out: float) -> float  # into (-180, 180]; + = left turn (CCW)
def direction_to_azimuth(direction_deg) -> float          # (90 - d) % 360
def azimuth_to_direction(azimuth_deg) -> float            # (90 - az) % 360
def direction_of(p, q) -> float                           # degrees(atan2(qy-py, qx-px)), normalized [0,360)
def azimuth_of(p, q) -> float
def unit_vector(direction_deg) -> List[float]             # [cos, sin]
def left_normal(direction_deg) -> List[float]             # [-sin, cos]
def right_normal(direction_deg) -> List[float]            # [sin, -cos]
def dms_parts(deg: float, seconds_decimals: int = 0) -> Tuple[int, int, float]
    # rounds TOTAL seconds first so 59.9999" carries into minutes/degrees; deg >= 0 expected
def format_dms(deg, seconds_decimals=0, pad_degrees=False) -> str   # 45.5041667 -> 45°30'15"
def parse_dms(text) -> float             # accepts 45°30'15", 45d30'15", 45-30-15, 45 30 15, 45.5042
def format_bearing(azimuth_deg, seconds_decimals=0) -> str   # quadrant rule §0; degrees padded to 2
def parse_bearing(text) -> float         # -> azimuth; accepts "S 45°00'00\" E", "S45-00-00E", "N 45 30 15 W"
def format_azimuth(azimuth_deg, seconds_decimals=0) -> str  # DMS, no quadrant, padded to 3? NO: unpadded
```
Pinned values: `format_bearing(45.5041667) == 'N 45°30\'15" E'`; `format_bearing(90) == 'N 90°00\'00" E'`; `format_bearing(0) == 'N 00°00\'00" E'`; `format_bearing(135) == 'S 45°00\'00" E'`; `format_bearing(180) == 'S 00°00\'00" E'`; `format_bearing(270) == 'S 90°00\'00" W'`; `format_bearing(300) == 'N 60°00\'00" W'`; `format_bearing(5.5) == 'N 05°30\'00" E'`; `format_dms(5.5) == '5°30\'00"'`; `format_dms(59.99999) == '60°00\'00"'`; `direction_to_azimuth(30) == 60`; `(0) == 90`; `(-90) == 180`; `(180) == 270`; `signed_delta_deg(0, 30) == 30`; `(0, -30) == -30`; `(170, -170) == 20`; `parse_bearing('S 45°00\'00" W') == 225`.

### 3.2 `design/stations.py`
```python
class StationSystem:
    def __init__(self, begin_station: float, length: float, equations: List[StationEquation])
    @property end_station_raw -> float
    def regions(self) -> List[Region]
    def region_of_raw(self, raw: float) -> int
    def to_display(self, raw: float) -> Tuple[float, int]            # (display, region)
    def to_raw(self, display: float, region: Optional[int] = None) -> float
        # finds regions whose [display_start, display_end) contain display (last closed);
        # none -> DesignError("station 22+00.00 does not exist on this alignment (gap between 20+00.00 BK and 25+00.00 AH)")
        # >1 and region None -> DesignError("station 19+00.00 occurs in regions 1 and 2; pass region=", hint="regions: 1 = 10+00.00..20+00.00, 2 = 18+00.00..25+18.88")
    def format(self, raw: float, decimals: int = 2) -> str            # format_station(display)
    def parse(self, value, region: Optional[int] = None) -> float     # number -> display feet; "12+34.56" -> parse_station; returns RAW
    def in_range(self, raw: float) -> bool                            # begin-EPS <= raw <= end+EPS
    def require_in_range(self, raw: float, alignment_name: str) -> None
        # DesignError("station 26+00.00 is outside ALIGN-1 (10+00.00 to 25+18.88)")

def build_equations(begin_station, length, items: List[dict]) -> List[StationEquation]
    # items: {"back": display, "ahead": display} or {"raw_station", "back", "ahead"}; back/ahead may be "12+34.56" strings
    # raw derived from back through preceding equations; if raw_station given it must agree within STATION_EPS
def equation_label(eq: StationEquation, decimals=2) -> str   # "STA 20+00.00 BK = STA 25+00.00 AH"
```
Pinned (alignment A: begin 1000, length 1518.879, equation raw 2000/back 2000/ahead 2500): `to_display(1500) == (1500, 1)`; `to_display(2000) == (2500, 2)`; `to_display(2300) == (2800, 2)`; `format(2300) == "28+00.00"`; `to_raw(2800) == 2300`; `parse("28+00") == 2300`; `to_raw(2200)` raises (gap); end text `"30+18.88"`. Overlap equation (raw 2000/back 2000/ahead 1800): `to_raw(1900)` raises ambiguity naming regions 1 and 2; `to_raw(1900, region=2) == 2100`.

### 3.3 `design/horizontal.py`
```python
def compile_pis(pis: List[PI]) -> List[object]
def curve_from_pi(back_pt, pi_pt, ahead_pt, radius: float, start_dist: float) -> CurveElement
def element_from_dict(d: dict) -> object            # raises DesignError on unknown/spiral kind
def element_to_dict(el) -> dict
def elements_from_dicts(items: List[dict], tol: float = CONNECT_TOL) -> List[object]
    # accepts the stored shape OR the minimal import shape:
    #   {"kind":"tangent","start","end"} ; {"kind":"curve","pc","pt","center","direction"} (radius optional, derived)
    # recomputes length/direction/delta/start_dist; validates continuity (start == previous end within tol) ->
    #   DesignError("element 2 starts 0.050 ft from the end of element 1") ; heading continuity within 0.01 deg is a
    #   returned warning list? NO: returns elements only; heading kinks are allowed (LandXML reality) — no error
def pis_from_elements(elements) -> List[PI]         # [first start] + [curve.pi with radius] + [last end]; only valid when
                                                    # every curve is between tangents/ends (else returns [])
def validate_continuity(elements, tol=CONNECT_TOL) -> None
def alignment_from_elements(name, elements, begin_station=0.0, equations=(), description="") -> Alignment
    # sets source="elements", pis=[]; then attempts PI recovery: if pis_from_elements is non-empty and
    # compile_pis(recovered) reproduces every element endpoint within 1e-3 ft, sets pis=recovered, source="pis"
def curve_data(alignment: Alignment, n: int, decimals: int = 2, dms_decimals: int = 0) -> dict   # §5 row shape
def tangent_data(alignment: Alignment, n: int, decimals: int = 2, dms_decimals: int = 0) -> dict
def junction_kind(alignment, i: int) -> Optional[str]   # between element i and i+1: "pc"|"pt"|"pcc"|"prc"|None

class Alignment:
    @property length -> float
    @property end_station -> float                   # raw
    def stations(self) -> StationSystem
    def curves(self) -> List[CurveElement]           # travel order
    def tangents(self) -> List[TangentElement]
    def curve_index(self, element_index: int) -> int # 1-based
    def element_at(self, dist: float) -> Tuple[int, float]   # (index, local s); exact junction -> AHEAD element
    def point_at(self, dist: float) -> List[float]
    def direction_at(self, dist: float) -> float
    def station_to_xy(self, station_raw: float, offset: float = 0.0) -> Tuple[List[float], float, int]
        # (point_with_offset, direction_deg, element_index); raises DesignError when out of range
    def xy_to_station(self, point) -> dict
        # {"station": raw, "offset": right+, "on_point": [x,y], "direction_deg", "element_index"}
    def bbox(self) -> Tuple[float, float, float, float]   # tangents by endpoints, curves via geo.arc_bbox
    def to_dict / from_dict
```
**`compile_pis` algorithm** (n PIs):
1. `n >= 2`; consecutive PIs not coincident (`distance > 0.01`) else `"PI-2 and PI-3 are coincident"`; `pis[0].radius == 0 and pis[-1].radius == 0` else `"BEGIN/END PIs cannot carry a radius"`; every interior `radius > 0` else `DesignError("PI-2 is an angle point (radius 0); interior PIs must have a curve radius", hint="pass [x, y, R] for every interior PI")`.
2. For each interior PI k: `d_in = direction_of(P[k-1], P[k])`, `d_out = direction_of(P[k], P[k+1])`, `δ = signed_delta_deg(d_in, d_out)`; `|δ| < ANGLE_EPS` → `"PI-2 has no deflection (collinear); remove it"`; `|δ| >= 180 − ANGLE_EPS` → `"PI-2 deflects 180°"`. `direction = "L" if δ > 0 else "R"`, `Δ = |δ|`, `T = R·tan(Δ/2)`, `L = R·radians(Δ)`, `PC = PI − T·unit(d_in)`, `PT = PI + T·unit(d_out)`, `center = PC + R·(left_normal(d_in) if L else right_normal(d_in))`.
3. Fit check per segment between consecutive PIs (T = 0 at ends): first segment `T_1 <= D_0 + GEOM_EPS` else `"curve at PI-1 (T=616.28') is longer than the back tangent from BEGIN (600.00')"`; interior `T_k + T_{k+1} <= D_k + GEOM_EPS` else `"curves at PI-2 (T=321.54') and PI-3 (T=321.54') overlap by 43.08' on the 600.00' tangent between them; reduce a radius or move the PIs"`; last segment likewise (`"...longer than the ahead tangent to END"`).
4. Emit: tangent from previous PT (or BEGIN) to this PC only if its length > GEOM_EPS (back-to-back curves emit no zero-length tangent), then the curve; final tangent from last PT to END (if > GEOM_EPS). `start_dist` cumulative.

**Junction classification**: tangent→curve = `pc`, curve→tangent = `pt`, curve→curve same direction = `pcc`, opposite = `prc`.

**`station_to_xy`**: `dist = station_raw − begin_station`; `dist < −STATION_EPS or dist > length + STATION_EPS` → `require_in_range` error; clamp; `element_at` picks the AHEAD element at exact junctions. Tangent: `p = start + s·unit(direction)`. Curve: `φ0 = direction_of(center, pc)`, `sign = +1 (L) / −1 (R)`, `φ = φ0 + sign·degrees(s/R)`, `p = center + R·[cos φ, sin φ]`, `heading = direction_in_deg + sign·degrees(s/R)`. Offset: `p + offset·right_normal(heading)`.

**`xy_to_station`**: project onto every element. Tangent: `s = dot(P−start, u)`, valid iff `−GEOM_EPS <= s <= length + GEOM_EPS`, `offset = dot(P−start, right_normal(dir))`. Curve: `r = |P−center|`; skip if `r < GEOM_EPS`; `φ = direction_of(center, P)`; `sweep = norm_deg(sign·(φ − φ0))`; `s = R·radians(sweep)`; valid iff `s <= L + GEOM_EPS` (also accept sweep within ANGLE_EPS of 360 as s=0); `offset = (R − r)·(−1 if L else +1)`. Among valid projections choose minimum `|offset|`, ties → lower station. None → `DesignError("point (900.00, 1000.00) does not project onto ALIGN-1 (stations 10+00.00 to 25+18.88)", hint="points before BEGIN, after END, or at a curve center have no perpendicular station")`.

**`curve_data` row shape** (all stations raw + `_text` display):
```json
{"alignment":"ALIGN-1","index":1,"ref":"C-1","direction":"L","radius":800.0,"delta_deg":30.0,"delta_dms":"30°00'00\"",
 "tangent":214.359354,"length":418.87902,"external":28.220944,"mid_ordinate":27.259339,"chord":414.110472,
 "degree_of_curve_deg":7.1619725,"degree_of_curve_dms":"7°09'43\"",
 "direction_in_deg":0.0,"direction_out_deg":30.0,"azimuth_in_deg":90.0,"azimuth_out_deg":60.0,
 "bearing_in":"N 90°00'00\" E","bearing_out":"N 60°00'00\" E",
 "chord_direction_deg":15.0,"chord_azimuth_deg":75.0,"chord_bearing":"N 75°00'00\" E",
 "pc_station":1600.0,"pi_station":1814.359354,"pt_station":2018.87902,"mc_station":1809.43951,
 "pc_station_text":"16+00.00","pi_station_text":"18+14.36","pt_station_text":"20+18.88","mc_station_text":"18+09.44",
 "pc":[1600.0,1000.0],"pi":[1814.359354,1000.0],"pt":[2000.0,1107.179677],"center":[1600.0,1800.0]}
```
Formulas: `T = R·tan(Δ/2)`, `L = R·rad(Δ)`, `E = R·(sec(Δ/2) − 1)`, `M = R·(1 − cos(Δ/2))`, `C = 2R·sin(Δ/2)`, `D_c = 5729.578/R`, `chord_direction = direction_in + sign·Δ/2`, `pi_station = pc_station + T`, `mc_station = pc_station + L/2`. Numbers in JSON are unrounded floats (formatting happens in labels).

**`tangent_data` row shape**: `{"alignment","index","ref":"T-1","start":[..],"end":[..],"length":600.0,"direction_deg":0.0,"azimuth_deg":90.0,"bearing":"N 90°00'00\" E","start_station":1000.0,"end_station":1600.0,"mid_station":1300.0,"start_station_text","end_station_text","mid_station_text","mid_point":[1300.0,1000.0]}`.

### 3.4 `design/vertical.py`
```python
class Profile:
    def validate(self) -> None
    def curves(self) -> List[dict]           # one row per interior PVI (including grade breaks), §5 "vcs" shape
    def elevation_at(self, station_raw: float) -> float    # DesignError outside [first, last] PVI station
    def grade_at(self, station_raw: float) -> float        # ratio; at a grade break returns the AHEAD grade
    def station_range(self) -> Tuple[float, float]
    def to_dict / from_dict
def vc_data(profile: Profile, n: int) -> dict             # n = 1-based interior PVI index
```
Per interior PVI k: `g1 = (E_k − E_{k−1})/(S_k − S_{k−1})`, `g2 = (E_{k+1} − E_k)/(S_{k+1} − S_k)`, `A_pct = |g2 − g1|·100`, `K = L/A_pct` (None when A_pct == 0 or L == 0), `r = (g2 − g1)/L`, `PVC = (S_k − L/2, E_k − g1·L/2)`, `PVT = (S_k + L/2, E_k + g2·L/2)`, `type = "break" if L == 0 else ("crest" if g2 < g1 else "sag")`, `external = A_pct·L/800`, high/low point exists iff `g1·g2 < 0`: `x = g1·L/(g1 − g2)` from PVC, `station = PVC + x`, `elevation = E_PVC + g1·x + (r/2)·x²`; else `high_low = None`. Elevation on a VC: `E_PVC + g1·x + (r/2)·x²`; grade `g1 + r·x`; off-curve linear.

`vc_data` row: `{"profile","alignment","index":1,"ref":"VC-1","type":"crest","length":400.0,"pvi_station":2000.0,"pvi_elevation":120.0,"pvc_station":1800.0,"pvc_elevation":116.0,"pvt_station":2200.0,"pvt_elevation":114.0,"g1_pct":2.0,"g2_pct":-3.0,"A_pct":5.0,"K":80.0,"external":2.5,"high_low":{"kind":"high","x_from_pvc":160.0,"station":1960.0,"elevation":117.6} | null, "pvi_station_text","pvc_station_text","pvt_station_text","high_low_station_text"}` (station_text fields require the parent alignment's equations → filled by the query layer; the pure function fills them with plain `format_station`).

### 3.5 `design/anchors.py`
Grammar (case-insensitive, whitespace-tolerant, single shlex token when written without spaces):
```
anchor  := ref [ "@" offset ]
ref     := "BEGIN" | "END" | ("PI"|"PC"|"PT"|"MC"|"T"|"EQ") "-" n | station
station := int "+" number            ; display station "18+00" / "18+00.00"
        |  number                     ; display station in feet, e.g. "1800"
offset  := signed number [ "L" | "R" ]  ; feet, right positive; "25L" == "-25", "25R" == "25"
```
Dict form: `{"ref": "PC-1", "offset": 10}` or `{"station": 1800 | "18+00", "offset": 25.0, "region": 2}`. A bare JSON number is a display station.
```python
def parse_anchor(value) -> AnchorRef      # str | int | float | dict; DesignError("cannot parse anchor 'PC3'", hint=<grammar one-liner>)
def infer_kind(ref: AnchorRef) -> str     # begin/end/pi/pc/pt/mc/bearing(T-n)/equation/station
def resolve_anchor(alignment: Alignment, ref: AnchorRef) -> AnchorPoint
def list_anchors(alignment: Alignment) -> List[AnchorPoint]   # BEGIN, END, PC/PI/PT/MC-n per curve, T-n, EQ-n (offset 0)
```
Resolution: `PC-n`/`PT-n`/`MC-n` → curve n's pc/pt/mid point on the centerline; `PI-n` → `station = pc_station + T`, `on_point = curve.pi`, `direction_deg = direction_in_deg`, offset applied along `right_normal(direction_in)`; `T-n` → tangent n midpoint; `EQ-n` → point at `raw_station`; `BEGIN`/`END`; station → `to_raw` then `station_to_xy`. Errors: `"anchor 'PC-3' does not exist: ALIGN-1 has 2 curves (PC-1, PC-2)"` with hint `"valid: BEGIN, END, PI-1..PI-2, PC-1..PC-2, PT-1..PT-2, MC-1..MC-2, T-1..T-3, EQ-1..EQ-1, or a station within 10+00.00..25+18.88"`; station out of range → §3.2 message.
Canonical `ref` strings: named refs upper-case; station refs formatted display `"18+00.00"`.
Pinned on alignment A: `PC-1` → (1600,1000) dir 0; `MC-1` → (1807.055, 1027.259), station 1809.440; `PI-1` → point (1814.359, 1000), station 1814.359; `T-1` → (1300,1000); `T-2` → (2216.506, 1232.180), station 2268.879; `"18+00@25"` → (1804.108, 1000.647); `"18+00@25L"` → offset −25; `"1800"` → station 1800.

### 3.6 `design/labels.py`
```python
def upright(angle_deg: float) -> float      # identical to handlers._upright: a%=360; if 90<a<=270: a-=180; ((a+180)%360)-180
def offset_point(p, angle_deg, dist) -> List[float]
def label_content(alignment: Alignment, ap: AnchorPoint, kind: str) -> str
def compile_label(alignment, ap: AnchorPoint, kind: str, side: Optional[str] = None,
                  label_offset: Optional[float] = None, rotation: str = "along",
                  content: Optional[str] = None, halign: Optional[str] = None,
                  valign: Optional[str] = None) -> LabelSpec
def sheet_pose(spec: LabelSpec, transform, viewport_rotation_deg: float, label_offset_in: float) -> Tuple[List[float], float]
    # position = transform.to_paper(spec.anchor_point) offset by label_offset_in along
    #   (spec.direction_deg + viewport_rotation_deg + (90 if side == "left" else -90));
    # rotation: along -> upright(direction + twist); perpendicular -> upright(direction + twist + 90); horizontal -> 0
def stationing_plan(alignment, interval=100.0, tick_half=10.0, label_offset=16.0,
                    include_pc_pt=True, include_equations=True,
                    station_range: Optional[Tuple[float, float]] = None) -> StationingPlan   # station_range in RAW
CURVE_COLUMNS: "OrderedDict[str, Tuple[str, float]]"  # key -> (header, default width in)
DEFAULT_CURVE_COLUMNS = ["curve", "pi_sta", "delta", "direction", "radius", "tangent", "length", "chord", "chord_bearing"]
def curve_table_rows(alignment, columns=None, curves=None, decimals=2, dms_decimals=0) -> Tuple[List[str], List[List[str]], List[float]]
    # (headers, rows, widths_in)
```
Kind/anchor agreement (`compile_label` raises `DesignError`): `pc` needs `PC-n`; `pt` needs `PT-n`; `pi` needs `PI-n`; `mc`/`curve_data` need `MC-n` (curve_data also accepts `PI-n`); `bearing` needs an anchor on a tangent (`T-n`, or a station anchor whose element is a tangent) — `"bearing labels go on tangents; MC-1 is on curve C-1 (use T-1 or T-2)"`; `equation` needs `EQ-n`; `begin`/`end` need `BEGIN`/`END`; `pcc`/`prc` need `PC-n` where `junction_kind` matches; `station`/`custom` accept any; `custom` requires `content` → `"kind custom requires content"`.

Content table:

| kind | content |
|---|---|
| station | `18+00.00` |
| pc / pt / pi / pcc / prc | `PC 16+00.00` / `PT 20+18.88` / `PI 18+14.36` / `PCC …` / `PRC …` |
| mc | `C-1` |
| bearing | `N 60°00'00" E` (bearing of the tangent) |
| begin / end | `BEGIN STA 10+00.00` / `END STA 25+18.88` |
| equation | `STA 20+00.00 BK = STA 25+00.00 AH` |
| curve_data | `C-1\nΔ = 30°00'00"\nR = 800.00'\nT = 214.36'\nL = 418.88'` |
| custom | caller's `content` |

Model placement: `side` defaults from `DEFAULT_SIDE[kind]`; `label_offset` default `MODEL_LABEL_OFFSET`; `position = offset_point(anchor_point, direction + (90 if left else −90), label_offset)`; `rotation_deg`: along → `upright(direction)`, perpendicular → `upright(direction + 90)`, horizontal → 0; `halign` default `"center"`; `valign` default `DEFAULT_VALIGN[side]`. (The `upright` fold on west-heading text is kept identical to the engine — known gotcha, flagged for PE review.)

`stationing_plan`: for each region in order: `station_disp = ceil((region.display_start − 1e-9)/interval)·interval`; `while station_disp < region.display_end` (`<= end + 1e-6` for the last region): `raw = station_disp − shift`; `(pt, dir) = point_at/direction_at`; TickSpec `start = offset_point(pt, dir+90, −tick_half)`, `end = offset_point(pt, dir+90, +tick_half)`; LabelSpec kind `station`, side left, `valign bottom`, content `format_station(station_disp)`, rotation along. With `station_range=(a_raw, b_raw)` only raw stations in `[a, b]` are emitted. Junctions (`include_pc_pt`): per element boundary with `junction_kind` non-None: LabelSpec at the boundary distance, ref `PC-n`/`PT-n` (for pcc/prc: `PC-n` of the ahead curve), side right, `valign top`, content per table. Equations (`include_equations`): LabelSpec kind `equation`, ref `EQ-n`, side right, valign top, `label_offset` = 1.5 × label_offset (stacked below a possible junction label). `begin_text`/`end_text` = display of begin and end.

Curve table column catalog (key → header → cell format): `curve→CURVE→C-1`; `pi_sta→PI STA→18+14.36`; `pc_sta→PC STA`; `pt_sta→PT STA`; `delta→DELTA→30°00'00"`; `direction→DIR→LT|RT`; `radius→R→800.00'`; `tangent→T→214.36'`; `length→L→418.88'`; `external→E→28.22'`; `mid_ordinate→M→27.26'`; `chord→C→414.11'`; `chord_bearing→CH BRG→N 75°00'00" E`. Default widths (in): curve 0.8, pi_sta 1.1, pc_sta 1.1, pt_sta 1.1, delta 1.3, direction 0.6, radius 1.0, tangent 1.0, length 1.0, external 0.9, mid_ordinate 0.9, chord 1.0, chord_bearing 1.6. Unknown column key → `DesignError` listing the catalog.

Pinned default row for A: `["C-1", "18+14.36", "30°00'00\"", "LT", "800.00'", "214.36'", "418.88'", "414.11'", "N 75°00'00\" E"]`.

## 4. Commands

All handlers live in `commands/design_handlers.py` with signature `name(doc, p) -> (message, diff, warnings)`. Shared helpers imported from `handlers`: `CommandFault, _diff, _space, _layer, _style, _entity_common, _add, _find, _annotation_warnings, _space_label, _upright, _offset_pt`. `_alignment(doc, p)` helper: `p.get("alignment")` or the only alignment if exactly one exists, else `CommandFault("alignment is required: the document has 2 alignments (ALIGN-1, RAMP-A)", hint="run list_alignments")`; unknown name → `CommandFault("no alignment named 'SR-100'", hint="alignments: ['ALIGN-1']")`. Schemas + examples live in `commands/design_schemas.py` as `DESIGN_SCHEMAS` / `DESIGN_EXAMPLES`; `schemas.py` ends with `SCHEMAS.update(DESIGN_SCHEMAS); EXAMPLES.update(DESIGN_EXAMPLES)`. Schema fragments (defined in `design_schemas.py`): `STATION = {"type": ["number","string"], "description": "display station: feet (1600) or '16+00.00'"}`; `PI_ITEM = {"type":"array","items":NUM,"minItems":2,"maxItems":3,"description":"[x, y] or [x, y, radius]"}`; `PVI_ITEM = {"type":"array","items":NUM,"minItems":2,"maxItems":3,"description":"[station, elevation] or [station, elevation, vc_length]"}`; `EQUATION = obj({"back": STATION, "ahead": STATION, "raw_station": NUM}, ["back","ahead"])`; `ELEMENT = obj({"kind":{"enum":["tangent","curve"]},"start":POINT,"end":POINT,"pc":POINT,"pt":POINT,"center":POINT,"radius":POS,"direction":{"enum":["L","R"]}}, ["kind"])`; `ANCHOR = {"type":["string","number","object"], "description": "BEGIN | END | PI-n | PC-n | PT-n | MC-n | T-n | EQ-n | '18+00.00' | 1800, optionally '@offset' (ft, right +, e.g. 'PC-1@16', '18+00@25L'); or {ref|station, offset, region}"}`; `KIND = {"enum": list(LABEL_KINDS)}`; `ROTATION = {"enum": ["along","perpendicular","horizontal"]}`; `SIDE = {"enum": ["left","right"]}`.

REGISTRY insertion: after `annotate_stationing`, before `attach_reference`, in this order. `bus.py` adds `from roaddraft.commands import design_handlers as dh`.

### 4.1 `create_alignment` — c3d `["CREATEALIGNMENTLAYOUT"]`, ord `["complex by pi"]`
Schema: `obj({"name": NSTR, "pis": {"type":"array","items":PI_ITEM,"minItems":2}, "elements": {"type":"array","items":ELEMENT,"minItems":1}, "begin_station": STATION, "equations": {"type":"array","items":EQUATION}, "description": STR}, ["name"])`.
Example: `{"name": "ALIGN-1", "begin_station": "10+00", "pis": [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]}`.
Handler: name unused else fault (`hint="modify_alignment or delete_alignment"`); exactly one of `pis`/`elements` else `CommandFault("give exactly one of pis (PI-based) or elements (from CoordGeom)")`; `begin_station` parsed with `parse_station` (default 0); `pis` → `compile_pis`; `elements` → `elements_from_dicts` + `alignment_from_elements`; equations via `build_equations`; store `doc.design.alignments[name]`. Message: `"alignment ALIGN-1 created: 3 elements (2 tangents, 1 curve), 1518.88 ft, 10+00.00 to 25+18.88"`. Diff `created=["alignment:ALIGN-1"]`. Warnings: none.

### 4.2 `modify_alignment` — c3d `["EDITALIGNMENT"]`, ord `["alignment edit"]`
Schema: `obj({"name": NSTR, "changes": {"type":"object","minProperties":1,"description":"any of: pis, begin_station, equations, description, rename"}}, ["name","changes"])`. Example: `{"name": "ALIGN-1", "changes": {"begin_station": "20+00"}}`.
Handler: unknown change keys fault listing the five; `pis` → recompile (source becomes `"pis"`); `begin_station`/`equations` re-validated against the (new) length; `rename` re-keys, updates `Profile.alignment` of bound profiles and `anchor.alignment` on every entity in every space. Warning when entities anchored to the alignment exist and geometry/stations changed: `"18 entities are anchored to ALIGN-1 and were not regenerated; re-run draw_alignment / annotate_stationing / place_label"`. Diff `modified=["alignment:NAME"]` (+ `"alignment:OLD"` deleted and `"alignment:NEW"` created on rename; modified entity ids listed).

### 4.3 `delete_alignment` — c3d `["DELETEALIGNMENT"]`, ord `["alignment delete"]`
Schema: `obj({"name": NSTR, "cascade": {"type":"boolean","description":"also delete profiles bound to it (default false)"}}, ["name"])`. Example `{"name": "ALIGN-1"}`.
Handler: bound profiles and no cascade → `CommandFault("ALIGN-1 has 1 profile (PROF-1)", hint="pass cascade=true or delete_profile first")`. Entities keep their anchors; warning `"12 entities remain anchored to deleted alignment ALIGN-1"`. Diff `deleted=["alignment:ALIGN-1", "profile:PROF-1"...]`.

### 4.4 `create_profile` — c3d `["CREATEPROFILELAYOUT"]`, ord `["profile complex by vpi"]`
Schema: `obj({"name": NSTR, "alignment": NSTR, "pvis": {"type":"array","items":PVI_ITEM,"minItems":2}, "description": STR}, ["name","alignment","pvis"])`. Example: `{"name": "PROF-1", "alignment": "ALIGN-1", "pvis": [[1000, 100], [2000, 120, 400], [3000, 90]]}`.
Handler: alignment must exist; profile name unused; PVI stations are display → raw via the alignment's `StationSystem.parse`; `Profile.validate()`; warning (not fault) when any PVI lies outside the alignment's station range: `"PVI-3 (30+00.00) is beyond the end of ALIGN-1 (25+18.88)"`. Message `"profile PROF-1 created on ALIGN-1: 3 PVIs, 1 vertical curve, 10+00.00 to 30+00.00"`. Diff `created=["profile:PROF-1"]`.

### 4.5 `delete_profile` — c3d `["DELETEPROFILE"]`, ord `["profile delete"]`
Schema `obj({"name": NSTR}, ["name"])`. Example `{"name": "PROF-1"}`. Diff `deleted=["profile:PROF-1"]`.

### 4.6 `draw_alignment` — c3d `["ALIGNMENTTOPOLYLINE"]`, ord `["alignment export geometry"]`
Schema: `obj({"alignment": NSTR, "layer": NSTR, "color": COLOR, "linetype": LINETYPE, "replace": {"type":"boolean","description":"delete this alignment's previously drawn elements first (default false)"}})`. Example `{"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"}`.
Handler: model space only. Existing entities with `anchor.alignment == name and anchor.kind == "element"`: if `replace` delete them (diff deleted), else warning `"ALIGN-1 already drawn (LN-001, AR-001, LN-002); pass replace=true to redraw"` and still draw. Per element in travel order: tangent → `Line(start, end)`; curve → `Arc(center, radius, start_angle_deg, end_angle_deg)` with `L: start = direction_of(center, pc), end = direction_of(center, pt)`; `R: start = direction_of(center, pt), end = direction_of(center, pc)` (Arc entities are always CCW). Each entity gets the element anchor (§2.7); `_entity_common` fields. Message `"ALIGN-1 drawn on V-ALIGN-CNTR: 2 lines, 1 arc"`. Diff `created` in travel order (so the ids feed the legacy `path_ids` mode unchanged). Pinned: for A the arc is `center [1600,1800], start −90 (=270), end −60 (=300)` — matches `centerline_session`; the R-mirror of A yields `start 60, end 90`.

### 4.7 `place_label` — c3d `["ADDALIGNMENTSTAOFFLABEL"]`, ord `["place label"]`
Schema:
```python
obj({"space": SPACE, "alignment": NSTR, "anchor": ANCHOR, "kind": KIND,
     "content": {**STR, "description": "explicit text; omit to auto-generate from design data (recorded either way)"},
     "side": SIDE, "label_offset": {"type":"number","minimum":0,"description":"distance from the anchor point, feet in model / inches on sheets; default 16 ft / 0.32 in"},
     "rotation": ROTATION, "height": {**POS, "description":"text height, feet in model / inches on sheets; default 8 ft / 0.10 in"},
     "style": NSTR, "halign": HALIGN, "valign": VALIGN, "layer": NSTR, "color": COLOR, "linetype": LINETYPE,
     "viewport": {**NSTR, "description":"sheet space only: viewport id/name carrying the anchor; default = the first viewport whose frame contains the point"}},
    ["space", "anchor"])
```
Example: `{"space": "model", "alignment": "ALIGN-1", "anchor": "PC-1"}`.
Handler steps: (1) `_space`; (2) `_alignment`; (3) `parse_anchor` → `resolve_anchor` (DesignError → CommandFault); (4) `kind = p.get("kind") or infer_kind(ref)`; (5) `compile_label(...)` with `side/label_offset(model default)/rotation/content/halign/valign`; (6) if sheet: pick viewport — explicit `viewport` (id or fault `"viewport VP-009 is not on C-101"`) else the first `vp` with `geo.bbox_contains(vp.paper_bbox(), (q0,q1,q0,q1))` where `q = vp.transform().to_paper(anchor_point)`; none → `CommandFault("anchor PC-1 of ALIGN-1 (1600.00, 1000.00) is not visible in any viewport of C-101", hint="viewports: VP-001 shows x 1100..2650, y 730..1655; move/resize it (modify_viewport) or pass viewport=")`; `(position, rotation_deg) = sheet_pose(spec, vp.transform(), vp.rotation_deg, p.get("label_offset", 0.32))`; height default 0.10; (7) `_add(doc, space, "text", Text, {...common, position, content, height, style(validated; default current_text_style), rotation_deg, halign, valign, anchor: spec.anchor_record(vp.id or None)})` — on sheets the recorded `label_offset` is the inch value; (8) warnings: `_annotation_warnings` (sheets) + `"label duplicates TX-004 (same alignment/anchor/kind)"` when another Text in the same container has an equal `(alignment, ref, kind)` anchor triple. Message: `"label TX-007 'PC 16+00.00' (pc @ PC-1 of ALIGN-1) placed in model space"` / `"... placed on sheet C-101 via VP-001"`. Diff `created=[id]`.
Pinned (A, defaults): `PC-1` → content `PC 16+00.00`, position `(1600, 984)`, rotation 0, halign center, valign top, anchor `{alignment:"ALIGN-1", ref:"PC-1", kind:"pc", station:1600.0, offset:0.0, side:"right", label_offset:16.0, rotation:"along", viewport:null, content_auto:true}`. `"13+00"` → `13+00.00` at `(1300, 1016)`, valign bottom. `T-2` bearing → `N 60°00'00" E` at `(2208.506, 1246.036)`, rotation 30. `"18+00"` with `rotation=perpendicular` → rotation `upright(104.324) = −75.676`. `kind=pc anchor=PT-1` → fault. `kind=custom` without content → fault. Explicit `content="PC 16+00"` stored verbatim, `content_auto: false`.
Sheet pinned: viewport `center_paper [17, 11.7], model_center [1700, 1150], 31×18.5, fpi 50`: `PC-1` → position `(15.0, 8.38)`, height 0.10, `anchor.viewport == "VP-001"`, `anchor.label_offset == 0.32`; the same viewport with `rotation_deg 20` → rotation 20 and position `= to_paper([1600,1000]) + 0.32·[cos(−70°), sin(−70°)]`.

### 4.8 `place_curve_table` — c3d `["ADDALIGNMENTCURVETABLE"]`, ord `["place curve table"]`
Schema: `obj({"space": SPACE, "alignment": NSTR, "position": {**POINT,"description":"top-left corner, paper inches"}, "curves": {"type":"array","items":{"type":"integer","minimum":1}}, "columns": {"type":"array","items":NSTR,"minItems":1,"description":"keys: curve, pi_sta, pc_sta, pt_sta, delta, direction, radius, tangent, length, external, mid_ordinate, chord, chord_bearing"}, "title": STR, "text_height": POS, "layer": NSTR, "style": NSTR, "color": COLOR}, ["space", "position"])`. Example `{"space": "C-101", "alignment": "ALIGN-1", "position": [24.0, 8.5]}`.
Handler: `space` must be a sheet else `CommandFault("place_curve_table places tables on sheets", hint="pass a sheet id/name as space")`; `curve_table_rows(alignment, columns, curves)`; `_add(..., "table", Table, {position, columns: [{"header", "width"}], rows, text_height (default 0.12), title (default "CURVE DATA"), style, anchor: {"alignment", "ref": "CURVES", "kind": "curve_table", "content_auto": true}})`; warnings `_annotation_warnings`. Message `"curve table TB-001 (1 curve, 9 columns) placed on sheet C-101"`.

### 4.9 `import_landxml` — c3d `["LANDXMLIN"]`, ord `["import landxml"]`
Schema: `obj({"path": NSTR, "xml": {**NSTR,"description":"LandXML text inline (keeps the journal self-contained)"}, "alignments": {"type":"array","items":NSTR}, "on_conflict": {"enum":["error","replace","rename"]}})`. Example `{"path": "survey/alignments.xml"}`.
Handler: exactly one of `path`/`xml` (fault otherwise); `path` read at execute time (fault `"file not found: ..."`; journal then depends on the file, exactly like `attach_reference` — say so in the description); `parse_landxml` (adapter `LandXMLError` → CommandFault with line/col); filter by `alignments` (unknown names fault listing the file's names); conflicts per `on_conflict` (default `error`: `"alignment ALIGN-1 already exists"`, hint `on_conflict=replace|rename`; `rename` appends `-2`, `-3`); insert alignments then profiles. Message `"imported 2 alignments (ALIGN-1, RAMP-A) and 1 profile from LandXML 1.2 (USSurveyFoot); skipped: Surfaces"`. Diff `created` (`alignment:*`, `profile:*`; `modified` on replace). Warnings: adapter warnings verbatim.

### 4.10 `annotate_stationing` (modified; aliases unchanged)
Schema changes (in `schemas.py`, WP6): `required` → `["space"]`; new properties `"alignment": {**NSTR, "description": "design-model alignment name: true stations, equations, and anchored output (alternative to path_ids)"}`, `"station_range": {"type":"array","items":STATION,"minItems":2,"maxItems":2,"description":"alignment mode: only annotate between these display stations"}`, `"include_equations": {"type":"boolean","description":"alignment mode: label station equations (default true)"}`; description of `begin_station` gains "(entity-chain mode only)". EXAMPLE unchanged.
Handler (`handlers.py`): first lines become
```python
if "alignment" in p and "path_ids" in p: raise CommandFault("give either path_ids (entity-chain mode) or alignment (design mode), not both")
if "alignment" in p:
    from roaddraft.commands import design_handlers
    return design_handlers.annotate_stationing_alignment(doc, p)
if "path_ids" not in p: raise CommandFault("path_ids is required in entity-chain mode", hint="or pass alignment=NAME for design-model stationing")
if "begin_station" not in p: raise CommandFault("begin_station is required with path_ids")
```
— the rest of the function is byte-identical. `annotate_stationing_alignment` (in `design_handlers.py`): `begin_station` present → `CommandFault("alignment mode uses ALIGN-1's own stationing (begins 10+00.00); omit begin_station", hint="modify_alignment changes begin_station")`; `space` must be `"model"` (`"alignment-mode stationing draws in model space; use place_label for sheet labels"`); layers/style exactly as the entity mode; `station_range` parsed to raw; `plan = stationing_plan(...)`; materialise `plan.items` in order with the local `add()` closure pattern (Line for TickSpec on tick layer with tick anchor; Text for LabelSpec on label layer with anchor record); message `"stationing annotated in model space from ALIGN-1: 16 ticks @ 100 ft, 2 PC/PT labels, 1 equation labels, stations 10+00.00 to 30+18.88"`; warnings `[]`.

### 4.11 `modify_entity` (one-literal change, WP6)
`known = set(entity.to_dict()) | {"color", "linetype", "anchor"}`. Setting `"anchor": null` clears it; a malformed anchor faults via `as_anchor`.

## 5. Queries (`api/session.py`, WP7)

All added to `QUERIES` with description/schema/example and `_q_<name>` methods. Station inputs are display; `DesignError` → `_QueryFault(str(e), hint=e.hint)`. `_alignment_q(p)` mirrors the handler helper.

| Query | Params (schema) | Result (`ok`/`name` added by `query()`) |
|---|---|---|
| `list_alignments` | `obj({})` | `{"count": 1, "alignments": [{"name","description","source","begin_station","begin_station_text","end_station","end_station_text","length","curves","tangents","equations","profiles": [names], "drawn": bool}]}` |
| `station_to_xy` | `obj({"alignment": NSTR, "station": STATION, "offset": NUM, "region": {"type":"integer","minimum":1}}, ["station"])` ex `{"alignment":"ALIGN-1","station":"16+00","offset":12}` | `{"alignment","point":[x,y],"on_point":[x,y],"station":1600.0,"station_text":"16+00.00","region":1,"offset":12.0,"direction_deg":0.0,"azimuth_deg":90.0,"bearing":"N 90°00'00\" E","element_index":1,"element_kind":"curve","element_ref":"C-1"}` (exact junction → ahead element) |
| `xy_to_station` | `obj({"alignment": NSTR, "point": POINT}, ["point"])` ex `{"alignment":"ALIGN-1","point":[1300,1012]}` | `{"alignment","station":1300.0,"station_text":"13+00.00","region":1,"offset":-12.0,"distance":12.0,"side":"L"\|"R"\|"ON","on_point":[1300,1000],"direction_deg":0.0,"element_index":0,"element_kind":"tangent","element_ref":"T-1"}` |
| `resolve_anchor` | `obj({"alignment": NSTR, "anchor": ANCHOR, "kind": KIND, "space": SPACE, "viewport": NSTR, "side": SIDE, "label_offset": NUM, "rotation": ROTATION}, ["anchor"])` ex `{"alignment":"ALIGN-1","anchor":"PC-1"}` | dry run of `place_label`: `{"anchor": <anchor record>, "kind", "auto_content", "space", "viewport", "position", "rotation_deg", "halign", "valign"}`; same faults as the command |
| `get_design_data` | `obj({"kind": {"enum":["alignments","curves","tangents","equations","anchors","profiles","pvis","vcs"]}, "alignment": NSTR, "profile": NSTR, "start": {"type":"integer","minimum":0}, "limit": {"type":"integer","minimum":1,"maximum":500}}, ["kind"])` ex `{"kind":"curves","alignment":"ALIGN-1"}` | `{"kind","total","start","limit","rows":[...]}`; default limit 50. Rows: `alignments` = `Alignment.to_dict()` without `elements` + `length,end_station,begin_station_text,end_station_text,curves,tangents`; `curves` = `curve_data` rows (station texts via equations); `tangents` = `tangent_data` rows; `equations` = `{"alignment","index","ref":"EQ-1","raw_station","back","back_text","ahead","ahead_text","label"}`; `anchors` = `list_anchors` records `{"alignment","ref","kind_hint","station","station_text","point","direction_deg"}`; `profiles` = `Profile.to_dict()` + `{"pvis": n, "curves": n, "station_range_text"}`; `pvis` = `{"profile","alignment","index","ref":"PVI-1","station","station_text","elevation","length","grade_in_pct","grade_out_pct"}`; `vcs` = `vc_data` rows with `_text` filled through the alignment's equations. Filters: `alignment` (all kinds), `profile` (profiles/pvis/vcs). |
| `export_landxml` | `obj({"path": STR, "alignments": {"type":"array","items":NSTR}, "include_xml": BOOL, "include_base64": BOOL})` ex `{}` | `_file_result` (default name `f"{_slug(project_name)}.xml"` under `out_dir`) + `"xml": str` when `include_xml`; fault when no alignments |
| `get_document_state` (summary) | unchanged | summary gains `"alignments": [names]`, `"profiles": [names]` |

## 6. LandXML 1.2 (`adapters/landxml.py`, WP5) — stdlib `xml.etree.ElementTree` only

```python
LANDXML_NS = "http://www.landxml.org/schema/LandXML-1.2"
class LandXMLError(Exception): (message, hint=None)
@dataclass
class LandXMLData:
    alignments: List[Alignment]; profiles: List[Profile]
    linear_unit: str; to_us_ft: float; warnings: List[str]; skipped: List[str]
def parse_landxml(text: str) -> LandXMLData
def write_landxml(alignments: List[Alignment], profiles: List[Profile], project_name: str = "",
                  application_version: str = "0.2") -> str
```
Written skeleton (attribute order as listed; numbers `f"{v:.6f}"`; points **`"{y:.6f} {x:.6f}"` = northing easting**):
```xml
<?xml version="1.0" encoding="UTF-8"?>
<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2" date="2026-01-01" time="00:00:00" language="English" readOnly="false">
  <Units><Imperial linearUnit="USSurveyFoot" areaUnit="squareFoot" volumeUnit="cubicYard" temperatureUnit="fahrenheit" pressureUnit="inchHG" angularUnit="decimal degrees" directionUnit="decimal degrees"/></Units>
  <Application name="RoadDraft" version="0.2"/>
  <Project name="..."/>
  <Alignments>
    <Alignment name="ALIGN-1" desc="" staStart="1000.000000" length="1518.879020">
      <CoordGeom>
        <Line dir="90.000000" length="600.000000"><Start>1000.000000 1000.000000</Start><End>1000.000000 1600.000000</End></Line>
        <Curve rot="ccw" radius="800.000000" length="418.879020" chord="414.110472" delta="30.000000" dirStart="90.000000" dirEnd="60.000000" tangent="214.359354" external="28.220944" midOrd="27.259339">
          <Start>1000.000000 1600.000000</Start><Center>1800.000000 1600.000000</Center><End>1107.179677 2000.000000</End><PI>1000.000000 1814.359354</PI></Curve>
        <Line dir="60.000000" length="500.000000"><Start>1107.179677 2000.000000</Start><End>1357.179677 2433.012702</End></Line>
      </CoordGeom>
      <StaEquation staAhead="2500.000000" staBack="2000.000000" staInternal="2000.000000"/>
      <Profile name="ALIGN-1"><ProfAlign name="PROF-1" desc="">
        <PVI>1000.000000 100.000000</PVI>
        <ParaCurve length="400.000000">2000.000000 120.000000</ParaCurve>
        <PVI>3000.000000 90.000000</PVI>
      </ProfAlign></Profile>
    </Alignment>
  </Alignments>
</LandXML>
```
`date`/`time` are fixed literals ("2026-01-01", "00:00:00") so output is byte-stable.

Mapping table:

| LandXML | RoadDraft | Notes |
|---|---|---|
| `Units/Imperial@linearUnit="USSurveyFoot"` | factor 1.0 | write always this |
| `Imperial@linearUnit="foot"` | factor `0.3048 / (1200/3937) = 0.999998` | applied to every coordinate/length/radius/station/elevation on read |
| `Metric@linearUnit="meter"` | factor `3937/1200 = 3.280833333` | anything else → `LandXMLError("unsupported linearUnit 'X'; supported: USSurveyFoot, foot, meter")` |
| `Alignment@name` / `@desc` | `Alignment.name` / `description` | |
| `Alignment@staStart` | `begin_station` | display == raw at BEGIN |
| `Alignment@length` | checked vs summed elements | mismatch > 0.01 ft → warning `"Alignment ALIGN-1 length 1518.90 in file vs 1518.88 computed"` |
| `CoordGeom/Line` (`Start`, `End`) | `TangentElement` | `dir`/`length` attributes written, ignored on read |
| `CoordGeom/Curve` (`Start`, `End`, `Center`, `PI`) | `CurveElement` | `rot="ccw"` ⇔ `direction "L"`, `rot="cw"` ⇔ `"R"`. `Center` missing → computed from `Start`/`End`/`radius`/`rot` (chord midpoint + `sqrt(R²−c²)` along the left normal of the chord for ccw, right for cw). `PI` missing → `PC + T·unit(direction_in)`. `radius` missing and `Center` present → `|Start − Center|`. `dirStart`/`dirEnd`/`delta`/`chord`/`tangent`/`external`/`midOrd` written for interoperability, ignored on read |
| `CoordGeom/Spiral`, `IrregularLine`, `Chain` | — | `LandXMLError("alignment 'X' contains a Spiral element; spirals are not supported in this version", hint="replace the spiral upstream or import a different alignment")` |
| `StaEquation@staInternal/@staBack/@staAhead` | `StationEquation(raw_station, back, ahead)` | `staInternal` missing → derived from `staBack` through preceding equations |
| `Profile/ProfAlign@name` | `Profile.name` | fallback `Profile@name`, then `"<alignment>-PROF"`; duplicate names get `-2`, `-3` |
| `ProfAlign/PVI` text `"station elevation"` | `PVI(length=0)` | PVI text is station then elevation (not northing/easting); stations read as RAW |
| `ProfAlign/ParaCurve@length` text `"station elevation"` | `PVI(length=L)` | |
| `ProfAlign/UnsymParaCurve`, `CircCurve` | — | `LandXMLError("unsymmetrical/circular vertical curves are not supported in this version")` |
| top-level `<Profiles>` | accepted on read | export nests under `Alignment` |
| `Surfaces`, `Parcels`, `PipeNetworks`, `CgPoints`, other children | ignored | tag names collected once into `skipped` |

Edge cases: namespaced and namespace-less files both parse (strip `{…}` prefixes); continuity gap > `CONNECT_TOL` → `LandXMLError("alignment 'X': element 2 starts 0.050 ft from the end of element 1")`; an alignment with an empty `CoordGeom` → error; `staStart` missing → 0.0; XML syntax errors → `LandXMLError("LandXML parse error at line 12 column 5: ...")`. Import goes through `alignment_from_elements` (PI recovery). Round-trip contract: `parse_landxml(write_landxml(A))` reproduces every element endpoint/center within 1e-5 ft, `delta_deg` within 1e-6, equations exactly, PVIs within 1e-6; `write(parse(write(x))) == write(x)` byte-identical.

## 7. Task generator (`tasks/`, WP2 + WP9)

### 7.1 `tasks/standards.py` (WP2) — DRAFT, for PE review
```python
# AASHTO "A Policy on Geometric Design of Highways and Streets", 7th ed. (2018), Table 3-7,
# minimum radius (ft) for e_max = 6 %. DRAFT: transcribed from memory; a PE must verify before release.
MIN_RADIUS_FT_EMAX6 = {15: 39, 20: 81, 25: 144, 30: 231, 35: 340, 40: 485, 45: 643, 50: 833,
                       55: 1060, 60: 1330, 65: 1660, 70: 2040, 75: 2500, 80: 3050}
# AASHTO 2018, rural collectors, level terrain, maximum grade (%). DRAFT.
MAX_GRADE_PCT = {30: 7, 35: 7, 40: 7, 45: 7, 50: 6, 55: 6, 60: 5}
# AASHTO 2018 Tables 3-34 (crest, stopping sight distance) and 3-36 (sag), minimum K (ft per % A). DRAFT.
MIN_K_CREST = {30: 19, 35: 29, 40: 44, 45: 61, 50: 84, 55: 114, 60: 151, 65: 193, 70: 247}
MIN_K_SAG   = {30: 37, 35: 49, 40: 64, 45: 79, 50: 96, 55: 115, 60: 136, 65: 157, 70: 181}
MIN_VC_LENGTH_FT = 200.0          # simplification of "L >= 3V" for V <= 65; DRAFT
def min_radius(v_mph) -> float ; def max_grade(v_mph) -> float ; def min_k(v_mph, curve_type) -> float
STANDARDS_STATUS = "DRAFT — for PE review; not a published standard"
```

### 7.2 `tasks/spec_v1.py` (WP2) — `DRAFTING_SPEC_V1` (DRAFT)
```python
DRAFTING_SPEC_V1 = {
  "spec_id": "roaddraft-drafting-spec", "version": "draft-v1", "status": "DRAFT — for PE review",
  "units": {"model": "us_survey_ft", "paper": "inch"},
  "sheet": {"size": "ANSI_D", "allowed_feet_per_inch": [50, 100], "viewport": {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5},
            "fit_window_in": [26.0, 15.0], "north_arrow": {"required": True, "block": "NORTH_ARROW", "position": [31.6, 19.2], "scale": 0.9},
            "required_title_fields": ["project", "agency", "sheet_title", "sheet_number", "total_sheets", "designed_by", "drawn_by", "checked_by", "date", "scale"],
            "scale_text_format": "1\" = {fpi:.0f}'"},
  "layers": {"alignment": "V-ALIGN-CNTR", "ticks": "V-ROAD-STA", "labels": "V-ANNO-TEXT", "tables": "V-ANNO-TABL"},
  "layer_props": {"V-ALIGN-CNTR": {"color": "red", "linetype": "center", "lineweight_mm": 0.35},
                  "V-ROAD-STA": {"color": "gray", "lineweight_mm": 0.18},
                  "V-ANNO-TEXT": {"color": "black", "lineweight_mm": 0.25},
                  "V-ANNO-TABL": {"color": "black", "lineweight_mm": 0.25}},
  "text": {"label_height_in": 0.10, "table_height_in": 0.12, "height_tolerance_pct": 10},
  "stationing": {"interval_ft": 100, "format": "12+34.56", "decimals": 2, "tick_half_len_in": 0.20, "label_offset_in": 0.32, "label_side": "left", "rotation": "along"},
  "labels": {"pc_pt": {"required": True, "side": "right", "format": "PC 16+00.00"},
             "bearing": {"required": True, "anchor": "T-n", "format": "quadrant", "seconds_decimals": 0, "side": "left"},
             "mc": {"required": True, "format": "C-1"},
             "pi": {"required": False}, "equation": {"required_when_present": True, "format": "STA 20+00.00 BK = STA 25+00.00 AH"}},
  "curve_table": {"required": True, "title": "CURVE DATA", "columns": ["curve", "pi_sta", "delta", "direction", "radius", "tangent", "length", "chord", "chord_bearing"], "length_decimals": 2, "angle_format": "dms"},
  "tolerances": {"length_ft": 0.005, "station_ft": 0.005, "angle_seconds": 1, "position_model_ft": 0.05, "position_paper_in": 0.05, "rotation_deg": 1.0},
  "checks": [
     {"id": "D1-01", "name": "alignment linework on the alignment layer matches design geometry", "weight": 10, "hard_fail": True},
     {"id": "D1-02", "name": "station tick at every interval station (per region)", "weight": 12, "hard_fail": False},
     {"id": "D1-03", "name": "station label content/format correct and anchored", "weight": 12, "hard_fail": True},
     {"id": "D1-04", "name": "PC/PT label for every curve, correct, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-05", "name": "bearing label on every tangent, quadrant format, anchored T-n", "weight": 10, "hard_fail": True},
     {"id": "D1-06", "name": "curve table on the sheet: one row per curve, values within rounding, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-07", "name": "label position within tolerance of the anchor-implied position (no free-floating text)", "weight": 8, "hard_fail": False},
     {"id": "D1-08", "name": "legibility: no Text/Table overlaps on the sheet, nothing outside the usable area", "weight": 6, "hard_fail": False},
     {"id": "D1-09", "name": "layers and text heights per spec", "weight": 6, "hard_fail": False},
     {"id": "D1-10", "name": "title block fields present; scale string matches the viewport", "weight": 5, "hard_fail": False},
     {"id": "D1-11", "name": "north arrow present on the sheet", "weight": 3, "hard_fail": False}],
}
def spec_hash() -> str          # "sha256:" + sha256(canonical json of DRAFTING_SPEC_V1)[:16]
def spec_subset(keys=("units","sheet","layers","layer_props","text","stationing","labels","curve_table","tolerances","checks")) -> dict
```
`tests/test_spec_v1.py`: weights sum to 100; check ids unique; `status` starts with "DRAFT"; every `layers` value has `layer_props`; every `curve_table.columns` key ∈ the catalog list `["curve","pi_sta","pc_sta","pt_sta","delta","direction","radius","tangent","length","external","mid_ordinate","chord","chord_bearing"]` (literal in the test); `spec_hash()` is stable across two calls; `min_radius(45) == 643`, `max_grade(50) == 6`, `min_k(45,"crest") == 61`, `min_k(45,"sag") == 79`.

### 7.3 `tasks/brief.py` (WP9)
```python
GENERATOR_VERSION = "d1-v1"
@dataclass
class TaskBrief:   # agent-visible
    task_id: str; seed: int; level: str; generator_version: str; spec_version: str; spec_hash: str
    project: dict; design: dict; deliverable: dict; drafting_spec: dict; instructions: str
    def to_dict(self) -> dict ; @classmethod from_dict ; def to_json(self) -> str
@dataclass
class GroundTruth:  # verifier-only
    task_id: str; design_fingerprint: str
    labels: List[dict]; ticks: List[dict]; elements: List[dict]; curve_table: dict; sheet: dict; counts: dict
    def to_dict / from_dict / to_json
@dataclass
class Task:
    brief: TaskBrief; truth: GroundTruth; baseline: dict      # baseline = Document JSON with the design pre-seeded
def canonical_json(obj) -> str      # json.dumps(round_floats(obj, 6), sort_keys=True, separators=(",", ":"))
def compute_task_id(seed: int, level: str, payload: dict) -> str   # f"{level}-{seed:06d}-{sha256(canonical_json(payload)).hexdigest()[:12]}"
```
TaskBrief JSON:
```json
{"task_id": "D1-000042-3fa8c1e2b0d4", "seed": 42, "level": "D1", "generator_version": "d1-v1",
 "spec_version": "draft-v1", "spec_hash": "sha256:...",
 "project": {"name": "SR 118 RESURFACING", "agency": "STATE DOT DISTRICT 4", "route": "SR 118", "county": "HARLAN COUNTY",
             "design_speed_mph": 45, "designed_by": "RD", "drawn_by": "AGENT", "checked_by": "RD", "date": "2026-02-11"},
 "design": {"design_speed_mph": 45, "alignments": {"ALIGN-1": <Alignment.to_dict()>}, "profiles": {"PROF-1": <Profile.to_dict()>}},
 "deliverable": {"sheet_name": "C-101", "sheet_size": "ANSI_D", "feet_per_inch": 50,
                 "viewport": {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5, "model_center": [x, y], "rotation_deg": 0.0},
                 "stationing_interval_ft": 100, "station_format": "12+34.56",
                 "required_label_kinds": ["station", "pc", "pt", "bearing", "mc", "curve_table"],
                 "curve_table_columns": [...spec...], "curve_table_position": [x_in, y_in],
                 "text_heights": {"model_label_ft": 5.0, "sheet_table_in": 0.12}, "tick_half_len_ft": 10.0, "label_offset_ft": 16.0,
                 "north_arrow": true, "title_block_fields": {"project": ..., "agency": ..., "sheet_title": "ROADWAY PLAN", "sheet_number": "C-101", "total_sheets": "1", "designed_by", "drawn_by", "checked_by", "date", "scale": "1\" = 50'"}},
 "drafting_spec": <spec_subset()>,
 "instructions": "Draft plan sheet C-101 (ANSI D, 1\" = 50') showing alignment ALIGN-1 in full: draw the alignment on V-ALIGN-CNTR, station ticks and labels every 100 ft, PC/PT labels, a bearing on every tangent, a C-n callout at every mid-curve, a curve data table on the sheet, a north arrow, and a filled title block. Use anchored labels (place_label), never raw text."}
```
GroundTruth JSON:
```json
{"task_id": "...", "design_fingerprint": "sha256:...",
 "labels": [{"kind": "pc", "alignment": "ALIGN-1", "anchor": "PC-1", "content": "PC 16+00.00", "station": 1600.0, "space": "model",
             "side": "right", "label_offset": 16.0, "rotation": "along", "position": [1600.0, 984.0], "rotation_deg": 0.0,
             "halign": "center", "valign": "top", "layer": "V-ANNO-TEXT", "height": 5.0, "required": true}, ...],
 "ticks": [{"station": 1100.0, "station_text": "11+00.00", "start": [x, y], "end": [x, y], "layer": "V-ROAD-STA"}, ...],
 "elements": [{"ref": "T-1", "kind": "tangent", "layer": "V-ALIGN-CNTR"}, {"ref": "C-1", "kind": "curve", ...}],
 "curve_table": {"space": "C-101", "columns": [...keys...], "headers": [...], "rows": [[...]], "layer": "V-ANNO-TABL",
                 "anchor": {"alignment": "ALIGN-1", "ref": "CURVES", "kind": "curve_table"}},
 "sheet": {"name": "C-101", "size": "ANSI_D", "feet_per_inch": 50, "viewport": {...}, "north_arrow_block": "NORTH_ARROW", "title_block_fields": {...}},
 "counts": {"labels": 24, "ticks": 16, "curves": 1, "tangents": 2, "equations": 0}}
```
The hash payload = `{"generator_version", "spec_hash", "project", "design", "deliverable"}` (not `instructions`, not the truth).

### 7.4 `tasks/generator.py` (WP9)
```python
def generate_task(seed: int, curves: Optional[int] = None, equations: bool = False,
                  design_speed_mph: Optional[int] = None, level: str = "D1") -> Task
```
Only `rng = random.Random(seed)` is used (no global RNG, no clock). Algorithm, in this exact order of draws:
1. `V = design_speed_mph or rng.choice([35, 40, 45, 50, 55])`; `n = curves or rng.choice([1, 2, 2, 3])`.
2. Origin `x0 = round(rng.uniform(5000, 20000), 2)`, `y0 = round(rng.uniform(5000, 20000), 2)`; initial direction `d0 = rng.randrange(0, 360)` (degrees, math convention).
3. Per curve k: `R_k = ceil(min_radius(V) · rng.uniform(1.15, 2.5) / 50) · 50`; `Δ_k = rng.randrange(30, 121) / 2` (15.0–60.0° in 0.5° steps); `turn_k = rng.choice(["L", "R"])`; `T_k = R_k·tan(Δ_k/2)`.
4. Segment lengths: `D_0 = round(T_1 + rng.uniform(250, 600))`; `D_k = round(T_k + T_{k+1} + rng.uniform(200, 600))` for interior; `D_n = round(T_n + rng.uniform(250, 600))`.
5. Walk: `P_0 = [x0, y0]`; heading `d = d0`; for k: `P_k = P_{k−1} + D_{k−1}·unit(d)`, then `d += (+Δ_k if turn L else −Δ_k)`; `P_n = P_{n−1} + ...`; all PIs rounded to 0.01 ft. `pis = [PI(P_0, 0)] + [PI(P_k, R_k)] + [PI(P_n, 0)]`; `compile_pis` (must succeed by construction; if it raises, it is a generator bug → assertion).
6. `begin_station = 100 · rng.randrange(10, 200)` (10+00 … 199+00).
7. Fit: `bbox` of the alignment padded 100 ft; `fpi = 50` if `(w <= 26·50 and h <= 15·50)` else `100` if `(w <= 26·100 and h <= 15·100)` else: halve every `uniform` range's realised lengths (multiply `D` by 0.7 and rebuild from step 5 with the same PIs directions) — bounded loop of 10; deterministic because no new draws happen inside the loop.
8. `equations`: if `equations`: choose tangent index `t = rng.randrange(1, n_tangents+1)` — wait: choose the *longest* tangent; `back = ceil((start_station + 50)/100)·100` (first even station ≥ 50 ft into the tangent; if that is within 50 ft of the tangent end, no equation and a warning in `brief.instructions`); `ahead = back + rng.choice([100, 200, 300, 500])`.
9. Profile: PVIs at BEGIN and END plus interior PVIs spaced `s_j = round(rng.uniform(600, 1000))` until the remaining length < 600; `elev_0 = round(rng.uniform(100, 500), 2)`; each grade `g_j = rng.choice([-1, 1]) · rng.randrange(5, int(max_grade(V)·10)+1) / 1000` (0.5 % … gmax in 0.1 % steps; never zero); interior VC: `A = |g_out − g_in|·100`; `L = max(200, ceil(min_k(V, type)·A/50)·50)`; if `L > 500`: reduce `|g_out|` by 0.1 % steps until `L <= 500` (deterministic loop); elevations follow. Non-overlap holds by construction (`L/2 <= 250 < 300 <= spacing/2`).
10. Project meta from seeded word lists: routes `["SR 12","SR 118","US 41","CR 7","SR 260"]`, projects `["RESURFACING","REALIGNMENT","WIDENING","SAFETY IMPROVEMENTS"]`, agencies `["STATE DOT DISTRICT 4","COUNTY ENGINEER","STATE DOT DISTRICT 7"]`, counties list of 5; `date = "2026-01-01" + timedelta(days=seed % 365)`.
11. Deliverable: viewport `model_center` = alignment bbox center rounded to 0.01; `curve_table_position`: candidate top-left corners in order [bottom-right, top-right, bottom-left, top-left] of the usable area inset 0.25 in (table size from `curve_table_rows` widths and `Table` row factors: height = `text_height·(2.0 + 1.8·(rows+1))`); choose the first whose paper rect does not intersect the alignment bbox mapped to paper and expanded by 1.0 in; fallback bottom-right.
12. `baseline` = `Document.new(project.name)`; `doc.design.alignments["ALIGN-1"]`, `doc.design.profiles["PROF-1"]`; `doc.meta.update(task_id=..., spec_version=..., design_speed_mph=V)`; `baseline = doc.to_dict()` (computed after `task_id`).
13. `truth = compute_ground_truth(brief)`; `task_id` computed before steps 12–13.

### 7.5 `tasks/ground_truth.py` (WP9)
```python
def compute_ground_truth(brief: TaskBrief) -> GroundTruth
def match_truth(doc: Document, truth: GroundTruth) -> dict
    # {"matched": n, "missing": [truth label descriptors], "extra": [entity ids with anchors not in truth],
    #  "content_mismatch": [...], "position_mismatch": [...]}; a truth label matches an entity when
    #  (anchor.alignment, anchor.ref, anchor.kind) are equal, content equal, |position − expected| <= tolerances.position_model_ft
```
`compute_ground_truth` rebuilds `Alignment.from_dict`, calls `stationing_plan(interval, tick_half, label_offset)` for ticks/station/junction/equation labels, `compile_label` for `bearing` at every `T-n` and `mc` at every `MC-n`, `curve_table_rows` for the table, all with the deliverable's sizes. Because the reference solution calls the same functions with the same arguments, the reference document matches the truth exactly (asserted in tests).

### 7.6 `tasks/reference.py` (WP9)
```python
def session_for_task(task: Task, out_dir=None) -> Session       # Session(_document=Document.from_dict(task.baseline), out_dir=out_dir)
def reference_solution(task: Task, session: Session) -> List[dict]  # executes; returns session.bus.journal; raises RuntimeError on any non-ok result
def check_replay(session: Session, path) -> bool                # save_journal -> Session.replay_journal -> to_dict equality
```
Ordered commands (D = `brief.deliverable`, S = `brief.drafting_spec`, A = alignment name):
1. `set_meta {"updates": {"task_id", "spec_version"}}`
2. `create_layer` × 4 from `S.layers`/`S.layer_props` (alignment, ticks, labels, tables)
3. `draw_alignment {"alignment": A, "layer": S.layers.alignment}`
4. `annotate_stationing {"space":"model","alignment":A,"interval":D.stationing_interval_ft,"tick_half_len":D.tick_half_len_ft,"text_height":D.text_heights.model_label_ft,"label_offset":D.label_offset_ft,"layer":S.layers.ticks,"label_layer":S.layers.labels}`
5. `place_label {"space":"model","alignment":A,"anchor":"T-n","kind":"bearing","height":model_label_ft,"layer":S.layers.labels}` for n = 1..tangents
6. `place_label {"space":"model","alignment":A,"anchor":"MC-n","kind":"mc","height":model_label_ft,"layer":S.layers.labels}` for n = 1..curves
7. `create_sheet {"name": D.sheet_name, "size": D.sheet_size}`
8. `create_viewport {"sheet": D.sheet_name, **D.viewport}`
9. `place_curve_table {"space": D.sheet_name, "alignment": A, "position": D.curve_table_position, "columns": D.curve_table_columns, "text_height": D.text_heights.sheet_table_in, "layer": S.layers.tables}`
10. `insert_block {"space": D.sheet_name, "block_name": "NORTH_ARROW", "position": S.sheet.north_arrow.position, "scale": S.sheet.north_arrow.scale}`
11. `fill_title_block {"sheet": D.sheet_name, "fields": D.title_block_fields}`

`tasks/__main__.py`: `python -m roaddraft.tasks SEED [--out DIR] [--curves N] [--equations]` writes `<task_id>.brief.json`, `.truth.json`, `.journal.jsonl`, `.rdoc.json`, `.xml`, `C-101.png`, runs `check_replay` and prints `match_truth` counts. `examples/generate_task.py` does the same for seed 42 into `examples/output/`.

## 8. REPL, `/api/state`, Toolspace, optional GUI tool

### 8.1 `api/lines.py` (WP7)
```python
REPL_ALIASES += {"alignment": "create_alignment", "drawalign": "draw_alignment", "profile": "create_profile",
                 "label": "place_label", "curvetable": "place_curve_table", "landxmlin": "import_landxml",
                 "sta2xy": "station_to_xy", "xy2sta": "xy_to_station", "design": "get_design_data",
                 "anchor": "resolve_anchor"}
POSITIONAL += {"create_alignment": ["name"], "modify_alignment": ["name"], "delete_alignment": ["name"],
               "create_profile": ["name", "alignment"], "delete_profile": ["name"], "draw_alignment": ["alignment"],
               "place_label": ["anchor", "alignment"], "place_curve_table": ["position", "alignment"],
               "import_landxml": ["path"], "station_to_xy": ["station", "alignment", "offset"],
               "xy_to_station": ["point", "alignment"], "get_design_data": ["kind", "alignment"],
               "resolve_anchor": ["anchor", "alignment"], "export_landxml": ["path"]}
VARIADIC += {"create_alignment": "pis", "create_profile": "pvis"}
SPATIAL |= {"place_label", "place_curve_table", "resolve_anchor"}
BUILTIN_QUERIES += {"alignments": "list_alignments"}
```
New builtin `landxml [PATH]` → `export_landxml` (both `route_line` and `Repl.dispatch`, the `dxf` pattern). `HELP` banner gains a "Design" block listing `alignment NAME x,y x,y,R x,y begin_station=10+00`, `drawalign NAME`, `station alignment=NAME`, `label PC-1 [NAME] kind=pc`, `curvetable 24,8.5 NAME`, `profile NAME ALIGN sta,elev sta,elev,L ...`, `alignments`, `sta2xy 16+00 NAME`, `xy2sta 1300,1012 NAME`, `design curves`, `anchor PC-1`, `landxmlin PATH`, `landxml [PATH]`. Transcript that must work: `alignment ALIGN-1 1000,1000 1814.359354,1000,800 2433.012702,1357.179677 begin_station=1000` → ok; `drawalign ALIGN-1 layer=CL`; `station alignment=ALIGN-1`; `label PC-1`; `sta2xy 16+00 ALIGN-1` → point `[1600, 1000]`.

### 8.2 `/api/state` (WP8, `server.py`)
`"alignments": self._alignment_state(doc)` after `"references"`: `[{"name","begin_station_text","end_station_text","station_range": "10+00.00 to 25+18.88","length","curves","tangents","equations","source","profiles": [names],"drawn": bool}]`; `"profiles": [{"name","alignment","pvis"}]`. Test `test_state_includes_alignments` populates `session.doc.design.alignments` directly (no bus needed) and asserts the keys.

### 8.3 Toolspace (WP8, `index.html`)
`S.tsOpen.alignments = true`; after the References section append `tsSection("alignments", "Alignments", n, sec => ...)` following the References row pattern: `.lname` = `name · station_range · N curves`; row click prefills `station alignment=NAME`; a "draw" glyph posts `draw_alignment` when `drawn` is false; `.x` posts `delete_alignment` (confirm). Empty state text: `no alignments — alignment NAME x,y x,y,R x,y begin_station=10+00`. Station modal (finishTool station branch) gains a first field `{key: "alignment", label: "Alignment", options: ["(picked entities)", ...S.state.alignments.map(a => a.name)]}`; when an alignment is chosen the exec sends `{space, alignment, interval, tick_half_len, text_height, label_offset}` (no `path_ids`/`begin_station`). Ribbon: Home ▸ Create Design adds `{t:"big", icon:"alignment", label:"Draw Alignment", act:"drawalign"}` (prefill `drawalign `); Annotate ▸ Labels & Tables adds `Label` (act → `openForm("Place label", [alignment select, anchor, kind select, side select, rotation select])` → `exec("place_label", …)`) and `Curve Table` (prefill `curvetable `); Output ▸ Export adds `LandXML` (act → query `export_landxml`). Tab-completion list gains the new verbs. New `ICONS.alignment` (polyline-with-arc glyph).

### 8.4 OPTIONAL click-PIs Alignment tool (WP8, stretch; not required for acceptance)
`TOOLS.alignment = {hint: "click PIs in order; Enter to create"}`; ribbon `{t:"big", icon:"alignment", label:"Alignment", tool:"alignment"}`; key `g`; reuse `S.pts` exactly like `pline` (rubber-band condition at the pline line, dblclick dedupe condition extended); `finishTool` branch when `S.pts.length >= 2`: `openForm("Create alignment", [name, begin_station "10+00", radius (applied to every interior PI), layer select, draw "yes"])` → `exec("create_alignment", {name, begin_station, pis: S.pts.map((p,i) => (i===0||i===S.pts.length-1) ? p : [...p, R])})` then `exec("draw_alignment", {alignment: name, layer})` when draw = yes; clear `S.pts` before the modal.

### 8.5 README (WP10)
New section "Design model (Phase 1)": alignments/profiles, the anchor grammar table, label kinds table, alignment-mode stationing, LandXML, `python -m roaddraft.tasks 42`; layout tree adds `design/ adapters/ tasks/`; stale test counts replaced by the real `pytest -q` count; "What this is not (yet)" reduced to verifier/session server/MCP/spirals/profile views. `examples/demo_plan_sheet.py` rewritten: `create_alignment` → `draw_alignment` → `annotate_stationing(alignment=…)` → `place_label` bearings/`mc` → sheet/viewport → `place_curve_table` → north arrow → notes → title block → outputs + `export_landxml` + replay assertion (≈ 22 commands instead of 56).

## 9. Test plan (file per package; each test name carries its hand-calc numbers)

**WP1 `tests/test_design_angles.py`**: `test_bearing_45_30_15_E`, `test_bearing_due_east_N90E`, `test_bearing_due_north_N00E`, `test_bearing_135_is_S45E`, `test_bearing_180_S00E`, `test_bearing_270_S90W`, `test_bearing_300_N60W`, `test_bearing_5_5_pads_N05`, `test_dms_5_5_unpadded`, `test_dms_carry_59_99999_to_60`, `test_direction_to_azimuth_30_60_0_90_neg90_180_180_270`, `test_signed_delta_0_30_plus30_0_neg30_170_neg170_plus20`, `test_parse_bearing_S45W_225_roundtrip`.
**`tests/test_design_stations.py`** (A, eq raw 2000/2000/2500): `test_display_1500_region1`, `test_display_2000_is_2500_region2`, `test_display_2300_is_2800`, `test_format_2300_28_00_00`, `test_to_raw_2800_is_2300`, `test_parse_28_00_is_2300`, `test_gap_2200_raises`, `test_overlap_1800_ambiguous_1900_regions_1_2`, `test_overlap_region2_1900_is_2100`, `test_bad_back_2200_raises`, `test_raw_outside_alignment_raises`, `test_equation_label_STA_20_BK_25_AH`, `test_end_text_30_18_88`.
**`tests/test_design_horizontal.py`**: `test_curve_R800_d30_T214_359_L418_879_E28_221_M27_259_C414_110_Dc7_162`, `test_curve_R500_d45_T207_107_L392_699_E41_196_M38_060_C382_683`, `test_alignment_A_elements_600_curve_500_length_1518_879`, `test_A_pc_1600_pi_1814_359_pt_2018_879_end_25_18_88`, `test_A_center_1600_1800_direction_L_pt_2000_1107_180`, `test_A_chord_bearing_N75E_back_N90E_ahead_N60E`, `test_station_1800_xy_1797_923_1024_870_dir_14_324`, `test_station_1800_offset25_1804_108_1000_647_radius_825`, `test_station_2300_xy_2243_458_1247_740`, `test_xy_to_station_2228_458_1273_721_is_2300_offset_neg30`, `test_xy_to_station_1300_1012_offset_neg12`, `test_xy_before_begin_900_raises`, `test_xy_at_center_1600_1800_raises`, `test_roundtrip_200_random_stations_offsets_1e6`, `test_mirror_A_direction_R_pt_2000_892_820`, `test_reverse_curve_B_deltas_26_565_T141_641_L278_189_length_3107_848_stations_858_1136_1971_2249`, `test_compound_two_left_30_curves_no_zero_tangent_junction_pcc`, `test_R2300_longer_than_back_tangent_600_raises`, `test_two_R1200_d30_on_600_overlap_43_08_raises`, `test_interior_radius_0_angle_point_raises`, `test_collinear_pi_raises`, `test_station_2600_outside_raises_10_00_to_25_18_88`, `test_to_dict_from_dict_exact`, `test_spiral_element_rejected`, `test_elements_from_dicts_reproduces_compile_1e6`, `test_pi_recovery_from_elements_source_pis`, `test_no_forbidden_imports_in_design_package`.
**`tests/test_design_vertical.py`**: `test_P_g1_2_g2_neg3_A5_K80_crest_pvc_1800_116_pvt_2200_114_E2_5`, `test_P_high_point_1960_117_6`, `test_P_elev_2000_117_5_1900_117_375_grade_1900_0_75`, `test_P_elev_1500_110_2600_102`, `test_P_elev_999_raises`, `test_sag_g1_neg2_g2_3_low_1960_102_4_elev_2000_102_5`, `test_same_sign_2_1_no_high_low_K400`, `test_equal_grades_L200_raises`, `test_overlap_500_500_on_400_raises_100`, `test_L800_on_300_does_not_fit_raises`, `test_end_pvi_length_raises`, `test_non_increasing_raises`, `test_grade_break_returns_ahead_grade`.
**`tests/test_design_anchors.py`**: `test_PC1_1600_1000_dir0`, `test_MC1_1807_055_1027_259_station_1809_440`, `test_PI1_point_1814_359_station_1814_359`, `test_T1_1300_1000_T2_2216_506_1232_180`, `test_18_00_at_25_1804_108_1000_647`, `test_18_00_at_25L_offset_neg25`, `test_numeric_1800_is_display`, `test_dict_station_region_offset`, `test_PC3_raises_lists_valid`, `test_PC3_no_dash_parse_error_hint`, `test_list_anchors_count_2_plus_4_curves_plus_tangents_plus_eq`.
**`tests/test_design_labels.py`**: `test_upright_matches_engine_grid_0_to_360`, `test_pc1_default_right_16_position_1600_984_valign_top`, `test_station_1300_left_1016_valign_bottom`, `test_bearing_T2_N60E_rotation_30_position_2208_506_1246_036`, `test_perpendicular_18_00_rotation_neg75_676`, `test_bearing_on_MC1_raises`, `test_kind_pc_anchor_PT1_raises`, `test_custom_requires_content`, `test_curve_data_multiline_C1_R800_T214_36_L418_88`, `test_sheet_pose_pc1_15_0_8_38_and_twist20`, `test_curve_table_default_row_C1_18_14_36_30_LT_800_214_36_418_88_414_11_N75E`, `test_stationing_plan_A_16_ticks_PC_PT`, `test_stationing_plan_equation_2000_2500_labels_19_25_30_not_20_24`, `test_stationing_plan_range_12_00_18_00_7_ticks`.

**WP2 `tests/test_spec_v1.py`** (§7.2). **WP3 `tests/test_design_schemas.py`**: `test_every_example_validates_against_its_schema` (jsonschema Draft 2020-12), `test_every_schema_closed_additionalProperties_false`, `test_schema_and_example_keys_equal_the_nine_commands`.

**WP4 `tests/test_design_document.py`**: `test_document_round_trip_with_alignment_profile_equation`, `test_from_dict_without_design_key_loads_empty_design`, `test_legacy_v01_fixture_loads`, `test_entity_without_anchor_serializes_without_key`, `test_text_anchor_round_trip_and_translated_keeps_it`, `test_line_arc_table_blockref_transformed_keep_anchor`, `test_expand_entities_block_with_anchored_text_keeps_anchor`, `test_as_anchor_rejects_string_and_bad_key`, `test_existing_91_tests_unchanged` (just runs; implicit).

**WP5 `tests/test_landxml.py`**: `test_write_A_start_text_is_northing_easting_1000_1600`, `test_write_read_A_elements_1e5_equations_pvis`, `test_write_parse_write_byte_identical`, `test_reverse_curve_rot_ccw_then_cw`, `test_metric_304_8m_line_is_999_998_ft`, `test_international_foot_factor_0_999998`, `test_spiral_fixture_raises_not_supported`, `test_gap_fixture_raises_0_050_ft`, `test_unsym_paracurve_raises`, `test_namespace_less_file_parses`, `test_pi_recovery_sets_source_pis`, `test_center_missing_computed_from_radius_rot`, `test_no_forbidden_imports_in_adapters`.

**WP6 `tests/test_design_commands.py`**: `test_create_alignment_diff_and_message_10_00_to_25_18_88`, `test_create_alignment_duplicate_faults`, `test_create_alignment_overlap_atomic_no_journal_growth`, `test_undo_removes_alignment`, `test_create_alignment_from_elements`, `test_modify_alignment_rename_rewrites_anchors_and_profiles`, `test_delete_alignment_with_profile_faults_then_cascade`, `test_create_profile_display_stations_and_warning_beyond_end`, `test_draw_alignment_LN_AR_LN_arc_270_300_anchors_T1_C1_T2`, `test_draw_alignment_mirror_arc_60_90`, `test_draw_alignment_twice_warns_replace_deletes`, `test_import_landxml_inline_xml_replays`, `test_import_landxml_conflict_error_replace_rename`, `test_modify_entity_sets_and_clears_anchor_rejects_junk`, `test_replay_determinism_all_new_commands`, `test_manifest_lists_nine_commands_with_examples`, `test_no_alias_collisions_except_LAYER_XREF`. **`tests/test_design_labels_cmd.py`**: `test_place_label_pc1_content_position_1600_984_anchor_record`, `test_place_label_station_13_00_1300_1016`, `test_place_label_bearing_T2_N60E_rotation_30`, `test_place_label_perpendicular_neg75_676`, `test_place_label_infers_kind_from_anchor`, `test_place_label_kind_mismatch_faults`, `test_place_label_custom_without_content_faults`, `test_place_label_explicit_content_verbatim_content_auto_false`, `test_place_label_sheet_15_0_8_38_viewport_VP001_height_0_10`, `test_place_label_sheet_twist20_rotation_20`, `test_place_label_sheet_no_viewport_faults_with_hint`, `test_place_label_duplicate_warning`, `test_place_label_default_alignment_when_single_else_fault`, `test_move_entities_keeps_anchor`, `test_place_curve_table_row_and_anchor`, `test_place_curve_table_in_model_faults`. **`tests/test_stationing_alignment.py`**: `test_alignment_mode_A_matches_entity_mode_labels_16_PC_PT`, `test_alignment_mode_every_tick_and_label_anchored_entity_mode_none`, `test_alignment_mode_equation_2000_2500_16_ticks_labels_19_25_30_not_20_and_EQ1_label`, `test_station_range_12_00_18_00_7_ticks`, `test_both_path_ids_and_alignment_fault`, `test_neither_fault`, `test_begin_station_with_alignment_fault`, `test_alignment_mode_on_sheet_faults`, `test_entity_mode_golden_unchanged_34_ids` (snapshot of `centerline_session` output before/after).

**WP7 `tests/test_design_queries.py`**: `test_list_alignments_shape`, `test_station_to_xy_16_00_string_and_1600_number_agree`, `test_station_to_xy_offset12_1600_988`, `test_xy_to_station_1300_1012_neg12_side_L`, `test_resolve_anchor_dry_run_equals_place_label`, `test_get_design_data_curves_row_numbers`, `test_get_design_data_pagination_start_1_limit_1_total_3`, `test_get_design_data_vcs_A5_K80`, `test_unknown_alignment_query_failed_hint`, `test_summary_lists_alignments_profiles`, `test_export_landxml_file_contains_staStart`, `test_route_line_sta2xy_and_alignments_builtin`, `test_route_line_alignment_variadic_pis` (needs WP6 → this one test lives in WP10's file instead).

**WP8 `tests/test_web_design.py`**: `test_state_includes_alignments_and_profiles`, `test_state_alignment_station_range_text`.

**WP9 `tests/test_tasks.py`**: `test_seed_42_twice_identical_json_and_id`, `test_seed_43_differs`, `test_task_ids_match_pinned_fixture_seeds_1_2_3_42_100`, `test_200_seeds_R_ge_min_radius_grade_le_max_K_ge_min_compile_ok_fits_window`, `test_truth_label_count_equals_reference_entities`, `test_reference_solution_zero_faults_zero_warnings_20_seeds`, `test_reference_matches_truth_missing_empty_content_empty_position_empty`, `test_check_replay_true`, `test_render_sheet_png_over_20kB`, `test_equations_dial_produces_EQ1_label`, `test_baseline_has_design_no_entities_no_sheets`.

**WP10 `tests/test_design_integration.py`**: `test_route_line_full_transcript_8_1`, `test_demo_plan_sheet_runs_and_replays`, `test_readme_test_count_matches` (optional), `test_help_lists_every_new_verb`.

## 10. Work packages

| WP | Stage | Owner files (exclusive) | Depends on | Acceptance | DO NOT TOUCH |
|---|---|---|---|---|---|
| **WP1 design core** | 1 | `design/*` (9 files), 6 `tests/test_design_*.py` (angles, stations, horizontal, vertical, anchors, labels) | none (reads `core/geometry.py`, `core/units.py`) | `.venv/bin/pytest -q tests/test_design_angles.py tests/test_design_stations.py tests/test_design_horizontal.py tests/test_design_vertical.py tests/test_design_anchors.py tests/test_design_labels.py` + full suite green | anything outside `design/` and its tests |
| **WP2 standards + spec** | 1 | `tasks/__init__.py`, `tasks/standards.py`, `tasks/spec_v1.py`, `tests/test_spec_v1.py` | none | `pytest -q tests/test_spec_v1.py` | everything else; never edit `tasks/__init__.py` again |
| **WP3 design schemas** | 1 | `commands/design_schemas.py`, `tests/test_design_schemas.py` | none (imports `schemas.py` fragments only; defines `LABEL_KINDS` list literally, not importing `design`) | `pytest -q tests/test_design_schemas.py` | `schemas.py`, `bus.py`, `handlers.py` |
| **WP4 document wiring** | 2 | `document/document.py`, `document/entities.py`, `tests/test_design_document.py`, `tests/fixtures/legacy_v01.rdoc.json` | WP1 | `pytest -q tests/test_design_document.py tests/test_document.py` + full suite | `sheets.py`, `references.py`, `commands/*`, `design/*` |
| **WP5 LandXML adapter** | 2 | `adapters/__init__.py`, `adapters/landxml.py`, `tests/test_landxml.py`, `tests/fixtures/landxml/*` | WP1 | `pytest -q tests/test_landxml.py` | `commands/*`, `design/*`, `document/*` |
| **WP6 commands** | 3 | `commands/design_handlers.py`, `commands/handlers.py`, `commands/schemas.py`, `commands/bus.py`, `tests/test_design_commands.py`, `tests/test_design_labels_cmd.py`, `tests/test_stationing_alignment.py` | WP1, WP3, WP4, WP5 | `pytest -q tests/test_design_commands.py tests/test_design_labels_cmd.py tests/test_stationing_alignment.py tests/test_stationing.py tests/test_session.py` + full suite | `design/*`, `adapters/*`, `document/*`, `api/*`, `web/*`, `design_schemas.py` (fix requests go to WP3's owner as a follow-up) |
| **WP7 API/REPL** | 3 | `api/session.py`, `api/lines.py`, `cli/repl.py`, `tests/test_design_queries.py` | WP1, WP4, WP5 (tests populate `doc.design` directly via `Session(_document=doc)`; grammar entries for WP6 commands are strings only) | `pytest -q tests/test_design_queries.py tests/test_session.py tests/test_web.py` + full suite | `commands/*`, `document/*`, `design/*`, `web/*` |
| **WP8 web** | 3 | `web/server.py`, `web/static/index.html`, `tests/test_web_design.py` | WP4 | `pytest -q tests/test_web_design.py tests/test_web.py`; manual GUI check of the Toolspace node | anything outside `web/` |
| **WP9 tasks** | 4 | `tasks/brief.py`, `tasks/generator.py`, `tasks/ground_truth.py`, `tasks/reference.py`, `tasks/__main__.py`, `tests/test_tasks.py`, `tests/fixtures/task_ids_d1_v1.json`, `examples/generate_task.py` | WP1–WP7 | `pytest -q tests/test_tasks.py`; `python -m roaddraft.tasks 42 --out /tmp/x` writes 6 files | everything under `src/` outside `tasks/` (a needed bus change is a WP6 follow-up, never a tasks-side workaround) |
| **WP10 docs + integration** | 4 | `README.md`, `examples/demo_plan_sheet.py`, `tests/test_design_integration.py` | WP1–WP8 | `pytest -q` (whole suite); `python examples/demo_plan_sheet.py` ends with the replay OK line | `src/**`, other tests |

Merge order: WP1, WP2, WP3 (any order) → WP4, WP5 (any order) → WP6, WP7, WP8 (any order) → WP9, WP10 (any order). The C1↔C2 contract is this document: WP6 registers exactly `dh.create_alignment, dh.modify_alignment, dh.delete_alignment, dh.create_profile, dh.delete_profile, dh.draw_alignment, dh.place_label, dh.place_curve_table, dh.import_landxml` and calls `dh.annotate_stationing_alignment`; WP3's `DESIGN_SCHEMAS`/`DESIGN_EXAMPLES` keys are exactly those nine names. Interfaces between stages are the signatures in §2–§6; a deviation requires a one-line note in the PR and a ping to the downstream owner.

## 11. Out of scope (Phase 1)

- Spirals (`"spiral"` reserved in `ELEMENT_KINDS`; rejected everywhere; TS/SC/CS/ST anchors, spiral pieces, and LandXML `Spiral` are future work).
- Asymmetric vertical curves (`UnsymParaCurve`), circular vertical curves.
- Profile VIEW drawing on sheets, VC tables, grade labels (D2).
- The verifier (`run_check`, scoring), the session server, MCP mode, `get_task_brief` query, `run_check` budgets.
- Annotation-scale document setting; station-offset labels (`STA 12+34.56 25.00' RT`); match lines; multi-sheet (D3).
- Superelevation, surfaces, corridors, cross sections; LandXML `Surfaces`/`Parcels`/`PipeNetworks` (silently skipped).
- Alignment hit-testing/selection in the GUI; DXF XDATA for anchors.
- Fixing the `_upright` west-heading valign gotcha (kept identical in both stationing modes; flagged for PE review).
- Standards tables are DRAFT (AASHTO values transcribed, uncited page numbers) and the drafting spec is DRAFT; both must be PE-reviewed before any published task set; `spec_hash` in every task id ensures corrections mint new ids rather than silently re-scoring old ones.