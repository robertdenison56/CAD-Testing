"""Anchor provenance: the bus stamps ``anchor.placed_by``, nothing else writes it.

Text earns credit in an eval only through an anchor, so an anchor a caller
attached by hand must be distinguishable from one a design command placed.
The bus stamps the creating command's name; modify_entity can neither claim
provenance nor transfer it; editing an anchored label leaves its stamp alone.
"""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.document.entities import Text, as_anchor
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import reference_solution, session_for_task

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]


def design_session() -> Session:
    s = Session(project_name="provenance-tests")
    assert s.execute("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                                          "pis": A_PIS})["ok"]
    s.execute("create_layer", {"name": "V-ANNO-TEXT", "color": "black"})
    return s


def anchor_of(s: Session, r: dict, n: int = 0) -> dict:
    _space, e = s.doc.find_entity(r["created"][n])
    return e.anchor


def test_every_producer_stamps_its_own_name():
    s = design_session()
    stamps = {}
    r = s.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ANNO-TEXT"})
    stamps["draw_alignment"] = anchor_of(s, r)["placed_by"]
    r = s.execute("draw_offset", {"alignment": "ALIGN-1", "offsets": [-12, 12]})
    stamps["draw_offset"] = anchor_of(s, r)["placed_by"]
    r = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    stamps["place_label"] = anchor_of(s, r)["placed_by"]
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                          "interval": 200.0})
    assert r["ok"], r
    stamped = {anchor_of(s, r, i)["placed_by"] for i in range(len(r["created"]))}
    assert stamped == {"annotate_stationing"}
    stamps["annotate_stationing"] = stamped.pop()
    s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    r = s.execute("place_curve_table", {"space": "C-101", "alignment": "ALIGN-1",
                                        "position": [24.0, 8.5]})
    stamps["place_curve_table"] = anchor_of(s, r)["placed_by"]
    r = s.execute("draw_station_offset", {"alignment": "ALIGN-1",
                                          "points": ["11+00@24R", "12+00@24R"]})
    stamps["draw_station_offset"] = anchor_of(s, r)["placed_by"]
    assert stamps == {name: name for name in ANCHOR_PRODUCERS}


def test_hand_anchored_text_carries_no_provenance():
    """place_text + modify_entity is the spoof the stamp exists to catch."""
    s = design_session()
    r = s.execute("place_text", {"space": "model", "position": [1600.0, 984.0],
                                 "content": "PC 16+00.00", "height": 8.0})
    tid = r["created"][0]
    assert s.doc.model_entities[tid].anchor is None
    r = s.execute("modify_entity", {"id": tid, "changes": {"anchor": {
        "alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc", "station": 1600.0,
        "offset": 0.0, "side": "right", "label_offset": 16.0, "rotation": "along",
        "viewport": None, "content_auto": True}}})
    assert r["ok"], r
    a = s.doc.model_entities[tid].anchor
    assert a["ref"] == "PC-1" and "placed_by" not in a


def test_modify_entity_cannot_claim_provenance():
    s = design_session()
    r = s.execute("place_text", {"space": "model", "position": [1600.0, 984.0],
                                 "content": "PC 16+00.00", "height": 8.0})
    tid = r["created"][0]
    r = s.execute("modify_entity", {"id": tid, "changes": {"anchor": {
        "alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc",
        "placed_by": "place_label"}}})
    assert r["ok"], r  # accepted as an anchor, rejected as a claim
    assert "placed_by" not in s.doc.model_entities[tid].anchor


def test_modify_entity_cannot_transfer_provenance():
    """A stamped label's own anchor, copied onto plain text, loses the stamp."""
    s = design_session()
    placed = s.execute("place_label", {"space": "model", "anchor": "PC-1"})
    stolen = dict(s.doc.model_entities[placed["created"][0]].anchor)
    assert stolen["placed_by"] == "place_label"
    r = s.execute("place_text", {"space": "model", "position": [1700.0, 984.0],
                                 "content": "PC 16+00.00", "height": 8.0})
    tid = r["created"][0]
    assert s.execute("modify_entity", {"id": tid, "changes": {"anchor": stolen}})["ok"]
    assert "placed_by" not in s.doc.model_entities[tid].anchor


def test_editing_a_placed_label_keeps_its_stamp():
    """Layer fixes, nudges, renames and moves are drafting, not forgery."""
    s = design_session()
    tid = s.execute("place_label", {"space": "model", "anchor": "PC-1"})["created"][0]
    assert s.execute("modify_entity", {"id": tid,
                                       "changes": {"layer": "V-ANNO-TEXT"}})["ok"]
    assert s.doc.model_entities[tid].anchor["placed_by"] == "place_label"
    a = dict(s.doc.model_entities[tid].anchor, side="left")
    assert s.execute("modify_entity", {"id": tid, "changes": {"anchor": a}})["ok"]
    assert s.doc.model_entities[tid].anchor["placed_by"] == "place_label"
    assert s.execute("move_entities", {"ids": [tid], "delta": [5, 5]})["ok"]
    assert s.doc.model_entities[tid].anchor["placed_by"] == "place_label"
    r = s.execute("modify_alignment", {"name": "ALIGN-1", "changes": {"rename": "SR-100"}})
    assert r["ok"], r
    a = s.doc.model_entities[tid].anchor
    assert a["alignment"] == "SR-100" and a["placed_by"] == "place_label"


def test_undo_redo_and_replay_reproduce_the_stamp(tmp_path):
    s = design_session()
    tid = s.execute("place_label", {"space": "model", "anchor": "PC-1"})["created"][0]
    assert s.execute("undo")["ok"] and tid not in s.doc.model_entities
    assert s.execute("redo")["ok"]
    assert s.doc.model_entities[tid].anchor["placed_by"] == "place_label"
    path = tmp_path / "p.journal.jsonl"
    assert s.query("save_journal", {"path": str(path)})["ok"]
    assert Session.replay_journal(path).doc.to_dict() == s.doc.to_dict()


def test_as_anchor_validates_placed_by():
    base = {"alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc"}
    assert as_anchor({**base, "placed_by": "place_label"})["placed_by"] == "place_label"
    assert as_anchor({**base, "placed_by": None})["placed_by"] is None
    assert "placed_by" not in as_anchor(base)
    for bad in ("", 7, True, ["place_label"]):
        with pytest.raises(ValueError, match="placed_by"):
            as_anchor({**base, "placed_by": bad})


@pytest.mark.parametrize("seed", [1, 42, 100])
def test_every_anchor_a_reference_solution_places_is_stamped(seed):
    """The E0 contract the verifier reads: on a clean sheet, every anchored
    entity was placed by a design command."""
    task = generate_task(seed)
    s = session_for_task(task)
    reference_solution(task, s)
    anchored = [e for e in s.doc.model_entities.values() if e.anchor]
    for sheet in s.doc.sheets.values():
        anchored += [e for e in sheet.entities.values() if e.anchor]
    assert anchored
    assert {e.anchor.get("placed_by") for e in anchored} <= set(ANCHOR_PRODUCERS)
    labels = [e for e in anchored if isinstance(e, Text)]
    assert len(labels) == len(task.truth.labels)


def test_a_piece_cut_from_design_linework_keeps_its_producer():
    s = design_session()
    r = s.execute("draw_offset", {"alignment": "ALIGN-1", "offsets": [-12]})
    edge = r["created"][0]  # the first tangent's edge
    s.execute("draw_line", {"space": "model", "start": [1300, 900], "end": [1300, 1100]})
    s.execute("draw_line", {"space": "model", "start": [1340, 900], "end": [1340, 1100]})
    r = s.execute("trim", {"targets": [{"id": edge, "at": [1320, 1012]}]})
    assert r["ok"], r
    piece = s.doc.model_entities[r["created"][0]]
    assert piece.anchor["placed_by"] == "draw_offset" and piece.anchor["kind"] == "offset"
    # a hand-made anchor cut in two gains nothing a verifier trusts
    t = s.execute("draw_line", {"space": "model", "start": [1200, 950], "end": [1400, 950]})
    tid = t["created"][0]
    s.execute("modify_entity", {"id": tid, "changes": {"anchor": {
        "alignment": "ALIGN-1", "ref": "T-1", "kind": "offset", "offset": 50.0}}})
    r = s.execute("break_entity", {"id": tid, "at": [1250, 950]})
    assert s.doc.model_entities[r["created"][0]].anchor["placed_by"] == "break_entity"
