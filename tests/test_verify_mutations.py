"""The mutation catalog (eval plan section 3.6): one change to a reference
drawing moves exactly the checks it should, by exactly the expected amount,
and hard-fails exactly when it should."""
from __future__ import annotations

import pytest

from tests.verify_mutations import MUTATIONS, Base


def test_catalog_has_at_least_25_mutations():
    assert len(MUTATIONS) >= 25
    assert len({m.name for m in MUTATIONS}) == len(MUTATIONS)


@pytest.mark.parametrize("mutation", MUTATIONS, ids=[m.name for m in MUTATIONS])
def test_mutation_moves_exactly_the_expected_checks(mutation):
    base = Base(**mutation.base)
    before = base.verify()
    assert before.effective_score == 100.0 and not before.all_findings()
    mutation.apply(base)
    report = base.verify()
    assert report.hard_failed is mutation.hard_fail
    if mutation.tampered:
        assert not report.design_fingerprint_ok
        assert [f.code for f in report.findings] == ["design_tampered"]
        assert report.rubric_score == 0.0 and report.effective_score == 0.0
        assert all(c.skipped and c.credit == 0.0 and not c.findings for c in report.checks)
        return
    assert report.design_fingerprint_ok and not report.findings
    for check in report.checks:
        if not check.in_scope:  # plan prep checks: not this task's business
            assert check.credit == 0.0 and not check.findings and check.skipped
            continue
        want = mutation.credits.get(check.id, 1.0)
        want = want(base) if callable(want) else want
        assert check.credit == pytest.approx(want, abs=1e-6), (check.id, check.to_dict())
        codes = {f.code for f in check.findings}
        assert codes == mutation.codes.get(check.id, set()), (check.id, check.to_dict())
    if mutation.hard_fail:
        assert report.effective_score == 0.0
    else:
        assert report.effective_score == report.rubric_score


def _rebearing(base: Base, n: int, along: float) -> None:
    """Swap T-n's bearing for one the labeler anchors at a station ``along`` ft into
    the tangent, the side, offset and height the reference lettered it with."""
    from roaddraft.design.stations import format_station
    old = base.label(f"T-{n}", "bearing")
    align = base.doc.design.alignments[base.A]
    t = align.tangents()[n - 1]
    station = float(align.begin_station) + t.start_dist + along
    base.ex("delete_entities", {"ids": [old.id]})
    base.ex("place_label", {"space": "model", "alignment": base.A, "anchor": format_station(station),
                            "kind": "bearing", "side": old.anchor["side"],
                            "label_offset": old.anchor["label_offset"], "height": old.height,
                            "layer": old.layer})


def test_a_bearing_anchored_at_its_tangent_s_middle_station_is_that_tangent_s_bearing():
    # d1-verify-v5 (PE decision 2026-10-18): the labelers take a station for a bearing, and
    # the task asks for each tangent's bearing at its middle; until v5 only T-n matched
    base = Base(seed=1, curves=3)
    align = base.doc.design.alignments[base.A]
    for n, t in enumerate(align.tangents(), 1):
        _rebearing(base, n, t.length / 2.0)
    assert all(e.anchor["ref"] != "T-1" for e in base.labels("bearing"))
    report = base.verify()
    assert report.effective_score == 100.0 and not report.all_findings()


def test_a_station_anchored_bearing_off_the_middle_is_present_but_misplaced():
    base = Base(seed=1, curves=3)
    _rebearing(base, 1, 25.0)
    checks = {c.id: c for c in base.verify().checks}
    assert checks["D1-05"].credit == 1.0 and not checks["D1-05"].findings
    assert checks["D1-07"].credit < 1.0 and checks["D1-07"].findings
