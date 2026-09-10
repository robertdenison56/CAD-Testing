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

from roaddraft.commands import design_handlers as dh
from roaddraft.commands import handlers as h
from roaddraft.commands.schemas import EXAMPLES, SCHEMAS
from roaddraft.document.document import Document

UNDO_LIMIT = 100


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
    CommandSpec("place_text",
                "Place a text annotation. Height is in space units: feet in model "
                "space, inches on sheets. Supports \\n for multi-line.",
                h.place_text, {"c3d": ["TEXT", "MTEXT"], "ord": ["place text"]}),
    CommandSpec("insert_block", "Insert a block/cell reference.", h.insert_block,
                {"c3d": ["INSERT"], "ord": ["place cell"]}),
    CommandSpec("place_table",
                "Place a data table (e.g. curve data). Position is the top-left "
                "corner; column widths are in space units.", h.place_table,
                {"c3d": ["TABLE"], "ord": ["place table"]}),
    CommandSpec("move_entities", "Translate entities by [dx, dy].",
                h.move_entities, {"c3d": ["MOVE"], "ord": ["move element"]}),
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
                "rotated along the path, and PC/PT/PCC/PRC labels at junctions.",
                h.annotate_stationing,
                {"c3d": ["ADDALIGNMENTLABELS"], "ord": ["annotate stationing"]}),
    CommandSpec("create_alignment",
                "Create a horizontal alignment in the design model from PIs "
                "([x, y] at BEGIN/END, [x, y, R] interior) or from CoordGeom "
                "elements; optional begin station (display, '10+00') and station "
                "equations. Alignments are pure design data: draw_alignment puts "
                "linework in model space, annotate_stationing/place_label label it.",
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
                "polygons) control how it displays.",
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
                "polygon in host coordinates, null clears) or clip masks "
                "(masks: list of polygons).", h.modify_reference,
                {"c3d": ["XCLIP"],
                 "ord": ["reference settings", "reference clip boundary",
                         "reference clip mask", "reference levels",
                         "reference presentation"]}),
    CommandSpec("reload_references",
                "Re-read all referenced basefiles from disk on next use.",
                h.reload_references, {"ord": ["reference reload"]}),
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
        self._push_undo(snapshot, spec.name)
        self._redo.clear()
        return self._record(spec.name, params, message, diff, warnings)

    def execute_json(self, call: dict) -> dict:
        """Execute {'command': name, 'params': {...}} (the wire format)."""
        if not isinstance(call, dict) or "command" not in call:
            return self._error("?", "invalid_call",
                               "expected {'command': <name>, 'params': {...}}")
        return self.execute(call["command"], call.get("params") or {})

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
    def replay(cls, baseline: dict, entries: List[dict]) -> "CommandBus":
        """Rebuild a bus by re-executing a journal against its baseline document.
        Deterministic: same baseline + same journal -> same document."""
        bus = cls(Document.from_dict(baseline))
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
