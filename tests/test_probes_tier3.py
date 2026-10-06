"""The tier-3 probes, and whether their checks can tell right from wrong.

Each probe is built around named ways of getting a layout's alignment data
wrong -- the PI-to-PI distance for a tangent, a BC folded to read top to
bottom, curve numbers restarted on a new sheet, a paper dimension that reads
inches, the centerline's radius on an offset line, the station arithmetic an
equation breaks, a fix made by adding instead of replacing, lettering parallel
to the model on a turned sheet -- and the tests prove each one fails with a
message that says what is wrong. Correct work done another way (a copy of the
design labelled with the engine's own labelers, lettering in the sheet file's
model space, a hand-built table, widths lettered in their bands) still passes.

Sheet L-2 takes about 20 s to build; ``l2_build`` (conftest.py) builds it once
and keeps it in the pytest cache.
"""
from __future__ import annotations

import math
import shutil

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Circle, Line, Table, Text
from roaddraft.probes import drafting, fixture, notation, plotted, tasks, tier2, tier3
from roaddraft.probes.tier3 import SR, SR70, TIER3_PROBES, Road


# ------------------------------------------------------------------ setup


def begin(probe_id: str, tmp_path, l2=None):
    """``(probe, untouched baseline, a session to work in)``."""
    probe = tasks.get(probe_id)
    if probe.start == "l2":
        shutil.copytree(l2, tmp_path, dirs_exist_ok=True)
        doc = tmp_path / fixture.L2_SHEET_FILE
    else:
        doc = fixture.start_document(tmp_path, probe.start)
    return probe, Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)


def solved(probe_id: str, tmp_path, l2=None):
    probe, base, s = begin(probe_id, tmp_path, l2)
    probe.solve(s)
    assert probe.check(base, s).passed
    return probe, base, s


def do(s: Session, command: str, /, **params):
    r = s.execute(command, params)
    assert r["ok"], r
    return r


def texts(s: Session, sheet: str):
    return [e for e in tier2.sheet_named(s.doc, sheet).entities.values() if isinstance(e, Text)]


def text_with(s: Session, sheet: str, part: str) -> Text:
    return next(t for t in texts(s, sheet) if part in t.content)


def fails(probe, base, s, *phrases):
    r = probe.check(base, s)
    assert not r.passed, f"{probe.id} passed: {r.detail}"
    for phrase in phrases:
        assert phrase in r.detail, r.detail
    return r.detail


def copy_design(s: Session, qualified: str = SR, name: str = fixture.ALIGNMENT):
    """The data-shortcut route: the design copied into the sheet file from
    what get_design_data returns, so the engine's labelers can work on it."""
    row = s.query("get_design_data", {"alignment": qualified})["rows"][0]
    pis = [p["point"] + ([p["radius"]] if p["radius"] else []) for p in row["pis"]]
    params = {"name": name, "begin_station": row["begin_station"], "pis": pis}
    if row["equations"]:
        params["equations"] = [{"back": e["back"], "ahead": e["ahead"]} for e in row["equations"]]
    do(s, "create_alignment", **params)


# --------------------------------------------------------------- the set


def test_the_ten_are_wired_in_and_start_from_real_documents(tmp_path, l2_build):
    assert len(TIER3_PROBES) == 10
    assert tasks.PROBES[-10:] == TIER3_PROBES and len(tasks.PROBES) == 33
    assert len({p.id for p in tasks.PROBES}) == len(tasks.PROBES)
    for probe in TIER3_PROBES:
        assert "tier3" in probe.tags and probe.start in fixture.START
        assert probe.solve and probe.note and len(probe.prompt) > 80
        assert not probe.id.startswith("draft-") and "draft" not in probe.tags
        assert "PC " not in probe.prompt and "PT " not in probe.prompt   # BC and EC, always
    eq = Session.load(fixture.start_document(tmp_path / "eq", "sheets-eq"))
    rows = eq.query("get_design_data", {"alignment": SR, "kind": "equations"})["rows"]
    assert rows[0]["label"] == "STA 35+00.00 BK = STA 35+50.00 AH"
    row = Session.load(fixture.start_document(tmp_path / "row", "sheets-row"))
    found = row.query("find_entities", {"layer": "V-ROW", "visible_on": "C-102", "limit": 50})
    assert found["total"] == 10 and all(not e.get("anchor") for e in found["entities"])
    qa = Session.load(fixture.start_document(tmp_path / "qa", "sheets-qa"))
    planted = tier3.qa_planted(qa)
    assert sorted(planted) == ["C-101", "C-102", "C-103"] and sum(map(len, planted.values())) == 8
    l2 = Session.load(l2_build / fixture.L2_SHEET_FILE, out_dir=l2_build)
    sheet = tier2.sheet_named(l2.doc, "L-2")
    assert not [e for e in sheet.entities.values() if e.layer in ("S-ANNO-CURV", "S-ANNO-MTCH")]
    assert l2.query("find_entities", {"layer": "V-ANNO-ALGN", "limit": 5})["total"] == 0
    assert len([e for e in sheet.entities.values() if e.layer == "S-ANNO-CALL"]) == 56


@pytest.mark.parametrize("probe", TIER3_PROBES, ids=lambda p: p.id)
def test_the_scripted_solution_passes_and_the_untouched_document_does_not(probe, tmp_path, l2_build):
    _probe, base, s = begin(probe.id, tmp_path, l2_build)
    untouched = probe.check(base, base)
    assert not untouched.passed, f"{probe.id} passes with nothing done: {untouched.detail}"
    probe.solve(s)
    result = probe.check(base, s)
    assert result.passed, f"{probe.id}: {result.detail}"


# ---------------------------------------------------------- reading values


def test_notation_reads_values_not_spellings():
    for text in ('N 71°33\'54" E 1240.36\'', 'N71°33\'54"E 1240.36\'', "N 71-33-54 E 1240.36 FT"):
        assert notation.bearings(text) == [pytest.approx(71.565, abs=1e-6)]
        assert notation.feet(text) == [1240.36]
    assert notation.bearings('S 71°33\'54" W') == [pytest.approx(251.565, abs=1e-6)]
    assert notation.has_station('"SR-100" 24+05.27 BC', 2405.27)
    assert not notation.has_station("24+05 BC", 2405.27)       # not to the hundredth
    assert not notation.has_station("2405.27 BC", 2405.27)     # a station carries its plus
    assert notation.angles("18°26'06\"") == [pytest.approx(18.435, abs=1e-6)]
    assert notation.decimal_degrees("18.43°") == [18.43]
    assert notation.number("1200'") == 1200.0 and notation.number("1200") == 1200.0
    assert notation.number('N 71°33\'54" E') is None
    assert notation.has_word("43+21.30 EC", "EC") and not notation.has_word("SEC 3", "EC")
    assert [notation.curve_number(c) for c in ("1", "C-1", "C2", "CURVE 3", "x")] == [1, 1, 2, 3, None]


def test_the_plotted_reader_sees_model_space_work_through_a_turned_viewport(tmp_path, l2_build):
    # 8 ft text along the model at 11.49 deg shows at 5.03 deg, 0.16 in high, on L-2
    s = Session.load(l2_build / fixture.L2_SHEET_FILE, out_dir=l2_build)
    sheet = tier2.sheet_named(s.doc, "L-2")
    road = Road(s, SR70)
    raw = road.align.stations().parse("577+00")
    t = Text(id="TX-T", layer="0", position=road.model(raw, -10.0), content="N 78 E",
             height=8.0, rotation_deg=road.heading(raw))
    view = plotted.plot(s, sheet, [("model", t)])
    assert len(view.texts) == 1
    seen = view.texts[0]
    assert seen.rotation == pytest.approx(road.paper_heading(sheet.viewports[0], raw), abs=1e-9)
    assert seen.height == pytest.approx(0.16) and seen.space == "model"
    # a quad turned 45 degrees overlaps a box only where it really reaches it
    diamond = [[0, -1], [1, 0], [0, 1], [-1, 0]]
    assert plotted.boxes_overlap(diamond, [[0.4, 0.4], [2, 0.4], [2, 2], [0.4, 2]])
    assert not plotted.boxes_overlap(diamond, [[0.6, 0.6], [2, 0.6], [2, 2], [0.6, 2]])


# -------------------------------------------------------------- line data


def test_line_data_wants_the_tangent_length_the_forward_bearing_and_the_place(tmp_path):
    probe, base, s = solved("line-data", tmp_path)
    t2 = text_with(s, "C-102", "1240.36")
    do(s, "modify_entity", id=t2.id, changes={"content": 'N 71°33\'54" E  1581.14\''})
    fails(probe, base, s, "T-2 on C-102", "1240.36' long")
    do(s, "modify_entity", id=t2.id, changes={"content": 'S 71°33\'54" W  1240.36\''})
    fails(probe, base, s, "back bearing")
    do(s, "modify_entity", id=t2.id, changes={"content": 'N 71°33\'54" E  1240.36\'',
                                              "rotation_deg": 0.0})
    fails(probe, base, s, "runs at 0.00°")
    do(s, "modify_entity", id=t2.id, changes={"rotation_deg": 18.434949, "valign": "top"})
    fails(probe, base, s, "sits across the centerline")
    d = math.radians(18.434949)
    above = list(t2.position)
    below = [above[0] + 0.12 * math.sin(d), above[1] - 0.12 * math.cos(d)]
    do(s, "modify_entity", id=t2.id, changes={"position": below})
    fails(probe, base, s, "below the line")
    do(s, "modify_entity", id=t2.id, changes={"position": above, "valign": "bottom", "height": 0.25})
    fails(probe, base, s, "runs over linework")
    do(s, "modify_entity", id=t2.id, changes={"height": 0.10})
    assert probe.check(base, s).passed


def test_line_data_on_a_sheet_that_does_not_show_the_tangent_is_missing_from_the_one_that_does(tmp_path):
    probe, base, s = solved("line-data", tmp_path)
    t2 = text_with(s, "C-102", "1240.36")
    do(s, "delete_entities", ids=[t2.id])
    do(s, "place_text", space="C-101", position=[20.0, 9.0], content=t2.content, height=0.1,
       rotation_deg=18.434949)
    fails(probe, base, s, "T-2 on C-102", "no lettering gives")


def test_line_data_by_the_copy_route_or_in_model_space_passes(tmp_path):
    # the engine's own labeler on a copy of the design, through the viewport
    probe, base, s = begin("line-data", tmp_path)
    copy_design(s)
    for row in s.query("get_design_data", {"alignment": fixture.ALIGNMENT, "kind": "tangents"})["rows"]:
        do(s, "place_label", space=["C-101", "C-102", "C-103"][row["index"] - 1],
           alignment=fixture.ALIGNMENT, anchor=row["ref"], kind="custom",
           content=f"{row['bearing']} {row['length']:.2f}'", side="left", label_offset=0.06)
    assert probe.check(base, s).passed, probe.check(base, s).detail
    # text in the sheet file's model space, 5 ft high, plots at 0.10 in
    probe, base, s = begin("line-data", tmp_path / "m")
    road = Road(base, SR)
    for t in road.tangents():
        mid = (t["start_station"] + t["end_station"]) / 2.0
        do(s, "place_text", space="model", position=road.model(mid, -3.0), height=5.0,
           rotation_deg=road.heading(mid), halign="center", valign="bottom",
           content=f"{t['bearing']}  {t['length']:.2f}'")
    assert probe.check(base, s).passed, probe.check(base, s).detail


# ----------------------------------------------------------- curve points


def test_curve_points_must_read_bottom_to_top_to_the_hundredth_with_the_right_word(tmp_path):
    probe, base, s = solved("curve-points", tmp_path)
    ec = text_with(s, "C-102", "27+91.37 EC")
    do(s, "modify_entity", id=ec.id, changes={"rotation_deg": -71.565051})
    fails(probe, base, s, "reads top to bottom", "108.43°")
    do(s, "modify_entity", id=ec.id, changes={"rotation_deg": 108.434949,
                                              "content": '"SR-100" 27+91.37 BC'})
    fails(probe, base, s, "it is the EC")
    do(s, "modify_entity", id=ec.id, changes={"content": '"SR-100" 27+91 EC'})
    fails(probe, base, s, "to the hundredth")
    do(s, "modify_entity", id=ec.id, changes={"content": '"SR-100" 27+91.37 EC', "halign": "center",
                                              "position": tier3._at(s, SR, "C-102", 2791.367473)[0]})
    fails(probe, base, s, "covers the point")


def test_curve_points_by_the_copy_route_read_bottom_to_top_now(tmp_path):
    # place_label rotation=perpendicular reads bottom to top since BC/EC
    # letters that way (PPM 2-1.2); before, PT-1 and PC-2 came out -71.57 deg
    probe, base, s = begin("curve-points", tmp_path)
    copy_design(s)
    for sheet, anchor in (("C-101", "BC-1"), ("C-102", "EC-1"), ("C-102", "BC-2"), ("C-103", "EC-2")):
        do(s, "place_label", space=sheet, alignment=fixture.ALIGNMENT, anchor=anchor,
           rotation="perpendicular", side="left", halign="left", valign="middle",
           label_offset=0.45)
    assert probe.check(base, s).passed, probe.check(base, s).detail
    labels = [t.content for t in texts(s, "C-102")]
    assert sorted(labels) == ["BC 40+31.72", "EC 27+91.37"]


# ------------------------------------------------------------- curve data


def test_curve_data_scopes_each_table_to_its_sheet_and_numbers_along_the_line(tmp_path):
    probe, base, s = solved("curve-data", tmp_path)
    c101 = next(e for e in tier2.sheet_named(s.doc, "C-101").entities.values() if isinstance(e, Table))
    rows = c101.rows + [["2", "900'", "18°26'06\"", "146.05'", "289.58'"]]
    do(s, "modify_entity", id=c101.id, changes={"rows": rows})
    fails(probe, base, s, "C-101's table lists curve 2, which C-101 does not show")
    probe, base, s = solved("curve-data", tmp_path / "b")
    c103 = next(e for e in tier2.sheet_named(s.doc, "C-103").entities.values() if isinstance(e, Table))
    do(s, "modify_entity", id=c103.id, changes={"rows": [["1"] + c103.rows[0][1:]]})
    fails(probe, base, s, "C-103's table numbers curve 2 as 1", "not restarted")


def test_curve_data_values_are_read_column_by_column(tmp_path):
    probe, base, s = solved("curve-data", tmp_path)
    c102 = next(e for e in tier2.sheet_named(s.doc, "C-102").entities.values() if isinstance(e, Table))
    good = [list(r) for r in c102.rows]
    for change, phrase in (((3, "15.70'"), "15.70' is its external"),
                           ((2, "18.43°"), "decimal degrees"),
                           ((1, "1220'"), "R reads 1220.0"),
                           ((4, "194.73'"), "194.73' is its T")):
        rows = [list(r) for r in good]
        rows[0][change[0]] = change[1]
        do(s, "modify_entity", id=c102.id, changes={"rows": rows})
        fails(probe, base, s, phrase)
    do(s, "modify_entity", id=c102.id, changes={"rows": good})
    assert probe.check(base, s).passed


def test_a_bubble_aimed_at_the_chord_misses_and_a_hand_built_table_counts(tmp_path):
    probe, base, s = solved("curve-data", tmp_path)
    sheet = tier2.sheet_named(s.doc, "C-102")
    road = Road(base, SR)
    c1 = road.curves()[0]
    chord_mid = [(c1["pc"][0] + c1["pt"][0]) / 2.0, (c1["pc"][1] + c1["pt"][1]) / 2.0]
    tip = sheet.viewports[0].transform().to_paper(chord_mid)
    bubble = next(t for t in texts(s, "C-102") if t.content == "1")
    leader = next(e for e in sheet.entities.values() if isinstance(e, Line)
                  and abs(math.dist(e.start, bubble.position) - 0.2) < 1e-6)
    do(s, "modify_entity", id=leader.id, changes={"end": tip})
    fails(probe, base, s, "bubble 1's leader on C-102 stops", "ft off the curve")
    # a table lettered as texts, one per cell, reads like place_table's
    probe, base, s = solved("curve-data", tmp_path / "b")
    for name in fixture.SHEETS:
        table = next(e for e in tier2.sheet_named(s.doc, name).entities.values() if isinstance(e, Table))
        do(s, "delete_entities", ids=[table.id])
        for i, row in enumerate(table.rows):
            for j, cell in enumerate(row):
                do(s, "place_text", space=name, position=[25.0 + 0.9 * j, 5.0 - 0.25 * i],
                   content=cell, height=0.1)
    assert probe.check(base, s).passed, probe.check(base, s).detail


# -------------------------------------------------------------- stationing


def test_stationing_holds_the_caltrans_lettering_ticks_and_side(tmp_path):
    probe, base, s = solved("stationing", tmp_path)
    six = next(t for t in texts(s, "C-102") if t.content == "6")
    do(s, "modify_entity", id=six.id, changes={"content": "26+00"})
    fails(probe, base, s, "26+00 is lettered '26+00'; Caltrans letters it '6'")
    do(s, "modify_entity", id=six.id, changes={"content": "26"})
    fails(probe, base, s, "lettered '26'")
    do(s, "modify_entity", id=six.id, changes={"content": "6", "valign": "bottom",
                                               "position": tier3._at(s, SR, "C-102", 2600.0, -2.0)[0]})
    fails(probe, base, s, "above the line")
    probe, base, s = solved("stationing", tmp_path / "b")
    tick = next(e for e in tier2.sheet_named(s.doc, "C-102").entities.values()
                if isinstance(e, Line) and math.dist(e.start, tier3._at(s, SR, "C-102", 3000.0, -3.5)[0]) < 0.01)
    p, _d = tier3._at(s, SR, "C-102", 3000.0)
    do(s, "modify_entity", id=tick.id, changes={"start": [p[0], p[1] + 0.2], "end": [p[0], p[1] - 0.2]})
    fails(probe, base, s, "the tick at 30+00")


def test_station_numbers_may_be_square_to_the_sheet_and_tables_may_carry_units(tmp_path):
    probe, base, s = solved("stationing", tmp_path)
    for t in texts(s, "C-102"):
        do(s, "modify_entity", id=t.id, changes={"rotation_deg": 0.0})
    assert probe.check(base, s).passed, probe.check(base, s).detail
    probe, base, s = solved("curve-data", tmp_path / "b")
    for name in fixture.SHEETS:
        table = next(e for e in tier2.sheet_named(s.doc, name).entities.values() if isinstance(e, Table))
        cols = [{"header": h, "width": c["width"]} for h, c in
                zip(("CURVE NO.", "R (FT)", "DELTA", "T (FT)", "L (FT)"), table.columns)]
        do(s, "delete_entities", ids=[table.id])
        do(s, "place_table", space=name, position=table.position, columns=cols, rows=table.rows,
           title=table.title, text_height=table.text_height)
    assert probe.check(base, s).passed, probe.check(base, s).detail


def test_stationing_by_the_copy_route_passes(tmp_path):
    probe, base, s = begin("stationing", tmp_path)
    copy_design(s)
    do(s, "create_layer", name="V-ANNO-STAT", color="black")
    r = do(s, "annotate_stationing", space="model", alignment=fixture.ALIGNMENT, interval=100,
           station_range=["26+00", "41+00"], include_pc_pt=False, tick_half_len=3.5,
           text_height=4.0, label_offset=-5.0, layer="V-ANNO-STAT")
    for eid in r["created"]:
        e = s.doc.model_entities[eid]
        if isinstance(e, Text):
            do(s, "modify_entity", id=eid, changes={
                "content": tier3.caltrans_lettering(e.anchor["station"]), "valign": "top"})
    assert probe.check(base, s).passed, probe.check(base, s).detail


# ------------------------------------------------------------- width dims


def _dims_at(s: Session, station: float, **extra):
    for lo, hi, _w, _what in tier3.BANDS:
        p1 = tier3._at(s, SR, "C-101", station, lo)[0]
        p2 = tier3._at(s, SR, "C-101", station, hi)[0]
        do(s, "place_dimension", space="C-101", kind="aligned", p1=p1, p2=p2,
           line_point=[(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2], text_height=0.08, **extra)


def test_width_dims_on_paper_need_the_plot_scale_and_room_for_their_numbers(tmp_path):
    probe, base, s = begin("width-dims", tmp_path)
    _dims_at(s, 1700.0)
    fails(probe, base, s, "reads '0.16'", "measure_scale")
    probe, base, s = begin("width-dims", tmp_path / "b")
    _dims_at(s, 1700.0, precision=0, measure_scale=50.0)
    fails(probe, base, s, "overlap")


def test_widths_lettered_in_their_bands_or_dimensioned_in_the_model_pass(tmp_path):
    probe, base, s = begin("width-dims", tmp_path)
    for lo, hi, width, _what in tier3.BANDS:
        do(s, "place_text", space="C-101", position=tier3._at(s, SR, "C-101", 1700.0, (lo + hi) / 2)[0],
           content=f"{width:g}'", height=0.08, halign="center", valign="middle")
    assert probe.check(base, s).passed, probe.check(base, s).detail
    probe, base, s = begin("width-dims", tmp_path / "m")
    road = Road(base, SR)
    for (lo, hi, _w, _what), station in zip(tier3.BANDS, (1680.0, 1690.0, 1710.0, 1720.0)):
        p1, p2 = road.model(station, lo), road.model(station, hi)
        do(s, "place_dimension", space="model", kind="aligned", p1=p1, p2=p2,
           line_point=[(p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2], text_height=4.0, precision=0)
    assert probe.check(base, s).passed, probe.check(base, s).detail


# ----------------------------------------------------------- right of way


def test_row_data_wants_the_offset_geometry_every_piece_and_the_order(tmp_path):
    probe, base, s = solved("row-data", tmp_path)
    curves = next(e for e in tier2.sheet_named(s.doc, "C-102").entities.values()
                  if isinstance(e, Table) and e.title == "CURVE TABLE")
    good = [list(r) for r in curves.rows]
    rows = [list(r) for r in good]
    rows[0][1] = "1200.00'"
    do(s, "modify_entity", id=curves.id, changes={"rows": rows})
    fails(probe, base, s, "C1's radius reads 1200.0", "centerline's radius")
    rows = [list(r) for r in good]
    rows[0][3] = "235.20'"
    do(s, "modify_entity", id=curves.id, changes={"rows": rows})
    fails(probe, base, s, "C1's length")
    do(s, "modify_entity", id=curves.id, changes={"rows": good})
    jog = next(t for t in texts(s, "C-102") if t.content == "L2")
    do(s, "delete_entities", ids=[jog.id])
    fails(probe, base, s, "has no tag")
    probe, base, s = solved("row-data", tmp_path / "b")
    one, two = (next(t for t in texts(s, "C-102") if t.content == tag) for tag in ("L1", "L3"))
    do(s, "modify_entity", id=one.id, changes={"content": "L3"})
    do(s, "modify_entity", id=two.id, changes={"content": "L1"})
    fails(probe, base, s, "should be", "C1, L1, L2, L3, L4, L5, C2")


def test_row_data_tags_on_the_left_line_do_not_count(tmp_path):
    probe, base, s = solved("row-data", tmp_path)
    tag = next(t for t in texts(s, "C-102") if t.content == "L3")
    road = Road(base, SR)
    vp = tier2.sheet_named(base.doc, "C-102").viewports[0]
    do(s, "modify_entity", id=tag.id, changes={"position": road.paper(vp, 3300.0, -57.0)})
    fails(probe, base, s, "left right of way line")


# ---------------------------------------------------------------- equation


def test_equation_data_catches_station_arithmetic_across_the_equation(tmp_path):
    probe, base, s = solved("equation-data", tmp_path)
    t2 = text_with(s, "C-102", "1240.36")
    do(s, "modify_entity", id=t2.id, changes={"content": t2.content.replace("1240.36", "1290.35")})
    fails(probe, base, s, "1290.35' is the difference of its stations across the equation")
    do(s, "modify_entity", id=t2.id, changes={"content": t2.content.replace("1290.35", "1240.36")})
    bc = text_with(s, "C-102", "40+81.72 BC")
    do(s, "modify_entity", id=bc.id, changes={"content": "40+31.72 BC"})
    fails(probe, base, s, "without the equation", "40+81.72")
    do(s, "modify_entity", id=bc.id, changes={"content": "40+81.72 BC"})
    eq = text_with(s, "C-102", "BK")
    do(s, "modify_entity", id=eq.id, changes={"content": "35+50.00 BK = 35+00.00 AH"})
    fails(probe, base, s, "it is 35+00.00 BK = 35+50.00 AH")


def test_the_back_station_of_an_equation_teaches_instead_of_saying_it_does_not_exist(tmp_path):
    _probe, base, _s = begin("equation-data", tmp_path)
    r = base.query("station_to_xy", {"alignment": SR, "station": "35+00"})
    assert not r["ok"] and "back reading of the equation" in r["error"]["message"]
    assert "region=1" in r["error"]["hint"]
    r = base.query("station_to_xy", {"alignment": SR, "station": "35+00", "region": 1})
    assert r["ok"] and r["station_text"] == "35+50.00"


# ---------------------------------------------------------------------- QA


def test_qa_wants_every_plant_fixed_by_replacing_not_adding(tmp_path):
    probe, base, s = begin("qa-alignment-data", tmp_path)
    for t in texts(s, "C-102"):
        if "1581.14" in t.content:
            do(s, "place_text", space="C-102", position=[t.position[0], t.position[1] + 0.5],
               content=t.content.replace("1581.14", "1240.36"), height=t.height,
               rotation_deg=t.rotation_deg)
    fails(probe, base, s)
    probe.solve(s)
    detail = fails(probe, base, s)
    assert "twice" in detail or "still letters" in detail, detail


def test_qa_fails_on_a_right_item_changed_and_passes_on_a_retyped_one(tmp_path):
    probe, base, s = begin("qa-alignment-data", tmp_path)
    probe.solve(s)
    assert probe.check(base, s).passed
    t1 = text_with(s, "C-101", "1405.27")
    do(s, "delete_entities", ids=[t1.id])
    do(s, "place_text", space="C-101", position=t1.position, content=t1.content, height=t1.height,
       rotation_deg=t1.rotation_deg, halign=t1.halign, valign=t1.valign)
    assert probe.check(base, s).passed        # retyped where it was: the same item
    t1 = text_with(s, "C-101", "1405.27")
    do(s, "modify_entity", id=t1.id, changes={"position": [t1.position[0] + 1.0, t1.position[1]]})
    fails(probe, base, s, "was changed or removed, and it was right")


def _fix(s: Session, plant: dict):
    """Undo one plant the way an agent would: edit the text, swap the cells,
    renumber the row and the bubble."""
    sheet = tier2.sheet_named(s.doc, plant["sheet"])
    if "was" in plant:
        t = next(t for t in texts(s, plant["sheet"]) if plant["now"] in t.content)
        do(s, "modify_entity", id=t.id, changes={"content": t.content.replace(plant["now"], plant["was"])})
        return
    table = next(e for e in sheet.entities.values() if isinstance(e, Table))
    if plant.get("swap"):
        rows = [list(r) for r in table.rows]
        rows[-1][3], rows[-1][4] = rows[-1][4], rows[-1][3]
        do(s, "modify_entity", id=table.id, changes={"rows": rows})
        return
    do(s, "modify_entity", id=table.id, changes={"rows": [["2"] + table.rows[0][1:]]})
    bubble = next(t for t in texts(s, plant["sheet"]) if t.content == "1")
    do(s, "modify_entity", id=bubble.id, changes={"content": "2"})


def test_qa_names_each_plant_until_it_is_fixed(tmp_path):
    # the check reports one problem at a time; fix whichever it names, and
    # every one of the five has to be named before the sheets pass
    probe, base, s = begin("qa-alignment-data", tmp_path)
    says = {0: "24+05.27", 1: "1240.36' long", 2: "curve 2's T reads 289.58", 3: "curve 2 as 1",
            4: "it is the EC"}
    named = []
    for _ in range(len(tier3.QA_PLANTS)):
        r = probe.check(base, s)
        assert not r.passed
        which = next(i for i, phrase in says.items() if phrase in r.detail and i not in named)
        named.append(which)
        _fix(s, tier3.QA_PLANTS[which])
    assert sorted(named) == [0, 1, 2, 3, 4]
    assert probe.check(base, s).passed


# --------------------------------------------------------------- L-2


def test_l2_match_lines_must_be_square_on_the_turned_sheet(tmp_path, l2_build):
    probe, base, s = solved("l2-match-lines", tmp_path, l2_build)
    road = Road(base, SR70)
    sheet = tier2.sheet_named(s.doc, "L-2")
    vp = sheet.viewports[0]
    raw = road.align.stations().parse("589+50")
    line = next(e for e in sheet.entities.values() if isinstance(e, Line)
                and math.dist(e.start, road.paper(vp, raw, -95.0)) < 1e-3)
    q = road.paper(vp, raw)
    do(s, "modify_entity", id=line.id, changes={"start": [q[0], q[1] + 1.5], "end": [q[0], q[1] - 1.5]})
    fails(probe, base, s, "runs at 90.00° on the sheet", "123.27°")
    model_square = math.radians(road.heading(raw) + 90.0)
    a = [q[0] + 1.5 * math.cos(model_square), q[1] + 1.5 * math.sin(model_square)]
    b = [q[0] - 1.5 * math.cos(model_square), q[1] - 1.5 * math.sin(model_square)]
    do(s, "modify_entity", id=line.id, changes={"start": a, "end": b})
    fails(probe, base, s, "square to the line in the model", "turned")
    probe, base, s = solved("l2-match-lines", tmp_path / "b", l2_build)
    l1 = text_with(s, "L-2", "(L-1)")
    do(s, "modify_entity", id=l1.id, changes={"content": "MATCH LINE (L-3)"})
    fails(probe, base, s, "back of it is L-1")


def test_l2_alignment_data_numbering_twist_pcc_and_legibility(tmp_path, l2_build):
    probe, base, s = solved("l2-alignment-data", tmp_path, l2_build)
    table = next(e for e in tier2.sheet_named(s.doc, "L-2").entities.values() if isinstance(e, Table))
    good = [list(r) for r in table.rows]
    do(s, "modify_entity", id=table.id, changes={"rows": [[str(int(r[0]) - 1)] + r[1:] for r in good]})
    fails(probe, base, s, "the design's own indices", "2, 3, 4, 5")
    do(s, "modify_entity", id=table.id, changes={"rows": good})
    pcc = text_with(s, "L-2", "588+34.95 PCC")
    do(s, "modify_entity", id=pcc.id, changes={"content": '"SR70" 588+34.95 EC'})
    fails(probe, base, s, "it is the PCC")
    do(s, "modify_entity", id=pcc.id, changes={"content": '"SR70" 588+34.95 PCC'})
    t2 = text_with(s, "L-2", "230.76")
    road = Road(base, SR70)
    raw = road.align.stations().parse("577+32")
    do(s, "modify_entity", id=t2.id, changes={"rotation_deg": road.heading(raw)})
    fails(probe, base, s, "the viewport is turned")
    do(s, "modify_entity", id=t2.id, changes={
        "rotation_deg": road.paper_heading(tier2.sheet_named(base.doc, "L-2").viewports[0], raw)})
    assert probe.check(base, s).passed
    note = next(t for t in texts(base, "L-2") if t.content.startswith("NOTES"))
    do(s, "place_text", space="L-2", position=note.position, content="C-2", height=0.14)
    fails(probe, base, s, "overlaps the sheet's 'NOTES:'")


def test_setup_hands_a_tier3_probe_its_own_start_document(tmp_path, capsys):
    from roaddraft.probes.__main__ import main
    assert main(["list", "--tag", "tier3"]) == 0
    assert "10 probes" in capsys.readouterr().out
    out = tmp_path / "eq"
    assert main(["setup", "equation-data", "--out", str(out)]) == 0
    assert (out / fixture.EQ_SHEET_FILE).exists() and (out / fixture.EQ_MODEL_FILE).exists()
    assert main(["score", "equation-data", "--doc", str(out / fixture.EQ_SHEET_FILE)]) == 1
    assert "FAIL" in capsys.readouterr().out
