"""Pilot 12: a small plan set, from the base files to a numbered, indexed set.

Every probe so far hands the model one sheet that already exists. A plan set is
the job around the sheets: deciding where each layout breaks, setting each
viewport so its stretch of road fits at 1" = 50', numbering the sheets and
keeping the numbers, totals and index in step, carrying match lines whose
station agrees on both sides, and taking quantities off the base linework for
a summary sheet. Each step is easy alone. What makes the job hard is keeping
them consistent across five sheets that no one engine command ties together:
the index has to list the sheets that are actually there, and the station
lettered on a match line has to be the station the line sits at.

* ``p12-route65-d13``: the Caltrans Route 65 "D13" line from 640+00 to
  672+00. The model gets one empty sheet file with the base files attached
  (AA01 design, BB01 topo) and builds the whole set in it: a title sheet with
  an index of sheets, three layout sheets on the Caltrans border at 1" = 50'
  with a match line between each pair, and a summary of quantities sheet.
  Three is the least that covers the range: a layout's plan area is 31.6 in,
  1580 ft, and 3200 ft plus some overlap does not fit on two.

The base files are the redrafts of the published layouts L-1, L-2 and L-3
(PPM-045, -046, -047), combined. The redrafts keep each sheet's design on its
own local datum (sheet centre at E 10,000 N 10,000), so the three base sets are
joined here into L-1's frame. L-2's set is translated so its "D13" meets
L-1's at 651+24.30, where both lines run N 00°03'30" E, so no turn is needed.
L-3's set is translated and turned 0.034° so its "D13" meets L-2's curve at
662+40. The traced roadway and topo linework of all three come along, their
own anchors dropped. "D13" is re-made as one alignment: L-1's tangent from
638+95.91, then the published R = 5000' curve from L-2's BC (654+06.05)
through the published EC near 690+10, then 200 ft of tangent. Over L-2 and
L-3 the combined line stays within 0.04 ft of each sheet's rebuilt one. The
base also gets "D13"'s centerline, its stationing (ticks and Caltrans
numbers), and its edges of pavement drawn with ``draw_offset`` at 40 ft each
side on a layer of their own (V-ROAD-EP), where the traced ±40 ft lines run.
The quantities are taken off those: the traced linework's layers do not say
what a line is (the "edge" layer of L-2 holds the outline of the words ROUTE
65), so a takeoff from them would have no single right answer.

Grading reads only the sheet file (the base files are the start's, rebuilt
here):

1. the set: exactly one title sheet, three layout sheets and one summary of
   quantities sheet, told apart by the sheet title in the title block (or the
   sheet name);
2. the numbering: sheet numbers 1..5, each used once, the title sheet 1, the
   layouts numbered in station order, and TOTAL SHEETS 5 on every sheet;
3. the index: a table (or rows of text) on the title sheet with one row per
   sheet present, each row's number a sheet's number and its title that
   sheet's title (one contains the other), and no row for a sheet that is not
   there;
4. the layouts: on the Caltrans border, every viewport at 1" = 50' and inside
   the border's plan area;
5. coverage: every station from 640+00 to 672+00, checked every 10 ft, on the
   centerline inside some layout's viewport;
6. and 7. each match line, between the layouts in station order. On both
   sheets a line shows square to "D13" (within 2°), reaching at least 40 ft
   each side of it, and next to it (within 1.5 in) a text with MATCH LINE and
   a station. That station must be within 1 ft of where the line crosses, and
   the same, to the hundredth, on both sheets;
8. and 9. the summary of quantities: a table on that sheet with the HMA area
   between the V-ROAD-EP edges over 640+00 to 672+00 (80 ft x 3200 ft =
   28,444.44 SY) in a row marked SY, and the length of the right of way
   lines on V-ROW in AA01 between the same stations (each piece counted by
   its station square off "D13") in a row marked LF, each within 1 %. The
   R/W lines run from 638+96 to 670+70, so the fence has to be cut at
   640+00; the whole layer is 4 % too long.

The naive answers this catches (``tests/test_pilot_plan_set.py``). One is
the whole set right except an index typed from the plan of the set rather
than the set as built: its row for the summary sheet carries the number 6,
and that fails item 3. One letters the match lines with a station 20 ft from
where they are drawn, which fails items 6 and 7. One measures the fence
along every V-ROW line instead of 640+00 to 672+00 (2,871 LF against
2,761), which fails item 9.
"""
from __future__ import annotations

import copy
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.design.horizontal import Alignment
from roaddraft.document import viewmap
from roaddraft.document.fileformat import read_document, write_document
from roaddraft.probes import notation as nt
from roaddraft.probes import plotted as pl
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common

PROBE_ID = "p12-route65-d13"
SOURCES = ["PPM-045", "PPM-046", "PPM-047"]     # Route 65 layouts L-1, L-2, L-3
AA01, BB01 = "0000000000aa01.rdraft", "0000000000bb01.rdraft"
SHEET_FILE = "route65-d13-plans.rdraft"
ALIGN = "D13"
QUALIFIED = f"AA01:{ALIGN}"
RANGE = (64000.0, 67200.0)
EP_LAYER, EP_OFFSET = "V-ROAD-EP", 40.0
ROW_LAYER = "V-ROW"
LAYOUTS = 3
FPI = 50.0
R_CURVE, DELTA_DEG, END_TANGENT_FT = 5000.0, 41.2994, 200.0   # published R; L-4's BC to EC
#: the joint between L-2's and L-3's rebuilt lines, where L-3's set is fitted to the curve
JOINT_23 = 66240.0
QUANTITY_TOL = 0.01
MATCH_TOL_FT = 1.0
MATCH_REACH_FT = 40.0
MATCH_TURN_DEG = 2.0
MATCH_NEAR_IN = 1.5
COVER_STEP_FT = 10.0


# ------------------------------------------------------------------ the base files


def _rot(p, about, theta_deg: float) -> List[float]:
    t = math.radians(theta_deg)
    dx, dy = p[0] - about[0], p[1] - about[1]
    return [about[0] + dx * math.cos(t) - dy * math.sin(t),
            about[1] + dx * math.sin(t) + dy * math.cos(t)]


class _Move:
    """Rotate about ``about`` by ``theta`` degrees, then shift."""

    def __init__(self, theta: float = 0.0, about=(0.0, 0.0), shift=(0.0, 0.0)):
        self.theta, self.about, self.shift = float(theta), list(about), list(shift)

    def __call__(self, p) -> List[float]:
        q = _rot(p, self.about, self.theta) if self.theta else list(p)
        return [q[0] + self.shift[0], q[1] + self.shift[1]]

    def entity(self, e: dict) -> dict:
        e = copy.deepcopy(e)
        e.pop("anchor", None)
        t = e["type"]
        if t == "line":
            e["start"], e["end"] = self(e["start"]), self(e["end"])
        elif t == "polyline":
            e["vertices"] = [self(v) for v in e["vertices"]]
        elif t == "arc":
            e["center"] = self(e["center"])
            e["start_angle_deg"] = float(e["start_angle_deg"]) + self.theta
            e["end_angle_deg"] = float(e["end_angle_deg"]) + self.theta
        elif t == "text":
            e["position"] = self(e["position"])
            e["rotation_deg"] = float(e.get("rotation_deg", 0.0)) + self.theta
        elif t == "circle":
            e["center"] = self(e["center"])
        else:
            raise ValueError(f"no move for a {t}")
        return e


def _station_xy(align: Alignment, raw: float):
    p, h, _ = align.station_to_xy(raw)
    return p, h


@lru_cache(maxsize=None)
def _sources() -> Tuple[dict, dict]:
    aa = {s: read_document(common.folder(s) / AA01) for s in SOURCES}
    bb = {s: read_document(common.folder(s) / BB01) for s in SOURCES}
    return aa, bb


def _combined_pis() -> Tuple[float, List[list]]:
    """The begin station and PIs of the one "D13" (L-1's frame)."""
    aa, _bb = _sources()
    a1, a2 = (Alignment.from_dict(aa[s]["design"]["alignments"][ALIGN]) for s in SOURCES[:2])
    p1, h1 = _station_xy(a1, a2.begin_station)
    p2, _h2 = _station_xy(a2, a2.begin_station)
    shift = [p1[0] - p2[0], p1[1] - p2[1]]
    pc = a2.curves()[0].pc
    bc = [pc[0] + shift[0], pc[1] + shift[1]]
    t = R_CURVE * math.tan(math.radians(DELTA_DEG) / 2.0)
    u_in, u_out = math.radians(h1), math.radians(h1 + DELTA_DEG)
    pi = [bc[0] + t * math.cos(u_in), bc[1] + t * math.sin(u_in)]
    end = [pi[0] + (t + END_TANGENT_FT) * math.cos(u_out), pi[1] + (t + END_TANGENT_FT) * math.sin(u_out)]
    return float(a1.begin_station), [list(a1.point_at(0.0)), pi + [R_CURVE], end]


def _moves(combined: Alignment) -> Dict[str, _Move]:
    """Each source sheet's frame to L-1's."""
    aa, _bb = _sources()
    a1, a2, a3 = (Alignment.from_dict(aa[s]["design"]["alignments"][ALIGN]) for s in SOURCES)
    p1, _ = _station_xy(a1, a2.begin_station)
    p2, _ = _station_xy(a2, a2.begin_station)
    p3, h3 = _station_xy(a3, JOINT_23)
    pc, hc = _station_xy(combined, JOINT_23)
    return {SOURCES[0]: _Move(),
            SOURCES[1]: _Move(shift=[p1[0] - p2[0], p1[1] - p2[1]]),
            SOURCES[2]: _Move(hc - h3, p3, [pc[0] - p3[0], pc[1] - p3[1]])}


def _merge(docs: Dict[str, dict], moves: Dict[str, _Move], meta: dict, drop=lambda e: False) -> dict:
    """One document from the sources' model space, moved into one frame and
    renumbered; their own references, sheets and design left behind."""
    first = docs[SOURCES[0]]
    out = {k: copy.deepcopy(v) for k, v in first.items()
           if k in ("schema_version", "settings", "text_styles", "blocks")}
    out["meta"] = dict(first.get("meta") or {}, **meta)
    layers: dict = {}
    for s in SOURCES:
        for name, layer in docs[s]["layers"].items():
            layers.setdefault(name, copy.deepcopy(layer))
    out["layers"] = layers
    counters: Dict[str, int] = {}
    ents: Dict[str, dict] = {}
    for s in SOURCES:
        for e in docs[s]["model"]["entities"].values():
            if drop(e):
                continue
            moved = moves[s].entity(e)
            prefix = e["id"].split("-")[0]
            counters[prefix] = counters.get(prefix, 0) + 1
            moved["id"] = f"{prefix}-{counters[prefix]:03d}"
            ents[moved["id"]] = moved
    out["model"] = {"entities": ents}
    out["sheets"] = {}
    out["references"] = {}
    out["design"] = {"alignments": {}, "profiles": {}}
    out["id_counters"] = counters
    return out


@lru_cache(maxsize=None)
def base_documents() -> Tuple[dict, dict]:
    """``(AA01, BB01)`` document dicts of the combined project."""
    aa, bb = _sources()
    begin, pis = _combined_pis()
    probe = Session()
    common.ok(probe.execute("create_alignment", {"name": ALIGN, "begin_station": begin, "pis": pis}))
    combined = probe.doc.design.alignments[ALIGN]
    moves = _moves(combined)
    on_d13 = lambda e: (e.get("anchor") or {}).get("alignment") == ALIGN
    design = _merge(aa, moves, {
        "project_name": "Caltrans Route 65: \"D13\" line, layouts L-1 to L-3 combined",
        "description": ("Master Design file, roadway (\"aa\"): the redrafted base files of "
                        "PPM-045, -046 and -047 (layouts L-1, L-2, L-3) joined into L-1's frame; "
                        "\"D13\" re-made as one alignment; edges of pavement at 40 ft each side "
                        "on V-ROAD-EP")}, drop=on_d13)
    topo = _merge(bb, moves, {
        "project_name": "Caltrans Route 65: topography, layouts L-1 to L-3 combined",
        "description": "Master Topographic file (\"bb\"): the redrafted BB01s of PPM-045, -046 "
                       "and -047 joined into L-1's frame"})
    from roaddraft.document.document import Document
    s = Session(_document=Document.from_dict(design))
    common.ok(s.execute("create_alignment", {"name": ALIGN, "begin_station": begin, "pis": pis,
                                             "description": "\"D13\" LINE, L-1 to L-3"}))
    common.ok(s.execute("draw_alignment", {"alignment": ALIGN, "layer": "V-ALIGN-CNTR"}))
    common.ok(s.execute("create_layer", {"name": EP_LAYER, "color": "black", "lineweight_mm": 0.35,
                                         "description": "Edge of pavement, Route 65 mainline"}))
    common.ok(s.execute("draw_offset", {"alignment": ALIGN, "offsets": [-EP_OFFSET, EP_OFFSET],
                                        "layer": EP_LAYER}))
    common.ok(s.execute("annotate_stationing", {
        "space": "model", "alignment": ALIGN, "interval": 100, "tick_half_len": 3.5,
        "text_height": 5.0, "label_offset": 10.0, "layer": "V-ANNO-STAT",
        "label_layer": "V-ANNO-STAT", "lettering": "caltrans", "view_rotation": -89.94}))
    return s.doc.to_dict(), topo


@lru_cache(maxsize=None)
def centerline() -> Alignment:
    return Alignment.from_dict(base_documents()[0]["design"]["alignments"][ALIGN])


def _entity_length(e: dict) -> float:
    if e["type"] == "line":
        return math.dist(e["start"], e["end"])
    if e["type"] == "polyline":
        v = e["vertices"] + ([e["vertices"][0]] if e.get("closed") else [])
        return sum(math.dist(a, b) for a, b in zip(v, v[1:]))
    if e["type"] == "arc":
        return float(e["radius"]) * math.radians((e["end_angle_deg"] - e["start_angle_deg"]) % 360.0)
    return 0.0


def _in_range_length(points: Sequence[Sequence[float]], align: Alignment, step: float = 0.25) -> float:
    """Length of a run of straight segments whose stations (square off the
    centerline) fall inside ``RANGE``: each segment cut into short pieces, each
    piece counted by the station of its middle."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        n = max(1, int(math.ceil(length / step)))
        for k in range(n):
            t = (k + 0.5) / n
            m = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            try:
                st = float(align.xy_to_station(m)["station"])
            except Exception:  # off either end of the line
                continue
            if RANGE[0] <= st <= RANGE[1]:
                total += length / n
    return total


@lru_cache(maxsize=None)
def quantities() -> Dict[str, float]:
    """The truth: HMA between the edges (SY) and right of way fence along the
    V-ROW lines (LF), both over ``RANGE``."""
    aa, _bb = base_documents()
    align = centerline()
    row = 0.0
    for e in aa["model"]["entities"].values():
        if e["layer"] != ROW_LAYER:
            continue
        if e["type"] == "line":
            row += _in_range_length([e["start"], e["end"]], align)
        elif e["type"] == "polyline":
            v = e["vertices"] + ([e["vertices"][0]] if e.get("closed") else [])
            row += _in_range_length(v, align)
        else:
            raise ValueError(f"a {e['type']} on {ROW_LAYER}")
    return {"SY": 2.0 * EP_OFFSET * (RANGE[1] - RANGE[0]) / 9.0, "LF": row}


def build_start(out: Path) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    aa, bb = base_documents()
    write_document(out / AA01, aa)
    write_document(out / BB01, bb)
    s = Session(project_name="Route 65 \"D13\" plan set", out_dir=out)
    path = common.save(s, out / SHEET_FILE)
    common.ok(s.execute("attach_reference", {"name": "AA01", "path": AA01, "space": "model"}))
    common.ok(s.execute("attach_reference", {"name": "BB01", "path": BB01, "space": "model"}))
    return common.save(s, path)


common.register(PROBE_ID, SHEET_FILE, build_start)


# ------------------------------------------------------------------ reading the set


def _norm(text) -> str:
    return " ".join(str(text or "").upper().replace("\n", " ").split())


def _title(sheet) -> str:
    return _norm((sheet.title_block_fields or {}).get("sheet_title")) or _norm(sheet.name)


def _kind(sheet) -> str:
    t = _title(sheet)
    if "TITLE" in t or "COVER" in t:
        return "title"
    if "QUANTIT" in t:
        return "soq"
    if "LAYOUT" in t:
        return "layout"
    return "other"


def _int(value) -> Optional[int]:
    m = re.match(r"^\s*(\d+)\s*$", str(value if value is not None else ""))
    return int(m.group(1)) if m else None


def _view(session: Session, sheet) -> pl.Plot:
    items = [(sheet.id, e) for e in sheet.entities.values()]
    items += [("model", e) for e in session.doc.model_entities.values()]
    return pl.plot(session, sheet, items)


def _shows(sheet, vp, point) -> bool:
    q = vp.transform().to_paper(point)
    x0, y0, x1, y1 = sheet.usable_area()
    return viewmap.in_window(vp, q) and x0 <= q[0] <= x1 and y0 <= q[1] <= y1


def _covered(sheet, align: Alignment) -> Optional[Tuple[float, float]]:
    shown = [st for st in _frange(align.begin_station, align.end_station, 5.0)
             if any(_shows(sheet, vp, align.station_to_xy(st)[0]) for vp in sheet.viewports)]
    return (min(shown), max(shown)) if shown else None


def _frange(a: float, b: float, step: float) -> List[float]:
    n = int(math.floor((b - a) / step + 1e-9))
    return [a + k * step for k in range(n + 1)] + ([b] if a + n * step < b - 1e-9 else [])


def _rows_of(sheet, view: pl.Plot) -> List[List[str]]:
    """The index rows on a sheet: its tables' rows, or rows of its text."""
    rows = [list(map(str, r)) for t in view.tables for r in [t.headers] + t.rows]
    if any(_number_cell(r) is not None for r in rows):
        return rows
    lines = []
    for t in view.free_texts():
        lines += [ln for ln in t.content.split("\n") if ln.strip()]
    split = [re.split(r"\s{2,}|\t", ln.strip(), maxsplit=1) for ln in lines]
    split = [s if len(s) == 2 else re.split(r"\s+", s[0], maxsplit=1) for s in split]
    return split + pl.text_rows(view.free_texts())


def _number_cell(row: Sequence[str]) -> Optional[int]:
    for cell in row:
        n = _int(cell)
        if n is not None:
            return n
    return None


def _index_problem(title_sheet, view: pl.Plot, sheets: list) -> Optional[str]:
    rows = [(n, " ".join(c for c in r if _int(c) != n))
            for r in _rows_of(title_sheet, view) for n in [_number_cell(r)] if n is not None]
    if not rows:
        return f"no index of sheets on {title_sheet.name}"
    by_number: Dict[int, List[str]] = {}
    for n, title in rows:
        by_number.setdefault(n, []).append(_norm(title))
    numbers = {_int((s.title_block_fields or {}).get("sheet_number")): s for s in sheets}
    stray = sorted(n for n in by_number if n not in numbers)
    if stray:
        return f"the index lists sheet {stray[0]}, which the set does not have"
    for n, sheet in sorted((k, v) for k, v in numbers.items() if k is not None):
        titles = by_number.get(n)
        if not titles:
            return f"the index has no row for sheet {n} ({_title(sheet)})"
        want = _title(sheet)
        if not any(t and (want in t or t in want) for t in titles):
            return f"the index calls sheet {n} {titles[0]!r}; its title block says {want!r}"
        if len(titles) > 1:
            return f"the index lists sheet {n} {len(titles)} times"
    return None


def _numbering_problem(sheets: list, by_kind: Dict[str, list], align: Alignment) -> Optional[str]:
    total = len(sheets)
    numbers = []
    for s in sheets:
        f = s.title_block_fields or {}
        n, t = _int(f.get("sheet_number")), _int(f.get("total_sheets"))
        if n is None:
            return f"sheet {s.name} has no sheet number in its title block"
        if t != total:
            return f"sheet {s.name} says TOTAL SHEETS {f.get('total_sheets')!r}; the set has {total}"
        numbers.append(n)
    if sorted(numbers) != list(range(1, total + 1)):
        return f"the sheets are numbered {sorted(numbers)}; a set of {total} is 1 to {total}, each once"
    if by_kind["title"] and _int(by_kind["title"][0].title_block_fields.get("sheet_number")) != 1:
        return "the title sheet is not sheet 1"
    layouts = [(c[0], _int(s.title_block_fields.get("sheet_number")), s.name)
               for s in by_kind["layout"] for c in [_covered(s, align)] if c]
    order = [n for _a, n, _name in sorted(layouts)]
    if order != sorted(order):
        return "the layout sheets are not numbered in station order"
    return None


def _layout_problem(sheet) -> Optional[str]:
    if (sheet.title_block_template or "").lower() != "caltrans":
        return f"{sheet.name} is not on the Caltrans border (template {sheet.title_block_template!r})"
    if not sheet.viewports:
        return f"{sheet.name} has no viewport"
    x0, y0, x1, y1 = sheet.usable_area()
    for vp in sheet.viewports:
        if abs(float(vp.feet_per_inch) - FPI) > 1e-6:
            return f"{sheet.name}'s viewport is at 1\" = {float(vp.feet_per_inch):g}'; layouts are 1\" = 50'"
        a, b, c, d = vp.paper_bbox()
        if a < x0 - 0.05 or b < y0 - 0.05 or c > x1 + 0.05 or d > y1 + 0.05:
            return f"{sheet.name}'s viewport runs outside the border"
    return None


def _coverage_problem(layouts: list, align: Alignment) -> Optional[str]:
    for st in _frange(RANGE[0], RANGE[1], COVER_STEP_FT):
        p = align.station_to_xy(st)[0]
        if not any(_shows(s, vp, p) for s in layouts for vp in s.viewports):
            return f"{align.stations().format(st)} is on no layout sheet"
    return None


def _joined(segs: Sequence[pl.PSeg], snap: float = 0.01, turn: float = 1.0) -> List[pl.PSeg]:
    """Plotted segments with collinear runs that meet end to end joined into one,
    so a match line drawn in pieces (out to the centerline and on) reads whole."""
    out = [pl.PSeg(list(s.a), list(s.b), s.source, s.space, s.closed) for s in segs if s.length > 1e-9]
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                p, q = out[i], out[j]
                if pl.turn_between(p.angle, q.angle, 180.0) > turn:
                    continue
                ends = [(p.a, p.b, q.a, q.b), (p.a, p.b, q.b, q.a), (p.b, p.a, q.a, q.b), (p.b, p.a, q.b, q.a)]
                for far_p, near_p, near_q, far_q in ends:
                    if math.dist(near_p, near_q) <= snap:
                        out[i] = pl.PSeg(far_p, far_q, p.source, p.space)
                        del out[j]
                        merged = True
                        break
                if merged:
                    break
            if merged:
                break
    return out


def _match_on(session: Session, sheet, align: Alignment, near: float) -> Tuple[Optional[float], str]:
    """``(lettered station, problem)`` of the match line ``sheet`` shows near station ``near``."""
    view = _view(session, sheet)
    vp = sheet.viewports[0]
    to_model = vp.transform().to_model
    found = []
    for seg in _joined(view.segs):
        a, b = to_model(seg.a), to_model(seg.b)
        try:
            ra, rb = align.xy_to_station(a), align.xy_to_station(b)
        except Exception:
            continue
        oa, ob = float(ra["offset"]), float(rb["offset"])
        if oa * ob >= 0 or min(abs(oa), abs(ob)) < MATCH_REACH_FT:
            continue
        t = oa / (oa - ob)
        cross = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
        try:
            rc = align.xy_to_station(cross)
        except Exception:
            continue
        st = float(rc["station"])
        if abs(st - near) > 300.0:
            continue
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        turn = abs(((ang - float(rc["direction_deg"])) % 180.0) - 90.0)
        if turn > MATCH_TURN_DEG:
            continue
        found.append((st, seg))
    if not found:
        return None, f"no match line on {sheet.name} near {align.stations().format(near)}"
    texts = [t for t in view.free_texts()
             if nt.has_word(t.content, "MATCH") and nt.has_word(t.content, "LINE")]
    for st, seg in sorted(found, key=lambda f: abs(f[0] - near)):
        for t in texts:
            if seg.distance(t.center()) > MATCH_NEAR_IN:
                continue
            lettered = nt.stations(t.content)
            if not lettered:
                continue
            value = lettered[0][0]
            if abs(value - st) > MATCH_TOL_FT:
                return None, (f"the match line on {sheet.name} is lettered {lettered[0][1]} but sits at "
                              f"{align.stations().format(st)}")
            return value, ""
    return None, (f"the match line on {sheet.name} at {align.stations().format(found[0][0])} is not "
                  f"lettered MATCH LINE with its station")


def _soq_problem(view: pl.Plot, unit: str, want: float, what: str) -> Optional[str]:
    pattern = {"SY": r"\bS\.?\s?Y\.?\b|\bSQ\.?\s*YD|\bSQUARE\s+YARD",
               "LF": r"\bL\.?\s?F\.?\b|\bLIN\.?\s*FT|\bLINEAR\s+F(EE|OO)T"}[unit]
    seen = []
    number = lambda text: [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", text)]
    for t in view.tables:
        unit_cols = [k for k, h in enumerate(t.headers) if re.search(pattern, str(h).upper())]
        for r in t.rows:
            line = " ".join(map(str, r))
            if re.search(pattern, line.upper()):
                nums = number(line)
            elif unit_cols:   # the unit in the column's header
                nums = [n for k in unit_cols if k < len(r) for n in number(str(r[k]))]
            else:
                continue
            seen += nums
            if any(abs(n - want) <= QUANTITY_TOL * want for n in nums):
                return None
    if not view.tables:
        return "no table on the summary of quantities sheet"
    if not seen:
        return f"the summary of quantities has no row in {unit} for {what}"
    return (f"the summary of quantities gives {what} as {', '.join(f'{n:,.2f}' for n in seen[:3])} "
            f"{unit}; the base linework gives {want:,.2f}")


def check(baseline: Session, submitted: Session) -> Result:
    tally = Tally()
    align = centerline()
    sheets = list(submitted.doc.sheets.values())
    by_kind: Dict[str, list] = {"title": [], "layout": [], "soq": [], "other": []}
    for s in sheets:
        by_kind[_kind(s)].append(s)
    problem = None
    if len(by_kind["title"]) != 1:
        problem = f"{len(by_kind['title'])} title sheets; the set has one"
    elif len(by_kind["layout"]) != LAYOUTS:
        problem = f"{len(by_kind['layout'])} layout sheets; the set has {LAYOUTS}"
    elif len(by_kind["soq"]) != 1:
        problem = f"{len(by_kind['soq'])} summary of quantities sheets; the set has one"
    elif by_kind["other"]:
        problem = f"sheet {by_kind['other'][0].name} ({_title(by_kind['other'][0])!r}) is not one asked for"
    tally.add("the set: a title sheet, three layouts, a summary of quantities", problem)
    tally.add("sheet numbers and totals in every title block",
              _numbering_problem(sheets, by_kind, align) if sheets else "the file has no sheets")
    title = by_kind["title"][0] if by_kind["title"] else None
    tally.add("the index of sheets",
              _index_problem(title, _view(submitted, title), sheets) if title else "no title sheet")
    layouts = by_kind["layout"]
    tally.add("the layouts on the Caltrans border at 1\" = 50'",
              next((p for p in map(_layout_problem, layouts) if p), None) if layouts else "no layout sheets")
    ok_layouts = [s for s in layouts if not _layout_problem(s)]
    tally.add("640+00 to 672+00 all shown", _coverage_problem(ok_layouts, align) if ok_layouts
              else "no layout sheet to show it")
    ordered = sorted(((c, s) for s in ok_layouts for c in [_covered(s, align)] if c),
                     key=lambda cs: cs[0][0])
    for k in range(LAYOUTS - 1):
        item = f"the match line between layouts {k + 1} and {k + 2}"
        if k + 1 >= len(ordered):
            tally.add(item, "there is no such pair of layout sheets")
            continue
        (ca, a), (cb, b) = ordered[k], ordered[k + 1]
        near = (ca[1] + cb[0]) / 2.0
        va, pa = _match_on(submitted, a, align, near)
        vb, pb = _match_on(submitted, b, align, near)
        problem = pa or pb or None
        if problem is None and abs(va - vb) > 0.005:
            problem = (f"the match line is lettered {align.stations().format(va)} on {a.name} and "
                       f"{align.stations().format(vb)} on {b.name}")
        tally.add(item, problem)
    q = quantities()
    soq = by_kind["soq"][0] if by_kind["soq"] else None
    view = _view(submitted, soq) if soq else None
    tally.add("HMA area (SY)", _soq_problem(view, "SY", q["SY"], "the HMA area") if soq
              else "no summary of quantities sheet")
    tally.add("right of way fence (LF)", _soq_problem(view, "LF", q["LF"], "the right of way fence")
              if soq else "no summary of quantities sheet")
    return tally.result(
        f"a five-sheet set: title sheet with a matching index, three layouts at 1\" = 50' showing "
        f"640+00 to 672+00 with agreeing match lines, numbers and totals consistent, and the "
        f"quantities ({q['SY']:,.0f} SY, {q['LF']:,.0f} LF) within 1 %")


# ------------------------------------------------------------------ the solution


BREAKS = [64000.0, 65100.0, 66200.0, 67200.0]
TITLE_FIELDS = {"dist": "03", "county": "Pla", "route": "65", "post_miles": "R11.9/R24.1"}


def _station(session: Session, raw: float) -> Tuple[List[float], float]:
    r = common.ok(session.query("station_to_xy", {"alignment": QUALIFIED, "station": raw}))
    return r["point"], float(r["direction_deg"])


def make_solve(index_from_plan: bool = False, rounded_match: bool = False,
               whole_fence: bool = False):
    """The scripted set. The switches are the naive slips the tests try:
    ``index_from_plan`` types the index from a plan that had a sixth sheet,
    ``rounded_match`` letters the match lines 20 ft off where they are drawn,
    ``whole_fence`` measures every V-ROW line instead of 640+00 to 672+00."""
    def solve(session: Session) -> None:
        names = ["TITLE"] + [f"L-{k + 1}" for k in range(LAYOUTS)] + ["Q-1"]
        titles = ["TITLE SHEET"] + ["LAYOUT"] * LAYOUTS + ["SUMMARY OF QUANTITIES"]
        total = len(names)
        for n, (name, title) in enumerate(zip(names, titles), start=1):
            fields = dict(TITLE_FIELDS, sheet_title=title, sheet_number=str(n), total_sheets=str(total))
            if title == "LAYOUT":
                fields.update(sheet_id=name, scale="SCALE: 1\" = 50'")
            common.ok(session.execute("create_sheet", {"name": name, "size": "ANSI_D",
                                                       "title_block_template": "caltrans",
                                                       "title_block_fields": fields}))
        # the layouts: each viewport on the middle of its stretch, turned to run with it
        for k in range(LAYOUTS):
            a, b = BREAKS[k], BREAKS[k + 1]
            mid, heading = _station(session, (a + b) / 2.0)
            p_a, _ = _station(session, a)
            p_b, _ = _station(session, b)
            centre = [(p_a[0] + p_b[0] + 2 * mid[0]) / 4.0, (p_a[1] + p_b[1] + 2 * mid[1]) / 4.0]
            common.ok(session.execute("create_viewport", {
                "sheet": names[k + 1], "center_paper": [17.702, 11.0], "width_in": 31.5,
                "height_in": 20.9, "model_center": centre, "feet_per_inch": FPI,
                "rotation_deg": -heading}))
        # the match lines, once in model space, lettered on both sheets
        common.ok(session.execute("create_layer", {"name": "S-ANNO-MTCH", "color": "black",
                                                   "lineweight_mm": 0.5}))
        for k, st in enumerate(BREAKS[1:-1]):
            text = f"{int(st // 100)}+{st % 100:05.2f}"
            common.ok(session.execute("draw_station_offset", {
                "alignment": QUALIFIED, "layer": "S-ANNO-MTCH",
                "points": [f"{text}@120L", f"{text}@120R"]}))
            lettered = st + (20.0 if rounded_match else 0.0)
            label = f"MATCH LINE STA {int(lettered // 100)}+{lettered % 100:05.2f}"
            for sheet in (names[k + 1], names[k + 2]):
                common.ok(session.execute("place_label", {
                    "space": sheet, "alignment": QUALIFIED, "anchor": text, "kind": "custom",
                    "content": label, "rotation": "perpendicular", "side": "left",
                    "label_offset": 1.2, "height": 0.14, "layer": "S-ANNO-MTCH",
                    "halign": "center", "valign": "bottom"}))
        # the quantities, off the base linework
        left = [_point(session, st, -EP_OFFSET) for st in _frange(RANGE[0], RANGE[1], 10.0)]
        right = [_point(session, st, EP_OFFSET) for st in _frange(RANGE[0], RANGE[1], 10.0)]
        area = common.ok(session.query("area", {"points": left + right[::-1]}))
        sy = _sq_yd(area)
        rows = common.ok(session.query("find_entities", {"layer": ROW_LAYER, "limit": 500,
                                                         "detail": "full"}))["entities"]
        lf = sum((r["length"] if whole_fence else _fence_length(session, r["entity"]))
                 for r in rows)
        common.ok(session.execute("create_layer", {"name": "S-ANNO-TABL", "color": "black",
                                                   "lineweight_mm": 0.25}))
        common.ok(session.execute("place_table", {
            "space": "Q-1", "layer": "S-ANNO-TABL", "position": [4.0, 18.0],
            "title": "SUMMARY OF QUANTITIES",
            "columns": [{"header": "ITEM", "width": 6.0}, {"header": "UNIT", "width": 1.2},
                        {"header": "QUANTITY", "width": 2.0}],
            "rows": [["HMA (TYPE A) PAVEMENT, 640+00 TO 672+00", "SQYD", f"{sy:,.0f}"],
                     ["FENCE (TYPE CL-6), RIGHT OF WAY", "LF", f"{lf:,.0f}"]],
            "text_height": 0.14}))
        # the index, from the set as built
        index = [[str(n), (t if t != "LAYOUT" else f"LAYOUT {names[n - 1]}")]
                 for n, t in enumerate(titles, start=1)]
        if index_from_plan:   # the plan had a typical section as sheet 5; it was dropped
            index = index[:-1] + [["6", "SUMMARY OF QUANTITIES"]]
        common.ok(session.execute("place_table", {
            "space": "TITLE", "layer": "S-ANNO-TABL", "position": [24.0, 16.0],
            "title": "INDEX OF SHEETS",
            "columns": [{"header": "SHEET NO.", "width": 1.4}, {"header": "DESCRIPTION", "width": 4.5}],
            "rows": index, "text_height": 0.14}))
        common.ok(session.execute("place_text", {
            "space": "TITLE", "position": [16.0, 19.5], "height": 0.35, "halign": "center",
            "valign": "top",
            "content": "STATE OF CALIFORNIA\nDEPARTMENT OF TRANSPORTATION\n"
                       "PROJECT PLANS FOR CONSTRUCTION ON\nSTATE HIGHWAY IN PLACER COUNTY\n"
                       "ROUTE 65, \"D13\" LINE, 640+00 TO 672+00"}))
    return solve


def _point(session: Session, st: float, offset: float) -> List[float]:
    r = common.ok(session.query("station_to_xy", {"alignment": QUALIFIED, "station": st,
                                                  "offset": offset}))
    return r["point"]


def _sq_yd(area: dict) -> float:
    for key in ("square_yards", "area_sy", "sq_yd"):
        if key in area:
            return float(area[key])
    return float(area.get("area_sf", area.get("area")) or 0.0) / 9.0


def _station_of(session: Session, p) -> Optional[float]:
    r = session.query("xy_to_station", {"alignment": QUALIFIED, "point": list(p)})
    return float(r["station"]) if r.get("ok") else None


def _fence_length(session: Session, e: dict) -> float:
    """A takeoff of one right of way line over the range: each segment kept,
    dropped, or cut where it crosses 640+00 or 672+00 (found by halving)."""
    pts = [e["start"], e["end"]] if e["type"] == "line" else list(e["vertices"])
    if e.get("closed"):
        pts.append(pts[0])
    inside = lambda st: st is not None and RANGE[0] <= st <= RANGE[1]
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        sa, sb = _station_of(session, a), _station_of(session, b)
        if inside(sa) and inside(sb):
            total += math.dist(a, b)
        elif inside(sa) or inside(sb):
            p_in, p_out = (a, b) if inside(sa) else (b, a)
            for _ in range(30):
                mid = [(p_in[0] + p_out[0]) / 2.0, (p_in[1] + p_out[1]) / 2.0]
                if inside(_station_of(session, mid)):
                    p_in = mid
                else:
                    p_out = mid
            total += math.dist(a if inside(sa) else b, p_in)
    return total


PROMPT = (
    "Put together a small plan set for the Route 65 \"D13\" line from 640+00 to 672+00, all in "
    "this one file. The design and topo base files are already attached (AA01 and BB01). The set "
    "is: a title sheet with an index of sheets listing every sheet in the set by sheet number "
    "and title; three layout sheets on the Caltrans border at 1\" = 50' that between them show "
    "the whole of 640+00 to 672+00, with a match line between each pair, lettered MATCH LINE "
    "with its station on both sheets; and a summary of quantities sheet with a table of two "
    "items: the HMA pavement area between the edges of pavement (layer V-ROAD-EP in AA01) from "
    "640+00 to 672+00, in square yards, and new right of way fence along the right of way lines "
    "(layer V-ROW in AA01) over the same stations, in linear feet. Fill in each sheet's title "
    "block with its sheet title, its sheet number and the total number of sheets.")

NOTE = (
    "Start: an empty sheet file with the combined Route 65 base (L-1, L-2 and L-3's redrafted "
    "AA01/BB01 joined into one frame; \"D13\" one alignment 638+95.91 to 692+10.11, BC 654+06.05, "
    "R 5000'; edges of pavement at 40 ft on V-ROAD-EP). Expected: five sheets numbered 1-5 of 5 "
    "(title sheet 1), an index that matches them, three Caltrans layouts at 1\"=50' covering "
    "640+00-672+00, two match lines each lettered with the same station on both sheets and "
    "drawn there, and a summary table with 28,444.44 SY and the V-ROW length between 640+00 and "
    "672+00 in LF (within 1 %; the whole layer is 4 % more).")

PROBES: List[Probe] = [
    Probe(id=PROBE_ID, prompt=PROMPT, check=check, solve=make_solve(), note=NOTE,
          tags=["plan-set", "sheets", "caltrans", "quantities", "whole-job"], start=PROBE_ID),
]

__all__ = ["PROBES", "PROBE_ID", "base_documents", "centerline", "quantities", "build_start",
           "check", "make_solve"]
