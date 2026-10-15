"""Anchor references: named design points on an alignment.

An anchor names a point *by its meaning* (``PC-1``, ``T-2``, ``18+00``) so a
label placed on it carries provenance the verifier can check.  Grammar
(case-insensitive, whitespace-tolerant; a single shlex token when written
without spaces)::

    anchor  := ref [ "@" offset ]
    ref     := "BEGIN" | "END" | ("PI"|"PC"|"PT"|"BC"|"EC"|"MC"|"T"|"EQ") "-" n | station
    station := int "+" number            ; display station "18+00" / "18+00.00"
            |  number                     ; display station in feet, e.g. "1800"
    offset  := signed number [ "L" | "R" ]  ; feet, right positive; "25L" == "-25"

Dict form: ``{"ref": "PC-1", "offset": 10}`` or
``{"station": 1800 | "18+00", "offset": 25.0, "region": 2}``.  A bare JSON
number is a display station.

Canonical ``ref`` strings are upper-case for named refs and formatted display
stations (``"18+00.00"``) for station refs.  ``BC-n`` and ``EC-n``, the names a
Caltrans plan letters (PPM 2-2.5), are read as ``PC-n`` and ``PT-n``: the same
point, so the canonical ref is ``PC-n`` / ``PT-n`` either way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from roaddraft.core.units import format_station, parse_station
from roaddraft.design.angles import right_normal
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment, CurveElement, TangentElement

GRAMMAR_HINT = ("anchor = BEGIN | END | PI-n | PC-n | PT-n | MC-n | T-n | EQ-n | '86+50.00' | 8650, "
                "optionally '@offset' (ft, right +; '25L' = 25 ft left), e.g. 'PC-2@18', '86+50@25L'; "
                "BC-n / EC-n are the same points as PC-n / PT-n; "
                "or {ref|station, offset, region}")

_NAMED_KINDS = {"PI": "pi", "PC": "pc", "PT": "pt", "BC": "pc", "EC": "pt", "MC": "mc",
                "T": "tangent", "EQ": "equation"}
#: Caltrans letters the beginning and end of a curve BC and EC; the design
#: model calls the same points PC and PT
_CANONICAL = {"BC": "PC", "EC": "PT"}
_NAMED_RE = re.compile(r"^(PI|PC|PT|BC|EC|MC|T|EQ)\s*-\s*(\d+)$")
_STATION_RE = re.compile(r"^(-?\d+)\s*\+\s*(\d+(?:\.\d*)?)$")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_OFFSET_RE = re.compile(r"^([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([LR])?$")


@dataclass
class AnchorRef:
    """A parsed, unresolved anchor."""

    ref: str  # canonical: "PC-1", "BEGIN", "18+00.00" (display text), ...
    kind_hint: str  # "begin"|"end"|"pi"|"pc"|"pt"|"mc"|"tangent"|"equation"|"station"
    index: Optional[int]  # for -n forms
    station_display: Optional[float]  # for station form
    offset: float = 0.0  # right +
    region: Optional[int] = None


@dataclass
class AnchorPoint:
    """A resolved anchor: where it is and what it belongs to."""

    alignment: str
    ref: str  # canonical
    kind_hint: str
    station: float  # raw
    station_text: str  # display, 2 decimals
    region: int
    offset: float
    on_point: List[float]  # centerline point (offset 0)
    point: List[float]  # including offset
    direction_deg: float  # heading ahead at the station (PI: heading of the back tangent)
    element_index: int  # 0-based into alignment.elements (PI: the curve's index)
    curve_index: Optional[int]  # 1-based, for pi/pc/pt/mc (and stations on a curve)
    tangent_index: Optional[int]  # 1-based, for T-n and station anchors on a tangent

    def to_record(self) -> dict:
        return {"alignment": self.alignment, "ref": self.ref,
                "station": float(self.station), "offset": float(self.offset)}


# ------------------------------------------------------------------ parse


def _cannot(value, why: Optional[str] = None) -> DesignError:
    msg = f"cannot parse anchor {value!r}" + (f": {why}" if why else "")
    return DesignError(msg, hint=GRAMMAR_HINT)


def _parse_offset(text: str, original) -> float:
    t = str(text).strip().upper()
    if not t:
        return 0.0
    m = _OFFSET_RE.match(t)
    if not m:
        raise _cannot(original, f"bad offset {text!r} (use 25, -25, 25L or 25R)")
    value = float(m.group(1))
    side = m.group(2)
    if side == "L":
        value = -abs(value)
    elif side == "R":
        value = abs(value)
    return value


def parse_offset(value) -> float:
    """``12`` / ``-12`` / ``"12L"`` / ``"12R"`` -> signed feet, right positive.

    The form a drafter says out loud ("twelve feet left") reaches the engine as
    ``"12L"``; a bare number is already signed.
    """
    if isinstance(value, bool):
        raise _cannot(value, "an offset is a number or a string like '15L'")
    if isinstance(value, (int, float)):
        return float(value)
    return _parse_offset(value, value)


def _parse_ref_text(text: str, original) -> AnchorRef:
    t = str(text).strip().upper()
    if not t:
        raise _cannot(original, "empty reference")
    if t == "BEGIN":
        return AnchorRef(ref="BEGIN", kind_hint="begin", index=None, station_display=None)
    if t == "END":
        return AnchorRef(ref="END", kind_hint="end", index=None, station_display=None)
    m = _NAMED_RE.match(t)
    if m:
        n = int(m.group(2))
        if n < 1:
            raise _cannot(original, "indices are 1-based")
        name = _CANONICAL.get(m.group(1), m.group(1))
        return AnchorRef(ref=f"{name}-{n}", kind_hint=_NAMED_KINDS[m.group(1)],
                         index=n, station_display=None)
    m = _STATION_RE.match(t)
    if m:
        disp = float(parse_station(f"{m.group(1)}+{m.group(2)}"))
        return AnchorRef(ref=format_station(disp), kind_hint="station", index=None,
                         station_display=disp)
    if _NUMBER_RE.match(t):
        disp = float(t)
        return AnchorRef(ref=format_station(disp), kind_hint="station", index=None,
                         station_display=disp)
    if re.match(r"^(PI|PC|PT|BC|EC|MC|T|EQ)\d+$", t):
        raise _cannot(original, "named anchors need a dash: PC-1, not PC1")
    raise _cannot(original)


def parse_anchor(value) -> AnchorRef:
    """Parse ``str | int | float | dict`` into an ``AnchorRef``."""
    if isinstance(value, bool):
        raise _cannot(value)
    if isinstance(value, (int, float)):
        disp = float(value)
        return AnchorRef(ref=format_station(disp), kind_hint="station", index=None,
                         station_display=disp)
    if isinstance(value, dict):
        allowed = {"ref", "station", "offset", "region"}
        unknown = set(value) - allowed
        if unknown:
            raise _cannot(value, f"unknown keys {sorted(unknown)}; allowed: ref, station, offset, region")
        if ("ref" in value) == ("station" in value):
            raise _cannot(value, "give exactly one of ref or station")
        if "ref" in value:
            if not isinstance(value["ref"], str):
                raise _cannot(value, "ref must be a string")
            ref = _parse_ref_text(value["ref"], value)
        else:
            sta = value["station"]
            if isinstance(sta, bool) or not isinstance(sta, (int, float, str)):
                raise _cannot(value, "station must be a number or '84+27.93'")
            ref = _parse_ref_text(str(sta), value)
            if ref.kind_hint != "station":
                raise _cannot(value, "station must be a number or '84+27.93'")
        off = value.get("offset", 0.0)
        if off is None:
            off = 0.0
        if isinstance(off, bool) or not isinstance(off, (int, float, str)):
            raise _cannot(value, "offset must be a number (or '25L'/'25R')")
        ref.offset = _parse_offset(str(off), value) if isinstance(off, str) else float(off)
        region = value.get("region")
        if region is not None:
            if isinstance(region, bool) or not isinstance(region, int) or region < 1:
                raise _cannot(value, "region must be a positive integer")
            if ref.kind_hint != "station":
                raise _cannot(value, "region applies to station anchors only")
            ref.region = int(region)
        return ref
    if isinstance(value, str):
        text = value.strip()
        if "@" in text:
            ref_txt, _, off_txt = text.partition("@")
            ref = _parse_ref_text(ref_txt, value)
            ref.offset = _parse_offset(off_txt, value)
            return ref
        return _parse_ref_text(text, value)
    raise _cannot(value)


_KIND_FROM_HINT = {"begin": "begin", "end": "end", "pi": "pi", "pc": "pc", "pt": "pt", "mc": "mc",
                   "tangent": "bearing", "equation": "equation", "station": "station"}


def infer_kind(ref: AnchorRef) -> str:
    """Default label kind for an anchor (``T-n`` -> bearing)."""
    return _KIND_FROM_HINT[ref.kind_hint]


# ---------------------------------------------------------------- resolve


def _valid_hint(alignment: Alignment) -> str:
    nc = len(alignment.curves())
    nt = len(alignment.tangents())
    ne = len(alignment.equations)
    st = alignment.stations()
    parts = ["BEGIN", "END"]
    if nc:
        parts += [f"PI-1..PI-{nc}", f"PC-1..PC-{nc}", f"PT-1..PT-{nc}", f"MC-1..MC-{nc}"]
    if nt:
        parts.append(f"T-1..T-{nt}")
    if ne:
        parts.append(f"EQ-1..EQ-{ne}")
    return ("valid: " + ", ".join(parts) +
            f", or a station within {st.begin_text()}..{st.end_text()}")


def _missing(alignment: Alignment, ref: AnchorRef, what: str, count: int, prefix: str) -> DesignError:
    names = ", ".join(f"{prefix}-{i}" for i in range(1, count + 1)) if count else "none"
    plural = what if count == 1 else what + "s"
    return DesignError(
        f"anchor '{ref.ref}' does not exist: {alignment.name} has {count} {plural} ({names})",
        hint=_valid_hint(alignment))


def resolve_anchor(alignment: Alignment, ref: AnchorRef) -> AnchorPoint:
    """Resolve an ``AnchorRef`` on ``alignment`` into an ``AnchorPoint``."""
    if isinstance(ref, (str, int, float, dict)):
        ref = parse_anchor(ref)
    st = alignment.stations()
    begin = float(alignment.begin_station)
    kind = ref.kind_hint
    elements = alignment.elements

    if kind == "pi":
        curves = alignment.curves()
        if ref.index is None or ref.index > len(curves):
            raise _missing(alignment, ref, "curve", len(curves), "PI")
        c = curves[ref.index - 1]
        idx = elements.index(c)
        raw = begin + c.start_dist + c.tangent_length
        direction = float(c.direction_in_deg)
        on_point = [float(c.pi[0]), float(c.pi[1])]
        rn = right_normal(direction)
        point = [on_point[0] + ref.offset * rn[0], on_point[1] + ref.offset * rn[1]]
        disp, region = st.to_display(raw)
        return AnchorPoint(alignment=alignment.name, ref=ref.ref, kind_hint=kind, station=raw,
                           station_text=format_station(disp), region=region,
                           offset=float(ref.offset), on_point=on_point, point=point,
                           direction_deg=direction, element_index=idx, curve_index=ref.index,
                           tangent_index=None)

    forced_index: Optional[int] = None
    if kind in ("pc", "pt", "mc"):
        curves = alignment.curves()
        if ref.index is None or ref.index > len(curves):
            raise _missing(alignment, ref, "curve", len(curves), kind.upper())
        c = curves[ref.index - 1]
        forced_index = elements.index(c)
        if kind == "pc":
            dist = c.start_dist
        elif kind == "pt":
            dist = c.end_dist
        else:
            dist = c.start_dist + c.length / 2.0
        raw = begin + dist
    elif kind == "tangent":
        tangents = alignment.tangents()
        if ref.index is None or ref.index > len(tangents):
            raise _missing(alignment, ref, "tangent", len(tangents), "T")
        t = tangents[ref.index - 1]
        forced_index = elements.index(t)
        raw = begin + t.start_dist + t.length / 2.0
    elif kind == "equation":
        eqs = alignment.equations
        if ref.index is None or ref.index > len(eqs):
            raise _missing(alignment, ref, "equation", len(eqs), "EQ")
        raw = float(eqs[ref.index - 1].raw_station)
    elif kind == "begin":
        raw = begin
    elif kind == "end":
        raw = begin + alignment.length
    elif kind == "station":
        raw = st.parse(ref.station_display, ref.region)
        st.require_in_range(raw, alignment.name)
    else:  # pragma: no cover - parse guarantees the set above
        raise DesignError(f"unknown anchor kind {kind!r}")

    on_point, direction, idx = alignment.station_to_xy(raw, 0.0)
    if ref.offset:
        point, _, _ = alignment.station_to_xy(raw, ref.offset)
    else:
        point = list(on_point)
    if forced_index is not None:
        idx = forced_index
    element = elements[idx]
    curve_index = alignment.curve_index(idx) if isinstance(element, CurveElement) else None
    tangent_index = alignment.tangent_index(idx) if isinstance(element, TangentElement) else None
    disp, region = st.to_display(raw)
    return AnchorPoint(alignment=alignment.name, ref=ref.ref, kind_hint=kind, station=raw,
                       station_text=format_station(disp), region=region, offset=float(ref.offset),
                       on_point=on_point, point=point, direction_deg=float(direction),
                       element_index=idx, curve_index=curve_index, tangent_index=tangent_index)


def resolve_record(alignment: Alignment, record: dict) -> AnchorPoint:
    """Resolve a stored anchor record (``{"ref", "station", "offset", ...}``).

    Named refs resolve by name; station refs use the recorded RAW station so
    an equation overlap can never make the lookup ambiguous."""
    offset = float(record.get("offset") or 0.0)
    ref = parse_anchor(record["ref"])
    ref.offset = offset
    if ref.kind_hint != "station" or record.get("station") is None:
        return resolve_anchor(alignment, ref)
    raw = float(record["station"])
    st = alignment.stations()
    st.require_in_range(raw, alignment.name)
    on_point, direction, idx = alignment.station_to_xy(raw, 0.0)
    point = alignment.station_to_xy(raw, offset)[0] if offset else list(on_point)
    element = alignment.elements[idx]
    disp, region = st.to_display(raw)
    return AnchorPoint(alignment=alignment.name, ref=format_station(disp), kind_hint="station",
                       station=raw, station_text=format_station(disp), region=region,
                       offset=offset, on_point=on_point, point=point,
                       direction_deg=float(direction), element_index=idx,
                       curve_index=(alignment.curve_index(idx)
                                    if isinstance(element, CurveElement) else None),
                       tangent_index=(alignment.tangent_index(idx)
                                      if isinstance(element, TangentElement) else None))


def list_anchors(alignment: Alignment) -> List[AnchorPoint]:
    """Every named anchor of an alignment (offset 0): BEGIN, END, PC/PI/PT/MC-n,
    T-n, EQ-n."""
    refs = ["BEGIN", "END"]
    for n in range(1, len(alignment.curves()) + 1):
        refs += [f"PC-{n}", f"PI-{n}", f"PT-{n}", f"MC-{n}"]
    refs += [f"T-{n}" for n in range(1, len(alignment.tangents()) + 1)]
    refs += [f"EQ-{n}" for n in range(1, len(alignment.equations) + 1)]
    return [resolve_anchor(alignment, parse_anchor(r)) for r in refs]


__all__ = ["AnchorRef", "AnchorPoint", "GRAMMAR_HINT", "parse_anchor", "parse_offset",
           "infer_kind", "resolve_anchor", "resolve_record", "list_anchors"]
