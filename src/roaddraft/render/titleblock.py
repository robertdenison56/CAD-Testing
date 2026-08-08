"""Standard title block template, generated as primitive entities so the PNG,
PDF, and DXF renderers all draw exactly the same border and title block.

The semantic truth is sheet.title_block_fields; this module is only the
drawn representation.
"""
from __future__ import annotations

from typing import List

from roaddraft.document.entities import Entity, Line, Polyline, Text
from roaddraft.document.sheets import BORDER_MARGIN_IN, TITLE_STRIP_H_IN, Sheet

LABEL_COLOR = "#666666"
LABEL_H = 0.07
VALUE_H = 0.13


def _lw(entity: Entity, mm: float) -> Entity:
    entity._lw_mm = mm  # render-time lineweight for ephemeral template entities
    return entity


def title_block_entities(sheet: Sheet) -> List[Entity]:
    m = BORDER_MARGIN_IN
    W, H = sheet.width_in, sheet.height_in
    strip = m + TITLE_STRIP_H_IN
    iw = W - 2 * m
    out: List[Entity] = []

    out.append(_lw(Polyline(id="TB:border",
                            vertices=[[m, m], [W - m, m], [W - m, H - m], [m, H - m]],
                            closed=True), 0.5))
    out.append(_lw(Line(id="TB:strip", start=[m, strip], end=[W - m, strip]), 0.5))

    xs = [m + f * iw for f in (0.34, 0.60, 0.74, 0.88)]
    for i, x in enumerate(xs):
        out.append(_lw(Line(id=f"TB:div{i}", start=[x, m], end=[x, strip]), 0.25))

    fields = sheet.title_block_fields

    def get(key):
        return str(fields.get(key, ""))

    def label(tid, x, y, s):
        out.append(Text(id=tid, position=[x, y], content=s, height=LABEL_H,
                        color=LABEL_COLOR, halign="left", valign="top"))

    def value(tid, x, y, s, height=VALUE_H, halign="left", valign="middle"):
        if s:
            out.append(Text(id=tid, position=[x, y], content=s, height=height,
                            halign=halign, valign=valign))

    pad = 0.12
    top = strip - 0.06

    # cell 1: project / agency
    label("TB:l_proj", m + pad, top, "PROJECT")
    value("TB:v_proj", m + pad, m + 0.72, get("project"), height=0.16)
    value("TB:v_agency", m + pad, m + 0.32, get("agency"), height=0.10)

    # cell 2: sheet title
    label("TB:l_title", xs[0] + pad, top, "SHEET TITLE")
    value("TB:v_title", (xs[0] + xs[1]) / 2, m + 0.55, get("sheet_title"),
          height=0.18, halign="center")

    # cell 3: designed / drawn / checked
    for i, (key, lbl) in enumerate([("designed_by", "DESIGNED BY"),
                                    ("drawn_by", "DRAWN BY"),
                                    ("checked_by", "CHECKED BY")]):
        y = strip - 0.28 - i * 0.36
        label(f"TB:l_{key}", xs[1] + pad, y + 0.12, lbl)
        value(f"TB:v_{key}", xs[1] + 1.1, y, get(key), height=0.10)

    # cell 4: date / scale
    mid = m + TITLE_STRIP_H_IN / 2
    out.append(_lw(Line(id="TB:div_ds", start=[xs[2], mid], end=[xs[3], mid]), 0.25))
    label("TB:l_date", xs[2] + pad, strip - 0.06, "DATE")
    value("TB:v_date", xs[2] + pad, mid + 0.24, get("date"), height=0.11)
    label("TB:l_scale", xs[2] + pad, mid - 0.06, "SCALE")
    value("TB:v_scale", xs[2] + pad, m + 0.24, get("scale"), height=0.11)

    # cell 5: sheet number
    label("TB:l_no", xs[3] + pad, top, "SHEET")
    value("TB:v_no", (xs[3] + W - m) / 2, m + 0.62, get("sheet_number"),
          height=0.20, halign="center")
    total = get("total_sheets")
    value("TB:v_total", (xs[3] + W - m) / 2, m + 0.22,
          f"OF {total}" if total else "", height=0.10, halign="center")

    return out
