"""MCP server over stdio: every RoadDraft command and query as an agent tool.

This is the natural-language front door. The bus already carries, per command,
a description, a JSON Schema and a worked example -- which is exactly an MCP
tool definition -- so the tool list is derived from ``Session.manifest()``
rather than written twice. 43 commands + 26 queries, no name collisions.

A tool call goes straight through the bus, so everything the engine already
guarantees still holds for an agent: schema validation with teaching errors,
atomic application, the journal, undo. A command that faults comes back as a
tool error carrying the message, the hint and a valid example -- the model
reads it and corrects itself.

Renders come back as images, so an agent can look at the sheet it just drew.

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
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from roaddraft import __version__
from roaddraft.api.session import Session
from roaddraft.document import fileformat
from roaddraft.document.fileformat import DocumentFormatError

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
                     exclude: Optional[Sequence[str]] = None) -> List[dict]:
    """MCP tool definitions from the command/query manifest, plus the extras.

    ``only`` keeps just those names (the eval harness's whitelist, later);
    ``exclude`` drops them. Both are applied to bus and extra tools alike.
    """
    manifest = session.manifest()
    tools: List[dict] = []
    for entry in list(manifest["commands"]) + list(manifest["queries"]):
        description = entry["description"]
        if entry.get("example"):
            description += "\nExample params: " + json.dumps(entry["example"])
        tools.append({"name": entry["name"], "description": description,
                      "inputSchema": entry["params_schema"]})
    for name, spec in EXTRA_TOOLS.items():
        tools.append({"name": name, "description": spec["description"],
                      "inputSchema": spec["inputSchema"]})
    if only:
        keep = set(only)
        tools = [t for t in tools if t["name"] in keep]
    if exclude:
        drop = set(exclude)
        tools = [t for t in tools if t["name"] not in drop]
    return tools


class RoadDraftMCP:
    """One MCP session over one RoadDraft ``Session``."""

    def __init__(self, session: Session, only: Optional[Sequence[str]] = None,
                 exclude: Optional[Sequence[str]] = None, autosave: bool = False,
                 trace: Optional[str] = None):
        self.session = session
        self.only = list(only) if only else None
        self.exclude = list(exclude) if exclude else None
        self.protocol_version = PROTOCOL_VERSION
        self.autosave = autosave
        self.trace = Path(trace) if trace else None
        #: where autosave writes: the file the document was opened from. It does
        #: not follow a save_document to somewhere else (see _autosave).
        self.home = getattr(session.doc, "_path", None)

    # ------------------------------------------------------------- tools

    def tools(self) -> List[dict]:
        return tool_definitions(self.session, self.only, self.exclude)

    def _kinds(self) -> Dict[str, str]:
        """``{tool name: "command" | "query" | "extra"}`` for the exposed tools."""
        manifest = self.session.manifest()
        kinds = {c["name"]: "command" for c in manifest["commands"]}
        kinds.update({q["name"]: "query" for q in manifest["queries"]})
        kinds.update({name: "extra" for name in EXTRA_TOOLS})
        exposed = {t["name"] for t in self.tools()}
        return {k: v for k, v in kinds.items() if k in exposed}

    def call_tool(self, name: str, arguments: Optional[dict]) -> dict:
        """Run one tool. Returns an MCP tool result; a fault is ``isError``."""
        arguments = arguments or {}
        kind = self._kinds().get(name)
        if kind is None:
            return self._tool_error(
                f"unknown tool {name!r}. Call tools/list for the surface, or the "
                f"list_commands tool for the command manifest.")
        if kind == "extra":
            return self._call_extra(name, arguments)
        result = (self.session.execute(name, arguments) if kind == "command"
                  else self.session.query(name, arguments))
        self._trace(name, kind, arguments, result)
        if kind == "command" and result.get("ok"):
            self._autosave()
        content = [_text(result)]
        if result.get("ok") and name in IMAGE_QUERIES:
            image = _image_content(result.get("path"))
            if image is not None:
                content.append(image)
        return {"content": content, "isError": not result.get("ok", False)}

    def _call_extra(self, name: str, arguments: dict) -> dict:
        if name != "open_document":
            return self._tool_error(f"unknown tool {name!r}")
        path = arguments.get("path")
        if not isinstance(path, str) or not path:
            return self._tool_error("open_document needs a path to a document file")
        try:
            self.session = Session.load(path, out_dir=self.session.out_dir)
            self.home = getattr(self.session.doc, "_path", None)
        except FileNotFoundError:
            return self._tool_error(f"no such document: {path}")
        except DocumentFormatError as ex:  # not a document, or malformed JSON
            return self._tool_error(f"cannot open {path}: {ex}")
        except Exception as ex:  # failed validation
            return self._tool_error(f"cannot open {path}: {type(ex).__name__}: {ex}")
        summary = self.session.query("get_document_state", {})
        return {"content": [_text({"ok": True, "opened": str(Path(path).resolve()),
                                   "state": summary})], "isError": False}

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
        it and what it tripped on, not only for what it left behind."""
        if self.trace is None:
            return
        entry = {"tool": name, "kind": kind, "arguments": arguments,
                 "ok": bool(result.get("ok"))}
        if result.get("ok"):
            for key in ("message", "warnings", "created"):
                if result.get(key):
                    entry[key] = result[key]
        else:
            error = result.get("error") or {}
            entry["error"] = {k: error.get(k) for k in ("type", "message", "hint")
                              if error.get(k)}
        self.trace.parent.mkdir(parents=True, exist_ok=True)
        with self.trace.open("a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

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
                "instructions": (
                    "RoadDraft is a headless 2D CAD engine for roadway plans. Model "
                    "space is US survey feet, and a point is [x, y] = [easting, "
                    "northing] -- the other way round from how coordinates are usually "
                    "spoken, so N 5000, E 2000 is [2000, 5000]. Sheets are paper inches "
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
                    "find_entities {anchor: {kind: 'offset', offset: [-12, 12]}, "
                    "visible_on: 'C-102'} is the pavement edges that sheet shows. Then "
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
                    "'DESIGN:SR-100', and station_to_xy, xy_to_station, resolve_anchor "
                    "and get_design_data all accept that name and answer in host "
                    "coordinates. To call one out, give place_callout a target_anchor "
                    "('18+00@12R', 'PC-1') and that alignment name. Otherwise commands "
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
                    "point_on_entity take a sheet and answer in paper inches as well.")}

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


def journal_path(document: Path) -> Path:
    """``SR-100.sheets.rdoc.json`` -> ``SR-100.sheets.jsonl``, beside it."""
    name = Path(document).name
    for suffix in (".rdoc.json", ".rdraft", ".json"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return Path(document).with_name(name + ".jsonl")


def _text(payload) -> dict:
    """A text content block: readable JSON while it is small, compact when not."""
    compact = json.dumps(payload, ensure_ascii=False)
    text = (json.dumps(payload, ensure_ascii=False, indent=2)
            if len(compact) <= 4000 else compact)
    return {"type": "text", "text": text}


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
                                        "file: arguments, outcome, faults and hints")
    parser.add_argument("--list-tools", action="store_true",
                        help="print the tool names that would be served, then exit")
    args = parser.parse_args(argv)

    if args.doc:
        session = Session.load(args.doc, out_dir=args.out_dir)
    else:
        session = Session(project_name=args.project, out_dir=args.out_dir)
    server = RoadDraftMCP(session, only=_names(args.only), exclude=_names(args.exclude),
                          autosave=args.autosave, trace=args.trace)

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
