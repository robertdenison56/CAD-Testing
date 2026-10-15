"""Coordinate geometry: bearings and distances in, coordinates out.

A deed, a field book and a design report all describe linework the same way:
start here, run this bearing this far, turn this much, run that far. The engine
works in coordinates, so somebody has to turn one into the other -- and that is
the arithmetic a drafter (or a model) gets wrong: a sine for a cosine, an
azimuth read as a bearing, a deflection turned the wrong way. This module does
it, so a course goes in the way it was written.

A *course* is one leg of a traverse. Its direction is given exactly one way:

* ``bearing``: a quadrant bearing, ``N 45°30'15" E`` (also ``N45-30-15E``,
  ``N 45 30 15 E``, ``N45E``);
* ``azimuth``: degrees clockwise from north, a number or DMS text;
* ``deflection``: the angle turned from the previous course, with its side:
  ``40 L``, ``25°00'00" RT``, or a number, right (clockwise) positive; or the
  size of the angle and ``turn``: left/right;
* ``angle_right``: the angle measured clockwise from the backsight -- the
  previous course run backwards -- as a field traverse records it.

A straight course adds ``distance`` (feet). A curve course is told by its
``radius`` and ``turn`` (left/right) and how much of the circle it runs --
``delta``, ``length`` or ``chord`` -- and it continues the previous course's
direction (a tangent curve) unless ``chord_bearing`` places it on its own (a
non-tangent curve, as a deed calls one).

Points are ``[x, y]`` = ``[easting, northing]``; azimuths are clockwise from
north; nothing here touches a document.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from roaddraft.design.angles import (
    azimuth_to_direction, format_bearing, format_dms, norm_deg, parse_bearing, parse_dms,
)

DIRECTION_KEYS = ("bearing", "azimuth", "deflection", "angle_right")
CURVE_EXTENT_KEYS = ("delta", "length", "chord")
TURNS = {"l": -1, "lt": -1, "left": -1, "r": 1, "rt": 1, "right": 1}

#: A traverse whose end lands this close to its start reports its closure even
#: when close was not asked for (feet).
CLOSURE_REPORT_FT = 1.0


class CogoError(ValueError):
    """A course that cannot be computed, with a hint that says how to fix it."""

    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


# ----------------------------------------------------------------- basics


def forward(point: Sequence[float], azimuth_deg: float, distance: float) -> List[float]:
    """The point ``distance`` feet from ``point`` along ``azimuth_deg``:
    ``E + d sin(az), N + d cos(az)``."""
    a = math.radians(azimuth_deg)
    return [float(point[0]) + distance * math.sin(a),
            float(point[1]) + distance * math.cos(a)]


def inverse(a: Sequence[float], b: Sequence[float]):
    """``(azimuth_deg, distance)`` from ``a`` to ``b``."""
    de, dn = float(b[0]) - float(a[0]), float(b[1]) - float(a[1])
    distance = math.hypot(de, dn)
    azimuth = norm_deg(math.degrees(math.atan2(de, dn))) if distance > 0 else 0.0
    return azimuth, distance


def _angle(value, name: str) -> float:
    """A plain angle: a number of degrees or DMS text (``40°00'00"``, ``40-00-00``)."""
    if isinstance(value, bool):
        raise CogoError(f"{name} must be an angle, got {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return parse_dms(str(value))
    except ValueError:
        raise CogoError(f"{name}: cannot read {value!r} as an angle",
                        hint="degrees as a number (40.5) or DMS text: 40°30'00\", "
                             "40-30-00 or 40 30 00")


def parse_quadrant_bearing(text) -> float:
    """A quadrant bearing as an azimuth, refusing angles past 90 degrees
    (``N 100 E`` is a typo, not a direction)."""
    if not isinstance(text, str):
        raise CogoError(f"bearing must be text like \"N 45°30'15\\\" E\", got {text!r}",
                        hint="a number of degrees from north is an azimuth: pass it as "
                             "azimuth instead")
    try:
        azimuth = parse_bearing(text)
    except ValueError:
        raise CogoError(f"cannot read bearing {text!r}",
                        hint="a quadrant bearing starts with N or S and ends with E or W: "
                             "N 47°30'15\" E, S47-30-15W, N47E")
    body = re.sub(r"^\s*[NnSs]|[EeWw]\s*$", "", text)
    if body.strip():
        try:
            quadrant = parse_dms(body)
        except ValueError:
            quadrant = 0.0
        if quadrant > 90.0 + 1e-9:
            raise CogoError(f"bearing {text!r} turns {quadrant:g}° from north or south; a "
                            f"quadrant bearing is at most 90°",
                            hint="past 90° it is the other quadrant (N 104 E is S 76 E), "
                                 "or give an azimuth (clockwise from north, 0-360)")
    return azimuth


#: An angle with its side named before or after it: "40 L", "L40", "40L",
#: "25°00'00\" RT", "LEFT 40". The look-arounds keep a side from being read
#: out of the middle of a word.
_SIDED = re.compile(r"^\s*(?:(lt|rt|left|right|l|r)(?![a-z])\s*)?(.*?)\s*"
                    r"(?:(?<![a-z])(lt|rt|left|right|l|r))?\s*$", re.IGNORECASE)


def parse_deflection(value, turn=None) -> float:
    """A deflection as a signed angle, right (clockwise) positive.

    ``40 L``, ``L 40``, ``25°00'00" RT``, ``-40`` (left), or the size of the
    angle with ``turn`` = left/right."""
    side = None
    if turn is not None:
        side = TURNS.get(str(turn).strip().lower())
        if side is None:
            raise CogoError(f"turn must be left or right, got {turn!r}")
    if isinstance(value, bool):
        raise CogoError(f"deflection must be an angle, got {value!r}")
    if isinstance(value, (int, float)):
        size = float(value)
        if side is not None:
            if size < 0:
                raise CogoError("give the deflection's size with turn, or a signed number "
                                "(right positive), not both",
                                hint="{deflection: 40, turn: 'left'} or {deflection: -40}")
            return side * size
        return size
    m = _SIDED.match(str(value))
    before, body, after = (m.group(1), m.group(2), m.group(3)) if m else (None, str(value), None)
    if before and after:
        raise CogoError(f"deflection {value!r} names a side twice")
    named = before or after
    if named:
        named_side = TURNS[named.lower()]
        if side is not None and side != named_side:
            raise CogoError(f"deflection {value!r} turns {named} but turn says {turn}")
        side = named_side
    size = _angle(body, "deflection")
    if side is None:
        return size
    if size < 0:
        raise CogoError(f"deflection {value!r}: a sided angle is a size; drop the minus sign")
    return side * size


def _turn_sign(turn, where: str) -> int:
    side = TURNS.get(str(turn).strip().lower()) if turn is not None else None
    if side is None:
        raise CogoError(f"{where}: turn must be left or right, got {turn!r}",
                        hint="a curve bends one way: turn: 'left' or 'right' (L/R)")
    return side


def describe_turn(sign: int) -> str:
    return "right" if sign > 0 else "left"


# -------------------------------------------------------------- directions


def direction_of_leg(leg: dict, previous_azimuth: Optional[float], where: str) -> float:
    """The azimuth a straight course runs at, from whichever one way it was given."""
    given = [k for k in DIRECTION_KEYS if k in leg]
    if len(given) != 1:
        raise CogoError(
            f"{where}: give exactly one of bearing, azimuth, deflection or angle_right"
            + (f" (got {', '.join(given)})" if given else ""),
            hint="bearing: \"N 47°30'15\\\" E\"; azimuth: 47.5 (clockwise from north); "
                 "deflection: \"33 L\" (turned from the previous course)")
    key = given[0]
    if key == "bearing":
        return parse_quadrant_bearing(leg["bearing"])
    if key == "azimuth":
        return norm_deg(_angle(leg["azimuth"], f"{where} azimuth"))
    if previous_azimuth is None:
        raise CogoError(
            f"{where}: a {key.replace('_', ' ')} is turned from the previous course, and "
            f"there is none",
            hint="give the first course a bearing or an azimuth (or initial_bearing / "
                 "initial_azimuth for the direction it turns from)")
    if key == "deflection":
        return norm_deg(previous_azimuth + parse_deflection(leg["deflection"], leg.get("turn")))
    return norm_deg(previous_azimuth + 180.0 + _angle(leg["angle_right"], f"{where} angle_right"))


def distance_of_leg(leg: dict, where: str) -> float:
    value = leg.get("distance")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CogoError(f"{where}: distance must be a number of feet, got {value!r}")
    if value <= 0:
        raise CogoError(f"{where}: distance must be positive, got {value:g}")
    return float(value)


# ----------------------------------------------------------------- courses


@dataclass
class Course:
    """One computed leg: a line, or a circular curve."""

    kind: str  # "line" | "curve"
    start: List[float]
    end: List[float]
    azimuth_in: float
    azimuth_out: float
    length: float
    # curves only
    center: Optional[List[float]] = None
    radius: Optional[float] = None
    delta: Optional[float] = None
    turn: Optional[int] = None  # +1 right, -1 left
    tangent: bool = True  # a curve that continues the previous course's direction

    @property
    def chord(self) -> float:
        return math.dist(self.start, self.end)

    @property
    def chord_azimuth(self) -> float:
        return inverse(self.start, self.end)[0]

    def arc_angles(self):
        """``(start_angle_deg, end_angle_deg)`` of the curve as a counter-clockwise
        arc entity: a left curve runs counter-clockwise from its start, a right
        one clockwise, so its entity starts at the course's end."""
        a0 = math.degrees(math.atan2(self.start[1] - self.center[1],
                                     self.start[0] - self.center[0]))
        if self.turn < 0:
            return a0, a0 + self.delta
        return a0 - self.delta, a0

    def to_dict(self, decimals: int = 6) -> dict:
        def r(v):
            return round(v, decimals)

        out = {"kind": self.kind, "start": [r(v) for v in self.start],
               "end": [r(v) for v in self.end]}
        if self.kind == "line":
            out.update(azimuth=r(self.azimuth_in), bearing=format_bearing(self.azimuth_in),
                       distance=r(self.length))
            return out
        out.update(radius=r(self.radius), turn=describe_turn(self.turn),
                   delta=r(self.delta), delta_text=format_dms(self.delta),
                   length=r(self.length), chord=r(self.chord),
                   chord_bearing=format_bearing(self.chord_azimuth),
                   center=[r(v) for v in self.center],
                   bearing_in=format_bearing(self.azimuth_in),
                   bearing_out=format_bearing(self.azimuth_out),
                   tangent=self.tangent)
        return out

    def describe(self) -> str:
        if self.kind == "line":
            return f"{format_bearing(self.azimuth_in)} {self.length:.2f}'"
        return (f"curve {describe_turn(self.turn)} R={self.radius:.2f}' "
                f"Δ={format_dms(self.delta)} L={self.length:.2f}'")


def _curve_course(start, previous_azimuth: Optional[float], leg: dict, where: str) -> Course:
    radius = leg.get("radius")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius <= 0:
        raise CogoError(f"{where}: a curve needs a positive radius, got {radius!r}")
    radius = float(radius)
    sign = _turn_sign(leg.get("turn"), where)
    given = [k for k in CURVE_EXTENT_KEYS if k in leg]
    if len(given) != 1:
        raise CogoError(f"{where}: say how far the curve runs with exactly one of delta, "
                        f"length or chord" + (f" (got {', '.join(given)})" if given else ""),
                        hint="delta: the central angle (40 or \"40°00'00\\\"\"); length: arc "
                             "length in feet; chord: the straight distance end to end")
    if given[0] == "delta":
        delta = _angle(leg["delta"], f"{where} delta")
    elif given[0] == "length":
        length = leg["length"]
        if isinstance(length, bool) or not isinstance(length, (int, float)) or length <= 0:
            raise CogoError(f"{where}: length must be a positive number of feet")
        delta = math.degrees(float(length) / radius)
    else:
        chord = leg["chord"]
        if isinstance(chord, bool) or not isinstance(chord, (int, float)) or chord <= 0:
            raise CogoError(f"{where}: chord must be a positive number of feet")
        if chord > 2.0 * radius + 1e-9:
            raise CogoError(f"{where}: a {chord:g}' chord does not fit a {radius:g}' radius "
                            f"(at most the diameter, {2 * radius:g}')")
        delta = math.degrees(2.0 * math.asin(min(1.0, float(chord) / (2.0 * radius))))
    if not 0.0 < delta < 360.0:
        raise CogoError(f"{where}: a curve's central angle must be between 0 and 360 "
                        f"degrees, got {delta:g}")
    tangent = "chord_bearing" not in leg
    if tangent:
        if previous_azimuth is None:
            raise CogoError(
                f"{where}: a tangent curve continues the previous course's direction, and "
                f"there is none",
                hint="give chord_bearing for a curve that does not start tangent, or "
                     "initial_bearing for the direction the traverse starts in")
        azimuth_in = previous_azimuth
    else:
        chord_azimuth = parse_quadrant_bearing(leg["chord_bearing"]) \
            if isinstance(leg["chord_bearing"], str) and re.match(r"^\s*[NnSs]", leg["chord_bearing"]) \
            else norm_deg(_angle(leg["chord_bearing"], f"{where} chord_bearing"))
        azimuth_in = norm_deg(chord_azimuth - sign * delta / 2.0)
    center = forward(start, azimuth_in + sign * 90.0, radius)
    chord_len = 2.0 * radius * math.sin(math.radians(delta) / 2.0)
    end = forward(start, azimuth_in + sign * delta / 2.0, chord_len)
    return Course(kind="curve", start=list(start), end=end, azimuth_in=azimuth_in,
                  azimuth_out=norm_deg(azimuth_in + sign * delta),
                  length=radius * math.radians(delta), center=center, radius=radius,
                  delta=delta, turn=sign, tangent=tangent)


def is_curve_leg(leg: dict) -> bool:
    return "radius" in leg


@dataclass
class Traverse:
    start: List[float]
    courses: List[Course] = field(default_factory=list)
    closing: Optional[Course] = None  # the course back to the start, when it closes

    @property
    def end(self) -> List[float]:
        return list(self.courses[-1].end) if self.courses else list(self.start)

    @property
    def length(self) -> float:
        return sum(c.length for c in self.courses)

    def misclosure(self) -> dict:
        """How far the end lands from the start: the error a closed traverse
        carries, its direction, and the precision ratio surveyors quote."""
        azimuth, error = inverse(self.end, self.start)
        out = {"distance": error, "dx": self.start[0] - self.end[0],
               "dy": self.start[1] - self.end[1], "perimeter": self.length}
        if error > 1e-9:
            out["bearing"] = format_bearing(azimuth)
            out["precision"] = self.length / error
            out["precision_text"] = f"1:{self.length / error:,.0f}"
        else:
            out["precision_text"] = "closes exactly"
        return out


def run_traverse(start: Sequence[float], legs: List[dict],
                 initial_azimuth: Optional[float] = None, close: bool = False) -> Traverse:
    """Compute a traverse from ``start`` through ``legs``.

    ``initial_azimuth`` is the direction a leading deflection or tangent curve
    turns from (the course the traverse continues). With ``close`` the closing
    course from the end back to the start is computed too."""
    if not legs:
        raise CogoError("a traverse needs at least one course")
    point = [float(start[0]), float(start[1])]
    traverse = Traverse(start=list(point))
    azimuth = initial_azimuth
    for i, leg in enumerate(legs):
        where = f"legs[{i}]"
        if not isinstance(leg, dict):
            raise CogoError(f"{where} must be an object, got {leg!r}")
        if is_curve_leg(leg):
            stray = [k for k in DIRECTION_KEYS + ("distance",) if k in leg]
            if stray:
                raise CogoError(f"{where} has a radius, which makes it a curve, and also "
                                f"{', '.join(stray)}",
                                hint="a curve course is {radius, turn, delta|length|chord"
                                     "[, chord_bearing]}; a straight one is {bearing|azimuth|"
                                     "deflection|angle_right, distance}")
            course = _curve_course(point, azimuth, leg, where)
        else:
            stray = [k for k in ("turn",) if k in leg and "deflection" not in leg]
            stray += [k for k in CURVE_EXTENT_KEYS + ("chord_bearing",) if k in leg]
            if stray:
                verb = "belongs" if len(stray) == 1 else "belong"
                raise CogoError(f"{where}: {', '.join(stray)} {verb} to a curve course, which "
                                f"needs a radius",
                                hint="{radius: 500, turn: 'left', delta: 40} is a curve")
            az = direction_of_leg(leg, azimuth, where)
            dist = distance_of_leg(leg, where)
            course = Course(kind="line", start=list(point), end=forward(point, az, dist),
                            azimuth_in=az, azimuth_out=az, length=dist)
        traverse.courses.append(course)
        point = course.end
        azimuth = course.azimuth_out
    if close:
        az, dist = inverse(point, traverse.start)
        if dist > 1e-9:
            traverse.closing = Course(kind="line", start=list(point), end=list(traverse.start),
                                      azimuth_in=az, azimuth_out=az, length=dist)
    return traverse


def initial_azimuth_of(p: dict) -> Optional[float]:
    """The direction a traverse starts from, given as ``initial_bearing`` or
    ``initial_azimuth`` (at most one)."""
    if "initial_bearing" in p and "initial_azimuth" in p:
        raise CogoError("give initial_bearing or initial_azimuth, not both")
    if "initial_bearing" in p:
        return parse_quadrant_bearing(p["initial_bearing"])
    if "initial_azimuth" in p:
        return norm_deg(_angle(p["initial_azimuth"], "initial_azimuth"))
    return None


# ------------------------------------------------------- alignment legs


def pis_from_legs(start: Sequence[float], legs: List[dict]) -> List[list]:
    """PI rows for ``create_alignment`` from a start point and PI-to-PI legs.

    Each leg runs from one PI to the next: a direction (bearing, azimuth,
    deflection or angle_right) and a ``distance``. A leg after the first may
    carry ``radius``, the curve at the PI where it starts -- where the
    alignment deflects -- which is how a layout is described: "S 80° E 800 ft
    to PI-1, where it deflects 40° left on a 500 ft curve; then 700 ft ..."."""
    if not legs:
        raise CogoError("legs needs at least one leg from BEGIN")
    points = [[float(start[0]), float(start[1])]]
    radii = [0.0]
    azimuth = None
    for i, leg in enumerate(legs):
        where = f"legs[{i}]"
        if not isinstance(leg, dict):
            raise CogoError(f"{where} must be an object, got {leg!r}")
        stray = [k for k in CURVE_EXTENT_KEYS + ("chord_bearing",) if k in leg]
        if stray:
            raise CogoError(f"{where}: {', '.join(stray)} describe a curve course of a "
                            f"traverse; an alignment leg is a tangent from PI to PI",
                            hint="put the curve's radius on the leg that starts at its PI "
                                 "and the alignment fits the curve there")
        radius = leg.get("radius", 0.0)
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius < 0:
            raise CogoError(f"{where}: radius must be a number of feet (0 for none)")
        if i == 0 and radius:
            raise CogoError(f"{where} starts at BEGIN, which carries no curve",
                            hint="a leg's radius is the curve at the PI where that leg "
                                 "starts; put it on the next leg")
        if "turn" in leg and "deflection" not in leg:
            raise CogoError(f"{where}: turn goes with deflection")
        azimuth = direction_of_leg(leg, azimuth, where)
        points.append(forward(points[-1], azimuth, distance_of_leg(leg, where)))
        if i > 0:
            radii[-1] = float(radius)
        radii.append(0.0)
    return [[p[0], p[1], r] if r else [p[0], p[1]] for p, r in zip(points, radii)]


# ------------------------------------------------------------- leg text

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)"
_KV = re.compile(r"^(r|radius|d|delta|l|len|length|c|chord|cb|chord_bearing)\s*=\s*(.+)$",
                 re.IGNORECASE)


def parse_leg_text(text: str) -> dict:
    """One course as people write it, for the command line and the GUI.

    * ``N 45°30'15" E 250.00`` -- bearing then distance (``S80E 800``);
    * ``AZ 75.5 250`` -- azimuth then distance;
    * ``40 L 700`` / ``25°00'00" RT 600`` -- deflection then distance;
    * a trailing ``R=500`` adds a radius (the curve at the PI, for an alignment);
    * ``CURVE R=500 LEFT DELTA=40`` (or ``L=``/``LENGTH=``, ``CHORD=``,
      ``CB=`` for a non-tangent chord bearing) -- a curve course.
    """
    raw = str(text).strip()
    if not raw:
        raise CogoError("empty course")
    tokens = raw.replace(",", " ").split()
    head = tokens[0].lower()
    if head in ("c", "curve", "arc"):
        leg: dict = {}
        for token in tokens[1:]:
            kv = _KV.match(token)
            if kv:
                key, value = kv.group(1).lower(), kv.group(2)
                if key in ("r", "radius"):
                    leg["radius"] = _number(value, raw)
                elif key in ("d", "delta"):
                    leg["delta"] = value
                elif key in ("l", "len", "length"):
                    leg["length"] = _number(value, raw)
                elif key in ("c", "chord"):
                    leg["chord"] = _number(value, raw)
                else:
                    leg["chord_bearing"] = value
            elif token.lower() in TURNS:
                leg["turn"] = describe_turn(TURNS[token.lower()])
            else:
                raise CogoError(f"cannot read {token!r} in curve course {raw!r}",
                                hint="CURVE R=450 LEFT DELTA=33°00'00\" (or L=260, "
                                     "CHORD=255, CB=N76E for a non-tangent curve)")
        return leg
    radius = None
    if len(tokens) >= 2 and _KV.match(tokens[-1]) and _KV.match(tokens[-1]).group(1).lower() \
            in ("r", "radius"):
        radius = _number(_KV.match(tokens[-1]).group(2), raw)
        tokens = tokens[:-1]
    if len(tokens) < 2:
        raise CogoError(f"cannot read course {raw!r}",
                        hint="a direction then a distance: N47°30'E 250, AZ 75.5 250, "
                             "33 L 820")
    dist_text, body = tokens[-1], " ".join(tokens[:-1])
    distance = _number(dist_text.rstrip("'"), raw)
    if body.lower().startswith("az"):
        leg = {"azimuth": body[2:].lstrip(" =:")}
    elif re.match(r"^\s*[NnSs]", body) and re.search(r"[EeWw]\s*$", body):
        leg = {"bearing": body}
    elif _SIDED.match(body) and (_SIDED.match(body).group(1) or _SIDED.match(body).group(3)):
        leg = {"deflection": body}
    else:
        raise CogoError(f"cannot read the direction {body!r} in course {raw!r}",
                        hint="a bearing (N47°30'E), AZ and an azimuth (AZ 75.5) or a "
                             "deflection with its side (33 L, 18°30'00\" RT)")
    leg["distance"] = distance
    if radius is not None:
        leg["radius"] = radius
    return leg


def _number(text: str, course: str) -> float:
    try:
        return float(str(text).strip().rstrip("'"))
    except ValueError:
        raise CogoError(f"cannot read {text!r} as a number in course {course!r}")


def as_leg(value, where: str) -> dict:
    """A leg given as an object, or as one course of text."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return parse_leg_text(value)
        except CogoError as e:
            raise CogoError(f"{where}: {e}", hint=e.hint)
    raise CogoError(f"{where} must be an object or a course of text, got {value!r}")


def direction_as_heading(azimuth_deg: float) -> float:
    """Math heading (CCW from +X) of an azimuth, for code that draws."""
    return azimuth_to_direction(azimuth_deg)


__all__ = [
    "CogoError", "Course", "Traverse", "forward", "inverse", "parse_quadrant_bearing",
    "parse_deflection", "direction_of_leg", "run_traverse", "pis_from_legs",
    "parse_leg_text", "as_leg", "initial_azimuth_of", "describe_turn",
]
