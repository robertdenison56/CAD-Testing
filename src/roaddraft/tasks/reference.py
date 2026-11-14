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
from roaddraft.design.labels import DEFAULT_VALIGN
from roaddraft.document.document import Document
from roaddraft.document.fileformat import INTERCHANGE_EXT, write_document
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
    ttype = task_type(D.get("task_type", "plan-sheet"))
    # the alignment the labelers are pointed at: the document's own, or the base
    # drawing's through the reference when the design lives only there
    ref_name = D.get("design_reference") or S.get("reference", {}).get("name", "BASE")
    AL = f"{ref_name}:{A}" if ttype.design_referenced else A
    layers = S["layers"]
    props = S["layer_props"]
    sheets = D["sheets"]
    alignment = task.brief.design["alignments"][A]
    n_tangents = sum(1 for el in alignment["elements"] if el["kind"] == "tangent")
    n_curves = sum(1 for el in alignment["elements"] if el["kind"] == "curve")
    label_h = D["text_heights"]["model_label_ft"]
    # model labels read upright through a twisted viewport (a real sheet's)
    view = {"view_rotation": D["view_rotation"]} if D.get("view_rotation") else {}
    # where a real sheet's labels go to clear its existing work (tasks.real)
    poses = D.get("label_poses") or {}

    def pose(group: str, ref: str) -> dict:
        pz = (poses.get(group) or {}).get(ref)
        return {"side": pz["side"], "label_offset": pz["label_offset_ft"]} if pz else {}

    steps: List[tuple] = []
    for phase in PHASE_ORDER:
        if phase not in want:
            continue
        if phase == "design":
            params = {"name": A, "begin_station": alignment["begin_station"],
                      "pis": [[pi["point"][0], pi["point"][1]] + ([pi["radius"]] if pi["radius"] else [])
                              for pi in alignment["pis"]]}
            if alignment.get("equations"):
                params["equations"] = [{"back": q["back"], "ahead": q["ahead"]}
                                       for q in alignment["equations"]]
            if alignment.get("description"):
                params["description"] = alignment["description"]
            steps.append(("create_alignment", params))
        elif phase == "layers":
            for name in S.get("layer_set") or list(dict.fromkeys(layers.values())):
                steps.append(("create_layer", {"name": name, **props[name]}))
        elif phase == "linework":
            steps.append(("draw_alignment", {"alignment": A, "layer": layers["alignment"]}))
        elif phase == "edges":
            pave = D["pavement"]
            steps.append(("draw_offset", {"alignment": A, "offsets": list(pave["offsets_ft"]),
                                          "layer": pave["layer"]}))
        elif phase == "stationing":
            params = {
                "space": "model", "alignment": AL, "interval": D["stationing_interval_ft"],
                "tick_half_len": D["tick_half_len_ft"], "text_height": label_h,
                "label_offset": D["label_offset_ft"], "layer": layers["ticks"],
                "label_layer": layers["labels"],
                "lettering": D.get("station_lettering", "caltrans")}
            if D.get("station_label_side"):
                params["station_side"] = D["station_label_side"]
            if D.get("point_label_offset_ft") is not None:
                params["point_label_offset"] = D["point_label_offset_ft"]
            params.update(view)
            if poses.get("station_side"):
                params["station_side"] = poses["station_side"]
            if poses.get("points"):  # each curve point placed on its own, where it clears
                params["include_pc_pt"] = False
            steps.append(("annotate_stationing", params))
            for ref, pz in (poses.get("points") or {}).items():
                steps.append(("place_label", {
                    "space": "model", "alignment": AL, "anchor": ref, "kind": pz["kind"],
                    "content": pz["content"], "height": label_h, "layer": layers["labels"],
                    **pose("points", ref), **view}))
        elif phase == "bearings":
            bearing_offset = D.get("bearing_label_offset_ft", D["label_offset_ft"])
            for n in range(1, n_tangents + 1):
                steps.append(("place_label", {
                    "space": "model", "alignment": AL, "anchor": f"T-{n}", "kind": "bearing",
                    "height": label_h, "label_offset": bearing_offset,
                    "layer": layers["labels"], **pose("bearings", f"T-{n}"), **view}))
        elif phase == "callouts":
            for n in range(1, n_curves + 1):
                steps.append(("place_label", {
                    "space": "model", "alignment": AL, "anchor": f"MC-{n}", "kind": "mc",
                    "height": label_h,
                    "label_offset": D.get("mc_label_offset_ft", D["label_offset_ft"]),
                    "layer": layers["labels"], **pose("callouts", f"MC-{n}"), **view}))
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
                          "line_point": ahead, "text_height": label_h, "layer": D["dims_layer"],
                          **view}
                if wd.get("text_gap_ft"):
                    params["text_gap"] = wd["text_gap_ft"]
                steps.append(("place_dimension", params))
        elif phase == "reference":
            for r in D.get("references") or []:  # a real sheet's base files, as published
                steps.append(("attach_reference", {"name": r["name"], "path": r["file"],
                                                   "space": r.get("space", "model")}))
            if not D.get("basefile"):
                continue  # nothing to attach: the drawing is all in this document
            ref_spec = S.get("reference", {})
            steps.append(("attach_reference", {
                "name": ref_spec.get("name", "BASE"), "path": D["basefile"],
                "space": ref_spec.get("space", "model")}))
        elif phase == "sheet":
            for sh in sheets:
                params = {"name": sh["name"], "size": sh["size"]}
                if sh.get("template"):  # a real sheet's border
                    params["title_block_template"] = sh["template"]
                steps.append(("create_sheet", params))
                steps.append(("create_viewport", {"sheet": sh["name"], **sh["viewport"]}))
            drawn = set()
            for sh in sheets:
                for m in sh.get("matches", []):
                    if m["station"] not in drawn:  # one match line, labelled on both sheets
                        drawn.add(m["station"])
                        half = m["half_width_ft"]
                        steps.append(("draw_station_offset", {
                            "alignment": AL, "layer": layers.get("match", layers["ticks"]),
                            "points": [f"{m['station_text']}@{half:g}L",
                                       f"{m['station_text']}@{half:g}R"]}))
                    # the match label reads along its match line, centred on the offset
                    # point and beside the line (the pose the generator fitted on the sheet)
                    steps.append(("place_label", {
                        "space": sh["name"], "alignment": AL, "anchor": m["station_text"],
                        "kind": "custom", "content": m["label"], "rotation": m["rotation"],
                        "side": m["side"], "label_offset": m["label_offset_in"],
                        "halign": "center", "valign": DEFAULT_VALIGN[m["side"]],
                        "height": S["text"]["label_height_in"],
                        "layer": layers.get("match", layers["labels"])}))
        elif phase == "table":
            for sh in sheets:
                if not sh["curves"]:
                    continue
                params = {"space": sh["name"], "alignment": AL,
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
                here = sh.get("north_arrow") or {}  # a real sheet's: where it is clear, to north
                params = {"space": sh["name"], "block_name": na["block"],
                          "position": here.get("position", na["position"]),
                          "scale": here.get("scale", na["scale"]),
                          "layer": layers.get("symbols", "0")}
                if here.get("rotation_deg"):
                    params["rotation_deg"] = here["rotation_deg"]
                steps.append(("insert_block", params))
        elif phase == "title":
            for sh in sheets:
                steps.append(("fill_title_block", {"sheet": sh["name"],
                                                   "fields": sh["title_block_fields"]}))
        elif phase == "notes":
            # a real sheet's construction callouts (tasks.real_callouts): each note placed
            # on the sheet, aimed by station and offset at the line it calls out, its text
            # where the published note stood
            for c in D.get("callouts") or []:
                steps.append(("place_callout", {
                    "space": sheets[0]["name"],
                    "alignment": f"{c['reference']}:{c['alignment']}",
                    "target_anchor": {"station": c["station_text"], "offset": c["offset"]},
                    "position": list(c["position"]), "content": c["content"],
                    "height": c["height"], "arrow": bool(c.get("arrow", True)),
                    "layer": c.get("layer") or layers["labels"]}))
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
    phases the task asks for (plus the layers when they are not given).  On a
    revised task (the generator's revision dial, ``tasks.revise``) the start is
    a finished sheet: what was lettered from the old design comes off, the
    phases the change leaves behind are lettered again, and each note citing
    the line reads its restationed text.  Where the change is left to the
    drafter in the base drawing, the list carries ``open_document`` twice: the
    base drawing, where the line is changed and its linework redrawn, and the
    sheet file again (``document_name``), where the base drawing is reloaded.
    That one is the episode's tool, not a bus command; ``reference_solution``
    reads it the same way."""
    D = task.brief.deliverable
    ttype = task_type(D.get("task_type", "plan-sheet"))
    revision = D.get("revision")
    if revision:
        from roaddraft.tasks.revise import STALE_PHASES
        notes = [("modify_entity", {"id": n["id"], "changes": {"content": n["after"]}})
                 for n in revision["notes"] if n["after"] != n["before"]]
        change: List[tuple] = []
        if revision.get("by_drafter"):
            # the design is the drafter's to change: the centerline redrawn with it
            A = task.brief.alignment_name
            new = Alignment.from_dict(task.brief.design["alignments"][A])
            changes = ({"begin_station": revision["to"]} if revision["kind"] == "station" else
                       {"pis": [list(p.point) + ([float(p.radius)] if p.radius else [])
                                for p in new.pis]})
            change = [("modify_alignment", {"name": A, "changes": changes, "redraw": True})]
            if not ttype.design_referenced:
                # this file's own line: its labels follow it (modify_alignment does both)
                return [_meta(task)] + change + notes
            # the base drawing's line (tasks.revise.BASE_KINDS): changed there, its pavement
            # edges redrawn too, then back in the sheet file the base drawing is read again
            if revision["kind"] != "station":
                pave = D["pavement"]
                change.append(("draw_offset", {"alignment": A, "offsets": list(pave["offsets_ft"]),
                                               "layer": pave["layer"], "replace": True}))
            change = ([("open_document", {"path": D["basefile"]})] + change
                      + [("open_document", {"path": document_name(task)}),
                         ("reload_references", {})])
        return ([_meta(task)] + change
                + [("delete_entities", {"ids": list(revision["stale"])})] + notes
                + phase_commands(task, [p for p in ttype.solution_phases()
                                        if p in STALE_PHASES[revision["kind"]]]))
    return [_meta(task)] + phase_commands(task, ttype.solution_phases())


def document_name(task: Task) -> str:
    """The file name a task's own document goes by beside the files it ships
    (``session_for_task``, and an episode's folder)."""
    return f"{task.task_id}{INTERCHANGE_EXT}"


def reference_solution(task: Task, session: Session) -> List[dict]:
    """Execute the solution commands; returns the journal.  Raises
    ``RuntimeError`` on any non-ok result (warnings are collected on
    ``session.reference_warnings``).  An ``open_document`` in the list (a
    revision made in the base drawing) switches to that file of the task,
    loaded from beside ``session``'s document and written back after every
    command, or back to ``session`` by its own name; the journal returned is
    ``session``'s, the document the task hands over."""
    warnings: List[str] = []
    current = session
    for name, params in solution_commands(task):
        if name == "open_document":
            home = Path(session.doc._path)
            if params["path"] == home.name:
                current = session
            else:
                current = Session.load(home.parent / params["path"], out_dir=session.out_dir)
            continue
        result = current.execute(name, params)
        if not result["ok"]:
            raise RuntimeError(f"reference solution: {name} failed: "
                               f"{result['error']['message']} ({result['error'].get('hint')})")
        if current is not session:
            write_document(current.doc._path, current.doc.to_dict())
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
           "document_name", "reference_solution", "check_replay"]
