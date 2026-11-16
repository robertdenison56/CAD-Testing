"""Generated striping plans with the no-passing zones found from the profile
(2026-11-15, training plan §8: the ``p13`` family as a training set).

The striping pilots (``p13-striping-*``, six instances on WFL and CFL sheets)
hand a model a two-lane road, a station range, a speed and a design profile, and
ask for the pavement markings in model space: white edge lines, and a yellow
centerline whose no-passing zones the model has to find itself from the MUTCD's
passing sight distance on the profile, each direction of travel its own.  None of
the pilots' sheets may train (plan decision 7), and the task needs none of them:
it is a line, a profile and a range.  ``striping_task(seed)`` makes one from the
seed alone:

- the start: a seeded design (``tasks.generator.generate_task``, two or three
  sheets long, its centerline drawn by the reference), the edges of pavement
  15 ft each side on ``rd_EP``, the office's two empty layers for pavement
  markings (``pm_STRIPE-YELLOW``, ``pm_STRIPE-WHITE``), and a design profile of
  this module's own in place of the generator's, which stops at the ends of the
  line: the sight lines look a passing sight distance past the range both ways,
  so the profile carries the existing road on behind the begin and beyond the
  end, as the pilots' do.  One file, no sheet;
- what the seed draws (stream ``striping:<seed>``): the range (600 to 1,200 ft
  on 50-ft stations), the speed (40 to 70 mph, so 600 to 1,200 ft of passing
  sight distance), and the profile -- one governing vertical curve and up to
  two sags clear of its sight lines, grades in tenths of a percent, PVIs on
  10-ft stations.  ``KINDS`` are what the range then shows: a zone for the
  up-station traffic only, for the down-station traffic only, one for each with
  a broken centerline between, the two overlapping (double solid), a crest too
  gentle to restrict anything, and a sag (which never does).  A zone may lie
  inside the range or run on past either end of it, from a crest that is off
  the range altogether;
- the prompts: the pilots' own wording (``probes.pilot.striping._prompt`` and
  ``_vague``), less the sheet's name: the work is in model space and this file
  has no sheet;
- the check: the pilots' own (``striping.make_check``; at the vague level its
  lenient form), on a ``striping.Job`` of this line, range, speed and profile.
  The truth is the pilots' sweep of the profile (``striping.zones``), not this
  module's closed form.

**What a seed must be to be kept.**  The pilots' check reads a merged piece of
15 ft or less as a stripe, so a zone or a passing stretch the range clips to a
sliver cannot be graded as what it is: every zone and every stretch between
zones is at least ``MIN_PIECE`` ft on the range.  And the governing crest stands
alone: the sight lines that bound its zones begin and end on the straight grades
either side of it (``reach``), so its zones are the ones a drafter can work out
by hand from the curve's A, L and K -- ``closed_form`` -- and the generator
holds the sweep to that within ``AGREE_FT``.  A draw that fails either is drawn
again (``ATTEMPTS``); a kind the seed cannot make gives way to the next
(``dialed`` in the manifest).

A probe task of the pilots' harness (``eval.probe_tasks``), registered outside
``probes/pilot`` (whose files the held-out set's hashes cover) with
``probes.fixture.register_start`` under ``train-striping-<seed>``.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.probes import fixture
from roaddraft.probes.base import Probe
from roaddraft.probes.pilot import striping as p13

#: the training set's seeds (the other sets hold 10000-20299)
SEEDS = range(24000, 24300)
#: the file the drafter is handed
FILE = "design.rdraft"
#: the task type the report strata see, and the pilot family the set carries
TASK_TYPE = "train-striping"
FAMILY = "p13"
ID_PREFIX = "TR-"
#: the office's layers for pavement markings, empty in the start, and the pavement's
YELLOW, WHITE = "pm_STRIPE-YELLOW", "pm_STRIPE-WHITE"
EP_LAYER, EP_OFFSET = "rd_EP", 15.0
#: what the range shows, in the order a seed's place in the set dials them
KINDS = ("up", "down", "both", "up", "down", "gentle", "both", "double", "sag", "up", "down",
         "both")
SPEEDS = (40, 45, 50, 55, 60, 65, 70)
RANGES = (600.0, 750.0, 750.0, 900.0, 1000.0, 1200.0)
#: the least a zone, or a stretch between zones, may measure on the range (see the docstring)
MIN_PIECE = 80.0
#: how far the pilots' sweep and the closed form may differ at a zone end (the sweep's grid
#: is 1 ft; the check allows 25)
AGREE_FT = 3.0
ATTEMPTS = 60
#: grade limits, percent
G_MAX = 7.0

Interval = Tuple[float, float]


def _ok(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


# ------------------------------------------------------------------ one crest by hand


def reach(a_pct: float, length: float, psd: float, h: float = p13.EYE) -> Optional[float]:
    """How far before the PVC of a crest standing alone (grades ``a_pct`` percent apart,
    ``length`` ft of curve) the no-passing zone of the traffic coming up to it begins, for
    eye and object both ``h`` ft up and a passing sight distance ``psd``; None when the
    crest hides nothing at that distance.

    The zone begins where the line from the eye, on the grade before the curve, to the
    object ``psd`` ahead just touches the curve.  With K = L / A and c = 100 h:

    - a line touching the curve is ``h`` above the road ``w = sqrt(2 c K)`` either side of
      where it touches, so two points on the curve see each other ``2 w`` apart, and with
      eye and object on the grades either side the least sight distance is
      ``L / 2 + 4 c / A``;
    - the object on the curve: the line touches ``x`` past the PVC with
      ``x / 2 + c K / x + w = psd``, the object ``x + w`` past the PVC;
    - the object on the grade beyond: the line leaves the first grade at ``t`` percent
      with ``c / t + c / (A - t) = psd - L / 2``, the eye ``c / t - K t / 2`` before the PVC.
    """
    c = 100.0 * h
    k = length / a_pct
    w = math.sqrt(2.0 * c * k)
    least = 2.0 * w if 2.0 * w <= length else length / 2.0 + 4.0 * c / a_pct
    if psd <= least:
        return None
    if psd >= 2.0 * w:
        x = (psd - w) - math.sqrt((psd - w) ** 2 - 2.0 * c * k)
        if x + w <= length:
            return psd - x - w
    d = psd - length / 2.0
    disc = a_pct * a_pct / 4.0 - c * a_pct / d
    if disc < 0.0:
        return None
    t = a_pct / 2.0 - math.sqrt(disc)
    return c / t - k * t / 2.0


def closed_form(pvc: float, pvt: float, a_pct: float, psd: float, ra: float, rb: float
                ) -> Tuple[List[Interval], List[Interval]]:
    """``(up-station zones, down-station zones)`` on [ra, rb] of one crest standing alone:
    up-station from ``reach`` before the PVC to as far past the PVT less the sight
    distance; down-station the same sight lines seen from their other end, ``psd`` on."""
    u = reach(a_pct, pvt - pvc, psd)
    if u is None:
        return [], []
    up = (pvc - u, pvt + u - psd)
    down = (up[0] + psd, pvt + u)
    return ([(max(a, ra), min(b, rb)) for a, b in (up,) if b > ra and a < rb],
            [(max(a, ra), min(b, rb)) for a, b in (down,) if b > ra and a < rb])


# ------------------------------------------------------------------ the profile


def _tenth(rng: random.Random, lo: float, hi: float) -> float:
    return rng.randrange(int(round(lo * 10)), int(round(hi * 10)) + 1) / 10.0


def _curve(rng: random.Random, kind: str, psd: float) -> Optional[Tuple[float, float, float]]:
    """``(g1, g2, L)`` of the governing curve for ``kind``, grades in percent; None when
    this draw does not suit the kind."""
    if kind == "sag":
        a = _tenth(rng, 1.5, 7.0)
        g1 = _tenth(rng, -G_MAX, G_MAX - a)
        if abs(g1) < 0.05 or abs(g1 + a) < 0.05:
            return None
        return g1, round(g1 + a, 1), float(rng.randrange(150, 801, 50))
    steep = kind == "double"
    a = _tenth(rng, 8.0, 13.0) if steep else _tenth(rng, 1.2, 9.0)
    length = float(rng.randrange(400 if steep else 100, 801, 50))
    g1 = _tenth(rng, a - G_MAX, G_MAX)
    if abs(g1) < 0.05 or abs(g1 - a) < 0.05:
        return None
    u = reach(a, length, psd)
    if kind == "gentle":
        c = 100.0 * p13.EYE
        w = math.sqrt(2.0 * c * length / a)
        least = 2.0 * w if 2.0 * w <= length else length / 2.0 + 4.0 * c / a
        return (g1, round(g1 - a, 1), length) if u is None and least - psd >= 40.0 else None
    if u is None:
        return None
    zone = length + 2.0 * u - psd            # the zone's length before the range clips it
    if zone < 150.0 or (steep and zone - psd < MIN_PIECE + 20.0):
        return None
    if kind == "both" and psd - zone < MIN_PIECE + 20.0:
        return None
    return g1, round(g1 - a, 1), length


def _place(rng: random.Random, kind: str, psd: float, length: float, a: float, ra: float,
           rb: float) -> Optional[float]:
    """The PVI station that shows ``kind`` on [ra, rb], on a 10-ft station."""
    if kind in ("sag", "gentle"):
        lo, hi = ra + 60.0, rb - 60.0
    else:
        u = reach(a, length, psd)
        zone = length + 2.0 * u - psd
        # s, where the up-station zone begins: it runs s to s + zone, the down-station
        # zone s + psd to s + psd + zone; ``some`` of a zone has to show on the range
        some = MIN_PIECE + 20.0
        if kind == "up":       # some of the up zone on the range, none of the down zone
            lo, hi = max(ra - zone + some, rb - psd + 40.0), rb - some
        elif kind == "down":   # some of the down zone, none of the up zone
            lo, hi = ra - psd - zone + some, min(rb - psd - some, ra - zone - 40.0)
        else:                  # some of each, and so the stretch between (or shared by) them
            lo, hi = ra - zone + some, rb - psd - some
        if hi < lo:
            return None
        return round((rng.uniform(lo, hi) + length / 2.0 + u) / 10.0) * 10.0
    if hi < lo:
        return None
    return round(rng.uniform(lo, hi) / 10.0) * 10.0


def _profile(rng: random.Random, kind: str, psd: float, ra: float, rb: float
             ) -> Optional[Tuple[tuple, dict]]:
    """A profile showing ``kind`` on [ra, rb]: ``(pvis, facts)``, or None for a draw that
    does not."""
    drawn = _curve(rng, kind, psd)
    if drawn is None:
        return None
    g1, g2, length = drawn
    a = abs(g1 - g2)
    p = _place(rng, kind, psd, length, a, ra, rb)
    if p is None:
        return None
    pvc, pvt = p - length / 2.0, p + length / 2.0
    u = reach(a, length, psd) if g2 < g1 else None
    # the stretch the governing curve's sight lines use: nothing else may curve inside it
    clear = (pvc - (u or 0.0) - 60.0, pvt + (u or 0.0) + 60.0)
    p0 = math.floor((min(ra - psd, clear[0]) - 450.0) / 50.0) * 50.0
    p1 = math.ceil((max(rb + psd, clear[1]) + 450.0) / 50.0) * 50.0
    stations: List[Tuple[float, float]] = [(p, length)]
    grades = [g1, g2]
    # a sag before and a sag after, clear of the sight lines, where the grades allow one
    for side in (-1, 1):
        if rng.random() >= 0.6:
            continue
        ls = float(rng.randrange(100, 401, 50))
        change = _tenth(rng, 0.5, 4.0)
        if side < 0:
            g0 = round(grades[0] - change, 1)
            room = (p0 + ls / 2.0 + 60.0, clear[0] - ls / 2.0)
            if abs(g0) > G_MAX or abs(g0) < 0.05 or room[1] < room[0]:
                continue
            stations.insert(0, (round(rng.uniform(*room) / 10.0) * 10.0, ls))
            grades.insert(0, g0)
        else:
            g3 = round(grades[-1] + change, 1)
            room = (clear[1] + ls / 2.0, p1 - ls / 2.0 - 60.0)
            if abs(g3) > G_MAX or abs(g3) < 0.05 or room[1] < room[0]:
                continue
            stations.append((round(rng.uniform(*room) / 10.0) * 10.0, ls))
            grades.append(g3)
    elevation = round(rng.uniform(150.0, 2400.0), 2)
    pvis: List[tuple] = [(p0, elevation)]
    here = p0
    for (station, ls), grade in zip(stations, grades):
        elevation = round(elevation + grade * (station - here) / 100.0, 2)
        pvis.append((station, elevation, ls))
        here = station
    pvis.append((p1, round(elevation + grades[-1] * (p1 - here) / 100.0, 2)))
    facts = {"pvi": p, "g1": g1, "g2": g2, "length": length, "curves": len(stations),
             "crest": g2 < g1, "pvc": pvc, "pvt": pvt}
    return tuple(pvis), facts


def _pieces(up: Sequence[Interval], down: Sequence[Interval], ra: float, rb: float
            ) -> List[float]:
    """The lengths of every stretch the marking changes over: each zone, each stretch
    where one direction alone is restricted, both are, or neither is."""
    cuts = sorted({ra, rb} | {v for z in list(up) + list(down) for v in z})
    return [b - a for a, b in zip(cuts, cuts[1:]) if b - a > 1e-6]


def _shows(kind: str, up: Sequence[Interval], down: Sequence[Interval]) -> bool:
    overlap = any(min(b, d) - max(a, c) > 0.5 for a, b in up for c, d in down)
    want = {"up": (1, 0), "down": (0, 1), "both": (1, 1), "double": (1, 1),
            "gentle": (0, 0), "sag": (0, 0)}[kind]
    return (len(up), len(down)) == want and overlap == (kind == "double")


# ------------------------------------------------------------------ the task


@dataclass(frozen=True)
class StripingTask:
    """One generated striping plan: its probe, the pilots' job it is graded as, and
    what the generator chose."""
    seed: int
    probe: Probe
    job: p13.Job
    base_task_id: str
    kind: str
    wanted: str
    up: Tuple[Interval, ...]
    down: Tuple[Interval, ...]
    facts: tuple

    def task_id(self, level: str) -> str:
        """``TR-<probe id>-<hash>`` over the task text at ``level``, the design it is on
        and the profile, so a changed generator or prompt is a new task."""
        from roaddraft.eval.probe_tasks import brief_text
        h = hashlib.sha256((brief_text(self.probe, level) + "\0" + self.base_task_id + "\0"
                            + repr(self.job.pvis)).encode("utf-8")).hexdigest()[:10]
        return f"{ID_PREFIX}{self.probe.id}-{h}"


def _base(seed: int, rng: random.Random):
    """The seeded design under the striping: ``(task, session)`` with the centerline drawn.
    Three sheets long where the seed lays out on three, else two."""
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.reference import phase_commands, session_for_task
    curves = rng.choice((1, 2, 3))
    task = None
    for sheets in (3, 2):
        try:
            task = generate_task(seed, curves=curves, equations=False,
                                 task_type="draw-alignment", sheets=sheets)
            break
        except ValueError:
            continue
    if task is None:
        raise ValueError(f"seed {seed}: no line of two or three sheets")
    session = session_for_task(task)
    for name, params in phase_commands(task, ["linework"]):
        _ok(session.execute(name, params))
    return task, session


def _start(session, alignment: str, profile: str, pvis: Sequence[tuple]) -> None:
    """The pavement, the marking layers and the design profile; the generator's own
    profile (it stops at the ends of the line) and what names the seeded task go."""
    doc = session.doc
    for name in list(doc.design.profiles):
        _ok(session.execute("delete_profile", {"name": name}))
    _ok(session.execute("create_profile", {
        "name": profile, "alignment": alignment, "pvis": [list(p) for p in pvis],
        "description": "finished grade, with the existing road each end"}))
    _ok(session.execute("draw_offset", {"alignment": alignment,
                                        "offsets": [-EP_OFFSET, EP_OFFSET], "layer": EP_LAYER}))
    _ok(session.execute("create_layer", {"name": YELLOW, "color": "yellow",
                                         "lineweight_mm": 0.35,
                                         "description": "pavement marking, yellow"}))
    _ok(session.execute("create_layer", {"name": WHITE, "color": "black", "lineweight_mm": 0.35,
                                         "description": "pavement marking, white"}))
    for key in ("task_id", "spec_version", "design_speed_mph"):
        (doc.meta or {}).pop(key, None)


def _briefs(job: p13.Job) -> Tuple[str, str]:
    """The pilots' two briefs for ``job``, less the sheet: this file has none."""
    out = []
    for text in (p13._prompt(job), p13._vague(job)):
        named = f" (sheet {job.sheet})"
        assert text.count(named) == 1, text
        out.append(text.replace(named, ""))
    return out[0], out[1]


@lru_cache(maxsize=None)
def striping_task(seed: int) -> StripingTask:
    """The generated striping plan of ``seed``; ``ValueError`` when the seed gives none."""
    rng = random.Random(f"striping:{seed}")
    task, session = _base(seed, rng)
    alignment = task.brief.alignment_name
    row = _ok(session.query("get_design_data", {"kind": "alignments"}))["rows"][0]
    begin, end = float(row["begin_station"]), float(row["end_station"])
    wanted = KINDS[(seed - SEEDS[0]) % len(KINDS)]
    order = [wanted] + [k for k in ("up", "down", "both", "gentle", "sag") if k != wanted]
    found = None
    for kind in order:
        for _ in range(ATTEMPTS):
            mph = rng.choice(SPEEDS[:4] if kind == "double" else SPEEDS)
            psd = float(p13.MUTCD_PSD[mph])
            first = math.ceil((begin + 20.0) / 50.0) * 50.0
            span = min(rng.choice(RANGES), math.floor((end - 20.0 - first) / 50.0) * 50.0)
            if span < RANGES[0]:
                raise ValueError(f"seed {seed}: the line is too short for a striping range")
            ra = first + 50.0 * rng.randrange(int((end - 20.0 - first - span) // 50.0) + 1)
            rb = ra + span
            made = _profile(rng, kind, psd, ra, rb)
            if made is None:
                continue
            pvis, facts = made
            try:
                up, down = p13.zones(pvis, psd, ra, rb)
            except (ValueError, p13.DesignError):  # a profile that does not validate or reach
                continue
            if not _shows(kind, up, down) or min(_pieces(up, down, ra, rb)) < MIN_PIECE:
                continue
            by_hand = (closed_form(facts["pvc"], facts["pvt"], abs(facts["g1"] - facts["g2"]),
                                   psd, ra, rb) if facts["crest"] else ([], []))
            if [len(z) for z in by_hand] != [len(up), len(down)] or any(
                    abs(x - y) > AGREE_FT for zs, ws in zip(by_hand, (up, down))
                    for z, w in zip(zs, ws) for x, y in zip(z, w)):
                continue
            found = (kind, mph, ra, rb, pvis, facts, tuple(up), tuple(down))
            break
        if found:
            break
    if not found:
        raise ValueError(f"seed {seed}: no profile shows a kind of this set on its line")
    kind, mph, ra, rb, pvis, facts, up, down = found
    probe_id = f"t13-striping-{seed}"
    profile = rng.choice((f"{alignment} PGL", f"{alignment} PGL", f"{alignment} FG", "PGL-1"))
    _start(session, alignment, profile, pvis)
    start = _register(seed, session)
    job = p13.Job(id=probe_id, start=start, redraft="", sheet_file=FILE, sheet=alignment,
                  ra=ra, rb=rb, mph=mph, ali_file=FILE, refs=(), alignment=alignment,
                  profile=profile, pvis=pvis, extent=p13._BEYOND)
    assert p13.truth(job) == (up, down)
    explicit, vague = _briefs(job)
    said = "; ".join(f"{who} {p13._sta(a)} to {p13._sta(b)}"
                     for who, zs in (("up-station", up), ("down-station", down))
                     for a, b in zs) or "none"
    probe = Probe(id=probe_id, prompt=explicit, vague=vague, check=p13.make_check(job),
                  vague_check=p13.make_check(job, lenient=True),
                  solve=lambda s, job=job: p13.solve_job(job, s), start=start,
                  tags=["striping", "sight-distance", "train"], family=FAMILY,
                  params={"seed": seed, "kind": kind, "mph": mph, "range": [ra, rb]},
                  note=(f"Generated striping on seed {seed}'s line, {p13._sta(ra)} to "
                        f"{p13._sta(rb)} at {mph} mph (PSD {job.psd:.0f} ft), kind {kind}: "
                        f"{'crest' if facts['crest'] else 'sag'} at PVI {p13._sta(facts['pvi'])} "
                        f"({facts['g1']:+.2f}% to {facts['g2']:+.2f}%, {facts['length']:.0f}' VC); "
                        f"no-passing zones {said}."))
    return StripingTask(seed, probe, job, task.task_id, kind, wanted, up, down,
                        tuple(sorted(facts.items())))


_STARTS: Dict[int, dict] = {}


def _register(seed: int, session) -> str:
    """Register the start ``train-striping-<seed>``: the document as built, written to
    the project folder each time an episode starts."""
    from roaddraft.document.fileformat import write_document
    name = f"train-striping-{seed}"
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
    """A manifest entry of ``train-striping``."""
    t = striping_task(seed)
    facts = dict(t.facts)
    row = {"seed": seed, "family": FAMILY, "task_type": TASK_TYPE, "kind": t.kind,
           "mph": t.job.mph, "range": [t.job.ra, t.job.rb],
           "curve": {"type": "crest" if facts["crest"] else "sag", "pvi": facts["pvi"],
                     "g1_pct": facts["g1"], "g2_pct": facts["g2"], "length": facts["length"]},
           "vertical_curves": facts["curves"],
           "profile": t.job.profile, "pvis": [list(p) for p in t.job.pvis],
           "zones_up": [list(z) for z in t.up], "zones_down": [list(z) for z in t.down],
           "base_task_id": t.base_task_id,
           "task_id": t.task_id("explicit"), "vague_task_id": t.task_id("vague")}
    if t.kind != t.wanted:  # the seed's line or draws could not show the kind its place dials
        row["dialed"] = {"kind": t.wanted}
    return row


def probe_task(row: dict, strict: bool = True, level: str = "explicit"):
    """The probe task a ``train-striping`` manifest row names, posed at ``level``."""
    from roaddraft.eval.probe_tasks import ProbeTask, brief_text
    t = striping_task(int(row["seed"]))
    tid = t.task_id(level)
    want = row.get("vague_task_id") if level == "vague" else row["task_id"]
    if strict and tid != want:
        raise ValueError(f"{level} task id of striping seed {row['seed']} is {tid}, the manifest "
                         f"says {want}: the generator or prompt changed; python -m "
                         "roaddraft.eval taskset --write train-striping")
    return ProbeTask(t.probe, tid, TASK_TYPE, brief_text(t.probe, level), level)


__all__ = ["SEEDS", "FILE", "TASK_TYPE", "FAMILY", "KINDS", "YELLOW", "WHITE", "StripingTask",
           "striping_task", "reach", "closed_form", "entry", "probe_task"]
