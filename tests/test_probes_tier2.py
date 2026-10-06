"""The tier-2 probes, and whether their checks can tell right from wrong.

As for the drafting-probes: each probe is built around specific ways of
getting it wrong -- stopping after one sheet, text dropped on the shoulder
line, an arc centred on the corner instead of inside it, a mistake fixed by
adding instead of replacing -- and the tests prove each of those fails with a
message that says what is wrong, while correct work done another way (a curb
trimmed by moving its endpoint, a shoulder relayered by redrawing it, a
callout re-aimed instead of replaced) still passes.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, Line, Text
from roaddraft.probes import drafting, fixture, tasks, tier2
from roaddraft.probes.drafting import EOP, SHLD
from roaddraft.probes.tier2 import ROADWAY, TIER2_PROBES


def begin(probe_id: str, tmp_path):
    """``(probe, untouched baseline, a session to work in)``."""
    probe = tasks.get(probe_id)
    doc = fixture.start_document(tmp_path, probe.start)
    return probe, Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)


def do(s: Session, command: str, /, **params):
    r = s.execute(command, params)
    assert r["ok"], r
    return r


def rows(s: Session, **find):
    r = s.query("find_entities", {**find, "limit": 50})
    assert r["ok"], r
    return r["entities"]


# ------------------------------------------------------------- the probe set


def test_the_six_are_wired_in_and_start_from_real_documents(tmp_path):
    assert len(TIER2_PROBES) == 6
    assert tasks.PROBES[:len(tasks.FIND_PROBES) + len(drafting.DRAFT_PROBES) + 6] == \
        tasks.FIND_PROBES + drafting.DRAFT_PROBES + TIER2_PROBES
    assert len({p.id for p in tasks.PROBES}) == len(tasks.PROBES)
    for probe in TIER2_PROBES:
        assert "tier2" in probe.tags and probe.start in fixture.START
        assert probe.solve and probe.note and len(probe.prompt) > 80
        assert probe.id.startswith("draft-") == ("draft" in probe.tags)
    corner = Session.load(fixture.start_document(tmp_path / "i", "intersection"))
    assert sorted(corner.doc.design.alignments) == ["CROSS-AVE", "MAIN-ST"]
    arcs = [e for e in corner.doc.model_entities.values() if isinstance(e, Arc)]
    assert len(arcs) == 3 and all(a.radius == 50.0 for a in arcs)
    flawed = Session.load(fixture.start_document(tmp_path / "f", "flawed"))
    planted = tier2.planted(flawed)
    assert planted["edge"].layer == EOP and planted["edge"].anchor is None
    assert planted["shoulder"].layer == EOP and planted["shoulder"].anchor["offset"] == -20.0
    assert planted["callout"].tip is not None and len(planted["callout"].ids) == 3


@pytest.mark.parametrize("probe", TIER2_PROBES, ids=lambda p: p.id)
def test_the_scripted_solution_passes_and_the_untouched_document_does_not(probe, tmp_path):
    _probe, base, s = begin(probe.id, tmp_path)
    untouched = probe.check(base, base)
    assert not untouched.passed, f"{probe.id} passes with nothing done: {untouched.detail}"
    probe.solve(s)
    result = probe.check(base, s)
    assert result.passed, f"{probe.id}: {result.detail}"


# ------------------------------------------------------- pairing callouts


def test_callouts_pair_text_with_its_leader_however_it_was_drawn(tmp_path):
    s = Session.load(fixture.start_document(tmp_path, "blank"), out_dir=tmp_path)
    do(s, "place_callout", space="model", target=[100.0, 200.0], position=[400.0, 50.0],
       content="A", layer="V-ANNO-TEXT")
    do(s, "draw_line", space="model", layer="V-ANNO-TEXT", start=[900.0, 900.0], end=[1000.0, 1000.0])
    do(s, "place_text", space="model", position=[1000.0, 1000.0], content="B", height=8.0,
       layer="V-ANNO-TEXT")
    do(s, "place_text", space="model", position=[3000.0, 3000.0], content="C", height=8.0,
       layer="V-ANNO-TEXT")
    found = {c.text.content: c for c in tier2.callouts(list(s.doc.model_entities.values()), s.doc)}
    assert math.dist(found["A"].tip, [100.0, 200.0]) < 1e-6
    assert len(found["A"].segments) == 2 and len(found["A"].ids) == 3   # leader, shoulder, text
    assert math.dist(found["B"].tip, [900.0, 900.0]) < 1e-6
    assert found["C"].tip is None and found["C"].segments == []


# ---------------------------------------------------------- sheet-set


def _annotate(s: Session, sheet: str, dy_scale=1.0):
    for what, find in ROADWAY:
        north = "left" in what or what == "the centerline"
        tier2._callout_on(s, sheet, what, find, 1.0, (3.0 if what == "the centerline" else 2.0 * (1 if north else -1)) * dy_scale)


def _titles(s: Session, sheets=fixture.SHEETS, **extra):
    for i, name in enumerate(sheets):
        do(s, "fill_title_block", sheet=name, fields={**tasks.TITLE_FIELDS, "sheet_number": str(i + 1),
                                                       "total_sheets": "3", **extra})


def test_sheet_set_wants_every_sheet_and_the_centerline_by_name(tmp_path):
    probe, base, s = begin("sheet-set-callouts", tmp_path)
    _annotate(s, "C-101")
    _titles(s)
    r = probe.check(base, s)
    assert not r.passed and r.detail.startswith("C-102,")
    _annotate(s, "C-102")
    _annotate(s, "C-103")
    assert probe.check(base, s).passed
    # the centerline callout has to say SR-100, not CENTERLINE
    _probe, base, s = begin("sheet-set-callouts", tmp_path / "b")
    for name in fixture.SHEETS:
        for what, find in ROADWAY:
            tier2._callout_on(s, name, what, find, 1.0, 2.0,
                              content="CENTERLINE" if what == "the centerline" else None)
    _titles(s)
    r = probe.check(base, s)
    assert not r.passed and "reads SR-100" in r.detail


def test_sheet_set_work_in_the_model_and_unnumbered_title_blocks_fail(tmp_path):
    probe, base, s = begin("sheet-set-callouts", tmp_path)
    for what, find in ROADWAY:
        for name in fixture.SHEETS:
            eid = rows(base, visible_on=name, **find)[0]["id"]
            tasks.callout_at(s, eid, content=tier2.WORDING[what])
    _titles(s)
    r = probe.check(base, s)
    assert not r.passed and "paper space" in r.detail
    probe, base, s = begin("sheet-set-callouts", tmp_path / "b")
    probe.solve(s)
    do(s, "fill_title_block", sheet="C-102", fields={**tasks.TITLE_FIELDS, "sheet_number": "",
                                                      "total_sheets": "3"})
    r = probe.check(base, s)
    assert not r.passed and "C-102: title block: sheet_number" in r.detail
    do(s, "fill_title_block", sheet="C-102", fields={"sheet_number": "2 of 3", "total_sheets": ""})
    assert probe.check(base, s).passed


# ----------------------------------------------------------- stations


def _station_callout(s: Session, st: int, q, content=None, space="C-101", **extra):
    do(s, "place_callout", space=space, target_anchor=tier2.station_label(st),
       alignment=f"DESIGN:{fixture.ALIGNMENT}", position=[q[0] + 0.4, q[1] + 1.6],
       content=content or f"STA {tier2.station_label(st)}", layer=tier2._paper_layer(s), **extra)


def test_station_callouts_count_misses_misreadings_and_model_space(tmp_path):
    probe, base, s = begin("station-callouts", tmp_path)
    required, optional = tier2.sheet_stations(base)
    assert [st for st, _p, _q in required] == list(range(1100, 2501, 100))
    assert [st for st, _p, _q in optional] == [1000]
    for st, _p, q in required[:-2]:
        _station_callout(s, st, q)
    r = probe.check(base, s)
    assert not r.passed and "2 of 15" in r.detail and "24+00, 25+00" in r.detail
    for st, _p, q in required[-2:]:
        _station_callout(s, st, q, content=f"STA {st}")
    r = probe.check(base, s)
    assert not r.passed and "does not read the station" in r.detail and "24+00" in r.detail
    # the optional edge station is neither required nor penalised
    probe, base, s = begin("station-callouts", tmp_path / "b")
    for st, _p, q in required:
        _station_callout(s, st, q)
    assert probe.check(base, s).passed
    # the same calls in model space are not plan annotation
    probe, base, s = begin("station-callouts", tmp_path / "c")
    a = tier2._sr100_design()
    for st, p, _q in required:
        do(s, "place_callout", space="model", target=p, position=[p[0] + 30.0, p[1] + 60.0],
           content=f"STA {tier2.station_label(st)}", layer="V-ANNO-TEXT")
    r = probe.check(base, s)
    assert not r.passed and "paper space" in r.detail


def test_a_station_leader_that_misses_by_a_few_feet_does_not_count(tmp_path):
    probe, base, s = begin("station-callouts", tmp_path)
    required, _optional = tier2.sheet_stations(base)
    for st, p, q in required:
        off = [p[0], p[1] + (3.0 if st == 1500 else 0.0)]
        do(s, "place_callout", space="C-101", target=s.query("model_to_sheet", {
            "sheet": "C-101", "point": off})["sheet_point"], position=[q[0] + 0.4, q[1] + 1.6],
           content=f"STA {tier2.station_label(st)}", layer=tier2._paper_layer(s))
    r = probe.check(base, s)
    assert not r.passed and "1 of 15" in r.detail and "15+00" in r.detail


# -------------------------------------------------------------- clean


def test_clean_callouts_fail_on_text_over_linework_crossing_leaders_and_the_margin(tmp_path):
    left, shoulder, centre = tier2.CLEAN_TARGETS
    probe, base, s = begin("clean-callouts", tmp_path)
    tier2._callout_on(s, "C-102", *left, dx=0.3, dy=0.1)          # text dropped beside the tip
    tier2._callout_on(s, "C-102", *shoulder, dx=1.0, dy=-2.2)
    tier2._callout_on(s, "C-102", *centre, dx=1.0, dy=3.0)
    r = probe.check(base, s)
    assert not r.passed and "sits over linework" in r.detail and "EDGE OF PAVEMENT" in r.detail

    probe, base, s = begin("clean-callouts", tmp_path / "b")
    tier2.AT["the right edge of shoulder"], keep = 0.2, tier2.AT["the right edge of shoulder"]
    try:
        tier2._callout_on(s, "C-102", *left, dx=1.0, dy=-2.5)      # text south of a north line
        tier2._callout_on(s, "C-102", *shoulder, dx=1.0, dy=2.5)   # text north of a south line
    finally:
        tier2.AT["the right edge of shoulder"] = keep
    tier2._callout_on(s, "C-102", *centre, dx=1.0, dy=3.0)
    r = probe.check(base, s)
    assert not r.passed and "cross" in r.detail

    probe, base, s = begin("clean-callouts", tmp_path / "c")
    tier2._callout_on(s, "C-102", *left, dx=-1.0, dy=2.2)
    tier2._callout_on(s, "C-102", *shoulder, dx=1.0, dy=2.6)     # north too, out of the way
    row = rows(base, visible_on="C-102", **centre[1])[0]
    do(s, "place_callout", space="C-102", target_entity=row["id"], at=0.55,
       position=[row["sheet_point"][0] + 1.0, 1.0], content="SR-100",
       layer=tier2._paper_layer(s))                                   # down in the title strip
    r = probe.check(base, s)
    assert not r.passed and "outside the drawing area" in r.detail


def test_clean_callouts_in_the_model_fail_on_aim_before_anything_else(tmp_path):
    probe, base, s = begin("clean-callouts", tmp_path)
    for what, find in tier2.CLEAN_TARGETS:
        tasks.callout_at(s, rows(base, visible_on="C-102", **find)[0]["id"], content=tier2.WORDING[what])
    r = probe.check(base, s)
    assert not r.passed and "paper space" in r.detail


# ------------------------------------------------------------- corner


def _trim_by_moving_ends(s: Session):
    g = tier2._corner()
    for road, eid in tier2._ne_pieces(s).items():
        e = s.doc.model_entities[eid]
        corner = [g["cross_tp"][0], g["main_tp"][1]]
        end = "start" if math.dist(e.start, corner) < math.dist(e.end, corner) else "end"
        do(s, "modify_entity", id=eid, changes={end: g["main_tp"] if road == "main" else g["cross_tp"]})


def test_a_return_at_the_wrong_corner_or_centred_on_the_corner_fails(tmp_path):
    probe, base, s = begin("draft-intersection-corner", tmp_path)
    se = fixture.corner_geometry("SE")
    do(s, "draw_arc", space="model", layer=EOP, center=se["center"], radius=50.0,
       start_angle_deg=se["start_deg"], end_angle_deg=se["end_deg"])
    _trim_by_moving_ends(s)
    r = probe.check(base, s)
    assert not r.passed and "curb return" in r.detail
    probe, base, s = begin("draft-intersection-corner", tmp_path / "b")
    g = tier2._corner()
    do(s, "draw_arc", space="model", layer=EOP, center=[g["cross_tp"][0], g["main_tp"][1]],
       radius=50.0, start_angle_deg=0.0, end_angle_deg=90.0)
    _trim_by_moving_ends(s)
    r = probe.check(base, s)
    assert not r.passed and "curb return" in r.detail


def test_a_return_with_the_curbs_left_running_to_the_corner_fails(tmp_path):
    probe, base, s = begin("draft-intersection-corner", tmp_path)
    g = tier2._corner()
    do(s, "draw_arc", space="model", layer=EOP, center=g["center"], radius=g["radius"],
       start_angle_deg=g["start_deg"], end_angle_deg=g["end_deg"])
    r = probe.check(base, s)
    assert not r.passed and "between the return and the corner" in r.detail
    # a 44 ft return is not the one asked for
    probe, base, s = begin("draft-intersection-corner", tmp_path / "b")
    do(s, "draw_arc", space="model", layer=EOP, center=[5076.0, 5088.0], radius=44.0,
       start_angle_deg=180.0, end_angle_deg=270.0)
    _trim_by_moving_ends(s)
    assert not probe.check(base, s).passed


def test_a_return_with_the_curbs_trimmed_by_moving_their_ends_passes(tmp_path):
    probe, base, s = begin("draft-intersection-corner", tmp_path)
    g = tier2._corner()
    do(s, "draw_arc", space="model", layer=EOP, center=g["center"], radius=g["radius"],
       start_angle_deg=g["start_deg"], end_angle_deg=g["end_deg"])
    _trim_by_moving_ends(s)
    r = probe.check(base, s)
    assert r.passed, r.detail


# ---------------------------------------------------------- fix-the-drawing


def _fix_edge(s: Session, P, remove=True):
    a = s.doc.design.alignments[fixture.ALIGNMENT]
    e = P["edge"]
    st0, st1 = sorted(a.xy_to_station(p)["station"] for p in (e.start, e.end))
    if remove:
        do(s, "delete_entities", ids=[e.id])
    do(s, "draw_offset", alignment=fixture.ALIGNMENT, offsets=[12.0], layer=EOP,
       station_range=[round(st0, 2), round(st1, 2)])


def test_fixing_one_mistake_names_the_next_and_adding_is_not_fixing(tmp_path):
    probe, base, s = begin("draft-fix-the-drawing", tmp_path)
    P = tier2.planted(base)
    _fix_edge(s, P)
    r = probe.check(base, s)
    assert not r.passed and "shoulder on V-ROAD-SHLD" in r.detail
    do(s, "modify_entity", id=P["shoulder"].id, changes={"layer": SHLD})
    r = probe.check(base, s)
    assert not r.passed and "still points at the shoulder" in r.detail
    # adding a 12 ft piece beside the 11 ft one leaves the mistake in the drawing
    probe, base, s = begin("draft-fix-the-drawing", tmp_path / "b")
    _fix_edge(s, P, remove=False)
    r = probe.check(base, s)
    assert not r.passed and "hand-drawn piece at 11 ft" in r.detail


def test_the_callout_may_be_re_aimed_and_the_shoulder_redrawn_but_not_left_half_done(tmp_path):
    probe, base, s = begin("draft-fix-the-drawing", tmp_path)
    P = tier2.planted(base)
    a = s.doc.design.alignments[fixture.ALIGNMENT]
    _fix_edge(s, P)
    # the shoulder relayered by redrawing it
    sh = P["shoulder"]
    st0, st1 = sorted(a.xy_to_station(p)["station"] for p in (sh.start, sh.end))
    do(s, "delete_entities", ids=[sh.id])
    do(s, "draw_offset", alignment=fixture.ALIGNMENT, offsets=[-20.0], layer=SHLD,
       station_range=[round(st0, 2), round(st1, 2)])
    # the callout re-aimed at the edge by moving the leader's tip
    c = P["callout"]
    leader = next(eid for eid in c.ids if isinstance(s.doc.model_entities.get(eid), Line)
                  and any(math.dist(end, c.tip) < 1e-6
                          for end in (s.doc.model_entities[eid].start, s.doc.model_entities[eid].end)))
    e = s.doc.model_entities[leader]
    end = "start" if math.dist(e.start, c.tip) < 1e-6 else "end"
    do(s, "modify_entity", id=leader, changes={end: a.station_to_xy(1800.0, 12.0)[0]})
    r = probe.check(base, s)
    assert r.passed, r.detail
    # deleting the text and leaving the leader is not a fix
    probe, base, s = begin("draft-fix-the-drawing", tmp_path / "b")
    _fix_edge(s, P)
    do(s, "modify_entity", id=P["shoulder"].id, changes={"layer": SHLD})
    do(s, "delete_entities", ids=[P["callout"].text.id])
    r = probe.check(base, s)
    assert not r.passed and "left behind" in r.detail


def test_touching_anything_else_or_drawing_the_edge_twice_fails(tmp_path):
    probe, base, s = begin("draft-fix-the-drawing", tmp_path)
    probe.solve(s)
    arc = next(e for e in base.doc.model_entities.values()
               if isinstance(e, Arc) and e.layer == EOP and e.anchor["offset"] == -12.0)
    do(s, "delete_entities", ids=[arc.id])
    r = probe.check(base, s)
    assert not r.passed and arc.id in r.detail and "did not ask" in r.detail
    probe, base, s = begin("draft-fix-the-drawing", tmp_path / "b")
    probe.solve(s)
    do(s, "draw_offset", alignment=fixture.ALIGNMENT, offsets=[12.0], layer=EOP)
    r = probe.check(base, s)
    assert not r.passed and "drawn twice" in r.detail


# ------------------------------------------------------------ roadway-sheets


def _sheet(s: Session, fpi=100.0, center=None, center_paper=(17.0, 11.7), title=True):
    a = s.doc.design.alignments[drafting.ELM["name"]]
    x0, y0, x1, y1 = a.bbox()
    do(s, "create_sheet", name="C-101", size="ANSI_D")
    do(s, "create_viewport", sheet="C-101", center_paper=list(center_paper), width_in=31.0,
       height_in=18.5, model_center=center or [(x0 + x1) / 2.0, (y0 + y1) / 2.0], feet_per_inch=fpi)
    if title:
        do(s, "fill_title_block", sheet="C-101", fields={"project": "ELM AVE", "sheet_title": "PLAN",
                                                          "scale": tier2.RS["scale"]})


def test_the_sheet_must_be_at_scale_show_it_all_sit_on_the_paper_and_be_titled(tmp_path):
    probe, base, s = begin("draft-roadway-sheets", tmp_path)
    drafting._solve_roadway(s)
    r = probe.check(base, s)
    assert not r.passed and "no sheet named C-101" in r.detail
    _sheet(s, fpi=50.0)
    r = probe.check(base, s)
    assert not r.passed and "not 1\"=100'" in r.detail

    probe, base, s = begin("draft-roadway-sheets", tmp_path / "b")
    drafting._solve_roadway(s)
    _sheet(s, center=list(drafting.ELM["start"]))
    r = probe.check(base, s)
    assert not r.passed and "misses the end" in r.detail

    probe, base, s = begin("draft-roadway-sheets", tmp_path / "c")
    drafting._solve_roadway(s)
    _sheet(s, center_paper=(26.0, 11.7))
    r = probe.check(base, s)
    assert not r.passed and "outside the sheet's drawing area" in r.detail

    probe, base, s = begin("draft-roadway-sheets", tmp_path / "d")
    drafting._solve_roadway(s)
    _sheet(s, title=False)
    r = probe.check(base, s)
    assert not r.passed and "title block: project" in r.detail


def test_the_roadway_part_is_judged_first(tmp_path):
    probe, base, s = begin("draft-roadway-sheets", tmp_path)
    do(s, "create_alignment", name=drafting.ELM["name"], pis=drafting._elm_pis(),
       begin_station=drafting.ELM["begin"])
    do(s, "draw_alignment", alignment=drafting.ELM["name"], layer=drafting.CL)
    _sheet(s)
    r = probe.check(base, s)
    assert not r.passed and "edge of pavement" in r.detail


# --------------------------------------------------------------- the CLI


def test_setup_and_score_hand_a_tier2_probe_its_own_start_document(tmp_path, capsys):
    from roaddraft.probes.__main__ import main
    assert main(["list", "--tag", "tier2"]) == 0
    assert "6 probes" in capsys.readouterr().out
    out = tmp_path / "corner"
    assert main(["setup", "draft-intersection-corner", "--out", str(out)]) == 0
    assert (out / fixture.INTERSECTION_FILE).exists()
    assert main(["score", "draft-intersection-corner", "--doc",
                 str(out / fixture.INTERSECTION_FILE)]) == 1
    assert "FAIL" in capsys.readouterr().out
