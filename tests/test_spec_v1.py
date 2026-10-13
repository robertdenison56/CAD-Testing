"""WP2 acceptance: DRAFT design standards and DRAFTING_SPEC_V1 (Phase 1 spec section 7.1 / 7.2)."""
import copy
import hashlib
import json
import os
import re

import pytest

from roaddraft.tasks import spec_v1, standards
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_SUBSET_KEYS, spec_hash, spec_subset
from roaddraft.tasks.standards import (
    MIN_VC_LENGTH_FT,
    STANDARDS_STATUS,
    max_grade,
    min_k,
    min_radius,
)

# Literal catalog of curve-table column keys (spec section 3.6 / 4.8); deliberately NOT imported.
CURVE_TABLE_COLUMN_CATALOG = ["curve", "pi_sta", "pc_sta", "pt_sta", "delta", "direction", "radius",
                              "tangent", "length", "external", "mid_ordinate", "chord", "chord_bearing"]


# --- DRAFTING_SPEC_V1 content -------------------------------------------------------------------

def test_layout_check_weights_sum_to_100_plan_prep_checks_ride_outside():
    weights = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}
    assert sum(w for cid, w in weights.items() if cid <= "D1-11") == 100
    assert all(isinstance(w, int) and w > 0 for w in weights.values())
    assert {cid for cid in weights if cid > "D1-11"} == {"D1-12", "D1-13", "D1-14", "D1-15"}


def test_check_ids_unique_D1_00_to_D1_15():
    ids = [c["id"] for c in DRAFTING_SPEC_V1["checks"]]
    assert len(ids) == len(set(ids)) == 16
    assert ids == ["D1-%02d" % i for i in range(0, 16)]
    for check in DRAFTING_SPEC_V1["checks"]:
        assert set(check) == {"id", "name", "weight", "hard_fail"}
        assert isinstance(check["hard_fail"], bool)
        assert check["name"]


def test_status_starts_with_DRAFT():
    assert DRAFTING_SPEC_V1["status"].startswith("DRAFT")
    assert spec_v1.SPEC_STATUS.startswith("DRAFT")
    assert STANDARDS_STATUS.startswith("DRAFT")


def test_spec_id_and_version_draft_v2():
    assert DRAFTING_SPEC_V1["spec_id"] == "roaddraft-drafting-spec"
    assert DRAFTING_SPEC_V1["version"] == "draft-v2"
    assert spec_v1.SPEC_VERSION == "draft-v2"


def test_layers_are_caltrans_named_levels_with_props_and_sources():
    layers = DRAFTING_SPEC_V1["layers"]
    props = DRAFTING_SPEC_V1["layer_props"]
    levels = DRAFTING_SPEC_V1["caltrans_levels"]
    assert set(layers) == {"alignment", "ticks", "labels", "tables", "edges", "dims", "symbols",
                           "match"}
    assert layers["alignment"] == "align_MAIN" and layers["ticks"] == "align_MAIN-anno"
    assert layers["labels"] == "align_MAIN-anno" and layers["tables"] == "align_CURVE-DATA"
    assert layers["edges"] == "rd_EP" and layers["dims"] == "rd_LAYOUT-NOTE-anno"
    assert layers["symbols"] == "pp_PRESENTATION" and layers["match"] == "border_INSIDE-BORDER-anno"
    layer_set = DRAFTING_SPEC_V1["layer_set"]
    assert len(layer_set) == len(set(layer_set)) == 16
    assert set(layers.values()) <= set(layer_set) == set(props) == set(levels)
    wt = DRAFTING_SPEC_V1["lineweight_mm_by_wt"]
    for name in layer_set:
        assert "color" in props[name] and "lineweight_mm" in props[name], name
        assert "Caltrans level %d" % levels[name]["number"] in props[name]["description"], name
        assert props[name]["lineweight_mm"] == wt[str(levels[name]["weight"])], name
        assert "cadd-appx-a10" in levels[name]["source"], name
    # the CADD Users Manual's main-route alignment is the heaviest plan line, the border heavier
    assert levels["align_MAIN"]["weight"] == 3 and levels["border_SHEET"]["weight"] == 4
    assert levels["rd_EP"]["weight"] == 2  # the PPM layout checklist's "usually WT=2"


def test_curve_table_columns_in_catalog():
    columns = DRAFTING_SPEC_V1["curve_table"]["columns"]
    assert columns == ["curve", "radius", "delta", "tangent", "length"]  # No., R, Δ, T, L
    assert DRAFTING_SPEC_V1["curve_table"]["headers"] == ["No.", "R", "Δ", "T", "L"]
    for key in columns:
        assert key in CURVE_TABLE_COLUMN_CATALOG, key
    assert len(columns) == len(set(columns))
    assert DRAFTING_SPEC_V1["curve_table"]["title"] == "CURVE DATA"


def test_sheet_ANSI_D_viewport_17_11_7_31x18_5_fit_26x15_north_arrow_31_6_19_2():
    sheet = DRAFTING_SPEC_V1["sheet"]
    assert sheet["size"] == "ANSI_D"
    assert sheet["allowed_feet_per_inch"] == [50, 100]
    assert sheet["viewport"] == {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5}
    assert sheet["fit_window_in"] == [26.0, 15.0]
    assert sheet["north_arrow"] == {"required": True, "block": "NORTH_ARROW", "position": [31.6, 19.2], "scale": 0.9}
    assert len(sheet["required_title_fields"]) == 10
    assert sheet["scale_text_format"].format(fpi=50) == "1\" = 50'"
    assert sheet["scale_text_format"].format(fpi=100) == "1\" = 100'"


def test_text_0_10_0_12_stationing_100_tick_0_20_offset_0_32():
    assert DRAFTING_SPEC_V1["units"] == {"model": "us_survey_ft", "paper": "inch"}
    text = DRAFTING_SPEC_V1["text"]
    assert text["label_height_in"] == pytest.approx(0.10)
    assert text["table_height_in"] == pytest.approx(0.12)
    assert text["height_tolerance_pct"] == 10
    st = DRAFTING_SPEC_V1["stationing"]  # the PPM's stationing (ppm-text p. 2-8)
    assert st["interval_ft"] == 100 and st["full_station_every_ft"] == 500
    assert st["format"] == "caltrans" and st["decimals"] == 2
    assert st["tick_half_len_in"] == pytest.approx(0.07)  # a 7 ft tick at 1" = 50'
    assert st["label_offset_in"] == pytest.approx(0.12)
    assert st["label_side"] == "below" and st["rotation"] == "along"


def test_labels_required_pc_pt_bearing_mc_not_pi_equation_when_present():
    labels = DRAFTING_SPEC_V1["labels"]
    assert labels["pc_pt"]["required"] is True and labels["pc_pt"]["side"] == "left"
    assert labels["pc_pt"]["format"] == "24+05.27 BC" and labels["pc_pt"]["rotation"] == "perpendicular"
    assert labels["pc_pt"]["label_offset_in"] == pytest.approx(0.45)
    assert labels["bearing"]["required"] is True and labels["bearing"]["anchor"] == "T-n"
    assert labels["bearing"]["format"] == "quadrant" and labels["bearing"]["seconds_decimals"] == 0
    assert labels["bearing"]["side"] == "above" and labels["bearing"]["with_length"] is True
    assert labels["mc"]["required"] is True and labels["mc"]["format"] == "1"
    assert labels["mc"]["bubble"]["radius_text_heights"] == 2.0
    assert labels["pi"]["required"] is False
    assert labels["equation"]["required_when_present"] is True
    assert labels["equation"]["format"] == "STA 20+00.00 BK = STA 25+00.00 AH"


def test_tolerances_0_005_ft_1_sec_0_05_position_1_deg():
    tol = DRAFTING_SPEC_V1["tolerances"]
    assert tol == {"length_ft": 0.005, "station_ft": 0.005, "angle_seconds": 1,
                   "position_model_ft": 0.05, "position_paper_in": 0.05, "rotation_deg": 1.0}


def test_sheet_setup_check_and_reweighting_decided_2026_10_09():
    weights = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}
    assert weights["D1-00"] == 5 and weights["D1-02"] == 9 and weights["D1-11"] == 1
    hard = {c["id"] for c in DRAFTING_SPEC_V1["checks"] if c["hard_fail"]}
    assert hard == {"D1-01", "D1-03", "D1-04", "D1-05", "D1-06", "D1-12", "D1-13", "D1-15"}
    scoring = DRAFTING_SPEC_V1["scoring"]
    assert "hard fail" in scoring["hard_fail"] and scoring["effective_score"].startswith("0 if hard")


def test_spec_is_json_serializable_round_trip():
    text = json.dumps(DRAFTING_SPEC_V1)
    assert json.loads(text) == DRAFTING_SPEC_V1


# --- spec_hash ---------------------------------------------------------------------------------

def test_spec_hash_stable_across_two_calls():
    first = spec_hash()
    second = spec_hash()
    assert first == second
    assert re.fullmatch(r"sha256:[0-9a-f]{16}", first), first


def test_spec_hash_equals_sha256_of_canonical_json_16_hex():
    canonical = json.dumps(DRAFTING_SPEC_V1, sort_keys=True, separators=(",", ":"))
    expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    assert spec_hash() == expected


def test_spec_hash_independent_of_key_order_but_changes_with_content():
    reordered = {k: DRAFTING_SPEC_V1[k] for k in reversed(list(DRAFTING_SPEC_V1))}
    assert spec_hash(reordered) == spec_hash()
    edited = copy.deepcopy(DRAFTING_SPEC_V1)
    edited["checks"][0]["weight"] += 1
    assert spec_hash(edited) != spec_hash()
    assert spec_hash() == spec_hash(DRAFTING_SPEC_V1)  # the edit did not touch the module constant


# --- spec_subset -------------------------------------------------------------------------------

def test_spec_subset_default_12_sections_omits_id_version_status():
    subset = spec_subset()
    assert list(subset) == list(SPEC_SUBSET_KEYS)
    assert len(subset) == 12
    assert set(subset).isdisjoint({"spec_id", "version", "status"})
    for key in subset:
        assert subset[key] == DRAFTING_SPEC_V1[key]


def test_spec_subset_is_deep_copy_and_orders_by_keys():
    subset = spec_subset(("layers", "units"))
    assert list(subset) == ["layers", "units"]
    subset["layers"]["alignment"] = "X"
    assert DRAFTING_SPEC_V1["layers"]["alignment"] == "align_MAIN"
    nested = spec_subset(("checks",))
    nested["checks"][0]["weight"] = 0
    assert DRAFTING_SPEC_V1["checks"][0]["weight"] == 5


def test_spec_subset_unknown_key_raises_listing_sections():
    with pytest.raises(ValueError) as e:
        spec_subset(("units", "nope"))
    assert "'nope'" in str(e.value) and "tolerances" in str(e.value)


# --- standards ---------------------------------------------------------------------------------

def test_min_radius_45_is_643():
    assert min_radius(45) == 643
    assert isinstance(min_radius(45), float)


def test_max_grade_50_is_6():
    assert max_grade(50) == 6


def test_min_k_45_crest_61_sag_79():
    assert min_k(45, "crest") == 61
    assert min_k(45, "sag") == 79


def test_generator_speeds_35_to_55_all_tabulated_and_monotonic():
    for v in (35, 40, 45, 50, 55):
        assert min_radius(v) > 0 and max_grade(v) > 0
        assert min_k(v, "crest") > 0 and min_k(v, "sag") > 0
    radii = [min_radius(v) for v in sorted(standards.MIN_RADIUS_FT_EMAX6)]
    assert radii == sorted(radii)
    ks = [min_k(v, "crest") for v in sorted(standards.MIN_K_CREST)]
    assert ks == sorted(ks)
    assert MIN_VC_LENGTH_FT == 200.0


def test_standards_unknown_speed_and_curve_type_raise():
    with pytest.raises(ValueError) as e:
        min_radius(42)
    assert "42" in str(e.value) and "45" in str(e.value)
    with pytest.raises(ValueError):
        max_grade(65)
    with pytest.raises(ValueError):
        min_k(45, "hump")


# --- package hygiene ---------------------------------------------------------------------------

def test_tasks_data_modules_import_only_stdlib():
    """standards.py, spec_v1.py and __init__.py must not import design/document/api/commands/web."""
    pkg_dir = os.path.dirname(spec_v1.__file__)
    forbidden = re.compile(r"^\s*(from|import)\s+roaddraft\.(design|document|api|commands|web|adapters|render|core)\b",
                           re.MULTILINE)
    for name in ("__init__.py", "standards.py", "spec_v1.py"):
        with open(os.path.join(pkg_dir, name), encoding="utf-8") as fh:
            source = fh.read()
        assert not forbidden.search(source), "%s imports a forbidden package" % name


def test_tasks_init_is_docstring_only():
    import roaddraft.tasks as pkg
    with open(pkg.__file__, encoding="utf-8") as fh:
        source = fh.read()
    assert pkg.__doc__ and pkg.__doc__.strip()
    assert source.strip().startswith('"""') and source.strip().endswith('"""')
