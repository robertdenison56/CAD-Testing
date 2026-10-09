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
import re
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
    "print": "print_pdf", "plot": "print_pdf",
    # design model (Phase 1)
    "alignment": "create_alignment", "drawalign": "draw_alignment",
    "profile": "create_profile", "label": "place_label",
    "curvetable": "place_curve_table", "landxmlin": "import_landxml",
    "sta2xy": "station_to_xy", "xy2sta": "xy_to_station",
    "design": "get_design_data", "anchor": "resolve_anchor",
    "offset": "draw_offset", "edge": "draw_offset", "callout": "place_callout",
    "dim": "place_dimension", "dist": "measure", "di": "measure",
    # coordinate geometry and editing
    "cogo": "draw_traverse", "trav": "draw_traverse", "fillet": "fillet",
    "parallel": "offset_entity", "offsetent": "offset_entity",
    "keypoints": "key_points", "kp": "key_points", "snap": "snap",
    "trim": "trim", "extend": "extend", "break": "break_entity",
    "join": "join_entities", "explode": "explode_entities", "chamfer": "chamfer",
    "lengthen": "lengthen", "copy": "copy_entities", "rotate": "rotate_entities",
    "mirror": "mirror_entities", "scale": "scale_entities", "array": "array_entities",
    "point": "create_points", "points": "create_points",
    "pointtable": "place_point_table", "labelseg": "label_segments",
    "linetable": "label_segments", "so": "draw_station_offset",
    "along": "place_along", "divide": "place_along", "hatch": "hatch",
    "area": "area", "list": "get_entity", "props": "get_entity",
    # annotation scales
    "annoscale": "set_annotation_scale", "annoadd": "add_annotation_scale",
    "annodel": "delete_annotation_scale", "annopaper": "set_annotation_defaults",
}

POSITIONAL = {
    "draw_line": ["start", "end"],
    "place_dimension": ["kind"],
    "measure": ["from", "to"],
    "draw_circle": ["center", "radius"],
    "place_text": ["position", "content"],
    "insert_block": ["block_name", "position"],
    "create_sheet": ["name"],
    "print_pdf": ["space"],
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
    "draw_traverse": ["start"],
    "traverse": ["start"],
    "snap": ["point"],
    "break_entity": ["id", "at", "to"],
    "place_point_table": ["position"],
    "place_along": ["path"],
    "get_entity": ["id"],
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
    "draw_traverse": "legs",
    "traverse": "legs",
    "key_points": "ids",
    "join_entities": "ids",
    "explode_entities": "ids",
    "array_entities": "ids",
    "label_segments": "ids",
    "draw_station_offset": "points",
}

FOLD_EXTRA_KWARGS = {  # unknown key=value pairs fold into this dict param
    "fill_title_block": "fields",
    "set_meta": "updates",
}

SPATIAL = {"draw_line", "draw_polyline", "draw_arc", "draw_circle", "place_text",
           "place_callout", "place_dimension", "draw_traverse", "snap",
           "insert_block", "place_table", "annotate_stationing",
           "attach_reference", "place_label", "place_curve_table", "resolve_anchor",
           "hatch", "create_points", "place_point_table", "label_segments", "area"}

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


#: An entity id as the commands print them: LN-001, or DESIGN:LN-004 for an
#: element of a reference.
ENTITY_ID = re.compile(r"^(?:[^:\s]+:)*[A-Z]{2}-\d+$")
SIDES = ("left", "right")


def _is_kv(token: str) -> bool:
    key, eq, _raw = token.partition("=")
    return bool(eq) and key.isidentifier()


def resolve_verb(low: str, args: list) -> str:
    """The command a typed verb means. ``offset`` is two commands: with
    alignment offsets (``offset 12L 12R``) it draws an alignment's edges, and
    with an entity first (``offset LN-001 12 left``) it copies that entity
    parallel, as AutoCAD's OFFSET does."""
    if low in ("offset", "o") and args and ENTITY_ID.match(args[0]):
        return "offset_entity"
    if low == "o":
        return "offset_entity"
    return REPL_ALIASES.get(low, low)


def _offset_entity_params(args: list):
    """``offset LN-001 [AR-002 ...] 12 left`` / ``12L 12R`` / key=value."""
    params, ids, numbers, unexpected = {}, [], [], []
    side = None
    for token in args:
        if _is_kv(token):
            key, _, raw = token.partition("=")
            params[key] = parse_value(raw)
        elif ENTITY_ID.match(token):
            ids.append(token)
        elif token.lower() in SIDES:
            side = token.lower()
        else:
            value = parse_value(token)
            if isinstance(value, (int, float)) or re.match(r"^\d+(\.\d*)?[LlRr]$", token):
                numbers.append(value)
            else:
                unexpected.append(token)
    if ids:
        params.setdefault("ids", ids)
    if side is not None:
        params["side"] = side
        if numbers:
            params.setdefault("distance", abs(float(numbers[0])))
            unexpected += [str(n) for n in numbers[1:]]
    elif numbers:
        params.setdefault("offsets", numbers)
    return params, unexpected


def _fillet_params(args: list):
    """``fillet LN-001 LN-002 50`` / key=value."""
    params, ids, unexpected = {}, [], []
    for token in args:
        if _is_kv(token):
            key, _, raw = token.partition("=")
            params[key] = parse_value(raw)
        elif ENTITY_ID.match(token):
            ids.append(token)
        elif isinstance(parse_value(token), (int, float)) and "radius" not in params:
            params["radius"] = parse_value(token)
        else:
            unexpected.append(token)
    if ids:
        params.setdefault("ids", ids)
    return params, unexpected


def _is_point(value) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(
        isinstance(v, (int, float)) for v in value)


def _ids_value(raw: str):
    """``CI-001`` / ``CI-001,LN-002`` / a JSON list -> a list of ids."""
    value = parse_value(raw)
    if isinstance(value, list):
        return value
    return [part for part in str(raw).split(",") if part]


LIST_KEYS = {"boundaries", "boundary", "ids", "from_entities", "boundary_layers"}


def _split(args: list):
    """``(key=value params, entity ids, points, numbers, words)`` of a line,
    in order of appearance within each kind."""
    params, ids, points, numbers, words = {}, [], [], [], []
    for token in args:
        if _is_kv(token):
            key, _, raw = token.partition("=")
            params[key] = _ids_value(raw) if key in LIST_KEYS else parse_value(raw)
        elif ENTITY_ID.match(token):
            ids.append(token)
        else:
            value = parse_value(token)
            if _is_point(value):
                points.append(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                numbers.append(value)
            else:
                words.append(token)
    return params, ids, points, numbers, words


def _trim_params(args: list):
    """``trim LN-005 2986,2399 [keep] [LN-006 3014,2399 ...] boundaries=CI-001``:
    each id takes the point after it -- the part to cut away, or with the
    word keep the part to keep."""
    params, targets, unexpected = {}, [], []
    keep = False
    for token in args:
        if _is_kv(token):
            key, _, raw = token.partition("=")
            params[key] = _ids_value(raw) if key in LIST_KEYS else parse_value(raw)
        elif ENTITY_ID.match(token):
            targets.append({"id": token})
        elif token.lower() == "keep":
            keep = True
        elif token.lower() in ("start", "end") and targets:
            targets[-1]["end"] = token.lower()
        else:
            value = parse_value(token)
            if _is_point(value) and targets and not ({"at", "keep"} & set(targets[-1])):
                targets[-1]["keep" if keep else "at"] = value
                keep = False
            else:
                unexpected.append(token)
    if targets:
        params.setdefault("targets", targets)
    return params, unexpected


def _extend_params(args: list):
    params, unexpected = _trim_params(args)
    for t in params.get("targets", []):
        if "keep" in t:
            unexpected.append("keep")
    return params, unexpected


def _chamfer_params(args: list):
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("ids", ids)
    for key, value in zip(("distance", "distance2"), numbers):
        params.setdefault(key, value)
    return params, [str(v) for v in points] + [str(v) for v in numbers[2:]] + words


def _lengthen_params(args: list):
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("id", ids[0])
    ends = [w.lower() for w in words if w.lower() in ("start", "end")]
    if ends:
        params.setdefault("end", ends[0])
    if numbers and not {"delta", "total", "percent", "to"} & set(params):
        params["delta"] = numbers[0]
    if points and "to" not in params:
        params["to"] = points[0]
    rest = [w for w in words if w.lower() not in ("start", "end")] + ids[1:]
    return params, rest


def _copy_params(args: list):
    """``copy LN-001 LN-002 20,0`` (a displacement) or ``... 0,0 20,0`` (from,
    to) [count=3]."""
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("ids", ids)
    if len(points) == 1:
        params.setdefault("delta", points[0])
    elif len(points) >= 2:
        params.setdefault("from", points[0])
        params.setdefault("to", points[1])
    if numbers:
        params.setdefault("count", int(numbers[0]))
    return params, [str(p) for p in points[2:]] + words


def _rotate_params(args: list):
    """``rotate LN-001 0,0 90 [copy=true]``."""
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("ids", ids)
    if points:
        params.setdefault("base", points[0])
    if numbers:
        params.setdefault("angle", numbers[0])
    elif words and "angle" not in params and "to_direction" not in params:
        params["angle"] = " ".join(words)  # '30 CW', DMS text
        words = []
    return params, words


def _mirror_params(args: list):
    """``mirror LN-001 0,0 0,10 [keep_original=false]``."""
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("ids", ids)
    if len(points) >= 2:
        params.setdefault("line", points[:2])
    return params, [str(n) for n in numbers] + words


def _scale_params(args: list):
    """``scale LN-001 0,0 0.5``."""
    params, ids, points, numbers, words = _split(args)
    if ids:
        params.setdefault("ids", ids)
    if points:
        params.setdefault("base", points[0])
    if numbers:
        params.setdefault("factor", numbers[0])
    return params, words


def _points_params(args: list):
    """``point 1500,2000 [1534,2059 ...] description=MON``."""
    params, ids, points, numbers, words = _split(args)
    if points:
        params.setdefault("points", [{"point": q} for q in points])
    if ids:
        params.setdefault("from_entities", ids)
    return params, [str(n) for n in numbers] + words


def _hatch_params(args: list):
    """``hatch 1700,988 ANSI31`` (a point inside) or ``hatch PL-002 CI-001 SOLID``."""
    params, ids, points, numbers, words = _split(args)
    if points:
        if len(points) >= 3:
            params.setdefault("points", points)
        else:
            params.setdefault("at", points[0])
    if ids:
        params.setdefault("boundary", ids)
    if words:
        params.setdefault("pattern", words[0])
        words = words[1:]
    if numbers:
        params.setdefault("scale", numbers[0])
    return params, words


def _area_params(args: list):
    params, ids, points, numbers, words = _split(args)
    if points:
        if len(points) >= 3:
            params.setdefault("points", points)
        else:
            params.setdefault("at", points[0])
    if ids:
        params.setdefault("ids", ids)
    return params, [str(n) for n in numbers] + words


SPECIAL = {"offset_entity": _offset_entity_params, "fillet": _fillet_params,
           "trim": _trim_params, "extend": _extend_params, "chamfer": _chamfer_params,
           "lengthen": _lengthen_params, "copy_entities": _copy_params,
           "rotate_entities": _rotate_params, "mirror_entities": _mirror_params,
           "scale_entities": _scale_params, "create_points": _points_params,
           "hatch": _hatch_params, "area": _area_params}


def build_params(name: str, args: list, current_space: str):
    if name in SPECIAL:
        params, unexpected = SPECIAL[name](args)
        if name in SPATIAL and not (name == "area" and "ids" in params):
            params.setdefault("space", current_space)
        return params, unexpected
    params = {}
    extras = {}
    unexpected = []
    positional = list(POSITIONAL.get(name, []))
    variadic = VARIADIC.get(name)
    var_list = []
    for token in args:
        if "=" in token and not token[0].isdigit() and token[0] not in "-[{," \
                and _is_kv(token):
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


def print_params(args: list, current_space: str):
    """Params for a ``print`` line. With nothing said about what to print it
    prints the space you are in; ``print all`` prints every sheet."""
    params, unexpected = build_params("print_pdf", args, current_space)
    if params.get("space") in ("all", "sheets"):
        params.pop("space")
    elif "space" not in params and "sheets" not in params:
        params["space"] = current_space
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
    if low in ("print", "plot"):
        params, unexpected = print_params(args, current_space)
        if unexpected:
            return {"kind": "error",
                    "message": f"unexpected arguments {unexpected}; "
                               f"try: help print_pdf"}
        return {"kind": "result", "result": session.query("print_pdf", params)}
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

    name = resolve_verb(low, args)
    if name == low and low not in REPL_ALIASES:
        name = cmd
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
