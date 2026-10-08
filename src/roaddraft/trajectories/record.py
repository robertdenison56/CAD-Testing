"""Record what a run does, the way a model's run is recorded.

A probe's ``solve`` drafts through ``Session.execute`` and ``Session.query``,
the two calls the MCP server exposes as tools. The journal keeps the commands;
it does not keep the queries, and a trajectory that is to teach a model how to
draft must show the question asked before each command as well as the command.
``Recorder`` hooks both calls on one session and sends each through the MCP
server's own ``call_tool``, so the solve runs on the tool surface a model has
(the server decides what kind of call it was, and the solve reads back the
JSON text the server returns) and the server's ``--trace`` writes the run as
it would write a model's: one line per call, the full result included.

It also audits the one thing a scripted solution can do that a model cannot:
read the document object directly (``session.doc``) instead of asking a
query. Every such read during a solve is noted with the file and line that
made it. A trajectory with any is not *faithful*: a model working through the
tool surface could not have taken that step, so the numbers in the next
command came from nowhere it can see.

``replay_trace`` runs a trace that kept no results (the server's trace before
it carried them) against a fresh start under the recorder, so the
conversation the model had can be rebuilt result for result.
"""
from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from roaddraft.api.session import Session
from roaddraft.mcp.server import RoadDraftMCP, trace_line, trace_result
from roaddraft.probes import fixture
from roaddraft.probes.base import Probe, Result

#: subpackages whose own code reads the document in the course of answering a
#: call: the engine. A read from anywhere else during a solve is a direct read.
INTERNAL = ("api", "commands", "document", "design", "render", "adapters", "core",
            "mcp", "trajectories")


@dataclass
class DirectRead:
    """One read of ``session.doc`` by code outside the engine."""
    file: str
    line: int
    function: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line} in {self.function}"


@dataclass
class Call:
    """One tool call as the recorder saw it: what was sent, what came back."""
    tool: str
    kind: str                       # "command" | "query"
    arguments: dict
    result: dict
    #: what the solve said before this call (its arithmetic, see Recorder.say)
    said: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.result.get("ok"))

    def trace_line(self) -> dict:
        """The MCP server's trace line for this call (``said`` added)."""
        return trace_line(self.tool, self.kind, self.arguments, self.result, said=self.said)


def _jsonable(value):
    """A deep copy through JSON: what a tool call carries over the wire."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def _is_internal(filename: str) -> bool:
    parts = Path(filename).parts
    if "roaddraft" not in parts:
        return False
    after = parts[len(parts) - 1 - parts[::-1].index("roaddraft") + 1:]
    return bool(after) and after[0] in INTERNAL


def _short(filename: str) -> str:
    parts = Path(filename).parts
    if "roaddraft" in parts:
        i = len(parts) - 1 - parts[::-1].index("roaddraft")
        return "/".join(parts[i:])
    return Path(filename).name


_AUDITED = {}


def _audited(base):
    """``base`` with a ``doc`` property that tells the recorder who read it."""
    if getattr(base, "_audits_doc", False):
        return base
    if base in _AUDITED:
        return _AUDITED[base]

    class Audited(base):
        _audits_doc = True

        @property
        def doc(self):
            recorder = self.__dict__.get("_recorder")
            if recorder is not None:
                recorder._doc_read(sys._getframe(1))
            return base.doc.fget(self)

    Audited.__name__, Audited.__qualname__ = base.__name__, base.__qualname__
    Audited.__module__ = base.__module__
    _AUDITED[base] = Audited
    return Audited


class _Plain:
    """The session as the MCP server holds it while the recorder has hooked
    it: ``execute`` and ``query`` are the class's own, so a call the server
    makes does not come back through the hook. Everything else is the
    session's."""

    def __init__(self, session: Session, base):
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_base", base)

    def execute(self, name, params=None):
        return self._base.execute(self._session, name, params)

    def query(self, name, params=None):
        return self._base.query(self._session, name, params)

    def __getattr__(self, name):
        return getattr(self._session, name)

    def __setattr__(self, name, value):
        setattr(self._session, name, value)


def _reply_result(reply: dict) -> dict:
    """The result dict a tool reply carries: the JSON in its text block. The
    one reply that is not JSON (an unknown tool) becomes a fault."""
    text = reply["content"][0]["text"]
    try:
        return json.loads(text)
    except ValueError:
        return {"ok": False, "error": {"type": "unknown_tool", "message": text}}


class Recorder:
    """Hooks one session's ``execute`` and ``query``, sends each call through
    the MCP server, and keeps every call with its full result; audits direct
    reads of the document meanwhile.

        with Recorder(session) as rec:
            probe.solve(session)
        rec.calls, rec.direct_reads

    With ``trace`` the server writes its own ``--trace`` file as the run goes,
    the lines a model's run would leave (``said`` is not among them; the kept
    trace from ``write_trace`` has it). While attached the session also has
    ``say(text)``: a solve calls it to show the arithmetic behind its next
    call, and the text becomes the assistant's words before that call in the
    conversation."""

    def __init__(self, session: Session, trace=None):
        self.session = session
        self.trace = Path(trace) if trace else None
        self.calls: List[Call] = []
        self.direct_reads: List[DirectRead] = []
        self._pending: Optional[str] = None
        self._original_class = None
        self.server: Optional[RoadDraftMCP] = None

    def __enter__(self) -> "Recorder":
        self.attach()
        return self

    def __exit__(self, *exc) -> None:
        self.detach()

    def attach(self) -> None:
        s = self.session
        if s.__dict__.get("_recorder") is not None:
            raise RuntimeError("this session is already being recorded")
        base = self._original_class = s.__class__
        self.server = RoadDraftMCP(_Plain(s, base),
                                   trace=str(self.trace) if self.trace else None)
        s.__class__ = _audited(base)
        s.__dict__["_recorder"] = self
        s.__dict__["execute"] = lambda name, params=None: self._record("command", name, params)
        s.__dict__["query"] = lambda name, params=None: self._record("query", name, params)
        s.__dict__["say"] = self.say

    def detach(self) -> None:
        s = self.session
        for key in ("_recorder", "execute", "query", "say"):
            s.__dict__.pop(key, None)
        if self._original_class is not None:
            s.__class__ = self._original_class
            self._original_class = None

    def say(self, text: str) -> None:
        """What the solve says before its next call: shown work."""
        self._pending = f"{self._pending}\n{text}" if self._pending else text

    def _record(self, kind: str, name: str, params) -> dict:
        sent = _jsonable(params or {})
        said, self._pending = self._pending, None
        reply = self.server.call_tool(name, sent)
        result = _reply_result(reply)
        self.calls.append(Call(name, self.server.kind_of(name) or kind, sent,
                               trace_result(result), said=said))
        return result

    def _doc_read(self, frame) -> None:
        while frame is not None and frame.f_code.co_filename == __file__:
            frame = frame.f_back
        if frame is None or _is_internal(frame.f_code.co_filename):
            return
        self.direct_reads.append(DirectRead(_short(frame.f_code.co_filename),
                                            frame.f_lineno, frame.f_code.co_name))

    @property
    def faithful(self) -> bool:
        return not self.direct_reads

    def write_trace(self, path) -> Path:
        """One JSON line per call: the server's trace shape, ``said`` included."""
        return write_trace(self.calls, path)


def write_trace(calls: Iterable[Call], path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for call in calls:
            fh.write(json.dumps(call.trace_line(), ensure_ascii=False) + "\n")
    return path


@dataclass
class Recording:
    """A run recorded on a probe's start: the document it left, the calls, the
    direct reads, and the verdict read back from disk."""
    probe: Probe
    document: Path
    calls: List[Call]
    direct_reads: List[DirectRead] = field(default_factory=list)
    result: Optional[Result] = None

    @property
    def faithful(self) -> bool:
        return not self.direct_reads

    def counts(self) -> dict:
        return {"calls": len(self.calls),
                "queries": sum(c.kind == "query" for c in self.calls),
                "commands": sum(c.kind == "command" for c in self.calls),
                "faults": sum(not c.ok for c in self.calls),
                "direct_reads": len(self.direct_reads)}


def fresh_start(probe: Probe, folder, start_dir=None) -> Path:
    """The probe's start document, written fresh under ``folder`` (copied from
    ``start_dir`` when one was built already)."""
    folder = Path(folder)
    if start_dir is None:
        return fixture.start_document(folder, probe.start)
    shutil.copytree(start_dir, folder, dirs_exist_ok=True)
    return folder / fixture.START[probe.start]


def _prepare(probe: Probe, folder, start_dir=None):
    document = fresh_start(probe, folder, start_dir)
    baseline = Session.load(document, out_dir=folder)
    session = Session.load(document, out_dir=folder)
    return document, baseline, session


def _finish(probe: Probe, document: Path, baseline: Session, session: Session,
            recorder: Recorder) -> Recording:
    r = session.query("save_document", {"path": str(document)})
    if not r.get("ok"):
        raise RuntimeError(f"save_document: {r['error']['message']}")
    finished = Session.load(document, out_dir=document.parent)
    return Recording(probe, document, recorder.calls, recorder.direct_reads,
                     probe.check(baseline, finished))


def record_solve(probe: Probe, folder, start_dir=None, trace=None) -> Recording:
    """Run ``probe.solve`` on a fresh start under ``folder`` with the recorder
    attached, every call through the MCP server; with ``trace`` the server
    writes its trace file as it goes. The document is saved and scored from
    disk afterwards, outside the recording, as autosave does for a model."""
    if probe.solve is None:
        raise ValueError(f"{probe.id} has no scripted solution")
    document, baseline, session = _prepare(probe, folder, start_dir)
    with Recorder(session, trace=trace) as recorder:
        probe.solve(session)
    return _finish(probe, document, baseline, session, recorder)


def read_trace(path) -> List[dict]:
    """The lines of an MCP ``--trace`` file (or of a recorded trace)."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


#: queries a model's trace may hold that write files: replayed into the replay
#: folder, never where the model's own path pointed (which may be another
#: machine, or the run's kept files)
FILE_WRITERS = ("export_dxf", "export_landxml", "export_pdf", "print_pdf",
                "render_sheet", "render_model")
#: not replayed at all: a model's "save as" moved nothing that matters to the
#: drawing, and replaying it would write the document somewhere else
NOT_REPLAYED = ("save_document", "save_journal")


def replay_trace(probe: Probe, lines: Iterable[dict], folder, start_dir=None) -> Recording:
    """Replay a model's trace on a fresh start, recording the results its
    calls produce. The engine is deterministic, so the replayed document is
    the one the model left, and the results are the ones it read. A save the
    model made is kept as the trace reported it, not run again; a file the
    model exported or rendered is written under ``folder``."""
    document, baseline, session = _prepare(probe, folder, start_dir)
    folder = Path(folder)
    with Recorder(session) as recorder:
        for entry in lines:
            kind, tool = entry.get("kind"), entry["tool"]
            arguments = dict(entry.get("arguments") or {})
            if kind == "extra" or tool == "open_document":
                continue
            if tool in NOT_REPLAYED:
                result = {"ok": bool(entry.get("ok")), "name": tool, "replayed": False}
                if entry.get("error"):
                    result["error"] = entry["error"]
                recorder.calls.append(Call(tool, kind, _jsonable(arguments), result,
                                           said=entry.get("said")))
                continue
            if tool in FILE_WRITERS and isinstance(arguments.get("path"), str):
                arguments["path"] = str(folder / Path(arguments["path"]).name)
            if entry.get("said"):
                recorder.say(entry["said"])
            call = session.execute if kind == "command" else session.query
            call(tool, arguments)
    return _finish(probe, document, baseline, session, recorder)


def same_document(a_path, b_path) -> bool:
    """Whether two saved documents hold the same drawing."""
    return (Session.load(a_path).doc.to_dict() == Session.load(b_path).doc.to_dict())


__all__ = ["INTERNAL", "FILE_WRITERS", "NOT_REPLAYED", "DirectRead", "Call", "Recorder",
           "Recording", "fresh_start", "record_solve", "read_trace", "replay_trace",
           "same_document", "write_trace"]
