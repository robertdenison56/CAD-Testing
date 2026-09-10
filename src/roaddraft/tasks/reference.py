"""The reference solution for a D1 task (spec section 7.6): the ordered command
list a perfect drafter would send, executed through a Session.

Because every command calls the same design functions the ground truth was
computed with, the resulting document matches the truth exactly; the journal
it leaves behind is a replayable expert trajectory.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from roaddraft.api.session import Session
from roaddraft.document.document import Document
from roaddraft.tasks.brief import Task


def session_for_task(task: Task, out_dir=None) -> Session:
    """A fresh session on the task's baseline document (design pre-seeded)."""
    return Session(_document=Document.from_dict(task.baseline), out_dir=out_dir)


def reference_commands(task: Task) -> List[tuple]:
    """``[(command, params), ...]`` in the reference order."""
    D = task.brief.deliverable
    S = task.brief.drafting_spec
    A = task.brief.alignment_name
    layers = S["layers"]
    props = S["layer_props"]
    steps: List[tuple] = [
        ("set_meta", {"updates": {"task_id": task.brief.task_id,
                                  "spec_version": task.brief.spec_version}}),
    ]
    for role in ("alignment", "ticks", "labels", "tables"):
        name = layers[role]
        steps.append(("create_layer", {"name": name, **props[name]}))
    steps.append(("draw_alignment", {"alignment": A, "layer": layers["alignment"]}))
    steps.append(("annotate_stationing", {
        "space": "model", "alignment": A, "interval": D["stationing_interval_ft"],
        "tick_half_len": D["tick_half_len_ft"],
        "text_height": D["text_heights"]["model_label_ft"],
        "label_offset": D["label_offset_ft"], "layer": layers["ticks"],
        "label_layer": layers["labels"]}))
    alignment = task.brief.design["alignments"][A]
    n_tangents = sum(1 for el in alignment["elements"] if el["kind"] == "tangent")
    n_curves = sum(1 for el in alignment["elements"] if el["kind"] == "curve")
    bearing_offset = D.get("bearing_label_offset_ft", D["label_offset_ft"])
    for n in range(1, n_tangents + 1):
        steps.append(("place_label", {
            "space": "model", "alignment": A, "anchor": f"T-{n}", "kind": "bearing",
            "height": D["text_heights"]["model_label_ft"], "label_offset": bearing_offset,
            "layer": layers["labels"]}))
    for n in range(1, n_curves + 1):
        steps.append(("place_label", {
            "space": "model", "alignment": A, "anchor": f"MC-{n}", "kind": "mc",
            "height": D["text_heights"]["model_label_ft"], "label_offset": D["label_offset_ft"],
            "layer": layers["labels"]}))
    steps.append(("create_sheet", {"name": D["sheet_name"], "size": D["sheet_size"]}))
    steps.append(("create_viewport", {"sheet": D["sheet_name"], **D["viewport"]}))
    steps.append(("place_curve_table", {
        "space": D["sheet_name"], "alignment": A, "position": D["curve_table_position"],
        "columns": D["curve_table_columns"], "text_height": D["text_heights"]["sheet_table_in"],
        "layer": layers["tables"]}))
    na = S["sheet"]["north_arrow"]
    steps.append(("insert_block", {"space": D["sheet_name"], "block_name": na["block"],
                                   "position": na["position"], "scale": na["scale"]}))
    steps.append(("fill_title_block", {"sheet": D["sheet_name"],
                                       "fields": D["title_block_fields"]}))
    return steps


def reference_solution(task: Task, session: Session) -> List[dict]:
    """Execute the reference commands; returns the journal.  Raises
    ``RuntimeError`` on any non-ok result (warnings are collected on
    ``session.reference_warnings``)."""
    warnings: List[str] = []
    for name, params in reference_commands(task):
        result = session.execute(name, params)
        if not result["ok"]:
            raise RuntimeError(f"reference solution: {name} failed: "
                               f"{result['error']['message']} ({result['error'].get('hint')})")
        warnings.extend(f"{name}: {w}" for w in result.get("warnings", []))
    session.reference_warnings = warnings
    return session.bus.journal


def check_replay(session: Session, path) -> bool:
    """Save the journal and replay it into a fresh session; True when the
    replayed document equals the live one."""
    path = Path(path)
    result = session.query("save_journal", {"path": str(path)})
    if not result["ok"]:
        raise RuntimeError(result["error"]["message"])
    replayed = Session.replay_journal(path)
    return replayed.doc.to_dict() == session.doc.to_dict()


__all__ = ["session_for_task", "reference_commands", "reference_solution", "check_replay"]
