"""Pilot 12 (plan set): the combined base holds together, the probe builds, the
scripted set passes while the empty start fails, and the naive slips fail."""
from __future__ import annotations

import math
import shutil

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, plan_set

PROBE = plan_set.PROBES[0]


def test_probe_builds():
    assert [p.id for p in plan_set.PROBES] == ["p12-route65-d13"]
    assert PROBE.prompt.strip() and PROBE.note.strip() and PROBE.solve
    assert PROBE.start in fixture.START


def test_combined_centerline():
    # one "D13": L-1's tangent, the published R 5000' curve from L-2's BC
    d13 = plan_set.centerline()
    st = d13.stations()
    assert st.begin_text() == "638+95.91"
    curve = d13.curves()[0]
    assert abs(curve.radius - 5000.0) < 1e-6
    assert st.format(d13.begin_station + curve.start_dist) == "654+06.05"
    assert d13.begin_station <= plan_set.RANGE[0] and d13.end_station >= plan_set.RANGE[1]
    q = plan_set.quantities()
    assert math.isclose(q["SY"], 80.0 * 3200.0 / 9.0)
    assert 2000.0 < q["LF"] < 4000.0


def test_selftest(tmp_path):
    ref = reference.write(PROBE, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", PROBE.start)
    assert not PROBE.check(Session.load(doc, out_dir=doc.parent),
                           Session.load(doc, out_dir=doc.parent)).passed


def _attempt(tmp_path, **slip):
    start = tmp_path / "start"
    doc = fixture.start_document(start, PROBE.start)
    work = tmp_path / "work"
    shutil.copytree(start, work)
    mine = work / doc.name
    session = Session.load(mine, out_dir=work)
    plan_set.make_solve(**slip)(session)
    common.save(session, mine)
    return PROBE.check(Session.load(doc, out_dir=start), Session.load(mine, out_dir=work))


def test_index_typed_from_the_plan_fails(tmp_path):
    r = _attempt(tmp_path, index_from_plan=True)
    assert not r.passed and "index" in r.detail
    assert dict(r.items)["the index of sheets"] is False


def test_match_line_lettered_off_its_station_fails(tmp_path):
    r = _attempt(tmp_path, rounded_match=True)
    assert not r.passed and "match line" in r.detail


def test_fence_over_the_whole_layer_fails(tmp_path):
    r = _attempt(tmp_path, whole_fence=True)
    assert not r.passed and "fence" in r.detail


# ------------------------------------------------------- the vague level (2026-11-08)

import re

import pytest

from roaddraft.document.fileformat import read_document, write_document
from roaddraft.mcp.server import tool_definitions


def _tool_names():
    return [t["name"] for t in tool_definitions(Session())]


def test_vague_brief():
    v = PROBE.vague
    assert v.strip() and v != PROBE.prompt and len(v) < len(PROBE.prompt)
    assert PROBE.vague_check is plan_set.vague_check
    for name in _tool_names():
        assert not re.search(rf"\b{re.escape(name)}\b", v, re.I), name
    # what the drafter cannot know: the job, its files, the sheets, the quantities' data
    for kept in ('"D13"', "Route 65", "Caltrans", "640+00", "672+00", "this one file", "AA01",
                 "BB01", "title sheet", "index of sheets", "layout sheets",
                 "summary of quantities", "HMA", "V-ROAD-EP", "square yards", "fence", "V-ROW",
                 "linear feet"):
        assert kept in v, kept
    # what a Caltrans drafter knows: the border, the scale, the count, the lettering, the fields
    for dropped in ("border", "1\" = 50'", "three", "MATCH LINE", "title block",
                    "sheet number", "total"):
        assert dropped not in v, dropped


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    """The scripted set, solved once: ``(start folder, its document, solved folder)``."""
    root = tmp_path_factory.mktemp("p12-vague")
    start = root / "start"
    doc = fixture.start_document(start, PROBE.start)
    work = root / "solved"
    shutil.copytree(start, work)
    session = Session.load(work / doc.name, out_dir=work)
    PROBE.solve(session)
    common.save(session, work / doc.name)
    return start, doc, work


def _graded(solved, tmp_path, edit=None, session_edit=None):
    """``(explicit, vague)`` results of the scripted set with ``edit(document dict)`` or
    ``session_edit(session)`` applied to a copy."""
    start, doc, work = solved
    mine = tmp_path / "mine"
    shutil.copytree(work, mine)
    path = mine / doc.name
    if edit is not None:
        d = read_document(path)
        edit(d)
        write_document(path, d)
    if session_edit is not None:
        s = Session.load(path, out_dir=mine)
        session_edit(s)
        common.save(s, path)
    base = lambda: Session.load(doc, out_dir=start)
    got = lambda: Session.load(path, out_dir=mine)
    return PROBE.check(base(), got()), PROBE.vague_check(base(), got())


def _sheets(d, *names):
    return [s for s in d["sheets"].values() if s["name"] in names]


def test_vague_solution_passes_and_start_fails(solved, tmp_path):
    explicit, vague = _graded(solved, tmp_path)
    assert explicit.passed and vague.passed, vague.detail
    start, doc, _work = solved
    s = Session.load(doc, out_dir=start)
    assert not PROBE.vague_check(s, s).passed


def _matchline(d):
    for sheet in d["sheets"].values():
        for e in sheet["entities"].values():
            if e["type"] == "text" and e["content"].startswith("MATCH LINE STA "):
                e["content"] = e["content"].replace("MATCH LINE STA ", "MATCHLINE STA. ")


def _of_total(d):
    for sheet in d["sheets"].values():
        f = sheet["title_block_fields"]
        f["sheet_number"] = f"{f['sheet_number']} OF {f.pop('total_sheets')}"


def _plan_titles(d):
    for sheet in _sheets(d, "L-1", "L-2", "L-3"):
        sheet["title_block_fields"]["sheet_title"] = "PLAN"


def _range_index(d):
    (title,) = _sheets(d, "TITLE")
    (table,) = [e for e in title["entities"].values() if e["type"] == "table"]
    table["rows"] = [["1", "TITLE SHEET"], ["2-4", "LAYOUTS"], ["5", "SUMMARY OF QUANTITIES"]]


@pytest.mark.parametrize("edit,item", [
    (_matchline, "the match line between layouts 1 and 2"),
    (_of_total, "sheet numbers and totals in every title block"),
    (_plan_titles, "the set: a title sheet, three layouts, a summary of quantities"),
    (_range_index, "the index of sheets"),
], ids=["matchline-lettered-so", "sheet-n-of-total", "layouts-titled-plan", "index-by-range"])
def test_vague_reads_the_set_by_meaning(solved, tmp_path, edit, item):
    """A convention only the explicit brief states, done another standard way: wrong at the
    explicit level, right at the vague one."""
    explicit, vague = _graded(solved, tmp_path, edit)
    assert not explicit.passed and dict(explicit.items)[item] is False
    assert vague.passed, vague.detail


def test_vague_summary_lettered_as_text(solved, tmp_path):
    q = plan_set.quantities()

    def lettered(s):
        (table,) = [eid for eid, e in s.doc.sheets["SH-005"].entities.items() if e.TYPE == "table"]
        common.ok(s.execute("delete_entities", {"ids": [table]}))
        common.ok(s.execute("place_text", {
            "space": "Q-1", "position": [4.0, 18.0], "height": 0.14,
            "content": f"HMA (TYPE A) PAVEMENT   SQYD   {q['SY']:,.0f}\n"
                       f"FENCE (TYPE CL-6)   LF   {q['LF']:,.0f}"}))
    explicit, vague = _graded(solved, tmp_path, session_edit=lettered)
    assert not dict(explicit.items)["HMA area (SY)"]
    assert vague.passed, vague.detail


@pytest.mark.parametrize("edit,item", [
    (lambda d: _sheets(d, "L-2")[0]["title_block_fields"].update(total_sheets="6"),
     "sheet numbers in every title block, totals right where lettered"),
    (lambda d: [s.update(title_block_template="standard") for s in _sheets(d, "L-1", "L-2", "L-3")],
     "the layouts on the Caltrans border at one standard scale"),
    (lambda d: _sheets(d, "L-3")[0]["viewports"][0].update(feet_per_inch=45.0),
     "the layouts on the Caltrans border at one standard scale"),
], ids=["wrong-total", "not-the-caltrans-border", "not-a-standard-scale"])
def test_vague_still_grades_what_is_lettered(solved, tmp_path, edit, item):
    explicit, vague = _graded(solved, tmp_path, edit)
    assert not explicit.passed
    assert not vague.passed and dict(vague.items)[item] is False


def _set_at(session, fpi, breaks, reach=250.0):
    """The scripted set laid out at 1" = ``fpi``' with a layout between each pair of
    ``breaks`` (quantities typed from the truth: the scale is what is tried here)."""
    n_lay = len(breaks) - 1
    names = ["TITLE"] + [f"L-{k + 1}" for k in range(n_lay)] + ["Q-1"]
    titles = ["TITLE SHEET"] + ["LAYOUT"] * n_lay + ["SUMMARY OF QUANTITIES"]
    for n, (name, title) in enumerate(zip(names, titles), start=1):
        fields = dict(plan_set.TITLE_FIELDS, sheet_title=title, sheet_number=str(n),
                      total_sheets=str(len(names)))
        common.ok(session.execute("create_sheet", {"name": name, "size": "ANSI_D",
                                                   "title_block_template": "caltrans",
                                                   "title_block_fields": fields}))
    for k in range(n_lay):
        mid, heading = plan_set._station(session, (breaks[k] + breaks[k + 1]) / 2.0)
        common.ok(session.execute("create_viewport", {
            "sheet": names[k + 1], "center_paper": [17.702, 11.0], "width_in": 31.5,
            "height_in": 20.9, "model_center": mid, "feet_per_inch": fpi,
            "rotation_deg": -heading}))
    common.ok(session.execute("create_layer", {"name": "S-ANNO-MTCH", "color": "black"}))
    for k, st in enumerate(breaks[1:-1]):
        text = f"{int(st // 100)}+{st % 100:05.2f}"
        common.ok(session.execute("draw_station_offset", {
            "alignment": plan_set.QUALIFIED, "layer": "S-ANNO-MTCH",
            "points": [f"{text}@{reach:g}L", f"{text}@{reach:g}R"]}))
        for sheet in (names[k + 1], names[k + 2]):
            common.ok(session.execute("place_label", {
                "space": sheet, "alignment": plan_set.QUALIFIED, "anchor": text,
                "kind": "custom", "content": f"MATCH LINE STA {text}",
                "rotation": "perpendicular", "side": "left", "label_offset": 1.2,
                "height": 0.14, "layer": "S-ANNO-MTCH", "halign": "center", "valign": "bottom"}))
    q = plan_set.quantities()
    common.ok(session.execute("place_table", {
        "space": "Q-1", "position": [4.0, 18.0], "title": "SUMMARY OF QUANTITIES",
        "columns": [{"header": "ITEM", "width": 6.0}, {"header": "UNIT", "width": 1.2},
                    {"header": "QUANTITY", "width": 2.0}],
        "rows": [["HMA (TYPE A) PAVEMENT", "SQYD", f"{q['SY']:,.0f}"],
                 ["FENCE (TYPE CL-6), RIGHT OF WAY", "LF", f"{q['LF']:,.0f}"]],
        "text_height": 0.14}))
    common.ok(session.execute("place_table", {
        "space": "TITLE", "position": [24.0, 16.0], "title": "INDEX OF SHEETS",
        "columns": [{"header": "SHEET NO.", "width": 1.4}, {"header": "DESCRIPTION", "width": 4.5}],
        "rows": [[str(n), t] for n, t in enumerate(titles, start=1)], "text_height": 0.14}))


def _graded_at(tmp_path, fpi, breaks):
    start = tmp_path / "start"
    doc = fixture.start_document(start, PROBE.start)
    work = tmp_path / "work"
    shutil.copytree(start, work)
    session = Session.load(work / doc.name, out_dir=work)
    _set_at(session, fpi, breaks)
    common.save(session, work / doc.name)
    base = lambda: Session.load(doc, out_dir=start)
    got = lambda: Session.load(work / doc.name, out_dir=work)
    return PROBE.check(base(), got()), PROBE.vague_check(base(), got())


def test_layouts_a_scale_takes():
    assert plan_set.layouts_needed(50.0) == plan_set.LAYOUTS == 3
    assert [plan_set.layouts_needed(f) for f in (10, 20, 30, 40, 60, 100, 200)] == [11, 6, 4, 3, 2,
                                                                                   2, 1]


def test_vague_another_standard_scale(tmp_path):
    """Two layouts at 1" = 100' with one match line: the explicit brief's three at 1" = 50'
    fail it, the vague level takes any standard scale and the count it needs."""
    explicit, vague = _graded_at(tmp_path, 100.0, [64000.0, 65600.0, 67200.0])
    assert not explicit.passed and not dict(explicit.items)["the layouts on the Caltrans border at 1\" = 50'"]
    assert vague.passed, vague.detail
    assert "the match line between layouts 1 and 2" in dict(vague.items)
    assert "the match line between layouts 2 and 3" not in dict(vague.items)


def test_vague_more_layouts_than_the_scale_takes_fails(tmp_path):
    _explicit, vague = _graded_at(tmp_path, 100.0, [64000.0, 65067.0, 66133.0, 67200.0])
    items = dict(vague.items)
    assert not vague.passed and not items["the set: a title sheet, the layouts its scale takes, "
                                          "a summary of quantities"]
    assert "takes 2" in vague.detail


def test_vague_naive_slips_still_fail(tmp_path):
    """The index from the plan, the match line lettered off its station and the fence over the
    whole layer are wrong at both levels."""
    for slip, item in (("index_from_plan", "the index of sheets"),
                       ("rounded_match", "the match line between layouts 1 and 2"),
                       ("whole_fence", "right of way fence (LF)")):
        start = tmp_path / slip / "start"
        doc = fixture.start_document(start, PROBE.start)
        work = tmp_path / slip / "work"
        shutil.copytree(start, work)
        session = Session.load(work / doc.name, out_dir=work)
        plan_set.make_solve(**{slip: True})(session)
        common.save(session, work / doc.name)
        r = PROBE.vague_check(Session.load(doc, out_dir=start),
                              Session.load(work / doc.name, out_dir=work))
        assert not r.passed and dict(r.items)[item] is False, slip
