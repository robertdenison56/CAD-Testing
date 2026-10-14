"""Budgets trip the way the plan says, and are recorded."""
from __future__ import annotations

from roaddraft.eval.budget import Budgets, BudgetState


def test_single_mode_has_no_run_check_budget():
    assert Budgets().for_mode("single").run_checks == 0
    assert Budgets().for_mode("self_correct").run_checks == 3
    assert Budgets(run_checks=5).for_mode("vision").run_checks == 5


def test_steps_trip():
    b = Budgets(steps=3)
    s = BudgetState()
    for _ in range(3):
        assert s.tripped(b) is None
        s.note_call(True)
    assert s.tripped(b) == "steps"
    assert s.remaining(b)["steps"] == 0


def test_consecutive_faults_trip_and_a_success_resets_them():
    b = Budgets(faults=3)
    s = BudgetState()
    s.note_call(False); s.note_call(False)
    assert s.tripped(b) is None and s.consecutive_faults == 2
    s.note_call(True)
    assert s.consecutive_faults == 0 and s.faults == 2
    for _ in range(3):
        s.note_call(False)
    assert s.tripped(b) == "faults" and s.faults == 5


def test_output_tokens_and_wall_clock_trip():
    b = Budgets(output_tokens=100, wall_clock_s=10)
    s = BudgetState(started=1000.0)
    s.note_usage({"output_tokens": 60})
    assert s.tripped(b, now=1001.0) is None
    s.note_usage({"output_tokens": 40})
    assert s.tripped(b, now=1001.0) == "output_tokens"
    s2 = BudgetState(started=1000.0)
    assert s2.tripped(b, now=1009.0) is None
    assert s2.tripped(b, now=1010.0) == "wall_clock"


def test_zero_limits_mean_no_limit_for_tokens_and_clock():
    b = Budgets(output_tokens=0, wall_clock_s=0)
    s = BudgetState(started=0.0)
    s.note_usage({"output_tokens": 10 ** 9})
    assert s.tripped(b, now=10 ** 9) is None


def test_records_are_plain_dicts():
    assert Budgets().to_dict()["steps"] == 150
    d = BudgetState().to_dict()
    assert set(d) == {"steps", "run_check_uses", "faults", "output_tokens", "elapsed_ms"}
