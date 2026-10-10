"""The RoadDraft GUI: a local web application over the same Session tool
surface the AI and the terminal REPL use (PRD M3 thin viewer, first slice of
the M2 session server).

Standard library only (ThreadingHTTPServer + Server-Sent Events): no web
framework. The browser gets:

  GET  /                     the single-page UI
  GET  /api/state            light state: rev, spaces, layers, counts
  GET  /api/manifest         full tool manifest (schemas + examples + aliases)
  POST /api/execute          {command, params} -> command bus
  POST /api/query            {query, params}   -> queries/exports
  POST /api/line             {line, space}     -> human command-line grammar
  POST /api/file             {action, path?, project?, discard?} -> File
                             New / Open / Save / Save As (a dialog when no path)
  POST /api/select           {space, corners, crossing?} -> the entities a
                             dragged window (or crossing) box selects; GUI
                             only, so not on the agents' tool surface
  POST /api/chain            {ids, tolerance?} -> the chain of lines, arcs and
                             polylines those elements belong to, in order (the
                             Station tool's pick; GUI only)
  GET  /api/events          SSE stream; fires whenever the document changes
  GET  /render/<ref>.png     live render of 'model' or a sheet id/name

Every mutation bumps a revision; the canvas re-renders on the SSE signal, so
the browser behaves like a CAD window: type a command, see the sheet change.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session, _slug
from roaddraft.core import colors as colorlib
from roaddraft.document.document import LINETYPES
from roaddraft.document.fileformat import journal_path
from roaddraft.document.references import resolve_reference_path
from roaddraft.render import mpl as mpl_render

STATIC_DIR = Path(__file__).parent / "static"
RENDER_CACHE_MAX = 12

#: Where the GUI keeps a drawing's files until it is first saved.
DRAWINGS_DIR = Path.home() / "Documents" / "RoadDraft"


class WebApp:
    """Owns the session, a revision counter, and the render cache.

    It also owns which drawing is open. File ▸ New and Open swap the session
    for another one, and ``saved_rev`` remembers the revision last opened or
    saved, so ``dirty`` means changed since then.

    Given a ``drawings_dir``, a drawing's files follow it: relative paths and
    default-named exports land beside the drawing (in ``drawings_dir`` until
    it is first saved), and exports go to ``out_dir`` instead when one is
    given. Without one the session keeps its own paths, as the tests expect.
    ``dialogs`` asks a person for a file path when a request carries none."""

    def __init__(self, session: Session, dialogs=None, drawings_dir=None,
                 out_dir=None):
        self.session = session
        self.lock = threading.RLock()
        self.change = threading.Condition()
        self.rev = 0
        self.saved_rev = 0
        self.generation = 0  # bumps each time a different drawing is opened
        self._cache = {}
        self.dialogs = dialogs
        self.drawings_dir = Path(drawings_dir) if drawings_dir else None
        self.out_dir = Path(out_dir) if out_dir else None
        self._dialog_open = threading.Lock()
        self._place_files()

    # ------------------------------------------------------------- changes

    def bump(self, saved=False):
        with self.change:
            self.rev += 1
            if saved:
                self.saved_rev = self.rev
            self.change.notify_all()

    @property
    def dirty(self) -> bool:
        with self.change:
            return self.rev != self.saved_rev

    def _run_tracked(self, fn):
        """Run a session call under the lock; bump rev if the journal grew."""
        with self.lock:
            before = len(self.session.bus.journal)
            result = fn()
            changed = len(self.session.bus.journal) != before
        if changed:
            self.bump()
        return result

    def execute(self, command, params):
        return self._run_tracked(lambda: self.session.execute(command, params))

    def query(self, query, params):
        return self._run_tracked(
            lambda: self._note_save(self.session.query(query, params)))

    def select_window(self, body):
        """The entities a box dragged in the Select tool takes in."""
        from roaddraft.document.window_select import window_ids
        space = body.get("space") or "model"
        try:
            (ax, ay), (bx, by) = [[float(v) for v in c] for c in body["corners"]]
        except (KeyError, TypeError, ValueError):
            return {"ok": False, "error": {
                "type": "invalid_params",
                "message": "corners must be two [x, y] points"}}
        with self.lock:
            doc = self.session.doc
            resolved = doc.resolve_space(space)
            if resolved is None:
                return {"ok": False, "error": {
                    "type": "query_failed", "message": f"space {space!r} not found"}}
            entities = resolved[1]
            ids = window_ids(doc, entities, [ax, ay], [bx, by],
                             crossing=bool(body.get("crossing")))
            rows = [{"id": i, "entity": entities[i].to_dict(),
                     "bbox": list(entities[i].bbox(doc))} for i in ids]
        return {"ok": True, "count": len(rows), "entities": rows}

    def line(self, line, space):
        def run():
            resp = route_line(self.session, line, space or "model")
            if isinstance(resp, dict) and resp.get("kind") == "result":
                self._note_save(resp.get("result"))
            return resp
        return self._run_tracked(run)

    def chain(self, body):
        """The chain of linework the picked elements belong to, in order --
        what the Station tool stations -- with each element for the highlight."""
        from roaddraft.commands.handlers import CommandFault, chain_elements
        ids = body.get("ids")
        if not isinstance(ids, list) or not ids or \
                not all(isinstance(i, str) for i in ids):
            return {"ok": False, "error": {
                "type": "invalid_params", "message": "ids must be a list of entity ids"}}
        with self.lock:
            doc = self.session.doc
            try:
                order, warnings = chain_elements(
                    doc, ids, float(body.get("tolerance") or 1.0))
            except CommandFault as fault:
                return {"ok": False, "error": {
                    "type": "query_failed", "message": str(fault), "hint": fault.hint}}
            rows = [{"id": i, "entity": doc.find_entity(i)[1].to_dict()} for i in order]
        return {"ok": True, "ids": order, "entities": rows, "warnings": warnings}

    def _note_save(self, result):
        """A save_document that went through, such as 'save PATH' typed on the
        command line, leaves the drawing clean and living where it was written.
        Runs under the lock, so no command can slip in between."""
        if isinstance(result, dict) and result.get("ok") \
                and result.get("name") == "save_document":
            self._place_files()
            self.bump(saved=True)
        return result

    # --------------------------------------------------------------- files

    def file_action(self, body: dict) -> dict:
        """File ▸ New / Open / Save / Save As. Without a ``path`` the person
        is asked with a file dialog. A dialog closed without a choice answers
        ``{"ok": false, "cancelled": true}``."""
        action = body.get("action", "")
        try:
            if action == "new":
                return self.new_document(str(body.get("project") or "Untitled"),
                                         discard=bool(body.get("discard")))
            if action == "open":
                return self.open_document(body.get("path"),
                                          discard=bool(body.get("discard")))
            if action == "save":
                return self.save_document()
            if action == "save_as":
                return self.save_document_as(body.get("path"))
        except _FileFault as fault:
            return fault.result(action)
        return _FileFault("unknown_action", f"unknown file action {action!r}",
                          hint="new, open, save or save_as").result(action)

    def new_document(self, project: str, discard=False) -> dict:
        self._check_unsaved(discard, "start a new drawing")
        self._replace(Session(project_name=project, out_dir=self.session.out_dir))
        return {"ok": True, "name": "new", "message": f"new drawing: {project}",
                "warnings": []}

    def open_document(self, path=None, discard=False) -> dict:
        self._check_unsaved(discard, "open another drawing")
        if path is None:
            path = self._ask_open()
            if path is None:
                return _cancelled("open")
        path = self._resolve(path)
        if not path.is_file():
            raise _FileFault("open_failed", f"no file at {path}")
        try:
            session = Session.load(path, out_dir=self.session.out_dir)
        except Exception as ex:  # report a bad file; never take the GUI down
            raise _FileFault("open_failed", f"could not open {path.name}: {ex}")
        self._replace(session)
        return {"ok": True, "name": "open", "message": f"opened {path.name}",
                "path": str(session.doc._path), "warnings": []}

    def save_document(self) -> dict:
        """Save where the drawing lives; a drawing never saved asks where."""
        host = self.session.doc._path
        if host is None:
            return self.save_document_as(None, action="save")
        return self._save_to(Path(host), "save")

    def save_document_as(self, path=None, action="save_as") -> dict:
        if path is None:
            path = self._ask_save()
            if path is None:
                return _cancelled(action)
        return self._save_to(self._resolve(path), action)

    def _save_to(self, path: Path, action: str) -> dict:
        with self.lock:
            found = self._found_references()
            try:
                result = self.session.query("save_document", {"path": str(path)})
            except OSError as ex:
                raise _FileFault("save_failed", f"could not save {path.name}: "
                                 f"{ex.strerror or ex}")
            if not result.get("ok"):
                return result
            lost = sorted(found - self._found_references())
            self._place_files()
            self.bump(saved=True)
        saved = Path(result["path"])
        result = dict(result, name=action, message=f"saved {saved.name}")
        result["warnings"] = [
            f"reference {name} is not found from {saved.parent}: a relative "
            f"reference path follows the drawing, so copy the basefile beside "
            f"it or attach it again" for name in lost]
        return result

    def _replace(self, session: Session):
        with self.lock:
            self.session = session
            self._cache.clear()
            self.generation += 1
            self._place_files()
            self.bump(saved=True)

    def _check_unsaved(self, discard: bool, doing: str):
        if not discard and self.dirty:
            raise _FileFault(
                "unsaved_changes", f"{self._file_name()} has unsaved changes",
                hint=f"save it first, or pass discard=true to {doing} anyway")

    def _found_references(self) -> set:
        doc = self.session.doc
        return {ref.name for ref in doc.references.values()
                if resolve_reference_path(doc, ref).exists()}

    def _home(self) -> Path:
        """The folder this drawing's files belong in."""
        host = self.session.doc._path
        if host is not None:
            return Path(host).parent
        return self.drawings_dir or self.session.out_dir

    def _place_files(self):
        if self.drawings_dir is None:
            return
        home = self._home()
        self.session.base_dir = home
        self.session.out_dir = self.out_dir or home

    def _resolve(self, path) -> Path:
        p = Path(path).expanduser()
        return p if p.is_absolute() else self._home() / p

    def _file_name(self) -> str:
        host = self.session.doc._path
        return Path(host).name if host else "Untitled"

    def _default_save_name(self) -> str:
        host = self.session.doc._path
        if host is not None:
            return Path(host).name
        return _slug(self.session.doc.meta["project_name"]) + ".rdraft"

    def _ask_open(self) -> Optional[str]:
        start = self._home()
        return self._ask(lambda d: d.open_path(start), suggestion=f"{start}/")

    def _ask_save(self) -> Optional[str]:
        start, name = self._home(), self._default_save_name()
        return self._ask(lambda d: d.save_path(start, name),
                         suggestion=str(start / name))

    def _ask(self, show, suggestion: str) -> Optional[str]:
        """Run a dialog outside the lock: the page keeps rendering behind it."""
        if self.dialogs is None:
            raise _FileFault("no_file_dialog", "no file dialog here; give a path",
                             suggestion=suggestion)
        if not self._dialog_open.acquire(blocking=False):
            raise _FileFault("dialog_open", "a file dialog is already open")
        try:
            return show(self.dialogs)
        except DialogError as ex:
            raise _FileFault("dialog_failed", str(ex))
        finally:
            self._dialog_open.release()

    def _file_state(self, doc) -> dict:
        host = doc._path
        home = self._home()
        return {
            "path": str(host) if host else None,
            "name": self._file_name(),
            "dirty": self.dirty,
            "folder": str(home),
            "journal": str(journal_path(
                host or home / f"{_slug(doc.meta['project_name'])}.rdraft")),
        }

    # --------------------------------------------------------------- state

    def state(self) -> dict:
        with self.lock:
            doc = self.session.doc
            def hexcolor(c):
                try:
                    return colorlib.to_hex(c)
                except ValueError:
                    return "#000000"
            return {
                "rev": self.rev,
                "generation": self.generation,
                "file": self._file_state(doc),
                "project": doc.meta["project_name"],
                "spaces": [{"ref": "model", "label": "Model"}] + [
                    {"ref": s.id, "label": s.name} for s in doc.sheets.values()],
                "current_layer": doc.settings["current_layer"],
                "blocks": sorted(doc.blocks),
                "text_styles": sorted(doc.text_styles),
                "linetypes": list(LINETYPES),
                "colors": {name: hexval for name, hexval
                           in colorlib.NAMED_HEX.items() if name != "grey"},
                "layers": [{
                    "name": layer.name,
                    "color": hexcolor(layer.color),
                    "linetype": layer.linetype,
                    "visible": layer.visible,
                    "lineweight_mm": layer.lineweight_mm,
                    "description": layer.description,
                } for layer in doc.layers.values()],
                "model_entity_count": len(doc.model_entities),
                "sheets": [{"id": s.id, "name": s.name, "size": s.size,
                            "entities": len(s.entities),
                            "viewports": len(s.viewports)}
                           for s in doc.sheets.values()],
                "references": self._reference_state(doc),
                "annotation": self._annotation_state(doc),
                "alignments": self._alignment_state(doc),
                "profiles": [{"name": pr.name, "alignment": pr.alignment,
                              "pvis": len(pr.pvis)}
                             for pr in doc.design.profiles.values()],
                "journal_length": len(self.session.bus.journal),
            }

    @staticmethod
    def _reference_state(doc):
        from roaddraft.document.references import describe_reference
        return [describe_reference(doc, ref) for ref in doc.references.values()]

    @staticmethod
    def _annotation_state(doc):
        from roaddraft.document import annotation as anno
        scale = anno.current_scale(doc)
        return {"scale": scale, "name": anno.scale_name(doc, scale),
                "scales": anno.scale_list(doc), "paper": anno.paper_defaults(doc),
                "model_sizes": anno.model_sizes(doc) or dict(anno.FIXED_MODEL_SIZES)}

    @staticmethod
    def _alignment_state(doc):
        from roaddraft.design.horizontal import pis_from_elements
        out = []
        for a in doc.design.alignments.values():
            st = a.stations()
            # the PIs the GUI edits by: as laid out, or recovered from elements
            pis = a.pis if a.source == "pis" and a.pis else pis_from_elements(a.elements)
            out.append({
                "pis": [[float(q.point[0]), float(q.point[1]), float(q.radius)]
                        for q in pis],
                "editable": bool(pis),
                "name": a.name,
                "begin_station_text": st.begin_text(),
                "end_station_text": st.end_text(),
                "station_range": f"{st.begin_text()} to {st.end_text()}",
                "length": a.length,
                "curves": len(a.curves()), "tangents": len(a.tangents()),
                "equations": len(a.equations), "source": a.source,
                "profiles": [pr.name for pr in doc.design.profiles_of(a.name)],
                "drawn": any(e.anchor and e.anchor.get("alignment") == a.name
                             and e.anchor.get("kind") == "element"
                             for e in doc.model_entities.values()),
            })
        return out

    # -------------------------------------------------------------- render

    def render_png(self, ref: str, dpi: float, frames: bool, bounds=None,
                   dark=False, aspect=None):
        """Returns (png_bytes, meta) or (None, None). meta carries the
        pixel->space mapping the GUI needs for click-to-draw. ``aspect``
        shapes a model render to the screen area it fills."""
        key = (ref, self.rev, dpi, frames,
               tuple(bounds) if bounds else None, dark, aspect)
        with self.lock:
            if key in self._cache:
                return self._cache[key]
            doc = self.session.doc
            buf = io.BytesIO()
            if ref == "model":
                fig, drawn = mpl_render.model_figure(doc, bounds=bounds,
                                                     dark=dark, aspect=aspect)
                meta = {"kind": "model", "bounds": list(drawn)}
            else:
                sheet = doc.sheet_by_ref(ref)
                if sheet is None:
                    return None, None
                fig = mpl_render.sheet_figure(doc, sheet,
                                              show_viewport_frames=frames)
                meta = {"kind": "sheet",
                        "size_in": [sheet.width_in, sheet.height_in]}
            fig.savefig(buf, format="png", dpi=dpi,
                        facecolor=fig.get_facecolor())
            mpl_render.plt.close(fig)
            result = (buf.getvalue(), meta)
            self._cache[key] = result
            while len(self._cache) > RENDER_CACHE_MAX:
                self._cache.pop(next(iter(self._cache)))
            return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def app(self) -> WebApp:
        return self.server.app

    def log_message(self, fmt, *args):  # quiet
        pass

    # ------------------------------------------------------------ plumbing

    def _json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _bytes(self, data, ctype, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------- routes

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            html = (STATIC_DIR / "index.html").read_bytes()
            self._bytes(html, "text/html; charset=utf-8")
        elif url.path == "/api/state":
            self._json(self.app.state())
        elif url.path == "/api/manifest":
            self._json(self.app.session.manifest())
        elif url.path == "/api/events":
            self._sse()
        elif url.path.startswith("/render/") and url.path.endswith(".png"):
            ref = unquote(url.path[len("/render/"):-len(".png")])
            q = parse_qs(url.query)
            dpi = float(q.get("dpi", ["130"])[0])
            frames = q.get("frames", ["1"])[0] != "0"
            bounds = None
            if "bounds" in q:
                try:
                    parts = [float(v) for v in q["bounds"][0].split(",")]
                    if len(parts) == 4 and parts[2] > parts[0] \
                            and parts[3] > parts[1]:
                        bounds = parts
                except ValueError:
                    bounds = None
            dark = q.get("theme", ["paper"])[0] == "dark"
            aspect = None  # model space: the shape of the canvas it fills
            try:
                aspect = round(min(max(float(q["aspect"][0]), 0.05), 20.0), 4)
            except (KeyError, ValueError):
                pass
            data, meta = self.app.render_png(ref, min(max(dpi, 30), 300),
                                             frames, bounds, dark, aspect)
            if data is None:
                self._json({"error": f"no space {ref!r}"}, code=404)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-RD-Kind", meta["kind"])
                if meta["kind"] == "model":
                    self.send_header("X-RD-Bounds",
                                     ",".join(f"{v:.6f}" for v in meta["bounds"]))
                else:
                    self.send_header("X-RD-Size-In",
                                     ",".join(str(v) for v in meta["size_in"]))
                self.end_headers()
                self.wfile.write(data)
        else:
            self._json({"error": "not found"}, code=404)

    def do_POST(self):
        url = urlparse(self.path)
        body = self._body()
        try:
            self._post(url.path, body)
        except Exception as ex:  # an export into a folder it cannot write, say
            self._json({"ok": False, "error": {
                "type": "internal_error",
                "message": f"{type(ex).__name__}: {ex}"}}, code=500)

    def _post(self, path, body):
        if path == "/api/execute":
            self._json(self.app.execute(body.get("command", ""),
                                        body.get("params") or {}))
        elif path == "/api/query":
            self._json(self.app.query(body.get("query", ""),
                                      body.get("params") or {}))
        elif path == "/api/line":
            self._json(self.app.line(body.get("line", ""),
                                     body.get("space") or "model"))
        elif path == "/api/select":
            self._json(self.app.select_window(body))
        elif path == "/api/file":
            self._json(self.app.file_action(body))
        elif path == "/api/chain":
            self._json(self.app.chain(body))
        else:
            self._json({"error": "not found"}, code=404)

    # ----------------------------------------------------------------- sse

    def _sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        app = self.app
        try:
            while True:
                with app.change:
                    app.change.wait(timeout=15.0)
                    rev = app.rev
                self.wfile.write(f"data: {{\"rev\": {rev}}}\n\n".encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


class _FileFault(Exception):
    """A File action that could not be done, reported in the bus's error shape."""

    def __init__(self, etype, message, hint=None, **extra):
        super().__init__(message)
        self.etype, self.hint, self.extra = etype, hint, extra

    def result(self, action) -> dict:
        error = {"type": self.etype, "message": str(self), **self.extra}
        if self.hint:
            error["hint"] = self.hint
        return {"ok": False, "name": action, "error": error, "warnings": []}


def _cancelled(action) -> dict:
    return {"ok": False, "name": action, "cancelled": True, "warnings": []}


class DialogError(RuntimeError):
    """A file dialog could not be shown."""


class MacDialogs:
    """The standard macOS Open and Save panels, asked for through osascript.
    This is how the GUI running in a browser gets real file dialogs; a
    desktop window would bring its own."""

    _OPEN = ("on run argv",
             "activate",
             "set f to choose file with prompt (item 1 of argv) "
             "default location (POSIX file (item 2 of argv))",
             "return POSIX path of f",
             "end run")
    _SAVE = ("on run argv",
             "activate",
             "set f to choose file name with prompt (item 1 of argv) "
             "default location (POSIX file (item 2 of argv)) "
             "default name (item 3 of argv)",
             "return POSIX path of f",
             "end run")

    def open_path(self, folder) -> Optional[str]:
        return self._run(self._OPEN, "Open a RoadDraft drawing",
                         existing_dir(folder))

    def save_path(self, folder, name) -> Optional[str]:
        return self._run(self._SAVE, "Save the drawing as",
                         existing_dir(folder), name)

    @staticmethod
    def _run(script, *args) -> Optional[str]:
        cmd = ["osascript"]
        for line in script:
            cmd += ["-e", line]
        proc = subprocess.run(cmd + [str(a) for a in args],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            return proc.stdout.strip() or None
        if "(-128)" in proc.stderr:  # User canceled.
            return None
        raise DialogError(proc.stderr.strip() or "osascript failed")


def existing_dir(folder) -> Path:
    """The folder, or its nearest ancestor that exists: a dialog cannot start
    in a folder that is not there yet."""
    p = Path(folder)
    while not p.is_dir() and p != p.parent:
        p = p.parent
    return p


def default_dialogs():
    """The file dialogs this machine can show the browser GUI, or None."""
    if sys.platform == "darwin" and shutil.which("osascript"):
        return MacDialogs()
    return None


def create_server(session: Session, host="127.0.0.1", port=8787, *,
                  dialogs=None, drawings_dir=None, out_dir=None):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = WebApp(session, dialogs=dialogs, drawings_dir=drawings_dir,
                        out_dir=out_dir)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="roaddraft-web",
        description="RoadDraft GUI: browser front end over the AI tool surface")
    parser.add_argument("document", nargs="?",
                        help="saved document to open (.rdraft or .rdoc.json)")
    parser.add_argument("--project", default="Untitled",
                        help="project name for a new document")
    parser.add_argument("--out-dir", default=None,
                        help="directory for exports (default: beside the "
                             "drawing, or ~/Documents/RoadDraft until it is "
                             "first saved)")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true",
                        help="don't auto-open the browser")
    ns = parser.parse_args(argv)

    if ns.document:
        session = Session.load(ns.document, out_dir=ns.out_dir)
    else:
        session = Session(project_name=ns.project, out_dir=ns.out_dir)

    port = ns.port
    server = None
    for attempt in range(20):
        try:
            server = create_server(session, port=port + attempt,
                                   dialogs=default_dialogs(),
                                   drawings_dir=DRAWINGS_DIR,
                                   out_dir=ns.out_dir)
            port = port + attempt
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit("no free port found")

    url = f"http://127.0.0.1:{port}"
    print(f"RoadDraft GUI: {url}  (Ctrl+C to stop)")
    if not ns.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
