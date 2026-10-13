"""The find-probes, and whether their checks can tell right from wrong.

A probe set that only confirms good work is worthless -- these tests spend most
of their effort on the failing cases: the curve trap, pointing at the wrong
parallel line, text with no leader, and doing the job on some of the sheets.
"""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.document.locate import point_at, resolve_entity
from roaddraft.probes import fixture, tasks


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    out = tmp_path_factory.mktemp("probe-project")
    _model, sheets = fixture.build(out)
    return out, sheets


def fresh(project) -> Session:
    out, sheets = project
    return Session.load(sheets, out_dir=out)


def baseline(project) -> Session:
    return fresh(project)


@pytest.mark.parametrize("probe", [p for p in tasks.FIND_PROBES if p.solve],
                         ids=lambda p: p.id)
def test_the_scripted_solution_passes_and_the_untouched_project_does_not(probe, project):
    base = baseline(project)
    session = fresh(project)
    probe.solve(session)
    result = probe.check(base, session)
    assert result.passed, f"{probe.id}: {result.detail}"
    untouched = probe.check(base, fresh(project))
    assert not untouched.passed, f"{probe.id} passes without doing anything"


def test_every_probe_has_a_prompt_and_either_a_solution_or_a_reason():
    assert len(tasks.PROBES) == len({p.id for p in tasks.PROBES})
    for probe in tasks.PROBES:
        assert probe.prompt.strip() and probe.tags
        assert probe.solve or probe.blocked_on, probe.id
    assert not [p.id for p in tasks.PROBES if p.blocked_on]


def test_the_curve_trap_fails_the_check(project):
    """Aiming at the midpoint of an arc's endpoints is the mistake the probe
    exists to catch: 15.5 ft off on this alignment, 15x the tolerance."""
    base = baseline(project)
    session = fresh(project)
    arc_id = tasks.targets(session, anchor={"kind": "offset",
                                            "offset": list(fixture.EDGE_OFFSETS)},
                           type="arc", visible_on="C-102")[0]
    entity, owner, _ref, _space = resolve_entity(session.doc, arc_id)
    start = point_at(owner, entity, "start")[0]
    end = point_at(owner, entity, "end")[0]
    chord_mid = [(start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0]

    session.execute("create_layer", {"name": "rd_LAYOUT-NOTE-anno", "color": "black"})
    r = session.execute("place_callout", {"space": "model", "target": chord_mid,
                                          "position": [chord_mid[0] + 150.0,
                                                       chord_mid[1] - 150.0],
                                          "content": "EP", "layer": "rd_LAYOUT-NOTE-anno"})
    # The engine cannot call this empty space -- 15.3 ft off the edge is 7.3 ft
    # from the shoulder -- but it does say which line the tip landed on.
    assert r["ok"] and r["warnings"]
    assert "rd_ES" in r["warnings"][0] and "20.00' LT" in r["warnings"][0]
    result = tasks.get("edge-curve-c102").check(base, session)
    assert not result.passed
    assert "nearest miss" in result.detail

    # the same callout aimed by entity passes
    good = fresh(project)
    tasks.callout_at(good, arc_id)
    assert tasks.get("edge-curve-c102").check(base, good).passed


def test_pointing_at_the_wrong_parallel_line_fails(project):
    """Shoulder is 20 ft out, pavement edge is 12: a plausible confusion."""
    base = baseline(project)
    session = fresh(project)
    edge_id = tasks.targets(session, anchor={"kind": "offset", "offset": -12.0},
                            visible_on="C-101")[0]
    tasks.callout_at(session, edge_id, content="SHOULDER")
    result = tasks.get("shoulder-c101").check(base, session)
    assert not result.passed and "nearest miss" in result.detail
    # 8 ft apart, so the miss is small but real
    assert "8.0" in result.detail or "7.9" in result.detail


def test_text_with_no_leader_and_a_leader_with_no_text_both_fail(project):
    base = baseline(project)
    probe = tasks.get("edge-c102")

    text_only = fresh(project)
    text_only.execute("create_layer", {"name": "rd_LAYOUT-NOTE-anno", "color": "black"})
    edge = tasks.targets(text_only, anchor={"kind": "offset",
                                            "offset": list(fixture.EDGE_OFFSETS)},
                         visible_on="C-102")[0]
    entity, owner, _ref, _space = resolve_entity(text_only.doc, edge)
    on_it = point_at(owner, entity, "mid")[0]
    text_only.execute("place_text", {"space": "model", "position": on_it,
                                     "content": "EDGE OF PAVEMENT", "height": 8.0,
                                     "layer": "rd_LAYOUT-NOTE-anno"})
    result = probe.check(base, text_only)
    assert not result.passed and "no leader" in result.detail

    leader_only = fresh(project)
    leader_only.execute("draw_line", {"space": "model", "start": on_it,
                                      "end": [on_it[0] + 100, on_it[1] - 100]})
    result = probe.check(base, leader_only)
    assert not result.passed and "no text" in result.detail


def test_a_callout_built_by_hand_scores_the_same_as_place_callout(project):
    """The check reads the document, not the command list."""
    base = baseline(project)
    session = fresh(project)
    edge = tasks.targets(session, anchor={"kind": "offset",
                                          "offset": list(fixture.EDGE_OFFSETS)},
                         visible_on="C-102")[0]
    entity, owner, _ref, _space = resolve_entity(session.doc, edge)
    on_it = point_at(owner, entity, "mid")[0]
    session.execute("create_layer", {"name": "rd_LAYOUT-NOTE-anno", "color": "black"})
    session.execute("draw_line", {"space": "model", "start": on_it,
                                  "end": [on_it[0] + 150, on_it[1] - 150],
                                  "layer": "rd_LAYOUT-NOTE-anno"})
    session.execute("place_text", {"space": "model",
                                   "position": [on_it[0] + 160, on_it[1] - 150],
                                   "content": "EDGE OF PAVEMENT", "height": 8.0,
                                   "layer": "rd_LAYOUT-NOTE-anno"})
    assert tasks.get("edge-c102").check(base, session).passed


def test_title_blocks_must_be_every_sheet_and_carry_the_right_values(project):
    base = baseline(project)
    probe = tasks.get("title-blocks")

    partial = fresh(project)
    for name in ("C-101", "C-102"):
        partial.execute("fill_title_block", {"sheet": name,
                                             "fields": {**tasks.TITLE_FIELDS,
                                                        "sheet_title": "ROADWAY PLAN"}})
    result = probe.check(base, partial)
    assert not result.passed and "C-103" in result.detail

    wrong = fresh(project)
    for name in ("C-101", "C-102", "C-103"):
        wrong.execute("fill_title_block", {"sheet": name,
                                           "fields": {**tasks.TITLE_FIELDS,
                                                      "sheet_title": "ROADWAY PLAN",
                                                      "scale": "1\" = 100'"}})
    result = probe.check(base, wrong)
    assert not result.passed and "scale" in result.detail


def test_pc_by_station_needs_the_referenced_design_and_now_has_it(project):
    """This probe was blocked until queries could read a referenced design: a PC
    is not an entity, so there is nothing to find -- only a station to ask for."""
    session = fresh(project)
    assert session.query("list_alignments", {})["alignments"] == []   # owns none
    qualified = f"DESIGN:{fixture.ALIGNMENT}"
    assert session.query("list_alignments", {"include_references": True})["count"] == 1
    pc = session.query("resolve_anchor", {"alignment": qualified, "anchor": "PC-1"})
    assert pc["ok"] and pc["station_text"] and pc["auto_content"].endswith(" BC")
    # nothing in the drawing sits at the PC, which is why find_entities cannot do it
    assert all(row["point"] != pc["point"]
               for row in session.query("find_entities", {})["entities"])
    # and the probe's own check agrees once the work is done
    base = baseline(project)
    tasks.get("pc-by-station").solve(session)
    assert tasks.get("pc-by-station").check(base, session).passed
