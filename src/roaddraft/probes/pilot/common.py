"""What the pilots share: the example sheets, staged into a probe's project.

A pilot starts from a real sheet: the redrafted file set (the sheet file and
the base files it references, every ``.rdraft`` in the folder) copied into
the probe's project folder, then cut, planted or stripped there. The check
grades against the redraft itself, read from the repository, which the
model cannot reach (``roaddraft-mcp --root`` holds it to its run folder).
"""
from __future__ import annotations

import csv
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

from roaddraft.api.session import Session
from roaddraft.document.document import Document
from roaddraft.document.fileformat import read_document
from roaddraft.probes import fixture

REPO = Path(__file__).resolve().parents[4]
EXAMPLES = REPO / "examples" / "Exmple Plans"
#: the redrafted file sets, one folder per published sheet
REDRAFT_ROOT = EXAMPLES / "Redraft"
#: the published sheets, one PDF per page (``Sheets/manifest.csv``)
SHEETS_ROOT = EXAMPLES / "Sheets"
AGENCIES = ("Caltrans-PPM", "WFL", "CFL", "FDOT-NexGen")


@lru_cache(maxsize=None)
def manifest(agency: str) -> List[dict]:
    """The agency's ``redraft-manifest.csv`` rows (id, section, sheet, status,
    kind, family, sheet_file, bases, alignments, note)."""
    path = REDRAFT_ROOT / agency / "redraft-manifest.csv"
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def row(sheet_id: str) -> dict:
    """The manifest row of a redrafted sheet (``PPM-045``, ``WFL-Plan-Profile-Sheets-p14``)."""
    for agency in AGENCIES:
        for r in manifest(agency):
            if r["id"] == sheet_id:
                return dict(r, agency=agency)
    raise KeyError(f"no redrafted sheet {sheet_id!r}")


def folder(sheet_id: str) -> Path:
    """The redraft folder of a sheet: its ``.rdraft`` set, PDF, DXF and PNG."""
    r = row(sheet_id)
    dirs = [p for p in (REDRAFT_ROOT / r["agency"]).rglob("*") if p.is_dir()]
    # an exact name first: CFL-D-Plan-and-Profile is also the prefix of ...-with-Bridge
    hits = [p for p in dirs if p.name == sheet_id] or \
        [p for p in dirs if p.name.startswith(sheet_id + "-")]
    if len(hits) != 1:
        raise KeyError(f"{sheet_id}: {len(hits)} redraft folders")
    return hits[0]


def sheet_file(sheet_id: str) -> str:
    """The file name of the sheet's own drawing (the rest of the set are its bases)."""
    return row(sheet_id)["sheet_file"]


def source_pdf(sheet_id: str) -> Path:
    """The published one-page PDF the redraft was drawn from (``Sheets/<agency>/...``)."""
    r = row(sheet_id)
    hits = sorted((SHEETS_ROOT / r["agency"]).rglob(f"{folder(sheet_id).name}.pdf"))
    if not hits:
        raise KeyError(f"{sheet_id}: no published PDF under {SHEETS_ROOT / r['agency']}")
    return hits[0]


def stage(out: Path, sheet_id: str) -> Dict[str, Path]:
    """Copy the sheet's ``.rdraft`` set into ``out``: ``{file name: path}``.
    References are relative, so the copies find each other."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    copied = {}
    for src in sorted(folder(sheet_id).glob("*.rdraft")):
        dst = out / src.name
        shutil.copyfile(src, dst)
        copied[src.name] = dst
    return copied


def load(path: Path, out_dir: Optional[Path] = None) -> Session:
    """A session on a document file; its references resolve from its own folder."""
    path = Path(path)
    return Session.load(path, out_dir=out_dir or path.parent)


def document(path: Path) -> Document:
    """A document read without a session (no references loaded)."""
    doc = Document.from_dict(read_document(Path(path)))
    doc._path = Path(path)
    return doc


def ok(result: dict) -> dict:
    """A command's result, or the error it came back with raised."""
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name', 'command')}: {result['error']['message']}")
    return result


def save(session: Session, path: Path) -> Path:
    ok(session.query("save_document", {"path": str(path)}))
    return Path(path)


def rasterize(pdf: Path, png: Path, dpi: int = 200) -> Path:
    """One PDF page to a PNG (poppler's ``pdftoppm``); a scan's stand-in."""
    png = Path(png)
    png.parent.mkdir(parents=True, exist_ok=True)
    stem = png.with_suffix("")
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-singlefile", str(pdf), str(stem)],
                   check=True, capture_output=True)
    return png


def register(name: str, filename: str, builder: Callable[[Path], Path]) -> str:
    """Register a start document for ``Probe.start``: ``builder(out)`` writes the
    project under ``out`` and returns the document the agent is handed, which
    must be ``out / filename``. Returns the name, for ``Probe(start=...)``."""
    def build(out: Path) -> Path:
        path = Path(builder(Path(out)))
        if path.resolve() != (Path(out) / filename).resolve():
            raise RuntimeError(f"start {name!r} built {path}, not {Path(out) / filename}")
        return path
    fixture.register_start(name, filename, build)
    return name


def answers(session: Session) -> Dict[str, str]:
    """What a model recorded with ``set_meta`` (a probe that asks for answers
    keeps them in the document, so the check still reads only the drawing)."""
    return {str(k): str(v) for k, v in (session.doc.meta or {}).items()}


__all__ = ["REPO", "EXAMPLES", "REDRAFT_ROOT", "SHEETS_ROOT", "AGENCIES", "manifest", "row",
           "folder", "sheet_file", "source_pdf", "stage", "load", "document", "ok", "save",
           "rasterize", "register", "answers"]
