"""The grounded drafter for the generated plan-and-profile sheets (``tasks.planprofile``,
the ``p06`` family): read the sheet, the line and the design profile, work the grade
out on the sheet's stations, set the profile grid, put the plan view over it so that a
station sits at the same paper x in both, check that it does, then draw the grid, the
grade line and the vertical curves' lettering.

Everything below the plan is arithmetic, and the engine has no query for an elevation
at a station, so the shown work carries it, one sum a value:

- the grade at a station on a tangent, from the point before it:
  ``el + g * d / 100``; on a vertical curve, from its PVC:
  ``el + g1 * x / 100 +/- A * x * x / 200 / L`` (a sag adds, a crest takes away);
- the paper: ``x = station / h - (s0 / h - x0)``, ``y = elevation / v - (e0 / v - y0)``,
  the two bracketed constants worked out once;
- the plan view: as wide as the grid and 0.2 in more each side, centred on the grid's
  middle, which is the station half way along the sheet; ``station_to_xy`` gives that
  station's point and direction, and the view is turned by minus the direction.  The
  same turn's ``station_to_xy`` calls with the sheet named read back where the first
  and last full stations landed on the paper, and the next turn compares them with
  the grid's.

At the explicit level the task states the scales and the grid's datum.  At the vague
level the drafter takes ``tasks.planprofile.rule_layout``'s layout and shows it: the
scale the file plots at, a tenth of it vertically (1" = 10' where that is taller than
half the usable height), the grid's corner 0.5 in inside the usable area's, the 5 ft
lines at or outside the lowest and highest grade.

The audit's forms this family adds (``RULES`` and ``rounded``; ``reasoning.audit``
applies them to a plan-and-profile brief only):

- ``A rounds down (up) to B, a whole N``: B is grounded when it is A taken down (up)
  to a multiple of N, N being 5 (the grid's elevation lines), 25 (a point of the grade
  line along a vertical curve) or 100 (a full station);
  A is a number of the shown work and is audited as one;
- a string of digits (a grid elevation, ``315``) is grounded when its number is;
- ``PVI <station>\\nEL <elevation>``, ``<length>' VC\\nK = <K>`` and
  ``HIGH PT (LOW PT) <station>\\nEL <elevation>`` are grounded when each value in them
  was read or worked out;
- the layer names a drafter makes where the file keeps none for a profile
  (``OWN_LAYERS``).
"""
from __future__ import annotations

import math
import re
from typing import Generator, List, Optional, Sequence, Tuple

from roaddraft.trajectories.grounded import Seen, Turn, _q
from roaddraft.trajectories.reasoning import _n, _ok, _r4

#: the drafter's own layout, the generator's rule (``tasks.planprofile.rule_layout``)
MARGIN_IN = 0.5
GAP_IN = 0.25
SIDE_IN = 0.2
ELEV_STEP = 5.0
V_COARSE = 10.0
#: a vertex of the grade line this often along a vertical curve
CURVE_STEP = 25.0
#: the layers the drafter makes where the file keeps none for a profile:
#: ``(name, what it says the layer is for)`` for the grid, the grade line, the lettering
OWN_LAYERS = ("PROF-GRID", "PROF-GRADE", "PROF-TEXT")
#: how far the plan may sit off the grid before the drafter stops (paper inches)
LINED_UP_IN = 0.04

_ST = r"\d+\+\d{2}(?:\.\d+)?"
_HEAD = re.compile(rf"Lay out sheet (\S+) as a plan and profile sheet for (.+?),? "
                   rf"(?:stations|from) ({_ST}) to ({_ST}),? (?:using|with) the design profile "
                   rf"(.+?)\.(?:\s|$)")
_SCALES = re.compile(r"Profile view below it at 1\"=(\d+(?:\.\d+)?)' horizontal and "
                     r"1\"=(\d+(?:\.\d+)?)' vertical")
_DATUM = re.compile(rf"lower-left corner at paper \((\d+(?:\.\d+)?), (\d+(?:\.\d+)?)\) in, which "
                    rf"is station {_ST}, elevation (\d+(?:\.\d+)?); the grid runs to station "
                    rf"{_ST} and elevation (\d+(?:\.\d+)?)")
_TEXT = re.compile(r"Text (\d+(?:\.\d+)?) in\.")


def is_brief(text: str) -> bool:
    """Whether ``text`` is a plan-and-profile task (the pilots' wording)."""
    return bool(_HEAD.search(text))


def _feet(station: str) -> float:
    a, b = station.split("+")
    return int(a) * 100.0 + float(b)


def read_brief(text: str) -> dict:
    """What the task states: the sheet, the line, its stations, the profile; at the
    explicit level the scales, the grid's datum and the text height too."""
    m = _HEAD.search(text)
    if not m:
        raise ValueError("the task names no sheet to lay out as plan and profile")
    out = {"sheet": m.group(1), "alignment": m.group(2), "s0": _feet(m.group(3)),
           "s1": _feet(m.group(4)), "profile": m.group(5)}
    scales, datum, height = _SCALES.search(text), _DATUM.search(text), _TEXT.search(text)
    if scales and datum:
        out.update(h=float(scales.group(1)), v=float(scales.group(2)),
                   x0=float(datum.group(1)), y0=float(datum.group(2)),
                   e0=float(datum.group(3)), e1=float(datum.group(4)))
        if height:
            out["text"] = float(height.group(1))
    return out


# ------------------------------------------------------------ the audit's forms

_ROUNDED = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?) rounds (down|up) to (\d+), a whole (5|25|100)\b")
_DIGITS = re.compile(r"^\d+$")
_PVI_LABEL = re.compile(rf"^PVI ({_ST})\nEL (\d+\.\d\d)$")
_VC_LABEL = re.compile(r"^(\d+)' VC\nK = (\d+\.\d\d)$")
_POINT_LABEL = re.compile(rf"^(?:HIGH|LOW) PT ({_ST})\nEL (\d+\.\d\d)$")


def rounded(turns: Sequence[dict]) -> Tuple[float, ...]:
    """The numbers the shown work rounds to a whole 5, 25 or 100, where the rounding is
    right: ``312.47 rounds down to 310, a whole 5``."""
    out = []
    for turn in turns:
        said = (turn.get("assistant") or {}).get("text") or ""
        for a, way, b, step in _ROUNDED.findall(said):
            a, b, step = float(a), float(b), float(step)
            want = (math.floor(a / step + 1e-9) if way == "down"
                    else math.ceil(a / step - 1e-9)) * step
            if abs(want - b) < 1e-9:
                out.append(b)
    return tuple(out)


def _read(seen: Seen, value: str) -> bool:
    return seen.number(float(value), standards=False)


def digits(value: str, seen: Seen) -> bool:
    """A number lettered as its digits (a grid elevation), read or worked out."""
    return bool(_DIGITS.match(value)) and _read(seen, value)


def curve_label(value: str, seen: Seen) -> bool:
    """A vertical curve's lettering: every value in it read or worked out."""
    for form in (_PVI_LABEL, _POINT_LABEL):
        m = form.match(value)
        if m:
            return _read(seen, str(_feet(m.group(1)))) and _read(seen, m.group(2))
    m = _VC_LABEL.match(value)
    return bool(m) and _read(seen, m.group(1)) and _read(seen, m.group(2))


def own_layer(value: str, seen: Seen) -> bool:
    return value in OWN_LAYERS


RULES = (digits, curve_label, own_layer)


# ------------------------------------------------------------ the shown work


def _sum(*terms) -> Tuple[str, float]:
    """A sum as the shown work writes it and its value at four decimals: numbers and
    the operators between them, ``*`` and ``/`` before ``+`` and ``-``.  Every number
    is written without a sign (the audit's grammar), so a negative one is an error."""
    numbers = [_r4(t) for t in terms[0::2]]
    ops = list(terms[1::2])
    if any(n < 0 for n in numbers):
        raise ValueError(f"a negative term in a sum: {terms}")
    parts, signs = [numbers[0]], []
    for op, n in zip(ops, numbers[1:]):
        if op == "*":
            parts[-1] *= n
        elif op == "/":
            parts[-1] /= n
        else:
            signs.append(op)
            parts.append(n)
    total = parts[0]
    for op, part in zip(signs, parts[1:]):
        total = total + part if op == "+" else total - part
    value = _r4(total)
    text = _n(numbers[0]) + "".join(f" {op} {_n(n)}" for op, n in zip(ops, numbers[1:]))
    return f"{text} = {_n(value)}", value


def _signed(value: float) -> Tuple[str, float]:
    """``('+', |value|)`` or ``('-', |value|)``: a signed term for ``_sum``."""
    return ("+" if value >= 0 else "-"), abs(float(value))


def _pct(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}{_n(abs(value))} %"


class _Grade:
    """The design profile as its rows give it, and the grade at a station with the
    sum that works it out."""

    def __init__(self, pvis: Sequence[dict], vcs: Sequence[dict]):
        self.pvis, self.vcs = list(pvis), list(vcs)
        if len(self.pvis) < 2 or len(self.vcs) != len(self.pvis) - 2:
            raise ValueError("the profile's PVIs and vertical curves do not match")
        first, last = self.pvis[0], self.pvis[-1]
        self.begin, self.end = float(first["station"]), float(last["station"])
        #: the points the grade runs straight between, or curves between:
        #: ``(station, elevation, name)``
        self.knots: List[Tuple[float, float, str]] = [
            (self.begin, float(first["elevation"]), first["ref"])]
        #: ``("line", a, b, grade %)`` and ``("curve", row)``, in order
        self.pieces: List[tuple] = []
        grade = float(first["grade_out_pct"])
        for row in self.vcs:
            pvi = f"PVI-{int(row['index']) + 1}"
            if float(row["length"]) > 0:
                pvc = (float(row["pvc_station"]), float(row["pvc_elevation"]), f"the PVC of {row['ref']}")
                pvt = (float(row["pvt_station"]), float(row["pvt_elevation"]), f"the PVT of {row['ref']}")
                self._line(pvc, float(row["g1_pct"]))
                self.pieces.append(("curve", row))
                self.knots.append(pvt)
            else:
                self._line((float(row["pvi_station"]), float(row["pvi_elevation"]), pvi),
                           float(row["g1_pct"]))
            grade = float(row["g2_pct"])
        self._line((self.end, float(last["elevation"]), last["ref"]), grade)

    def _line(self, b: tuple, grade: float) -> None:
        a = self.knots[-1]
        if b[0] - a[0] > 1e-6:
            self.pieces.append(("line", a, b, grade))
            self.knots.append(b)

    def knot(self, station: float) -> Optional[Tuple[float, float, str]]:
        return next((k for k in self.knots if abs(k[0] - station) < 1e-6), None)

    def at(self, station: float) -> Tuple[float, str]:
        """The grade at ``station`` and the words that work it out."""
        known = self.knot(station)
        if known is not None:
            return _r4(known[1]), f"{_n(station)} is {known[2]}, el {_n(known[1])}."
        for piece in self.pieces:
            if piece[0] == "line":
                _kind, a, b, grade = piece
                if a[0] < station < b[0]:
                    d_text, d = _sum(station, "-", a[0])
                    op, g = _signed(grade)
                    text, value = _sum(a[1], op, g, "*", d, "/", 100.0)
                    return value, (f"{_n(station)} is {d_text} ft past {a[2]} on the "
                                   f"{_pct(grade)} grade: {text}.")
            else:
                row = piece[1]
                pvc, pvt = float(row["pvc_station"]), float(row["pvt_station"])
                if pvc < station < pvt:
                    x_text, x = _sum(station, "-", pvc)
                    op1, g1 = _signed(float(row["g1_pct"]))
                    op2 = "+" if row["type"] == "sag" else "-"
                    text, value = _sum(float(row["pvc_elevation"]), op1, g1, "*", x, "/", 100.0,
                                       op2, float(row["A_pct"]), "*", x, "*", x, "/", 200.0, "/",
                                       float(row["length"]))
                    return value, f"{_n(station)} on {row['ref']}, x = {x_text}: {text}."
        raise ValueError(f"station {station} is not on the profile")

    def curves(self) -> List[dict]:
        return [row for row in self.vcs if float(row["length"]) > 0]


def _grade_stations(grade: _Grade, g0: float, g1: float) -> List[float]:
    """Where the grade line takes a vertex between ``g0`` and ``g1``: both ends, every
    point the grade changes at, and every ``CURVE_STEP`` ft along a vertical curve."""
    cuts = {g0, g1} | {k[0] for k in grade.knots if g0 < k[0] < g1}
    for row in grade.curves():
        lo, hi = max(float(row["pvc_station"]), g0), min(float(row["pvt_station"]), g1)
        s = math.floor(lo / CURVE_STEP + 1e-9) * CURVE_STEP + CURVE_STEP
        while s < hi - 1e-6:
            cuts.add(s)
            s += CURVE_STEP
    out: List[float] = []
    for s in sorted(cuts):
        if not out or s - out[-1] > 1e-6:
            out.append(s)
    return out


def _curve_points(row: dict, g0: float, g1: float) -> str:
    """The words that count the grade line's points along a curve: the whole 25s
    between its ends on the sheet."""
    lo, hi = max(float(row["pvc_station"]), g0), min(float(row["pvt_station"]), g1)
    first = math.floor(lo / CURVE_STEP + 1e-9) * CURVE_STEP + CURVE_STEP
    if first >= hi - 1e-6:
        return f"No whole {_n(CURVE_STEP)} falls on it between {_n(lo)} and {_n(hi)}."
    if abs(lo / CURVE_STEP - round(lo / CURVE_STEP)) < 1e-9:
        steps = [_sum(lo, "+", CURVE_STEP)[0]]
    else:
        steps = [f"{_n(lo)} rounds up to {_n(first)}, a whole 25"]
    s = first
    while s + CURVE_STEP < hi - 1e-6:
        text, s = _sum(s, "+", CURVE_STEP)
        steps.append(text)
    return f"Its points on the sheet, between {_n(lo)} and {_n(hi)}: " + "; ".join(steps) + "."


def _full(station: float) -> bool:
    return abs(station / 100.0 - round(station / 100.0)) < 1e-9


def _sta(station: float) -> str:
    """``93+00`` for a full station."""
    whole = int(round(station))
    return f"{whole // 100}+{whole % 100:02d}"


# ------------------------------------------------------------ the drafter


def solve_profile(text: str) -> Generator[Turn, List[dict], Turn]:
    brief = read_brief(text)
    sheet, alignment, profile = brief["sheet"], brief["alignment"], brief["profile"]
    s0, s1 = brief["s0"], brief["s1"]
    stated = "h" in brief

    # -- 1: what the file holds
    calls = [_q("get_sheet_state", sheet=sheet), _q("list_layers"), _q("list_annotation_scales"),
             _q("list_alignments"),
             _q("get_design_data", alignment=alignment, kind="tangents"),
             _q("get_design_data", kind="pvis", profile=profile),
             _q("get_design_data", kind="vcs", profile=profile)]
    results = yield Turn(
        f"Sheet {sheet} is to carry the plan of {alignment} over its profile {profile}, with "
        "every station at the same paper x in both. Read how the sheet is set up, the layers and "
        "the scale the file plots at, the line and its tangents, and the profile's PVIs and "
        "vertical curves.", calls)
    _ok(results, calls)
    state, layers, scales, aligns, tangents, pvis, vcs = results
    for r in (pvis, vcs, tangents):
        if int(r["total"]) > len(r["rows"]):
            raise ValueError("the design has more rows than one page")
    usable = [float(v) for v in state["sheet"]["usable_area"]]
    if state["sheet"]["viewports"]:
        raise ValueError("the sheet already has a view")
    line = next((a for a in aligns["alignments"] if a["name"] == alignment), None)
    if line is None:
        raise ValueError(f"the file has no alignment {alignment}")
    a0, a1 = float(line["begin_station"]), float(line["end_station"])
    grade = _Grade(pvis["rows"], vcs["rows"])
    height = float(brief.get("text") or scales["paper"]["text_height_in"])

    # -- 2: the grade on the sheet, the grid, the plan view over it
    said: List[str] = []
    g0, g1 = max(s0, grade.begin), min(s1, grade.end)
    said.append(f"The sheet runs from station {_n(s0)} to {_n(s1)}; {profile} runs from "
                f"{_n(grade.begin)} to {_n(grade.end)}, so the grade line on this sheet runs from "
                f"{_n(g0)} to {_n(g1)}. It is straight between vertical curves and takes a point "
                f"every {_n(CURVE_STEP)} ft along one.")
    for row in grade.curves():
        if float(row["pvc_station"]) < g1 and float(row["pvt_station"]) > g0:
            said.append(
                f"{row['ref']} is a {_n(row['length'])} ft {row['type']}, PVC {_n(row['pvc_station'])} "
                f"el {_n(row['pvc_elevation'])} to PVT {_n(row['pvt_station'])}, {_pct(row['g1_pct'])} "
                f"in and {_pct(row['g2_pct'])} out, A = {_n(row['A_pct'])}: x ft past the PVC the "
                f"grade is the PVC's el {'+' if row['g1_pct'] >= 0 else '-'} g1 * x / 100 "
                f"{'+' if row['type'] == 'sag' else '-'} A * x * x / 200 / L.")
            said.append(_curve_points(row, g0, g1))
    stations = _grade_stations(grade, g0, g1)
    elevations = []
    for s in stations:
        value, how = grade.at(s)
        elevations.append(value)
        said.append(how)
    points = [row["high_low"] for row in grade.curves()
              if row["high_low"] and s0 <= float(row["high_low"]["station"]) <= s1]
    for row in grade.curves():
        hl = row["high_low"]
        if hl and s0 <= float(hl["station"]) <= s1:
            said.append(f"{row['ref']} has its {hl['kind']} point on the sheet, at "
                        f"{_n(hl['station'])} el {_n(hl['elevation'])}.")

    if stated:
        h, v = brief["h"], brief["v"]
        x0, y0, e0, e1 = brief["x0"], brief["y0"], brief["e0"], brief["e1"]
        said.append(f"The task sets the grid: 1\"={_n(h)}' along and 1\"={_n(v)}' up, its lower "
                    f"left corner at paper [{_n(x0)}, {_n(y0)}], which is station {_n(s0)} el "
                    f"{_n(e0)}, running to el {_n(e1)}.")
        span_text, span = _sum(e1, "-", e0)
    else:
        h = float(scales["current"] or 0.0)
        if not h:
            raise ValueError("the file has no plot scale set")
        low = min(elevations + [_r4(p["elevation"]) for p in points])
        high = max(elevations + [_r4(p["elevation"]) for p in points])
        e0 = math.floor(low / ELEV_STEP + 1e-9) * ELEV_STEP
        e1 = math.ceil(high / ELEV_STEP - 1e-9) * ELEV_STEP
        if e1 - e0 < 2 * ELEV_STEP:
            raise ValueError("the grade is too flat for a grid of 5 ft lines")
        v_text, v = _sum(h, "/", 10.0)
        x_text, x0 = _sum(usable[0], "+", MARGIN_IN)
        y_text, y0 = _sum(usable[1], "+", MARGIN_IN)
        span_text, span = _sum(e1, "-", e0)
        tall_text, tall = _sum(span, "/", v)
        room_text, room = _sum(usable[3], "-", usable[1])
        half_text, half = _sum(room, "/", 2.0)
        said.append(
            f"Nothing sets the layout, so: the file plots at 1\"={_n(h)}', and the plan and the "
            f"profile's stations take that scale; the profile's elevations a tenth of it, "
            f"{v_text}. The grade on the sheet runs from el {_n(low)} to {_n(high)}; the grid "
            f"takes the {_n(ELEV_STEP)} ft lines at or outside them: {_n(low)} rounds down to "
            f"{_n(e0)}, a whole 5, and {_n(high)} rounds up to {_n(e1)}, a whole 5; "
            f"{span_text} ft of elevation, {tall_text} in tall. The sheet's usable area runs "
            f"from [{_n(usable[0])}, {_n(usable[1])}] to [{_n(usable[2])}, {_n(usable[3])}]: "
            f"{room_text} in high, half of it {half_text}.")
        if tall > half:
            v = V_COARSE
            tall_text, tall = _sum(span, "/", v)
            said.append(f"That grid is taller than half the sheet, so the elevations go at "
                        f"1\"={_n(v)}' instead: {tall_text} in tall.")
            if tall > half:
                raise ValueError("the grade does not fit the sheet at 1\"=10'")
        said.append(f"The grid's lower left corner goes {_n(MARGIN_IN)} in inside the usable "
                    f"area's: x {x_text}, y {y_text}; it is station {_n(s0)} el {_n(e0)}.")
    run_text, run = _sum(s1, "-", s0)
    x1_text, x1 = _sum(x0, "+", run, "/", h)
    y1_text, y1 = _sum(y0, "+", span, "/", v)
    said.append(f"The grid is {run_text} ft long and {span_text} ft high: its right edge is at x "
                f"{x1_text} and its top at y {y1_text}.")
    # the plan view
    wide_text, wide = _sum(run, "/", h, "+", SIDE_IN, "+", SIDE_IN)
    cx_text, cx = _sum(x0, "+", run, "/", h, "/", 2.0)
    sc_text, sc = _sum(s0, "+", run, "/", 2.0)
    yb_text, yb = _sum(y1, "+", GAP_IN)
    hp_text, hp = _sum(usable[3], "-", yb)
    cy_text, cy = _sum(yb, "+", hp, "/", 2.0)
    on = next((t for t in tangents["rows"]
               if float(t["start_station"]) <= sc <= float(t["end_station"])), None)
    if on is None:
        raise ValueError("the middle of the sheet is on a curve: no level plan lines up")
    said.append(
        f"The plan goes over the grid at the same scale, so a station is at the same x in both "
        f"when the plan's middle is over the grid's middle and the line runs level there. The "
        f"view is as wide as the grid and {_n(SIDE_IN)} in more each side, {wide_text} in, "
        f"centred at x {cx_text}, which is station {sc_text}. It starts {_n(GAP_IN)} in over the "
        f"grid, y {yb_text}, and runs to the top of the usable area: {hp_text} in high, centred "
        f"at y {cy_text}. Station {_n(sc)} is on {on['ref']} ({_n(on['start_station'])} to "
        f"{_n(on['end_station'])}), a tangent, so its direction is the one to level: find its "
        f"point and direction.")
    calls = [_q("station_to_xy", alignment=alignment, station=sc)]
    results = yield Turn(" ".join(said), calls)
    _ok(results, calls)
    at = results[0]
    direction = float(at["direction_deg"])
    twist = -direction

    # -- 3: the plan view, its stationing, and where its stations landed
    lo, hi = max(s0, a0), min(s1, a1)
    said = [f"The line runs at {_n(direction)} degrees at station {_n(sc)}, so the view is "
            f"turned -{_n(direction)} degrees to lay it level, stations increasing to the right, "
            f"with that station's point at the view's centre."]
    if _full(lo):
        first = lo
    elif lo == s0:
        text_, first = _sum(lo, "+", 50.0)
        said.append(f"The first full station on the sheet is {text_}.")
    else:
        first = math.ceil(lo / 100.0 - 1e-9) * 100.0
        said.append(f"The line begins at {_n(lo)}, on the sheet: {_n(lo)} rounds up to "
                    f"{_n(first)}, a whole 100, its first full station.")
    if _full(hi):
        last = hi
    elif hi == s1:
        text_, last = _sum(hi, "-", 50.0)
        said.append(f"The last full station on the sheet is {text_}.")
    else:
        last = math.floor(hi / 100.0 + 1e-9) * 100.0
        said.append(f"The line ends at {_n(hi)}, on the sheet: {_n(hi)} rounds down to "
                    f"{_n(last)}, a whole 100, its last full station.")
    anno = next((row["name"] for row in layers["layers"]
                 if "stations" in str(row.get("description") or "").lower()), None)
    stationing = {"space": "model", "alignment": alignment, "station_range": [lo, hi],
                  "interval": 100, "lettering": "full", "view_rotation": twist}
    if anno:
        stationing["layer"] = anno
    said.append(f"Station the line through that view from {_n(lo)} to {_n(hi)}, every full "
                f"station lettered and read upright through the turn"
                + (f", on {anno}" if anno else "")
                + f"; then read back where {_n(first)} and {_n(last)} landed on the paper.")
    calls = [_q("create_viewport", sheet=sheet, center_paper=[cx, cy], width_in=wide,
                height_in=hp, model_center=at["point"], feet_per_inch=h, rotation_deg=twist),
             _q("annotate_stationing", **stationing),
             _q("station_to_xy", alignment=alignment, station=first, sheet=sheet),
             _q("station_to_xy", alignment=alignment, station=last, sheet=sheet)]
    results = yield Turn(" ".join(said), calls)
    _ok(results, calls)
    landed = [r["on_sheet"]["sheet_point"] for r in results[2:]]

    # -- 4: lined up? then the grid
    kx_text, kx = _sum(s0, "/", h, "-", x0)
    ky_text, ky = _sum(e0, "/", v, "-", y0)

    def X(station: float) -> Tuple[str, float]:
        op, k = _signed(-kx)
        return _sum(station, "/", h, op, k)

    def Y(elevation: float) -> Tuple[str, float]:
        op, k = _signed(-ky)
        return _sum(elevation, "/", v, op, k)

    said = [f"On the grid a station is at x = station / {_n(h)} - ({kx_text}) and an elevation "
            f"at y = elevation / {_n(v)} - ({ky_text})."]
    for station, point in zip((first, last), landed):
        text_, x = X(station)
        if abs(x - float(point[0])) > LINED_UP_IN:
            raise RuntimeError(f"the plan shows {station} at x {point[0]}, the grid at {x}")
        said.append(f"Station {_n(station)} is at x {text_} on the grid and at x "
                    f"{_n(point[0])} on the plan.")
    said.append("The plan's stations sit over the profile's, to the width of a line.")
    found = [next((row["name"] for row in layers["layers"]
                   if word in str(row.get("description") or "").lower()), None)
             for word in ("profile grid", "profile grade", "annotation for the profile")]
    calls = []
    if all(found):
        l_grid, l_grade, l_text = found
        said.append(f"The file keeps layers for a profile: {l_grid} for the grid, {l_grade} for "
                    f"the grade line, {l_text} for the lettering.")
    else:
        l_grid, l_grade, l_text = OWN_LAYERS
        said.append(f"The file keeps no layers for a profile, so make them: {l_grid}, "
                    f"{l_grade} and {l_text}.")
        calls += [_q("create_layer", name=name) for name in OWN_LAYERS]
    first_g, last_g = s0, s1
    if not _full(s0):
        text_, first_g = _sum(s0, "+", 50.0)
        if first_g != first:        # the line begins later on the sheet: not worked out yet
            said.append(f"The grid's first full station is {text_}.")
    if not _full(s1):
        text_, last_g = _sum(s1, "-", 50.0)
        if last_g != last:
            said.append(f"The grid's last full station is {text_}.")
    xg_text, xg = X(first_g)
    step_text, step = _sum(100.0, "/", h)
    rise_text, rise = _sum(ELEV_STEP, "/", v)
    between_text, between = _sum(last_g, "-", first_g)
    cols_text, cols = _sum(between, "/", 100.0, "+", 1.0)
    rows_text, rows = _sum(span, "/", ELEV_STEP, "+", 1.0)
    cols, rows = int(round(cols)), int(round(rows))
    said.append(
        f"The grid has a line at every full station, {_n(first_g)} to {_n(last_g)}, "
        f"{between_text} ft: the first at "
        f"x {xg_text}, then every {step_text} in, {cols_text} lines; and a line every "
        f"{_n(ELEV_STEP)} ft of elevation from y {_n(y0)}, every {rise_text} in, {rows_text} "
        f"lines. Draw the first of each, from the grid's bottom to its top and from its left "
        f"edge to its right, to repeat next.")
    calls += [_q("draw_line", space=sheet, layer=l_grid, start=[xg, y0], end=[xg, y1]),
              _q("draw_line", space=sheet, layer=l_grid, start=[x0, y0], end=[x1, y0])]
    n_layers = len(calls) - 2
    yl_text, yl = _sum(y0, "-", 0.12)
    said.append(f"Letter the stations under the grid, centred under their lines at y {yl_text}:")
    x, station = xg, first_g
    for k in range(cols):
        if k:
            x_text, x = _sum(x, "+", step)
            s_text, station = _sum(station, "+", 100.0)
            said.append(f"{s_text} at x {x_text};")
        calls.append(_q("place_text", space=sheet, layer=l_text, position=[x, yl],
                        content=_sta(station), height=height, halign="center", valign="top"))
    xl_text, xl = _sum(x0, "+", 0.05)
    xr_text, xr = _sum(x1, "-", 0.05)
    yt_text, yt = _sum(y0, "+", 0.05)
    said.append(f"and the elevations at both ends of their lines, just inside the grid at x "
                f"{xl_text} and x {xr_text} and just over the line, el {_n(e0)} at y {yt_text}:")
    elevation = e0
    for k in range(rows):
        if k:
            e_text, elevation = _sum(elevation, "+", ELEV_STEP)
            y_text, yt = _sum(yt, "+", rise)
            said.append(f"{e_text} at y {y_text};")
        label = str(int(round(elevation)))
        calls.append(_q("place_text", space=sheet, layer=l_text, position=[xl, yt],
                        content=label, height=height, halign="left", valign="bottom"))
        calls.append(_q("place_text", space=sheet, layer=l_text, position=[xr, yt],
                        content=label, height=height, halign="right", valign="bottom"))
    results = yield Turn(" ".join(said), calls)
    _ok(results, calls)
    v_line = results[n_layers]["created"][0]
    h_line = results[n_layers + 1]["created"][0]

    # -- 5: the grid's other lines, the grade line, the curves' lettering
    said = [f"Repeat the grid's lines: {cols} columns {_n(step)} in apart, {rows} rows "
            f"{_n(rise)} in apart."]
    calls = []
    if cols > 1:
        calls.append(_q("array_entities", ids=[v_line], kind="rectangular", rows=1, columns=cols,
                        column_spacing=step))
    calls.append(_q("array_entities", ids=[h_line], kind="rectangular", rows=rows, columns=1,
                    row_spacing=rise))
    said.append("The grade line, each point on the paper:")
    vertices = []
    for s, e in zip(stations, elevations):
        x_text, x = X(s)
        y_text, y = Y(e)
        said.append(f"{_n(s)} el {_n(e)}: x {x_text}, y {y_text};")
        vertices.append([x, y])
    calls.append(_q("draw_polyline", space=sheet, layer=l_grade, vertices=vertices))
    lettered = []
    for row in grade.curves():
        if not (s0 <= float(row["pvi_station"]) <= s1):
            continue
        x_text, x = X(float(row["pvi_station"]))
        y_text, y = Y(float(row["pvi_elevation"]))
        up_text, up = _sum(y, "+", 0.45)
        ty_text, ty = _sum(y, "+", 0.5)
        tx_text, tx = _sum(x, "-", 0.05)
        dn_text, dn = _sum(y, "-", 0.35)
        said.append(
            f"{row['ref']} has its PVI on the sheet, at x {x_text}, y {y_text}: a tick up from "
            f"it to y {up_text}, its station and elevation lettered up the tick from "
            f"[{tx_text}, {ty_text}], and its length and K centred under it at y {dn_text}.")
        calls += [
            _q("draw_line", space=sheet, layer=l_text, start=[x, y], end=[x, up]),
            _q("place_text", space=sheet, layer=l_text, position=[tx, ty],
               content=f"PVI {row['pvi_station_text']}\nEL {float(row['pvi_elevation']):.2f}",
               height=height, rotation_deg=90, halign="left", valign="bottom"),
            _q("place_text", space=sheet, layer=l_text, position=[x, dn],
               content=f"{float(row['length']):.0f}' VC\nK = {float(row['K']):.2f}",
               height=height, halign="center", valign="top")]
        lettered.append(row["ref"])
    marked = []
    for row in grade.curves():
        hl = row["high_low"]
        if not hl or not (s0 <= float(hl["station"]) <= s1):
            continue
        high = hl["kind"] == "high"
        x_text, x = X(float(hl["station"]))
        y_text, y = Y(float(hl["elevation"]))
        op = "-" if high else "+"       # a high point lettered under the grade, a low one over
        end_text, end = _sum(y, op, 0.9)
        ty_text, ty = _sum(y, op, 1.0)
        tx_text, tx = _sum(x, "+", 0.05)
        said.append(
            f"The {hl['kind']} point of {row['ref']} is at x {x_text}, y {y_text}: a tick "
            f"{'down' if high else 'up'} from it to y {end_text}, lettered along the tick from "
            f"[{tx_text}, {ty_text}].")
        calls += [
            _q("draw_line", space=sheet, layer=l_text, start=[x, y], end=[x, end]),
            _q("place_text", space=sheet, layer=l_text, position=[tx, ty],
               content=(f"{'HIGH' if high else 'LOW'} PT {row['high_low_station_text']}\n"
                        f"EL {float(hl['elevation']):.2f}"),
               height=height, rotation_deg=90, halign="right" if high else "left",
               valign="bottom")]
        marked.append(f"the {hl['kind']} point of {row['ref']}")
    if not marked:
        said.append("No vertical curve has a high or low point on this sheet, so none is "
                    "lettered.")
    results = yield Turn(" ".join(said), calls)
    _ok(results, calls)
    note = (f"Sheet {sheet} laid out as plan over profile for {alignment}: the plan at "
            f"1\"={_n(h)}' turned level and stationed, lined up over a profile grid at "
            f"1\"={_n(h)}' by 1\"={_n(v)}' whose lower left corner is at [{_n(x0)}, {_n(y0)}] "
            f"(station {_n(s0)}, el {_n(e0)}); the grade line of {profile} drawn from {_n(g0)} "
            f"to {_n(g1)}; "
            + (f"{', '.join(lettered)} lettered with PVI, length and K" if lettered
               else "no PVI is on the sheet")
            + (f"; {', '.join(marked)} lettered." if marked else "; no high or low point on it."))
    return Turn("Done.", [_q("submit", note=note)])


__all__ = ["solve_profile", "read_brief", "is_brief", "rounded", "RULES", "OWN_LAYERS",
           "digits", "curve_label", "own_layer"]
