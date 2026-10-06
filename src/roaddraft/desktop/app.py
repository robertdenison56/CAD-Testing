"""RoadDraft in a window of its own.

The page and the engine are the ones ``roaddraft-web`` serves to a browser.
Here the server runs inside this process on a free loopback port, the page
shows in a native window (pywebview: on macOS, WebKit, the engine Safari
uses), and both end when the window closes. There is nothing to start first
and nothing left running after.

Closing the window ends the program, so a drawing with unsaved changes asks
first: the window refuses to close and hands the page the same Save / Don't
Save / Cancel question File ▸ Open asks, and the page closes the window once
the changes are saved or let go.

A windowed app has no console, so it writes a log instead, and a frozen one
keeps matplotlib's font cache in its own cache folder so the font list is
built on the first launch, not on every one.
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import platform
import sys
import threading
from pathlib import Path

APP_NAME = "RoadDraft"

#: Drawings the Open dialog offers; the rest are a choice away.
OPEN_FILE_TYPES = ("RoadDraft drawings (*.rdraft;*.json)", "All files (*.*)")

log = logging.getLogger("roaddraft.desktop")


def support_dirs(home=None, system=sys.platform) -> dict:
    """Where the app keeps its log and its caches."""
    home = Path(home) if home else Path.home()
    if system == "darwin":
        return {"logs": home / "Library" / "Logs" / APP_NAME,
                "cache": home / "Library" / "Caches" / APP_NAME}
    base = home / ".roaddraft"
    return {"logs": base / "logs", "cache": base / "cache"}


def prepare_environment(cache_dir: Path, frozen: bool) -> None:
    """Run before matplotlib is imported. A frozen app keeps matplotlib's
    config and font cache in its own cache folder; a development run keeps
    using the person's own, so its renders match the other tools'.

    PyInstaller's matplotlib hook has already pointed matplotlib at a fresh
    temporary folder, which would rebuild the font list on every launch. Its
    folder is still empty here, so it goes (rmdir never removes one in use)."""
    if frozen:
        previous = os.environ.get("MPLCONFIGDIR")
        os.environ["MPLCONFIGDIR"] = str(Path(cache_dir) / "matplotlib")
        if previous:
            try:
                os.rmdir(previous)
            except OSError:
                pass


class _LogStream:
    """Stands in for the console a windowed app lacks: each line written to
    stdout or stderr (an HTTP handler's traceback, say) goes to the log."""

    def __init__(self, logger, level):
        self.logger, self.level, self._pending = logger, level, ""

    def write(self, text):
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            if line.strip():
                self.logger.log(self.level, line)
        return len(text)

    def flush(self):
        pass


def setup_logging(log_dir: Path, console: bool) -> Path:
    """Log to ``log_dir/roaddraft.log`` (rotated), uncaught exceptions too,
    and to the terminal when there is one. Without one, stdout and stderr go
    to the log as well."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "roaddraft.log"
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    if console:  # run from a terminal: show it there too
        echo = logging.StreamHandler()
        echo.setFormatter(logging.Formatter("RoadDraft: %(message)s"))
        root.addHandler(echo)

    def excepthook(etype, value, tb):
        log.critical("uncaught exception", exc_info=(etype, value, tb))

    def thread_excepthook(args):
        name = args.thread.name if args.thread else "?"
        log.critical("uncaught exception in thread %s", name,
                     exc_info=(args.exc_type, args.exc_value,
                               args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    if not console:
        logging.raiseExceptions = False  # a failing log must not write to itself
        sys.stdout = _LogStream(logging.getLogger("stdout"), logging.INFO)
        sys.stderr = _LogStream(logging.getLogger("stderr"), logging.ERROR)
    return path


def window_title(app) -> str:
    """The drawing's name, the macOS way: '<file> — Edited' while it has
    unsaved changes. A drawing never saved goes by its project name."""
    with app.lock:
        host = app.session.doc._path
        name = Path(host).name if host else app.session.doc.meta["project_name"]
    return f"{name} — Edited" if app.dirty else name


def follow_title(app, window, stop: threading.Event) -> None:
    """Keep the window title on the drawing until ``stop``: it wakes on every
    change the GUI makes, and once a second besides."""
    shown = None
    while not stop.is_set():
        title = window_title(app)
        if title != shown:
            window.set_title(title)
            shown = title
        with app.change:
            app.change.wait(timeout=1.0)


class WindowDialogs:
    """The window's own Open and Save panels, as WebApp asks for them."""

    def __init__(self, window):
        self.window = window

    def open_path(self, folder):
        import webview
        from roaddraft.web.server import existing_dir
        chosen = self.window.create_file_dialog(
            webview.FileDialog.OPEN, directory=str(existing_dir(folder)),
            file_types=OPEN_FILE_TYPES)
        return chosen[0] if chosen else None

    def save_path(self, folder, name):
        import webview
        from roaddraft.web.server import existing_dir
        chosen = self.window.create_file_dialog(
            webview.FileDialog.SAVE, directory=str(existing_dir(folder)),
            save_filename=name)
        if isinstance(chosen, (tuple, list)):
            chosen = chosen[0] if chosen else None
        return chosen or None


class CloseGuard:
    """Closing the window ends the program, so unsaved changes are settled
    first. pywebview asks ``on_closing`` on the main thread, before closing,
    and running JavaScript needs that thread free: so a dirty drawing refuses
    the close, the page is asked from another thread, and the page calls
    ``close`` once the person has saved or let the changes go."""

    def __init__(self, app, window=None):
        self.app, self.window = app, window
        self.settled = False

    def on_closing(self):
        if self.settled or not self.app.dirty:
            return True
        threading.Thread(target=self._ask_page, name="close-guard",
                         daemon=True).start()
        return False

    def _ask_page(self):
        try:
            self.window.evaluate_js("rdConfirmClose()")
        except Exception:
            log.exception("could not ask the page about unsaved changes")

    def close(self):
        self.settled = True
        self.window.destroy()


class DesktopApi:
    """What the page may ask of the window, as ``window.pywebview.api``.
    pywebview exposes every public method and walks every public attribute,
    so this keeps its state private."""

    def __init__(self, guard: CloseGuard):
        self._guard = guard

    def close_window(self):
        """The page has settled any unsaved changes: close the window."""
        self._guard.close()


def dock_icon_path(frozen: bool):
    """The app icon packaging/make_icons.py built, for the Dock while the app
    runs from a development environment (as Python, whose icon it would show
    otherwise). A built app carries its own; None when there is none to use."""
    if frozen:
        return None
    path = Path(__file__).resolve().parents[3] / "build" / "icons" / "RoadDraft.png"
    return path if path.is_file() else None


def show_dock_icon(path) -> None:
    """Put ``path`` in the Dock. AppKit work, so it runs on the main thread."""
    try:
        import AppKit
        from PyObjCTools import AppHelper
    except ImportError:
        return

    def apply():
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(path))
        if image is not None:
            AppKit.NSApplication.sharedApplication().setApplicationIconImage_(image)

    AppHelper.callAfter(apply)


def serve(session, drawings_dir, out_dir=None):
    """Start the GUI server on a free loopback port, on a daemon thread.
    Returns ``(server, url)``."""
    from roaddraft.web.server import create_server
    server = create_server(session, port=0, drawings_dir=drawings_dir,
                           out_dir=out_dir)
    threading.Thread(target=server.serve_forever, name="roaddraft-server",
                     daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="roaddraft-desktop",
        description="RoadDraft in a window of its own: the GUI without a "
                    "browser or a server to start")
    parser.add_argument("document", nargs="?",
                        help="drawing to open (.rdraft or .rdoc.json)")
    parser.add_argument("--project", default="Untitled",
                        help="project name for a new drawing")
    parser.add_argument("--out-dir", default=None,
                        help="directory for exports (default: beside the "
                             "drawing, or ~/Documents/RoadDraft until it is "
                             "first saved)")
    parser.add_argument("--debug", action="store_true",
                        help="enable the web inspector (right-click ▸ "
                             "Inspect Element)")
    frozen = bool(getattr(sys, "frozen", False))
    # A frozen app ignores arguments it does not know: macOS may add its own
    # when it launches an app.
    ns, extra = parser.parse_known_args(argv)
    if extra and not frozen:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")

    dirs = support_dirs()
    prepare_environment(dirs["cache"], frozen)
    log_path = setup_logging(dirs["logs"], console=not frozen)
    log.info("starting: Python %s on %s, frozen=%s, log %s",
             platform.python_version(), platform.platform(), frozen, log_path)

    try:
        import webview
    except ImportError:
        log.error("roaddraft-desktop needs pywebview: "
                  "pip install -e '.[desktop]'")
        print("roaddraft-desktop needs pywebview: pip install -e '.[desktop]'",
              file=sys.stderr)
        return 1

    # these import matplotlib, so they come after prepare_environment
    from roaddraft.api.session import Session
    from roaddraft.web.server import DRAWINGS_DIR

    if ns.document:
        session = Session.load(ns.document, out_dir=ns.out_dir)
    else:
        session = Session(project_name=ns.project, out_dir=ns.out_dir)
    server, url = serve(session, DRAWINGS_DIR, ns.out_dir)
    app = server.app
    log.info("GUI server at %s", url)

    guard = CloseGuard(app)
    window = webview.create_window(
        window_title(app), url, js_api=DesktopApi(guard),
        width=1360, height=860, min_size=(1024, 680),
        background_color="#16171b", text_select=True)
    guard.window = window
    app.dialogs = WindowDialogs(window)
    window.events.closing += guard.on_closing
    icon = dock_icon_path(frozen)
    if icon and sys.platform == "darwin":
        window.events.shown += lambda: show_dock_icon(icon)

    stop = threading.Event()
    threading.Thread(target=follow_title, args=(app, window, stop),
                     name="window-title", daemon=True).start()
    webview.start(debug=ns.debug)

    # The window has closed. (Quit from the menu ends the process without
    # coming back here; nothing below needs to run for that to be safe.)
    stop.set()
    server.shutdown()
    server.server_close()
    log.info("closed")
    logging.shutdown()
    # End now rather than wait on threads: pywebview leaves one waiting to
    # hand the page the answer to close_window, in a window that is gone, and
    # a windowless app would otherwise sit in the Dock.
    os._exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
