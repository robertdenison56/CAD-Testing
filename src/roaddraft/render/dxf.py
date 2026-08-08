"""DXF export via ezdxf. DXF is a render target, not the source of truth
(PRD section 3): the semantic JSON document is canonical, and this export
produces a file AutoCAD/Civil 3D or MicroStation can open, with real layers,
blocks, paper-space layouts, and viewports.
"""
from __future__ import annotations

import ezdxf
from ezdxf.enums import TextEntityAlignment

from roaddraft.core import colors as colorlib
from roaddraft.document.entities import (
    Arc, BlockRef, Circle, Line, Polyline, Table, Text,
)

LINETYPE_MAP = {
    "continuous": "CONTINUOUS",
    "dashed": "DASHED",
    "center": "CENTER",
    "hidden": "HIDDEN",
    "dot": "DOT",
    "phantom": "PHANTOM",
}

VALID_LINEWEIGHTS = [0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70,
                     80, 90, 100, 106, 120, 140, 158, 200, 211]

ALIGN_MAP = {
    ("left", "bottom"): TextEntityAlignment.BOTTOM_LEFT,
    ("center", "bottom"): TextEntityAlignment.BOTTOM_CENTER,
    ("right", "bottom"): TextEntityAlignment.BOTTOM_RIGHT,
    ("left", "middle"): TextEntityAlignment.MIDDLE_LEFT,
    ("center", "middle"): TextEntityAlignment.MIDDLE_CENTER,
    ("right", "middle"): TextEntityAlignment.MIDDLE_RIGHT,
    ("left", "top"): TextEntityAlignment.TOP_LEFT,
    ("center", "top"): TextEntityAlignment.TOP_CENTER,
    ("right", "top"): TextEntityAlignment.TOP_RIGHT,
}

MTEXT_ATTACHMENT = {
    ("left", "top"): 1, ("center", "top"): 2, ("right", "top"): 3,
    ("left", "middle"): 4, ("center", "middle"): 5, ("right", "middle"): 6,
    ("left", "bottom"): 7, ("center", "bottom"): 8, ("right", "bottom"): 9,
}


def _nearest_lineweight(mm: float) -> int:
    target = int(round(mm * 100))
    return min(VALID_LINEWEIGHTS, key=lambda v: abs(v - target))


def _linetype(dxf, name):
    lt = LINETYPE_MAP.get(name, "CONTINUOUS")
    return lt if dxf.linetypes.has_entry(lt) else "CONTINUOUS"


def _apply_color(entity, color):
    if color is None:
        return
    aci = colorlib.to_aci(color)
    if aci is not None:
        entity.dxf.color = aci
    else:
        entity.rgb = colorlib.to_rgb(color)


def _attribs(dxf, e):
    attribs = {"layer": e.layer}
    if e.linetype is not None:
        attribs["linetype"] = _linetype(dxf, e.linetype)
    lw_mm = getattr(e, "_lw_mm", None)
    if lw_mm:
        attribs["lineweight"] = _nearest_lineweight(lw_mm)
    return attribs


def _add_entities(space, dxf, doc, entities):
    for e in entities:
        if isinstance(e, Table):
            _add_entities(space, dxf, doc, e.primitives(doc))
            continue
        attribs = _attribs(dxf, e)
        if isinstance(e, Line):
            out = space.add_line(tuple(e.start), tuple(e.end), dxfattribs=attribs)
        elif isinstance(e, Polyline):
            out = space.add_lwpolyline([tuple(v) for v in e.vertices], format="xy",
                                       close=e.closed, dxfattribs=attribs)
        elif isinstance(e, Arc):
            out = space.add_arc(tuple(e.center), e.radius, e.start_angle_deg,
                                e.end_angle_deg, dxfattribs=attribs)
        elif isinstance(e, Circle):
            out = space.add_circle(tuple(e.center), e.radius, dxfattribs=attribs)
        elif isinstance(e, BlockRef):
            out = space.add_blockref(e.block_name, tuple(e.position), dxfattribs={
                **attribs, "xscale": e.scale, "yscale": e.scale,
                "rotation": e.rotation_deg})
        elif isinstance(e, Text):
            style = e.style if dxf.styles.has_entry(e.style) else "STANDARD"
            key = (e.halign, e.valign)
            if "\n" in e.content:
                out = space.add_mtext(
                    e.content.replace("\n", r"\P"),
                    dxfattribs={**attribs, "char_height": e.height, "style": style,
                                "rotation": e.rotation_deg,
                                "attachment_point": MTEXT_ATTACHMENT.get(key, 7)})
                out.dxf.insert = tuple(e.position)
            else:
                out = space.add_text(
                    e.content,
                    dxfattribs={**attribs, "height": e.height, "style": style,
                                "rotation": e.rotation_deg})
                out.set_placement(tuple(e.position),
                                  align=ALIGN_MAP.get(key,
                                                      TextEntityAlignment.BOTTOM_LEFT))
        else:
            continue
        _apply_color(out, e.color)


def _ensure_layer(dxf, name, layer):
    if dxf.layers.has_entry(name):
        dxf_layer = dxf.layers.get(name)
    else:
        dxf_layer = dxf.layers.add(name)
    aci = colorlib.to_aci(layer.color)
    if aci is not None:
        dxf_layer.dxf.color = aci
    else:
        dxf_layer.rgb = colorlib.to_rgb(layer.color)
    dxf_layer.dxf.linetype = _linetype(dxf, layer.linetype)
    dxf_layer.dxf.lineweight = _nearest_lineweight(layer.lineweight_mm)
    if not layer.visible:
        dxf_layer.off()


def _export_references(space, dxf, doc, space_key):
    """Write referenced basefile geometry, bound onto '<REF>$<layer>' layers
    (references are flattened into the DXF; the JSON document keeps them live).
    """
    from roaddraft.document.entities import entity_from_dict
    from roaddraft.document.references import reference_groups

    for ref, base, prims in reference_groups(doc, space_key):
        for layer in base.layers.values():
            _ensure_layer(dxf, f"{ref.name}${layer.name}", layer)
        remapped = []
        for prim in prims:
            d = prim.to_dict()
            d["layer"] = f"{ref.name}${d.get('layer', '0')}"
            remapped.append(entity_from_dict(d))
        _add_entities(space, dxf, base, remapped)


def export_dxf(doc, path):
    from roaddraft.render.titleblock import title_block_entities

    dxf = ezdxf.new("R2018", setup=True)

    for layer in doc.layers.values():
        _ensure_layer(dxf, layer.name, layer)

    for style in doc.text_styles.values():
        if not dxf.styles.has_entry(style.name):
            dxf.styles.add(style.name, font="arial.ttf")
        dxf_style = dxf.styles.get(style.name)
        dxf_style.dxf.width = style.width_factor

    for block in doc.blocks.values():
        blk = dxf.blocks.new(block.name, base_point=tuple(block.base_point))
        _add_entities(blk, dxf, doc, block.entities)

    _export_references(dxf.modelspace(), dxf, doc, "model")
    _add_entities(dxf.modelspace(), dxf, doc, doc.model_entities.values())

    for sheet in doc.sheets.values():
        layout = dxf.layouts.new(sheet.name)
        try:
            layout.page_setup(size=(sheet.width_in, sheet.height_in),
                              margins=(0, 0, 0, 0), units="inch")
        except Exception:
            pass  # page setup is cosmetic; geometry is still correct
        _add_entities(layout, dxf, doc, title_block_entities(sheet))
        _export_references(layout, dxf, doc, sheet.id)
        _add_entities(layout, dxf, doc, sheet.entities.values())
        for vp in sheet.viewports:
            dxf_vp = layout.add_viewport(
                center=tuple(vp.center_paper),
                size=(vp.width_in, vp.height_in),
                view_center_point=tuple(vp.model_center),
                view_height=vp.height_in * vp.feet_per_inch)
            try:
                dxf_vp.dxf.view_twist_angle = vp.rotation_deg
            except Exception:
                pass

    dxf.saveas(path)
