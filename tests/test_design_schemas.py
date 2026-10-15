"""WP3: design command schemas (commands/design_schemas.py).

Checks the ten design command schemas/examples, that the re-declared
fragments stay byte-identical to commands/schemas.py, and that
design_schemas never imports schemas.py (which imports it back).
"""
import os
import subprocess
import sys

import jsonschema
import pytest
from jsonschema import Draft202012Validator

from roaddraft.commands import design_schemas as ds
from roaddraft.commands import schemas as base

DESIGN_COMMANDS = {"create_alignment", "modify_alignment", "delete_alignment",
                   "create_profile", "delete_profile", "draw_alignment", "draw_offset",
                   "place_label", "place_curve_table", "import_landxml"}

LABEL_KINDS_13 = ["station", "pc", "pt", "pi", "mc", "pcc", "prc", "bearing", "begin",
                  "end", "equation", "curve_data", "custom"]


def _validator(name):
    return Draft202012Validator(ds.DESIGN_SCHEMAS[name])


def _ok(name, params):
    return _validator(name).is_valid(params)


# --- the three tests named in the spec (section 9) --------------------------

def test_every_example_validates_against_its_schema():
    for name, schema in ds.DESIGN_SCHEMAS.items():
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(ds.DESIGN_EXAMPLES[name])


def test_every_schema_closed_additionalProperties_false():
    for name, schema in ds.DESIGN_SCHEMAS.items():
        assert schema["type"] == "object", name
        assert schema["additionalProperties"] is False, name
        assert isinstance(schema["required"], list), name
        assert set(schema["required"]) <= set(schema["properties"]), name
    # nested object fragments are closed too
    assert ds.EQUATION["additionalProperties"] is False
    assert ds.ELEMENT["additionalProperties"] is False


def test_schema_and_example_keys_equal_the_ten_design_commands():
    assert set(ds.DESIGN_SCHEMAS) == DESIGN_COMMANDS
    assert set(ds.DESIGN_EXAMPLES) == DESIGN_COMMANDS
    assert len(ds.DESIGN_SCHEMAS) == 10 and len(ds.DESIGN_EXAMPLES) == 10
    # none of them collides with an existing base command
    assert not (DESIGN_COMMANDS & set(base.SCHEMAS) - DESIGN_COMMANDS)


# --- re-declared fragments must equal schemas.py's (drift guard) -----------

@pytest.mark.parametrize("frag", ["POINT", "NUM", "POS", "STR", "NSTR", "SPACE",
                                  "HALIGN", "VALIGN", "COLOR", "LINETYPE"])
def test_redeclared_fragment_equals_schemas_py(frag):
    assert getattr(ds, frag) == getattr(base, frag), frag


def test_obj_helper_equals_schemas_py_obj():
    assert ds.obj({}) == base.obj({})
    assert ds.obj({"a": ds.NUM}, ["a"]) == base.obj({"a": base.NUM}, ["a"])
    assert ds.obj({"a": ds.NUM}, ("a",), True) == base.obj({"a": base.NUM}, ("a",), True)
    assert ds.obj({"a": ds.NUM})["additionalProperties"] is False
    assert ds.obj({"a": ds.NUM}, ["a"])["required"] == ["a"]


def test_label_kinds_literal_13_values():
    assert isinstance(ds.LABEL_KINDS, list)
    assert ds.LABEL_KINDS == LABEL_KINDS_13
    assert len(set(ds.LABEL_KINDS)) == 13
    assert ds.KIND == {"enum": LABEL_KINDS_13}
    assert ds.KIND["enum"] is not ds.LABEL_KINDS  # a copy, not the same list


# --- fragment shapes pinned by the spec preamble ----------------------------

def test_fragments_match_spec_preamble():
    # the spec's example stations and offsets were the probe fixture's; since
    # 2026-10-14 the help text uses its own (tests/test_help_text.py)
    assert ds.STATION == {"type": ["number", "string"],
                          "description": "display station: feet (8400) or '84+00.00'"}
    assert ds.PI_ITEM == {"type": "array", "items": ds.NUM, "minItems": 2, "maxItems": 3,
                          "description": "[x, y] or [x, y, radius]"}
    assert ds.PVI_ITEM == {"type": "array", "items": ds.NUM, "minItems": 2, "maxItems": 3,
                           "description": "[station, elevation] or "
                                          "[station, elevation, vc_length]"}
    assert ds.EQUATION == ds.obj({"back": ds.STATION, "ahead": ds.STATION,
                                  "raw_station": ds.NUM}, ["back", "ahead"])
    assert ds.ELEMENT["required"] == ["kind"]
    assert ds.ELEMENT["properties"]["kind"] == {"enum": ["tangent", "curve"]}
    assert ds.ELEMENT["properties"]["direction"] == {"enum": ["L", "R"]}
    assert set(ds.ELEMENT["properties"]) == {"kind", "start", "end", "pc", "pt", "center",
                                             "radius", "direction"}
    assert ds.ANCHOR["type"] == ["string", "number", "object"]
    assert "PC-2@18" in ds.ANCHOR["description"]
    assert ds.ROTATION == {"enum": ["along", "perpendicular", "horizontal"]}
    assert ds.SIDE["enum"] == ["left", "right", "above", "below"]


# --- per-command property sets and required lists ---------------------------

def test_create_alignment_properties_and_required():
    s = ds.DESIGN_SCHEMAS["create_alignment"]
    assert set(s["properties"]) == {"name", "pis", "elements", "begin_station",
                                    "equations", "description", "angle_points",
                                    "start", "legs"}
    # a layout by bearings and distances: start + legs (added Oct 2026)
    assert s["properties"]["start"]["type"] == "array"
    assert s["properties"]["legs"]["items"] == ds.ALIGNMENT_LEG
    assert s["properties"]["angle_points"]["type"] == "boolean"
    assert s["required"] == ["name"]
    assert s["properties"]["pis"] == {"type": "array", "items": ds.PI_ITEM, "minItems": 2}
    assert s["properties"]["elements"] == {"type": "array", "items": ds.ELEMENT,
                                           "minItems": 1}
    assert s["properties"]["begin_station"] == ds.STATION
    assert s["properties"]["equations"] == {"type": "array", "items": ds.EQUATION}


def test_modify_delete_alignment_and_profile_shapes():
    m = ds.DESIGN_SCHEMAS["modify_alignment"]
    assert m["required"] == ["name", "changes"]
    assert m["properties"]["changes"]["minProperties"] == 1
    for key in ("pis", "begin_station", "equations", "description", "rename"):
        assert key in m["properties"]["changes"]["description"]
    d = ds.DESIGN_SCHEMAS["delete_alignment"]
    assert d["required"] == ["name"]
    assert d["properties"]["cascade"]["type"] == "boolean"
    p = ds.DESIGN_SCHEMAS["create_profile"]
    assert p["required"] == ["name", "alignment", "pvis"]
    assert p["properties"]["pvis"] == {"type": "array", "items": ds.PVI_ITEM, "minItems": 2}
    assert ds.DESIGN_SCHEMAS["delete_profile"] == ds.obj({"name": ds.NSTR}, ["name"])


def test_draw_alignment_no_required_and_replace_flag():
    s = ds.DESIGN_SCHEMAS["draw_alignment"]
    assert s["required"] == []
    assert set(s["properties"]) == {"alignment", "layer", "color", "linetype", "replace"}
    assert s["properties"]["linetype"] == ds.LINETYPE
    assert s["properties"]["replace"]["type"] == "boolean"


def test_place_label_properties_and_required_space_anchor():
    s = ds.DESIGN_SCHEMAS["place_label"]
    assert s["required"] == ["space", "anchor"]
    assert set(s["properties"]) == {"space", "alignment", "anchor", "kind", "content", "side",
                                    "label_offset", "rotation", "height", "style", "halign",
                                    "valign", "layer", "color", "linetype", "viewport",
                                    "view_rotation"}
    assert s["properties"]["anchor"] == ds.ANCHOR
    assert s["properties"]["kind"] == ds.KIND
    assert s["properties"]["side"] == ds.SIDE
    assert s["properties"]["rotation"]["enum"] == ds.ROTATION["enum"]
    assert s["properties"]["label_offset"]["minimum"] == 0
    assert s["properties"]["height"]["exclusiveMinimum"] == 0
    assert s["properties"]["halign"] == ds.HALIGN
    assert s["properties"]["valign"] == ds.VALIGN


def test_place_curve_table_properties_and_required_space_position():
    s = ds.DESIGN_SCHEMAS["place_curve_table"]
    assert s["required"] == ["space", "position"]
    assert set(s["properties"]) == {"space", "alignment", "position", "curves", "columns",
                                    "first_curve_number", "title", "text_height", "layer",
                                    "style", "color"}
    assert s["properties"]["curves"]["items"] == {"type": "integer", "minimum": 1}
    assert s["properties"]["columns"]["minItems"] == 1
    for key in ("curve", "pi_sta", "pc_sta", "pt_sta", "delta", "direction", "radius",
                "tangent", "length", "external", "mid_ordinate", "chord", "chord_bearing"):
        assert key in s["properties"]["columns"]["description"]


def test_import_landxml_properties_and_on_conflict_enum():
    s = ds.DESIGN_SCHEMAS["import_landxml"]
    assert s["required"] == []
    assert set(s["properties"]) == {"path", "xml", "alignments", "on_conflict"}
    assert s["properties"]["on_conflict"] == {"enum": ["error", "replace", "rename"]}
    assert s["properties"]["alignments"] == {"type": "array", "items": ds.NSTR}


# --- validation behaviour: accepts and rejects ------------------------------

def test_create_alignment_accepts_string_and_numeric_station_and_equations():
    assert _ok("create_alignment", {"name": "A", "begin_station": 1000,
                                    "pis": [[0, 0], [100, 0, 50], [200, 100]]})
    assert _ok("create_alignment", {"name": "A", "begin_station": "10+00",
                                    "pis": [[0, 0], [200, 100]],
                                    "equations": [{"back": "20+00", "ahead": 2500}]})
    assert _ok("create_alignment", {"name": "A", "equations": [
        {"back": 2000, "ahead": 2500, "raw_station": 2000.0}]})


def test_create_alignment_rejects_bad_pis_and_extra_keys():
    assert not _ok("create_alignment", {"name": "A", "pis": [[0, 0]]})          # minItems 2
    assert not _ok("create_alignment", {"name": "A", "pis": [[0, 0], [1]]})     # item minItems
    assert not _ok("create_alignment", {"name": "A", "pis": [[0, 0], [1, 2, 3, 4]]})
    assert not _ok("create_alignment", {"name": "A", "pis": [[0, 0], ["1", 2]]})
    assert not _ok("create_alignment", {"name": "", "pis": [[0, 0], [1, 2]]})
    assert not _ok("create_alignment", {"pis": [[0, 0], [1, 2]]})               # name required
    assert not _ok("create_alignment", {"name": "A", "pis": [[0, 0], [1, 2]], "bogus": 1})
    assert not _ok("create_alignment", {"name": "A", "begin_station": True})
    assert not _ok("create_alignment", {"name": "A", "equations": [{"back": 1}]})
    assert not _ok("create_alignment", {"name": "A",
                                        "equations": [{"back": 1, "ahead": 2, "x": 3}]})


def test_create_alignment_elements_minimal_import_shape_and_spiral_rejected():
    assert _ok("create_alignment", {"name": "A", "elements": [
        {"kind": "tangent", "start": [0, 0], "end": [600, 0]},
        {"kind": "curve", "pc": [600, 0], "pt": [1000, 107.18], "center": [600, 800],
         "direction": "L"}]})
    assert _ok("create_alignment", {"name": "A", "elements": [
        {"kind": "curve", "pc": [600, 0], "pt": [1000, 107.18], "center": [600, 800],
         "radius": 800, "direction": "R"}]})
    assert not _ok("create_alignment", {"name": "A", "elements": []})
    assert not _ok("create_alignment", {"name": "A", "elements": [{"kind": "spiral"}]})
    assert not _ok("create_alignment", {"name": "A", "elements": [{"start": [0, 0]}]})
    assert not _ok("create_alignment", {"name": "A", "elements": [
        {"kind": "curve", "direction": "left"}]})
    assert not _ok("create_alignment", {"name": "A", "elements": [
        {"kind": "curve", "radius": 0}]})
    assert not _ok("create_alignment", {"name": "A", "elements": [
        {"kind": "tangent", "length": 600}]})   # stored-shape keys are not accepted


def test_modify_alignment_rejects_empty_changes():
    assert _ok("modify_alignment", {"name": "A", "changes": {"rename": "B"}})
    assert not _ok("modify_alignment", {"name": "A", "changes": {}})
    assert not _ok("modify_alignment", {"name": "A"})


def test_delete_alignment_cascade_must_be_boolean():
    assert _ok("delete_alignment", {"name": "A", "cascade": True})
    assert not _ok("delete_alignment", {"name": "A", "cascade": "yes"})
    assert not _ok("delete_alignment", {})


def test_create_profile_pvis_2_or_3_numbers():
    assert _ok("create_profile", {"name": "P", "alignment": "A",
                                  "pvis": [[1000, 100], [2000, 120, 400], [3000, 90]]})
    assert not _ok("create_profile", {"name": "P", "alignment": "A", "pvis": [[1000, 100]]})
    assert not _ok("create_profile", {"name": "P", "alignment": "A",
                                      "pvis": [[1000, 100], [2000, 120, 400, 1]]})
    assert not _ok("create_profile", {"name": "P", "pvis": [[1000, 100], [2000, 120]]})


def test_draw_alignment_linetype_and_color_types():
    assert _ok("draw_alignment", {})
    assert _ok("draw_alignment", {"alignment": "A", "layer": "CL", "color": "red",
                                  "linetype": "center", "replace": True})
    assert not _ok("draw_alignment", {"linetype": "wavy"})
    assert not _ok("draw_alignment", {"color": 1})
    assert not _ok("draw_alignment", {"replace": "true"})
    assert not _ok("draw_alignment", {"path_ids": ["LN-001"]})


def test_place_label_anchor_forms_string_number_dict_not_bool_or_list():
    base_p = {"space": "model"}
    assert _ok("place_label", {**base_p, "anchor": "PC-1"})
    assert _ok("place_label", {**base_p, "anchor": "18+00@25L"})
    assert _ok("place_label", {**base_p, "anchor": 1800})
    assert _ok("place_label", {**base_p, "anchor": 1800.5})
    assert _ok("place_label", {**base_p, "anchor": {"ref": "PC-1", "offset": 10}})
    assert _ok("place_label", {**base_p, "anchor": {"station": "18+00", "offset": 25.0,
                                                    "region": 2}})
    assert not _ok("place_label", {**base_p, "anchor": True})
    assert not _ok("place_label", {**base_p, "anchor": ["PC-1"]})
    assert not _ok("place_label", {**base_p, "anchor": None})
    assert not _ok("place_label", base_p)                                # anchor required
    assert not _ok("place_label", {"anchor": "PC-1"})                    # space required


def test_place_label_enums_and_numeric_bounds():
    p = {"space": "model", "anchor": "PC-1"}
    for kind in LABEL_KINDS_13:
        assert _ok("place_label", {**p, "kind": kind}), kind
    assert not _ok("place_label", {**p, "kind": "curve"})
    assert _ok("place_label", {**p, "side": "left", "rotation": "perpendicular",
                               "label_offset": 0, "height": 5, "halign": "center",
                               "valign": "top", "content": "PC 16+00", "viewport": "VP-001",
                               "style": "STANDARD", "layer": "V-ANNO-TEXT", "color": "black",
                               "linetype": "continuous"})
    assert not _ok("place_label", {**p, "side": "up"})
    assert not _ok("place_label", {**p, "rotation": "vertical"})
    assert not _ok("place_label", {**p, "label_offset": -1})
    assert not _ok("place_label", {**p, "height": 0})
    assert not _ok("place_label", {**p, "halign": "middle"})
    assert not _ok("place_label", {**p, "valign": "center"})
    assert not _ok("place_label", {**p, "viewport": ""})
    assert not _ok("place_label", {**p, "position": [0, 0]})             # not a raw text


def test_place_curve_table_curves_columns_position():
    p = {"space": "C-101", "position": [24.0, 8.5]}
    assert _ok("place_curve_table", p)
    assert _ok("place_curve_table", {**p, "alignment": "A", "curves": [1, 2],
                                     "columns": ["curve", "radius"], "title": "CURVE DATA",
                                     "text_height": 0.12, "layer": "V-ANNO-TABL",
                                     "style": "STANDARD", "color": "black"})
    assert not _ok("place_curve_table", {"space": "C-101"})
    assert not _ok("place_curve_table", {"position": [24.0, 8.5]})
    assert not _ok("place_curve_table", {**p, "position": [24.0]})
    assert not _ok("place_curve_table", {**p, "curves": [0]})
    assert not _ok("place_curve_table", {**p, "curves": [1.5]})
    assert not _ok("place_curve_table", {**p, "columns": []})
    assert not _ok("place_curve_table", {**p, "text_height": 0})
    assert not _ok("place_curve_table", {**p, "rows": [["C-1"]]})


def test_import_landxml_path_xml_alignments_on_conflict():
    assert _ok("import_landxml", {"path": "survey/alignments.xml"})
    assert _ok("import_landxml", {"xml": "<LandXML/>", "alignments": ["ALIGN-1"],
                                  "on_conflict": "rename"})
    assert _ok("import_landxml", {})     # exactly-one-of path/xml is the handler's job
    assert not _ok("import_landxml", {"path": ""})
    assert not _ok("import_landxml", {"on_conflict": "skip"})
    assert not _ok("import_landxml", {"alignments": "ALIGN-1"})
    assert not _ok("import_landxml", {"alignments": [""]})


def test_best_match_gives_a_readable_teaching_error():
    err = jsonschema.exceptions.best_match(
        _validator("create_alignment").iter_errors({"name": "A", "pis": [[0, 0]]}))
    assert err is not None and "too short" in err.message


# --- import direction: no cycle back into schemas.py -----------------------

def test_design_schemas_source_never_imports_schemas_py():
    src = open(ds.__file__, encoding="utf-8").read()
    assert "roaddraft.commands.schemas" not in src.replace("``roaddraft.commands.schemas``", "")
    assert "from roaddraft.commands import schemas" not in src
    assert "from . import schemas" not in src
    assert "from .schemas" not in src
    assert "roaddraft.design" not in src.replace("``design.labels", "")
    assert "import numpy" not in src


def test_design_schemas_imports_with_schemas_py_blocked():
    """Simulate the future cycle: schemas.py imports design_schemas at its end,
    so design_schemas must load while schemas.py is unavailable. (Note that
    roaddraft/__init__.py imports the api, which loads schemas.py before any
    submodule runs, so a plain sys.modules check cannot prove this.)"""
    code = (
        "import sys, importlib.abc\n"
        "import roaddraft, roaddraft.commands\n"          # package init loads the api
        "sys.modules.pop('roaddraft.commands.design_schemas', None)\n"
        "sys.modules.pop('roaddraft.commands.schemas', None)\n"
        "if hasattr(roaddraft.commands, 'schemas'):\n"
        "    delattr(roaddraft.commands, 'schemas')\n"
        "class Block(importlib.abc.MetaPathFinder):\n"
        "    def find_spec(self, name, path, target=None):\n"
        "        if name == 'roaddraft.commands.schemas':\n"
        "            raise ImportError('design_schemas must not import schemas.py')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import roaddraft.commands.design_schemas as ds\n"
        "assert 'roaddraft.commands.schemas' not in sys.modules, 'cycle'\n"
        "assert len(ds.DESIGN_SCHEMAS) == 10 and len(ds.DESIGN_EXAMPLES) == 10\n"
        "print('blocked-ok')\n")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env)
    assert out.returncode == 0, out.stderr
    assert "blocked-ok" in out.stdout
