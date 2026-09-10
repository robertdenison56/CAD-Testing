"""LandXML 1.2 import/export of alignments and profiles (stdlib ElementTree).

Mapping (spec section 6): ``Alignment/CoordGeom`` ``Line`` and ``Curve``
elements become tangent/curve elements (spirals are rejected), ``StaEquation``
becomes a station equation, ``Profile/ProfAlign`` ``PVI``/``ParaCurve``
become PVIs with symmetric vertical curves.  Points are written
``"northing easting"`` (y then x).  Output is byte-stable: fixed date/time
literals and six-decimal numbers, so ``write(parse(write(x))) == write(x)``.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from roaddraft.core import geometry as geo
from roaddraft.core.units import US_SURVEY_FOOT_METERS
from roaddraft.design.angles import direction_of, direction_to_azimuth, left_normal, right_normal
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (
    Alignment, CurveElement, TangentElement, alignment_from_elements, curve_data,
    elements_from_dicts,
)
from roaddraft.design.stations import StationEquation, build_equations
from roaddraft.design.vertical import PVI, Profile

LANDXML_NS = "http://www.landxml.org/schema/LandXML-1.2"
UNIT_FACTORS = {
    "USSurveyFoot": 1.0,
    "foot": 0.3048 / US_SURVEY_FOOT_METERS,  # 0.999998 US survey ft per international ft
    "meter": 1.0 / US_SURVEY_FOOT_METERS,  # 3.280833333
}
_META_TAGS = ("Units", "Application", "Project", "CoordinateSystem", "FeatureDictionary")


class LandXMLError(Exception):
    def __init__(self, message: str, hint: Optional[str] = None):
        super().__init__(message)
        self.hint = hint


@dataclass
class LandXMLData:
    alignments: List[Alignment]
    profiles: List[Profile]
    linear_unit: str
    to_us_ft: float
    warnings: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)


# ------------------------------------------------------------------ read


def _strip(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _child(el, name: str):
    for c in el:
        if _strip(c.tag) == name:
            return c
    return None


def _children(el, name: str) -> list:
    return [c for c in el if _strip(c.tag) == name]


def _num(text, what: str) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        raise LandXMLError(f"{what}: expected a number, got {text!r}")


def _point(el, what: str, factor: float) -> List[float]:
    """LandXML point text ``"northing easting"`` -> ``[x, y]`` in US survey feet."""
    if el is None or not (el.text or "").strip():
        raise LandXMLError(f"{what} is missing")
    parts = el.text.split()
    if len(parts) < 2:
        raise LandXMLError(f"{what}: expected 'northing easting', got {el.text!r}")
    n, e = _num(parts[0], what), _num(parts[1], what)
    return [e * factor, n * factor]


def _pair(el, what: str, factor: float) -> Tuple[float, float]:
    """PVI text ``"station elevation"`` -> ``(station, elevation)`` scaled."""
    if el is None or not (el.text or "").strip():
        raise LandXMLError(f"{what} is missing")
    parts = el.text.split()
    if len(parts) < 2:
        raise LandXMLError(f"{what}: expected 'station elevation', got {el.text!r}")
    return _num(parts[0], what) * factor, _num(parts[1], what) * factor


def _unique(name: str, taken: Dict[str, int], warnings: List[str], what: str) -> str:
    if name not in taken:
        taken[name] = 1
        return name
    n = taken[name] + 1
    while f"{name}-{n}" in taken:
        n += 1
    taken[name] = n
    taken[f"{name}-{n}"] = 1
    warnings.append(f"{what} {name!r} appears more than once; renamed to {name}-{n}")
    return f"{name}-{n}"


def _parse_units(root, warnings: List[str]) -> Tuple[str, float]:
    units = _child(root, "Units")
    if units is None:
        warnings.append("no Units element; assuming USSurveyFoot")
        return "USSurveyFoot", 1.0
    system = next(iter(list(units)), None)
    if system is None:
        warnings.append("empty Units element; assuming USSurveyFoot")
        return "USSurveyFoot", 1.0
    lu = system.get("linearUnit")
    if lu not in UNIT_FACTORS:
        raise LandXMLError(f"unsupported linearUnit {lu!r}; supported: USSurveyFoot, foot, meter")
    return lu, UNIT_FACTORS[lu]


def _curve_item(el, name: str, i: int, factor: float) -> dict:
    what = f"alignment {name!r} element {i} (Curve)"
    rot = el.get("rot")
    if rot not in ("ccw", "cw"):
        raise LandXMLError(f"{what}: rot must be 'ccw' or 'cw', got {rot!r}")
    direction = "L" if rot == "ccw" else "R"
    start = _point(_child(el, "Start"), f"{what} Start", factor)
    end = _point(_child(el, "End"), f"{what} End", factor)
    radius = el.get("radius")
    radius = _num(radius, f"{what} radius") * factor if radius is not None else None
    center_el = _child(el, "Center")
    if center_el is not None:
        center = _point(center_el, f"{what} Center", factor)
        if radius is None:
            radius = geo.distance(start, center)
    else:
        if radius is None:
            raise LandXMLError(f"{what}: needs a radius or a Center")
        chord = geo.distance(start, end)
        half = chord / 2.0
        if half > radius + 1e-9:
            raise LandXMLError(f"{what}: chord {chord:.3f} is longer than the diameter "
                               f"{2 * radius:.3f}")
        h = math.sqrt(max(radius * radius - half * half, 0.0))
        d = direction_of(start, end)
        normal = left_normal(d) if direction == "L" else right_normal(d)
        mid = [(start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0]
        center = [mid[0] + h * normal[0], mid[1] + h * normal[1]]
    item = {"kind": "curve", "pc": start, "pt": end, "center": center, "direction": direction,
            "radius": radius}
    pi_el = _child(el, "PI")
    if pi_el is not None:
        item["pi"] = _point(pi_el, f"{what} PI", factor)
    return item


def _parse_alignment(a, index: int, factor: float, warnings: List[str], skipped: List[str],
                     taken: Dict[str, int]) -> Tuple[Alignment, list]:
    raw_name = a.get("name") or f"ALIGN-{index}"
    name = _unique(raw_name, taken, warnings, "alignment")
    desc = a.get("desc") or ""
    sta_start = _num(a.get("staStart", 0.0), f"alignment {name!r} staStart") * factor
    cg = _child(a, "CoordGeom")
    if cg is None or not len(list(cg)):
        raise LandXMLError(f"alignment {name!r} has no CoordGeom geometry")
    items = []
    for i, el in enumerate(list(cg), start=1):
        tag = _strip(el.tag)
        if tag == "Line":
            what = f"alignment {name!r} element {i} (Line)"
            items.append({"kind": "tangent",
                          "start": _point(_child(el, "Start"), f"{what} Start", factor),
                          "end": _point(_child(el, "End"), f"{what} End", factor)})
        elif tag == "Curve":
            items.append(_curve_item(el, name, i, factor))
        elif tag == "Spiral":
            raise LandXMLError(
                f"alignment {name!r} contains a Spiral element; spirals are not supported "
                f"in this version",
                hint="replace the spiral upstream or import a different alignment")
        elif tag in ("IrregularLine", "Chain"):
            raise LandXMLError(
                f"alignment {name!r} contains a {tag} element; only Line and Curve "
                f"CoordGeom elements are supported")
        else:
            raise LandXMLError(f"alignment {name!r}: unknown CoordGeom element <{tag}>")
    try:
        elements = elements_from_dicts(items)
    except DesignError as e:
        raise LandXMLError(f"alignment {name!r}: {e}", hint=e.hint)
    length = sum(el.length for el in elements)
    if a.get("length") is not None:
        file_len = _num(a.get("length"), f"alignment {name!r} length") * factor
        if abs(file_len - length) > 0.01:
            warnings.append(f"Alignment {name} length {file_len:.2f} in file vs "
                            f"{length:.2f} computed")
    eq_items = []
    for eq in _children(a, "StaEquation"):
        what = f"alignment {name!r} StaEquation"
        if eq.get("staBack") is None or eq.get("staAhead") is None:
            raise LandXMLError(f"{what}: staBack and staAhead are required")
        item = {"back": _num(eq.get("staBack"), what) * factor,
                "ahead": _num(eq.get("staAhead"), what) * factor}
        if eq.get("staInternal") is not None:
            item["raw_station"] = _num(eq.get("staInternal"), what) * factor
        eq_items.append(item)
    try:
        equations = build_equations(sta_start, length, eq_items)
        align = alignment_from_elements(name, elements, begin_station=sta_start,
                                        equations=equations, description=desc)
    except DesignError as e:
        raise LandXMLError(f"alignment {name!r}: {e}", hint=e.hint)
    for child in a:
        tag = _strip(child.tag)
        if tag in ("CoordGeom", "StaEquation", "Profile") or tag in skipped:
            continue
        skipped.append(tag)
    return align, _children(a, "Profile")


def _parse_profiles(profile_els: list, alignment_name: str, factor: float,
                    warnings: List[str], skipped: List[str],
                    taken: Dict[str, int]) -> List[Profile]:
    out: List[Profile] = []
    for prof in profile_els:
        prof_aligns = _children(prof, "ProfAlign")
        for child in prof:
            tag = _strip(child.tag)
            if tag != "ProfAlign" and tag not in skipped:
                skipped.append(tag)
        for pa in prof_aligns:
            raw_name = pa.get("name") or prof.get("name") or f"{alignment_name}-PROF"
            name = _unique(raw_name, taken, warnings, "profile")
            pvis: List[PVI] = []
            for i, el in enumerate(list(pa), start=1):
                tag = _strip(el.tag)
                what = f"profile {name!r} PVI {i}"
                if tag == "PVI":
                    sta, elev = _pair(el, what, factor)
                    pvis.append(PVI(station=sta, elevation=elev, length=0.0))
                elif tag == "ParaCurve":
                    sta, elev = _pair(el, what, factor)
                    length = _num(el.get("length", 0.0), f"{what} length") * factor
                    pvis.append(PVI(station=sta, elevation=elev, length=length))
                elif tag in ("UnsymParaCurve", "CircCurve"):
                    raise LandXMLError(
                        f"profile {name!r}: unsymmetrical/circular vertical curves are not "
                        f"supported in this version")
                else:
                    raise LandXMLError(f"profile {name!r}: unknown ProfAlign element <{tag}>")
            profile = Profile(name=name, alignment=alignment_name, pvis=pvis,
                              description=pa.get("desc") or prof.get("desc") or "")
            try:
                profile.validate()
            except DesignError as e:
                raise LandXMLError(f"profile {name!r}: {e}", hint=e.hint)
            out.append(profile)
    return out


def parse_landxml(text: str) -> LandXMLData:
    """Parse LandXML 1.2 text into alignments and profiles (US survey feet)."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        line, col = getattr(e, "position", (0, 0)) or (0, 0)
        raise LandXMLError(f"LandXML parse error at line {line} column {col}: {e}")
    if _strip(root.tag) != "LandXML":
        raise LandXMLError(f"root element is <{_strip(root.tag)}>, not <LandXML>")
    warnings: List[str] = []
    skipped: List[str] = []
    unit, factor = _parse_units(root, warnings)
    alignments: List[Alignment] = []
    profiles: List[Profile] = []
    align_taken: Dict[str, int] = {}
    prof_taken: Dict[str, int] = {}
    top_profiles = []
    for child in root:
        tag = _strip(child.tag)
        if tag == "Alignments":
            for i, a in enumerate(_children(child, "Alignment"), start=1):
                align, prof_els = _parse_alignment(a, i, factor, warnings, skipped, align_taken)
                alignments.append(align)
                profiles.extend(_parse_profiles(prof_els, align.name, factor, warnings, skipped,
                                                prof_taken))
        elif tag == "Profiles":
            top_profiles.extend(_children(child, "Profile"))
        elif tag == "Profile":
            top_profiles.append(child)
        elif tag in _META_TAGS:
            continue
        elif tag not in skipped:
            skipped.append(tag)
    names = [a.name for a in alignments]
    for prof in top_profiles:
        target = prof.get("alignRef") or prof.get("alignmentRef") or prof.get("alignment")
        if target is None and prof.get("name") in names:
            target = prof.get("name")
        if target is None and len(names) == 1:
            target = names[0]
            warnings.append(f"top-level Profile {prof.get('name')!r} bound to the only "
                            f"alignment {target!r}")
        if target not in names:
            warnings.append(f"top-level Profile {prof.get('name')!r} skipped: no alignment "
                            f"reference")
            continue
        profiles.extend(_parse_profiles([prof], target, factor, warnings, skipped, prof_taken))
    return LandXMLData(alignments=alignments, profiles=profiles, linear_unit=unit,
                       to_us_ft=factor, warnings=warnings, skipped=skipped)


# ----------------------------------------------------------------- write


def _f(v: float) -> str:
    return f"{float(v):.6f}"


def _p(pt) -> str:
    return f"{float(pt[1]):.6f} {float(pt[0]):.6f}"


def _attr(v: str) -> str:
    return escape(str(v), {'"': "&quot;"})


def _write_alignment(align: Alignment, profiles: List[Profile]) -> List[str]:
    out = [f'    <Alignment name="{_attr(align.name)}" desc="{_attr(align.description)}" '
           f'staStart="{_f(align.begin_station)}" length="{_f(align.length)}">',
           "      <CoordGeom>"]
    for i, el in enumerate(align.elements):
        if isinstance(el, TangentElement):
            out.append(f'        <Line dir="{_f(direction_to_azimuth(el.direction_deg))}" '
                       f'length="{_f(el.length)}"><Start>{_p(el.start)}</Start>'
                       f'<End>{_p(el.end)}</End></Line>')
        elif isinstance(el, CurveElement):
            n = align.curve_index(i)
            row = curve_data(align, n)
            out.append(
                f'        <Curve rot="{"ccw" if el.direction == "L" else "cw"}" '
                f'radius="{_f(el.radius)}" length="{_f(el.length)}" chord="{_f(row["chord"])}" '
                f'delta="{_f(el.delta_deg)}" dirStart="{_f(row["azimuth_in_deg"])}" '
                f'dirEnd="{_f(row["azimuth_out_deg"])}" tangent="{_f(row["tangent"])}" '
                f'external="{_f(row["external"])}" midOrd="{_f(row["mid_ordinate"])}">')
            out.append(f'          <Start>{_p(el.pc)}</Start><Center>{_p(el.center)}</Center>'
                       f'<End>{_p(el.pt)}</End><PI>{_p(el.pi)}</PI></Curve>')
        else:  # pragma: no cover - spirals never exist in this version
            raise LandXMLError(f"cannot write element kind {getattr(el, 'kind', '?')!r}")
    out.append("      </CoordGeom>")
    for eq in align.equations:
        out.append(f'      <StaEquation staAhead="{_f(eq.ahead)}" staBack="{_f(eq.back)}" '
                   f'staInternal="{_f(eq.raw_station)}"/>')
    if profiles:
        out.append(f'      <Profile name="{_attr(align.name)}">')
        for prof in profiles:
            out.append(f'        <ProfAlign name="{_attr(prof.name)}" '
                       f'desc="{_attr(prof.description)}">')
            for pvi in prof.pvis:
                if pvi.length > 0:
                    out.append(f'          <ParaCurve length="{_f(pvi.length)}">'
                               f'{_f(pvi.station)} {_f(pvi.elevation)}</ParaCurve>')
                else:
                    out.append(f'          <PVI>{_f(pvi.station)} {_f(pvi.elevation)}</PVI>')
            out.append("        </ProfAlign>")
        out.append("      </Profile>")
    out.append("    </Alignment>")
    return out


def write_landxml(alignments: List[Alignment], profiles: List[Profile], project_name: str = "",
                  application_version: str = "0.2") -> str:
    """Serialize alignments (+ their profiles) as LandXML 1.2 text."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<LandXML xmlns="{LANDXML_NS}" version="1.2" date="2026-01-01" time="00:00:00" '
        f'language="English" readOnly="false">',
        '  <Units><Imperial linearUnit="USSurveyFoot" areaUnit="squareFoot" '
        'volumeUnit="cubicYard" temperatureUnit="fahrenheit" pressureUnit="inchHG" '
        'angularUnit="decimal degrees" directionUnit="decimal degrees"/></Units>',
        f'  <Application name="RoadDraft" version="{_attr(application_version)}"/>',
        f'  <Project name="{_attr(project_name)}"/>',
        "  <Alignments>",
    ]
    for align in alignments:
        bound = [p for p in profiles if p.alignment == align.name]
        lines.extend(_write_alignment(align, bound))
    lines.append("  </Alignments>")
    lines.append("</LandXML>")
    return "\n".join(lines) + "\n"


__all__ = ["LANDXML_NS", "UNIT_FACTORS", "LandXMLError", "LandXMLData", "parse_landxml",
           "write_landxml"]
