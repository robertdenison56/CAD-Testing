"""``roaddraft-mcp --root``: a benchmarked model's files held to its episode folder.

The reference solutions sit in the same repository as an episode, under the
names its start documents carry, and a tool that takes a path took any path:
absolute, through '..', or through a link. So a model could open, attach or
import an answer, and write anywhere. Under a root (document/confine.py) every
one of those is refused, a path inside still works however it is written, and
the paths in results are relative to the working directory, so the model is
not told where it is. Without a root nothing changes: the GUI and the desktop
app read and write where their user points them.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from roaddraft.api.session import Session
from roaddraft.document import confine
from roaddraft.mcp import config as mcpconfig
from roaddraft.mcp import server as mcpserver
from roaddraft.mcp.server import RoadDraftMCP
from roaddraft.probes import tasks
from roaddraft.runners import McpServer, setup_probe

A_PIS = [[1000, 1000], [1814.359354, 1000, 800], [2433.012702, 1357.179677]]
OUTSIDE = "is outside the folder this session may read and write"


def basefile(path: Path) -> Path:
    base = Session(project_name="Base")
    base.execute("draw_line", {"space": "model", "start": [0, 0], "end": [100, 0]})
    base.query("save_document", {"path": str(path)})
    return path


def landxml() -> str:
    s = Session()
    s.execute("create_alignment", {"name": "ALIGN-1", "pis": A_PIS})
    return s.query("export_landxml", {"include_xml": True, "path": os.devnull})["xml"]


@dataclass
class World:
    tmp: Path
    outside: Path      # where the answers are
    episode: Path      # the root
    project: Path      # the server's working directory, where the start document is
    sheet: Path


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = basefile(outside / "answer.rdoc.json")
    (outside / "answer.xml").write_text(landxml())
    episode = tmp_path / "episode"
    project = episode / "project"
    project.mkdir(parents=True)
    basefile(project / "base.rdoc.json")
    (project / "design.xml").write_text(landxml())
    (project / "linked.rdoc.json").symlink_to(secret)                  # a file link out
    (project / "linked.xml").symlink_to(outside / "answer.xml")
    (episode / "out").symlink_to(outside, target_is_directory=True)   # a folder link out
    start = Session(project_name="Sheet")
    start.execute("create_alignment", {"name": "ALIGN-1", "pis": A_PIS})
    start.execute("create_sheet", {"name": "C-1", "size": "ANSI_D"})
    sheet = project / "sheet.rdoc.json"
    start.query("save_document", {"path": str(sheet)})
    monkeypatch.chdir(project)
    return World(tmp_path, outside, episode, project, sheet)


def server(w: World, rooted: bool = True) -> RoadDraftMCP:
    return RoadDraftMCP(Session.load(w.sheet, out_dir=w.episode / "renders"),
                        autosave=True, trace=str(w.episode / "trace.jsonl"),
                        root=str(w.episode) if rooted else None)


def call(srv: RoadDraftMCP, tool: str, **arguments) -> dict:
    return srv.call_tool(tool, arguments)


def text(result: dict) -> str:
    return "\n".join(b["text"] for b in result["content"] if b["type"] == "text")


def body(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


def outside_files(w: World):
    return sorted(p.name for p in w.outside.iterdir())


#: every way a path can lead out of the episode, as written from project/
def escapes(w: World, name: str):
    return [str(w.outside / name),               # absolute
            f"../../outside/{name}",             # through '..'
            f"../out/{name}"]                    # through a folder link


# ------------------------------------------------------------------- reads


def test_attaching_an_answer_is_refused_however_the_path_is_written(world):
    srv = server(world)
    for path in escapes(world, "answer.rdoc.json") + ["linked.rdoc.json"]:
        r = call(srv, "attach_reference", name="PEEK", path=path)
        assert r["isError"], path
        error = body(r)["error"]
        assert error["message"] == f"cannot attach reference: {path!r} {OUTSIDE}"
    assert srv.session.doc.references == {}


def test_opening_an_answer_is_refused(world):
    srv = server(world)
    for path in escapes(world, "answer.rdoc.json") + ["linked.rdoc.json"]:
        r = call(srv, "open_document", path=path)
        assert r["isError"], path
        assert text(r) == (f"cannot open {path}: {path!r} {OUTSIDE} "
                           f"({confine.OutsideRoot.hint})")
    assert srv.session.doc._path == world.sheet.resolve()   # still the start
    assert srv.home == world.sheet.resolve()


def test_importing_an_answer_as_landxml_is_refused(world):
    srv = server(world)
    for path in escapes(world, "answer.xml") + ["linked.xml"]:
        r = call(srv, "import_landxml", path=path, on_conflict="replace")
        assert r["isError"], path
        error = body(r)["error"]
        assert error["message"] == f"{path!r} {OUTSIDE}"
        assert error["hint"] == confine.OutsideRoot.hint


def test_a_reference_moved_out_by_modify_reference_is_refused_and_stays_put(world):
    srv = server(world)
    assert not call(srv, "attach_reference", name="BASE", path="base.rdoc.json")["isError"]
    for path in escapes(world, "answer.rdoc.json"):
        r = call(srv, "modify_reference", name="BASE", changes={"path": path})
        assert r["isError"] and OUTSIDE in body(r)["error"]["message"]
    ref = body(call(srv, "list_references"))["references"][0]
    assert ref["path"] == "base.rdoc.json" and ref["status"] == "loaded"


def test_a_stored_reference_that_leads_out_does_not_load(world):
    # a document handed over with a reference out of the folder: it does not
    # load, and list_references does not print where it would have led
    host = Session(project_name="Host")
    host.execute("attach_reference", {"name": "OUT", "path": str(world.outside / "answer.rdoc.json")})
    host.query("save_document", {"path": str(world.project / "host.rdoc.json")})
    srv = server(world)
    assert not call(srv, "open_document", path="host.rdoc.json")["isError"]
    ref = body(call(srv, "list_references"))["references"][0]
    assert ref["status"] == "error" and OUTSIDE in ref["error"]
    assert ref["resolved_path"] == str(world.outside / "answer.rdoc.json")  # as stored, not resolved
    assert ref["entities"] == 0
    found = body(call(srv, "find_entities", include_references=True))
    assert found["ok"] and found["total"] == 0          # the answer's line is not searched
    with confine.held(None):                             # the same document, not held
        assert srv.session.query("find_entities", {"include_references": True})["total"] == 1


def test_a_path_inside_the_folder_works_however_it_is_written(world):
    srv = server(world)
    for name, path in (("A", "base.rdoc.json"), ("B", str(world.project / "base.rdoc.json")),
                       ("C", "../project/base.rdoc.json")):
        r = call(srv, "attach_reference", name=name, path=path)
        assert not r["isError"], text(r)
    refs = body(call(srv, "list_references"))["references"]
    assert [r["resolved_path"] for r in refs] == ["base.rdoc.json"] * 3
    r = call(srv, "import_landxml", path="design.xml", on_conflict="replace")
    assert not r["isError"], text(r)
    r = call(srv, "open_document", path="base.rdoc.json")
    assert not r["isError"] and body(r)["opened"] == "base.rdoc.json"


# ------------------------------------------------------------------ writes


WRITERS = [("save_document", {}, "w.rdraft"),
           ("save_journal", {}, "w.jsonl"),
           ("render_model", {}, "w.png"),
           ("render_sheet", {"sheet": "C-1"}, "w.png"),
           ("export_dxf", {}, "w.dxf"),
           ("export_pdf", {}, "w.pdf"),
           ("print_pdf", {"space": "model"}, "w.pdf"),
           ("export_landxml", {}, "w.xml")]


@pytest.mark.parametrize("tool,extra,name", WRITERS, ids=[w[0] for w in WRITERS])
def test_nothing_is_written_outside_the_folder(world, tool, extra, name):
    srv = server(world)
    before = outside_files(world)
    for path in escapes(world, name):
        r = call(srv, tool, path=path, **extra)
        assert r["isError"], path
        error = body(r)["error"]
        assert error["message"] == f"{path!r} {OUTSIDE}"
        assert error["hint"] == confine.OutsideRoot.hint
    assert outside_files(world) == before
    r = call(srv, tool, path=f"../renders/{name}", **extra)   # inside: fine
    assert not r["isError"], text(r)
    assert body(r)["path"] == f"../renders/{name}"


def test_a_link_cannot_carry_a_save_out(world):
    srv = server(world)
    (world.project / "w.rdraft").symlink_to(world.outside / "planted.rdraft")
    r = call(srv, "save_document", path="w")   # gains .rdraft: the link
    assert r["isError"] and OUTSIDE in body(r)["error"]["message"]
    assert not (world.outside / "planted.rdraft").exists()


# ------------------------------------------------------------- what it shows


def test_results_and_the_trace_show_no_absolute_path(world):
    srv = server(world)
    shown = []
    shown.append(call(srv, "attach_reference", name="BASE", path="base.rdoc.json"))
    shown.append(call(srv, "attach_reference", name="GONE", path="missing.rdoc.json"))
    shown.append(call(srv, "list_references"))
    shown.append(call(srv, "render_model"))
    shown.append(call(srv, "render_sheet", sheet="C-1"))
    shown.append(call(srv, "save_document", path="copy"))
    shown.append(call(srv, "open_document", path="copy.rdraft"))
    shown.append(call(srv, "import_landxml", path="nowhere.xml"))
    words = "\n".join(text(r) for r in shown)
    for form in {str(world.tmp), os.path.realpath(world.tmp)}:
        assert form not in words
        assert form not in (world.episode / "trace.jsonl").read_text()
    render = shown[3]
    assert body(render)["path"] == "../renders/model.png"
    assert render["content"][1]["type"] == "image"     # read from the real path
    assert body(shown[5])["path"] == "copy.rdraft"
    missing = body(shown[1])["error"]
    assert missing["message"] == ("cannot attach reference: file not found: "
                                  "missing.rdoc.json (looked in .)")
    assert "host document's folder (.)" in missing["hint"]


def test_show_rewrites_paths_inside_the_root_and_nothing_else(tmp_path):
    folder = tmp_path / "CAD Testing" / "ep"          # the repository's own name has a space
    root = confine.Root(folder)
    real = os.path.realpath(folder)
    base = os.path.join(real, "project")
    assert root.show(f"{real}/project/a b.rdraft", base) == "a b.rdraft"
    assert root.show(f"looked in {real}/project)", base) == "looked in .)"
    assert root.show(f"'{real}/renders/x.png'", base) == "'../renders/x.png'"
    assert root.show(real, base) == ".."
    assert root.show(f"{real}x/y and {tmp_path}/other", base) == f"{real}x/y and {tmp_path}/other"
    assert root.show({"a": [f"{real}/q", 3, None]}, base) == {"a": ["../q", 3, None]}


# ------------------------------------------------------------ without a root


def test_without_a_root_nothing_is_held(world):
    srv = server(world, rooted=False)
    secret = str(world.outside / "answer.rdoc.json")
    assert not call(srv, "attach_reference", name="A", path=secret)["isError"]
    assert not call(srv, "attach_reference", name="B", path="../../outside/answer.rdoc.json")["isError"]
    assert not call(srv, "attach_reference", name="C", path="linked.rdoc.json")["isError"]
    refs = body(call(srv, "list_references"))["references"]
    assert refs[0]["resolved_path"] == secret
    assert not call(srv, "import_landxml", path=str(world.outside / "answer.xml"),
                    on_conflict="replace")["isError"]
    r = call(srv, "save_document", path=str(world.outside / "w.rdraft"))
    assert not r["isError"] and body(r)["path"] == str(world.outside / "w.rdraft")
    r = call(srv, "render_model")
    assert body(r)["path"] == str(world.episode / "renders" / "model.png")
    assert not call(srv, "open_document", path=secret)["isError"]


def test_the_engine_holds_nothing_outside_a_tool_call(world):
    s = Session()
    assert confine.current() is None
    r = s.execute("attach_reference", {"name": "A", "path": str(world.outside / "answer.rdoc.json")})
    assert r["ok"]


# ------------------------------------------------------- the server and runner


def test_the_runner_starts_every_episode_held_to_its_folder(tmp_path):
    probe = next(p for p in tasks.PROBES if p.start == "blank")
    outside = tmp_path / "answers"
    outside.mkdir()
    basefile(outside / "answer.rdoc.json")
    setup = setup_probe(tmp_path / "run" / probe.id, probe,
                        [sys.executable, "-m", "roaddraft.mcp.server"])
    assert setup.cmd[-2:] == ["--root", str(setup.folder)]
    srv = McpServer(setup.cmd, cwd=setup.folder / "project", log=setup.folder / "server.log")
    try:
        r = srv.call("attach_reference", {"name": "PEEK", "path": str(outside / "answer.rdoc.json")})
        assert r.is_error and OUTSIDE in r.text
        r = srv.call("open_document", {"path": "../../../answers/answer.rdoc.json"})
        assert r.is_error and OUTSIDE in r.text
        r = srv.call("render_model", {})
        assert not r.is_error and json.loads(r.text)["path"] == "../renders/model.png"
        assert r.images   # the server read the render by its real path
    finally:
        srv.close()
    # the refusals echo the path the model gave; where the episode is, never
    trace = (setup.folder / "trace.jsonl").read_text()
    assert str(outside / "answer.rdoc.json") in trace
    for form in {str(setup.folder), os.path.realpath(setup.folder)}:
        assert form not in trace


def test_the_server_moves_into_its_root_when_started_elsewhere(world, monkeypatch, capsys):
    monkeypatch.chdir(world.tmp)
    doc = os.path.relpath(world.sheet, world.tmp)
    assert mcpserver.main(["--root", "episode", "--doc", doc, "--list-tools"]) == 0
    assert os.getcwd() == os.path.realpath(world.episode)
    assert "open_document" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        mcpserver.main(["--root", str(world.tmp / "no-such-folder"), "--list-tools"])


def test_a_client_registration_carries_the_root(tmp_path):
    args = mcpconfig.server_args(doc=str(tmp_path / "d.rdraft"), root=str(tmp_path))
    assert args[-2:] == ["--root", str(tmp_path.resolve())]
    assert "--root" not in mcpconfig.server_args(doc=str(tmp_path / "d.rdraft"))
