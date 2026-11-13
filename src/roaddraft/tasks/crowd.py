"""The crowd dial of the seeded generator (2026-11-12, Robert: "Clearing step").

A seeded sheet carries one line and the lettering its own task puts there, and
the generator sees to it that the engine's default label poses land on nothing
(the curve floor, the tangent floor, the plan window's pad).  So no seeded task
ever asks a drafter to look at what its lettering fell on, which is the whole
of the crowded pilots (``p04``: 13 sheets, none passed by any model) and the
legibility half of the twisted ones (``p17``).

``crowded(task, seed)`` takes a task the generator made and hands back the same
road on a sheet somebody has already worked on:

- a second line, ``ALIGN-2``: a straight road laid across the first, drawn and
  lettered (ticks, station numbers, its bearing and length) the office's way.
  Where the design lives in a base drawing (``annotate-base``) the line and its
  linework go there and its lettering in the sheet file, anchored through the
  reference, as a real sheet file carries it;
- one or two notes lettered on the paper itself, as a real plan sheet's
  construction notes are.

Each is aimed: the default pose of at least one label the task asks for lands
on the second line's lettering, and another on each note.  Measured on the 13
``p04`` sheets lettered at the default poses (2026-11-12), 9 of the 42
collisions are a new label on another line's lettering and 33 are a new label
on lettering drawn on the paper, so the dial carries both.

A crowded task is kept only when the reference solution can clear it: the
truth's ``label_poses`` (the other side of the line, then further off, chosen
as ``tasks.real.choose_poses`` chooses them on a real sheet) put every asked
label clear and the reference scores 100.  Side and offset are not graded
(legibility is), so a drafter is free to clear the sheet another way.  Every
truth sheet lists the start's entities as ``given_entities``: an overlap among
what was handed over is not the drafter's, an overlap with it is.

The crowding is drawn from a stream of its own (``crowd:<seed>``), so the
seed's road, stationing and layout are those of its uncrowded task, whose id
is what it always was.
"""
from __future__ import annotations

import copy
import dataclasses
import random
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.angles import unit_vector
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.labels import compile_label, stationing_plan
from roaddraft.tasks.brief import Task, compute_task_id
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import task_type

#: the types the dial fits: a sheet already set up, and model lettering asked for
CROWD_TYPES = ("annotate-base", "annotate-sheet", "bearings", "curve-callouts", "stationing")
#: the phases that letter the model
LETTERING = ("stationing", "bearings", "callouts")
#: the second line
CROWD_NAME = "ALIGN-2"
#: what a plan sheet's own notes say (the kind a layout carries beside the line)
NOTES = ("EXIST R/W", "CONST C&G", "SAWCUT LINE", "EXIST FENCE", "MATCH EXIST PVMT",
         "EXIST EP", "REMOVE AC DIKE", "CONFORM", "EXIST CULVERT", "TEMP FENCE")
NOTE_HEIGHT_IN = 0.10
#: the level the notes are lettered on
NOTE_LAYER = "rd_LAYOUT-NOTE-anno"
#: the label kinds a crowd may be aimed at: the ones a drafter can set again elsewhere
#: (a station equation's label has one pose)
AIMED = ("station", "pc", "pt", "pcc", "prc", "bearing", "mc")
#: the second line: how far it runs each side of its middle on the paper, how far its
#: middle is set from the label it is aimed at, and the angle it crosses the first line at
HALF_IN = (3.0, 5.5)
JITTER_IN = 0.15
SKEW_DEG = (35.0, 145.0)
NOTE_JITTER_IN = 0.04
#: paper kept between a note and the edge of the viewport
NOTE_EDGE_IN = 0.25
ATTEMPTS = 40
#: where the reference may set a label again (paper inches off the line), its own
#: side first: ``tasks.real``'s lists
POINT_OFFSETS_IN = (0.45, 0.75, 1.05)
BEARING_OFFSETS_IN = (0.06, 0.2, 0.35)
MC_OFFSETS_IN = (0.80, 1.2, 1.6)
_EPS = 0.005


def _r2(v: float) -> float:
    return round(float(v), 2)


def _ok(result: dict, what: str) -> dict:
    if not result.get("ok"):
        raise AssertionError(f"crowd dial bug: {what} failed: {result['error']['message']}")
    return result


def _view(D: dict):
    """The one sheet's viewport: its transform and its frame on the paper."""
    vp = D["sheets"][0]["viewport"]
    t = geo.ViewportTransform(vp["center_paper"], vp["model_center"], vp["feet_per_inch"],
                              vp.get("rotation_deg", 0.0))
    (cx, cy), w, h = vp["center_paper"], float(vp["width_in"]), float(vp["height_in"])
    return t, (cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0)


def _inside(quad, rect, margin: float = 0.0) -> bool:
    return all(rect[0] + margin <= v[0] <= rect[2] - margin
               and rect[1] + margin <= v[1] <= rect[3] - margin for v in quad)


def _centre(quad) -> List[float]:
    return [sum(v[0] for v in quad) / len(quad), sum(v[1] for v in quad) / len(quad)]


def _hit(a, b) -> bool:
    from roaddraft.verify.legibility import overlap_depth
    return overlap_depth(a, b) > _EPS


def targets(task: Task) -> List[dict]:
    """The labels the task asks for that its sheet shows whole and a drafter can
    set again: each with its footprint on the paper at the default pose."""
    from roaddraft.verify.legibility import text_quad
    from roaddraft.verify.match import KIND_GROUP
    D = task.brief.deliverable
    t, frame = _view(D)
    fpi, twist = float(D["feet_per_inch"]), float(D.get("view_rotation") or 0.0)
    scope = set(task.truth.scope)
    out = []
    for row in task.truth.labels:
        if row["kind"] not in AIMED or KIND_GROUP.get(row["kind"]) not in scope:
            continue
        quad = text_quad(t.to_paper(row["position"]), row["content"], row["height"] / fpi,
                         row["rotation_deg"] + twist, row["halign"], row["valign"])
        if _inside(quad, frame):
            out.append({"ref": row["anchor"], "kind": row["kind"], "station": row["station"],
                        "quad": quad})
    return out


def _side_line(rng: random.Random, victim: dict, align: Alignment, D: dict) -> Alignment:
    """A straight second line whose middle falls by ``victim``, across the first."""
    t, _frame = _view(D)
    fpi = float(D["feet_per_inch"])
    heading = float(align.station_to_xy(float(victim["station"]))[1])
    u = unit_vector((heading + rng.uniform(*SKEW_DEG)) % 360.0)
    mid = t.to_model(_centre(victim["quad"]))
    mid = [mid[0] + rng.uniform(-JITTER_IN, JITTER_IN) * fpi,
           mid[1] + rng.uniform(-JITTER_IN, JITTER_IN) * fpi]
    half = rng.uniform(*HALF_IN) * fpi
    pis = [PI([_r2(mid[0] - half * u[0]), _r2(mid[1] - half * u[1])], 0.0),
           PI([_r2(mid[0] + half * u[0]), _r2(mid[1] + half * u[1])], 0.0)]
    begin = 100.0 * rng.randrange(10, 200) + rng.choice((0.0, 20.0, 40.0, 60.0, 80.0))
    return Alignment(name=CROWD_NAME, elements=compile_pis(pis), pis=pis, source="pis",
                     begin_station=begin)


def _line_quads(side: Alignment, D: dict) -> List[list]:
    """The second line's lettering on the paper, as the office letters a line."""
    from roaddraft.verify.legibility import text_quad
    t, _frame = _view(D)
    fpi, twist = float(D["feet_per_inch"]), float(D.get("view_rotation") or 0.0)
    h_in = float(D["text_heights"]["model_label_ft"]) / fpi
    plan = stationing_plan(side, interval=float(D["stationing_interval_ft"]),
                           tick_half=float(D["tick_half_len_ft"]),
                           label_offset=float(D["label_offset_ft"]),
                           lettering=D["station_lettering"],
                           station_side=D["station_label_side"],
                           point_offset=float(D["point_label_offset_ft"]), view_rotation=twist)
    specs = list(plan.labels())
    specs.append(compile_label(side, resolve_anchor(side, parse_anchor("T-1")), "bearing",
                               label_offset=float(D["bearing_label_offset_ft"]),
                               view_rotation=twist))
    return [text_quad(t.to_paper(s.position), s.content, h_in, s.rotation_deg + twist, s.halign,
                      s.valign) for s in specs]


def _draw(rng: random.Random, aimed: Sequence[dict], align: Alignment, D: dict) -> Optional[dict]:
    """One try at a crowd: the second line and the notes, or None when the line
    misses every label it could have been aimed at."""
    from roaddraft.verify.legibility import text_quad
    _t, frame = _view(D)
    victim = rng.choice(list(aimed))
    side = _side_line(rng, victim, align, D)
    quads = _line_quads(side, D)
    struck = [a for a in aimed if any(_hit(a["quad"], q) for q in quads)]
    if not struck:
        return None
    notes = []
    taken = {a["ref"] for a in struck}
    for _ in range(rng.choice((1, 1, 2))):
        free = [a for a in aimed if a["ref"] not in taken] or list(aimed)
        mark = rng.choice(free)
        c = _centre(mark["quad"])
        position = [_r2(c[0] + rng.uniform(-NOTE_JITTER_IN, NOTE_JITTER_IN)),
                    _r2(c[1] + rng.uniform(-NOTE_JITTER_IN, NOTE_JITTER_IN))]
        content = rng.choice(NOTES)
        quad = text_quad(position, content, NOTE_HEIGHT_IN, 0.0, "center", "middle")
        if not _inside(quad, frame, NOTE_EDGE_IN) or not _hit(quad, mark["quad"]):
            continue
        if any(_hit(quad, text_quad(n["position"], n["content"], NOTE_HEIGHT_IN, 0.0, "center",
                                    "middle")) for n in notes):
            continue  # two notes on each other is nobody's sheet
        taken.add(mark["ref"])
        notes.append({"position": position, "content": content, "height_in": NOTE_HEIGHT_IN,
                      "layer": NOTE_LAYER})
    if not notes:
        return None
    return {"alignment": side.to_dict(), "notes": notes}


def _apply(task: Task, crowd: dict, poses: Optional[dict] = None) -> Tuple[Task, dict]:
    """``task`` with ``crowd`` on its starting drawing (and ``poses`` in its
    truth): ``(the task, {"line": ids, "notes": ids})``, the ids being what the
    crowd put in the sheet file."""
    from roaddraft.api.session import Session
    from roaddraft.document.document import Document
    from roaddraft.tasks.prompts import render_prompts
    from roaddraft.tasks.reference import session_for_task
    b0 = task.brief
    D = copy.deepcopy(b0.deliverable)
    D["crowd"] = copy.deepcopy(crowd)
    if poses:
        D["label_poses"] = copy.deepcopy(poses)
    payload = {"generator_version": b0.generator_version, "spec_hash": b0.spec_hash,
               "project": b0.project, "design": b0.design, "deliverable": D}
    brief = dataclasses.replace(b0, task_id=compute_task_id(b0.seed, b0.level, payload),
                                deliverable=D, instructions="", prompts={})
    brief.prompts = render_prompts(brief)
    # (a note the generator added to the explicit prompt stays on it)
    brief.instructions = brief.prompts["explicit"] + b0.instructions[len(b0.prompts["explicit"]):]
    truth = compute_ground_truth(brief)

    S = brief.drafting_spec
    layers = S["layers"]
    ttype = task_type(D["task_type"])
    side = Alignment.from_dict(dict(crowd["alignment"], name=CROWD_NAME))
    files = copy.deepcopy(task.files)
    if ttype.design_referenced:
        # the line and its linework live in the base drawing, its lettering in the sheet file
        base = Document.from_dict(files[D["basefile"]])
        base.design.alignments[CROWD_NAME] = side
        drawn = Session(_document=base)
        _ok(drawn.execute("draw_alignment", {"alignment": CROWD_NAME,
                                             "layer": layers["alignment"]}), "drawing the line")
        if "task_id" in base.meta:
            base.meta["task_id"] = brief.task_id
        files[D["basefile"]] = base.to_dict()
        session = session_for_task(Task(brief=brief, truth=truth,
                                        baseline=copy.deepcopy(task.baseline), files=files))
        ref = D.get("design_reference") or S.get("reference", {}).get("name", "BASE")
        name = f"{ref}:{CROWD_NAME}"
    else:
        doc = Document.from_dict(copy.deepcopy(task.baseline))
        doc.design.alignments[CROWD_NAME] = side
        session = Session(_document=doc)
        _ok(session.execute("draw_alignment", {"alignment": CROWD_NAME,
                                               "layer": layers["alignment"]}), "drawing the line")
        name = CROWD_NAME
    view = {"view_rotation": D["view_rotation"]} if D.get("view_rotation") else {}
    label_h = D["text_heights"]["model_label_ft"]
    made = {"line": [], "notes": []}
    result = _ok(session.execute("annotate_stationing", {
        "space": "model", "alignment": name, "interval": D["stationing_interval_ft"],
        "tick_half_len": D["tick_half_len_ft"], "text_height": label_h,
        "label_offset": D["label_offset_ft"], "layer": layers["ticks"],
        "label_layer": layers["labels"], "lettering": D["station_lettering"],
        "station_side": D["station_label_side"], **view}), "stationing the line")
    made["line"] += result["created"]
    result = _ok(session.execute("place_label", {
        "space": "model", "alignment": name, "anchor": "T-1", "kind": "bearing",
        "height": label_h, "label_offset": D["bearing_label_offset_ft"],
        "layer": layers["labels"], **view}), "lettering the line's bearing")
    made["line"] += result["created"]
    sheet_name = D["sheets"][0]["name"]
    for note in crowd["notes"]:
        result = _ok(session.execute("place_text", {
            "space": sheet_name, "position": list(note["position"]), "content": note["content"],
            "height": note["height_in"], "halign": "center", "valign": "middle",
            "layer": note["layer"]}), "lettering a note")
        made["notes"] += result["created"]
    session.doc.meta.update(task_id=brief.task_id)
    sheet = session.doc.sheet_by_ref(sheet_name)
    given = sorted(set(session.doc.model_entities) | set(sheet.entities))
    for tsh in truth.sheets:  # legibility judges new work against what was handed over
        tsh["given_entities"] = given
    return Task(brief=brief, truth=truth, baseline=session.doc.to_dict(), files=files), made


def _reference(task: Task):
    """The reference solution's report on ``task``, and the finished document."""
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify import verify
    session = session_for_task(task)
    reference_solution(task, session)
    return verify(session.doc, task.truth), session.doc


def struck(task: Task, made: dict) -> Dict[str, int]:
    """What the engine's default poses land on: ``{"line": the labels put on the
    second line's lettering, "notes": the notes a label was put on, "labels":
    the labels on either}``, each a count."""
    report, _doc = _reference(task)
    given = set(task.truth.sheets[0].get("given_entities") or ())
    on_line, notes, labels = set(), set(), set()
    for f in report.check("D1-08").findings:
        if f.code != "overlap":
            continue
        new = [i for i in f.entity_ids if i not in given and ":" not in i]
        if not new:
            continue
        if any(i in made["line"] for i in f.entity_ids):
            on_line.update(new)
            labels.update(new)
        hit = [i for i in f.entity_ids if i in made["notes"]]
        if hit:
            notes.update(hit)
            labels.update(new)
    return {"line": len(on_line), "notes": len(notes), "labels": len(labels)}


def choose_poses(task: Task) -> dict:
    """Where the asked labels go to clear the crowded start: the spec's pose
    unless it lands on what the sheet already shows or on a label set before
    it, then the other side of the line, then further off -- the drafter's
    moves ``tasks.real.choose_poses`` makes on a real sheet.  Station numbers
    come from one stationing command and move as a set.  Only the groups the
    task asks for, and only where something moved: the given lettering stays
    where the reference drafted it."""
    from roaddraft.tasks.reference import session_for_task
    from roaddraft.verify.context import Context
    from roaddraft.verify.legibility import reference_items, sheet_items, text_quad
    D = task.brief.deliverable
    spec = DRAFTING_SPEC_V1
    asked = [p for p in task_type(D["task_type"]).solution_phases() if p in LETTERING]
    session = session_for_task(task)
    ctx = Context.build(session.doc, task.truth, spec)
    sv = ctx.sheets[0]
    view = sv.views[0]
    context = [it.quad for it in sheet_items(ctx, sv) + reference_items(ctx, sv)]
    fpi = float(D["feet_per_inch"])
    vr = float(D.get("view_rotation") or 0.0)
    twist = float(view.vp.rotation_deg)
    h_in = float(spec["text"]["label_height_in"])
    align = Alignment.from_dict(task.brief.design["alignments"][task.brief.alignment_name])
    placed: List[list] = []

    def quad(ls) -> list:
        return text_quad(view.transform.to_paper(ls.position), ls.content, h_in,
                         ls.rotation_deg + twist, ls.halign, ls.valign)

    def cost(q) -> int:
        c = sum(1 for o in context + placed if _hit(q, o))
        return c + (0 if _inside(q, view.rect) else 100)

    def plan_for(side: str):
        return stationing_plan(align, interval=float(D["stationing_interval_ft"]),
                               tick_half=float(D["tick_half_len_ft"]),
                               label_offset=float(D["label_offset_ft"]),
                               lettering=D["station_lettering"], station_side=side,
                               point_offset=float(D["point_label_offset_ft"]), view_rotation=vr)

    def pick(ap, kind, content, default: str, offsets: Sequence[float]):
        other = {"left": "right", "right": "left", "above": "below", "below": "above"}[default]
        scored = []
        for n, (off, side) in enumerate((o, s) for o in offsets for s in (default, other)):
            ls = compile_label(align, ap, kind, side=side, label_offset=off * fpi,
                               content=content, view_rotation=vr)
            c = cost(quad(ls))
            scored.append((c, n, side, off, quad(ls)))
            if c == 0:
                break
        c, n, side, off, q = min(scored, key=lambda x: x[:2])
        placed.append(q)
        return side, off, n > 0

    poses: dict = {}
    if "stationing" in asked:
        default = D["station_label_side"]
        best = None
        for side in (default, "above" if default == "below" else "below"):
            plan = plan_for(side)
            qs = [quad(l) for l in plan.labels() if l.kind in ("station", "equation")]
            c = sum(cost(q) for q in qs)
            if best is None or c < best[0]:
                best = (c, side, qs, plan)
        placed += best[2]
        if best[1] != default:
            poses["station_side"] = best[1]
        pp = spec["labels"]["pc_pt"]
        points, moved = {}, False
        for l in best[3].labels():
            if l.kind not in ("pc", "pt", "pcc", "prc"):
                continue
            side, off, was = pick(resolve_anchor(align, parse_anchor(l.ref)), l.kind, l.content,
                                  pp["side"], POINT_OFFSETS_IN)
            moved = moved or was
            points[l.ref] = {"kind": l.kind, "content": l.content, "side": side,
                             "label_offset_ft": round(off * fpi, 2)}
        if moved:
            poses["points"] = points
    for phase, group, kind, key, offsets in (
            ("bearings", "bearings", "bearing", "bearing", BEARING_OFFSETS_IN),
            ("callouts", "callouts", "mc", "mc", MC_OFFSETS_IN)):
        if phase not in asked:
            continue
        refs = ([f"T-{n}" for n in range(1, len(align.tangents()) + 1)] if kind == "bearing"
                else [f"MC-{n}" for n in range(1, len(align.curves()) + 1)])
        chosen, moved = {}, False
        for ref in refs:
            side, off, was = pick(resolve_anchor(align, parse_anchor(ref)), kind, None,
                                  spec["labels"][key]["side"], offsets)
            moved = moved or was
            chosen[ref] = {"side": side, "label_offset_ft": round(off * fpi, 2)}
        if moved:
            poses[group] = chosen
    return poses


def fits(ttype, n_sheets: int) -> Optional[str]:
    """Why the dial cannot crowd a task of this type and layout, or None."""
    if ttype.name not in CROWD_TYPES:
        return (f"a {ttype.name} task has no lettering to keep clear on a sheet already set up; "
                f"the crowd dial fits {', '.join(CROWD_TYPES)}")
    if n_sheets != 1:
        return "a crowded task is laid out on one sheet"
    return None


def crowded(task: Task, seed: int) -> Task:
    """``task`` on a sheet already worked on: a second lettered line across the
    first and a note or two on the paper, each on the default pose of a label
    the task asks for, with the poses that clear them in the truth.  Raises
    ``ValueError`` when the seed's sheet cannot be crowded that way."""
    D = task.brief.deliverable
    ttype = task_type(D["task_type"])
    why = fits(ttype, len(D["sheets"]))
    if why:
        raise ValueError(why)
    aimed = targets(task)
    if not aimed:
        raise ValueError(f"seed {seed}: its sheet shows no label a crowd could be aimed at")
    align = Alignment.from_dict(task.brief.design["alignments"][task.brief.alignment_name])
    rng = random.Random(f"crowd:{int(seed)}")
    for _attempt in range(ATTEMPTS):
        crowd = _draw(rng, aimed, align, D)
        if crowd is None:
            continue
        made, ids = _apply(task, crowd)
        hits = struck(made, ids)
        if not hits["line"] or hits["notes"] < len(crowd["notes"]):
            continue
        poses = choose_poses(made)
        if not poses:
            continue
        made, ids = _apply(task, crowd, poses)
        report, _doc = _reference(made)
        if abs(report.effective_score - 100.0) < 1e-9:
            return made
    raise ValueError(f"seed {seed}: no crowding of its {ttype.name} sheet that the reference "
                     f"clears in {ATTEMPTS} tries")


__all__ = ["CROWD_TYPES", "CROWD_NAME", "NOTES", "NOTE_LAYER", "crowded", "targets", "struck",
           "choose_poses", "fits"]
