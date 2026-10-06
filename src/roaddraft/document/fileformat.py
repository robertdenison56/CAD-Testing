"""The document file format: what a RoadDraft drawing is on disk.

A drawing is ``Document.to_dict()`` serialized as JSON. Two file shapes carry
it, and a reader picks between them by *content*, never by extension, so a
renamed or extension-less file still opens:

  ``.rdraft``     the application document - what a person saves, sends and
                  double-clicks, and the extension the desktop build registers
                  with the OS as its own filetype.
  ``.rdoc.json``  the open interchange form: plain JSON, diffable in git. Task
                  fixtures, probe fixtures and example output stay here.

Both shapes hold the same bytes today. They are separate names because the
application document is meant to grow a zip container (document + journal +
embedded references + thumbnail, so a project travels as one file) while the
interchange form is not: a container would cost the line-by-line diffs the
task and probe fixtures rely on. Every read and write of a document goes
through ``read_document``/``write_document``, so that change lands here and
no caller has to know which shape it got.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The application document: what a person saves and the desktop build owns.
DOCUMENT_EXT = ".rdraft"

#: The open interchange form. Plain JSON, kept diffable for fixtures and tests.
INTERCHANGE_EXT = ".rdoc.json"

#: Extensions a save path may already carry; anything else gains DOCUMENT_EXT.
KNOWN_EXTS = (DOCUMENT_EXT, INTERCHANGE_EXT, ".json")

#: First bytes of a zip local file header - the container shape, not yet written.
_ZIP_MAGIC = b"PK\x03\x04"


class DocumentFormatError(ValueError):
    """A file is not a readable RoadDraft document."""


def normalize_path(path) -> Path:
    """Give a save path the application extension when it carries none of ours.

    The extension is appended rather than substituted: names in this project
    carry dotted qualifiers (``SR-100.sheets``, ``SR-100.model``) that
    ``with_suffix`` would eat.
    """
    p = Path(path)
    name = p.name.lower()
    if any(name.endswith(ext) for ext in KNOWN_EXTS):
        return p
    return p.with_name(p.name + DOCUMENT_EXT)


def sniff(head: bytes) -> str:
    """Which file shape these opening bytes are: 'json', 'container', or ''."""
    if head.startswith(_ZIP_MAGIC):
        return "container"
    if head.lstrip()[:1] == b"{":
        return "json"
    return ""


def read_document(path) -> dict:
    """The document dict held in ``path``, whatever file shape holds it.

    Raises ``FileNotFoundError`` if it is not there and ``DocumentFormatError``
    if it is not a RoadDraft document. That last check earns its keep because
    ``Document.from_dict`` defaults every field, so any stray JSON object would
    otherwise open as a silently blank drawing.
    """
    p = Path(path)
    raw = p.read_bytes()
    shape = sniff(raw[:8])
    if shape == "container":
        raise DocumentFormatError(
            f"{p.name} is a container-format document; this build reads JSON "
            "documents only")
    if shape != "json":
        raise DocumentFormatError(f"{p.name} is not a RoadDraft document")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise DocumentFormatError(f"{p.name} is not readable JSON: {ex}") from ex
    if not isinstance(data, dict) or "schema_version" not in data:
        raise DocumentFormatError(
            f"{p.name} is JSON but not a RoadDraft document: no schema_version")
    return data


def write_document(path, data: dict) -> Path:
    """Write a document dict, creating parent folders. Returns the path written,
    which may have gained ``DOCUMENT_EXT``."""
    p = normalize_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    return p


def journal_path(document) -> Path:
    """``SR-100.sheets.rdoc.json`` -> ``SR-100.sheets.jsonl``, beside it: where a
    document's journal is kept."""
    name = Path(document).name
    for suffix in (INTERCHANGE_EXT, DOCUMENT_EXT, ".json"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return Path(document).with_name(name + ".jsonl")
