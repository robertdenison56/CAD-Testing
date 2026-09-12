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


LENGTH_FORMATS = ("feet", "feet_inches", "decimal")


def format_length(value: float, unit_format: str = "feet", precision: int = 2) -> str:
    """Format a measured length the way a drafter writes it.

    ``feet`` -> ``120.00'`` (the plan-view default), ``feet_inches`` ->
    ``12'-6"`` (structures and details; trailing zeros on the inches are
    trimmed, and 11.999 in carries into the next foot), ``decimal`` ->
    ``120.00`` with no unit mark, for sheet inches or a caller-supplied suffix.
    """
    if unit_format not in LENGTH_FORMATS:
        raise ValueError(f"unit_format must be one of {list(LENGTH_FORMATS)}, "
                         f"got {unit_format!r}")
    p = max(int(precision), 0)
    v = float(value)
    if unit_format == "decimal":
        return f"{v:.{p}f}"
    if unit_format == "feet":
        return f"{v:.{p}f}'"
    sign = "-" if v < 0 else ""
    v = abs(v)
    feet = int(v)
    inches = (v - feet) * 12.0
    text = f"{inches:.{p}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if not text:
        text = "0"
    if float(text) >= 12.0:  # rounding carried into the next foot
        feet += 1
        text = "0"
    if feet == 0 and text != "0":
        return f"{sign}{text}\""
    return f"{sign}{feet}'-{text}\""


def format_plot_scale(feet_per_inch: float) -> str:
    """``50 -> '1"=50\''`` (the annotation / viewport scale as drafters write it)."""
    return f"1\"={float(feet_per_inch):g}'"


def lineweight_points(lineweight_mm: float) -> float:
    """Convert a plotted lineweight in millimeters to printer points."""
    return lineweight_mm * 72.0 / 25.4


# ------------------------------------------------------------ length units

# Length units a document may declare in meta.model_units / meta.paper_units,
# as meters per unit. Reference attachments use these for MicroStation-style
# "true scale": a basefile drawn in meters lands in a US-survey-foot host at
# the right size.
UNIT_METERS = {
    "us_survey_ft": US_SURVEY_FOOT_METERS,
    "ft": 0.3048,
    "m": 1.0,
    "inch": 0.0254,
    "mm": 0.001,
}

UNIT_ALIASES = {
    "us_survey_foot": "us_survey_ft", "usft": "us_survey_ft",
    "survey_ft": "us_survey_ft", "sft": "us_survey_ft",
    "feet": "ft", "foot": "ft", "international_ft": "ft", "ift": "ft",
    "meter": "m", "meters": "m", "metre": "m", "metres": "m",
    "in": "inch", "inches": "inch",
    "millimeter": "mm", "millimetre": "mm", "millimeters": "mm",
}


def normalize_unit(name):
    """Canonical unit key for a declared unit name, or None if unknown."""
    if not isinstance(name, str):
        return None
    key = name.strip().lower()
    key = UNIT_ALIASES.get(key, key)
    return key if key in UNIT_METERS else None


def unit_factor(from_unit: str, to_unit: str) -> float:
    """Multiplier that expresses a length in from_unit as a length in to_unit.
    Raises ValueError for a unit the table does not know."""
    a = normalize_unit(from_unit)
    b = normalize_unit(to_unit)
    if a is None:
        raise ValueError(f"unknown unit {from_unit!r}; known units: "
                         f"{sorted(UNIT_METERS)}")
    if b is None:
        raise ValueError(f"unknown unit {to_unit!r}; known units: "
                         f"{sorted(UNIT_METERS)}")
    return UNIT_METERS[a] / UNIT_METERS[b]
