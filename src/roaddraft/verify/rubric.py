"""Credit to points: the spec's weighted check list run through ``CHECKS``.

Weights and the hard-fail flags live in the spec (``spec_hash`` covers
them); the formulas live in ``checks`` (``VERIFIER_VERSION`` covers them).
A task's scope (the truth groups it asks for) puts some checks in play;
the rest are reported out of scope at no credit, and ``VerifyReport``
renormalises the in-scope weights to 100.  A value finding under an in-scope
hard-fail check, or a tampered design, makes the effective score 0.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from roaddraft.tasks.types import checks_in_scope
from roaddraft.verify.checks import CHECKS, Analysis
from roaddraft.verify.report import CheckResult


def _spec_checks(spec: dict) -> List[dict]:
    unknown = [c["id"] for c in spec["checks"] if c["id"] not in CHECKS]
    if unknown:
        raise ValueError(f"the verifier has no formula for spec check(s) {unknown}; "
                         f"it knows {sorted(CHECKS)}")
    return spec["checks"]


def score_checks(spec: dict, analysis: Optional[Analysis], scope: Optional[Iterable[str]] = None,
                 check_groups: Optional[dict] = None) -> List[CheckResult]:
    """One ``CheckResult`` per spec check.  Checks outside ``scope`` are
    marked so and skipped; with no analysis (a tampered design) every check
    is skipped at zero credit.  ``check_groups`` overrides the group each
    check draws from (``tasks.types.CHECK_GROUPS``)."""
    checks = _spec_checks(spec)
    in_scope = set(checks_in_scope(scope, [c["id"] for c in checks], check_groups))
    out = []
    for c in checks:
        result = CheckResult(id=c["id"], name=c["name"], weight=c["weight"], credit=0.0,
                             hard_fail=bool(c["hard_fail"]), in_scope=c["id"] in in_scope)
        if analysis is None or not result.in_scope:
            result.skipped = True
        else:
            credit, findings = CHECKS[c["id"]](analysis)
            result.credit = round(min(1.0, max(0.0, float(credit))), 6)
            result.findings = findings
        out.append(result)
    return out


__all__ = ["score_checks"]
