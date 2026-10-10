"""The verifier's report: findings, per-check results, and the scored whole.

Findings are the unit of everything downstream (eval plan section 3.1): the
harness's ``run_check`` shows them to the agent stripped of ``expected`` and
``actual`` (``agent_view``), the report generator rolls their codes up into
the failure taxonomy, and the mutation tests assert on them.  ``note`` is a
fixed phrase that says what is wrong without saying what is right, so it
survives the stripping.

A task's scope decides which checks are in play; the rubric score is the
weighted mean credit of those, scaled to 100, so a one-piece task and a
whole sheet both score on the same 0-100.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: The closed set of finding codes.
FINDING_CODES = (
    "missing", "wrong_value", "unanchored", "anchor_inconsistent", "misplaced", "not_visible",
    "duplicate", "overlap", "off_sheet", "geometry_mismatch", "extra_linework", "wrong_layer",
    "wrong_height", "wrong_layer_props", "missing_field", "wrong_field", "design_tampered",
    "sheet_missing", "viewport_scale", "not_fitted",
)

#: Codes that say wrong work is shown on the sheet.  One of these under a
#: check the spec marks ``hard_fail`` fails the whole sheet; missing work only
#: costs credit.
VALUE_CODES = ("wrong_value", "geometry_mismatch", "extra_linework", "design_tampered")


@dataclass
class Finding:
    code: str
    anchor: Optional[dict] = None
    entity_ids: List[str] = field(default_factory=list)
    expected: Any = None
    actual: Any = None
    note: Optional[str] = None

    def __post_init__(self):
        if self.code not in FINDING_CODES:
            raise ValueError(f"unknown finding code {self.code!r}")

    @property
    def is_value(self) -> bool:
        return self.code in VALUE_CODES

    def to_dict(self, strip: bool = False) -> dict:
        d: Dict[str, Any] = {"code": self.code}
        if self.anchor is not None:
            d["anchor"] = dict(self.anchor)
        if self.entity_ids:
            d["entity_ids"] = list(self.entity_ids)
        if not strip:
            if self.expected is not None:
                d["expected"] = self.expected
            if self.actual is not None:
                d["actual"] = self.actual
        if self.note:
            d["note"] = self.note
        return d


@dataclass
class CheckResult:
    id: str
    name: str
    weight: float
    credit: float
    hard_fail: bool  # the spec's flag for this check
    findings: List[Finding] = field(default_factory=list)
    skipped: bool = False
    in_scope: bool = True

    @property
    def points(self) -> float:
        """Spec weight x credit (before the scope's renormalisation)."""
        return round(self.weight * self.credit, 4)

    @property
    def hard_fail_triggered(self) -> bool:
        return self.in_scope and self.hard_fail and any(f.is_value for f in self.findings)

    @property
    def status(self) -> str:
        if not self.in_scope:
            return "out_of_scope"
        if self.hard_fail_triggered or self.credit <= 0.0:
            return "fail"
        return "pass" if self.credit >= 1.0 else "partial"

    def to_dict(self) -> dict:
        d = {"id": self.id, "name": self.name, "weight": self.weight, "credit": self.credit,
             "points": self.points, "hard_fail": self.hard_fail,
             "hard_fail_triggered": self.hard_fail_triggered, "in_scope": self.in_scope,
             "findings": [f.to_dict() for f in self.findings]}
        if self.skipped:
            d["skipped"] = True
        return d


@dataclass
class VerifyReport:
    verifier_version: str
    spec_version: str
    spec_hash: str
    task_id: str
    prompt_level: str
    design_fingerprint_ok: bool
    checks: List[CheckResult]
    counts: Dict[str, int]
    scope: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)  # document-level (design_tampered)
    audit: Optional[dict] = None
    timing_ms: Optional[float] = None  # kept out of to_dict(): reports are byte-stable

    def in_scope(self) -> List[CheckResult]:
        return [c for c in self.checks if c.in_scope]

    @property
    def scope_weight(self) -> float:
        """The spec weight of the checks in play."""
        return float(sum(c.weight for c in self.in_scope()))

    @property
    def rubric_score(self) -> float:
        """Weighted mean credit over the in-scope checks, on 0-100."""
        total = self.scope_weight
        if total <= 0:
            return 0.0
        return round(100.0 * sum(c.weight * c.credit for c in self.in_scope()) / total, 4)

    @property
    def hard_failed(self) -> bool:
        return (any(c.hard_fail_triggered for c in self.checks)
                or any(f.is_value for f in self.findings))

    @property
    def effective_score(self) -> float:
        return 0.0 if self.hard_failed else self.rubric_score

    def check(self, check_id: str) -> CheckResult:
        for c in self.checks:
            if c.id == check_id:
                return c
        raise KeyError(check_id)

    def all_findings(self) -> List[Finding]:
        return list(self.findings) + [f for c in self.checks for f in c.findings]

    def to_dict(self, include_timing: bool = False) -> dict:
        d = {"verifier_version": self.verifier_version, "spec_version": self.spec_version,
             "spec_hash": self.spec_hash, "task_id": self.task_id,
             "prompt_level": self.prompt_level, "scope": list(self.scope),
             "design_fingerprint_ok": self.design_fingerprint_ok,
             "rubric_score": self.rubric_score, "hard_failed": self.hard_failed,
             "effective_score": self.effective_score, "scope_weight": self.scope_weight,
             "findings": [f.to_dict() for f in self.findings],
             "checks": [c.to_dict() for c in self.checks],
             "counts": dict(self.counts)}
        if self.audit is not None:
            d["audit"] = self.audit
        if include_timing and self.timing_ms is not None:
            d["timing_ms"] = self.timing_ms
        return d

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False, ensure_ascii=False)

    def agent_view(self, max_findings: int = 5) -> dict:
        """What ``run_check`` shows an agent: per in-scope check its status and
        up to ``max_findings`` findings, never an expected or actual value and
        never points (eval plan section 3.5 item 5)."""
        out = {"hard_fail": self.hard_failed,
               "checks": [{"id": c.id, "status": c.status,
                           "findings": [f.to_dict(strip=True)
                                        for f in c.findings[:max_findings]],
                           **({"more_findings": len(c.findings) - max_findings}
                              if len(c.findings) > max_findings else {})}
                          for c in self.in_scope()]}
        if self.findings:
            out["findings"] = [f.to_dict(strip=True) for f in self.findings[:max_findings]]
        return out


__all__ = ["FINDING_CODES", "VALUE_CODES", "Finding", "CheckResult", "VerifyReport"]
