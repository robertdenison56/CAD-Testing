"""The drafting-probes, and whether their checks can tell right from wrong.

Each probe is built around a specific way of getting it wrong -- a swapped
northing and easting, a width used as an offset, an edge that runs through the
bulb -- and most of the effort here goes into proving that each of those fails,
with a message that says what is wrong. The other half is the opposite claim:
correct work done some other way (elements instead of PIs, lines and arcs
instead of draw_offset, four lines instead of a polyline) still passes, because
the checks judge what was drafted and not which commands drafted it.
"""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Arc, Line
from roaddraft.probes import drafting, fixture, tasks
from roaddraft.probes.drafting import CL, EOP, SHLD, traverse


def begin(probe_id: str, tmp_path):
    """``(probe, untouched baseline, a session to work in)``."""
    probe = tasks.get(probe_id)
    doc = fixture.start_document(tmp_path, probe.start)
    return probe, Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)


def do(s: Session, command: str, /, **params):
    r = s.execute(command, params)
    assert r["ok"], r
    return r


def copy_by_hand(s: Session, ids, layer: str):
    """Redraw entities as plain lines and arcs, then delete the originals."""
    for eid in ids:
        e = s.doc.model_entities[eid]
        if isinstance(e, Line):
            do(s, "draw_line", space="model", layer=layer, start=e.start, end=e.end)
        elif isinstance(e, Arc):
            do(s, "draw_arc", space="model", layer=layer, center=e.center, radius=e.radius,
               start_angle_deg=e.start_angle_deg, end_angle_deg=e.end_angle_deg)
    do(s, "delete_entities", ids=list(ids))


# ------------------------------------------------------------- the probe set


def test_every_drafting_probe_is_wired_in_and_starts_from_a_real_document(tmp_path):
    assert len(drafting.DRAFT_PROBES) == 8
    from roaddraft.probes import tier2
    assert tasks.PROBES == tasks.FIND_PROBES + drafting.DRAFT_PROBES + tier2.TIER2_PROBES
    assert len({p.id for p in tasks.PROBES}) == len(tasks.PROBES)
    for probe in drafting.DRAFT_PROBES:
        assert probe.id.startswith("draft-") and "draft" in probe.tags
        assert probe.start in fixture.START and probe.start != "sheets"
        assert probe.solve and probe.note and len(probe.prompt) > 60
    blank = Session.load(fixture.start_document(tmp_path / "b", "blank"))
    assert not blank.doc.model_entities and not blank.doc.design.alignments
    assert {CL, EOP, SHLD} <= set(blank.doc.layers) and "V-BLDG" not in blank.doc.layers
    centerline = Session.load(fixture.start_document(tmp_path / "c", "centerline"))
    assert list(centerline.doc.design.alignments) == ["SR-100"]
    assert {e.layer for e in centerline.doc.model_entities.values()} == {CL}


@pytest.mark.parametrize("probe", drafting.DRAFT_PROBES, ids=lambda p: p.id)
def test_the_scripted_solution_passes_and_the_untouched_document_does_not(probe, tmp_path):
    _probe, base, s = begin(probe.id, tmp_path)
    untouched = probe.check(base, base)
    assert not untouched.passed, f"{probe.id} passes with nothing done: {untouched.detail}"
    probe.solve(s)
    result = probe.check(base, s)
    assert result.passed, f"{probe.id}: {result.detail}"


def test_the_numbers_quoted_in_the_notes_are_right():
    pis = drafting._bd_pis()
    assert pis[1][:2] == pytest.approx([1798.31, 1415.57], abs=0.005)
    assert pis[2] == pytest.approx([2888.90, 1271.99], abs=0.005)
    assert drafting._bldg_corners() == [pytest.approx(c, abs=0.005) for c in (
        [1500, 1200], [1530, 1251.96], [1564.64, 1231.96], [1534.64, 1180])]
    assert drafting._cds_throat() == pytest.approx(1357.23, abs=0.005)
    a = drafting.expected_alignment("SR-9", drafting.PIC["pis"], "50+00")
    curve = a.curves()[0]
    external = math.dist(drafting.PIC["pis"][1][:2], curve.center) - curve.radius
    assert external == pytest.approx(65.9, abs=0.05)


# ------------------------------------------------------- 1. northing/easting


def test_a_swapped_northing_and_easting_fails(tmp_path):
    probe, base, s = begin("draft-tangent-ne", tmp_path)
    do(s, "create_alignment", name="MAIN-ST", begin_station="10+00",
       pis=[[5000, 2000], [6200, 2000]])
    do(s, "draw_alignment", alignment="MAIN-ST", layer=CL)
    result = probe.check(base, s)
    assert not result.passed and "MAIN-ST begins at [5000.00, 2000.00]" in result.detail
    assert "4242.64 ft from [2000.00, 5000.00]" in result.detail


def test_the_wrong_name_station_or_direction_each_fail(tmp_path):
    for case, params, message in (
            ("name", {"name": "MAIN", "begin_station": "10+00"}, "no alignment named MAIN-ST"),
            ("station", {"name": "MAIN-ST", "begin_station": "0+00"}, "begins at station"),
            ("north", {"name": "MAIN-ST", "begin_station": "10+00",
                       "pis": [[2000, 5000], [2000, 6200]]}, "MAIN-ST ends at")):
        probe, base, s = begin("draft-tangent-ne", tmp_path / case)
        do(s, "create_alignment", **{"pis": [[2000, 5000], [3200, 5000]], **params})
        do(s, "draw_alignment", alignment=params["name"], layer=CL)
        result = probe.check(base, s)
        assert not result.passed and message in result.detail, case
    # the name is not case-sensitive
    probe, base, s = begin("draft-tangent-ne", tmp_path / "case")
    do(s, "create_alignment", name="Main-St", begin_station="10+00",
       pis=[[2000, 5000], [3200, 5000]])
    do(s, "draw_alignment", alignment="Main-St", layer=CL)
    assert probe.check(base, s).passed


# --------------------------------------------------------- 2. PIs and a curve


def test_linework_from_pi_to_pi_is_not_an_alignment(tmp_path):
    probe, base, s = begin("draft-pi-curve", tmp_path)
    do(s, "draw_polyline", space="model", layer=CL,
       vertices=[[1000, 1000], [2200, 1000], [3100, 1900]])
    result = probe.check(base, s)
    assert not result.passed and "linework is not an alignment" in result.detail


def test_a_wrong_curve_fails_and_an_undrawn_alignment_fails(tmp_path):
    probe, base, s = begin("draft-pi-curve", tmp_path / "no-curve")
    # leaving the curve out altogether is a mistake the engine will not take
    r = s.execute("create_alignment", {"name": "SR-9", "begin_station": "50+00",
                                       "pis": [[1000, 1000], [2200, 1000], [3100, 1900]]})
    assert not r["ok"] and "curve radius" in r["error"]["message"]
    for case, radius, message in (("r600", 600, "SR-9 is"),
                                  ("r810", 810, "leaves its described path by 0.82 ft"),
                                  ("r801", 801, None)):
        probe, base, s = begin("draft-pi-curve", tmp_path / case)
        do(s, "create_alignment", name="SR-9", begin_station="50+00",
           pis=[[1000, 1000], [2200, 1000, radius], [3100, 1900]])
        do(s, "draw_alignment", alignment="SR-9", layer=CL)
        result = probe.check(base, s)
        if message is None:        # 1 ft of radius moves the curve 0.08 ft: inside tolerance
            assert result.passed, result.detail
        else:
            assert not result.passed and message in result.detail, (case, result.detail)
    probe, base, s = begin("draft-pi-curve", tmp_path / "undrawn")
    do(s, "create_alignment", name="SR-9", begin_station="50+00", pis=drafting.PIC["pis"])
    result = probe.check(base, s)
    assert not result.passed and "nothing drawn for the centerline" in result.detail


def test_the_right_linework_on_the_wrong_layer_says_so(tmp_path):
    probe, base, s = begin("draft-pi-curve", tmp_path)
    do(s, "create_alignment", name="SR-9", begin_station="50+00", pis=drafting.PIC["pis"])
    do(s, "draw_alignment", alignment="SR-9", layer=EOP)
    result = probe.check(base, s)
    assert not result.passed
    assert f"is drawn, but not on {CL}" in result.detail and EOP in result.detail


def test_an_alignment_built_from_elements_and_drawn_by_hand_passes(tmp_path):
    """What is judged is where it runs, not which parameters made it."""
    probe, base, s = begin("draft-pi-curve", tmp_path)
    want = drafting.expected_alignment("SR-9", drafting.PIC["pis"], "50+00")
    elements = []
    for el in want.elements:
        if hasattr(el, "center"):
            elements.append({"kind": "curve", "pc": el.start, "pt": el.end,
                             "center": el.center, "direction": el.direction})
        else:
            elements.append({"kind": "tangent", "start": el.start, "end": el.end})
    do(s, "create_alignment", name="SR-9", begin_station="50+00", elements=elements)
    drawn = do(s, "draw_alignment", alignment="SR-9", layer=CL)["created"]
    copy_by_hand(s, drawn, CL)
    assert all(e.anchor is None for e in s.doc.model_entities.values())
    result = probe.check(base, s)
    assert result.passed, result.detail


# ------------------------------------------- 3. bearing, distance, deflection


def bearing_alignment(s, legs, radius=600.0):
    p = traverse([1000.0, 1000.0], legs)
    pis = [[round(v, 2) for v in p[0]], [round(p[1][0], 2), round(p[1][1], 2), radius],
           [round(v, 2) for v in p[2]]]
    do(s, "create_alignment", name="RAMP-B", begin_station="10+00", pis=pis)
    do(s, "draw_alignment", alignment="RAMP-B", layer=CL)


def test_coordinates_worked_to_the_hundredth_pass(tmp_path):
    probe, base, s = begin("draft-bearing-distance", tmp_path)
    bearing_alignment(s, [(62.5, 900.0), (97.5, 1100.0)])
    assert probe.check(base, s).passed


def test_the_ways_of_misreading_a_bearing_each_fail(tmp_path):
    for case, legs in (
            ("angle-from-east", [(90 - 62.5, 900.0), (90 - 62.5 - 35, 1100.0)]),
            ("deflected-left", [(62.5, 900.0), (62.5 - 35, 1100.0)]),
            ("deflection-as-bearing", [(62.5, 900.0), (35.0, 1100.0)]),
            ("rounded-to-the-degree", [(62.0, 900.0), (97.0, 1100.0)])):
        probe, base, s = begin("draft-bearing-distance", tmp_path / case)
        bearing_alignment(s, legs)
        result = probe.check(base, s)
        assert not result.passed and "RAMP-B" in result.detail, case


def test_trig_worked_to_three_figures_is_not_good_enough(tmp_path):
    """sin 62.5 = 0.887, cos = 0.462, sin 97.5 = 0.991, cos = -0.131: the end
    lands 0.7 ft out. Four figures lands inside the tolerance."""
    for figures, passes in ((3, False), (4, True)):
        probe, base, s = begin("draft-bearing-distance", tmp_path / str(figures))
        r = lambda v: round(v, figures)  # noqa: E731
        pi = [1000 + 900 * r(math.sin(math.radians(62.5))),
              1000 + 900 * r(math.cos(math.radians(62.5)))]
        end = [pi[0] + 1100 * r(math.sin(math.radians(97.5))),
               pi[1] + 1100 * r(math.cos(math.radians(97.5)))]
        do(s, "create_alignment", name="RAMP-B", begin_station="10+00",
           pis=[[1000, 1000], [*pi, 600], end])
        do(s, "draw_alignment", alignment="RAMP-B", layer=CL)
        assert probe.check(base, s).passed is passes, figures


# ------------------------------------------------------ 4. lanes and shoulders


def test_a_shoulder_width_used_as_an_offset_fails(tmp_path):
    probe, base, s = begin("draft-edges-shoulders", tmp_path)
    do(s, "draw_offset", alignment="SR-100", offsets=[-12, 12], layer=EOP)
    do(s, "draw_offset", alignment="SR-100", offsets=[-8, 8], layer=SHLD)
    result = probe.check(base, s)
    assert not result.passed and "edge of shoulder" in result.detail


def test_one_side_only_and_swapped_layers_fail(tmp_path):
    probe, base, s = begin("draft-edges-shoulders", tmp_path / "one-side")
    do(s, "draw_offset", alignment="SR-100", offsets=[12], layer=EOP)
    do(s, "draw_offset", alignment="SR-100", offsets=[20], layer=SHLD)
    result = probe.check(base, s)
    assert not result.passed and "the left edge of pavement" in result.detail
    probe, base, s = begin("draft-edges-shoulders", tmp_path / "swapped")
    do(s, "draw_offset", alignment="SR-100", offsets=[-12, 12], layer=SHLD)
    do(s, "draw_offset", alignment="SR-100", offsets=[-20, 20], layer=EOP)
    result = probe.check(base, s)
    assert not result.passed and f"but not on {EOP}" in result.detail


def test_an_edge_chorded_through_the_curves_fails_and_one_built_by_hand_passes(tmp_path):
    probe, base, s = begin("draft-edges-shoulders", tmp_path / "chords")
    a = s.doc.design.alignments["SR-100"]
    for layer, offset in ((EOP, -12), (EOP, 12), (SHLD, -20), (SHLD, 20)):
        do(s, "draw_polyline", space="model", layer=layer,
           vertices=drafting.along(a, offset, step=200.0))
    result = probe.check(base, s)
    assert not result.passed and "no linework within" in result.detail

    probe, base, s = begin("draft-edges-shoulders", tmp_path / "by-hand")
    for layer, offsets in ((EOP, [-12, 12]), (SHLD, [-20, 20])):
        made = do(s, "draw_offset", alignment="SR-100", offsets=offsets, layer=layer)
        copy_by_hand(s, made["created"], layer)
    assert all(e.anchor is None or e.layer == CL for e in s.doc.model_entities.values())
    result = probe.check(base, s)
    assert result.passed, result.detail


# ------------------------------------------------------------ 5. a turn lane


def test_a_turn_lane_edge_that_runs_on_past_its_stations_fails(tmp_path):
    probe, base, s = begin("draft-turn-lane", tmp_path)
    tasks.get("draft-turn-lane").solve(s)
    assert probe.check(base, s).passed
    do(s, "draw_offset", alignment="SR-100", offsets=[24], layer=EOP)      # the whole length
    result = probe.check(base, s)
    assert not result.passed and "where there should be none" in result.detail


def test_a_turn_lane_missing_its_taper_or_its_end_fails(tmp_path):
    a = None
    for case, skip, message in (("no-taper", "taper", "the 120 ft taper"),
                                ("no-end", "end", "the square end at 36+00")):
        probe, base, s = begin("draft-turn-lane", tmp_path / case)
        a = s.doc.design.alignments["SR-100"]
        p = lambda st, off: a.station_to_xy(st, off)[0]  # noqa: E731
        do(s, "draw_offset", alignment="SR-100", offsets=[24], layer=EOP,
           station_range=["31+20", "36+00"])
        if skip != "taper":
            do(s, "draw_line", space="model", layer=EOP, start=p(3000, 12), end=p(3120, 24))
        if skip != "end":
            do(s, "draw_line", space="model", layer=EOP, start=p(3600, 24), end=p(3600, 12))
        result = probe.check(base, s)
        assert not result.passed and message in result.detail, case


def test_a_turn_lane_drawn_on_the_left_fails(tmp_path):
    probe, base, s = begin("draft-turn-lane", tmp_path)
    a = s.doc.design.alignments["SR-100"]
    p = lambda st, off: a.station_to_xy(st, off)[0]  # noqa: E731
    do(s, "draw_line", space="model", layer=EOP, start=p(3000, -12), end=p(3120, -24))
    do(s, "draw_offset", alignment="SR-100", offsets=[-24], layer=EOP,
       station_range=["31+20", "36+00"])
    do(s, "draw_line", space="model", layer=EOP, start=p(3600, -24), end=p(3600, -12))
    assert not probe.check(base, s).passed


# ----------------------------------------------------------- 6. a cul-de-sac


def cul_de_sac(s, edge_to, bulb="circle"):
    do(s, "create_alignment", name="OAK-CT", begin_station="10+00",
       pis=[[3000, 2000], [3000, 2400]])
    do(s, "draw_alignment", alignment="OAK-CT", layer=CL)
    if bulb == "circle":
        do(s, "draw_circle", space="model", layer=EOP, center=[3000, 2400], radius=45)
    else:  # trimmed: the mouth between the two edges left open
        mouth = math.degrees(math.asin(14 / 45))
        do(s, "draw_arc", space="model", layer=EOP, center=[3000, 2400], radius=45,
           start_angle_deg=270 + mouth, end_angle_deg=270 - mouth + 360)
    do(s, "draw_offset", alignment="OAK-CT", offsets=[-14, 14], layer=EOP,
       station_range=[1000.0, edge_to])


def test_edges_run_through_the_bulb_fail_and_edges_stopped_short_fail(tmp_path):
    probe, base, s = begin("draft-cul-de-sac", tmp_path / "through")
    cul_de_sac(s, 1400.0)
    result = probe.check(base, s)
    assert not result.passed and "inside the bulb" in result.detail
    probe, base, s = begin("draft-cul-de-sac", tmp_path / "short")
    cul_de_sac(s, 1340.0)
    result = probe.check(base, s)
    assert not result.passed and "up to the bulb" in result.detail


def test_a_bulb_trimmed_at_the_mouth_passes_like_a_full_circle(tmp_path):
    for bulb in ("circle", "trimmed"):
        probe, base, s = begin("draft-cul-de-sac", tmp_path / bulb)
        cul_de_sac(s, 1357.23, bulb)
        result = probe.check(base, s)
        assert result.passed, (bulb, result.detail)


# ------------------------------------------------------------- 7. a building


def building(s, corners, as_lines=False, layer="V-BLDG"):
    if layer not in s.doc.layers:
        do(s, "create_layer", name=layer, color="black")
    if as_lines:
        for a, b in zip(corners, corners[1:] + corners[:1]):
            do(s, "draw_line", space="model", layer=layer, start=a, end=b)
    else:
        do(s, "draw_polyline", space="model", layer=layer, vertices=corners, closed=True)


def test_a_building_square_to_the_grid_or_turned_the_wrong_way_fails(tmp_path):
    for case, corners in (
            ("on-axis", [[1500, 1200], [1500, 1260], [1540, 1260], [1540, 1200]]),
            ("turned-left", [[1500, 1200], *traverse([1500, 1200], [(-30, 60)])[1:],
                             *traverse(traverse([1500, 1200], [(-30, 60)])[1], [(60, 40)])[1:],
                             *traverse([1500, 1200], [(60, 40)])[1:]]),
            ("sides-swapped", [[1500, 1200], *traverse([1500, 1200], [(30, 40)])[1:],
                               *traverse(traverse([1500, 1200], [(30, 40)])[1], [(120, 60)])[1:],
                               *traverse([1500, 1200], [(120, 60)])[1:]])):
        probe, base, s = begin("draft-building", tmp_path / case)
        building(s, corners)
        result = probe.check(base, s)
        assert not result.passed and "footprint" in result.detail, case


def test_a_building_of_four_lines_passes_and_the_layer_has_to_exist(tmp_path):
    probe, base, s = begin("draft-building", tmp_path / "lines")
    building(s, drafting._bldg_corners(), as_lines=True)
    assert probe.check(base, s).passed
    probe, base, s = begin("draft-building", tmp_path / "layer")
    building(s, drafting._bldg_corners(), layer=EOP)
    result = probe.check(base, s)
    assert not result.passed and "no layer V-BLDG" in result.detail


# -------------------------------------------------------- 8. the whole roadway


def roadway(s, legs=None, shoulder=16.0, label=True):
    p = traverse([1000.0, 3000.0], legs or drafting.ELM["legs"])
    do(s, "create_alignment", name="ELM-AVE", begin_station="10+00",
       pis=[p[0], [*p[1], 500.0], [*p[2], 700.0], p[3]])
    do(s, "draw_alignment", alignment="ELM-AVE", layer=CL)
    do(s, "draw_offset", alignment="ELM-AVE", offsets=[-11, 11], layer=EOP)
    do(s, "draw_offset", alignment="ELM-AVE", offsets=[-shoulder, shoulder], layer=SHLD)
    if label:
        do(s, "annotate_stationing", alignment="ELM-AVE", space="model", interval=100,
           layer="V-ANNO-TEXT")


def test_the_whole_roadway_fails_on_each_part_left_wrong(tmp_path):
    for case, kwargs, message in (
            ("first-deflection-right", {"legs": [(100, 800), (140, 700), (165, 600)]},
             "ELM-AVE ends at"),
            ("shoulder-as-width", {"shoulder": 5.0}, "edge of shoulder"),
            ("unlabelled", {"label": False}, "stations carry a label")):
        probe, base, s = begin("draft-roadway", tmp_path / case)
        roadway(s, **kwargs)
        result = probe.check(base, s)
        assert not result.passed and message in result.detail, (case, result.detail)
    probe, base, s = begin("draft-roadway", tmp_path / "right")
    roadway(s)
    assert probe.check(base, s).passed


def test_station_labels_typed_by_hand_count_and_labels_in_the_wrong_place_do_not(tmp_path):
    want = drafting.expected_alignment("ELM-AVE", drafting._elm_pis(), "10+00")
    for case, shift, passes in (("beside", 20.0, True), ("far-away", 400.0, False)):
        probe, base, s = begin("draft-roadway", tmp_path / case)
        roadway(s, label=False)
        for st in range(1000, int(want.end_station) + 1, 100):
            at = want.station_to_xy(float(st), -shift)[0]
            do(s, "place_text", space="model", position=at, height=8.0,
               content=f"{st // 100}+00", layer="V-ANNO-TEXT")
        assert probe.check(base, s).passed is passes, case


# ----------------------------------------------------------------- the CLI


def test_setup_and_score_hand_a_drafting_probe_its_own_start_document(tmp_path, capsys):
    from roaddraft.probes.__main__ import main
    out = tmp_path / "probe"
    assert main(["setup", "draft-edges-shoulders", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    doc = out / fixture.CENTERLINE_FILE
    assert doc.is_file() and str(doc) in printed and "--autosave" in printed
    assert main(["score", "draft-edges-shoulders", "--doc", str(doc)]) == 1   # untouched
    s = Session.load(doc, out_dir=out)
    tasks.get("draft-edges-shoulders").solve(s)
    s.query("save_document", {"path": str(doc)})
    assert main(["score", "draft-edges-shoulders", "--doc", str(doc)]) == 0
    assert main(["list", "--tag", "draft"]) == 0
    listed = capsys.readouterr().out
    # the 8 here plus the three tier-2 drafting probes, which carry the tag too
    assert "draft-roadway" in listed and "edge-c102" not in listed and "11 probes" in listed
