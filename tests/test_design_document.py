"""WP4 tests: Document.design and Entity.anchor wiring (spec sections 2.6, 2.7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.model import DesignModel
from roaddraft.design.stations import StationEquation
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document.document import SCHEMA_VERSION, Document
from roaddraft.document.entities import (
    Arc, BlockRef, Line, Table, Text, as_anchor, entity_from_dict, expand_entities,
)

FIXTURES = Path(__file__).parent / "fixtures"
A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]
ANCHOR = {"alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc", "station": 1600.0, "offset": 0.0,
          "side": "right", "label_offset": 16.0, "rotation": "along", "viewport": None,
          "content_auto": True}


def design_doc() -> Document:
    doc = Document.new("Design")
    align = Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                      begin_station=1000.0, equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    doc.design.alignments["ALIGN-1"] = align
    doc.design.profiles["PROF-1"] = Profile(name="PROF-1", alignment="ALIGN-1",
                                            pvis=[PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90)])
    return doc


def test_document_round_trip_with_alignment_profile_equation():
    doc = design_doc()
    d = doc.to_dict()
    assert d["schema_version"] == SCHEMA_VERSION == "0.2"
    keys = list(d)
    assert keys.index("references") < keys.index("design") < keys.index("id_counters")
    assert d["design"]["alignments"]["ALIGN-1"]["equations"] == [
        {"raw_station": 2000.0, "back": 2000.0, "ahead": 2500.0}]
    assert d["design"]["profiles"]["PROF-1"]["pvis"][1] == {"station": 2000.0, "elevation": 120.0,
                                                            "length": 400.0}
    back = Document.from_dict(json.loads(json.dumps(d)))
    assert back.to_dict() == d
    assert isinstance(back.design, DesignModel)
    assert back.design.alignments["ALIGN-1"].length == pytest.approx(1518.879, abs=1e-3)
    assert back.design.profiles_of("ALIGN-1")[0].name == "PROF-1"
    assert back.design.fingerprint() == doc.design.fingerprint()


def test_from_dict_without_design_key_loads_empty_design():
    d = Document.new("Plain").to_dict()
    del d["design"]
    doc = Document.from_dict(d)
    assert doc.design.alignments == {} and doc.design.profiles == {}
    assert doc.to_dict()["design"] == {"alignments": {}, "profiles": {}}


def test_legacy_v01_fixture_loads():
    data = json.loads((FIXTURES / "legacy_v01.rdoc.json").read_text())
    assert data["schema_version"] == "0.1" and "design" not in data
    doc = Document.from_dict(data)
    assert len(doc.model_entities) == 2 and len(doc.sheets) == 1
    assert doc.design.alignments == {}
    for e in doc.model_entities.values():
        assert e.anchor is None and "anchor" not in e.to_dict()


def test_entity_without_anchor_serializes_without_key():
    line = Line(id="LN-001", start=[0, 0], end=[1, 1])
    assert "anchor" not in line.to_dict()
    assert Line.from_dict(line.to_dict()).anchor is None
    assert Line.from_dict({**line.to_dict(), "anchor": None}).anchor is None


def test_text_anchor_round_trip_and_translated_keeps_it():
    t = Text(id="TX-001", position=[1600, 984], content="PC 16+00.00", height=8, anchor=ANCHOR)
    d = t.to_dict()
    assert d["anchor"] == ANCHOR
    assert d["anchor"] is not t.anchor  # a copy
    back = entity_from_dict(json.loads(json.dumps(d)))
    assert back.anchor == ANCHOR
    moved = t.translated([10, 5])
    assert moved.anchor == ANCHOR and moved.position == [1610, 989]


def test_line_arc_table_blockref_transformed_keep_anchor():
    fn = lambda p: [p[0] * 2, p[1] * 2]
    a = {"alignment": "ALIGN-1", "ref": "T-1", "kind": "element", "station": 1000.0, "offset": 0.0}
    line = Line(id="LN-1", start=[0, 0], end=[1, 0], anchor=a)
    arc = Arc(id="AR-1", center=[0, 0], radius=1, anchor=a)
    table = Table(id="TB-1", position=[0, 0], columns=[{"header": "A", "width": 1}], rows=[["1"]],
                  anchor={"alignment": "ALIGN-1", "ref": "CURVES", "kind": "curve_table",
                          "content_auto": True})
    ref = BlockRef(id="BR-1", block_name="NORTH_ARROW", position=[0, 0], anchor=a)
    for e in (line, arc, table, ref):
        t = e.transformed(fn, 10.0, 2.0)
        assert t.anchor == e.anchor
        assert entity_from_dict(t.to_dict()).anchor == e.anchor


def test_expand_entities_block_with_anchored_text_keeps_anchor():
    doc = Document.new("B")
    block = doc.blocks["NORTH_ARROW"]
    block.entities[-1].anchor = {"alignment": "ALIGN-1", "ref": "BEGIN", "kind": "custom"}
    ref = BlockRef(id="BR-001", block_name="NORTH_ARROW", position=[5, 5], scale=2.0)
    prims = expand_entities(doc, [ref])
    texts = [p for p in prims if isinstance(p, Text)]
    assert texts and texts[0].anchor == {"alignment": "ALIGN-1", "ref": "BEGIN", "kind": "custom"}
    assert texts[0].id == "BR-001:B4"


def test_as_anchor_rejects_string_and_bad_key():
    assert as_anchor(None) is None
    assert as_anchor({"alignment": "A", "ref": "PC-1", "kind": "pc"}) == {
        "alignment": "A", "ref": "PC-1", "kind": "pc"}
    full = as_anchor(ANCHOR)
    assert full == ANCHOR and full is not ANCHOR
    for bad in ("PC-1", ["a"], 3, {"alignment": "A", "ref": "PC-1"},
                {"alignment": "A", "ref": "", "kind": "pc"},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "bogus": 1},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "station": "16+00"},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "side": "up"},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "rotation": "spin"},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "content_auto": "yes"},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "viewport": 1},
                {"alignment": "A", "ref": "PC-1", "kind": "pc", "station": True}):
        with pytest.raises(ValueError) as ei:
            as_anchor(bad)
        assert str(ei.value).startswith("anchor:")
    with pytest.raises(ValueError):
        Text.from_dict({"position": [0, 0], "content": "x", "height": 1, "anchor": "PC-1"})
