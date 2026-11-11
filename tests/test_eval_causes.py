"""roaddraft.eval.causes: every lost point of a run put down to one cause (a drafting
standard not known, tool use, reasoning, budget), read from the episode files."""
import json

import pytest

from roaddraft.eval import causes
from roaddraft.eval.__main__ import main


def _check(cid, weight, credit, findings=(), triggered=False):
    return {"id": cid, "name": cid, "weight": weight, "credit": credit, "points": weight * credit,
            "hard_fail": triggered, "hard_fail_triggered": triggered, "in_scope": True,
            "findings": [f if isinstance(f, dict) else {"code": f} for f in findings]}


def _call(name, ok=True, params=None, created=()):
    res = {"ok": ok, "name": name}
    if ok:
        res.update(created=list(created), modified=[])
    else:
        res["error"] = {"type": "command_failed", "message": "no"}
    return {"name": name, "params": params or {}}, res


def _episode(run_dir, task_id, level, checks, calls=(), termination="submit", tripped=None,
             hard_failed=False, baseline_ids=(), harness="e3-v3", tools="t1", probe=None, passed=None,
             items=()):
    eps = run_dir / "episodes"
    eps.mkdir(parents=True, exist_ok=True)
    if probe:
        rubric = 100.0 * sum(1 for _, ok in items if ok) / max(1, len(items))
        effective = 100.0 if passed else 0.0
        verify = {"type": "verify", "kind": "probe", "probe": probe, "passed": passed,
                  "items": [list(i) for i in items], "rubric_score": rubric, "effective_score": effective,
                  "hard_failed": not passed, "checks": [_check("PROBE", 100, rubric / 100, triggered=not passed)]}
    else:
        total = sum(c["weight"] for c in checks)
        rubric = 100.0 * sum(c["weight"] * c["credit"] for c in checks) / total
        effective = 0.0 if hard_failed else rubric
        verify = {"type": "verify", "verifier_version": "d1-verify-v8", "rubric_score": rubric,
                  "effective_score": effective, "hard_failed": hard_failed, "checks": checks}
    if not calls and not probe:
        calls = [_call("draw_alignment", created=["LN-0"])]   # a D1 episode that drew something
    turns = []
    for n, (call, res) in enumerate(calls):
        turns.append({"type": "turn", "n": n, "assistant": {"tool_calls": [call]}, "results": [res]})
    recs = [{"type": "header", "task_id": task_id, "task_type": "pilot-x" if probe else "stationing",
             "level": level, "model": "m", "harness_version": harness, "tools_sha256": tools, "probe": probe},
            *turns,
            {"type": "journal", "baseline": {"model": {"entities": [{"id": i} for i in baseline_ids]}},
             "entries": []},
            verify,
            {"type": "end", "termination": termination, "budget_tripped": tripped,
             "effective_score": effective, "rubric_score": rubric, "hard_failed": verify["hard_failed"]}]
    (eps / f"{task_id}.{level}.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def _cause(s, cause):
    return s["by_cause"].get(cause, 0.0)


def test_each_finding_kind_gets_its_cause_and_the_parts_add_up(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    calls = [_call("annotate_stationing", created=["LN-1"]),
             _call("place_text", params={"text": "12+00"}, created=["TX-1"]),
             _call("place_label", params={"anchor": "T-1"}, created=["TX-2"])]
    _episode(run, "T1", "vague", [
        _check("D1-02", 10, 0.0, ["missing"]),                                          # standard: left off
        _check("D1-07", 10, 0.0, [{"code": "unanchored", "entity_ids": ["TX-1"]}]),     # tool use
        _check("D1-05", 10, 0.0, [{"code": "wrong_value", "entity_ids": ["TX-2"]}]),    # reasoning
        _check("D1-03", 10, 1.0)], calls=calls)
    s = causes.analyse(run)
    assert s["paired_tasks"] == 0
    assert _cause(s, "standard") == pytest.approx(25.0)
    assert _cause(s, "tool_use") == pytest.approx(25.0)
    assert _cause(s, "reasoning") == pytest.approx(25.0)
    assert sum(s["by_cause"].values()) == pytest.approx(s["lost_per_task"])
    subs = {r["sub"]: r for r in s["lines"]}
    assert "left off: station ticks every 100 ft" in subs
    assert "the right command with the wrong input" in subs
    assert s["standard_confirmed"] == {"unconfirmed": pytest.approx(25.0)}


def test_an_element_left_off_after_its_command_failed_is_tool_use(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"]), _check("D1-01", 10, 1.0)],
             calls=[_call("draw_alignment", created=["LN-0"]), _call("annotate_stationing", ok=False),
                    _call("get_document_state", ok=False)])
    s = causes.analyse(run)
    assert _cause(s, "tool_use") == pytest.approx(50.0) and _cause(s, "standard") == 0.0
    assert s["lines"][0]["sub"].startswith("left off after annotate_stationing failed")


def test_a_failed_command_that_later_worked_is_not_a_tool_fault(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"]), _check("D1-01", 10, 1.0)],
             calls=[_call("annotate_stationing", ok=False), _call("annotate_stationing", created=["LN-1"])])
    assert _cause(causes.analyse(run), "standard") == pytest.approx(50.0)


def test_findings_on_the_start_documents_own_entities_are_not_the_models(tmp_path):
    run = tmp_path / "e3-d1-real-m-single-vague-v3"
    _episode(run, "T1", "vague", [
        _check("D1-07", 10, 0.5, [{"code": "unanchored", "entity_ids": ["TX-001"]},
                                  {"code": "unanchored", "entity_ids": ["TX-9"]}]),
        _check("D1-05", 10, 1.0)],
        calls=[_call("place_text", created=["TX-9"])], baseline_ids=["TX-001"])
    s = causes.analyse(run)
    assert _cause(s, "tool_use") == pytest.approx(25.0)   # all of D1-07's loss, on TX-9
    assert s["lines"][0]["tasks"] == 1


def test_pairing_keeps_what_was_recovered_when_told_and_moves_the_rest_to_reasoning(tmp_path):
    vague = tmp_path / "e3-d1-test-m-single-vague-v3"
    explicit = tmp_path / "e3-d1-test-m-single-v3"
    _episode(vague, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"]), _check("D1-08", 10, 0.5, ["overlap"])])
    _episode(explicit, "T1", "explicit", [_check("D1-02", 10, 1.0), _check("D1-08", 10, 0.5, ["overlap"])])
    assert causes.find_explicit(vague) == explicit
    s = causes.analyse(vague, explicit)
    assert s["paired_tasks"] == 1
    assert _cause(s, "standard") == pytest.approx(50.0)     # the ticks, earned back when told
    assert _cause(s, "reasoning") == pytest.approx(25.0)    # the overlap, lost when told too
    assert s["standard_confirmed"] == {"confirmed": pytest.approx(50.0)}
    assert any(r["sub"].startswith("lost even when told: ") for r in s["lines"])


def test_no_pair_across_a_harness_or_tool_surface_change(tmp_path):
    vague = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(vague, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"])])
    _episode(tmp_path / "e3-d1-test-m-single-v3", "T1", "explicit", [_check("D1-02", 10, 1.0)], tools="t0")
    _episode(tmp_path / "e3-d1-test-m-single", "T1", "explicit", [_check("D1-02", 10, 1.0)], harness="e3-v2")
    assert causes.find_explicit(vague) is None


def test_a_hard_fail_takes_the_cause_of_its_trigger(tmp_path):
    run = tmp_path / "e3-d1-test-hard-m-single-vague-v3"
    calls = [_call("annotate_stationing", params={"layer": "ALIGN"}, created=["LN-7"]),
             _call("place_curve_table", created=["TB-1"])]
    _episode(run, "T1", "vague", [
        _check("D1-01", 10, 1.0, [{"code": "extra_linework", "entity_ids": ["LN-7"]}], triggered=True),
        _check("D1-06", 10, 0.5, [{"code": "wrong_value", "entity_ids": ["TB-1"]}])],
        calls=calls, hard_failed=True)
    s = causes.analyse(run)
    assert s["lost_per_task"] == pytest.approx(100.0)
    assert _cause(s, "standard") == pytest.approx(75.0)     # the rubric's 75, zeroed by ticks on the alignment layer
    assert _cause(s, "reasoning") == pytest.approx(25.0)    # the curve table's own loss
    assert "hard fail: annotation drafted on the alignment layer" in {r["sub"] for r in s["lines"]}


def test_a_value_wrong_only_by_its_escapes_is_tool_use(tmp_path):
    run = tmp_path / "e3-d1-real-m-single-vague-v3"
    calls = [_call("place_callout", params={"content": "A\\nB"}, created=["CO-1"]),
             _call("place_callout", params={"content": "C"}, created=["CO-2"])]
    _episode(run, "T1", "vague", [
        _check("D1-16", 10, 0.0, [{"code": "wrong_value", "entity_ids": ["CO-1"], "actual": "A\\nB", "expected": "A\nB"},
                                  {"code": "wrong_value", "entity_ids": ["CO-2"], "actual": "C", "expected": "D"}]),
        _check("D1-08", 10, 1.0)], calls=calls)
    subs = {r["sub"]: r["points_per_task"] for r in causes.analyse(run)["lines"]}
    assert subs["text escaped wrong in the call (a literal \\n or \\\")"] == pytest.approx(25.0)
    assert subs["a callout reading the wrong note"] == pytest.approx(25.0)


def test_a_curve_table_listing_another_sheets_curves_is_a_standard(tmp_path):
    run = tmp_path / "e3-d1-test-hard-m-single-vague-v3"
    _episode(run, "T1", "vague", [
        _check("D1-06", 10, 0.5, [{"code": "wrong_value", "entity_ids": ["TB-1"], "note": causes.CURVE_SCOPE_NOTE}]),
        _check("D1-02", 10, 1.0)], calls=[_call("place_curve_table", created=["TB-1"])])
    s = causes.analyse(run)
    assert _cause(s, "standard") == pytest.approx(25.0)
    assert s["lines"][0]["sub"] == "a sheet's curve table lists only the curves that sheet shows"


def test_nothing_drawn_is_reasoning_unless_every_drawing_call_failed(tmp_path):
    run = tmp_path / "e3-d1-real-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-01", 10, 0.0, ["missing"])], calls=[_call("list_alignments")])
    _episode(run, "T2", "vague", [_check("D1-01", 10, 0.0, ["missing"])],
             calls=[_call("draw_alignment", ok=False)])
    s = causes.analyse(run)
    assert _cause(s, "reasoning") == pytest.approx(50.0) and _cause(s, "tool_use") == pytest.approx(50.0)
    assert "submitted without drawing anything" in {r["sub"] for r in s["lines"]}


def test_early_ends_budget_and_the_fault_budget_is_tool_use(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"])], termination="budget", tripped="steps")
    _episode(run, "T2", "vague", [_check("D1-02", 10, 0.0, ["missing"])], termination="budget", tripped="faults")
    s = causes.analyse(run)
    assert _cause(s, "budget") == pytest.approx(50.0) and _cause(s, "tool_use") == pytest.approx(50.0)


def test_pilots_take_one_cause_each(tmp_path):
    vague = tmp_path / "e3-hard-pilots-m-single-vague-v3"
    explicit = tmp_path / "e3-hard-pilots-m-single-v3"
    items = [("drawn", True), ("bearing N 10 E", False)]
    _episode(vague, "PR-a-1", "vague", [], probe="a", passed=False, items=items)                    # standard
    _episode(vague, "PR-b-1", "vague", [], probe="b", passed=False, items=items)                    # reasoning
    _episode(vague, "PR-c-1", "vague", [], probe="c", passed=False, items=items,
             calls=[_call("draw_traverse", ok=False)])                                               # tool use
    _episode(vague, "PR-d-1", "vague", [], probe="d", passed=True, items=[("drawn", True)])
    for p, ok in (("a", True), ("b", False), ("c", True), ("d", True)):
        _episode(explicit, f"PR-{p}-2", "explicit", [], probe=p, passed=ok, items=items)
    s = causes.analyse(vague, causes.find_explicit(vague))
    assert s["pilots"] and s["paired_tasks"] == 4
    assert [_cause(s, c) for c in ("standard", "reasoning", "tool_use")] == [pytest.approx(25.0)] * 3
    assert s["failed_items"] == {"pilot-x": {"bearing N 10 E": 3}}
    alone = causes.analyse(vague)
    assert _cause(alone, "unresolved") == pytest.approx(50.0)


def test_cli_writes_each_report_and_the_table(tmp_path, capsys):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-11", 1, 0.0, ["missing"]), _check("D1-02", 9, 1.0)])
    table = tmp_path / "CAUSES.md"
    assert main(["causes", str(run), "--table", str(table)]) == 0
    md = (run / "report" / "causes.md").read_text()
    assert "left off: the north arrow" in md and "unconfirmed" in md
    assert json.loads((run / "report" / "causes.json").read_text())["tasks"] == 1
    assert "## `d1-test`" in table.read_text()
    assert "standard 10.0" in capsys.readouterr().out
