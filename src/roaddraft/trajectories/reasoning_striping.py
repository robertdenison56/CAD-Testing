"""The grounded drafter for the generated striping plans (``tasks.striping``, the
``p13`` family): read the profile's vertical curves, work out each direction's
no-passing zones by hand in the shown work, then draw the edge lines, the solid
lines over the zones and the broken lines as real 10-ft stripes.

How the zones are worked out (every step a sum the audit can follow, the
numbers the engine's own: A, L, K, PVC and PVT of each vertical curve from
``get_design_data kind=vcs``):

- a sag hides nothing; a crest restricts passing only where its sight distance
  is less than the MUTCD's minimum passing sight distance for the speed;
- with eye and object both 3.5 ft up, a sight line touching the curve is 3.5 ft
  above the road ``w = sqrt(2 * 100 * 3.5 * K)`` either side of where it
  touches, so the least sight distance on the crest is ``2 w`` when that is
  shorter than the curve and ``L / 2 + 4 * 100 * 3.5 / A`` when it is not;
- the up-station zone begins where the line from the eye, on the grade before
  the PVC, to the object a sight distance ahead just touches the curve: with
  the object on the curve, ``x`` past the PVC where
  ``x = (S - w) - sqrt((S - w)^2 - 2 * 100 * 3.5 * K)``, the eye
  ``S - x - w`` before the PVC; with the object on the grade beyond the PVT,
  at the angle ``t = A / 2 - sqrt(A * A / 4 - 100 * 3.5 * A / (S - L / 2))``
  percent off the first grade, the eye ``100 * 3.5 / t - K * t / 2`` before
  the PVC;
- the zone runs from that eye to as far past the PVT, less the sight distance;
  the same sight lines seen from their other end restrict the down-station
  traffic one sight distance further on.

That holds for a crest whose sight lines begin and end on the straight grades
either side of it, which the drafter checks against the other curves it read;
where another curve is in the way it stops (the recording is not kept).  The
generated set's crests stand alone; the six held-out pilots' mostly do not.

The broken lines are one 10-ft stripe drawn pointing east (``array_entities``
turns a copy by the path's bearing, so the pattern has to point along +x),
copied along the alignment every 40 ft over each stretch at its offset, and
the pattern deleted.

What the audit takes for this family beyond the general forms
(``reasoning.audit``, on a task that names the MUTCD's passing sight distance):
``MUTCD_NUMBERS``, the standard's own values, as the D1 audit takes spec v1's;
and a square root stated in the shown work, ``sqrt(X) = Y``, when Y is the
root of X to the fourth decimal (``roots``; X itself has to be grounded, as
every number in the shown work has).
"""
from __future__ import annotations

import math
import re
from typing import Generator, List, Optional, Sequence, Tuple

from roaddraft.trajectories.grounded import Turn, _q
from roaddraft.trajectories.reasoning import _n, _ok, _r4

#: MUTCD Table 3B-1: minimum passing sight distance, 85th-percentile speed (mph) -> ft
PSD = {25: 450, 30: 500, 35: 550, 40: 600, 45: 700, 50: 800, 55: 900, 60: 1000, 65: 1100,
       70: 1200}
#: MUTCD Section 3B.02: the eye and the object, ft above the road
HEIGHT = 3.5
#: MUTCD Section 3A.06: a broken line's stripe and gap, ft
STRIPE, GAP = 10.0, 30.0
#: each line of a double line off the centerline, ft (4-in lines 4 in apart)
PAIR = 0.33
#: what the audit takes as the standard's: the table's distances, the heights, the broken
#: line, the pair's offset; and the formulas' own constants (percent, halves, quarters)
MUTCD_NUMBERS = tuple(float(v) for v in PSD.values()) + (HEIGHT, STRIPE, GAP, PAIR,
                                                         100.0, 2.0, 4.0)

_ROOT = re.compile(r"sqrt\((\d+(?:\.\d+)?)\) = (\d+(?:\.\d+)?)")
_JOB = re.compile(r"Stripe (.+?) from (\d+\+\d+(?:\.\d+)?) to (\d+\+\d+(?:\.\d+)?)")
_PROFILE = re.compile(r"design profile (.+?) for an 85th-percentile speed of (\d+) mph")
_LANES = re.compile(r"(\d+(?:\.\d+)?)-ft lanes")
_STA = re.compile(r"(\d+)\+(\d+(?:\.\d+)?)")

Interval = Tuple[float, float]


def is_striping(text: str) -> bool:
    """Whether a task text is a striping plan's (its audit takes this module's forms)."""
    return "MUTCD" in text and "passing sight distance" in text


def roots(turns: Sequence[dict]) -> Tuple[float, ...]:
    """The square roots an episode's shown work states and gets right: ``sqrt(X) = Y``
    with Y the root of X to the fourth decimal."""
    found = []
    for turn in turns:
        for x, y in _ROOT.findall((turn.get("assistant") or {}).get("text") or ""):
            if abs(float(y) - math.sqrt(float(x))) <= 0.0001:
                found.append(float(y))
    return tuple(found)


def _feet(station: str) -> float:
    m = _STA.fullmatch(station)
    return int(m.group(1)) * 100 + float(m.group(2))


def read_job(text: str) -> dict:
    """The line, the range, the profile, the speed and the lane width the task states."""
    job, prof, lanes = _JOB.search(text), _PROFILE.search(text), _LANES.search(text)
    if not (job and prof and lanes):
        raise ValueError("the task names no line, range, profile, speed or lane width")
    return {"alignment": job.group(1), "ra": _feet(job.group(2)), "rb": _feet(job.group(3)),
            "profile": prof.group(1), "mph": int(prof.group(2)), "lane": float(lanes.group(1))}


class Work:
    """Shown work: sentences, and sums worked on the numbers as written (four decimals),
    so each stated result is the sum of what the line shows."""

    def __init__(self) -> None:
        self.lines: List[str] = []

    def say(self, text: str) -> None:
        self.lines.append(text)

    def sum(self, *tokens) -> Tuple[str, float]:
        """``a op b [op c ...]`` as written and its value; ``*`` and ``/`` bind first."""
        shown = [t if isinstance(t, str) else _n(t) for t in tokens]
        value = _r4(eval(" ".join(shown), {"__builtins__": {}}))  # digits and + - * / only
        return f"{' '.join(shown)} = {_n(value)}", value

    def calc(self, *tokens) -> float:
        text, value = self.sum(*tokens)
        self.lines.append(text + ".")
        return value

    def root(self, x: float) -> float:
        y = _r4(math.sqrt(float(_n(x))))
        self.lines.append(f"sqrt({_n(x)}) = {_n(y)}.")
        return y

    def text(self) -> str:
        return " ".join(self.lines)


def _crest(w: Work, vc: dict, s: float, c: float) -> Optional[Tuple[Interval, Interval]]:
    """One crest's zones before the range clips them: ``(up-station, down-station)``, or
    None when its sight distance is enough.  ``c`` is 100 x the eye height, worked out."""
    a, length, k = _r4(vc["A_pct"]), _r4(vc["length"]), _r4(vc["K"])
    pvc, pvt = _r4(vc["pvc_station"]), _r4(vc["pvt_station"])
    w.say(f"{vc['ref']} is a crest: A = {_n(a)} %, L = {_n(length)} ft, K = {_n(k)}, PVC "
          f"{_n(pvc)}, PVT {_n(pvt)}. A sight line touching the curve is {_n(HEIGHT)} ft above "
          f"the road w = sqrt(2 * {_n(c)} * K) either side of where it touches:")
    ck2 = w.calc(2, "*", c, "*", k)
    reach = w.root(ck2)
    across = w.calc(2, "*", reach)
    if across <= length:
        least = across
        w.say(f"That is within the curve's {_n(length)} ft, so two points on the curve "
              f"{_n(across)} ft apart only just see each other: the least sight distance "
              f"on this crest is {_n(least)} ft.")
    else:
        w.say(f"That is longer than the curve, so the shortest sight line spans it, the eye "
              f"and the object on the grades either side, L / 2 + 4 * {_n(c)} / A:")
        least = w.calc(length, "/", 2, "+", 4, "*", c, "/", a)
    if s <= least:
        w.say(f"That is not less than the {_n(s)} ft needed: {vc['ref']} restricts nothing.")
        return None
    w.say(f"That is less than the {_n(s)} ft needed, so {vc['ref']} makes a no-passing zone. "
          f"For up-station traffic it begins where the line from the eye, on the grade before "
          f"the PVC, to the object {_n(s)} ft ahead just touches the curve.")
    u = None
    if s >= across:
        w.say("Try the object on the curve: the line touches x past the PVC, "
              "x = (S - w) - sqrt((S - w) * (S - w) - w * w).")
        d = w.calc(s, "-", reach)
        sq = w.calc(d, "*", d)
        disc = w.calc(sq, "-", ck2)
        r = w.root(disc)
        x = w.calc(d, "-", r)
        xo = w.calc(x, "+", reach)
        if xo <= length:
            w.say(f"The object is {_n(xo)} ft past the PVC, on the curve as supposed, and the "
                  f"eye {_n(s)} ft behind it is before the PVC by")
            u = w.calc(s, "-", xo)
        else:
            w.say(f"That puts the object {_n(xo)} ft past the PVC, beyond the curve's "
                  f"{_n(length)} ft: it is on the grade past the PVT instead.")
    if u is None:
        w.say(f"With the object on the grade beyond the PVT the line leaves the first grade "
              f"at t percent, {_n(c)} / t + {_n(c)} / (A - t) = S - L / 2, so "
              f"t = A / 2 - sqrt(A * A / 4 - {_n(c)} * A / (S - L / 2)), and the eye is "
              f"{_n(c)} / t - K * t / 2 before the PVC.")
        half = w.calc(length, "/", 2)
        d = w.calc(s, "-", half)
        q = w.calc(c, "*", a, "/", d)
        p = w.calc(a, "*", a, "/", 4)
        if p < q:
            raise RuntimeError(f"{vc['ref']}: no sight line touches the curve from the grades")
        disc = w.calc(p, "-", q)
        r = w.root(disc)
        t = w.calc(a, "/", 2, "-", r)
        e1 = w.calc(c, "/", t)
        e2 = w.calc(k, "*", t, "/", 2)
        u = w.calc(e1, "-", e2)
    w.say(f"So the up-station zone begins {_n(u)} ft before the PVC and, the curve being the "
          f"same from either end, ends as far past the PVT less the {_n(s)} ft:")
    begin = w.calc(pvc, "-", u)
    far = w.calc(pvt, "+", u)
    end = w.calc(far, "-", s)
    shown, down = w.sum(begin, "+", s)
    w.say(f"The same sight lines seen from their other end restrict down-station traffic "
          f"{_n(s)} ft further on, from {shown} to {_n(far)}.")
    return (begin, end), (down, far)


def _minus(xs: Sequence[Interval], ys: Sequence[Interval]) -> List[Interval]:
    out = list(xs)
    for c, d in ys:
        out = [piece for a, b in out for piece in ((a, min(b, c)), (max(a, d), b))
               if piece[1] - piece[0] > 1e-6]
    return sorted(out)


def _both(xs: Sequence[Interval], ys: Sequence[Interval]) -> List[Interval]:
    return sorted((max(a, c), min(b, d)) for a, b in xs for c, d in ys
                  if min(b, d) - max(a, c) > 1e-6)


def _runs(xs: Sequence[Interval]) -> str:
    return ", ".join(f"{_n(a)} to {_n(b)}" for a, b in xs) or "nowhere"


def solve_striping(text: str) -> Generator[Turn, List[dict], Turn]:
    """Find each direction's no-passing zones from the profile and stripe the range."""
    job = read_job(text)
    align, profile, ra, rb, mph = (job["alignment"], job["profile"], job["ra"], job["rb"],
                                   job["mph"])
    lane = job["lane"]
    if mph not in PSD:
        raise ValueError(f"the MUTCD's table has no {mph} mph")
    s = float(PSD[mph])
    calls = [_q("get_design_data", kind="vcs", profile=profile),
             _q("get_design_data", kind="profiles", profile=profile),
             _q("get_design_data", kind="alignments"),
             _q("list_layers")]
    results = yield Turn(
        f"Striping {align} from {_n(ra)} to {_n(rb)}: white edge lines, and a yellow centerline "
        f"whose no-passing zones have to be found on the profile, each direction of travel its "
        f"own. The MUTCD's minimum passing sight distance at {mph} mph is {_n(s)} ft, from an "
        f"eye {_n(HEIGHT)} ft up to an object {_n(HEIGHT)} ft up. Read the vertical curves of "
        f"{profile} and how far it runs, the line, and the layers the file keeps for markings.",
        calls)
    _ok(results, calls)
    vcs, profiles, alignments, layers = results
    if (vcs.get("more") or {}).get("remaining"):
        raise ValueError("more vertical curves than one page")
    curves = sorted(vcs["rows"], key=lambda r: float(r["pvc_station"]))
    row = next(r for r in profiles["rows"] if r["name"] == profile)
    ends = [int(a) * 100 + float(b) for a, b in _STA.findall(row["station_range_text"])]
    line = next(r for r in alignments["rows"] if r["name"] == align)

    def marking(colour: str) -> str:
        name = next((r["name"] for r in layers["layers"]
                     if "marking" in str(r.get("description") or "").lower()
                     and colour in str(r.get("description") or "").lower()), None)
        if name is None:
            raise RuntimeError(f"the file has no layer for {colour} pavement markings")
        return name
    yellow, white = marking("yellow"), marking("white")

    w = Work()
    w.say(f"The sight lines look S = {_n(s)} ft past the range each way:")
    back = w.calc(ra, "-", s)
    on = w.calc(rb, "+", s)
    if back < ends[0] or on > ends[1]:
        raise RuntimeError("the profile does not reach a sight distance past the range")
    w.say(f"{profile} runs {_n(ends[0])} to {_n(ends[1])}, so it covers them. With eye and "
          f"object both {_n(HEIGHT)} ft up and grades in percent the height enters as")
    c = w.calc(100, "*", HEIGHT)
    up: List[Interval] = []
    down: List[Interval] = []
    for vc in curves:
        if vc["type"] != "crest":
            w.say(f"{vc['ref']} is a sag: the road falls away below every sight line across "
                  f"it, so it hides nothing.")
            continue
        zones = _crest(w, vc, s, c)
        if zones is None:
            continue
        (a, b), (d, e) = zones
        others = [o for o in curves if o is not vc
                  and float(o["pvt_station"]) > a and float(o["pvc_station"]) < e]
        if others:
            raise RuntimeError(f"{others[0]['ref']} lies on the sight lines of {vc['ref']}: "
                               "its zones cannot be worked out as a crest standing alone")
        w.say(f"Those sight lines run from {_n(a)} to {_n(e)}, on the straight grades either "
              f"side of {vc['ref']} with no other curve between, so the two zones stand.")
        up.append((a, b))
        down.append((d, e))
    rng = [(ra, rb)]
    up, down = _both(up, rng), _both(down, rng)
    double, either = _both(up, down), sorted(up + down)
    open_ = _minus(rng, either)
    up_only, down_only = _minus(up, down), _minus(down, up)
    w.say(f"On the range {_n(ra)} to {_n(rb)}: no passing for up-station traffic {_runs(up)}; "
          f"for down-station traffic {_runs(down)}.")
    w.say(f"The marking: white solid edge lines {_n(lane)} ft each side of the centerline over "
          f"the whole range, on {white}. Yellow on {yellow}: a solid line {_n(PAIR)} ft right "
          f"of the centerline over each up-station zone (its traffic keeps right of the "
          f"centerline looking up-station) and {_n(PAIR)} ft left over each down-station zone"
          + (f", double solid where they overlap ({_runs(double)})" if double else "")
          + f"; broken lines of {_n(STRIPE)}-ft stripes and {_n(GAP)}-ft gaps on the centerline "
          f"where both may pass ({_runs(open_)}), and beside a solid line where the other "
          f"direction may pass, {_n(PAIR)} ft off on the other side (left {_runs(up_only)}; "
          f"right {_runs(down_only)}).")
    calls = [_q("draw_offset", alignment=align, offsets=[-lane, lane], station_range=[ra, rb],
                layer=white)]
    for a, b in up:
        calls.append(_q("draw_offset", alignment=align, offsets=[PAIR], station_range=[a, b],
                        layer=yellow))
    for a, b in down:
        calls.append(_q("draw_offset", alignment=align, offsets=[-PAIR], station_range=[a, b],
                        layer=yellow))
    broken = ([(None, r) for r in open_] + [(-PAIR, r) for r in up_only]
              + [(PAIR, r) for r in down_only])
    broken = [(off, r) for off, r in broken if r[1] - r[0] >= STRIPE]
    if not broken:
        results = yield Turn(w.text(), calls)
        _ok(results, calls)
    else:
        x0, y0 = (float(v) for v in line["pis"][0]["point"])
        w.say(f"The broken lines are real stripes: draw one {_n(STRIPE)}-ft stripe as a pattern, "
              f"pointing east from the line's first point so that copies turn with the "
              f"alignment, copy it along each stretch, and delete it after. Its far end is at x =")
        x1 = w.calc(x0, "+", STRIPE)
        calls.append(_q("draw_line", space="model", layer=yellow, start=[_r4(x0), _r4(y0)],
                        end=[x1, _r4(y0)]))
        results = yield Turn(w.text(), calls)
        _ok(results, calls)
        pattern = results[-1]["created"][0]
        w = Work()
        text_every, every = w.sum(STRIPE, "+", GAP)
        text_half, half = w.sum(STRIPE, "/", 2)
        w.say(f"Copy the pattern ({pattern}) along {align} over each stretch, a stripe every "
              f"{text_every} ft. A copy's middle lands on the path, so the first stripe's "
              f"middle is half a stripe in, {text_half} ft, and no stripe's middle is nearer "
              f"the far end than that, so none runs past it.")
        calls = []
        for off, (a, b) in broken:
            where = ("on the centerline" if off is None else
                     f"{_n(PAIR)} ft {'right' if off > 0 else 'left'}")
            text_a, first = w.sum(a, "+", half)
            text_b, last = w.sum(b, "-", half)
            w.say(f"{_n(a)} to {_n(b)} {where}: from {text_a} to {text_b}.")
            params = {"ids": [pattern], "kind": "path", "path": align, "every": every,
                      "from": first, "to": last}
            if off is not None:
                params["offset"] = off
            calls.append(_q("array_entities", **params))
        w.say("Then delete the pattern, which is no stripe of the plan.")
        calls.append(_q("delete_entities", ids=[pattern]))
        results = yield Turn(w.text(), calls)
        _ok(results, calls)
    note = (f"Striped {align} from {_n(ra)} to {_n(rb)} in model space for {mph} mph (passing "
            f"sight distance {_n(s)} ft, eye and object {_n(HEIGHT)} ft): white edge lines "
            f"{_n(lane)} ft each side on {white}; yellow on {yellow}: no-passing zones from the "
            f"profile's crests, up-station traffic {_runs(up)} (solid {_n(PAIR)} ft right), "
            f"down-station traffic {_runs(down)} (solid {_n(PAIR)} ft left); broken "
            f"{_n(STRIPE)}-ft stripes with {_n(GAP)}-ft gaps on the centerline where both may "
            f"pass and beside each solid line where the other direction may. The broken lines "
            f"are array_entities copies of one pattern stripe along the alignment, the pattern "
            f"deleted.")
    return Turn("Done.", [_q("submit", note=note)])


__all__ = ["PSD", "MUTCD_NUMBERS", "is_striping", "roots", "read_job", "solve_striping", "Work"]
