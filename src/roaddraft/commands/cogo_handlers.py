"""Survey and plan-production tools:

* ``create_points`` / ``place_point_table`` -- COGO points (numbered, with
  elevation and description) and the table that lists them;
* ``label_segments`` -- bearings and distances on right-of-way lines and
  curves, along them or as L1/C1 tags with line and curve tables;
* ``draw_station_offset`` -- linework through station-and-offset points of an
  alignment (Civil 3D's 'SO), following the alignment where the offset holds;
* ``place_along`` -- symbols or points at an interval along a path or an
  alignment (AutoCAD MEASURE / DIVIDE): delineators, station markers;
* ``hatch`` -- fill or pattern an area bounded by linework, a polygon, or
  the region around a point.

Each returns ``(message, diff, warnings)`` and raises ``CommandFault`` with a
hint, like every handler.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.commands.edit_handlers import _fmt, _resolve
from roaddraft.commands.handlers import (
    CommandFault, _add, _diff, _entity_common, _space, _space_label, _style,
)
from roaddraft.core import geometry as geo
from roaddraft.design.angles import direction_to_azimuth, format_bearing, format_dms
from roaddraft.document import annotation as anno
from roaddraft.document import hatching, paths, regions, snaps
from roaddraft.document.document import Document
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Hatch, Line, Point, Polyline, Table, Text,
)

#: Paper heights a plan letters these at (inches); model space multiplies by
#: the annotation scale (or the engine's fixed 80 ft/in when it is off).
POINT_TEXT_IN = 0.08
LABEL_TEXT_IN = 0.10
FIXED_FT_PER_IN = 80.0


def _paper_to_space(doc: Document, space_key: str, inches: float) -> float:
    if space_key != "model":
        return inches
    scale = anno.current_scale(doc)
    return inches * (scale if scale is not None else FIXED_FT_PER_IN)


# ------------------------------------------------------------------ points


def point_numbers(doc: Document) -> Dict[int, str]:
    """Point number -> entity id, across every space."""
    out = {}
    spaces = [doc.model_entities] + [s.entities for s in doc.sheets.values()]
    for entities in spaces:
        for e in entities.values():
            if isinstance(e, Point) and e.number is not None:
                out[e.number] = e.id
    return out


def next_point_number(doc: Document, start: Optional[int] = None) -> int:
    used = point_numbers(doc)
    n = start if start is not None else (max(used) + 1 if used else 1)
    while n in used:
        n += 1
    return n


POINT_FORMATS = ("PNEZD", "PENZD", "PNEZ", "PENZ", "PNE", "PEN", "NEZD", "ENZD", "NEZ",
                 "ENZ", "NE", "EN")


def parse_point_text(text: str, fmt: str = "PNEZD") -> List[dict]:
    """Rows of a point file (comma or whitespace separated), one point a line,
    fields in the order ``fmt`` names: P number, N northing, E easting,
    Z elevation, D description (the rest of the line). Blank lines and
    lines starting with # are skipped."""
    fmt = fmt.upper()
    if fmt not in POINT_FORMATS:
        raise CommandFault(f"format must be one of {', '.join(POINT_FORMATS)}, got {fmt!r}")
    rows = []
    for n, raw in enumerate(str(text).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "," in line:
            parts = [x.strip() for x in line.split(",")]
        else:
            parts = line.split()
        if "D" in fmt and len(parts) > len(fmt):
            k = fmt.index("D")
            parts = parts[:k] + [" ".join(parts[k:])]
        needed = max(fmt.index("N"), fmt.index("E")) + 1  # elevation and description may be left off
        if len(parts) < needed:
            raise CommandFault(f"line {n} of the point text has {len(parts)} fields, and "
                               f"{fmt} needs {needed} or more: {raw!r}")
        row = {}
        try:
            for key, value in zip(fmt, parts):
                if key == "P":
                    row["number"] = int(float(value))
                elif key == "N":
                    row["northing"] = float(value)
                elif key == "E":
                    row["easting"] = float(value)
                elif key == "Z":
                    row["elevation"] = float(value) if value not in ("", "-") else None
                elif key == "D":
                    row["description"] = value
        except ValueError:
            raise CommandFault(f"line {n} of the point text does not read as {fmt}: {raw!r}",
                               hint="northing and easting are numbers; check the column order "
                                    "(format)")
        rows.append(row)
    if not rows:
        raise CommandFault("the point text has no points in it")
    return rows


def _row_point(row: dict, where: str) -> List[float]:
    if "point" in row:
        if "northing" in row or "easting" in row:
            raise CommandFault(f"{where}: give point [x, y] or northing and easting, not both")
        return [float(row["point"][0]), float(row["point"][1])]
    if "northing" in row and "easting" in row:
        return [float(row["easting"]), float(row["northing"])]
    raise CommandFault(f"{where} needs a location: point [x, y] (x = easting) or northing and "
                       f"easting")


def _point_style(doc: Document, space_key: str, p: dict) -> dict:
    height = float(p.get("text_height", _paper_to_space(doc, space_key, POINT_TEXT_IN)))
    size = float(p.get("size", height))
    if height <= 0 or size <= 0:
        raise CommandFault("text_height and size must be positive")
    style = {"marker": p.get("marker", "x"), "size": size, "text_height": height,
             "label": list(p.get("label", ["number", "elevation", "description"])),
             "style": _style(doc, p.get("style", doc.settings["current_text_style"]))}
    if space_key == "model":
        style["annotative"] = anno.text_record(doc, height)
    return style


def create_points(doc: Document, p: dict):
    space_key, _container = _space(doc, p.get("space", "model"))
    sources = [k for k in ("points", "text", "from_entities") if k in p]
    if not sources:
        raise CommandFault("give the points: points (a list), text (a point file's lines) or "
                           "from_entities (points at their ends and vertices)")
    rows: List[dict] = []
    for i, row in enumerate(p.get("points", [])):
        rows.append({**row, "point": _row_point(row, f"points[{i}]")})
    if "text" in p:
        for row in parse_point_text(p["text"], p.get("format", "PNEZD")):
            rows.append({**row, "point": _row_point(row, "a point text line")})
    if "from_entities" in p:
        seen: List[List[float]] = []
        for eid in p["from_entities"]:
            entity, _owner, _ref, _sk = _resolve(doc, eid)
            for sp in snaps.entity_key_points(entity, eid):
                if sp.kind not in ("endpoint", "insertion", "node"):
                    continue
                if any(geo.distance(sp.point, q) < 1e-6 for q in seen):
                    continue
                seen.append(sp.point)
                rows.append({"point": list(sp.point), "description": p.get("description", "")})
        if not seen:
            raise CommandFault("the entities have no ends or vertices to set points on")
    used = point_numbers(doc)
    taken = set()
    for row in rows:
        n = row.get("number")
        if n is None:
            continue
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise CommandFault(f"point number {n!r} is not a whole number from 1 up")
        if n in used:
            raise CommandFault(f"point {n} already exists ({used[n]})",
                               hint="leave number off to number automatically, or set "
                                    "start_number past the points already in the drawing")
        if n in taken:
            raise CommandFault(f"point number {n} is given twice")
        taken.add(n)
    style = _point_style(doc, space_key, p)
    common = _entity_common(doc, p)
    start = p.get("start_number")
    created = []
    summary = []
    for row in rows:
        n = row.get("number")
        if n is None:
            n = start if start is not None else None
            n = next_point_number(doc, n)
            while n in taken:
                n = next_point_number(doc, n + 1)
            start = n + 1
        taken.add(n)
        elevation = row.get("elevation")
        _, e = _add(doc, space_key, "point", Point, {
            **common, **style, "position": row["point"], "number": n,
            "elevation": None if elevation is None else float(elevation),
            "description": str(row.get("description") or p.get("description", "") or "")})
        created.append(e.id)
        if len(summary) < 12:
            desc = f" {e.description}" if e.description else ""
            elev = f" EL {e.elevation:.2f}" if e.elevation is not None else ""
            summary.append(f"{n} {_fmt(e.position)}{elev}{desc}")
    numbers = sorted(doc.resolve_space(space_key)[1][eid].number for eid in created)
    span = _ranges(numbers)
    more = f" (+{len(created) - len(summary)} more)" if len(created) > len(summary) else ""
    return (f"{len(created)} point{'s' if len(created) != 1 else ''} ({span}) on layer "
            f"{common['layer']!r} in {_space_label(doc, space_key)}: "
            + "; ".join(summary) + more, _diff(created=created), [])


def _select_points(doc: Document, value) -> List[Point]:
    """Points by 'all', a list of numbers or ids, or a range text '1-20, 25'."""
    numbers = point_numbers(doc)
    if value in (None, "all"):
        chosen = sorted(numbers)
    elif isinstance(value, str):
        chosen = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
            if m:
                lo, hi = int(m.group(1)), int(m.group(2))
                chosen += [n for n in sorted(numbers) if lo <= n <= hi]
            elif part.isdigit():
                chosen.append(int(part))
            else:
                raise CommandFault(f"cannot read {part!r} as a point number or range",
                                   hint="'all', [1, 2, 3], or '1-20, 25'")
    else:
        chosen = []
        for item in value:
            if isinstance(item, int) and not isinstance(item, bool):
                chosen.append(item)
            else:
                found = doc.find_entity(str(item))
                if found is None or not isinstance(found[1], Point):
                    raise CommandFault(f"{item!r} is not a point number or a point's id")
                chosen.append(found[1].number)
    out = []
    for n in dict.fromkeys(chosen):
        if n not in numbers:
            raise CommandFault(f"there is no point {n}",
                               hint=f"points: {_ranges(sorted(numbers)) or 'none'}")
        found = doc.find_entity(numbers[n])
        out.append(found[1])
    if not out:
        raise CommandFault("no points to list", hint="create_points first")
    return out


def _ranges(numbers: List[int]) -> str:
    out, run = [], []
    for n in numbers:
        if run and n == run[-1] + 1:
            run.append(n)
            continue
        if run:
            out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
        run = [n]
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return ", ".join(out)


POINT_COLUMNS = {"number": "POINT", "northing": "NORTHING", "easting": "EASTING",
                 "elevation": "ELEV", "description": "DESCRIPTION"}


def _column_widths(headers, rows, height: float) -> List[float]:
    widths = []
    for j, header in enumerate(headers):
        longest = max(geo.text_size(s, height)[0] for s in [header] + [str(r[j]) for r in rows])
        widths.append(round(longest + 2.0 * height, 4))
    return widths


def place_point_table(doc: Document, p: dict):
    space_key, _container = _space(doc, p["space"])
    points = _select_points(doc, p.get("points", "all"))
    columns = p.get("columns")
    if columns is None:
        columns = ["number", "northing", "easting"]
        if any(pt.elevation is not None for pt in points):
            columns.append("elevation")
        if any(pt.description for pt in points):
            columns.append("description")
    for c in columns:
        if c not in POINT_COLUMNS:
            raise CommandFault(f"unknown column {c!r}", hint=f"columns: {list(POINT_COLUMNS)}")
    places = int(p.get("precision", 2))
    rows = []
    for pt in points:
        cells = {"number": str(pt.number), "northing": f"{pt.position[1]:.{places}f}",
                 "easting": f"{pt.position[0]:.{places}f}",
                 "elevation": "" if pt.elevation is None else f"{pt.elevation:.{places}f}",
                 "description": pt.description}
        rows.append([cells[c] for c in columns])
    height = float(p.get("text_height", _paper_to_space(doc, space_key, LABEL_TEXT_IN)))
    headers = [POINT_COLUMNS[c] for c in columns]
    widths = _column_widths(headers, rows, height)
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    _, table = _add(doc, space_key, "table", Table, {
        **_entity_common(doc, p), "position": [float(v) for v in p["position"]],
        "columns": [{"header": h, "width": w} for h, w in zip(headers, widths)],
        "rows": rows, "text_height": height, "title": p.get("title", "POINT TABLE"),
        "style": style})
    from roaddraft.commands.handlers import _annotation_warnings
    return (f"point table {table.id}: {len(rows)} points "
            f"({_ranges([pt.number for pt in points])}) in {_space_label(doc, space_key)}",
            _diff(created=[table.id]), _annotation_warnings(doc, space_key, table))


# ------------------------------------------------------- segment labels


def _segments(doc: Document, ids: Sequence[str]):
    """``[(id, piece, space)]`` for every segment of the entities: a line,
    each straight or curved run of a polyline, an arc."""
    out = []
    for eid in ids:
        entity, _owner, _ref, space_key = _resolve(doc, eid)
        if isinstance(entity, Circle):
            raise CommandFault(f"{eid} is a circle; it has no bearing or distance to label")
        if not isinstance(entity, paths.PATH_ENTITY_TYPES):
            raise CommandFault(f"{eid} is a {entity.TYPE}; label_segments labels lines, "
                               f"polylines and arcs")
        try:
            pieces = paths.pieces_of(entity)[0]
        except paths.PathError as e:
            raise CommandFault(str(e), hint=e.hint)
        out += [(eid, piece, space_key) for piece in pieces]
    return out


def _curve_values(piece: paths.ArcSeg) -> dict:
    delta = abs(piece.sweep)
    r = piece.radius
    chord = 2.0 * r * math.sin(math.radians(delta) / 2.0)
    a, b = piece.start, piece.end
    chord_az = direction_to_azimuth(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])))
    return {"radius": r, "delta": delta, "length": piece.length,
            "tangent": r * math.tan(math.radians(delta) / 2.0), "chord": chord,
            "chord_bearing": format_bearing(chord_az)}


def _line_values(piece: paths.Seg) -> dict:
    az = direction_to_azimuth(piece.direction)
    return {"bearing": format_bearing(az), "length": piece.length, "azimuth": az}


def _order_key(doc: Document, name: str):
    """A function giving the station along an alignment (this document's or a
    referenced one -- ordering only reads it) of a point."""
    from roaddraft.document.references import find_reference_alignment
    if name in doc.design.alignments:
        align, to_base = doc.design.alignments[name], (lambda q: q)
    else:
        found = find_reference_alignment(doc, name) if ":" in name else None
        if found is None:
            raise CommandFault(f"no alignment {name!r} to order the segments along",
                               hint=f"alignments: {list(doc.design.alignments) or 'none'}; a "
                                    f"referenced one is 'DESIGN:SR-100'")
        align, placement = found
        to_base = placement.to_base

    def station(q):
        try:
            return align.xy_to_station(to_base(q))["station"]
        except Exception:
            return math.inf
    return station


def _visible_mid(doc: Document, sheet, piece):
    """``(viewport, model point, heading)`` at the middle of the part of a
    piece a sheet shows, or None when it shows none of it."""
    from roaddraft.document import viewmap
    cls, fields = paths.entity_fields_of(piece)
    probe = cls(id="probe", **fields)
    for vp in sheet.viewports:
        seen = viewmap.point_at_visible(doc, probe, "mid", vp)
        if seen is not None:
            point, direction, _shown = seen
            return vp, point, direction if direction is not None else piece.dir_at(0.0)
    return None


def label_segments(doc: Document, p: dict):
    segments = _segments(doc, p["ids"])
    style_kind = p.get("style", "values")
    if style_kind not in ("values", "tags"):
        raise CommandFault(f"style must be values or tags, got {style_kind!r}")
    seg_space = segments[0][2]
    if any(sk != seg_space for _e, _pc, sk in segments):
        raise CommandFault("the entities are in different spaces; label one space at a time")
    if p.get("order_along"):
        station = _order_key(doc, p["order_along"])
        segments.sort(key=lambda seg: station(seg[1].point_at(seg[1].length / 2.0)))
    target_key = seg_space
    sheet = None
    if "space" in p:
        target_key, _c = _space(doc, p["space"])
        if target_key != seg_space:
            if seg_space != "model" or target_key not in doc.sheets:
                raise CommandFault(f"labels for linework in {_space_label(doc, seg_space)} go "
                                   f"there, or on a sheet that shows the model")
            sheet = doc.sheets[target_key]
            if not sheet.viewports:
                raise CommandFault(f"sheet {sheet.name} has no viewport to see the linework "
                                   f"through", hint="create_viewport first")
    height = float(p.get("text_height", _paper_to_space(doc, target_key, LABEL_TEXT_IN)))
    gap = float(p.get("offset", height * 0.6))
    places = int(p.get("precision", 2))
    tstyle = _style(doc, p.get("text_style", doc.settings["current_text_style"]))
    common = _entity_common(doc, {k: v for k, v in p.items() if k != "space"})
    container = doc.resolve_space(target_key)[1]
    record = anno.text_record(doc, height, gap) if target_key == "model" else None
    created: List[str] = []
    warnings: List[str] = []
    line_rows, curve_rows = [], []
    line_no = int(p.get("line_start", 1))
    curve_no = int(p.get("curve_start", 1))

    def place(text, at, heading, above: bool):
        rotation = geo.upright(heading)
        ux, uy = math.cos(math.radians(rotation + 90.0)), math.sin(math.radians(rotation + 90.0))
        sign = 1.0 if above else -1.0
        position = [at[0] + ux * gap * sign, at[1] + uy * gap * sign]
        eid = doc.new_id("text")
        container[eid] = Text(id=eid, **common, position=position, content=text,
                              height=height, style=tstyle, rotation_deg=rotation,
                              halign="center", valign="bottom" if above else "top",
                              annotative=record)
        created.append(eid)

    skipped = []
    n_lines = n_curves = 0
    for eid, piece, _sk in segments:
        if sheet is not None:
            seen = _visible_mid(doc, sheet, piece)
            if seen is None:
                skipped.append(eid)
                continue
            vp, mid, heading = seen
            t = vp.transform()
            mid, heading = t.to_paper(mid), heading + t.rotation_deg
        else:
            mid = piece.point_at(piece.length / 2.0)
            heading = piece.dir_at(piece.length / 2.0)
        if isinstance(piece, paths.Seg):
            n_lines += 1
            v = _line_values(piece)
            if style_kind == "values":
                place(v["bearing"], mid, heading, True)
                place(f"{v['length']:.{places}f}'", mid, heading, False)
            else:
                tag = f"L{line_no}"
                line_no += 1
                place(tag, mid, heading, True)
                line_rows.append([tag, v["bearing"], f"{v['length']:.{places}f}'"])
        else:
            n_curves += 1
            v = _curve_values(piece)
            if style_kind == "values":
                place(f"R={v['radius']:.{places}f}' \u0394={format_dms(v['delta'])}",
                      mid, heading, True)
                place(f"L={v['length']:.{places}f}'", mid, heading, False)
            else:
                tag = f"C{curve_no}"
                curve_no += 1
                place(tag, mid, heading, True)
                curve_rows.append([tag, f"{v['radius']:.{places}f}'", format_dms(v["delta"]),
                                   f"{v['length']:.{places}f}'", f"{v['tangent']:.{places}f}'",
                                   v["chord_bearing"], f"{v['chord']:.{places}f}'"])
    if skipped:
        warnings.append(f"no viewport of {sheet.name} shows {', '.join(dict.fromkeys(skipped))}; "
                        f"those segments were not labelled")
    if not created:
        raise CommandFault("nothing was labelled: no segment is shown where the labels go",
                           hint="find_entities with visible_on lists what a sheet shows")
    tables = []
    if style_kind == "tags":
        spec = p.get("table")
        if not spec:
            raise CommandFault("tags need a table to list their values: table {position "
                               "(top-left corner), space (default where the tags go)}")
        tkey, _c = _space(doc, spec.get("space", target_key))
        th = float(spec.get("text_height", _paper_to_space(doc, tkey, LABEL_TEXT_IN)))
        x, y = [float(v) for v in spec["position"]]
        for title, headers, rows in (
                ("LINE TABLE", ["LINE", "BEARING", "LENGTH"], line_rows),
                ("CURVE TABLE", ["CURVE", "RADIUS", "DELTA", "LENGTH", "TANGENT", "CHORD BRG",
                                 "CHORD"], curve_rows)):
            if not rows:
                continue
            widths = _column_widths(headers, rows, th)
            _, table = _add(doc, tkey, "table", Table, {
                **common, "position": [x, y],
                "columns": [{"header": h, "width": w} for h, w in zip(headers, widths)],
                "rows": rows, "text_height": th, "title": title, "style": tstyle})
            created.append(table.id)
            tables.append(f"{title.lower()} {table.id} ({len(rows)} rows)")
            y -= table.size()[1] + th * 2.0
    where = f"sheet {sheet.name}" if sheet is not None else _space_label(doc, target_key)
    what = "bearings and distances" if style_kind == "values" else "tags"
    message = (f"{what} on {n_lines} line{'s' if n_lines != 1 else ''} and {n_curves} "
               f"curve{'s' if n_curves != 1 else ''} in {where}")
    if style_kind == "tags":
        message += (f" ({', '.join(r[0] for r in line_rows + curve_rows)})")
    if tables:
        message += "; " + ", ".join(tables)
    return message, _diff(created=created), warnings


# ------------------------------------------------------ station and offset


def _alignment(doc: Document, p: dict, **kw):
    from roaddraft.commands import design_handlers as dh
    return dh._alignment(doc, p, **kw)


def _design_fault(e) -> CommandFault:
    return CommandFault(str(e), hint=getattr(e, "hint", None))


def _offset_run(align, a, b) -> List[paths.Piece]:
    """The alignment's offset chain between two anchor points at one offset,
    travelled from ``a`` to ``b``."""
    from roaddraft.design.offsets import offset_pieces
    lo, hi = sorted((a.station, b.station))
    pieces = []
    for op in offset_pieces(align, a.offset, (lo, hi)):
        if op.kind == "tangent":
            pieces.append((paths.Seg(op.start, op.end), op))
        else:
            # stored counter-clockwise; travel with stationing on a right curve is clockwise
            if op.direction == "L":
                piece = paths.ArcSeg(op.center, op.radius, op.start_angle_deg,
                                     op.end_angle_deg)
            else:
                piece = paths.ArcSeg(op.center, op.radius, op.end_angle_deg,
                                     op.start_angle_deg)
            pieces.append((piece, op))
    if b.station < a.station:
        pieces = [(pc.reversed(), op) for pc, op in reversed(pieces)]
    return pieces


def draw_station_offset(doc: Document, p: dict):
    from roaddraft.design.anchors import resolve_anchor
    from roaddraft.design.errors import DesignError
    space_key, _container = _space(doc, p.get("space", "model"))
    if space_key != "model":
        raise CommandFault("stations and offsets are model-space feet; draw in model space",
                           hint="a sheet sees the result through its viewports")
    align = _alignment(doc, p, referenced=True)
    if len(p["points"]) < 2:
        raise CommandFault("give at least two station-and-offset points to draw between")
    try:
        anchors = [resolve_anchor(align, value) for value in p["points"]]
    except DesignError as e:
        raise _design_fault(e)
    follow = bool(p.get("follow", True))
    runs: List[List[Tuple[paths.Piece, object]]] = []
    notes = []
    st = align.stations()
    pairs = list(zip(anchors, anchors[1:]))
    if p.get("close"):
        pairs.append((anchors[-1], anchors[0]))
    for a, b in pairs:
        same_offset = abs(a.offset - b.offset) < 1e-9
        if geo.distance(a.point, b.point) < 1e-9:
            continue
        if follow and same_offset and abs(a.station - b.station) > 1e-9:
            try:
                run = _offset_run(align, a, b)
            except DesignError as e:
                raise _design_fault(e)
            runs.append(run)
            side = "RT" if a.offset > 0 else "LT"
            notes.append(f"along {align.name} {abs(a.offset):.2f}' {side if a.offset else ''} "
                         f"from {a.station_text} to {b.station_text}".replace("  ", " "))
        else:
            seg = paths.Seg(a.point, b.point)
            runs.append([(seg, None)])
            az = direction_to_azimuth(seg.direction)
            notes.append(f"{format_bearing(az)} {seg.length:.2f}' from {a.station_text} "
                         f"{_off_text(a.offset)} to {b.station_text} {_off_text(b.offset)}")
    if not runs:
        raise CommandFault("the points all fall in one place; there is nothing to draw")
    common = _entity_common(doc, p)
    created = []
    if p.get("polyline"):
        pieces = [pc for run in runs for pc, _op in run]
        closed = bool(p.get("close")) and geo.distance(pieces[-1].end, pieces[0].start) < 1e-6
        _, e = _add(doc, "model", "polyline", Polyline,
                    {**common, **paths.polyline_fields_of(pieces, closed)})
        created.append(e.id)
    else:
        for run in runs:
            for piece, op in run:
                cls, fields = paths.entity_fields_of(piece)
                anchor = None
                if op is not None:
                    anchor = {"alignment": align.name, "ref": op.ref, "kind": "offset",
                              "station": op.station, "offset": op.offset}
                _, e = _add(doc, "model", cls.TYPE, cls, {**common, **fields, "anchor": anchor})
                created.append(e.id)
    pts = "; ".join(f"{a.station_text} {_off_text(a.offset)} = {_fmt(a.point)}" for a in anchors)
    return (f"drawn by station and offset on {align.name} ({len(created)} "
            f"entit{'y' if len(created) == 1 else 'ies'}: {', '.join(created)}): "
            + "; ".join(notes) + f". Points: {pts}", _diff(created=created), [])


def _off_text(offset: float) -> str:
    if abs(offset) < 1e-9:
        return "CL"
    return f"{abs(offset):.2f}' {'RT' if offset > 0 else 'LT'}"


# ------------------------------------------------------------- along a path


def sample_path(doc: Document, p: dict):
    """Positions along ``p['path']`` -- an entity, a chain of entities, or an
    alignment of this document -- every ``every`` or ``count`` of them, from
    ``from`` to ``to``, ``offset`` to the right. Returns ``([{point, heading,
    along, station?}], description)``."""
    from roaddraft.design.anchors import parse_offset
    from roaddraft.design.errors import DesignError
    spec = p["path"]
    if ("every" in p) == ("count" in p):
        raise CommandFault("say how many with exactly one of every (a spacing) or count "
                           "(evenly spaced, both ends included)")
    try:
        offset = parse_offset(p.get("offset", 0.0))
    except DesignError as e:
        raise _design_fault(e)
    every = float(p["every"]) if "every" in p else None
    count = int(p["count"]) if "count" in p else None
    if every is not None and every <= 0:
        raise CommandFault("every must be a positive spacing")
    if count is not None and count < 1:
        raise CommandFault("count must be at least 1")
    positions = []
    if is_alignment_path(doc, spec):
        align = _alignment(doc, {"alignment": spec})
        st = align.stations()
        begin, end = float(align.begin_station), float(align.begin_station) + align.length
        try:
            lo = st.parse(p["from"]) if "from" in p else begin
            hi = st.parse(p["to"]) if "to" in p else end
        except DesignError as e:
            raise _design_fault(e)
        lo, hi = max(lo, begin), min(hi, end)
        if hi < lo:
            raise CommandFault("to comes before from along the alignment")
        stations = _spaced(lo, hi, every, count, round_to=every if "from" not in p else None)
        for s in stations:
            point, heading, _i = align.station_to_xy(s, offset)
            positions.append({"point": point, "heading": heading, "along": s - begin,
                              "station": st.format(s)})
        what = (f"{align.name} from {st.format(lo)} to {st.format(hi)}"
                + (f", {_off_text(offset)}" if offset else ""))
    else:
        ids = [spec] if isinstance(spec, str) else list(spec)
        entities = [_resolve(doc, eid)[0] for eid in ids]
        try:
            path = paths.Path.of_chain(entities) if len(entities) > 1 else \
                paths.Path.of_entity(entities[0])
        except paths.PathError as e:
            raise CommandFault(str(e), hint=e.hint)
        lo = float(p.get("from", 0.0))
        hi = float(p.get("to", path.length))
        lo, hi = max(lo, 0.0), min(hi, path.length)
        if hi < lo:
            raise CommandFault("to comes before from along the path")
        stations = _spaced(lo, hi, every, count, closed=path.closed and lo == 0.0
                           and abs(hi - path.length) < 1e-9)
        for s in stations:
            q = path.point_at(s)
            heading = path.dir_at(s)
            if offset:
                rx, ry = math.sin(math.radians(heading)), -math.cos(math.radians(heading))
                q = [q[0] + rx * offset, q[1] + ry * offset]
            positions.append({"point": q, "heading": heading, "along": s})
        what = (f"{' > '.join(ids)} from {lo:.2f}' to {hi:.2f}'"
                + (f", {_off_text(offset)}" if offset else ""))
    if not positions:
        raise CommandFault("no positions fall between from and to at that spacing")
    if every is not None:
        what += f" every {every:g}'"
    return positions, what


def is_alignment_path(doc: Document, spec) -> bool:
    """Is a path given by name an alignment (rather than an entity id)?"""
    if not isinstance(spec, str):
        return False
    if spec in doc.design.alignments:
        return True
    if doc.find_entity(spec) is not None:
        return False
    from roaddraft.document.locate import resolve_entity
    if resolve_entity(doc, spec) is not None:
        return False
    if ":" in spec:
        return True  # a referenced alignment: _alignment explains why not
    raise CommandFault(f"path {spec!r} is neither an entity nor an alignment of this document",
                       hint=f"alignments: {list(doc.design.alignments) or 'none'}; entity ids "
                            f"come from find_entities, hit_test and snap")


def _path_space(doc: Document, spec) -> str:
    if is_alignment_path(doc, spec):
        return "model"
    first = spec if isinstance(spec, str) else spec[0]
    return _resolve(doc, first)[3]


def _spaced(lo: float, hi: float, every: Optional[float], count: Optional[int],
            round_to: Optional[float] = None, closed: bool = False) -> List[float]:
    if count is not None:
        if count == 1:
            return [lo]
        n = count if closed else count - 1
        return [lo + (hi - lo) * k / n for k in range(count)]
    s = lo if round_to is None else math.ceil((lo - 1e-9) / round_to) * round_to
    out = []
    while s <= hi + 1e-9 and len(out) <= 100000:
        out.append(min(s, hi))
        s += every
    if closed and out and abs(out[-1] - hi) < 1e-9 and len(out) > 1:
        out.pop()  # the end of a closed path is its start
    return out


def place_along(doc: Document, p: dict):
    positions, described = sample_path(doc, p)
    if len(positions) > 2000:
        raise CommandFault(f"{len(positions)} positions is too many for one command",
                           hint="space them wider, or place a stretch at a time (from / to)")
    space_key = _path_space(doc, p["path"])
    common = _entity_common(doc, p)
    align = bool(p.get("align", True))
    created = []
    if "block" in p:
        name = p["block"]
        if name not in doc.blocks:
            raise CommandFault(f"block {name!r} does not exist",
                               hint=f"blocks: {sorted(doc.blocks)}; define_block makes one")
        for pos in positions:
            rotation = (pos["heading"] if align else 0.0) + float(p.get("rotation", 0.0))
            _, e = _add(doc, space_key, "blockref", BlockRef, {
                **common, "block_name": name, "position": pos["point"],
                "scale": float(p.get("scale", 1.0)), "rotation_deg": rotation})
            created.append(e.id)
        what = f"block {name}"
    else:
        style = _point_style(doc, space_key, p)
        start = p.get("start_number")
        for pos in positions:
            n = next_point_number(doc, start)
            start = n + 1
            _, e = _add(doc, space_key, "point", Point, {
                **common, **style, "position": pos["point"], "number": n,
                "description": str(p.get("description", ""))})
            created.append(e.id)
        what = "points"
    first, last = positions[0], positions[-1]

    def where(pos):
        return pos.get("station") or f"{pos['along']:.2f}'"

    return (f"{len(created)} {what} along {described}: first at {where(first)} "
            f"{_fmt(first['point'])}, last at {where(last)} {_fmt(last['point'])}",
            _diff(created=created), [])


# -------------------------------------------------------------------- hatch


def build_loops(doc: Document, space_key: str, p: dict):
    """The boundary loops an area command names: ``(loops, ids, how)``.
    Exactly one of ``boundary`` (ids), ``points`` (a polygon) or ``at`` (a
    point inside linework that closes around it)."""
    ways = [k for k in ("boundary", "points", "at") if k in p]
    if len(ways) != 1:
        raise CommandFault(
            "give the area with exactly one of boundary (closed entities, or entities that "
            "join into closed loops), points (a polygon) or at (a point inside the area)",
            hint="at traces the linework around the point the way AutoCAD's pick-a-point "
                 "hatch does; boundary uses the entities named")
    tol = float(p.get("gap_tolerance", regions.GAP_TOL))
    if ways[0] == "points":
        pts = [[float(q[0]), float(q[1])] for q in p["points"]]
        if len(pts) < 3:
            raise CommandFault("a polygon needs at least three points")
        return [{"vertices": pts}], [], f"the polygon through {len(pts)} points"
    if ways[0] == "boundary":
        entities, ids = [], []
        loops = []
        for eid in p["boundary"]:
            entity, _owner, _ref, sk = _resolve(doc, eid)
            if sk != space_key:
                raise CommandFault(f"{eid} is in {_space_label(doc, sk)}, not "
                                   f"{_space_label(doc, space_key)}")
            ids.append(eid)
            if isinstance(entity, Hatch):
                loops += [dict(loop) for loop in entity.loops]
            else:
                entities.append(entity)
        try:
            loops += regions.chain_loops(entities, tol) if entities else []
        except regions.RegionError as e:
            raise CommandFault(str(e), hint=e.hint)
        return loops, ids, f"the boundary {', '.join(ids)}"
    point = [float(p["at"][0]), float(p["at"][1])]
    layers = set(p["boundary_layers"]) if p.get("boundary_layers") else None
    pieces, owners, closed = [], [], []
    for item in snaps.space_items(doc, space_key, p.get("include_references", True)):
        if layers is not None and item.entity.layer not in layers:
            continue
        if not isinstance(item.entity, paths.PATH_ENTITY_TYPES):
            continue
        try:
            item_pieces = paths.pieces_of(item.entity)[0]
        except paths.PathError:
            continue
        pieces += item_pieces
        owners += [item.eid] * len(item_pieces)
        loop = regions.loop_of_entity(item.entity)
        if loop is not None:
            closed.append((item.eid, loop))
    try:
        found = regions.trace_region(pieces, owners, point, tol,
                                     islands=bool(p.get("islands", True)),
                                     closed_shapes=closed)
    except regions.RegionError as e:
        raise CommandFault(str(e), hint=e.hint)
    loops = [found["outer"]] + found["islands"]
    n = len(found["islands"])
    how = (f"the region around {_fmt(point)}, bounded by {', '.join(found['ids'])}"
           + (f" ({n} island{'s' if n != 1 else ''})" if n else ""))
    return loops, found["ids"], how


def _clean(loop: dict) -> dict:
    out = {"vertices": [[round(v[0], 9), round(v[1], 9)] for v in loop["vertices"]]}
    if loop.get("bulges"):
        out["bulges"] = [round(b, 12) for b in loop["bulges"]]
    return out


def area_text(area: float, space_key: str) -> str:
    if space_key != "model":
        return f"{area:,.2f} sq in"
    return f"{area:,.2f} sq ft ({area / 9.0:,.2f} SY, {area / 43560.0:,.4f} ac)"


def default_hatch_scale(doc: Document, space_key: str) -> float:
    if space_key != "model":
        return 1.0
    scale = anno.current_scale(doc)
    return float(scale if scale is not None else FIXED_FT_PER_IN)


def hatch(doc: Document, p: dict):
    space_key, _container = _space(doc, p["space"])
    loops, ids, how = build_loops(doc, space_key, p)
    try:
        pattern = hatching.canonical_pattern(p.get("pattern", "SOLID"))
    except ValueError as e:
        raise CommandFault(str(e))
    scale = float(p.get("scale", default_hatch_scale(doc, space_key)))
    opacity = float(p.get("opacity", 1.0))
    if not 0.0 < opacity <= 1.0:
        raise CommandFault("opacity is more than 0 and at most 1 (1 = opaque)")
    loops = regions.oriented([_clean(loop) for loop in loops])
    measure = regions.region_measure(loops)
    if measure["area"] <= 1e-9:
        raise CommandFault("the boundary encloses no area")
    _, e = _add(doc, space_key, "hatch", Hatch, {
        **_entity_common(doc, p), "loops": loops, "pattern": pattern, "scale": scale,
        "angle_deg": float(p.get("angle", 0.0)), "opacity": opacity})
    warnings = []
    if pattern != "SOLID":
        gap = hatching.spacing(pattern, scale)
        bb = e.bbox(doc)
        extent = max(bb[2] - bb[0], bb[3] - bb[1])
        if gap < math.inf and extent / gap > 1500:
            better = scale * extent / gap / 300.0
            warnings.append(f"{pattern} at scale {scale:g} draws lines {gap:.3g} apart across "
                            f"{extent:.0f}: very dense. A scale near {better:.3g} reads better")
    islands = sum(1 for row in measure["loops"] if row["kind"] == "island")
    return (f"hatch {e.id} ({pattern}{'' if pattern == 'SOLID' else f', scale {scale:g}'}) "
            f"in {_space_label(doc, space_key)}: {how}; area {area_text(measure['area'], space_key)}"
            + (f", {islands} island{'s' if islands != 1 else ''} left open" if islands else ""),
            _diff(created=[e.id]), warnings)


__all__ = ["create_points", "place_point_table", "label_segments", "draw_station_offset",
           "place_along", "hatch", "sample_path", "build_loops", "next_point_number",
           "point_numbers", "parse_point_text", "area_text"]
