"""JSON Schemas for every command's parameters.

These schemas are the contract of the machine-facing tool surface: they are
served verbatim in the tool manifest, used to validate every call, and echoed
back in teaching errors when a call is invalid.
"""
from __future__ import annotations

from roaddraft.commands.design_schemas import DESIGN_EXAMPLES, DESIGN_SCHEMAS, STATION
from roaddraft.document.document import LINETYPES
from roaddraft.document.sheets import SHEET_SIZES

POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
         "description": "[x, y]"}
NUM = {"type": "number"}
POS = {"type": "number", "exclusiveMinimum": 0}
STR = {"type": "string"}
NSTR = {"type": "string", "minLength": 1}
SPACE = {"type": "string", "minLength": 1,
         "description": "'model' (design space, US survey feet) or a sheet id/name "
                        "(paper space, inches), e.g. 'SH-001' or 'C-101'"}
IDS = {"type": "array", "items": NSTR, "minItems": 1, "description": "entity ids"}
SCALAR = {"type": ["string", "number", "boolean"]}
LINETYPE = {"type": "string", "enum": list(LINETYPES)}
HALIGN = {"type": "string", "enum": ["left", "center", "right"]}
VALIGN = {"type": "string", "enum": ["bottom", "middle", "top"]}
COLOR = {"type": "string",
         "description": "named CAD color (black, red, yellow, green, cyan, blue, "
                        "magenta, gray, white) or '#RRGGBB'"}
POLYGON = {"type": "array", "items": POINT, "minItems": 3,
           "description": "polygon: at least 3 [x, y] points, implicitly closed"}
POLYGON_CLIP = {**POLYGON,
                "description": "clip boundary polygon in host coordinates; only "
                               "basefile geometry inside it displays"}


def obj(props, required=(), extra=False):
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": extra}


_ENTITY_COMMON = {
    "space": SPACE,
    "layer": {**NSTR, "description": "layer name; defaults to the current layer"},
    "color": {**COLOR, "description": "override color; omit for ByLayer"},
    "linetype": {**LINETYPE, "description": "override linetype; omit for ByLayer"},
}

SCHEMAS = {
    "set_meta": obj(
        {"updates": {"type": "object", "minProperties": 1,
                     "additionalProperties": SCALAR,
                     "description": "keys merged into document meta "
                                    "(project_name, description, ...)"}},
        ["updates"]),
    "create_layer": obj(
        {"name": NSTR, "color": COLOR, "linetype": LINETYPE,
         "lineweight_mm": {**POS, "description": "plotted lineweight in mm"},
         "description": STR},
        ["name"]),
    "modify_layer": obj(
        {"name": NSTR,
         "changes": {"type": "object", "minProperties": 1,
                     "description": "any of: color, linetype, lineweight_mm, "
                                    "description, visible"}},
        ["name", "changes"]),
    "set_current_layer": obj({"name": NSTR}, ["name"]),
    "create_text_style": obj(
        {"name": NSTR, "font": STR, "width_factor": POS, "default_height": POS},
        ["name"]),
    "define_block": obj(
        {"name": NSTR,
         "base_point": POINT,
         "entities": {"type": "array", "minItems": 1, "items": {"type": "object"},
                      "description": "entity dicts (types: line, polyline, arc, "
                                     "circle, text) in block-local coordinates"},
         "description": STR},
        ["name", "entities"]),
    "draw_line": obj({**_ENTITY_COMMON, "start": POINT, "end": POINT},
                     ["space", "start", "end"]),
    "draw_polyline": obj(
        {**_ENTITY_COMMON,
         "vertices": {"type": "array", "items": POINT, "minItems": 2},
         "closed": {"type": "boolean"}},
        ["space", "vertices"]),
    "draw_arc": obj(
        {**_ENTITY_COMMON, "center": POINT, "radius": POS,
         "start_angle_deg": {**NUM, "description": "degrees CCW from +X"},
         "end_angle_deg": {**NUM, "description": "arc runs CCW from start to end"}},
        ["space", "center", "radius", "start_angle_deg", "end_angle_deg"]),
    "draw_circle": obj({**_ENTITY_COMMON, "center": POINT, "radius": POS},
                       ["space", "center", "radius"]),
    "place_text": obj(
        {**_ENTITY_COMMON, "position": POINT, "content": NSTR,
         "height": {**POS, "description": "text height in space units "
                                          "(feet in model, inches on sheets)"},
         "style": NSTR, "rotation_deg": NUM, "halign": HALIGN, "valign": VALIGN},
        ["space", "position", "content", "height"]),
    "place_callout": obj(
        {**_ENTITY_COMMON,
         "target": {**POINT, "description": "an explicit point for the leader to point "
                                            "at; prefer target_entity, which cannot "
                                            "miss"},
         "target_entity": {**NSTR,
                           "description": "what to point at, by id (find_entities and "
                                          "hit_test return them; reference elements are "
                                          "'DESIGN:LN-004'). The engine computes a point "
                                          "on it, so a curve is aimed at correctly. Give "
                                          "exactly one of target / target_entity."},
         "at": {"description": "where along target_entity: start|mid|end or a fraction "
                               "0-1 (default mid)"},
         "position": {**POINT, "description": "where the text sits, clear of the geometry"},
         "content": NSTR,
         "height": {**POS, "description": "text height in space units (feet in model, "
                                          "inches on sheets); defaults to the annotation "
                                          "scale in model space, 0.10 in on a sheet"},
         "landing": {"type": "number", "minimum": 0,
                     "description": "horizontal shoulder at the text (default 2.5 x "
                                    "height; 0 for none)"},
         "arrow": {"type": "boolean", "description": "arrowhead at the target (default true)"},
         "arrow_size": {**POS, "description": "arrowhead length (default: the text height)"},
         "style": NSTR},
        ["space", "position", "content"]),
    "insert_block": obj(
        {**_ENTITY_COMMON, "block_name": NSTR, "position": POINT,
         "scale": POS, "rotation_deg": NUM},
        ["space", "block_name", "position"]),
    "place_table": obj(
        {**_ENTITY_COMMON,
         "position": {**POINT, "description": "top-left corner; table grows downward"},
         "title": STR,
         "columns": {"type": "array", "minItems": 1,
                     "items": obj({"header": STR, "width": POS}, ["header", "width"])},
         "rows": {"type": "array",
                  "items": {"type": "array", "items": {"type": ["string", "number"]}}},
         "text_height": POS, "style": NSTR},
        ["space", "position", "columns", "rows"]),
    "move_entities": obj({"ids": IDS, "delta": {**POINT, "description": "[dx, dy]"}},
                         ["ids", "delta"]),
    "modify_entity": obj(
        {"id": NSTR,
         "changes": {"type": "object", "minProperties": 1,
                     "description": "entity fields to change (not id/type)"}},
        ["id", "changes"]),
    "delete_entities": obj({"ids": IDS}, ["ids"]),
    "create_sheet": obj(
        {"name": {**NSTR, "description": "sheet name, e.g. 'C-101'"},
         "size": {"type": "string", "enum": sorted(SHEET_SIZES)},
         "width_in": POS, "height_in": POS,
         "title_block_fields": {"type": "object", "additionalProperties": SCALAR}},
        ["name"]),
    "delete_sheet": obj({"sheet": NSTR}, ["sheet"]),
    "create_viewport": obj(
        {"sheet": NSTR,
         "center_paper": {**POINT, "description": "viewport center on the sheet, inches"},
         "width_in": POS, "height_in": POS,
         "model_center": {**POINT, "description": "model-space point (feet) shown at "
                                                  "the viewport center"},
         "feet_per_inch": {**POS, "description": "plot scale: 1\"=50' -> 50"},
         "rotation_deg": {**NUM, "description": "view twist: model appears rotated "
                                                "CCW by this angle on the sheet"}},
        ["sheet", "center_paper", "width_in", "height_in", "model_center",
         "feet_per_inch"]),
    "modify_viewport": obj(
        {"sheet": NSTR, "viewport_id": NSTR,
         "changes": {"type": "object", "minProperties": 1,
                     "description": "any of: center_paper, width_in, height_in, "
                                    "model_center, feet_per_inch, rotation_deg"}},
        ["sheet", "viewport_id", "changes"]),
    "delete_viewport": obj({"sheet": NSTR, "viewport_id": NSTR},
                           ["sheet", "viewport_id"]),
    "fill_title_block": obj(
        {"sheet": NSTR,
         "fields": {"type": "object", "minProperties": 1,
                    "additionalProperties": SCALAR,
                    "description": "standard keys: project, agency, sheet_title, "
                                   "sheet_number, total_sheets, designed_by, "
                                   "drawn_by, checked_by, date, scale"}},
        ["sheet", "fields"]),
    "annotate_stationing": obj(
        {"space": SPACE,
         "path_ids": {**IDS, "description": "line/polyline/arc entity ids forming "
                                            "the centerline, in order along it "
                                            "(entity-chain mode)"},
         "alignment": {**NSTR, "description": "design-model alignment name: true "
                                              "stations, equations, and anchored "
                                              "output (alternative to path_ids)"},
         "begin_station": {**NUM, "description": "station value (feet) at the "
                                                 "start of the first element "
                                                 "(entity-chain mode only)"},
         "station_range": {"type": "array", "items": STATION, "minItems": 2,
                           "maxItems": 2,
                           "description": "alignment mode: only annotate between "
                                          "these display stations"},
         "include_equations": {"type": "boolean",
                               "description": "alignment mode: label station "
                                              "equations (default true)"},
         "interval": {**POS, "description": "tick spacing in feet (default 100)"},
         "tick_half_len": {**POS, "description": "tick half-length each side of "
                                                 "the path (default 10 ft, or the "
                                                 "annotation scale x 0.20 in)"},
         "text_height": {**POS, "description": "label height (default 8 ft, or the "
                                               "annotation scale x 0.10 in)"},
         "label_offset": {**NUM, "description": "label offset left of the path "
                                                "(default 16 ft, or the annotation "
                                                "scale x 0.32 in)"},
         "layer": {**NSTR, "description": "layer for ticks; default current"},
         "label_layer": {**NSTR, "description": "layer for labels; default same "
                                                "as ticks"},
         "include_pc_pt": {"type": "boolean",
                           "description": "label PC/PT/PCC at tangent-curve "
                                          "junctions (default true)"},
         "connect_tolerance": {**POS, "description": "max gap between path "
                                                     "elements (default 1 ft)"}},
        ["space"]),
    "attach_reference": obj(
        {"name": {**NSTR, "description": "reference name, e.g. 'SURVEY'"},
         "path": {**NSTR, "description": "path to a RoadDraft document "
                                         "(.rdraft or .rdoc.json, saved with "
                                         "save_document); a relative path "
                                         "resolves against the host document's "
                                         "folder, then the working directory"},
         "space": SPACE,
         "offset": {**POINT, "description": "placement offset in host units"},
         "rotation_deg": NUM, "scale": POS,
         "visible": {"type": "boolean"},
         "true_scale": {"type": "boolean",
                        "description": "convert the basefile's model_units "
                                       "into the host space's units before "
                                       "placement (default true; MicroStation "
                                       "true scale)"},
         "levels_off": {"type": "array", "items": NSTR,
                        "description": "basefile layers (levels) hidden in "
                                       "this attachment only"},
         "symbology": {"type": "object",
                       "description": "display overrides for the whole "
                                      "attachment: color, linetype, "
                                      "lineweight_mm, gray (true = gray-out)"},
         "clip": POLYGON_CLIP,
         "masks": {"type": "array", "items": POLYGON,
                   "description": "clip mask polygons in host coordinates; "
                                  "geometry inside a mask is hidden"},
         "model": {**NSTR, "description": "which basefile model to attach: "
                                          "'model' (its design model, default) "
                                          "or one of its sheet names/ids "
                                          "(paper inches, border and title "
                                          "block included)"},
         "nest_depth": {"type": "integer", "minimum": 0, "maximum": 5,
                        "description": "live nesting: also display the "
                                       "basefile's own references this many "
                                       "levels deep (default 0 = none)"}},
        ["name", "path"]),
    "detach_reference": obj({"name": {**NSTR, "description": "reference name "
                                                             "or id"}}, ["name"]),
    "modify_reference": obj(
        {"name": NSTR,
         "changes": {"type": "object", "minProperties": 1,
                     "description": "any of: path, offset, rotation_deg, scale, "
                                    "visible, true_scale, levels_off (list of "
                                    "basefile layer names), symbology "
                                    "({color, linetype, lineweight_mm, gray}), "
                                    "clip (polygon in host coordinates, or "
                                    "null to clear), masks (list of polygons), "
                                    "model ('model' or a basefile sheet), "
                                    "nest_depth (0-5)"}},
        ["name", "changes"]),
    "reload_references": obj({}),
    "set_annotation_scale": obj(
        {"scale": {"type": ["string", "number", "null"],
                   "description": "a scale-list name ('1\"=50\''), feet per inch (50), "
                                  "'1:600', or null/'off' to turn annotation scaling off"},
         "rescale": {"type": "boolean",
                     "description": "re-size existing annotative model entities to the "
                                    "new scale (default true)"},
         "adopt": {"type": "boolean",
                   "description": "also stamp un-scaled model texts and anchored ticks as "
                                  "annotative at the new scale (default false)"}},
        ["scale"]),
    "add_annotation_scale": obj(
        {"scale": {"type": ["string", "number"],
                   "description": "feet per inch (25) or '1\"=25\'' or '1:300'"},
         "name": {**STR, "description": "list name; default '1\"=25\''"}},
        ["scale"]),
    "delete_annotation_scale": obj({"scale": {"type": ["string", "number"],
                                              "description": "list name or feet per inch"}},
                                   ["scale"]),
    "set_annotation_defaults": obj(
        {"text_height_in": {**POS, "description": "label text height on paper (default 0.10)"},
         "tick_half_len_in": {**POS, "description": "station tick half-length on paper "
                                                    "(default 0.20)"},
         "label_offset_in": {**POS, "description": "label offset from the line on paper "
                                                   "(default 0.32)"}}),
    "undo": obj({}),
    "redo": obj({}),
}

EXAMPLES = {
    "set_meta": {"updates": {"project_name": "SR 100 Resurfacing",
                             "description": "Demo project"}},
    "create_layer": {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center",
                     "lineweight_mm": 0.35, "description": "Roadway centerline"},
    "modify_layer": {"name": "V-ALIGN-CNTR", "changes": {"color": "blue"}},
    "set_current_layer": {"name": "V-ALIGN-CNTR"},
    "create_text_style": {"name": "ROMANS", "font": "DejaVu Sans",
                          "width_factor": 0.9, "default_height": 0.12},
    "define_block": {"name": "MONUMENT", "base_point": [0, 0], "entities": [
        {"type": "circle", "center": [0, 0], "radius": 0.5},
        {"type": "line", "start": [-0.5, 0], "end": [0.5, 0]}]},
    "draw_line": {"space": "model", "start": [1000.0, 1000.0], "end": [1600.0, 1000.0],
                  "layer": "V-ALIGN-CNTR"},
    "draw_polyline": {"space": "model",
                      "vertices": [[0, 0], [100, 0], [100, 50]], "closed": False},
    "draw_arc": {"space": "model", "center": [1600.0, 1800.0], "radius": 800.0,
                 "start_angle_deg": -90.0, "end_angle_deg": -60.0},
    "draw_circle": {"space": "model", "center": [1250.0, 980.0], "radius": 24.0},
    "place_callout": {"space": "model", "target_entity": "DESIGN:LN-004", "at": "mid",
                      "position": [1200.0, 900.0], "content": "EP 12' RT",
                      "layer": "V-ANNO-TEXT"},
    "place_text": {"space": "SH-001", "position": [17.0, 20.5],
                   "content": "ROADWAY PLAN", "height": 0.25, "halign": "center"},
    "insert_block": {"space": "SH-001", "block_name": "NORTH_ARROW",
                     "position": [31.5, 19.0], "scale": 1.0},
    "place_table": {"space": "SH-001", "position": [26.0, 8.0], "title": "CURVE DATA",
                    "columns": [{"header": "CURVE", "width": 1.0},
                                {"header": "R", "width": 1.2}],
                    "rows": [["C-1", "800.00'"]], "text_height": 0.12},
    "move_entities": {"ids": ["TX-001"], "delta": [0.5, 0.0]},
    "modify_entity": {"id": "TX-001", "changes": {"content": "STA 12+00",
                                                  "height": 0.15}},
    "delete_entities": {"ids": ["LN-004", "TX-002"]},
    "create_sheet": {"name": "C-101", "size": "ANSI_D",
                     "title_block_fields": {"sheet_title": "ROADWAY PLAN"}},
    "delete_sheet": {"sheet": "C-101"},
    "create_viewport": {"sheet": "C-101", "center_paper": [17.0, 12.0],
                        "width_in": 31.0, "height_in": 18.0,
                        "model_center": [1700.0, 1150.0], "feet_per_inch": 50.0,
                        "rotation_deg": 0.0},
    "modify_viewport": {"sheet": "C-101", "viewport_id": "VP-001",
                        "changes": {"feet_per_inch": 40.0}},
    "delete_viewport": {"sheet": "C-101", "viewport_id": "VP-001"},
    "fill_title_block": {"sheet": "C-101", "fields": {
        "project": "SR 100 RESURFACING", "sheet_title": "ROADWAY PLAN",
        "sheet_number": "C-101", "scale": "1\" = 50'"}},
    "annotate_stationing": {"space": "model", "path_ids": ["LN-001", "AR-001"],
                            "begin_station": 1000.0, "interval": 100},
    "attach_reference": {"name": "SURVEY", "path": "survey_base.rdraft",
                         "space": "model"},
    "detach_reference": {"name": "SURVEY"},
    "modify_reference": {"name": "SURVEY", "changes": {
        "levels_off": ["V-SURV-TOPO"], "symbology": {"gray": True},
        "clip": [[900, 800], [2600, 800], [2600, 1100], [900, 1100]]}},
    "reload_references": {},
    "set_annotation_scale": {"scale": "1\"=50'"},
    "add_annotation_scale": {"scale": 25, "name": "1\"=25'"},
    "delete_annotation_scale": {"scale": "1\"=25'"},
    "set_annotation_defaults": {"text_height_in": 0.12, "label_offset_in": 0.35},
    "undo": {},
    "redo": {},
}

# Phase 1 design commands (alignments, profiles, anchored labels, curve
# tables, LandXML): schemas and examples live in design_schemas.py.
SCHEMAS.update(DESIGN_SCHEMAS)
EXAMPLES.update(DESIGN_EXAMPLES)
