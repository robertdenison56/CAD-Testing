"""The trajectory log (eval plan section 4.6): one JSON-lines file per
episode -- ``header``, one ``turn`` per agent turn, the replayable
``journal`` (baseline, the task's files, the bus entries), ``verify``,
``audit``, ``end``.  The journal block alone rebuilds the document, so any
episode can be re-verified with a newer verifier without rerunning its
agent (``reverify``).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from roaddraft.api.session import Session
from roaddraft.document.document import Document

RECORD_TYPES = ("header", "turn", "journal", "verify", "audit", "end")


def episode_path(root, task_id: str, agent: str, dialect: str, mode: str, level: str,
                 sample: int) -> Path:
    """``<root>/episodes/<task_id>.<agent>.<dialect>.<mode>.<level>.<sample>.jsonl``."""
    safe = agent.replace("/", "-").replace(" ", "_")
    return Path(root) / "episodes" / f"{task_id}.{safe}.{dialect}.{mode}.{level}.{sample}.jsonl"


class TrajectoryWriter:
    """Appends records to an episode file as the episode runs, so a stopped
    run leaves what it had."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8")

    def write(self, record: dict) -> None:
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def read_episode(path) -> Dict[str, object]:
    """The records of an episode file by type: ``header``, ``turns`` (a list),
    ``journal``, ``verify``, ``audit``, ``end``; missing ones are None."""
    out: Dict[str, object] = {"header": None, "turns": [], "journal": None, "verify": None,
                              "audit": None, "end": None}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        kind = rec.get("type")
        if kind == "turn":
            out["turns"].append(rec)
        elif kind in out:
            out[kind] = rec
    return out


def is_complete(path) -> bool:
    """An episode file with an ``end`` record: the runner skips it on resume."""
    p = Path(path)
    if not p.exists():
        return False
    try:
        return read_episode(p)["end"] is not None
    except (OSError, ValueError):
        return False


def replay_journal(journal: dict, out_dir=None) -> Session:
    """A session rebuilt from a trajectory's journal block: the baseline
    document, the task's files written beside it, the entries re-executed.

    A block may carry ``opened`` (an episode that changed another document of
    its task, such as the base drawing a sheet file references): each is that
    file's own commands and how many of the handed document's entries came
    before it was opened.  They are replayed in the file at that point and
    written back, and at the end the session's document reads its references
    from the files as they then stand, as the episode graded it."""
    doc = Document.from_dict(journal["baseline"])
    session = Session(_document=doc, out_dir=out_dir)
    files = journal.get("files") or {}
    folder = None
    if files:
        if out_dir is None:
            session._task_dir = tempfile.TemporaryDirectory(prefix="roaddraft-replay-")
            out_dir = session._task_dir.name
        folder = Path(out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (folder / name).write_text(json.dumps(content))
        session.doc._path = folder / journal.get("document_name", "replay.rdoc.json")
    entries = list(journal.get("entries", []))
    opened = [v for v in journal.get("opened") or [] if int(v["at"]) <= len(entries)]
    changed = bool(opened)
    for i in range(len(entries) + 1):
        while opened and int(opened[0]["at"]) <= i:
            _replay_opened(folder, opened.pop(0))
        if i == len(entries):
            break
        entry = entries[i]
        result = session.execute(entry["name"], entry.get("params") or {})
        if not result.get("ok"):
            raise RuntimeError(f"replay: {entry['name']} failed: {result['error']['message']}")
    if changed:
        session.doc._ref_cache.clear()
    return session


def _replay_opened(folder: Optional[Path], visit: dict) -> None:
    """Replay what an episode did to another document of its task, in that
    document's file, and write it back."""
    from roaddraft.document.fileformat import write_document
    if folder is None:
        raise RuntimeError(f"replay: {visit['document']} was opened, and the block ships no files")
    path = folder / visit["document"]
    other = Session.load(path)
    for entry in visit.get("entries") or []:
        result = other.execute(entry["name"], entry.get("params") or {})
        if not result.get("ok"):
            raise RuntimeError(f"replay: {entry['name']} in {visit['document']} failed: "
                               f"{result['error']['message']}")
    write_document(path, other.doc.to_dict())


def reverify(path, level: Optional[str] = None):
    """Re-score an episode from its journal block with the current verifier.
    ``level`` defaults to the level the episode was posed at."""
    from roaddraft.tasks.brief import GroundTruth
    from roaddraft.verify import verify
    records = read_episode(path)
    if records["journal"] is None or records["header"] is None:
        raise ValueError(f"{path}: no journal block to replay")
    truth = records["journal"].get("truth")
    if truth is None:
        raise ValueError(f"{path}: the journal block carries no truth")
    session = replay_journal(records["journal"])
    level = level or records["header"].get("level", "explicit")
    return verify(session.doc, GroundTruth.from_dict(truth), journal=session.bus.journal,
                  prompt_level=level)


__all__ = ["RECORD_TYPES", "episode_path", "TrajectoryWriter", "read_episode", "is_complete",
           "replay_journal", "reverify"]
