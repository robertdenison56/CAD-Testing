"""RoadDraft design model: pure roadway-geometry math.

Imports only ``roaddraft.core`` (never commands/api/web/document/tasks).
"""
from __future__ import annotations

from roaddraft.design.angles import (
    azimuth_of,
    azimuth_to_direction,
    direction_of,
    direction_to_azimuth,
    dms_parts,
    format_azimuth,
    format_bearing,
    format_dms,
    left_normal,
    norm_deg,
    parse_bearing,
    parse_dms,
    right_normal,
    signed_delta_deg,
    unit_vector,
)
from roaddraft.design.anchors import (
    GRAMMAR_HINT,
    AnchorPoint,
    AnchorRef,
    infer_kind,
    list_anchors,
    parse_anchor,
    resolve_anchor,
)
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (
    ANGLE_EPS,
    CONNECT_TOL,
    ELEMENT_KINDS,
    GEOM_EPS,
    PI,
    Alignment,
    CurveElement,
    TangentElement,
    alignment_from_elements,
    compile_pis,
    curve_data,
    curve_from_pi,
    element_from_dict,
    element_to_dict,
    elements_from_dicts,
    junction_kind,
    pis_from_elements,
    tangent_data,
    validate_continuity,
)
from roaddraft.design.labels import (
    CURVE_COLUMNS,
    DEFAULT_CURVE_COLUMNS,
    DEFAULT_SIDE,
    DEFAULT_VALIGN,
    LABEL_KINDS,
    MODEL_LABEL_OFFSET,
    MODEL_TEXT_HEIGHT,
    MODEL_TICK_HALF,
    ROTATION_MODES,
    SHEET_LABEL_OFFSET,
    SHEET_TEXT_HEIGHT,
    SIDES,
    LabelSpec,
    StationingPlan,
    TickSpec,
    compile_label,
    curve_table_rows,
    label_content,
    offset_point,
    sheet_pose,
    stationing_plan,
    upright,
)
from roaddraft.design.model import DesignModel
from roaddraft.design.stations import (
    STATION_EPS,
    Region,
    StationEquation,
    StationSystem,
    build_equations,
    equation_label,
)
from roaddraft.design.vertical import PVI, Profile, vc_data

__all__ = [
    "DesignError",
    # angles
    "norm_deg", "signed_delta_deg", "direction_to_azimuth", "azimuth_to_direction",
    "direction_of", "azimuth_of", "unit_vector", "left_normal", "right_normal", "dms_parts",
    "format_dms", "parse_dms", "format_bearing", "parse_bearing", "format_azimuth",
    # stations
    "STATION_EPS", "StationEquation", "Region", "StationSystem", "build_equations",
    "equation_label",
    # horizontal
    "ELEMENT_KINDS", "GEOM_EPS", "ANGLE_EPS", "CONNECT_TOL", "PI", "TangentElement",
    "CurveElement", "Alignment", "compile_pis", "curve_from_pi", "element_from_dict",
    "element_to_dict", "elements_from_dicts", "pis_from_elements", "validate_continuity",
    "alignment_from_elements", "curve_data", "tangent_data", "junction_kind",
    # vertical
    "PVI", "Profile", "vc_data",
    # anchors
    "GRAMMAR_HINT", "AnchorRef", "AnchorPoint", "parse_anchor", "infer_kind", "resolve_anchor",
    "list_anchors",
    # labels
    "LABEL_KINDS", "ROTATION_MODES", "SIDES", "DEFAULT_SIDE", "DEFAULT_VALIGN",
    "MODEL_LABEL_OFFSET", "MODEL_TEXT_HEIGHT", "MODEL_TICK_HALF", "SHEET_LABEL_OFFSET",
    "SHEET_TEXT_HEIGHT", "LabelSpec", "TickSpec", "StationingPlan", "upright", "offset_point",
    "label_content", "compile_label", "sheet_pose", "stationing_plan", "CURVE_COLUMNS",
    "DEFAULT_CURVE_COLUMNS", "curve_table_rows",
    # model
    "DesignModel",
]
