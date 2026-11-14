"""The episode loop and the four agents (eval plan sections 4.1, 4.3).

The oracle through the loop scores 100 on all 50 d1-dev tasks: the harness
loses no points.  That number is this file's permanent test."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import Agent, AgentRefusal, NullAgent, OracleAgent, ReplayAgent, ScriptedAgent, Submit, ToolCall
from roaddraft.eval.agents import calls_from_commands
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import Episode, EpisodeConfig, run_episode
from roaddraft.eval.trajectory import read_episode, replay_journal, reverify
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import solution_commands

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


# ---------------------------- a revision made in the base drawing (open_document)

#: the checks such a task reads in the base drawing: the design, its centerline, its edges
BASE_CHECKS = ("D1-01", "D1-12", "D1-15")


@pytest.fixture(scope="module")
def base_task():
    """A curve's radius changed by the drafter in the base drawing the sheet file references."""
    return generate_task(18000, curves=1, task_type="annotate-base", revise="base-radius")


@pytest.fixture(scope="module")
def station():
    """The same flavour, a restation: nothing moves, so the base drawing's edges stay."""
    return generate_task(18002, curves=2, task_type="annotate-base", revise="base-station")


class _Turns(Agent):
    """Plays the given turns, a list of calls each, then stops without calling submit."""
    name = "turns"

    def __init__(self, *turns):
        self.script = [list(turn) for turn in turns]

    def act(self, obs):
        return self.script.pop(0) if self.script else Submit()


def _halves(task):
    """The reference solution up to its last command in the base drawing, and from the
    open_document that goes back to the sheet file on; and the two file names."""
    commands = solution_commands(task)
    back = max(i for i, (name, _) in enumerate(commands) if name == "open_document")
    assert commands[back][1]["path"] == f"{task.task_id}.rdoc.json"
    return commands[:back], commands[back:], task.brief.deliverable["basefile"], commands[back][1]["path"]


def _desk(task):
    ep = Episode(task, NullAgent(), EpisodeConfig(mode="single"))
    ep.reset()
    return ep


def _credits(result):
    return {c.id: c.credit for c in result.report.in_scope()}


def test_oracle_scores_100_and_null_0_on_a_revision_made_in_the_base_drawing(base_task, station, tmp_path):
    for task in (base_task, station):
        in_base, _, base_name, _ = _halves(task)
        for level in ("explicit", "vague"):
            config = EpisodeConfig(level=level)
            r = run_episode(task, OracleAgent(), config, out_root=tmp_path)
            assert r.termination == "submit" and r.faults == 0, (task.task_id, level, r.error)
            assert r.effective_score == 100.0 and not r.report.hard_failed, (task.task_id, level)
            assert run_episode(task, NullAgent(), config).effective_score == 0.0
            # the file alone re-scores it: what was done in the base drawing is in its journal block
            assert reverify(r.path).effective_score == 100.0
            visit, = read_episode(r.path)["journal"]["opened"]
            assert visit["document"] == base_name
            done = [e["name"] for e in visit["entries"]]
            assert done[0] == "modify_alignment" and done == [name for name, _ in in_base[2:]]
            assert visit["at"] == 1   # the handed document had taken its set_meta, and no more


def test_submit_with_the_base_drawing_open_is_refused_with_the_way_back_and_the_episode_goes_on(
        base_task, station, tmp_path):
    for task in (base_task, station):
        in_base, rest, base_name, handed = _halves(task)

        def early():
            return calls_from_commands(in_base) + [ToolCall("submit", {})]

        def late():
            return calls_from_commands(rest) + [ToolCall("submit", {"note": "done"})]

        r = run_episode(task, _Turns(early(), late()), out_root=tmp_path)
        assert r.termination == "submit" and r.turns == 2 and r.effective_score == 100.0
        # the refused submit is a step and a fault, like any call that failed
        assert r.steps == len(in_base) + len(rest) + 2 and r.faults == 1
        first, second = read_episode(r.path)["turns"]
        refused = first["results"][-1]
        assert refused["ok"] is False and refused["error"]["type"] == "wrong_document"
        assert base_name in refused["error"]["message"] and handed in refused["error"]["message"]
        assert "open_document" in refused["error"]["hint"]
        assert "reload_references" in refused["error"]["hint"]
        assert first["assistant"]["submit"] is False and second["assistant"]["submit"] is True
        assert second["results"][-1] == {"ok": True, "name": "submit", "message": "submitted"}
        # in one turn the calls after the refused submit still run, and the next submit ends it
        r = run_episode(task, _Turns(early() + late() + [ToolCall("create_layer", {"name": "never"})]))
        assert r.termination == "submit" and r.turns == 1 and r.effective_score == 100.0
        assert r.steps == len(in_base) + len(rest) + 2 and r.faults == 1


def test_an_episode_that_ends_in_the_base_drawing_is_graded_on_the_sheet_file_as_it_now_reads(
        base_task, station):
    for task in (base_task, station):
        in_base, _, _, _ = _halves(task)
        idle = _credits(run_episode(task, NullAgent()))
        assert idle["D1-15"] < 1.0
        # the sheet file reads the base drawing first, so it holds a copy of the old design
        read = ToolCall("list_alignments", {"include_references": True})
        r = run_episode(task, _Turns([read] + calls_from_commands(in_base)))
        assert r.termination == "submit" and r.error is None
        assert r.report.task_id == task.task_id and r.effective_score < 100.0
        credit = _credits(r)
        # the design, the centerline and the edges are read in the base drawing's file as it
        # now stands, not in the copy the sheet file had
        assert all(credit[check] == 1.0 for check in BASE_CHECKS), credit
        # the lettering is the sheet file's, still the old design's: every other check stands
        # where it does when nothing is done
        assert credit["D1-04"] < 1.0 and credit["D1-05"] < 1.0
        assert ({k: v for k, v in credit.items() if k not in BASE_CHECKS}
                == {k: v for k, v in idle.items() if k not in BASE_CHECKS})


def test_the_whole_solution_then_the_base_drawing_left_open_still_scores_100(base_task, station, tmp_path):
    for task in (base_task, station):
        in_base, rest, base_name, _ = _halves(task)
        again = ToolCall("open_document", {"path": base_name})
        r = run_episode(task, _Turns(calls_from_commands(in_base + rest) + [again]), out_root=tmp_path)
        assert r.termination == "submit" and r.faults == 0 and r.steps == len(in_base) + len(rest) + 1
        assert r.effective_score == 100.0 and not r.report.hard_failed
        # the last visit changed nothing, and the block keeps only the one that did
        assert len(read_episode(r.path)["journal"]["opened"]) == 1
        assert reverify(r.path).effective_score == 100.0


def test_back_in_the_sheet_file_a_changed_base_drawing_is_flagged_until_it_is_reloaded(base_task):
    in_base, _, base_name, handed = _halves(base_task)
    change = next(ToolCall(name, dict(params)) for name, params in in_base if name == "modify_alignment")
    read = ToolCall("list_alignments", {"include_references": True})
    ep = _desk(base_task)
    old = ep.execute(read)["alignments"][0]   # the sheet file reads the base drawing
    assert ep.execute(ToolCall("open_document", {"path": base_name}))["warnings"] == []
    assert ep.execute(change)["ok"] is True
    back = ep.execute(ToolCall("open_document", {"path": handed}))
    warning, = back["warnings"]
    assert "has changed since this file read it" in warning and "reload_references" in warning
    assert ep.execute(read)["alignments"][0] == old   # its copy is still the old design
    assert ep.execute(ToolCall("reload_references", {}))["ok"] is True
    assert ep.execute(read)["alignments"][0] != old
    there = ep.execute(ToolCall("open_document", {"path": base_name}))
    again = ep.execute(ToolCall("open_document", {"path": handed}))
    assert there["ok"] and again["ok"] and there["warnings"] == [] and again["warnings"] == []
    assert [visit["document"] for visit in ep.opened] == [base_name] and ep.state.faults == 0
    # the warning is for a copy the sheet file had read: one that never read it has none
    ep = _desk(base_task)
    ep.execute(ToolCall("open_document", {"path": base_name}))
    assert ep.execute(change)["ok"] is True
    assert ep.execute(ToolCall("open_document", {"path": handed}))["warnings"] == []


def test_a_base_drawing_opened_and_left_as_it_was_leaves_no_record(base_task):
    _, _, base_name, handed = _halves(base_task)
    ep = _desk(base_task)
    assert ep.execute(ToolCall("open_document", {"path": base_name}))["ok"] is True
    assert ep.execute(ToolCall("list_alignments", {}))["count"] == 1   # a query changes nothing
    back = ep.execute(ToolCall("open_document", {"path": handed}))
    assert back["ok"] is True and back["warnings"] == []
    assert ep.opened == [] and ep.other is None
    _, records = ep.finish()
    assert records[0]["type"] == "journal" and "opened" not in records[0]


def test_replay_journal_rebuilds_the_document_of_an_episode_that_changed_the_base_drawing(
        base_task, station, tmp_path):
    for task in (base_task, station):
        base_name = task.brief.deliverable["basefile"]
        ep = Episode(task, OracleAgent(), EpisodeConfig(), out_root=tmp_path)
        journal = read_episode(ep.run().path)["journal"]
        assert journal["opened"]
        replayed = replay_journal(journal)
        assert replayed.doc.to_dict() == ep.session.doc.to_dict()
        # the base drawing it rebuilt beside the document is the one the episode left
        rebuilt = json.loads((Path(replayed.doc._path).parent / base_name).read_text())
        assert rebuilt == json.loads((Path(ep.root.real) / base_name).read_text())
        assert rebuilt != task.files[base_name]
    # the old path: a block with no other document replays as it always has, with files or none
    for task in (generate_task(1), generate_task(7, task_type="attach-reference")):
        ep = Episode(task, OracleAgent(), EpisodeConfig(), out_root=tmp_path)
        r = ep.run()
        journal = read_episode(r.path)["journal"]
        assert r.effective_score == 100.0 and "opened" not in journal
        assert replay_journal(journal).doc.to_dict() == ep.session.doc.to_dict()
