"""Tool profiles: the surface a server serves, cut down for an experiment.

The default profile is the whole command surface and the instructions every
ranked run gets. ``basic`` (pilot 16, 2026-10-19) takes away the commands
that do a drafter's geometry for the model -- an alignment from bearings and
distances, a parallel offset, a fillet, a trim, the station and viewport
conversions, the labelers that letter an alignment from its design, a
callout aimed at an entity or anchor -- and leaves lines, arcs, text, tables,
blocks, sheets and the queries that read the drawing and the design. A design
alignment can still be made, from PI coordinates the model works out
(``create_alignment`` without ``start`` and ``legs``), and drawn by hand.

All 33 probes stay passable on ``basic``: each reference solution's document,
with every anchor the engine stamped removed, still passes its check (audit,
2026-10-19). A model
on ``basic`` has to work out the coordinates itself, so the same probe on
both profiles separates what the model can do from what the engine does
for it.

A profile changes what a run is measured on, so a ``basic`` run is its own
row, never mixed with the default board (``runners`` records the profile in
``run.json``).
"""
from __future__ import annotations

from typing import Dict, List

#: commands that compute geometry or lettering from the design for the caller
BASIC_EXCLUDE: List[str] = sorted([
    # geometry construction and editing that solves an intersection or offset
    "draw_traverse", "traverse", "offset_entity", "draw_offset", "fillet", "chamfer",
    "trim", "extend", "lengthen", "break_entity", "join_entities", "place_along",
    # reading points off geometry and converting between spaces
    "key_points", "snap", "point_on_entity", "hit_test", "measure", "area",
    "model_to_sheet", "sheet_to_model",
    # the design route: stations, anchors, an alignment drawn from its design
    "station_to_xy", "xy_to_station", "resolve_anchor", "draw_alignment",
    "draw_station_offset",
    # lettering generated from the design
    "annotate_stationing", "label_segments", "place_label", "place_curve_table",
    "place_point_table",
])

#: parameters a tool keeps on the default profile but loses on ``basic``: an
#: alignment from bearings and distances (its PIs as coordinates stay, the only
#: way to make a design a check can read), the callout aimed by the engine, and
#: the sheet point find_entities works out
BASIC_STRIP: Dict[str, List[str]] = {
    "create_alignment": ["start", "legs"],
    "place_callout": ["target_entity", "target_anchor", "alignment", "at", "viewport"],
    "find_entities": ["visible_on"],
}

#: what a server on ``basic`` says at initialize, in place of the default
#: instructions; written about a drawing of its own, like those
BASIC_INSTRUCTIONS = (
    "RoadDraft is a headless 2D CAD engine for roadway plans. Model "
    "space is US survey feet, and a point is [x, y] = [easting, "
    "northing] -- the other way round from how coordinates are usually "
    "spoken. Sheets are paper inches seen through viewports at a "
    "feet-per-inch scale. Work through the commands: each one validates its "
    "params and explains what was wrong, every change is journaled and "
    "undoable. Start with get_document_state to see what is in the "
    "document, list_commands for the full surface, and render_sheet or "
    "render_model to look at your work."
    "\n\n"
    "This server offers the basic drafting surface: lines, polylines, arcs, "
    "circles, text, callouts with a leader to a point you give, dimensions, "
    "tables, blocks, hatches, sheets and viewports, and the edits that move, "
    "copy, rotate, mirror, scale and change what is there. The geometry is "
    "yours to work out. create_alignment takes an alignment's PIs as "
    "coordinates, with the radius of the curve at each, and stores it as a "
    "design with stationing; drawing it is up to you. get_design_data gives an alignment's design -- its "
    "PIs, curve data and stationing -- and get_entity and find_entities read "
    "what is drawn; from those, compute the coordinates you need. A sheet's "
    "viewport (get_sheet_state) gives its center in paper inches, the model "
    "point it shows there, its scale in feet per inch and its twist, which "
    "is all it takes to carry a model point to the paper and back."
)

PROFILES = ("default", "basic")


def exclude(profile: str) -> List[str]:
    """The tool names a profile hides."""
    return list(BASIC_EXCLUDE) if profile == "basic" else []


def strip(profile: str) -> Dict[str, List[str]]:
    """``{tool: [params it loses]}`` on a profile."""
    return {k: list(v) for k, v in BASIC_STRIP.items()} if profile == "basic" else {}


def instructions(profile: str, default: str) -> str:
    return BASIC_INSTRUCTIONS if profile == "basic" else default


__all__ = ["PROFILES", "BASIC_EXCLUDE", "BASIC_STRIP", "BASIC_INSTRUCTIONS", "exclude",
           "strip", "instructions"]
