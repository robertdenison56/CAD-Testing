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
  GET  /api/events           SSE stream; fires whenever the document changes
  GET  /render/<ref>.png     live render of 'model' or a sheet id/name

Every mutation bumps a revision; the canvas re-renders on the SSE signal, so
the browser behaves like a CAD window: type a command, see the sheet change.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import io
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from roaddraft.api.lines import route_line
from roaddraft.api.session import Session
from roaddraft.core import colors as colorlib
from roaddraft.document.document import LINETYPES
from roaddraft.render import mpl as mpl_render

STATIC_DIR = Path(__file__).parent / "static"
RENDER_CACHE_MAX = 12


class WebApp:
    """Owns the session, a revision counter, and the render cache."""

    def __init__(self, session: Session):
        self.session = session
        self.lock = threading.RLock()
        self.change = threading.Condition()
        self.rev = 0
        self._cache = {}

    # ------------------------------------------------------------- changes

    def bump(self):
        with self.change:
            self.rev += 1
            self.change.notify_all()

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
        return self._run_tracked(lambda: self.session.query(query, params))

    def line(self, line, space):
        return self._run_tracked(
            lambda: route_line(self.session, line, space or "model"))

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
        out = []
        for a in doc.design.alignments.values():
            st = a.stations()
            out.append({
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
                   dark=False):
        """Returns (png_bytes, meta) or (None, None). meta carries the
        pixel->space mapping the GUI needs for click-to-draw."""
        key = (ref, self.rev, dpi, frames,
               tuple(bounds) if bounds else None, dark)
        with self.lock:
            if key in self._cache:
                return self._cache[key]
            doc = self.session.doc
            buf = io.BytesIO()
            if ref == "model":
                fig, drawn = mpl_render.model_figure(doc, bounds=bounds,
                                                     dark=dark)
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
            data, meta = self.app.render_png(ref, min(max(dpi, 30), 300),
                                             frames, bounds, dark)
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
        if url.path == "/api/execute":
            self._json(self.app.execute(body.get("command", ""),
                                        body.get("params") or {}))
        elif url.path == "/api/query":
            self._json(self.app.query(body.get("query", ""),
                                      body.get("params") or {}))
        elif url.path == "/api/line":
            self._json(self.app.line(body.get("line", ""),
                                     body.get("space") or "model"))
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


def create_server(session: Session, host="127.0.0.1", port=8787):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.app = WebApp(session)
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
                        help="directory for exports (default ./renders)")
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
            server = create_server(session, port=port + attempt)
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
