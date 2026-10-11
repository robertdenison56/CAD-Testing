"""``DRAFTING_SPEC_V1`` -- the DRAFT drafting specification for D1 plan-sheet tasks.

The dictionary below is the contract an agent's drawing is graded against:
sheet size and viewport, layer names and properties, text heights, stationing
conventions, which labels are required and how they are worded, the curve
table layout, verifier tolerances, and the weighted check list.  It is DRAFT
and must be reviewed by a licensed professional engineer before any task set
built on it is published.

``spec_hash()`` folds the canonical JSON of the spec into every task id, so
that any edit to this dictionary (including a PE correction) mints new task
ids instead of silently re-scoring old ones.  ``spec_subset()`` is the
agent-visible slice embedded in a task brief.

This module imports only the standard library.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Dict, Optional, Sequence

DRAFTING_SPEC_V1 = {
  "spec_id": "roaddraft-drafting-spec", "version": "draft-v1", "status": "DRAFT — for PE review",
  "units": {"model": "us_survey_ft", "paper": "inch"},
  "sheet": {"size": "ANSI_D", "allowed_feet_per_inch": [50, 100], "viewport": {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5},
            "fit_window_in": [26.0, 15.0], "north_arrow": {"required": True, "block": "NORTH_ARROW", "position": [31.6, 19.2], "scale": 0.9},
            "required_title_fields": ["project", "agency", "sheet_title", "sheet_number", "total_sheets", "designed_by", "drawn_by", "checked_by", "date", "scale"],
            "scale_text_format": "1\" = {fpi:.0f}'"},
  "layers": {"alignment": "V-ALIGN-CNTR", "ticks": "V-ROAD-STA", "labels": "V-ANNO-TEXT", "tables": "V-ANNO-TABL",
             "edges": "V-ROAD-EOP", "dims": "V-ANNO-DIMS"},
  "layer_props": {"V-ALIGN-CNTR": {"color": "red", "linetype": "center", "lineweight_mm": 0.35},
                  "V-ROAD-STA": {"color": "gray", "lineweight_mm": 0.18},
                  "V-ANNO-TEXT": {"color": "black", "lineweight_mm": 0.25},
                  "V-ANNO-TABL": {"color": "black", "lineweight_mm": 0.25},
                  "V-ROAD-EOP": {"color": "blue", "lineweight_mm": 0.35},
                  "V-ANNO-DIMS": {"color": "black", "lineweight_mm": 0.25}},
  # the typical section (plan prep, decided 2026-10-10): two lanes, the edge of pavement a
  # lane width each side of the centerline, the width dimensioned across each tangent
  "pavement": {"lanes": 2, "lane_widths_ft": [11, 12], "edge_layer": "V-ROAD-EOP",
               "width_dimension": {"kind": "aligned", "per": "tangent", "at": "the even station nearest the tangent's midpoint",
                                   "layer": "V-ANNO-DIMS", "text_height_in": 0.10, "format": "24.00'"}},
  "reference": {"name": "BASE", "space": "model", "placement": "identity (no offset, rotation or scale), visible, unclipped"},
  "text": {"label_height_in": 0.10, "table_height_in": 0.12, "height_tolerance_pct": 10},
  "stationing": {"interval_ft": 100, "format": "12+34.56", "decimals": 2, "tick_half_len_in": 0.20, "label_offset_in": 0.32, "label_side": "left", "rotation": "along"},
  # BC/EC, as Caltrans letters curve points (ppm-text p. 2-85, pdf 114); decided 2026-10-05
  "labels": {"pc_pt": {"required": True, "side": "right", "format": "BC 16+00.00"},
             "bearing": {"required": True, "anchor": "T-n", "format": "quadrant", "seconds_decimals": 0, "side": "left"},
             "mc": {"required": True, "format": "C-1"},
             "pi": {"required": False}, "equation": {"required_when_present": True, "format": "STA 20+00.00 BK = STA 25+00.00 AH"}},
  "curve_table": {"required": True, "title": "CURVE DATA", "columns": ["curve", "pi_sta", "delta", "direction", "radius", "tangent", "length", "chord", "chord_bearing"], "length_decimals": 2, "angle_format": "dms"},
  "tolerances": {"length_ft": 0.005, "station_ft": 0.005, "angle_seconds": 1, "position_model_ft": 0.05, "position_paper_in": 0.05, "rotation_deg": 1.0},
  # The scoring rule (PE decisions 2026-10-09, eval plan 3.7 items 1, 3, 4; D1-00's 5 points
  # came from D1-02 12 -> 9 and D1-11 3 -> 1): text and tables
  # earn credit only as anchored work placed by an anchoring command; linework and ticks
  # earn it by geometric match. Missing work costs credit; a wrong value shown on the sheet
  # under a hard-fail check zeroes the sheet.
  "scoring": {"rubric": "sum of weight x credit over the checks a task's scope puts in play, scaled to 100",
              "hard_fail": "missing work costs credit; a wrong value shown on the sheet under a hard_fail check is a hard fail",
              "effective_score": "0 if hard failed, otherwise the rubric score",
              "text_credit": "labels and the curve table earn credit only when placed by place_label, annotate_stationing (alignment mode) or place_curve_table; raw text earns nothing",
              "geometry_credit": "alignment linework and station ticks earn credit by matching the design geometry, however they were drawn",
              "legibility": "judged in paper space on the deliverable sheet, model-space labels seen through their viewport"},
  # The prompt dial (decided 2026-10-10): every task is posed in natural language at two
  # levels over the same truth. "explicit" states the drafting standards the task touches;
  # "vague" states the request in a sentence. What must be on the sheet is graded the same
  # at both; a convention the prompt did not state is graded by the "lenient" rules (any
  # standard scale, any layer but 0, any legible height, values read by meaning, not format).
  "prompt_levels": {
      "explicit": {"states": ["scale", "layers", "text_heights", "tick_length", "label_format", "table_columns", "match_line"],
                   "title_fields": ["project", "agency", "sheet_title", "sheet_number", "total_sheets", "designed_by", "drawn_by", "checked_by", "date", "scale"]},
      "vague": {"states": [], "title_fields": ["project", "sheet_number"]}},
  "lenient": {"standard_feet_per_inch": [10, 20, 30, 40, 50, 60, 100, 200],
              "label_height_in": [0.08, 0.20], "table_height_in": [0.08, 0.25], "tick_length_in": [0.05, 1.0],
              "match_line_min_in": 1.0,
              "table_core_columns": ["curve", "delta", "radius", "length"]},
  # Tasks (decided 2026-10-10): a task starts from a document with some drafting phases done
  # and asks for others (the task type); only the checks the asked-for work drives are graded,
  # renormalised to 100. A two-sheet layout breaks at a match line, drawn once across the
  # centerline and labelled on each sheet; the match line scores inside D1-00.
  "task_types": ["draw-alignment", "stationing", "curve-callouts", "bearings", "curve-table", "title-block", "sheet-setup", "annotate-sheet", "plan-sheet",
                 "layer-setup", "pavement-edges", "pavement-widths", "pavement", "attach-reference"],
  "sheet_setup": {"one_sheet": {"sheet": 0.25, "scale": 0.25, "fitted": 0.5},
                  "many_sheets": {"sheet": 0.2, "scale": 0.2, "fitted": 0.4, "match_line": 0.2}},
  "checks": [
     {"id": "D1-00", "name": "sheet setup: each deliverable sheet, a viewport at an allowed scale, its part of the alignment fitted, the match line between sheets", "weight": 5, "hard_fail": False},
     {"id": "D1-01", "name": "alignment linework on the alignment layer matches design geometry", "weight": 10, "hard_fail": True},
     {"id": "D1-02", "name": "station tick at every interval station (per region)", "weight": 9, "hard_fail": False},
     {"id": "D1-03", "name": "station and station-equation labels: content/format correct and anchored", "weight": 12, "hard_fail": True},
     {"id": "D1-04", "name": "BC/EC (PCC/PRC) label for every curve and a C-n callout at every mid-curve, correct, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-05", "name": "bearing label on every tangent, quadrant format, anchored T-n", "weight": 10, "hard_fail": True},
     {"id": "D1-06", "name": "curve table on the sheet: one row per curve, values within rounding, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-07", "name": "label position within tolerance of the anchor-implied position (no free-floating text)", "weight": 8, "hard_fail": False},
     {"id": "D1-08", "name": "legibility: no Text/Table overlaps on the sheet, nothing outside the usable area", "weight": 6, "hard_fail": False},
     {"id": "D1-09", "name": "layers and text heights per spec", "weight": 6, "hard_fail": False},
     {"id": "D1-10", "name": "title block fields present; scale string matches the viewport", "weight": 5, "hard_fail": False},
     {"id": "D1-11", "name": "north arrow present on the sheet", "weight": 1, "hard_fail": False},
     # plan-prep checks (2026-10-10); outside the layout sheet's 100 points, in play only for
     # the task types that ask for them
     {"id": "D1-12", "name": "pavement edges: the offset linework at the typical section's width matches the design", "weight": 8, "hard_fail": True},
     {"id": "D1-13", "name": "pavement width dimensioned across each tangent, between the edges, reading the width", "weight": 6, "hard_fail": True},
     {"id": "D1-14", "name": "the base drawing attached as a reference in model space, at identity, visible", "weight": 5, "hard_fail": False}],
}

SPEC_VERSION = DRAFTING_SPEC_V1["version"]          # "draft-v1"; the brief's ``spec_version``
SPEC_STATUS = DRAFTING_SPEC_V1["status"]            # starts with "DRAFT"

#: Keys of ``DRAFTING_SPEC_V1`` that ``spec_subset()`` copies into a task brief by default.
SPEC_SUBSET_KEYS = ("units", "sheet", "layers", "layer_props", "text", "stationing", "labels",
                    "curve_table", "tolerances", "scoring", "checks")


def _canonical_json(obj: object) -> str:
    """Deterministic JSON: sorted keys, no whitespace, ASCII-escaped non-ASCII."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def spec_hash(spec: Optional[dict] = None) -> str:
    """Return ``"sha256:" + sha256(canonical JSON of the spec)[:16]``.

    ``spec`` defaults to ``DRAFTING_SPEC_V1``; passing another dict hashes that
    dict with the same canonical encoding (``sort_keys=True``,
    ``separators=(",", ":")``), which is how tests show that an edited spec
    hashes differently.  Deterministic across processes and platforms: no
    clock, no id(), no dict insertion order.
    """
    payload = DRAFTING_SPEC_V1 if spec is None else spec
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return "sha256:" + digest[:16]


def spec_subset(keys: Sequence[str] = SPEC_SUBSET_KEYS) -> Dict[str, object]:
    """Return a deep copy of the requested top-level sections of ``DRAFTING_SPEC_V1``.

    ``keys`` defaults to the agent-visible sections (everything except
    ``spec_id`` / ``version`` / ``status``, which the brief carries as
    ``spec_version`` and ``spec_hash``).  Key order follows ``keys``.  The copy
    is independent of the module constant, so a caller may edit it freely.
    Raises ``ValueError`` naming the unknown key and the available sections.
    """
    out: Dict[str, object] = {}
    for key in keys:
        if key not in DRAFTING_SPEC_V1:
            raise ValueError(
                "DRAFTING_SPEC_V1 has no section %r; sections: %s"
                % (key, ", ".join(DRAFTING_SPEC_V1.keys()))
            )
        out[key] = copy.deepcopy(DRAFTING_SPEC_V1[key])
    return out
