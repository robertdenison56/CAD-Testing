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
        want = mutation.credits.get(check.id, 1.0)
        want = want(base) if callable(want) else want
        assert check.credit == pytest.approx(want, abs=1e-6), (check.id, check.to_dict())
        codes = {f.code for f in check.findings}
        assert codes == mutation.codes.get(check.id, set()), (check.id, check.to_dict())
    if mutation.hard_fail:
        assert report.effective_score == 0.0
    else:
        assert report.effective_score == report.rubric_score
