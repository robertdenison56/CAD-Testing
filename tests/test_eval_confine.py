"""An eval episode's file access is held to its own folder (document/confine.py).

The harness drives a Session directly, not through ``roaddraft-mcp --root``, so
the episode holds the root itself: every tool call runs with file access held
to a fresh temporary folder that has the task's files and the renders and not
the truth.  A reference attached by an absolute path, through '..', by a link
or by a path that only exists in the working directory is refused, a render
written outside is refused, and the agent is never shown where the folder is.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from roaddraft.document import confine
from roaddraft.eval.agents import Agent, LLMAgent, NullAgent, OracleAgent, Submit, ToolCall
from roaddraft.eval.episode import Episode, EpisodeConfig, run_episode
from roaddraft.eval.providers import FakeProvider
from roaddraft.eval.providers.fake import turn
from roaddraft.eval.trajectory import read_episode
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.real import build_real_task
from roaddraft.tasks.reference import reference_solution, session_for_task

REFUSED = "is outside the folder this session may read and write"


@pytest.fixture(scope="module")
def task():
    return generate_task(7, task_type="attach-reference")  # ships its base file


@pytest.fixture(scope="module")
def answer(task, tmp_path_factory):
    """A loadable document outside every episode folder: the task's base
    file, and the reference solution, the answer a model must not read."""
    folder = tmp_path_factory.mktemp("outside")
    (base_name, base), = task.files.items()
    (folder / base_name).write_text(json.dumps(base))
    solved = session_for_task(task)
    reference_solution(task, solved)
    saved = solved.query("save_document", {"path": str(folder / "answer.rdoc.json")})
    assert saved["ok"], saved
    return folder


def _episode(task, mode="self_correct"):
    ep = Episode(task, NullAgent(), EpisodeConfig(mode=mode))
    ep.reset()
    return ep


def _attach(ep, path, name="SNEAK"):
    return ep.execute(ToolCall("attach_reference", {"name": name, "path": path}))


def _refused(result, given):
    assert result["ok"] is False, result
    assert f"{given!r} {REFUSED}" in result["error"]["message"], result["error"]


# --------------------------------------------------------------- the folder

def test_the_episode_folder_holds_the_tasks_files_and_nothing_of_the_truth(task):
    ep = _episode(task)
    folder = Path(ep.root.real)
    assert folder.is_dir() and folder.name.startswith("roaddraft-episode-")
    assert sorted(p.name for p in folder.iterdir()) == sorted(task.files)
    assert Path(ep.session.doc._path).parent == Path(ep.root.given)
    truth = json.dumps(task.truth.to_dict())
    assert all(truth not in p.read_text() for p in folder.iterdir())
    assert confine.current() is None  # held per call, not for the harness


def test_each_episode_gets_a_folder_of_its_own(task):
    a, b = _episode(task), _episode(task)
    assert a.root.real != b.root.real
    assert not a.root.contains(b.root.real) and not b.root.contains(a.root.real)


# -------------------------------------------------------- reads: references

def test_a_reference_by_absolute_path_is_refused(task, answer):
    ep = _episode(task)
    for path in (str(answer / "answer.rdoc.json"), str(answer / next(iter(task.files)))):
        _refused(_attach(ep, path), path)
    assert not ep.session.doc.references


def test_a_reference_through_dot_dot_is_refused(task, answer):
    ep = _episode(task)
    up = os.path.relpath(answer / "answer.rdoc.json", ep.root.real)
    assert up.startswith("..")
    _refused(_attach(ep, up), up)
    sideways = f"renders/../{up}"
    _refused(_attach(ep, sideways), sideways)
    assert not ep.session.doc.references


def test_a_reference_by_a_link_to_a_file_outside_is_refused(task, answer):
    ep = _episode(task)
    folder = Path(ep.root.real)
    (folder / "linked.rdoc.json").symlink_to(answer / "answer.rdoc.json")
    (folder / "away").symlink_to(answer, target_is_directory=True)
    _refused(_attach(ep, "linked.rdoc.json"), "linked.rdoc.json")
    _refused(_attach(ep, "away/answer.rdoc.json"), "away/answer.rdoc.json")
    assert not ep.session.doc.references


def test_a_path_found_only_in_the_working_directory_is_refused(task, answer, monkeypatch):
    monkeypatch.chdir(answer)  # references fall back to the working directory
    ep = _episode(task)
    _refused(_attach(ep, "answer.rdoc.json"), "answer.rdoc.json")
    assert not ep.session.doc.references


def test_a_relative_reference_inside_the_folder_attaches_and_shows_no_folder(task):
    ep = _episode(task)
    (name, _), = task.files.items()
    ok = _attach(ep, name, name="BASE")
    assert ok["ok"] is True, ok
    listed = ep.execute(ToolCall("list_references", {}))
    assert listed["ok"] and listed["references"][0]["status"] == "loaded"
    assert listed["references"][0]["resolved_path"] == name
    # nested in a subfolder, through a '..' that stays inside: still the folder's
    sub = Path(ep.root.real) / "sub"
    sub.mkdir()
    (sub / "copy.rdoc.json").write_text((Path(ep.root.real) / name).read_text())
    assert _attach(ep, "sub/../sub/copy.rdoc.json", name="COPY")["ok"] is True
    shown = json.dumps([listed, ep.state_summary(), ep.execute(ToolCall("list_references", {}))])
    assert ep.root.real not in shown and ep.root.given not in shown
    assert "roaddraft-episode-" not in shown


def test_a_missing_file_names_the_folder_relative(task):
    ep = _episode(task)
    missing = _attach(ep, "nope.rdoc.json")
    assert missing["ok"] is False
    assert "(looked in .)" in missing["error"]["message"]
    assert "folder (.)" in missing["error"]["hint"]
    assert "roaddraft-episode-" not in json.dumps(missing)


# ------------------------------------------------------------- writes: renders

def test_a_render_to_a_path_outside_is_refused_and_nothing_is_written(task, answer):
    ep = _episode(task)
    sheet = task.brief.deliverable["sheets"][0]["name"]
    for path in (str(answer / "out.png"), "../out.png", f"renders/../../{sheet}.png"):
        r = ep.execute(ToolCall("render_sheet", {"sheet": sheet, "path": path}))
        _refused(r, path)
        r = ep.execute(ToolCall("render_model", {"path": path}))
        _refused(r, path)
    assert not (answer / "out.png").exists()
    assert not (Path(ep.root.real).parent / "out.png").exists()
    (Path(ep.root.real) / "away").symlink_to(answer, target_is_directory=True)
    _refused(ep.execute(ToolCall("render_model", {"path": "away/model.png"})), "away/model.png")
    assert not (answer / "model.png").exists()


def test_a_render_lands_in_the_folder_and_its_shown_path_can_be_handed_back(task):
    ep = _episode(task)
    sheet = task.brief.deliverable["sheets"][0]["name"]
    first = ep.execute(ToolCall("render_sheet", {"sheet": sheet}))
    assert first["ok"] and first["path"] == f"renders/{sheet}.png", first
    assert (Path(ep.root.real) / first["path"]).is_file()
    again = ep.execute(ToolCall("render_sheet", {"sheet": sheet, "path": first["path"]}))
    assert again["ok"] and again["path"] == first["path"]
    mine = ep.execute(ToolCall("render_model", {"path": "check/model.png"}))
    assert mine["ok"] and mine["path"] == "check/model.png"
    assert (Path(ep.root.real) / "check" / "model.png").is_file()


# ------------------------------------------------------------- the agent's view

def test_nothing_the_agent_is_shown_or_the_trajectory_keeps_names_the_folder(task, answer, tmp_path):
    sheet = task.brief.deliverable["sheets"][0]["name"]
    (name, _), = task.files.items()
    provider = FakeProvider([
        turn([("attach_reference", {"name": "BASE", "path": name}),
              ("attach_reference", {"name": "SNEAK", "path": str(answer / "answer.rdoc.json")}),
              ("attach_reference", {"name": "GONE", "path": "gone.rdoc.json"}),
              ("list_references", {}), ("render_sheet", {"sheet": sheet}),
              ("render_model", {"path": "../model.png"})]),
        turn([("submit", {})])])
    r = run_episode(task, LLMAgent(provider), EpisodeConfig(mode="vision"), out_root=tmp_path)
    assert r.termination == "submit"
    given = str(answer / "answer.rdoc.json")  # the agent's own words, echoed in the refusal
    results = provider.requests[1]["transcript"][-1]["results"]
    assert [json.loads(x["content"])["ok"] for x in results] == [True, False, False, True, True, False]
    assert results[4]["images"] and results[4]["images"][0][0] == "image/png"  # read before the scrub
    for text in (json.dumps(provider.requests), Path(r.path).read_text()):
        assert "roaddraft-episode-" not in text and os.getcwd() not in text
        assert str(answer) not in text.replace(given, "")
    turns = read_episode(r.path)["turns"]
    assert turns[0]["results"][4]["path"] == f"renders/{sheet}.png"


# ------------------------------------------------------- the agents, as before

def test_the_oracle_still_attaches_by_its_relative_name_and_scores_100(task):
    r = run_episode(task, OracleAgent())
    assert r.effective_score == 100.0 and r.faults == 0


@pytest.mark.parametrize("sheet_id, alignment, type_name", [
    ("PPM-045", "D13", "real-attach-reference"),   # attaches two real base files
    ("PPM-045", "TB1", "real-plan-sheet"),         # draws through a referenced base
])
def test_the_oracle_on_a_real_sheet_reads_its_base_files_inside_the_folder(sheet_id, alignment,
                                                                          type_name):
    r = run_episode(build_real_task(sheet_id, alignment, type_name), OracleAgent())
    assert r.effective_score == 100.0 and r.faults == 0, r.report.to_json()[:300]


def test_the_null_agent_still_scores_0(task):
    assert run_episode(task, NullAgent()).effective_score == 0.0


def test_the_root_is_held_only_for_the_tool_call():
    class Peek(Agent):
        name = "peek"
        def __init__(self):
            self.seen = []
        def act(self, obs):
            self.seen.append(confine.current())
            if len(self.seen) == 1:
                return [ToolCall("list_layers", {})]
            return Submit()
    agent = Peek()
    run_episode(generate_task(1), agent)
    assert agent.seen == [None, None] and confine.current() is None
