"""Design-model command handlers (Phase 1): alignments, profiles, anchored
labels, curve tables, LandXML import, and alignment-mode stationing.

Same contract as ``handlers.py``: ``name(doc, p) -> (message, diff, warnings)``,
semantic problems raise ``CommandFault`` (design errors are re-raised with
their hint) and the bus keeps every command atomic.  Every entity these
handlers create carries an ``anchor`` record naming the design element it
came from, which is what the verifier checks.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from roaddraft.adapters.landxml import LandXMLError, parse_landxml
from roaddraft.commands.handlers import (
    CommandFault, _add, _annotation_warnings, _diff, _entity_common, _layer, _space,
    _space_label, _style,
)
from roaddraft.core import geometry as geo
from roaddraft.core.units import parse_station
from roaddraft.design.anchors import infer_kind, parse_anchor, parse_offset, resolve_anchor
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import (
    PI, Alignment, TangentElement, alignment_from_elements, compile_pis, elements_from_dicts,
)
from roaddraft.design.labels import (
    MODEL_TEXT_HEIGHT, SHEET_LABEL_OFFSET, SHEET_TEXT_HEIGHT, TickSpec, compile_label,
    curve_table_rows, sheet_pose, stationing_plan,
)
from roaddraft.design.offsets import offset_pieces
from roaddraft.design.stations import StationSystem, build_equations
from roaddraft.design.vertical import PVI, Profile
from roaddraft.document import annotation as anno
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Line, Table, Text

ALIGNMENT_CHANGES = ("pis", "begin_station", "equations", "description", "rename")


# ---------------------------------------------------------------- helpers


def _fault(e: DesignError) -> CommandFault:
    return CommandFault(str(e), hint=e.hint)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _offset_text(value: float) -> str:
    """``-12.0 -> "12.00' LT"`` -- the way a drafter reads an offset back."""
    side = "RT" if value > 0 else ("LT" if value < 0 else "ON")
    return f"{abs(value):.2f}' {side}"


def _alignment(doc: Document, p: dict, key: str = "alignment") -> Alignment:
    """``p[key]`` or the document's only alignment; teaching faults otherwise."""
    aligns = doc.design.alignments
    name = p.get(key)
    if name is None:
        if len(aligns) == 1:
            return next(iter(aligns.values()))
        if not aligns:
            raise CommandFault("the document has no alignments",
                               hint="create one with create_alignment or import_landxml")
        raise CommandFault(
            f"alignment is required: the document has {len(aligns)} alignments "
            f"({', '.join(aligns)})", hint="run list_alignments")
    if name not in aligns:
        raise CommandFault(f"no alignment named {name!r}", hint=f"alignments: {list(aligns)}")
    return aligns[name]


def _display_station(value, what: str = "begin_station") -> float:
    if isinstance(value, bool):
        raise CommandFault(f"{what} must be a number or '12+34.56'")
    if isinstance(value, str):
        try:
            return float(parse_station(value))
        except ValueError:
            raise CommandFault(f"cannot parse {what} {value!r}",
                               hint="use feet (1600) or station notation '16+00.00'")
    return float(value)


def _lenient_raw(st: StationSystem, value) -> float:
    """Display -> raw, allowing stations before BEGIN / beyond END (no
    equations apply there); gaps and overlaps still raise."""
    try:
        return st.parse(value)
    except DesignError:
        if isinstance(value, str):
            disp = float(parse_station(value))
        else:
            disp = float(value)
        regions = st.regions()
        if disp < regions[0].display_start:
            return disp
        if disp > regions[-1].display_end:
            return disp - regions[-1].shift
        raise


def _anchored(doc: Document, alignment: str) -> List[Tuple[str, object]]:
    """``(space_key, entity)`` for every entity anchored to ``alignment``."""
    out = []
    for eid, e in doc.model_entities.items():
        if e.anchor and e.anchor.get("alignment") == alignment:
            out.append(("model", e))
    for sheet in doc.sheets.values():
        for e in sheet.entities.values():
            if e.anchor and e.anchor.get("alignment") == alignment:
                out.append((sheet.id, e))
    return out


def _describe(align: Alignment) -> str:
    nt, nc = len(align.tangents()), len(align.curves())
    return (f"{_plural(len(align.elements), 'element')} ({_plural(nt, 'tangent')}, "
            f"{_plural(nc, 'curve')})")


def _next_name(name: str, taken) -> str:
    n = 2
    while f"{name}-{n}" in taken:
        n += 1
    return f"{name}-{n}"


# ------------------------------------------------------------- alignments


def create_alignment(doc: Document, p: dict):
    name = p["name"]
    if name in doc.design.alignments:
        raise CommandFault(f"alignment {name!r} already exists",
                           hint="modify_alignment or delete_alignment")
    has_pis, has_elements = "pis" in p, "elements" in p
    if has_pis == has_elements:
        raise CommandFault("give exactly one of pis (PI-based) or elements (from CoordGeom)")
    begin = _display_station(p.get("begin_station", 0.0))
    description = str(p.get("description", ""))
    try:
        if has_pis:
            pis = [PI.from_dict(x) for x in p["pis"]]
            align = Alignment(name=name, elements=compile_pis(pis), pis=pis, begin_station=begin,
                              description=description, source="pis")
        else:
            align = alignment_from_elements(name, elements_from_dicts(p["elements"]),
                                            begin_station=begin, description=description)
        align.equations = build_equations(begin, align.length, p.get("equations", []))
    except DesignError as e:
        raise _fault(e)
    doc.design.alignments[name] = align
    st = align.stations()
    return (f"alignment {name} created: {_describe(align)}, {align.length:.2f} ft, "
            f"{st.begin_text()} to {st.end_text()}",
            _diff(created=[f"alignment:{name}"]), [])


def modify_alignment(doc: Document, p: dict):
    name = p["name"]
    align = _alignment(doc, {"alignment": name})
    changes = p["changes"]
    bad = set(changes) - set(ALIGNMENT_CHANGES)
    if bad:
        raise CommandFault(f"cannot change {sorted(bad)} on an alignment",
                           hint=f"allowed changes: {list(ALIGNMENT_CHANGES)}")
    new = Alignment.from_dict(align.to_dict())
    stations_changed = False
    try:
        if "pis" in changes:
            pis = [PI.from_dict(x) for x in changes["pis"]]
            new.elements = compile_pis(pis)
            new.pis = pis
            new.source = "pis"
            stations_changed = True
        if "description" in changes:
            new.description = str(changes["description"])
        if "begin_station" in changes:
            new.begin_station = _display_station(changes["begin_station"])
            stations_changed = True
        if "equations" in changes:
            stations_changed = True
        if stations_changed:
            items = changes.get("equations", [q.to_dict() for q in new.equations])
            new.equations = build_equations(new.begin_station, new.length, items)
    except DesignError as e:
        raise _fault(e)

    final = name
    modified_ids: List[str] = []
    created: List[str] = []
    deleted: List[str] = []
    if "rename" in changes:
        final = changes["rename"]
        if not isinstance(final, str) or not final:
            raise CommandFault("rename must be a non-empty alignment name")
        if final != name and final in doc.design.alignments:
            raise CommandFault(f"alignment {final!r} already exists")
        new.name = final
    if final != name:
        del doc.design.alignments[name]
        for prof in doc.design.profiles_of(name):
            prof.alignment = final
        for _space_key, entity in _anchored(doc, name):
            entity.anchor = dict(entity.anchor, alignment=final)
            modified_ids.append(entity.id)
        deleted.append(f"alignment:{name}")
        created.append(f"alignment:{final}")
    doc.design.alignments[final] = new

    warnings = []
    anchored = _anchored(doc, final)
    if stations_changed and anchored:
        warnings.append(
            f"{len(anchored)} entities are anchored to {final} and were not regenerated; "
            f"re-run draw_alignment / annotate_stationing / place_label")
    st = new.stations()
    return (f"alignment {final} updated: {', '.join(sorted(changes))} "
            f"({st.begin_text()} to {st.end_text()})",
            _diff(created=created, modified=[f"alignment:{final}"] + modified_ids,
                  deleted=deleted), warnings)


def delete_alignment(doc: Document, p: dict):
    name = p["name"]
    _alignment(doc, {"alignment": name})
    profiles = doc.design.profiles_of(name)
    if profiles and not p.get("cascade"):
        raise CommandFault(
            f"{name} has {_plural(len(profiles), 'profile')} "
            f"({', '.join(pr.name for pr in profiles)})",
            hint="pass cascade=true or delete_profile first")
    del doc.design.alignments[name]
    deleted = [f"alignment:{name}"]
    for prof in profiles:
        del doc.design.profiles[prof.name]
        deleted.append(f"profile:{prof.name}")
    anchored = _anchored(doc, name)
    warnings = ([f"{len(anchored)} entities remain anchored to deleted alignment {name}"]
                if anchored else [])
    return f"alignment {name} deleted", _diff(deleted=deleted), warnings


# --------------------------------------------------------------- profiles


def create_profile(doc: Document, p: dict):
    name, aname = p["name"], p["alignment"]
    align = _alignment(doc, {"alignment": aname})
    if name in doc.design.profiles:
        raise CommandFault(f"profile {name!r} already exists", hint="delete_profile first")
    st = align.stations()
    pvis: List[PVI] = []
    warnings: List[str] = []
    for i, item in enumerate(p["pvis"], start=1):
        try:
            raw = _lenient_raw(st, item[0])
        except DesignError as e:
            raise CommandFault(f"PVI-{i}: {e}", hint=e.hint)
        length = float(item[2]) if len(item) > 2 else 0.0
        pvis.append(PVI(station=raw, elevation=float(item[1]), length=length))
        if raw > st.end_station_raw + 1e-6:
            warnings.append(f"PVI-{i} ({st.format(raw)}) is beyond the end of {aname} "
                            f"({st.end_text()})")
        elif raw < st.begin_station - 1e-6:
            warnings.append(f"PVI-{i} ({st.format(raw)}) is before the beginning of {aname} "
                            f"({st.begin_text()})")
    profile = Profile(name=name, alignment=aname, pvis=pvis,
                      description=str(p.get("description", "")))
    try:
        profile.validate()
    except DesignError as e:
        raise _fault(e)
    doc.design.profiles[name] = profile
    n_vc = sum(1 for q in pvis[1:-1] if q.length > 0)
    return (f"profile {name} created on {aname}: {len(pvis)} PVIs, "
            f"{_plural(n_vc, 'vertical curve')}, {st.format(pvis[0].station)} to "
            f"{st.format(pvis[-1].station)}",
            _diff(created=[f"profile:{name}"]), warnings)


def delete_profile(doc: Document, p: dict):
    name = p["name"]
    if name not in doc.design.profiles:
        raise CommandFault(f"no profile named {name!r}",
                           hint=f"profiles: {list(doc.design.profiles)}")
    del doc.design.profiles[name]
    return f"profile {name} deleted", _diff(deleted=[f"profile:{name}"]), []


# ---------------------------------------------------------------- drawing


def draw_alignment(doc: Document, p: dict):
    align = _alignment(doc, p)
    common = _entity_common(doc, p)
    existing = [eid for eid, e in doc.model_entities.items()
                if e.anchor and e.anchor.get("alignment") == align.name
                and e.anchor.get("kind") == "element"]
    warnings: List[str] = []
    deleted: List[str] = []
    if existing:
        if p.get("replace"):
            for eid in existing:
                del doc.model_entities[eid]
            deleted = list(existing)
        else:
            warnings.append(f"{align.name} already drawn ({', '.join(existing)}); "
                            f"pass replace=true to redraw")
    created: List[str] = []
    n_lines = n_arcs = 0
    for i, el in enumerate(align.elements):
        anchor = {"alignment": align.name, "ref": align.element_ref(i), "kind": "element",
                  "station": float(align.begin_station) + float(el.start_dist), "offset": 0.0}
        if isinstance(el, TangentElement):
            _, e = _add(doc, "model", "line", Line, {
                **common, "start": list(el.start), "end": list(el.end), "anchor": anchor})
            n_lines += 1
        else:
            s, en = el.ccw_angles()
            _, e = _add(doc, "model", "arc", Arc, {
                **common, "center": list(el.center), "radius": float(el.radius),
                "start_angle_deg": s, "end_angle_deg": en, "anchor": anchor})
            n_arcs += 1
        created.append(e.id)
    return (f"{align.name} drawn on {common['layer']}: {_plural(n_lines, 'line')}, "
            f"{_plural(n_arcs, 'arc')}", _diff(created=created, deleted=deleted), warnings)


def draw_offset(doc: Document, p: dict):
    """Draw constant offsets of an alignment: pavement edges, shoulders, ROW."""
    align = _alignment(doc, p)
    common = _entity_common(doc, p)
    warnings: List[str] = []
    offsets: List[float] = []
    for raw in p["offsets"]:
        try:
            value = parse_offset(raw)
        except DesignError as e:
            raise _fault(e)
        if any(abs(value - seen) < 1e-9 for seen in offsets):
            warnings.append(f"offset {_offset_text(value)} given twice; drawn once")
            continue
        offsets.append(value)

    chains = []
    for value in offsets:
        try:
            chains.append((value, offset_pieces(align, value)))
        except DesignError as e:
            raise _fault(e)

    deleted: List[str] = []
    for value, _pieces in chains:
        existing = [eid for eid, e in doc.model_entities.items()
                    if e.anchor and e.anchor.get("alignment") == align.name
                    and e.anchor.get("kind") == "offset"
                    and abs(float(e.anchor.get("offset") or 0.0) - value) < 1e-9]
        if not existing:
            continue
        if p.get("replace"):
            for eid in existing:
                del doc.model_entities[eid]
            deleted += existing
        else:
            warnings.append(f"offset {_offset_text(value)} of {align.name} already drawn "
                            f"({', '.join(existing)}); pass replace=true to redraw")

    created: List[str] = []
    n_lines = n_arcs = 0
    for value, pieces in chains:
        for piece in pieces:
            anchor = {"alignment": align.name, "ref": piece.ref, "kind": "offset",
                      "station": piece.station, "offset": piece.offset}
            if piece.kind == "tangent":
                _, e = _add(doc, "model", "line", Line, {
                    **common, "start": list(piece.start), "end": list(piece.end),
                    "anchor": anchor})
                n_lines += 1
            else:
                _, e = _add(doc, "model", "arc", Arc, {
                    **common, "center": list(piece.center), "radius": float(piece.radius),
                    "start_angle_deg": piece.start_angle_deg,
                    "end_angle_deg": piece.end_angle_deg, "anchor": anchor})
                n_arcs += 1
            created.append(e.id)
    text = ", ".join(_offset_text(v) for v, _ in chains)
    return (f"{align.name} offset {text} drawn on {common['layer']}: "
            f"{_plural(n_lines, 'line')}, {_plural(n_arcs, 'arc')}",
            _diff(created=created, deleted=deleted), warnings)


# ----------------------------------------------------------------- labels


def _pick_viewport(doc: Document, sheet, explicit: Optional[str], anchor_point, ap, align):
    if explicit:
        vp = sheet.viewport_by_id(explicit)
        if vp is None:
            raise CommandFault(f"viewport {explicit} is not on {sheet.name}",
                               hint=f"viewports: {[v.id for v in sheet.viewports]}")
        return vp
    for vp in sheet.viewports:
        q = vp.transform().to_paper(anchor_point)
        if geo.bbox_contains(vp.paper_bbox(), (q[0], q[1], q[0], q[1])):
            return vp
    if not sheet.viewports:
        hint = "the sheet has no viewport; create_viewport first"
    else:
        shows = []
        for vp in sheet.viewports:
            mb = vp.transform().visible_model_bbox(vp.width_in, vp.height_in)
            shows.append(f"{vp.id} shows x {mb[0]:.0f}..{mb[2]:.0f}, y {mb[1]:.0f}..{mb[3]:.0f}")
        hint = (f"viewports: {'; '.join(shows)}; move/resize it (modify_viewport) or pass "
                f"viewport=")
    raise CommandFault(
        f"anchor {ap.ref} of {align.name} ({anchor_point[0]:.2f}, {anchor_point[1]:.2f}) is not "
        f"visible in any viewport of {sheet.name}", hint=hint)


def plan_label(doc: Document, p: dict) -> dict:
    """Everything ``place_label`` would do, without adding the entity (shared
    with the ``resolve_anchor`` dry-run query)."""
    space_key, container = _space(doc, p["space"])
    align = _alignment(doc, p)
    try:
        ref = parse_anchor(p["anchor"])
        ap = resolve_anchor(align, ref)
        kind = p.get("kind") or infer_kind(ref)
        scaled = anno.model_sizes(doc)  # None when the annotation scale is off
        if space_key == "model":
            model_offset = p.get("label_offset",
                                 scaled["label_offset"] if scaled else None)
        else:
            model_offset = None
        spec = compile_label(
            align, ap, kind, side=p.get("side"), label_offset=model_offset,
            rotation=p.get("rotation", "along"), content=p.get("content"),
            halign=p.get("halign"), valign=p.get("valign"))
    except DesignError as e:
        raise _fault(e)
    vp = None
    annotative = None
    if space_key == "model":
        position, rotation_deg = spec.position, spec.rotation_deg
        height = p.get("height", scaled["text_height"] if scaled else MODEL_TEXT_HEIGHT)
        recorded_offset = spec.label_offset
        annotative = anno.text_record(doc, height, spec.label_offset)
    else:
        sheet = doc.sheets[space_key]
        vp = _pick_viewport(doc, sheet, p.get("viewport"), spec.anchor_point, ap, align)
        recorded_offset = float(p.get("label_offset", SHEET_LABEL_OFFSET))
        position, rotation_deg = sheet_pose(spec, vp.transform(), vp.rotation_deg,
                                            recorded_offset)
        height = p.get("height", SHEET_TEXT_HEIGHT)
    record = spec.anchor_record(vp.id if vp is not None else None)
    record["label_offset"] = float(recorded_offset)
    return {"space_key": space_key, "container": container, "alignment": align, "spec": spec,
            "anchor_point": ap, "kind": kind, "viewport": vp, "position": position,
            "rotation_deg": rotation_deg, "height": float(height), "anchor": record,
            "annotative": annotative}


def place_label(doc: Document, p: dict):
    plan = plan_label(doc, p)
    spec = plan["spec"]
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    space_key, e = _add(doc, p["space"], "text", Text, {
        **_entity_common(doc, p), "position": plan["position"], "content": spec.content,
        "height": plan["height"], "style": style, "rotation_deg": plan["rotation_deg"],
        "halign": spec.halign, "valign": spec.valign, "anchor": plan["anchor"],
        "annotative": plan["annotative"]})
    warnings = _annotation_warnings(doc, space_key, e)
    key = (spec.alignment, spec.ref, spec.kind)
    for other in plan["container"].values():
        if other is e or not isinstance(other, Text) or not other.anchor:
            continue
        a = other.anchor
        if (a.get("alignment"), a.get("ref"), a.get("kind")) == key:
            warnings.append(f"label duplicates {other.id} (same alignment/anchor/kind)")
    preview = spec.content if len(spec.content) <= 40 else spec.content[:37] + "..."
    where = ("model space" if space_key == "model"
             else f"sheet {doc.sheets[space_key].name} via {plan['viewport'].id}")
    return (f"label {e.id} {preview!r} ({spec.kind} @ {spec.ref} of {spec.alignment}) placed in "
            f"{where}", _diff(created=[e.id]), warnings)


def place_curve_table(doc: Document, p: dict):
    space_key, _container = _space(doc, p["space"])
    if space_key == "model":
        raise CommandFault("place_curve_table places tables on sheets",
                           hint="pass a sheet id/name as space")
    align = _alignment(doc, p)
    try:
        headers, rows, widths = curve_table_rows(align, p.get("columns"), p.get("curves"))
    except DesignError as e:
        raise _fault(e)
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    space_key, e = _add(doc, p["space"], "table", Table, {
        **_entity_common(doc, p), "position": list(p["position"]),
        "columns": [{"header": h, "width": w} for h, w in zip(headers, widths)],
        "rows": rows, "text_height": p.get("text_height", 0.12),
        "title": p.get("title", "CURVE DATA"), "style": style,
        "anchor": {"alignment": align.name, "ref": "CURVES", "kind": "curve_table",
                   "content_auto": True}})
    warnings = _annotation_warnings(doc, space_key, e)
    return (f"curve table {e.id} ({_plural(len(rows), 'curve')}, {len(headers)} columns) placed "
            f"on {_space_label(doc, space_key)}", _diff(created=[e.id]), warnings)


# ---------------------------------------------------------------- LandXML


def import_landxml(doc: Document, p: dict):
    has_path, has_xml = "path" in p, "xml" in p
    if has_path == has_xml:
        raise CommandFault("give exactly one of path (a file read at execute time) or xml "
                           "(inline text)")
    if has_path:
        try:
            text = Path(p["path"]).read_text()
        except FileNotFoundError:
            raise CommandFault(f"file not found: {p['path']}")
        except OSError as ex:
            raise CommandFault(f"cannot read {p['path']}: {ex}")
    else:
        text = p["xml"]
    try:
        data = parse_landxml(text)
    except LandXMLError as e:
        raise CommandFault(str(e), hint=e.hint)
    names = [a.name for a in data.alignments]
    if not names:
        raise CommandFault("the LandXML file contains no alignments",
                           hint=f"skipped sections: {data.skipped}" if data.skipped else None)
    alignments, profiles = data.alignments, data.profiles
    wanted = p.get("alignments")
    if wanted:
        unknown = [w for w in wanted if w not in names]
        if unknown:
            raise CommandFault(f"alignments {unknown} are not in the file",
                               hint=f"file alignments: {names}")
        alignments = [a for a in alignments if a.name in wanted]
        profiles = [pr for pr in profiles if pr.alignment in wanted]
    on_conflict = p.get("on_conflict", "error")
    created: List[str] = []
    modified: List[str] = []
    renamed: Dict[str, str] = {}
    for align in alignments:
        name = align.name
        if name in doc.design.alignments:
            if on_conflict == "error":
                raise CommandFault(f"alignment {name} already exists",
                                   hint="on_conflict=replace|rename")
            if on_conflict == "replace":
                doc.design.alignments[name] = align
                modified.append(f"alignment:{name}")
                continue
            new = _next_name(name, doc.design.alignments)
            renamed[name] = new
            align.name = new
            name = new
        doc.design.alignments[name] = align
        created.append(f"alignment:{name}")
    for prof in profiles:
        prof.alignment = renamed.get(prof.alignment, prof.alignment)
        pname = prof.name
        if pname in doc.design.profiles:
            if on_conflict == "error":
                raise CommandFault(f"profile {pname} already exists",
                                   hint="on_conflict=replace|rename")
            if on_conflict == "replace":
                doc.design.profiles[pname] = prof
                modified.append(f"profile:{pname}")
                continue
            pname = _next_name(pname, doc.design.profiles)
            prof.name = pname
        doc.design.profiles[pname] = prof
        created.append(f"profile:{pname}")
    imported = [a.name for a in alignments]
    msg = (f"imported {_plural(len(alignments), 'alignment')} ({', '.join(imported)}) and "
           f"{_plural(len(profiles), 'profile')} from LandXML 1.2 ({data.linear_unit})")
    if data.skipped:
        msg += f"; skipped: {', '.join(data.skipped)}"
    return msg, _diff(created=created, modified=modified), list(data.warnings)


# ------------------------------------------------------------- stationing


def annotate_stationing_alignment(doc: Document, p: dict):
    """Alignment mode of ``annotate_stationing``: true stations, equations,
    and anchored ticks/labels from the design model."""
    align = _alignment(doc, p)
    st = align.stations()
    if "begin_station" in p:
        raise CommandFault(
            f"alignment mode uses {align.name}'s own stationing (begins {st.begin_text()}); "
            f"omit begin_station", hint="modify_alignment changes begin_station")
    space_key, container = _space(doc, p["space"])
    if space_key != "model":
        raise CommandFault("alignment-mode stationing draws in model space; use place_label "
                           "for sheet labels")
    tick_layer = _layer(doc, p)
    label_layer = p.get("label_layer", tick_layer)
    if label_layer not in doc.layers:
        raise CommandFault(f"label layer {label_layer!r} does not exist",
                           hint=f"existing layers: {sorted(doc.layers)}")
    style = doc.settings["current_text_style"]
    interval = p.get("interval", 100.0)
    sizes = anno.size_defaults(doc)  # annotation scale x paper defaults, or fixed feet
    tick_half = p.get("tick_half_len", sizes["tick_half_len"])
    text_h = p.get("text_height", sizes["text_height"])
    label_off = p.get("label_offset", sizes["label_offset"])
    station_range = None
    if "station_range" in p:
        try:
            station_range = (st.parse(p["station_range"][0]), st.parse(p["station_range"][1]))
        except DesignError as e:
            raise _fault(e)
    try:
        plan = stationing_plan(align, interval=interval, tick_half=tick_half,
                               label_offset=label_off,
                               include_pc_pt=p.get("include_pc_pt", True),
                               include_equations=p.get("include_equations", True),
                               station_range=station_range)
    except DesignError as e:
        raise _fault(e)

    created: List[str] = []

    def add(kind, cls, fields):
        eid = doc.new_id(kind)
        container[eid] = cls(id=eid, **fields)
        created.append(eid)

    for item in plan.items:
        if isinstance(item, TickSpec):
            add("line", Line, {"layer": tick_layer, "start": item.start, "end": item.end,
                               "anchor": item.anchor_record(align.name),
                               "annotative": anno.tick_record(doc, tick_half)})
        else:
            add("text", Text, {"layer": label_layer, "style": style, "position": item.position,
                               "content": item.content, "height": text_h,
                               "rotation_deg": item.rotation_deg, "halign": item.halign,
                               "valign": item.valign, "anchor": item.anchor_record(None),
                               "annotative": anno.text_record(doc, text_h, item.label_offset)})
    return (f"stationing annotated in model space from {align.name}: {plan.n_ticks} ticks @ "
            f"{interval:g} ft, {plan.n_junctions} PC/PT labels, {plan.n_equations} equation "
            f"labels, stations {plan.begin_text} to {plan.end_text}",
            _diff(created=created), [])


__all__ = [
    "create_alignment", "modify_alignment", "delete_alignment", "create_profile",
    "delete_profile", "draw_alignment", "place_label", "place_curve_table", "import_landxml",
    "annotate_stationing_alignment", "plan_label",
]
