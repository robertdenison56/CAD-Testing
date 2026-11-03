"""Pilots 4, 17 and 5 (layout): the probes build, the scripted solutions pass
while the untouched starts fail, and the naive answers named in the notes fail."""
from __future__ import annotations

import copy

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, layout
from roaddraft.tasks.reference import phase_commands

IDS = ["p04-crowded-ppm045", "p04-crowded-ppm050", "p17-twist-ppm160", "p17-twist-fdot916",
       "p05-breaks-fdot904", "p05-breaks-cfl"]
#: the 2026-11-03 expansion, in table order
NEW_P4 = ["p04-crowded-ppm051", "p04-crowded-ppm052", "p04-crowded-ppm155", "p04-crowded-ppm156",
          "p04-crowded-ppm157", "p04-crowded-ppm158", "p04-crowded-ppm160", "p04-crowded-ppm161",
          "p04-crowded-ppm230", "p04-crowded-fdot915", "p04-crowded-ppm047"]
NEW_P17 = ["p17-twist-ppm209", "p17-twist-ppm161", "p17-twist-ppm111", "p17-twist-ppm156",
           "p17-twist-ppm158", "p17-twist-ppm155", "p17-twist-ppm230", "p17-twist-ppm046",
           "p17-twist-fdot915", "p17-twist-fdot923", "p17-twist-wfl04", "p17-twist-wfl21",
           "p17-twist-cflpla"]
NEW_P5 = ["p05-breaks-fdot918", "p05-breaks-fdot904cl2", "p05-breaks-fdot904cl4",
          "p05-breaks-fdot904cl9", "p05-breaks-ppm048", "p05-breaks-cflswppp"]
BY_ID = {p.id: p for p in layout.PROBES}
#: the quick ones (about a second each); the L-7 and SR 50 builds run in the selftest CLI
QUICK = ["p04-crowded-ppm045", "p17-twist-ppm160", "p17-twist-fdot916", "p05-breaks-cfl"]
#: PD-3 and PD-11 take 20 s and 80 s to build (their lines' truths): the selftest CLI runs them
SLOW = {"p04-crowded-ppm156", "p04-crowded-ppm157"}
QUICK_P4 = [p for p in NEW_P4 if p not in SLOW]


def test_probes_build():
    assert [p.id for p in layout.PROBES] == (IDS[:2] + NEW_P4 + IDS[2:4] + NEW_P17 + IDS[4:]
                                              + NEW_P5)
    for p in layout.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "layout" in p.tags


def test_fewest_sheets():
    # each stretch fits two sheets run corner to corner, so three pass and four fail
    assert layout._fewest("p05-breaks-fdot904") == 2
    assert layout._fewest("p05-breaks-cfl") == 2


def _pair(tmp_path, probe):
    doc = fixture.start_document(tmp_path, probe.start)
    return Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path), doc


@pytest.mark.parametrize("pid", QUICK)
def test_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched, _ = _pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


def _letter_defaults(session, sheet_id, sheet_name, names, view_rotation):
    """The labelers' default poses (no clearing), tables placed clear."""
    given = layout._given(session, sheet_name)
    for name in names:
        task = copy.deepcopy(layout._task(sheet_id, name))
        task.brief.deliverable.pop("label_poses", None)
        task.brief.deliverable["view_rotation"] = view_rotation
        for command, params in phase_commands(task, ["stationing", "bearings", "callouts"]):
            common.ok(session.execute(command, params))
    placer = layout._Placer(session, layout._truth(sheet_id, names[0], given), given)
    layout._place_tables(session, placer, sheet_id, names, sheet_name)


def test_crowded_defaults_fail(tmp_path):
    """L-1 lettered at the engine's default poses: two bearings land on the
    sheet's callouts, which D1-08 charges though the content is all right."""
    probe = BY_ID["p04-crowded-ppm045"]
    base, sub, _ = _pair(tmp_path, probe)
    _letter_defaults(sub, "PPM-045", "L-1", ["D13", "TB2", "TB1"], -89.94166666666666)
    result = probe.check(base, sub)
    assert not result.passed and "legibility" in result.detail
    failed = [item for item, ok in result.items if not ok]
    assert failed == ["legibility: nothing over other lettering, under a leader, cut by the "
                      "viewport, off the sheet or upside down"]


def test_twist_ignored_fails(tmp_path):
    """The re-cut FDOT sheet lettered without the viewport's twist: upside down."""
    probe = BY_ID["p17-twist-fdot916"]
    base, sub, _ = _pair(tmp_path, probe)
    _letter_defaults(sub, "FDOT-916-1-Drainage-Network-Plan-Sheet", "1", ["CL1"], 0.0)
    result = probe.check(base, sub)
    assert not result.passed and "wrong side" in result.detail
    # and with the twist, the same defaults pass: the sheet is not crowded
    base2, sub2, _ = _pair(tmp_path / "again", probe)
    _letter_defaults(sub2, "FDOT-916-1-Drainage-Network-Plan-Sheet", "1", ["CL1"], -113.0)
    assert probe.check(base2, sub2).passed


def test_too_many_sheets_fail(tmp_path):
    """The CFL stretch cut into four sheets, each laid out and matched properly."""
    probe = BY_ID["p05-breaks-cfl"]
    base, sub, _ = _pair(tmp_path, probe)
    cfg = layout.P5["p05-breaks-cfl"]
    align = layout._road(sub, cfg["alignment"])
    st = align.stations()
    a, b = st.parse(cfg["a"]), st.parse(cfg["b"])
    ua = layout._usable(cfg["size"], cfg["template"])
    w, h = ua[2] - ua[0] - 0.1, ua[3] - ua[1] - 0.1
    ends = [a + (b - a) * (k + 1) / 4 for k in range(4)]
    common.ok(sub.execute("create_layer", {"name": "ML"}))
    for k, (lo, hi) in enumerate(zip([a] + ends[:-1], ends)):
        twist, _slack = layout._fit(align, lo, hi, w, h, 10.0)
        mid = align.point_at((lo + hi) / 2.0 - float(align.begin_station))
        common.ok(sub.execute("create_sheet", {"name": f"S{k + 1}", "size": cfg["size"],
                                               "title_block_template": cfg["template"]}))
        common.ok(sub.execute("create_viewport", {
            "sheet": f"S{k + 1}", "center_paper": [(ua[0] + ua[2]) / 2, (ua[1] + ua[3]) / 2],
            "width_in": w, "height_in": h, "model_center": mid, "feet_per_inch": 50,
            "rotation_deg": twist}))
    result = probe.check(base, sub)
    assert not result.passed
    assert ("number of sheets", False) in result.items


# ------------------------------------------------- the 2026-11-03 expansion

def _copies(tmp_path, probe, n):
    """The start built once, then ``n`` sessions on copies of it, and its baseline."""
    import shutil
    first = fixture.start_document(tmp_path / "start", probe.start)
    out = []
    for k in range(n):
        shutil.copytree(tmp_path / "start", tmp_path / f"c{k}")
        out.append(Session.load(tmp_path / f"c{k}" / first.name, out_dir=tmp_path / f"c{k}"))
    return Session.load(first, out_dir=tmp_path / "start"), out


def test_new_tables():
    for pid in NEW_P4:
        assert pid in layout.P4
    for pid in NEW_P17:
        assert pid in layout.P17
    for pid in NEW_P5:
        assert pid in layout.P5
    # the existing instances' prompts are unchanged by the shared wording (their ids carry them)
    assert layout._p4_prompt("p04-crowded-ppm045").startswith(
        'Sheet L-1 of this Caltrans layout has lost the alignment data of all 3 of its lines: '
        '"D13", "TB2" and "TB1" (alignments D13, TB2, TB1 of the base file attached as AA01, '
        'reached as AA01:D13 and so on). Letter all of them, in this sheet file, for every line '
        'the way a Caltrans layout shows it:\n')
    assert "at 1\" = 50' on the FDOT 11 x 17" in layout._p5_prompt("p05-breaks-fdot904")


@pytest.mark.parametrize("pid", QUICK_P4 + NEW_P17)
def test_whole_stations_derived(pid):
    """The 500-ft stations the prompt says are lettered whole are the truths' own."""
    cfg = layout.P4.get(pid) or layout.P17[pid]
    names = cfg["names"] if "names" in cfg else [cfg["name"]]
    assert layout._whole(cfg["sheet_id"], names) == cfg["whole"]


@pytest.mark.parametrize("pid", QUICK_P4 + NEW_P17)
def test_new_prompts_leak_nothing(pid):
    """No BC/EC station, bearing or curve value of the truth is in the task text."""
    probe = BY_ID[pid]
    cfg = layout.P4.get(pid) or layout.P17[pid]
    names = cfg["names"] if "names" in cfg else [cfg["name"]]
    for name in names:
        truth = layout._task(cfg["sheet_id"], name).truth
        for label in truth.labels:
            if label["kind"] in ("pc", "pt", "pcc", "prc"):  # '24+05.27 BC'
                assert label["content"].split()[0] not in probe.prompt
            elif label["kind"] == "bearing":  # 'N 71°33'54" E 1240.36'': the bearing, the length
                bearing, length = label["content"].rsplit(" ", 1)
                assert bearing not in probe.prompt and length not in probe.prompt
        for table in truth.curve_tables:
            for row in table["rows"]:
                for cell in row[1:]:
                    assert cell not in probe.prompt


def test_new_fewest_sheets():
    # spare 0 on every new one: only the fewest pass
    want = {"p05-breaks-fdot918": 3, "p05-breaks-fdot904cl2": 4, "p05-breaks-fdot904cl4": 3,
            "p05-breaks-fdot904cl9": 3, "p05-breaks-ppm048": 3, "p05-breaks-cflswppp": 2}
    for pid, n in want.items():
        assert layout._fewest(pid) == n
        assert layout.P5[pid]["spare"] == 0
    assert "spare" not in layout.P5["p05-breaks-fdot904"] and "fpi" not in layout.P5[
        "p05-breaks-cfl"]


@pytest.mark.parametrize("pid", QUICK_P4 + NEW_P17 + NEW_P5)
def test_new_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched, _ = _pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


@pytest.mark.parametrize("pid", QUICK_P4)
def test_new_crowded_defaults_fail(tmp_path, pid):
    """Every new sheet lettered at the labelers' default poses, tables placed clear:
    the content is right, but something lands on something (D1-08 alone fails)."""
    cfg = layout.P4[pid]
    probe = BY_ID[pid]
    base, (sub,) = _copies(tmp_path, probe, 1)
    twist = float(layout._sheet(base, cfg["sheet"]).viewports[0].rotation_deg)
    _letter_defaults(sub, cfg["sheet_id"], cfg["sheet"], list(cfg["names"]), twist)
    result = probe.check(base, sub)
    failed = [item for item, ok in result.items if not ok]
    assert failed == ["legibility: nothing over other lettering, under a leader, cut by the "
                      "viewport, off the sheet or upside down"]


@pytest.mark.parametrize("pid", NEW_P17)
def test_new_twist_naive_fail(tmp_path, pid):
    """Lettered without the viewport's twist: upside down. With the published twist: upside
    down too, except on FDOT-915 (no twist traps both there). With the new twist the
    labelers' defaults pass: the sheets are not crowded, the twist is the test."""
    from roaddraft.tasks import real
    cfg = layout.P17[pid]
    probe = BY_ID[pid]
    src = real.real_sheet(cfg["sheet_id"])
    published = float(next(iter(common.document(src.folder / src.sheet_file).sheets.values()))
                      .viewports[0].rotation_deg)
    base, (none, old, right) = _copies(tmp_path, probe, 3)
    twist = float(layout._sheet(base, cfg["sheet"]).viewports[0].rotation_deg)
    assert abs(twist - published) > 20.0
    _letter_defaults(none, cfg["sheet_id"], cfg["sheet"], [cfg["name"]], 0.0)
    result = probe.check(base, none)
    assert not result.passed and "wrong side" in result.detail
    _letter_defaults(old, cfg["sheet_id"], cfg["sheet"], [cfg["name"]], published)
    result = probe.check(base, old)
    if pid == "p17-twist-fdot915":
        assert result.passed
    else:
        assert not result.passed and "wrong side" in result.detail
    _letter_defaults(right, cfg["sheet_id"], cfg["sheet"], [cfg["name"]], twist)
    assert probe.check(base, right).passed


def _lay(session, cfg, ends, twists):
    """Sheets ending at ``ends``, viewports filling the usable area less 0.1 in at
    ``twists``, each break's match line drawn square and lettered on both sheets."""
    import math
    from roaddraft.core import geometry as geo
    fpi = float(cfg.get("fpi", layout.FPI))
    ua = layout._usable(cfg["size"], cfg["template"])
    align = layout._road(session, cfg["alignment"])
    st = align.stations()
    starts = [st.parse(cfg["a"])] + list(ends[:-1])
    common.ok(session.execute("create_layer", {"name": "ML"}))
    names = []
    for k, (lo, hi, twist) in enumerate(zip(starts, ends, twists)):
        _s, pts, _d = layout._samples(align, lo, hi)
        bb = geo.bbox_of_points([geo.rotate_point(list(p), twist) for p in pts])
        centre = geo.rotate_point([(bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0], -twist)
        names.append(f"S{k + 1}")
        common.ok(session.execute("create_sheet", {"name": names[-1], "size": cfg["size"],
                                                   "title_block_template": cfg["template"]}))
        common.ok(session.execute("create_viewport", {
            "sheet": names[-1], "center_paper": [(ua[0] + ua[2]) / 2, (ua[1] + ua[3]) / 2],
            "width_in": ua[2] - ua[0] - 0.1, "height_in": ua[3] - ua[1] - 0.1,
            "model_center": centre, "feet_per_inch": fpi, "rotation_deg": twist}))
    for k, b in enumerate(ends[:-1]):
        for name in names[k:k + 2]:
            p, q = [common.ok(session.query("station_to_xy", {
                "alignment": cfg["alignment"], "station": st.format(b), "offset": off,
                "sheet": name}))["on_sheet"]["sheet_point"] for off in (-60.0, 60.0)]
            common.ok(session.execute("draw_line", {"space": name, "layer": "ML", "start": p,
                                                    "end": q}))
            common.ok(session.execute("place_text", {
                "space": name, "layer": "ML", "content": f"MATCH LINE STA {st.format(b)}",
                "position": [p[0] + (q[0] - p[0]) * 0.8, p[1] + (q[1] - p[1]) * 0.8],
                "height": 0.1, "halign": "center", "valign": "bottom",
                "rotation_deg": geo.reading_up(math.degrees(math.atan2(q[1] - p[1],
                                                                        q[0] - p[0])))}))


def _north_up_ends(align, a, b, w, h, fpi):
    """The longest north-up sheets in turn, ending on 10-ft stations."""
    import math
    ends, start = [], a

    def fits(lo, hi):
        _s, pts, _d = layout._samples(align, lo, hi)
        return ((pts[:, 0].max() - pts[:, 0].min()) / fpi <= w
                and (pts[:, 1].max() - pts[:, 1].min()) / fpi <= h)
    while not fits(start, b):
        lo, hi = start, b
        while hi - lo > 0.5:
            lo, hi = ((lo + hi) / 2, hi) if fits(start, (lo + hi) / 2) else (lo, (lo + hi) / 2)
        start = math.floor(lo / 10.0) * 10.0
        ends.append(start)
    return ends + [b]


@pytest.mark.parametrize("pid", NEW_P5)
def test_new_breaks_naive_fail(tmp_path, pid):
    """Each laid out properly (match lines square and lettered alike) but cut north-up, cut
    the conventional way (each sheet's chord within 3° of level), or one sheet too many."""
    cfg = layout.P5[pid]
    probe = BY_ID[pid]
    base, (north, level, many) = _copies(tmp_path, probe, 3)
    fpi = float(cfg.get("fpi", layout.FPI))
    ua = layout._usable(cfg["size"], cfg["template"])
    w, h = ua[2] - ua[0] - 0.1, ua[3] - ua[1] - 0.1
    align = layout._road(base, cfg["alignment"])
    st = align.stations()
    a, b = st.parse(cfg["a"]), st.parse(cfg["b"])
    fewest = layout._fewest(pid)
    # north-up: one sheet more than the fewest (and, on Route 65, right to left);
    # on the CFL stretch two north-up sheets do it
    ends = _north_up_ends(align, a, b, w, h, fpi)
    _lay(north, cfg, ends, [0.0] * len(ends))
    result = probe.check(base, north)
    if pid == "p05-breaks-cflswppp":
        assert len(ends) == fewest and result.passed
    else:
        assert len(ends) == fewest + 1 and ("number of sheets", False) in result.items
    if pid == "p05-breaks-ppm048":
        assert ("S1: stationing reads left to right", False) in result.items
    # level: one sheet more than the fewest, except on Route 65's one long curve
    ends = layout._greedy(align, a, b, w, h, round_to=10.0, level=3.0, fpi=fpi)
    twists = [layout._fit(align, lo, hi, w, h, 3.0, fpi)[0]
              for lo, hi in zip([a] + ends[:-1], ends)]
    _lay(level, cfg, ends, twists)
    result = probe.check(base, level)
    if pid == "p05-breaks-ppm048":
        assert len(ends) == fewest and result.passed
    else:
        assert len(ends) == fewest + 1 and not result.passed
        assert [item for item, ok in result.items if not ok] == ["number of sheets"]
    # one too many, cut evenly, each sheet fitted
    n = fewest + 1
    ends = [a + (b - a) * (k + 1) / n for k in range(n)]
    twists = [layout._fit(align, lo, hi, w, h, None, fpi)[0]
              for lo, hi in zip([a] + ends[:-1], ends)]
    _lay(many, cfg, ends, twists)
    result = probe.check(base, many)
    assert [item for item, ok in result.items if not ok] == ["number of sheets"]
