"""MCP server over stdio: every RoadDraft command and query as an agent tool.

This is the natural-language front door. The bus already carries, per command,
a description, a JSON Schema and a worked example -- which is exactly an MCP
tool definition -- so the tool list is derived from ``Session.manifest()``
rather than written twice: every command and query, no name collisions.

A tool call goes straight through the bus, so everything the engine already
guarantees still holds for an agent: schema validation with teaching errors,
atomic application, the journal, undo. A command that faults comes back as a
tool error carrying the message, the hint and a valid example -- the model
reads it and corrects itself.

Renders come back as images, so an agent can look at the sheet it just drew.

With ``--root DIR`` every file a tool reads or writes must lie inside DIR
(document/confine.py), and the paths in results are shown relative to the
working directory rather than absolute: a benchmarked model works in its
episode folder and learns nothing of where that is.

Transport is newline-delimited JSON-RPC 2.0 on stdin/stdout (the MCP stdio
transport). The official Python SDK needs 3.10+ and this project runs on 3.9,
so the protocol is implemented here with the standard library only -- the same
call the web server made. **stdout carries protocol frames only**; anything
worth saying goes to stderr.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from roaddraft import __version__
from roaddraft.api.session import Session
from roaddraft.mcp import config as mcpconfig
from roaddraft.mcp import profiles
from roaddraft.document import confine, fileformat
from roaddraft.document.fileformat import DocumentFormatError, journal_path

#: Revision of the MCP spec this server implements. The client's requested
#: version is echoed back when it sends one: only the stable core (initialize,
#: tools/list, tools/call, ping) is implemented, and that has not changed
#: across the dated revisions.
PROTOCOL_VERSION = "2025-06-18"

SERVER_INFO = {"name": "roaddraft", "title": "RoadDraft CAD engine",
               "version": __version__}

#: Session-level tools that are not bus commands.
EXTRA_TOOLS = {
    "open_document": {
        "description": "Open a RoadDraft document (.rdraft, or .rdoc.json) as "
                       "the working document, replacing the current one. Relative "
                       "reference paths in the file resolve from its own folder, "
                       "so a sheet file finds the model it references.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "required": ["path"],
                        "properties": {"path": {"type": "string", "minLength": 1,
                                                "description": "path to the document file"}}},
    },
}

#: Served only with ``--attachments DIR``: the images a task came with (a scanned
#: sheet, a markup), which a model looks at a region at a time. Not a bus query,
#: so the ranked runs' tool surface and its digest are untouched.
ATTACHMENT_TOOL = {
    "view_attachment": {
        "description": "Look at an image this task came with, such as a scanned plan "
                       "sheet or a marked-up print. With no name, lists the attachments "
                       "and their sizes in pixels. With a name, returns the image; a large "
                       "image comes back scaled down to fit, so pass region [left, top, "
                       "right, bottom] as fractions of its width and height, measured from "
                       "the top-left corner, to see part of it in full detail: [0.5, 0.5, "
                       "1, 1] is the lower-right quarter.",
        "inputSchema": {"type": "object", "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string", "minLength": 1,
                                     "description": "the attachment's file name"},
                            "region": {"type": "array", "minItems": 4, "maxItems": 4,
                                       "items": {"type": "number", "minimum": 0, "maximum": 1},
                                       "description": "[left, top, right, bottom], fractions "
                                                      "of the image from its top-left corner"}}},
    },
}

#: Longest side, in pixels, of an attachment view sent back
ATTACHMENT_MAX_PX = 1568
#: Image files an attachments folder may hold
ATTACHMENT_TYPES = (".png", ".jpg", ".jpeg")

#: Queries whose ``path`` result is an image worth showing the agent.
IMAGE_QUERIES = ("render_sheet", "render_model")

#: Largest image returned inline (bytes). Bigger renders come back as a path.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

# JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


def tool_definitions(session: Session, only: Optional[Sequence[str]] = None,
                     exclude: Optional[Sequence[str]] = None,
                     strip: Optional[Dict[str, List[str]]] = None,
                     attachments: bool = False) -> List[dict]:
    """MCP tool definitions from the command/query manifest, plus the extras.

    ``only`` keeps just those names (the eval harness's whitelist, later);
    ``exclude`` drops them. Both are applied to bus and extra tools alike.
    ``strip`` takes parameters out of a tool's schema (a profile's), and
    ``attachments`` adds ``view_attachment``.
    """
    manifest = session.manifest()
    tools: List[dict] = []
    for entry in list(manifest["commands"]) + list(manifest["queries"]):
        description = entry["description"]
        if entry.get("example"):
            description += "\nExample params: " + json.dumps(entry["example"])
        tools.append({"name": entry["name"], "description": description,
                      "inputSchema": entry["params_schema"]})
    extras = dict(EXTRA_TOOLS, **(ATTACHMENT_TOOL if attachments else {}))
    for name, spec in extras.items():
        tools.append({"name": name, "description": spec["description"],
                      "inputSchema": spec["inputSchema"]})
    for tool in tools:
        gone = (strip or {}).get(tool["name"])
        if gone:
            schema = json.loads(json.dumps(tool["inputSchema"]))
            for key in gone:
                schema.get("properties", {}).pop(key, None)
            if "required" in schema:
                schema["required"] = [k for k in schema["required"] if k not in gone]
            tool["inputSchema"] = schema
            tool["description"] = tool["description"].split("\nExample params: ")[0]
    if only:
        keep = set(only)
        tools = [t for t in tools if t["name"] in keep]
    if exclude:
        drop = set(exclude)
        tools = [t for t in tools if t["name"] not in drop]
    return tools


#: What the server tells a client at initialize: the one piece of guidance
#: every agent gets. The recorded trajectories use it as their system message.
#: Its examples are a drawing of their own, never a probe's (tests/test_help_text.py).
INSTRUCTIONS = (
    "RoadDraft is a headless 2D CAD engine for roadway plans. Model "
    "space is US survey feet, and a point is [x, y] = [easting, "
    "northing] -- the other way round from how coordinates are usually "
    "spoken, so N 7300, E 4100 is [4100, 7300]. Sheets are paper inches "
    "seen through viewports at a feet-per-inch scale. Work through the commands: "
    "each one validates its params and explains what was wrong, every "
    "change is journaled and undoable. Start with get_document_state "
    "to see what is in the document, list_commands for the full "
    "surface, and render_sheet or render_model to look at your work."
    "\n\n"
    "To annotate something, find it before you point at it. In a sheet "
    "file the design usually lives in a referenced basefile, so the "
    "document owns no geometry of its own; find_entities searches the "
    "attachments too. Filter by what a thing IS -- layer, type, or its "
    "design anchor -- rather than dumping the document: "
    "find_entities {anchor: {kind: 'offset', offset: [-15, 15]}, "
    "visible_on: 'P-202'} is the pavement edges that sheet shows. Then "
    "pass the id straight to place_callout as target_entity, and the "
    "engine puts the leader tip on the geometry. Do not compute the "
    "point yourself: the midpoint of a curve's endpoints is not on the "
    "curve, and roadway linework runs parallel a few feet apart, so a "
    "hand-computed point usually lands on the wrong line rather than on "
    "nothing. If you do pass a raw target point, read the warning that "
    "comes back -- it names what the tip actually touched."
    "\n\n"
    "Some things are not entities at all -- a station, a PC, a point at "
    "an offset. Ask the design for those: list_alignments with "
    "include_references=true names a referenced alignment "
    "'BASE:RTE-7', and station_to_xy, xy_to_station, resolve_anchor "
    "and get_design_data all accept that name and answer in host "
    "coordinates. To call one out, give place_callout a target_anchor "
    "('86+50@15R', 'PC-2'; BC-2 and EC-2 name the PC and PT too) and that "
    "alignment name. Otherwise commands "
    "do not take it: nothing can be drawn, labelled or anchored to an "
    "alignment this document does not own."
    "\n\n"
    "Plan annotation belongs on the sheet, in paper inches, not in the "
    "model. Pass the sheet as place_callout's space and still name a "
    "model target -- target_entity or target_anchor: the engine sees it "
    "through the sheet's viewport (scale and twist included) and puts "
    "the tip where it shows on the paper. 'at' then runs along the part "
    "of the entity that sheet shows, since a pavement edge runs the "
    "whole project and a sheet shows one stretch. find_entities with "
    "visible_on gives each row a sheet_point, which is where that tip "
    "will land -- use it to choose a position for the text that is "
    "clear of the linework. Never work out a viewport by hand: "
    "model_to_sheet and sheet_to_model convert, and station_to_xy and "
    "point_on_entity take a sheet and answer in paper inches as well."
    "\n\n"
    "Drafting from a description works the same way: give the engine the "
    "description, not coordinates you worked out. A bearing and distance "
    "goes in as written -- create_alignment takes start + legs (each leg a "
    "bearing, azimuth or deflection and the distance to the next PI, with "
    "the radius of the curve at the PI it starts from), draw_traverse "
    "draws lines and curves course by course, and traverse computes the "
    "points without drawing. offset_entity copies linework parallel at a "
    "distance (one entity, or a chain offset as one path), fillet rounds "
    "the corner between two lines with a curve (a curb return), and "
    "measure with along gives distances along a line, chain or alignment "
    "and square off it. key_points and snap give the exact endpoints, "
    "intersections, centers and alignment design points (PI, BC, EC) to "
    "build on. Station-and-offset drafting is draw_station_offset with the "
    "stations and offsets given ('82+00@15R'). Linework drawn through "
    "something is cut back with trim (a point on the part to cut away) or "
    "run on with extend, not redrawn from computed points; break, join, "
    "lengthen, chamfer, copy, rotate, mirror, scale and array edit what is "
    "there. create_points sets COGO points, label_segments letters bearings "
    "and distances or L1/C1 tags with line and curve tables, place_along "
    "sets blocks or points at an interval, hatch fills an area (a point "
    "inside is enough), and area and get_entity read areas, lengths, "
    "bearings and curve data off the drawing."
)


class RoadDraftMCP:
    """One MCP session over one RoadDraft ``Session``."""

    def __init__(self, session: Session, only: Optional[Sequence[str]] = None,
                 exclude: Optional[Sequence[str]] = None, autosave: bool = False,
                 trace: Optional[str] = None, root: Optional[str] = None,
                 profile: str = "default", attachments: Optional[str] = None):
        self.session = session
        self.only = list(only) if only else None
        #: the tool profile (``mcp.profiles``): what it hides joins ``exclude``
        self.profile = profile
        hidden = list(exclude or []) + profiles.exclude(profile)
        self.exclude = hidden or None
        self.strip = profiles.strip(profile)
        #: the folder of images ``view_attachment`` shows; None serves no such tool
        self.attachments = Path(attachments).resolve() if attachments else None
        self.protocol_version = PROTOCOL_VERSION
        self.autosave = autosave
        self.trace = Path(trace) if trace else None
        #: where autosave writes: the file the document was opened from. It does
        #: not follow a save_document to somewhere else (see _autosave).
        self.home = getattr(session.doc, "_path", None)
        #: the folder every tool's file access is held to (``--root``); None
        #: holds nothing
        self.root = confine.Root(root) if root else None

    # ------------------------------------------------------------- tools

    def tools(self) -> List[dict]:
        return tool_definitions(self.session, self.only, self.exclude, self.strip,
                                attachments=self.attachments is not None)

    def _kinds(self) -> Dict[str, str]:
        """``{tool name: "command" | "query" | "extra"}`` for the exposed tools."""
        manifest = self.session.manifest()
        kinds = {c["name"]: "command" for c in manifest["commands"]}
        kinds.update({q["name"]: "query" for q in manifest["queries"]})
        kinds.update({name: "extra" for name in EXTRA_TOOLS})
        if self.attachments is not None:
            kinds.update({name: "extra" for name in ATTACHMENT_TOOL})
        exposed = {t["name"] for t in self.tools()}
        return {k: v for k, v in kinds.items() if k in exposed}

    def kind_of(self, name: str) -> Optional[str]:
        """``"command"``, ``"query"`` or ``"extra"`` for an exposed tool; None otherwise."""
        return self._kinds().get(name)

    def call_tool(self, name: str, arguments: Optional[dict]) -> dict:
        """Run one tool. Returns an MCP tool result; a fault is ``isError``.
        Under a root the tool's file access is held to it, and the result is
        what the agent is shown -- and the trace keeps -- with the root's
        paths made relative; the server's own writes (autosave, the trace)
        are not held."""
        arguments = arguments or {}
        kind = self._kinds().get(name)
        if kind is None:
            return self._tool_error(
                f"unknown tool {name!r}. Call tools/list for the surface, or the "
                f"list_commands tool for the command manifest.")
        gone = sorted(k for k in self.strip.get(name, []) if k in arguments)
        if gone:
            return self._tool_error(
                f"{name} takes no {', '.join(gone)} on this server (the {self.profile} tool "
                f"profile): work out the coordinates yourself and give them")
        if name in ATTACHMENT_TOOL:
            return self._view_attachment(arguments)
        with confine.held(self.root):
            if kind == "extra":
                return self._shown(self._call_extra(name, arguments))
            result = (self.session.execute(name, arguments) if kind == "command"
                      else self.session.query(name, arguments))
        image_path = result.get("path") if result.get("ok") and name in IMAGE_QUERIES else None
        result = self._shown(result)
        self._trace(name, kind, arguments, result)
        if kind == "command" and result.get("ok"):
            self._autosave()
        content = [_text(result)]
        if image_path:
            image = _image_content(image_path)
            if image is not None:
                content.append(image)
        return {"content": content, "isError": not result.get("ok", False)}

    def _shown(self, result: dict) -> dict:
        """``result`` with every absolute path inside the root written
        relative to the working directory; as it is with no root."""
        return result if self.root is None else self.root.show(result)

    def _call_extra(self, name: str, arguments: dict) -> dict:
        if name != "open_document":
            return self._tool_error(f"unknown tool {name!r}")
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            return self._tool_error("open_document needs a path to a document file")
        try:
            confine.check(path)
            self.session = Session.load(path, out_dir=self.session.out_dir)
            self.home = getattr(self.session.doc, "_path", None)
        except confine.OutsideRoot as ex:
            return self._tool_error(f"cannot open {path}: {ex} ({ex.hint})")
        except FileNotFoundError:
            return self._tool_error(f"no such document: {path}")
        except DocumentFormatError as ex:  # not a document, or malformed JSON
            return self._tool_error(f"cannot open {path}: {ex}")
        except Exception as ex:  # failed validation
            return self._tool_error(f"cannot open {path}: {type(ex).__name__}: {ex}")
        summary = self.session.query("get_document_state", {})
        return {"content": [_text({"ok": True, "opened": str(Path(path).resolve()),
                                   "state": summary})], "isError": False}

    def _view_attachment(self, arguments: dict) -> dict:
        """``view_attachment``: list the attachments, or show one (a region of it)
        scaled to fit ``ATTACHMENT_MAX_PX``. Traced like a query."""
        from PIL import Image
        folder = self.attachments
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in ATTACHMENT_TYPES) \
            if folder.is_dir() else []
        name = arguments.get("name")
        if not name:
            listing = []
            for p in files:
                with Image.open(p) as im:
                    listing.append({"name": p.name, "size_px": list(im.size)})
            result = {"ok": True, "attachments": listing}
            self._trace("view_attachment", "query", arguments, result)
            return {"content": [_text(result)], "isError": False}
        match = [p for p in files if p.name == name]
        if not match:
            result = {"ok": False, "error": {"message": f"no attachment {name!r}; attachments: "
                                                        f"{', '.join(p.name for p in files) or 'none'}"}}
            self._trace("view_attachment", "query", arguments, result)
            return self._tool_error(result["error"]["message"])
        region = arguments.get("region") or [0, 0, 1, 1]
        left, top, right, bottom = (float(v) for v in region)
        if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
            result = {"ok": False, "error": {"message": "region is [left, top, right, bottom] "
                                                        "with left < right and top < bottom, "
                                                        "each from 0 to 1"}}
            self._trace("view_attachment", "query", arguments, result)
            return self._tool_error(result["error"]["message"])
        with Image.open(match[0]) as im:
            w, h = im.size
            box = (round(left * w), round(top * h), round(right * w), round(bottom * h))
            crop = im.convert("RGB").crop(box)
        fit = min(1.0, ATTACHMENT_MAX_PX / max(crop.size))
        if fit < 1.0:
            crop = crop.resize((max(1, round(crop.size[0] * fit)), max(1, round(crop.size[1] * fit))),
                               Image.LANCZOS)
        import io
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        result = {"ok": True, "name": name, "size_px": [w, h], "region": [left, top, right, bottom],
                  "region_px": list(box), "shown_px": list(crop.size),
                  "scale": round(fit, 4)}
        self._trace("view_attachment", "query", arguments, result)
        image = {"type": "image", "data": base64.b64encode(buf.getvalue()).decode("ascii"),
                 "mimeType": "image/png"}
        return {"content": [_text(result), image], "isError": False}

    @staticmethod
    def _tool_error(message: str) -> dict:
        return {"content": [{"type": "text", "text": message}], "isError": True}

    def _autosave(self) -> None:
        """Write the document back where it was opened from, and its journal
        beside it, after every command that changed it. An agent is asked to do
        a drafting job, not to remember to save: without this its work lives in
        memory and is gone when the client hangs up. A document that was never
        opened from a file has nowhere to go and is left alone.

        The file it was opened from stays the target even if the agent saves a
        copy elsewhere. Real models do that -- "save as" under a name of their
        own, often a relative one -- and if autosave followed them there, the
        file whoever launched the server is watching would silently go stale.
        Written directly rather than through save_document, which would move
        the document (and with it how relative references resolve)."""
        if not self.autosave or self.home is None:
            return
        fileformat.write_document(self.home, self.session.doc.to_dict())
        self.session.query("save_journal", {"path": str(journal_path(self.home))})

    def _trace(self, name: str, kind: str, arguments: dict, result: dict) -> None:
        """One line per tool call -- queries and faults too, which the journal
        does not keep -- so a run can be read back for how the agent went about
        it and what it tripped on, not only for what it left behind. The line
        carries the full result the agent was shown (see ``trace_line``), so
        the run converts to a conversation without being replayed."""
        if self.trace is None:
            return
        self.trace.parent.mkdir(parents=True, exist_ok=True)
        with self.trace.open("a") as fh:
            fh.write(json.dumps(trace_line(name, kind, arguments, result),
                                ensure_ascii=False) + "\n")

    # ---------------------------------------------------------- protocol

    def handle(self, message: dict) -> Optional[dict]:
        """Handle one JSON-RPC message. Returns None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 message")
        method = message.get("method")
        mid = message.get("id")
        if method is None:  # a response to something we never asked
            return None
        params = message.get("params") or {}
        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                name = params.get("name")
                if not isinstance(name, str):
                    return _error(mid, INVALID_PARAMS, "tools/call needs a tool name")
                result = self.call_tool(name, params.get("arguments"))
            elif method == "ping":
                result = {}
            elif method.startswith("notifications/"):
                return None
            else:
                if mid is None:
                    return None
                return _error(mid, METHOD_NOT_FOUND, f"method {method!r} is not supported; "
                                                     f"this server implements initialize, "
                                                     f"tools/list, tools/call and ping")
        except Exception as ex:  # never take the server down over one call
            if mid is None:
                return None
            return _error(mid, INTERNAL_ERROR, f"{type(ex).__name__}: {ex}")
        if mid is None:
            return None
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _initialize(self, params: dict) -> dict:
        requested = params.get("protocolVersion")
        if isinstance(requested, str) and requested:
            self.protocol_version = requested
        return {"protocolVersion": self.protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": dict(SERVER_INFO),
                "instructions": profiles.instructions(self.profile, INSTRUCTIONS)}

    def serve(self, stdin=None, stdout=None) -> None:
        """Read newline-delimited JSON-RPC from stdin until EOF."""
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError as ex:
                _write(stdout, _error(None, PARSE_ERROR, f"invalid JSON: {ex}"))
                continue
            if isinstance(message, list):  # JSON-RPC batch
                for reply in filter(None, (self.handle(m) for m in message)):
                    _write(stdout, reply)
                continue
            reply = self.handle(message)
            if reply is not None:
                _write(stdout, reply)


# ------------------------------------------------------------------ helpers


def _text(payload) -> dict:
    """A text content block: readable JSON while it is small, compact when not."""
    compact = json.dumps(payload, ensure_ascii=False)
    text = (json.dumps(payload, ensure_ascii=False, indent=2)
            if len(compact) <= 4000 else compact)
    return {"type": "text", "text": text}


def result_text(result: dict) -> str:
    """The text a tool result carries to the model: what call_tool returns."""
    return _text(result)["text"]


#: a string in a traced result longer than this is replaced by a marker. No
#: result the engine returns is that long except by accident (a render comes
#: back as a path, not as bytes); the cap keeps a trace readable if one is.
TRACE_MAX_STRING = 8192


def trace_result(result):
    """A result as a trace keeps it: a copy through JSON, long strings cut."""
    if isinstance(result, dict):
        return {str(k): trace_result(v) for k, v in result.items()}
    if isinstance(result, (list, tuple)):
        return [trace_result(v) for v in result]
    if isinstance(result, str) and len(result) > TRACE_MAX_STRING:
        return f"<{len(result)} characters omitted>"
    if isinstance(result, float) and result != result:  # NaN is not JSON
        return None
    return result


def trace_line(name: str, kind: str, arguments: dict, result: dict,
               said: Optional[str] = None) -> dict:
    """One line of a trace: the call, its outcome at a glance (message,
    created, or the error with its hint), and under ``result`` the whole
    answer the agent was shown. ``said`` is what a scripted solve said
    before the call (``roaddraft.trajectories``); a model's trace has none."""
    entry = {"tool": name, "kind": kind, "arguments": trace_result(arguments),
             "ok": bool(result.get("ok"))}
    if result.get("ok"):
        for key in ("message", "warnings", "created"):
            if result.get(key):
                entry[key] = trace_result(result[key])
    else:
        error = result.get("error") or {}
        entry["error"] = {k: error.get(k) for k in ("type", "message", "hint")
                          if error.get(k)}
    if said:
        entry["said"] = said
    entry["result"] = trace_result(result)
    return entry


def _image_content(path) -> Optional[dict]:
    if not path:
        return None
    file = Path(path)
    try:
        if not file.is_file() or file.stat().st_size > MAX_IMAGE_BYTES:
            return None
        data = file.read_bytes()
    except OSError:
        return None
    return {"type": "image", "data": base64.b64encode(data).decode("ascii"),
            "mimeType": "image/png"}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def _write(stream, payload: dict) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    stream.flush()


def _names(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _start_inside(args) -> None:
    """Relative paths resolve against the working directory, so under a root
    it must lie inside it: a client that starts the server elsewhere has it
    moved into the root, its own path options made absolute first."""
    root = confine.Root(args.root)
    if root.contains(os.getcwd()):
        return
    for option in ("doc", "out_dir", "trace", "root"):
        if getattr(args, option):
            setattr(args, option, os.path.abspath(getattr(args, option)))
    os.chdir(root.real)
    print(f"roaddraft-mcp: working directory moved into --root {root.real}", file=sys.stderr)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="roaddraft-mcp",
        description="Serve the RoadDraft command surface to an agent over MCP (stdio).")
    parser.add_argument("--doc", help="open this document (.rdraft or .rdoc.json) "
                                      "as the working document")
    parser.add_argument("--out-dir", help="where renders and exports are written "
                                          "(default ./renders)")
    parser.add_argument("--project", default="Untitled",
                        help="project name for a new document (ignored with --doc)")
    parser.add_argument("--only", help="comma-separated tool names to expose")
    parser.add_argument("--exclude", help="comma-separated tool names to hide")
    parser.add_argument("--autosave", action="store_true",
                        help="write the document (and its journal, beside it) back to "
                             "its file after every command, so the work outlives the "
                             "session without the agent having to save")
    parser.add_argument("--trace", help="append one JSON line per tool call to this "
                                        "file: arguments, outcome, faults and hints, and "
                                        "the full result the agent was shown")
    parser.add_argument("--root", metavar="DIR",
                        help="hold every file a tool reads or writes (a document, a "
                             "reference, LandXML, a render, an export, a save) inside "
                             "DIR, links followed, and show paths in results relative "
                             "to the working directory instead of absolute. The "
                             "server starts in DIR unless already inside it. For a "
                             "benchmarked model, which must not read what lies "
                             "outside its episode")
    parser.add_argument("--profile", choices=profiles.PROFILES, default="default",
                        help="the tool surface: default (everything), or basic (no "
                             "commands that work out geometry for the caller; mcp/profiles.py)")
    parser.add_argument("--attachments", metavar="DIR",
                        help="serve view_attachment over the images in DIR (a task's "
                             "scanned sheet or markup)")
    parser.add_argument("--list-tools", action="store_true",
                        help="print the tool names that would be served, then exit")
    parser.add_argument("--config", metavar="CLIENT", choices=sorted(mcpconfig.CLIENTS),
                        help="instead of serving, print the registration of this server -- "
                             "with the options given here -- for an MCP client, then exit: "
                             + ", ".join(sorted(mcpconfig.CLIENTS)))
    parser.add_argument("--name", default=mcpconfig.DEFAULT_NAME,
                        help="the server's name in the client (default %(default)s)")
    parser.add_argument("--write", nargs="?", const="-", metavar="FILE",
                        help="with --config: put the registration in the client's file "
                             "(or FILE), merged in beside the servers already there")
    args = parser.parse_args(argv)

    if args.config:
        if args.doc and not Path(args.doc).is_file():
            print(f"note: {args.doc} does not exist yet", file=sys.stderr)
        return mcpconfig.configure(
            args.config, name=args.name,
            args=mcpconfig.server_args(doc=args.doc, autosave=args.autosave, trace=args.trace,
                                       out_dir=args.out_dir, only=_names(args.only),
                                       exclude=_names(args.exclude), project=args.project,
                                       root=args.root, profile=args.profile,
                                       attachments=args.attachments),
            write_to=args.write)
    if args.write:
        parser.error("--write goes with --config")

    if args.root:
        if not Path(args.root).is_dir():
            parser.error(f"--root {args.root} is not a folder")
        _start_inside(args)

    if args.doc:
        session = Session.load(args.doc, out_dir=args.out_dir)
    else:
        session = Session(project_name=args.project, out_dir=args.out_dir)
    if args.attachments and not Path(args.attachments).is_dir():
        parser.error(f"--attachments {args.attachments} is not a folder")
    server = RoadDraftMCP(session, only=_names(args.only), exclude=_names(args.exclude),
                          autosave=args.autosave, trace=args.trace, root=args.root,
                          profile=args.profile, attachments=args.attachments)

    if args.list_tools:
        tools = server.tools()
        for tool in tools:
            print(tool["name"])
        print(f"{len(tools)} tools", file=sys.stderr)
        return 0

    where = args.doc or f"a new {args.project!r} document"
    print(f"roaddraft {__version__} MCP server on stdio: {where}, "
          f"{len(server.tools())} tools", file=sys.stderr)
    server.serve()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
