"""Units and formatting.

Model space units are US survey feet; paper (sheet) units are inches.
Viewport scale is expressed as feet-per-inch (1"=50' -> 50.0).
"""
from __future__ import annotations

US_SURVEY_FOOT_METERS = 1200.0 / 3937.0


def format_station(value_ft: float, decimals: int = 2) -> str:
    """Format a station distance in feet as '12+34.57' (100-ft stations)."""
    sign = "-" if value_ft < 0 else ""
    v = abs(float(value_ft))
    whole = int(v // 100)
    rem = v - whole * 100
    rem_txt = f"{rem:0{decimals + 3}.{decimals}f}"
    if float(rem_txt) >= 100.0:  # rounding carried into the next station
        whole += 1
        rem_txt = f"{0.0:0{decimals + 3}.{decimals}f}"
    return f"{sign}{whole}+{rem_txt}"


def parse_station(text: str) -> float:
    """Parse '12+34.57' (or a plain number string) into feet."""
    t = text.strip()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    if "+" in t:
        whole, rem = t.split("+", 1)
        value = int(whole) * 100 + float(rem)
    else:
        value = float(t)
    return -value if neg else value


def lineweight_points(lineweight_mm: float) -> float:
    """Convert a plotted lineweight in millimeters to printer points."""
    return lineweight_mm * 72.0 / 25.4
