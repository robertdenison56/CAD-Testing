"""JSON Schemas for every command's parameters.

These schemas are the contract of the machine-facing tool surface: they are
served verbatim in the tool manifest, used to validate every call, and echoed
back in teaching errors when a call is invalid.
"""
from __future__ import annotations

from roaddraft.commands.design_schemas import (
    ANCHOR, DESIGN_EXAMPLES, DESIGN_SCHEMAS, STATION,
)
from roaddraft.core.units import LENGTH_FORMATS
from roaddraft.document.document import LINETYPES
from roaddraft.document.entities import DIM_ARROWS, DIM_KINDS
from roaddraft.document.sheets import SHEET_SIZES, TITLE_BLOCK_TEMPLATES
from roaddraft.render.titleblock import keys_text

POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
         "description": "[x, y]"}
NUM = {"type": "number"}
POS = {"type": "number", "exclusiveMinimum": 0}
STR = {"type": "string"}
NSTR = {"type": "string", "minLength": 1}
SPACE = {"type": "string", "minLength": 1,
         "description": "'model' (design space, US survey feet) or a sheet id/name "
                        "(paper space, inches), e.g. 'SH-004' or 'P-201'"}
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


# --- coordinate geometry (bearings and distances) ---------------------------

ANGLE_TEXT = {"type": ["number", "string"],
              "description": "degrees as a number, or DMS text: 40°30'15\", 40-30-15"}
DIRECTION_PROPS = {
    "bearing": {"type": "string",
                "description": "quadrant bearing: N 47°30'15\" E, S47-30-15W, N47E"},
    "azimuth": {**ANGLE_TEXT, "description": "degrees clockwise from north, 0-360 (a "
                                             "number or DMS text)"},
    "deflection": {**ANGLE_TEXT,
                   "description": "the angle turned from the previous course, with its side: "
                                  "'33 L', '18°30'00\" RT', or a number with right "
                                  "(clockwise) positive; or its size with turn"},
    "turn": {"type": "string", "enum": ["left", "right", "L", "R"],
             "description": "which way a deflection or a curve turns"},
    "angle_right": {**ANGLE_TEXT, "description": "angle measured clockwise from the "
                                                 "backsight (the previous course run "
                                                 "backwards), as a field traverse records it"},
}
COURSE = {
    "type": ["object", "string"],
    "description": "one course. Straight: a direction (exactly one of bearing, azimuth, "
                   "deflection, angle_right) and distance. Curve: radius, turn and one of "
                   "delta, length or chord; it continues the previous course's direction "
                   "unless chord_bearing places it (a non-tangent curve). Or the course as "
                   "text: \"N 47°30'15\\\" E 250\", \"AZ 75.5 250\", \"33 L 820\", "
                   "\"CURVE R=450 LEFT DELTA=33\"",
    "properties": {
        **DIRECTION_PROPS,
        "distance": {**POS, "description": "length of a straight course (feet in model)"},
        "radius": {**POS, "description": "radius of a curve course -- giving one makes the "
                                         "course a curve"},
        "delta": {**ANGLE_TEXT, "description": "a curve's central angle"},
        "length": {**POS, "description": "a curve's arc length"},
        "chord": {**POS, "description": "a curve's chord length"},
        "chord_bearing": {"type": ["string", "number"],
                          "description": "a non-tangent curve's chord bearing (or azimuth)"},
    },
    "additionalProperties": False,
}
TRAVERSE_PROPS = {
    "start": {"description": "where the traverse begins: a point [x, y] (x = easting, y = "
                             "northing), or an entity id to continue from its end (start_at "
                             "says which end; the entity's direction there is the course a "
                             "leading deflection turns from)"},
    "start_at": {"type": "string", "enum": ["start", "end"],
                 "description": "with a start entity: continue from its end (default) or "
                                "its start"},
    "legs": {"type": "array", "items": COURSE, "minItems": 1,
             "description": "the courses in order, each from where the last one ended"},
    "initial_bearing": {"type": "string",
                        "description": "the direction a leading deflection or tangent curve "
                                       "turns from, as a quadrant bearing"},
    "initial_azimuth": {**ANGLE_TEXT, "description": "the same as an azimuth"},
    "close": {"type": "boolean",
              "description": "the traverse should close on its start: report the "
                             "misclosure (distance, bearing, precision 1:N) and, when "
                             "drawing, add the closing course"},
}


#: the keys each border letters, read off the templates (render/titleblock.py)
TITLE_BLOCK_KEYS = (
    "the keys the sheet's border letters -- "
    + "; ".join(f"{t}: {keys_text(t)}" for t in TITLE_BLOCK_TEMPLATES if t != "none")
    + ". A key the border does not letter is kept with the sheet, and the result warns; "
      "get_sheet_state lists a sheet's own (title_block_keys)")

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
         "closed": {"type": "boolean"},
         "bulges": {"type": "array", "items": NUM,
                    "description": "arc segments, the DXF way: one value per vertex for the "
                                   "segment that starts there, tan(sweep/4) -- 0 straight, 1 a "
                                   "half circle, positive counter-clockwise. Omit for straight "
                                   "segments"}},
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
                                            "at, in the callout's own space (paper inches "
                                            "on a sheet); prefer target_entity or "
                                            "target_anchor, which cannot miss"},
         "target_entity": {**NSTR,
                           "description": "what to point at, by id (find_entities and "
                                          "hit_test return them; reference elements are "
                                          "'BASE:LN-017'). The engine computes a point "
                                          "on it, so a curve is aimed at correctly. On a "
                                          "sheet it may be a model or referenced entity: "
                                          "the tip lands where the viewport shows it. "
                                          "Give exactly one of target / target_entity / "
                                          "target_anchor."},
         "at": {"description": "where along target_entity the leader TIP goes: "
                               "start|mid|end or a fraction 0-1 (default mid) -- not "
                               "where the text goes, which is position. From a sheet "
                               "it runs along the part of the entity that sheet shows, "
                               "so mid is always a point the reader can see"},
         "target_anchor": {**ANCHOR,
                           "description": "a station, offset or named point of an "
                                          "alignment to point at: '87+41.62@19.75L', "
                                          "'PC-2', {station, offset}. There is no "
                                          "entity at a station, so this is how a "
                                          "station-and-offset callout is aimed"},
         "alignment": {**NSTR,
                       "description": "the alignment target_anchor is on; a referenced "
                                      "one is 'BASE:RTE-7' (read, not owned -- the "
                                      "callout carries no anchor). Defaults to the "
                                      "document's only alignment"},
         "viewport": {**NSTR,
                      "description": "on a sheet, the viewport to see the target "
                                     "through (default: the first one that shows it)"},
         "position": {**POINT,
                      "description": "where the text sits, clear of the geometry, in the "
                                     "callout's own space. The text reads away from the "
                                     "target: when the target is to the left, the text "
                                     "starts here and runs right (left-justified); when "
                                     "it is to the right, the text ends here "
                                     "(right-justified). Vertically it is centred on "
                                     "this point, and the landing runs from here back "
                                     "toward the target"},
         "content": {**NSTR, "description": "the callout's text; \\n starts a new line"},
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
    "place_dimension": obj(
        {**_ENTITY_COMMON,
         "kind": {"type": "string", "enum": list(DIM_KINDS),
                  "description": "linear (measured along one axis), aligned (the true "
                                 "distance between two points), angular (the angle at "
                                 "a vertex), radius, diameter, or arc_length"},
         "line_point": {**POINT,
                        "description": "where the dimension line goes -- the point a "
                                       "drafter drags to. It also settles what is being "
                                       "measured: clear above or below a pair of points "
                                       "is a horizontal dimension and out to the side a "
                                       "vertical one; on an angular dimension it picks "
                                       "which of the four angles between the rays is "
                                       "meant; on a radius or diameter it is where the "
                                       "text sits (inside the circle draws across it, "
                                       "outside draws a leader)"},
         "p1": {**POINT, "description": "first measured point (angular: a point out "
                                        "along the first ray; radius/diameter: the point "
                                        "on the circle the arrow touches, default: "
                                        "toward line_point)"},
         "p2": {**POINT, "description": "second measured point (arc_length: the far end, "
                                        "measured counter-clockwise from p1)"},
         "center": {**POINT, "description": "angular: the vertex. radius/diameter/"
                                            "arc_length: the centre of the circle"},
         "radius": {**POS, "description": "radius of the circle being measured; or give "
                                          "of_entity"},
         "of_entity": {**NSTR,
                       "description": "measure this entity: a line/polyline/arc end to "
                                      "end (linear, aligned), or an arc/circle's own "
                                      "geometry (radius, diameter, arc_length). Ids come "
                                      "from find_entities and hit_test; reference "
                                      "elements are 'SURVEY:LN-001'"},
         "from_entity": {**NSTR, "description": "measure from a point on this entity "
                                                "(angular: one of the two lines whose "
                                                "intersection is the vertex)"},
         "to_entity": {**NSTR, "description": "measure to a point on this entity "
                                              "(angular: the other line)"},
         "from_at": {"description": "where on from_entity: start|mid|end or a fraction "
                                    "0-1 (default mid)"},
         "to_at": {"description": "where on to_entity: start|mid|end or a fraction 0-1 "
                                  "(default mid)"},
         "rotation_deg": {**NUM,
                          "description": "linear: the direction measured along (0 = "
                                         "horizontal, 90 = vertical). Omit and the "
                                         "engine reads it off line_point"},
         "view_rotation": {"type": "number",
                           "description": "model space: the twist (rotation_deg) of the "
                                          "viewport the dimension is read through; its "
                                          "text is set to read upright on that sheet "
                                          "instead of in the model (default 0, an "
                                          "untwisted view)"},
         "text": {**STR, "description": "override the measured value ('' hides the text "
                                        "entirely); omit to let the number follow the "
                                        "geometry"},
         "prefix": {**STR, "description": "before the number; defaults to the kind's own "
                                          "(R=, \u00d8, L=)"},
         "suffix": {**STR, "description": "after the number, e.g. ' TYP'"},
         "unit_format": {"type": "string", "enum": list(LENGTH_FORMATS),
                         "description": "feet (120.00'), feet_inches (12'-6\") or "
                                        "decimal (no unit mark). Default: feet in model "
                                        "space, decimal on a sheet. An angular dimension "
                                        "reads DMS (28\u00b015'30\") unless this is "
                                        "'decimal'"},
         "precision": {"type": "integer", "minimum": 0, "maximum": 6,
                       "description": "decimals in the number (default 2)"},
         "arrow": {"type": "string", "enum": list(DIM_ARROWS),
                   "description": "terminator: arrow (default), tick (the oblique civil "
                                  "slash), dot, or none"},
         "arrow_size": {**POS, "description": "arrowhead length (default 1.2 x the text "
                                              "height)"},
         "text_gap": {**POS, "description": "gap between the dimension line and the text "
                                            "(default 0.5 x the text height)"},
         "extension_offset": {**POS, "description": "gap between the measured point and "
                                                    "its extension line (default 0.6 x "
                                                    "the text height)"},
         "extension_beyond": {**POS, "description": "how far an extension line runs past "
                                                    "the dimension line (default 1.0 x "
                                                    "the text height)"},
         "text_height": {**POS, "description": "text height in space units; defaults to "
                                               "the annotation scale in model space, "
                                               "0.10 in on a sheet"},
         "style": NSTR,
         "measure_scale": {**POS,
                           "description": "multiplier from drawn length to reported "
                                          "length (AutoCAD DIMLFAC). 1 by default; on a "
                                          "sheet, set it to the viewport's plot scale "
                                          "(50 for 1\"=50') to dimension in model feet"}},
        ["space", "kind", "line_point"]),
    "draw_traverse": obj(
        {**_ENTITY_COMMON, **TRAVERSE_PROPS,
         "polyline": {"type": "boolean",
                      "description": "draw one polyline instead of separate lines (straight "
                                     "courses only; with close it is a closed polyline)"}},
        ["space", "start", "legs"]),
    "offset_entity": obj(
        {"ids": {**IDS,
                 "description": "what to copy parallel: one line, polyline, arc or circle, or "
                                "several that join end to end (in order along them), offset "
                                "together as one path. Reference elements ('BASE:LN-017') "
                                "may be copied into this document"},
         "distance": {**POS, "description": "how far, with side or toward"},
         "side": {"type": "string", "enum": ["left", "right"],
                  "description": "left or right of the direction the path runs: a line "
                                 "start to end, a polyline in vertex order, an arc or circle "
                                 "counter-clockwise, a chain in the order of ids"},
         "toward": {**POINT, "description": "a point on the side to offset to, the way a "
                                            "drafter clicks the side"},
         "through": {**POINT, "description": "a point the parallel passes through; the "
                                             "distance is measured square to the path"},
         "offsets": {"type": "array", "minItems": 1, "items": {"type": ["number", "string"]},
                     "description": "several parallels at once, right of the path's "
                                    "direction positive ('15L', '15R' say the side): "
                                    "[-15, 15] is both edges of a 30 ft pavement"},
         "join": {"type": "string", "enum": ["sharp", "round"],
                  "description": "outside corners: sharp extends the pieces to meet (default), "
                                 "round swings an arc about the corner"},
         "connect_tolerance": {**POS, "description": "largest gap between chained pieces "
                                                     "(default 0.01)"},
         "layer": {**NSTR, "description": "layer of the copies; default the source's layer"},
         "color": COLOR, "linetype": LINETYPE},
        ["ids"]),
    "fillet": obj(
        {"ids": {"type": "array", "items": NSTR, "minItems": 2, "maxItems": 2,
                 "description": "the two lines to join"},
         "radius": {"type": "number", "minimum": 0,
                    "description": "curve radius; 0 extends or trims the lines to a sharp "
                                   "corner"},
         "keep": {"type": "array", "items": POINT, "minItems": 2, "maxItems": 2,
                  "description": "a point on the part of each line to keep, in the order of "
                                 "ids (where a drafter clicks them); default: each line's end "
                                 "farther from where they meet"},
         "trim": {"type": "boolean",
                  "description": "trim or extend the lines to the tangent points (default "
                                 "true); false draws only the curve"},
         "layer": {**NSTR, "description": "layer of the curve; default the first line's"},
         "color": COLOR, "linetype": LINETYPE},
        ["ids", "radius"]),
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
        {"name": {**NSTR, "description": "sheet name, e.g. 'P-201'"},
         "size": {"type": "string", "enum": sorted(SHEET_SIZES)},
         "width_in": POS, "height_in": POS,
         "title_block_template": {
             "type": "string", "enum": sorted(TITLE_BLOCK_TEMPLATES),
             "description": "border and title block drawing: 'standard' "
                            "(default), 'caltrans' (Caltrans plan sheet: left "
                            "binding strip, plot strip, Dist/COUNTY/ROUTE "
                            "block), 'wfl' (FHWA Federal Lands 11 x 17 plan "
                            "sheet: PROJECT / SHEET NUMBER block top right, "
                            "sheet title box bottom right, plot stamp up the "
                            "left margin), 'fdot' (FDOT 11 x 17 plan sheet: "
                            "revisions, engineer of record, ROAD NO./COUNTY/"
                            "FINANCIAL PROJECT ID, sheet title and number in a "
                            "strip across the foot), or 'none' to draw your own"},
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
                    "description": TITLE_BLOCK_KEYS}},
        ["sheet", "fields"]),
    "annotate_stationing": obj(
        {"space": {**SPACE, "description": "'model': stationing is drawn in model space, "
                                           "never on a sheet, and every sheet shows it "
                                           "through its viewport; design mode refuses a "
                                           "sheet name"},
         "path_ids": {**IDS, "description": "line/polyline/arc entity ids forming "
                                            "the centerline, in order along it "
                                            "(entity-chain mode); with chain=true, "
                                            "any one or more of them"},
         "chain": {"type": "boolean",
                   "description": "entity-chain mode: follow the elements joined end "
                                  "to end from path_ids, so one id stations the whole "
                                  "centerline; stops where the linework branches, "
                                  "unless path_ids names the way on"},
         "alignment": {**NSTR, "description": "design-model alignment name: true "
                                              "stations, equations, and anchored "
                                              "output (alternative to path_ids); a "
                                              "referenced one as 'BASE:ALIGN-1'"},
         "lettering": {"enum": ["caltrans", "full"],
                       "description": "alignment mode: 'caltrans' (default) letters the "
                                      "whole station number at each 500 ft and the ones "
                                      "digit elsewhere (85, 6, 7, ... 90); 'full' letters "
                                      "every station 86+00.00"},
         "station_side": {"enum": ["below", "above", "left", "right"],
                          "description": "alignment mode: where the station numbers go; "
                                         "default below the line"},
         "point_side": {"enum": ["left", "right", "above", "below"],
                        "description": "alignment mode: where the BC/EC and equation "
                                       "lettering goes, square to the line and reading "
                                       "bottom to top; default left"},
         "view_rotation": {"type": "number",
                           "description": "alignment mode: the twist (rotation_deg) of the "
                                          "viewport the labels are read through; they are "
                                          "lettered upright on that sheet instead of in the "
                                          "model (default 0, an untwisted view)"},
         "point_label_offset": {**POS, "description": "alignment mode: BC/EC and equation "
                                                      "distance from the line (default "
                                                      "22.5 ft, or the annotation scale x "
                                                      "0.45 in)"},
         "begin_station": {**STATION, "description": "entity-chain mode: the station "
                                                     "(feet, or '15+90.29') at the "
                                                     "start of the first element, or "
                                                     "at start_point when given"},
         "start_point": {**POINT, "description": "entity-chain mode: a point on the "
                                                 "path where begin_station is known; "
                                                 "stations run on from the end of the "
                                                 "path nearer it"},
         "reverse": {"type": "boolean",
                     "description": "entity-chain mode: run the stations the other "
                                    "way along the path"},
         "station_range": {"type": "array", "items": STATION, "minItems": 2,
                           "maxItems": 2,
                           "description": "alignment mode: only annotate between "
                                          "these display stations"},
         "include_equations": {"type": "boolean",
                               "description": "alignment mode: label station "
                                              "equations (default true)"},
         "interval": {**POS, "description": "tick spacing in feet (default 100)"},
         "tick_half_len": {**POS, "description": "tick half-length each side of "
                                                 "the path (default 3.5 ft, a 7 ft tick "
                                                 "at 1\" = 50', or the annotation scale "
                                                 "x 0.07 in)"},
         "text_height": {**POS, "description": "label height (default 8 ft, or the "
                                               "annotation scale x 0.10 in)"},
         "label_offset": {**NUM, "description": "station number distance from the "
                                                "path, below it (default 6 ft, or the "
                                                "annotation scale x 0.12 in: half a "
                                                "text height under the tick); negative "
                                                "is the older way of asking for "
                                                "stations on the right, BC/EC left"},
         "layer": {**NSTR, "description": "layer for ticks; default current"},
         "label_layer": {**NSTR, "description": "layer for labels; default same "
                                                "as ticks"},
         "include_pc_pt": {"type": "boolean",
                           "description": "letter BC/EC/PCC/PRC at the curve "
                                          "points (default true)"},
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
    "set_meta": {"updates": {"project_name": "RTE 7 Resurfacing",
                             "description": "Demo project"}},
    "create_layer": {"name": "align_MAIN", "color": "black", "linetype": "continuous",
                     "lineweight_mm": 0.35, "description": "Roadway centerline"},
    "modify_layer": {"name": "align_MAIN", "changes": {"color": "blue"}},
    "set_current_layer": {"name": "align_MAIN"},
    "create_text_style": {"name": "ROMANS", "font": "DejaVu Sans",
                          "width_factor": 0.9, "default_height": 0.12},
    "define_block": {"name": "MONUMENT", "base_point": [0, 0], "entities": [
        {"type": "circle", "center": [0, 0], "radius": 0.5},
        {"type": "line", "start": [-0.5, 0], "end": [0.5, 0]}]},
    "draw_line": {"space": "model", "start": [4100.0, 7300.0], "end": [4700.0, 7300.0],
                  "layer": "V-ALIGN-CNTR"},
    "draw_polyline": {"space": "model",
                      "vertices": [[0, 0], [100, 0], [100, 50]], "closed": False},
    "draw_arc": {"space": "model", "center": [4700.0, 8100.0], "radius": 800.0,
                 "start_angle_deg": -90.0, "end_angle_deg": -60.0},
    "draw_circle": {"space": "model", "center": [4350.0, 7280.0], "radius": 24.0},
    "place_callout": {"space": "model", "target_entity": "BASE:LN-017", "at": "mid",
                      "position": [4300.0, 7200.0], "content": "EP 15' RT",
                      "layer": "V-ANNO-TEXT"},
    "place_text": {"space": "SH-004", "position": [17.0, 20.5],
                   "content": "ROADWAY PLAN", "height": 0.25, "halign": "center"},
    "place_dimension": {"space": "model", "kind": "linear", "from_entity": "LN-002",
                        "to_entity": "LN-003", "line_point": [4350.0, 7180.0],
                        "layer": "V-ANNO-DIMS"},
    "draw_traverse": {"space": "model", "start": [4100.0, 7300.0],
                      "legs": [{"bearing": "S 76°15'00\" E", "distance": 650.0},
                               {"deflection": "33 L", "distance": 820.0},
                               "N 71°45'00\" E 540"],
                      "layer": "V-SURV-LINE"},
    "offset_entity": {"ids": ["LN-001"], "distance": 15.0, "side": "right",
                      "layer": "V-ROAD-EOP"},
    "fillet": {"ids": ["LN-001", "LN-002"], "radius": 50.0},
    "insert_block": {"space": "SH-004", "block_name": "NORTH_ARROW",
                     "position": [31.5, 19.0], "scale": 1.0},
    "place_table": {"space": "SH-004", "position": [26.0, 8.0], "title": "CURVE DATA",
                    "columns": [{"header": "CURVE", "width": 1.0},
                                {"header": "R", "width": 1.2}],
                    "rows": [["C-1", "450.00'"]], "text_height": 0.12},
    "move_entities": {"ids": ["TX-001"], "delta": [0.5, 0.0]},
    "modify_entity": {"id": "TX-001", "changes": {"content": "STA 84+00",
                                                  "height": 0.15}},
    "delete_entities": {"ids": ["LN-004", "TX-002"]},
    "create_sheet": {"name": "P-201", "size": "ANSI_D",
                     "title_block_fields": {"sheet_title": "ROADWAY PLAN"}},
    "delete_sheet": {"sheet": "P-201"},
    "create_viewport": {"sheet": "P-201", "center_paper": [17.0, 12.0],
                        "width_in": 31.0, "height_in": 18.0,
                        "model_center": [4800.0, 7450.0], "feet_per_inch": 50.0,
                        "rotation_deg": 0.0},
    "modify_viewport": {"sheet": "P-201", "viewport_id": "VP-001",
                        "changes": {"feet_per_inch": 40.0}},
    "delete_viewport": {"sheet": "P-201", "viewport_id": "VP-001"},
    "fill_title_block": {"sheet": "P-201", "fields": {
        "project": "RTE 7 RESURFACING", "sheet_title": "ROADWAY PLAN",
        "sheet_number": "P-201", "scale": "1\" = 50'"}},
    "annotate_stationing": {"space": "model", "alignment": "BASE:ALIGN-1", "interval": 100,
                            "lettering": "caltrans", "view_rotation": 0},
    "attach_reference": {"name": "SURVEY", "path": "survey_base.rdraft",
                         "space": "model"},
    "detach_reference": {"name": "SURVEY"},
    "modify_reference": {"name": "SURVEY", "changes": {
        "levels_off": ["V-SURV-TOPO"], "symbology": {"gray": True},
        "clip": [[4000, 7100], [5700, 7100], [5700, 7400], [4000, 7400]]}},
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

# Editing, COGO points, segment labels, hatching and placement along a path:
# schemas and examples live in modify_schemas.py.
from roaddraft.commands.modify_schemas import MODIFY_EXAMPLES, MODIFY_SCHEMAS  # noqa: E402

SCHEMAS.update(MODIFY_SCHEMAS)
EXAMPLES.update(MODIFY_EXAMPLES)
