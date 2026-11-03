"""Pilot 14 (qa_review): the probes build, the scripted reviews pass while the
untouched starts fail, the prepared sheets agree with their designs, and the
naive reviews named in the notes fail."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, qa_review as qa

IDS = ["p14-qa-review-ppm045a", "p14-qa-review-ppm045b", "p14-qa-review-wfl19",
       "p14-qa-review-fdot916a", "p14-qa-review-fdot916b", "p14-qa-review-ppm048a",
       "p14-qa-review-ppm048b", "p14-qa-review-wfl19b", "p14-qa-review-cflpla"]
#: the instances added on 2026-11-03, and their plants
NEW_PLANTS = {"p14-qa-review-fdot916b": qa.FDOT916_PLANTS, "p14-qa-review-ppm048b": qa.PPM048_PLANTS,
              "p14-qa-review-wfl19b": qa.WFL19B_PLANTS, "p14-qa-review-cflpla": qa.CFL_PLANTS}
BY_ID = {p.id: p for p in qa.PROBES}


def test_probes_build():
    assert [p.id for p in qa.PROBES] == IDS
    for p in qa.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "QA-REVIEW" in p.prompt and "NO ERRORS FOUND" in p.prompt
        # the prompt never says how many errors there are, or what kind
        assert not any(w in p.prompt.lower() for w in ("bearing", "north arrow", "upside", "six", "three"))


@pytest.mark.parametrize("pid", IDS)
def test_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", probe.start)
    untouched = probe.check(Session.load(doc), Session.load(doc))
    assert not untouched.passed


def test_prepared_sheets_agree_with_their_designs(tmp_path):
    # L-1: the lettering is the rebuilt design's, to the hundredth
    qa.prepare_ppm045(tmp_path / "l1")
    s = common.load(tmp_path / "l1" / qa.PPM_FILE)
    sheet = next(iter(s.doc.sheets.values()))
    aa = common.load(tmp_path / "l1" / qa.PPM_AA01)
    v = qa.ppm045_values(aa)
    assert aa.doc.model_entities["TX-036"].content == v["TB1 T-1 bearing"] == 'N 03°57’26" W'
    assert sheet.entities["TX-005"].content == v["TB1 C-1 L"]
    assert sheet.entities["TX-127"].content == f'"TB1" {v["TB1 C-1 PT"]} EC'
    tb2 = common.ok(aa.query("get_design_data", {"kind": "curves", "alignment": "TB2"}))["rows"][0]
    t1 = common.ok(aa.query("get_design_data", {"kind": "tangents", "alignment": "TB2"}))["rows"][0]
    assert tb2["bearing_out"] == t1["bearing"]          # no kink at the EC any more
    # D.10: the design is the whole curve its curve data letters
    qa.prepare_wfl19(tmp_path / "d10")
    d = common.load(tmp_path / "d10" / qa.WFL_FILE)
    cv = common.ok(d.query("get_design_data", {"kind": "curves", "alignment": "ALI:MAIN 01"}))["rows"][0]
    assert (cv["pi_station_text"], cv["pt_station_text"], f"{cv['tangent']:.2f}", f"{cv['length']:.2f}") == \
        ("149+35.83", "152+96.54", "554.92", "915.64")


def _callout(session, target, text):
    sheet = next(iter(session.doc.sheets.values()))
    if qa.QA_LAYER not in session.doc.layers:
        common.ok(session.execute("create_layer", {"name": qa.QA_LAYER}))
    common.ok(session.execute("place_callout", {"space": sheet.name, "layer": qa.QA_LAYER, "target": target,
                                                "position": [target[0] + 1.0, target[1] + 0.8],
                                                "content": text}))


def _scored(tmp_path, pid, act):
    probe = BY_ID[pid]
    doc = fixture.start_document(tmp_path, probe.start)
    s = Session.load(doc, out_dir=tmp_path)
    act(s)
    common.save(s, doc)
    return probe.check(Session.load(doc), Session.load(doc, out_dir=tmp_path))


def _targets(session, plants):
    out = []
    for p in plants:
        texts, segs = qa.plant_marks(session, p)
        out.append(texts[0].center() if texts else segs[len(segs) // 2].mid())
    return out


def test_naive_reviews_fail(tmp_path):
    # the control: one query on the unlabelled match line sinks it
    r = _scored(tmp_path / "a", "p14-qa-review-ppm045a",
                lambda s: _callout(s, [29.75, 9.0], "MATCH LINE HAS NO SHEET NUMBER"))
    assert not r.passed
    # six errors: fixing one instead of marking it fails; missing the arrow fails
    def fix(s):
        qa._modify_text(s, "TX-005", lambda t: "163.42’")
    assert not _scored(tmp_path / "b", "p14-qa-review-ppm045b", fix).passed

    def five(s):
        for p, t in zip(qa.PPM_PLANTS, _targets(s, qa.PPM_PLANTS)):
            if "north" not in p["item"]:
                _callout(s, t, "QA " + p["item"])
    r = _scored(tmp_path / "c", "p14-qa-review-ppm045b", five)
    assert not r.passed and "north arrow" in r.detail
    # all six plus one query passes; plus two queries fails
    def six_plus(n):
        def go(s):
            for p, t in zip(qa.PPM_PLANTS, _targets(s, qa.PPM_PLANTS)):
                _callout(s, t, "QA " + p["item"])
            for k in range(n):
                _callout(s, [26.0 + k, 16.0], "QA QUERY")
        return go
    assert _scored(tmp_path / "d", "p14-qa-review-ppm045b", six_plus(1)).passed
    assert not _scored(tmp_path / "e", "p14-qa-review-ppm045b", six_plus(2)).passed
    # D.10: calling it clean fails
    def clean(s):
        sheet = next(iter(s.doc.sheets.values()))
        common.ok(s.execute("create_layer", {"name": qa.QA_LAYER}))
        common.ok(s.execute("place_text", {"space": sheet.name, "layer": qa.QA_LAYER, "position": [3, 2],
                                           "height": 0.1, "content": "NO ERRORS FOUND"}))
    assert not _scored(tmp_path / "f", "p14-qa-review-wfl19", clean).passed


# ------------------------------------------------- the instances added on 2026-11-03


def test_new_prepared_sheets_agree_with_their_designs(tmp_path):
    # FDOT sheet 1: the PC from the design, the fourteen tags numbered as published
    s = common.load(qa.prepare_fdot916(tmp_path / "f"))
    sheet = next(iter(s.doc.sheets.values()))
    pc = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "ALI:CL1"}))["rows"][0]
    assert sheet.entities["TX-057"].content == f"PC STA. +{pc['pc_station_text'][-5:]}" == "PC STA. +70.74"
    tags = sorted(e.content for e in sheet.entities.values() if getattr(e, "content", "")[:2] in ("S-", "P-")
                  and len(e.content) == 5)
    assert {"S-101", "S-110", "P-101", "P-107"} <= set(tags) and len(tags) >= 21
    # CFL: the lower curve's data is the design's
    s = common.load(qa.prepare_cflpla(tmp_path / "c"))
    cv = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "ALI:CL1"}))["rows"][0]
    assert (cv["pc_station_text"], cv["pi_station_text"], cv["pt_station_text"], cv["delta_dms"],
            f"{cv['radius']:.2f}", f"{cv['tangent']:.2f}", f"{cv['length']:.2f}") == \
        ("34+00.32", "36+49.08", "38+84.48", "32°26'40\"", "855.00", "248.76", "484.15")
    nxt = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "ALI:CL1"}))["rows"][1]
    assert nxt["pc_station_text"] == "41+32.03"
    # the redraft's drawn centerline still lies on the rebuilt design
    ali = common.load(tmp_path / "c" / qa.CFL_ALI)
    for e in ali.doc.model_entities.values():
        if e.layer == "P_ALIGN":
            for p in qa._points(e)[:2] if not hasattr(e, "radius") else []:
                assert abs(common.ok(ali.query("xy_to_station", {"alignment": "CL1", "point": p}))["offset"]) < 0.05
    # L-4: the table, the bearings, lengths, EC and the POT/POC stations are the design's
    s = common.load(qa.prepare_ppm048(tmp_path / "l4"))
    sheet = next(iter(s.doc.sheets.values()))
    rows = sheet.entities[qa.PPM048_TABLE].rows
    in4 = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "AA01:IN4"}))["rows"][0]
    assert rows[1][1:] == [f"{in4['radius']:.2f}'", "74°50'50\"", f"{in4['tangent']:.2f}'", f"{in4['length']:.2f}'"]
    assert in4["pt_station_text"] == "681+58.69"
    t = common.ok(s.query("get_design_data", {"kind": "tangents", "alignment": "AA01:IND1"}))["rows"][0]
    assert f"{t['length']:.2f}" == "4833.49"
    aa = common.load(tmp_path / "l4" / qa.PPM048_AA01)
    for station, other, want in ((67843.61, "IND1", "55+90.29"), (68340.13, "IND1", "59+72.49")):
        name = "D13" if station == 67843.61 else "IN4"
        xy = common.ok(aa.query("station_to_xy", {"alignment": name, "station": station}))["point"]
        assert common.ok(aa.query("xy_to_station", {"alignment": other, "point": xy}))["station_text"] == want


@pytest.mark.parametrize("pid", sorted(NEW_PLANTS))
def test_new_plants_lie_apart(tmp_path, pid):
    """No QA mark can claim two plants: every two lie over 1.5 in apart on paper."""
    probe = BY_ID[pid]
    doc = fixture.start_document(tmp_path, probe.start)
    s = Session.load(doc, out_dir=tmp_path)
    shapes = [qa.plant_marks(s, p) for p in NEW_PLANTS[pid]]
    pts = [[t.center() for t in texts] + [q for g in segs for q in (g.a, g.b, g.mid())]
           for texts, segs in shapes]
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            gap = min(qa._distance(shapes[j], p) for p in pts[i])
            assert gap > 1.5, (pid, NEW_PLANTS[pid][i]["item"], NEW_PLANTS[pid][j]["item"], gap)


def _mark_plants(plants, skip=(), queries=()):
    def go(s):
        for p, t in zip(plants, _targets(s, plants)):
            if not any(k in p["item"] for k in skip):
                _callout(s, t, "QA " + p["item"])
        for q in queries:
            _callout(s, q, "QA QUERY")
    return go


def test_new_controls_punish_false_alarms(tmp_path):
    # FDOT 1: a query on a pipe's LF (the drawn line between the inlet symbols is shorter)
    assert not _scored(tmp_path / "a", "p14-qa-review-fdot916a",
                       lambda s: _callout(s, [5.6, 4.85], "87 LF? DRAWN ABOUT 80 FT")).passed
    # FDOT 1: the north arrow, which points down the paper, called wrong
    assert not _scored(tmp_path / "b", "p14-qa-review-fdot916a",
                       lambda s: _callout(s, [13.3, 7.9], "NORTH ARROW POINTS DOWN")).passed
    # L-4: stationing of lines the base file does not carry
    assert not _scored(tmp_path / "c", "p14-qa-review-ppm048a",
                       lambda s: _callout(s, [8.5, 8.4], "+96.28 OF WHAT LINE?")).passed

    def clean(s):
        sheet = next(iter(s.doc.sheets.values()))
        common.ok(s.execute("create_layer", {"name": qa.QA_LAYER}))
        common.ok(s.execute("place_text", {"space": sheet.name, "layer": qa.QA_LAYER, "position": [3, 2],
                                           "height": 0.1, "content": "NO ERRORS FOUND"}))
    assert _scored(tmp_path / "d", "p14-qa-review-ppm048a", clean).passed
    assert not _scored(tmp_path / "e", "p14-qa-review-ppm048b", clean).passed


def test_new_naive_reviews_fail(tmp_path):
    # FDOT 1: the lettered values alone, missing the turned arrow and the missing tick
    r = _scored(tmp_path / "a", "p14-qa-review-fdot916b", _mark_plants(qa.FDOT916_PLANTS, skip=("north", "tick")))
    done = dict(r.items)
    assert not r.passed and not done["the north arrow (turned 180°)"] and not done["the 707+00 tick (missing)"]
    assert sum(not d for d in done.values()) == 2
    # all six plus one query passes; plus two fails
    assert _scored(tmp_path / "b", "p14-qa-review-fdot916b",
                   _mark_plants(qa.FDOT916_PLANTS, queries=[[3.0, 9.5]])).passed
    assert not _scored(tmp_path / "c", "p14-qa-review-fdot916b",
                       _mark_plants(qa.FDOT916_PLANTS, queries=[[3.0, 9.5], [15.0, 9.5]])).passed
    # CFL: checked against the design only, the upper plan's two missed
    r = _scored(tmp_path / "d", "p14-qa-review-cflpla", _mark_plants(qa.CFL_PLANTS, skip=("upper",)))
    done = dict(r.items)
    assert not r.passed and not done["the upper curve's direction (LT for RT)"]
    assert not done["the upper tangent's bearing (quadrant flipped)"]
    assert _scored(tmp_path / "e", "p14-qa-review-cflpla", _mark_plants(qa.CFL_PLANTS)).passed
    # L-4: the table queried as a whole, at its title, not at the cell
    def table_title(s):
        _mark_plants(qa.PPM048_PLANTS, skip=("table",))(s)
        _callout(s, [5.25, 3.75], "QA CURVE TABLE")
    r = _scored(tmp_path / "f", "p14-qa-review-ppm048b", table_title)
    assert not r.passed and not dict(r.items)["curve 36's L in the curve table"]
    # L-4: every plant marked, and the IND1 bearing also fixed in the design file: a change
    def fix_too(s):
        _mark_plants(qa.PPM048_PLANTS)(s)
        aa = common.load(tmp_path / "g" / qa.PPM048_AA01)
        qa._modify_text(aa, "TX-058", lambda t: t.replace('"W', '"E'))
        common.save(aa, tmp_path / "g" / qa.PPM048_AA01)
    r = _scored(tmp_path / "g", "p14-qa-review-ppm048b", fix_too)
    assert not r.passed and "base file" in r.detail
    # D.10 b: the curve data and the PT checked, the stationing not
    r = _scored(tmp_path / "h", "p14-qa-review-wfl19b",
                _mark_plants(qa.WFL19B_PLANTS, skip=("tick", "upside", "154")))
    assert not r.passed
    # D.10 b: the (correct) arrow queried as well as all five: one false alarm, allowed
    assert _scored(tmp_path / "i", "p14-qa-review-wfl19b",
                   _mark_plants(qa.WFL19B_PLANTS, queries=[[3.74, 9.6]])).passed


def test_first_instances_keep_their_model_space_blind_spot(tmp_path):
    """The first three instances' checks compare no model space (see
    ``qa._STRIP_KEYS``); kept as they were, so their grades do not move."""
    def fix_in_base(s):
        for p, t in zip(qa.PPM_PLANTS, _targets(s, qa.PPM_PLANTS)):
            _callout(s, t, "QA " + p["item"])
        aa = common.load(tmp_path / qa.PPM_AA01)
        qa._modify_text(aa, "TX-036", lambda t: t[:-1] + "W")
        common.save(aa, tmp_path / qa.PPM_AA01)
    assert _scored(tmp_path, "p14-qa-review-ppm045b", fix_in_base).passed
