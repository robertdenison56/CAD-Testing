"""The command bus: the single gate through which document state changes.

Every mutation is a named, JSON-serializable command that is schema-validated,
applied atomically (a fault restores the pre-command snapshot), journaled, and
undoable. The journal replays deterministically, which makes a session log a
training trajectory.

Commands carry Civil 3D-style and MicroStation/ORD-style aliases so the same
action space can later be presented in either program's vocabulary (PRD
section 4 - program dialects).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import jsonschema
from jsonschema.exceptions import best_match

from roaddraft.commands import annotation_handlers as ah
from roaddraft.commands import design_handlers as dh
from roaddraft.commands import dimension_handlers as dim
from roaddraft.commands import edit_handlers as eh
from roaddraft.commands import handlers as h
from roaddraft.commands.schemas import EXAMPLES, SCHEMAS
from roaddraft.document.document import Document

UNDO_LIMIT = 100

# The commands that place design-anchored work, and so the only provenance a
# verifier trusts. The bus stamps anchor.placed_by on the entities a command
# creates (_stamp_provenance), which makes provenance the bus's to write
# rather than the handler's or the caller's.
ANCHOR_PRODUCERS = ("draw_alignment", "draw_offset", "annotate_stationing",
                    "place_label", "place_curve_table")


@dataclass
class CommandSpec:
    name: str
    description: str
    handler: Optional[Callable]
    aliases: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def schema(self) -> dict:
        return SCHEMAS[self.name]

    @property
    def example(self) -> dict:
        return EXAMPLES[self.name]


REGISTRY: List[CommandSpec] = [
    CommandSpec("set_meta", "Update document metadata (project name, description).",
                h.set_meta),
    CommandSpec("create_layer",
                "Create a layer (MicroStation: level). Entities reference layers "
                "for color/linetype/lineweight unless overridden.",
                h.create_layer, {"c3d": ["LAYER"], "ord": ["level create"]}),
    CommandSpec("modify_layer", "Change a layer's color, linetype, lineweight, "
                "description, or visibility.", h.modify_layer,
                {"c3d": ["LAYER"], "ord": ["level manager"]}),
    CommandSpec("set_current_layer",
                "Set the current layer, used when a drawing command omits 'layer'.",
                h.set_current_layer, {"c3d": ["CLAYER"], "ord": ["active level"]}),
    CommandSpec("create_text_style", "Create a named text style.",
                h.create_text_style, {"c3d": ["STYLE"], "ord": ["text style"]}),
    CommandSpec("define_block",
                "Define a reusable symbol (AutoCAD: block, MicroStation: cell) "
                "from primitive entities in block-local coordinates.",
                h.define_block, {"c3d": ["BLOCK"], "ord": ["cell create"]}),
    CommandSpec("draw_line", "Draw a line segment.", h.draw_line,
                {"c3d": ["LINE"], "ord": ["place line"]}),
    CommandSpec("draw_polyline", "Draw a polyline through vertices.",
                h.draw_polyline, {"c3d": ["PLINE"], "ord": ["place smartline"]}),
    CommandSpec("draw_arc",
                "Draw a circular arc running counter-clockwise from start to end "
                "angle (degrees from +X).", h.draw_arc,
                {"c3d": ["ARC"], "ord": ["place arc"]}),
    CommandSpec("draw_circle", "Draw a circle.", h.draw_circle,
                {"c3d": ["CIRCLE"], "ord": ["place circle"]}),
    CommandSpec("draw_traverse",
                "Draw lines and curves by bearing and distance (COGO), the way a deed, a "
                "field book or a design report gives them: start at a point -- or at the end "
                "of an entity, to carry on from it -- and run course after course, each a "
                "quadrant bearing, an azimuth or a deflection from the previous course, and "
                "a distance; a curve course by radius, turn and delta, length or chord. The "
                "engine computes every point, so there is no trigonometry to do by hand, and "
                "close=true reports how well a boundary closes (precision 1:N). The traverse "
                "query computes the same points without drawing.",
                eh.draw_traverse,
                {"c3d": ["BD", "AD", "DD"], "ord": ["place line by bearing and distance"]}),
    CommandSpec("place_text",
                "Place a text annotation. Height is in space units: feet in model "
                "space, inches on sheets. Supports \\n for multi-line.",
                h.place_text, {"c3d": ["TEXT", "MTEXT"], "ord": ["place text"]}),
    CommandSpec("place_callout",
                "Text with a leader pointing at something: the way a drafter annotates "
                "geometry that carries no design model of its own -- a pavement edge, a "
                "utility, anything seen through a reference. Name what it points at: "
                "target_entity (an id from find_entities or hit_test, referenced "
                "entities included) or target_anchor (a station, offset or named point "
                "of an alignment, a referenced one included). Plan callouts belong on "
                "the sheet, and from a sheet both are seen through its viewport -- the "
                "tip lands in paper inches where the model shows, with no scale or "
                "twist arithmetic to do by hand. Leader, landing, arrowhead and text "
                "are drawn as ordinary entities on the current or given layer.",
                h.place_callout,
                {"c3d": ["MLEADER", "QLEADER", "LEADER"],
                 "ord": ["place note", "place callout"]}),
    CommandSpec("place_dimension",
                "Measure the drawing and say so on it: linear, aligned, angular, "
                "radius, diameter or arc_length. The document stores the measurement "
                "-- the points, the arc, and where the dimension line was dragged to "
                "-- and derives extension lines, dimension line, arrowheads and the "
                "number from it, so the text cannot drift from the geometry and the "
                "annotation scale re-sizes the annotation without moving the "
                "measurement. Name what to measure (of_entity for one entity end to "
                "end or a curve's own geometry, from_entity/to_entity for two, two "
                "lines for the angle between them) or give the points outright; "
                "line_point settles which measurement was meant.",
                dim.place_dimension,
                {"c3d": ["DIM", "DIMLINEAR", "DIMALIGNED", "DIMANGULAR", "DIMRADIUS",
                         "DIMDIAMETER", "DIMARC"],
                 "ord": ["place dimension", "dimension element", "dimension linear",
                         "dimension angle", "dimension radius"]}),
    CommandSpec("insert_block", "Insert a block/cell reference.", h.insert_block,
                {"c3d": ["INSERT"], "ord": ["place cell"]}),
    CommandSpec("place_table",
                "Place a data table (e.g. curve data). Position is the top-left "
                "corner; column widths are in space units.", h.place_table,
                {"c3d": ["TABLE"], "ord": ["place table"]}),
    CommandSpec("move_entities", "Translate entities by [dx, dy].",
                h.move_entities, {"c3d": ["MOVE"], "ord": ["move element"]}),
    CommandSpec("offset_entity",
                "Copy a line, polyline, arc or circle parallel to itself at a distance "
                "(AutoCAD OFFSET, MicroStation Copy Parallel): say the side as left/right of "
                "the direction it runs, or give a point on that side (toward) or one the copy "
                "passes through (through), or several signed offsets at once. Several "
                "entities that join end to end are offset together as one path, corners "
                "mitred (or rounded) so the copy stays continuous; curves keep their centre "
                "and change radius. Works on reference elements too, copying them into this "
                "document. For an alignment's own offsets, tied to the design, use "
                "draw_offset.",
                eh.offset_entity, {"c3d": ["O"], "ord": ["copy parallel"]}),
    CommandSpec("fillet",
                "Round the corner between two lines with a curve of a given radius, tangent "
                "to both, and trim or extend the lines to meet it (AutoCAD FILLET, "
                "MicroStation Construct Circular Fillet) -- a curb return, a driveway "
                "flare, the corner of a parking area. The lines need not touch; keep says "
                "which part of each line stays when they cross. Radius 0 extends or trims "
                "them to a sharp corner. The answer gives the tangent points, delta, "
                "tangent length and arc length.",
                eh.fillet,
                {"c3d": ["FILLET", "F"], "ord": ["construct circular fillet", "fillet single"]}),
    CommandSpec("modify_entity",
                "Change fields of one entity (geometry, content, layer, style...).",
                h.modify_entity, {"c3d": ["PROPERTIES"], "ord": ["modify element"]}),
    CommandSpec("delete_entities", "Delete entities by id.", h.delete_entities,
                {"c3d": ["ERASE"], "ord": ["delete element"]}),
    CommandSpec("create_sheet",
                "Create a sheet (AutoCAD: paper-space layout, MicroStation: sheet "
                "model) with a border and title block. Paper units are inches.",
                h.create_sheet, {"c3d": ["LAYOUT"], "ord": ["sheet model create"]}),
    CommandSpec("delete_sheet", "Delete a sheet.", h.delete_sheet),
    CommandSpec("create_viewport",
                "Create a viewport on a sheet windowing into model space at a plot "
                "scale (feet_per_inch; 1\"=50' -> 50) with optional view twist.",
                h.create_viewport,
                {"c3d": ["MVIEW"], "ord": ["place named boundary"]}),
    CommandSpec("modify_viewport", "Change viewport placement, scale, or twist.",
                h.modify_viewport),
    CommandSpec("delete_viewport", "Delete a viewport from a sheet.",
                h.delete_viewport),
    CommandSpec("fill_title_block", "Set title block fields on a sheet.",
                h.fill_title_block,
                {"c3d": ["ATTEDIT"], "ord": ["edit tags"]}),
    CommandSpec("annotate_stationing",
                "The roadway stationing engine. Entity-chain mode (path_ids + "
                "begin_station): walk connected line/polyline/arc entities. "
                "Design mode (alignment=NAME): use the alignment's true stations "
                "and equations and anchor every tick and label. Either way it "
                "draws perpendicular ticks at the interval, '12+34.56' labels "
                "rotated along the path, and BC/EC/PCC/PRC labels at the curve "
                "points.",
                h.annotate_stationing,
                {"c3d": ["ADDALIGNMENTLABELS"], "ord": ["annotate stationing"]}),
    CommandSpec("create_alignment",
                "Create a horizontal alignment in the design model from PIs "
                "([x, y] at BEGIN/END, [x, y, R] interior), from bearings and distances "
                "(start + legs: each leg a bearing, azimuth or deflection and the distance "
                "to the next PI, with the radius of the curve at the PI it starts from), "
                "or from CoordGeom elements; optional begin station (display, '10+00') and "
                "station equations. x is the easting and y the northing, so N 5000, E 2000 "
                "is [2000, 5000]. Given legs, the engine computes the PIs -- no "
                "trigonometry by hand -- and get_design_data kind=tangents reads the "
                "bearings and lengths back. Alignments are pure design data: "
                "draw_alignment puts linework in model space, annotate_stationing/"
                "place_label label it.",
                dh.create_alignment,
                {"c3d": ["CREATEALIGNMENTLAYOUT"], "ord": ["complex by pi"]}),
    CommandSpec("modify_alignment",
                "Change an alignment's PIs, begin station, equations, description, "
                "or name (rename rewrites anchors and profile bindings). Entities "
                "already drawn from it are not regenerated (a warning says so).",
                dh.modify_alignment, {"c3d": ["EDITALIGNMENT"], "ord": ["alignment edit"]}),
    CommandSpec("delete_alignment",
                "Delete an alignment (cascade=true also deletes its profiles); "
                "drawn entities keep their anchors.",
                dh.delete_alignment,
                {"c3d": ["DELETEALIGNMENT"], "ord": ["alignment delete"]}),
    CommandSpec("create_profile",
                "Create a vertical profile on an alignment from PVIs "
                "([station, elevation] or [station, elevation, vc_length]; "
                "stations are display stations).",
                dh.create_profile,
                {"c3d": ["CREATEPROFILELAYOUT"], "ord": ["profile complex by vpi"]}),
    CommandSpec("delete_profile", "Delete a profile by name.", dh.delete_profile,
                {"c3d": ["DELETEPROFILE"], "ord": ["profile delete"]}),
    CommandSpec("draw_alignment",
                "Draw an alignment's tangents and curves as anchored line/arc "
                "entities in model space (replace=true redraws).",
                dh.draw_alignment,
                {"c3d": ["ALIGNMENTTOPOLYLINE"], "ord": ["alignment export geometry"]}),
    CommandSpec("draw_offset",
                "Draw constant offsets of an alignment as anchored lines and arcs: "
                "pavement edges, shoulders, right of way. Offsets are feet, right of "
                "the direction of stationing positive ('12L' says the side out loud), "
                "so a 24 ft pavement is offsets [-12, 12]. Tangents shift sideways; "
                "curves keep their center and change radius, so the chain meets end to "
                "end exactly. station_range draws only part of the chain, which is how "
                "an edge or a curb line stops short of an intersection and picks up "
                "again on the far leg.",
                dh.draw_offset,
                {"c3d": ["CREATEOFFSETALIGNMENT", "OFFSET"],
                 "ord": ["single offset entire element", "offset element"]}),
    CommandSpec("place_label",
                "Place a design-anchored label: name a point on an alignment "
                "(PC-1, T-2, '18+00@25L', ...) and a kind (station, pc, pt, pi, "
                "mc, bearing, equation, curve_data, custom...); content, side, "
                "offset, and rotation follow drafting convention unless "
                "overridden. Works in model space or on a sheet through a "
                "viewport. The text records its anchor for the verifier.",
                dh.place_label,
                {"c3d": ["ADDALIGNMENTSTAOFFLABEL"], "ord": ["place label"]}),
    CommandSpec("place_curve_table",
                "Place a curve data table (Δ, R, T, L, chord, bearings...) for an "
                "alignment on a sheet, one row per curve, anchored to the "
                "alignment.", dh.place_curve_table,
                {"c3d": ["ADDALIGNMENTCURVETABLE"], "ord": ["place curve table"]}),
    CommandSpec("import_landxml",
                "Import LandXML 1.2 alignments (Line/Curve CoordGeom, station "
                "equations) and profiles into the design model, from a file path "
                "(read at execute time, so replay depends on the file) or inline "
                "xml text.", dh.import_landxml,
                {"c3d": ["LANDXMLIN"], "ord": ["import landxml"]}),
    CommandSpec("attach_reference",
                "Attach an external RoadDraft document (basefile) as a reference "
                "(AutoCAD: xref, MicroStation: reference attachment). The host "
                "stores path + placement + display settings; the basefile's "
                "model geometry displays under this document's own entities and "
                "in sheet viewports, and reloads from disk — never copied in. "
                "Relative paths resolve against the host document's folder. "
                "true_scale converts the basefile's units into the host space's "
                "(default on); levels_off, symbology (color/linetype/"
                "lineweight_mm/gray), clip (boundary polygon) and masks (mask "
                "polygons) control how it displays; model picks the "
                "basefile's design model or one of its sheets; nest_depth "
                "shows the basefile's own references (live nesting).",
                h.attach_reference,
                {"c3d": ["XATTACH", "XREF"], "ord": ["reference attach"]}),
    CommandSpec("detach_reference", "Detach a reference by name.",
                h.detach_reference,
                {"c3d": ["XREF"], "ord": ["reference detach"]}),
    CommandSpec("modify_reference",
                "Change a reference's path, placement (offset/rotation/scale), "
                "visibility, true_scale, per-attachment level display "
                "(levels_off), symbology overrides (color, linetype, "
                "lineweight_mm, gray=true for gray-out), clip boundary (clip: "
                "polygon in host coordinates, null clears), clip masks "
                "(masks: list of polygons), model (design model or a "
                "basefile sheet) or nest_depth (live nesting).",
                h.modify_reference,
                {"c3d": ["XCLIP"],
                 "ord": ["reference settings", "reference clip boundary",
                         "reference clip mask", "reference levels",
                         "reference presentation"]}),
    CommandSpec("reload_references",
                "Re-read all referenced basefiles from disk on next use.",
                h.reload_references, {"ord": ["reference reload"]}),
    CommandSpec("set_annotation_scale",
                "Set the current annotation scale (AutoCAD annotation scale / Civil 3D "
                "drawing scale): annotation commands then size text, ticks and label "
                "offsets from paper defaults (0.10 / 0.20 / 0.32 in) x the scale, stamp "
                "what they draw as annotative, and this command re-sizes existing "
                "annotative model annotation for the new plot scale (anchored labels are "
                "re-placed through the design). null/'off' restores the fixed feet "
                "defaults.", ah.set_annotation_scale,
                {"c3d": ["CANNOSCALE"], "ord": ["active annotation scale"]}),
    CommandSpec("add_annotation_scale", "Add a named plot scale to the document's scale "
                "list.", ah.add_annotation_scale,
                {"c3d": ["SCALELISTEDIT"], "ord": ["annotation scale add"]}),
    CommandSpec("delete_annotation_scale", "Remove a plot scale from the scale list (not "
                "the current one).", ah.delete_annotation_scale,
                {"ord": ["annotation scale delete"]}),
    CommandSpec("set_annotation_defaults",
                "Set the paper-unit annotation defaults (text height, tick half-length, "
                "label offset in inches) that the annotation scale converts to feet.",
                ah.set_annotation_defaults, {"c3d": ["DIMSTYLE"], "ord": ["annotation settings"]}),
    CommandSpec("undo", "Revert the most recent command.", None,
                {"c3d": ["U", "UNDO"], "ord": ["undo"]}),
    CommandSpec("redo", "Re-apply the most recently undone command.", None,
                {"c3d": ["REDO"], "ord": ["redo"]}),
]

SPECS: Dict[str, CommandSpec] = {spec.name: spec for spec in REGISTRY}


def _alias_map() -> Dict[str, str]:
    amap = {}
    for spec in REGISTRY:
        amap[spec.name.lower()] = spec.name
        for names in spec.aliases.values():
            for alias in names:
                amap[alias.lower()] = spec.name
    return amap


ALIASES = _alias_map()


class CommandBus:
    def __init__(self, document: Document):
        self.doc = document
        self.baseline = document.to_dict()
        self.journal: List[dict] = []
        self._undo: List[tuple] = []  # (snapshot, command_name)
        self._redo: List[tuple] = []
        self._validators: Dict[str, jsonschema.Draft202012Validator] = {}

    # ------------------------------------------------------------ resolve

    @staticmethod
    def resolve(name: str) -> Optional[CommandSpec]:
        canonical = ALIASES.get(name.lower())
        return SPECS.get(canonical) if canonical else None

    def _validator(self, spec: CommandSpec):
        if spec.name not in self._validators:
            self._validators[spec.name] = jsonschema.Draft202012Validator(spec.schema)
        return self._validators[spec.name]

    # ------------------------------------------------------------ execute

    def execute(self, name: str, params: Optional[dict] = None) -> dict:
        params = params or {}
        spec = self.resolve(name)
        if spec is None:
            suggestions = difflib.get_close_matches(name.lower(), list(ALIASES), n=3)
            return self._error(name, "unknown_command",
                               f"unknown command {name!r}",
                               hint=f"did you mean {suggestions}? "
                                    f"Use list_commands for the full tool surface.")
        error = best_match(self._validator(spec).iter_errors(params))
        if error is not None:
            path = ".".join(str(p) for p in error.absolute_path)
            return self._error(
                spec.name, "invalid_params",
                f"{error.message}" + (f" (at {path!r})" if path else ""),
                hint="params must match the schema; a valid example is included",
                schema=spec.schema, example=spec.example)

        if spec.name == "undo":
            return self._do_undo()
        if spec.name == "redo":
            return self._do_redo()

        snapshot = self.doc.to_dict()
        try:
            message, diff, warnings = spec.handler(self.doc, params)
        except h.CommandFault as fault:
            self._restore(snapshot)
            return self._error(spec.name, "command_failed", str(fault),
                              hint=fault.hint, example=spec.example)
        except Exception as ex:  # defensive: never leave a half-applied command
            self._restore(snapshot)
            return self._error(spec.name, "internal_error",
                               f"{type(ex).__name__}: {ex}")
        self._stamp_provenance(spec.name, diff["created"])
        self._push_undo(snapshot, spec.name)
        self._redo.clear()
        return self._record(spec.name, params, message, diff, warnings)

    def execute_json(self, call: dict) -> dict:
        """Execute {'command': name, 'params': {...}} (the wire format)."""
        if not isinstance(call, dict) or "command" not in call:
            return self._error("?", "invalid_call",
                               "expected {'command': <name>, 'params': {...}}")
        return self.execute(call["command"], call.get("params") or {})

    def _stamp_provenance(self, name: str, created: List[str]):
        """Stamp ``anchor.placed_by`` with the command that created the entity.

        Only creation stamps: an anchor attached to an existing entity later
        carries no provenance (modify_entity cannot claim any, and preserves
        what an entity was created with), and editing an anchored label -- a
        rename, a move, a layer change -- leaves its stamp alone."""
        for eid in created:
            found = self.doc.find_entity(eid)
            if found is not None and found[1].anchor is not None:
                found[1].anchor["placed_by"] = name

    def _restore(self, snapshot: dict):
        """Replace the document from a snapshot, keeping the transient host
        path so relative reference paths still resolve after undo/redo."""
        path = self.doc._path
        self.doc = Document.from_dict(snapshot)
        self.doc._path = path

    # --------------------------------------------------------- undo / redo

    def _push_undo(self, snapshot: dict, name: str):
        self._undo.append((snapshot, name))
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)

    def _do_undo(self) -> dict:
        if not self._undo:
            return self._error("undo", "nothing_to_undo", "nothing to undo")
        self._redo.append((self.doc.to_dict(), self._undo[-1][1]))
        snapshot, undone = self._undo.pop()
        self._restore(snapshot)
        return self._record("undo", {}, f"undid {undone}",
                            {"created": [], "modified": [], "deleted": []}, [])

    def _do_redo(self) -> dict:
        if not self._redo:
            return self._error("redo", "nothing_to_redo", "nothing to redo")
        snapshot, redone = self._redo.pop()
        self._push_undo(self.doc.to_dict(), f"undo of {redone}")
        self._restore(snapshot)
        return self._record("redo", {}, f"redid {redone}",
                            {"created": [], "modified": [], "deleted": []}, [])

    # ------------------------------------------------------------- results

    def _record(self, name, params, message, diff, warnings) -> dict:
        seq = len(self.journal) + 1
        self.journal.append({"seq": seq, "name": name, "params": params})
        return {"ok": True, "command_id": seq, "name": name, "message": message,
                "created": diff["created"], "modified": diff["modified"],
                "deleted": diff["deleted"], "warnings": warnings}

    @staticmethod
    def _error(name, etype, message, hint=None, schema=None, example=None) -> dict:
        error = {"type": etype, "message": message}
        if hint:
            error["hint"] = hint
        if schema is not None:
            error["valid_params_schema"] = schema
        if example is not None:
            error["example"] = example
        return {"ok": False, "name": name, "error": error, "warnings": []}

    # ------------------------------------------------------------- replay

    @classmethod
    def replay(cls, baseline: dict, entries: List[dict], home=None) -> "CommandBus":
        """Rebuild a bus by re-executing a journal against its baseline document.
        Deterministic: same baseline + same journal -> same document. ``home``
        is the host path relative reference paths resolve from, as a loaded
        document's own path is."""
        bus = cls(Document.from_dict(baseline))
        bus.doc._path = home
        for entry in entries:
            result = bus.execute(entry["name"], entry.get("params") or {})
            if not result["ok"]:
                raise RuntimeError(
                    f"replay diverged at seq {entry.get('seq')}: "
                    f"{result['error']['message']}")
        return bus

    # ------------------------------------------------------------ manifest

    @staticmethod
    def manifest() -> List[dict]:
        return [{
            "name": spec.name,
            "kind": "command",
            "description": spec.description,
            "params_schema": spec.schema,
            "example": spec.example,
            "aliases": spec.aliases,
        } for spec in REGISTRY]
