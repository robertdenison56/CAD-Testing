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
BY_ID = {p.id: p for p in layout.PROBES}
#: the quick ones (about a second each); the L-7 and SR 50 builds run in the selftest CLI
QUICK = ["p04-crowded-ppm045", "p17-twist-ppm160", "p17-twist-fdot916", "p05-breaks-cfl"]


def test_probes_build():
    assert [p.id for p in layout.PROBES] == IDS
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
