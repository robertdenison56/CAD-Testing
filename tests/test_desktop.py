"""The desktop window's pieces that run without a window: where it keeps its
log and caches, the title it shows, its file dialogs, and how it settles
unsaved changes before it closes."""
import json
import logging
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from roaddraft.api.session import Session
from roaddraft.desktop import app as desktop
from roaddraft.desktop.app import (CloseGuard, DesktopApi, WindowDialogs,
                                   follow_title, prepare_environment,
                                   serve, setup_logging, support_dirs,
                                   window_title)
from roaddraft.web.server import STATIC_DIR, WebApp


class FakeWindow:
    def __init__(self, dialog_answer=None):
        self.titles, self.scripts, self.dialogs = [], [], []
        self.destroyed = False
        self.dialog_answer = dialog_answer
        self.titled = threading.Event()
        self.asked = threading.Event()

    def set_title(self, title):
        self.titles.append(title)
        self.titled.set()

    def evaluate_js(self, script):
        self.scripts.append(script)
        self.asked.set()

    def destroy(self):
        self.destroyed = True

    def create_file_dialog(self, dialog_type, directory="", save_filename="",
                           file_types=()):
        self.dialogs.append((dialog_type, directory, save_filename, file_types))
        return self.dialog_answer


def gui(tmp_path):
    return WebApp(Session(project_name="SR 100"),
                  drawings_dir=tmp_path / "Drawings")


def draw(app):
    assert app.execute("draw_line", {"space": "model", "start": [0, 0],
                                     "end": [10, 0]})["ok"]


# ------------------------------------------------------------ setting up


def test_support_dirs_follow_the_platform(tmp_path):
    mac = support_dirs(tmp_path, "darwin")
    assert mac == {"logs": tmp_path / "Library" / "Logs" / "RoadDraft",
                   "cache": tmp_path / "Library" / "Caches" / "RoadDraft"}
    other = support_dirs(tmp_path, "linux")
    assert other["logs"].parent == tmp_path / ".roaddraft"


def test_only_a_frozen_app_moves_the_matplotlib_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("MPLCONFIGDIR", raising=False)
    prepare_environment(tmp_path, frozen=False)
    assert "MPLCONFIGDIR" not in desktop.os.environ
    prepare_environment(tmp_path, frozen=True)
    assert desktop.os.environ["MPLCONFIGDIR"] == str(tmp_path / "matplotlib")


@pytest.fixture()
def restored_logging(monkeypatch):
    """setup_logging changes process-wide state: put it all back."""
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(logging, "raiseExceptions", logging.raiseExceptions)
    yield
    for h in root.handlers[:]:
        if h not in handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


def test_the_log_takes_uncaught_exceptions(tmp_path, restored_logging):
    path = setup_logging(tmp_path / "Logs", console=True)
    assert path == tmp_path / "Logs" / "roaddraft.log"
    try:
        raise ValueError("boom in the GUI")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    thread = threading.Thread(target=lambda: 1 / 0, name="worker")
    thread.start()
    thread.join()
    text = path.read_text()
    assert "ValueError: boom in the GUI" in text
    assert "uncaught exception in thread worker" in text
    assert "ZeroDivisionError" in text


def test_without_a_console_stdout_and_stderr_go_to_the_log(tmp_path,
                                                           restored_logging):
    path = setup_logging(tmp_path, console=False)
    print("hello from a print")
    sys.stderr.write("Traceback (most recent call last):\n  oops\n")
    text = path.read_text()
    assert "INFO stdout: hello from a print" in text
    assert "ERROR stderr: Traceback (most recent call last):" in text


# ------------------------------------------------------------ the title


def test_the_title_names_the_drawing_and_marks_unsaved_changes(tmp_path):
    app = gui(tmp_path)
    assert window_title(app) == "SR 100"
    draw(app)
    assert window_title(app) == "SR 100 — Edited"
    app.file_action({"action": "save_as", "path": str(tmp_path / "plan")})
    assert window_title(app) == "plan.rdraft"


def test_the_title_follows_changes(tmp_path):
    app, window, stop = gui(tmp_path), FakeWindow(), threading.Event()
    thread = threading.Thread(target=follow_title, args=(app, window, stop),
                              daemon=True)
    thread.start()
    try:
        assert window.titled.wait(5)
        window.titled.clear()
        draw(app)
        assert window.titled.wait(5)
        assert window.titles == ["SR 100", "SR 100 — Edited"]
    finally:
        stop.set()
        app.bump()  # wake it to see stop
        thread.join(5)
    assert not thread.is_alive()


# ------------------------------------------------------------ dialogs


def test_open_dialog_starts_in_a_folder_that_exists(tmp_path):
    pytest.importorskip("webview")
    window = FakeWindow(dialog_answer=("/x/plan.rdraft",))
    path = WindowDialogs(window).open_path(tmp_path / "Drawings" / "not yet")
    assert path == "/x/plan.rdraft"
    kind, directory, _, file_types = window.dialogs[0]
    assert directory == str(tmp_path)
    from webview import FileDialog
    from webview.util import parse_file_type
    assert kind == FileDialog.OPEN
    for f in file_types:  # what pywebview would refuse
        parse_file_type(f)


def test_save_dialog_offers_the_name_and_handles_cancel(tmp_path):
    pytest.importorskip("webview")
    window = FakeWindow(dialog_answer="/x/SR_100.rdraft")
    dialogs = WindowDialogs(window)
    assert dialogs.save_path(tmp_path, "SR_100.rdraft") == "/x/SR_100.rdraft"
    assert window.dialogs[0][2] == "SR_100.rdraft"
    window.dialog_answer = None
    assert dialogs.save_path(tmp_path, "SR_100.rdraft") is None
    window.dialog_answer = ("/x/a.rdraft",)  # some platforms answer a tuple
    assert dialogs.save_path(tmp_path, "a.rdraft") == "/x/a.rdraft"


# ------------------------------------------------------------ closing


def test_a_clean_drawing_closes_at_once(tmp_path):
    guard = CloseGuard(gui(tmp_path), FakeWindow())
    assert guard.on_closing() is True
    assert guard.window.scripts == []


def test_unsaved_changes_hold_the_window_and_ask_the_page(tmp_path):
    app, window = gui(tmp_path), FakeWindow()
    guard = CloseGuard(app, window)
    draw(app)
    assert guard.on_closing() is False
    assert window.asked.wait(5)
    assert window.scripts == ["rdConfirmClose()"]
    assert not window.destroyed
    DesktopApi(guard).close_window()  # the page settled it
    assert window.destroyed and guard.settled
    assert guard.on_closing() is True  # and the window may now go


def test_the_dock_icon_is_for_development_runs_only():
    assert desktop.dock_icon_path(frozen=True) is None
    path = desktop.dock_icon_path(frozen=False)
    assert path is None or (path.is_file() and
                            path.parts[-3:] == ("build", "icons", "RoadDraft.png"))


def test_the_desktop_app_imports_without_matplotlib():
    """The app points matplotlib's cache folder before matplotlib loads, so
    importing it (and the roaddraft package) must not load matplotlib."""
    import subprocess
    code = ("import sys, roaddraft.desktop.app; "
            "print('matplotlib' in sys.modules); "
            "from roaddraft import Session, Document; "
            "print(Session.__name__, Document.__name__)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True).stdout.split()
    assert out == ["False", "Session", "Document"]


def test_the_page_sees_only_close_window():
    api = DesktopApi(CloseGuard(None))
    assert [n for n in dir(api) if not n.startswith("_")] == ["close_window"]


def test_the_page_can_settle_a_close():
    html = (STATIC_DIR / "index.html").read_text()
    assert "async function rdConfirmClose()" in html
    assert "window.pywebview.api.close_window()" in html


# ------------------------------------------------------------ the server


def test_serve_runs_the_gui_on_a_free_port(tmp_path):
    server, url = serve(Session(project_name="Served"), tmp_path / "Drawings")
    try:
        assert server.server_address[1] != 0
        assert url == f"http://127.0.0.1:{server.server_address[1]}/"
        with urllib.request.urlopen(url + "api/state", timeout=10) as resp:
            state = json.loads(resp.read())
        assert state["project"] == "Served"
        assert state["file"]["folder"] == str(tmp_path / "Drawings")
    finally:
        server.shutdown()
        server.server_close()
