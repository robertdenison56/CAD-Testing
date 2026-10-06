"""Tier-3 probes: the alignment data of a layout sheet, and the work around it.

A Caltrans layout must show "stationing equations, distances and bearings of
all tangents, stations of all curve points and curve data" for every station
line, curve numbers consecutive along the line and never restarted on the next
sheet (ppm-text p. 2-85); bearing and distance above the line (p. 2-89); the
traveled way and shoulders dimensioned (p. 2-90); stationing ticked every
100 ft, 7.0 ft long at 1" = 50', the whole number only at 500 ft stations and
the annotation below the line (p. 2-8); BC and EC text and match lines read
bottom to top (p. 2-4). None of the first 23 probes asks for any of it.

* ``line-data`` -- bearing and length of every tangent, along and above the line.
* ``curve-points`` -- BC and EC stations, square to the line, reading bottom to top.
* ``curve-data`` -- a CURVE DATA table on each sheet for the curves it shows,
  numbered along the line, and a numbered bubble on each curve.
* ``stationing`` -- Caltrans stationing for the 16 stations C-102 shows.
* ``width-dims`` -- the lanes and shoulders dimensioned across the road.
* ``row-data`` -- right of way lines tagged L1/C1 with line and curve tables.
* ``equation-data`` -- a station equation, and the arithmetic it breaks.
* ``qa-alignment-data`` -- five errors planted in finished alignment data.
* ``l2-match-lines`` -- match lines on the real, twisted Caltrans sheet L-2.
* ``l2-alignment-data`` -- the whole job on L-2.

Every sheet file here *references* its design: ``place_label``,
``place_curve_table`` and ``annotate_stationing`` refuse a referenced
alignment. So an agent either composes the lettering from ``get_design_data``
or copies the design into the sheet file and uses the engine's labelers. The
checks read the sheet as it plots (``plotted``) -- paper space and the sheet
file's model space through each viewport -- so both routes score alike. Values
are read, not spellings (``notation``): ``N71°33'54"E`` passes where
``N 71°33'54" E`` does, ``1581.14'`` fails wherever it is written. The words
are the standard's: BC, EC, PCC, BK, AH.
"""
from __future__ import annotations

import itertools
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.design.errors import DesignError
from roaddraft.document import viewmap
from roaddraft.document.entities import Circle, Line, Polyline, Table, Text
from roaddraft.document.references import find_reference_alignment, reference_groups
from roaddraft.probes import fixture
from roaddraft.probes import notation as nt
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result
from roaddraft.probes.drafting import run
from roaddraft.probes.tier2 import paper_linework, sheet_named, sheet_stations

AIM_FT = 1.0              # where a leader tip or a tick lands, as plotted
TURN_DEG = 1.0            # how far lettering may turn off the direction asked for
CLEAR_IN = 0.02           # air between lettering and linework
BAND_IN = 0.03            # how far a curve point may lie outside its text's height band
NEAR_IN = 1.0             # how far line data may sit from its line
VALUE_FT = 0.011          # lengths lettered to the hundredth
RADIUS_FT = 0.5           # Caltrans curve tables letter R to the whole foot
ALIGN = fixture.ALIGNMENT
SR = f"DESIGN:{ALIGN}"
SR70 = "DESIGN:SR70"
LAYER = "S-ANNO-ALGN"


# ------------------------------------------------------------------- the road


class Road:
    """A referenced alignment as the sheets show it, read from the start
    document: stations to host points and paper points, headings, and what
    each viewport shows (window and reference clip both)."""

    def __init__(self, session: Session, qualified: str):
        found = find_reference_alignment(session.doc, qualified)
        if found is None:
            raise RuntimeError(f"the start document carries no {qualified}")
        self.align, self.place = found
        ref_name = qualified.split(":", 1)[0]
        ref = next((r for r in session.doc.references.values() if r.name == ref_name), None)
        self.clip = [list(p) for p in ref.clip] if ref is not None and ref.clip else None
        self.session, self.qualified = session, qualified
        self._tangents = self._curves = None

    @property
    def begin(self) -> float:
        return float(self.align.begin_station)

    @property
    def end(self) -> float:
        return float(self.align.end_station)

    def text(self, raw: float) -> str:
        return self.align.stations().format(raw)

    def display(self, raw: float) -> float:
        return nt.stations(self.text(raw))[0][0]

    def model(self, raw: float, offset: float = 0.0) -> List[float]:
        return self.place.to_host(self.align.station_to_xy(raw, offset)[0])

    def heading(self, raw: float) -> float:
        dist = min(max(raw - self.begin, 0.0), self.align.length)
        return self.align.direction_at(dist) + self.place.rotation_deg

    def paper(self, vp, raw: float, offset: float = 0.0) -> List[float]:
        return vp.transform().to_paper(self.model(raw, offset))

    def paper_heading(self, vp, raw: float) -> float:
        return self.heading(raw) + float(vp.rotation_deg)

    def locate(self, host_point) -> Optional[Tuple[float, float]]:
        """``(raw station, offset ft right +)`` of a host point, None past the ends."""
        try:
            r = self.align.xy_to_station(self.place.to_base(host_point))
        except DesignError:
            return None
        return float(r["station"]), float(r["offset"]) * self.place.scale

    def shows(self, vp, host_point, inset: float = 0.0) -> bool:
        q = vp.transform().to_paper(host_point)
        x0, y0, x1, y1 = vp.paper_bbox()
        if not (x0 + inset <= q[0] <= x1 - inset and y0 + inset <= q[1] <= y1 - inset):
            return False
        return self.clip is None or geo.point_in_polygon(host_point, self.clip)

    def shown(self, vp, raw0: float, raw1: float, offset: float = 0.0,
              step: float = 2.0) -> Optional[Tuple[float, float]]:
        """The part of ``[raw0, raw1]`` this viewport shows, as raw stations."""
        n = max(2, int(math.ceil((raw1 - raw0) / step)))
        hits = [raw0 + (raw1 - raw0) * i / n for i in range(n + 1)]
        hits = [st for st in hits if self.shows(vp, self.model(st, offset))]
        return (min(hits), max(hits)) if hits else None

    def tangents(self) -> List[dict]:
        if self._tangents is None:
            self._tangents = _rows(self.session, self.qualified, "tangents")
        return self._tangents

    def curves(self) -> List[dict]:
        if self._curves is None:
            self._curves = _rows(self.session, self.qualified, "curves")
        return self._curves

    def curve_points(self) -> List[Tuple[str, float, str]]:
        """``(word, raw station, refs)`` for every BC, EC, PCC and PRC."""
        out: List[Tuple[str, float, str]] = []
        curves = self.curves()
        for i, c in enumerate(curves):
            if out and abs(out[-1][1] - c["pc_station"]) < 0.01:
                word = "PCC" if c["direction"] == curves[i - 1]["direction"] else "PRC"
                out[-1] = (word, out[-1][1], f"{out[-1][2]}={c['ref']}")
            else:
                out.append(("BC", c["pc_station"], f"PC of {c['ref']}"))
            out.append(("EC", c["pt_station"], f"PT of {c['ref']}"))
        return out


def _rows(session: Session, qualified: str, kind: str) -> List[dict]:
    r = session.query("get_design_data", {"alignment": qualified, "kind": kind, "limit": 200})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return r["rows"]


def _vp(sheet):
    return sheet.viewports[0]


def _views(baseline: Session, submitted: Session, name: str, added_only: bool = True):
    """``(baseline sheet, submitted sheet, what the submission puts on it)``."""
    sheet_b = sheet_named(baseline.doc, name)
    sheet_s = sheet_named(submitted.doc, name)
    if sheet_s is None:
        return sheet_b, None, None
    view = pl.plot(submitted, sheet_s, pl.sheet_items(baseline, submitted, name, added_only))
    return sheet_b, sheet_s, view


def _q(text: str, limit: int = 60) -> str:
    one = " / ".join(text.split("\n"))
    return repr(one if len(one) <= limit else one[:limit - 3] + "...")


def _nearest(texts: Sequence[pl.PText], point, within: float) -> List[pl.PText]:
    near = [t for t in texts if math.dist(t.center(), point) <= within]
    return sorted(near, key=lambda t: math.dist(t.center(), point))


# ------------------------------------------------------- lettering along a line


def _along_problem(t: pl.PText, road: Road, vp, a: float, b: float, side: Optional[int],
                   near: float = NEAR_IN, clear: Optional[Sequence] = None) -> Optional[str]:
    """Is ``t`` lettered along the stretch ``a``..``b`` of a tangent, reading
    left to right, above it (``side`` +1: left of the stationing) or on either
    side (None), and within ``near`` of it? ``clear``: paper points it must
    keep CLEAR_IN from."""
    d = road.paper_heading(vp, (a + b) / 2.0)
    want = geo.upright(d)
    if pl.turn_between(t.rotation, want) > TURN_DEG:
        if pl.turn_between(t.rotation, want + 180.0) <= TURN_DEG:
            return f"{_q(t.content)} reads upside down"
        return (f"{_q(t.content)} runs at {pl.wrap(t.rotation):.2f}° on the sheet; the line runs "
                f"at {pl.wrap(want):.2f}° there")
    p0, p1 = road.paper(vp, a), road.paper(vp, b)
    along, left = pl.offset_from(t.center(), p0, d)
    if along < 0.0 or along > math.dist(p0, p1):
        return f"{_q(t.content)} sits beyond the part of the tangent this sheet shows"
    lefts = [pl.offset_from(k, p0, d)[1] for k in t.corners()]
    if min(lefts) < 0.0 < max(lefts):
        return f"{_q(t.content)} sits across the centerline"
    if side is not None and side > 0 and max(lefts) <= 0.0:
        return f"{_q(t.content)} is below the line; line data goes above it"
    if abs(left) > near:
        return f"{_q(t.content)} sits {abs(left):.2f} in from the line (within {near:g} in is beside it)"
    if clear:
        x0, y0, x1, y1 = geo.bbox_expand(t.bbox(), CLEAR_IN)
        hit = next((p for p in clear if x0 <= p[0] <= x1 and y0 <= p[1] <= y1
                    and t.contains(p, CLEAR_IN)), None)
        if hit is not None:
            return (f"{_q(t.content)} runs over linework at [{hit[0]:.2f}, {hit[1]:.2f}] in "
                    f"(less than {CLEAR_IN} in of air)")
    return None


def _line_data_problem(view: pl.Plot, road: Road, vp, t: dict, a: float, b: float,
                       side: Optional[int] = 1, clear=None, near: float = NEAR_IN,
                       split: bool = False) -> Optional[str]:
    """Is tangent ``t`` (shown from ``a`` to ``b``) lettered with its bearing
    and length? ``split`` lets the two be separate texts, as L-2 letters them."""
    az, length, bearing = float(t["azimuth_deg"]), float(t["length"]), t["bearing"]
    texts = view.free_texts()

    def has_bearing(x):
        return any(nt.azimuth_close(v, az) for v in nt.bearings(x.content))

    def has_length(x):
        return any(abs(v - length) <= VALUE_FT for v in nt.feet(x.content))

    whole = [x for x in texts if has_bearing(x) and has_length(x)]
    problems = []
    for x in whole:
        problem = _along_problem(x, road, vp, a, b, side, near, clear)
        if problem is None:
            return None
        problems.append(problem)
    if split:
        parts = []
        for want in (has_bearing, has_length):
            ok = [x for x in texts if want(x)
                  and _along_problem(x, road, vp, a, b, None, near, clear) is None]
            parts.append(ok)
        if all(parts):
            return None
    if problems:
        return problems[0]
    mid = road.paper(vp, (a + b) / 2.0)
    near_texts = _nearest(texts, mid, 0.5 * math.dist(road.paper(vp, a), road.paper(vp, b)) + 1.0)
    for x in near_texts:
        brgs, lens = nt.bearings(x.content), nt.feet(x.content)
        if brgs and not any(nt.azimuth_close(v, az) for v in brgs):
            if any(nt.azimuth_close(v, az, either_way=True) for v in brgs):
                return (f"{_q(x.content)} gives the back bearing; along the stationing the "
                        f"tangent bears {bearing}")
            return f"{_q(x.content)} does not give the tangent's bearing, {bearing}"
        if brgs and lens:
            return f"{_q(x.content)}: the tangent is {length:.2f}' long, from its BC/EC to the next"
    found = f"; nearest lettering: {_q(near_texts[0].content)}" if near_texts else ""
    return f"no lettering gives {bearing} {length:.2f}'{found}"


def _tangents_on(road: Road, sheet, min_in: float = 2.0):
    """``(tangent, a, b, vp)`` for every tangent the sheet shows at least
    ``min_in`` of."""
    vp = _vp(sheet)
    out = []
    for t in road.tangents():
        span = road.shown(vp, float(t["start_station"]), float(t["end_station"]))
        if span is not None and (span[1] - span[0]) / vp.feet_per_inch >= min_in:
            out.append((t, span[0], span[1], vp))
    return out


# ------------------------------------------------- lettering square to the line


def _square_problem(t: pl.PText, point, d: float, reading_up: bool = True,
                    side: Optional[int] = 1, band: float = BAND_IN) -> Optional[str]:
    """Is ``t`` lettered on the line square to the centerline through
    ``point`` (paper), the line running at ``d`` there?"""
    want = d + 90.0
    if reading_up:
        if pl.turn_between(t.rotation, want) > TURN_DEG:
            if pl.turn_between(t.rotation, want + 180.0) <= TURN_DEG:
                return (f"{_q(t.content)} reads top to bottom (at {pl.wrap(t.rotation):.2f}°); "
                        f"square to the line and reading bottom to top is {pl.wrap(want):.2f}°")
            return (f"{_q(t.content)} runs at {pl.wrap(t.rotation):.2f}°; square to the line is "
                    f"{pl.wrap(want):.2f}°")
    elif pl.turn_between(t.rotation, want, 180.0) > TURN_DEG:
        return (f"{_q(t.content)} runs at {pl.wrap(t.rotation):.2f}°; square to the line is "
                f"{pl.wrap(want):.2f}°")
    off = t.axis_distance(point) - t.size()[1] / 2.0
    if off > band:
        return (f"{_q(t.content)} is {off:.2f} in off the line square to the centerline through "
                f"the point it names")
    if t.contains(point):
        return f"{_q(t.content)} covers the point it names; it belongs beside it, off the line"
    if side is not None:
        left = pl.offset_from(t.center(), point, d)[1]
        if side > 0 and left <= 0.0:
            return f"{_q(t.content)} is on the right of the line; it was asked for on the left"
    return None


def _point_problem(view: pl.Plot, word: str, display: float, point, d: float,
                   reading_up: bool = True, side: Optional[int] = 1,
                   band: float = BAND_IN) -> Optional[str]:
    """Is the curve point ``word`` at station ``display`` lettered square to
    the line through ``point``?"""
    texts = view.free_texts()
    station = f"{int(display // 100)}+{display % 100:05.2f}"
    right = [x for x in texts if nt.has_station(x.content, display) and nt.has_word(x.content, word)]
    problems = [_square_problem(x, point, d, reading_up, side, band) for x in right]
    if any(p is None for p in problems):
        return None
    if problems:
        return problems[0]
    for x in _nearest(texts, point, 3.0):
        if nt.has_station(x.content, display):
            others = [w for w in ("BC", "EC", "PC", "PT", "PCC", "PRC") if nt.has_word(x.content, w)]
            return (f"{_q(x.content)} letters {station} as {'/'.join(others) or 'no curve point'}; "
                    f"it is the {word}")
        if any(abs(v - display) <= 0.6 for v, _w in nt.stations(x.content)):
            return f"{_q(x.content)}: the {word} is at {station}, to the hundredth"
    return f"no lettering reads {station} {word}"


# --------------------------------------------------------------- curve tables


@dataclass
class Row:
    number: Optional[int]
    R: Optional[float]
    delta: Optional[float]
    T: Optional[float]
    L: Optional[float]
    cells: List[str]
    box: Optional[Tuple[float, float, float, float]] = None

    def text(self) -> str:
        return " | ".join(self.cells)


def _key(header: str) -> Optional[str]:
    h = re.sub(r"\(.*?\)", "", header.upper())                # "R (FT)" is R
    h = re.sub(r"[^A-ZΔ#]", "", h.replace("⊗", ""))
    if h in ("NO", "N", "NUMBER", "CURVE", "CRV", "#", "CURVENO", "NUM"):
        return "no"
    if h in ("R", "RADIUS", "RAD"):
        return "R"
    if h in ("Δ", "DELTA", "D", "DEFL", "I"):
        return "delta"
    if h in ("T", "TAN", "TANGENT"):
        return "T"
    if h in ("L", "LEN", "LENGTH", "ARC"):
        return "L"
    return None


def _read_curve_row(cells: List[str], keys: Optional[List[Optional[str]]] = None) -> Row:
    cells = [c.strip() for c in cells]
    if keys and len(keys) == len(cells) and {"R", "delta", "T", "L"} <= set(keys):
        by = {k: c for k, c in zip(keys, cells) if k}
        no = by.get("no", cells[0])
        dl = nt.angles(by["delta"])
        return Row(nt.curve_number(no), nt.number(by["R"]), dl[0] if dl else None,
                   nt.number(by["T"]), nt.number(by["L"]), cells)
    if len(cells) == 1:                      # one text holding the whole row
        parts = cells[0].split(None, 1)
        if len(parts) < 2:
            return Row(None, None, None, None, None, cells)
        head, rest = parts
        dl = nt.angles(rest)
        nums = [float(m.group(0).replace(",", "")) for m in
                re.finditer(r"\d[\d,]*(?:\.\d+)?", nt.DMS_RE.sub(" ", rest))]
        vals = nums + [None] * 3
        return Row(nt.curve_number(head), vals[0], dl[0] if dl else None, vals[1], vals[2], cells)
    dl, nums = None, []
    for c in cells[1:]:
        a = nt.angles(c)
        if a and dl is None:
            dl = a[0]
            continue
        v = nt.number(c)
        if v is not None:
            nums.append(v)
    vals = nums + [None] * 3
    return Row(nt.curve_number(cells[0]), vals[0], dl, vals[1], vals[2], cells)


def _curve_rows(view: pl.Plot) -> List[Row]:
    out = []
    for t in view.tables:
        keys = [_key(h) for h in t.headers]
        for cells in t.rows:
            row = _read_curve_row(cells, keys)
            row.box = t.box
            out.append(row)
    for cells in pl.text_rows(view.free_texts()):
        row = _read_curve_row(cells)
        if row.number is not None and sum(v is not None for v in (row.R, row.delta, row.T, row.L)) >= 3:
            out.append(row)
    return [r for r in out if r.number is not None]


def _row_problem(row: Row, c: dict, number: int) -> Optional[str]:
    if row.R is None or abs(row.R - c["radius"]) > RADIUS_FT:
        return f"curve {number}'s R reads {row.R!r}; it is {c['radius']:.0f}'"
    if row.delta is None or not nt.azimuth_close(row.delta, c["delta_deg"]):
        dec = [v for cell in row.cells for v in nt.decimal_degrees(cell)]
        if dec:
            return f"curve {number}'s Δ is written in decimal degrees ({dec[0]:g}°); it is {c['delta_dms']}"
        return f"curve {number}'s Δ reads {row.delta!r}; it is {c['delta_dms']}"
    if row.T is None or abs(row.T - c["tangent"]) > VALUE_FT:
        hint = ""
        for name in ("external", "mid_ordinate", "length"):
            if row.T is not None and abs(row.T - c[name]) <= VALUE_FT:
                hint = f" ({row.T:.2f}' is its {name.replace('_', '-')})"
        return f"curve {number}'s T reads {row.T!r}; it is {c['tangent']:.2f}'{hint}"
    if row.L is None or abs(row.L - c["length"]) > VALUE_FT:
        hint = (f" ({row.L:.2f}' is its T)" if row.L is not None
                and abs(row.L - c["tangent"]) <= VALUE_FT else "")
        return f"curve {number}'s L reads {row.L!r}; it is {c['length']:.2f}'{hint}"
    return None


def _curves_on(road: Road, sheet, min_in: float = 0.25) -> List[int]:
    """1-based indices of the curves the sheet shows at least ``min_in`` of."""
    vp = _vp(sheet)
    out = []
    for c in road.curves():
        span = road.shown(vp, float(c["pc_station"]), float(c["pt_station"]), step=1.0)
        if span is not None and (span[1] - span[0]) / vp.feet_per_inch >= min_in:
            out.append(int(c["index"]))
    return out


def _table_problem(view: pl.Plot, road: Road, sheet, wanted: Dict[int, dict], name: str,
                   clear: Optional[Sequence] = None) -> Optional[str]:
    """``wanted``: plan curve number -> the design's curve row."""
    rows = _curve_rows(view)
    if not rows:
        return f"{name} has no CURVE DATA table"
    for r in rows:
        if r.number in wanted:
            continue
        same = next((n for n, c in sorted(wanted.items()) if _row_problem(r, c, n) is None), None)
        if same is not None:
            return (f"{name}'s table numbers curve {same} as {r.number}; curve numbers run along "
                    f"the line and are not restarted on a new sheet")
        return (f"{name}'s table lists curve {r.number}, which {name} does not show; it shows "
                f"{', '.join(map(str, sorted(wanted)))}")
    for number, c in sorted(wanted.items()):
        mine = [r for r in rows if r.number == number]
        if not mine:
            return f"{name}'s table has no row for curve {number}"
        problems = [_row_problem(r, c, number) for r in mine]
        if all(p is not None for p in problems):
            return f"{name}: {problems[0]}"
    area = sheet.usable_area()
    for r in rows:
        if r.box is None:
            continue
        if not geo.bbox_contains(area, r.box, tol=1e-6):
            return f"{name}'s table runs outside the drawing area"
        if clear:
            x0, y0, x1, y1 = geo.bbox_expand(r.box, CLEAR_IN)
            hit = next((p for p in clear if x0 <= p[0] <= x1 and y0 <= p[1] <= y1), None)
            if hit is not None:
                return (f"{name}'s table sits over the roadway at [{hit[0]:.2f}, {hit[1]:.2f}] in; "
                        f"keep it clear")
    return None


def _bubbles(view: pl.Plot) -> List[Tuple[pl.PCircle, Optional[int]]]:
    out = []
    for c in view.circles:
        if not 0.08 <= c.radius <= 0.45:
            continue
        inside = [t for t in view.free_texts() if math.dist(t.center(), c.center) <= 0.6 * c.radius]
        nums = [nt.curve_number(t.content) for t in inside]
        out.append((c, next((n for n in nums if n is not None), None)))
    return out


def _on_curve(road: Road, vp, c: dict, tip) -> Tuple[bool, float]:
    host = vp.transform().to_model(tip)
    where = road.locate(host)
    if where is None:
        return False, math.inf
    st, off = where
    if not (float(c["pc_station"]) - AIM_FT <= st <= float(c["pt_station"]) + AIM_FT):
        return False, math.inf
    return abs(off) <= AIM_FT and road.shows(vp, host), abs(off)


def _bubble_problem(view: pl.Plot, road: Road, vp, number: int, c: dict, name: str) -> Optional[str]:
    found = _bubbles(view)
    mine = [b for b, n in found if n == number]
    if not mine:
        have = sorted(n for _b, n in found if n is not None)
        return (f"{name} has no bubble numbered {number} on its curve"
                + (f" (bubbles: {', '.join(map(str, have))})" if have else ""))
    best = math.inf
    for b in mine:
        for tip, _path in pl.chains_from(view, b.center, b.radius + 0.12):
            if math.dist(tip, b.center) <= b.radius:
                continue
            ok, miss = _on_curve(road, vp, c, tip)
            if ok:
                return None
            best = min(best, miss)
    if best == math.inf:
        return f"bubble {number} on {name} has no leader reaching its curve"
    return f"bubble {number}'s leader on {name} stops {best:.2f} ft off the curve (needed {AIM_FT} ft)"


# ------------------------------------------------------------------ solving


def _layer(session: Session) -> str:
    if LAYER not in session.doc.layers:
        run(session, "create_layer", {"name": LAYER, "color": "black"})
    return LAYER


def _at(session: Session, qualified: str, sheet: str, raw: float, offset: float = 0.0):
    """Paper point and paper heading of a RAW station: asked by its display
    station and region, the way a station past an equation has to be named."""
    stations = find_reference_alignment(session.doc, qualified)[0].stations()
    display, region = stations.to_display(raw)
    r = session.query("station_to_xy", {"alignment": qualified, "station": display,
                                        "region": region, "offset": offset, "sheet": sheet})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    o = r["on_sheet"]
    return o["sheet_point"], r["direction_deg"] + o["rotation_deg"]


def _step(p, deg: float, dist: float) -> List[float]:
    u = pl.unit(deg)
    return [p[0] + u[0] * dist, p[1] + u[1] * dist]


def _letter_tangent(session: Session, qualified: str, sheet: str, t: dict, a: float, b: float,
                    above: float = 0.06, content: Optional[str] = None):
    p, d = _at(session, qualified, sheet, (a + b) / 2.0)
    run(session, "place_text", {"space": sheet, "layer": _layer(session),
                                "position": _step(p, d + 90.0, above), "height": 0.10,
                                "rotation_deg": geo.upright(d), "halign": "center",
                                "valign": "bottom",
                                "content": content or f"{t['bearing']}  {t['length']:.2f}'"})


def _letter_point(session: Session, qualified: str, sheet: str, raw: float, text: str,
                  out: float = 0.48):
    p, d = _at(session, qualified, sheet, raw)
    run(session, "draw_line", {"space": sheet, "layer": _layer(session), "start": p,
                               "end": _step(p, d + 90.0, out - 0.04)})
    run(session, "place_text", {"space": sheet, "layer": _layer(session),
                                "position": _step(p, d + 90.0, out), "height": 0.10,
                                "rotation_deg": geo.reading_up(d + 90.0), "halign": "left",
                                "valign": "middle", "content": text})


def _bubble(session: Session, qualified: str, sheet: str, raw: float, number: int,
            rise: float = 1.0):
    p, d = _at(session, qualified, sheet, raw)
    centre = _step(p, d + 90.0, rise)
    layer = _layer(session)
    run(session, "draw_circle", {"space": sheet, "layer": layer, "center": centre, "radius": 0.2})
    run(session, "place_text", {"space": sheet, "layer": layer, "position": centre,
                                "content": str(number), "height": 0.12, "halign": "center",
                                "valign": "middle"})
    run(session, "draw_line", {"space": sheet, "layer": layer,
                               "start": _step(centre, d - 90.0, 0.2), "end": p})


CURVE_COLUMNS = (("No.", 0.6), ("R", 0.9), ("Δ", 1.2), ("T", 0.9), ("L", 0.9))


def _curve_table(session: Session, sheet: str, rows: List[List[str]], position=(25.0, 5.6)):
    run(session, "place_table", {"space": sheet, "layer": _layer(session),
                                 "position": list(position), "title": "CURVE DATA",
                                 "columns": [{"header": h, "width": w} for h, w in CURVE_COLUMNS],
                                 "rows": rows, "text_height": 0.10})


def _curve_cells(number: int, c: dict) -> List[str]:
    return [str(number), f"{c['radius']:.0f}'", c["delta_dms"], f"{c['tangent']:.2f}'",
            f"{c['length']:.2f}'"]


# 1. line data ------------------------------------------------------------------------


def _check_line_data(baseline, submitted):
    road = Road(baseline, SR)
    done = 0
    for name in fixture.SHEETS:
        sheet_b, sheet_s, view = _views(baseline, submitted, name)
        if sheet_s is None:
            return Result(False, f"sheet {name} is gone")
        lines = paper_linework(baseline, sheet_b)
        for t, a, b, vp in _tangents_on(road, sheet_b):
            problem = _line_data_problem(view, road, vp, t, a, b, side=1, clear=lines)
            if problem:
                return Result(False, f"{t['ref']} on {name}: {problem}")
            done += 1
    return Result(True, f"all {done} tangents lettered with bearing and length on the sheet that "
                        f"shows them: above the line, parallel to it, clear of the linework")


def _solve_line_data(session):
    road = Road(session, SR)
    for name in fixture.SHEETS:
        sheet = sheet_named(session.doc, name)
        for t, a, b, _vp_ in _tangents_on(road, sheet):
            _letter_tangent(session, SR, name, t, a, b)


# 2. curve points ---------------------------------------------------------------------


def _points_on(road: Road, sheet, inset: float = 0.25):
    vp = _vp(sheet)
    return [(word, raw, refs) for word, raw, refs in road.curve_points()
            if road.shows(vp, road.model(raw), inset)]


def _check_curve_points(baseline, submitted):
    road = Road(baseline, SR)
    done = 0
    for name in fixture.SHEETS:
        sheet_b, sheet_s, view = _views(baseline, submitted, name)
        if sheet_s is None:
            return Result(False, f"sheet {name} is gone")
        vp = _vp(sheet_b)
        for word, raw, refs in _points_on(road, sheet_b):
            problem = _point_problem(view, word, road.display(raw), road.paper(vp, raw),
                                     road.paper_heading(vp, raw))
            if problem:
                return Result(False, f"the {word} at {road.text(raw)} on {name} ({refs}): {problem}")
            done += 1
    return Result(True, f"all {done} curve points lettered with station and BC/EC, square to the "
                        f"line, reading bottom to top, beside the point")


def _solve_curve_points(session):
    road = Road(session, SR)
    for name in fixture.SHEETS:
        sheet = sheet_named(session.doc, name)
        for word, raw, _refs in _points_on(road, sheet):
            _letter_point(session, SR, name, raw, f'"{ALIGN}" {road.text(raw)} {word}')


# 3. curve data -----------------------------------------------------------------------


def _curve_data_problem(view, road: Road, sheet_b, name: str, numbering: Dict[int, int],
                        clear=None) -> Optional[str]:
    """``numbering``: the design's curve index -> the number the plan gives it."""
    curves = {int(c["index"]): c for c in road.curves()}
    shown = _curves_on(road, sheet_b)
    wanted = {numbering[i]: curves[i] for i in shown}
    problem = _table_problem(view, road, sheet_b, wanted, name, clear)
    if problem:
        return problem
    vp = _vp(sheet_b)
    for number, c in sorted(wanted.items()):
        problem = _bubble_problem(view, road, vp, number, c, name)
        if problem:
            return problem
    return None


def _check_curve_data(baseline, submitted):
    road = Road(baseline, SR)
    numbering = {int(c["index"]): int(c["index"]) for c in road.curves()}
    for name in fixture.SHEETS:
        sheet_b, sheet_s, view = _views(baseline, submitted, name)
        if sheet_s is None:
            return Result(False, f"sheet {name} is gone")
        problem = _curve_data_problem(view, road, sheet_b, name, numbering,
                                      clear=paper_linework(baseline, sheet_b))
        if problem:
            return Result(False, problem)
    return Result(True, "each sheet's CURVE DATA table lists exactly the curves it shows, numbered "
                        "along SR-100 with the design's R, Δ, T and L, and every curve carries its "
                        "numbered bubble with a leader to the curve")


def _solve_curve_data(session):
    road = Road(session, SR)
    curves = {int(c["index"]): c for c in road.curves()}
    for name in fixture.SHEETS:
        sheet = sheet_named(session.doc, name)
        vp = _vp(sheet)
        shown = _curves_on(road, sheet)
        _curve_table(session, name, [_curve_cells(i, curves[i]) for i in shown])
        for i in shown:
            c = curves[i]
            a, b = road.shown(vp, float(c["pc_station"]), float(c["pt_station"]), step=1.0)
            _bubble(session, SR, name, (a + b) / 2.0, i)


# 4. stationing -----------------------------------------------------------------------

STATION_SHEET = "C-102"
TICK_FT = 7.0


def caltrans_lettering(station: float) -> str:
    """The whole station number at each 500 ft, otherwise the ones digit."""
    hundreds = int(round(station / 100.0))
    return str(hundreds) if hundreds % 5 == 0 else str(hundreds % 10)


def _tick_problem(view, q, d: float, fpi: float, label: str) -> Optional[str]:
    reach = AIM_FT / fpi
    near = [s for s in view.segs if not s.closed and s.distance(q) <= reach]
    want = TICK_FT / fpi
    good = [s for s in near if pl.turn_between(s.angle, d + 90.0, 180.0) <= 2.0
            and abs(s.length - want) <= 0.02 and math.dist(s.mid(), q) <= reach]
    if good:
        return None
    if not near:
        return f"no tick at {label}"
    s = min(near, key=lambda s: math.dist(s.mid(), q))
    if pl.turn_between(s.angle, d + 90.0, 180.0) > 2.0:
        return (f"the tick at {label} is not square to the line (it runs at {s.angle % 180.0:.1f}°; "
                f"square is {(d + 90.0) % 180.0:.1f}°)")
    if abs(s.length - want) > 0.02:
        return (f"the tick at {label} is {s.length:.3f} in long ({s.length * fpi:.1f} ft at plot "
                f"scale); 7 ft at 1\"={fpi:g}' is {want:.2f} in")
    return f"the tick at {label} is not centred on the centerline"


def _station_label_problem(view, q, d: float, want: str, label: str) -> Optional[str]:
    near = _nearest(view.free_texts(), q, 0.4)
    for t in near:
        if t.content.strip() != want:
            continue
        along, left = pl.offset_from(t.center(), q, d)
        if left >= 0.0:
            continue
        # along the line, or square to the sheet: either reads left to right
        level = min(pl.turn_between(t.rotation, geo.upright(d)), pl.turn_between(t.rotation, 0.0))
        if abs(along) > 0.15 or level > 3.0:
            continue
        return None
    for t in near:
        content = t.content.strip()
        if content == want:
            if pl.offset_from(t.center(), q, d)[1] >= 0.0:
                return f"{label} is lettered {want!r} above the line; station numbers go below it"
            return f"{label}'s {want!r} is not set under its tick, along the line"
        if nt.stations(content) or re.fullmatch(r"\d+(\.\d+)?", content):
            return f"{label} is lettered {content!r}; Caltrans letters it {want!r}"
    return f"{label} has no station number under it (it should read {want!r})"


def _check_stationing(baseline, submitted):
    road = Road(baseline, SR)
    sheet_b, sheet_s, view = _views(baseline, submitted, STATION_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {STATION_SHEET} is gone")
    vp = _vp(sheet_b)
    required, _optional = sheet_stations(baseline, STATION_SHEET)
    if not (view.segs or view.texts):
        return Result(False, f"nothing was added to {STATION_SHEET}")
    for st, _p, q in required:
        label = road.text(float(st))[:-3]
        d = road.paper_heading(vp, float(st))
        problem = (_tick_problem(view, q, d, vp.feet_per_inch, label)
                   or _station_label_problem(view, q, d, caltrans_lettering(st), label))
        if problem:
            return Result(False, problem)
    return Result(True, f"all {len(required)} stations {road.text(required[0][0])[:-3]} to "
                        f"{road.text(required[-1][0])[:-3]} ticked 7 ft across the line and "
                        f"lettered Caltrans-style below it")


def _solve_stationing(session):
    required, _optional = sheet_stations(session, STATION_SHEET)
    layer = _layer(session)
    for st, _p, _q in required:
        p, d = _at(session, SR, STATION_SHEET, float(st))
        run(session, "draw_line", {"space": STATION_SHEET, "layer": layer,
                                   "start": _step(p, d + 90.0, 0.07), "end": _step(p, d - 90.0, 0.07)})
        run(session, "place_text", {"space": STATION_SHEET, "layer": layer,
                                    "position": _step(p, d - 90.0, 0.10), "height": 0.08,
                                    "rotation_deg": geo.upright(d), "halign": "center",
                                    "valign": "top", "content": caltrans_lettering(st)})


# 5. width dimensions ------------------------------------------------------------------

WIDTH_SHEET = "C-101"
WIDTH_AT = 1700.0
WIDTH_NEAR_FT = 25.0
BANDS = [(-20.0, -12.0, 8.0, "left shoulder"), (-12.0, 0.0, 12.0, "left lane"),
         (0.0, 12.0, 12.0, "right lane"), (12.0, 20.0, 8.0, "right shoulder")]


def _width_value(text: str) -> Optional[float]:
    vals = nt.feet(text)
    if vals:
        return vals[0]
    return nt.number(text)


def _check_width_dims(baseline, submitted):
    road = Road(baseline, SR)
    sheet_b, sheet_s, view = _views(baseline, submitted, WIDTH_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {WIDTH_SHEET} is gone")
    vp = _vp(sheet_b)
    fpi = vp.feet_per_inch
    d = road.paper_heading(vp, WIDTH_AT)

    def where(p):
        return road.locate(vp.transform().to_model(p))

    def on_edges(p, q, lo, hi):
        a, b = where(p), where(q)
        if a is None or b is None:
            return False
        if abs(a[0] - WIDTH_AT) > WIDTH_NEAR_FT or abs(b[0] - WIDTH_AT) > WIDTH_NEAR_FT:
            return False
        offs = sorted((a[1], b[1]))
        return abs(offs[0] - lo) <= AIM_FT and abs(offs[1] - hi) <= AIM_FT

    candidates: List[List[pl.PText]] = [[] for _ in BANDS]
    notes: List[str] = []
    for i, (lo, hi, width, what) in enumerate(BANDS):
        for dim in view.dims:
            if dim.p1 is None or dim.p2 is None or not on_edges(dim.p1, dim.p2, lo, hi):
                continue
            seg = pl.PSeg(dim.p1, dim.p2)
            if pl.turn_between(seg.angle, d + 90.0, 180.0) > 3.0:
                notes.append(f"the dimension on the {what} is not measured across the road")
                continue
            value = _width_value(dim.text)
            if value is not None and abs(value - width) <= 0.5 and dim.texts:
                candidates[i].append(dim.texts[0])
            else:
                hint = (f"; a dimension on paper measures inches unless its measure_scale is the "
                        f"plot scale ({fpi:g})" if value is not None and value < 1.0 else "")
                notes.append(f"the dimension across the {what} reads {dim.text!r}, not "
                             f"{width:g}'{hint}")
        for seg in view.segs:
            if seg.closed or not on_edges(seg.a, seg.b, lo, hi):
                continue
            for t in view.free_texts():
                value = _width_value(t.content)
                if value is not None and abs(value - width) <= 0.5 and seg.distance(t.center()) <= 0.3:
                    candidates[i].append(t)
        for t in view.free_texts():
            value = _width_value(t.content)
            w = where(t.center())
            if (value is not None and abs(value - width) <= 0.5 and w is not None
                    and abs(w[0] - WIDTH_AT) <= WIDTH_NEAR_FT and lo < w[1] < hi):
                candidates[i].append(t)
    for i, (lo, hi, width, what) in enumerate(BANDS):
        if not candidates[i]:
            note = next((n for n in notes if what in n), None)
            return Result(False, note or f"the {what} ({width:g}') is not dimensioned across the "
                                         f"road at {road.text(WIDTH_AT)[:-3]}")
    pools = [c[:6] for c in candidates]
    for choice in itertools.product(*pools):
        if not any(pl.boxes_overlap(a.corners(), b.corners())
                   for a, b in itertools.combinations(choice, 2) if a is not b):
            return Result(True, f"the four widths at {road.text(WIDTH_AT)[:-3]} dimensioned across "
                                f"the road, 8' 12' 12' 8', each number clear of the others")
    for choice in itertools.product(*pools):
        for a, b in itertools.combinations(choice, 2):
            if a is not b and pl.boxes_overlap(a.corners(), b.corners()):
                return Result(False, f"the widths are there, but {_q(a.content)} and "
                                     f"{_q(b.content)} overlap; every number must be readable")
    return Result(False, "the widths are there, but their numbers overlap")


def _solve_width_dims(session):
    layer = _layer(session)
    for (lo, hi, _width, _what), station in zip(BANDS, (1680.0, 1690.0, 1710.0, 1720.0)):
        p1, _d = _at(session, SR, WIDTH_SHEET, station, lo)
        p2, _d = _at(session, SR, WIDTH_SHEET, station, hi)
        run(session, "place_dimension", {
            "space": WIDTH_SHEET, "layer": layer, "kind": "aligned", "p1": p1, "p2": p2,
            "line_point": [(p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0],
            "measure_scale": 50.0, "unit_format": "feet", "precision": 0, "arrow": "tick",
            "text_height": 0.08})


# 6. right of way line and curve data -----------------------------------------------------

ROW_SHEET = "C-102"
TAG_RE = re.compile(r"^\s*([LC])\s*-?\s*(\d+)\s*$", re.I)


@dataclass
class Piece:
    kind: str                   # "line" | "arc"
    side: str                   # "L" | "R"
    station: float
    tag: str                    # what it should be tagged, in order along the road
    length: float
    azimuth: Optional[float] = None
    radius: Optional[float] = None
    delta: Optional[float] = None
    geometry: Optional[dict] = None
    paper: Optional[List[list]] = None      # points along the part the sheet shows
    shown_length: float = 0.0


def _row_pieces(baseline: Session, sheet) -> List[Piece]:
    road = Road(baseline, SR)
    vp = _vp(sheet)
    to_paper = vp.transform().to_paper
    out = []
    for g in fixture.row_pieces(road.align):
        if g["kind"] == "line":
            pts = [[g["start"][0] + (g["end"][0] - g["start"][0]) * i / 400.0,
                    g["start"][1] + (g["end"][1] - g["start"][1]) * i / 400.0] for i in range(401)]
            dx, dy = g["end"][0] - g["start"][0], g["end"][1] - g["start"][1]
            az = (90.0 - math.degrees(math.atan2(dy, dx))) % 360.0
            piece = Piece("line", g["side"], g["station"], "", g["length"], azimuth=az, geometry=g)
        else:
            s, t = geo.arc_sweep(g["start_angle_deg"], g["end_angle_deg"])
            pts = [geo.arc_point(g["center"], g["radius"], s + (t - s) * i / 400.0) for i in range(401)]
            piece = Piece("arc", g["side"], g["station"], "", g["length"], radius=g["radius"],
                          delta=g["delta_deg"], geometry=g)
        shown = [p for p in pts if road.shows(vp, p)]
        if len(shown) < 2:
            continue
        piece.paper = [to_paper(p) for p in shown]
        piece.shown_length = piece.length * (len(shown) - 1) / 400.0
        out.append(piece)
    rights = sorted((p for p in out if p.side == "R"), key=lambda p: p.station)
    counts = {"line": 0, "arc": 0}
    for p in rights:
        counts[p.kind] += 1
        p.tag = f"{'L' if p.kind == 'line' else 'C'}{counts[p.kind]}"
    return out


def _paper_distance(points: Sequence[list], q) -> float:
    return min(math.dist(p, q) for p in points)


def _roadway_paper(baseline: Session, sheet) -> List[list]:
    """Paper points along the referenced centerline, edges and shoulders."""
    vp = _vp(sheet)
    out = []
    for _ref, _base, prims in reference_groups(baseline.doc, "model"):
        for e in prims:
            if e.layer not in ("V-ALIGN-CNTR", "V-ROAD-EOP", "V-ROAD-SHLD"):
                continue
            if isinstance(e, Line):
                pts = [[e.start[0] + (e.end[0] - e.start[0]) * i / 200.0,
                        e.start[1] + (e.end[1] - e.start[1]) * i / 200.0] for i in range(201)]
            elif hasattr(e, "radius") and hasattr(e, "start_angle_deg"):
                s, t = geo.arc_sweep(e.start_angle_deg, e.end_angle_deg)
                pts = [geo.arc_point(e.center, e.radius, s + (t - s) * i / 200.0) for i in range(201)]
            else:
                continue
            out += [vp.transform().to_paper(p) for p in pts if viewmap.shows(vp, p)]
    return out


def _tag_rows(view: pl.Plot) -> Dict[str, List[Tuple[List[str], List[Optional[str]]]]]:
    """Table rows keyed by the tag in their first cell, with column keys."""
    rows: Dict[str, List[Tuple[List[str], List[Optional[str]]]]] = {}

    def key(header: str) -> Optional[str]:
        h = re.sub(r"[^A-ZΔ]", "", re.sub(r"\(.*?\)", "", header.upper()))
        if h in ("TAG", "LINE", "CURVE", "NO", "NUMBER", "SEGMENT", "COURSE", "ID"):
            return "tag"
        if h in ("BEARING", "BRG", "DIRECTION", "BEARINGS"):
            return "bearing"
        if h in ("LENGTH", "DISTANCE", "DIST", "L", "LEN", "ARCLENGTH", "ARC"):
            return "length"
        if h in ("RADIUS", "R", "RAD"):
            return "radius"
        if h in ("DELTA", "Δ", "D", "CENTRALANGLE"):
            return "delta"
        return None

    for t in view.tables:
        keys = [key(h) for h in t.headers]
        for cells in t.rows:
            m = TAG_RE.match(cells[0]) if cells else None
            if m:
                rows.setdefault(f"{m.group(1).upper()}{int(m.group(2))}", []).append((cells, keys))
    for cells in pl.text_rows(view.free_texts()):
        head = cells[0].split()[0] if cells and cells[0].split() else ""
        m = TAG_RE.match(head)
        if m and (len(cells) > 1 or len(cells[0].split()) > 1):
            rows.setdefault(f"{m.group(1).upper()}{int(m.group(2))}", []).append((cells, []))
    return rows


def _line_row_ok(cells: List[str], keys, p: Piece) -> Optional[str]:
    by = {k: c for k, c in zip(keys, cells) if k}
    joined = "  ".join(cells[1:])
    brgs = nt.bearings(by.get("bearing", joined))
    if not any(nt.azimuth_close(b, p.azimuth, either_way=True) for b in brgs):
        return f"{p.tag}'s bearing reads {_q(by.get('bearing', joined))}"
    if "length" in by:
        lengths = nt.feet(by["length"]) or [nt.number(by["length"])]
    else:
        lengths = nt.feet(joined)
    if not any(v is not None and abs(v - p.length) <= VALUE_FT for v in lengths):
        if any(v is not None and abs(v - p.shown_length) <= 0.6 for v in lengths):
            return (f"{p.tag}'s length is the part this sheet shows; the whole line is "
                    f"{p.length:.2f}'")
        return f"{p.tag}'s length reads {_q(by.get('length', joined))}; it is {p.length:.2f}'"
    return None


def _arc_row_ok(cells: List[str], keys, p: Piece, centerline: Dict[str, float]) -> Optional[str]:
    by = {k: c for k, c in zip(keys, cells) if k}
    if {"radius", "delta", "length"} <= set(by):
        radius = nt.number(by["radius"])
        dl = nt.angles(by["delta"])
        delta = dl[0] if dl else None
        length = nt.number(by["length"])
    else:
        rest = "  ".join(cells[1:]) if len(cells) > 1 else cells[0].split(None, 1)[-1]
        dl = nt.angles(rest)
        delta = dl[0] if dl else None
        nums = [float(m.group(0).replace(",", "")) for m in
                re.finditer(r"\d[\d,]*(?:\.\d+)?", nt.DMS_RE.sub(" ", rest))]
        radius = nums[0] if nums else None
        length = nums[1] if len(nums) > 1 else None
    if radius is None or abs(radius - p.radius) > VALUE_FT:
        hint = ""
        if radius is not None and any(abs(radius - v) <= 0.5 for v in centerline.values()):
            hint = " (that is the centerline's radius; the right of way is offset from it)"
        return f"{p.tag}'s radius reads {radius!r}; it is {p.radius:.2f}'{hint}"
    if delta is None or not nt.azimuth_close(delta, p.delta):
        return f"{p.tag}'s delta reads {delta!r}"
    if length is None or abs(length - p.length) > VALUE_FT:
        if length is not None and abs(length - p.shown_length) <= 0.6:
            return (f"{p.tag}'s length is the part this sheet shows; the whole curve is "
                    f"{p.length:.2f}'")
        return f"{p.tag}'s length reads {length!r}; it is {p.length:.2f}'"
    return None


def _check_row_data(baseline, submitted):
    sheet_b, sheet_s, view = _views(baseline, submitted, ROW_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {ROW_SHEET} is gone")
    pieces = _row_pieces(baseline, sheet_b)
    rights = [p for p in pieces if p.side == "R"]
    roadway = _roadway_paper(baseline, sheet_b)
    tags = [(t, TAG_RE.match(t.content)) for t in view.free_texts()]
    tags = [(t, f"{m.group(1).upper()}{int(m.group(2))}") for t, m in tags if m]
    if not tags:
        return Result(False, f"no L1/C1 tags on {ROW_SHEET}")
    tagged: Dict[int, List[str]] = {}
    for t, tag in tags:
        c = t.center()
        dists = [(_paper_distance(p.paper, c), i) for i, p in enumerate(pieces)]
        best_d, best_i = min(dists)
        road_d = _paper_distance(roadway, c) if roadway else math.inf
        if road_d < best_d:
            return Result(False, f"the tag {tag} sits nearer the roadway than any right of way line")
        if best_d > 0.5:
            return Result(False, f"the tag {tag} is {best_d:.2f} in from the nearest right of way "
                                 f"line; set it beside its piece")
        p = pieces[best_i]
        if p.side != "R":
            return Result(False, f"the tag {tag} is on the left right of way line; the task is the "
                                 f"right-hand one")
        tagged.setdefault(best_i, []).append(tag)
    order = ", ".join(p.tag for p in rights)
    for p in rights:
        i = pieces.index(p)
        got = tagged.get(i, [])
        if not got:
            what = "jog" if p.kind == "line" and p.length < 50 else p.kind
            return Result(False, f"the right of way {what} at {Road(baseline, SR).text(p.station)} "
                                 f"({p.length:.2f}') has no tag")
        if len(got) > 1:
            return Result(False, f"one piece is tagged twice: {', '.join(got)}")
        if got[0] != p.tag:
            return Result(False, f"the piece tagged {got[0]} should be {p.tag}: along SR-100 the "
                                 f"pieces this sheet shows run {order}")
    rows = _tag_rows(view)
    road = Road(baseline, SR)
    centerline = {c["ref"]: float(c["radius"]) for c in road.curves()}
    for p in rights:
        mine = rows.get(p.tag, [])
        if not mine:
            return Result(False, f"{p.tag} has no row in a {'LINE' if p.kind == 'line' else 'CURVE'} "
                                 f"TABLE")
        problems = [(_line_row_ok(c, k, p) if p.kind == "line" else _arc_row_ok(c, k, p, centerline))
                    for c, k in mine]
        if all(x is not None for x in problems):
            return Result(False, problems[0])
    return Result(True, f"all {len(rights)} pieces of the right of way tagged in order ({order}) "
                        f"and tabulated with their full bearings, lengths, radii and deltas")


def _solve_row_data(session):
    sheet = sheet_named(session.doc, ROW_SHEET)
    vp = _vp(sheet)
    road = Road(session, SR)
    layer = _layer(session)
    rights = [p for p in _row_pieces(session, sheet) if p.side == "R"]
    lines, arcs = [], []
    for p in rights:
        mid = p.paper[len(p.paper) // 2]
        host = vp.transform().to_model(mid)
        st, _off = road.locate(host)
        d = road.paper_heading(vp, st)
        # outside the right of way, or ahead of a jog, which runs across the road
        pos = _step(mid, d - 90.0, 0.14) if p.kind == "arc" or p.length > 50 else _step(mid, d, 0.14)
        run(session, "place_text", {"space": ROW_SHEET, "layer": layer, "position": pos,
                                    "content": p.tag, "height": 0.10, "halign": "center",
                                    "valign": "middle"})
        if p.kind == "line":
            g = p.geometry
            r = session.query("measure", {"from": g["start"], "to": g["end"]})
            lines.append([p.tag, r["bearing"], f"{p.length:.2f}'"])
        else:
            arcs.append([p.tag, f"{p.radius:.2f}'", _dms(p.delta), f"{p.length:.2f}'"])
    run(session, "place_table", {"space": ROW_SHEET, "layer": layer, "position": [24.0, 7.2],
                                 "title": "LINE TABLE",
                                 "columns": [{"header": "TAG", "width": 0.6},
                                             {"header": "BEARING", "width": 1.6},
                                             {"header": "LENGTH", "width": 1.0}],
                                 "rows": lines, "text_height": 0.10})
    run(session, "place_table", {"space": ROW_SHEET, "layer": layer, "position": [28.0, 7.2],
                                 "title": "CURVE TABLE",
                                 "columns": [{"header": "TAG", "width": 0.6},
                                             {"header": "RADIUS", "width": 1.0},
                                             {"header": "DELTA", "width": 1.2},
                                             {"header": "LENGTH", "width": 1.0}],
                                 "rows": arcs, "text_height": 0.10})


def _dms(deg: float) -> str:
    total = round(deg * 3600.0)
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{d}°{m:02d}'{s:02d}\""


# 7. a station equation ------------------------------------------------------------------

EQ_SHEET = "C-102"
PAIR_RE = re.compile(r"(\d+\+\d{2}\.\d{2})\s*(BK|AH)\b|\b(BK|AH)\s*(?:STA\.?\s*)?(\d+\+\d{2}\.\d{2})", re.I)


def _pairs(text: str) -> List[Tuple[float, str]]:
    out = []
    for m in PAIR_RE.finditer(text.upper()):
        sta, word = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        out.append((nt.stations(sta)[0][0], word))
    return out


def _check_equation(baseline, submitted):
    road = Road(baseline, SR)
    sheet_b, sheet_s, view = _views(baseline, submitted, EQ_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {EQ_SHEET} is gone")
    vp = _vp(sheet_b)
    eq = _rows(baseline, SR, "equations")[0]
    raw = float(eq["raw_station"])
    point, d = road.paper(vp, raw), road.paper_heading(vp, raw)
    back, ahead = float(eq["back"]), float(eq["ahead"])
    lettered = [t for t in view.free_texts() if _pairs(t.content)
                and _square_problem(t, point, d, True, None) is None]
    pairs = {p for t in lettered for p in _pairs(t.content)}
    if (back, "BK") not in pairs or (ahead, "AH") not in pairs:
        truth = f"{eq['back_text']} BK = {eq['ahead_text']} AH"
        near = [t for t in view.free_texts() if _pairs(t.content)]
        if not near:
            return Result(False, f"no lettering gives the equation {truth} at its point")
        problem = _square_problem(near[0], point, d, True, None)
        if problem:
            return Result(False, f"the equation: {problem}")
        return Result(False, f"the equation reads {_q(near[0].content)}; it is {truth}")
    t2 = next(t for t in road.tangents() if t["ref"] == "T-2")
    span = road.shown(vp, float(t2["start_station"]), float(t2["end_station"]))
    problem = _line_data_problem(view, road, vp, t2, span[0], span[1], side=1)
    if problem:
        spread = road.display(float(t2["end_station"])) - road.display(float(t2["start_station"]))
        if f"{spread:.2f}" in problem or any(abs(v - spread) <= VALUE_FT for t in view.free_texts()
                                             for v in nt.feet(t.content)):
            problem = (f"{spread:.2f}' is the difference of its stations across the equation; the "
                       f"tangent is {float(t2['length']):.2f}' long")
        return Result(False, f"T-2: {problem}")
    c2 = next(c for c in road.curves() if int(c["index"]) == 2)
    raw_bc = float(c2["pc_station"])
    problem = _point_problem(view, "BC", road.display(raw_bc), road.paper(vp, raw_bc),
                             road.paper_heading(vp, raw_bc), True, None)
    if problem:
        if any(nt.has_station(t.content, raw_bc) for t in view.free_texts()):
            problem = (f"it is lettered {int(raw_bc // 100)}+{raw_bc % 100:05.2f}, its station "
                       f"without the equation; ahead of {eq['back_text']} BK = {eq['ahead_text']} "
                       f"AH it is {c2['pc_station_text']}")
        return Result(False, f"the BC of curve 2: {problem}")
    spread = road.display(float(t2["end_station"])) - road.display(float(t2["start_station"]))
    return Result(True, f"the equation {eq['back_text']} BK = {eq['ahead_text']} AH lettered at its "
                        f"point, T-2 at {float(t2['length']):.2f}' (not the {spread:.2f}' its "
                        f"stations differ by), and the BC at {c2['pc_station_text']}")


def _solve_equation(session):
    road = Road(session, SR)
    eq = _rows(session, SR, "equations")[0]
    raw = float(eq["raw_station"])
    _letter_point(session, SR, EQ_SHEET, raw,
                  f"{eq['back_text']} BK = {eq['ahead_text']} AH")
    sheet = sheet_named(session.doc, EQ_SHEET)
    vp = _vp(sheet)
    t2 = next(t for t in road.tangents() if t["ref"] == "T-2")
    a, b = road.shown(vp, float(t2["start_station"]), float(t2["end_station"]))
    # letter the tangent between the equation and the curve, clear of the equation
    _letter_tangent(session, SR, EQ_SHEET, t2, raw + 150.0, b)
    c2 = next(c for c in road.curves() if int(c["index"]) == 2)
    _letter_point(session, SR, EQ_SHEET, float(c2["pc_station"]), f"{c2['pc_station_text']} BC")


# 8. QA the alignment data -----------------------------------------------------------------

QA_PLANTS = [
    {"sheet": "C-101", "was": "24+05.27 BC", "now": "24+50.27 BC",
     "what": "the BC of curve 1 lettered 24+50.27 (digits transposed)"},
    {"sheet": "C-102", "was": "1240.36'", "now": "1581.14'",
     "what": "T-2's length lettered 1581.14', the PI-to-PI distance"},
    {"sheet": "C-102", "table": 2, "swap": True,
     "what": "T and L swapped in curve 2's row of the curve table"},
    {"sheet": "C-103", "renumber": (2, 1),
     "what": "curve 2 numbered 1 in the table and its bubble (numbering restarted)"},
    {"sheet": "C-103", "was": "43+21.30 EC", "now": "43+21.30 BC",
     "what": "the EC of curve 2 lettered BC"},
]


def letter_alignment_data(session: Session):
    """The scripted lettering of line-data, curve-points and curve-data: the
    finished sheets the QA probe starts from."""
    _solve_line_data(session)
    _solve_curve_points(session)
    _solve_curve_data(session)


def _sheet_texts(session: Session, name: str) -> List[Text]:
    sheet = sheet_named(session.doc, name)
    return [e for e in sheet.entities.values() if isinstance(e, Text)]


def _sheet_tables(session: Session, name: str) -> List[Table]:
    sheet = sheet_named(session.doc, name)
    return [e for e in sheet.entities.values() if isinstance(e, Table)]


def plant_qa_errors(session: Session):
    for plant in QA_PLANTS:
        name = plant["sheet"]
        if "was" in plant:
            t = next(t for t in _sheet_texts(session, name) if plant["was"] in t.content)
            run(session, "modify_entity", {"id": t.id, "changes": {
                "content": t.content.replace(plant["was"], plant["now"])}})
        elif plant.get("swap"):
            table = _sheet_tables(session, name)[0]
            rows = [list(r) for r in table.rows]
            for r in rows:
                if r[0] == str(plant["table"]):
                    r[3], r[4] = r[4], r[3]
            run(session, "modify_entity", {"id": table.id, "changes": {"rows": rows}})
        elif "renumber" in plant:
            old, new = plant["renumber"]
            table = _sheet_tables(session, name)[0]
            rows = [[str(new) if i == 0 and c == str(old) else c for i, c in enumerate(r)]
                    for r in table.rows]
            run(session, "modify_entity", {"id": table.id, "changes": {"rows": rows}})
            t = next(t for t in _sheet_texts(session, name) if t.content == str(old))
            run(session, "modify_entity", {"id": t.id, "changes": {"content": str(new)}})


def qa_planted(baseline: Session) -> Dict[str, set]:
    """Ids of what the plants touched, per sheet: the edited texts, the
    tables, and the whole renumbered bubble (circle, number and leader)."""
    out: Dict[str, set] = {}
    for plant in QA_PLANTS:
        name = plant["sheet"]
        ids = out.setdefault(name, set())
        if "now" in plant:
            ids |= {t.id for t in _sheet_texts(baseline, name) if plant["now"] in t.content}
        else:
            ids |= {t.id for t in _sheet_tables(baseline, name)}
        if "renumber" in plant:
            _old, new = plant["renumber"]
            sheet = sheet_named(baseline.doc, name)
            number = next(t for t in _sheet_texts(baseline, name) if t.content == str(new))
            ids.add(number.id)
            for e in sheet.entities.values():
                if isinstance(e, Circle) and math.dist(e.center, number.position) < 0.05:
                    ids.add(e.id)
                    ids |= {f.id for f in sheet.entities.values() if isinstance(f, Line)
                            and min(math.dist(f.start, e.center), math.dist(f.end, e.center))
                            <= e.radius + 0.01}
    return out


def _same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, Text):
        return (a.content.strip() == b.content.strip() and math.dist(a.position, b.position) <= 0.05
                and pl.turn_between(a.rotation_deg, b.rotation_deg) <= 0.5)
    if isinstance(a, Line):
        return ((math.dist(a.start, b.start) <= 0.05 and math.dist(a.end, b.end) <= 0.05)
                or (math.dist(a.start, b.end) <= 0.05 and math.dist(a.end, b.start) <= 0.05))
    if isinstance(a, Circle):
        return math.dist(a.center, b.center) <= 0.05 and abs(a.radius - b.radius) <= 0.01
    if isinstance(a, Table):
        return ([[c.strip() for c in r] for r in a.rows] == [[c.strip() for c in r] for r in b.rows]
                and math.dist(a.position, b.position) <= 0.05)
    return a.to_dict() == b.to_dict()


def _describe(e) -> str:
    if isinstance(e, Text):
        return f"the text {_q(e.content)}"
    if isinstance(e, Table):
        return f"the table {_q(e.title or 'table')}"
    return f"a {type(e).__name__.lower()}"


def _check_qa(baseline, submitted):
    road = Road(baseline, SR)
    planted = qa_planted(baseline)
    numbering = {int(c["index"]): int(c["index"]) for c in road.curves()}
    for name in fixture.SHEETS:
        sheet_b, sheet_s, view = _views(baseline, submitted, name, added_only=False)
        if sheet_s is None:
            return Result(False, f"sheet {name} is gone")
        vp = _vp(sheet_b)
        for t, a, b, _vp_ in _tangents_on(road, sheet_b):
            problem = _line_data_problem(view, road, vp, t, a, b, side=1)
            if problem:
                return Result(False, f"{t['ref']} on {name}: {problem}")
        for word, raw, refs in _points_on(road, sheet_b):
            problem = _point_problem(view, word, road.display(raw), road.paper(vp, raw),
                                     road.paper_heading(vp, raw))
            if problem:
                return Result(False, f"the {word} at {road.text(raw)} on {name}: {problem}")
        problem = _curve_data_problem(view, road, sheet_b, name, numbering)
        if problem:
            return Result(False, problem)
        for plant in QA_PLANTS:
            if plant["sheet"] == name and "now" in plant:
                wrong = [t for t in view.free_texts() if plant["now"] in t.content]
                if wrong:
                    return Result(False, f"{name} still letters {_q(wrong[0].content)}")
        bubbles = _bubbles(view)
        shown = {numbering[i] for i in _curves_on(road, sheet_b)}
        stray = sorted({n for _b, n in bubbles if n is not None and n not in shown})
        if stray:
            return Result(False, f"{name} still has a bubble numbered "
                                 f"{', '.join(map(str, stray))}, a curve it does not show")
        for e in sheet_b.entities.values():
            if e.id in planted.get(name, set()):
                continue
            mine = sheet_s.entities.get(e.id)
            if mine is not None and _same(e, mine):
                continue
            if any(_same(e, f) for f in sheet_s.entities.values()):
                continue
            return Result(False, f"{_describe(e)} on {name} was changed or removed, and it was right")
        counts: Dict[str, int] = {}
        for t in view.free_texts():
            key = " ".join(t.content.split())
            counts[key] = counts.get(key, 0) + 1
        doubled = [k for k, n in counts.items() if n > 1]
        if doubled:
            return Result(False, f"{name} letters {_q(doubled[0])} twice")
        if len(view.tables) > 1:
            return Result(False, f"{name} has {len(view.tables)} curve tables")
    return Result(True, "all five planted errors corrected (BC station, T-2 length, curve 2's T and "
                        "L, the restarted curve number, the EC lettered BC) and nothing else touched")


def _solve_qa(session):
    for plant in QA_PLANTS:
        name = plant["sheet"]
        if "was" in plant:
            t = next(t for t in _sheet_texts(session, name) if plant["now"] in t.content)
            run(session, "modify_entity", {"id": t.id, "changes": {
                "content": t.content.replace(plant["now"], plant["was"])}})
        elif plant.get("swap"):
            table = _sheet_tables(session, name)[0]
            rows = [list(r) for r in table.rows]
            for r in rows:
                if r[0] == str(plant["table"]):
                    r[3], r[4] = r[4], r[3]
            run(session, "modify_entity", {"id": table.id, "changes": {"rows": rows}})
        elif "renumber" in plant:
            old, new = plant["renumber"]
            table = _sheet_tables(session, name)[0]
            rows = [[str(old) if i == 0 and c == str(new) else c for i, c in enumerate(r)]
                    for r in table.rows]
            run(session, "modify_entity", {"id": table.id, "changes": {"rows": rows}})
            t = next(t for t in _sheet_texts(session, name) if t.content == str(new))
            run(session, "modify_entity", {"id": t.id, "changes": {"content": str(old)}})


# 9 and 10. Caltrans L-2 ------------------------------------------------------------------

L2_SHEET = "L-2"
MATCH = [(57450.0, "L-1"), (58950.0, "L-3")]
MATCH_REACH_FT = 40.0
#: L-2's curves continue the line's numbering from L-1, which ends with curve 1
L2_FIRST_CURVE = 2


def _match_problem(view, road: Road, vp, station: float, sheet_tag: str) -> Optional[str]:
    q, d = road.paper(vp, station), road.paper_heading(vp, station)
    fpi = vp.feet_per_inch
    label = road.text(station)
    near = [s for s in view.segs if not s.closed and s.distance(q) <= AIM_FT / fpi]
    good = []
    for s in near:
        if pl.turn_between(s.angle, d + 90.0, 180.0) > TURN_DEG:
            continue
        lefts = [pl.offset_from(p, q, d)[1] * fpi for p in (s.a, s.b)]
        if min(lefts) <= -MATCH_REACH_FT and max(lefts) >= MATCH_REACH_FT:
            good.append(s)
    if not good:
        if not near:
            return f"no match line crosses \"SR70\" at {label}"
        s = max(near, key=lambda s: s.length)
        if pl.turn_between(s.angle, d + 90.0, 180.0) > TURN_DEG:
            model_square = pl.wrap(road.heading(station) + 90.0)
            hint = (" (square to the line in the model, but the viewport is turned "
                    f"{vp.rotation_deg:+.3f}°)" if pl.turn_between(s.angle, model_square, 180.0) <= TURN_DEG
                    else "")
            return (f"the match line at {label} runs at {s.angle % 180.0:.2f}° on the sheet; square "
                    f"to \"SR70\" there is {(d + 90.0) % 180.0:.2f}°{hint}")
        lefts = [pl.offset_from(p, q, d)[1] * fpi for p in (s.a, s.b)]
        return (f"the match line at {label} reaches {min(lefts):.0f} ft to {max(lefts):.0f} ft "
                f"from the centerline; it should run at least {MATCH_REACH_FT:g} ft past it on both sides")
    line = good[0]
    for t in view.free_texts():
        if not (nt.has_word(t.content, "MATCH") and nt.has_word(t.content, "LINE")):
            continue
        if line.distance(t.center()) > 0.5:
            continue
        tag = re.search(r"\bL\s*-\s*(\d+)\b", t.content.upper())
        if tag and f"L-{tag.group(1)}" != sheet_tag:
            return (f"the match line at {label} reads {_q(t.content)}: back of it is {MATCH[0][1]}, "
                    f"ahead of it {MATCH[1][1]}")
        if not tag:
            continue
        if pl.turn_between(t.rotation, line.angle, 180.0) > 2.0:
            return f"{_q(t.content)} is not lettered along its match line"
        return None
    return f"the match line at {label} is not lettered MATCH LINE ({sheet_tag})"


def _check_match_lines(baseline, submitted):
    road = Road(baseline, SR70)
    sheet_b, sheet_s, view = _views(baseline, submitted, L2_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {L2_SHEET} is gone")
    vp = _vp(sheet_b)
    for station, tag in MATCH:
        problem = _match_problem(view, road, vp, road.align.stations().parse(station), tag)
        if problem:
            return Result(False, problem)
    return Result(True, "both match lines square to \"SR70\" on the turned sheet at 574+50 and "
                        "589+50, across the roadway, lettered MATCH LINE (L-1) and (L-3)")


def _solve_match_lines(session):
    layer = _layer(session)
    for station, tag in MATCH:
        a, d = _at(session, SR70, L2_SHEET, station, -95.0)
        b, _d = _at(session, SR70, L2_SHEET, station, 89.0)
        run(session, "draw_line", {"space": L2_SHEET, "layer": layer, "start": a, "end": b})
        p, d = _at(session, SR70, L2_SHEET, station, 60.0 if tag == "L-1" else -60.0)
        rot = geo.reading_up(d + 90.0)
        run(session, "place_text", {"space": L2_SHEET, "layer": layer,
                                    "position": _step(p, d + (180.0 if tag == "L-1" else 0.0), 0.08),
                                    "rotation_deg": rot, "height": 0.14, "halign": "center",
                                    "valign": "bottom" if tag == "L-1" else "top",
                                    "content": f"MATCH LINE ({tag})"})


def _l2_numbering(road: Road) -> Dict[int, int]:
    return {int(c["index"]): int(c["index"]) + L2_FIRST_CURVE - 1 for c in road.curves()}


def _l2_shown_points(road: Road, vp) -> List[Tuple[str, float, str]]:
    return [(w, raw, refs) for w, raw, refs in road.curve_points()
            if road.shows(vp, road.model(raw), 0.1)]


def _reference_texts(session: Session, sheet) -> List[pl.PText]:
    """Lettering a referenced design shows through the sheet's viewports."""
    out = []
    for vp in sheet.viewports:
        fn, turn, k = vp.transform().to_paper, float(vp.rotation_deg), 1.0 / vp.feet_per_inch
        for _ref, base, prims in reference_groups(session.doc, "model"):
            for e in prims:
                if not isinstance(e, Text):
                    continue
                t = e.transformed(fn, turn, k)
                if viewmap.in_window(vp, t.position):
                    out.append(pl.PText(t.content, list(t.position), float(t.rotation_deg),
                                        float(t.height), t.halign, t.valign, 1.0, e.id, "model"))
    return out


def _check_l2_data(baseline, submitted):
    road = Road(baseline, SR70)
    sheet_b, sheet_s, view = _views(baseline, submitted, L2_SHEET)
    if sheet_s is None:
        return Result(False, f"sheet {L2_SHEET} is gone")
    vp = _vp(sheet_b)
    numbering = _l2_numbering(road)
    for t, a, b, _vp_ in _tangents_on(road, sheet_b):
        problem = _line_data_problem(view, road, vp, t, a, b, side=None, near=0.6, split=True)
        if problem:
            model_dir = geo.upright(road.heading((a + b) / 2.0))
            if any(pl.turn_between(x.rotation, model_dir) <= TURN_DEG for x in view.free_texts()
                   if nt.bearings(x.content) or nt.feet(x.content)):
                problem += (f" (it is parallel to the line in the model; the viewport is turned "
                            f"{vp.rotation_deg:+.3f}°)")
            return Result(False, f"the tangent {road.text(a)} to {road.text(b)}: {problem}")
    for word, raw, refs in _l2_shown_points(road, vp):
        problem = _point_problem(view, word, road.display(raw), road.paper(vp, raw),
                                 road.paper_heading(vp, raw), reading_up=False, side=None,
                                 band=0.04)
        if problem:
            return Result(False, f"the {word} at {road.text(raw)}: {problem}")
    problem = _curve_data_problem(view, road, sheet_b, L2_SHEET, numbering)
    if problem:
        rows = _curve_rows(view)
        if rows and {r.number for r in rows} == {i for i in numbering}:
            problem = (f"the table numbers the curves {', '.join(str(i) for i in sorted(numbering))}, "
                       f"the design's own indices; this sheet continues from L-1, whose last curve "
                       f"is 1, so they are {', '.join(str(n) for n in sorted(numbering.values()))}")
        return Result(False, problem)
    others = _reference_texts(baseline, sheet_b)
    others += pl.plot(baseline, sheet_b, [(sheet_b.id, e) for e in sheet_b.entities.values()]).texts
    mine = view.free_texts() + [d for dim in view.dims for d in dim.texts]
    boxes = [(t.corners(), _q(t.content)) for t in mine]
    boxes += [([[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]], "the curve table")
              for b in {tb.box for tb in view.tables}]
    for quad, what in boxes:
        hit = next((o for o in others if pl.boxes_overlap(quad, o.corners())), None)
        if hit is not None:
            return Result(False, f"{what} overlaps the sheet's {_q(hit.content)}")
    for (qa, wa), (qb, wb) in itertools.combinations(boxes, 2):
        if wa != wb and pl.boxes_overlap(qa, qb):
            return Result(False, f"{wa} overlaps {wb}")
    return Result(True, "L-2's alignment data restored: both tangents with bearing and length "
                        "parallel to the turned line, five curve points including the PCC, bubbles "
                        "2 to 5 on their curves, the curve table 2 to 5, and no lettering over "
                        "lettering")


def _solve_l2_data(session):
    road = Road(session, SR70)
    sheet = sheet_named(session.doc, L2_SHEET)
    vp = _vp(sheet)
    numbering = _l2_numbering(road)
    curves = {int(c["index"]): c for c in road.curves()}
    for t, a, b, _vp_ in _tangents_on(road, sheet):
        mid = (a + b) / 2.0
        _letter_tangent(session, SR70, L2_SHEET, t, mid - 40.0, mid + 40.0)
    for word, raw, _refs in _l2_shown_points(road, vp):
        _letter_point(session, SR70, L2_SHEET, raw, f'"SR70" {road.text(raw)} {word}', out=1.1)
    shown = _curves_on(road, sheet)
    _curve_table(session, L2_SHEET, [_curve_cells(numbering[i], curves[i]) for i in shown],
                 position=(3.923, 4.09))
    for i in shown:
        c = curves[i]
        a, b = road.shown(vp, float(c["pc_station"]), float(c["pt_station"]), step=1.0)
        _bubble(session, SR70, L2_SHEET, (a + b) / 2.0, numbering[i], rise=1.6)


# ------------------------------------------------------------------- the probes

TIER3_PROBES: List[Probe] = [
    Probe(id="line-data", start="sheets", tags=["tier3", "paper", "alignment-data", "line"],
          prompt="On sheets C-101 through C-103, letter the line data of SR-100. For every "
                 "tangent, on the sheet that shows it, letter its bearing and its length as one "
                 "line of text, for example N 45°00'00\" E 1234.56'. Set it just above the "
                 "centerline and parallel to it, reading left to right, clear of all linework.",
          check=_check_line_data, solve=_solve_line_data,
          note="Three tangents, one per sheet: T-1 N 90°00'00\" E 1405.27', T-2 N 71°33'54\" E "
               "1240.36', T-3 N 90°00'00\" E 1353.95'. The traps are the PI-to-PI distances "
               "(1600.00, 1581.14, 1500.00), the back bearing, text below the line or across the "
               "edge of pavement 0.24 in away, and a label on a sheet that does not show the tangent."),
    Probe(id="curve-points", start="sheets", tags=["tier3", "paper", "alignment-data", "station"],
          prompt="On sheets C-101 through C-103, letter the station of every curve point of SR-100 "
                 "that the sheet shows, each BC and each EC, the Caltrans way. Give the station to "
                 "the hundredth followed by BC or EC (12+34.56 BC). Letter it along the line square "
                 "to the centerline through that point, on the left of the centerline, reading "
                 "bottom to top.",
          check=_check_curve_points, solve=_solve_curve_points,
          note="Four points: 24+05.27 BC on C-101, 27+91.37 EC and 40+31.72 BC on C-102, 43+21.30 "
               "EC on C-103. Where the line climbs to the right (PT-1, PC-2) bottom to top is "
               "108.43°; text folded upright to -71.57° reads top to bottom and fails. So does "
               "24+05 for 24+05.27, and text that covers its point."),
    Probe(id="curve-data", start="sheets", tags=["tier3", "paper", "alignment-data", "curve", "table"],
          prompt="Add SR-100's curve data to sheets C-101 through C-103. On each sheet, place a "
                 "CURVE DATA table with columns No., R, Δ, T and L listing every curve that sheet "
                 "shows. On the plan, mark each of those curves with its number in a circle, with "
                 "a leader to the curve. Number the curves 1, 2, … in order along SR-100; a curve "
                 "keeps its number on every sheet. Keep the table clear of the roadway.",
          check=_check_curve_data, solve=_solve_curve_data,
          note="C-101 shows curve 1, C-102 both, C-103 curve 2. Curve 1: R 1200', Δ 18°26'06\", "
               "T 194.73', L 386.10'; curve 2: R 900', T 146.05', L 289.58'. Fails: both curves on "
               "every sheet, C-103's curve renumbered 1, E or M in the T column, Δ in decimal "
               "degrees, a bubble leader short of the arc."),
    Probe(id="stationing", start="sheets", tags=["tier3", "paper", "alignment-data", "loop"],
          prompt="Station SR-100 on sheet C-102 the Caltrans way, at every 100 ft station the sheet "
                 "shows. Draw a tick 7 ft long at plot scale across the centerline, square to it "
                 "and centred on it. Below the line, letter the whole station number at multiples "
                 "of 500 ft (30, 35, 40) and only the ones digit elsewhere (6, 7, 8, 9, 1, 2, …), "
                 "reading left to right.",
          check=_check_stationing, solve=_solve_stationing,
          note="Sixteen stations, 26+00 to 41+00; 41+00 is on curve 2, so its tick is radial. A "
               "7 ft tick is 0.14 in on paper. Fails: 26+00 lettering, whole numbers everywhere, "
               "labels above the line, 7 in or 14 ft ticks."),
    Probe(id="width-dims", start="sheets", tags=["tier3", "paper", "dimension"],
          prompt="On sheet C-101 at SR-100 station 17+00, dimension the roadway across, from "
                 "outside edge of shoulder to outside edge of shoulder: the left shoulder, the two "
                 "lanes and the right shoulder, each reading its width in feet (8', 12', 12', 8'). "
                 "Every number must be readable: no two may overlap.",
          check=_check_width_dims, solve=_solve_width_dims,
          note="A dimension drawn on paper reads inches (0.24, 0.16) unless measure_scale is the "
               "plot scale, 50. The spans are 0.24 in and 0.16 in, so the engine puts each number "
               "outside its extension lines and four at one station collide: stagger them, or "
               "letter the widths in their bands."),
    Probe(id="row-data", start="sheets-row", tags=["tier3", "paper", "line", "curve", "table"],
          prompt="The right of way of SR-100 is drawn on V-ROW in the design file. On sheet C-102, "
                 "letter the line and curve data of the right-hand right of way line (right of the "
                 "stationing direction) the way a right of way map does. Tag each straight piece "
                 "the sheet shows L1, L2, … and each curved piece C1, C2, …, numbered in order "
                 "along SR-100 and set beside its piece. Add a LINE TABLE (tag, bearing, length) "
                 "and a CURVE TABLE (tag, radius, delta, length) giving each piece's full geometry, "
                 "not just the part on this sheet.",
          check=_check_row_data, solve=_solve_row_data,
          note="Seven pieces: C1 R 1250.00' L 402.19', L1 208.63', the jog L2 S 18°26'06\" E 30.00', "
               "L3 600.00', the jog back L4 30.00', L5 431.72', C2 R 850.00' L 273.49'. The lines "
               "are raw linework with no design data: measure gives their bearings. Fails: the "
               "centerline's radii, the visible length, the left line, a jog left untagged."),
    Probe(id="equation-data", start="sheets-eq", tags=["tier3", "paper", "alignment-data", "station"],
          prompt="SR-100 has a station equation, on sheet C-102. On that sheet, letter it the "
                 "Caltrans way, with its back and ahead stations to the hundredth and BK and AH, "
                 "square to the centerline at the equation and reading bottom to top. Then letter "
                 "the bearing and length of the tangent it falls on, above the line and parallel "
                 "to it, and the station of the BC of the next curve, lettered the way the "
                 "equation is.",
          check=_check_equation, solve=_solve_equation,
          note="35+00.00 BK = 35+50.00 AH on T-2. T-2 is 1240.36' long though its stations differ "
               "by 1290.35'; the BC of curve 2 is 40+81.72, not the 40+31.72 it would be without "
               "the equation."),
    Probe(id="qa-alignment-data", start="sheets-qa", tags=["tier3", "paper", "qa", "edit"],
          prompt="Sheets C-101 through C-103 already carry SR-100's alignment data: the bearing and "
                 "length of each tangent, the BC and EC stations, curve numbers and CURVE DATA "
                 "tables. Check every item against the design and correct whatever is wrong. "
                 "Change nothing that is right.",
          check=_check_qa, solve=_solve_qa,
          note="Five planted: " + "; ".join(p["what"] for p in QA_PLANTS) + ". Every right item "
               "must keep its value and place, and nothing may be lettered twice."),
    Probe(id="l2-match-lines", start="l2", tags=["tier3", "paper", "caltrans", "twist"],
          prompt="Sheet L-2 shows the \"SR70\" line from 574+50 to 589+50; the layout continues on "
                 "sheet L-1 back of 574+50 and on L-3 ahead of 589+50. Draw the two match lines on "
                 "L-2: each square to the \"SR70\" line at its station, running at least 40 ft past "
                 "the centerline on both sides, and lettered along the line MATCH LINE with the "
                 "adjoining sheet in parentheses: MATCH LINE (L-1), MATCH LINE (L-3).",
          check=_check_match_lines, solve=_solve_match_lines,
          note="The viewport is turned -6.457°. On paper the line runs at 0.14° at 574+50 and "
               "33.27° at 589+50, so a vertical match line is right at L-1 and 33° wrong at L-3, "
               "and one square to the model direction is 6.46° wrong at both."),
    Probe(id="l2-alignment-data", start="l2", tags=["tier3", "paper", "caltrans", "twist", "whole-job"],
          prompt="Sheet L-2 has lost its alignment data. Put it back the way a Caltrans layout shows "
                 "it, for the \"SR70\" line as this sheet shows it: the bearing and length of each "
                 "tangent, the station of each curve point, each curve's number in a circle on the "
                 "plan, and a CURVE DATA table (No., R, Δ, T, L). Curve numbers continue from sheet "
                 "L-1, which ends with curve 1. Nothing you add may overlap other lettering on the "
                 "sheet.",
          check=_check_l2_data, solve=_solve_l2_data,
          note="Two tangents (230.76' N 78°30'50\" E, 251.23' N 66°39'57\" E), five curve points "
               "(576+16.93 EC, 578+47.69 BC, 582+85.52 EC, 585+36.75 BC, 588+34.95 PCC), curves 2 "
               "to 5, of which 2 and 5 only partly show. Fails: numbering 1 to 4 (the design's "
               "C-1..C-4), lettering parallel to the model instead of the turned sheet, BC or EC at "
               "the PCC, lettering over the sheet's own."),
]

__all__ = ["TIER3_PROBES", "Road", "QA_PLANTS", "letter_alignment_data", "plant_qa_errors",
           "qa_planted", "caltrans_lettering", "BANDS", "MATCH"]
