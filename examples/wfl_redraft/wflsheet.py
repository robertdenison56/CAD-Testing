"""Digitise a WFL sample plan sheet into what each file of its redraft owns.

The WFL counterpart of ppm_redraft/ppmsheet.py: the same steps, driven by the FHWA
Federal Lands (WFL) 11 x 17 border instead of the Caltrans one, and by what the WFL
sheets do differently:

  * the lettering is TrueType, drawn as filled outlines over a real text layer, so
    the text layer is trusted and the outlines only give each run its cap height;
  * station ticks are drawn to one side of the centerline, and the station numbers
    ("111", "112") are lettered square to the line at a fixed offset from it;
  * nothing prints a numeric scale: it comes from the tick spacing, or a graphic
    scale bar ("Scale in feet");
  * existing features are thin dashed lines (Caltrans dots them);
  * a plan-profile sheet carries the profile grid in its lower half, which stays
    on the sheet, and the plan view above it is what the viewport shows.

    digitise(sheet_id, rel, extract, cfg) -> dict (JSON-able)

Config keys (all optional; see configs/README.md):
    kind, family, fpi, twist, calibration, template, sheet_regions, plan_rect,
    no_alignments, fields, drop_fonts, skip/reason
"""
import math
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ppm_redraft"))

import alignfit                                                   # noqa: E402
from leaders import landings, component, ends_of, poly_dist, closed, plen   # noqa: E402
from ppmsheet import (match_glyphs, reanchor, join_lines, mark_symbols,        # noqa: E402
                      run_center, centroid, bad_char)
from sheetgeom import Sheet, extent, Grid, bbox_of                # noqa: E402

FRAME = (0.7, 0.3, 16.3, 10.7)                 # the WFL border frame on a 17 x 11 sheet
TB = (14.3, 10.3, 16.3, 10.7)                  # the PROJECT / SHEET NUMBER block
TITLE_BOX = (12.3, 0.3, 16.3, 1.3)             # the sheet title box
SHEET_W, SHEET_H = 17.0, 11.0
SCALES = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0, 200.0)
CAP_EM = 0.72                                  # cap height / em, lettering without outlines

NUMBER = re.compile(r"^\d{1,4}$")
PLUS = re.compile(r"^\+\d+(\.\d+)?$")
WIDTH = re.compile(r"^\d{1,3}(\.\d+)?['’]$")
OFFSET = re.compile(r"^\d+(\.\d+)?['’]\s*(Lt|Rt)\.?$", re.I)
STATION = re.compile(r"^\d{1,4}\+\d{2}(\.\d+)?$")
MATCH = re.compile(r"^MATCH\s*LINE", re.I)
SHEET_NO = re.compile(r"^[A-Z]{1,2}\.\s?\d{1,3}[A-Z]?$")
NAME = re.compile(r'^"([A-Za-z0-9 \-]+)"(\s*Line\b.*)?$', re.I)      # '"MAIN 01" Line to be constructed'
SCALE_BAR = re.compile(r"^scale\s+in\s+(feet|miles)$", re.I)
SCALE_TEXT = re.compile(r"^(NO SCALE|SCALE\b.*|1\"\s*=\s*\d+')$", re.I)

PLAN_FAMILIES = {"plan-profile", "approach", "parking", "erosion", "drainage", "wall",
                 "detour", "traffic", "signing", "site", "demolition", "layout"}


def snap_h(h):
    """MicroStation sizes text by its capital height, so the text layer's size is the
    cap height itself: kept as lettered, to the thousandth."""
    return round(h, 3)


def family_of(rel, fields):
    """What kind of sheet this is, from the source file and the title block."""
    stem = rel.split("/")[-1].lower()
    title = (fields.get("sheet_title") or "").upper()
    if "general" in stem:
        return "general"
    if "summary" in stem:
        return "soq"
    if "cross-sections" in stem:
        return "xs"
    if "TABULATION" in title or ("QUANTIT" in title and "PLAN" not in title):
        return "qtab"
    if "SURVEY CONTROL" in title:
        return "survey"
    if "TYPICAL SECTION" in title or "typical" in stem:
        return "typical"
    if "DETAIL" in title and "PLAN" not in title:
        return "details"
    if "CULVERT" in title or "DRAINAGE" in title or "HYDRAULIC" in title:
        return "drainage"
    if "plan-profile" in stem or "PLAN AND PROFILE" in title or "PLAN & PROFILE" in title:
        return "plan-profile"
    if "DEMOLITION" in title:
        return "demolition"
    if "EROSION" in title:
        return "erosion"
    if "WALL" in title:
        return "wall"
    if "DETOUR" in title or "TEMPORARY TRAFFIC" in title:
        return "detour"
    if "SIGNING" in title or "SIGN " in title:
        return "signing"
    if "TRAFFIC CONTROL" in title:
        return "traffic"
    if "LAYOUT" in title:
        return "layout"
    if "SITE PLAN" in title:
        return "site"
    if "LINE GRAPH" in title or "SECTION" in title or "POINT TABLE" in title:
        return "details"
    if "approach" in stem:
        return "approach"
    if "parking" in stem:
        return "parking"
    return "other"


# ------------------------------------------------------------- calibration
def calibrate(D):
    """(scale, (ox, oy), how): the published frame fitted to FRAME.  The split WFL
    pages are full-size 17 x 11 prints (scale 1), bar one reduced page."""
    W, H = D["page_in"]
    hz, vt = [], []
    for p in D["paths"]:
        for sub in p["subs"]:
            for a, b in zip(sub, sub[1:]):
                L = math.dist(a, b)
                if L < min(W, H) * 0.5:
                    continue
                if abs(a[1] - b[1]) < 0.01:
                    hz.append((min(a[0], b[0]), max(a[0], b[0]), (a[1] + b[1]) / 2, p["lw"]))
                elif abs(a[0] - b[0]) < 0.01:
                    vt.append((min(a[1], b[1]), max(a[1], b[1]), (a[0] + b[0]) / 2, p["lw"]))
    for lw in sorted({h[3] for h in hz} | {v[3] for v in vt}, reverse=True):
        H_ = [h for h in hz if h[3] == lw and h[1] - h[0] > W * 0.8]
        V_ = [v for v in vt if v[3] == lw and v[1] - v[0] > H * 0.8]
        if len(H_) < 2 or len(V_) < 2:
            continue
        y0, y1 = min(h[2] for h in H_), max(h[2] for h in H_)
        x0, x1 = min(v[2] for v in V_), max(v[2] for v in V_)
        sx = (x1 - x0) / (FRAME[2] - FRAME[0])
        sy = (y1 - y0) / (FRAME[3] - FRAME[1])
        if abs(sx - sy) / sx < 0.01 and 0.4 < sx < 2.5:
            s = (sx + sy) / 2
            return s, (x0 - FRAME[0] * s, y0 - FRAME[1] * s), f"frame lw {lw}"
    s = W / SHEET_W if W >= H else 1.0
    return s, (0.0, 0.0), "default (no frame found)"


# ------------------------------------------------------------- text layer
def dedupe_chars(chars):
    """Bold lettering is printed as the same string two or three times, a hair
    apart, and once more in a second font: one copy of each character stays."""
    out, seen = [], {}
    for c in chars:
        key = (c["t"], round(c["y"] / 0.02))
        xs = seen.setdefault(key, [])
        # a copy sits well within the letter's own advance of the first; two of the
        # same letter in a row sit a whole advance apart.  The copy in the second
        # font (its name starts with "*") is set with that font's widths, so it
        # drifts along the string: it may sit up to an advance away
        k = 1.0 if (c.get("font") or "").startswith("*") else 0.6
        tol = k * c["adv"] if c["adv"] > 0 else 0.25 * max(c["size"], 0.02)
        if any(abs(x - c["x"]) < tol for x in xs):
            continue
        xs.append(c["x"])
        out.append(c)
    return out


def join_pieces(pieces, gap=0.2):
    """Runs on one line, left to right, joined with a space where they are apart
    (a gap of more than `gap` of the lettering's size)."""
    pieces = sorted(pieces, key=lambda r: r["x"] if abs(r["rot"]) < 45 else r["y"])
    text = ""
    for prev, r in zip([None] + pieces, pieces):
        if prev is None:
            text = r["text"]
            continue
        if abs(r["rot"]) < 45:
            g = r["x"] - prev["end"][0]
        else:
            g = r["y"] - prev["end"][1]
        text += ("" if g < gap * max(r["size"], 0.02) else " ") + r["text"]
    return text.strip()


def cell_text(chars, x0, x1, y0, y1):
    """The lettering in a title block cell, read a character at a time (the runs of
    a bold value break where its copies overlap): a space where two characters
    are more than a third of the size apart."""
    cs = sorted((c for c in chars if c["t"].strip() and x0 <= c["x"] < x1 and y0 <= c["y"] < y1
                 and c["size"] > 0.01), key=lambda c: c["x"])
    out = []
    for c in cs:
        if out and c["t"] == out[-1]["t"] and \
                c["x"] - out[-1]["x"] < (0.6 * c["adv"] if c["adv"] > 0 else 0.3 * c["size"]):
            continue                          # a bold copy of the last letter
        if out and c["x"] - (out[-1]["x"] + out[-1]["adv"]) > 0.33 * c["size"]:
            out.append({"t": " ", "x": c["x"], "adv": 0.0, "size": c["size"]})
        out.append(c)
    return re.sub(r"\s+", " ", "".join(c["t"] for c in out)).strip()


def title_fields(runs, has_title_box, chars=(), TB=TB):
    """Title block values by where the WFL border puts them (`TB` is the PROJECT /
    SHEET NUMBER block, which a portrait cross-section sheet carries at its own top
    right corner)."""
    f = {}
    hdr = {}
    for r in runs:
        x, y = run_center(r)
        if x < TB[0] - 0.05 or abs(r["rot"]) > 1:
            continue
        t = r["text"].strip().upper()
        if TB[1] + 0.19 < y < TB[3] + 0.02 and t in ("STATE", "PROJECT", "SHEET", "NUMBER"):
            hdr[t] = x
    sx = TB[2] - 0.4
    px0 = TB[0]
    if "STATE" in hdr:
        px0 = TB[0] + 0.4
        f["state"] = cell_text(chars, TB[0], px0, TB[1], TB[1] + 0.2)
    f["project"] = cell_text(chars, px0, sx, TB[1], TB[1] + 0.2)
    f["sheet_number"] = cell_text(chars, sx, TB[2] + 0.05, TB[1], TB[1] + 0.2).replace(" ", "")
    for key in ("project", "sheet_number"):
        if not f[key]:
            del f[key]
    # the NPS numbers above the frame
    for r in runs:
        x, y = run_center(r)
        if y > FRAME[3] and x > 10 and abs(r["rot"]) < 1:
            t = r["text"].strip()
            if t.upper().startswith("NPS"):
                f["nps_pmis" if "PMIS" in t.upper() else "nps_drawing"] = t
    # the plot stamp up the left margin: date and time, file, [description]
    stamp = sorted((r for r in runs if r["x"] < FRAME[0] and abs(r["rot"] - 90) < 2),
                   key=lambda r: r["y"])
    groups, cur = [], []
    for r in stamp:
        if cur and r["y"] - cur[-1]["end"][1] > 0.4:
            groups.append(cur)
            cur = []
        cur.append(r)
    if cur:
        groups.append(cur)
    if groups:
        f["date_plotted"] = join_pieces(groups[0])
    if len(groups) > 1:
        rest = join_pieces([r for g in groups[1:] for r in g])
        m = re.match(r"^(.*?\.dgn)\s*(\[.*?\])?\s*(.*)$", rest, re.S)
        if m:
            f["dgn_file"] = m.group(1)
            if m.group(2):
                f["description"] = m.group(2)
            if m.group(3).strip():
                f["stamp_extra"] = m.group(3).strip()      # Designed by / Checked by on older borders
        else:
            f["dgn_file"] = rest
    # the sheet title box and the scale beside it
    if has_title_box:
        inside = [r for r in runs if abs(r["rot"]) < 1 and
                  TITLE_BOX[0] < run_center(r)[0] < TITLE_BOX[2] and
                  TITLE_BOX[1] < run_center(r)[1] < TITLE_BOX[3]]
        lines = join_lines(inside)
        f["sheet_title"] = "\n".join(r["text"].strip() for r in sorted(lines, key=lambda r: -r["y"])
                                     if r["text"].strip())
    for r in runs:
        x, y = run_center(r)
        if abs(r["rot"]) < 1 and y < TITLE_BOX[3] and TITLE_BOX[0] - 2.5 < x < TITLE_BOX[0] and \
                SCALE_TEXT.match(r["text"].strip()):
            f["scale"] = r["text"].strip()
            r["kind"] = "title"
    return f


# ------------------------------------------------------------- scale
def scale_bar(runs):
    """Feet per inch from a graphic scale bar: its 'Scale in feet' label and the
    numbers lettered along it."""
    for r in runs:
        m = SCALE_BAR.match(r["text"].strip())
        if not m or m.group(1).lower() != "feet" or abs(r["rot"]) > 1:
            continue
        cx, cy = run_center(r)
        nums = []
        for q in runs:
            if q is r or abs(q["rot"]) > 1 or not NUMBER.match(q["text"].strip()):
                continue
            qx, qy = run_center(q)
            if abs(qx - cx) < 2.5 and 0.0 < abs(qy - cy) < 0.6:
                nums.append((qx, int(q["text"])))
        nums.sort()
        zero = next((x for x, v in nums if v == 0), None)
        right = [(x, v) for x, v in nums if zero is not None and x > zero + 0.3 and v > 0]
        if right:
            # from the bar's zero to the last number on its right (a bar may run left
            # of zero too)
            fpi = right[-1][1] / (right[-1][0] - zero)
            near = min(SCALES, key=lambda s: abs(s - fpi))
            return near if abs(near - fpi) < 0.06 * fpi else round(fpi, 1)
    return None


# ------------------------------------------------------------- alignments
def wfl_ticks(chain, segs, spacing):
    """Station ticks on a chain: [(along, point on the chain, length)].  WFL draws a
    tick from the centerline out to one side; a tick across the line counts too.
    Only the ticks on the 100 ft rhythm are kept, the longest at each station."""
    found = []
    pts = chain.pts
    x0 = min(p[0] for p in pts) - 0.4; x1 = max(p[0] for p in pts) + 0.4
    y0 = min(p[1] for p in pts) - 0.4; y1 = max(p[1] for p in pts) + 0.4
    for a, b in segs:
        if not (x0 <= a[0] <= x1 and y0 <= a[1] <= y1):
            continue
        L = math.dist(a, b)
        if not 0.06 < L < 0.3:
            continue
        v = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        hit = False
        for e, o in ((a, b), (b, a)):
            de, ae, ue = chain.locate(e)
            if de < 0.012 and abs(ue[0] * v[0] + ue[1] * v[1]) < 0.15:
                found.append((ae, e, L))
                hit = True
                break
        if hit:
            continue
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        d, along, u = chain.locate(m)
        if d <= 0.02 and abs(u[0] * v[0] + u[1] * v[1]) < 0.15:
            found.append((along, m, L / 2))
    found.sort()
    if len(found) < 2:
        return found
    best = []
    for a0, _, _ in found:
        keep = [t for t in found if abs(((t[0] - a0) / spacing) - round((t[0] - a0) / spacing)) < 0.03]
        if len(keep) > len(best):
            best = keep
    out = []
    for t in best:
        if out and abs(t[0] - out[-1][0]) < 0.03:
            if t[2] > out[-1][2]:
                out[-1] = t
            continue
        out.append(t)
    return out


def label_ticks(ticks, runs, chain, spacing):
    """Station (ft) at each tick from the numbers lettered square to the line at
    its station, however far out they sit."""
    labelled = []
    for along, m, _ in ticks:
        near = None
        for r in runs:
            if not NUMBER.match(r["text"].strip()) or len(r["text"].strip()) < 2:
                continue
            d, al, _ = chain.locate(r["center"])
            if abs(al - along) < 0.08 and 0.05 < d < 2.2 and (near is None or d < near[0]):
                near = (d, r)
        labelled.append(near[1] if near else None)
    a0 = ticks[0][0]
    ks = [round((t[0] - a0) / spacing) for t in ticks]
    best = None
    for direction in (1, -1):
        for i, r in enumerate(labelled):
            if r is None:
                continue
            h0 = int(r["text"]) - direction * ks[i]
            score = 0
            for k, rr in zip(ks, labelled):
                if rr is None:
                    continue
                score += 1 if int(rr["text"]) == h0 + direction * k else -2
            if best is None or score > best[0]:
                best = (score, direction, h0)
    if best is None or best[0] < 2:
        return None
    _, direction, h0 = best
    return direction, [(h0 + direction * k) * 100.0 for k in ks], labelled


def fit(heavy_paths, short_segs, runs, fpi, min_len=2.0, names=None):
    """Alignments found on the sheet at this scale (alignfit.fit with WFL ticks and
    labels): dicts in sheet inches with elements, begin station, name, ticks, and
    how the station numbers sit (offset from the line, angle to it, height).
    `names` are the runs a name may come from (the '"MAIN 01" Line to be
    constructed' label is a callout, so it is not among the free runs)."""
    spacing = 100.0 / fpi
    names = runs if names is None else names
    for r in list(runs) + list(names):
        r.setdefault("center", run_center(r))
    out = []
    pieces = [pc for ch in alignfit.chains_of(alignfit.dedupe(heavy_paths))
              for pc in alignfit.split_reversals(ch)]
    for ch in pieces:
        if ch.length() < min_len or math.dist(ch.pts[0], ch.pts[-1]) < 0.05:
            continue
        if not alignfit.well_formed(alignfit.elements_of(ch)):
            continue
        ticks = wfl_ticks(ch, short_segs, spacing)
        if len(ticks) < 2:
            continue
        lab = label_ticks(ticks, runs, ch, spacing)
        if lab is None:
            continue
        direction, stations, labels = lab
        if direction < 0:
            ch.reverse()
            ticks = sorted((ch.length() - a, m, h) for a, m, h in ticks)
            stations = list(reversed(stations))
            labels = list(reversed(labels))
        begin = sum(s - a * fpi for (a, _, _), s in zip(ticks, stations)) / len(ticks)
        resid = max(abs(begin + a * fpi - s) for (a, _, _), s in zip(ticks, stations))
        if resid > 10.0 or ticks[-1][0] > ch.length() + 0.05:
            continue
        # the name: a '"NAME" Line ...' label near the chain, else a bare '"NAME"'
        name = None
        for r in names:
            m = NAME.match(r["text"].strip())
            if not m:
                continue
            d, _, _ = ch.locate(r["center"])
            if d > 1.8:
                continue
            rank = (0 if m.group(2) else 1, d)
            if name is None or rank < name[0]:
                name = (rank, m.group(1).strip())
        # how the sheet letters the station numbers
        offs, rels, hs = [], [], []
        for (along, m, _), r in zip(ticks, labels):
            if r is None:
                continue
            d, al, u = ch.locate(r["center"])
            side = u[0] * (r["center"][1] - m[1]) - u[1] * (r["center"][0] - m[0])
            offs.append(d if side > 0 else -d)
            th = math.degrees(math.atan2(u[1], u[0]))
            rels.append(((r["rot"] - th) + 180.0) % 360.0 - 180.0)
            hs.append(r["h"])
        out.append({"chain": ch, "paths": [pid for pid, _ in ch.parts],
                    "elements": alignfit.elements_of(ch),
                    "begin_station": begin, "fit_residual_ft": resid,
                    "name": name[1] if name else None, "name_dist": name[0][1] if name else None,
                    "ticks": ticks, "stations": stations,
                    "labels": [r["id"] if r else None for r in labels],
                    "label_offset_in": statistics.median(offs) if offs else 0.3,
                    "label_rot_rel": statistics.median(rels) if rels else -90.0,
                    "label_h": statistics.median(hs) if hs else 0.10,
                    "tick_len_in": statistics.median(t[2] for t in ticks)})
    return out


def fit_any_scale(heavy, segs, runs, scales, names=None):
    """The scale that letters the most station ticks, and its alignments."""
    best = None
    for s in scales:
        als = fit(heavy, segs, runs, s, names=names)
        score = sum(sum(1 for l in a["labels"] if l) for a in als)
        if als and score >= 2 and (best is None or score > best[0]):
            best = (score, s, als)
    return (best[1], best[2]) if best else (None, [])


# ------------------------------------------------------------- regions
def profile_divider(paths):
    """On a plan-profile sheet, the heavy full-width line between the plan view and
    the profile grid (its y), else None."""
    ys = []
    for p in paths:
        if p["lw"] < 0.9 or p["dash"]:
            continue
        for a, b in zip(p["pts"], p["pts"][1:]):
            if abs(a[1] - b[1]) < 0.01 and abs(a[0] - b[0]) > 0.85 * (FRAME[2] - FRAME[0]) \
                    and 3.0 < a[1] < 8.0:
                ys.append(a[1])
    return max(ys) if ys else None


def is_existing(p):
    """WFL draws existing features as thin dashed lines."""
    return bool(p["dash"]) and p["lw"] <= 0.6


# ------------------------------------------------------------- main
def digitise(sheet_id, rel, extract, cfg):
    cfg = dict(cfg or {})
    W, H = extract["page_in"]
    portrait = H > W
    if "calibration" in cfg:
        s, ox, oy = cfg["calibration"]
        how = "config"
    elif portrait:
        s, (ox, oy), how = 1.0, (0.0, 0.0), "portrait page kept as printed"
    else:
        s, (ox, oy), how = calibrate(extract)
    sh = Sheet(extract, s, (ox, oy))
    sheet_w, sheet_h = (W, H) if portrait else (SHEET_W, SHEET_H)

    # ---------------------------------------------------------- lettering
    sh.D["chars"] = dedupe_chars([dict(c, size=0.0) if bad_char(c) else c for c in sh.D["chars"]])
    # (a reduced print's second-font copies of bold letters carry garbage sizes: a
    # stray character lettered a quarter inch tall or more is one of those)
    drop_fonts = tuple(cfg.get("drop_fonts", ()))
    runs = [r for r in sh.runs() if r["h"] < 1.2 and not
            (r["size"] > 0.25 and len(r["text"].strip()) <= 2 and (r.get("font") or "").startswith("*"))
            and not (drop_fonts and (r.get("font") or "").startswith(drop_fonts))]
    for r in runs:
        r["text"] = r["text"].replace("^", "°")
        n = max(1, len(r["text"]))
        L = math.dist((r["x"], r["y"]), r["end"])
        if n >= 3 and r["h"] > 1.8 * L / n:
            r["h"] = 1.15 * L / n
        if r["h"] < 0.04:
            r["h"] = 0.04
    light = [r for r in runs if (r.get("color") or 0) >= 0.5]
    if len(light) > 0.5 * len(runs):
        light = []
    runs = [r for r in runs if r not in light]

    # ---------------------------------------------------------- linework
    paths = sh.paths()
    seen = set()
    for p in paths:
        p["dest"] = None
        p["bbox"] = bbox_of(p["pts"])
        white_stroke = (p.get("stroke_color") or 0) >= 0.95
        if (not p["stroke"] or white_stroke) and not p["fill"]:
            p["dest"] = "drop:mask"
            continue
        # bold linework is printed twice over itself: one copy stays (a leader drawn
        # twice has no free end to follow)
        key = (p["lw"], p["dash"], p["fill"], tuple((round(x, 3), round(y, 3)) for x, y in p["pts"]))
        if key in seen:
            p["dest"] = "drop:dup"
        seen.add(key)

    # ---------------------------------------------------------- glyph outlines
    owner = match_glyphs(runs, paths)
    pgrid = Grid(0.5)
    for p in paths:
        if extent(p["pts"]) < 0.9:
            pgrid.add(p, p["bbox"])
    moved = []
    for r in runs:
        if r.get("split") and r["strokes"] < max(1, len(r["text"].replace(" ", "")) // 3):
            mine = owner.get(r["id"], [])
            for p in mine:
                p["dest"] = None
            if reanchor(r, paths, pgrid):
                moved.append(r)
            else:
                for p in mine:
                    p["dest"] = "drop:glyph"
    if moved:
        match_glyphs(moved, paths)
    # MicroStation sizes text by its capital height, and prints the lettering as
    # filled outlines over the text layer: where a sheet's lettering is outlined, the
    # size is the cap height.  A sheet without outlines (a summary of quantities made
    # from a spreadsheet) carries ordinary PDF font sizes, the em, so the cap height
    # is about 0.72 of it.
    lettered = [r for r in runs if len(r["text"].strip()) >= 2]
    native = lettered and sum(1 for r in lettered if r.get("strokes", 0) > 0) >= 0.5 * len(lettered)
    cap = 1.0 if native else CAP_EM
    for r in runs:
        r["h"] = snap_h(cap * r["size"])
        r["kind"] = None
        r["center"] = run_center(r)

    # ---------------------------------------------------------- border and title block
    def has_line(a, b, tol=0.04):
        for p in paths:
            if len(p["pts"]) < 2 or extent(p["pts"]) < 0.3:
                continue
            for u, v in zip(p["pts"], p["pts"][1:]):
                if poly_dist(a, [u, v]) < tol and poly_dist(b, [u, v]) < tol:
                    return True
        return False
    std = (not portrait) and has_line((TB[0], TB[1]), (TB[2], TB[1])) and \
        has_line((TB[0], TB[1]), (TB[0], TB[3]))
    template = bool(cfg.get("template", std))
    title_box = template and (has_line((TITLE_BOX[0], TITLE_BOX[1]), (TITLE_BOX[0], TITLE_BOX[3]), 0.08) or
                              has_line((TITLE_BOX[0] + 0.055, TITLE_BOX[1]), (TITLE_BOX[0] + 0.055, TITLE_BOX[3]), 0.08))
    frame = FRAME if not portrait else (0.0, 0.0, W, H)

    def outside(x, y):
        return not (frame[0] + .02 < x < frame[2] - .02 and frame[1] + .02 < y < frame[3] - .02)

    def in_title(x, y):
        if outside(x, y):
            return True
        if x > TB[0] - 0.05 and y > TB[1] - 0.05:
            return True
        return title_box and x > TITLE_BOX[0] - 0.05 and y < TITLE_BOX[3] + 0.05

    for r in runs:
        if template and in_title(*r["center"]):
            r["kind"] = "title"
    chars = [c for c in sh.D["chars"] if c["size"] > 0.01]
    for c in chars:
        c["x"], c["y"] = sh.P((c["x"], c["y"]))
        c["size"], c["adv"] = c["size"] / sh.s, c["adv"] / sh.s
    fields = title_fields(runs, title_box, chars) if template else {}
    if not template:
        # the border is kept as drawn, but the block's values are still read
        tb = (W - 2.25, H - 0.9, W - 0.25, H - 0.5) if portrait else TB
        fields = {k: v for k, v in title_fields(runs, False, chars, tb).items()
                  if k in ("project", "sheet_number", "state", "nps_pmis", "nps_drawing",
                           "date_plotted", "dgn_file", "description")}
    fields.update(cfg.get("fields", {}))
    fam = cfg.get("family") or family_of(rel, fields)

    def through_plan(pts):
        mids = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:])]
        return any(not in_title(x, y) for x, y in mids)
    for p in paths:
        if p["dest"] is not None:
            continue
        inside_tb = (all(in_title(x, y) for x, y in p["pts"]) and not through_plan(p["pts"])) or \
            (any(in_title(x, y) for x, y in p["pts"]) and extent(p["pts"]) < 0.5)
        if template and inside_tb:
            p["dest"] = "title"
        elif not template and all(outside(x, y) for x, y in p["pts"]):
            p["dest"] = "sheet:line"

    # ---------------------------------------------------------- regions
    regions = [tuple(b) for b in cfg.get("sheet_regions", [])]
    divider = profile_divider(paths) if fam in ("plan-profile", "drainage", "approach", "wall") else None
    if divider and "plan_rect" not in cfg:
        regions.append((frame[0], frame[1], frame[2], divider))
    plan_rect = tuple(cfg.get("plan_rect") or ((frame[0], divider, frame[2], frame[3]) if divider else frame))

    def in_regions(pts):
        return any(all(b[0] <= x <= b[2] and b[1] <= y <= b[3] for x, y in pts) for b in regions)

    # ---------------------------------------------------------- match lines
    mruns = [r for r in runs if r["kind"] is None and
             (MATCH.match(r["text"]) or r["text"].strip().upper() in ("MATCH", "MATCHLINE"))]
    for r in mruns:
        r["kind"] = "match"
    for p in paths:
        if p["dest"] is not None or p["lw"] < 0.9 or p["dash"] or len(p["pts"]) > 3:
            continue
        a, b = p["pts"][0], p["pts"][-1]
        if math.dist(a, b) < 0.15:
            continue
        for r in mruns:
            d, t = alignfit.dist_seg(r["center"], a, b)
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if d < 0.45 and abs(((ang - r["rot"]) + 90) % 180 - 90) < 4:
                p["dest"] = "sheet:match"
                break

    # ---------------------------------------------------------- callouts
    callouts = []
    rid = {r["id"]: r for r in runs}
    # leaders are the thin pens; a bold note's underline (its landing) is heavier
    live = [p for p in paths if p["dest"] is None]
    thin = [p for p in live if p["lw"] <= 0.8 and not p["dash"] and not p["fill"]]
    others = [p for p in paths if p["dest"] in (None, "sheet:match", "title", "sheet:line")]
    taken = set()
    alnum = lambda t: sum(ch.isalnum() for ch in t)
    cands = [r for r in runs if r["kind"] is None and alnum(r["text"]) >= 2 and
             not WIDTH.match(r["text"]) and not NUMBER.match(r["text"]) and
             not PLUS.match(r["text"]) and not re.match(r"^[\d.]+\s*%$", r["text"].strip()) and
             not re.match(r"^\d+\s*[-–]\s*\d+$", r["text"].strip())]
    tgrid, ogrid, vgrid = Grid(0.25), Grid(0.5), Grid(0.5)
    for p in thin:
        vgrid.add(p, p["bbox"])
        for q in p["pts"]:
            tgrid.add(p, (q[0], q[1], q[0], q[1]))
    for o in others:
        ogrid.add(o, o["bbox"])

    class Live:
        def __init__(self, g):
            self.g = g

        def near(self, bbox, pad=0.0):
            return [p for p in self.g.near(bbox, pad) if p["id"] not in taken]

    def free_end(pt, comp_ids):
        for o in ogrid.near((pt[0], pt[1], pt[0], pt[1]), 0.012):
            if o["id"] in comp_ids or o["dest"] in ("drop:glyph",):
                continue
            if poly_dist(pt, o["pts"]) < 0.012:
                return False
        return True

    for r in cands:
        rb = (min(r["x"], r["end"][0]), min(r["y"], r["end"][1]), max(r["x"], r["end"][0]), max(r["y"], r["end"][1]))
        local = [t for t in vgrid.near(rb, 3.0) if t["id"] not in taken]
        for land, leg in landings(r, local):
            # WFL draws the landing and the leader as separate strokes: the thin pens
            # are passed so one does not count as linework the other runs into
            comp = component(land, leg, thin, [], thin_grid=Live(tgrid), other_grid=ogrid)
            if sum(plen(p["pts"]) for p in comp) > 25:
                continue
            if len(comp) == 1 and len(comp[0]["pts"]) == 2:
                continue                 # a bare underline (a table's blank), not a leader
            mid = ((r["x"] + r["end"][0]) / 2, (r["y"] + r["end"][1]) / 2)
            text_end, tips, deco = ends_of(comp, leg, mid)
            if not tips:
                continue
            if not free_end(text_end, {p["id"] for p in comp}):
                continue
            for p in comp:
                taken.add(p["id"])
                p["dest"] = "sheet:squiggle" if p["id"] in deco else "drop:leader"
            r["kind"] = "callout-head"
            callouts.append({"run": r["id"], "landing": [list(leg[0]), list(leg[1])],
                             "text_end": list(text_end), "tips": [list(t) for t in tips],
                             "paths": [p["id"] for p in comp], "deco": deco})
            break
    free = lambda r: (r["kind"] is None and not WIDTH.match(r["text"]) and
                      not NUMBER.match(r["text"]) and not PLUS.match(r["text"]))
    for c in callouts:
        r0 = rid[c["run"]]
        keep = [r0]
        for direction in (1, -1):
            last = r0
            while True:
                nxt = None
                for r in runs:
                    if r in keep or not free(r) or abs(r["rot"] - r0["rot"]) > 1 or abs(r0["rot"]) > 1:
                        continue
                    if abs(r["h"] - r0["h"]) > 0.25 * r0["h"]:
                        continue
                    # the lines of one block sit at the engine's line spacing (1.6 h);
                    # a wider gap (past an underline) starts a separate note, kept
                    # as text where it is lettered
                    dy = (last["y"] - r["y"]) * direction
                    if not 1.2 * last["h"] < dy < last["h"] * 2.0 + 0.02:
                        continue
                    dx = r["x"] - r0["x"]
                    if abs(dx) < 0.06 or (direction == 1 and -0.06 < dx < 1.0):
                        nxt = r
                        break
                if nxt is None:
                    break
                keep.append(nxt)
                nxt["kind"] = "callout"
                last = nxt
        r0["kind"] = "callout"
        keep.sort(key=lambda r: -r["y"])
        c["lines"] = [r["id"] for r in keep]
        c["text"] = "\n".join(r["text"] for r in keep)
    allg = Grid(0.5)
    for p in paths:
        if p["dest"] is None and extent(p["pts"]) <= 0.16:
            allg.add(p, p["bbox"])
    for c in callouts:
        c["arrow"] = False
        for t in c["tips"]:
            for p in allg.near((t[0], t[1], t[0], t[1]), 0.2):
                if p["dest"] is not None or extent(p["pts"]) > 0.16 or len(p["pts"]) < 3:
                    continue
                if (closed(p) or p["fill"]) and extent(p["pts"]) > 0.03 and \
                        any(math.dist(q, t) < 0.03 for q in p["pts"]):
                    p["dest"] = "drop:arrowhead"
                    c["arrow"] = True
                elif not closed(p) and extent(p["pts"]) < 0.09 and \
                        min(math.dist(p["pts"][0], t), math.dist(p["pts"][-1], t)) < 0.006:
                    p["dest"] = "sheet:squiggle"

    # ---------------------------------------------------------- scale and kind
    fpi = cfg.get("fpi")
    bar = scale_bar(runs)
    if fpi is None:
        fpi = bar
    kind = cfg.get("kind")
    aligns, twist = [], cfg.get("twist")
    twist_how = "config" if twist is not None else None
    heavy = [p for p in paths if p["dest"] is None and not p["fill"] and not in_regions(p["pts"])
             and p["lw"] >= 1.2 and not p["dash"] and plen(p["pts"]) > 0.3]
    segs = [(p["pts"][0], p["pts"][-1]) for p in paths
            if p["dest"] is None and len(p["pts"]) == 2 and
            0.06 < math.dist(p["pts"][0], p["pts"][-1]) < 0.3 and not in_regions(p["pts"])]
    free_runs = [r for r in runs if r["kind"] is None and not in_regions([r["center"]])]
    name_runs = [r for r in runs if r["kind"] in (None, "callout", "callout-head") and
                 not in_regions([r["center"]]) and NAME.match(r["text"].strip())]
    if kind != "sheet" and not cfg.get("no_alignments") and heavy:
        if fpi:
            aligns = fit(heavy, segs, free_runs, fpi, names=name_runs)
        else:
            fpi, aligns = fit_any_scale(heavy, segs, free_runs, SCALES, names=name_runs)
        if aligns:
            aligns, dupes = alignfit.tidy(aligns, fpi)
            dup_ids = {pid for al in dupes for pid in al["paths"]}
            for p in paths:
                if p["id"] in dup_ids and p["dest"] is None:
                    p["dest"] = "drop:centerline"
    if kind is None:
        kind = "plan" if (fpi and (aligns or bar) and fam in PLAN_FAMILIES) else "sheet"
    if kind == "plan" and not fpi:
        fpi = 50.0

    # ---------------------------------------------------------- plan view
    if kind == "plan":
        if twist is None and aligns:
            twist = alignfit.twist_from_bearings(aligns, free_runs)
            twist_how = "bearing" if twist is not None else None
        if twist is None:
            twist, twist_how = 0.0, "none"
        used = set()
        for k, al in enumerate(aligns):
            if not al["name"]:
                al["name"] = f"CL{k + 1}"
            used.update(al["paths"])
            for rid_ in al["labels"]:
                if rid_ and rid[rid_]["kind"] is None:
                    rid[rid_]["kind"] = "station"
            for along, m, L in al["ticks"]:
                for p in pgrid.near((m[0], m[1], m[0], m[1]), 0.05):
                    if p["dest"] is None and len(p["pts"]) == 2 and \
                            min(math.dist(p["pts"][0], m), math.dist(p["pts"][-1], m)) < 0.015:
                        p["dest"] = "drop:tick"
        for p in paths:
            if p["id"] in used:
                p["dest"] = "drop:centerline"
        for r in runs:
            if r["kind"] is not None:
                continue
            t = r["text"].strip()
            if NAME.match(t) or alignfit.BEARING.search(t.replace(" ", "")):
                if any(al["chain"].locate(r["center"])[0] < 1.0 for al in aligns):
                    r["kind"] = "align-text"
        mark_symbols(paths, runs)
        for p in paths:
            if p["dest"] is not None:
                continue
            if in_regions(p["pts"]):
                p["dest"] = "sheet:line"
            elif is_existing(p):
                p["dest"] = "sur"
            elif fam == "drainage" and p["lw"] >= 1.2 and not p["dash"]:
                p["dest"] = "hyd"
            else:
                p["dest"] = "cor"
        # small symbols ride with the line they sit on
        longp = [p for p in paths if p["dest"] in ("cor", "hyd", "sur") and plen(p["pts"]) >= 0.25]
        lgrid = Grid(0.5)
        for q in longp:
            lgrid.add(q, q["bbox"])
        for p in paths:
            if p["dest"] not in ("cor", "hyd") or plen(p["pts"]) >= 0.25:
                continue
            c = centroid(p["pts"])
            best, bd = None, 0.12
            for q in lgrid.near((c[0], c[1], c[0], c[1]), 0.12):
                d = poly_dist(c, q["pts"])
                if d < bd:
                    best, bd = q, d
            if best is not None:
                p["dest"] = best["dest"]
                p["symbol_of"] = best["id"]
        dashed = [p for p in paths if p["dest"] == "sur"]
        dgrid = Grid(0.5)
        for p in dashed:
            dgrid.add(p, p["bbox"])
        for r in runs:
            if r["kind"] is not None or in_regions([r["center"]]):
                continue
            t = r["text"].strip()
            if t in ("R/W", "r/w", "C/L", "CL"):
                r["kind"] = "design-label"
            elif NUMBER.match(t) and len(t) >= 3 and any(
                    poly_dist(r["center"], p["pts"]) < 0.25
                    for p in dgrid.near((r["center"][0], r["center"][1]) * 2, 0.25)):
                r["kind"] = "topo-label"
    else:
        for p in paths:
            if p["dest"] is None:
                p["dest"] = "sheet:line"
        twist, twist_how = 0.0, "none"
    for r in runs:
        if r["kind"] is None:
            r["kind"] = "text"
    for r in light:
        r["kind"] = "light"
        r["center"] = run_center(r)
    runs += light

    return {"id": sheet_id, "rel": rel, "family": fam, "kind": kind, "fpi": fpi,
            "twist": twist, "twist_how": twist_how, "calibration": [s, ox, oy], "calibration_how": how,
            "portrait": portrait, "sheet_size": [sheet_w, sheet_h], "page_in": [W, H],
            "template": template, "title_box": bool(title_box), "fields": fields,
            "plan_rect": list(plan_rect), "profile_divider": divider, "regions": [list(b) for b in regions],
            "text_mode": "layer", "text_native": bool(native), "runs": runs, "paths": paths,
            "callouts": callouts,
            "aligns": [dict({k: v for k, v in al.items() if k != "chain"}, length=al["chain"].length())
                       for al in aligns],
            "counts": dict(Counter(str(p["dest"]) for p in paths)),
            "text_counts": dict(Counter(r["kind"] for r in runs))}
