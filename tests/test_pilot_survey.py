"""Pilot 3, survey traps: the probes build, their truth is what the notes say,
and each scripted solution passes while the untouched start and the naive
answer fail."""
from __future__ import annotations

import math

import pytest

from roaddraft.api.session import Session
from roaddraft.design import cogo
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, survey

IDS = [survey.MIS_ID, survey.GG_ID, survey.IF_ID]


def test_probes_build():
    assert [p.id for p in survey.PROBES] == IDS
    for p in survey.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START


def test_misclosure_truth():
    t = survey.misclosure_truth()
    assert t["misclosure"] == pytest.approx(0.2747, abs=1e-3)
    assert t["precision"] == pytest.approx(6534, abs=5)
    assert t["area"] == pytest.approx(132346.1, abs=0.5)
    # the balance holds the POB and moves later corners further
    moves = [math.dist(a, b) for a, b in zip(t["raw"], t["corners"])]
    assert moves[0] == 0.0 and all(0.02 < m < 0.25 for m in moves[1:])


def test_unit_truths():
    ties = survey.grid_ground_truth()
    occupied = survey._control(survey.GG_OCCUPIED)
    for (_n, _d, xy), (_n2, _d2, _a, ground) in zip(ties, survey.GG_TIES):
        # skipping the factor would be off by more than the tolerance
        assert ground * (1 - survey.GG_FACTOR) > 3 * survey.GG_TOL_FT
        assert math.dist(occupied, xy) == pytest.approx(ground * survey.GG_FACTOR, abs=1e-6)
    for (_n, _d, xy), row in zip(survey.intl_feet_truth(), survey.IF_POINTS):
        assert abs(xy[0] - row[4]) > 1.0          # the given value is not the answer


def _session_pair(tmp_path, probe):
    doc = fixture.start_document(tmp_path, probe.start)
    return Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path), doc


@pytest.mark.parametrize("probe", survey.PROBES, ids=IDS)
def test_selftest(tmp_path, probe):
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched, _ = _session_pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


def test_naive_answers_fail(tmp_path):
    probes = {p.id: p for p in survey.PROBES}
    # the deed as written, closed with a closing course
    base, s, doc = _session_pair(tmp_path / "a", probes[survey.MIS_ID])
    raw = survey.misclosure_truth()["raw"][:-1]
    s.execute("create_layer", {"name": survey.MIS_LAYER})
    s.execute("draw_polyline", {"space": "model", "layer": survey.MIS_LAYER,
                                "vertices": raw, "closed": True})
    assert not probes[survey.MIS_ID].check(base, s).passed
    # ground distances plotted on the grid drawing
    base, s, doc = _session_pair(tmp_path / "b", probes[survey.GG_ID])
    occ, bs = survey._control(survey.GG_OCCUPIED), survey._control(survey.GG_BACKSIGHT)
    az_bs, _ = cogo.inverse(occ, bs)
    s.execute("create_points", {"points": [
        {"number": n, "point": cogo.forward(occ, az_bs + cogo.parse_dms(a), g)}
        for n, _d, a, g in survey.GG_TIES]})
    assert not probes[survey.GG_ID].check(base, s).passed
    # international feet typed in as US survey feet
    base, s, doc = _session_pair(tmp_path / "c", probes[survey.IF_ID])
    s.execute("create_points", {"points": [
        {"number": n, "northing": north, "easting": east}
        for n, _d, _u, north, east in survey.IF_POINTS]})
    assert not probes[survey.IF_ID].check(base, s).passed
