"""The episode loop and the four agents (eval plan sections 4.1, 4.3).

The oracle through the loop scores 100 on all 50 d1-dev tasks: the harness
loses no points.  That number is this file's permanent test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import Agent, AgentRefusal, NullAgent, OracleAgent, ReplayAgent, ScriptedAgent, Submit, ToolCall
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import Episode, EpisodeConfig, run_episode
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.generator import generate_task

DEV = tasksets.load("d1-dev")["tasks"]


def _task(i: int = 0):
    return tasksets.task_from_entry(DEV[i])


def test_oracle_through_the_loop_scores_100_on_every_d1_dev_task():
    for entry in DEV:
        task = tasksets.task_from_entry(entry)
        for level in ("explicit", "vague"):
            r = run_episode(task, OracleAgent(), EpisodeConfig(level=level))
            assert r.termination == "submit", (entry["task_id"], level, r.error)
            assert r.effective_score == 100.0 and not r.report.hard_failed, (entry["task_id"], level)
            assert r.faults == 0 and r.steps > 0


def test_null_submits_at_once_and_scores_0():
    r = run_episode(_task(0), NullAgent())
    assert r.termination == "submit" and r.steps == 0 and r.turns == 1
    assert r.effective_score == 0.0 and r.report.rubric_score == 0.0


def test_scripted_drafter_scores_about_65_on_the_whole_sheet_and_is_stable():
    task = generate_task(42)  # plan-sheet, one sheet
    first = run_episode(task, ScriptedAgent())
    again = run_episode(task, ScriptedAgent())
    assert 55.0 <= first.effective_score <= 75.0, first.effective_score
    assert first.effective_score == again.effective_score
    assert first.report.to_json() == again.report.to_json()
    done = {c.id for c in first.report.in_scope() if c.credit == 1.0}
    undone = {c.id for c in first.report.in_scope() if c.credit == 0.0}
    assert {"D1-01", "D1-02"} <= done and {"D1-05", "D1-06", "D1-10"} <= undone


def test_a_hidden_tool_is_refused_as_a_step_with_a_teaching_error():
    class Sneaky(Agent):
        name = "sneaky"
        def __init__(self):
            self.turn = 0
        def act(self, obs):
            self.turn += 1
            if self.turn == 1:
                return [ToolCall("save_document", {"path": "x.rdoc.json"}),
                        ToolCall("list_layers", {})]
            assert obs["results"][0]["ok"] is False
            assert obs["results"][0]["error"]["type"] == "unknown_command"
            assert "not a tool of this episode" in obs["results"][0]["error"]["message"]
            assert obs["results"][1]["ok"] is True
            return Submit()
    r = run_episode(_task(0), Sneaky())
    assert r.termination == "submit" and r.steps == 2 and r.faults == 1


def test_parallel_calls_run_in_order_and_all_results_come_back():
    class TwoAtOnce(Agent):
        name = "two"
        def __init__(self):
            self.turn = 0
        def act(self, obs):
            self.turn += 1
            if self.turn == 1:
                return [ToolCall("create_layer", {"name": "A"}),
                        ToolCall("create_layer", {"name": "A"}),   # a fault: exists
                        ToolCall("create_layer", {"name": "B"})]
            res = obs["results"]
            assert [r["ok"] for r in res] == [True, False, True]
            assert obs["state"] and obs["budget"]["steps"] == Budgets.steps - 3
            return Submit()
    r = run_episode(_task(0), TwoAtOnce())
    assert r.steps == 3 and r.faults == 1 and r.termination == "submit"


def test_step_budget_ends_the_episode_as_budget_not_error():
    class Forever(Agent):
        name = "forever"
        def act(self, obs):
            return [ToolCall("list_layers", {})]
    r = run_episode(_task(0), Forever(), EpisodeConfig(budgets=Budgets(steps=5)))
    assert r.termination == "budget" and r.budget_tripped == "steps" and r.steps == 5


def test_consecutive_faults_end_the_episode():
    class Broken(Agent):
        name = "broken"
        def act(self, obs):
            return [ToolCall("place_label", {"nonsense": 1})]
    r = run_episode(_task(0), Broken(), EpisodeConfig(budgets=Budgets(faults=4)))
    assert r.termination == "budget" and r.budget_tripped == "faults" and r.faults == 4


def test_a_turn_of_blind_faults_is_one_fault_in_a_row():
    # e3-v3: sixteen copies of one failing call in a turn trip no faults budget of 8 on their
    # own; the turns do, once the model has failed that many times with the errors in front of it
    class Spray(Agent):
        name = "spray"
        def act(self, obs):
            return [ToolCall("place_label", {"nonsense": 1})] * 6
    r = run_episode(_task(0), Spray(), EpisodeConfig(budgets=Budgets(faults=2)))
    assert r.termination == "budget" and r.budget_tripped == "faults"
    assert r.turns == 2 and r.faults == 12 and r.steps == 12 and r.invalid_calls == 12


def test_a_one_item_list_is_read_as_the_value_and_counted_as_repaired(tmp_path):
    # e3-v3: the serving stack's list round a single value (LM Studio's Gemma 4 template)
    class Wrapped(Agent):
        name = "wrapped"
        def act(self, obs):
            if obs["turn"] == 0:
                return [ToolCall("list_alignments", {"include_references": [True]}),
                        ToolCall("list_alignments", {"include_references": True})]
            return Submit()
    r = run_episode(_task(0), Wrapped(), EpisodeConfig(), out_root=tmp_path)
    assert r.termination == "submit" and r.faults == 0 and r.invalid_calls == 0
    assert r.repaired_calls == 1 and r.summary()["repaired_calls"] == 1
    rec = read_episode(Path(r.path))
    first, second = rec["turns"][0]["results"]
    assert first["ok"] and first["repaired"] == [
        'include_references: [true] was read as true (a one-item list where the schema takes one value)']
    assert first["warnings"] == first["repaired"] and "repaired" not in second
    assert rec["end"]["repaired_calls"] == 1 and rec["header"]["harness_version"] == "e3-v3"


def test_refusal_and_agent_error_are_outcomes():
    class Refuses(Agent):
        name = "refuses"
        def act(self, obs):
            raise AgentRefusal("no")
    class Crashes(Agent):
        name = "crashes"
        def act(self, obs):
            raise RuntimeError("boom")
    assert run_episode(_task(0), Refuses()).termination == "refusal"
    r = run_episode(_task(0), Crashes())
    assert r.termination == "error" and "boom" in r.error
    assert r.effective_score == 0.0


def test_run_check_is_a_step_with_a_budget_and_shows_no_expected_values():
    class Checker(Agent):
        name = "checker"
        def __init__(self):
            self.turn = 0
            self.views = []
        def act(self, obs):
            self.turn += 1
            if self.turn == 1:
                return [ToolCall("run_check", {})] * 4
            self.views = obs["results"]
            return Submit()
    task = _task(0)
    c = Checker()
    r = run_episode(task, c, EpisodeConfig(mode="self_correct"))
    assert [v["ok"] for v in c.views] == [True, True, True, False]
    assert c.views[3]["error"]["type"] == "budget_exhausted"
    assert c.views[0]["budget_remaining"] == 2 and "checks" in c.views[0]
    text = json.dumps(c.views[0])
    assert "expected" not in text and "points" not in text
    assert r.run_check_uses == 3 and r.steps == 4
    single = run_episode(task, Checker(), EpisodeConfig(mode="single"))
    assert single.run_check_uses == 0


def test_submit_as_a_tool_call_ends_the_episode_after_the_calls_before_it():
    class ToolSubmit(Agent):
        name = "toolsubmit"
        def act(self, obs):
            return [ToolCall("create_layer", {"name": "Z"}), ToolCall("submit", {"note": "done"}),
                    ToolCall("create_layer", {"name": "never"})]
    r = run_episode(_task(0), ToolSubmit())
    assert r.termination == "submit" and r.steps == 2


def test_replay_agent_reproduces_the_oracle_from_its_journal(tmp_path):
    task = _task(1)
    first = run_episode(task, OracleAgent(), out_root=tmp_path)
    journal = read_episode(first.path)["journal"]
    again = run_episode(task, ReplayAgent(journal["entries"]))
    assert again.effective_score == 100.0 and again.steps == first.steps


def test_oracle_passes_through_the_create_alignment_and_attach_reference_types():
    for name, scope_word in (("create-alignment", "design"), ("attach-reference", "reference")):
        task = generate_task(7, task_type=name)
        r = run_episode(task, OracleAgent())
        assert r.effective_score == 100.0 and r.faults == 0, (name, r.report.to_json()[:300])


def test_oversized_results_are_cut_with_a_hint():
    class Dumper(Agent):
        name = "dumper"
        def __init__(self):
            self.turn = 0
            self.result = None
        def act(self, obs):
            self.turn += 1
            if self.turn == 1:
                return [ToolCall("get_document_state", {"detail": "full"})]
            self.result = obs["results"][0]
            return Submit()
    task = generate_task(42, task_type="annotate-sheet")  # linework + sheet already drawn
    d = Dumper()
    run_episode(task, d, EpisodeConfig(result_cap=2000))
    assert d.result["truncated"] is True and len(d.result["text"]) == 2000 and "hint" in d.result


def test_a_harness_failure_inside_a_tool_call_ends_the_episode_on_record(tmp_path, monkeypatch, capsys):
    """2026-10-28: Gemma 4 12B's D1-001041 raised TypeError inside a tool call; the exception escaped the loop
    and the file had no end record. Now the call's result names the failure, the episode ends as the harness's
    error with its end record, no step is counted, and the traceback goes to stderr."""
    import roaddraft.eval.episode as ep

    class Draws(Agent):
        name = "draws"

        def act(self, obs):
            return [ToolCall("list_layers", {}), ToolCall("list_layers", {})]

    def boom(self, call):
        raise TypeError("unhashable type: 'list'")

    monkeypatch.setattr(ep.Episode, "_execute", boom)
    r = run_episode(_task(0), Draws(), out_root=tmp_path)
    assert r.termination == "error" and r.error.startswith("harness: TypeError: unhashable")
    assert r.steps == 0 and r.turns == 1 and r.faults == 0
    rec = read_episode(r.path)
    assert rec["end"]["termination"] == "error" and "unhashable" in rec["end"]["error"]
    results = rec["turns"][0]["results"]
    assert len(results) == 1 and results[0]["error"]["type"] == "harness_error"   # the second call never ran
    assert "Traceback" in capsys.readouterr().err


def test_a_scoring_failure_still_writes_the_end_record(tmp_path, monkeypatch, capsys):
    import roaddraft.eval.episode as ep

    def boom(*args, **kwargs):
        raise RuntimeError("verifier boom")

    monkeypatch.setattr(ep, "verify", boom)
    r = run_episode(_task(0), NullAgent(), out_root=tmp_path)
    assert r.termination == "error" and r.error == "harness: scoring: RuntimeError: verifier boom"
    assert r.effective_score == 0.0 and r.report.hard_failed is False and r.report.to_dict()["unscored"]
    rec = read_episode(r.path)
    assert rec["end"]["termination"] == "error" and rec["end"]["effective_score"] == 0.0 and rec["verify"] is None
    assert "verifier boom" in capsys.readouterr().err
