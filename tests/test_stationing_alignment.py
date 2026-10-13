"""WP6 tests: annotate_stationing in alignment mode (spec section 4.10)."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Line, Text
from tests.test_stationing import centerline_session

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def alignment_session(**extra):
    s = Session(project_name="sta-align")
    r = s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00", "pis": A_PIS,
                                       **extra})
    assert r["ok"], r
    s.execute("create_layer", {"name": "CL", "color": "red"})
    return s


def texts(s):
    return [e for e in s.doc.model_entities.values() if isinstance(e, Text)]


def lines(s):
    return [e for e in s.doc.model_entities.values() if isinstance(e, Line)]


def test_alignment_mode_A_matches_entity_mode_labels_16_BC_EC():
    ent, ids = centerline_session()
    r_ent = ent.execute("annotate_stationing", {"space": "model", "path_ids": ids,
                                                "begin_station": 1000.0, "interval": 100.0})
    ali = alignment_session()
    r_ali = ali.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                                "interval": 100.0})
    assert r_ali["ok"], r_ali
    assert r_ali["message"] == ("stationing annotated in model space from ALIGN-1: 16 ticks @ "
                                "100 ft lettered the whole station at each 500 ft, the ones digit "
                                "elsewhere, 2 BC/EC labels, 0 equation labels, stations 10+00.00 "
                                "to 25+18.88")
    assert len(r_ali["created"]) == len(r_ent["created"]) == 34
    ent_texts = sorted(texts(ent), key=lambda t: t.id)
    ali_texts = sorted(texts(ali), key=lambda t: t.id)
    assert [t.content for t in ent_texts] == [t.content for t in ali_texts]
    for a, b in zip(ent_texts, ali_texts):
        assert a.position == pytest.approx(b.position, abs=1e-6)
        assert a.rotation_deg == pytest.approx(b.rotation_deg, abs=1e-6)
        assert (a.halign, a.valign, a.height) == (b.halign, b.valign, b.height)
    ent_ticks = [e for e in lines(ent) if e.layer == "0"]
    ali_ticks = [e for e in lines(ali) if e.anchor and e.anchor["kind"] == "tick"]
    assert len(ent_ticks) == len(ali_ticks) == 16
    for a, b in zip(ent_ticks, ali_ticks):
        assert a.start == pytest.approx(b.start, abs=1e-6)
        assert a.end == pytest.approx(b.end, abs=1e-6)


def test_alignment_mode_every_tick_and_label_anchored_entity_mode_none():
    ent, ids = centerline_session()
    ent.execute("annotate_stationing", {"space": "model", "path_ids": ids, "begin_station": 1000.0})
    assert all(e.anchor is None for e in ent.doc.model_entities.values())
    ali = alignment_session()
    ali.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1", "layer": "CL",
                                        "label_layer": "0"})
    for e in ali.doc.model_entities.values():
        assert e.anchor and e.anchor["alignment"] == "ALIGN-1"
        if isinstance(e, Line):
            assert e.anchor["kind"] == "tick" and e.layer == "CL"
            assert e.anchor["ref"].count("+") == 1 and e.anchor["offset"] == 0.0
        else:
            assert e.layer == "0"
            assert e.anchor["kind"] in ("station", "pc", "pt")
            assert e.anchor["content_auto"] is True and e.anchor["viewport"] is None
    pc = next(e for e in texts(ali) if e.content.endswith(" BC"))
    assert pc.anchor["ref"] == "PC-1" and pc.anchor["side"] == "left"
    assert pc.anchor["rotation"] == "perpendicular" and pc.anchor["label_offset"] == 22.5
    sta = next(e for e in texts(ali) if e.anchor["ref"] == "13+00.00")
    assert sta.content == "3" and sta.anchor["side"] == "right"  # below an eastbound line
    assert sta.anchor["station"] == pytest.approx(1300.0) and sta.anchor["label_offset"] == 6.0


def test_alignment_mode_equation_2000_2500_16_ticks_labels_19_25_30_not_20_and_EQ1_label():
    s = alignment_session(equations=[{"back": "20+00", "ahead": "25+00"}])
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1"})
    assert r["ok"] and "16 ticks" in r["message"] and "1 equation labels" in r["message"]
    assert "stations 10+00.00 to 30+18.88" in r["message"]
    contents = {t.content for t in texts(s)}
    refs = {t.anchor["ref"] for t in texts(s) if t.anchor["kind"] == "station"}
    assert {"9", "25", "30"} <= contents and {"19+00.00", "25+00.00", "30+00.00"} <= refs
    assert "20+00.00" not in refs and "24+00.00" not in refs
    eq = next(t for t in texts(s) if t.anchor["kind"] == "equation")
    assert eq.content == "STA 20+00.00 BK = STA 25+00.00 AH" and eq.anchor["ref"] == "EQ-1"
    assert eq.anchor["label_offset"] == 22.5
    assert "25+18.88 EC" in contents
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "include_equations": False})
    assert r["ok"] and "0 equation labels" in r["message"]


def test_station_range_12_00_18_00_7_ticks():
    s = alignment_session()
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "station_range": ["12+00", 1800]})
    assert r["ok"] and "7 ticks" in r["message"]
    assert len(lines(s)) == 7
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "station_range": ["12+00", "40+00"]})
    assert not r["ok"] and "40+00.00" in r["error"]["message"]


def test_both_path_ids_and_alignment_fault():
    s = alignment_session()
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "path_ids": ["LN-001"]})
    assert not r["ok"]
    assert r["error"]["message"] == ("give either path_ids (entity-chain mode) or alignment "
                                     "(design mode), not both")


def test_neither_fault():
    s = alignment_session()
    r = s.execute("annotate_stationing", {"space": "model"})
    assert not r["ok"] and r["error"]["message"] == "path_ids is required in entity-chain mode"
    assert r["error"]["hint"] == "or pass alignment=NAME for design-model stationing"
    r = s.execute("annotate_stationing", {"space": "model", "path_ids": ["LN-001"]})
    assert not r["ok"] and r["error"]["message"] == "begin_station is required with path_ids"


def test_begin_station_with_alignment_fault():
    s = alignment_session()
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "begin_station": 1000})
    assert not r["ok"]
    assert r["error"]["message"] == ("alignment mode uses ALIGN-1's own stationing (begins "
                                     "10+00.00); omit begin_station")
    assert r["error"]["hint"] == "modify_alignment changes begin_station"


def test_alignment_mode_on_sheet_faults():
    s = alignment_session()
    s.execute("create_sheet", {"name": "C-101"})
    r = s.execute("annotate_stationing", {"space": "C-101", "alignment": "ALIGN-1"})
    assert not r["ok"]
    assert r["error"]["message"] == ("alignment-mode stationing draws in model space; use "
                                     "place_label for sheet labels")
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "NOPE"})
    assert not r["ok"] and "no alignment named 'NOPE'" in r["error"]["message"]


def test_entity_mode_golden_unchanged_34_ids():
    s, ids = centerline_session()
    r = s.execute("annotate_stationing", {"space": "model", "path_ids": ids,
                                          "begin_station": 1000.0, "interval": 100.0})
    assert r["ok"] and len(r["created"]) == 34
    assert r["created"][0] == "LN-003" and r["created"][1] == "TX-001"
    assert r["created"][-1] == "TX-018"
    snapshot = s.doc.to_dict()
    for e in snapshot["model"]["entities"].values():
        assert "anchor" not in e
    assert snapshot["design"] == {"alignments": {}, "profiles": {}}
    assert s.execute("undo", {})["ok"] and len(s.doc.model_entities) == 3
