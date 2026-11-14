"""Generated deeds to plot, check and balance (2026-11-13, training plan §8 build 5).

The deed half of the survey-trap pilots (``p03-misclosure-*``, three instances on
agency sheets) hands a model a legal description that does not close and asks
for the misclosure, the precision and the parcel balanced by the compass
(Bowditch) rule holding the point of beginning.  None of the pilots' sheets may
train (plan decision 7), and the deed needs none of them: a deed is a list of
courses from a point, and a drawing to put it on.  ``deed_probe(seed)`` makes
one from the seed alone:

- the start: a seeded design (``tasks.generator.generate_task``, its centerline
  drawn by the reference), the right of way drawn each side as raw linework on
  ``rd_RIGHT-OF-WAY`` (no anchor records, the way deed lines arrive), the
  office's empty ``V-PROP`` layer for property lines, and the annotation scale
  the drawing is plotted at.  One file, no sheet;
- the deed: a parcel beside the road, beginning at a point on the right of way
  on a tangent, running along it (about half of them on into the road's curve,
  as a tangent curve at the right of way's radius: one in three by the draw, and
  every line with no tangent of 160 ft), then three to five courses away from the
  road and back.  Written to the second and the hundredth, with
  one or two scrivener's errors planted (a distance 0.08-0.32 ft off, a bearing
  10-45 seconds off), so that as written it misses its start by 0.06-0.5 ft at
  a precision between 1:2,500 and 1:15,000 (the pilots' are 1:4,259-1:6,534);
- the prompts: the pilots' own wording (``probes.pilot.survey._deed_prompt`` and
  ``_deed_vague``) on the deed's text;
- the check: the pilots' own (``survey.check_deed``; at the vague level
  ``survey.lenient_layer`` of it), on the deed as written: every corner within
  0.02 ft of the compass balance, nothing else on the layer, closed, the curve on
  its balanced arc, the area labelled inside, misclosure, precision and area
  recorded with ``set_meta``.

The task is a probe task (``eval.probe_tasks``): the pilots run on that harness,
with the MCP server's tools and a pass/fail check of their own, and so do these.
Nothing here is added to ``probes/pilot`` (whose files the held-out set's
hashes cover) or to ``tasks.types``; the start is registered with
``probes.fixture.register_start`` under ``train-deed-<seed>``.  Every random
draw comes from the stream ``deed:<seed>``.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from roaddraft.design import cogo
from roaddraft.design.angles import format_bearing, format_dms
from roaddraft.probes import fixture
from roaddraft.probes.base import Probe
from roaddraft.probes.pilot import survey

#: the training set's seeds (the other sets hold 10000-18299)
SEEDS = range(19000, 19300)
#: the file the drafter is handed
FILE = "design.rdraft"
#: the office's property-line layer, empty in the start, and the right of way's
LAYER = "V-PROP"
RW_LAYER = "rd_RIGHT-OF-WAY"
#: the scale the design file is plotted at (its annotation scale)
SCALE_FPI = 50.0
#: the task type the report strata see, and the pilot family the set carries
TASK_TYPE = "train-survey-traps"
FAMILY = "p03"
#: id prefix of a generated probe task
ID_PREFIX = "TR-"
#: how far off a planted error may leave the deed, and its precision
MISS_FT = (0.06, 0.5)
PRECISION = (2500.0, 15000.0)
ATTEMPTS = 40


def _f2(value: float) -> float:
    return round(float(value) + 0.0, 2)


def _bearing(az: float) -> str:
    return format_bearing(az % 360.0)


def _dms(deg: float) -> str:
    return format_dms(deg)


def _route(project: str) -> str:
    """``SR 12`` out of ``SR 12 SAFETY IMPROVEMENTS``; the project name when it has no route."""
    words = project.split()
    return " ".join(words[:2]) if len(words) >= 2 and words[1][:1].isdigit() else project


_CARDINAL = ((0, "northerly"), (45, "northeasterly"), (90, "easterly"), (135, "southeasterly"),
             (180, "southerly"), (225, "southwesterly"), (270, "westerly"), (315, "northwesterly"))


def _cardinal(az: float) -> str:
    az %= 360.0
    return min(_CARDINAL, key=lambda c: min(abs(az - c[0]), 360.0 - abs(az - c[0])))[1]


@dataclass(frozen=True)
class DeedTask:
    """One generated deed: its probe, the deed as written, and what the generator chose."""
    seed: int
    probe: Probe
    deed: survey.Deed
    base_task_id: str
    curve: bool
    errors: Tuple[str, ...]
    misclosure: float
    precision: float

    def task_id(self, level: str) -> str:
        """``TR-<probe id>-<hash>`` over the task text at ``level`` and the design it is on,
        so a changed generator or prompt is a new task."""
        from roaddraft.eval.probe_tasks import brief_text
        h = hashlib.sha256((brief_text(self.probe, level) + "\0" + self.base_task_id)
                           .encode("utf-8")).hexdigest()[:10]
        return f"{ID_PREFIX}{self.probe.id}-{h}"


# ------------------------------------------------------------------ the start


def _base(seed: int, rng: random.Random):
    """The seeded design under the deed: ``(task, session)`` with the centerline drawn."""
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import phase_commands, session_for_task
    task = generate_task(seed, curves=rng.choice((1, 2, 3)), equations=False,
                         task_type="draw-alignment", sheets=1)
    session = session_for_task(task)
    for name, params in phase_commands(task, ["linework"]):
        _ok(session.execute(name, params))
    return task, session


def _ok(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


def _start(session, alignment: str, rw: float) -> None:
    """The right of way each side, the empty property-line layer and the plot scale."""
    doc = session.doc
    ids = sorted(e.id for e in doc.model_entities.values()
                 if (e.anchor or {}).get("kind") == "element"
                 and (e.anchor or {}).get("alignment") == alignment)
    ids.sort(key=lambda i: float((doc.model_entities[i].anchor or {}).get("station", 0.0)))
    _ok(session.execute("offset_entity", {"ids": ids, "offsets": [-rw, rw], "layer": RW_LAYER}))
    for e in doc.model_entities.values():
        if e.layer == RW_LAYER:
            e.anchor = None
    _ok(session.execute("create_layer", {"name": LAYER, "color": "magenta", "linetype": "phantom",
                                         "lineweight_mm": 0.35, "description": "property lines"}))
    _ok(session.execute("set_annotation_scale", {"scale": SCALE_FPI}))
    for key in ("task_id", "spec_version"):
        (doc.meta or {}).pop(key, None)


# ------------------------------------------------------------------ the deed


def _courses(rng: random.Random, session, alignment: str, rw: float,
             want_curve: bool) -> Optional[Tuple[list, list, bool, str]]:
    """The parcel's true corners and the courses as the deed writes them, before any
    error: ``(pob, legs, curve, away_word)``, or None when this seed's line has no room."""
    tangents = session.query("get_design_data", {"alignment": alignment, "kind": "tangents"})["rows"]
    curves = session.query("get_design_data", {"alignment": alignment, "kind": "curves"})["rows"]
    side = rng.choice((1, -1))                 # +1 right of the line, -1 left
    curve = None
    bends = [(t, c) for t in tangents for c in curves
             if abs(c["pc_station"] - t["end_station"]) < 1e-6 and t["length"] >= 40.0]
    straights = [t for t in tangents if t["length"] >= 160.0]
    if bends and (want_curve or not straights):  # a tangent with a curve after it
        tangent, curve = rng.choice(bends)
    elif straights:
        tangent = rng.choice(straights)
    else:
        longest = max(tangents, key=lambda t: t["length"])
        if longest["length"] < 60.0:
            return None
        tangent = longest
    az = float(tangent["azimuth_deg"])
    length = float(tangent["length"])
    away = az + 90.0 * side
    if curve is None:
        run = rng.uniform(0.55, 0.9) * length
        u = rng.uniform(0.05, 1.0) * (length - run) * 0.9
        legs = [{"bearing": _bearing(az), "distance": _f2(run)}]
    else:
        u = rng.uniform(0.1, 0.5) * length
        run = length - u
        turn = "right" if curve["direction"] == "R" else "left"
        # the right of way inside the curve has the smaller radius
        r = float(curve["radius"]) - rw if (side > 0) == (turn == "right") else float(curve["radius"]) + rw
        delta = float(curve["delta_deg"]) * rng.uniform(0.35, 0.85)
        legs = [{"bearing": _bearing(az), "distance": _f2(run)},
                {"radius": _f2(r), "turn": turn, "delta": _dms(delta)}]
    start = cogo.forward(tangent["start"], az, u)
    pob = [_f2(v) for v in cogo.forward(start, away, rw)]
    t = cogo.run_traverse(pob, [dict(leg) for leg in legs])
    end = list(t.courses[-1].end)
    out_az = (float(curve["azimuth_in_deg"]) + (1 if legs[-1].get("turn") == "right" else -1)
              * float(cogo.parse_dms(legs[-1]["delta"]))) if curve is not None else az
    # back across the parcel: out from the road, along a back line, in to the start
    depth_a, depth_b = rng.uniform(120.0, 320.0), rng.uniform(120.0, 320.0)
    a = cogo.forward(end, out_az + 90.0 * side + rng.uniform(-12.0, 12.0), depth_a)
    b = cogo.forward(pob, az + 90.0 * side + rng.uniform(-12.0, 12.0), depth_b)
    corners = [a]
    if rng.random() < 0.6:  # a jog in the back line
        mid = [(a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0]
        corners.append(cogo.forward(mid, away, rng.uniform(-40.0, 40.0)))
    corners.append(b)
    here = end
    for p in corners:
        az_k, d = cogo.inverse(here, p)
        legs.append({"bearing": _bearing(az_k), "distance": _f2(d)})
        here = cogo.run_traverse(pob, [dict(leg) for leg in legs]).courses[-1].end
    az_k, d = cogo.inverse(here, pob)          # the closing course, as written it closes
    legs.append({"bearing": _bearing(az_k), "distance": _f2(d)})
    return pob, legs, curve is not None, _cardinal(away)


def _plant(rng: random.Random, legs: list) -> Tuple[list, Tuple[str, ...]]:
    """One or two scrivener's errors on the straight courses: a distance written
    0.08-0.32 ft off, a bearing written 10-45 seconds off."""
    straight = [i for i, leg in enumerate(legs) if "bearing" in leg]
    legs = [dict(leg) for leg in legs]
    count = rng.choice((1, 2))
    chosen = rng.sample(straight, count)
    kinds = ["distance", "bearing"] if count == 2 else [rng.choice(("distance", "bearing"))]
    said = []
    for i, kind in zip(chosen, kinds):
        sign = rng.choice((1, -1))
        if kind == "distance":
            by = _f2(rng.uniform(0.08, 0.32))
            legs[i]["distance"] = _f2(legs[i]["distance"] + sign * by)
            said.append(f"course {i + 1} distance {sign * by:+.2f} ft")
        else:
            sec = rng.randint(10, 45)
            az = cogo.parse_quadrant_bearing(legs[i]["bearing"]) + sign * sec / 3600.0
            legs[i]["bearing"] = _bearing(az)
            said.append(f"course {i + 1} bearing {sign * sec:+d}\"")
    return legs, tuple(said)


def _deed_text(pob, legs, curve: bool, away_word: str, route: str) -> str:
    c = [survey._course_text(leg) for leg in legs]
    n, e = pob[1], pob[0]
    on = 2 if curve else 1
    text = (f"BEGINNING at a point on the {away_word} right of way line of {route} at "
            f"N {n:,.2f}, E {e:,.2f}; thence along said right of way line {c[0]}; ")
    if curve:
        text += f"thence continuing along said right of way line {c[1]}; "
    rest = c[on:]
    text += f"thence leaving said right of way line {rest[0]}; "
    for course in rest[1:-1]:
        text += f"thence {course}; "
    text += f"thence {rest[-1]} to the POINT OF BEGINNING."
    return text


# ------------------------------------------------------------------ the probe


def _check(deed: survey.Deed):
    return lambda baseline, submitted: survey.check_deed(deed, baseline, submitted)


def _vague_check(deed: survey.Deed):
    return survey.lenient_layer(
        lambda baseline, submitted, layer: survey.check_deed(replace(deed, layer=layer),
                                                             baseline, submitted))


@lru_cache(maxsize=None)
def deed_task(seed: int) -> DeedTask:
    """The generated deed of ``seed``; ``ValueError`` when the seed's line gives none."""
    rng = random.Random(f"deed:{seed}")
    task, session = _base(seed, rng)
    alignment = task.brief.alignment_name
    rw = _f2(rng.uniform(40.0, 75.0))
    want_curve = rng.random() < 1.0 / 3.0
    for _ in range(ATTEMPTS):
        drawn = _courses(rng, session, alignment, rw, want_curve)
        if drawn is None:
            raise ValueError(f"seed {seed}: no tangent long enough for a deed")
        pob, true_legs, curve, away_word = drawn
        legs, errors = _plant(rng, true_legs)
        t = cogo.run_traverse(pob, [dict(leg) for leg in legs], close=True)
        m = t.misclosure()
        precision = m["perimeter"] / m["distance"] if m["distance"] else math.inf
        if MISS_FT[0] <= m["distance"] <= MISS_FT[1] and PRECISION[0] <= precision <= PRECISION[1]:
            break
    else:
        raise ValueError(f"seed {seed}: no planted error leaves a deed in range")
    _start(session, alignment, rw)
    route = _route(str((session.doc.meta or {}).get("project_name") or alignment))
    probe_id = f"t03-deed-{seed}"
    deed = survey.Deed(id=probe_id, sheet_id="", file=FILE, pob=tuple(pob), legs=tuple(legs),
                       layer=LAYER)
    text = _deed_text(pob, legs, curve, away_word, route)
    intro = f"Right of Way sent the grant deed for the parcel {away_word} of {route}."
    explicit = survey._deed_prompt(
        intro + " Plot it in this design file (on the project's coordinates).", text, "")
    vague = survey._deed_vague(intro, text)
    start = _register(seed, session)
    probe = Probe(id=probe_id, prompt=explicit, vague=vague, check=_check(deed),
                  vague_check=_vague_check(deed), solve=lambda s: survey.solve_deed(deed, s),
                  start=start, tags=["survey", "cogo", "train"], family=FAMILY,
                  params={"seed": seed, "curve": curve, "errors": list(errors)},
                  note=(f"Generated deed of {len(legs)} courses ({'with' if curve else 'no'} curve) "
                        f"on seed {seed}'s design, planted: {'; '.join(errors)}; misses by "
                        f"{m['distance']:.3f} ft, 1:{precision:,.0f}."))
    return DeedTask(seed, probe, deed, task.task_id, curve, errors, m["distance"], precision)


_STARTS: Dict[int, dict] = {}


def _register(seed: int, session) -> str:
    """Register the start ``train-deed-<seed>``: the document as built, written to the
    project folder each time an episode starts."""
    from roaddraft.document.fileformat import write_document
    name = f"train-deed-{seed}"
    _STARTS[seed] = session.doc.to_dict()
    if name in fixture.EXTRA_STARTS:
        return name

    def build(out: Path) -> Path:
        path = Path(out) / FILE
        write_document(path, _STARTS[seed])
        return path

    fixture.register_start(name, FILE, build)
    return name


# ------------------------------------------------------------------ the set


def entry(seed: int) -> dict:
    """A manifest entry of ``train-deeds``."""
    d = deed_task(seed)
    return {"seed": seed, "family": FAMILY, "task_type": TASK_TYPE, "kind": "deed",
            "curve": d.curve, "courses": len(d.deed.legs), "errors": list(d.errors),
            "misclosure_ft": round(d.misclosure, 4), "precision": round(d.precision, 1),
            "base_task_id": d.base_task_id,
            "task_id": d.task_id("explicit"), "vague_task_id": d.task_id("vague")}


def probe_task(row: dict, strict: bool = True, level: str = "explicit"):
    """The probe task a ``train-deeds`` manifest row names, posed at ``level``."""
    from roaddraft.eval.probe_tasks import ProbeTask, brief_text
    d = deed_task(int(row["seed"]))
    tid = d.task_id(level)
    want = row.get("vague_task_id") if level == "vague" else row["task_id"]
    if strict and tid != want:
        raise ValueError(f"{level} task id of deed seed {row['seed']} is {tid}, the manifest "
                         f"says {want}: the generator or prompt changed; python -m "
                         "roaddraft.eval taskset --write train-deeds")
    return ProbeTask(d.probe, tid, TASK_TYPE, brief_text(d.probe, level), level)


__all__ = ["SEEDS", "FILE", "LAYER", "RW_LAYER", "SCALE_FPI", "TASK_TYPE", "FAMILY", "DeedTask",
           "deed_task", "entry", "probe_task"]
