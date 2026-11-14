"""Labels follow the design they were lettered from (commands/label_updates.py).

modify_alignment used to leave every label anchored to the alignment where the
old design put it, with a warning, and said nothing at all when the labels were
lettered through a reference whose basefile changed (pilot work, 2026-10-19).
Now the labels move: the invariant is that labelling a design and then changing
it leaves the same lettering as changing it and then labelling it.
"""
from __future__ import annotations

import math
from collections import Counter

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Circle, Line, Table, Text

PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677, 500],
       [2433.012702, 2200]]
MOVED = [[1000, 1000], [1814.359354, 1000, 600], [2433.012702, 1357.179677, 700],
         [2433.012702, 2200]]
LONGER = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677, 500],
          [2433.012702, 2900]]


def _design(s: Session, name: str = "SR-100", pis=PIS, begin: str = "10+00") -> None:
    assert s.execute("create_alignment", {"name": name, "begin_station": begin,
                                          "pis": pis})["ok"]


def _sheet(s: Session, twist: float = 10.0) -> None:
    assert s.execute("create_sheet", {"name": "C-101", "size": "ANSI_D"})["ok"]
    assert s.execute("create_viewport", {
        "sheet": "C-101", "center_paper": [17, 11.5], "width_in": 30, "height_in": 19,
        "model_center": [1750, 1600], "feet_per_inch": 100, "rotation_deg": twist})["ok"]


def _letter(s: Session, name: str = "SR-100") -> None:
    """Every kind of lettering the engine anchors."""
    for layer in ("STA", "LBL"):
        s.execute("create_layer", {"name": layer})
    calls = [
        ("annotate_stationing", {"space": "model", "alignment": name, "layer": "STA"}),
        ("place_label", {"space": "model", "alignment": name, "anchor": "PC-1",
                         "layer": "LBL"}),
        ("place_label", {"space": "model", "alignment": name, "anchor": "T-2",
                         "kind": "bearing", "layer": "LBL"}),
        ("place_label", {"space": "model", "alignment": name, "anchor": "PI-2",
                         "kind": "curve_data", "layer": "LBL"}),
        ("place_label", {"space": "model", "alignment": name, "anchor": "MC-2",
                         "kind": "mc", "layer": "LBL"}),
        ("place_label", {"space": "model", "alignment": name, "anchor": "15+00",
                         "layer": "LBL"}),
        ("place_label", {"space": "C-101", "alignment": name, "anchor": "PT-1",
                         "layer": "LBL"}),
        ("place_label", {"space": "C-101", "alignment": name, "anchor": "20+00@40L",
                         "kind": "custom", "content": "FENCE", "layer": "LBL"}),
        ("place_curve_table", {"space": "C-101", "alignment": name, "position": [24, 8]}),
    ]
    for command, params in calls:
        r = s.execute(command, params)
        assert r["ok"], (command, r)


def _lettering(s: Session) -> Counter:
    """What is lettered from the design, without ids: a multiset of poses."""
    def r(v):
        return round(float(v), 4)

    out = Counter()
    for space, container in [("model", s.doc.model_entities)] + [
            (sh.name, sh.entities) for sh in s.doc.sheets.values()]:
        for e in container.values():
            a = e.anchor or {}
            if not a or a.get("kind") in ("element", "offset"):
                continue
            head = (space, type(e).__name__, a["kind"], a["ref"], a.get("placed_by"))
            if isinstance(e, Text):
                out[head + (r(e.position[0]), r(e.position[1]), r(e.rotation_deg % 360),
                            e.content, e.halign, e.valign, r(a.get("station") or 0))] += 1
            elif isinstance(e, Line):
                out[head + tuple(r(v) for v in e.start + e.end)] += 1
            elif isinstance(e, Circle):
                out[head + (r(e.center[0]), r(e.center[1]), r(e.radius))] += 1
            elif isinstance(e, Table):
                out[head + (tuple(tuple(row) for row in e.rows),)] += 1
    return out


def _fresh(pis, begin="10+00", twist=10.0) -> Session:
    s = Session(project_name="fresh")
    _design(s, pis=pis, begin=begin)
    _sheet(s, twist)
    _letter(s)
    return s


@pytest.mark.parametrize("changes,label", [
    ({"pis": MOVED}, "both radii changed"),
    ({"begin_station": "12+50"}, "begin station moved"),
    ({"pis": LONGER}, "the line runs on 700 ft"),
])
def test_lettering_then_changing_the_design_is_changing_it_then_lettering(changes, label):
    s = Session(project_name="follows")
    _design(s)
    _sheet(s)
    _letter(s)
    before = _lettering(s)
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": changes})
    assert r["ok"], r
    assert r["warnings"] == [], (label, r["warnings"])
    assert "labels:" in r["message"] and "stationing set laid out again" in r["message"]
    after = _lettering(s)
    assert after != before, label
    want = _fresh(changes.get("pis", PIS), changes.get("begin_station", "10+00"))
    assert after == _lettering(want), label
    # and a second look finds nothing left to do
    again = s.execute("update_labels", {"alignment": "SR-100"})
    assert again["ok"] and again["created"] == again["deleted"] == []
    assert again["modified"] == [] and "already in step" in again["message"]


@pytest.mark.parametrize("twist", [-120.0, 75.0, 160.0])
def test_sheet_lettering_followed_through_a_turned_view_runs_clear_of_its_line(twist):
    # place_label sets a sheet label from the end and the edge the paper wants
    # (training plan decision 13); laid out again after the design changes, it must
    # go by the paper too, not the model
    from roaddraft.design.anchors import parse_anchor, resolve_anchor
    s = Session(project_name="turned")
    _design(s)
    _sheet(s, twist)
    _letter(s)
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"pis": MOVED}})
    assert r["ok"] and r["warnings"] == [], r
    assert _lettering(s) == _lettering(_fresh(MOVED, twist=twist))
    align = s.doc.design.alignments["SR-100"]
    labels = [e for e in s.doc.sheets["SH-001"].entities.values()
              if isinstance(e, Text) and e.anchor and e.anchor.get("rotation") in
              ("perpendicular", "along")]
    assert len(labels) == 2
    for e in labels:
        paper = resolve_anchor(align, parse_anchor(e.anchor["ref"])).direction_deg + twist
        side = paper + (90.0 if e.anchor["side"] == "left" else -90.0)
        body = (e.rotation_deg + (0.0 if e.halign == "left" else 180.0)
                if e.anchor["rotation"] == "perpendicular"
                else e.rotation_deg + (90.0 if e.valign == "bottom" else -90.0))
        assert math.cos(math.radians(body - side)) > 0.5, (e.content, e.halign, e.valign)


def test_stationing_regenerated_keeps_its_provenance_and_undo_takes_it_back():
    s = Session(project_name="prov")
    _design(s)
    _sheet(s)
    _letter(s)
    snapshot = s.doc.to_dict()
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"pis": LONGER}})
    assert r["created"] and r["deleted"]
    for eid in r["created"]:
        entity = s.doc.model_entities[eid]
        assert entity.anchor["placed_by"] == "annotate_stationing", eid
    assert s.execute("undo", {})["ok"]
    assert s.doc.to_dict() == snapshot


def test_a_redrawn_centerline_is_draw_alignments_work():
    s = Session(project_name="redraw")
    _design(s)
    s.execute("create_layer", {"name": "CL"})
    s.execute("draw_alignment", {"alignment": "SR-100", "layer": "CL"})
    r = s.execute("modify_alignment", {"name": "SR-100", "redraw": True,
                                       "changes": {"pis": MOVED}})
    assert r["ok"] and r["warnings"] == []
    drawn = [e for e in s.doc.model_entities.values() if e.anchor["kind"] == "element"]
    assert drawn and {e.anchor["placed_by"] for e in drawn} == {"draw_alignment"}


def test_offsets_are_linework_and_a_warning_names_them():
    s = Session(project_name="edges")
    _design(s)
    s.execute("create_layer", {"name": "EP"})
    s.execute("draw_offset", {"alignment": "SR-100", "offsets": [-12, 12], "layer": "EP"})
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"pis": MOVED}})
    assert r["ok"] and len(r["warnings"]) == 1
    assert "still follow the old design" in r["warnings"][0]
    assert "draw_offset replace=true" in r["warnings"][0]


def test_a_label_whose_anchor_is_gone_is_named_and_left():
    s = Session(project_name="gone")
    _design(s)
    s.execute("create_layer", {"name": "LBL"})
    r = s.execute("place_label", {"space": "model", "alignment": "SR-100", "anchor": "PC-2",
                                  "layer": "LBL"})
    gone = r["created"][0]
    where = list(s.doc.model_entities[gone].position)
    one_curve = [PIS[0], PIS[1], PIS[2][:2]]
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"pis": one_curve}})
    assert r["ok"] and gone in r["warnings"][0] and "could not follow" in r["warnings"][0]
    assert s.doc.model_entities[gone].position == where


def test_update_labels_faults_teach():
    s = Session(project_name="none")
    _design(s)
    r = s.execute("update_labels", {})
    assert not r["ok"] and "nothing in this document is anchored" in r["error"]["message"]
    r = s.execute("update_labels", {"alignment": "SR-100"})
    assert not r["ok"] and "anchored to SR-100" in r["error"]["message"]
    r = s.execute("update_labels", {"alignment": "NOPE"})
    assert not r["ok"] and "no alignment named 'NOPE'" in r["error"]["message"]


# ------------------------------------------------------- through a reference


def _base(tmp_path, pis=PIS) -> None:
    model = Session(project_name="design", out_dir=tmp_path)
    _design(model, pis=pis)
    model.query("save_document", {"path": str(tmp_path / "design.rdraft")})


def _host(tmp_path) -> Session:
    host = Session(project_name="plans", out_dir=tmp_path)
    host.query("save_document", {"path": str(tmp_path / "plans.rdraft")})
    assert host.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                             "path": "design.rdraft"})["ok"]
    _sheet(host)
    _letter(host, "DESIGN:SR-100")
    return host


def test_labels_lettered_through_a_reference_follow_its_basefile(tmp_path):
    """The redline flow: the design is changed in its base file (as an agent does
    through open_document), the sheet file reloads it, is told its lettering is
    stale, and update_labels brings it up to date."""
    _base(tmp_path)
    host = _host(tmp_path)
    before = _lettering(host)
    base = Session.load(tmp_path / "design.rdraft", out_dir=tmp_path)
    r = base.execute("modify_alignment", {"name": "SR-100", "changes": {"pis": MOVED}})
    assert r["ok"] and r["warnings"] == []      # the base holds no labels of its own
    base.query("save_document", {"path": str(tmp_path / "design.rdraft")})

    r = host.execute("reload_references", {})
    assert r["ok"] and len(r["warnings"]) == 1
    assert "DESIGN:SR-100" in r["warnings"][0] and "update_labels" in r["warnings"][0]
    assert _lettering(host) == before           # told, not changed

    r = host.execute("update_labels", {"alignment": "DESIGN:SR-100"})
    assert r["ok"] and r["warnings"] == [], r
    # the same as lettering the changed design through the reference afresh
    other = tmp_path / "fresh"
    other.mkdir()
    _base(other, MOVED)
    assert _lettering(host) == _lettering(_host(other))
    assert host.execute("reload_references", {})["warnings"] == []
    # with no alignment named, every lettered one is brought up to date
    assert "already in step" in host.execute("update_labels", {})["message"]


def test_a_set_lettered_through_a_twist_before_the_record_carried_it_keeps_reading_upright():
    """The redraft base files (2026-10-10) were lettered through their sheets'
    twists before the anchor recorded ``view_rotation``.  Laid out again through
    no twist, a line running past 90 degrees in the model had its numbers turned
    round, upside down through the viewport (L-1's "TB1" at 93.96 degrees under
    -89.94): Astra marked nine of them on the clean QA-review control, 2026-10-23.
    The twist is read off the pose instead."""
    s = Session(project_name="old-twist")
    # a line running N 04 W: direction 94 degrees, past the model's upright limit
    pis = [[1000, 1000], [930.0, 2000]]
    _design(s, pis=pis)
    s.execute("create_layer", {"name": "STA"})
    r = s.execute("annotate_stationing", {"space": "model", "alignment": "SR-100",
                                          "layer": "STA", "view_rotation": -89.94})
    assert r["ok"], r
    numbers = [e for e in s.doc.model_entities.values()
               if isinstance(e, Text) and e.anchor and e.anchor.get("kind") == "station"]
    assert numbers and all(abs(n.rotation_deg - 94.0) < 0.1 for n in numbers)
    for n in numbers:                      # an old file: the twist was never recorded
        n.anchor.pop("view_rotation", None)
    r = s.execute("modify_alignment", {"name": "SR-100", "changes": {"begin_station": "12+50"}})
    assert r["ok"] and "stationing set laid out again" in r["message"], r
    again = [e for e in s.doc.model_entities.values()
             if isinstance(e, Text) and e.anchor and e.anchor.get("kind") == "station"]
    assert again and all(abs(n.rotation_deg - 94.0) < 0.1 for n in again), \
        sorted({round(n.rotation_deg, 2) for n in again})
    # and without the twist the same change would have turned them round
    s2 = Session(project_name="no-twist")
    _design(s2, pis=pis)
    s2.execute("create_layer", {"name": "STA"})
    assert s2.execute("annotate_stationing", {"space": "model", "alignment": "SR-100",
                                              "layer": "STA"})["ok"]
    flat = [e for e in s2.doc.model_entities.values()
            if isinstance(e, Text) and e.anchor and e.anchor.get("kind") == "station"]
    assert flat and all(abs(n.rotation_deg + 86.0) < 0.1 for n in flat)


def test_an_untwisted_set_laid_out_again_stays_untwisted():
    """A set lettered through no twist records none.  Until 2026-11-12 its twist
    was guessed off a station number's pose all the same, and the guess (the
    twist that keeps that number level) laid a curve point's label out upside
    down after a restation: seed 15015's "194+97.76 BC" came back at 136.9
    degrees.  No twist now stands when no twist poses every label as it is."""
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify.legibility import reads_upside_down
    task = generate_task(15015, curves=3, task_type="annotate-sheet")
    s = session_for_task(task)
    reference_solution(task, s)

    def poses():
        return sorted((e.anchor["kind"], e.anchor["ref"], round(e.rotation_deg, 6))
                      for e in s.doc.model_entities.values()
                      if isinstance(e, Text) and e.anchor and e.anchor.get("kind") != "mc")

    lettered = poses()
    begin = task.brief.design["alignments"]["ALIGN-1"]["begin_station"]
    r = s.execute("modify_alignment", {"name": "ALIGN-1",
                                       "changes": {"begin_station": begin + 25.0}})
    assert r["ok"] and "stationing set laid out again" in r["message"], r
    assert not [e.content for e in s.doc.model_entities.values()
                if isinstance(e, Text) and reads_upside_down(e.rotation_deg)]
    # laid out again, the set is the one stationing lettered fresh on the restationed line
    from roaddraft.tasks.reference import phase_commands
    fresh = session_for_task(task)
    assert fresh.execute("modify_alignment", {"name": "ALIGN-1",
                                              "changes": {"begin_station": begin + 25.0}})["ok"]
    for name, params in phase_commands(task, ["stationing"]):
        assert fresh.execute(name, params)["ok"]
    stationing = ("tick", "station", "pc", "pt")
    assert [p for p in poses() if p[0] in stationing] == sorted(
        (e.anchor["kind"], e.anchor["ref"], round(e.rotation_deg, 6))
        for e in fresh.doc.model_entities.values()
        if isinstance(e, Text) and e.anchor and e.anchor.get("kind") in stationing)
    assert len(lettered) > 10
