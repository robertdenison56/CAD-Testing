"""JSON Schemas and examples for the editing, COGO-point, labelling, hatching
and placement commands (modify_handlers.py, cogo_handlers.py).

``schemas.py`` merges ``MODIFY_SCHEMAS`` / ``MODIFY_EXAMPLES`` into
``SCHEMAS`` / ``EXAMPLES`` at its end, as it does the design schemas. Like
``design_schemas``, this module must not import ``schemas`` (that would be a
cycle); the fragments it needs come from ``design_schemas``.
"""
from __future__ import annotations

from roaddraft.commands.design_schemas import (
    ANCHOR, ANGLE_TEXT, COLOR, LINETYPE, NSTR, NUM, POINT, POS, SPACE, STR, obj,
)

IDS = {"type": "array", "items": NSTR, "minItems": 1, "description": "entity ids"}
BOOL = {"type": "boolean"}
INT1 = {"type": "integer", "minimum": 1}
LAYER = {**NSTR, "description": "layer name; defaults to the current layer"}

_STYLE = {"layer": LAYER, "color": {**COLOR, "description": "override color; omit for ByLayer"},
          "linetype": {**LINETYPE, "description": "override linetype; omit for ByLayer"}}

_EDGES = {
    "boundaries": {**IDS, "description": "the edges to cut or extend to (lines, polylines, arcs, "
                                         "circles; reference elements 'BASE:LN-017' count "
                                         "too). Omit to use every one in the space, as "
                                         "AutoCAD's quick trim does"},
    "extend_boundaries": {"type": "boolean",
                          "description": "count an edge where it would cross if it ran on (a "
                                         "line as its infinite line, an arc as its circle) -- "
                                         "AutoCAD's edge mode Extend (default false)"},
    "include_references": {"type": "boolean",
                           "description": "with no boundaries named: reference elements are "
                                          "edges too (default true)"},
}

DIRECTION = {"type": ["string", "array"],
             "description": "a direction: a quadrant bearing (\"N 30°00'00\\\" E\"), an azimuth "
                            "('AZ 30'), or two points [[x1, y1], [x2, y2]] along it"}

PATH = {"type": ["string", "array"], "items": NSTR,
        "description": "what to run along: an entity id (line, polyline, arc, circle; reference "
                       "elements too), a list of ids that join end to end, or an alignment of "
                       "this document ('ALIGN-1')"}
_ALONG = {
    "path": PATH,
    "every": {**POS, "description": "spacing along the path, feet in model. On an alignment "
                                    "with no from, positions fall on round stations "
                                    "(every 100 -> 81+00, 82+00, ...)"},
    "count": {**INT1, "description": "how many, evenly spaced from from to to, both ends "
                                     "included (AutoCAD DIVIDE)"},
    "from": {"type": ["number", "string"],
             "description": "where to start: distance along the path, or on an alignment a "
                            "station ('82+00'); default its start"},
    "to": {"type": ["number", "string"],
           "description": "where to stop (distance or station); default its end"},
    "offset": {"type": ["number", "string"],
               "description": "square off the path, right of its direction positive ('2R', "
                              "'2L' say the side); default on it"},
}

_POINT_STYLE = {
    "marker": {"type": "string", "enum": ["x", "cross", "circle", "circle_x", "dot", "none"],
               "description": "point marker (default x)"},
    "size": {**POS, "description": "marker width in space units (default the label height)"},
    "text_height": {**POS, "description": "label height in space units (default 0.08 in on "
                                          "paper: 0.08 x the annotation scale in model)"},
    "label": {"type": "array", "items": {"type": "string",
                                          "enum": ["number", "elevation", "description"]},
              "description": "label lines beside the marker, top to bottom (default number, "
                             "elevation, description; [] for none)"},
    "style": {**NSTR, "description": "text style of the label"},
}

POINT_ROW = obj({
    "point": {**POINT, "description": "[x, y] = [easting, northing]"},
    "northing": NUM, "easting": NUM,
    "number": {**INT1, "description": "point number; omit to number automatically"},
    "elevation": NUM,
    "description": {**STR, "description": "raw description code, e.g. 'EP', 'MON FD'"},
})

MODIFY_SCHEMAS = {
    "trim": obj({
        "targets": {"type": "array", "minItems": 1,
                    "items": obj({
                        "id": {**NSTR, "description": "the line, polyline, arc or circle to cut"},
                        "at": {**POINT, "description": "a point on the part to cut away -- where "
                                                       "a drafter clicks"},
                        "keep": {**POINT, "description": "instead of at: a point on the part to "
                                                         "keep; every other part goes"}},
                        ["id"]),
                    "description": "what to trim, each with at (the part to remove) or keep "
                                   "(the part to keep). The entity is cut where the edges cross "
                                   "it"},
        **_EDGES}, ["targets"]),
    "extend": obj({
        "targets": {"type": "array", "minItems": 1,
                    "items": obj({
                        "id": {**NSTR, "description": "the line, arc or open polyline to run "
                                                      "on"},
                        "end": {"type": "string", "enum": ["start", "end"],
                                "description": "which end runs on"},
                        "at": {**POINT, "description": "instead of end: a point near the end "
                                                       "to extend"}},
                        ["id"]),
                    "description": "what to extend: each runs straight on (an arc round its "
                                   "circle) to the nearest edge"},
        **_EDGES}, ["targets"]),
    "break_entity": obj({
        "id": {**NSTR, "description": "line, polyline, arc or circle"},
        "at": {**POINT, "description": "where to break it (the nearest point on it)"},
        "to": {**POINT, "description": "a second point: the part between at and to is removed "
                                       "(on a circle or closed polyline, from at onward to to). "
                                       "Without it the entity is split in two at at"}},
        ["id", "at"]),
    "join_entities": obj({
        "ids": {**IDS, "minItems": 2,
                "description": "lines, arcs and polylines to join: collinear lines become one "
                               "line and arcs on one circle one arc (across gaps); anything "
                               "else that meets end to end becomes one polyline, arcs kept as "
                               "arc segments (closed when it closes)"},
        "tolerance": {**POS, "description": "largest gap between ends that still join (default "
                                            "0.01)"}},
        ["ids"]),
    "explode_entities": obj({
        "ids": {**IDS, "description": "polylines (into lines and arcs), block references (into "
                                      "what the block is drawn with), dimensions and tables "
                                      "(into lines and text), points (marker and label) and "
                                      "hatches (into their boundary polylines)"}},
        ["ids"]),
    "chamfer": obj({
        "ids": {"type": "array", "items": NSTR, "minItems": 2, "maxItems": 2,
                "description": "the two lines"},
        "distance": {**POS, "description": "how far back from the corner on the first line"},
        "distance2": {**POS, "description": "how far back on the second (default distance)"},
        "angle": {**ANGLE_TEXT, "description": "instead of distance2: the chamfer's angle from "
                                               "the first line"},
        "keep": {"type": "array", "items": POINT, "minItems": 2, "maxItems": 2,
                 "description": "a point on the part of each line to keep (default each line's "
                                "end farther from the corner)"},
        "trim": {"type": "boolean", "description": "trim the lines to the chamfer (default "
                                                   "true)"},
        **_STYLE},
        ["ids", "distance"]),
    "lengthen": obj({
        "id": {**NSTR, "description": "line, arc or open polyline"},
        "end": {"type": "string", "enum": ["start", "end"], "description": "which end moves"},
        "at": {**POINT, "description": "instead of end: a point near the end that moves"},
        "delta": {**NUM, "description": "feet to add along it (negative shortens)"},
        "total": {**POS, "description": "the new total length"},
        "percent": {**POS, "description": "the new length as a percentage of the old"},
        "to": {**POINT, "description": "run the end to where this point falls square to it"}},
        ["id"]),
    "copy_entities": obj({
        "ids": {**IDS, "description": "what to copy; reference elements are copied into this "
                                      "document"},
        "delta": {**POINT, "description": "displacement [dx, dy]"},
        "from": {**POINT, "description": "base point (with to)"},
        "to": {**POINT, "description": "where the base point goes"},
        "count": {**INT1, "description": "repeat the displacement this many times (default 1)"}},
        ["ids"]),
    "rotate_entities": obj({
        "ids": IDS,
        "base": {**POINT, "description": "the point to rotate about"},
        "angle": {"type": ["number", "string"],
                  "description": "degrees counter-clockwise (DMS text works; '30 CW' turns "
                                 "clockwise)"},
        "from_direction": {**DIRECTION, "description": "with to_direction: turn this direction "
                                                       "onto that one (AutoCAD rotate "
                                                       "reference) -- e.g. a building's side "
                                                       "given by two corners onto a bearing"},
        "to_direction": DIRECTION,
        "copy": {"type": "boolean", "description": "rotate a copy, leaving the original "
                                                   "(default false)"}},
        ["ids", "base"]),
    "mirror_entities": obj({
        "ids": IDS,
        "line": {"type": "array", "items": POINT, "minItems": 2, "maxItems": 2,
                 "description": "two points on the mirror line"},
        "keep_original": {"type": "boolean",
                          "description": "keep the original and add the mirror image (default "
                                         "true); false mirrors in place. Text stays readable"}},
        ["ids", "line"]),
    "scale_entities": obj({
        "ids": IDS,
        "base": {**POINT, "description": "the point that stays put"},
        "factor": {**POS, "description": "scale factor"},
        "from_length": {**POS, "description": "with to_length: scale so this length becomes "
                                              "that one"},
        "to_length": POS,
        "copy": {"type": "boolean", "description": "scale a copy (default false)"}},
        ["ids", "base"]),
    "array_entities": obj({
        "ids": {**IDS, "description": "what to repeat; the original stays and copies are added"},
        "kind": {"type": "string", "enum": ["rectangular", "polar", "path"],
                 "description": "rectangular (rows x columns), polar (round a center) or path "
                                "(along linework or an alignment)"},
        "rows": INT1, "columns": INT1,
        "row_spacing": {**NUM, "description": "rectangular: distance between rows (negative: "
                                              "downward)"},
        "column_spacing": {**NUM, "description": "rectangular: distance between columns"},
        "angle": {**NUM, "description": "rectangular: the array's rotation, degrees CCW"},
        "center": {**POINT, "description": "polar: the center"},
        "count": {**INT1, "description": "polar: items including the original; path: copies "
                                         "evenly spaced from from to to"},
        "fill_angle": {**NUM, "description": "polar: degrees to fill, CCW positive (default "
                                             "360)"},
        "rotate_items": {"type": "boolean", "description": "polar: turn each copy with the "
                                                           "array (default true)"},
        "path": PATH,
        "every": _ALONG["every"], "from": _ALONG["from"], "to": _ALONG["to"],
        "offset": _ALONG["offset"],
        "base_point": {**POINT, "description": "path: the point of the selection that lands on "
                                               "each position (default its insertion point, or "
                                               "the middle of its extents)"},
        "align_items": {"type": "boolean",
                        "description": "path: turn each copy to the path's direction there, so "
                                       "a symbol drawn pointing east (+x) points along it "
                                       "(default true)"}},
        ["ids"]),
    "create_points": obj({
        "space": {**SPACE, "description": "default model"},
        "points": {"type": "array", "minItems": 1, "items": POINT_ROW,
                   "description": "points to create: point [x, y] or northing and easting, "
                                  "with optional number, elevation, description"},
        "text": {**STR, "description": "a point file's lines (comma or space separated), "
                                       "fields in the order format names"},
        "format": {"type": "string", "enum": ["PNEZD", "PENZD", "PNEZ", "PENZ", "PNE", "PEN",
                                               "NEZD", "ENZD", "NEZ", "ENZ", "NE", "EN"],
                   "description": "column order of text: P number, N northing, E easting, Z "
                                  "elevation, D description (default PNEZD)"},
        "from_entities": {**IDS, "description": "set points on these entities' ends and "
                                                "vertices (a deed's corners drawn as a "
                                                "traverse)"},
        "description": {**STR, "description": "description for points that give none"},
        "start_number": {**INT1, "description": "first number to use (default the next free)"},
        **_POINT_STYLE, "layer": LAYER, "color": _STYLE["color"]}),
    "place_point_table": obj({
        "space": SPACE,
        "position": {**POINT, "description": "top-left corner; the table grows downward"},
        "points": {"type": ["string", "array"],
                   "description": "'all' (default), point numbers [1, 2, 5], ids, or a range "
                                  "'1-20, 25'"},
        "columns": {"type": "array", "items": {"type": "string", "enum": [
            "number", "northing", "easting", "elevation", "description"]},
            "description": "default number, northing, easting, and elevation / description "
                           "when any point has one"},
        "title": STR,
        "text_height": {**POS, "description": "default 0.10 in on a sheet"},
        "precision": {"type": "integer", "minimum": 0, "maximum": 6},
        "style": NSTR, "layer": LAYER, "color": _STYLE["color"]},
        ["space", "position"]),
    "label_segments": obj({
        "ids": {**IDS, "description": "lines, polylines (each segment) and arcs to label -- "
                                      "right of way, easements, a deed's courses"},
        "style": {"type": "string", "enum": ["values", "tags"],
                  "description": "values (default): bearing over distance along each line, "
                                 "radius and delta over length on each curve. tags: L1, C1 ... "
                                 "on the linework with a line table and a curve table listing "
                                 "the values"},
        "space": {**SPACE, "description": "where the labels go (default where the linework is); "
                                          "a sheet letters model linework through its "
                                          "viewports, in paper inches"},
        "table": obj({"position": {**POINT, "description": "top-left corner of the tables"},
                      "space": {**SPACE, "description": "default where the tags go"},
                      "text_height": POS}, ["position"]),
        "text_height": {**POS, "description": "label height (default 0.10 in on paper)"},
        "offset": {**POS, "description": "gap between the line and its labels (default 0.6 x "
                                         "the text height)"},
        "precision": {"type": "integer", "minimum": 0, "maximum": 6},
        "order_along": {**NSTR, "description": "number and letter the segments in order of "
                                               "station along this alignment ('RTE-7', or a "
                                               "referenced 'BASE:RTE-7') instead of the order "
                                               "of ids"},
        "line_start": {**INT1, "description": "first line tag number (default 1)"},
        "curve_start": {**INT1, "description": "first curve tag number (default 1)"},
        "text_style": NSTR, "layer": LAYER, "color": _STYLE["color"]},
        ["ids"]),
    "draw_station_offset": obj({
        "space": {**SPACE, "description": "model (the default; stations are model feet)"},
        "alignment": {**NSTR, "description": "the alignment the stations are on (default the "
                                             "only one)"},
        "points": {"type": "array", "items": ANCHOR, "minItems": 2,
                   "description": "station-and-offset points in order: '82+00@15R', "
                                  "'82+90@26R', 'PC-2@15L', 'END@18R', {station, offset}"},
        "follow": {"type": "boolean",
                   "description": "between two points at the same offset, follow the "
                                  "alignment (arcs on its curves, exactly as draw_offset) "
                                  "instead of a straight chord (default true); where the "
                                  "offset changes the run is a straight taper"},
        "polyline": {"type": "boolean", "description": "draw one polyline (curves as arc "
                                                       "segments) instead of lines and arcs"},
        "close": {"type": "boolean", "description": "close back to the first point"},
        **_STYLE},
        ["points"]),
    "place_along": obj({
        **_ALONG,
        "block": {**NSTR, "description": "insert this block at each position (delineators, "
                                         "signs, markers); default COGO points"},
        "align": {"type": "boolean", "description": "turn blocks to the path's direction "
                                                    "(default true)"},
        "rotation": {**NUM, "description": "extra rotation of each block, degrees CCW"},
        "scale": {**POS, "description": "block scale (default 1)"},
        "description": {**STR, "description": "points: their description"},
        "start_number": {**INT1, "description": "points: first number (default the next "
                                                "free)"},
        **_POINT_STYLE, "layer": LAYER, "color": _STYLE["color"]},
        ["path"]),
    "hatch": obj({
        "space": SPACE,
        "boundary": {**IDS, "description": "closed entities (closed polylines, circles, a hatch) "
                                           "or entities that join into closed loops; a loop "
                                           "inside another is an island"},
        "points": {"type": "array", "items": POINT, "minItems": 3,
                   "description": "a polygon to hatch"},
        "at": {**POINT, "description": "a point inside the area: the engine traces the linework "
                                       "around it (AutoCAD's pick-a-point hatch), dangling "
                                       "lines ignored, closed shapes inside left as islands"},
        "pattern": {**NSTR, "description": "SOLID (default) or an AutoCAD pattern: ANSI31 "
                                           "(diagonal: removal, new pavement), ANSI37 "
                                           "(crosshatch), AR-CONC (concrete), AR-SAND, GRAVEL, "
                                           "DOTS, EARTH, NET, LINE, BRICK, SWAMP, GRASS, ..."},
        "scale": {**POS, "description": "pattern scale, AutoCAD's way: pattern units x scale. "
                                        "Default the annotation scale in model (50 at 1\"=50'), "
                                        "1 on a sheet"},
        "angle": {**NUM, "description": "pattern rotation, degrees CCW"},
        "opacity": {"type": "number", "exclusiveMinimum": 0, "maximum": 1,
                    "description": "1 opaque (default); less screens it"},
        "islands": {"type": "boolean", "description": "with at: leave closed shapes inside "
                                                      "open (default true)"},
        "gap_tolerance": {**POS, "description": "largest gap in the linework that still closes "
                                                "the area (default 0.01)"},
        "boundary_layers": {"type": "array", "items": NSTR,
                            "description": "with at: trace only linework on these layers"},
        "include_references": {"type": "boolean",
                               "description": "with at: trace reference linework too (default "
                                              "true)"},
        "layer": LAYER, "color": _STYLE["color"]},
        ["space"]),
}

MODIFY_EXAMPLES = {
    "trim": {"targets": [{"id": "LN-010", "at": [6100.0, 8692.0]},
                         {"id": "LN-011", "at": [6100.0, 8692.0]}],
             "boundaries": ["CI-001"]},
    "extend": {"targets": [{"id": "LN-012", "end": "end"}], "boundaries": ["LN-003"]},
    "break_entity": {"id": "LN-004", "at": [4600.0, 7315.0], "to": [4660.0, 7315.0]},
    "join_entities": {"ids": ["LN-001", "AR-001", "LN-002"]},
    "explode_entities": {"ids": ["PL-003"]},
    "chamfer": {"ids": ["LN-001", "LN-002"], "distance": 10.0, "distance2": 25.0},
    "lengthen": {"id": "LN-005", "end": "end", "delta": 12.5},
    "copy_entities": {"ids": ["BR-001"], "delta": [100.0, 0.0], "count": 3},
    "rotate_entities": {"ids": ["PL-001"], "base": [4600.0, 7500.0],
                        "from_direction": [[4600.0, 7500.0], [4660.0, 7500.0]],
                        "to_direction": "N 34°15'00\" E"},
    "mirror_entities": {"ids": ["LN-020", "AR-005"],
                        "line": [[4100.0, 7300.0], [4700.0, 7300.0]]},
    "scale_entities": {"ids": ["BR-002"], "base": [31.5, 19.0], "factor": 0.5},
    "array_entities": {"ids": ["BR-003"], "kind": "path", "path": "LN-010", "every": 50.0,
                       "offset": "2R"},
    "create_points": {"text": "1,7300.00,4600.00,101.25,MON FD\n2,7359.81,4634.40,,IP SET",
                      "format": "PNEZD", "layer": "V-SURV-PNTS"},
    "place_point_table": {"space": "P-201", "position": [26.0, 20.0], "points": "1-12"},
    "label_segments": {"ids": ["PL-004"], "style": "tags",
                       "table": {"position": [5600.0, 7700.0]}, "layer": "V-ANNO-ROW"},
    "draw_station_offset": {"alignment": "ALIGN-1",
                            "points": ["82+00@15R", "82+90@26R", "86+50@26R", "86+50@15R"],
                            "layer": "V-ROAD-EOP"},
    "place_along": {"path": "ALIGN-1", "every": 200.0, "offset": "18R", "block": "DELINEATOR"},
    "hatch": {"space": "model", "at": [4350.0, 7306.0], "pattern": "ANSI31",
              "layer": "V-ROAD-HTCH"},
}

__all__ = ["MODIFY_SCHEMAS", "MODIFY_EXAMPLES"]
