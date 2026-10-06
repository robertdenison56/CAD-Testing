"""Reading the numbers a drafter letters: stations, bearings, angles, feet.

The tier-3 checks hold lettering to its *value*, not its spelling. A bearing
written ``N71°33'54"E``, ``N 71°33'54" E`` or ``N 71-33-54 E`` is the same
bearing, and all three pass where the value is right. ``N 71°35'34" E`` fails
wherever it is written. Stations must carry their plus (``24+05.27``, not
``2405.27``), since that is how a station is lettered.

Each reader returns every value it finds in a string, in order, so a check can
ask whether the right one is among them and quote what was written when it is
not.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_DEG = "°º˚"
_MIN = "'’′‘`"
_SEC = '"”″“'

STATION_RE = re.compile(r"(?<![\d.])(\d+)\s*\+\s*(\d{2}(?:\.\d+)?)(?![\d])")
BEARING_RE = re.compile(
    rf"\b([NS])\s*(\d{{1,2}}(?:\.\d+)?)\s*(?:[{_DEG}]|d\b|-|\s)\s*(\d{{1,2}})\s*(?:[{_MIN}]|m\b|-|\s)"
    rf"\s*(\d{{1,2}}(?:\.\d+)?)\s*(?:[{_SEC}]|''|s\b)?\s*([EW])\b", re.I)
DMS_RE = re.compile(
    rf"(?<![\d.])(\d{{1,3}})\s*[{_DEG}]\s*(\d{{1,2}})\s*[{_MIN}]\s*(\d{{1,2}}(?:\.\d+)?)\s*(?:[{_SEC}]|'')?")
DECIMAL_DEG_RE = re.compile(rf"(?<![\d.])(\d{{1,3}}\.\d+)\s*[{_DEG}]")
FEET_RE = re.compile(rf"(?<![\d.+])(\d[\d,]*(?:\.\d+)?)\s*(?:[{_MIN}]|\bFT\b|\bFEET\b)", re.I)
NUMBER_RE = re.compile(r"^\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*$")
WORD_RE = re.compile(r"[A-Z]+")


def stations(text: str) -> List[Tuple[float, str]]:
    """``(feet, as written)`` for every ``12+34.56`` in the text."""
    out = []
    for m in STATION_RE.finditer(text or ""):
        out.append((int(m.group(1)) * 100.0 + float(m.group(2)), m.group(0)))
    return out


def has_station(text: str, value: float, decimals: int = 2) -> bool:
    """Does the text letter this station, to ``decimals`` places?"""
    for feet_value, written in stations(text):
        frac = written.split("+", 1)[1].strip()
        places = len(frac.split(".", 1)[1]) if "." in frac else 0
        if places >= decimals and abs(feet_value - value) <= 0.5 * 10 ** -decimals + 1e-9:
            return True
    return False


def bearings(text: str) -> List[float]:
    """Azimuths (degrees clockwise from north) of every quadrant bearing."""
    out = []
    for m in BEARING_RE.finditer(text or ""):
        ns, d, mi, s, ew = m.groups()
        angle = float(d) + float(mi) / 60.0 + float(s) / 3600.0
        ns, ew = ns.upper(), ew.upper()
        if ns == "N":
            az = angle if ew == "E" else 360.0 - angle
        else:
            az = 180.0 - angle if ew == "E" else 180.0 + angle
        out.append(az % 360.0)
    return out


def azimuth_close(a: float, b: float, seconds: float = 1.0, either_way: bool = False) -> bool:
    """Within ``seconds`` of arc, optionally allowing the back bearing."""
    d = abs((a - b + 180.0) % 360.0 - 180.0)
    if either_way:
        d = min(d, abs((a - b) % 360.0 - 180.0))
    return d <= seconds / 3600.0 + 1e-9


def _without_bearings(text: str) -> str:
    return BEARING_RE.sub(" ", text or "")


def angles(text: str) -> List[float]:
    """Degrees of every degree-minute-second angle that is not part of a bearing."""
    out = []
    for m in DMS_RE.finditer(_without_bearings(text)):
        out.append(float(m.group(1)) + float(m.group(2)) / 60.0 + float(m.group(3)) / 3600.0)
    return out


def decimal_degrees(text: str) -> List[float]:
    """Angles written as decimal degrees (``18.43°``): how a DMS angle should not be."""
    return [float(m.group(1)) for m in DECIMAL_DEG_RE.finditer(_without_bearings(text))]


def _without_angles(text: str) -> str:
    t = _without_bearings(text)
    t = DMS_RE.sub(" ", t)
    return STATION_RE.sub(" ", t)


def feet(text: str) -> List[float]:
    """Every length marked as feet (``1240.36'``, ``12 FT``), angles and stations excluded."""
    return [float(m.group(1).replace(",", "")) for m in FEET_RE.finditer(_without_angles(text))]


def number(cell: str) -> Optional[float]:
    """A table cell that is a bare number, or a number marked as feet."""
    if bearings(cell) or angles(cell) or stations(cell):
        return None
    m = NUMBER_RE.match(cell or "")
    if m:
        return float(m.group(1).replace(",", ""))
    found = feet(cell)
    if len(found) == 1 and FEET_RE.sub("", _without_angles(cell)).strip() == "":
        return found[0]
    return None


def words(text: str) -> List[str]:
    """Upper-case words, so ``BC`` in ``"SR-100" 24+05.27 BC`` is found and the
    ``EC`` hidden in ``SEC`` is not."""
    return WORD_RE.findall((text or "").upper())


def has_word(text: str, word: str) -> bool:
    return word.upper() in words(text)


def curve_number(cell: str) -> Optional[int]:
    """``1``, ``C1``, ``C-1`` or ``CURVE 1``, read as curve 1."""
    m = re.match(r"^\s*(?:CURVE\s*|C\s*-?\s*)?(\d+)\s*$", (cell or "").upper())
    return int(m.group(1)) if m else None


__all__ = ["stations", "has_station", "bearings", "azimuth_close", "angles", "decimal_degrees",
           "feet", "number", "words", "has_word", "curve_number"]
