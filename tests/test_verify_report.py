"""The report contract (verify.report): its shape, the closed finding-code
set, the hard-fail rule, and the agent's view, which never shows a value
the agent should have computed itself."""
from __future__ import annotations

import json

import pytest

from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.types import GROUPS
from roaddraft.verify import FINDING_CODES, VALUE_CODES, VERIFIER_VERSION, Finding, verify
from roaddraft.verify.checks import CHECKS
from roaddraft.verify.rubric import score_checks
from tests.verify_mutations import BASE, MUTATIONS, Base


def test_finding_codes_are_a_closed_set():
    assert set(VALUE_CODES) <= set(FINDING_CODES)
    with pytest.raises(ValueError):
        Finding("looks_off")


def test_report_shape():
    b = Base(**BASE)
    d = verify(b.doc, b.truth).to_dict()
    assert list(d) == ["verifier_version", "spec_version", "spec_hash", "task_id",
                       "prompt_level", "scope", "design_fingerprint_ok", "rubric_score",
                       "hard_failed", "effective_score", "scope_weight", "findings", "checks",
                       "counts"]
    assert d["scope"] == list(GROUPS) and d["scope_weight"] == 100
    assert d["verifier_version"] == VERIFIER_VERSION and d["spec_hash"] == spec_hash()
    assert d["spec_version"] == DRAFTING_SPEC_V1["version"] and d["task_id"] == b.task.task_id
    assert [c["id"] for c in d["checks"]] == [c["id"] for c in DRAFTING_SPEC_V1["checks"]]
    assert sum(c["weight"] for c in d["checks"]) == 100
    for c in d["checks"]:
        assert set(c) == {"id", "name", "weight", "credit", "points", "hard_fail",
                          "hard_fail_triggered", "in_scope", "findings"}
        assert c["in_scope"] is True
    assert json.loads(json.dumps(d)) == d
    with_timing = verify(b.doc, b.truth).to_dict(include_timing=True)
    assert with_timing["timing_ms"] > 0


def test_every_spec_check_has_a_formula_and_unknown_ones_are_refused():
    assert [c["id"] for c in DRAFTING_SPEC_V1["checks"]] == sorted(CHECKS)
    spec = json.loads(json.dumps(DRAFTING_SPEC_V1))
    spec["checks"].append({"id": "D1-99", "name": "x", "weight": 1, "hard_fail": False})
    with pytest.raises(ValueError, match="D1-99"):
        score_checks(spec, None)


def test_a_value_finding_hard_fails_only_under_a_hard_fail_check():
    b = Base(**BASE)
    r = verify(b.doc, b.truth)
    soft = r.check("D1-10")
    soft.findings.append(Finding("wrong_value"))
    assert not soft.hard_fail_triggered and not r.hard_failed
    hard = r.check("D1-03")
    hard.findings.append(Finding("missing"))
    assert not r.hard_failed
    hard.findings.append(Finding("wrong_value"))
    assert r.hard_failed and r.effective_score == 0.0 and r.rubric_score == 100.0


@pytest.mark.parametrize("mutation", MUTATIONS, ids=[m.name for m in MUTATIONS])
def test_agent_view_never_shows_an_expected_value(mutation):
    b = Base(**mutation.base)
    mutation.apply(b)
    r = verify(b.doc, b.truth)
    view = r.agent_view()
    text = json.dumps(view, ensure_ascii=False)
    assert "expected" not in text and "actual" not in text and "points" not in text
    assert view["hard_fail"] is r.hard_failed
    for c in view["checks"]:
        assert c["status"] in ("pass", "partial", "fail") and len(c["findings"]) <= 5
    public = {s["name"] for s in b.truth.sheets}  # the prompt names the sheets
    for f in r.all_findings():
        # a station label's anchor ref is its own wording: naming the anchor is not a leak
        if (isinstance(f.expected, str) and len(f.expected) > 3
                and f.expected != (f.anchor or {}).get("ref") and f.expected not in public):
            assert f.expected not in text, (f.code, f.expected)
