"""Label placement and wording: one shared module for commands and ground truth.

``compile_label`` turns an anchor + label kind into a fully specified text
placement (content, position, rotation, alignment) in model space;
``sheet_pose`` maps it through a viewport; ``stationing_plan`` produces the
tick/label plan an alignment-mode ``annotate_stationing`` materialises; and
``curve_table_rows`` builds the curve data table.  Because the task
generator's ground truth calls these same functions, the reference solution
matches the truth exactly.

Wording and placement follow the Caltrans Plans Preparation Manual, the one
convention set the probes and the benchmark share (decided 2026-10-11):

- Station numbers go below the line (ppm-text p. 2-8): the whole station at
  each 500 ft, the ones digit elsewhere (``30``, then ``1``, ``2`` ...).
- The beginning and end of a curve are lettered with the station then the word,
  ``24+05.27 BC``, square to the line on its left and reading bottom to top
  (p. 2-85, 2-4); the design model and its anchors call the points PC and PT.
- A tangent carries its bearing and its length above the line, parallel to it
  (p. 2-89): ``N 71°33'54" E 1240.36'``.
- A curve is numbered in a bubble with a leader to the curve, and the curve
  table lists No., R, Δ, T and L (p. 2-85).

``above`` and ``below`` are paper-relative sides: ``resolve_side`` turns them
into the left or right of the stationing direction so a label's anchor record
always names a side a verifier can recompute.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from roaddraft.core import geometry as geo
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
#: ``above`` and ``below`` are the paper's up and down; ``left`` and ``right`` the
#: stationing direction's
SIDES = ("left", "right", "above", "below")
#: where each kind goes by default, as the PPM letters a layout
DEFAULT_SIDE = {"station": "below", "bearing": "above", "begin": "left", "end": "left",
                "pc": "left", "pt": "left", "pi": "left", "mc": "right", "pcc": "left",
                "prc": "left", "equation": "left", "curve_data": "right", "custom": "left"}
#: how each kind reads by default: curve points and equations square to the
#: line (bottom to top), the curve number upright in its bubble, the rest along
DEFAULT_ROTATION = {"pc": "perpendicular", "pt": "perpendicular", "pcc": "perpendicular",
                    "prc": "perpendicular", "equation": "perpendicular", "mc": "horizontal"}
DEFAULT_VALIGN = {"left": "bottom", "right": "top"}
#: engine defaults in model feet, sized for 1" = 50' (the paper figures below x 50)
MODEL_LABEL_OFFSET = 6.0      # station numbers: half a text height under a 7 ft tick
MODEL_POINT_OFFSET = 22.5     # curve points and equations, square to the line
MODEL_BEARING_OFFSET = 3.0    # bearing and distance, just above the line
MODEL_BUBBLE_OFFSET = 40.0    # the curve number bubble, off the curve
MODEL_TEXT_HEIGHT = 8.0
MODEL_TICK_HALF = 3.5         # a 7 ft tick (ppm-text p. 2-8: 7.0' at 1" = 50')
SHEET_LABEL_OFFSET = 0.12
SHEET_POINT_OFFSET = 0.45
SHEET_BEARING_OFFSET = 0.06
SHEET_BUBBLE_OFFSET = 0.80
SHEET_TEXT_HEIGHT = 0.10
#: the curve number bubble's radius, in text heights (0.2 in around 0.10 in text)
BUBBLE_RADIUS_FACTOR = 2.0
#: stations carry their whole number at multiples of this, the ones digit elsewhere
FULL_STATION_FT = 500.0
#: what a plan letters at each curve point: the design's PC and PT are the
#: Caltrans BC and EC
CURVE_POINT_WORDS = {"pc": "BC", "pt": "EC", "pi": "PI", "pcc": "PCC", "prc": "PRC"}
#: the default offset of each kind from its anchor, in model feet and sheet inches
MODEL_OFFSETS = {"station": MODEL_LABEL_OFFSET, "bearing": MODEL_BEARING_OFFSET,
                 "pc": MODEL_POINT_OFFSET, "pt": MODEL_POINT_OFFSET, "pcc": MODEL_POINT_OFFSET,
                 "prc": MODEL_POINT_OFFSET, "equation": MODEL_POINT_OFFSET,
                 "mc": MODEL_BUBBLE_OFFSET}
SHEET_OFFSETS = {"station": SHEET_LABEL_OFFSET, "bearing": SHEET_BEARING_OFFSET,
                 "pc": SHEET_POINT_OFFSET, "pt": SHEET_POINT_OFFSET, "pcc": SHEET_POINT_OFFSET,
                 "prc": SHEET_POINT_OFFSET, "equation": SHEET_POINT_OFFSET,
                 "mc": SHEET_BUBBLE_OFFSET}


def default_offset(kind: str, space: str = "model") -> float:
    """The offset a label of ``kind`` takes from its anchor when none is given:
    model feet (sized for 1" = 50') or sheet inches."""
    table = SHEET_OFFSETS if space != "model" else MODEL_OFFSETS
    return float(table.get(kind, SHEET_LABEL_OFFSET if space != "model" else MODEL_LABEL_OFFSET))


def caltrans_station_text(display_station: float, full_every: float = FULL_STATION_FT) -> str:
    """How a layout letters a whole station (ppm-text p. 2-8): the whole station
    number at each multiple of ``full_every`` (``30`` for 30+00), the ones
    digit elsewhere (``6`` for 26+00), never a plus."""
    hundreds = int(round(float(display_station) / 100.0))
    per = int(round(float(full_every) / 100.0)) or 1
    return str(hundreds) if hundreds % per == 0 else str(hundreds % 10)


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
    """Fold a rotation into (-90, 90] so text never reads upside down."""
    return geo.upright(angle_deg)


def reading_up(angle_deg: float) -> float:
    """Fold a rotation into (-45, 135]: text square to a line reads bottom to top."""
    return geo.reading_up(angle_deg)


def offset_point(p: Sequence[float], angle_deg: float, dist: float) -> List[float]:
    a = math.radians(angle_deg)
    return [p[0] + dist * math.cos(a), p[1] + dist * math.sin(a)]


def resolve_side(side: str, direction_deg: float) -> str:
    """``left`` or ``right`` of a line running ``direction_deg`` for a side that
    may be paper-relative: ``below`` is the side under text set along the line
    (its right when the text reads with the stationing, its left when
    ``upright`` has turned the text round), ``above`` the other."""
    if side in ("left", "right"):
        return side
    if side not in SIDES:
        raise DesignError(f"side must be one of {list(SIDES)}, not {side!r}")
    flipped = 90.0 < float(direction_deg) % 360.0 <= 270.0
    below = "left" if flipped else "right"
    return below if side == "below" else ("right" if below == "left" else "left")


def beside(p: Sequence[float], direction_deg: float, side: str, dist: float) -> List[float]:
    """The point ``dist`` off ``p`` on ``side`` of a line running ``direction_deg``."""
    side = resolve_side(side, direction_deg)
    return offset_point(p, direction_deg + (90.0 if side == "left" else -90.0), dist)


def label_pose(direction_deg: float, side: str, rotation: str) -> Tuple[float, str, str]:
    """``(rotation_deg, halign, valign)`` of a label on ``side`` (left/right) of a
    line running ``direction_deg``: text along the line stays upright and
    sits clear of the line on its side; text square to it reads bottom to
    top and runs away from the line; horizontal text is centred."""
    side_angle = direction_deg + (90.0 if side == "left" else -90.0)
    if rotation == "perpendicular":
        rot = reading_up(direction_deg + 90.0)
        outward = math.cos(math.radians(rot - side_angle)) > 0.0
        return rot, ("left" if outward else "right"), "middle"
    if rotation == "horizontal":
        return 0.0, "center", "middle"
    rot = upright(direction_deg)
    up = math.cos(math.radians(rot + 90.0 - side_angle)) > 0.0
    return rot, "center", ("bottom" if up else "top")


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
        # a whole station is lettered the Caltrans way (the number under its tick); any
        # other station in full
        display, _region = st.to_display(ap.station)
        if abs(display / 100.0 - round(display / 100.0)) < 1e-6:
            return caltrans_station_text(display)
        return st.format(ap.station)
    if kind in CURVE_POINT_WORDS:
        return f"{st.format(ap.station)} {CURVE_POINT_WORDS[kind]}"
    if kind == "mc":
        return str(ap.curve_index)
    if kind == "bearing":
        el = alignment.elements[ap.element_index]
        if not isinstance(el, TangentElement):
            raise DesignError(_bearing_message(alignment, ap))
        return f"{format_bearing(direction_to_azimuth(el.direction_deg))} {el.length:.2f}'"
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
    if kind == "mc" and hint == "station" and ap.curve_index is not None:
        return  # the curve's number where a sheet shows the curve, not only at its middle
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
                  label_offset: Optional[float] = None, rotation: Optional[str] = None,
                  content: Optional[str] = None, halign: Optional[str] = None,
                  valign: Optional[str] = None) -> LabelSpec:
    """Place a label of ``kind`` at anchor ``ap`` in model space.  ``side``,
    ``label_offset`` and ``rotation`` default by kind (the PPM's placement);
    the spec records the side as left or right of the line."""
    if kind not in LABEL_KINDS:
        raise DesignError(f"unknown label kind {kind!r}; kinds: {', '.join(LABEL_KINDS)}")
    _check_kind_anchor(alignment, ap, kind)
    if kind == "custom" and content is None:
        raise DesignError("kind custom requires content")
    rotation = rotation or DEFAULT_ROTATION.get(kind, "along")
    if rotation not in ROTATION_MODES:
        raise DesignError(f"rotation must be one of {list(ROTATION_MODES)}, not {rotation!r}")
    direction = float(ap.direction_deg)
    side = resolve_side(side or DEFAULT_SIDE[kind], direction)
    content_auto = content is None
    text = label_content(alignment, ap, kind) if content_auto else str(content)
    off = default_offset(kind, "model") if label_offset is None else float(label_offset)
    if off < 0:
        raise DesignError("label_offset must be >= 0")
    position = offset_point(ap.point, direction + (90.0 if side == "left" else -90.0), off)
    rot, h, v = label_pose(direction, side, rotation)
    return LabelSpec(kind=kind, alignment=alignment.name, ref=ap.ref, station=float(ap.station),
                     offset=float(ap.offset), region=int(ap.region),
                     anchor_point=[float(ap.point[0]), float(ap.point[1])],
                     direction_deg=direction, side=side, label_offset=off, rotation=rotation,
                     content=text, content_auto=content_auto, position=position,
                     rotation_deg=rot, halign=halign or h, valign=valign or v)


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
        rot = reading_up(spec.direction_deg + twist + 90.0)
    else:
        rot = 0.0
    return position, rot


# ------------------------------------------------------------- stationing


def stationing_plan(alignment: Alignment, interval: float = 100.0,
                    tick_half: float = MODEL_TICK_HALF, label_offset: float = MODEL_LABEL_OFFSET,
                    include_pc_pt: bool = True, include_equations: bool = True,
                    station_range: Optional[Tuple[float, float]] = None,
                    lettering: str = "caltrans", station_side: Optional[str] = None,
                    point_side: Optional[str] = None,
                    point_offset: Optional[float] = None) -> StationingPlan:
    """Ticks + labels for every interval station (per region), BC/EC/PCC/PRC
    labels, and equation labels.  ``station_range`` is in RAW stations.

    The PPM's layout by default: station numbers below the line, lettered
    ``caltrans`` (the whole number at each 500 ft, the ones digit elsewhere;
    ``full`` letters every one ``26+00.00``); curve points and equations
    ``point_offset`` off the line on its left, square to it and reading
    bottom to top.  A negative ``label_offset`` is the older way of asking
    for stations on the right and points on the left.  Each label records
    the side it is on (left or right of the stationing) with a positive
    offset."""
    if interval <= 0:
        raise DesignError("interval must be > 0")
    if lettering not in ("caltrans", "full"):
        raise DesignError(f"lettering must be 'caltrans' or 'full', not {lettering!r}")
    if label_offset < 0:
        station_side, point_side = station_side or "right", point_side or "left"
    station_side = station_side or DEFAULT_SIDE["station"]
    point_side = point_side or DEFAULT_SIDE["pc"]
    for s in (station_side, point_side):
        if s not in SIDES:
            raise DesignError(f"side must be one of {list(SIDES)}, not {s!r}")
    label_offset = abs(float(label_offset))
    point_offset = MODEL_POINT_OFFSET if point_offset is None else abs(float(point_offset))
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
                side = resolve_side(station_side, direction)
                rot, h, v = label_pose(direction, side, "along")
                items.append(LabelSpec(
                    kind="station", alignment=alignment.name, ref=text, station=raw, offset=0.0,
                    region=region.index, anchor_point=list(pt), direction_deg=direction,
                    side=side, label_offset=label_offset, rotation="along",
                    content=caltrans_station_text(sd) if lettering == "caltrans" else text,
                    content_auto=True, position=beside(pt, direction, side, label_offset),
                    rotation_deg=rot, halign=h, valign=v))
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
            side = resolve_side(point_side, direction)
            rot, h, v = label_pose(direction, side, "perpendicular")
            items.append(LabelSpec(
                kind=jk, alignment=alignment.name, ref=ref, station=raw, offset=0.0,
                region=region, anchor_point=list(pt), direction_deg=direction,
                side=side, label_offset=point_offset, rotation="perpendicular",
                content=f"{st.format(raw)} {CURVE_POINT_WORDS[jk]}", content_auto=True,
                position=beside(pt, direction, side, point_offset),
                rotation_deg=rot, halign=h, valign=v))
            n_junctions += 1

    n_equations = 0
    if include_equations:
        for n, eq in enumerate(alignment.equations, start=1):
            raw = float(eq.raw_station)
            if not in_range(raw):
                continue
            pt, direction = at(raw)
            disp, region = st.to_display(raw)
            side = resolve_side(point_side, direction)
            rot, h, v = label_pose(direction, side, "perpendicular")
            items.append(LabelSpec(
                kind="equation", alignment=alignment.name, ref=f"EQ-{n}", station=raw, offset=0.0,
                region=region, anchor_point=list(pt), direction_deg=direction, side=side,
                label_offset=point_offset, rotation="perpendicular", content=equation_label(eq),
                content_auto=True, position=beside(pt, direction, side, point_offset),
                rotation_deg=rot, halign=h, valign=v))
            n_equations += 1

    return StationingPlan(items=items, n_ticks=n_ticks, n_junctions=n_junctions,
                          n_equations=n_equations, begin_text=st.begin_text(),
                          end_text=st.end_text())


# ------------------------------------------------------------ curve table

#: column key -> (header, width in): No., R, Δ, T and L are the PPM's curve data
#: table (ppm-examples layout sheets); the rest are offered for other offices
CURVE_COLUMNS = OrderedDict([
    ("curve", ("No.", 0.6)),
    ("pi_sta", ("PI STA", 1.1)),
    ("pc_sta", ("BC STA", 1.1)),
    ("pt_sta", ("EC STA", 1.1)),
    ("delta", ("Δ", 1.3)),
    ("direction", ("DIR", 0.6)),
    ("radius", ("R", 1.0)),
    ("tangent", ("T", 1.0)),
    ("length", ("L", 1.0)),
    ("external", ("E", 0.9)),
    ("mid_ordinate", ("M", 0.9)),
    ("chord", ("C", 1.0)),
    ("chord_bearing", ("CH BRG", 1.6)),
])
DEFAULT_CURVE_COLUMNS = ["curve", "radius", "delta", "tangent", "length"]


def _cell(row: dict, key: str, decimals: int) -> str:
    if key == "curve":
        return str(row["index"])
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
                     dms_decimals: int = 0, first_number: int = 1
                     ) -> Tuple[List[str], List[List[str]], List[float]]:
    """``(headers, rows, widths_in)`` for a curve data table.  ``first_number``
    is the plan's number for the alignment's first curve: curve numbers run
    along the line across the layout sheets (ppm-text p. 2-85), so a design
    file holding only a later part of the line numbers on from the sheet
    before."""
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
        row["index"] = int(n) + int(first_number) - 1
        rows.append([_cell(row, k, decimals) for k in keys])
    return headers, rows, widths


__all__ = [
    "LABEL_KINDS", "ROTATION_MODES", "SIDES", "DEFAULT_SIDE", "DEFAULT_ROTATION", "DEFAULT_VALIGN",
    "MODEL_LABEL_OFFSET", "MODEL_POINT_OFFSET", "MODEL_BEARING_OFFSET", "MODEL_BUBBLE_OFFSET",
    "MODEL_TEXT_HEIGHT", "MODEL_TICK_HALF", "SHEET_LABEL_OFFSET", "SHEET_POINT_OFFSET",
    "SHEET_BEARING_OFFSET", "SHEET_BUBBLE_OFFSET", "SHEET_TEXT_HEIGHT", "BUBBLE_RADIUS_FACTOR",
    "FULL_STATION_FT", "MODEL_OFFSETS", "SHEET_OFFSETS", "default_offset",
    "caltrans_station_text", "CURVE_POINT_WORDS", "LabelSpec", "TickSpec", "StationingPlan",
    "upright", "reading_up", "offset_point", "resolve_side", "beside", "label_pose",
    "label_content", "compile_label", "sheet_pose", "stationing_plan", "CURVE_COLUMNS",
    "DEFAULT_CURVE_COLUMNS", "curve_table_rows",
]
