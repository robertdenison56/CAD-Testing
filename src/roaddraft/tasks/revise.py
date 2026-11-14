"""The revision dial of the seeded generator (2026-11-12, plan §8 build 4).

The redline pilots (``p11``, 12 instances) hand a model a finished sheet and one
change to its design: a curve's radius, a PI moved, the line restationed.  What
the best row misses on 8 of the 12 is lettering left behind from before the
change.  Measured 2026-11-12: on the 12 pilots, the scripted solution with its
re-lettering replaced by one ``update_labels`` passes none.  A curve point
lettered with its text given keeps the old text, a tangent the change brings in
gets no bearing, and stations past a new end get no tick.  What does pass is
the scripted route: take off what was lettered from the old design, letter it
again, and restation every note that cites the line.

``revised(task, seed, kind)`` hands over the seed's finished sheet after the
designer has changed its design:

- the sheet as the office lettered it from the old design (the reference's own
  drafting of every phase the task's type asks for), the title block and north
  arrow too where the type has them;
- on ``annotate-base`` the design changed where it lives, in the base drawing,
  with its centerline and pavement edges redrawn to it, as a designer leaves a
  revision: the drafter has no way into the base file, so the lettering is its
  half;
- on ``annotate-sheet`` the design lives in this file and the change is the
  drafter's to make (2026-11-12, Robert: "Yes, revision only"): the start keeps
  the old design, and the truth grades the design (D1-15) and the centerline
  drawn from it (D1-01) beside the lettering;
- on ``annotate-base`` again, by one of ``BASE_KINDS`` (2026-11-13, Robert:
  "allow them, in the pin's cut"), the change is the drafter's to make where
  the design lives: the base drawing is handed over on the old design, with
  its old centerline and pavement edges.  The drafter opens it, changes the
  line there, redraws its linework, goes back to the sheet file and reads the
  base drawing again, then takes off the old lettering and letters the line
  again.  The truth grades the design, the centerline and the pavement edges
  in the base drawing (D1-15, D1-01, D1-12, read through the reference)
  beside the lettering;
- one or two notes lettered on the paper, each citing a station of the line
  (``CONFORM STA 147+40.00``), the first of them at a point the change
  restations where the line has one (a one-curve line whose PI moves keeps
  nothing past the change, so its note keeps its station).

``kind`` is one of ``KINDS``: ``radius`` (one curve's radius, every PI held),
``pi`` (one curve's PI moved along its back tangent, its radius and every
other PI held) or ``station`` (the line restationed, its geometry held).  The
truth is the revised design's; the brief's ``revision`` names the change, the
ids lettered from the old design (``stale``) and each note's text before and
after.  A revised task is kept only when the reference -- the stale lettering
taken off, the line lettered again, the notes restationed -- scores 100 at
both levels and the start does not.

A note's station is chosen where a drafter can restation it from the sheet
alone: on a tangent the change leaves where it was, past a whole station whose
tick is lettered on that same tangent.  The old tick still marks where the
line's old station was, so ``xy_to_station`` of its point on the revised line,
plus how far past it the note is, is the note's new station.

A revised truth's scope carries ``eval.tools.REVISION_SCOPE`` beside its
groups, which puts ``modify_alignment`` and ``update_labels`` on the drafter's
tool list.  No other task has it, so no other task's list moves.  A truth of
one of ``BASE_KINDS`` carries ``tasks.types.BASE_SCOPE`` as well, which adds
``open_document`` and ``reload_references`` (``eval.tools.BASE_COMMANDS``) and
tells the verifier where the design is graded; neither earlier flavour has it.
A PI is moved by the arithmetic a drafter does from ``measure`` (``moved_pi``),
so a drafter who works it out lands on the revised design exactly.

The revision is drawn from a stream of its own (``revise:<seed>``) and the
unrevised task's id is what it always was.  Equations are refused: what a
restation does to a station equation is a question of its own.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import PI, Alignment, CurveElement, TangentElement, compile_pis
from roaddraft.design.stations import build_equations
from roaddraft.tasks.brief import Task, compute_task_id
from roaddraft.tasks.ground_truth import compute_ground_truth
from roaddraft.tasks.standards import min_radius
from roaddraft.tasks.types import task_type

#: the types the dial fits: a sheet set up and lettered, the lettering asked for
REVISE_TYPES = ("annotate-base", "annotate-sheet")
KINDS = ("radius", "pi", "station")
#: the same three changes, left for the drafter to make in the base drawing that holds the
#: design (``annotate-base`` only): what ``revise=`` takes for that flavour, and what a
#: manifest entry of it carries.  The brief's ``revision`` still names its kind of ``KINDS``
BASE_PREFIX = "base-"
BASE_KINDS = tuple(BASE_PREFIX + kind for kind in KINDS)
#: what the labelers letter in the model from an alignment (a curve number's bubble and
#: leader go with it); the curve table is on the sheet
LETTERING_KINDS = ("tick", "station", "pc", "pt", "pcc", "prc", "equation", "bearing", "mc",
                   "mc_bubble", "mc_leader")
#: the lettering phases a revision of each kind leaves behind: every label records the
#: station it stands at, so a restation leaves them all, the bearings and curve numbers too;
#: the curve data holds no station, so the table stays
STALE_PHASES = {"radius": ("stationing", "bearings", "callouts", "table"),
                "pi": ("stationing", "bearings", "callouts", "table"),
                "station": ("stationing", "bearings", "callouts")}
NOTE_LAYER = "rd_LAYOUT-NOTE-anno"
NOTE_WORDS = ("CONFORM", "BEGIN SAWCUT", "END SAWCUT", "EXIST CULVERT", "MATCH EXIST",
              "BEGIN AC DIKE", "END AC DIKE", "EXIST DRIVEWAY")
NOTE_HEIGHT_IN = 0.10
#: how far a note is set off its point on the paper, tried in turn, either side
NOTE_OFFSETS_IN = (0.8, 1.1, 1.4, 1.7)
NOTE_EDGE_IN = 0.25
#: how far past its whole station a note's station may be, in steps of 5 ft
NOTE_STEPS = range(2, 19)
#: a radius changes by a factor drawn from one of these, rounded to 50 ft
RADIUS_FACTORS = ((0.6, 0.85), (1.15, 1.5))
#: how far a PI moves along its back tangent (ft), and how far a line is restationed
PI_MOVE_FT = (15.0, 45.0)
RESTATION_FT = tuple(range(15, 100, 5))
ATTEMPTS = 30
#: how close to the revised line a point must be to be on it (ft)
ON_LINE_FT = 0.001
_EPS = 0.005


def station_text(raw: float) -> str:
    """A station to the hundredth (``147+65.32``), by whole cents so it never
    rounds to ``+100.00``."""
    cents = int(round(float(raw) * 100.0))
    whole, rest = divmod(cents, 10000)
    return f"{whole}+{rest // 100:02d}.{rest % 100:02d}"


def fits(ttype, n_sheets: int, equations: bool = False) -> Optional[str]:
    """Why the dial cannot revise a task of this type and layout, or None."""
    if ttype.name not in REVISE_TYPES:
        return (f"a {ttype.name} task does not letter a whole line on a sheet set up; the revision "
                f"dial fits {', '.join(REVISE_TYPES)}")
    if n_sheets != 1:
        return "a revised task is laid out on one sheet"
    if equations:
        return "a revised task has no station equation"
    return None


def _ok(result: dict, what: str) -> dict:
    if not result.get("ok"):
        raise AssertionError(f"revision dial bug: {what} failed: {result['error']['message']}")
    return result


def _rows(align: Alignment) -> List[list]:
    """The line's PIs as rows: ``[x, y]`` at the ends, ``[x, y, R]`` at a curve."""
    return [list(p.point) + ([float(p.radius)] if p.radius else []) for p in align.pis]


def _rebuilt(align: Alignment, rows: Sequence[Sequence[float]], begin: float) -> Alignment:
    pis = [PI([float(r[0]), float(r[1])], float(r[2]) if len(r) > 2 else 0.0) for r in rows]
    new = Alignment(name=align.name, elements=compile_pis(pis), pis=pis, source="pis",
                    begin_station=float(begin))
    new.equations = build_equations(float(begin), new.length, [])
    return new


def _sound(align: Alignment, v_mph: int, old: Alignment) -> bool:
    """The generator's own floors still hold, or the old line's where it sat
    below them: curves and tangents long enough to letter, every radius above
    the design speed's, every deflection at least the generator's (its PIs are
    rounded to the hundredth, so a 15° curve comes out a few ten-thousandths
    short)."""
    from roaddraft.tasks.generator import MIN_CURVE_FT, MIN_EXTRA_FT
    r_floor = math.ceil(min_radius(v_mph) * 1.15 / 50.0) * 50.0
    tangents = [el.length for el in old.elements if isinstance(el, TangentElement)]
    tangent_floor = min([MIN_EXTRA_FT] + tangents)
    for el in align.elements:
        if isinstance(el, CurveElement):
            if (el.length < MIN_CURVE_FT - 1e-6 or el.radius < r_floor - 1e-6
                    or el.delta_deg < 15.0 - 0.01):
                return False
        elif el.length < tangent_floor - 1e-6:
            return False
    return True


def _change(rng: random.Random, kind: str, align: Alignment) -> Tuple[dict, Alignment]:
    """One draw of a change of ``kind``: ``(what it is, the revised line)``."""
    rows = _rows(align)
    curves = [i for i, r in enumerate(rows[1:-1], start=1) if len(r) > 2]
    begin = float(align.begin_station)
    st = align.stations()
    if kind == "station":
        by = float(rng.choice((-1, 1)) * rng.choice(RESTATION_FT))
        return ({"kind": kind, "by": by, "from": st.format(begin),
                 "to": station_text(begin + by)}, _rebuilt(align, rows, begin + by))
    # a PI moved along its back tangent turns the tangent ahead of it, so only a line with a
    # curve after it keeps a stretch past the change for a note to be restationed on
    n = rng.randint(1, len(curves) - 1 if kind == "pi" and len(curves) > 1 else len(curves))
    k = curves[n - 1]
    if kind == "radius":
        r0 = float(rows[k][2])
        r1 = round(r0 * rng.uniform(*rng.choice(RADIUS_FACTORS)) / 50.0) * 50.0
        rows[k] = rows[k][:2] + [r1]
        return {"kind": kind, "curve": n, "from": r0, "to": r1}, _rebuilt(align, rows, begin)
    back, pi = rows[k - 1], rows[k]
    by = round(rng.choice((-1, 1)) * rng.uniform(*PI_MOVE_FT), 2)
    rows[k] = moved_pi(back, pi, by) + rows[k][2:]
    return {"kind": kind, "curve": n, "by": by}, _rebuilt(align, rows, begin)


def _w(value: float) -> float:
    """A number as a drafter writes it: to the thousandth."""
    return float(f"{float(value):.3f}")


def moved_pi(back: Sequence[float], pi: Sequence[float], by: float) -> List[float]:
    """``pi`` moved ``by`` ft along its back tangent (from ``back``; + ahead), the
    way a drafter works it out from ``measure``: each coordinate plus the
    difference over the distance times the move, every number to the thousandth.
    The truth is made the same way, so a drafter who works it out gets the
    revised design to the bit."""
    dist = _w(round(math.hypot(pi[0] - back[0], pi[1] - back[1]), 6))
    out = []
    for i in (0, 1):
        d = _w(round(pi[i] - back[i], 6))
        a, b, c = _w(pi[i]), abs(d), abs(float(by))
        out.append(_w(a + b / dist * c if d * by >= 0 else a - b / dist * c))
    return out


def _finished(task: Task):
    """A session on ``task``'s start with every phase the task asks for drafted by
    the reference: the sheet as the office finished it from the design."""
    from roaddraft.tasks.reference import phase_commands, session_for_task
    session = session_for_task(task)
    ttype = task_type(task.brief.deliverable["task_type"])
    for name, params in phase_commands(task, ttype.solution_phases()):
        _ok(session.execute(name, params), name)
    return session


def _stale(session, alignment: str, sheet_name: str, kind: str) -> List[str]:
    """The ids lettered from the line that a revision of ``kind`` leaves behind."""
    doc = session.doc
    ids = [e.id for e in doc.model_entities.values()
           if (e.anchor or {}).get("alignment") == alignment
           and (e.anchor or {}).get("kind") in LETTERING_KINDS]
    if "table" in STALE_PHASES[kind]:
        sheet = doc.sheet_by_ref(sheet_name)
        ids += [e.id for e in sheet.entities.values()
                if (e.anchor or {}).get("alignment") == alignment
                and (e.anchor or {}).get("kind") == "curve_table"]
    return sorted(ids)


def _on(align: Alignment, point) -> Optional[dict]:
    """Where ``point`` falls on ``align`` when it is on it, else None."""
    try:
        r = align.xy_to_station(point)
    except DesignError:
        return None
    if r is None or abs(float(r["offset"])) > ON_LINE_FT:
        return None
    return r


def _candidates(old: Alignment, new: Alignment, ticks: Dict[float, list],
                own: bool = False) -> List[dict]:
    """Where a note may cite the line: ``{"tick", "at", "station", "new"}`` for
    each station ``at`` on a tangent the change leaves in place, past a whole
    station whose lettered tick (``ticks``: its point as the engine reports it)
    is on that tangent too, with the station the note then reads by the
    drafter's own route: from the tick where the change was made elsewhere, and
    (``own``) from the note's own point on the line before the change where the
    drafter makes it."""
    out = []
    end = float(old.end_station)
    for t, point in sorted(ticks.items()):
        _p, _d, i = old.station_to_xy(t)
        if not isinstance(old.elements[i], TangentElement):
            continue
        hit = _on(new, point)
        if hit is None or not isinstance(new.elements[int(hit["element_index"])], TangentElement):
            continue
        new_t = float(hit["station"])
        for k in NOTE_STEPS:
            at = t + 5.0 * k
            if at > end - 5.0:
                break
            p, _d, j = old.station_to_xy(at)
            if j != i:
                break
            there = _on(new, p)
            if there is None or int(there["element_index"]) != int(hit["element_index"]):
                break
            # the drafter writes the tick's new station to the thousandth and adds; where
            # the drafter makes the change, it reads the note's own point before and after
            new_at = (float(there["station"]) if own else round(round(new_t, 3) + (at - t), 3))
            if abs(float(there["station"]) - new_at) > 0.002:
                continue
            cents = new_at * 100.0
            if abs(cents - math.floor(cents) - 0.5) < 0.15:
                continue  # too near a half cent to letter one way for certain
            out.append({"tick": t, "at": at, "new": new_at, "point": list(p),
                        "moved": station_text(new_at) != station_text(at)})
    return out


def _note_spot(candidate: dict, new: Alignment, D: dict, taken: Sequence[list],
               content: str, rng: random.Random) -> Optional[Tuple[list, list]]:
    """Where on the paper a note at ``candidate`` is lettered: ``(position,
    footprint)`` clear of ``taken`` and inside the viewport, or None."""
    from roaddraft.verify.legibility import overlap_depth, text_quad
    vp = D["sheets"][0]["viewport"]
    t = geo.ViewportTransform(vp["center_paper"], vp["model_center"], vp["feet_per_inch"],
                              vp.get("rotation_deg", 0.0))
    (cx, cy), w, h = vp["center_paper"], float(vp["width_in"]), float(vp["height_in"])
    frame = (cx - w / 2.0 + NOTE_EDGE_IN, cy - h / 2.0 + NOTE_EDGE_IN,
             cx + w / 2.0 - NOTE_EDGE_IN, cy + h / 2.0 - NOTE_EDGE_IN)
    q = t.to_paper(candidate["point"])
    heading = math.radians(float(new.xy_to_station(candidate["point"])["direction_deg"])
                           + float(vp.get("rotation_deg", 0.0)))
    normal = (-math.sin(heading), math.cos(heading))
    sides = [1.0, -1.0]
    rng.shuffle(sides)
    for off in NOTE_OFFSETS_IN:
        for s in sides:
            at = [round(q[0] + s * off * normal[0], 2), round(q[1] + s * off * normal[1], 2)]
            quad = text_quad(at, content, NOTE_HEIGHT_IN, 0.0, "center", "middle")
            if not all(frame[0] <= v[0] <= frame[2] and frame[1] <= v[1] <= frame[3]
                       for v in quad):
                continue
            if any(overlap_depth(quad, o) > -0.1 for o in taken):
                continue  # a tenth of an inch clear of everything
            return at, quad
    return None


def _footprints(session, sheet_name: str, truth) -> List[list]:
    """What a note must stay clear of: everything the start's sheet shows, and
    the lettering the truth puts there."""
    from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
    from roaddraft.verify.context import Context
    from roaddraft.verify.legibility import reference_items, sheet_items, text_quad
    ctx = Context.build(session.doc, truth, DRAFTING_SPEC_V1)
    sv = ctx.sheet_view(sheet_name)
    out = [it.quad for it in sheet_items(ctx, sv) + reference_items(ctx, sv)]
    view = sv.views[0]
    fpi, twist = float(view.vp.feet_per_inch), float(view.vp.rotation_deg)
    for row in truth.labels:
        p = view.transform.to_paper(row["position"])
        out.append(text_quad(p, row["content"], float(row["height"]) / fpi,
                             float(row["rotation_deg"]) + twist, row["halign"], row["valign"]))
        if row["kind"] == "mc":
            r = 2.0 * float(row["height"]) / fpi
            out.append([[p[0] - r, p[1] - r], [p[0] + r, p[1] - r], [p[0] + r, p[1] + r],
                        [p[0] - r, p[1] + r]])
    return out


def _brief(task: Task, design: dict, D: dict):
    from roaddraft.tasks.prompts import render_prompts
    b0 = task.brief
    payload = {"generator_version": b0.generator_version, "spec_hash": b0.spec_hash,
               "project": b0.project, "design": design, "deliverable": D}
    brief = dataclasses.replace(b0, task_id=compute_task_id(b0.seed, b0.level, payload),
                                design=design, deliverable=D, instructions="", prompts={})
    brief.prompts = render_prompts(brief)
    brief.instructions = brief.prompts["explicit"]
    return brief


def _truth(brief, own: bool, in_base: bool = False):
    """The revised design's truth.  Its scope carries ``REVISION_SCOPE``, which
    puts ``modify_alignment`` and ``update_labels`` on the drafter's tool list;
    where the drafter makes the change, the design itself and its drawn
    centerline are graded too (D1-15, D1-01).  Where the drafter makes it in
    the base drawing (``in_base``), the pavement edges drawn there are graded
    as well (D1-12), and the scope carries ``BASE_SCOPE``: the three are read
    in the base drawing, and ``open_document`` and ``reload_references`` join
    the tool list."""
    from roaddraft.eval.tools import REVISION_SCOPE
    from roaddraft.tasks.types import BASE_SCOPE, GROUPS
    truth = compute_ground_truth(brief)
    want = (set(truth.scope) | ({"design", "linework"} if own else set())
            | ({"edges"} if in_base else set()))
    truth.scope = ([g for g in GROUPS if g in want] + [REVISION_SCOPE]
                   + ([BASE_SCOPE] if in_base else []))
    return truth


def _attempt(task: Task, rng: random.Random, kind: str, finished, stale: List[str],
             in_base: bool = False) -> Optional[Task]:
    """One try at revising ``task``: the revised task, or None.  ``in_base``:
    the change is left for the drafter to make in the base drawing."""
    from roaddraft.api.session import Session
    from roaddraft.document.document import Document
    from roaddraft.tasks.reference import session_for_task
    b0, D0 = task.brief, task.brief.deliverable
    ttype = task_type(D0["task_type"])
    name = b0.alignment_name
    old = Alignment.from_dict(b0.design["alignments"][name])
    try:
        change, new = _change(rng, kind, old)
    except DesignError:
        return None
    if not _sound(new, int(b0.design.get("design_speed_mph") or b0.project["design_speed_mph"]),
                  old):
        return None
    design = copy.deepcopy(b0.design)
    design["alignments"][name] = new.to_dict()
    design["profiles"] = {}  # the profile was laid out on the old stations
    D = copy.deepcopy(D0)
    D["sheets"][0]["station_range"] = [float(new.begin_station), float(new.end_station)]
    # the width dimensions a sheet of this type never shows were placed on the old stations
    D["width_dimensions"] = []
    S = b0.drafting_spec
    layers = S["layers"]
    files = copy.deepcopy(task.files)
    sheet_doc = Document.from_dict(copy.deepcopy(finished.doc.to_dict()))
    geometry = kind != "station"
    # -- the design changed where it lives, its linework redrawn to it
    handed_base = None
    if ttype.design_referenced:
        if in_base:
            # the change is the drafter's to make there: the base drawing is handed over as
            # it was, on the old design with its old linework (its profile gone, as the
            # revised design has none).  The notes below are still placed against the
            # revised base drawing, which is what the finished sheet shows
            kept = Document.from_dict(copy.deepcopy(files[D0["basefile"]]))
            kept.design.profiles.clear()
            handed_base = kept.to_dict()
        base = Document.from_dict(files[D0["basefile"]])
        base.design.alignments[name] = new
        base.design.profiles.clear()
        drawn = Session(_document=base)
        if geometry:
            _ok(drawn.execute("draw_alignment", {"alignment": name, "layer": layers["alignment"],
                                                 "replace": True}), "redrawing the line")
            pave = D0["pavement"]
            _ok(drawn.execute("draw_offset", {"alignment": name, "offsets": list(pave["offsets_ft"]),
                                              "layer": pave["layer"], "replace": True}),
                "redrawing the edges")
        files[D0["basefile"]] = drawn.doc.to_dict()
        alignment = f"{D0.get('design_reference') or S.get('reference', {}).get('name', 'BASE')}:{name}"
    else:
        # the design lives in this file: the change is the drafter's to make (2026-11-12,
        # Robert: "Yes, revision only"), so the start keeps the old design; the profile goes,
        # as the revised design has none
        sheet_doc.design.profiles.clear()
        alignment = name
    own = in_base or not ttype.design_referenced
    # in this file the labels follow the change; through a reference they do not, so what
    # was lettered from the old design comes off, whoever changed the base drawing
    D["revision"] = {**change, "alignment": alignment, "by_drafter": own,
                     "stale": [] if own and not in_base else list(stale), "notes": []}
    brief = _brief(task, design, D)
    truth = _truth(brief, own, in_base)
    plain = Task(brief=brief, truth=truth, baseline=sheet_doc.to_dict(), files=files)
    # -- the notes that cite the line, placed where the drafter can restation them
    session = session_for_task(plain)
    sheet_name = D["sheets"][0]["name"]
    # each tick's point as the engine reports it, which is what the drafter works from
    rows = _ok(session.query("find_entities", {"anchor": {"alignment": alignment, "kind": "tick"},
                                               "include_references": False, "limit": 500}),
               "reading the ticks")["entities"]
    ticks = {round(float(r["anchor"]["station"]), 2): r["point"] for r in rows}
    spots = _candidates(old, new, ticks, own)
    # a note the change restations, where the line has one; else one it leaves as it reads
    # (a one-curve line whose PI moves keeps nothing past the change)
    moved = [c for c in spots if c["moved"]] or spots
    if not moved:
        return None
    taken = _footprints(session, sheet_name, truth)
    notes = []
    picks = [rng.choice(moved)]
    if rng.random() < 0.5:
        rest = [c for c in spots if abs(c["at"] - picks[0]["at"]) > 150.0]
        if rest:
            picks.append(rng.choice(rest))
    words = list(NOTE_WORDS)
    rng.shuffle(words)
    for pick, word in zip(picks, words):
        before = f"{word} STA {station_text(pick['at'])}"
        spot = _note_spot(pick, new, D, taken, before, rng)
        if spot is None:
            continue
        position, quad = spot
        taken.append(quad)
        result = _ok(session.execute("place_text", {
            "space": sheet_name, "position": position, "content": before,
            "height": NOTE_HEIGHT_IN, "halign": "center", "valign": "middle",
            "layer": NOTE_LAYER}), "lettering a note")
        notes.append({"id": result["created"][0], "before": before,
                      "after": f"{word} STA {station_text(pick['new'])}",
                      "station": pick["at"], "new_station": pick["new"]})
    if not notes:
        return None
    D["revision"]["notes"] = notes
    brief = _brief(task, design, D)
    truth = _truth(brief, own, in_base)
    session.doc.meta.update(task_id=brief.task_id)
    if handed_base is not None:
        files[D0["basefile"]] = handed_base
    if ttype.design_referenced and "task_id" in (files[D0["basefile"]].get("meta") or {}):
        files[D0["basefile"]]["meta"]["task_id"] = brief.task_id
    return Task(brief=brief, truth=truth, baseline=session.doc.to_dict(), files=files)


def _scores(task: Task) -> Tuple[float, float, List[str]]:
    """``(the start's score, the reference's lowest score over the levels, the
    notes the reference leaves reading anything but their new text)``."""
    from roaddraft.tasks.reference import reference_solution, session_for_task
    from roaddraft.verify import verify
    start = session_for_task(task)
    before = verify(start.doc, task.truth, prompt_level="vague").effective_score
    session = session_for_task(task)
    reference_solution(task, session)
    after = min(verify(session.doc, task.truth, prompt_level=level).effective_score
                for level in ("explicit", "vague"))
    return before, after, left_stale(task, session.doc)


def left_stale(task: Task, doc) -> List[str]:
    """What a revised task's drafter left behind: the ids lettered from the old
    design still in ``doc``, and each note not reading its restationed text.
    Empty on any other task."""
    R = task.brief.deliverable.get("revision")
    if not R:
        return []
    sheet = doc.sheet_by_ref(task.brief.deliverable["sheets"][0]["name"])
    left = [i for i in R["stale"] if i in doc.model_entities
            or (sheet is not None and i in sheet.entities)]
    for note in R["notes"]:
        e = sheet.entities.get(note["id"]) if sheet is not None else None
        if e is None or getattr(e, "content", None) != note["after"]:
            left.append(note["id"])
    return left


def revised(task: Task, seed: int, kind=True) -> Task:
    """``task``'s finished sheet after the designer has changed its design:
    ``kind`` of ``KINDS`` (True: the seed's own pick), or of ``BASE_KINDS`` for
    the same change left to the drafter to make in the base drawing.  Raises
    ``ValueError`` when no revision of the seed's line keeps it lettered
    cleanly."""
    D = task.brief.deliverable
    ttype = task_type(D["task_type"])
    rng = random.Random(f"revise:{int(seed)}")
    if kind is True:
        kind = rng.choice(KINDS)
    in_base = kind in BASE_KINDS
    if in_base:
        kind = kind[len(BASE_PREFIX):]
    if kind not in KINDS:
        raise ValueError(f"unknown revision {kind!r}; kinds: {', '.join(KINDS + BASE_KINDS)}")
    why = fits(ttype, len(D["sheets"]),
               bool(Alignment.from_dict(task.brief.design["alignments"][
                   task.brief.alignment_name]).equations))
    if why:
        raise ValueError(why)
    if in_base and not ttype.design_referenced:
        raise ValueError(f"a {ttype.name} task keeps its design in its own file; a change made "
                         f"in the base drawing ({', '.join(BASE_KINDS)}) fits annotate-base")
    finished = _finished(task)
    name = task.brief.alignment_name
    S = task.brief.drafting_spec
    alignment = (f"{D.get('design_reference') or S.get('reference', {}).get('name', 'BASE')}:{name}"
                 if ttype.design_referenced else name)
    stale = _stale(finished, alignment, D["sheets"][0]["name"], kind)
    for _attempt_n in range(ATTEMPTS):
        made = _attempt(task, rng, kind, finished, stale, in_base)
        if made is None:
            continue
        before, after, left = _scores(made)
        if after == 100.0 and before < 100.0 and not left:
            return made
    raise ValueError(f"seed {seed}: no {kind} revision of its {ttype.name} sheet that the "
                     f"reference letters cleanly in {ATTEMPTS} tries")


__all__ = ["REVISE_TYPES", "KINDS", "BASE_KINDS", "LETTERING_KINDS", "STALE_PHASES", "NOTE_LAYER",
           "station_text", "moved_pi", "fits", "revised", "left_stale"]
