"""Pilot 10, typical sections: the probes build, the truth geometry is what the
description says, and each scripted solution passes while the untouched start
and the naive answers fail."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import typical

IDS = [p.id for p in typical.PROBES]


def test_probes_build():
    assert IDS == ["p10-typical-cfl01", "p10-typical-wfl07"]
    for p in typical.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START


def test_truth_geometry():
    cfl = typical.cfl_truth()
    breaks = dict(cfl["breaks"])
    assert breaks["left shoulder edge"][1] == pytest.approx(1186.42 - 0.24)
    assert breaks["right hinge"] == pytest.approx([15.0, 1186.42 - 0.24 - 0.75])
    assert breaks["ditch bottom"] == pytest.approx([-19.0, 1186.42 - 1.99])
    wfl = typical.wfl_truth()
    hinge = dict(wfl["breaks"])["right hinge"]
    # the 1:2 foreslope meets the subgrade 2.0 ft under the 2% finished grade
    assert hinge[0] == pytest.approx(19.1667, abs=1e-4)
    assert hinge[1] == pytest.approx(6241.36 - 2.0 - 0.02 * hinge[0])
    for truth in (cfl, wfl):
        (_l, left), (_r, right) = truth["catches"]
        # catch points lie on the ground line, cut on the left, fill on the right
        assert left[1] > truth["pg"] > right[1]


def _pair(tmp_path, probe):
    doc = fixture.start_document(tmp_path, probe.start)
    return Session.load(doc, out_dir=tmp_path), Session.load(doc, out_dir=tmp_path)


def test_start_is_stripped(tmp_path):
    for probe, spec in zip(typical.PROBES, (typical.CFL, typical.WFL)):
        base, _ = _pair(tmp_path / probe.id, probe)
        sheet = base.doc.sheet_by_ref(spec["sheet"])
        texts = {e.content for e in sheet.entities.values() if hasattr(e, "content")}
        assert spec["keep_text"] <= texts                 # the section's title stays
        assert not sheet.viewports
        assert [e.layer for e in base.doc.model_entities.values()] == [typical.EG_LAYER]


@pytest.mark.parametrize("probe", typical.PROBES, ids=IDS)
def test_selftest(tmp_path, probe):
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched = _pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


def test_flat_section_fails(tmp_path):
    """The crown skipped: shoulders drawn level with the centreline."""
    probe = typical.PROBES[0]
    base, s = _pair(tmp_path, probe)
    t = typical.cfl_truth()
    flat = [[p[0], t["pg"] if abs(p[0]) <= 12 else p[1]] for p in t["fg"]]
    s.execute("draw_polyline", {"space": "model", "vertices": flat})
    result = probe.check(base, s)
    assert not result.passed
    assert "shoulder edge" in result.detail
