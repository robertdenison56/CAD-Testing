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
  "layers": {"alignment": "V-ALIGN-CNTR", "ticks": "V-ROAD-STA", "labels": "V-ANNO-TEXT", "tables": "V-ANNO-TABL"},
  "layer_props": {"V-ALIGN-CNTR": {"color": "red", "linetype": "center", "lineweight_mm": 0.35},
                  "V-ROAD-STA": {"color": "gray", "lineweight_mm": 0.18},
                  "V-ANNO-TEXT": {"color": "black", "lineweight_mm": 0.25},
                  "V-ANNO-TABL": {"color": "black", "lineweight_mm": 0.25}},
  "text": {"label_height_in": 0.10, "table_height_in": 0.12, "height_tolerance_pct": 10},
  "stationing": {"interval_ft": 100, "format": "12+34.56", "decimals": 2, "tick_half_len_in": 0.20, "label_offset_in": 0.32, "label_side": "left", "rotation": "along"},
  # BC/EC, as Caltrans letters curve points (ppm-text p. 2-85, pdf 114); decided 2026-10-05
  "labels": {"pc_pt": {"required": True, "side": "right", "format": "BC 16+00.00"},
             "bearing": {"required": True, "anchor": "T-n", "format": "quadrant", "seconds_decimals": 0, "side": "left"},
             "mc": {"required": True, "format": "C-1"},
             "pi": {"required": False}, "equation": {"required_when_present": True, "format": "STA 20+00.00 BK = STA 25+00.00 AH"}},
  "curve_table": {"required": True, "title": "CURVE DATA", "columns": ["curve", "pi_sta", "delta", "direction", "radius", "tangent", "length", "chord", "chord_bearing"], "length_decimals": 2, "angle_format": "dms"},
  "tolerances": {"length_ft": 0.005, "station_ft": 0.005, "angle_seconds": 1, "position_model_ft": 0.05, "position_paper_in": 0.05, "rotation_deg": 1.0},
  "checks": [
     {"id": "D1-01", "name": "alignment linework on the alignment layer matches design geometry", "weight": 10, "hard_fail": True},
     {"id": "D1-02", "name": "station tick at every interval station (per region)", "weight": 12, "hard_fail": False},
     {"id": "D1-03", "name": "station label content/format correct and anchored", "weight": 12, "hard_fail": True},
     {"id": "D1-04", "name": "BC/EC label for every curve, correct, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-05", "name": "bearing label on every tangent, quadrant format, anchored T-n", "weight": 10, "hard_fail": True},
     {"id": "D1-06", "name": "curve table on the sheet: one row per curve, values within rounding, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-07", "name": "label position within tolerance of the anchor-implied position (no free-floating text)", "weight": 8, "hard_fail": False},
     {"id": "D1-08", "name": "legibility: no Text/Table overlaps on the sheet, nothing outside the usable area", "weight": 6, "hard_fail": False},
     {"id": "D1-09", "name": "layers and text heights per spec", "weight": 6, "hard_fail": False},
     {"id": "D1-10", "name": "title block fields present; scale string matches the viewport", "weight": 5, "hard_fail": False},
     {"id": "D1-11", "name": "north arrow present on the sheet", "weight": 3, "hard_fail": False}],
}

SPEC_VERSION = DRAFTING_SPEC_V1["version"]          # "draft-v1"; the brief's ``spec_version``
SPEC_STATUS = DRAFTING_SPEC_V1["status"]            # starts with "DRAFT"

#: Keys of ``DRAFTING_SPEC_V1`` that ``spec_subset()`` copies into a task brief by default.
SPEC_SUBSET_KEYS = ("units", "sheet", "layers", "layer_props", "text", "stationing", "labels",
                    "curve_table", "tolerances", "checks")


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
