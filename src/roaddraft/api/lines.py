"""Shared human command-line grammar.

One parser serves both human surfaces — the terminal REPL and the web GUI's
command bar — so a session transcript means the same thing everywhere:

    <command> [positional args] [key=value ...]

Values: numbers, 'x,y' points, true/false/null, JSON arrays/objects, strings.
route_line() turns one input line into an executed command/query against a
Session and returns a structured result (never prints).
"""
from __future__ import annotations

import json
import shlex

# Convenience first-token aliases (bus aliases like LINE/PLINE also resolve).
REPL_ALIASES = {
    "line": "draw_line", "pline": "draw_polyline", "polyline": "draw_polyline",
    "arc": "draw_arc", "circle": "draw_circle", "text": "place_text",
    "insert": "insert_block", "table": "place_table", "sheet": "create_sheet",
    "viewport": "create_viewport", "mview": "create_viewport",
    "titleblock": "fill_title_block", "erase": "delete_entities",
    "delete": "delete_entities", "move": "move_entities",
    "mklayer": "create_layer", "block": "define_block",
    "station": "annotate_stationing", "xref": "attach_reference",
    "xdetach": "detach_reference", "xreload": "reload_references",
    "refs": "list_references", "hit": "hit_test",
    # design model (Phase 1)
    "alignment": "create_alignment", "drawalign": "draw_alignment",
    "profile": "create_profile", "label": "place_label",
    "curvetable": "place_curve_table", "landxmlin": "import_landxml",
    "sta2xy": "station_to_xy", "xy2sta": "xy_to_station",
    "design": "get_design_data", "anchor": "resolve_anchor",
    "offset": "draw_offset", "edge": "draw_offset",
    # annotation scales
    "annoscale": "set_annotation_scale", "annoadd": "add_annotation_scale",
    "annodel": "delete_annotation_scale", "annopaper": "set_annotation_defaults",
}

POSITIONAL = {
    "draw_line": ["start", "end"],
    "draw_circle": ["center", "radius"],
    "place_text": ["position", "content"],
    "insert_block": ["block_name", "position"],
    "create_sheet": ["name"],
    "create_layer": ["name"],
    "set_current_layer": ["name"],
    "delete_sheet": ["sheet"],
    "fill_title_block": ["sheet"],
    "attach_reference": ["name", "path"],
    "detach_reference": ["name"],
    "modify_reference": ["name"],
    "create_alignment": ["name"],
    "modify_alignment": ["name"],
    "delete_alignment": ["name"],
    "create_profile": ["name", "alignment"],
    "delete_profile": ["name"],
    "draw_alignment": ["alignment"],
    "place_label": ["anchor", "alignment"],
    "place_curve_table": ["position", "alignment"],
    "import_landxml": ["path"],
    "station_to_xy": ["station", "alignment", "offset"],
    "xy_to_station": ["point", "alignment"],
    "get_design_data": ["kind", "alignment"],
    "resolve_anchor": ["anchor", "alignment"],
    "export_landxml": ["path"],
    "set_annotation_scale": ["scale"],
    "add_annotation_scale": ["scale", "name"],
    "delete_annotation_scale": ["scale"],
}

VARIADIC = {  # commands whose positional args collect into one list param
    "draw_polyline": "vertices",
    "delete_entities": "ids",
    "move_entities": "ids",
    "annotate_stationing": "path_ids",
    "create_alignment": "pis",
    "create_profile": "pvis",
    "draw_offset": "offsets",
}

FOLD_EXTRA_KWARGS = {  # unknown key=value pairs fold into this dict param
    "fill_title_block": "fields",
    "set_meta": "updates",
}

SPATIAL = {"draw_line", "draw_polyline", "draw_arc", "draw_circle", "place_text",
           "insert_block", "place_table", "annotate_stationing",
           "attach_reference", "place_label", "place_curve_table", "resolve_anchor"}

# bare words that map straight to queries
BUILTIN_QUERIES = {
    "state": "get_document_state",
    "layers": "list_layers",
    "styles": "list_text_styles",
    "blocks": "list_blocks",
    "sheets": "list_sheets",
    "journal": "get_journal",
    "alignments": "list_alignments",
    "annoscales": "list_annotation_scales",
}


def parse_value(token: str):
    low = token.lower()
    if low in ("true", "false"):
        return low == "true"
    if low == "null":
        return None
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        pass
    if token[:1] in "[{":
        try:
            return json.loads(token)
        except json.JSONDecodeError:
            return token
    if "," in token:
        parts = token.split(",")
        try:
            return [float(x) for x in parts]
        except ValueError:
            return token
    return token


def _schema_props(name: str):
    from roaddraft.commands.schemas import SCHEMAS
    return SCHEMAS.get(name, {}).get("properties", {})


def build_params(name: str, args: list, current_space: str):
    params = {}
    extras = {}
    unexpected = []
    positional = list(POSITIONAL.get(name, []))
    variadic = VARIADIC.get(name)
    var_list = []
    for token in args:
        if "=" in token and not token[0].isdigit() and token[0] not in "-[{,":
            key, _, raw = token.partition("=")
            value = parse_value(raw)
            if name in FOLD_EXTRA_KWARGS and key not in _schema_props(name):
                extras[key] = value
            else:
                params[key] = value
        elif positional:
            params[positional.pop(0)] = parse_value(token)
        elif variadic:
            var_list.append(parse_value(token))
        else:
            unexpected.append(token)
    if variadic and var_list:
        params.setdefault(variadic, var_list)
    if name in FOLD_EXTRA_KWARGS and extras:
        fold = FOLD_EXTRA_KWARGS[name]
        params.setdefault(fold, {}).update(extras)
    if name in SPATIAL:
        params.setdefault("space", current_space)
    return params, unexpected


def route_line(session, line: str, current_space: str = "model") -> dict:
    """Execute one human command line against a session.

    Returns one of:
      {"kind": "noop", "message": ...}                 nothing to run
      {"kind": "space", "space": ref, "message": ...}  caller switches space
      {"kind": "help", "topics"|[...] | "item": {...}} help payloads
      {"kind": "result", "result": {...}}              command/query result
      {"kind": "error", "message": ...}                parse-level problem
    """
    from roaddraft.api.session import QUERIES

    try:
        tokens = shlex.split(line, posix=True)
    except ValueError as ex:
        return {"kind": "error", "message": f"parse error: {ex}"}
    if not tokens:
        return {"kind": "noop", "message": ""}
    cmd, args = tokens[0], tokens[1:]
    low = cmd.lower()

    if low in ("quit", "exit", "q"):
        return {"kind": "noop", "message": "close the window to end the session"}
    if low in ("render", "rendermodel"):
        return {"kind": "noop",
                "message": "the canvas re-renders automatically after every command"}
    if low == "space":
        if not args:
            return {"kind": "noop", "message": f"current space: {current_space}"}
        ref = args[0]
        if ref == "model":
            return {"kind": "space", "space": "model",
                    "message": "drawing into model space"}
        sheet = session.doc.sheet_by_ref(ref)
        if sheet is not None:
            return {"kind": "space", "space": sheet.id,
                    "message": f"drawing into sheet {sheet.name}"}
        return {"kind": "error",
                "message": f"no space {ref!r}; valid: {session.doc.space_refs()}"}
    if low == "help":
        manifest = session.manifest()
        items = manifest["commands"] + manifest["queries"]
        if not args:
            return {"kind": "help", "topics": [
                {"name": i["name"], "kind": i["kind"],
                 "description": i["description"]} for i in items]}
        wanted = REPL_ALIASES.get(args[0].lower(), args[0])
        for item in items:
            if item["name"].lower() == wanted.lower():
                return {"kind": "help", "item": item}
        return {"kind": "error", "message": f"no command or query named {wanted!r}"}
    if low == "layer" and args:
        return {"kind": "result",
                "result": session.execute("set_current_layer", {"name": args[0]})}
    if low == "entities":
        ref = args[0] if args else current_space
        if ref == "model":
            return {"kind": "result", "result": session.query("get_model_state")}
        return {"kind": "result",
                "result": session.query("get_sheet_state", {"sheet": ref})}
    if low == "extents":
        return {"kind": "result", "result": session.query(
            "get_extents", {"space": args[0] if args else current_space})}
    if low == "dxf":
        return {"kind": "result", "result": session.query(
            "export_dxf", {"path": args[0]} if args else {})}
    if low == "pdf":
        return {"kind": "result", "result": session.query(
            "export_pdf", {"path": args[0]} if args else {})}
    if low == "landxml":
        return {"kind": "result", "result": session.query(
            "export_landxml", {"path": args[0]} if args else {})}
    if low == "save":
        if not args:
            return {"kind": "error", "message": "usage: save PATH"}
        return {"kind": "result",
                "result": session.query("save_document", {"path": args[0]})}
    if low == "journal" and args:
        return {"kind": "result",
                "result": session.query("save_journal", {"path": args[0]})}
    if low == "state" and args and args[0] == "full":
        return {"kind": "result",
                "result": session.query("get_document_state", {"detail": "full"})}
    if low in BUILTIN_QUERIES:
        return {"kind": "result", "result": session.query(BUILTIN_QUERIES[low])}

    name = REPL_ALIASES.get(low, cmd)
    spec = session.bus.resolve(name)
    canonical = spec.name if spec else name
    params, unexpected = build_params(canonical, args, current_space)
    if unexpected:
        return {"kind": "error",
                "message": f"unexpected arguments {unexpected}; "
                           f"try: help {canonical}"}
    if canonical in QUERIES:
        return {"kind": "result", "result": session.query(canonical, params)}
    return {"kind": "result", "result": session.execute(canonical, params)}
