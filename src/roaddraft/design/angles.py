"""Pure angle helpers: headings, azimuths, quadrant bearings, DMS.

Conventions (spec section 0):

* ``direction_deg`` is a math heading, degrees counter-clockwise from +X.
* ``azimuth_deg`` is clockwise from north: ``(90 - direction) % 360``.
* Quadrant bearings print as ``N 45°30'15" E`` with degrees zero-padded to
  two digits; deflection angles print as DMS with unpadded degrees.
* Seconds are rounded on the TOTAL seconds first so ``59.9999"`` carries
  into the minutes/degrees instead of printing ``60"``.

Every function here is pure and depends only on ``math``.
"""
from __future__ import annotations

import math
import re
from typing import List, Sequence, Tuple

DEG = "°"


def norm_deg(a: float) -> float:
    """Normalize an angle into ``[0, 360)``."""
    r = math.fmod(float(a), 360.0)
    if r < 0:
        r += 360.0
    if r >= 360.0:  # fmod noise (e.g. -1e-15 + 360)
        r -= 360.0
    return r


def signed_delta_deg(d_in: float, d_out: float) -> float:
    """Signed deflection from heading ``d_in`` to ``d_out`` in ``(-180, 180]``.

    Positive means a left (counter-clockwise) turn.
    """
    d = norm_deg(float(d_out) - float(d_in))
    if d > 180.0:
        d -= 360.0
    return d


def direction_to_azimuth(direction_deg: float) -> float:
    """Math heading (CCW from +X) -> azimuth (CW from north), ``[0, 360)``."""
    return norm_deg(90.0 - float(direction_deg))


def azimuth_to_direction(azimuth_deg: float) -> float:
    """Azimuth (CW from north) -> math heading (CCW from +X), ``[0, 360)``."""
    return norm_deg(90.0 - float(azimuth_deg))


def direction_of(p: Sequence[float], q: Sequence[float]) -> float:
    """Heading of the vector ``p -> q`` in degrees, normalized to ``[0, 360)``."""
    return norm_deg(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])))


def azimuth_of(p: Sequence[float], q: Sequence[float]) -> float:
    """Azimuth of the vector ``p -> q`` (clockwise from north)."""
    return direction_to_azimuth(direction_of(p, q))


def unit_vector(direction_deg: float) -> List[float]:
    """Unit vector ``[cos, sin]`` of a math heading."""
    a = math.radians(direction_deg)
    return [math.cos(a), math.sin(a)]


def left_normal(direction_deg: float) -> List[float]:
    """Unit normal to the LEFT of a heading: ``[-sin, cos]``."""
    a = math.radians(direction_deg)
    return [-math.sin(a), math.cos(a)]


def right_normal(direction_deg: float) -> List[float]:
    """Unit normal to the RIGHT of a heading: ``[sin, -cos]`` (offset +)."""
    a = math.radians(direction_deg)
    return [math.sin(a), -math.cos(a)]


def dms_parts(deg: float, seconds_decimals: int = 0) -> Tuple[int, int, float]:
    """Split a non-negative angle into ``(degrees, minutes, seconds)``.

    The TOTAL seconds are rounded to ``seconds_decimals`` first so that
    ``59.99999°`` becomes ``(60, 0, 0.0)`` rather than ``(59, 59, 60.0)``.
    """
    total = round(abs(float(deg)) * 3600.0, int(seconds_decimals))
    whole = int(math.floor(total + 1e-9))
    frac = total - whole
    if frac < 0:
        frac = 0.0
    d, rem = divmod(whole, 3600)
    m, s = divmod(rem, 60)
    sec = float(s) + (round(frac, int(seconds_decimals)) if seconds_decimals > 0 else 0.0)
    return int(d), int(m), sec


def _sec_text(sec: float, seconds_decimals: int) -> str:
    if seconds_decimals <= 0:
        return f"{int(round(sec)):02d}"
    return f"{sec:0{3 + seconds_decimals}.{seconds_decimals}f}"


def format_dms(deg: float, seconds_decimals: int = 0, pad_degrees: bool = False) -> str:
    """Format an angle as ``45°30'15"`` (degrees unpadded unless asked)."""
    d, m, s = dms_parts(deg, seconds_decimals)
    dtxt = f"{d:02d}" if pad_degrees else f"{d}"
    return f"{dtxt}{DEG}{m:02d}'{_sec_text(s, seconds_decimals)}\""


_DMS_SPLIT = re.compile(r"[°dD′'″\"mMsS\-\s]+")


def parse_dms(text: str) -> float:
    """Parse ``45°30'15"``, ``45d30'15"``, ``45-30-15``, ``45 30 15`` or ``45.5042``.

    Returns decimal degrees.  A leading ``-`` negates the whole angle.
    """
    t = str(text).strip()
    if not t:
        raise ValueError("empty angle text")
    neg = t.startswith("-")
    if neg:
        t = t[1:].strip()
    parts = [p for p in _DMS_SPLIT.split(t) if p != ""]
    if not parts or len(parts) > 3:
        raise ValueError(f"cannot parse angle {text!r}")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"cannot parse angle {text!r}")
    value = 0.0
    for i, v in enumerate(nums):
        value += v / (60.0 ** i)
    return -value if neg else value


def format_bearing(azimuth_deg: float, seconds_decimals: int = 0) -> str:
    """Quadrant bearing of an azimuth, e.g. ``N 45°30'15" E``.

    az in [0, 90] -> ``N az E``; (90, 180] -> ``S (180-az) E``;
    (180, 270] -> ``S (az-180) W``; (270, 360) -> ``N (360-az) W``.
    Degrees are zero-padded to two digits.
    """
    az = norm_deg(azimuth_deg)
    if az <= 90.0:
        ns, ang, ew = "N", az, "E"
    elif az <= 180.0:
        ns, ang, ew = "S", 180.0 - az, "E"
    elif az <= 270.0:
        ns, ang, ew = "S", az - 180.0, "W"
    else:
        ns, ang, ew = "N", 360.0 - az, "W"
    return f"{ns} {format_dms(ang, seconds_decimals, pad_degrees=True)} {ew}"


_BEARING_RE = re.compile(r"^\s*([NnSs])\s*(.*?)\s*([EeWw])\s*$")


def parse_bearing(text: str) -> float:
    """Parse a quadrant bearing into an azimuth (clockwise from north).

    Accepts ``S 45°00'00" E``, ``S45-00-00E``, ``N 45 30 15 W``.
    """
    m = _BEARING_RE.match(str(text))
    if not m:
        raise ValueError(f"cannot parse bearing {text!r}")
    ns, body, ew = m.group(1).upper(), m.group(2), m.group(3).upper()
    ang = parse_dms(body) if body.strip() else 0.0
    if ns == "N" and ew == "E":
        az = ang
    elif ns == "S" and ew == "E":
        az = 180.0 - ang
    elif ns == "S" and ew == "W":
        az = 180.0 + ang
    else:
        az = 360.0 - ang
    return norm_deg(az)


def format_azimuth(azimuth_deg: float, seconds_decimals: int = 0) -> str:
    """Azimuth as DMS without a quadrant, degrees unpadded (``75°00'00"``)."""
    return format_dms(norm_deg(azimuth_deg), seconds_decimals, pad_degrees=False)
