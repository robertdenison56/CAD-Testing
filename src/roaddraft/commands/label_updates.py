"""Keeping what is lettered from an alignment in step with its design.

The labelers letter a design once, as it stands: place_label, annotate_stationing
and place_curve_table leave text, ticks and tables carrying an anchor record
(the alignment, the ref -- a station, PC-1, T-2 -- and how it was posed). When
the design changes they are stale. Civil 3D and ORD labels follow their
alignment; here ``follow_design`` does it, from the records alone, the way the
verifier recomputes a label (resolve_record, compile_label, sheet_pose):

* a place_label label is posed again at its anchor, its lettering recomputed
  where the engine lettered it (``content_auto``), a curve-number bubble and
  leader with it;
* a stationing set (annotate_stationing's ticks, station numbers and curve-point
  and equation labels) is laid out again with the settings it was lettered with,
  read back off the set, so new stations get ticks and stations past a new end
  lose theirs;
* a curve table is refilled.

``modify_alignment`` runs it on the document's own labels; ``update_labels``
runs it on any alignment, including one read through a reference
('BASE:RTE-7'), whose basefile may have changed since its labels were lettered.
Anchored linework (draw_alignment's centerline, draw_offset's edges) is not a
label: it is reported, and redrawn by those commands with replace=true.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from roaddraft.commands.handlers import CommandFault, _diff
from roaddraft.core import geometry as geo
from roaddraft.core.units import parse_station
from roaddraft.design.anchors import parse_anchor, resolve_anchor, resolve_record
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import (
    CURVE_COLUMNS, LABEL_KINDS, SHEET_LABEL_OFFSET, TickSpec, compile_label, curve_table_rows,
    label_pose, sheet_pose, stationing_plan,
)
from roaddraft.document import annotation as anno
from roaddraft.document.document import Document
from roaddraft.document.entities import Circle, Line, Table, Text

#: the kinds annotate_stationing letters, and the curve-point ones among them
STATIONING_KINDS = ("tick", "station", "pc", "pt", "pcc", "prc", "equation")
POINT_KINDS = ("pc", "pt", "pcc", "prc")
#: anchored linework, which the labelers do not draw
LINEWORK_KINDS = ("element", "offset")
#: how far a label may sit from where its anchor puts it and still be in step
#: (feet in model space, inches on a sheet), and its rotation (degrees)
TOL = 1e-6
ANGLE_TOL = 1e-6
#: how far a label may stand from its no-twist pose and still be taken as lettered through
#: no twist (degrees): a pose differs by the twist itself, so anything finer than the
#: smallest twist a sheet uses will do
UNTWISTED_DEG = 0.01


@dataclass
class Followed:
    """What ``follow_design`` did to the entities anchored to one alignment."""
    alignment: str
    modified: List[str] = field(default_factory=list)
    created: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    #: labels re-posed, stationing sets laid out again, tables refilled
    labels: int = 0
    stationing: int = 0
    tables: int = 0
    #: ``(id, why)``: labels whose anchor no longer exists on the design
    stranded: List[Tuple[str, str]] = field(default_factory=list)
    #: anchored linework left as drawn
    linework: List[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.modified or self.created or self.deleted)

    def summary(self) -> str:
        parts = []
        if self.labels:
            parts.append(f"{_plural(self.labels, 'label')} re-placed")
        if self.stationing:
            parts.append(f"{_plural(self.stationing, 'stationing set')} laid out again")
        if self.tables:
            parts.append(f"{_plural(self.tables, 'curve table')} refilled")
        return ", ".join(parts) if parts else "every label already in step"

    def warnings(self) -> List[str]:
        out = []
        if self.stranded:
            listed = "; ".join(f"{eid}: {why}" for eid, why in self.stranded[:8])
            more = f" (and {len(self.stranded) - 8} more)" if len(self.stranded) > 8 else ""
            out.append(f"{_plural(len(self.stranded), 'label')} anchored to {self.alignment} "
                       f"could not follow it -- {listed}{more}; delete them or place them "
                       f"again")
        return out


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def anchored(doc: Document, alignment: str) -> List[Tuple[str, object]]:
    """``(space_key, entity)`` for every entity anchored to ``alignment``."""
    out = []
    for e in doc.model_entities.values():
        if e.anchor and e.anchor.get("alignment") == alignment:
            out.append(("model", e))
    for sheet in doc.sheets.values():
        for e in sheet.entities.values():
            if e.anchor and e.anchor.get("alignment") == alignment:
                out.append((sheet.id, e))
    return out


def _container(doc: Document, space_key: str) -> dict:
    return doc.model_entities if space_key == "model" else doc.sheets[space_key].entities


def follow_design(doc: Document, name: str, align: Alignment,
                  before: Optional[Alignment] = None) -> Followed:
    """Bring everything lettered from alignment ``name`` (as its labels name it:
    'RTE-7', or 'BASE:RTE-7' through a reference) up to date with ``align``.
    ``before`` is the design the labels were lettered from, when known: it
    tells a stationing set that ran to the old end from one stopped short."""
    out = Followed(name)
    groups: Dict[str, list] = {}
    for space_key, e in anchored(doc, name):
        kind = e.anchor.get("kind")
        if (space_key == "model" and kind in STATIONING_KINDS
                and e.anchor.get("placed_by") == "annotate_stationing"):
            groups.setdefault(space_key, []).append(e)
        elif isinstance(e, Text) and kind in LABEL_KINDS:
            _repose_label(doc, space_key, e, align, out)
        elif isinstance(e, Table) and kind == "curve_table":
            _refill_table(e, align, out)
        elif kind in LINEWORK_KINDS:
            out.linework.append(e.id)
    for space_key, group in groups.items():
        _relay_stationing(doc, space_key, group, align, before, out)
    return out


# ------------------------------------------------------------------ labels


def _resolve(align: Alignment, rec: dict):
    """The anchor point a record names on ``align``: a named point (PC-1, T-2)
    by its name; a station at its recorded raw station while that still reads
    as the station lettered, else at the station lettered (the begin station
    or an equation moved)."""
    named = parse_anchor(rec["ref"])
    if named.kind_hint == "station" and rec.get("station") is not None:
        st = align.stations()
        raw = float(rec["station"])
        if st.in_range(raw) and abs(st.to_display(raw)[0] - named.station_display) < TOL:
            return resolve_record(align, rec)
    named.offset = float(rec.get("offset") or 0.0)
    return resolve_anchor(align, named)


def _repose_label(doc: Document, space_key: str, e: Text, align: Alignment,
                  out: Followed) -> None:
    rec = e.anchor
    vp = None
    if space_key != "model":
        vp = doc.sheets[space_key].viewport_by_id(rec.get("viewport"))
        if vp is None:
            out.stranded.append((e.id, f"its viewport {rec.get('viewport')} is not on the sheet"))
            return
    try:
        ap = _resolve(align, rec)
        spec = compile_label(
            align, ap, rec["kind"], side=rec.get("side"),
            label_offset=rec.get("label_offset") if space_key == "model" else None,
            rotation=rec.get("rotation"),
            content=None if rec.get("content_auto") else e.content,
            # a sheet label reads through its viewport's twist (place_label)
            view_rotation=float(vp.rotation_deg if vp is not None
                                else rec.get("view_rotation") or 0.0))
    except DesignError as err:
        out.stranded.append((e.id, str(err)))
        return
    if space_key == "model":
        position, rotation = spec.position, spec.rotation_deg
    else:
        offset = rec.get("label_offset")
        position, rotation = sheet_pose(spec, vp.transform(), vp.rotation_deg,
                                        SHEET_LABEL_OFFSET if offset is None else float(offset))
    station = float(ap.station)
    if (geo.distance(position, e.position) <= TOL
            and abs((rotation - e.rotation_deg + 180.0) % 360.0 - 180.0) <= ANGLE_TOL
            and spec.content == e.content
            and abs(station - float(rec.get("station") or 0.0)) <= TOL):
        return
    e.position = [float(position[0]), float(position[1])]
    e.rotation_deg = float(rotation)
    e.content = spec.content
    e.halign, e.valign = spec.halign, spec.valign
    e.anchor = dict(rec, station=station)
    out.modified.append(e.id)
    out.labels += 1
    if rec["kind"] == "mc":
        tip = list(spec.anchor_point) if vp is None else vp.transform().to_paper(spec.anchor_point)
        _move_bubble(_container(doc, space_key), e, tip, out)


def _move_bubble(container: dict, text: Text, tip, out: Followed) -> None:
    """A curve number's bubble round its text and its leader to the curve,
    moved with it (design_handlers._add_bubble)."""
    rec = text.anchor
    center = [float(text.position[0]), float(text.position[1])]
    parts = [e for e in container.values() if e.anchor
             and (e.anchor.get("alignment"), e.anchor.get("ref")) == (rec["alignment"], rec["ref"])
             and e.anchor.get("kind") in ("mc_bubble", "mc_leader")]
    radius = next((e.radius for e in parts if isinstance(e, Circle)), 0.0)
    for e in parts:
        if isinstance(e, Circle):
            e.center = center
        elif isinstance(e, Line):
            d = geo.distance(center, tip)
            e.start = ([center[0] + (tip[0] - center[0]) * radius / d,
                        center[1] + (tip[1] - center[1]) * radius / d]
                       if d > radius + 1e-9 else list(center))
            e.end = [float(tip[0]), float(tip[1])]
        else:
            continue
        e.anchor = dict(e.anchor, station=rec["station"])
        out.modified.append(e.id)


# -------------------------------------------------------------- stationing


def _display(e) -> Optional[float]:
    try:
        return float(parse_station(e.anchor["ref"]))
    except (KeyError, ValueError):
        return None


def _settings(group: list, align: Alignment, before: Optional[Alignment]) -> dict:
    """The annotate_stationing settings a set was lettered with, read back off
    its ticks and labels."""
    ticks = [e for e in group if e.anchor["kind"] == "tick" and isinstance(e, Line)]
    numbers = [e for e in group if e.anchor["kind"] == "station" and isinstance(e, Text)]
    points = [e for e in group if e.anchor["kind"] in POINT_KINDS and isinstance(e, Text)]
    equations = [e for e in group if e.anchor["kind"] == "equation" and isinstance(e, Text)]
    shown = sorted({d for d in (_display(t) for t in ticks) if d is not None})
    steps = Counter(round(b - a, 6) for a, b in zip(shown, shown[1:]) if b - a > TOL)
    interval = steps.most_common(1)[0][0] if steps else 100.0
    settings = {"interval": interval, "include_pc_pt": bool(points),
                "include_equations": bool(equations),
                "lettering": "full" if any("+" in t.content for t in numbers) else "caltrans"}
    if ticks:
        settings["tick_half"] = geo.distance(ticks[0].start, ticks[0].end) / 2.0
    if numbers:
        settings["label_offset"] = float(numbers[0].anchor.get("label_offset") or 0.0)
        settings["station_side"] = numbers[0].anchor.get("side")
    marks = points + equations
    if marks:
        settings["point_offset"] = float(marks[0].anchor.get("label_offset") or 0.0)
        settings["point_side"] = marks[0].anchor.get("side")
    texts = numbers + marks
    if texts:
        settings["view_rotation"] = _view_rotation(texts, before or align)
    raws = [float(t.anchor["station"]) for t in ticks if t.anchor.get("station") is not None]
    if raws:
        lo, hi = min(raws), max(raws)
        ran = before or align
        begin = float(ran.begin_station)
        end = begin + ran.length
        if lo > begin + interval + TOL or hi < end - interval - TOL:
            settings["station_range"] = (lo, hi)
    return settings


def _view_rotation(texts: list, align: Alignment) -> float:
    """The twist a set was lettered to read through.  A label records it
    (``view_rotation`` in its anchor) when there is one; a label lettered
    through no twist records none, and nor does one lettered before the
    record carried it.  Laying the second kind out again through no twist
    turns every label whose line runs past 90 degrees in the model round, so
    it reads upside down through the viewport it was posed for (L-1's "TB1",
    at 93.96 degrees under a -89.94 degree twist).  So when no twist is
    recorded: no twist, when no twist poses every label the way it stands;
    otherwise the twist read off the pose -- the one that keeps a label that
    runs along its line the way it stands, upright through the view when the
    text runs with the line, turned round when it runs against it.

    (Until 2026-11-12 the pose was read on every set that recorded no twist,
    untwisted ones too.  That guess keeps a station number level, which is not
    no twist, and laid a curve point's label out upside down on a plain
    untwisted sheet after a restation; Robert: "Fix it now".)"""
    recorded = [t for t in texts if t.anchor.get("view_rotation") is not None]
    if recorded:
        return float(recorded[0].anchor["view_rotation"])
    if _untwisted(texts, align):
        return 0.0
    along = [t for t in texts if t.anchor.get("rotation", "along") == "along"
             and t.anchor.get("station") is not None]
    if not along:
        return 0.0
    t = along[0]
    dist = min(max(float(t.anchor["station"]) - float(align.begin_station), 0.0), align.length)
    direction = float(align.direction_at(dist))
    against = abs(_fold(float(t.rotation_deg) - direction)) > 90.0
    return _fold(180.0 - direction if against else -direction)


def _untwisted(texts: list, align: Alignment) -> bool:
    """Whether every one of ``texts`` stands as a labeler poses it through no
    twist on ``align``, the design it was lettered from."""
    posed = [t for t in texts if t.anchor.get("station") is not None]
    if not posed:
        return True
    for t in posed:
        rec = t.anchor
        dist = min(max(float(rec["station"]) - float(align.begin_station), 0.0), align.length)
        direction = float(align.direction_at(dist))
        side = rec.get("side") if rec.get("side") in ("left", "right") else "left"
        want, _h, _v = label_pose(direction, side, rec.get("rotation") or "along", 0.0)
        if abs(_fold(float(t.rotation_deg) - want)) > UNTWISTED_DEG:
            return False
    return True


def _fold(angle_deg: float) -> float:
    """An angle in (-180, 180]."""
    a = (float(angle_deg) + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def _relay_stationing(doc: Document, space_key: str, group: list, align: Alignment,
                      before: Optional[Alignment], out: Followed) -> None:
    s = _settings(group, align, before)
    try:
        plan = stationing_plan(
            align, interval=s["interval"],
            **{k: s[k] for k in ("tick_half", "label_offset", "station_side", "point_side",
                                 "point_offset", "view_rotation", "station_range") if k in s},
            include_pc_pt=s["include_pc_pt"], include_equations=s["include_equations"],
            lettering=s["lettering"])
    except DesignError as err:
        out.stranded += [(e.id, f"its stationing cannot be laid out again: {err}")
                         for e in group]
        return
    if _same_layout(group, plan.items):
        return
    container = _container(doc, space_key)
    tick = next((e for e in group if isinstance(e, Line)), None)
    number = next((e for e in group if isinstance(e, Text) and e.anchor["kind"] == "station"),
                  None)
    mark = next((e for e in group if isinstance(e, Text) and e.anchor["kind"] != "station"),
                None)
    for e in group:
        del container[e.id]
        out.deleted.append(e.id)
    for item in plan.items:
        eid = doc.new_id("line" if isinstance(item, TickSpec) else "text")
        if isinstance(item, TickSpec):
            like = tick or number or mark
            container[eid] = Line(
                id=eid, layer=like.layer, color=like.color, linetype=like.linetype,
                start=item.start, end=item.end,
                anchor=dict(item.anchor_record(align.name), placed_by="annotate_stationing"),
                annotative=anno.tick_record(doc, s.get("tick_half", 0.0)) if tick
                and tick.annotative else None)
        else:
            like = (number if item.kind == "station" else mark) or number or mark or tick
            height = like.height if isinstance(like, Text) else (number or mark).height
            container[eid] = Text(
                id=eid, layer=like.layer, color=like.color, style=getattr(like, "style", None)
                or doc.settings["current_text_style"], position=item.position,
                content=item.content, height=height, rotation_deg=item.rotation_deg,
                halign=item.halign, valign=item.valign,
                anchor=dict(item.anchor_record(None), placed_by="annotate_stationing"),
                annotative=anno.text_record(doc, height, item.label_offset)
                if getattr(like, "annotative", None) else None)
        out.created.append(eid)
    out.stationing += 1


def _same_layout(group: list, items: list) -> bool:
    """Does the set already stand where the plan would put it?"""
    def key(kind, ref, points, content):
        return (kind, ref, tuple(round(v, 6) for p in points for v in p), content)

    have = Counter()
    for e in group:
        if isinstance(e, Line):
            have[key("tick", e.anchor["ref"], (e.start, e.end), None)] += 1
        elif isinstance(e, Text):
            have[key(e.anchor["kind"], e.anchor["ref"], (e.position,), e.content)] += 1
    want = Counter()
    for item in items:
        if isinstance(item, TickSpec):
            want[key("tick", item.station_text, (item.start, item.end), None)] += 1
        else:
            want[key(item.kind, item.ref, (item.position,), item.content)] += 1
    return have == want


# ------------------------------------------------------------------ tables


#: a curve table's header -> its column key (design/labels.CURVE_COLUMNS)
HEADER_KEYS = {header: key for key, (header, _w) in CURVE_COLUMNS.items()}


def _refill_table(table: Table, align: Alignment, out: Followed) -> None:
    keys = [HEADER_KEYS.get(c.get("header")) for c in table.columns]
    if None in keys:
        out.stranded.append((table.id, "its columns are not the engine's curve table columns"))
        return
    first, curves = 1, None
    if "curve" in keys:
        col = keys.index("curve")
        numbers = [int(m.group()) for m in (re.search(r"\d+", str(r[col])) for r in table.rows)
                   if m]
        if numbers:
            first = numbers[0]
            indices = [n - first + 1 for n in numbers]
            if indices != list(range(1, len(indices) + 1)):
                curves = [n for n in indices if 1 <= n <= len(align.curves())]
    try:
        _headers, rows, _widths = curve_table_rows(align, keys, curves, first_number=first)
    except DesignError as err:
        out.stranded.append((table.id, str(err)))
        return
    if [[str(v) for v in r] for r in table.rows] == rows:
        return
    table.rows = rows
    out.modified.append(table.id)
    out.tables += 1


# ----------------------------------------------------------------- command


def update_labels(doc: Document, p: dict):
    """Bring the labels anchored to an alignment -- this document's, or one read
    through a reference -- up to date with its design."""
    from roaddraft.commands.design_handlers import _alignment
    names = [p["alignment"]] if p.get("alignment") else sorted({
        e.anchor["alignment"] for _k, e in anchored_any(doc)})
    if not names:
        raise CommandFault("nothing in this document is anchored to an alignment",
                           hint="place_label, annotate_stationing and place_curve_table "
                                "letter a design; this follows them when it changes")
    reports, warnings = [], []
    created: List[str] = []
    modified: List[str] = []
    deleted: List[str] = []
    for name in names:
        align = _alignment(doc, {"alignment": name}, referenced=True)
        if not anchored(doc, name):
            raise CommandFault(f"nothing in this document is anchored to {name}",
                               hint="update_labels follows what place_label, "
                                    "annotate_stationing and place_curve_table lettered")
        done = follow_design(doc, name, align)
        reports.append(f"{name}: {done.summary()}")
        warnings += done.warnings()
        created += done.created
        modified += done.modified
        deleted += done.deleted
    return ("labels brought up to date -- " + "; ".join(reports),
            _diff(created=created, modified=modified, deleted=deleted), warnings)


def anchored_any(doc: Document) -> List[Tuple[str, object]]:
    """``(space_key, entity)`` for every label, stationing mark and curve table
    anchored to any alignment."""
    out = []
    for e in doc.model_entities.values():
        if e.anchor and e.anchor.get("kind") not in LINEWORK_KINDS:
            out.append(("model", e))
    for sheet in doc.sheets.values():
        for e in sheet.entities.values():
            if e.anchor and e.anchor.get("kind") not in LINEWORK_KINDS:
                out.append((sheet.id, e))
    return out


def stale_labels(doc: Document) -> Dict[str, int]:
    """``{alignment: n}``: how many labels anchored through a reference no
    longer stand where their design puts them (nothing is changed)."""
    from roaddraft.commands.design_handlers import _referenced_alignment
    out: Dict[str, int] = {}
    names = sorted({e.anchor["alignment"] for _k, e in anchored_any(doc)
                    if ":" in e.anchor["alignment"]
                    and e.anchor["alignment"] not in doc.design.alignments})
    for name in names:
        try:
            align = _referenced_alignment(doc, name)
        except CommandFault:
            continue
        trial = Document.from_dict(doc.to_dict())
        trial._path = doc._path
        trial._ref_cache = doc._ref_cache
        done = follow_design(trial, name, align)
        n = len(set(done.modified) | set(done.deleted)) + len(done.stranded)
        if n:
            out[name] = n
    return out


__all__ = ["Followed", "follow_design", "anchored", "update_labels", "stale_labels",
           "STATIONING_KINDS"]
