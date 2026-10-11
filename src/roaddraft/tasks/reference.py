"""The reference solution for a D1 task (spec section 7.6): the ordered command
list a perfect drafter would send, executed through a Session.

The drawing is produced in phases (``tasks.types.PHASES``).  A task's
starting document already carries its *given* phases, drafted by these same
commands, and ``reference_solution`` runs the phases the task asks for.
Because every command calls the same design functions the ground truth was
computed with, the result matches the truth exactly; the journal it leaves
behind is a replayable expert trajectory.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Iterable, List

from roaddraft.api.session import Session
from roaddraft.design.horizontal import Alignment
from roaddraft.document.document import Document
from roaddraft.document.fileformat import INTERCHANGE_EXT
from roaddraft.tasks.brief import Task
from roaddraft.tasks.types import PHASE_ORDER, task_type  # noqa: F401


def session_for_task(task: Task, out_dir=None) -> Session:
    """A fresh session on the task's starting document.

    A task that ships files (a base drawing to attach) has them written
    beside the document in ``out_dir`` -- a temporary folder, kept alive on
    the session, when none is given -- so relative reference paths resolve."""
    session = Session(_document=Document.from_dict(task.baseline), out_dir=out_dir)
    if task.files:
        if out_dir is None:
            session._task_dir = tempfile.TemporaryDirectory(prefix="roaddraft-task-")
            out_dir = session._task_dir.name
        folder = Path(out_dir)
        folder.mkdir(parents=True, exist_ok=True)
        for name, content in task.files.items():
            (folder / name).write_text(json.dumps(content))
        session.doc._path = folder / f"{task.task_id}{INTERCHANGE_EXT}"
    return session


def phase_commands(task: Task, phases: Iterable[str]) -> List[tuple]:
    """``[(command, params), ...]`` drafting ``phases`` in reference order."""
    want = set(phases)
    D = task.brief.deliverable
    S = task.brief.drafting_spec
    A = task.brief.alignment_name
    layers = S["layers"]
    props = S["layer_props"]
    sheets = D["sheets"]
    alignment = task.brief.design["alignments"][A]
    n_tangents = sum(1 for el in alignment["elements"] if el["kind"] == "tangent")
    n_curves = sum(1 for el in alignment["elements"] if el["kind"] == "curve")
    label_h = D["text_heights"]["model_label_ft"]
    steps: List[tuple] = []
    for phase in PHASE_ORDER:
        if phase not in want:
            continue
        if phase == "layers":
            for name in layers.values():
                steps.append(("create_layer", {"name": name, **props[name]}))
        elif phase == "linework":
            steps.append(("draw_alignment", {"alignment": A, "layer": layers["alignment"]}))
        elif phase == "edges":
            pave = D["pavement"]
            steps.append(("draw_offset", {"alignment": A, "offsets": list(pave["offsets_ft"]),
                                          "layer": pave["layer"]}))
        elif phase == "stationing":
            steps.append(("annotate_stationing", {
                "space": "model", "alignment": A, "interval": D["stationing_interval_ft"],
                "tick_half_len": D["tick_half_len_ft"], "text_height": label_h,
                "label_offset": D["label_offset_ft"], "layer": layers["ticks"],
                "label_layer": layers["labels"]}))
        elif phase == "bearings":
            bearing_offset = D.get("bearing_label_offset_ft", D["label_offset_ft"])
            for n in range(1, n_tangents + 1):
                steps.append(("place_label", {
                    "space": "model", "alignment": A, "anchor": f"T-{n}", "kind": "bearing",
                    "height": label_h, "label_offset": bearing_offset,
                    "layer": layers["labels"]}))
        elif phase == "callouts":
            for n in range(1, n_curves + 1):
                steps.append(("place_label", {
                    "space": "model", "alignment": A, "anchor": f"MC-{n}", "kind": "mc",
                    "height": label_h,
                    "label_offset": D.get("mc_label_offset_ft", D["label_offset_ft"]),
                    "layer": layers["labels"]}))
        elif phase == "widths":
            align = Alignment.from_dict(alignment)
            half = float(D["pavement"]["half_width_ft"])
            for wd in D["width_dimensions"]:
                raw = float(wd["station"])
                p1 = align.station_to_xy(raw, -half)[0]
                p2 = align.station_to_xy(raw, half)[0]
                ahead = align.station_to_xy(min(raw + float(wd["line_offset_ft"]),
                                                align.end_station), 0.0)[0]
                params = {"space": "model", "kind": "aligned", "p1": p1, "p2": p2,
                          "line_point": ahead, "text_height": label_h, "layer": D["dims_layer"]}
                if wd.get("text_gap_ft"):
                    params["text_gap"] = wd["text_gap_ft"]
                steps.append(("place_dimension", params))
        elif phase == "reference":
            if not D.get("basefile"):
                continue  # nothing to attach: the drawing is all in this document
            ref_spec = S.get("reference", {})
            steps.append(("attach_reference", {
                "name": ref_spec.get("name", "BASE"), "path": D["basefile"],
                "space": ref_spec.get("space", "model")}))
        elif phase == "sheet":
            for sh in sheets:
                steps.append(("create_sheet", {"name": sh["name"], "size": sh["size"]}))
                steps.append(("create_viewport", {"sheet": sh["name"], **sh["viewport"]}))
            drawn = set()
            for sh in sheets:
                for m in sh.get("matches", []):
                    if m["station"] not in drawn:  # one match line, labelled on both sheets
                        drawn.add(m["station"])
                        half = m["half_width_ft"]
                        steps.append(("draw_station_offset", {
                            "alignment": A, "layer": layers["ticks"],
                            "points": [f"{m['station_text']}@{half:g}L",
                                       f"{m['station_text']}@{half:g}R"]}))
                    steps.append(("place_label", {
                        "space": sh["name"], "alignment": A, "anchor": m["station_text"],
                        "kind": "custom", "content": m["label"], "rotation": m["rotation"],
                        "side": m["side"], "label_offset": m["label_offset_in"],
                        "height": S["text"]["label_height_in"], "layer": layers["labels"]}))
        elif phase == "table":
            for sh in sheets:
                if not sh["curves"]:
                    continue
                params = {"space": sh["name"], "alignment": A,
                          "position": sh["curve_table_position"],
                          "columns": D["curve_table_columns"],
                          "text_height": D["text_heights"]["sheet_table_in"],
                          "layer": layers["tables"]}
                if len(sheets) > 1:
                    params["curves"] = list(sh["curves"])
                steps.append(("place_curve_table", params))
        elif phase == "north":
            na = S["sheet"]["north_arrow"]
            for sh in sheets:
                steps.append(("insert_block", {"space": sh["name"], "block_name": na["block"],
                                               "position": na["position"], "scale": na["scale"]}))
        elif phase == "title":
            for sh in sheets:
                steps.append(("fill_title_block", {"sheet": sh["name"],
                                                   "fields": sh["title_block_fields"]}))
    return steps


def _meta(task: Task) -> tuple:
    return ("set_meta", {"updates": {"task_id": task.brief.task_id,
                                     "spec_version": task.brief.spec_version}})


def reference_commands(task: Task) -> List[tuple]:
    """The whole drawing from the bare design: every phase the finished drawing
    of this task's type shows, in reference order."""
    ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
    return [_meta(task)] + phase_commands(task, ttype.shown())


def solution_commands(task: Task) -> List[tuple]:
    """What the reference drafter does on the task's starting document: the
    phases the task asks for (plus the layers when they are not given)."""
    ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
    return [_meta(task)] + phase_commands(task, ttype.solution_phases())


def reference_solution(task: Task, session: Session) -> List[dict]:
    """Execute the solution commands; returns the journal.  Raises
    ``RuntimeError`` on any non-ok result (warnings are collected on
    ``session.reference_warnings``)."""
    warnings: List[str] = []
    for name, params in solution_commands(task):
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


__all__ = ["session_for_task", "phase_commands", "reference_commands", "solution_commands",
           "reference_solution", "check_replay"]
