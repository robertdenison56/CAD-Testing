"""Label placement and wording: one shared module for commands and ground truth.

``compile_label`` turns an anchor + label kind into a fully specified text
placement (content, position, rotation, alignment) in model space;
``sheet_pose`` maps it through a viewport; ``stationing_plan`` produces the
tick/label plan an alignment-mode ``annotate_stationing`` materialises; and
``curve_table_rows`` builds the curve data table.  Because the task
generator's ground truth calls these same functions, the reference solution
matches the truth exactly.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from roaddraft.core.units import format_station
from roaddraft.design.anchors import AnchorPoint
from roaddraft.design.angles import direction_to_azimuth, format_bearing
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (
    Alignment, CurveElement, TangentElement, curve_data, junction_kind,
)
from roaddraft.design.stations import STATION_EPS, equation_label

LABEL_KINDS = ("station", "pc", "pt", "pi", "mc", "pcc", "prc", "bearing", "begin", "end",
               "equation", "curve_data", "custom")
ROTATION_MODES = ("along", "perpendicular", "horizontal")
SIDES = ("left", "right")
DEFAULT_SIDE = {"station": "left", "bearing": "left", "begin": "left", "end": "left",
                "pc": "right", "pt": "right", "pi": "right", "mc": "right", "pcc": "right",
                "prc": "right", "equation": "right", "curve_data": "right", "custom": "left"}
DEFAULT_VALIGN = {"left": "bottom", "right": "top"}
MODEL_LABEL_OFFSET = 16.0
MODEL_TEXT_HEIGHT = 8.0
MODEL_TICK_HALF = 10.0
SHEET_LABEL_OFFSET = 0.32
SHEET_TEXT_HEIGHT = 0.10


@dataclass
class LabelSpec:
    """A fully placed label in model space."""

    kind: str
    alignment: str
    ref: str
    station: float
    offset: float
    region: int
    anchor_point: List[float]
    direction_deg: float
    side: str
    label_offset: float
    rotation: str
    content: str
    content_auto: bool
    position: List[float]  # model space, after side offset
    rotation_deg: float  # model space, uprighted
    halign: str
    valign: str

    def anchor_record(self, viewport: Optional[str] = None) -> dict:
        """The anchor record stored on the entity (spec section 2.7)."""
        return {"alignment": self.alignment, "ref": self.ref, "kind": self.kind,
                "station": float(self.station), "offset": float(self.offset),
                "side": self.side, "label_offset": float(self.label_offset),
                "rotation": self.rotation, "viewport": viewport,
                "content_auto": bool(self.content_auto)}


@dataclass
class TickSpec:
    """A station tick across the centerline."""

    station: float
    station_text: str
    region: int
    point: List[float]
    direction_deg: float
    start: List[float]
    end: List[float]

    def anchor_record(self, alignment: str) -> dict:
        return {"alignment": alignment, "ref": self.station_text, "kind": "tick",
                "station": float(self.station), "offset": 0.0}


@dataclass
class StationingPlan:
    """Ticks and labels in creation order (ticks/labels interleaved, then
    junction labels, then equation labels)."""

    items: List[object]
    n_ticks: int
    n_junctions: int
    n_equations: int
    begin_text: str
    end_text: str

    def ticks(self) -> List[TickSpec]:
        return [i for i in self.items if isinstance(i, TickSpec)]

    def labels(self) -> List[LabelSpec]:
        return [i for i in self.items if isinstance(i, LabelSpec)]


# ------------------------------------------------------------ primitives


def upright(angle_deg: float) -> float:
    """Fold a rotation into (-90, 90] so text never reads upside down
    (identical to the stationing engine's ``_upright``)."""
    a = angle_deg % 360.0
    if 90.0 < a <= 270.0:
        a -= 180.0
    return ((a + 180.0) % 360.0) - 180.0


def offset_point(p: Sequence[float], angle_deg: float, dist: float) -> List[float]:
    a = math.radians(angle_deg)
    return [p[0] + dist * math.cos(a), p[1] + dist * math.sin(a)]


# --------------------------------------------------------------- content


def _index_of(ref: str) -> int:
    try:
        return int(ref.split("-", 1)[1])
    except (IndexError, ValueError):
        raise DesignError(f"anchor {ref!r} carries no index")


def label_content(alignment: Alignment, ap: AnchorPoint, kind: str) -> str:
    """Auto-generated wording for ``kind`` at anchor ``ap`` (spec section 3.6)."""
    st = alignment.stations()
    if kind == "station":
        return st.format(ap.station)
    if kind in ("pc", "pt", "pi", "pcc", "prc"):
        return f"{kind.upper()} {st.format(ap.station)}"
    if kind == "mc":
        return f"C-{ap.curve_index}"
    if kind == "bearing":
        el = alignment.elements[ap.element_index]
        if not isinstance(el, TangentElement):
            raise DesignError(_bearing_message(alignment, ap))
        return format_bearing(direction_to_azimuth(el.direction_deg))
    if kind == "begin":
        return f"BEGIN STA {st.begin_text()}"
    if kind == "end":
        return f"END STA {st.end_text()}"
    if kind == "equation":
        n = _index_of(ap.ref)
        if n < 1 or n > len(alignment.equations):
            raise DesignError(f"{alignment.name} has no equation {ap.ref}")
        return equation_label(alignment.equations[n - 1])
    if kind == "curve_data":
        row = curve_data(alignment, int(ap.curve_index))
        return (f"C-{ap.curve_index}\nΔ = {row['delta_dms']}\nR = {row['radius']:.2f}'\n"
                f"T = {row['tangent']:.2f}'\nL = {row['length']:.2f}'")
    if kind == "custom":
        raise DesignError("kind custom requires content")
    raise DesignError(f"unknown label kind {kind!r}; kinds: {', '.join(LABEL_KINDS)}")


def _bearing_message(alignment: Alignment, ap: AnchorPoint) -> str:
    el = alignment.elements[ap.element_index]
    where = (f"is on curve C-{ap.curve_index}" if isinstance(el, CurveElement)
             else "is not on a tangent")
    nt = len(alignment.tangents())
    options = " or ".join(f"T-{n}" for n in range(1, nt + 1)) if nt <= 2 else f"T-1..T-{nt}"
    return f"bearing labels go on tangents; {ap.ref} {where} (use {options})"


def _check_kind_anchor(alignment: Alignment, ap: AnchorPoint, kind: str) -> None:
    hint = ap.kind_hint
    needs = {"pc": "pc", "pt": "pt", "pi": "pi", "mc": "mc", "equation": "equation",
             "begin": "begin", "end": "end"}
    names = {"pc": "PC-n", "pt": "PT-n", "pi": "PI-n", "mc": "MC-n", "equation": "EQ-n",
             "begin": "BEGIN", "end": "END"}
    if kind in needs:
        if hint != needs[kind]:
            raise DesignError(f"kind {kind} requires a {names[kind]} anchor, not {ap.ref}",
                              hint=f"omit kind to infer it from the anchor ({ap.ref} -> "
                                   f"{_KIND_OF_HINT.get(hint, hint)})")
        return
    if kind == "curve_data":
        if hint not in ("mc", "pi"):
            raise DesignError(f"kind curve_data requires an MC-n or PI-n anchor, not {ap.ref}")
        return
    if kind == "bearing":
        el = alignment.elements[ap.element_index]
        if not isinstance(el, TangentElement):
            raise DesignError(_bearing_message(alignment, ap))
        return
    if kind in ("pcc", "prc"):
        if hint != "pc":
            raise DesignError(f"kind {kind} requires the PC-n anchor of the ahead curve, not {ap.ref}")
        jk = junction_kind(alignment, ap.element_index - 1)
        if jk != kind:
            raise DesignError(
                f"kind {kind} requires a PC-n at a curve-to-curve junction; {ap.ref} is a "
                f"{jk or 'begin'} junction")
        return
    if kind in ("station", "custom"):
        return
    raise DesignError(f"unknown label kind {kind!r}; kinds: {', '.join(LABEL_KINDS)}")


_KIND_OF_HINT = {"begin": "begin", "end": "end", "pi": "pi", "pc": "pc", "pt": "pt", "mc": "mc",
                 "tangent": "bearing", "equation": "equation", "station": "station"}


# ---------------------------------------------------------------- compile


def compile_label(alignment: Alignment, ap: AnchorPoint, kind: str, side: Optional[str] = None,
                  label_offset: Optional[float] = None, rotation: str = "along",
                  content: Optional[str] = None, halign: Optional[str] = None,
                  valign: Optional[str] = None) -> LabelSpec:
    """Place a label of ``kind`` at anchor ``ap`` in model space."""
    if kind not in LABEL_KINDS:
        raise DesignError(f"unknown label kind {kind!r}; kinds: {', '.join(LABEL_KINDS)}")
    _check_kind_anchor(alignment, ap, kind)
    if kind == "custom" and content is None:
        raise DesignError("kind custom requires content")
    if rotation not in ROTATION_MODES:
        raise DesignError(f"rotation must be one of {list(ROTATION_MODES)}, not {rotation!r}")
    side = side or DEFAULT_SIDE[kind]
    if side not in SIDES:
        raise DesignError(f"side must be 'left' or 'right', not {side!r}")
    content_auto = content is None
    text = label_content(alignment, ap, kind) if content_auto else str(content)
    off = MODEL_LABEL_OFFSET if label_offset is None else float(label_offset)
    if off < 0:
        raise DesignError("label_offset must be >= 0")
    direction = float(ap.direction_deg)
    position = offset_point(ap.point, direction + (90.0 if side == "left" else -90.0), off)
    if rotation == "along":
        rot = upright(direction)
    elif rotation == "perpendicular":
        rot = upright(direction + 90.0)
    else:
        rot = 0.0
    return LabelSpec(kind=kind, alignment=alignment.name, ref=ap.ref, station=float(ap.station),
                     offset=float(ap.offset), region=int(ap.region),
                     anchor_point=[float(ap.point[0]), float(ap.point[1])],
                     direction_deg=direction, side=side, label_offset=off, rotation=rotation,
                     content=text, content_auto=content_auto, position=position,
                     rotation_deg=rot, halign=halign or "center",
                     valign=valign or DEFAULT_VALIGN[side])


def sheet_pose(spec: LabelSpec, transform, viewport_rotation_deg: float,
               label_offset_in: float) -> Tuple[List[float], float]:
    """``(position_in, rotation_deg)`` of a label on a sheet through a viewport."""
    q = transform.to_paper(spec.anchor_point)
    twist = float(viewport_rotation_deg)
    ang = spec.direction_deg + twist + (90.0 if spec.side == "left" else -90.0)
    position = offset_point(q, ang, float(label_offset_in))
    if spec.rotation == "along":
        rot = upright(spec.direction_deg + twist)
    elif spec.rotation == "perpendicular":
        rot = upright(spec.direction_deg + twist + 90.0)
    else:
        rot = 0.0
    return position, rot


# ------------------------------------------------------------- stationing


def stationing_plan(alignment: Alignment, interval: float = 100.0, tick_half: float = 10.0,
                    label_offset: float = 16.0, include_pc_pt: bool = True,
                    include_equations: bool = True,
                    station_range: Optional[Tuple[float, float]] = None) -> StationingPlan:
    """Ticks + labels for every interval station (per region), PC/PT/PCC/PRC
    labels, and equation labels.  ``station_range`` is in RAW stations."""
    if interval <= 0:
        raise DesignError("interval must be > 0")
    st = alignment.stations()
    begin = float(alignment.begin_station)
    length = alignment.length
    lo = hi = None
    if station_range is not None:
        lo, hi = float(station_range[0]), float(station_range[1])
        if hi < lo:
            lo, hi = hi, lo

    def in_range(raw: float) -> bool:
        return lo is None or (lo - STATION_EPS <= raw <= hi + STATION_EPS)

    def at(raw: float):
        dist = min(max(raw - begin, 0.0), length)
        return alignment.point_at(dist), alignment.direction_at(dist)

    items: List[object] = []
    regions = st.regions()
    n_ticks = 0
    for region in regions:
        last = region.index == len(regions)
        sd = math.ceil((region.display_start - 1e-9) / interval) * interval
        while (sd <= region.display_end + 1e-6) if last else (sd < region.display_end - 1e-6):
            raw = sd - region.shift
            if in_range(raw):
                pt, direction = at(raw)
                text = format_station(sd)
                items.append(TickSpec(station=raw, station_text=text, region=region.index,
                                      point=pt, direction_deg=direction,
                                      start=offset_point(pt, direction + 90.0, -tick_half),
                                      end=offset_point(pt, direction + 90.0, tick_half)))
                items.append(LabelSpec(
                    kind="station", alignment=alignment.name, ref=text, station=raw, offset=0.0,
                    region=region.index, anchor_point=list(pt), direction_deg=direction,
                    side="left", label_offset=float(label_offset), rotation="along",
                    content=text, content_auto=True,
                    position=offset_point(pt, direction + 90.0, label_offset),
                    rotation_deg=upright(direction), halign="center", valign="bottom"))
                n_ticks += 1
            sd += interval

    n_junctions = 0
    if include_pc_pt:
        for i in range(len(alignment.elements) - 1):
            jk = junction_kind(alignment, i)
            if jk is None:
                continue
            raw = begin + alignment.elements[i].end_dist
            if not in_range(raw):
                continue
            pt, direction = at(raw)
            if jk == "pt":
                ref = f"PT-{alignment.curve_index(i)}"
            else:
                ref = f"PC-{alignment.curve_index(i + 1)}"
            disp, region = st.to_display(raw)
            items.append(LabelSpec(
                kind=jk, alignment=alignment.name, ref=ref, station=raw, offset=0.0,
                region=region, anchor_point=list(pt), direction_deg=direction, side="right",
                label_offset=float(label_offset), rotation="along",
                content=f"{jk.upper()} {st.format(raw)}", content_auto=True,
                position=offset_point(pt, direction - 90.0, label_offset),
                rotation_deg=upright(direction), halign="center", valign="top"))
            n_junctions += 1

    n_equations = 0
    if include_equations:
        for n, eq in enumerate(alignment.equations, start=1):
            raw = float(eq.raw_station)
            if not in_range(raw):
                continue
            pt, direction = at(raw)
            off = 1.5 * float(label_offset)
            disp, region = st.to_display(raw)
            items.append(LabelSpec(
                kind="equation", alignment=alignment.name, ref=f"EQ-{n}", station=raw, offset=0.0,
                region=region, anchor_point=list(pt), direction_deg=direction, side="right",
                label_offset=off, rotation="along", content=equation_label(eq),
                content_auto=True, position=offset_point(pt, direction - 90.0, off),
                rotation_deg=upright(direction), halign="center", valign="top"))
            n_equations += 1

    return StationingPlan(items=items, n_ticks=n_ticks, n_junctions=n_junctions,
                          n_equations=n_equations, begin_text=st.begin_text(),
                          end_text=st.end_text())


# ------------------------------------------------------------ curve table

CURVE_COLUMNS = OrderedDict([
    ("curve", ("CURVE", 0.8)),
    ("pi_sta", ("PI STA", 1.1)),
    ("pc_sta", ("PC STA", 1.1)),
    ("pt_sta", ("PT STA", 1.1)),
    ("delta", ("DELTA", 1.3)),
    ("direction", ("DIR", 0.6)),
    ("radius", ("R", 1.0)),
    ("tangent", ("T", 1.0)),
    ("length", ("L", 1.0)),
    ("external", ("E", 0.9)),
    ("mid_ordinate", ("M", 0.9)),
    ("chord", ("C", 1.0)),
    ("chord_bearing", ("CH BRG", 1.6)),
])
DEFAULT_CURVE_COLUMNS = ["curve", "pi_sta", "delta", "direction", "radius", "tangent", "length",
                         "chord", "chord_bearing"]


def _cell(row: dict, key: str, decimals: int) -> str:
    if key == "curve":
        return row["ref"]
    if key == "pi_sta":
        return row["pi_station_text"]
    if key == "pc_sta":
        return row["pc_station_text"]
    if key == "pt_sta":
        return row["pt_station_text"]
    if key == "delta":
        return row["delta_dms"]
    if key == "direction":
        return "LT" if row["direction"] == "L" else "RT"
    if key == "chord_bearing":
        return row["chord_bearing"]
    value = row[{"radius": "radius", "tangent": "tangent", "length": "length",
                 "external": "external", "mid_ordinate": "mid_ordinate", "chord": "chord"}[key]]
    return f"{value:.{decimals}f}'"


def curve_table_rows(alignment: Alignment, columns: Optional[Sequence[str]] = None,
                     curves: Optional[Sequence[int]] = None, decimals: int = 2,
                     dms_decimals: int = 0) -> Tuple[List[str], List[List[str]], List[float]]:
    """``(headers, rows, widths_in)`` for a curve data table."""
    keys = list(columns) if columns else list(DEFAULT_CURVE_COLUMNS)
    if not keys:
        raise DesignError("curve table needs at least one column")
    for key in keys:
        if key not in CURVE_COLUMNS:
            raise DesignError(f"unknown curve table column {key!r}",
                              hint=f"columns: {', '.join(CURVE_COLUMNS)}")
    n_curves = len(alignment.curves())
    indices = list(curves) if curves else list(range(1, n_curves + 1))
    headers = [CURVE_COLUMNS[k][0] for k in keys]
    widths = [float(CURVE_COLUMNS[k][1]) for k in keys]
    rows: List[List[str]] = []
    for n in indices:
        row = curve_data(alignment, int(n), decimals=decimals, dms_decimals=dms_decimals)
        rows.append([_cell(row, k, decimals) for k in keys])
    return headers, rows, widths


__all__ = [
    "LABEL_KINDS", "ROTATION_MODES", "SIDES", "DEFAULT_SIDE", "DEFAULT_VALIGN",
    "MODEL_LABEL_OFFSET", "MODEL_TEXT_HEIGHT", "MODEL_TICK_HALF", "SHEET_LABEL_OFFSET",
    "SHEET_TEXT_HEIGHT", "LabelSpec", "TickSpec", "StationingPlan", "upright", "offset_point",
    "label_content", "compile_label", "sheet_pose", "stationing_plan", "CURVE_COLUMNS",
    "DEFAULT_CURVE_COLUMNS", "curve_table_rows",
]
