"""Record the probes' scripted solutions as conversations, audit them, or
convert a model's traces.

    python -m roaddraft.trajectories audit [--tag TAG] [PROBE ...]
    python -m roaddraft.trajectories record --out DIR [--tag TAG] [PROBE ...]
    python -m roaddraft.trajectories record --out DIR --family FAMILY --seeds 0-99
    python -m roaddraft.trajectories convert PROBE --trace FILE --out DIR
                                             [--report FILE] [--prompt FILE] [--document DOC]
                                             [--source NAME] [--replay]
    python -m roaddraft.trajectories convert --run DIR --out DIR      one run folder
    python -m roaddraft.trajectories convert --runs DIR --out DIR     every run folder under DIR

``audit`` runs each scripted solution under the recorder and prints what it
asked, what it sent, and every direct read of the document it made: a solve
with none is a faithful trajectory. ``record`` runs those solves through the
MCP server with tracing on and keeps them under ``--out``: per probe
``trace.jsonl`` (the server's trace, results included), ``conversation.json``
converted from that trace, and ``record.json``; once, ``tools.json`` and an
index. ``convert`` is the trace-to-conversation converter: a trace the server
wrote with results in it converts as it stands; an older trace, which kept
arguments and outcomes only, is replayed on a fresh start to recover the
results (``--replay`` forces that, and with ``--document`` says whether the
replay reproduced the document the model left). A run folder is one the probe
rigs leave: ``trace.jsonl``, ``report.txt``, ``prompt.txt`` and ``project/``
under ``runs/<model>/<probe>/``; its probe is the folder's name and its source
the model's. ``rehydrate`` is ``convert --replay`` under its earlier name.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

from roaddraft import __version__
from roaddraft.api.session import Session
from roaddraft.probes import families, fixture, tasks
from roaddraft.probes.base import Probe
from roaddraft.trajectories.convert import (calls_from_trace, conversation, has_results,
                                            tool_list, tools_digest)
from roaddraft.trajectories.record import (Recording, fresh_start, read_trace, record_solve,
                                           replay_trace, same_document, write_trace)

RECORD = "record.json"


def _chosen(args) -> List[Probe]:
    if getattr(args, "family", None):
        seeds = families.parse_seeds(args.seeds or "0-9")
        return families.instances(args.family, seeds)
    known = {p.id for p in tasks.PROBES}
    unknown = [pid for pid in args.probes if pid not in known and not families.is_instance(pid)]
    if unknown:
        raise SystemExit(f"no probe {', '.join(unknown)}: see python -m roaddraft.probes list")
    chosen = [p for p in tasks.PROBES if p.solve
              and (not args.probes or p.id in args.probes)
              and (not args.tag or args.tag in p.tags)]
    chosen += [families.instance(pid) for pid in args.probes if families.is_instance(pid)]
    return chosen


def _starts(tmp: Path):
    built = {}

    def start_dir(probe) -> Path:
        if probe.start not in built:
            built[probe.start] = tmp / "start" / probe.start
            fixture.start_document(built[probe.start], probe.start)
        return built[probe.start]
    return start_dir


def _row(rec: Recording, how: str = "") -> str:
    c = rec.counts()
    verdict = ("pass" if rec.result.passed else "FAIL") if rec.result else "unscored"
    faithful = "yes" if rec.faithful else f"no ({c['direct_reads']})"
    return (f"  {rec.probe.id:26} {c['queries']:3}q {c['commands']:3}c {c['faults']:2} faults  "
            f"faithful: {faithful:8} {verdict}" + (f"  ({how})" if how else ""))


def cmd_audit(args) -> int:
    unfaithful = 0
    with tempfile.TemporaryDirectory() as tmp:
        start_dir = _starts(Path(tmp))
        for probe in _chosen(args):
            rec = record_solve(probe, Path(tmp) / probe.id, start_dir(probe))
            print(_row(rec))
            if not rec.faithful:
                unfaithful += 1
                for read in sorted(set(map(str, rec.direct_reads))):
                    print(f"      reads the document at {read}")
    print(f"{unfaithful} scripted solution(s) read the document directly")
    return 0


def keep(rec: Recording, folder: Path, tools_sha: str, report=None, source="solve",
         task=None, extra: Optional[dict] = None) -> dict:
    """Write a run's trace, then its conversation converted from that trace,
    then the record. The conversation is a function of the trace file, so
    what is kept is what ``convert`` would make of it."""
    folder.mkdir(parents=True, exist_ok=True)
    trace = write_trace(rec.calls, folder / "trace.jsonl")
    calls = calls_from_trace(read_trace(trace))
    conv = conversation(rec.probe, calls, tools_sha, rec.result, rec.direct_reads,
                        report=report, source=source, task=task)
    (folder / "conversation.json").write_text(json.dumps(conv, ensure_ascii=False, indent=1) + "\n")
    record = {k: conv[k] for k in ("probe", "tags", "start", "source", "roaddraft", "tools_sha256",
                                   "faithful", "direct_reads", "task", "report", "outcome", "counts")}
    record.update(extra or {})
    record["files"] = {"trace": trace.name, "conversation": "conversation.json"}
    (folder / RECORD).write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    return record


def write_tools(out: Path, tools: list, digest: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "tools.json").write_text(json.dumps({"roaddraft": __version__, "sha256": digest,
                                               "tools": tools}, ensure_ascii=False, indent=1) + "\n")


INDEX_SOLVES = """\
# Probe solves as conversations

Every probe's scripted solution, run through the MCP server with tracing on
and kept as the conversation a model would have had: the server's
instructions, the task as a model is given it, one assistant turn per tool
call, the text the server returned for it, and a report. Queries are in it as
well as commands; the journal beside each reference in
`benchmarks/probe_references` keeps only the commands.
"""

INDEX_RUNS = """\
# Model runs as conversations

Each run's trace converted to the conversation the model had: the server's
instructions, the task, one assistant turn per tool call, the text the server
returned for it, and the model's own report. A trace that kept no results was
replayed on a fresh start to recover them (`how` says which).
"""

INDEX_TAIL = """
Generated, not edited: `{command}`
(roaddraft {version}). `tools.json` holds the {ntools} tool definitions every
conversation was recorded against ({digest}).

    <probe>/trace.jsonl        every call: the MCP server's trace line, result included
    <probe>/conversation.json  the run as messages, with the verdict and the audit
    <probe>/record.json        the conversation's header: counts, faithfulness, verdict

A conversation is **faithful** when the run read nothing from the document
except through the tool surface, so a model could have taken every step in
it. A scripted solve that reads the document object directly (`session.doc`)
is listed with where it did so: its commands carry numbers that came from
nowhere a model can see, and it is not training data until that is fixed.

{faithful} of {total} faithful; {passed} of {total} pass their check.

| Probe | Tags | Queries | Commands | Faults | Faithful | Check |{how_head}
|---|---|---|---|---|---|---|{how_rule}
"""


def write_index(out: Path, command: str, tools: list, digest: str, runs: bool = False) -> Path:
    order = {p.id: k for k, p in enumerate(tasks.PROBES)}
    rows = sorted((json.loads(p.read_text()) for p in out.glob(f"*/{RECORD}")),
                  key=lambda r: (order.get(r["probe"], len(order)), r["probe"]))
    head = INDEX_RUNS if runs else INDEX_SOLVES
    lines = [head + INDEX_TAIL.format(
        command=command, version=__version__, ntools=len(tools), digest=digest,
        faithful=sum(r["faithful"] for r in rows), total=len(rows),
        passed=sum(bool(r["outcome"] and r["outcome"]["passed"]) for r in rows),
        how_head=" How |" if runs else "", how_rule="---|" if runs else "")]
    for r in rows:
        c = r["counts"]
        faithful = "yes" if r["faithful"] else "no: " + "; ".join(sorted(set(r["direct_reads"])))
        verdict = ("PASS" if r["outcome"]["passed"] else "FAIL") if r["outcome"] else "unscored"
        how = ""
        if runs:
            how = " " + r.get("how", "") + (
                "" if r.get("document_matches") is None
                else (", document reproduced" if r["document_matches"]
                      else ", document NOT reproduced")) + " |"
        lines.append(f"| {r['probe']} | {', '.join(r['tags'])} | {c['queries']} | {c['commands']} | "
                     f"{c['faults']} | {faithful} | {verdict} |{how}\n")
    index = out / "README.md"
    index.write_text("".join(lines))
    return index


def _fresh_tools(probe: Probe, tmp: Path):
    """The tool definitions and their digest, read off a fresh start."""
    start = fresh_start(probe, tmp / "tools" / probe.start)
    tools = tool_list(Session.load(start, out_dir=tmp))
    return tools, tools_digest(tools)


def cmd_record(args) -> int:
    out = Path(args.out)
    chosen = _chosen(args)
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        start_dir = _starts(Path(tmp))
        tools = tool_list(Session.load(start_dir(chosen[0]) / fixture.START[chosen[0].start]))
        digest = tools_digest(tools)
        write_tools(out, tools, digest)
        for probe in chosen:
            folder = out / probe.id
            if folder.exists():
                shutil.rmtree(folder)
            # the server writes its own trace as the solve runs; the kept trace
            # is the same lines with the solve's shown work added
            rec = record_solve(probe, Path(tmp) / probe.id, start_dir(probe),
                               trace=Path(tmp) / probe.id / "server-trace.jsonl")
            keep(rec, folder, digest)
            print(_row(rec))
            if not (rec.result and rec.result.passed):
                failures.append(probe.id)
    if not args.no_index:
        index = write_index(out, f"python -m roaddraft.trajectories record --out {args.out}"
                            + (f" --family {args.family} --seeds {args.seeds or '0-9'}"
                               if getattr(args, "family", None) else ""), tools, digest)
        print(f"index: {index}")
    return 1 if failures else 0


def convert_trace(probe: Probe, trace, out: Path, tmp: Path, report: Optional[str] = None,
                  task: Optional[str] = None, document=None, source: str = "model",
                  replay: bool = False, tools_sha: Optional[str] = None) -> dict:
    """One trace into ``out``. A trace with results converts as it stands and
    is scored against ``document`` when one is given; a trace without them,
    or any trace with ``replay``, is replayed on a fresh start, scored on the
    replayed document, and compared with ``document`` when one is given."""
    lines = read_trace(trace)
    if tools_sha is None:
        tools_sha = _fresh_tools(probe, tmp)[1]
    extra = {"from": str(trace)}
    if replay or not has_results(lines):
        rec = replay_trace(probe, lines, tmp / "replay" / probe.id)
        extra["how"] = "replayed" if replay else "replayed (the trace kept no results)"
        if document:
            extra["document_matches"] = same_document(document, rec.document)
    else:
        calls = calls_from_trace(lines)
        result = None
        if document:
            start = fresh_start(probe, tmp / "baseline" / probe.id)
            result = probe.check(Session.load(start, out_dir=tmp),
                                 Session.load(document, out_dir=tmp))
        rec = Recording(probe, Path(document) if document else None, calls, [], result)
        extra["how"] = "converted"
    record = keep(rec, out, tools_sha, report=report, source=source, task=task, extra=extra)
    print(_row(rec, extra["how"] + ("" if record.get("document_matches") is None else
                                    (", document reproduced" if record["document_matches"]
                                     else ", document NOT reproduced"))))
    return record


def _read(path) -> Optional[str]:
    return Path(path).read_text() if path else None


def _run_parts(folder: Path, probe: Probe, kept_prompt: bool) -> dict:
    """What a probe rig's run folder holds for the converter."""
    report = folder / "report.txt"
    prompt = folder / "prompt.txt"
    document = folder / "project" / fixture.START[probe.start]
    return {"report": report.read_text() if report.exists() else None,
            "task": prompt.read_text() if kept_prompt and prompt.exists() else None,
            "document": document if document.exists() else None}


def cmd_convert(args) -> int:
    out = Path(args.out)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if args.runs:
            root = Path(args.runs)
            folders = sorted(f for f in root.iterdir()
                             if (f / "trace.jsonl").exists() and f.name in tasks.BY_ID)
            if not folders:
                raise SystemExit(f"no run folders with a trace.jsonl under {root}")
            source = args.source or root.name
            tools, digest = _fresh_tools(tasks.get(folders[0].name), tmp)
            write_tools(out, tools, digest)
            for folder in folders:
                probe = tasks.get(folder.name)
                target = out / probe.id
                if target.exists():
                    shutil.rmtree(target)
                convert_trace(probe, folder / "trace.jsonl", target, tmp, source=source,
                              replay=args.replay, tools_sha=digest,
                              **_run_parts(folder, probe, args.kept_prompt))
            index = write_index(out, f"python -m roaddraft.trajectories convert --runs {args.runs} "
                                f"--out {args.out}", tools, digest, runs=True)
            print(f"index: {index}")
            return 0
        if args.run:
            folder = Path(args.run)
            probe = tasks.get(folder.name)
            convert_trace(probe, folder / "trace.jsonl", out, tmp,
                          source=args.source or folder.parent.name, replay=args.replay,
                          **_run_parts(folder, probe, args.kept_prompt))
        else:
            if not args.probe or not args.trace:
                raise SystemExit("convert needs PROBE --trace FILE, or --run DIR, or --runs DIR")
            probe = tasks.get(args.probe)
            convert_trace(probe, args.trace, out, tmp, report=_read(args.report),
                          task=_read(args.prompt), document=args.document,
                          source=args.source or "model", replay=args.replay)
    print(f"kept under {out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories",
                                     description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command")

    audit = subs.add_parser("audit", help="run each scripted solution under the recorder")
    audit.add_argument("probes", nargs="*")
    audit.add_argument("--tag")
    audit.add_argument("--family", help="audit instances of this probe family instead")
    audit.add_argument("--seeds", help="which instances (default 0-9)")

    record = subs.add_parser("record", help="run each scripted solution through the MCP "
                                            "server with tracing on and keep the conversation")
    record.add_argument("probes", nargs="*")
    record.add_argument("--tag")
    record.add_argument("--out", required=True)
    record.add_argument("--no-index", action="store_true")
    record.add_argument("--family", help="record instances of this probe family instead")
    record.add_argument("--seeds", help="which instances: 0-99, 3, or 0,2,5-7 (default 0-9)")

    convert = subs.add_parser("convert", help="a trace, or a model's run folders, into conversations")
    convert.add_argument("probe", nargs="?")
    convert.add_argument("--trace", help="the run's trace.jsonl")
    convert.add_argument("--run", help="one run folder (runs/<model>/<probe>) instead")
    convert.add_argument("--runs", help="a folder of run folders (runs/<model>) instead")
    convert.add_argument("--out", required=True)
    convert.add_argument("--report", help="the model's final report, as the closing message")
    convert.add_argument("--prompt", help="the prompt the model was handed, as the user message")
    convert.add_argument("--kept-prompt", action="store_true",
                         help="for --run/--runs: use the folder's prompt.txt as the user message")
    convert.add_argument("--document", help="the document the model left: scored, or compared "
                                            "with the replay")
    convert.add_argument("--source", help="who ran it (default: model, or the model folder's name)")
    convert.add_argument("--replay", action="store_true",
                         help="replay the trace on a fresh start even if it carries results")

    rehydrate = subs.add_parser("rehydrate", help="convert --replay, under its earlier name")
    rehydrate.add_argument("probe")
    rehydrate.add_argument("--trace", required=True)
    rehydrate.add_argument("--out", required=True)
    rehydrate.add_argument("--document")
    rehydrate.add_argument("--report")
    rehydrate.add_argument("--prompt")
    rehydrate.add_argument("--source", default="model")

    args = parser.parse_args(argv)
    if args.command == "audit":
        return cmd_audit(args)
    if args.command == "record":
        return cmd_record(args)
    if args.command == "convert":
        return cmd_convert(args)
    if args.command == "rehydrate":
        args.run = args.runs = None
        args.kept_prompt = False
        args.replay = True
        return cmd_convert(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
