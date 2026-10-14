"""Reading labels, table cells and the scale string by meaning.

At the ``full`` prompt level the prompt states every format, so content is
compared exactly (after ``normalize``).  At a terse level it does not, so a
value is right when it *means* the right thing: ``18+00`` is station
``18+00.00``, ``PC`` is the curve point the spec letters ``BC``,
``N45-30-15E`` is ``N 45°30'15" E``.  The value itself still has to be
right to the spec's tolerances; only the way it is written is free.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, Optional

from roaddraft.core.units import parse_station
from roaddraft.design.angles import parse_bearing, parse_dms
from roaddraft.verify.normalize import normalize

_STATION = r"(-?\d+\s*\+\s*\d+(?:\.\d*)?)"
_STA_RE = re.compile(r"^(?:STA\.?\s*)?" + _STATION + r"$", re.I)
_POINT_WORDS = {"pc": ("BC", "PC"), "pt": ("EC", "PT"), "pcc": ("PCC",), "prc": ("PRC",),
                "pi": ("PI",)}
#: a curve number: bare (the PPM's bubble), or C-1, C1, CURVE 1, CURVE NO. 1
_MC_RE = re.compile(r"^(?:C(?:URVE)?\s*(?:NO\.?)?\s*[-#]?\s*)?(\d+)$", re.I)
#: a bearing with an optional length after it: N 71°33'54\" E 1240.36'
_BEARING_LENGTH_RE = re.compile(r"^(.*?[NS].*?[EW])\s*([+-]?\d+(?:\.\d*)?)?\s*(?:'|FT\.?|FEET)?$", re.I)
_EQ_RE = re.compile(r"^(?:STA\.?\s*)?" + _STATION + r"\s*(?:BK|BACK)\.?\s*=\s*(?:STA\.?\s*)?"
                    + _STATION + r"\s*(?:AH|AHEAD)\.?$", re.I)
_NUMBER_RE = re.compile(r"^([+-]?\d+(?:\.\d*)?|\.\d+)\s*(?:'|FT\.?|FEET)?$", re.I)
_SCALE_RE = re.compile(r"^(?:SCALE:?\s*)?1\s*(?:\"|IN\.?|INCH)\s*=\s*(\d+(?:\.\d*)?)\s*(?:'|FT\.?|FEET)$",
                       re.I)

STATION_TOL = 0.005 + 1e-9
ANGLE_TOL_DEG = 1.0 / 3600.0 + 1e-9
LENGTH_TOL = 0.005 + 1e-9


def station(text: str) -> Optional[float]:
    m = _STA_RE.match(normalize(text))
    if not m:
        return None
    try:
        return parse_station(m.group(1).replace(" ", ""))
    except ValueError:
        return None


def _angle_close(a: float, b: float) -> bool:
    return abs((a - b + 180.0) % 360.0 - 180.0) <= ANGLE_TOL_DEG


def _bearing(text: str) -> Optional[float]:
    return _bearing_length(text)[0]


def _bearing_length(text: str):
    """``(azimuth, length)`` of a tangent's lettering: the bearing, with the
    length the PPM sets after it or none."""
    t = normalize(text)
    try:
        return parse_bearing(t), None
    except ValueError:
        pass
    m = _BEARING_LENGTH_RE.match(t)
    if not m:
        return None, None
    try:
        az = parse_bearing(m.group(1).strip())
    except ValueError:
        return None, None
    return az, (float(m.group(2)) if m.group(2) else None)


def _dms(text: str) -> Optional[float]:
    try:
        return parse_dms(normalize(text))
    except ValueError:
        return None


def _number(text: str) -> Optional[float]:
    m = _NUMBER_RE.match(normalize(text))
    return float(m.group(1)) if m else None


def _point_label(text: str, words) -> Optional[float]:
    """The station a curve-point label gives when its word is one of ``words``
    (first or last), else None."""
    parts = text.split()
    if len(parts) < 2:
        return None
    if parts[0].upper() in words:
        rest = " ".join(parts[1:])
    elif parts[-1].upper() in words:
        rest = " ".join(parts[:-1])
    else:
        return None
    return station(rest)


def same_label(kind: str, actual: str, expected: str) -> bool:
    """True when ``actual`` says what ``expected`` says, for a label of ``kind``."""
    a, e = normalize(actual), normalize(expected)
    if a == e:
        return True
    if kind == "station":
        x, y = station(a), station(e)
        return x is not None and y is not None and abs(x - y) <= STATION_TOL
    if kind in _POINT_WORDS:
        # the word before the station (BC 24+05.27) or after it, as the PPM
        # letters a layout (24+05.27 BC); either way it must be the right word
        pa, pe = _point_label(a, _POINT_WORDS[kind]), _point_label(e, _POINT_WORDS[kind])
        return (pa is not None and pe is not None and abs(pa - pe) <= STATION_TOL)
    if kind == "mc":
        ma, me = _MC_RE.match(a), _MC_RE.match(e)
        return bool(ma and me and int(ma.group(1)) == int(me.group(1)))
    if kind == "bearing":
        # the bearing must agree, and the length too when the expected has one
        (x, lx), (y, ly) = _bearing_length(a), _bearing_length(e)
        if x is None or y is None or not _angle_close(x, y):
            return False
        return ly is None or (lx is not None and abs(lx - ly) <= LENGTH_TOL)
    if kind == "equation":
        ma, me = _EQ_RE.match(a), _EQ_RE.match(e)
        if not (ma and me):
            return False
        return all(abs(parse_station(ma.group(i).replace(" ", ""))
                       - parse_station(me.group(i).replace(" ", ""))) <= STATION_TOL
                   for i in (1, 2))
    return False


# ------------------------------------------------------------- curve table

#: header words a drafter might use for each curve-table column key
HEADER_SYNONYMS: Dict[str, tuple] = {
    "curve": ("CURVE", "CURVE NO", "CURVE NO.", "CURVE #", "NO", "NO."),
    "pi_sta": ("PI STA", "PI STA.", "PI STATION", "PI"),
    "pc_sta": ("BC STA", "PC STA", "BC STATION", "PC STATION", "BC", "PC"),
    "pt_sta": ("EC STA", "PT STA", "EC STATION", "PT STATION", "EC", "PT"),
    "delta": ("DELTA", "Δ", "DELTA ANGLE", "CENTRAL ANGLE", "DEFLECTION", "I"),
    "direction": ("DIR", "DIR.", "DIRECTION", "TURN"),
    "radius": ("R", "RADIUS"),
    "tangent": ("T", "TANGENT", "TANGENT LENGTH"),
    "length": ("L", "LENGTH", "ARC LENGTH", "CURVE LENGTH"),
    "external": ("E", "EXTERNAL"),
    "mid_ordinate": ("M", "MIDDLE ORDINATE", "MID ORDINATE"),
    "chord": ("C", "CHORD", "LC", "LONG CHORD", "CHORD LENGTH"),
    "chord_bearing": ("CH BRG", "CHORD BEARING", "CB", "CHORD BRG"),
}
_HEADER_KEY = {normalize(h).upper(): key for key, hs in HEADER_SYNONYMS.items() for h in hs}


def column_key(header: str) -> Optional[str]:
    return _HEADER_KEY.get(normalize(header).upper())


def _direction(text: str) -> Optional[str]:
    t = normalize(text).upper()
    return {"L": "L", "LT": "L", "LEFT": "L", "R": "R", "RT": "R", "RIGHT": "R"}.get(t)


_CELL: Dict[str, Callable[[str, str], bool]] = {
    "curve": lambda a, e: same_label("mc", a, e),
    "delta": lambda a, e: (lambda x, y: x is not None and y is not None and _angle_close(x, y))(
        _dms(a), _dms(e)),
    "direction": lambda a, e: _direction(a) is not None and _direction(a) == _direction(e),
    "chord_bearing": lambda a, e: same_label("bearing", a, e),
}
for _k in ("pi_sta", "pc_sta", "pt_sta"):
    _CELL[_k] = lambda a, e: same_label("station", a, e)
for _k in ("radius", "tangent", "length", "external", "mid_ordinate", "chord"):
    _CELL[_k] = lambda a, e: (lambda x, y: x is not None and y is not None
                              and abs(x - y) <= LENGTH_TOL)(_number(a), _number(e))


def same_cell(key: str, actual: str, expected: str) -> bool:
    if normalize(actual) == normalize(expected):
        return True
    fn = _CELL.get(key)
    return bool(fn and fn(actual, expected))


_ANY_STATION = re.compile(_STATION)


def same_match_label(actual: str, station_text: str, other_sheet: str) -> bool:
    """A match-line label by meaning: it says MATCH, names the break station
    (any format) and the sheet it continues on."""
    a = normalize(actual).upper()
    if "MATCH" not in a or normalize(other_sheet).upper() not in a:
        return False
    want = parse_station(station_text.replace(" ", ""))
    for m in _ANY_STATION.finditer(a):
        try:
            if abs(parse_station(m.group(1).replace(" ", "")) - want) <= STATION_TOL:
                return True
        except ValueError:
            continue
    return False


def scale_fpi(text: str) -> Optional[float]:
    """Feet per inch from a scale string like ``1" = 50'``."""
    m = _SCALE_RE.match(normalize(text))
    return float(m.group(1)) if m else None


__all__ = ["same_label", "same_cell", "column_key", "HEADER_SYNONYMS", "scale_fpi", "station",
           "same_match_label"]
