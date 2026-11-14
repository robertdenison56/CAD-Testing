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
from roaddraft.tasks.reference import reference_solution, session_for_task, solution_commands

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


# ------------------------------------ another document of the task: open_document

@pytest.fixture(scope="module")
def base_task():
    """A revision the drafter makes in the base drawing the sheet file references: the
    one task whose episode opens another document (``eval.tools.BASE_COMMANDS``)."""
    return generate_task(18000, curves=1, task_type="annotate-base", revise="base-radius")


@pytest.fixture(scope="module")
def base_answer(base_task, tmp_path_factory):
    """Loadable documents outside every episode folder: the task's base file as it is
    handed over, and the sheet file of the reference solution."""
    folder = tmp_path_factory.mktemp("outside-base")
    (base_name, base), = base_task.files.items()
    (folder / base_name).write_text(json.dumps(base))
    solved = session_for_task(base_task)
    reference_solution(base_task, solved)
    saved = solved.query("save_document", {"path": str(folder / "answer.rdoc.json")})
    assert saved["ok"], saved
    return folder


def _open(ep, path):
    return ep.execute(ToolCall("open_document", {"path": path}))


def _folder_unnamed(ep, *shown):
    text = json.dumps(shown)
    assert ep.root.real not in text and ep.root.given not in text
    assert "roaddraft-episode-" not in text


def test_open_document_outside_the_folder_is_refused_and_nothing_opens(base_task, base_answer):
    ep = _episode(base_task, mode="single")
    folder = Path(ep.root.real)
    handed = f"{base_task.task_id}.rdoc.json"
    (base_name, _), = base_task.files.items()
    up = os.path.relpath(base_answer / "answer.rdoc.json", ep.root.real)
    assert up.startswith("..")
    (folder / "linked.rdoc.json").symlink_to(base_answer / "answer.rdoc.json")
    (folder / "away").symlink_to(base_answer, target_is_directory=True)
    for given in (str(base_answer / "answer.rdoc.json"),          # absolute
                  str(base_answer / base_name),                   # the base drawing's name, elsewhere
                  up, f"renders/../{up}", "renders/../../x",      # through '..'
                  "linked.rdoc.json",                             # a link to a file outside
                  "away/answer.rdoc.json", f"away/{base_name}"):  # a link to the folder outside
        result = _open(ep, given)
        _refused(result, given)
        assert ep.other is None and ep.other_name is None and ep.opened == []
        text = json.dumps(result)
        assert "roaddraft-episode-" not in text
        assert str(base_answer) not in text.replace(given, "")
    # the handed document is still the open one
    assert ep.desk is ep.session
    state = ep.execute(ToolCall("get_document_state", {}))
    assert state["ok"] and state["summary"]["document"] == handed


def test_inside_the_folder_only_the_tasks_own_documents_open(base_task):
    ep = _episode(base_task, mode="single")
    folder = Path(ep.root.real)
    handed = f"{base_task.task_id}.rdoc.json"
    (base_name, _), = base_task.files.items()
    # loadable and inside, and not a document of the task: a copy, and the name in a subfolder
    (folder / "copy.rdoc.json").write_text((folder / base_name).read_text())
    (folder / "sub").mkdir()
    (folder / "sub" / base_name).write_text((folder / base_name).read_text())
    for given in ("copy.rdoc.json", f"sub/{base_name}", "nope.rdoc.json"):
        result = _open(ep, given)
        assert result["ok"] is False, result
        assert result["error"]["message"] == f"no such document: {given}"
        assert handed in result["error"]["hint"] and base_name in result["error"]["hint"]
        assert ep.other is None and ep.opened == []
        _folder_unnamed(ep, result)


def test_the_base_drawing_opens_by_its_relative_name_and_so_does_the_handed_file_again(base_task):
    ep = _episode(base_task, mode="single")
    handed = f"{base_task.task_id}.rdoc.json"
    (base_name, _), = base_task.files.items()
    assert ep.execute(ToolCall("list_alignments", {}))["count"] == 0   # the design is not this file's
    there = _open(ep, base_name)
    assert there["ok"] is True, there
    assert there["opened"] == base_name and there["graded"] == handed
    assert there["state"]["summary"]["document"] == base_name
    assert ep.other_name == base_name and ep.desk is ep.other
    # every tool now answers for the base drawing, which holds the line as its own design
    assert ep.execute(ToolCall("get_document_state", {}))["summary"]["document"] == base_name
    listed = ep.execute(ToolCall("list_alignments", {}))
    assert [a["name"] for a in listed["alignments"]] == [base_task.brief.alignment_name]
    back = _open(ep, handed)
    assert back["ok"] is True and back["opened"] == back["graded"] == handed
    assert back["state"]["summary"]["document"] == handed
    assert ep.other is None and ep.desk is ep.session
    assert ep.execute(ToolCall("list_alignments", {}))["count"] == 0
    _folder_unnamed(ep, there, listed, back, ep.state_summary())
    assert ep.state.faults == 0


def test_open_document_is_no_tool_of_a_task_whose_scope_does_not_open_it(task):
    designer = generate_task(15000, curves=1, task_type="annotate-base", revise="radius")
    for other in (task, designer):   # each ships a base file, and neither carries both marks
        ep = _episode(other, mode="single")
        (name, _), = other.files.items()
        for call in (ToolCall("open_document", {"path": name}), ToolCall("reload_references", {})):
            result = ep.execute(call)
            assert result["ok"] is False and result["error"]["type"] == "unknown_command"
            assert "is not a tool of this episode" in result["error"]["message"]
        assert ep.other is None and ep.opened == []


def test_a_change_in_the_base_drawing_is_written_to_its_file_in_the_folder_and_nowhere_else(
        base_task, base_answer, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)   # a stray write would land in the working directory
    ep = _episode(base_task, mode="single")
    folder = Path(ep.root.real)
    (base_name, _), = base_task.files.items()
    shipped = json.dumps(base_task.files[base_name], sort_keys=True)
    outside = (base_answer / base_name).read_text()
    revision = base_task.brief.deliverable["revision"]   # a curve's radius, 'from' to 'to'
    change = dict(next(p for c, p in solution_commands(base_task) if c == "modify_alignment"))

    def radii():
        saved = json.loads((folder / base_name).read_text())
        return [pi["radius"] for pi in saved["design"]["alignments"][change["name"]]["pis"]]

    assert revision["from"] in radii() and revision["to"] not in radii()
    assert _open(ep, base_name)["ok"] is True
    # a query, and a command the engine refuses, write nothing
    before = (folder / base_name).read_text()
    assert ep.execute(ToolCall("list_alignments", {}))["ok"] is True
    assert ep.execute(ToolCall("modify_alignment", dict(change, name="NO-SUCH-LINE")))["ok"] is False
    assert (folder / base_name).read_text() == before
    done = ep.execute(ToolCall("modify_alignment", change))
    assert done["ok"] is True, done
    assert revision["to"] in radii() and revision["from"] not in radii()
    # the base file is the only file there, as it was: no sheet file, no journal, no copy
    assert sorted(p.name for p in folder.iterdir() if p.name != "renders") == sorted(base_task.files)
    assert [p for p in folder.rglob("*") if p.is_file()] == [folder / base_name]
    assert list(tmp_path.iterdir()) == []
    assert (base_answer / base_name).read_text() == outside
    assert json.dumps(base_task.files[base_name], sort_keys=True) == shipped
    _folder_unnamed(ep, done)


def test_the_trajectory_of_an_episode_that_opened_the_base_drawing_names_no_folder(
        base_task, tmp_path):
    r = run_episode(base_task, OracleAgent(), out_root=tmp_path)
    assert r.effective_score == 100.0 and r.faults == 0
    text = Path(r.path).read_text()
    assert "roaddraft-episode-" not in text and os.getcwd() not in text
    first = read_episode(r.path)["turns"][0]
    opened = [x for x in first["results"] if x["name"] == "open_document"]
    assert [x["opened"] for x in opened] == [next(iter(base_task.files)), f"{base_task.task_id}.rdoc.json"]
