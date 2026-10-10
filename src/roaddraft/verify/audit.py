"""Journal audit (eval plan section 3.5 item 7): informational in v1.

Counts what an episode did that a later spec might want to judge: anchors
edited by hand, anchored text dragged, design commands, raw text and
linework, undo/redo.  It reads a bus journal (``[{"seq", "name",
"params"}]``) or a saved one (an ``init`` record, then ``command`` records).
Failed calls never reach a journal, so invalid-call counts are the harness's
to report.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from roaddraft.document.document import Document
from roaddraft.document.entities import Text

DESIGN_COMMANDS = ("create_alignment", "modify_alignment", "delete_alignment", "create_profile",
                   "delete_profile", "import_landxml")
MOVE_COMMANDS = ("move_entities", "rotate_entities", "scale_entities", "mirror_entities")
RAW_TEXT = ("place_text", "place_table")
RAW_LINEWORK = ("draw_line", "draw_arc", "draw_polyline", "draw_circle")


def audit_journal(journal: Iterable[dict], doc: Optional[Document] = None) -> dict:
    entries = [e for e in journal
               if isinstance(e, dict) and e.get("type", "command") == "command" and "name" in e]
    names = Counter(e["name"] for e in entries)
    anchored_text = set()
    if doc is not None:
        spaces = [doc.model_entities] + [s.entities for s in doc.sheets.values()]
        anchored_text = {eid for ents in spaces for eid, e in ents.items()
                         if isinstance(e, Text) and e.anchor}
    anchor_edits = sum(1 for e in entries if e["name"] == "modify_entity"
                       and "anchor" in ((e.get("params") or {}).get("changes") or {}))
    moves = sum(1 for e in entries if e["name"] in MOVE_COMMANDS
                and anchored_text.intersection((e.get("params") or {}).get("ids") or []))
    return {"commands": len(entries),
            "by_command": dict(sorted(names.items())),
            "anchor_edits": anchor_edits,
            "anchored_text_moves": moves,
            "design_commands": sum(names[n] for n in DESIGN_COMMANDS),
            "raw_text": sum(names[n] for n in RAW_TEXT),
            "raw_linework": sum(names[n] for n in RAW_LINEWORK),
            "undos": names["undo"], "redos": names["redo"]}


__all__ = ["audit_journal", "DESIGN_COMMANDS"]
