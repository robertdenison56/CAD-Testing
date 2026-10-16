"""``DRAFTING_SPEC_V1`` -- the frozen v1 drafting specification for D1 plan-sheet tasks.

The dictionary below is the contract an agent's drawing is graded against:
sheet size and viewport, layer names and properties, text heights, stationing
conventions, which labels are required and how they are worded, the curve
table layout, verifier tolerances, and the weighted check list.  It was
reviewed decision by decision by a licensed professional engineer (Robert,
2026-10-05 to 2026-10-13; each decision is noted beside its value) and frozen
as ``v1`` on 2026-10-16 (eval plan section 3.7): every task set published on
it carries its hash, and any later edit mints new task ids under a new
version rather than re-scoring old ones.

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
  "spec_id": "roaddraft-drafting-spec", "version": "v1",
  "status": "FROZEN — v1, 2026-10-16, on the PE decisions of 2026-10-05 to 2026-10-13 (Robert)",
  # v1 (2026-10-16): draft-v4 frozen as is, after the generator fix that would otherwise have
  # moved frozen ids again (the width dimension line through the bearing, d1-v6). Nothing in
  # this dictionary changed but the version and status lines and the two level readings
  # below, now recorded as decided.
  # draft-v3 (2026-10-12, PE decision, Robert): plan scales are the common ones; the
  # generator fits each layout at the largest of them that shows it (1" = 50' for most).
  # Station numbers and bearings keep the PPM placement whatever the pavement width: text
  # touching an edge line on a narrow road is ordinary practice and is not a defect (the
  # 2026-10-12 sweep found the bearing cut by the 12 ft edge only at 1" = 100', which is
  # no longer used).
  # draft-v4 (2026-10-13, Robert): the scales are 1" = 40' and 1" = 50' only (10 and 20
  # dropped: no generated layout is short enough to use them); the label and table text
  # sizes stay 0.10 / 0.12 in (the PPM's 0.14 in considered and declined); every other
  # open item of eval plan 3.7 is confirmed as built. Nothing is left before the freeze.
  # draft-v2 (2026-10-11): the lettering conventions are the Plans Preparation Manual's, the
  # one set the probes (roaddraft.probes, Tier 3) and this benchmark share -- station numbers
  # below the line lettered the Caltrans way, BC/EC as station-then-word square to the line
  # reading bottom to top, bearing and distance above the tangent, the curve number in a
  # bubble, the curve table No./R/Δ/T/L -- and the labelers anchor through a referenced base
  # drawing (task type annotate-base). Every value cites its PPM page below.
  "units": {"model": "us_survey_ft", "paper": "inch"},
  "sheet": {"size": "ANSI_D", "allowed_feet_per_inch": [40, 50], "viewport": {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5},
            "fit_window_in": [26.0, 15.0], "north_arrow": {"required": True, "block": "NORTH_ARROW", "position": [31.6, 19.2], "scale": 0.9},
            "required_title_fields": ["project", "agency", "sheet_title", "sheet_number", "total_sheets", "designed_by", "drawn_by", "checked_by", "date", "scale"],
            "scale_text_format": "1\" = {fpi:.0f}'"},
  # Layers are Caltrans named levels (decided 2026-10-10, Robert: "set up more layers per
  # Caltrans PPM standards"), from the CADD Users Manual Appendix A10 "Named Level Libraries"
  # (April 12, 2021) with the weights of its Chapter 2.7 "Lines" (Oct 23, 2017) and the PPM's
  # layout-sheet checklist (ppm-text p. 2-89 (pdf 118)). Roles name the level each kind of
  # work goes on; ``layer_set`` is the whole set a layout sheet file carries; ``caltrans_levels``
  # records the source row behind each one. Two roles are this spec's own reading of the
  # library, decided 2026-10-13 (Robert): width dimensions on rd_LAYOUT-NOTE-anno and match
  # lines on border_INSIDE-BORDER-anno (the level the PPM gives the scale text).
  "layers": {"alignment": "align_MAIN", "ticks": "align_MAIN-anno", "labels": "align_MAIN-anno",
             "tables": "align_CURVE-DATA", "edges": "rd_EP", "dims": "rd_LAYOUT-NOTE-anno",
             "symbols": "pp_PRESENTATION", "match": "border_INSIDE-BORDER-anno"},
  "layer_set": ["align_MAIN", "align_MAIN-anno", "align_CURVE-DATA", "rd_EP", "rd_ETW", "rd_ES",
                "rd_LAYOUT-NOTE-anno", "rd_RIGHT-OF-WAY", "rd_RIGHT-OF-WAY-anno", "pp_PRESENTATION",
                "pp_LEGEND-anno", "border_SHEET", "border_PROJ-ID-BLOCK-anno", "border_INSIDE-BORDER-anno",
                "border_SEAL", "border_SIGNATURE"],
  # RoadDraft's rendering of a MicroStation weight (WT) as a plotted width; the WT is the source
  # value (CADD Users Manual 2.7-1, 2.7-2), the millimetres are this spec's choice
  "lineweight_mm_by_wt": {"0": 0.18, "1": 0.25, "2": 0.35, "3": 0.5, "4": 0.7},
  "layer_props": {
      "align_MAIN": {"color": "black", "lineweight_mm": 0.5, "description": "Alignment for Main line (Caltrans level 9017; WT 3)"},
      "align_MAIN-anno": {"color": "black", "lineweight_mm": 0.25, "description": "Annotation for Main line alignment: stations, curve points, bearings, callouts (Caltrans level 9018; WT 1)"},
      "align_CURVE-DATA": {"color": "black", "lineweight_mm": 0.25, "description": "Curve data information in tabular format (Caltrans level 9010; WT 1)"},
      "rd_EP": {"color": "black", "lineweight_mm": 0.35, "description": "Edge of Pavement (Caltrans level 9112; WT 2 on layouts)"},
      "rd_ETW": {"color": "black", "lineweight_mm": 0.25, "description": "Edge of Traveled Way (Caltrans level 9114; WT 1)"},
      "rd_ES": {"color": "black", "lineweight_mm": 0.25, "description": "Edge of Shoulder (Caltrans level 9113; WT 1)"},
      "rd_LAYOUT-NOTE-anno": {"color": "black", "lineweight_mm": 0.18, "description": "Annotation for construction shown in Master Design: layout notes, width dimensions (Caltrans level 9129; WT 0)"},
      "rd_RIGHT-OF-WAY": {"color": "cyan", "lineweight_mm": 0.25, "description": "Right of way (Caltrans level 9143, color 6; WT 1)"},
      "rd_RIGHT-OF-WAY-anno": {"color": "cyan", "lineweight_mm": 0.25, "description": "Annotation for right of way and TCE (Caltrans level 9144, color 6; WT 1)"},
      "pp_PRESENTATION": {"color": "black", "lineweight_mm": 0.25, "description": "Cells, line styles or other info for design presentation: the north arrow (Caltrans level 10232; WT 1)"},
      "pp_LEGEND-anno": {"color": "black", "lineweight_mm": 0.25, "description": "Annotation for notes, legends and abbreviations (Caltrans level 10225; WT 1)"},
      "border_SHEET": {"color": "black", "lineweight_mm": 0.7, "description": "Border for any discipline (Caltrans level 10210; WT 4)"},
      "border_PROJ-ID-BLOCK-anno": {"color": "magenta", "lineweight_mm": 0.25, "description": "Annotation in the project identification block (Caltrans level 10208, color 13; WT 1)"},
      "border_INSIDE-BORDER-anno": {"color": "magenta", "lineweight_mm": 0.35, "description": "Annotation inside the border: scale, match lines (Caltrans level 10206, color 13; WT 2)"},
      "border_SEAL": {"color": "yellow", "lineweight_mm": 0.25, "description": "Seal information of licensed person (Caltrans level 10209, color 4; WT 1)"},
      "border_SIGNATURE": {"color": "yellow", "lineweight_mm": 0.25, "description": "Signature of licensed person (Caltrans level 10211, color 4; WT 1)"}},
  # the source row behind each level: Appendix A10 number, library, color-table index, the
  # weight (CADD 2.7, or the PPM where it says otherwise) and where each comes from. Display
  # colors above are RoadDraft's nearest named color for the index, not the Caltrans table.
  "caltrans_levels": {
      "align_MAIN": {"number": 9017, "library": "Ct_Alignments", "color_index": 0, "weight": 3, "source": "cadd-appx-a10 p. A10-2; weight cadd-ch2-sect7 p. 2.7-1 (alignment lines for main routes)"},
      "align_MAIN-anno": {"number": 9018, "library": "Ct_Alignments", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-2; ppm-text p. 2-89 (pdf 118) route identification LV=align_MAIN-anno; weight cadd-ch2-sect7 p. 2.7-1 (stations for all alignment lines)"},
      "align_CURVE-DATA": {"number": 9010, "library": "Ct_Alignments", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-2"},
      "rd_EP": {"number": 9112, "library": "Ct_Roadway", "color_index": 0, "weight": 2, "source": "cadd-appx-a10 p. A10-18; ppm-text p. 2-90 (pdf 119) EP as a thicker weight line, usually WT=2 (cadd-ch2-sect7 p. 2.7-2 lists EP at WT 1)"},
      "rd_ETW": {"number": 9114, "library": "Ct_Roadway", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-18; cadd-ch2-sect7 p. 2.7-2"},
      "rd_ES": {"number": 9113, "library": "Ct_Roadway", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-18; cadd-ch2-sect7 p. 2.7-2"},
      "rd_LAYOUT-NOTE-anno": {"number": 9129, "library": "Ct_Roadway", "color_index": 0, "weight": 0, "source": "cadd-appx-a10 p. A10-18; weight cadd-ch2-sect7 p. 2.7-1 (dimension lines). this spec's choice of level for width dimensions, decided 2026-10-13 (Robert)"},
      "rd_RIGHT-OF-WAY": {"number": 9143, "library": "Ct_Roadway", "color_index": 6, "weight": 1, "source": "cadd-appx-a10 p. A10-18; cadd-ch2-sect7 p. 2.7-1 (right of way)"},
      "rd_RIGHT-OF-WAY-anno": {"number": 9144, "library": "Ct_Roadway", "color_index": 6, "weight": 1, "source": "cadd-appx-a10 p. A10-18"},
      "pp_PRESENTATION": {"number": 10232, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-16; ppm-text p. 2-89 (pdf 118) north arrow AC=NARR LV=pp_PRESENTATION WT=1"},
      "pp_LEGEND-anno": {"number": 10225, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 0, "weight": 1, "source": "cadd-appx-a10 p. A10-16; ppm-text p. 2-90 (pdf 119)"},
      "border_SHEET": {"number": 10210, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 0, "weight": 4, "source": "cadd-appx-a10 p. A10-16; ppm-text p. 2-89 (pdf 118); weight cadd-ch2-sect7 p. 2.7-1 (sheet border)"},
      "border_PROJ-ID-BLOCK-anno": {"number": 10208, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 13, "weight": 1, "source": "cadd-appx-a10 p. A10-17; ppm-text p. 2-89 (pdf 118) TX=7.0 FT=3 WT=1"},
      "border_INSIDE-BORDER-anno": {"number": 10206, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 13, "weight": 2, "source": "cadd-appx-a10 p. A10-17; ppm-text p. 2-89 (pdf 118) scale TX=8.75 FT=3 WT=2. this spec's choice of level for match lines, decided 2026-10-13 (Robert)"},
      "border_SEAL": {"number": 10209, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 4, "weight": 1, "source": "cadd-appx-a10 p. A10-17; ppm-text p. 2-89 (pdf 118)"},
      "border_SIGNATURE": {"number": 10211, "library": "Ct_ProjectPlans_BorderSheetInfo", "color_index": 4, "weight": 1, "source": "cadd-appx-a10 p. A10-17; ppm-text p. 2-89 (pdf 118)"}},
  # the typical section (plan prep, decided 2026-10-10): two lanes, the edge of pavement a
  # lane width each side of the centerline, the width dimensioned across each tangent
  "pavement": {"lanes": 2, "lane_widths_ft": [11, 12], "edge_layer": "rd_EP",
               "width_dimension": {"kind": "aligned", "per": "tangent", "at": "the half station nearest the tangent's midpoint",
                                   "layer": "rd_LAYOUT-NOTE-anno", "text_height_in": 0.10, "format": "24.00'"}},
  "reference": {"name": "BASE", "space": "model", "placement": "identity (no offset, rotation or scale), visible, unclipped"},
  "text": {"label_height_in": 0.10, "table_height_in": 0.12, "height_tolerance_pct": 10},
  # Stationing the Caltrans way (ppm-text p. 2-8, pdf 37): 100 ft per station, the whole
  # station number at 500 ft stations and the ones digit elsewhere, no plus on a whole
  # station; a 7.0 ft tick at 1" = 50' (2.8 ft at 1" = 20': 0.14 in on paper), centred on
  # the line; the number below the line, half a text height under the tick
  "stationing": {"interval_ft": 100, "format": "caltrans", "full_station_every_ft": 500, "decimals": 2,
                 "tick_half_len_in": 0.07, "label_offset_in": 0.12, "label_side": "below", "rotation": "along",
                 "example": "30, 1, 2, 3, 4, 35 for 30+00 to 35+00",
                 "source": "ppm-text p. 2-8 (pdf 37)"},
  # The alignment data of a layout (ppm-text p. 2-85, 2-89; pdf 114, 118): BC and EC
  # stations to the hundredth, station then word, square to the line on its left and reading
  # bottom to top (p. 2-4); bearing and distance of every tangent above the line, parallel to
  # it; the curve number in a bubble with a leader to the curve; equations lettered like the
  # curve points. Decided 2026-10-05 (BC/EC words) and 2026-10-11 (the rest).
  "labels": {"pc_pt": {"required": True, "side": "left", "rotation": "perpendicular", "reads": "bottom to top",
                       "format": "24+05.27 BC", "label_offset_in": 0.45, "source": "ppm-text p. 2-85, 2-4"},
             "bearing": {"required": True, "anchor": "T-n", "format": "quadrant", "seconds_decimals": 0, "side": "above",
                         "with_length": True, "length_decimals": 2, "example": "N 71°33'54\" E 1240.36'",
                         "label_offset_in": 0.06, "source": "ppm-text p. 2-89 (pdf 118)"},
             "mc": {"required": True, "format": "1", "bubble": {"radius_text_heights": 2.0, "leader": "from the bubble's edge to the middle of the curve"},
                    "numbering": "consecutive along the line, never restarted on the next sheet", "side": "right",
                    "label_offset_in": 0.80, "source": "ppm-text p. 2-85 (pdf 114)"},
             "pi": {"required": False},
             "equation": {"required_when_present": True, "format": "STA 20+00.00 BK = STA 25+00.00 AH", "side": "left",
                          "rotation": "perpendicular", "label_offset_in": 0.45}},
  # The curve data table as the PPM's layouts carry it: No., R, Δ, T, L (ppm-examples)
  "curve_table": {"required": True, "title": "CURVE DATA", "columns": ["curve", "radius", "delta", "tangent", "length"],
                  "headers": ["No.", "R", "Δ", "T", "L"], "length_decimals": 2, "angle_format": "dms",
                  "source": "ppm-examples layout sheets; ppm-text p. 2-85 (pdf 114)"},
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
                 "layer-setup", "pavement-edges", "pavement-widths", "pavement", "attach-reference",
                 "create-alignment", "annotate-base"],
  "sheet_setup": {"one_sheet": {"sheet": 0.25, "scale": 0.25, "fitted": 0.5},
                  "many_sheets": {"sheet": 0.2, "scale": 0.2, "fitted": 0.4, "match_line": 0.2}},
  "checks": [
     {"id": "D1-00", "name": "sheet setup: each deliverable sheet, a viewport at an allowed scale, its part of the alignment fitted, the match line between sheets", "weight": 5, "hard_fail": False},
     {"id": "D1-01", "name": "alignment linework on the alignment layer matches design geometry", "weight": 10, "hard_fail": True},
     {"id": "D1-02", "name": "station tick at every interval station (per region)", "weight": 9, "hard_fail": False},
     {"id": "D1-03", "name": "station numbers (the Caltrans way, below the line) and station-equation labels: content/format correct and anchored", "weight": 12, "hard_fail": True},
     {"id": "D1-04", "name": "BC/EC (PCC/PRC) station lettered at every curve point and the curve number in a bubble at every mid-curve, correct, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-05", "name": "bearing and distance on every tangent, quadrant format, anchored T-n", "weight": 10, "hard_fail": True},
     {"id": "D1-06", "name": "curve table on the sheet (No., R, Δ, T, L): one row per curve, values within rounding, anchored", "weight": 14, "hard_fail": True},
     {"id": "D1-07", "name": "label position within tolerance of the anchor-implied position (no free-floating text)", "weight": 8, "hard_fail": False},
     {"id": "D1-08", "name": "legibility: no Text/Table overlaps on the sheet, nothing outside the usable area", "weight": 6, "hard_fail": False},
     {"id": "D1-09", "name": "layers and text heights per spec", "weight": 6, "hard_fail": False},
     {"id": "D1-10", "name": "title block fields present; scale string matches the viewport", "weight": 5, "hard_fail": False},
     {"id": "D1-11", "name": "north arrow present on the sheet", "weight": 1, "hard_fail": False},
     # plan-prep checks (2026-10-10); outside the layout sheet's 100 points, in play only for
     # the task types that ask for them
     {"id": "D1-12", "name": "pavement edges: the offset linework at the typical section's width matches the design", "weight": 8, "hard_fail": True},
     {"id": "D1-13", "name": "pavement width dimensioned across each tangent, between the edges, reading the width", "weight": 6, "hard_fail": True},
     {"id": "D1-14", "name": "the base drawing attached as a reference in model space, at identity, visible", "weight": 5, "hard_fail": False},
     # design input (2026-10-11): the alignment the prompt describes, created in the design
     {"id": "D1-15", "name": "alignment created from the given geometry: begin station, PIs and radii, equations within tolerance", "weight": 12, "hard_fail": True}],
}

SPEC_VERSION = DRAFTING_SPEC_V1["version"]          # "v1"; the brief's ``spec_version``
SPEC_STATUS = DRAFTING_SPEC_V1["status"]            # starts with "FROZEN" (was "DRAFT" to draft-v4)

#: Keys of ``DRAFTING_SPEC_V1`` that ``spec_subset()`` copies into a task brief by default.
SPEC_SUBSET_KEYS = ("units", "sheet", "layers", "layer_set", "layer_props", "text", "stationing",
                    "labels", "curve_table", "tolerances", "scoring", "checks")


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
