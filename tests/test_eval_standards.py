"""roaddraft.eval.standards: a vague run's lost points split into drafting standards not
applied, the work done wrong, hard fails and early ends, paired with an explicit run."""
import json

import pytest

from roaddraft.eval import standards
from roaddraft.eval.__main__ import main


def _check(cid, weight, credit, codes=(), hard=False):
    return {"id": cid, "name": cid, "weight": weight, "credit": credit, "points": weight * credit,
            "hard_fail": hard, "hard_fail_triggered": False, "in_scope": True,
            "findings": [{"code": c} for c in codes]}


def _episode(run_dir, task_id, level, checks, termination="submit", hard_failed=False, task_type="stationing"):
    total = sum(c["weight"] for c in checks)
    rubric = 100.0 * sum(c["weight"] * c["credit"] for c in checks) / total
    effective = 0.0 if hard_failed else rubric
    eps = run_dir / "episodes"
    eps.mkdir(parents=True, exist_ok=True)
    recs = [{"type": "header", "task_id": task_id, "task_type": task_type, "level": level, "model": "m"},
            {"type": "verify", "verifier_version": "d1-verify-v8", "rubric_score": rubric,
             "effective_score": effective, "hard_failed": hard_failed, "checks": checks},
            {"type": "end", "termination": termination, "effective_score": effective,
             "rubric_score": rubric, "hard_failed": hard_failed}]
    (eps / f"{task_id}.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\n")


def test_layer_zero_is_a_standard_and_the_parts_add_up(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    # D1-09 half lost to layer 0, D1-04 lost to a wrong value
    _episode(run, "T1", "vague", [_check("D1-02", 10, 1.0), _check("D1-09", 10, 0.5, ["wrong_layer"]),
                                  _check("D1-04", 20, 0.5, ["wrong_value"])])
    s = standards.analyse(run)
    assert s["tasks"] == 1 and s["paired_tasks"] == 0
    assert sum(s["by_kind"].values()) == pytest.approx(s["lost_per_task"])
    assert s["by_kind"]["standard"] == pytest.approx(12.5)    # 10 x 0.5 of 40
    assert s["by_kind"]["work"] == pytest.approx(25.0)        # 20 x 0.5 of 40
    std = [r for r in s["lines"] if r["kind"] == "standard"]
    assert std[0]["standard"].startswith("nothing drafted on layer 0")


def test_paired_split_recovered_when_told_and_lost_at_both(tmp_path):
    vague = tmp_path / "e3-d1-test-m-single-vague-v3"
    explicit = tmp_path / "e3-d1-test-m-single-v3"
    _episode(vague, "T1", "vague", [_check("D1-02", 10, 0.0, ["missing"]), _check("D1-08", 10, 0.5, ["overlap"])])
    _episode(explicit, "T1", "explicit", [_check("D1-02", 10, 1.0), _check("D1-08", 10, 0.5, ["overlap"])])
    assert standards.find_explicit(vague) == explicit
    s = standards.analyse(vague, standards.find_explicit(vague))
    assert s["paired_tasks"] == 1
    lines = {r["standard"]: r for r in s["lines"]}
    ticks = lines["left off: station ticks every 100 ft"]
    assert ticks["recovered_per_task"] == pytest.approx(50.0) and ticks["lost_at_both_per_task"] == pytest.approx(0.0)
    over = lines["lettering clear of linework and other lettering"]
    assert over["recovered_per_task"] == pytest.approx(0.0) and over["lost_at_both_per_task"] == pytest.approx(25.0)


def test_hard_fail_and_early_end_are_not_standards(tmp_path):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-03", 10, 0.8, ["wrong_value"], hard=True)], hard_failed=True)
    _episode(run, "T2", "vague", [_check("D1-02", 10, 0.0, ["missing"])], termination="budget")
    s = standards.analyse(run)
    assert s["by_kind"]["hard_fail"] == pytest.approx(40.0)    # T1's rubric 80, over two tasks
    assert s["by_kind"]["ended_early"] == pytest.approx(50.0)
    assert s["by_kind"].get("standard", 0.0) == pytest.approx(0.0)
    assert sum(s["by_kind"].values()) == pytest.approx(s["lost_per_task"])


def test_cli_writes_the_report(tmp_path, capsys):
    run = tmp_path / "e3-d1-test-m-single-vague-v3"
    _episode(run, "T1", "vague", [_check("D1-11", 1, 0.0, ["missing"]), _check("D1-02", 9, 1.0)])
    assert main(["standards", str(run)]) == 0
    md = (run / "report" / "standards.md").read_text()
    assert "left off: the north arrow" in md and "No explicit run" in md
    assert json.loads((run / "report" / "standards.json").read_text())["tasks"] == 1
    assert "points a task lost" in capsys.readouterr().out
