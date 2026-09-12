"""Command implementations. Each handler mutates the document and returns
(message, diff, warnings). Semantic problems raise CommandFault with a hint;
the bus restores the pre-command snapshot, so every command is atomic.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

from roaddraft.core import colors as colorlib
from roaddraft.core import geometry as geo
from roaddraft.core.units import format_station
from roaddraft.document import annotation as anno
from roaddraft.document.document import LINETYPES, BlockDef, Document, Layer, TextStyle
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Dimension, Line, Polyline, Table, Text, entity_from_dict,
)
from roaddraft.document.entities import as_point, as_positive
from roaddraft.document.references import (
    Reference, as_levels, as_nest_depth, as_polygon, as_polygons,
    as_symbology, reference_levels, resolve_reference, unit_factor_for,
)
from roaddraft.document.sheets import (
    SHEET_SIZES, TITLE_BLOCK_TEMPLATES, Sheet, Viewport,
)


class CommandFault(Exception):
    def __init__(self, message: str, hint: str = None):
        super().__init__(message)
        self.hint = hint


def _diff(created=(), modified=(), deleted=()):
    return {"created": list(created), "modified": list(modified),
            "deleted": list(deleted)}


# ------------------------------------------------------------- validation


def _space(doc: Document, ref: str):
    resolved = doc.resolve_space(ref)
    if resolved is None:
        raise CommandFault(f"space {ref!r} not found",
                           hint=f"valid spaces: {doc.space_refs()}")
    return resolved


def _layer(doc: Document, p: dict) -> str:
    name = p.get("layer") or doc.settings["current_layer"]
    if name not in doc.layers:
        raise CommandFault(
            f"layer {name!r} does not exist",
            hint=f"existing layers: {sorted(doc.layers)}; create it with create_layer")
    return name


def _style(doc: Document, name: str) -> str:
    if name not in doc.text_styles:
        raise CommandFault(
            f"text style {name!r} does not exist",
            hint=f"existing styles: {sorted(doc.text_styles)}; "
                 f"create it with create_text_style")
    return name


def _color_ok(color):
    if color is not None and not colorlib.is_valid(color):
        raise CommandFault(
            f"invalid color {color!r}",
            hint="use a named color (black, red, yellow, green, cyan, blue, magenta, "
                 "gray, white) or '#RRGGBB'")
    return color


def _linetype_ok(lt):
    if lt is not None and lt not in LINETYPES:
        raise CommandFault(f"invalid linetype {lt!r}",
                           hint=f"valid linetypes: {list(LINETYPES)}")
    return lt


def _entity_common(doc: Document, p: dict) -> dict:
    return {
        "layer": _layer(doc, p),
        "color": _color_ok(p.get("color")),
        "linetype": _linetype_ok(p.get("linetype")),
    }


def _space_label(doc: Document, space_key: str) -> str:
    if space_key == "model":
        return "model space"
    return f"sheet {doc.sheets[space_key].name}"


def _annotation_warnings(doc: Document, space_key: str, entity) -> List[str]:
    """Legibility feedback for sheet annotation: off-sheet and text-on-text
    overlap warnings (PRD section 5.2: every action returns a diff + warnings)."""
    warnings = []
    if space_key == "model":
        return warnings
    sheet = doc.sheets[space_key]
    bb = entity.bbox(doc)
    if bb is None:
        return warnings
    if not geo.bbox_contains(sheet.paper_bbox(), bb, tol=1e-6):
        warnings.append(f"{entity.id} extends beyond the {sheet.width_in}x"
                        f"{sheet.height_in} in sheet extents")
    for other in sheet.entities.values():
        if other.id == entity.id or not isinstance(other, (Text, Table, Dimension)):
            continue
        ob = other.bbox(doc)
        if ob is not None and geo.bbox_intersects(bb, ob):
            warnings.append(f"{entity.id} overlaps {other.id}")
    return warnings


def _add(doc: Document, space_ref: str, kind: str, entity_cls, fields: dict):
    space_key, container = _space(doc, space_ref)
    eid = doc.new_id(kind)
    entity = entity_cls(id=eid, **fields)
    container[eid] = entity
    return space_key, entity


# ------------------------------------------------------- document resources


def set_meta(doc: Document, p: dict):
    doc.meta.update(p["updates"])
    keys = ", ".join(sorted(p["updates"]))
    return f"meta updated: {keys}", _diff(modified=["meta"]), []


def create_layer(doc: Document, p: dict):
    name = p["name"]
    if name in doc.layers:
        raise CommandFault(f"layer {name!r} already exists",
                           hint="use modify_layer to change it")
    doc.layers[name] = Layer(
        name=name,
        color=_color_ok(p.get("color")) or "black",
        linetype=_linetype_ok(p.get("linetype")) or "continuous",
        lineweight_mm=p.get("lineweight_mm", 0.25),
        description=p.get("description", ""),
    )
    return f"layer {name!r} created", _diff(created=[f"layer:{name}"]), []


def modify_layer(doc: Document, p: dict):
    name = p["name"]
    if name not in doc.layers:
        raise CommandFault(f"layer {name!r} does not exist",
                           hint=f"existing layers: {sorted(doc.layers)}")
    allowed = {"color", "linetype", "lineweight_mm", "description", "visible"}
    changes = p["changes"]
    bad = set(changes) - allowed
    if bad:
        raise CommandFault(f"cannot change {sorted(bad)} on a layer",
                           hint=f"allowed fields: {sorted(allowed)}")
    layer = doc.layers[name]
    if "color" in changes:
        layer.color = _color_ok(changes["color"])
    if "linetype" in changes:
        layer.linetype = _linetype_ok(changes["linetype"])
    if "lineweight_mm" in changes:
        lw = changes["lineweight_mm"]
        if not (isinstance(lw, (int, float)) and lw > 0):
            raise CommandFault("lineweight_mm must be a positive number")
        layer.lineweight_mm = float(lw)
    if "description" in changes:
        layer.description = str(changes["description"])
    if "visible" in changes:
        layer.visible = bool(changes["visible"])
    return (f"layer {name!r} updated: {', '.join(sorted(changes))}",
            _diff(modified=[f"layer:{name}"]), [])


def set_current_layer(doc: Document, p: dict):
    name = p["name"]
    if name not in doc.layers:
        raise CommandFault(f"layer {name!r} does not exist",
                           hint=f"existing layers: {sorted(doc.layers)}")
    doc.settings["current_layer"] = name
    return f"current layer set to {name!r}", _diff(modified=["settings"]), []


def create_text_style(doc: Document, p: dict):
    name = p["name"]
    if name in doc.text_styles:
        raise CommandFault(f"text style {name!r} already exists")
    doc.text_styles[name] = TextStyle(
        name=name, font=p.get("font", "DejaVu Sans"),
        width_factor=p.get("width_factor", 1.0),
        default_height=p.get("default_height", 0.12),
    )
    return f"text style {name!r} created", _diff(created=[f"style:{name}"]), []


BLOCK_ENTITY_TYPES = {"line", "polyline", "arc", "circle", "text"}


def define_block(doc: Document, p: dict):
    name = p["name"]
    if name in doc.blocks:
        raise CommandFault(f"block {name!r} already exists",
                           hint="block redefinition is not supported; "
                                "use a new name")
    entities = []
    for i, ed in enumerate(p["entities"]):
        etype = ed.get("type")
        if etype not in BLOCK_ENTITY_TYPES:
            raise CommandFault(
                f"entities[{i}]: type {etype!r} not allowed inside a block",
                hint=f"allowed types: {sorted(BLOCK_ENTITY_TYPES)}")
        try:
            entity = entity_from_dict(ed)
        except (KeyError, ValueError, TypeError) as ex:
            raise CommandFault(f"entities[{i}] is not a valid {etype}: {ex}")
        entity.id = f"B{i + 1}"
        entities.append(entity)
    doc.blocks[name] = BlockDef(name=name, base_point=list(p.get("base_point", [0, 0])),
                                entities=entities,
                                description=p.get("description", ""))
    return (f"block {name!r} defined with {len(entities)} entities",
            _diff(created=[f"block:{name}"]), [])


# ---------------------------------------------------------------- drawing


def draw_line(doc: Document, p: dict):
    space_key, e = _add(doc, p["space"], "line", Line, {
        **_entity_common(doc, p), "start": list(p["start"]), "end": list(p["end"])})
    return (f"line {e.id} on layer {e.layer!r} in {_space_label(doc, space_key)}",
            _diff(created=[e.id]), [])


def draw_polyline(doc: Document, p: dict):
    space_key, e = _add(doc, p["space"], "polyline", Polyline, {
        **_entity_common(doc, p),
        "vertices": [list(v) for v in p["vertices"]],
        "closed": p.get("closed", False)})
    return (f"polyline {e.id} ({len(e.vertices)} vertices"
            f"{', closed' if e.closed else ''}) on layer {e.layer!r} in "
            f"{_space_label(doc, space_key)}", _diff(created=[e.id]), [])


def draw_arc(doc: Document, p: dict):
    space_key, e = _add(doc, p["space"], "arc", Arc, {
        **_entity_common(doc, p), "center": list(p["center"]),
        "radius": p["radius"], "start_angle_deg": p["start_angle_deg"],
        "end_angle_deg": p["end_angle_deg"]})
    return (f"arc {e.id} (R={e.radius:.2f}) on layer {e.layer!r} in "
            f"{_space_label(doc, space_key)}", _diff(created=[e.id]), [])


def draw_circle(doc: Document, p: dict):
    space_key, e = _add(doc, p["space"], "circle", Circle, {
        **_entity_common(doc, p), "center": list(p["center"]), "radius": p["radius"]})
    return (f"circle {e.id} (R={e.radius:.2f}) on layer {e.layer!r} in "
            f"{_space_label(doc, space_key)}", _diff(created=[e.id]), [])


def place_text(doc: Document, p: dict):
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    space_key, _ = _space(doc, p["space"])
    # model-space text drafted with an annotation scale on is annotative
    annotative = anno.text_record(doc, p["height"]) if space_key == "model" else None
    space_key, e = _add(doc, p["space"], "text", Text, {
        **_entity_common(doc, p), "position": list(p["position"]),
        "content": p["content"], "height": p["height"], "style": style,
        "rotation_deg": p.get("rotation_deg", 0.0),
        "halign": p.get("halign", "left"), "valign": p.get("valign", "bottom"),
        "annotative": annotative})
    warnings = _annotation_warnings(doc, space_key, e)
    preview = e.content if len(e.content) <= 40 else e.content[:37] + "..."
    return (f"text {e.id} ({preview!r}) placed in {_space_label(doc, space_key)}",
            _diff(created=[e.id]), warnings)


def insert_block(doc: Document, p: dict):
    if p["block_name"] not in doc.blocks:
        raise CommandFault(f"block {p['block_name']!r} does not exist",
                           hint=f"available blocks: {sorted(doc.blocks)}; "
                                f"define one with define_block")
    space_key, e = _add(doc, p["space"], "blockref", BlockRef, {
        **_entity_common(doc, p), "block_name": p["block_name"],
        "position": list(p["position"]), "scale": p.get("scale", 1.0),
        "rotation_deg": p.get("rotation_deg", 0.0)})
    return (f"block {e.block_name!r} inserted as {e.id} in "
            f"{_space_label(doc, space_key)}", _diff(created=[e.id]), [])


def place_table(doc: Document, p: dict):
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    ncols = len(p["columns"])
    for i, row in enumerate(p["rows"]):
        if len(row) != ncols:
            raise CommandFault(
                f"rows[{i}] has {len(row)} cells but there are {ncols} columns")
    space_key, e = _add(doc, p["space"], "table", Table, {
        **_entity_common(doc, p), "position": list(p["position"]),
        "columns": [{"header": str(c["header"]), "width": float(c["width"])}
                    for c in p["columns"]],
        "rows": [[str(v) for v in row] for row in p["rows"]],
        "text_height": p.get("text_height", 0.12),
        "title": p.get("title", ""), "style": style})
    warnings = _annotation_warnings(doc, space_key, e)
    return (f"table {e.id} ({len(e.rows)} rows x {ncols} cols) placed in "
            f"{_space_label(doc, space_key)}", _diff(created=[e.id]), warnings)


# ---------------------------------------------------------------- editing


def _find(doc: Document, eid: str):
    found = doc.find_entity(eid)
    if found is None:
        raise CommandFault(f"entity {eid!r} not found",
                           hint="ids are listed by get_model_state / get_sheet_state")
    return found


def move_entities(doc: Document, p: dict):
    delta = p["delta"]
    moved = []
    for eid in p["ids"]:
        space_key, entity = _find(doc, eid)
        _, container = doc.resolve_space(space_key)
        container[eid] = entity.translated(delta)
        moved.append(eid)
    return (f"moved {len(moved)} entities by [{delta[0]}, {delta[1]}]",
            _diff(modified=moved), [])


def place_callout(doc: Document, p: dict):
    """Text with a leader pointing at something -- the way a drafter annotates
    geometry that has no design model of its own, including geometry seen
    through a reference."""
    from roaddraft.design.labels import MODEL_TEXT_HEIGHT, SHEET_TEXT_HEIGHT
    from roaddraft.document.locate import nearest_entity, point_at, resolve_entity

    space_key, _container = _space(doc, p["space"])
    warnings: List[str] = []
    if ("target" in p) == ("target_entity" in p):
        raise CommandFault(
            "give exactly one of target (a point) or target_entity (what to point at)",
            hint="target_entity is the reliable one: name the entity and the engine "
                 "computes a point on it, curves included. find_entities and hit_test "
                 "return the ids.")
    if "target_entity" in p:
        eid = p["target_entity"]
        found = resolve_entity(doc, eid)
        if found is None:
            raise CommandFault(f"no entity {eid!r} to point at",
                               hint="find_entities and hit_test return ids; elements of "
                                    "an attached reference are 'REFNAME:ID'")
        entity, owner, _ref, entity_space = found
        if entity_space != space_key:
            raise CommandFault(
                f"{eid} is in {entity_space}, but the callout goes in {space_key}",
                hint=f"place the callout in {entity_space}, or point at something there")
        try:
            target, _direction = point_at(owner, entity, p.get("at", "mid"))
        except ValueError as ex:
            raise CommandFault(str(ex), hint="at is start|mid|end or a fraction 0-1")
    else:
        target = as_point(p["target"])
    position = as_point(p["position"])
    if space_key == "model":
        sizes = anno.size_defaults(doc)
        height = float(p.get("height", sizes["text_height"] or MODEL_TEXT_HEIGHT))
    else:
        height = float(p.get("height", SHEET_TEXT_HEIGHT))
    if height <= 0:
        raise CommandFault(f"height must be positive, got {height}")
    landing = float(p.get("landing", 2.5 * height))
    if landing < 0:
        raise CommandFault(f"landing must be zero or positive, got {landing}")
    arrow_size = float(p.get("arrow_size", height))
    style = _style(doc, p.get("style", doc.settings["current_text_style"]))
    common = _entity_common(doc, p)

    # The text sits away from the target: the landing runs from the text back
    # toward it, so the callout reads left to right on either side.
    from_left = target[0] <= position[0]
    elbow = [position[0] - landing, position[1]] if from_left else \
            [position[0] + landing, position[1]]
    halign = "left" if from_left else "right"

    if "target" in p:
        # A point typed by hand can miss, and roadway linework runs parallel 8 to
        # 12 ft apart, so a miss usually lands on the *wrong* line rather than on
        # nothing. Report what the tip actually touched either way.
        nearest = nearest_entity(doc, space_key, target)
        reach = max(height, arrow_size)
        if nearest is None:
            warnings.append(f"nothing in {_space_label(doc, space_key)} to point at")
        elif nearest[1] > reach:
            warnings.append(
                f"the leader points at empty space: the nearest entity {nearest[0]} is "
                f"{nearest[1]:.2f} away from [{target[0]:.2f}, {target[1]:.2f}] "
                f"(within {reach:.2f} counts as on it); pass target_entity to aim at "
                f"something exactly")
        else:
            warnings.append(
                f"the leader tip lands on {_describe_target(doc, nearest[0])}; pass "
                f"target_entity instead of a point if that is not what you meant")

    created: List[str] = []
    _, leader = _add(doc, space_key, "line", Line, {
        **common, "start": list(target), "end": elbow})
    created.append(leader.id)
    if landing > 0:
        _, shoulder = _add(doc, space_key, "line", Line, {
            **common, "start": elbow, "end": list(position)})
        created.append(shoulder.id)
    if p.get("arrow", True) and arrow_size > 0:
        _, head = _add(doc, space_key, "polyline", Polyline, {
            **common, "vertices": _arrow_head(target, elbow, arrow_size), "closed": True})
        created.append(head.id)
    _, text = _add(doc, space_key, "text", Text, {
        **common, "position": list(position), "content": p["content"], "height": height,
        "style": style, "rotation_deg": 0.0, "halign": halign, "valign": "middle",
        "annotative": anno.text_record(doc, height) if space_key == "model" else None})
    created.append(text.id)

    warnings += _annotation_warnings(doc, space_key, text)
    preview = p["content"] if len(p["content"]) <= 40 else p["content"][:37] + "..."
    return (f"callout {text.id} ({preview!r}) placed in {_space_label(doc, space_key)}",
            _diff(created=created), warnings)


def _describe_target(doc: Document, eid: str) -> str:
    """What a leader tip actually touched, in the terms the plan uses."""
    from roaddraft.document.locate import resolve_entity
    found = resolve_entity(doc, eid)
    if found is None:
        return eid
    entity = found[0]
    parts = [f"{eid} ({entity.TYPE} on {entity.layer}"]
    anchor = entity.anchor or {}
    if anchor.get("alignment"):
        offset = anchor.get("offset")
        if isinstance(offset, (int, float)) and not isinstance(offset, bool) and offset:
            parts.append(f", {abs(offset):.2f}' {'RT' if offset > 0 else 'LT'} of "
                         f"{anchor['alignment']}")
        else:
            parts.append(f", {anchor.get('kind', 'part')} of {anchor['alignment']}")
    return "".join(parts) + ")"


def _arrow_head(tip, tail, size: float) -> List[List[float]]:
    """A closed triangle at ``tip``, pointing away from ``tail``."""
    return geo.arrow_head(tip, tail, size)


def modify_entity(doc: Document, p: dict):
    eid = p["id"]
    changes = p["changes"]
    space_key, entity = _find(doc, eid)
    for immutable in ("id", "type"):
        if immutable in changes and changes[immutable] != getattr(
                entity, immutable if immutable == "id" else "TYPE"):
            raise CommandFault(f"entity {immutable} cannot be changed")
    known = set(entity.to_dict()) | {"color", "linetype", "anchor", "annotative"}
    unknown = set(changes) - known
    if unknown:
        raise CommandFault(
            f"unknown fields for {entity.TYPE}: {sorted(unknown)}",
            hint=f"editable fields: {sorted(known - {'id', 'type'})}")
    if isinstance(changes.get("anchor"), dict):
        # Provenance is the bus's to write: a caller can neither claim it nor
        # transfer it to another entity, so an anchor set here keeps whatever
        # the entity was created with -- for a hand-anchored entity, nothing.
        anchor = {k: v for k, v in changes["anchor"].items() if k != "placed_by"}
        placed_by = (entity.anchor or {}).get("placed_by")
        if placed_by is not None:
            anchor["placed_by"] = placed_by
        changes = {**changes, "anchor": anchor}  # p["changes"] is the journal's
    merged = {**entity.to_dict(), **changes}
    try:
        new_entity = entity_from_dict(merged)
    except (KeyError, ValueError, TypeError) as ex:
        raise CommandFault(f"invalid changes for {entity.TYPE} {eid}: {ex}",
                           hint=f"current fields: {sorted(entity.to_dict())}")
    if isinstance(new_entity, BlockRef) \
            and new_entity.block_name not in doc.blocks:
        raise CommandFault(f"block {new_entity.block_name!r} does not exist",
                           hint=f"available blocks: {sorted(doc.blocks)}")
    if new_entity.layer not in doc.layers:
        raise CommandFault(f"layer {new_entity.layer!r} does not exist",
                           hint=f"existing layers: {sorted(doc.layers)}")
    _color_ok(new_entity.color)
    _linetype_ok(new_entity.linetype)
    if isinstance(new_entity, (Text, Table, Dimension)):
        _style(doc, new_entity.style)
    _, container = doc.resolve_space(space_key)
    container[eid] = new_entity
    warnings = _annotation_warnings(doc, space_key, new_entity)
    return (f"{entity.TYPE} {eid} updated: {', '.join(sorted(changes))}",
            _diff(modified=[eid]), warnings)


def delete_entities(doc: Document, p: dict):
    deleted = []
    for eid in p["ids"]:
        space_key, _ = _find(doc, eid)
        _, container = doc.resolve_space(space_key)
        del container[eid]
        deleted.append(eid)
    return f"deleted {len(deleted)} entities", _diff(deleted=deleted), []


# ----------------------------------------------------------------- sheets


def create_sheet(doc: Document, p: dict):
    name = p["name"]
    if doc.sheet_by_ref(name) is not None:
        raise CommandFault(f"a sheet named {name!r} already exists",
                           hint=f"existing sheets: "
                                f"{[s.name for s in doc.sheets.values()]}")
    if "size" in p:
        size = p["size"]
        width, height = SHEET_SIZES[size]
    elif "width_in" in p and "height_in" in p:
        size = "CUSTOM"
        width, height = p["width_in"], p["height_in"]
    else:
        size = "ANSI_D"
        width, height = SHEET_SIZES[size]
    template = p.get("title_block_template", "standard")
    if template not in TITLE_BLOCK_TEMPLATES:
        raise CommandFault(
            f"unknown title block template {template!r}",
            hint=f"templates: {', '.join(sorted(TITLE_BLOCK_TEMPLATES))}")
    sid = doc.new_id("sheet")
    sheet = Sheet(id=sid, name=name, size=size, width_in=width, height_in=height,
                  title_block_template=template,
                  title_block_fields={k: str(v) for k, v in
                                      p.get("title_block_fields", {}).items()})
    doc.sheets[sid] = sheet
    ua = sheet.usable_area()
    return (f"sheet {name!r} ({sid}, {size} {width}x{height} in, {template} title "
            f"block) created; usable drawing area x {ua[0]}-{ua[2]}, "
            f"y {ua[1]}-{ua[3]} in",
            _diff(created=[sid]), [])


def delete_sheet(doc: Document, p: dict):
    sheet = doc.sheet_by_ref(p["sheet"])
    if sheet is None:
        raise CommandFault(f"sheet {p['sheet']!r} not found",
                           hint=f"existing sheets: "
                                f"{[s.name for s in doc.sheets.values()]}")
    del doc.sheets[sheet.id]
    return f"sheet {sheet.name!r} ({sheet.id}) deleted", _diff(deleted=[sheet.id]), []


def _sheet(doc: Document, ref: str) -> Sheet:
    sheet = doc.sheet_by_ref(ref)
    if sheet is None:
        raise CommandFault(f"sheet {ref!r} not found",
                           hint=f"existing sheets: "
                                f"{[s.name for s in doc.sheets.values()]} "
                                f"(create one with create_sheet)")
    return sheet


def create_viewport(doc: Document, p: dict):
    sheet = _sheet(doc, p["sheet"])
    vp = Viewport(id=doc.new_id("viewport"),
                  center_paper=list(p["center_paper"]),
                  width_in=p["width_in"], height_in=p["height_in"],
                  model_center=list(p["model_center"]),
                  feet_per_inch=p["feet_per_inch"],
                  rotation_deg=p.get("rotation_deg", 0.0))
    sheet.viewports.append(vp)
    warnings = []
    scale = anno.current_scale(doc)
    if scale is not None and abs(scale - vp.feet_per_inch) > 1e-9:
        warnings.append(f"{vp.id} plots at {anno.format_scale(vp.feet_per_inch)} but the "
                        f"annotation scale is {anno.scale_name(doc, scale)}; model annotation "
                        f"will appear at {scale / vp.feet_per_inch:.2g}x its paper size "
                        f"(set_annotation_scale {vp.feet_per_inch:g} to match)")
    if not geo.bbox_contains(sheet.usable_area(), vp.paper_bbox(), tol=1e-6):
        warnings.append(f"{vp.id} extends beyond the usable area "
                        f"(border margin / title strip) of sheet {sheet.name}")
    mb = vp.transform().visible_model_bbox(vp.width_in, vp.height_in)
    return (f"viewport {vp.id} on sheet {sheet.name} at 1\"={vp.feet_per_inch}' "
            f"showing model x {mb[0]:.1f}-{mb[2]:.1f}, y {mb[1]:.1f}-{mb[3]:.1f} ft",
            _diff(created=[vp.id]), warnings)


def modify_viewport(doc: Document, p: dict):
    sheet = _sheet(doc, p["sheet"])
    vp = sheet.viewport_by_id(p["viewport_id"])
    if vp is None:
        raise CommandFault(f"viewport {p['viewport_id']!r} not on sheet {sheet.name}",
                           hint=f"viewports: {[v.id for v in sheet.viewports]}")
    allowed = {"center_paper", "width_in", "height_in", "model_center",
               "feet_per_inch", "rotation_deg"}
    changes = p["changes"]
    bad = set(changes) - allowed
    if bad:
        raise CommandFault(f"cannot change {sorted(bad)} on a viewport",
                           hint=f"allowed fields: {sorted(allowed)}")
    merged = {**vp.to_dict(), **changes}
    try:
        new_vp = Viewport.from_dict(merged)
    except (KeyError, ValueError, TypeError) as ex:
        raise CommandFault(f"invalid viewport changes: {ex}")
    if new_vp.feet_per_inch <= 0:
        raise CommandFault("feet_per_inch must be positive")
    sheet.viewports[sheet.viewports.index(vp)] = new_vp
    return (f"viewport {new_vp.id} updated: {', '.join(sorted(changes))}",
            _diff(modified=[new_vp.id]), [])


def delete_viewport(doc: Document, p: dict):
    sheet = _sheet(doc, p["sheet"])
    vp = sheet.viewport_by_id(p["viewport_id"])
    if vp is None:
        raise CommandFault(f"viewport {p['viewport_id']!r} not on sheet {sheet.name}",
                           hint=f"viewports: {[v.id for v in sheet.viewports]}")
    sheet.viewports.remove(vp)
    return f"viewport {vp.id} deleted from sheet {sheet.name}", _diff(deleted=[vp.id]), []


# ------------------------------------------------------------- stationing


class _Piece:
    """One traversable piece of a path: a segment or an arc, oriented."""

    def __init__(self, kind, length, point_at, dir_at):
        self.kind = kind
        self.length = length
        self.point_at = point_at  # distance along piece -> [x, y]
        self.dir_at = dir_at      # distance along piece -> tangent degrees


def _line_piece(a, b):
    length = geo.distance(a, b)
    ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
    def point_at(s, a=a, b=b, length=length):
        t = 0.0 if length == 0 else s / length
        return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
    return _Piece("line", length, point_at, lambda s, ang=ang: ang)


def _arc_piece(center, radius, start_deg, sweep_deg, ccw):
    length = radius * math.radians(abs(sweep_deg))
    sign = 1.0 if ccw else -1.0
    def ang_at(s):
        return start_deg + sign * math.degrees(s / radius)
    def point_at(s):
        return geo.arc_point(center, radius, ang_at(s))
    def dir_at(s):
        return ang_at(s) + sign * 90.0
    return _Piece("arc", length, point_at, dir_at)


def _element_pieces(entity, reverse: bool) -> List[_Piece]:
    if isinstance(entity, Line):
        a, b = (entity.end, entity.start) if reverse else (entity.start, entity.end)
        return [_line_piece(a, b)]
    if isinstance(entity, Polyline):
        verts = list(reversed(entity.vertices)) if reverse else list(entity.vertices)
        return [_line_piece(a, b) for a, b in zip(verts, verts[1:])]
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        if reverse:
            return [_arc_piece(entity.center, entity.radius, e, e - s, ccw=False)]
        return [_arc_piece(entity.center, entity.radius, s, e - s, ccw=True)]
    raise CommandFault(
        f"{entity.id} is a {entity.TYPE}; stationing paths may only contain "
        f"line, polyline, or arc entities")


def _element_endpoints(entity):
    if isinstance(entity, Line):
        return entity.start, entity.end
    if isinstance(entity, Polyline):
        if len(entity.vertices) < 2:
            raise CommandFault(f"{entity.id} has fewer than 2 vertices")
        return entity.vertices[0], entity.vertices[-1]
    if isinstance(entity, Arc):
        s, e = geo.arc_sweep(entity.start_angle_deg, entity.end_angle_deg)
        return (geo.arc_point(entity.center, entity.radius, s),
                geo.arc_point(entity.center, entity.radius, e))
    raise CommandFault(
        f"{entity.id} is a {entity.TYPE}; stationing paths may only contain "
        f"line, polyline, or arc entities")


def _chain_path(doc: Document, ids: List[str], tol: float):
    """Orient the path elements head-to-tail. Returns (pieces, element_kinds,
    element_end_distances)."""
    entities = []
    for eid in ids:
        found = doc.find_entity(eid)
        if found is None:
            raise CommandFault(f"path entity {eid!r} not found")
        entities.append(found[1])

    reversed_flags = []
    for i, entity in enumerate(entities):
        p0, p1 = _element_endpoints(entity)
        if i == 0:
            if len(entities) == 1:
                reversed_flags.append(False)
            else:
                n0, n1 = _element_endpoints(entities[1])
                d_fwd = min(geo.distance(p1, n0), geo.distance(p1, n1))
                d_rev = min(geo.distance(p0, n0), geo.distance(p0, n1))
                if min(d_fwd, d_rev) > tol:
                    raise CommandFault(
                        f"path elements {ids[0]} and {ids[1]} do not touch "
                        f"(gap {min(d_fwd, d_rev):.2f} > tolerance {tol})",
                        hint="pass path_ids in order along the alignment; "
                             "raise connect_tolerance for small gaps")
                reversed_flags.append(d_rev < d_fwd)
        else:
            prev = entities[i - 1]
            pp0, pp1 = _element_endpoints(prev)
            prev_end = pp0 if reversed_flags[i - 1] else pp1
            d_fwd, d_rev = geo.distance(p0, prev_end), geo.distance(p1, prev_end)
            if min(d_fwd, d_rev) > tol:
                raise CommandFault(
                    f"path element {ids[i]} does not connect to {ids[i - 1]} "
                    f"(gap {min(d_fwd, d_rev):.2f} > tolerance {tol})",
                    hint="pass path_ids in order along the alignment; "
                         "raise connect_tolerance for small gaps")
            reversed_flags.append(d_rev < d_fwd)

    pieces: List[_Piece] = []
    element_kinds = []
    element_ends = []
    total = 0.0
    for entity, rev in zip(entities, reversed_flags):
        el_pieces = _element_pieces(entity, rev)
        pieces.extend(el_pieces)
        total += sum(piece.length for piece in el_pieces)
        element_kinds.append("arc" if isinstance(entity, Arc) else "line")
        element_ends.append(total)
    return pieces, element_kinds, element_ends


def _path_eval(pieces: List[_Piece], d: float):
    remaining = d
    for piece in pieces:
        if remaining <= piece.length or piece is pieces[-1]:
            return piece.point_at(min(remaining, piece.length)), \
                piece.dir_at(min(remaining, piece.length))
        remaining -= piece.length
    last = pieces[-1]
    return last.point_at(last.length), last.dir_at(last.length)


def _upright(angle_deg: float) -> float:
    """Fold a label rotation into (-90, 90] so text never reads upside down."""
    return geo.upright(angle_deg)


def _offset_pt(p, angle_deg, dist):
    a = math.radians(angle_deg)
    return [p[0] + dist * math.cos(a), p[1] + dist * math.sin(a)]


def annotate_stationing(doc: Document, p: dict):
    if "alignment" in p and "path_ids" in p:
        raise CommandFault("give either path_ids (entity-chain mode) or alignment (design "
                           "mode), not both")
    if "alignment" in p:
        from roaddraft.commands import design_handlers
        return design_handlers.annotate_stationing_alignment(doc, p)
    if "path_ids" not in p:
        raise CommandFault("path_ids is required in entity-chain mode",
                           hint="or pass alignment=NAME for design-model stationing")
    if "begin_station" not in p:
        raise CommandFault("begin_station is required with path_ids")
    space_key, container = _space(doc, p["space"])
    tick_layer = _layer(doc, p)
    label_layer = p.get("label_layer", tick_layer)
    if label_layer not in doc.layers:
        raise CommandFault(f"label layer {label_layer!r} does not exist",
                           hint=f"existing layers: {sorted(doc.layers)}")
    style = doc.settings["current_text_style"]

    begin = p["begin_station"]
    interval = p.get("interval", 100.0)
    sizes = anno.size_defaults(doc)  # annotation scale x paper defaults, or fixed feet
    tick_half = p.get("tick_half_len", sizes["tick_half_len"])
    text_h = p.get("text_height", sizes["text_height"])
    label_off = p.get("label_offset", sizes["label_offset"])
    tol = p.get("connect_tolerance", 1.0)
    tick_rec = anno.tick_record(doc, tick_half)
    text_rec = anno.text_record(doc, text_h, label_off)

    pieces, kinds, ends = _chain_path(doc, p["path_ids"], tol)
    total = ends[-1] if ends else 0.0
    if total <= 0:
        raise CommandFault("path has zero length")

    created = []

    def add(kind, cls, fields):
        eid = doc.new_id(kind)
        container[eid] = cls(id=eid, **fields)
        created.append(eid)

    n_ticks = 0
    station = math.ceil((begin - 1e-9) / interval) * interval
    while station <= begin + total + 1e-6:
        d = min(max(station - begin, 0.0), total)
        pt, ang = _path_eval(pieces, d)
        add("line", Line, {
            "layer": tick_layer,
            "start": _offset_pt(pt, ang + 90.0, -tick_half),
            "end": _offset_pt(pt, ang + 90.0, tick_half), "annotative": tick_rec})
        add("text", Text, {
            "layer": label_layer, "style": style,
            "position": _offset_pt(pt, ang + 90.0, label_off),
            "content": format_station(station), "height": text_h,
            "rotation_deg": _upright(ang), "halign": "center",
            "valign": "bottom", "annotative": text_rec})
        n_ticks += 1
        station += interval

    n_junctions = 0
    if p.get("include_pc_pt", True):
        labels = {("line", "arc"): "PC", ("arc", "line"): "PT",
                  ("arc", "arc"): "PCC"}
        for i in range(len(kinds) - 1):
            tag = labels.get((kinds[i], kinds[i + 1]))
            if tag is None:
                continue
            d = ends[i]
            pt, ang = _path_eval(pieces, d)
            add("text", Text, {
                "layer": label_layer, "style": style,
                "position": _offset_pt(pt, ang - 90.0, label_off),
                "content": f"{tag} {format_station(begin + d)}",
                "height": text_h, "rotation_deg": _upright(ang),
                "halign": "center", "valign": "top", "annotative": text_rec})
            n_junctions += 1

    message = (f"stationing annotated in {_space_label(doc, space_key)}: "
               f"{n_ticks} ticks @ {interval:g} ft, {n_junctions} PC/PT labels, "
               f"stations {format_station(begin)} to "
               f"{format_station(begin + total)}")
    return message, _diff(created=created), []


# ------------------------------------------------------------- references


def _reference_from_params(rid: str, space_key: str, p: dict) -> Reference:
    try:
        return Reference(
            id=rid, name=p["name"], path=p["path"], space=space_key,
            offset=as_point(p.get("offset", [0.0, 0.0])),
            rotation_deg=float(p.get("rotation_deg", 0.0)),
            scale=as_positive(p.get("scale", 1.0), "scale"),
            visible=bool(p.get("visible", True)),
            true_scale=bool(p.get("true_scale", True)),
            levels_off=as_levels(p.get("levels_off")),
            symbology=as_symbology(p.get("symbology")),
            clip=None if p.get("clip") is None else as_polygon(p["clip"], "clip"),
            masks=as_polygons(p.get("masks")),
            model=str(p.get("model", "model")),
            nest_depth=as_nest_depth(p.get("nest_depth", 0)))
    except ValueError as ex:
        raise CommandFault(str(ex))


def _check_model(ref: Reference, base: Document):
    if base.resolve_space(ref.model) is None:
        raise CommandFault(f"basefile {ref.path} has no model {ref.model!r}",
                           hint=f"models in the basefile: {base.space_refs()} "
                                f"('model' is its design model)")


def _check_levels(doc: Document, ref: Reference, base: Document):
    known = [lv["name"] for lv in reference_levels(doc, ref, base)]
    unknown = [name for name in ref.levels_off if name not in known]
    if unknown:
        raise CommandFault(f"levels_off names {unknown} are not levels of "
                           f"{ref.path}",
                           hint=f"levels of this attachment: {known}")


def _path_hint(doc: Document) -> str:
    from pathlib import Path
    host = getattr(doc, "_path", None)
    if host is not None:
        return (f"relative paths resolve against the host document's folder "
                f"({Path(host).parent}), then the working directory")
    return ("the host document has no path yet (save_document first), so "
            "relative paths resolve against the working directory")


def attach_reference(doc: Document, p: dict):
    name = p["name"]
    for ref in doc.references.values():
        if ref.name == name:
            raise CommandFault(f"a reference named {name!r} is already attached",
                               hint="detach_reference it first, or use a "
                                    "different name")
    space_key, _ = _space(doc, p.get("space", "model"))
    rid = doc.new_id("reference")
    ref = _reference_from_params(rid, space_key, p)
    base, error = resolve_reference(doc, ref)
    if base is None:
        raise CommandFault(f"cannot attach reference: {error}",
                           hint="the path must point to a RoadDraft document "
                                "(.rdraft or .rdoc.json, saved with "
                                "save_document); "
                                + _path_hint(doc))
    _check_model(ref, base)
    _check_levels(doc, ref, base)
    unit_k, base_units, host_units, unit_warning = unit_factor_for(doc, ref, base)
    doc.references[rid] = ref
    count = len(base.resolve_space(ref.model)[1])
    warnings = [] if count else [f"{name} has no model-space entities"]
    if unit_warning:
        warnings.append(unit_warning)
    scale_note = (f"; true scale x{unit_k:.6g} ({base_units} -> {host_units})"
                  if unit_k != 1.0 else "")
    return (f"reference {name!r} ({rid}) attached into "
            f"{_space_label(doc, space_key)}: {count} entities from {ref.path}"
            f"{scale_note}",
            _diff(created=[rid]), warnings)


def _find_reference(doc: Document, name: str) -> Reference:
    for ref in doc.references.values():
        if ref.name == name or ref.id == name:
            return ref
    raise CommandFault(
        f"reference {name!r} not found",
        hint=f"attached references: "
             f"{[r.name for r in doc.references.values()]}")


def detach_reference(doc: Document, p: dict):
    ref = _find_reference(doc, p["name"])
    del doc.references[ref.id]
    doc._ref_cache.pop(ref.id, None)
    return (f"reference {ref.name!r} ({ref.id}) detached",
            _diff(deleted=[ref.id]), [])


REFERENCE_FIELDS = ("path", "offset", "rotation_deg", "scale", "visible",
                    "true_scale", "levels_off", "symbology", "clip", "masks",
                    "model", "nest_depth")


def modify_reference(doc: Document, p: dict):
    ref = _find_reference(doc, p["name"])
    changes = p["changes"]
    bad = set(changes) - set(REFERENCE_FIELDS)
    if bad:
        raise CommandFault(f"cannot change {sorted(bad)} on a reference",
                           hint=f"allowed fields: {list(REFERENCE_FIELDS)}")
    notes = []
    if "offset" in changes:
        off = changes["offset"]
        if not (isinstance(off, list) and len(off) == 2
                and all(isinstance(v, (int, float)) for v in off)):
            raise CommandFault("offset must be [x, y]")
        ref.offset = [float(off[0]), float(off[1])]
    if "rotation_deg" in changes:
        ref.rotation_deg = float(changes["rotation_deg"])
    if "scale" in changes:
        if not (isinstance(changes["scale"], (int, float))
                and changes["scale"] > 0):
            raise CommandFault("scale must be a positive number")
        ref.scale = float(changes["scale"])
    if "visible" in changes:
        ref.visible = bool(changes["visible"])
    if "true_scale" in changes:
        if not isinstance(changes["true_scale"], bool):
            raise CommandFault("true_scale must be true or false")
        ref.true_scale = changes["true_scale"]
    try:
        if "symbology" in changes:
            ref.symbology = as_symbology(changes["symbology"])
            notes.append("symbology " + (", ".join(
                f"{k}={v}" for k, v in sorted(ref.symbology.items()))
                if ref.symbology else "cleared"))
        if "clip" in changes:
            ref.clip = None if changes["clip"] is None \
                else as_polygon(changes["clip"], "clip")
            notes.append("clip boundary cleared" if ref.clip is None
                         else f"clip boundary set ({len(ref.clip)} points)")
        if "masks" in changes:
            ref.masks = as_polygons(changes["masks"])
            notes.append(f"{len(ref.masks)} clip mask(s)")
        if "levels_off" in changes:
            ref.levels_off = as_levels(changes["levels_off"])
        if "nest_depth" in changes:
            ref.nest_depth = as_nest_depth(changes["nest_depth"])
            notes.append(f"nest depth {ref.nest_depth}")
    except ValueError as ex:
        raise CommandFault(str(ex))
    if "model" in changes:
        if not isinstance(changes["model"], str) or not changes["model"]:
            raise CommandFault("model must be 'model' or a sheet name/id")
        ref.model = changes["model"]
    if "path" in changes:
        ref.path = str(changes["path"])
        doc._ref_cache.pop(ref.id, None)
        base, error = resolve_reference(doc, ref)
        if base is None:
            raise CommandFault(f"new path is not loadable: {error}",
                               hint=_path_hint(doc))
    if "model" in changes or "levels_off" in changes:
        base, _error = resolve_reference(doc, ref)
        if base is not None:
            _check_model(ref, base)
            _check_levels(doc, ref, base)
        notes.append(f"levels off: {ref.levels_off}" if ref.levels_off
                     else "all levels on")
    detail = f" ({'; '.join(notes)})" if notes else ""
    return (f"reference {ref.name!r} updated: {', '.join(sorted(changes))}"
            f"{detail}",
            _diff(modified=[ref.id]), [])


def reload_references(doc: Document, p: dict):
    doc._ref_cache.clear()
    count = len(doc.references)
    return (f"reference cache cleared; {count} reference(s) will reload from "
            f"disk on next use", _diff(), [])


def fill_title_block(doc: Document, p: dict):
    sheet = _sheet(doc, p["sheet"])
    fields = {k: str(v) for k, v in p["fields"].items()}
    sheet.title_block_fields.update(fields)
    return (f"title block of {sheet.name} updated: {', '.join(sorted(fields))}",
            _diff(modified=[sheet.id]), [])
