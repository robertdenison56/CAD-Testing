"""Session: the complete machine-facing tool surface.

Everything an agent (AI or human UI) can do goes through exactly two entry
points, both JSON in / JSON out:

  - execute(name, params): mutate the document via the command bus
  - query(name, params):   read state, render images, export files

manifest() self-describes every command and query with schema + example, so a
model (or an MCP/REST wrapper) can discover the whole surface. Nothing about
the document is hidden: get_document_state(detail='full') is the entire file.
"""
from __future__ import annotations

import base64
import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, List, Optional

import jsonschema
from jsonschema.exceptions import best_match

from roaddraft.commands.bus import CommandBus
from roaddraft.commands.design_schemas import ANCHOR, KIND, POINT, ROTATION, SIDE, STATION
from roaddraft.commands.schemas import (
    IDS, NSTR, NUM, POS, SPACE, STR, TRAVERSE_PROPS, obj,
)
from roaddraft.core.units import LENGTH_FORMATS
from roaddraft.document import confine, fileformat
from roaddraft.document.annotation import DEFAULT_SCALES, format_scale, parse_scale
from roaddraft.document.document import Document
from roaddraft.document.sheets import SHEET_SIZES
from roaddraft.render import dxf as dxf_render
from roaddraft.render import mpl as mpl_render

DESIGN_DATA_KINDS = ["alignments", "curves", "tangents", "equations", "anchors", "profiles",
                     "pvis", "vcs"]
#: the kinds read from profiles rather than alignments
PROFILE_KINDS = ("profiles", "pvis", "vcs")

BOUNDS = {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
          "description": "[minx, miny, maxx, maxy]"}
BOOL = {"type": "boolean"}
DPI = {"type": "number", "minimum": 30, "maximum": 600}
PAPER = {"type": "string", "enum": ["sheet"] + sorted(SHEET_SIZES),
         "description": "paper to print on. 'sheet' (the default for a sheet) "
                        "keeps the sheet's own size; model space needs a named "
                        "paper and defaults to ANSI_D"}
ORIENTATION = {"type": "string", "enum": ["landscape", "portrait"],
               "description": "turns a named paper; a sheet printed on its own "
                              "size keeps its own orientation"}
PRINT_SCALE = {"type": ["number", "string"],
               "description": "'fit' (default) fits the page. On a sheet: "
                              "printed inches per sheet inch -- 1 / '1:1' full "
                              "size, 0.5 / '1:2' / '50%' a half-size set. In "
                              "model space: feet per inch -- 50, '1\"=50\'' "
                              "or '1:600'"}

#: Fields of a design-data row that are points, per kind. Points are mapped
#: into host coordinates for a referenced design; stations, lengths, radii and
#: bearings stay as designed.
DESIGN_POINT_FIELDS = {
    "alignments": ("pis",),
    "curves": ("pc", "pi", "pt", "center"),
    "tangents": ("start", "end", "mid_point"),
    "anchors": ("point",),
}

#: Said once, wherever a referenced design is read.
PLACED_NOTE = ("points are in host coordinates (where the reference draws them); "
               "stations, lengths, radii and bearings are as designed in the basefile")


def _place_point(placement, point):
    if point is None or placement.is_identity:
        return point
    return placement.to_host(point)


def _place_row(placement, row: dict, fields) -> dict:
    """A design-data row with its point fields mapped into the host space."""
    if placement.is_identity:
        return row
    out = dict(row)
    for field_name in fields:
        value = out.get(field_name)
        if value is None:
            continue
        if field_name == "pis":
            out[field_name] = [dict(pi, point=placement.to_host(pi["point"]))
                               if isinstance(pi, dict) and "point" in pi
                               else placement.to_host(pi) for pi in value]
        else:
            out[field_name] = placement.to_host(value)
    return out


def _placement_block(placement) -> dict:
    """What to append to a result read through a reference, so the mapping and
    its limits are visible rather than implied."""
    block = placement.to_dict()
    block["note"] = PLACED_NOTE
    block["read_only"] = True
    return block


def _as_set(value):
    """``None`` -> no filter; a scalar or list -> a set of allowed values."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        return {v for v in value}
    return {value}


def _anchor_matches(anchor, wanted: dict) -> bool:
    """Every named anchor field must match one of the values asked for."""
    if not anchor:
        return False
    for key, value in wanted.items():
        allowed = _as_set(value)
        actual = anchor.get(key)
        if isinstance(actual, (int, float)) and not isinstance(actual, bool):
            if not any(isinstance(a, (int, float)) and not isinstance(a, bool)
                       and abs(float(a) - float(actual)) < 1e-9 for a in allowed):
                return False
        elif actual not in allowed:
            return False
    return True


def _paper_corners(owner, text, viewport=None) -> List[List[float]]:
    """The four corners of a text's lettering on the paper, in inches,
    counter-clockwise from the lower left as it reads: the footprint the
    verifier judges legibility by (``verify.legibility.text_quad``).  A model
    text is seen through ``viewport``, its height over the feet per inch and
    turned by the twist; a sheet's own text is where it stands."""
    from roaddraft.verify.legibility import text_quad
    style = owner.text_styles.get(text.style)
    width_factor = style.width_factor if style else 1.0
    if viewport is None:
        quad = text_quad(text.position, text.content, text.height, text.rotation_deg,
                         text.halign, text.valign, width_factor)
    else:
        quad = text_quad(viewport.transform().to_paper(text.position), text.content,
                         text.height / float(viewport.feet_per_inch),
                         text.rotation_deg + float(viewport.rotation_deg),
                         text.halign, text.valign, width_factor)
    return [[round(v, 4) for v in corner] for corner in quad]


def _lettering(owner, entity):
    """The text an entity letters and legibility judges: a text itself, or the
    number a dimension draws (None for anything else, and for a dimension
    whose text is hidden)."""
    if entity.TYPE == "text":
        return entity
    if entity.TYPE == "dimension":
        from roaddraft.document.entities import Text
        return next((prim for prim in entity.primitives(owner)
                     if isinstance(prim, Text) and prim.content), None)
    return None


def _text_view(owner, entity, sheet):
    """The viewport of ``sheet`` that shows a dimension's number, or None (and
    None for anything but a dimension).  The number can stand a text length
    past the line it measures along, so one sheet's frame can show it, or cut
    it, where it does not show the middle of the dimension."""
    if entity.TYPE != "dimension":
        return None
    from roaddraft.document import viewmap
    text = _lettering(owner, entity)
    if text is None:
        return None
    return next((vp for vp in sheet.viewports if viewmap.shows(vp, text.position)), None)


QUERIES = {
    "get_document_state": {
        "description": "Document state. detail='summary' (default) for counts and "
                       "resource lists; detail='full' for the complete document "
                       "JSON (every entity, layer, style, block, sheet).",
        "schema": obj({"detail": {"type": "string", "enum": ["summary", "full"]}}),
        "example": {"detail": "summary"},
    },
    "get_model_state": {
        "description": "All model-space entities as JSON, optionally filtered to "
                       "a bounding box (feet). include_references=true also lists "
                       "what the attachments show, read-only, in host coordinates "
                       "and addressed 'REFNAME:ID' -- which is how to find "
                       "geometry to annotate in a sheet file whose design is "
                       "referenced in.",
        "schema": obj({"bounds": BOUNDS,
                       "include_references": {"type": "boolean"}}),
        "example": {"include_references": True},
    },
    "find_entities": {
        "description": "Find entities by what they are rather than where they are: "
                       "layer, type, anchor (alignment / kind / ref / offset), text "
                       "content, a bounding box, or what a given sheet shows. Any "
                       "filter takes one value or a list of values (match any). "
                       "Searches attached references too, so it is how to locate "
                       "geometry in a sheet file whose design is referenced in. Each "
                       "row carries a point that is ON the entity, ready to pass to "
                       "place_callout as target_entity or target.",
        "schema": obj({
            "space": {**NSTR, "description": "space to search (default 'model'); in a "
                                             "sheet, each text row (and each dimension row, "
                                             "for its text) carries paper_corners as "
                                             "visible_on gives them"},
            "layer": {"description": "layer name, or a list of them"},
            "type": {"description": "line|polyline|arc|circle|text|blockref|table|"
                                    "dimension|point|hatch, or a list"},
            "anchor": {"type": "object",
                       "description": "match the design anchor: any of alignment, "
                                      "kind (element|offset|station|tick|pc|pt|...), "
                                      "ref, offset. Each takes one value or a list, "
                                      "so {kind: 'offset', offset: [-15, 15]} finds "
                                      "both pavement edges."},
            "content_contains": {**NSTR,
                                 "description": "text entities whose content contains "
                                                "this (case-insensitive)"},
            "bounds": BOUNDS,
            "visible_on": {**NSTR,
                           "description": "sheet name: keep only model entities that "
                                          "sheet's viewports actually show. Each row then "
                                          "also carries sheet_point -- the middle of the "
                                          "part shown, in paper inches -- and the "
                                          "viewport it is seen through; a text row also "
                                          "carries paper_corners, the four corners of its "
                                          "lettering on that sheet in inches, "
                                          "counter-clockwise from the lower left as it "
                                          "reads: the footprint legibility is judged by. A "
                                          "dimension row carries its number's paper_corners "
                                          "the same way, and a dimension is listed when the "
                                          "sheet shows its middle or its number"},
            "include_references": {"type": "boolean",
                                   "description": "search attachments too (default true)"},
            "detail": {"type": "string", "enum": ["summary", "full"],
                       "description": "summary (default) is id, type, layer, a point on "
                                      "the entity, its length and anchor; full adds the "
                                      "whole entity"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500,
                      "description": "rows to return (default 50)"},
            "start": {"type": "integer", "minimum": 0,
                      "description": "skip this many matches (paging)"},
        }),
        "example": {"anchor": {"kind": "offset", "offset": [-15, 15]},
                    "visible_on": "P-202"},
    },
    "point_on_entity": {
        "description": "A point that is genuinely ON an entity, and the direction it "
                       "runs there: where='start'|'mid'|'end' or a fraction from 0 to 1. "
                       "Use it instead of computing a point from an arc's center and "
                       "angles -- the midpoint of a curve's endpoints is not on the "
                       "curve. Works on reference elements ('BASE:AR-009'). With "
                       "sheet, 'where' runs along the part of the entity that sheet "
                       "shows and the answer adds where it falls on the paper -- the "
                       "same point place_callout aims at from that sheet.",
        "schema": obj({"id": NSTR,
                       "where": {"description": "start|mid|end, or a fraction 0-1"},
                       "sheet": {**NSTR, "description": "a sheet that sees this model "
                                                        "entity through a viewport"},
                       "viewport": NSTR},
                      ["id"]),
        "example": {"id": "BASE:AR-009", "where": "mid"},
    },
    "model_to_sheet": {
        "description": "Where a model point falls on a sheet, in paper inches, seen "
                       "through a viewport's centre, scale and twist. Use it to decide "
                       "where annotation text should sit -- never do the viewport "
                       "arithmetic by hand. visible=false means no viewport shows the "
                       "point (the mapping through the first or given viewport is still "
                       "returned). To aim a callout, skip this and give place_callout a "
                       "target_entity or target_anchor.",
        "schema": obj({"sheet": NSTR, "point": POINT, "viewport": NSTR},
                      ["sheet", "point"]),
        "example": {"sheet": "P-202", "point": [8450.0, 6180.0]},
    },
    "sheet_to_model": {
        "description": "What a point on a sheet's paper is looking at: the model point "
                       "under it through the viewport it falls in, and the nearest "
                       "entity there (references included) with its distance in feet. "
                       "inside=false means the point is outside every viewport window.",
        "schema": obj({"sheet": NSTR, "point": POINT, "viewport": NSTR},
                      ["sheet", "point"]),
        "example": {"sheet": "P-202", "point": [17.0, 11.5]},
    },
    "measure": {
        "description": "Measure without drawing (AutoCAD DIST / MEASUREGEOM): the "
                       "distance, dx/dy, bearing and azimuth between two points, or one "
                       "entity's own length, radius and sweep. 'from' and 'to' each take "
                       "a point or an entity id (with from_at/to_at: start|mid|end or a "
                       "fraction), so a curve is measured from a point genuinely on it. "
                       "With along -- a line, a chain of entities or an alignment -- the "
                       "points are measured relative to it instead (MicroStation Measure "
                       "Distance along an element / perpendicular): how far along it each "
                       "one falls and how far off it, square, left or right; with two "
                       "points, the distance between them along it and across it. "
                       "The formatted reading is the same string place_dimension would "
                       "draw, which makes it the way to check a dimension before or "
                       "after placing it.",
        "schema": obj({
            "from": {"description": "a point [x, y] or an entity id"},
            "to": {"description": "a point [x, y] or an entity id"},
            "along": {"description": "measure relative to this: an entity id (line, polyline, "
                                     "arc, circle; reference elements 'BASE:LN-017'), a "
                                     "list of ids that join end to end, or an alignment name "
                                     "('RTE-7', 'BASE:RTE-7'). Each point is projected "
                                     "square onto it: along = distance from its start (the "
                                     "station, on an alignment), offset = perpendicular "
                                     "distance, right of its direction positive"},
            "from_at": {"description": "where on the 'from' entity (default mid)"},
            "to_at": {"description": "where on the 'to' entity (default mid)"},
            "entity": {**NSTR,
                       "description": "measure this entity on its own: length, and for "
                                      "an arc or circle its centre, radius and sweep"},
            "unit_format": {"type": "string", "enum": list(LENGTH_FORMATS),
                            "description": "feet (default), feet_inches or decimal"},
            "precision": {"type": "integer", "minimum": 0, "maximum": 6},
        }),
        "example": {"from": "LN-002", "to": "LN-003", "from_at": "start",
                    "to_at": "start"},
    },
    "traverse": {
        "description": "Coordinate geometry without drawing: from a start point (or the end "
                       "of an entity) run courses by bearing, azimuth or deflection and "
                       "distance, and curve courses by radius and delta, length or chord, and "
                       "get back every point, bearing and length -- point + bearing + "
                       "distance -> point, with no trigonometry by hand. close=true adds the "
                       "misclosure of a boundary and its precision (1:N). draw_traverse draws "
                       "the same courses; create_alignment takes start + legs directly.",
        "schema": obj(TRAVERSE_PROPS, ["start", "legs"]),
        "example": {"start": [4100.0, 7300.0],
                    "legs": [{"bearing": "S 76°15'00\" E", "distance": 650.0}, "33 L 820"]},
    },
    "key_points": {
        "description": "The exact points a drafter snaps to, listed: endpoints and vertices, "
                       "midpoints, centers, quadrants, insertion points, dimension "
                       "definition points (node), intersections between the entities, and "
                       "the design points of alignments (BEGIN, PI, BC/PC, EC/PT, radius "
                       "points, END -- points with no entity at them, each carrying the "
                       "anchor that names it). Name entities (id / ids), an alignment, or a "
                       "space and bounds. Use the points directly instead of computing a "
                       "corner or a curve's end by hand.",
        "schema": obj({
            "id": {**NSTR, "description": "one entity (reference elements 'BASE:LN-017')"},
            "ids": {**IDS, "description": "several entities; their intersections with each "
                                          "other are listed too"},
            "alignment": {**NSTR, "description": "an alignment's design points ('RTE-7', or "
                                                 "a referenced 'BASE:RTE-7')"},
            "space": {**NSTR, "description": "with no ids: every entity in this space "
                                             "(default model)"},
            "bounds": BOUNDS,
            "kinds": {"type": "array", "items": {"type": "string", "enum": [
                "endpoint", "midpoint", "center", "quadrant", "intersection", "insertion",
                "node", "design"]},
                "description": "only these kinds of point"},
            "include_references": {"type": "boolean",
                                   "description": "with no ids: attachments too (default "
                                                  "true)"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 2000,
                      "description": "rows to return (default 200)"},
        }),
        "example": {"ids": ["LN-001", "LN-002"]},
    },
    "snap": {
        "description": "Object snap: the exact key point nearest a rough point, as a cursor "
                       "snaps in CAD -- endpoint, midpoint, center, quadrant, intersection, "
                       "insertion, node, design (alignment PI/BC/EC...), and with 'from' (the "
                       "point a line is drawn from) perpendicular and tangent; nearest is the "
                       "fallback when nothing else is in reach. On a sheet it also snaps "
                       "through the viewport to the model and its references, answering in "
                       "paper inches with the model point beside it.",
        "schema": obj({
            "space": {**NSTR, "description": "space to snap in (default model)"},
            "point": POINT,
            "tolerance": {**POS, "description": "how far to look, in space units (default 5 "
                                                "ft in model, 0.1 in on a sheet)"},
            "modes": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": [
                "endpoint", "midpoint", "center", "quadrant", "intersection", "insertion",
                "node", "design", "perpendicular", "tangent", "nearest"]},
                "description": "snap modes to use (default endpoint, midpoint, center, "
                               "intersection, perpendicular, insertion, design)"},
            "from": {**POINT, "description": "the point the line is being drawn from, for "
                                             "perpendicular and tangent"},
            "viewport": {**NSTR, "description": "on a sheet: snap through this viewport"},
            "include_references": {"type": "boolean",
                                   "description": "snap to attachments too (default true)"},
        }, ["point"]),
        "example": {"point": [1601.0, 1001.0], "tolerance": 5.0},
    },
    "get_sheet_state": {
        "description": "One sheet: size, usable area, title block fields and the "
                       "keys its border letters (title_block_keys), viewports (with "
                       "the model region each shows), entities.",
        "schema": obj({"sheet": NSTR}, ["sheet"]),
        "example": {"sheet": "P-201"},
    },
    "get_entity": {
        "description": "One entity by id, with its space, bounding box and properties -- "
                       "what AutoCAD's LIST reads off it: a line's length and bearing, a "
                       "curve's radius, delta, length, chord and tangent, a polyline's "
                       "segments (and area when closed), a circle's area, a point's "
                       "northing, easting and elevation, a hatch's area. Reference elements "
                       "are addressed as 'REFNAME:ID' (as returned by hit_test) and come "
                       "back in host coordinates, read-only.",
        "schema": obj({"id": NSTR}, ["id"]),
        "example": {"id": "LN-001"},
    },
    "area": {
        "description": "Area and perimeter without drawing anything (AutoCAD AREA, "
                       "MicroStation Measure Area): of closed entities or entities that join "
                       "into closed loops (ids; a loop inside another is an island and "
                       "subtracts), a hatch, a polygon of points, or the region of linework "
                       "around a point (at) -- the area a pick-a-point hatch would fill. "
                       "Square feet, square yards and acres in model space (square inches "
                       "on a sheet), with the centroid and each loop's figures.",
        "schema": obj({
            "ids": {**IDS, "description": "closed entities (closed polylines, circles, "
                                          "hatches) or entities that join end to end into "
                                          "closed loops"},
            "points": {"type": "array", "items": POINT, "minItems": 3,
                       "description": "a polygon"},
            "at": {**POINT, "description": "a point inside linework that closes around "
                                           "it"},
            "space": {**NSTR, "description": "with points or at: the space (default "
                                             "model)"},
            "islands": {"type": "boolean",
                        "description": "with at: closed shapes inside subtract (default "
                                       "true)"},
            "gap_tolerance": {**POS, "description": "largest gap that still closes a loop "
                                                    "(default 0.01)"},
            "boundary_layers": {"type": "array", "items": NSTR,
                                "description": "with at: only linework on these layers"},
            "include_references": {"type": "boolean",
                                   "description": "with at: reference linework too "
                                                  "(default true)"},
        }),
        "example": {"at": [1700.0, 988.0]},
    },
    "get_extents": {
        "description": "Bounding box of all entities in a space.",
        "schema": obj({"space": NSTR}),
        "example": {"space": "model"},
    },
    "list_layers": {
        "description": "All layers with color/linetype/lineweight/visibility.",
        "schema": obj({}), "example": {},
    },
    "list_text_styles": {
        "description": "All text styles.", "schema": obj({}), "example": {},
    },
    "list_blocks": {
        "description": "All block (cell) definitions.",
        "schema": obj({}), "example": {},
    },
    "list_sheets": {
        "description": "All sheets with sizes and entity/viewport counts.",
        "schema": obj({}), "example": {},
    },
    "list_references": {
        "description": "All attached references (basefiles) with placement, "
                       "load status, resolved path, unit handling (true "
                       "scale factor), per-level display, symbology and clip "
                       "settings.",
        "schema": obj({}), "example": {},
    },
    "hit_test": {
        "description": "Find entities near a point (screen picking / locate). "
                       "Returns nearest first, within tolerance (space units). "
                       "Elements of attached references are located too "
                       "(id 'REFNAME:ID', reference=name, read_only=true) "
                       "unless include_references is false.",
        "schema": obj({"space": NSTR, "point": {
                           "type": "array", "items": {"type": "number"},
                           "minItems": 2, "maxItems": 2},
                       "tolerance": POS, "include_references": BOOL},
                      ["space", "point"]),
        "example": {"space": "model", "point": [1500.0, 1000.0],
                    "tolerance": 10.0},
    },
    "get_journal": {
        "description": "The command journal (the session's action trajectory).",
        "schema": obj({"start": {"type": "integer", "minimum": 1}}),
        "example": {"start": 1},
    },
    "list_commands": {
        "description": "The full tool manifest: every command and query with "
                       "params schema, example, and C3D/ORD dialect aliases.",
        "schema": obj({}), "example": {},
    },
    "render_sheet": {
        "description": "Render a sheet to PNG at true paper size (the vision "
                       "observation). Returns the file path; set "
                       "include_base64 for inline image data.",
        "schema": obj({"sheet": NSTR, "dpi": DPI, "path": STR,
                       "include_base64": BOOL, "show_viewport_frames": BOOL},
                      ["sheet"]),
        "example": {"sheet": "P-201", "dpi": 150},
    },
    "render_model": {
        "description": "Render model space to PNG (design geometry only, no "
                       "sheet frame).",
        "schema": obj({"bounds": BOUNDS, "dpi": DPI, "path": STR,
                       "include_base64": BOOL}),
        "example": {},
    },
    "export_dxf": {
        "description": "Export the document as DXF (opens in AutoCAD/Civil 3D "
                       "and MicroStation: real layers, blocks, layouts, "
                       "viewports).",
        "schema": obj({"path": STR}), "example": {},
    },
    "export_pdf": {
        "description": "Export sheets to a multi-page PDF at paper size.",
        "schema": obj({"path": STR,
                       "sheets": {"type": "array", "items": NSTR, "minItems": 1}}),
        "example": {},
    },
    "print_pdf": {
        "description": "Print (plot) to PDF with page setup -- the PLOT dialog, "
                       "where export_pdf is a batch dump. Prints one space "
                       "(space='model' or a sheet), a set of sheets, or every "
                       "sheet, onto the paper you choose at the scale you "
                       "choose: fit-to-page, a half-size set (scale='1:2' on a "
                       "sheet), or an exact plot scale in model space "
                       "(scale=50 is 1\"=50'). Also margins, portrait/landscape "
                       "and monochrome. A print that would not fit the paper "
                       "fails with the scale that would. Returns the path and "
                       "what each page was plotted at.",
        "schema": obj({"space": SPACE,
                       "sheets": {"type": "array", "items": NSTR, "minItems": 1,
                                  "description": "several sheets in one job; "
                                                 "omit space and sheets to "
                                                 "print every sheet"},
                       "path": STR, "paper": PAPER, "orientation": ORIENTATION,
                       "scale": PRINT_SCALE,
                       "bounds": {**BOUNDS,
                                  "description": "model-space window to print "
                                                 "(plot 'Window'); defaults to "
                                                 "the extents"},
                       "margin_in": {"type": "number", "minimum": 0,
                                     "description": "unprintable margin on all "
                                                    "four sides (default 0)"},
                       "monochrome": {**BOOL,
                                      "description": "plot every color black"},
                       "scale_lineweights": {**BOOL,
                                             "description": "shrink lineweights "
                                                            "with the plot scale "
                                                            "(off, as in CAD)"}}),
        "example": {"space": "model", "paper": "ANSI_D", "scale": 50},
    },
    "save_document": {
        "description": "Save the document. A path with no RoadDraft extension "
                       "gets '.rdraft', the application document; '.rdoc.json' "
                       "is the same JSON under the interchange name. The saved "
                       "path is returned.",
        "schema": obj({"path": NSTR}, ["path"]),
        "example": {"path": "project.rdraft"},
    },
    "save_journal": {
        "description": "Save the command journal (baseline + commands) as JSONL; "
                       "replayable deterministically.",
        "schema": obj({"path": NSTR}, ["path"]),
        "example": {"path": "session.journal.jsonl"},
    },
    # ------------------------------------------------ design model (Phase 1)
    "list_alignments": {
        "description": "Every alignment in the design model: stations, length, "
                       "curve/tangent/equation counts, bound profiles, and whether "
                       "it has been drawn. include_references=true also lists the "
                       "alignments inside attached basefiles, named "
                       "'REFNAME:ALIGNMENT' and read-only -- in a sheet file whose "
                       "design is referenced in, that is the only place they are.",
        "schema": obj({"include_references": {"type": "boolean"}}),
        "example": {"include_references": True},
    },
    "station_to_xy": {
        "description": "Model-space point at a display station (+ offset, right "
                       "positive) on an alignment, with heading, bearing, and the "
                       "element it lands on (an exact junction reads the ahead "
                       "element). An alignment in an attached basefile is named 'REFNAME:ALIGNMENT' (list_alignments include_references=true shows them); its points come back in host coordinates, while stations, lengths and bearings are as designed.",
        "schema": obj({"alignment": NSTR, "station": STATION, "offset": NUM,
                       "region": {"type": "integer", "minimum": 1},
                       "sheet": {**NSTR, "description": "also say where this falls on that sheet: adds on_sheet {viewport, sheet_point in paper inches, visible}"}},
                      ["station"]),
        "example": {"alignment": "ALIGN-1", "station": "84+00", "offset": 15},
    },
    "xy_to_station": {
        "description": "Perpendicular projection of a model-space point onto an "
                       "alignment: station, offset (L/R), and the element. The point "
                       "is given in host coordinates. An alignment in an attached basefile is named 'REFNAME:ALIGNMENT' (list_alignments include_references=true shows them); its points come back in host coordinates, while stations, lengths and bearings are as designed.",
        "schema": obj({"alignment": NSTR, "point": POINT}, ["point"]),
        "example": {"alignment": "ALIGN-1", "point": [1300, 1012]},
    },
    "resolve_anchor": {
        "description": "Dry run of place_label: where a label of this kind at this "
                       "anchor would land (content, position, rotation, viewport) "
                       "without placing it. Same faults as the command. For a "
                       "referenced alignment ('BASE:RTE-7') it answers where the "
                       "anchor is and what a label there would read, but not a label "
                       "plan -- nothing can be anchored to an alignment this document "
                       "does not own.",
        "schema": obj({"alignment": NSTR, "anchor": ANCHOR, "kind": KIND, "space": SPACE,
                       "viewport": NSTR, "side": SIDE, "label_offset": NUM,
                       "rotation": ROTATION, "content": STR,
                       "sheet": {**NSTR, "description": "for a referenced alignment: "
                                 "also say where the anchor falls on that sheet "
                                 "(on_sheet)"}}, ["anchor"]),
        "example": {"alignment": "ALIGN-1", "anchor": "PC-1"},
    },
    "get_design_data": {
        "description": "Tabular design data: alignments, curves (Δ/R/T/L/E/M/C, "
                       "bearings, PC/PI/PT/MC stations), tangents, station "
                       "equations, named anchors, profiles, PVIs, vertical curves. "
                       "Stations are raw + display text. Paginated (default 50). "
                       "kind defaults to 'alignments', the overview. ""An alignment in an attached basefile is named 'REFNAME:ALIGNMENT' (list_alignments include_references=true shows them); its points come back in host coordinates, while stations, lengths and bearings are as designed. "
                       "A profile in one is named 'REFNAME:PROFILE' (the profiles list_alignments "
                       "shows on a referenced alignment); profile alone reads it, or give the "
                       "referenced alignment and the profile's own name.",
        "schema": obj({"kind": {"enum": list(DESIGN_DATA_KINDS)}, "alignment": NSTR,
                       "profile": NSTR, "start": {"type": "integer", "minimum": 0},
                       "limit": {"type": "integer", "minimum": 1, "maximum": 500}}),
        "example": {"kind": "curves", "alignment": "ALIGN-1"},
    },
    "list_annotation_scales": {
        "description": "The annotation scale list, the current scale, the paper-unit "
                       "defaults with their model equivalents, and how many model "
                       "entities are annotative.",
        "schema": obj({}), "example": {},
    },
    "export_landxml": {
        "description": "Export the design model (alignments + profiles) as LandXML "
                       "1.2 (USSurveyFoot); opens in Civil 3D / ORD.",
        "schema": obj({"path": STR, "alignments": {"type": "array", "items": NSTR},
                       "include_xml": BOOL, "include_base64": BOOL}),
        "example": {},
    },
}


#: inside ``journals_beside_saves``: the journals save_document has written
_SAVED_JOURNALS: ContextVar[Optional[List[Path]]] = ContextVar("saved_journals", default=None)


@contextmanager
def journals_beside_saves() -> Iterator[List[Path]]:
    """While inside, save_document also writes the saving session's journal
    beside the document it saves (``journal_path``), so a scripted solution
    that edits more than the document it was handed -- a base file loaded,
    changed and saved, as an agent does with open_document -- keeps every
    file's commands. Yields the journals written, each once, in order."""
    written: List[Path] = []
    token = _SAVED_JOURNALS.set(written)
    try:
        yield written
    finally:
        _SAVED_JOURNALS.reset(token)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "untitled"


_RATIO_RE = re.compile(r"^1\s*:\s*(\d+(?:\.\d+)?)$")
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")
_FIT_TOL_IN = 1e-6   # a plot that overruns by less than this still fits


def _is_fit(value) -> bool:
    return isinstance(value, str) and value.strip().lower() == "fit"


def _paper_scale(value) -> float:
    """Printed inches per sheet inch, from 0.5, '1:2', '50%', 'half' or '1:1'.
    (Model space scales in feet per inch instead -- annotation.parse_scale.)"""
    if isinstance(value, bool):
        raise ValueError(f"plot scale must be a number or '1:2', not {value!r}")
    if isinstance(value, (int, float)):
        scale = float(value)
    else:
        text = str(value).strip().lower()
        ratio, percent = _RATIO_RE.match(text), _PERCENT_RE.match(text)
        if text in ("half", "half size", "half-size"):
            scale = 0.5
        elif text in ("full", "full size", "full-size"):
            scale = 1.0
        elif ratio and float(ratio.group(1)) > 0:
            scale = 1.0 / float(ratio.group(1))
        elif percent:
            scale = float(percent.group(1)) / 100.0
        else:
            raise ValueError(f"cannot read plot scale {value!r}; use 'fit', 1, "
                             f"0.5, '1:2' or '50%'")
    if scale <= 0:
        raise ValueError("plot scale must be positive")
    return scale


def _paper_scale_text(scale: float) -> str:
    if abs(scale - 1.0) < 1e-9:
        return "1:1 (full size)"
    if abs(scale - 0.5) < 1e-9:
        return "1:2 (half size)"
    return f"1:{1 / scale:.4g}" if scale < 1 else f"{scale:.4g}:1"


def _round_up(value: float, places: int = 2) -> float:
    """Round away from zero so a suggested scale always still fits."""
    factor = 10 ** places
    return int(value * factor + 0.999999) / factor


def _next_standard_scale(feet_per_inch: float):
    """The smallest standard plot scale no tighter than this one, so a print
    that does not fit can be sent to a real drawing scale."""
    return next((s for s in sorted(DEFAULT_SCALES) if s >= feet_per_inch - 1e-9),
                None)


class Session:
    def __init__(self, project_name: str = "Untitled", out_dir=None,
                 _document: Optional[Document] = None):
        self.bus = CommandBus(_document or Document.new(project_name))
        self.out_dir = Path(out_dir) if out_dir else Path.cwd() / "renders"
        #: The folder a relative file path resolves against. None is the
        #: working directory, as the REPL, the MCP server and the tests expect;
        #: the GUI points it at the drawing's own folder, because an app opened
        #: from Finder runs in '/'.
        self.base_dir: Optional[Path] = None
        #: journal records from before this session began: a document opened
        #: again over MCP carries what was journaled for it earlier, so its
        #: journal keeps every pass over the file (journal_records)
        self.journal_history: List[dict] = []
        self._validators = {}

    @property
    def doc(self) -> Document:
        return self.bus.doc

    # ----------------------------------------------------------- commands

    def execute(self, name: str, params: Optional[dict] = None) -> dict:
        return self.bus.execute(name, params)

    def execute_json(self, call: dict) -> dict:
        return self.bus.execute_json(call)

    # ------------------------------------------------------------ queries

    def query(self, name: str, params: Optional[dict] = None) -> dict:
        params = params or {}
        spec = QUERIES.get(name)
        if spec is None:
            return {"ok": False, "name": name, "error": {
                "type": "unknown_query",
                "message": f"unknown query {name!r}",
                "hint": f"valid queries: {sorted(QUERIES)}"}}
        if name not in self._validators:
            self._validators[name] = jsonschema.Draft202012Validator(spec["schema"])
        error = best_match(self._validators[name].iter_errors(params))
        if error is not None:
            return {"ok": False, "name": name, "error": {
                "type": "invalid_params", "message": error.message,
                "valid_params_schema": spec["schema"], "example": spec["example"]}}
        try:
            data = getattr(self, f"_q_{name}")(params)
        except _QueryFault as fault:
            return {"ok": False, "name": name, "error": {
                "type": "query_failed", "message": str(fault), "hint": fault.hint}}
        return {"ok": True, "name": name, **data}

    def manifest(self) -> dict:
        return {
            "commands": CommandBus.manifest(),
            "queries": [{
                "name": name, "kind": "query",
                "description": spec["description"],
                "params_schema": spec["schema"], "example": spec["example"],
            } for name, spec in QUERIES.items()],
        }

    # ---------------------------------------------------- query implementations

    def _q_get_document_state(self, p):
        if p.get("detail") == "full":
            return {"document": self.doc.to_dict()}
        doc = self.doc
        path = getattr(doc, "_path", None)
        return {"summary": {
            "document": Path(path).name if path else None,
            "meta": dict(doc.meta),
            "settings": dict(doc.settings),
            "layers": sorted(doc.layers),
            "text_styles": sorted(doc.text_styles),
            "blocks": sorted(doc.blocks),
            "sheets": [{"id": s.id, "name": s.name, "size": s.size,
                        "entities": len(s.entities), "viewports": len(s.viewports)}
                       for s in doc.sheets.values()],
            "model_entity_count": len(doc.model_entities),
            "model_extents": doc.extents("model"),
            "alignments": list(doc.design.alignments),
            "profiles": list(doc.design.profiles),
            "annotation_scale": doc.settings.get("annotation_scale"),
            "journal_length": len(self.bus.journal),
        }}

    def _q_get_model_state(self, p):
        from roaddraft.core import geometry as geo
        entities = [(e, self.doc, None) for e in self.doc.model_entities.values()]
        if p.get("include_references"):
            entities += self._reference_elements("model")
        if "bounds" in p:
            b = tuple(p["bounds"])
            entities = [(e, owner, ref) for e, owner, ref in entities
                        if e.bbox(owner) is not None
                        and geo.bbox_intersects(e.bbox(owner), b)]
        out = []
        for entity, _owner, ref in entities:
            d = entity.to_dict()
            if ref is not None:
                d["id"] = f"{ref}:{d['id']}"
                d["reference"] = ref
                d["read_only"] = True
            out.append(d)
        return {"count": len(out), "entities": out}

    def _reference_elements(self, space_key: str):
        """``[(primitive, basefile, reference name)]`` for everything the
        attachments in ``space_key`` display, in host coordinates."""
        from roaddraft.document.references import reference_groups
        found = []
        for ref, base, prims in reference_groups(self.doc, space_key):
            found += [(prim, base, ref.name) for prim in prims]
        return found

    def _q_find_entities(self, p):
        from roaddraft.core import geometry as geo
        from roaddraft.document import viewmap
        from roaddraft.document.locate import entity_length, representative_point

        space_ref = p.get("space", "model")
        resolved = self.doc.resolve_space(space_ref)
        if resolved is None:
            raise _QueryFault(f"space {space_ref!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        space_key, own = resolved
        candidates = [(e, self.doc, None) for e in own.values()]
        if p.get("include_references", True):
            candidates += self._reference_elements(space_key)

        bounds = tuple(p["bounds"]) if "bounds" in p else None
        shown_on = None
        if "visible_on" in p:
            if space_key != "model":
                raise _QueryFault(
                    "visible_on filters model entities by what a sheet shows",
                    hint="drop space (it defaults to model), or drop visible_on to "
                         "list a sheet's own entities")
            shown_on = self._sheet(p["visible_on"])
            window = self._visible_window(p["visible_on"])
            bounds = window if bounds is None else (
                max(bounds[0], window[0]), max(bounds[1], window[1]),
                min(bounds[2], window[2]), min(bounds[3], window[3]))

        layers = _as_set(p.get("layer"))
        types = _as_set(p.get("type"))
        anchor_filter = p.get("anchor") or {}
        contains = (p.get("content_contains") or "").lower()

        matches = []
        for entity, owner, ref in candidates:
            if layers is not None and entity.layer not in layers:
                continue
            if types is not None and entity.TYPE not in types:
                continue
            if anchor_filter and not _anchor_matches(entity.anchor, anchor_filter):
                continue
            if contains:
                content = getattr(entity, "content", None)
                if not isinstance(content, str) or contains not in content.lower():
                    continue
            if bounds is not None:
                bb = entity.bbox(owner)
                if bb is None or not geo.bbox_intersects(bb, bounds):
                    continue
            if shown_on is not None and not any(
                    viewmap.is_visible(owner, entity, vp) for vp in shown_on.viewports) \
                    and _text_view(owner, entity, shown_on) is None:
                continue  # in the window's bounding box, but not in the window
            matches.append((entity, owner, ref))

        total = len(matches)
        start = int(p.get("start", 0))
        limit = int(p.get("limit", 50))
        page = matches[start:start + limit]
        full = p.get("detail") == "full"

        rows = []
        for entity, owner, ref in page:
            eid = f"{ref}:{entity.id}" if ref else entity.id
            row = {"id": eid, "type": entity.TYPE, "layer": entity.layer}
            try:
                row["point"] = [round(v, 4) for v in representative_point(owner, entity)]
            except ValueError:
                pass
            length = entity_length(owner, entity)
            if length is not None:
                row["length"] = round(length, 4)
            lettered = _lettering(owner, entity)
            if shown_on is not None:
                seen = self._entity_on_sheet(shown_on, owner, entity, "mid")
                if seen is not None:
                    row.update(seen[0])
                if lettered is not None:
                    # through the viewport the row names: the one the entity is seen
                    # through, or, for a dimension whose middle no view shows, the one
                    # that shows its number
                    through = shown_on.viewport_by_id(seen[0]["viewport"]) if seen is not None \
                        else _text_view(owner, entity, shown_on)
                    if through is not None:
                        row.setdefault("viewport", through.id)
                        row["paper_corners"] = _paper_corners(owner, lettered, through)
            elif space_key != "model" and lettered is not None:
                row["paper_corners"] = _paper_corners(owner, lettered)
            if entity.anchor:
                row["anchor"] = dict(entity.anchor)
            content = getattr(entity, "content", None)
            if isinstance(content, str):
                row["content"] = content if len(content) <= 60 else content[:57] + "..."
            if ref:
                row["reference"] = ref
                row["read_only"] = True
            if full:
                row["entity"] = entity.to_dict()
                row["bbox"] = entity.bbox(owner)
            rows.append(row)

        out = {"space": space_key, "total": total, "count": len(rows), "entities": rows}
        if start + len(rows) < total:
            out["more"] = {"start": start + len(rows), "remaining": total - start - len(rows)}
        return out

    def _visible_window(self, sheet_ref: str):
        """The model region a sheet's viewports show (union)."""
        sheet = self._sheet(sheet_ref)
        boxes = [vp.transform().visible_model_bbox(vp.width_in, vp.height_in)
                 for vp in sheet.viewports]
        if not boxes:
            raise _QueryFault(f"sheet {sheet.name} has no viewport",
                              hint="create_viewport first, or drop visible_on")
        from roaddraft.core import geometry as geo
        window = boxes[0]
        for box in boxes[1:]:
            window = geo.bbox_union(window, box)
        return window

    def _on_sheet(self, sheet_ref, model_point, viewport=None) -> dict:
        """Where a model point falls on a sheet: the ``on_sheet`` block."""
        from roaddraft.document import viewmap
        sheet = self._sheet(sheet_ref)
        if not sheet.viewports:
            raise _QueryFault(f"sheet {sheet.name} has no viewport to see the model "
                              f"through", hint="create_viewport first")
        try:
            vp = viewmap.viewport_showing(sheet, model_point, viewport)
        except viewmap.ViewError as ex:
            raise _QueryFault(str(ex), hint=ex.hint)
        visible = vp is not None and viewmap.shows(vp, model_point)
        vp = vp or sheet.viewports[0]
        q = vp.transform().to_paper(model_point)
        out = {"sheet": sheet.name, "viewport": vp.id,
               "sheet_point": [round(v, 6) for v in q], "visible": visible,
               "feet_per_inch": vp.feet_per_inch, "rotation_deg": vp.rotation_deg}
        if not visible:
            out["note"] = (f"no viewport of {sheet.name} shows this point; sheet_point "
                           f"is where {vp.id} would put it, outside its window. "
                           + viewmap.describe_windows(sheet))
        return out

    def _entity_on_sheet(self, sheet, owner, entity, where, viewport=None):
        """``(block, model point, direction)`` for the part of an entity a sheet
        shows, or None when it shows none of it. The block's ``sheet_point`` is
        the point place_callout aims at from that sheet; ``shown`` is how much
        of the entity's length the viewport shows."""
        from roaddraft.document import viewmap
        vp = viewmap.viewport_showing_entity(sheet, owner, entity, viewport)
        seen = None if vp is None else viewmap.point_at_visible(owner, entity, where, vp)
        if seen is None:
            return None
        point, direction, shown = seen
        q = vp.transform().to_paper(point)
        return ({"sheet_point": [round(v, 4) for v in q], "viewport": vp.id,
                 "shown": round(shown, 4)}, point, direction)

    def _q_model_to_sheet(self, p):
        point = [float(v) for v in p["point"]]
        return {"point": point, **self._on_sheet(p["sheet"], point, p.get("viewport"))}

    def _q_sheet_to_model(self, p):
        from roaddraft.document import viewmap
        sheet = self._sheet(p["sheet"])
        if not sheet.viewports:
            raise _QueryFault(f"sheet {sheet.name} has no viewport to see the model "
                              f"through", hint="create_viewport first")
        q = [float(v) for v in p["point"]]
        try:
            vp = viewmap.viewport_under(sheet, q, p.get("viewport"))
        except viewmap.ViewError as ex:
            raise _QueryFault(str(ex), hint=ex.hint)
        inside = vp is not None and viewmap.in_window(vp, q)
        vp = vp or sheet.viewports[0]
        model_point = vp.transform().to_model(q)
        out = {"sheet": sheet.name, "sheet_point": q, "viewport": vp.id, "inside": inside,
               "point": [round(v, 6) for v in model_point],
               "feet_per_inch": vp.feet_per_inch, "rotation_deg": vp.rotation_deg}
        if not inside:
            out["note"] = (f"the point is outside every viewport window of {sheet.name}; "
                           f"this is what {vp.id} would map it to")
            return out
        from roaddraft.document.locate import nearest_entity
        hit = nearest_entity(self.doc, "model", model_point)
        if hit is not None:
            out["nearest"] = {"id": hit[0], "distance_ft": round(hit[1], 4),
                              "distance_in": round(hit[1] / vp.feet_per_inch, 4)}
        return out

    def _q_point_on_entity(self, p):
        from roaddraft.document.locate import entity_length, point_at
        eid = p["id"]
        found = self.doc.find_entity(eid)
        if found is not None:
            owner, entity = self.doc, found[1]
            space_key, ref = found[0], None
        else:
            from roaddraft.document.locate import resolve_entity
            element = resolve_entity(self.doc, eid)
            if element is None:
                raise _QueryFault(f"entity {eid!r} not found",
                                  hint="find_entities and hit_test return ids; "
                                       "reference elements are 'REFNAME:ID'")
            entity, owner, ref, space_key = element
        on_sheet = None
        try:
            if "sheet" in p:
                from roaddraft.document import viewmap
                sheet = self._sheet(p["sheet"])
                if space_key != "model":
                    raise _QueryFault(
                        f"{eid} is not in the model, so no sheet sees it through a "
                        f"viewport", hint="drop sheet: its point is already in its "
                                          "own space")
                seen = self._entity_on_sheet(sheet, owner, entity,
                                             p.get("where", "mid"), p.get("viewport"))
                if seen is None:
                    raise _QueryFault(
                        f"{eid} is not visible on {sheet.name}",
                        hint=f"find_entities with visible_on={sheet.name!r} lists what "
                             f"it shows; {viewmap.describe_windows(sheet)}")
                on_sheet, point, direction = seen
            else:
                if "viewport" in p:
                    raise _QueryFault("viewport goes with sheet")
                point, direction = point_at(owner, entity, p.get("where", "mid"))
        except ValueError as ex:
            hint = getattr(ex, "hint", None) or "where is start|mid|end or a fraction 0-1"
            raise _QueryFault(str(ex), hint=hint)
        out = {"id": eid, "space": space_key, "type": entity.TYPE,
               "where": p.get("where", "mid"),
               "point": [round(v, 6) for v in point],
               "direction_deg": None if direction is None else round(direction, 6)}
        length = entity_length(owner, entity)
        if length is not None:
            out["length"] = round(length, 6)
        if ref:
            out["reference"] = ref
            out["read_only"] = True
        if on_sheet is not None:
            out["on_sheet"] = {"sheet": self._sheet(p["sheet"]).name, **on_sheet}
        return out

    def _q_measure(self, p):
        from roaddraft.core import geometry as geo
        from roaddraft.core.units import format_length
        from roaddraft.design.angles import direction_of, format_bearing, format_dms
        from roaddraft.document.entities import Arc, Circle

        fmt = p.get("unit_format", "feet")
        precision = int(p.get("precision", 2))
        if "along" in p:
            return self._measure_along(p)
        if "entity" in p:
            entity, owner, ref, space_key = self._locate(p["entity"])
            from roaddraft.document.locate import entity_length, point_at
            out = {"entity": p["entity"], "space": space_key, "type": entity.TYPE}
            length = entity_length(owner, entity)
            if length is not None:
                out["length"] = round(length, 6)
                out["text"] = format_length(length, fmt, precision)
                out["start"] = [round(v, 6) for v in point_at(owner, entity, "start")[0]]
                out["end"] = [round(v, 6) for v in point_at(owner, entity, "end")[0]]
            if isinstance(entity, (Arc, Circle)):
                out["center"] = [round(v, 6) for v in entity.center]
                out["radius"] = round(entity.radius, 6)
                out["diameter"] = round(2.0 * entity.radius, 6)
            if isinstance(entity, Arc):
                start, end = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
                out["sweep_deg"] = round(end - start, 6)
                out["sweep"] = format_dms(end - start)
            if ref:
                out["reference"] = ref
                out["read_only"] = True
            return out
        if "from" not in p or "to" not in p:
            raise _QueryFault("measure needs 'from' and 'to', or a single 'entity'",
                              hint="each of from/to is a point [x, y] or an entity id; "
                                   "from_at/to_at say where on the entity")
        a = self._measure_point(p, "from", "from_at")
        b = self._measure_point(p, "to", "to_at")
        distance = geo.distance(a, b)
        direction = direction_of(a, b)
        return {"from": [round(v, 6) for v in a], "to": [round(v, 6) for v in b],
                "distance": round(distance, 6),
                "text": format_length(distance, fmt, precision),
                "dx": round(b[0] - a[0], 6), "dy": round(b[1] - a[1], 6),
                "direction_deg": round(direction, 6),
                "azimuth_deg": round((90.0 - direction) % 360.0, 6),
                "bearing": format_bearing((90.0 - direction) % 360.0)}

    def _measure_point(self, p, key, at_key):
        """One end of a measurement: a literal point, or a place on an entity."""
        from roaddraft.document.locate import point_at
        value = p[key]
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise _QueryFault(f"{key} must be a point [x, y] or an entity id, "
                                  f"got {value!r}")
            return [float(value[0]), float(value[1])]
        entity, owner, _ref, _space = self._locate(str(value))
        try:
            return point_at(owner, entity, p.get(at_key, "mid"))[0]
        except ValueError as ex:
            raise _QueryFault(str(ex),
                              hint=f"{at_key} is start|mid|end or a fraction 0-1")

    def _measure_along(self, p):
        """Points measured against a line, a chain or an alignment: along it
        and square off it."""
        from roaddraft.core.geometry import distance
        from roaddraft.core.units import format_length, format_station
        from roaddraft.design.angles import direction_to_azimuth, format_bearing
        from roaddraft.design.errors import DesignError
        from roaddraft.document import paths
        from roaddraft.document.locate import resolve_entity
        if "entity" in p:
            raise _QueryFault("entity measures one entity on its own; along measures points "
                              "against a line -- give from (and to) with along")
        if "from" not in p:
            raise _QueryFault("measuring along needs from (and to, for the distance between "
                              "two points)",
                              hint="from/to are points [x, y] or entity ids")
        fmt = p.get("unit_format", "feet")
        precision = int(p.get("precision", 2))
        points = [("from", self._measure_point(p, "from", "from_at"))]
        if "to" in p:
            points.append(("to", self._measure_point(p, "to", "to_at")))
        target = p["along"]
        out = {}
        rows = {}
        if isinstance(target, list) or resolve_entity(self.doc, str(target)) is not None:
            ids = list(target) if isinstance(target, list) else [str(target)]
            if not ids:
                raise _QueryFault("along needs at least one entity id")
            entities = [self._locate(str(eid))[0] for eid in ids]
            try:
                path = paths.Path.of_chain(entities) if len(entities) > 1 \
                    else paths.Path.of_entity(entities[0])
            except paths.PathError as e:
                raise _QueryFault(str(e), hint=e.hint)
            out["along"] = ids if isinstance(target, list) else ids[0]
            out["length"] = round(path.length, 6)
            for key, point in points:
                proj = path.project(point)
                row = {"point": [round(v, 6) for v in point],
                       "along": round(proj.along, 6), "offset": round(proj.offset, 6),
                       "side": proj.side, "foot": [round(v, 6) for v in proj.foot],
                       "perpendicular": proj.perpendicular,
                       "bearing": format_bearing(direction_to_azimuth(proj.direction))}
                if proj.beyond:
                    row["beyond"] = proj.beyond
                rows[key] = row
        else:
            a, placement = self._alignment_placed({"alignment": target})
            out["along"] = str(target)
            out["alignment"] = a.name
            for key, point in points:
                base = point if placement.is_identity else placement.to_base(point)
                try:
                    r = a.xy_to_station(base)
                except DesignError as e:
                    raise _QueryFault(str(e), hint=e.hint)
                disp, _region = a.stations().to_display(r["station"])
                foot = r["on_point"] if placement.is_identity else placement.to_host(r["on_point"])
                off = r["offset"]
                rows[key] = {"point": [round(v, 6) for v in point],
                             "along": round(r["station"] - a.begin_station, 6),
                             "station": round(r["station"], 6),
                             "station_text": format_station(disp),
                             "offset": round(off, 6),
                             "side": "on" if abs(off) < 1e-9 else ("right" if off > 0 else "left"),
                             "foot": [round(v, 6) for v in foot], "perpendicular": True,
                             "bearing": format_bearing(direction_to_azimuth(r["direction_deg"]))}
        for key, row in rows.items():
            row["offset_text"] = (f"{format_length(abs(row['offset']), fmt, precision)} "
                                  f"{row['side'].upper() if row['side'] != 'on' else 'ON'}")
            out[key] = row
        if "to" in rows:
            a_from, a_to = rows["from"], rows["to"]
            along = a_to["along"] - a_from["along"]
            across = a_to["offset"] - a_from["offset"]
            straight = distance(a_from["point"], a_to["point"])
            out.update(
                along_distance=round(abs(along), 6), along_change=round(along, 6),
                along_text=format_length(abs(along), fmt, precision),
                perpendicular_distance=round(abs(across), 6),
                offset_change=round(across, 6),
                perpendicular_text=format_length(abs(across), fmt, precision),
                distance=round(straight, 6),
                text=format_length(straight, fmt, precision))
        return out

    def _q_traverse(self, p):
        from roaddraft.commands import edit_handlers as eh
        from roaddraft.commands.handlers import CommandFault
        try:
            traverse, described = eh.compute_traverse(self.doc, p)
        except CommandFault as fault:
            raise _QueryFault(str(fault), hint=fault.hint)
        courses = [c.to_dict() for c in traverse.courses]
        out = {"start": [round(v, 6) for v in traverse.start], "from": described,
               "courses": courses, "end": [round(v, 6) for v in traverse.end],
               "length": round(traverse.length, 6),
               "points": [[round(v, 6) for v in traverse.start]]
               + [c["end"] for c in courses]}
        m = traverse.misclosure()
        if p.get("close") or m["distance"] <= 1.0:
            out["closure"] = {k: (round(v, 6) if isinstance(v, float) else v)
                              for k, v in m.items()}
            out["closure"]["text"] = eh.closure_text(traverse)
            if traverse.closing is not None:
                out["closing_course"] = traverse.closing.to_dict()
        return out

    def _q_key_points(self, p):
        from roaddraft.document import snaps
        kinds = set(p["kinds"]) if "kinds" in p else None
        given = [k for k in ("id", "ids", "alignment") if k in p]
        if len(given) > 1:
            raise _QueryFault("give one of id, ids or alignment (or neither, for a space)")
        notes = []
        rows = []
        if "alignment" in p:
            a, placement = self._alignment_placed(p)
            rows = snaps.alignment_key_points(a, p["alignment"], placement)
        else:
            if given:
                ids = [p["id"]] if "id" in p else list(p["ids"])
                items = []
                for eid in ids:
                    entity, owner, _ref, _space = self._locate(eid)
                    items.append(snaps.Item(eid, entity, owner))
            else:
                space_ref = p.get("space", "model")
                resolved = self.doc.resolve_space(space_ref)
                if resolved is None:
                    raise _QueryFault(f"space {space_ref!r} not found",
                                      hint=f"valid spaces: {self.doc.space_refs()}")
                items = snaps.space_items(self.doc, resolved[0],
                                          p.get("include_references", True),
                                          tuple(p["bounds"]) if "bounds" in p else None)
            for item in items:
                rows += snaps.entity_key_points(item.entity, item.eid)
            if len(items) > 1 and (kinds is None or "intersection" in kinds):
                if len(items) <= 400:
                    rows += snaps.intersection_points(items)
                else:
                    notes.append(f"{len(items)} entities: intersections are listed for 400 "
                                 f"or fewer -- narrow with bounds or ids")
            if not given and p.get("space", "model") == "model" and \
                    (kinds is None or "design" in kinds):
                design = snaps.design_key_points(self.doc)
                if "bounds" in p:
                    b = p["bounds"]
                    design = [sp for sp in design
                              if b[0] <= sp.point[0] <= b[2] and b[1] <= sp.point[1] <= b[3]]
                rows += design
        if kinds is not None:
            rows = [sp for sp in rows if sp.kind in kinds]
        limit = int(p.get("limit", 200))
        out = {"total": len(rows), "count": min(len(rows), limit),
               "points": [sp.to_dict() for sp in rows[:limit]]}
        if notes:
            out["notes"] = notes
        return out

    def _q_snap(self, p):
        from roaddraft.document import snaps
        space_ref = p.get("space", "model")
        resolved = self.doc.resolve_space(space_ref)
        if resolved is None:
            raise _QueryFault(f"space {space_ref!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        space_key = resolved[0]
        tolerance = float(p.get("tolerance", 5.0 if space_key == "model" else 0.1))
        modes = list(p.get("modes", snaps.DEFAULT_MODES))
        from_point = p.get("from")
        if from_point is None and set(modes) & set(snaps.FROM_MODES) \
                and "modes" in p and set(modes) <= set(snaps.FROM_MODES):
            raise _QueryFault("perpendicular and tangent snaps need from: the point the "
                              "line is drawn from")
        if "viewport" in p and space_key == "model":
            raise _QueryFault("viewport is for snapping on a sheet through to the model")
        include = p.get("include_references", True)
        try:
            found = snaps.snap(self.doc, space_key, p["point"], tolerance, modes,
                               from_point, include, p.get("viewport"),
                               pool_for=lambda key: self._snap_pool(key, include))
        except Exception as ex:  # a bad viewport name
            hint = getattr(ex, "hint", None)
            raise _QueryFault(str(ex), hint=hint)
        if not found:
            return {"snapped": False, "space": space_key,
                    "point": [round(v, 6) for v in p["point"]], "candidates": [],
                    "hint": f"nothing to snap to within {tolerance:g}; raise tolerance, or "
                            f"add modes such as nearest"}
        best = found[0]
        return {"snapped": True, "space": space_key, **best.to_dict(),
                "candidates": [sp.to_dict() for sp in found[1:8]]}

    def _snap_pool(self, space_key: str, include_references: bool):
        """What a space offers to snap to, made once per document state.

        A cursor asks for a snap many times a second, and re-reading every
        attachment each time is most of the cost. Every change goes through
        the journal -- undo, redo and reload_references included -- and an
        undo swaps in a new document, so (document, journal length) names a
        state exactly; attachments are cached on the document the same way."""
        from roaddraft.document import snaps
        state = (id(self.doc), len(self.bus.journal))
        if getattr(self, "_pools_state", None) != state:
            self._pools_state, self._pools = state, {}
        key = (space_key, include_references)
        if key not in self._pools:
            self._pools[key] = snaps.space_items(self.doc, space_key, include_references)
        return self._pools[key]

    def _locate(self, eid: str):
        """``(entity, owning document, reference name or None, space)``."""
        from roaddraft.document.locate import resolve_entity
        element = resolve_entity(self.doc, eid)
        if element is None:
            raise _QueryFault(f"entity {eid!r} not found",
                              hint="find_entities and hit_test return ids; reference "
                                   "elements are 'REFNAME:ID'")
        return element

    def _q_get_sheet_state(self, p):
        from roaddraft.render.titleblock import template_keys
        sheet = self._sheet(p["sheet"])
        state = sheet.to_dict()
        state["usable_area"] = sheet.usable_area()
        # what fill_title_block can letter on this sheet's border
        state["title_block_keys"] = list(template_keys(
            (sheet.title_block_template or "standard").lower()))
        for vp_state, vp in zip(state["viewports"], sheet.viewports):
            vp_state["visible_model_bbox"] = vp.transform().visible_model_bbox(
                vp.width_in, vp.height_in)
        return {"sheet": state}

    def _q_get_entity(self, p):
        found = self.doc.find_entity(p["id"])
        if found is None:
            element = self._reference_element(p["id"])
            if element is not None:
                return element
            raise _QueryFault(f"entity {p['id']!r} not found",
                              hint="ids are listed by get_model_state / "
                                   "get_sheet_state; reference elements are "
                                   "'REFNAME:ID' as returned by hit_test")
        space_key, entity = found
        from roaddraft.document.inquiry import properties
        return {"space": space_key, "entity": entity.to_dict(),
                "bbox": entity.bbox(self.doc),
                "properties": properties(self.doc, entity, space_key)}

    def _reference_element(self, eid: str):
        """A basefile element seen through an attachment, in host coordinates
        (true-scaled, placed, symbology applied, clipped). Read-only."""
        from roaddraft.document.references import reference_groups
        name, sep, sub_id = eid.partition(":")
        if not sep:
            return None
        for ref in self.doc.references.values():
            if ref.name != name:
                continue
            for group_ref, base, prims in reference_groups(self.doc, ref.space):
                if group_ref.id != ref.id:
                    continue
                for prim in prims:
                    if prim.id == sub_id:
                        from roaddraft.document.inquiry import properties
                        return {"space": ref.space, "entity": prim.to_dict(),
                                "bbox": prim.bbox(base), "reference": ref.name,
                                "read_only": True,
                                "properties": properties(base, prim, ref.space)}
        return None

    def _q_area(self, p):
        from roaddraft.commands import cogo_handlers as ch
        from roaddraft.commands.handlers import CommandFault
        from roaddraft.document import regions
        ways = [k for k in ("ids", "points", "at") if k in p]
        if len(ways) != 1:
            raise _QueryFault("give the area with exactly one of ids, points or at",
                              hint="ids: closed entities or a chain that closes; points: a "
                                   "polygon; at: a point inside linework that closes around "
                                   "it")
        params = dict(p)
        if "ids" in params:
            params["boundary"] = params.pop("ids")
            space_key = self._locate(params["boundary"][0])[3]
        else:
            resolved = self.doc.resolve_space(p.get("space", "model"))
            if resolved is None:
                raise _QueryFault(f"space {p.get('space')!r} not found",
                                  hint=f"valid spaces: {self.doc.space_refs()}")
            space_key = resolved[0]
        try:
            loops, ids, how = ch.build_loops(self.doc, space_key, params)
        except CommandFault as fault:
            raise _QueryFault(str(fault), hint=fault.hint)
        m = regions.region_measure(loops)
        out = {"space": space_key, "area": round(m["area"], 6),
               "perimeter": round(m["perimeter"], 6),
               "centroid": [round(v, 6) for v in m["centroid"]] if m["centroid"] else None,
               "text": ch.area_text(m["area"], space_key), "boundary": how,
               "loops": [{"kind": row["kind"], "area": round(row["area"], 6),
                          "perimeter": round(row["perimeter"], 6)} for row in m["loops"]]}
        if ids:
            out["ids"] = ids
        if space_key == "model":
            out["square_yards"] = round(m["area"] / 9.0, 6)
            out["acres"] = round(m["area"] / 43560.0, 8)
        return out

    def _q_get_extents(self, p):
        from roaddraft.document.references import extents_with_references
        ref = p.get("space", "model")
        if self.doc.resolve_space(ref) is None:
            raise _QueryFault(f"space {ref!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        return {"space": ref, "extents": extents_with_references(self.doc, ref)}

    def _q_list_layers(self, p):
        return {"current_layer": self.doc.settings["current_layer"],
                "layers": [l.to_dict() for l in self.doc.layers.values()]}

    def _q_list_text_styles(self, p):
        return {"current_text_style": self.doc.settings["current_text_style"],
                "text_styles": [s.to_dict() for s in self.doc.text_styles.values()]}

    def _q_list_blocks(self, p):
        return {"blocks": [{"name": b.name, "base_point": list(b.base_point),
                            "entities": len(b.entities),
                            "description": b.description}
                           for b in self.doc.blocks.values()]}

    def _q_list_sheets(self, p):
        return {"sheets": [{"id": s.id, "name": s.name, "size": s.size,
                            "width_in": s.width_in, "height_in": s.height_in,
                            "entities": len(s.entities),
                            "viewports": len(s.viewports)}
                           for s in self.doc.sheets.values()]}

    def _q_list_references(self, p):
        from roaddraft.document.references import describe_reference
        out = [describe_reference(self.doc, ref)
               for ref in self.doc.references.values()]
        return {"count": len(out), "references": out}

    def _q_hit_test(self, p):
        from roaddraft.document.entities import entity_distance
        resolved = self.doc.resolve_space(p["space"])
        if resolved is None:
            raise _QueryFault(f"space {p['space']!r} not found",
                              hint=f"valid spaces: {self.doc.space_refs()}")
        space_key, entities = resolved
        tol = p.get("tolerance", 5.0)
        hits = []

        def inside_hatch(e, d):
            # a click inside a hatch picks it, but any linework near the click wins
            if e.TYPE == "hatch" and d > tol * 0.95:
                from roaddraft.document.regions import point_in_loop
                if sum(1 for loop in e.loops if point_in_loop(p["point"], loop)) % 2:
                    return tol * 0.95
            return d

        for e in entities.values():
            d = inside_hatch(e, entity_distance(self.doc, e, p["point"]))
            if d <= tol:
                hits.append({"id": e.id, "type": e.TYPE, "layer": e.layer,
                             "distance": round(d, 4)})
        if p.get("include_references", True):
            from roaddraft.document.references import reference_groups
            for ref, base, prims in reference_groups(self.doc, space_key):
                for e in prims:
                    d = inside_hatch(e, entity_distance(base, e, p["point"]))
                    if d <= tol:
                        hits.append({"id": f"{ref.name}:{e.id}", "type": e.TYPE,
                                     "layer": e.layer, "distance": round(d, 4),
                                     "reference": ref.name, "read_only": True})
        # a tie goes to the thing with a place of its own -- a point, a block, a
        # text set on a line -- over the line it sits on
        rank = {"point": 0, "blockref": 1, "text": 2}
        hits.sort(key=lambda h: (h["distance"], rank.get(h["type"], 3)))
        return {"count": len(hits), "hits": hits[:5]}

    def _q_get_journal(self, p):
        start = p.get("start", 1)
        entries = [e for e in self.bus.journal if e["seq"] >= start]
        return {"count": len(entries), "entries": entries}

    def _q_list_commands(self, p):
        return {"manifest": self.manifest()}

    def _q_render_sheet(self, p):
        sheet = self._sheet(p["sheet"])
        path = self._out_path(p.get("path"), f"{_slug(sheet.name)}.png")
        mpl_render.render_sheet_png(
            self.doc, sheet, path, dpi=p.get("dpi", 150),
            show_viewport_frames=p.get("show_viewport_frames", True))
        return self._file_result(path, p.get("include_base64", False))

    def _q_render_model(self, p):
        path = self._out_path(p.get("path"), "model.png")
        bounds = mpl_render.render_model_png(self.doc, path,
                                             bounds=p.get("bounds"),
                                             dpi=p.get("dpi", 150))
        result = self._file_result(path, p.get("include_base64", False))
        result["bounds"] = bounds
        return result

    def _q_export_dxf(self, p):
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.dxf")
        dxf_render.export_dxf(self.doc, path)
        return self._file_result(path, False)

    def _q_export_pdf(self, p):
        sheets = ([self._sheet(ref) for ref in p["sheets"]] if "sheets" in p
                  else list(self.doc.sheets.values()))
        if not sheets:
            raise _QueryFault("no sheets to export",
                              hint="create one with create_sheet")
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.pdf")
        mpl_render.export_pdf(self.doc, path, sheets)
        return self._file_result(path, False)

    def _q_print_pdf(self, p):
        if "space" in p and "sheets" in p:
            raise _QueryFault(
                "print one space or a list of sheets, not both",
                hint="space='model' or space='P-201' prints one; "
                     "sheets=['P-201', 'P-202'] prints a set; omit both to "
                     "print every sheet")
        space = p.get("space")
        if space == "model":
            targets = ["model"]
        elif space is not None:
            targets = [self._sheet(space)]
        elif "sheets" in p:
            targets = [self._sheet(ref) for ref in p["sheets"]]
        else:
            targets = list(self.doc.sheets.values())
            if not targets:
                raise _QueryFault(
                    "no sheets to print",
                    hint="create one with create_sheet, or print the design "
                         "itself with space='model'")
        if "bounds" in p and targets != ["model"]:
            raise _QueryFault(
                "bounds is a model-space window; a sheet prints whole",
                hint="print the design with space='model' and bounds=[x0, y0, "
                     "x1, y1], or drop bounds to print the sheet")

        setups = [self._page_setup(target, p) for target in targets]
        project = _slug(self.doc.meta["project_name"])
        if targets == ["model"]:
            default_name = f"{project}-model-print.pdf"
        elif len(targets) == 1:
            default_name = f"{_slug(targets[0].name)}-print.pdf"
        else:
            default_name = f"{project}-print.pdf"
        path = self._out_path(p.get("path"), default_name)
        mpl_render.print_pdf(self.doc, path, [page for page, _ in setups])
        result = self._file_result(path, False)
        result["page_count"] = len(setups)
        result["pages"] = [described for _, described in setups]
        result["monochrome"] = bool(p.get("monochrome", False))
        return result

    def _page_setup(self, target, p):
        """Resolve one page of a print job -- the paper, the scale that fits on
        it, and a plain description of both. A requested scale that would run
        off the paper faults with the scale that would not."""
        orientation = p.get("orientation", "landscape")
        margin = p.get("margin_in", 0.0)
        mono = bool(p.get("monochrome", False))
        scale = p.get("scale", "fit")
        wanted_paper = p.get("paper")
        is_model = target == "model"

        if is_model and wanted_paper == "sheet":
            raise _QueryFault(
                "paper='sheet' has no sheet to take a size from",
                hint="model space prints on a named paper, e.g. paper='ANSI_D'; "
                     f"sizes: {sorted(SHEET_SIZES)}")
        if is_model or (wanted_paper and wanted_paper != "sheet"):
            paper_name = wanted_paper or "ANSI_D"
            paper = mpl_render.paper_size(paper_name, orientation)
        else:                                   # the sheet's own paper, as drawn
            paper_name = target.size
            paper = (target.width_in, target.height_in)
        area = mpl_render.printable_area(paper, margin)
        if area[0] <= 0 or area[1] <= 0:
            raise _QueryFault(
                f"a {margin:g} in margin leaves no printable area on "
                f"{paper[0]:g} x {paper[1]:g} in paper",
                hint="use a smaller margin_in or a bigger paper")

        if is_model:
            bounds = mpl_render.model_window(self.doc, p.get("bounds"))
            width_ft, height_ft = bounds[2] - bounds[0], bounds[3] - bounds[1]
            fitted = max(width_ft / area[0], height_ft / area[1])
            if _is_fit(scale):
                feet_per_inch = fitted
            else:
                try:
                    feet_per_inch = parse_scale(scale)
                except ValueError as ex:
                    raise _QueryFault(
                        str(ex),
                        hint="model space plots at feet per inch: 50, "
                             "'1\"=50\'', '1:600' -- or 'fit'")
                printed = (width_ft / feet_per_inch, height_ft / feet_per_inch)
                if (printed[0] > area[0] + _FIT_TOL_IN
                        or printed[1] > area[1] + _FIT_TOL_IN):
                    standard = _next_standard_scale(fitted)
                    raise _QueryFault(
                        f"{width_ft:.1f} x {height_ft:.1f} ft at "
                        f"{format_scale(feet_per_inch)} needs {printed[0]:.2f} x "
                        f"{printed[1]:.2f} in, but {paper_name} gives "
                        f"{area[0]:.2f} x {area[1]:.2f} in",
                        hint=f"use scale='fit' (about "
                             f"{format_scale(_round_up(fitted))})"
                             + (f", scale={standard:g} ({format_scale(standard)})"
                                if standard else "")
                             + ", a bigger paper, or a smaller bounds window")
            page = {"kind": "model", "bounds": bounds, "paper": paper,
                    "feet_per_inch": feet_per_inch, "mono": mono}
            return page, {
                "space": "model", "paper": paper_name,
                "paper_in": [round(v, 4) for v in paper],
                "scale": format_scale(round(feet_per_inch, 4)),
                "feet_per_inch": round(feet_per_inch, 6),
                "window_ft": [round(v, 3) for v in bounds],
                "printed_in": [round(width_ft / feet_per_inch, 3),
                               round(height_ft / feet_per_inch, 3)]}

        sheet = target
        content = (sheet.width_in, sheet.height_in)
        fitted = mpl_render.fit_scale(content, area)
        if _is_fit(scale):
            paper_scale = fitted
        else:
            try:
                paper_scale = _paper_scale(scale)
            except ValueError as ex:
                raise _QueryFault(
                    str(ex),
                    hint="a sheet plots at printed inches per sheet inch: 1 "
                         "(full size), 0.5 / '1:2' (half size), '50%' -- or "
                         "'fit'")
            printed = (content[0] * paper_scale, content[1] * paper_scale)
            if (printed[0] > area[0] + _FIT_TOL_IN
                    or printed[1] > area[1] + _FIT_TOL_IN):
                raise _QueryFault(
                    f"sheet {sheet.name} ({content[0]:g} x {content[1]:g} in) at "
                    f"{_paper_scale_text(paper_scale)} needs {printed[0]:.2f} x "
                    f"{printed[1]:.2f} in, but {paper_name} gives "
                    f"{area[0]:.2f} x {area[1]:.2f} in",
                    hint=f"use scale='fit' (about "
                         f"{_paper_scale_text(fitted)}), a bigger paper, or a "
                         f"smaller margin_in")
        page = {"kind": "sheet", "sheet": sheet, "paper": paper,
                "scale": paper_scale, "mono": mono,
                "lw_scale": paper_scale if p.get("scale_lineweights") else 1.0}
        return page, {
            "space": sheet.name, "paper": paper_name,
            "paper_in": [round(v, 4) for v in paper],
            "scale": _paper_scale_text(paper_scale),
            "printed_in": [round(content[0] * paper_scale, 3),
                           round(content[1] * paper_scale, 3)]}

    def _q_save_document(self, p):
        target = fileformat.normalize_path(self._resolve(p["path"]))
        self._inside(target, p["path"])
        path = fileformat.write_document(target, self.doc.to_dict())
        self.doc._path = path.resolve()  # relative reference paths follow the host
        written = _SAVED_JOURNALS.get()
        if written is not None:
            journal = Path(self._q_save_journal(
                {"path": str(fileformat.journal_path(path))})["path"]).resolve()
            if journal not in written:
                written.append(journal)
        return self._file_result(path, False)

    def journal_records(self) -> List[dict]:
        """The journal: any earlier passes over the document
        (``journal_history``), then an ``init`` with the document as this
        session began and every command since. Replay starts at the last init."""
        return (list(self.journal_history)
                + [{"type": "init", "document": self.bus.baseline}]
                + [{"type": "command", **entry} for entry in self.bus.journal])

    def _q_save_journal(self, p):
        path = self._inside(self._resolve(p["path"]), p["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record) for record in self.journal_records()]
        path.write_text("\n".join(lines) + "\n")
        return self._file_result(path, False)

    # ------------------------------------------------- design model queries

    def _alignment_q(self, p):
        return self._alignment_placed(p)[0]

    def _alignment_placed(self, p, key: str = "alignment"):
        """``(alignment, placement)``, accepting ``"DESIGN:SR-100"`` for an
        alignment that lives in an attached basefile.

        Queries read a referenced design; commands do not. Nothing can be
        drawn, labelled or anchored to an alignment the host does not own --
        this is how to ask *where* something is in a sheet file, not a way to
        own it.
        """
        from roaddraft.commands import design_handlers as dh
        from roaddraft.commands.handlers import CommandFault
        from roaddraft.document.references import (
            Placement, find_reference_alignment, reference_alignments,
        )
        name = p.get(key)
        if isinstance(name, str) and ":" in name:
            found = find_reference_alignment(self.doc, name)
            if found is None:
                known = [f"{ref.name}:{a.name}"
                         for ref, _b, a, _pl in reference_alignments(self.doc)]
                raise _QueryFault(
                    f"no alignment {name!r} in any attached reference",
                    hint=(f"referenced alignments: {known}" if known else
                          "no attachment carries a design model; list_references "
                          "shows what is attached"))
            return found
        try:
            return dh._alignment(self.doc, p, key), Placement()
        except CommandFault as fault:
            if not self.doc.design.alignments:
                extra = [f"{ref.name}:{a.name}"
                         for ref, _b, a, _pl in reference_alignments(self.doc)]
                if extra:
                    raise _QueryFault(
                        str(fault),
                        hint=f"this document owns no alignments, but its references "
                             f"carry {extra} -- name one of those to read its design")
            raise _QueryFault(str(fault), hint=fault.hint)

    @staticmethod
    def _drawn(doc, name) -> bool:
        return any(e.anchor and e.anchor.get("alignment") == name
                   and e.anchor.get("kind") == "element"
                   for e in doc.model_entities.values())

    def _q_list_alignments(self, p):
        rows = [self._alignment_row(self.doc, a, a.name)
                for a in self.doc.design.alignments.values()]
        if p.get("include_references"):
            from roaddraft.document.references import reference_alignments
            for ref, base, alignment, placement in reference_alignments(self.doc):
                row = self._alignment_row(base, alignment, f"{ref.name}:{alignment.name}")
                # named the way get_design_data's profile takes them
                row["profiles"] = [f"{ref.name}:{name}" for name in row["profiles"]]
                row["reference"] = ref.name
                row["read_only"] = True
                row["placement"] = _placement_block(placement)
                rows.append(row)
        return {"count": len(rows), "alignments": rows}

    def _alignment_row(self, doc, a, name: str) -> dict:
        st = a.stations()
        return {
            "name": name, "description": a.description, "source": a.source,
            "begin_station": a.begin_station, "begin_station_text": st.begin_text(),
            "end_station": a.end_station, "end_station_text": st.end_text(),
            "length": a.length, "curves": len(a.curves()), "tangents": len(a.tangents()),
            "equations": len(a.equations),
            "profiles": [pr.name for pr in doc.design.profiles_of(a.name)],
            "drawn": self._drawn(doc, a.name)}

    def _q_station_to_xy(self, p):
        from roaddraft.core.units import format_station
        from roaddraft.design.angles import direction_to_azimuth, format_bearing
        from roaddraft.design.errors import DesignError
        a, placement = self._alignment_placed(p)
        st = a.stations()
        offset = float(p.get("offset", 0.0))
        try:
            raw = st.parse(p["station"], p.get("region"))
            point, direction, idx = a.station_to_xy(raw, offset)
            on_point, _, _ = a.station_to_xy(raw, 0.0)
        except DesignError as e:
            raise _QueryFault(str(e), hint=e.hint)
        disp, region = st.to_display(raw)
        az = direction_to_azimuth(direction)
        out = {"alignment": a.name, "point": _place_point(placement, point),
               "on_point": _place_point(placement, on_point), "station": raw,
               "station_text": format_station(disp), "region": region, "offset": offset,
               "direction_deg": direction, "azimuth_deg": az, "bearing": format_bearing(az),
               "element_index": idx, "element_kind": a.elements[idx].kind,
               "element_ref": a.element_ref(idx)}
        if "sheet" in p:
            out["on_sheet"] = self._on_sheet(p["sheet"], out["point"])
        return out

    def _q_xy_to_station(self, p):
        from roaddraft.core.units import format_station
        from roaddraft.design.errors import DesignError
        a, placement = self._alignment_placed(p)
        point = p["point"] if placement.is_identity else placement.to_base(p["point"])
        try:
            r = a.xy_to_station(point)
        except DesignError as e:
            raise _QueryFault(str(e), hint=e.hint)
        disp, region = a.stations().to_display(r["station"])
        off = r["offset"]
        side = "ON" if abs(off) < 1e-9 else ("R" if off > 0 else "L")
        idx = r["element_index"]
        return {"alignment": a.name, "station": r["station"],
                "station_text": format_station(disp), "region": region, "offset": off,
                "distance": abs(off), "side": side,
                "on_point": _place_point(placement, r["on_point"]),
                "direction_deg": r["direction_deg"], "element_index": idx,
                "element_kind": a.elements[idx].kind, "element_ref": a.element_ref(idx)}

    def _q_resolve_anchor(self, p):
        from roaddraft.commands import design_handlers as dh
        from roaddraft.commands.handlers import CommandFault
        from roaddraft.design.errors import DesignError
        from roaddraft.design.labels import label_content
        params = dict(p)
        params.setdefault("space", "model")
        name = params.get("alignment")
        if isinstance(name, str) and ":" in name:
            return self._resolve_referenced_anchor(params)
        try:
            plan = dh.plan_label(self.doc, params)
        except CommandFault as fault:
            raise _QueryFault(str(fault), hint=fault.hint)
        spec = plan["spec"]
        if spec.content_auto:
            auto = spec.content
        else:
            try:
                auto = label_content(plan["alignment"], plan["anchor_point"], plan["kind"])
            except DesignError:
                auto = None
        vp = plan["viewport"]
        return {"anchor": plan["anchor"], "kind": plan["kind"], "content": spec.content,
                "auto_content": auto, "space": plan["space_key"],
                "viewport": vp.id if vp is not None else None, "position": plan["position"],
                "rotation_deg": plan["rotation_deg"], "height": plan["height"],
                "halign": spec.halign, "valign": spec.valign,
                "anchor_point": list(spec.anchor_point), "direction_deg": spec.direction_deg}

    def _resolve_referenced_anchor(self, p):
        """Where a named point of a *referenced* alignment is, and what a label
        there would read.

        Deliberately not a label plan: nothing can be anchored to an alignment
        this document does not own, so there is no position, viewport or height
        to give -- only the design fact and the wording it implies.
        """
        from roaddraft.core.units import format_station
        from roaddraft.design.anchors import parse_anchor, resolve_anchor
        from roaddraft.design.errors import DesignError
        from roaddraft.design.labels import label_content
        alignment, placement = self._alignment_placed(p)
        try:
            ref = parse_anchor(p["anchor"])
            point = resolve_anchor(alignment, ref)
        except DesignError as e:
            raise _QueryFault(str(e), hint=e.hint)
        kind = p.get("kind") or point.kind_hint
        try:
            auto = label_content(alignment, point, kind)
        except DesignError:
            auto = None
        out = {"alignment": alignment.name, "anchor": point.ref, "kind": kind,
                "auto_content": auto, "content": p.get("content", auto),
                "station": point.station, "station_text": format_station(point.station)
                if point.station is not None else None,
                "offset": point.offset,
                "point": _place_point(placement, point.point),
                "anchor_point": _place_point(placement, point.on_point),
                "direction_deg": point.direction_deg,
                "placement": _placement_block(placement),
                "labelling": "place_label, annotate_stationing and place_curve_table anchor "
                             "to this referenced alignment by its qualified name (the "
                             "reference must sit at identity); place_callout takes it "
                             "as target_anchor too"}
        if "sheet" in p:
            out["on_sheet"] = self._on_sheet(p["sheet"], out["point"])
        return out

    def _design_rows(self, kind, aligns, profiles, owner=None, prefix: str = ""):
        """Rows of ``kind``. ``owner`` is the document whose design they come
        from (the host's, or a basefile's), and ``prefix`` (``'BASE:'``) names
        a referenced alignment's profiles the way ``profile`` takes them."""
        owner = owner if owner is not None else self.doc
        from roaddraft.core.units import format_station
        from roaddraft.design.anchors import list_anchors
        from roaddraft.design.horizontal import curve_data, tangent_data
        from roaddraft.design.stations import equation_label
        from roaddraft.design.vertical import vc_data
        rows = []
        if kind == "alignments":
            for a in aligns:
                st = a.stations()
                d = a.to_dict()
                d.pop("elements", None)
                d.update(length=a.length, end_station=a.end_station,
                         begin_station_text=st.begin_text(), end_station_text=st.end_text(),
                         curves=len(a.curves()), tangents=len(a.tangents()),
                         profiles=[prefix + pr.name for pr in owner.design.profiles_of(a.name)],
                         drawn=self._drawn(owner, a.name))
                rows.append(d)
        elif kind == "curves":
            for a in aligns:
                rows.extend(curve_data(a, n) for n in range(1, len(a.curves()) + 1))
        elif kind == "tangents":
            for a in aligns:
                rows.extend(tangent_data(a, n) for n in range(1, len(a.tangents()) + 1))
        elif kind == "equations":
            for a in aligns:
                for n, eq in enumerate(a.equations, start=1):
                    rows.append({"alignment": a.name, "index": n, "ref": f"EQ-{n}",
                                 "raw_station": eq.raw_station, "back": eq.back,
                                 "back_text": format_station(eq.back), "ahead": eq.ahead,
                                 "ahead_text": format_station(eq.ahead),
                                 "label": equation_label(eq)})
        elif kind == "anchors":
            for a in aligns:
                for ap in list_anchors(a):
                    rows.append({"alignment": a.name, "ref": ap.ref, "kind_hint": ap.kind_hint,
                                 "station": ap.station, "station_text": ap.station_text,
                                 "point": ap.point, "direction_deg": ap.direction_deg})
        else:
            for prof in profiles:
                parent = owner.design.alignments.get(prof.alignment)
                fmt = parent.stations().format if parent else format_station
                if kind == "profiles":
                    d = prof.to_dict()
                    n = len(prof.pvis)
                    s0, s1 = prof.station_range()
                    d.update(pvis=n, curves=max(n - 2, 0),
                             station_range_text=f"{fmt(s0)} to {fmt(s1)}")
                    rows.append(d)
                elif kind == "pvis":
                    pv = prof.pvis
                    for i, q in enumerate(pv):
                        g_in = ((q.elevation - pv[i - 1].elevation)
                                / (q.station - pv[i - 1].station) * 100.0) if i > 0 else None
                        g_out = ((pv[i + 1].elevation - q.elevation)
                                 / (pv[i + 1].station - q.station) * 100.0) \
                            if i + 1 < len(pv) else None
                        rows.append({"profile": prof.name, "alignment": prof.alignment,
                                     "index": i + 1, "ref": f"PVI-{i + 1}",
                                     "station": q.station, "station_text": fmt(q.station),
                                     "elevation": q.elevation, "length": q.length,
                                     "grade_in_pct": g_in, "grade_out_pct": g_out})
                elif kind == "vcs":
                    for n in range(1, max(len(prof.pvis) - 1, 0)):
                        row = vc_data(prof, n)
                        for key in ("pvi", "pvc", "pvt"):
                            row[f"{key}_station_text"] = fmt(row[f"{key}_station"])
                        row["high_low_station_text"] = (
                            fmt(row["high_low"]["station"]) if row["high_low"] else None)
                        rows.append(row)
        return rows

    def _q_get_design_data(self, p):
        # no kind is the question "what is this alignment?": answer it, and say
        # what else can be asked (the commonest fault in every agent run so far)
        kind = p.get("kind", "alignments")
        from roaddraft.document.references import Placement, reference_base
        # the design read: the host's own, or the basefile a qualified name
        # ('BASE:SR-100', 'BASE:SR-100 PGL') reads through
        placement, owner = Placement(), self.doc
        if "alignment" in p:
            one, placement = self._alignment_placed(p)
            if placement.reference:
                owner = reference_base(self.doc, placement.reference)
            aligns = [one]
        else:
            aligns = list(owner.design.alignments.values())
        names = {a.name for a in aligns}
        if "profile" in p:
            prof, prof_owner, prof_placement = self._profile_placed(p["profile"], owner,
                                                                    placement)
            profiles = [prof]
            if "alignment" not in p and prof_placement.reference:
                # a referenced profile alone reads its own basefile's alignment
                owner, placement = prof_owner, prof_placement
                aligns = [a for a in [owner.design.alignments.get(prof.alignment)] if a]
        else:
            prof_owner, prof_placement = owner, placement
            profiles = [pr for pr in owner.design.profiles.values()
                        if "alignment" not in p or pr.alignment in names]
        if kind in PROFILE_KINDS:
            owner, placement = prof_owner, prof_placement
        prefix = f"{placement.reference}:" if placement.reference else ""
        rows = self._design_rows(kind, aligns, profiles, owner, prefix)
        fields = DESIGN_POINT_FIELDS.get(kind, ())
        rows = [_place_row(placement, row, fields) for row in rows]
        start = int(p.get("start", 0))
        limit = int(p.get("limit", 50))
        out = {"kind": kind, "total": len(rows), "start": start, "limit": limit,
               "rows": rows[start:start + limit]}
        if "kind" not in p:
            out["other_kinds"] = [k for k in DESIGN_DATA_KINDS if k != kind]
        if not placement.is_identity or placement.reference:
            out["placement"] = _placement_block(placement)
        elif kind in PROFILE_KINDS and not rows and not self.doc.design.profiles:
            carried = self._referenced_profile_names()
            if carried:
                out["hint"] = (f"this document owns no profiles, but its references carry "
                               f"{carried} -- name one as profile to read it")
        return out

    def _profile_placed(self, name, owner, placement):
        """``(profile, owner, placement)``: ``owner``'s profile ``name`` (the
        host's, or that of the basefile a referenced alignment was read from,
        placed by ``placement``), else a referenced one, ``'BASE:SR-100 PGL'``."""
        from roaddraft.document.references import find_reference_profile
        if name in owner.design.profiles:
            return owner.design.profiles[name], owner, placement
        found = find_reference_profile(self.doc, name) if ":" in str(name) else None
        if found is not None:
            return found
        referenced = self._referenced_profile_names()
        if ":" in str(name):
            raise _QueryFault(f"no profile {name!r} in any attached reference",
                              hint=(f"referenced profiles: {referenced}" if referenced else
                                    "no attachment carries a design profile; "
                                    "list_references shows what is attached"))
        prefix = f"{placement.reference}:" if placement.reference else ""
        known = [prefix + k for k in owner.design.profiles]
        carried = [k for k in referenced if k not in known]
        if not known and carried:
            raise _QueryFault(f"no profile named {name!r}",
                              hint=f"this document owns no profiles, but its references "
                                   f"carry {carried} -- name one of those to read it")
        raise _QueryFault(f"no profile named {name!r}", hint=f"profiles: {known + carried}")

    def _referenced_profile_names(self) -> List[str]:
        from roaddraft.document.references import reference_profiles
        return [f"{ref.name}:{prof.name}" for ref, _b, prof, _pl in reference_profiles(self.doc)]

    def _q_list_annotation_scales(self, p):
        from roaddraft.document import annotation as anno
        doc = self.doc
        scale = anno.current_scale(doc)
        sizes = anno.model_sizes(doc)
        return {"current": scale, "current_name": anno.scale_name(doc, scale),
                "scales": anno.scale_list(doc), "paper": anno.paper_defaults(doc),
                "model_sizes": sizes or dict(anno.FIXED_MODEL_SIZES),
                "annotative_entities": sum(1 for e in doc.model_entities.values()
                                           if e.annotative)}

    def _q_export_landxml(self, p):
        from roaddraft.adapters.landxml import write_landxml
        design = self.doc.design
        aligns = list(design.alignments.values())
        if "alignments" in p:
            unknown = [n for n in p["alignments"] if n not in design.alignments]
            if unknown:
                raise _QueryFault(f"no alignment named {unknown[0]!r}",
                                  hint=f"alignments: {list(design.alignments)}")
            aligns = [design.alignments[n] for n in p["alignments"]]
        if not aligns:
            raise _QueryFault("no alignments to export",
                              hint="create_alignment or import_landxml first")
        names = {a.name for a in aligns}
        profiles = [pr for pr in design.profiles.values() if pr.alignment in names]
        xml = write_landxml(aligns, profiles, self.doc.meta.get("project_name", ""))
        path = self._out_path(p.get("path"),
                              f"{_slug(self.doc.meta['project_name'])}.xml")
        path.write_text(xml)
        result = self._file_result(path, p.get("include_base64", False))
        result["alignments"] = [a.name for a in aligns]
        result["profiles"] = [pr.name for pr in profiles]
        if p.get("include_xml"):
            result["xml"] = xml
        return result

    # ------------------------------------------------------------- helpers

    def _sheet(self, ref):
        sheet = self.doc.sheet_by_ref(ref)
        if sheet is None:
            raise _QueryFault(
                f"sheet {ref!r} not found",
                hint=f"existing sheets: {[s.name for s in self.doc.sheets.values()]}")
        return sheet

    def _resolve(self, given) -> Path:
        path = Path(given).expanduser()
        if self.base_dir is not None and not path.is_absolute():
            path = Path(self.base_dir) / path
        return path

    def _out_path(self, given, default_name) -> Path:
        path = self._resolve(given) if given else self.out_dir / default_name
        self._inside(path, given)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _inside(path: Path, given=None) -> Path:
        """``path``, unless a held root (document/confine.py) refuses it."""
        try:
            return confine.check(path, given)
        except confine.OutsideRoot as ex:
            raise _QueryFault(str(ex), hint=ex.hint)

    @staticmethod
    def _file_result(path: Path, include_base64: bool) -> dict:
        data = {"path": str(path), "size_bytes": path.stat().st_size}
        if include_base64:
            data["base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
        return data

    # -------------------------------------------------------- persistence

    @classmethod
    def load(cls, path, out_dir=None) -> "Session":
        """Open a saved document. The file shape is read from its content, so
        a .rdraft, a .rdoc.json and a renamed file all open the same way."""
        doc = Document.from_dict(fileformat.read_document(path))
        doc._path = Path(path).resolve()  # relative reference paths resolve here
        return cls(_document=doc, out_dir=out_dir)

    @classmethod
    def replay_journal(cls, path, out_dir=None, home=None) -> "Session":
        """Rebuild a session by replaying a saved journal. Deterministic.

        A command that reads through a reference needs the referenced file, so
        relative reference paths resolve from ``home``, the document the journal
        was kept for, by default from the journal's own folder: a journal is
        kept beside its document."""
        lines = [json.loads(line) for line in
                 Path(path).read_text().splitlines() if line.strip()]
        if not lines or lines[0].get("type") != "init":
            raise ValueError("journal must start with an init record")
        # a document opened again starts a new pass with the file as it was
        # then (journal_records): its commands are replayed from there
        last = max(i for i, e in enumerate(lines) if e.get("type") == "init")
        bus = CommandBus.replay(lines[last]["document"],
                                [e for e in lines[last + 1:] if e.get("type") == "command"],
                                home=Path(home or path).resolve())
        session = cls(out_dir=out_dir)
        session.bus = bus
        session.journal_history = lines[:last]
        return session


class _QueryFault(Exception):
    def __init__(self, message, hint=None):
        super().__init__(message)
        self.hint = hint
