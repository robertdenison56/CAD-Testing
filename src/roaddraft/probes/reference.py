"""Each probe's reference solution, kept as a finished RoadDraft project.

``Probe.solve`` drafts through the engine's command bus, with the commands an
agent sends over MCP. ``write`` keeps what it drafts: the project the probe
starts from, with the document the agent is handed completed and saved under
its own name, so the folder opens in RoadDraft the way a model's finished
project does. Beside the document:

    <name>.jsonl      the journal: the start, then every command the solution
                      ran (Session.replay_journal rebuilds the document from it)
    <probe>.pdf       the sheets plotted with print_pdf, or model space when the
                      document has no sheets
    <probe>.dxf       the document for AutoCAD, Civil 3D or MicroStation: each
                      sheet a layout, the references bound in
    reference.json    the probe, its prompt, and the verdict

The verdict is ``Probe.check`` on the saved document read back from disk,
against the untouched start, which is how a model's document is scored.

    python -m roaddraft.probes reference --out benchmarks/probe_references
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from roaddraft import __version__
from roaddraft.api.session import Session
from roaddraft.document.fileformat import journal_path
from roaddraft.probes import fixture, tasks
from roaddraft.probes.base import Probe, Result

#: what a reference folder says about itself; the index is built from these
RECORD = "reference.json"


@dataclass
class Reference:
    probe: Probe
    #: the document the agent is handed, completed
    document: Path
    #: the start, then every command the scripted solution ran
    journal: Path
    #: Probe.check on the document read back from disk
    result: Result
    pdf: Optional[Path] = None
    dxf: Optional[Path] = None


def _ok(r: dict) -> dict:
    if not r.get("ok"):
        raise RuntimeError(f"{r.get('name')}: {r['error']['message']}")
    return r


def write(probe: Probe, folder, start_dir=None, plots: bool = True) -> Reference:
    """Solve ``probe`` in its start project under ``folder`` and keep the result.

    ``start_dir`` holds that start already built, and is copied rather than
    rebuilt (the L-2 start takes ~20 s); by default the start is built here."""
    if probe.solve is None:
        raise ValueError(f"{probe.id} has no scripted solution")
    folder = Path(folder)
    if start_dir is None:
        document = fixture.start_document(folder, probe.start)
    else:
        shutil.copytree(start_dir, folder, dirs_exist_ok=True)
        document = folder / fixture.START[probe.start]
    baseline = Session.load(document, out_dir=folder)
    session = Session.load(document, out_dir=folder)
    probe.solve(session)
    _ok(session.query("save_document", {"path": str(document)}))
    journal = journal_path(document)
    _ok(session.query("save_journal", {"path": str(journal)}))
    finished = Session.load(document, out_dir=folder)
    ref = Reference(probe, document, journal, probe.check(baseline, finished))
    if plots:
        ref.pdf, ref.dxf = _plot(probe, finished, folder)
    _record(ref, finished)
    return ref


def _plot(probe: Probe, session: Session, folder: Path):
    """The finished document as plotted, and as DXF."""
    sheets = [sheet.name for sheet in session.doc.sheets.values()]
    where = {"sheets": sheets} if sheets else {"space": "model"}
    pdf = _ok(session.query("print_pdf", {**where, "path": str(folder / f"{probe.id}.pdf")}))
    dxf = _ok(session.query("export_dxf", {"path": str(folder / f"{probe.id}.dxf")}))
    return Path(pdf["path"]), Path(dxf["path"])


def _record(ref: Reference, session: Session) -> None:
    attached = session.query("list_references", {}).get("references", [])
    record = {
        "probe": ref.probe.id,
        "prompt": ref.probe.prompt,
        "tags": ref.probe.tags,
        "start": ref.probe.start,
        "document": ref.document.name,
        "references": {r["name"]: r["path"] for r in attached},
        "journal": ref.journal.name,
        "pdf": ref.pdf.name if ref.pdf else None,
        "dxf": ref.dxf.name if ref.dxf else None,
        "passed": ref.result.passed,
        "detail": ref.result.detail,
        "roaddraft": __version__,
    }
    (ref.document.parent / RECORD).write_text(json.dumps(record, indent=1) + "\n")


def records(out) -> List[dict]:
    """Every reference under ``out``, in probe order."""
    order = {p.id: k for k, p in enumerate(tasks.PROBES)}
    found = [json.loads(path.read_text()) for path in Path(out).glob(f"*/{RECORD}")]
    return sorted(found, key=lambda r: (order.get(r["probe"], len(order)), r["probe"]))


INDEX_HEAD = """\
# Probe references

Every probe's scripted solution (`Probe.solve`), kept as a finished RoadDraft
project. Each folder is the project the probe starts from, with the document
the agent is handed completed and saved under its own name: open it in
RoadDraft and it reads its design through the reference beside it, as the
start does. The solution drafts through the engine's command bus, with the
same commands an agent sends over MCP, and the journal beside the document
holds every one of them; `Session.replay_journal` rebuilds the document from it.

Generated, not edited: `python -m roaddraft.probes reference --out {shown}`
(roaddraft {version}). Each verdict is `Probe.check` on the saved document read
back from disk, against a fresh start, which is how a model's document is
scored; `python -m roaddraft.probes score <probe> --doc <document>` repeats it.

    <probe>/<document>      the completed document: the file the agent is handed, finished
    <probe>/<design file>   what the document references, untouched
    <probe>/<name>.jsonl    the journal: the start, then every command the solution ran
    <probe>/<probe>.pdf     the sheets as plotted (print_pdf); model space when it has none
    <probe>/<probe>.dxf     for AutoCAD, Civil 3D or MicroStation: each sheet a layout, references bound in
    <probe>/reference.json  the probe, its prompt and the verdict

{passed} of {total} pass.

| Probe | Tags | Completed document | References | Check, read back from disk |
|---|---|---|---|---|
"""


def _cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def write_index(out, shown: Optional[str] = None) -> Path:
    """``README.md`` for a folder of references: what a folder holds, and one row
    per probe."""
    out = Path(out)
    rows = records(out)
    lines = [INDEX_HEAD.format(shown=shown or out, version=__version__,
                               passed=sum(r["passed"] for r in rows), total=len(rows))]
    for r in rows:
        refs = ", ".join(f"{name}: {path}" for name, path in r["references"].items()) or "none"
        verdict = "PASS" if r["passed"] else "FAIL"
        lines.append(f"| {r['probe']} | {', '.join(r['tags'])} | "
                     f"[{r['document']}]({r['probe']}/{r['document']}) | {_cell(refs)} | "
                     f"{verdict}: {_cell(r['detail'])} |\n")
    index = out / "README.md"
    index.write_text("".join(lines))
    return index


__all__ = ["RECORD", "Reference", "write", "records", "write_index"]
