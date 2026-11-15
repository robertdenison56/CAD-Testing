"""Probe-task episodes as training conversations
(``roaddraft.trajectories.conversations``; training plan section 8, build 5): the
generated deeds and planted-error sheets record on the pilots' harness
(``eval.probe_tasks``), and their conversation is what that harness sends a
model.  An episode is kept when, played again on the manifest's task, every call
answers as recorded, the task's check passes and the audit finds nothing
ungrounded."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.eval import probe_tasks
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents.llm import LLMAgent
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import EpisodeConfig
from roaddraft.eval.prompts import SystemExtra
from roaddraft.eval.providers.fake import FakeProvider, turn
from roaddraft.trajectories import conversations as cv
from roaddraft.trajectories import reasoning

from tests.test_trajectories_conversations import _rewrite, _sent, _shape


def _task(name: str = "train-deeds", n: int = 0, level: str = "vague"):
    return tasksets.task_from_entry(tasksets.load(name)["tasks"][n], level=level)


def _llm_episode(tmp_path, task, provider, budgets=Budgets(), extra=None):
    agent = LLMAgent(provider, label="fake-model")
    config = EpisodeConfig(level=task.level, budgets=budgets, system_extra=extra)
    result = probe_tasks.ProbeEpisode(task, agent, config, out_root=tmp_path).run()
    return result, Path(result.path)


def _oracle_run(tmp, extra=None):
    """An LLM agent replaying a generated deed's scripted solution three calls
    a turn, on budgets tight enough that the harness's notes come in."""
    task = _task()
    steps = len(probe_tasks.oracle_calls(task.probe)) + 8
    provider = FakeProvider.oracle(per_turn=3)
    result, path = _llm_episode(tmp, task, provider, Budgets(steps=steps, faults=3), extra)
    assert result.termination == "submit" and result.effective_score == 100.0
    return task, provider, result, path


@pytest.fixture(scope="module")
def oracle_run(tmp_path_factory):
    return _oracle_run(tmp_path_factory.mktemp("probe-oracle"))


def _drop(path, taskset="train-deeds", audit=False) -> str:
    with pytest.raises(cv.Drop) as caught:
        cv.convert_episode(path, taskset, audit=audit)
    return caught.value.reason


def test_a_probe_conversation_is_what_the_harness_sent_the_model(oracle_run):
    task, provider, result, path = oracle_run
    conv, defs = cv.convert_episode(path, "train-deeds", audit=False)
    msgs = conv["messages"]
    last = provider.requests[-1]
    # the probe harness's system prompt and the MCP server's tool list, as the agent sent them
    assert msgs[0] == {"role": "system", "content": last["system"]}
    budgets = Budgets(steps=len(probe_tasks.oracle_calls(task.probe)) + 8, faults=3).for_mode("single")
    assert last["system"] == probe_tasks.system_prompt("single", budgets)
    assert [d["name"] for d in defs] == last["tools"]
    # the task text is the probe runner's, and every message after it is the one sent, in order
    assert msgs[1] == {"role": "user", "content": probe_tasks.brief_text(task.probe, "vague")}
    assert [_shape(m) for m in msgs[1:-1]] == _sent(last["transcript"])
    assert _shape(msgs[-1])[2] == [("submit", {"note": "reference solution replayed"})]
    assert conv["header"]["counts"]["notes"] == len(provider.requests) - 1
    assert any("steps left" in m["content"] for m in msgs[2:] if m["role"] == "user")


def test_a_probe_conversations_header_pins_the_episode(oracle_run):
    task, provider, result, path = oracle_run
    conv, defs = cv.convert_episode(path, "train-deeds", audit=False)
    episode_header = json.loads(path.read_text().splitlines()[0])
    head = conv["header"]
    for key in ("task_id", "task_type", "tools_sha256", "prompt_hash", "spec_version", "spec_hash",
                "generator_version", "verifier_version", "harness_version", "level", "mode",
                "probe", "start"):
        assert head[key] == episode_header[key], key
    assert head["system_sha256"] == episode_header["prompt_sha256"]
    assert head["tools_sha256"] == cv.tools_sha256(defs)
    assert head["harness"] == "probe" and head["taskset"] == "train-deeds"
    # the header of a probe episode has no seed: the manifest entry's is carried
    assert head["seed"] == tasksets.load("train-deeds")["tasks"][0]["seed"]
    assert head["score"]["effective"] == 100.0 and head["source"] == "rollout"
    assert conv["id"] == f"{task.task_id}.vague"
    sent = cv.function_tools(defs)
    assert all(t["function"]["parameters"] == d["input_schema"] for t, d in zip(sent, defs))


def test_a_probe_episode_given_a_system_extra_converts_with_the_prompt_as_sent(tmp_path):
    file = tmp_path / "extra.md"
    file.write_text("Check every bearing against the deed before drawing it.\n")
    task, provider, result, path = _oracle_run(tmp_path, SystemExtra.load(file))
    header = json.loads(path.read_text().splitlines()[0])
    assert header["prompt_hash"] != cv.digest(task.brief)   # the brief and the extra, hashed together
    conv, _defs = cv.convert_episode(path, "train-deeds", audit=False)
    system = conv["messages"][0]["content"]
    assert system == provider.requests[-1]["system"]
    assert system.endswith("\n\nCheck every bearing against the deed before drawing it.\n")
    assert conv["header"]["system_extra"] == header["system_extra"]
    assert conv["header"]["prompt_hash"] == header["prompt_hash"]


@pytest.mark.parametrize("name, level", [("train-deeds", "vague"), ("train-deeds", "explicit"),
                                         ("train-qa", "vague")])
def test_a_grounded_probe_reference_converts_and_keeps_its_shown_work(tmp_path, name, level):
    task = _task(name, 1, level)
    row = reasoning.record_task(task, level, out_root=tmp_path)
    assert row["kept"]
    conv, defs = cv.convert_episode(row["path"], name)
    head, msgs = conv["header"], conv["messages"]
    assert head["source"] == "reference" and head["level"] == level and head["task_id"] == task.task_id
    # the drafter has no system prompt: it gets what the probe harness hands an agent on the
    # episode, which is recorded on the pilots' budgets
    assert msgs[0]["content"] == probe_tasks.system_prompt("single", probe_tasks.BUDGETS.for_mode("single"))
    assert msgs[1]["content"] == task.brief
    turns = [r for r in (json.loads(line) for line in Path(row["path"]).read_text().splitlines())
             if r["type"] == "turn"]
    assert [m["content"] for m in msgs if m["role"] == "assistant"] == [t["assistant"]["text"] for t in turns]
    assert msgs[-1]["tool_calls"][-1]["function"]["name"] == "submit"
    shown = [m for m in msgs if m["role"] == "tool"]
    assert len(shown) == head["counts"]["results_shown"] == sum(len(t["results"]) for t in turns[:-1])
    assert all(json.loads(m["content"])["ok"] for m in shown)
    assert {"submit", "get_task_brief", "open_document"} <= {d["name"] for d in defs}
    assert "run_check" not in {d["name"] for d in defs}


def test_the_audit_drops_the_scripted_solution(oracle_run):
    # the scripted solution's balanced corners are worked out off the page: ungrounded
    _, _, _, path = oracle_run
    assert _drop(path, audit=True) == "ungrounded"


def test_a_probe_episode_that_fails_its_check_is_dropped(tmp_path):
    result, path = _llm_episode(tmp_path, _task(), FakeProvider([turn([("list_layers", {})]),
                                                                 turn([("submit", {"note": "nothing"})])]))
    assert result.termination == "submit" and result.effective_score == 0.0
    assert _drop(path) == "score"
    assert cv.convert(path, "train-deeds").drop == "score"


def _first_result(records) -> dict:
    return next(r for r in records if r["type"] == "turn")["results"][0]


@pytest.mark.parametrize("change, reason", [
    (lambda rs: rs[-1].update(termination="budget"), "not_submitted"),
    (lambda rs: rs[0].update(mode="vision"), "vision"),
    (lambda rs: rs[1]["assistant"]["tool_calls"].append({"name": "view_attachment", "params": {}}), "vision"),
    (lambda rs: rs[1]["assistant"].update(nudges=1), "nudged"),
    (lambda rs: rs[0].update(prompt_hash="sha256:" + "0" * 64), "prompt"),
    (lambda rs: rs[0].update(task_id="TR-t03-deed-19000-0000000000"), "no_task"),
    (lambda rs: next(r for r in rs if r["type"] == "journal").update(start="train-deed-1"), "start"),
    (lambda rs: rs[0].update(tools_sha256="sha256:" + "1" * 64), "tools"),
    # a result the manifest's task does not give: the episode began from other documents
    (lambda rs: _first_result(rs).update(seen_elsewhere=1), "replay"),
])
def test_a_probe_episode_that_is_not_this_checkouts_task_or_tools_is_dropped(oracle_run, tmp_path, change, reason):
    _, _, _, path = oracle_run
    assert _drop(_rewrite(path, tmp_path / "changed.jsonl", change)) == reason


def test_a_probe_episode_is_held_to_its_own_level_and_set(oracle_run, tmp_path):
    _, _, _, path = oracle_run
    assert _drop(path, taskset="train-qa") == "no_task"
    # the vague task's id under an explicit header: not the manifest's task at that level
    assert _drop(_rewrite(path, tmp_path / "level.jsonl", lambda rs: rs[0].update(level="explicit"))) == "no_task"


def test_the_cli_converts_a_probe_set_beside_a_d1_set(tmp_path):
    from roaddraft.trajectories import grounded
    src, out = tmp_path / "src", tmp_path / "out"
    assert reasoning.record("train-deeds", src / "train-deeds-vague", level="vague", limit=3)["kept"] == 3
    assert reasoning.record("train-qa", src / "train-qa-vague", level="vague", limit=2)["kept"] == 2
    assert grounded.record("d1-train", src / "d1-train-vague", level="vague", limit=2)["kept"] == 2
    summary = cv.run(["d1-train", "train-deeds", "train-qa"], ["vague"], source=src, out=out,
                     log=lambda *_: None)
    assert {k: t["kept"] for k, t in summary["sets"].items()} == {
        "d1-train-vague": 2, "train-deeds-vague": 3, "train-qa-vague": 2}
    assert all(t["dropped"] == {} for t in summary["sets"].values())
    deeds = summary["sets"]["train-deeds-vague"]
    assert deeds["harness"] == "probe" and deeds["by_type"] == {"train-survey-traps": 3}
    assert deeds["seeds"] == [19000, 19002] and deeds["recorder"]["kept"] == 3
    assert "harness" not in summary["sets"]["d1-train-vague"]
    tools = json.loads((out / "tools.json").read_text())
    lines = [json.loads(line) for name in ("train-deeds", "train-qa")
             for line in (out / f"{name}-vague.jsonl").read_text().splitlines()]
    # the two probe sets share the MCP server's one tool list, kept once beside the D1 sets'
    assert len({c["header"]["tools_sha256"] for c in lines}) == 1
    for c in lines:
        row = tools[c["header"]["tools_sha256"]]
        assert cv.tools_sha256(row["definitions"]) == c["header"]["tools_sha256"]
        assert [t["function"]["name"] for t in row["function_tools"]] == row["names"]
    card = cv.card(out, tmp_path / "CARD.md").read_text()
    assert "| `train-deeds` | 19000-19299 | vague | 3 |  | 3 | 3 | 0 |" in card
    assert "are probe tasks" in card and "system prompt, probe tasks" in card
    assert "probe tasks: the MCP server's tools" in card


def test_the_convert_cli_takes_the_probe_sets(tmp_path, capsys):
    src, out = tmp_path / "src", tmp_path / "out"
    reasoning.record("train-qa", src / "train-qa-explicit", level="explicit", limit=1)
    assert cv.main(["convert", "--set", "train-qa", "--source", str(src), "--out", str(out),
                    "--jobs", "1", "--no-faults"]) == 0
    assert "1 conversations written" in capsys.readouterr().out
    assert (out / "train-qa-explicit.jsonl").read_text().count("\n") == 1


def test_report_reverify_reaches_a_generated_probe_episode(tmp_path):
    """``probe_tasks.rescore`` finds a generated probe by its id: the start
    built again from its seed, the kept files laid over it, the check run."""
    task = _task("train-qa", 0, "vague")
    row = reasoning.record_task(task, "vague", out_root=tmp_path)
    journal = next(r for r in (json.loads(line) for line in Path(row["path"]).read_text().splitlines())
                   if r["type"] == "journal")
    again = probe_tasks.rescore(row["path"], journal)
    assert again["passed"] and again["effective_score"] == 100.0 and again["probe"] == task.probe.id
    assert probe_tasks.by_id(_task().probe.id).id == _task().probe.id
    with pytest.raises(KeyError):
        probe_tasks.by_id("t99-nothing-1")
