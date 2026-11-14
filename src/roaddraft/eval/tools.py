"""What an episode lets the agent call (eval plan section 4.1).

The whitelist is the D1 neutral surface: the drafting commands and queries
a plan-sheet task needs, nothing that saves, exports, imports a design, edits
the design model or reads the journal.  ``place_text``, ``place_table`` and
the raw ``draw_*`` commands stay available on purpose -- the benchmark should
show whether a model takes the semantic path when the coordinate path
exists.  ``create_alignment`` is shown only when creating the design is the
task (scope ``design``); ``render_sheet`` / ``render_model`` only in the
self-correct and vision modes.  Three tools are the harness's own:
``get_task_brief``, ``run_check`` and ``submit``.  A fourth, ``open_document``,
is shown with ``reload_references`` only on a revised task whose design the
drafter changes in a base drawing (``BASE_COMMANDS``).

Tool definitions come straight from the session manifest: ``params_schema``
is the input schema (every schema is a closed object with a ``required``
list), the description carries the command's example.  The order is by name
so a cached prompt prefix is stable.
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Set, Tuple

from roaddraft.tasks.types import BASE_SCOPE


MODES = ("single", "self_correct", "vision")
#: the tools always carry their own names: no episode renames them (Robert, 2026-10-30)
DIALECTS = ("neutral",)

#: commands every task may call
COMMANDS = frozenset({
    "set_meta",
    "create_layer", "modify_layer", "set_current_layer", "create_text_style",
    "set_annotation_scale", "add_annotation_scale", "set_annotation_defaults",
    "draw_alignment", "annotate_stationing", "place_label", "place_curve_table",
    "draw_offset", "draw_station_offset", "place_dimension", "place_callout",
    "label_segments", "place_along", "attach_reference",
    "create_sheet", "create_viewport", "modify_viewport", "delete_sheet", "delete_viewport",
    "insert_block", "define_block", "fill_title_block",
    "place_text", "place_table", "draw_line", "draw_arc", "draw_polyline", "draw_circle",
    "offset_entity", "trim", "extend", "fillet", "break_entity", "join_entities",
    "copy_entities", "move_entities", "rotate_entities", "mirror_entities",
    "modify_entity", "delete_entities", "undo", "redo",
})
#: commands shown only when the task asks for the design (scope ``design``)
DESIGN_COMMANDS = frozenset({"create_alignment"})
#: what a revised task's truth carries in its scope beside its groups (the generator's
#: revision dial, ``tasks.revise``, 2026-11-12, Robert: "Yes, revision only"); no check grades
#: it (the verifier reads only ``tasks.types.GROUPS``), it only opens ``REVISION_COMMANDS``
REVISION_SCOPE = "revision"
#: commands shown only on a revised task: changing a line's design, and bringing what was
#: lettered from it up to date.  No other task's tool list, nor its digest, has them
REVISION_COMMANDS = frozenset({"modify_alignment", "update_labels"})
#: tools shown only on a revised task whose design the drafter changes in the base drawing
#: the sheet file references (its scope carries ``BASE_SCOPE`` beside the revision mark;
#: ``tasks.revise.BASE_KINDS``, 2026-11-13, Robert: "allow them, in the pin's cut"): opening
#: another document of the task, and reading a base drawing again once it has changed.
#: ``open_document`` is the harness's own (``DOCUMENT_TOOLS``): an episode holds the document
#: it was handed and switches to the base drawing and back; ``reload_references`` is the
#: engine's command.  No other task's tool list, nor its digest, has them: neither of the
#: two earlier revision flavours carries ``BASE_SCOPE``
BASE_COMMANDS = frozenset({"open_document", "reload_references"})
#: queries every task may call
QUERIES = frozenset({
    "list_alignments", "get_design_data", "station_to_xy", "xy_to_station", "resolve_anchor",
    "get_document_state", "get_model_state", "get_sheet_state", "get_entity", "get_extents",
    "find_entities", "list_layers", "list_sheets", "list_blocks", "list_text_styles",
    "list_references", "list_annotation_scales", "model_to_sheet", "sheet_to_model",
    "measure", "key_points", "snap", "hit_test", "point_on_entity", "area",
})
#: queries shown in the self-correct and vision modes
RENDER_QUERIES = frozenset({"render_sheet", "render_model"})
HARNESS_TOOLS = ("get_task_brief", "run_check", "submit")
#: the harness's tools that are shown only where a scope opens them (``BASE_COMMANDS``)
DOCUMENT_TOOLS = ("open_document",)

HARNESS_DEFINITIONS = {
    "open_document": {
        "description": ("Open another document of this task as the working document: the base "
                        "drawing a sheet file references (list_references gives its path), or "
                        "the file you were handed again (get_document_state names the open "
                        "file, 'document'). Every tool then reads and changes the open "
                        "document, and each change is saved to its file as it is made. A sheet "
                        "file can still hold the copy of a base drawing it read earlier: back in "
                        "it, call reload_references to read the base drawing as it now stands. "
                        "The file you were handed is the one that gets graded, so go back to it "
                        "before you submit."),
        "input_schema": {"type": "object",
                         "properties": {"path": {"type": "string", "minLength": 1,
                                                 "description": "the document's path, relative "
                                                                "to the folder of the file you "
                                                                "were handed"}},
                         "required": ["path"], "additionalProperties": False}},
    "get_task_brief": {
        "description": "The task text again: the rules and the request, as first given.",
        "input_schema": {"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False}},
    "run_check": {
        "description": ("Grade the document as it stands against the task: each check in "
                        "scope with its status (pass, partial, fail) and up to five findings, "
                        "never the expected values. A limited number of uses per episode; "
                        "each use counts as a step."),
        "input_schema": {"type": "object", "properties": {}, "required": [],
                         "additionalProperties": False}},
    "submit": {
        "description": "Finish the task. The document as it stands is what gets graded.",
        "input_schema": {"type": "object",
                         "properties": {"note": {"type": "string",
                                                 "description": "optional: what was done"}},
                         "required": [], "additionalProperties": False}},
}


def allowed_names(mode: str, scope: Iterable[str] = ()) -> Set[str]:
    """Every tool name an episode in ``mode`` on a task with ``scope`` may call."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; modes: {', '.join(MODES)}")
    names = set(COMMANDS) | set(QUERIES) | set(HARNESS_TOOLS)
    # a revision made in the base drawing has the design in its scope to be graded, not to
    # be created: a line of the same name made in the sheet file would stand in front of
    # the base drawing's, and everything lettered through the reference would lose for it
    in_base = {REVISION_SCOPE, BASE_SCOPE} <= set(scope)
    if "design" in set(scope) and not in_base:
        names |= DESIGN_COMMANDS
    if REVISION_SCOPE in set(scope):
        names |= REVISION_COMMANDS
        if in_base:
            names |= BASE_COMMANDS
    if mode != "single":
        names |= RENDER_QUERIES
    else:
        names.discard("run_check")
    return names


def is_allowed(name: str, mode: str, scope: Iterable[str] = ()) -> bool:
    return name in allowed_names(mode, scope)


def _describe(entry: dict) -> str:
    text = entry.get("description") or entry["name"]
    example = entry.get("example")
    if example:
        text = f"{text} Example: {json.dumps(example, separators=(',', ':'))}"
    return text


def tool_definitions(manifest: dict, mode: str, scope: Iterable[str] = ()) -> List[dict]:
    """The tools an agent is shown, sorted by name: ``{"name", "kind",
    "description", "input_schema"}``; ``kind`` is command, query or harness."""
    allowed = allowed_names(mode, scope)
    defs: List[dict] = []
    for kind in ("commands", "queries"):
        for entry in manifest.get(kind, []):
            if entry["name"] in allowed:
                defs.append({"name": entry["name"], "kind": entry.get("kind", kind[:-1]),
                             "description": _describe(entry),
                             "input_schema": entry["params_schema"]})
    for name in HARNESS_TOOLS + DOCUMENT_TOOLS:
        if name in allowed:
            defs.append({"name": name, "kind": "harness", **HARNESS_DEFINITIONS[name]})
    return sorted(defs, key=lambda d: d["name"])


def shape_params(name: str, params: Optional[dict]) -> Tuple[dict, List[str]]:
    """The parameters as the harness sends them, and what it changed: the
    ``anchor`` of a ``modify_entity`` change is stripped, since provenance is
    the engine's to stamp and not the agent's to write."""
    params = dict(params or {})
    notes: List[str] = []
    if name == "modify_entity" and isinstance(params.get("changes"), dict):
        changes = dict(params["changes"])
        if "anchor" in changes:
            changes.pop("anchor")
            notes.append("modify_entity: 'anchor' is set by the engine and was removed from changes")
            params["changes"] = changes
    return params, notes


SCALAR_TYPES = ("string", "number", "integer", "boolean")


def _takes_one_value(prop) -> bool:
    """Whether a property's schema takes a single value and never a list."""
    if not isinstance(prop, dict):
        return False
    t = prop.get("type")
    types = [t] if isinstance(t, str) else list(t or [])
    if any(x not in SCALAR_TYPES for x in types):
        return False
    if types:
        return True
    enum = prop.get("enum")
    return bool(enum) and all(not isinstance(v, (list, dict)) for v in enum)


def repair_params(params: Optional[dict], schema: Optional[dict]) -> Tuple[dict, List[str]]:
    """The parameters with a one-item list read as its one value wherever the
    tool's schema takes a single value, and a note for each (e3-v3,
    2026-11-03).  LM Studio's Gemma 4 template sent enum values that way --
    ``kind: ["curves"]`` -- in 465 of the 1,800 calls of the Q8_0 file's
    d1-test run, and the same weights under vLLM in none of 1,312, so the
    list is the serving stack's and not the model's.  The value still goes
    through validation as sent; a list of two, a list where the schema takes
    one, and a nested list are left alone.  The note reaches the model in the
    result's warnings, and the call counts as repaired, not invalid."""
    params = dict(params or {})
    repairs: List[str] = []
    props = (schema or {}).get("properties") or {}
    for key, value in list(params.items()):
        if (isinstance(value, list) and len(value) == 1 and _takes_one_value(props.get(key))
                and isinstance(value[0], (str, int, float, bool))):
            params[key] = value[0]
            repairs.append(f"{key}: {json.dumps(value)} was read as {json.dumps(value[0])} "
                           "(a one-item list where the schema takes one value)")
    return params, repairs


__all__ = ["MODES", "DIALECTS", "COMMANDS", "DESIGN_COMMANDS", "REVISION_SCOPE", "REVISION_COMMANDS",
           "BASE_SCOPE", "BASE_COMMANDS", "QUERIES", "RENDER_QUERIES",
           "HARNESS_TOOLS", "DOCUMENT_TOOLS", "allowed_names", "is_allowed", "tool_definitions",
           "shape_params", "repair_params"]
