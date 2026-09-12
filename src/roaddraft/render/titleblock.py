"""Title block templates, generated as primitive entities so the PNG, PDF, and
DXF renderers all draw exactly the same border and title block.

The semantic truth is sheet.title_block_fields; this module is only the
drawn representation.  ``sheet.title_block_template`` picks the drawing:

    standard   the generic bottom-strip block (default)
    caltrans   the Caltrans plan-sheet border: left binding strip, bottom
               plot strip, and the Dist/COUNTY/ROUTE/POST MILES title block
               with the engineer's seal panel (dimensioned for 22 x 34)
    none       border and title block are drawn by the document itself
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
    """Border + title block for ``sheet``, per its template."""
    template = (sheet.title_block_template or "standard").lower()
    if template == "none":
        return []
    if template == "caltrans":
        return caltrans_entities(sheet)
    return standard_entities(sheet)


def standard_entities(sheet: Sheet) -> List[Entity]:
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


# ----------------------------------------------------------- caltrans border
# Dimensions measured off a published Caltrans plan sheet (22 x 34 in).
# Horizontal positions are held from the left edge, the title block from the
# right; the left strip's cells are held from the top and bottom.
CT_TRIM = 0.005            # page trim line
CT_BIND = 1.904            # binding strip: main border starts here
CT_MARGIN = 0.503          # margin on the other three sides
CT_STRIP_X = 0.905         # outer edge of the lettered part of the strip
CT_SPLIT_LO = 1.205        # strip column split, below the calculated-by cell
CT_SPLIT_HI = 1.405        # strip column split, above it
CT_TB_W = 5.799            # title block width
CT_TB_H = 2.999            # title block height
CT_GRID_H = 0.780          # the Dist/COUNTY/ROUTE grid at the top of it
CT_HEAD_H = 0.341          # its header row
CT_PLOT_H = 1.195          # the plotted-on panel, lower right

# Dist/COUNTY/ROUTE/POST MILES/SHEET No./TOTAL SHEETS: (field, header, width)
CT_GRID = [("dist", "Dist", 0.501), ("county", "COUNTY", 0.999),
           ("route", "ROUTE", 1.140), ("post_miles", "POST MILES\nTOTAL PROJECT", 1.800),
           ("sheet_number", "SHEET\nNo.", 0.599), ("total_sheets", "TOTAL\nSHEETS", 0.760)]

# The left binding strip, top down: (height, outer cell, inner cell).  A cell
# is ("label", wording) for the printed caption or ("field", key) for a value.
CT_STRIP = [
    (1.144, ("field", "revised_by_3"), ("field", "date_revised_3")),
    (1.199, ("field", "revised_by_2"), ("field", "date_revised_2")),
    (1.200, ("field", "revised_by_1"), ("field", "date_revised_1")),
    (1.752, ("label", "REVISED BY"), ("label", "DATE REVISED")),
    (3.340, ("field", "designed_by"), ("field", "checked_by")),
    (1.916, ("label", "CALCULATED-\nDESIGNED BY"), ("label", "CHECKED BY")),
]
CT_STRIP_BOTTOM = 6.734    # the agency cell at the foot of the strip

CT_LABEL_H = 0.098
CT_VALUE_H = 0.140


def caltrans_entities(sheet: Sheet) -> List[Entity]:
    W, H = sheet.width_in, sheet.height_in
    f = sheet.title_block_fields
    out: List[Entity] = []
    n = [0]

    def get(key, default=""):
        return str(f.get(key, default))

    def line(x0, y0, x1, y1, mm=0.25):
        n[0] += 1
        out.append(_lw(Line(id=f"TB:l{n[0]}", start=[x0, y0], end=[x1, y1]), mm))

    def box(x0, y0, x1, y1, mm=0.25):
        n[0] += 1
        out.append(_lw(Polyline(id=f"TB:b{n[0]}",
                                vertices=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                                closed=True), mm))

    def text(x, y, s, height=CT_VALUE_H, halign="left", valign="bottom",
             rotation=0.0, color=None):
        if not s:
            return
        for i, part in enumerate(str(s).split("\n")):
            if not part:
                continue
            n[0] += 1
            dy = -i * height * 1.55
            pos = ([x - dy * math_sin(rotation), y + dy * math_cos(rotation)]
                   if rotation else [x, y + dy])
            out.append(Text(id=f"TB:t{n[0]}", position=pos, content=part,
                            height=height, halign=halign, valign=valign,
                            rotation_deg=rotation,
                            **({"color": color} if color else {})))

    # ---------------------------------------------------------- the border
    box(CT_TRIM, CT_TRIM, W - CT_TRIM, H - CT_TRIM, 0.13)
    box(CT_BIND, CT_MARGIN, W - CT_MARGIN, H - CT_MARGIN, 0.50)

    # --------------------------------------------- left binding strip cells
    line(CT_STRIP_X, CT_MARGIN, CT_STRIP_X, H - CT_MARGIN, 0.30)
    y = H - CT_MARGIN
    split_top = y - sum(c[0] for c in CT_STRIP)
    line(CT_SPLIT_HI, split_top, CT_SPLIT_HI, H - CT_MARGIN, 0.30)
    line(CT_SPLIT_LO, CT_MARGIN, CT_SPLIT_LO, split_top, 0.30)
    line(CT_STRIP_X, y, CT_BIND, y, 0.30)
    for height, outer, inner in CT_STRIP:
        cells = ((CT_STRIP_X, CT_SPLIT_HI, outer), (CT_SPLIT_HI, CT_BIND, inner))
        for cx0, cx1, (kind, cell) in cells:
            if kind == "label":
                text(cx0 + 0.115, y - height / 2, cell, CT_LABEL_H,
                     valign="middle", rotation=90.0, color=LABEL_COLOR)
            else:
                text((cx0 + cx1) / 2, y - height / 2, get(cell), CT_VALUE_H,
                     halign="center", valign="middle", rotation=90.0)
        y -= height
        line(CT_STRIP_X, y, CT_BIND, y, 0.30)
    line(CT_STRIP_X, CT_MARGIN + CT_STRIP_BOTTOM, CT_BIND,
         CT_MARGIN + CT_STRIP_BOTTOM, 0.30)
    line(CT_STRIP_X, CT_MARGIN, CT_BIND, CT_MARGIN, 0.30)
    mid = CT_MARGIN + (CT_STRIP_BOTTOM + (y - CT_MARGIN)) / 2
    text(CT_STRIP_X + 0.115, mid, "FUNCTIONAL SUPERVISOR", CT_LABEL_H,
         valign="middle", rotation=90.0, color=LABEL_COLOR)
    text(CT_SPLIT_LO + (CT_BIND - CT_SPLIT_LO) / 2, mid, get("functional_supervisor"),
         CT_VALUE_H, halign="center", valign="middle", rotation=90.0)
    low = CT_MARGIN + CT_STRIP_BOTTOM / 2
    text(CT_STRIP_X + 0.150, low, get("agency", "STATE OF CALIFORNIA"), 0.112,
         valign="middle", rotation=90.0)
    text(CT_SPLIT_LO + (CT_BIND - CT_SPLIT_LO) / 2, low, get("division"), 0.175,
         halign="center", valign="middle", rotation=90.0)

    # ------------------------------------------------------- bottom strip
    for x in (0.905, 5.777, 13.477, 22.252, 25.293):
        if x < W:
            line(x, CT_TRIM, x, CT_MARGIN, 0.13)
    text(0.985, 0.161, get("border_revised"), 0.120, color=LABEL_COLOR)
    text(5.877, 0.282, get("username"), 0.100, color=LABEL_COLOR)
    text(5.877, 0.077, get("dgn_file"), 0.100, color=LABEL_COLOR)
    text(13.577, 0.241, "RELATIVE BORDER SCALE", 0.098, color=LABEL_COLOR)
    text(14.100, 0.087, "IS IN INCHES", 0.098, color=LABEL_COLOR)
    bar_x, bar_y = 17.274, 0.104
    line(bar_x, bar_y, bar_x + 3.0, bar_y, 0.40)
    for i in range(4):
        line(bar_x + i, bar_y, bar_x + i, bar_y + 0.10, 0.40)
        text(bar_x + i, bar_y + 0.19, str(i), 0.092, halign="center")
    text(22.352, 0.159, get("unit"), CT_VALUE_H)
    text(25.393, 0.144, get("project_number_phase"), CT_VALUE_H)

    # ------------------------------------------- plotted-on panel, far right
    if W - CT_MARGIN + CT_PLOT_H < W:
        line(W - CT_MARGIN, CT_MARGIN, W - CT_TRIM, CT_MARGIN, 0.13)
        line(W - CT_MARGIN, CT_MARGIN + CT_PLOT_H, W - CT_TRIM,
             CT_MARGIN + CT_PLOT_H, 0.13)
        line(W - 0.351, CT_MARGIN, W - 0.351, CT_MARGIN + CT_PLOT_H, 0.13)
        text(W - 0.380, CT_MARGIN + 0.09, get("date_plotted"), 0.088,
             rotation=90.0, color=LABEL_COLOR)
        text(W - 0.179, CT_MARGIN + 0.09, get("time_plotted"), 0.088,
             rotation=90.0, color=LABEL_COLOR)

    # --------------------------------------------------------- title block
    x0, y1 = W - CT_MARGIN - CT_TB_W, H - CT_MARGIN
    y0 = y1 - CT_TB_H
    box(x0, y0, W - CT_MARGIN, y1, 0.50)
    grid_y = y1 - CT_GRID_H
    line(x0, grid_y, W - CT_MARGIN, grid_y, 0.13)
    head_y = y1 - CT_HEAD_H
    line(x0, head_y, W - CT_MARGIN, head_y, 0.13)
    x = x0
    for key, header, width in CT_GRID:
        if x > x0:
            line(x, grid_y, x, y1, 0.13)
        text(x + width / 2, y1 - 0.07, header, CT_LABEL_H,
             halign="center", valign="top")
        text(x + width / 2, (grid_y + head_y) / 2, get(key), CT_VALUE_H,
             halign="center", valign="middle")
        x += width

    # engineer's signature / approval panel
    seal_x = x0 + 3.727
    line(x0, y0 + 0.777, seal_x, y0 + 0.777, 0.50)          # panel divider
    line(x0 + 0.201, y0 + 1.739, x0 + 3.013, y0 + 1.739, 0.13)
    line(x0 + 3.158, y0 + 1.739, x0 + 3.806, y0 + 1.739, 0.13)
    text(x0 + 0.201, y0 + 1.550, "REGISTERED CIVIL ENGINEER", 0.101,
         color=LABEL_COLOR)
    text(x0 + 3.158, y0 + 1.550, "DATE", 0.100, color=LABEL_COLOR)
    text(x0 + 0.300, y0 + 1.790, get("registered_civil_engineer"), CT_VALUE_H)
    text(x0 + 3.158, y0 + 1.790, get("re_date"), CT_VALUE_H)
    line(x0 + 0.201, y0 + 1.017, x0 + 3.626, y0 + 1.017, 0.13)
    text(x0 + 0.201, y0 + 0.839, "PLANS APPROVAL DATE", 0.100, color=LABEL_COLOR)
    text(x0 + 0.964, y0 + 1.068, get("plans_approval_date"), CT_VALUE_H)
    for i, row in enumerate(get("disclaimer").split("\n")):
        text(x0 + 0.201, y0 + 0.545 - i * 0.147, row, CT_LABEL_H,
             color=LABEL_COLOR)

    # the seal
    seal = get("seal_name")
    if seal:
        cx, cy, r = x0 + 4.790, y0 + 1.230, 0.870
        n[0] += 1
        out.append(_lw(_circle(f"TB:seal{n[0]}", cx, cy, r), 0.40))
        n[0] += 1
        out.append(_lw(_circle(f"TB:seal{n[0]}", cx, cy, r * 0.74), 0.30))
        text(cx, cy + 0.380, seal, 0.128, halign="center", valign="middle")
        text(cx, cy - 0.020, get("seal_number"), 0.128,
             halign="center", valign="middle")
        text(cx, cy - 0.245, get("seal_expires"), 0.128,
             halign="center", valign="middle")
        text(cx, cy - 0.470, "CIVIL", 0.108, halign="center", valign="middle")
        line(cx - 0.45, cy + 0.205, cx + 0.45, cy + 0.205, 0.13)
        line(cx - 0.45, cy - 0.115, cx + 0.45, cy - 0.115, 0.13)
        line(cx - 0.53, cy - 0.340, cx + 0.53, cy - 0.340, 0.13)

    # ------------------------------------- sheet title, scale, sheet number
    text(x0 + 0.458, CT_MARGIN + 1.119, get("sheet_title"), 0.290)
    text(x0 + 0.262, CT_MARGIN + 0.761, get("scale"), 0.175)
    text(W - CT_MARGIN - 0.603, CT_MARGIN + 0.220, get("sheet_id"), 0.290,
         halign="right")
    return out


def _circle(eid, cx, cy, r, segments=64):
    import math
    return Polyline(id=eid, closed=True, vertices=[
        [cx + r * math.cos(2 * math.pi * i / segments),
         cy + r * math.sin(2 * math.pi * i / segments)]
        for i in range(segments)])


def math_sin(deg):
    import math
    return math.sin(math.radians(deg))


def math_cos(deg):
    import math
    return math.cos(math.radians(deg))
