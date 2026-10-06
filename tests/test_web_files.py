"""File New / Open / Save / Save As in the GUI: which drawing is open, whether
it has unsaved changes, where its files go, and the dialogs that ask for a
path when a request carries none."""
import json
import subprocess
import threading
import urllib.request
from pathlib import Path

import pytest

from roaddraft.api.session import Session
from roaddraft.document.fileformat import journal_path
from roaddraft.web import server as web
from roaddraft.web.server import MacDialogs, WebApp, create_server


class FakeDialogs:
    """Answers each dialog with the next canned path (None = cancelled) and
    records what it was asked."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def open_path(self, folder):
        self.asked.append(("open", Path(folder)))
        return self.answers.pop(0)

    def save_path(self, folder, name):
        self.asked.append(("save", Path(folder), name))
        return self.answers.pop(0)


def gui(tmp_path, dialogs=None, **kw):
    """A WebApp as the GUI runs it: files follow the drawing."""
    drawings = tmp_path / "Drawings"
    return WebApp(Session(project_name="SR 100"), dialogs=dialogs,
                  drawings_dir=drawings, **kw), drawings


def draw(app):
    r = app.execute("draw_line", {"space": "model", "start": [0, 0],
                                  "end": [100, 50]})
    assert r["ok"], r


def saved_drawing(path, project="Elsewhere", lines=1):
    s = Session(project_name=project)
    for i in range(lines):
        s.execute("draw_line", {"space": "model", "start": [0, i],
                                "end": [10, i]})
    s.query("save_document", {"path": str(path)})
    return path


# ----------------------------------------------------------- dirty / clean


def test_a_new_drawing_is_clean_and_lives_in_the_drawings_folder(tmp_path):
    app, drawings = gui(tmp_path)
    f = app.state()["file"]
    assert f == {"path": None, "name": "Untitled", "dirty": False,
                 "folder": str(drawings),
                 "journal": str(drawings / "SR_100.jsonl")}


def test_a_change_makes_it_dirty_and_saving_makes_it_clean(tmp_path):
    app, drawings = gui(tmp_path)
    draw(app)
    assert app.state()["file"]["dirty"]
    r = app.file_action({"action": "save_as", "path": str(tmp_path / "a")})
    assert r["ok"] and r["name"] == "save_as" and r["message"] == "saved a.rdraft"
    f = app.state()["file"]
    assert f["path"] == str((tmp_path / "a.rdraft").resolve())
    assert f["name"] == "a.rdraft" and not f["dirty"]
    assert (tmp_path / "a.rdraft").is_file()
    draw(app)
    assert app.file_action({"action": "save"})["ok"]  # where it lives now
    assert not app.dirty
    assert len(Session.load(tmp_path / "a.rdraft").doc.model_entities) == 2


def test_undo_after_saving_is_a_change(tmp_path):
    app, _ = gui(tmp_path)
    draw(app)
    app.file_action({"action": "save_as", "path": str(tmp_path / "a.rdraft")})
    app.execute("undo", {})
    assert app.dirty


def test_a_typed_save_moves_the_drawing_and_leaves_it_clean(tmp_path):
    app, _ = gui(tmp_path)
    app.file_action({"action": "save_as", "path": str(tmp_path / "a.rdraft")})
    draw(app)
    resp = app.line("save copies/b.rdraft", "model")
    assert resp["result"]["ok"], resp
    f = app.state()["file"]
    assert f["path"] == str((tmp_path / "copies" / "b.rdraft").resolve())
    assert not f["dirty"]


# ----------------------------------------------------------- dialogs


def test_saving_a_never_saved_drawing_asks_where(tmp_path):
    dialogs = FakeDialogs(str(tmp_path / "picked"))
    app, drawings = gui(tmp_path, dialogs)
    draw(app)
    r = app.file_action({"action": "save"})
    assert r["ok"] and r["name"] == "save"
    assert dialogs.asked == [("save", drawings, "SR_100.rdraft")]
    assert (tmp_path / "picked.rdraft").is_file()  # the extension is added
    app.file_action({"action": "save"})  # now it knows where: no dialog
    assert len(dialogs.asked) == 1


def test_save_as_offers_the_drawings_own_folder_and_name(tmp_path):
    dialogs = FakeDialogs(None)
    app, _ = gui(tmp_path, dialogs)
    app.file_action({"action": "save_as",
                     "path": str(tmp_path / "jobs" / "SR100.rdraft")})
    app.file_action({"action": "save_as"})
    assert dialogs.asked == [("save", tmp_path / "jobs", "SR100.rdraft")]


def test_a_cancelled_dialog_changes_nothing(tmp_path):
    app, drawings = gui(tmp_path, FakeDialogs(None, None))
    draw(app)
    assert app.file_action({"action": "save"}) == {
        "ok": False, "name": "save", "cancelled": True, "warnings": []}
    assert app.file_action({"action": "open", "discard": True})["cancelled"]
    f = app.state()["file"]
    assert f["path"] is None and f["dirty"]
    assert not drawings.exists()


def test_without_a_dialog_the_answer_suggests_a_path(tmp_path):
    app, drawings = gui(tmp_path)
    r = app.file_action({"action": "save_as"})
    assert not r["ok"] and r["error"]["type"] == "no_file_dialog"
    assert r["error"]["suggestion"] == str(drawings / "SR_100.rdraft")
    r = app.file_action({"action": "open"})
    assert r["error"]["suggestion"] == f"{drawings}/"


def test_one_dialog_at_a_time(tmp_path):
    release = threading.Event()

    class Slow(FakeDialogs):
        def open_path(self, folder):
            release.wait(5)
            return None

    app, _ = gui(tmp_path, Slow())
    first = threading.Thread(target=app.file_action, args=({"action": "open"},))
    first.start()
    try:
        for _ in range(100):  # wait for the first dialog to be up
            if app._dialog_open.locked():
                break
            threading.Event().wait(0.01)
        r = app.file_action({"action": "open"})
        assert r["error"]["type"] == "dialog_open"
    finally:
        release.set()
        first.join()


# ----------------------------------------------------------- open / new


def test_open_will_not_drop_unsaved_changes_unless_told(tmp_path):
    other = saved_drawing(tmp_path / "other.rdraft", lines=3)
    app, _ = gui(tmp_path)
    draw(app)
    r = app.file_action({"action": "open", "path": str(other)})
    assert not r["ok"] and r["error"]["type"] == "unsaved_changes"
    assert "discard" in r["error"]["hint"]
    assert app.state()["model_entity_count"] == 1
    rev, generation = app.rev, app.generation
    r = app.file_action({"action": "open", "path": str(other), "discard": True})
    assert r["ok"] and r["message"] == "opened other.rdraft"
    state = app.state()
    assert state["project"] == "Elsewhere" and state["model_entity_count"] == 3
    assert state["generation"] == generation + 1 and state["rev"] > rev
    assert state["file"]["path"] == str(other.resolve())
    assert not state["file"]["dirty"]


def test_open_by_dialog(tmp_path):
    other = saved_drawing(tmp_path / "other.rdoc.json")
    dialogs = FakeDialogs(str(other))
    app, drawings = gui(tmp_path, dialogs)
    assert app.file_action({"action": "open"})["ok"]
    assert dialogs.asked == [("open", drawings)]
    assert app.state()["file"]["name"] == "other.rdoc.json"


def test_a_bad_file_is_reported_and_the_drawing_stays(tmp_path):
    junk = tmp_path / "notes.json"
    junk.write_text('{"hello": 1}')
    app, _ = gui(tmp_path)
    draw(app)
    for path in (junk, tmp_path / "missing.rdraft"):
        r = app.file_action({"action": "open", "path": str(path),
                             "discard": True})
        assert not r["ok"] and r["error"]["type"] == "open_failed", r
    assert app.state()["model_entity_count"] == 1 and app.dirty


def test_new_replaces_the_drawing(tmp_path):
    app, drawings = gui(tmp_path)
    app.file_action({"action": "save_as", "path": str(tmp_path / "a.rdraft")})
    draw(app)
    assert app.file_action({"action": "new", "project": "SR 70"})["error"][
        "type"] == "unsaved_changes"
    r = app.file_action({"action": "new", "project": "SR 70", "discard": True})
    assert r["ok"]
    state = app.state()
    assert state["project"] == "SR 70" and state["model_entity_count"] == 0
    assert state["file"]["path"] is None and not state["file"]["dirty"]
    assert state["file"]["folder"] == str(drawings)


def test_an_unknown_action(tmp_path):
    app, _ = gui(tmp_path)
    r = app.file_action({"action": "print"})
    assert r["error"]["type"] == "unknown_action"


# ----------------------------------------------------------- where files go


def test_exports_follow_the_drawing(tmp_path):
    app, drawings = gui(tmp_path)
    app.execute("create_sheet", {"name": "C-101"})
    r = app.query("export_dxf", {})
    assert Path(r["path"]) == drawings / "SR_100.dxf"
    app.file_action({"action": "save_as",
                     "path": str(tmp_path / "job" / "plan.rdraft")})
    assert Path(app.query("export_pdf", {})["path"]) == \
        tmp_path / "job" / "SR_100.pdf"
    # a relative path typed on the command line lands beside the drawing too
    r = app.line("journal plan.jsonl", "model")
    assert Path(r["result"]["path"]) == tmp_path / "job" / "plan.jsonl"
    assert app.state()["file"]["journal"] == str(
        journal_path((tmp_path / "job" / "plan.rdraft").resolve()))


def test_an_out_dir_takes_the_exports_but_not_the_drawing(tmp_path):
    out = tmp_path / "exports"
    app, _ = gui(tmp_path, out_dir=out)
    app.file_action({"action": "save_as",
                     "path": str(tmp_path / "job" / "plan.rdraft")})
    assert Path(app.query("export_dxf", {})["path"]) == out / "SR_100.dxf"
    r = app.line("save copy.rdraft", "model")
    assert Path(r["result"]["path"]) == tmp_path / "job" / "copy.rdraft"


def test_without_a_drawings_folder_the_session_keeps_its_paths(tmp_path):
    other = saved_drawing(tmp_path / "other.rdraft")
    app = WebApp(Session(out_dir=str(tmp_path / "renders")))
    assert app.session.base_dir is None
    app.file_action({"action": "open", "path": str(other)})
    assert app.session.base_dir is None
    assert app.session.out_dir == tmp_path / "renders"


def test_save_as_warns_when_a_relative_reference_is_left_behind(tmp_path):
    saved_drawing(tmp_path / "a" / "base.rdoc.json", project="Base")
    app, _ = gui(tmp_path)
    app.file_action({"action": "save_as",
                     "path": str(tmp_path / "a" / "host.rdraft")})
    r = app.execute("attach_reference", {"name": "SURVEY",
                                         "path": "base.rdoc.json"})
    assert r["ok"], r
    r = app.file_action({"action": "save_as",
                         "path": str(tmp_path / "a" / "host2.rdraft")})
    assert r["ok"] and r["warnings"] == []  # same folder: still found
    r = app.file_action({"action": "save_as",
                         "path": str(tmp_path / "b" / "host.rdraft")})
    assert r["ok"] and len(r["warnings"]) == 1
    assert "SURVEY" in r["warnings"][0]


def test_a_save_that_cannot_be_written_is_reported(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    app, _ = gui(tmp_path)
    r = app.file_action({"action": "save_as",
                         "path": str(blocker / "plan.rdraft")})
    assert not r["ok"] and r["error"]["type"] == "save_failed"


# ----------------------------------------------------------- Session paths


def test_session_relative_paths_default_to_the_working_directory(
        tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    s = Session()
    r = s.query("save_document", {"path": "here.rdraft"})
    assert Path(r["path"]) == Path("here.rdraft")
    assert (tmp_path / "here.rdraft").is_file()
    s.base_dir = tmp_path / "base"
    r = s.query("save_journal", {"path": "j.jsonl"})
    assert Path(r["path"]) == tmp_path / "base" / "j.jsonl"


def test_session_paths_expand_the_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    r = Session().query("save_document", {"path": "~/plan.rdraft"})
    assert Path(r["path"]) == tmp_path / "plan.rdraft"


# ----------------------------------------------------------- the server


@pytest.fixture()
def served(tmp_path):
    session = Session(project_name="WebTest")
    srv = create_server(session, port=0, drawings_dir=tmp_path / "Drawings")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def post(base, path, body):
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as ex:
        return ex.code, json.loads(ex.read())


def test_file_endpoint(served, tmp_path):
    status, r = post(served, "/api/file",
                     {"action": "save_as", "path": str(tmp_path / "w.rdraft")})
    assert status == 200 and r["ok"]
    with urllib.request.urlopen(served + "/api/state", timeout=10) as resp:
        f = json.loads(resp.read())["file"]
    assert f["name"] == "w.rdraft" and not f["dirty"]


def test_a_failure_inside_a_request_comes_back_as_json(served, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    status, r = post(served, "/api/query", {
        "query": "export_dxf", "params": {"path": str(blocker / "x.dxf")}})
    assert status == 500 and not r["ok"]
    assert r["error"]["type"] == "internal_error"


# ----------------------------------------------------------- macOS dialogs


def fake_osascript(monkeypatch, returncode, stdout="", stderr=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

    monkeypatch.setattr(web.subprocess, "run", run)
    return calls


def test_mac_dialog_returns_the_chosen_path(monkeypatch, tmp_path):
    calls = fake_osascript(monkeypatch, 0, stdout="/Users/x/plan.rdraft\n")
    path = MacDialogs().save_path(tmp_path / "not" / "yet", "plan.rdraft")
    assert path == "/Users/x/plan.rdraft"
    # the paths ride as arguments, never pasted into the script
    assert calls[0][-3:] == ["Save the drawing as", str(tmp_path),
                             "plan.rdraft"]


def test_mac_dialog_cancel_is_none_and_failure_raises(monkeypatch, tmp_path):
    fake_osascript(monkeypatch, 1,
                   stderr="0:17: execution error: User canceled. (-128)")
    assert MacDialogs().open_path(tmp_path) is None
    fake_osascript(monkeypatch, 1, stderr="syntax error")
    with pytest.raises(web.DialogError):
        MacDialogs().open_path(tmp_path)
