"""Annotation-scale commands: the scale list, the current scale, the paper
defaults, and re-sizing annotative entities for another plot scale.

``set_annotation_scale`` is the AutoCAD annotation-scale switch: it changes
the current scale and (by default) re-sizes every annotative model-space
entity — text heights from their paper heights, station ticks about their
midpoints, and design-anchored labels re-placed at their paper offset from
the anchor through the design model.  Text with no anchor keeps its
insertion point, exactly like annotative text in AutoCAD.
"""
from __future__ import annotations

import math
from typing import List, Optional

from roaddraft.commands.handlers import CommandFault, _diff
from roaddraft.design.anchors import resolve_record
from roaddraft.design.errors import DesignError
from roaddraft.design.labels import LABEL_KINDS, compile_label
from roaddraft.document import annotation as anno
from roaddraft.document.document import Document
from roaddraft.document.entities import Dimension, Line, Point, Text


# ---------------------------------------------------------------- helpers


def _find_scale(doc: Document, value):
    """``(feet_per_inch, entry_or_None)`` for a list name, a number or a
    scale string."""
    entries = anno.scale_list(doc)
    if isinstance(value, str):
        for s in entries:
            if s["name"].lower() == value.strip().lower():
                return float(s["feet_per_inch"]), s
    try:
        fpi = anno.parse_scale(value)
    except ValueError as ex:
        raise CommandFault(str(ex), hint="scales: " + ", ".join(s["name"] for s in entries))
    for s in entries:
        if abs(float(s["feet_per_inch"]) - fpi) < 1e-9:
            return fpi, s
    return fpi, None


def _viewport_warnings(doc: Document, scale: float) -> List[str]:
    out = []
    for sheet in doc.sheets.values():
        for vp in sheet.viewports:
            if abs(vp.feet_per_inch - scale) > 1e-9:
                out.append(f"viewport {vp.id} on sheet {sheet.name} plots at "
                           f"{anno.format_scale(vp.feet_per_inch)}; model annotation sized "
                           f"for {anno.format_scale(scale)} will appear at "
                           f"{scale / vp.feet_per_inch:.2g}x")
    return out


def _replace_label(doc: Document, e: Text, rec: dict, scale: float) -> Optional[float]:
    """Re-place a design-anchored label at its paper offset through the
    design model.  Returns the paper offset it now sits at, or None when that
    is not possible."""
    a = e.anchor
    if not a or "offset_in" not in rec or a.get("kind") not in LABEL_KINDS:
        return None
    align = doc.design.alignments.get(a.get("alignment"))
    if align is None or a.get("side") not in ("left", "right"):
        return None
    side, offset_in = a["side"], float(rec["offset_in"])
    if offset_in < 0:  # lettered on the other side, as older files stored it
        side, offset_in = ("right" if side == "left" else "left"), -offset_in
    try:
        ap = resolve_record(align, a)
        spec = compile_label(align, ap, a["kind"], side=side,
                             label_offset=offset_in * scale,
                             rotation=a.get("rotation") or "along", content=e.content,
                             halign=e.halign, valign=e.valign)
    except (DesignError, KeyError, ValueError, TypeError):
        return None
    e.position = spec.position
    e.rotation_deg = spec.rotation_deg
    e.anchor = dict(a, side=spec.side, label_offset=spec.label_offset)
    return offset_in


def rescale_entities(doc: Document, scale: float) -> List[str]:
    """Re-size every annotative model-space entity stamped for another scale."""
    modified: List[str] = []
    for eid, e in doc.model_entities.items():
        rec = e.annotative
        if not rec or abs(float(rec["scale"]) - scale) < 1e-9:
            continue
        old = float(rec["scale"])
        if isinstance(e, Text):
            height_in = float(rec.get("height_in", e.height / old))
            offset_in = _replace_label(doc, e, rec, scale)
            e.height = height_in * scale
            e.annotative = dict(rec, scale=scale, height_in=height_in)
            if offset_in is not None:
                e.annotative["offset_in"] = offset_in
        elif isinstance(e, Dimension):
            height_in = float(rec.get("height_in", e.text_height / old))
            # every size a dimension has is derived from its text height, so one
            # factor re-sizes the annotation; the measured points do not move
            factor = (height_in * scale) / e.text_height if e.text_height else 1.0
            e.text_height = height_in * scale
            for key in ("arrow_size", "text_gap", "extension_offset",
                        "extension_beyond"):
                value = getattr(e, key)
                if value is not None:
                    setattr(e, key, value * factor)
            e.annotative = dict(rec, scale=scale, height_in=height_in)
        elif isinstance(e, Point):
            # the marker and the label are sized on paper together
            height_in = float(rec.get("height_in", e.text_height / old))
            factor = (height_in * scale) / e.text_height if e.text_height else 1.0
            e.text_height = height_in * scale
            e.size *= factor
            e.annotative = dict(rec, scale=scale, height_in=height_in)
        elif isinstance(e, Line):
            length = math.hypot(e.end[0] - e.start[0], e.end[1] - e.start[1])
            half_in = float(rec.get("half_len_in", length / 2.0 / old))
            half = half_in * scale
            mx, my = (e.start[0] + e.end[0]) / 2.0, (e.start[1] + e.end[1]) / 2.0
            if length > 1e-12:
                ux, uy = (e.end[0] - e.start[0]) / length, (e.end[1] - e.start[1]) / length
            else:
                ux, uy = 0.0, 1.0
            e.start = [mx - ux * half, my - uy * half]
            e.end = [mx + ux * half, my + uy * half]
            e.annotative = dict(rec, scale=scale, half_len_in=half_in)
        else:
            e.annotative = dict(rec, scale=scale)
        modified.append(eid)
    return modified


def adopt_entities(doc: Document, scale: float) -> List[str]:
    """Stamp un-stamped model annotation as annotative at ``scale`` (texts,
    and anchored station ticks) so later scale changes re-size it."""
    adopted: List[str] = []
    for eid, e in doc.model_entities.items():
        if e.annotative:
            continue
        if isinstance(e, Text):
            rec = {"scale": scale, "height_in": e.height / scale}
            if e.anchor and e.anchor.get("label_offset") is not None:
                rec["offset_in"] = float(e.anchor["label_offset"]) / scale
            e.annotative = rec
            adopted.append(eid)
        elif isinstance(e, Dimension):
            e.annotative = {"scale": scale, "height_in": e.text_height / scale}
            adopted.append(eid)
        elif isinstance(e, Line) and e.anchor and e.anchor.get("kind") == "tick":
            length = math.hypot(e.end[0] - e.start[0], e.end[1] - e.start[1])
            e.annotative = {"scale": scale, "half_len_in": length / 2.0 / scale}
            adopted.append(eid)
    return adopted


# --------------------------------------------------------------- commands


def set_annotation_scale(doc: Document, p: dict):
    old = anno.current_scale(doc)
    old_name = anno.scale_name(doc, old)
    value = p.get("scale")
    if value is None or (isinstance(value, str) and value.strip().lower() in ("off", "none")):
        doc.settings["annotation_scale"] = None
        return (f"annotation scale turned off (was {old_name}); annotation commands use the "
                f"fixed engine sizes (8 ft text, 10 ft ticks, 16 ft offsets) and existing "
                f"entities keep their sizes", _diff(modified=["settings"]), [])
    fpi, entry = _find_scale(doc, value)
    doc.settings["annotation_scale"] = fpi
    added = ""
    if entry is None:
        entries = anno.scale_list(doc) + [{"name": anno.format_scale(fpi), "feet_per_inch": fpi}]
        entries.sort(key=lambda s: float(s["feet_per_inch"]))
        doc.settings["annotation_scales"] = entries
        added = " (added to the scale list)"
    modified = ["settings"]
    n_adopted = 0
    if p.get("adopt"):
        ids = adopt_entities(doc, fpi)
        n_adopted = len(ids)
        modified += ids
    n_rescaled = 0
    if p.get("rescale", True):
        ids = rescale_entities(doc, fpi)
        n_rescaled = len(ids)
        modified += [i for i in ids if i not in modified]
    sizes = anno.model_sizes(doc)
    msg = (f"annotation scale set to {anno.scale_name(doc, fpi)}{added} (was {old_name}): "
           f"text {sizes['text_height']:g} ft, ticks {sizes['tick_half_len']:g} ft, "
           f"label offset {sizes['label_offset']:g} ft; {n_rescaled} annotative entities "
           f"rescaled")
    if n_adopted:
        msg += f", {n_adopted} adopted"
    return msg, _diff(modified=modified), _viewport_warnings(doc, fpi)


def add_annotation_scale(doc: Document, p: dict):
    try:
        fpi = anno.parse_scale(p["scale"])
    except ValueError as ex:
        raise CommandFault(str(ex))
    name = str(p.get("name") or anno.format_scale(fpi))
    entries = anno.scale_list(doc)
    for s in entries:
        if s["name"].lower() == name.lower():
            raise CommandFault(f"annotation scale {name!r} already exists",
                               hint="delete_annotation_scale it first or use another name")
        if abs(float(s["feet_per_inch"]) - fpi) < 1e-9:
            raise CommandFault(f"a scale of {anno.format_scale(fpi)} already exists as "
                               f"{s['name']!r}")
    entries.append({"name": name, "feet_per_inch": fpi})
    entries.sort(key=lambda s: float(s["feet_per_inch"]))
    doc.settings["annotation_scales"] = entries
    return (f"annotation scale {name!r} ({fpi:g} ft/in) added; "
            f"{len(entries)} scales in the list", _diff(created=[f"scale:{name}"]), [])


def delete_annotation_scale(doc: Document, p: dict):
    fpi, entry = _find_scale(doc, p["scale"])
    if entry is None:
        raise CommandFault(f"no annotation scale {p['scale']!r} in the list",
                           hint="scales: " + ", ".join(s["name"] for s in anno.scale_list(doc)))
    current = anno.current_scale(doc)
    if current is not None and abs(current - fpi) < 1e-9:
        raise CommandFault(f"{entry['name']} is the current annotation scale",
                           hint="set_annotation_scale to another scale (or off) first")
    doc.settings["annotation_scales"] = [s for s in anno.scale_list(doc)
                                         if s["name"] != entry["name"]]
    return (f"annotation scale {entry['name']!r} deleted",
            _diff(deleted=[f"scale:{entry['name']}"]), [])


def set_annotation_defaults(doc: Document, p: dict):
    paper = dict(anno.paper_defaults(doc))
    changed = []
    for key in anno.PAPER_KEYS:
        if key in p:
            paper[key] = float(p[key])
            changed.append(key)
    if not changed:
        raise CommandFault("give at least one of " + ", ".join(anno.PAPER_KEYS))
    doc.settings["annotation_paper"] = paper
    scale = anno.current_scale(doc)
    parts = [f"{k} = {paper[k]:g} in" for k in anno.PAPER_KEYS]
    if scale is not None:
        sizes = anno.model_sizes(doc)
        parts = [f"{k} = {paper[k]:g} in ({sizes[m]:g} ft at {anno.scale_name(doc, scale)})"
                 for k, m in zip(anno.PAPER_KEYS, ("text_height", "tick_half_len",
                                                   "label_offset"))]
    return "annotation paper defaults: " + ", ".join(parts), _diff(modified=["settings"]), []


__all__ = ["set_annotation_scale", "add_annotation_scale", "delete_annotation_scale",
           "set_annotation_defaults", "rescale_entities", "adopt_entities"]
