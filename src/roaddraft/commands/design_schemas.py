"""JSON Schemas and examples for the Phase 1 design commands.

``DESIGN_SCHEMAS`` / ``DESIGN_EXAMPLES`` hold the parameter contract of the
nine design-model commands (alignments, profiles, anchored labels, curve
tables, LandXML import). ``schemas.py`` merges them into ``SCHEMAS`` /
``EXAMPLES`` at its end, so they are served in the tool manifest, used to
validate every call, and echoed back in teaching errors exactly like the
base command schemas.

Import direction: this module must NOT import ``roaddraft.commands.schemas``
(``schemas.py`` imports this module, so a top-level import back would form a
cycle whenever ``design_schemas`` is imported first). The small building
blocks it needs are re-declared here, byte-for-byte equal to the ones in
``schemas.py``; ``tests/test_design_schemas.py`` asserts that equality so
the two copies cannot drift apart silently. It also does not import the
``design`` package: ``LABEL_KINDS`` is a literal copy of
``design.labels.LABEL_KINDS``.
"""
from __future__ import annotations

from roaddraft.document.document import LINETYPES

# --- fragments re-declared from schemas.py (keep identical) -----------------

POINT = {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2,
         "description": "[x, y]"}
NUM = {"type": "number"}
POS = {"type": "number", "exclusiveMinimum": 0}
STR = {"type": "string"}
NSTR = {"type": "string", "minLength": 1}
SPACE = {"type": "string", "minLength": 1,
         "description": "'model' (design space, US survey feet) or a sheet id/name "
                        "(paper space, inches), e.g. 'SH-004' or 'P-201'"}
LINETYPE = {"type": "string", "enum": list(LINETYPES)}
HALIGN = {"type": "string", "enum": ["left", "center", "right"]}
VALIGN = {"type": "string", "enum": ["bottom", "middle", "top"]}
COLOR = {"type": "string",
         "description": "named CAD color (black, red, yellow, green, cyan, blue, "
                        "magenta, gray, white) or '#RRGGBB'"}


def obj(props, required=(), extra=False):
    """Build a closed object schema (``additionalProperties`` false by default).

    Identical to ``schemas.obj``: every command schema is an ``obj(...)`` so
    any parameter not listed is rejected at validation time.
    """
    return {"type": "object", "properties": props, "required": list(required),
            "additionalProperties": extra}


# --- design vocabulary (literal copy of design.labels.LABEL_KINDS) ----------

LABEL_KINDS = ["station", "pc", "pt", "pi", "mc", "pcc", "prc", "bearing", "begin", "end",
               "equation", "curve_data", "custom"]

# --- design schema fragments (spec section 4 preamble) ----------------------

STATION = {"type": ["number", "string"],
           "description": "display station: feet (8400) or '84+00.00'"}
PI_ITEM = {"type": "array", "items": NUM, "minItems": 2, "maxItems": 3,
           "description": "[x, y] or [x, y, radius]"}
ANGLE_POINTS = {"type": "boolean",
                "description": "allow interior PIs of radius 0: angle points, where "
                               "the tangents meet with no curve -- a layout whose "
                               "curves come later (default false: a missing radius "
                               "is refused)"}
PVI_ITEM = {"type": "array", "items": NUM, "minItems": 2, "maxItems": 3,
            "description": "[station, elevation] or [station, elevation, vc_length]"}
EQUATION = obj({"back": STATION, "ahead": STATION, "raw_station": NUM}, ["back", "ahead"])
ELEMENT = obj({"kind": {"enum": ["tangent", "curve"]}, "start": POINT, "end": POINT,
               "pc": POINT, "pt": POINT, "center": POINT, "radius": POS,
               "direction": {"enum": ["L", "R"]}}, ["kind"])
ANCHOR = {"type": ["string", "number", "object"],
          "description": "BEGIN | END | PI-n | PC-n | PT-n | MC-n | T-n | EQ-n | "
                         "'86+50.00' | 8650, optionally '@offset' (ft, right +, e.g. "
                         "'PC-2@18', '86+50@25L'); or {ref|station, offset, region}. "
                         "BC-n and EC-n, as a Caltrans plan letters them, are PC-n and "
                         "PT-n"}
KIND = {"enum": list(LABEL_KINDS),
        "description": "what the label letters: station = the station number at a tick; "
                       "pc / pt / pcc / prc = the curve point's station and name (BC, EC); "
                       "pi = the PI; mc = the curve number in a bubble with a leader to the "
                       "middle of the curve, the plan's curve callout (the one kind that draws "
                       "the bubble); bearing = the tangent's bearing and length; begin / end = "
                       "BEGIN / END STA; equation = a station equation; curve_data = the "
                       "curve's C-n, delta, R, T, L block as plain text; custom = the content "
                       "as given, plain text with no bubble or leader. Default: the anchor's "
                       "own kind (PC-n -> pc, MC-n -> mc, T-n -> bearing, EQ-n -> equation), "
                       "so omit it unless the text should be something else"}
ROTATION = {"enum": ["along", "perpendicular", "horizontal"]}
SIDE = {"enum": ["left", "right", "above", "below"],
        "description": "left/right of the stationing direction, or above/below on the paper "
                       "(resolved to the line's left or right and recorded so); default by "
                       "kind: station numbers below, bearings above, curve points and "
                       "equations left, the curve bubble right"}

# --- alignment legs: a layout given by bearings and distances ---------------

ANGLE_TEXT = {"type": ["number", "string"],
              "description": "degrees as a number, or DMS text: 40°30'15\", 40-30-15"}
ALIGNMENT_LEG = {
    "type": ["object", "string"],
    "description": "one tangent, from one PI to the next: a direction (exactly one of "
                   "bearing, azimuth, deflection, angle_right) and the distance to the next "
                   "PI; radius is the curve at the PI where this leg starts (a leg after the "
                   "first). Or as text: \"S 76°15'00\\\" E 650\", \"33 L 820 R=450\"",
    "properties": {
        "bearing": {"type": "string",
                    "description": "quadrant bearing: N 47°30'15\" E, S47-30-15W, N47E"},
        "azimuth": {**ANGLE_TEXT, "description": "degrees clockwise from north, 0-360"},
        "deflection": {**ANGLE_TEXT,
                       "description": "the angle the alignment turns at the PI where this "
                                      "leg starts: '33 L', '18°30'00\" RT', or a number with "
                                      "right positive; or its size with turn"},
        "turn": {"type": "string", "enum": ["left", "right", "L", "R"],
                 "description": "which way a deflection turns"},
        "angle_right": {**ANGLE_TEXT, "description": "angle clockwise from the backsight"},
        "distance": {**POS, "description": "feet from this leg's PI to the next PI"},
        "radius": {"type": "number", "minimum": 0,
                   "description": "the curve at the PI where this leg starts (0 or omitted: "
                                  "none, which needs angle_points)"},
    },
    "additionalProperties": False,
}

# --- command schemas (spec sections 4.1 - 4.9) ------------------------------

DESIGN_SCHEMAS = {
    "create_alignment": obj(
        {"name": NSTR,
         "pis": {"type": "array", "items": PI_ITEM, "minItems": 2},
         "elements": {"type": "array", "items": ELEMENT, "minItems": 1},
         "start": {**POINT, "description": "BEGIN, where legs start: [x, y] = [easting, "
                                           "northing]"},
         "legs": {"type": "array", "items": ALIGNMENT_LEG, "minItems": 1,
                  "description": "the layout as bearings and distances, PI to PI from "
                                 "start -- as a report describes it: 'S 76° E 650 ft to PI-2, "
                                 "where it deflects 33° left on a 450 ft curve; then 820 "
                                 "ft...' is [{bearing: 'S 76 E', distance: 650}, "
                                 "{deflection: '33 L', radius: 450, distance: 820}, ...]"},
         "begin_station": STATION,
         "equations": {"type": "array", "items": EQUATION},
         "description": STR,
         "angle_points": ANGLE_POINTS},
        ["name"]),
    "modify_alignment": obj(
        {"name": NSTR,
         "changes": {"type": "object", "minProperties": 1,
                     "description": "any of: pis, begin_station, equations, "
                                    "description, rename"},
         "angle_points": ANGLE_POINTS,
         "redraw": {"type": "boolean",
                    "description": "when the pis change, redraw the alignment's "
                                   "drawn elements to the new geometry, on the "
                                   "layer they were drawn on (default false)"}},
        ["name", "changes"]),
    "update_labels": obj(
        {"alignment": {**NSTR, "description": "the alignment whose labels to bring up to "
                                              "date: this document's, or a referenced one "
                                              "as 'BASE:RTE-7'; omit for every one"}}),
    "delete_alignment": obj(
        {"name": NSTR,
         "cascade": {"type": "boolean",
                     "description": "also delete profiles bound to it (default false)"}},
        ["name"]),
    "create_profile": obj(
        {"name": NSTR, "alignment": NSTR,
         "pvis": {"type": "array", "items": PVI_ITEM, "minItems": 2},
         "description": STR},
        ["name", "alignment", "pvis"]),
    "delete_profile": obj({"name": NSTR}, ["name"]),
    "draw_alignment": obj(
        {"alignment": NSTR, "layer": NSTR, "color": COLOR, "linetype": LINETYPE,
         "replace": {"type": "boolean",
                     "description": "delete this alignment's previously drawn "
                                    "elements first (default false)"}}),
    "draw_offset": obj(
        {"alignment": NSTR,
         "offsets": {"type": "array", "minItems": 1,
                     "items": {"type": ["number", "string"]},
                     "description": "offset distances from the alignment, feet, right of "
                                    "the direction of stationing positive; a string may "
                                    "name the side ('15L', '15R'). A 30 ft pavement is "
                                    "[-15, 15]; add [-21, 21] for 6 ft shoulders."},
         "station_range": {"type": "array", "items": STATION, "minItems": 2,
                           "maxItems": 2,
                           "description": "draw only between these display stations: "
                                          "how a pavement edge stops at an intersection "
                                          "and picks up again on the far leg"},
         "layer": NSTR, "color": COLOR, "linetype": LINETYPE,
         "replace": {"type": "boolean",
                     "description": "delete this alignment's previously drawn offsets at "
                                    "the same distances first (default false); with a "
                                    "station_range, only the pieces inside it"}},
        ["offsets"]),
    "place_label": obj(
        {"space": SPACE,
         "alignment": {**NSTR, "description": "this document's alignment, or a referenced "
                                               "one as 'BASE:ALIGN-1' (read through the "
                                               "attachment, which must sit at identity)"},
         "anchor": ANCHOR, "kind": KIND,
         "content": {**STR, "description": "explicit text; omit to auto-generate from "
                                           "design data the Caltrans way (recorded either "
                                           "way): '84+62.18 BC', 'N 63°12\'40\" E 911.47\'', "
                                           "the curve number '1' in a bubble with a leader"},
         "side": SIDE,
         "label_offset": {"type": "number", "minimum": 0,
                          "description": "distance from the anchor point, feet in model / "
                                         "inches on sheets; default by kind, sized for "
                                         "1\" = 50' in model: stations 6 ft / 0.12 in, "
                                         "bearings 3 ft / 0.06 in, curve points and "
                                         "equations 22.5 ft / 0.45 in, the curve bubble "
                                         "40 ft / 0.80 in"},
         "rotation": {**ROTATION, "description": "default by kind: curve points and "
                                                  "equations perpendicular (reading bottom "
                                                  "to top), the curve number horizontal, "
                                                  "the rest along the line"},
         "height": {**POS, "description": "text height, feet in model / inches on sheets; "
                                          "default 8 ft / 0.10 in"},
         "view_rotation": {"type": "number",
                           "description": "model space: the twist (rotation_deg) of the "
                                          "viewport the labels are read through; they are "
                                          "lettered upright on that sheet instead of in the "
                                          "model (default 0, an untwisted view)"},
         "style": NSTR, "halign": HALIGN, "valign": VALIGN, "layer": NSTR,
         "color": COLOR, "linetype": LINETYPE,
         "viewport": {**NSTR, "description": "sheet space only: viewport id/name carrying "
                                             "the anchor; default = the first viewport "
                                             "whose frame contains the point"}},
        ["space", "anchor"]),
    "place_curve_table": obj(
        {"space": SPACE,
         "alignment": {**NSTR, "description": "this document's alignment, or a referenced "
                                               "one as 'BASE:ALIGN-1'"},
         "position": {**POINT, "description": "top-left corner, paper inches"},
         "curves": {"type": "array", "items": {"type": "integer", "minimum": 1},
                    "description": "the curves this sheet shows, by the alignment's own curve "
                                   "index (C-1, C-2 ...); default all"},
         "first_curve_number": {"type": "integer", "minimum": 1,
                                "description": "the plan's number for the alignment's first "
                                               "curve (default 1): curve numbers run along "
                                               "the line and never restart on the next sheet, "
                                               "so a design holding a later part of the line "
                                               "numbers on from the sheet before"},
         "columns": {"type": "array", "items": NSTR, "minItems": 1,
                     "description": "keys: curve, pi_sta, pc_sta, pt_sta, delta, direction, "
                                    "radius, tangent, length, external, mid_ordinate, "
                                    "chord, chord_bearing; default the Caltrans table: "
                                    "curve, radius, delta, tangent, length (No., R, Δ, T, L)"},
         "title": STR, "text_height": POS, "layer": NSTR, "style": NSTR, "color": COLOR},
        ["space", "position"]),
    "import_landxml": obj(
        {"path": {**NSTR, "description": "path to a LandXML 1.2 file, read when the "
                                         "command executes (replaying the journal then "
                                         "depends on the file, like attach_reference)"},
         "xml": {**NSTR, "description": "LandXML text inline (keeps the journal "
                                        "self-contained)"},
         "alignments": {"type": "array", "items": NSTR},
         "on_conflict": {"enum": ["error", "replace", "rename"]}}),
}

DESIGN_EXAMPLES = {
    "create_alignment": {"name": "ALIGN-1", "begin_station": "80+00",
                         "pis": [[4100, 7300], [4914.359354, 7300, 800],
                                 [5533.012702, 7657.179677]]},
    "modify_alignment": {"name": "ALIGN-1", "changes": {"begin_station": "90+00"}},
    "update_labels": {"alignment": "BASE:ALIGN-1"},
    "delete_alignment": {"name": "ALIGN-1"},
    "create_profile": {"name": "PROF-1", "alignment": "ALIGN-1",
                       "pvis": [[8000, 100], [8800, 120, 400], [9400, 90]]},
    "delete_profile": {"name": "PROF-1"},
    "draw_alignment": {"alignment": "ALIGN-1", "layer": "align_MAIN"},
    "draw_offset": {"alignment": "ALIGN-1", "offsets": [-15, 15], "layer": "rd_EP"},
    "place_label": {"space": "model", "alignment": "ALIGN-1", "anchor": "PC-1"},
    "place_curve_table": {"space": "P-201", "alignment": "ALIGN-1", "position": [24.0, 8.5]},
    "import_landxml": {"path": "survey/alignments.xml"},
}
