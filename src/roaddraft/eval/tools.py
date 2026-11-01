"""What an episode lets the agent call (eval plan section 4.1).

The whitelist is the D1 neutral surface: the drafting commands and queries
a plan-sheet task needs, nothing that saves, exports, imports a design, edits
the design model or reads the journal.  ``place_text``, ``place_table`` and
the raw ``draw_*`` commands stay available on purpose -- the benchmark should
show whether a model takes the semantic path when the coordinate path
exists.  ``create_alignment`` is shown only when creating the design is the
task (scope ``design``); ``render_sheet`` / ``render_model`` only in the
self-correct and vision modes.  Three tools are the harness's own:
``get_task_brief``, ``run_check`` and ``submit``.

Tool definitions come straight from the session manifest: ``params_schema``
is the input schema (every schema is a closed object with a ``required``
list), the description carries the command's example.  The order is by name
so a cached prompt prefix is stable.
"""
from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional, Set, Tuple


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

HARNESS_DEFINITIONS = {
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
    if "design" in set(scope):
        names |= DESIGN_COMMANDS
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
    for name in HARNESS_TOOLS:
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


__all__ = ["MODES", "DIALECTS", "COMMANDS", "DESIGN_COMMANDS", "QUERIES", "RENDER_QUERIES",
           "HARNESS_TOOLS", "allowed_names", "is_allowed", "tool_definitions", "shape_params"]
