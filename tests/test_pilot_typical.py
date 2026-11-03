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
    assert IDS == ["p10-typical-cfl01", "p10-typical-wfl07", "p10-typical-fdot9132",
                   "p10-typical-wfl04", "p10-typical-wfl05"]
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


# ------------------------------------------------- the sections added Nov 2026

NEW = {spec["id"]: spec for spec in typical.NEW_SPECS}
NEW_PROBES = [p for p in typical.PROBES if p.id in NEW]


def test_new_truths():
    fdot = typical.fdot_truth()
    breaks = dict(fdot["breaks"])
    pg = typical.FDOT["pg"]
    # the profile grade points are the inside lane edges, the median ditch 2.48 below
    assert breaks["left profile grade point"] == pytest.approx([-20.0, pg])
    assert breaks["median ditch"] == pytest.approx([0.0, pg - 0.48 - 2.0])
    assert breaks["right outside shoulder edge"] == pytest.approx([54.0, pg - 0.48 - 0.60])
    assert breaks["left ditch bottom, back edge"] == pytest.approx([-80.0, pg - 1.08 - 3.5])
    jeff = typical.jeff_truth()
    assert (jeff["fill_run"], jeff["cut_run"]) == (3.0, 2.0)
    (_l, left), (_r, right) = jeff["catches"]
    hinge, ditch = dict(jeff["breaks"])["left hinge"], dict(jeff["breaks"])["right ditch bottom"]
    assert 10.0 < hinge[1] - left[1] <= 10.0 + 1.0
    assert 5.0 < right[1] - ditch[1] <= 15.0
    ada = typical.ada_truth()
    pts = dict(ada["breaks"])
    pg = typical.ADA["pg"]
    assert pts["left lane edge (high side)"] == pytest.approx([-12.0, pg + 0.72])
    assert pts["left shoulder edge"] == pytest.approx([-14.0, pg + 0.68])
    assert pts["right shoulder edge (low side)"] == pytest.approx([16.0, pg - 0.96])
    assert not any(abs(p[0]) < 1e-9 for p in pts.values())       # no crown to vertex
    for truth in (fdot, jeff, ada):
        for _n, c in truth["catches"]:
            # catch points lie on the ground line
            assert typical._fg_at(truth["ground"], c[0]) == pytest.approx(c[1], abs=1e-6)


def test_slope_tables_pick_one_slope():
    """Each other row of the JEFF tables gives a height outside its own band."""
    jeff = typical.jeff_truth()
    hinge, ditch = dict(jeff["breaks"])["left hinge"], dict(jeff["breaks"])["right ditch bottom"]
    heights = {run: hinge[1] - typical._catch(hinge, -1, -1.0 / run, jeff["ground"])[1]
               for run in (6.0, 4.0, 3.0)}
    assert heights[6.0] > 5.0 and heights[4.0] > 10.0 and heights[3.0] > 10.0
    heights = {run: typical._catch(ditch, 1, 1.0 / run, jeff["ground"])[1] - ditch[1]
               for run in (3.0, 2.0, 1.5)}
    assert heights[3.0] > 5.0 and 5.0 < heights[2.0] <= 15.0 and heights[1.5] <= 15.0


def test_new_starts_are_stripped(tmp_path):
    for probe in NEW_PROBES:
        spec = NEW[probe.id]
        base, _ = _pair(tmp_path / probe.id, probe)
        sheet = base.doc.sheet_by_ref(spec["sheet"])
        texts = {e.content for e in sheet.entities.values() if hasattr(e, "content")}
        assert spec["keep_text"] <= texts
        assert not sheet.viewports
        assert [e.layer for e in base.doc.model_entities.values()] == [typical.EG_LAYER]
        # nothing of the old section is left in the strip boxes
        left = [e for e in sheet.entities.values() if e.bbox(base.doc)
                and any(typical._inside(e.bbox(base.doc), box) for box in spec["strip"])
                and not any(typical._inside(e.bbox(base.doc), box) for box in spec["keep"])]
        assert not left, probe.id


@pytest.mark.parametrize("probe", NEW_PROBES, ids=[p.id for p in NEW_PROBES])
def test_new_selftest(tmp_path, probe):
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    base, untouched = _pair(tmp_path / "start", probe)
    assert not probe.check(base, untouched).passed


def _naive(tmp_path, spec, edit, **overrides):
    """The reference drafting of an edited truth, checked against the real one."""
    probe = next(p for p in typical.PROBES if p.id == spec["id"])
    base, s = _pair(tmp_path, probe)
    t = spec["truth"]()
    edit(t)
    typical.solve_drawn(dict(spec, truth=lambda: t, **overrides), s)
    return probe.check(base, s)


def test_fdot_naive_answers_fail(tmp_path):
    pg = typical.FDOT["pg"]

    def on_centreline(t):           # the profile grade put on the construction centreline
        t["fg"] = [[x, y + 2.48] if abs(x) < 60 else [x, y] for x, y in t["fg"]]

    result = _naive(tmp_path / "cl", typical.FDOT, on_centreline)
    assert not result.passed
    assert not [ok for name, ok in result.items if name.startswith("median ditch")][0]

    def crowned(t):                 # each roadway crowned at the middle of its lanes
        fg = [[x, pg - 0.24] if abs(abs(x) - 20.0) < 1e-9 or abs(abs(x) - 44.0) < 1e-9
              else [x, y] for x, y in t["fg"]]
        t["fg"] = sorted(fg + [[-32.0, pg], [32.0, pg]])

    assert not _naive(tmp_path / "crown", typical.FDOT, crowned).passed

    def no_flat_bottom(t):          # the 1:4 back slope straight from the front slope's foot
        toe = dict(t["breaks"])["left ditch bottom, front slope foot"]
        catch = typical._catch(toe, -1, 0.25, t["ground"])
        t["fg"] = [catch] + [p for p in t["fg"][2:]]

    assert not _naive(tmp_path / "flat", typical.FDOT, no_flat_bottom).passed
    result = _naive(tmp_path / "ten", typical.FDOT, lambda t: None, scale=10.0)
    assert not result.passed
    assert dict(result.items)["viewport at 1\" = 20' showing the section, clear of the sheet's notes"] is False


def test_jeff_naive_answers_fail(tmp_path):
    def first_rows(t):              # 1:6 fill and 1:3 cut, the tables' first rows
        b = dict(t["breaks"])
        t["fg"][0] = typical._catch(b["left hinge"], -1, -1.0 / 6.0, t["ground"])
        t["fg"][-1] = typical._catch(b["right ditch bottom"], 1, 1.0 / 3.0, t["ground"])

    result = _naive(tmp_path / "first", typical.JEFF, first_rows)
    assert not result.passed and "catch point" in result.detail

    def at_the_hinge(t):            # the heights read off the ground at the hinge (7.0 ft:
        b = dict(t["breaks"])       # 1:4) and over the ditch (3.5 ft: 1:3), not at the catch
        g = t["ground"]
        assert b["left hinge"][1] - typical._fg_at(g, -18.0) == pytest.approx(7.0, abs=0.01)
        assert typical._fg_at(g, 22.0) - b["right ditch bottom"][1] == pytest.approx(3.5, abs=0.01)
        t["fg"][0] = typical._catch(b["left hinge"], -1, -1.0 / 4.0, g)
        t["fg"][-1] = typical._catch(b["right ditch bottom"], 1, 1.0 / 3.0, g)

    assert not _naive(tmp_path / "hinge", typical.JEFF, at_the_hinge).passed

    def mirrored(t):                # cut left, fill right
        t["fg"] = [[-x, y] for x, y in reversed(t["fg"])]

    assert not _naive(tmp_path / "mirror", typical.JEFF, mirrored).passed


def test_ada_naive_answers_fail(tmp_path):
    pg = typical.ADA["pg"]

    def crowned(t):                 # the normal 2% crown
        t["fg"] = [[x, pg - 0.02 * abs(x)] if abs(x) <= 16.0 else [x, y] for x, y in t["fg"]]
        t["fg"].insert(3, [0.0, pg])

    assert not _naive(tmp_path / "crown", typical.ADA, crowned).passed

    def inside_edge(t):             # rotated about the inside (right) edge of the traveled way
        edge = pg - 0.02 * 14.0
        t["fg"] = [[x, edge + 0.06 * (14.0 - x)] if -14.0 <= x <= 16.0 else [x, y]
                   for x, y in t["fg"]]

    assert not _naive(tmp_path / "edge", typical.ADA, inside_edge).passed

    def no_widening(t):             # the right lane left at 12 ft
        t["fg"] = [[14.0, pg - 0.06 * 14.0] if abs(x - 16.0) < 1e-9 else [x, y] for x, y in t["fg"]]

    result = _naive(tmp_path / "wide", typical.ADA, no_widening)
    assert not result.passed
    assert not [ok for name, ok in result.items if name.startswith("right shoulder edge")][0]

    def high_side_on_the_six(t):    # the high-side shoulder left on the 6%
        t["fg"] = [[-14.0, pg + 0.06 * 14.0] if abs(x + 14.0) < 1e-9 else [x, y]
                   for x, y in t["fg"]]

    assert not _naive(tmp_path / "six", typical.ADA, high_side_on_the_six).passed
