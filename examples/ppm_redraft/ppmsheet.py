"""Digitise any PPM example sheet into what each file of its redraft owns.

The generic counterpart of digitize_l4.py: the same steps, driven by rules and a small
per-sheet config instead of sheet-specific lists.

    digitise(ppm_id, rel, extract, cfg) -> dict (JSON-able)

Config keys (all optional; see configs/README.md):
    kind, family, fpi, twist, calibration, template, sheet_regions, text_mode,
    no_alignments, lw_scale, fields, char_map, skip/reason
"""
import math
import re
from collections import Counter

import alignfit
import traced
from calibrate import calibrate
from leaders import landings, component, ends_of, poly_dist, closed, plen
from sheetgeom import Sheet, run_box, in_box, extent, Grid, bbox_of, box_bbox

BORDER = (1.904, 0.503, 33.497, 21.497)
TB = (27.698, 18.498, 33.497, 21.497)            # title block box (template)
WIDTH = re.compile(r"^\d{1,2}(\.\d+)?['’]$")
PLUS = re.compile(r"^\+\d+(\.\d+)?$")
NUMBER = re.compile(r"^\d{1,4}$")
SCALE = re.compile(r"SCALE\W*1\W*=\W*(\d+)", re.I)
MATCH = re.compile(r"^MATCH\s*LINE", re.I)
SHEET_ID = re.compile(r"^[A-Z]{1,4}\s?-\s?(\d{1,3}[A-Za-z]?|XX?X?)$")    # "SE-XX" on generic sheets
HEIGHTS = (0.08, 0.10, 0.12, 0.14, 0.175, 0.20, 0.25, 0.29, 0.35, 0.50)

PLAN_FAMILIES = {"layout", "drainage", "utility", "stage", "delineation", "electrical",
                 "planting", "signs"}

# The drafting font's fractions and symbols sit at Windows-1252 code points in the text
# layer.  Fractions are remapped where they follow a digit or a space; symbols always.
FRACTIONS = {"†": "½", "‡": "¼", "…": "¾", "–": "⅜", "ƒ": "⅝", "⁄": "⅞", "—": "⅛",
             "›": "3/16", "−": "5/16", "‰": "½"}
SYMBOLS = {"Ñ": "∠", "¨": "±", "�": "℄"}


def family_of(rel):
    n = rel.split("/")[-1].lower()
    sec = rel.split("/")[0]
    if "2-2.02" in sec:
        return "title"
    if "2-2.03" in sec:
        return "sections"
    if "2-2.04" in sec:
        return "orientation"
    if "2-2.05" in sec:
        if "profile" in n or "superelevation" in n:
            return "profile"
        return "layout"
    if "2-2.06" in sec:
        return "details"
    if "2-2.08" in sec:
        return "erosion"
    if "2-2.10" in sec:
        if "-dp-" in n:
            return "profile"
        if "-dd-" in n:
            return "details"
        if "-dq-" in n:
            return "quantities"
        return "drainage"
    if "2-2.13" in sec:
        return "profile" if "profile" in n else "utility"
    if "2-2.18" in sec:
        if "-sq-" in n or "quantities" in n:
            return "quantities"
        return "details"
    if "2-2.14" in sec or "2-2.15" in sec:
        return "signs"
    if "2-2.16" in sec:
        return "quantities" if "quantities" in n else "stage"
    if "2-2.17" in sec:
        if "quantities" in n or "pdq" in n:
            return "quantities"
        if "detail" in n:
            return "details"
        return "delineation"
    if "2-2.19" in sec:
        return "quantities"
    if "2-2.22" in sec:
        return "planting"
    if "2-2.23" in sec:
        return "electrical"
    return "other"


def snap_h(h):
    return min(HEIGHTS, key=lambda v: abs(v - h))


def is_dotted(p):
    """Caltrans draws existing features dotted: short dashes, longer gaps."""
    d = p["dash"]
    if not d or len(d) < 2:
        return False
    dashes, gaps = d[0::2], d[1::2]
    return max(dashes) <= 2.0 and min(gaps) >= 1.3 * max(dashes) * 0.9 and dashes[0] <= 1.2


def centroid(pts):
    return (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))


def run_center(r):
    a = math.radians(r["rot"])
    L = math.dist((r["x"], r["y"]), r["end"])
    return (r["x"] + math.cos(a) * L / 2 - math.sin(a) * r["h"] / 2,
            r["y"] + math.sin(a) * L / 2 + math.cos(a) * r["h"] / 2)


def remap(text, extra=None):
    out = []
    for i, ch in enumerate(text):
        if extra and ch in extra:
            out.append(extra[ch]); continue
        if ch in SYMBOLS:
            out.append(SYMBOLS[ch]); continue
        if ch in FRACTIONS:
            prev = text[i - 1] if i else " "
            nxt = text[i + 1] if i + 1 < len(text) else " "
            if prev.isdigit() or prev == " " or nxt in "\"'’” " or i == 0:
                out.append(FRACTIONS[ch]); continue
        out.append(ch)
    return "".join(out)


def bad_char(c):
    return c["adv"] > 2.0 or c["size"] > 2.0 or not (-1 < c["x"] < 40 and -1 < c["y"] < 30)


# ------------------------------------------------------------- broken text
def broken_groups(sheet):
    """Text-layer strings whose matrices are corrupt: [(text, origin)].  Only a string's
    first character keeps a usable position, so each usable position starts a string."""
    groups, cur = [], None
    for c in sheet.D["chars"]:
        if not bad_char(c):
            cur = None
            continue
        valid = -1 < c["x"] < 40 and -1 < c["y"] < 30
        if cur is None or valid:
            cur = [c]
            groups.append(cur)
        else:
            cur.append(c)
    res = []
    for g in groups:
        t = "".join(c["t"] for c in g).strip()
        o = g[0]
        if t and -1 < o["x"] < 40 and -1 < o["y"] < 30:
            res.append((t, sheet.P((o["x"], o["y"]))))
    return res


def recover_broken(groups, leftovers):
    """Rotation, size and extent of each broken string from its own glyph strokes."""
    runs = []
    grid = Grid(0.25)
    glyphish = [p for p in leftovers if extent(p["pts"]) < 0.2 and not p["dash"]]
    for p in glyphish:
        p["_c"] = centroid(p["pts"])
        grid.add(p, (p["_c"][0], p["_c"][1], p["_c"][0], p["_c"][1]))
    claimed = set()
    for k, (text, o) in enumerate(groups):
        n = len(text)
        near = [p for p in grid.near((o[0], o[1], o[0], o[1]), 0.25)
                if id(p) not in claimed and min(math.dist(q, o) for q in p["pts"]) < 0.15]
        if not near:
            continue
        cluster = list(near)
        inside = {id(p) for p in cluster}
        limit = 0.13 * n + 0.2
        frontier = list(cluster)
        while frontier:
            q = frontier.pop()
            for p in grid.near((q["_c"][0], q["_c"][1], q["_c"][0], q["_c"][1]), 0.12):
                if id(p) in inside or id(p) in claimed or math.dist(p["_c"], o) > limit:
                    continue
                if math.dist(p["_c"], q["_c"]) < 0.12:
                    inside.add(id(p)); cluster.append(p); frontier.append(p)
        pts = [q for p in cluster for q in p["pts"]]
        ang = 0.0
        if n >= 3:
            mx, my = centroid(pts)
            sxx = sum((x - mx) ** 2 for x, _ in pts); syy = sum((y - my) ** 2 for _, y in pts)
            sxy = sum((x - mx) * (y - my) for x, y in pts)
            ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
            if (mx - o[0]) * math.cos(ang) + (my - o[1]) * math.sin(ang) < 0:
                ang += math.pi
            if abs(math.degrees(ang)) < 3:
                ang = 0.0
        ca, sa = math.cos(ang), math.sin(ang)
        al = [(x - o[0]) * ca + (y - o[1]) * sa for x, y in pts]
        ac = [-(x - o[0]) * sa + (y - o[1]) * ca for x, y in pts]
        L = max(al)
        h = L / (n * 0.95) if n > 1 else max(ac) - max(min(ac), -0.02)
        if n == 1 and not 0.07 <= h <= 0.22:
            h = 0.14
        if not 0.07 <= h <= 0.35 or L <= 0:
            continue                        # leave the strokes as drawn
        for p in cluster:
            claimed.add(id(p))
        runs.append({"id": f"b{k}", "text": text, "x": o[0], "y": o[1], "rot": math.degrees(ang),
                     "size": h / 1.12, "h": snap_h(h), "end": (o[0] + max(L, 0.06) * ca, o[1] + max(L, 0.06) * sa),
                     "broken": True, "split": False})
    return runs


# ------------------------------------------------------------- glyphs
def match_glyphs(runs, paths, extra_boxes=()):
    """Mark the text layer's drawn strokes (drop:glyph), and measure each run's height
    and length from the strokes it covers."""
    bgrid = Grid(0.5)
    for r in runs:
        b = run_box(r)
        bgrid.add((r, b), box_bbox(b))
    owner = {}
    for p in paths:
        if p["dest"] is not None:
            continue
        ext = extent(p["pts"])
        if ext > 0.9:
            continue
        for r, b in bgrid.near(p["bbox"]):
            if ext <= r["h"] * 1.5 and in_box(p["pts"], b):
                p["dest"] = "drop:glyph"
                owner.setdefault(r["id"], []).append(p)
                break
    for r in runs:
        got = owner.get(r["id"], [])
        r["strokes"] = len(got)
        if len(got) >= 2:
            a = math.radians(r["rot"]); ca, sa = math.cos(a), math.sin(a)
            tops = sorted(max(-(x - r["x"]) * sa + (y - r["y"]) * ca for x, y in p["pts"]) for p in got)
            al = [(x - r["x"]) * ca + (y - r["y"]) * sa for p in got for x, y in p["pts"]]
            # the cap height, past the odd stray stroke; hatched (filled) letters are
            # mostly short interior strokes, so read them nearer the top
            nchars = max(1, len(r["text"].replace(" ", "")))
            h = tops[int((0.97 if len(got) > 4 * nchars else 0.85) * (len(tops) - 1))]
            if 0.04 < h < 0.6:
                r["h_meas"] = h
            r["along"] = (min(al), max(al))
    return owner


def reanchor(r, paths, grid):
    """A piece of text that followed a run of spaces: slide it along its baseline onto
    the strokes that are really its letters."""
    a = math.radians(r["rot"]); ca, sa = math.cos(a), math.sin(a)
    L = math.dist((r["x"], r["y"]), r["end"])
    cand = []
    pad = 2.2
    bb = (min(r["x"], r["end"][0]) - pad, min(r["y"], r["end"][1]) - pad,
          max(r["x"], r["end"][0]) + pad, max(r["y"], r["end"][1]) + pad)
    for p in grid.near(bb):
        if p["dest"] is not None or extent(p["pts"]) > r["h"] * 1.5:
            continue
        al = [(x - r["x"]) * ca + (y - r["y"]) * sa for x, y in p["pts"]]
        ac = [-(x - r["x"]) * sa + (y - r["y"]) * ca for x, y in p["pts"]]
        if min(ac) > -0.35 * r["h"] and max(ac) < 1.35 * r["h"] and -0.6 < min(al) < 2.0:
            cand.append(min(al))
    if not cand:
        return False
    cand.sort()
    start = cand[0]
    if abs(start) < 0.03:
        return False
    r["x"] += start * ca; r["y"] += start * sa
    r["end"] = (r["x"] + L * ca, r["y"] + L * sa)
    return True


# ------------------------------------------------------------- title block
def join_lines(runs, gap=0.06):
    """Runs that sit on one baseline, joined in reading order."""
    used, out = set(), []
    for r in sorted(runs, key=lambda r: (round(r["rot"]), r["x"] if abs(r["rot"]) < 45 else r["y"])):
        if r["id"] in used:
            continue
        a = math.radians(r["rot"]); ca, sa = math.cos(a), math.sin(a)
        line = [r]; used.add(r["id"])
        grown = True
        while grown:
            grown = False
            last = line[-1]
            for q in runs:
                if q["id"] in used or abs(q["rot"] - r["rot"]) > 2:
                    continue
                across = -(q["x"] - r["x"]) * sa + (q["y"] - r["y"]) * ca
                along = (q["x"] - last["end"][0]) * ca + (q["y"] - last["end"][1]) * sa
                if abs(across) < 0.4 * r["h"] and -0.05 < along < 0.6:
                    line.append(q); used.add(q["id"]); grown = True
                    break
        text = line[0]["text"]
        for prev, q in zip(line, line[1:]):
            g = (q["x"] - prev["end"][0]) * ca + (q["y"] - prev["end"][1]) * sa
            text += ("" if g < gap else " ") + q["text"]
        out.append(dict(line[0], text=text, end=line[-1]["end"]))
    return out


def title_fields(runs):
    """Caltrans title block values by where the template puts them."""
    f = {}
    for r in runs:
        x, y = run_center(r)
        if x > 30.5 and 0.5 < y < 1.4 and abs(r["rot"]) < 1 and SHEET_ID.match(r["text"].strip()):
            f["sheet_id"] = r["text"].strip().replace(" ", "")
    cols = [("dist", 27.698, 28.199), ("county", 28.199, 29.198), ("route", 29.198, 30.338),
            ("post_miles", 30.338, 32.138), ("sheet_number", 32.138, 32.737),
            ("total_sheets", 32.737, 33.497)]
    # the grid's cells from the runs as lettered: joined first, "03" and "Pla" would
    # read as one county
    cells = {}
    for r in runs:
        x, y = run_center(r)
        if 20.71 < y < 21.16 and x > 27.4 and r["text"].strip():
            key = min(cols, key=lambda c: abs((c[1] + c[2]) / 2 - x))[0]
            cells.setdefault(key, []).append((-round(y, 2), x, r["text"].strip()))
    for key, vals in cells.items():
        f[key] = " ".join(t for _, _, t in sorted(vals))
    runs = join_lines(runs)
    title_lines = []
    for r in runs:
        x, y = run_center(r)
        t = r["text"].strip()
        if not t:
            continue
        if 20.71 < y < 21.16 and x > 27.4:
            continue
        elif x > 27.6 and 0.5 < y < 2.8 and abs(r["rot"]) < 1:
            u = t.upper()
            if u.startswith("SCALE") or u.startswith("NO SCALE"):
                f["scale"] = t
            elif SHEET_ID.match(t) and x > 30.5 and y < 1.3:
                f["sheet_id"] = t.replace(" ", "")
            elif r["h"] >= 0.15:
                m = re.match(r"^(.*\S)\s+([A-Z]{1,4}\s?-\s?(?:\d{1,3}[A-Za-z]?|XX?X?))$", t)
                if m and y < 1.6:
                    t = m.group(1)
                    f.setdefault("sheet_id", m.group(2).replace(" ", ""))
                title_lines.append((-r["y"], t))
        elif y < 0.503:
            if x < 5.7:
                f["border_revised"] = t
            elif x < 13.4:
                if t.upper().startswith("USERNAME"):
                    f["username"] = t
                elif t.upper().startswith("DGN"):
                    f["dgn_file"] = t
            elif 22.2 < x < 25.2:
                f["unit"] = (f.get("unit", "") + " " + t).strip()
            elif x > 25.2:
                f["project_number_phase"] = (f.get("project_number_phase", "") + "  " + t).strip()
        elif x > 33.497:
            u = t.upper()
            if u.startswith("DATE PLOTTED"):
                f["date_plotted"] = t
            elif u.startswith("TIME PLOTTED"):
                f["time_plotted"] = t
            elif re.match(r"^\d\d-\d\d-\d\d$", t):
                f["last_revision"] = t
    title_lines = [(k, t) for k, t in title_lines if sum(ch.isalnum() for ch in t) >= 3]
    if title_lines:
        f["sheet_title"] = "\n".join(t for _, t in sorted(title_lines))
    return f


# ------------------------------------------------------------- sheet symbols
def straight_run(p, min_len):
    """The polyline as one straight segment when it is straight, else None."""
    a, b = p["pts"][0], p["pts"][-1]
    if math.dist(a, b) < min_len:
        return None
    if all(poly_dist(q, [a, b]) < 0.01 for q in p["pts"][1:-1]):
        return a, b
    return None


def north_arrows(paths, pgrid):
    """North arrows: a small circle with a straight shaft (1.2 to 3.5 in) through its
    centre, free at both ends, and the hatching of a head or tail beside it.  Returns
    [(box, north direction degrees or None)]."""
    found = []
    for p in paths:
        if p["dest"] is not None or not closed(p):
            continue
        c = centroid(p["pts"])
        rad = max(math.dist(c, q) for q in p["pts"])
        if not 0.1 < rad < 0.25 or len(p["pts"]) < 20 or \
                rad - min(math.dist(c, q) for q in p["pts"]) > 0.25 * rad:
            continue                         # a circle, not a polygon (a manhole, a tag)
        for q in pgrid.near((c[0], c[1], c[0], c[1]), 0.02):
            if q is p or q["dest"] is not None or q["dash"]:
                continue
            seg = straight_run(q, 1.2)
            if not seg:      # a shaft drawn on into the head's outline: its longest leg
                legs = [(math.dist(u, v), (u, v)) for u, v in zip(q["pts"], q["pts"][1:])]
                seg = max(legs)[1] if legs and max(legs)[0] >= 1.2 else None
            if not seg or math.dist(*seg) > 3.5 or poly_dist(c, list(seg)) > 0.02:
                continue
            a, b = seg
            box = (min(a[0], b[0]) - 0.4, min(a[1], b[1]) - 0.4, max(a[0], b[0]) + 0.4, max(a[1], b[1]) + 0.4)

            # both ends free of other linework (a centerline runs on); the head's and
            # the feathers' own strokes, wholly inside the symbol, may touch them
            def free(e):
                return not any(o is not q and o["dest"] is None and o["lw"] >= 0.4 and
                               extent(o["pts"]) > 0.4 and poly_dist(e, o["pts"]) < 0.005 and
                               not all(box[0] <= x <= box[2] and box[1] <= y <= box[3] for x, y in o["pts"])
                               for o in pgrid.near((e[0], e[1], e[0], e[1]), 0.01))
            if not (free(a) and free(b)):
                continue
            # (stroked lettering found earlier may have taken a few of the head's strokes)
            members = [o for o in pgrid.near(box) if o["dest"] in (None, "sheet:glyph") and
                       all(poly_dist(pt, [a, b]) < 0.45 for pt in o["pts"])]
            hatch = [o for o in members if o is not q and o is not p and extent(o["pts"]) < 1.0
                     and not o["dash"]]
            if len(hatch) < 6:
                continue
            # the head is hatched with graded strokes (a triangle filled with lines);
            # the tail's feathers are all one length.  Failing that, the tail carries
            # more hatching.
            near_a = [o for o in hatch if math.dist(centroid(o["pts"]), a) < math.dist(centroid(o["pts"]), b)]
            near_b = [o for o in hatch if o not in near_a]
            ka = len({round(extent(o["pts"]) / 0.05) for o in near_a})
            kb = len({round(extent(o["pts"]) / 0.05) for o in near_b})
            # an arrow is hatched at both ends, its head graded (a tree's circle with a
            # leader to its centre has strokes round it too, but not this)
            if min(len(near_a), len(near_b)) < 3 or max(ka, kb) < 4:
                continue
            if ka != kb:
                tip = a if ka > kb else b
            else:
                tip = b if len(near_a) > len(near_b) else a
            tail = a if tip is b else b
            north = math.degrees(math.atan2(tip[1] - tail[1], tip[0] - tail[0])) \
                if (ka != kb or len(near_a) != len(near_b)) else None
            found.append((len(hatch), box, north, members))
            break
    if not found:
        return []
    # one north arrow to a sheet: the most hatched
    _, box, north, members = max(found, key=lambda f: f[0])
    for o in members:
        o["dest"] = "sheet:north"
    return [(box, north)]


def mark_symbols(paths, runs):
    """On a plan sheet, keep the sheet's own symbols on the sheet: tags (a circle,
    oval or hexagon round a short label, and the leader off it), the north arrow,
    direction-of-travel arrows, and the little arcs that lead a width to its line."""
    rgrid = Grid(0.5)
    for r in runs:
        if r["kind"] is None:
            rgrid.add(r, (r["center"][0], r["center"][1], r["center"][0], r["center"][1]))
    pgrid = Grid(0.5)
    for p in paths:
        if p["dest"] in (None, "sheet:glyph"):
            pgrid.add(p, p["bbox"])
    arrows = north_arrows(paths, pgrid)
    for p in paths:
        if p["dest"] is not None or not closed(p):
            continue
        x0, y0, x1, y1 = p["bbox"]
        w, h = x1 - x0, y1 - y0
        if not (0.12 < max(w, h) < 1.0 and min(w, h) > 0.1):
            continue
        inside = [r for r in rgrid.near(p["bbox"])
                  if r["kind"] is None and len(r["text"].strip()) <= 7 and
                  x0 + 0.05 * w < r["center"][0] < x1 - 0.05 * w and y0 + 0.05 * h < r["center"][1] < y1 - 0.05 * h]
        if inside and all(r["h"] < h for r in inside):
            p["dest"] = "sheet:tag"
            for r in inside:
                r["kind"] = "tag"
            for q in pgrid.near(p["bbox"], 0.05):
                if q["dest"] is None and q["lw"] <= 0.6 and not q["dash"] and len(q["pts"]) <= 3 and \
                        any(poly_dist(e, p["pts"]) < 0.02 for e in (q["pts"][0], q["pts"][-1])):
                    q["dest"] = "sheet:tag"
    for p in paths:
        if p["dest"] is None and 0.8 <= p["lw"] <= 1.1 and not p["dash"] and 6 <= len(p["pts"]) <= 9 \
                and math.dist(p["pts"][0], p["pts"][-1]) < 0.01 and 0.15 < extent(p["pts"]) < 0.5:
            p["dest"] = "sheet:arrow"
    wgrid = Grid(0.5)
    for r in runs:
        if r["kind"] is None and WIDTH.match(r["text"]):
            wgrid.add(r, (r["center"][0], r["center"][1], r["center"][0], r["center"][1]))
    for p in paths:
        if p["dest"] is None and p["lw"] <= 0.6 and not p["dash"] and not closed(p) and \
                extent(p["pts"]) < 0.3 and len(p["pts"]) > 3:
            c = centroid(p["pts"])
            if any(math.dist(c, r["center"]) < 0.3 for r in wgrid.near((c[0], c[1], c[0], c[1]), 0.3)):
                p["dest"] = "sheet:line"
    return arrows


def clusters(paths, gap):
    """Paths grouped where their boxes come within gap of each other."""
    g = Grid(0.3)
    for p in paths:
        g.add(p, p["bbox"])
    seen, out = set(), []
    for p in paths:
        if id(p) in seen:
            continue
        group, frontier = [p], [p]
        seen.add(id(p))
        while frontier:
            q = frontier.pop()
            qb = q["bbox"]
            for o in g.near(qb, gap):
                if id(o) in seen:
                    continue
                ob = o["bbox"]
                if max(ob[0], qb[0]) - min(ob[2], qb[2]) < gap and max(ob[1], qb[1]) - min(ob[3], qb[3]) < gap:
                    seen.add(id(o)); group.append(o); frontier.append(o)
        out.append(group)
    return out


def stroke_lettering(paths):
    """Lettering drawn as strokes, found without a text layer: clusters of small solid
    strokes, each about a letter in size, lined up in a short band."""
    small = [p for p in paths if p["dest"] is None and not p["dash"] and extent(p["pts"]) < 0.22
             and 0.3 <= p["lw"] <= 1.6]
    g = Grid(0.2)
    for p in small:
        g.add(p, p["bbox"])
    seen = set()
    for p in small:
        if id(p) in seen:
            continue
        cluster, frontier = [p], [p]
        seen.add(id(p))
        while frontier:
            q = frontier.pop()
            for o in g.near(q["bbox"], 0.07):
                if id(o) in seen:
                    continue
                bx = o["bbox"]; qb = q["bbox"]
                gapx = max(0.0, max(bx[0], qb[0]) - min(bx[2], qb[2]))
                gapy = max(0.0, max(bx[1], qb[1]) - min(bx[3], qb[3]))
                if gapx < 0.07 and gapy < 0.07:
                    seen.add(id(o)); cluster.append(o); frontier.append(o)
        if len(cluster) < 3:
            continue
        x0 = min(o["bbox"][0] for o in cluster); y0 = min(o["bbox"][1] for o in cluster)
        x1 = max(o["bbox"][2] for o in cluster); y1 = max(o["bbox"][3] for o in cluster)
        thin_side, long_side = sorted((x1 - x0, y1 - y0))
        # a word or a line of lettering: a band no taller than a letter or two
        if thin_side < 0.35 and long_side >= 0.12 and long_side / max(thin_side, 0.05) >= 1.2:
            for o in cluster:
                o["dest"] = "sheet:glyph"


# ------------------------------------------------------------- main
def digitise(ppm_id, rel, extract, cfg):
    cfg = dict(cfg or {})
    fam = cfg.get("family") or family_of(rel)
    if "calibration" in cfg:
        s, ox, oy = cfg["calibration"]
        how = "config"
    else:
        s, (ox, oy), how = calibrate(extract)
    sh = Sheet(extract, s, (ox, oy))
    text_mode = cfg.get("text_mode", "layer")

    # ---------------------------------------------------------- lettering
    sh.D["chars"] = [dict(c, size=0.0) if bad_char(c) else c for c in sh.D["chars"]]
    runs = [r for r in sh.runs() if r["h"] < 1.2]
    extra_map = cfg.get("char_map")
    for r in runs:
        r["text"] = remap(r["text"].replace("^", "°"), extra_map)
        n = max(1, len(r["text"]))
        L = math.dist((r["x"], r["y"]), r["end"])
        if n >= 3 and r["h"] > 1.8 * L / n:          # a lopsided matrix: trust the advance
            r["h"] = 1.15 * L / n
        if r["h"] < 0.04:                             # tiny but readable: measured below
            r["h"] = 0.04
    light = [r for r in runs if (r.get("color") or 0) >= 0.5]
    if len(light) > 0.5 * len(runs):
        light = []                    # a white-filled text layer over stroked lettering
    runs = [r for r in runs if r not in light]

    # ---------------------------------------------------------- linework
    lw_scale = cfg.get("lw_scale")
    paths = sh.paths()
    if lw_scale is None:
        lws = sorted(p["lw"] for p in paths if p["stroke"] and p["lw"] > 0)
        med = lws[len(lws) // 2] if lws else 1.0
        lw_scale = 1.0
        if med > 3.0:
            # widths written in device units (4, 10, 14, 18): the thinnest common width
            # is the thin pen
            thin = min(w for w in set(lws) if lws.count(w) >= 0.05 * len(lws))
            lw_scale = 0.4 / thin
    for p in paths:
        p["dest"] = None
        p["bbox"] = bbox_of(p["pts"])
        if lw_scale != 1.0:
            p["lw"] = round(p["lw"] * lw_scale, 3)
            if p["dash"]:
                p["dash"] = tuple(round(v * lw_scale, 3) for v in p["dash"])
        white_stroke = (p.get("stroke_color") or 0) >= 0.95
        if (not p["stroke"] or white_stroke) and not p["fill"]:
            p["dest"] = "drop:mask"          # white masks and invisible paths

    # ---------------------------------------------------------- glyph strokes
    owner = match_glyphs(runs, paths)
    pgrid = Grid(0.5)
    for p in paths:
        if extent(p["pts"]) < 0.9:
            pgrid.add(p, p["bbox"])
    moved = []
    for r in runs:
        if r.get("split") and r["strokes"] < max(1, len(r["text"].replace(" ", "")) // 3):
            mine = owner.get(r["id"], [])
            for p in mine:                   # free its strokes while it looks for its letters
                p["dest"] = None
            if reanchor(r, paths, pgrid):
                moved.append(r)
            else:
                for p in mine:
                    p["dest"] = "drop:glyph"
    if moved:
        match_glyphs(moved, paths)          # only the runs that moved: the rest keep theirs
    # text-layer characters with nothing drawn under them are invisible: drop them
    backed = [r for r in runs if len(r["text"].strip()) >= 2]
    stroke_backed = backed and sum(1 for r in backed if r["strokes"] > 0) >= 0.6 * len(backed)
    invisible = [r for r in runs if stroke_backed and r["strokes"] == 0]
    runs = [r for r in runs if not (stroke_backed and r["strokes"] == 0)]
    for r in runs:
        if r.get("h_meas"):
            r["h"] = snap_h(r["h_meas"])
    if text_mode == "layer":
        leftovers = [p for p in paths if p["dest"] is None and not p["fill"] and extent(p["pts"]) < 0.3]
        rec = recover_broken(broken_groups(sh), leftovers)
        match_glyphs(rec, paths)
        runs += [r for r in rec if r["strokes"] > 0]

    # ---------------------------------------------------------- border and title block
    def has_line(a, b, tol=0.03):
        for p in pgrid.near((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])), tol) + \
                [p for p in paths if extent(p["pts"]) >= 0.9]:
            if len(p["pts"]) < 2:
                continue
            for u, v in zip(p["pts"], p["pts"][1:]):
                if poly_dist(a, [u, v]) < tol and poly_dist(b, [u, v]) < tol:
                    return True
        return False
    std = has_line((TB[0], TB[1]), (TB[0], TB[3])) or has_line((TB[0], TB[1]), (TB[2], TB[1]))
    template = cfg.get("template", std)

    def outside(x, y):
        return not (BORDER[0] + .02 < x < BORDER[2] - .02 and BORDER[1] + .02 < y < BORDER[3] - .02)

    def in_title(x, y):
        return (x > TB[0] - 0.05 and y > TB[1] - 0.05) or (x > 27.6 and y < 1.85) or outside(x, y)

    for r in runs:
        x, y = run_center(r)
        r["center"] = (x, y)
        r["kind"] = "title" if (template and in_title(x, y)) else None
    fields = title_fields([r for r in runs if in_title(*r["center"])]) if template else {}
    fields.update(cfg.get("fields", {}))

    # printed scale -> plan?
    fpi = cfg.get("fpi")
    if fpi is None:
        for r in runs:
            m = SCALE.search(r["text"].replace(" ", ""))
            if m and (r["kind"] == "title" or not template or (r["center"][0] > 22 and r["center"][1] < 3.5)):
                fpi = float(m.group(1)); break
    if fpi is None and fields.get("scale"):
        m = SCALE.search(fields["scale"].replace(" ", ""))
        if m:
            fpi = float(m.group(1))
    kind = cfg.get("kind") or ("plan" if (fpi and fam in PLAN_FAMILIES) else "sheet")
    if kind == "plan" and not fpi:
        fpi = 50.0

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
        elif not template and all(outside(x, y) for x, y in p["pts"]) and \
                not any(not outside((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(p["pts"], p["pts"][1:])):
            p["dest"] = "sheet:line"         # the border as drawn
    if text_mode == "strokes":
        # the lettering stays as drawn: its strokes go on the sheet, the text layer is
        # only read (title block, scale, project number)
        # The template letters its own title block grid, sheet ID and border strip: the
        # drawn lettering there goes, a line at a time so no word is cut in two.  The
        # sheet's title and scale stay as drawn, and the template leaves those blank.
        def templated(x, y):
            return (x > TB[0] - 0.05 and y > TB[1] - 0.05) or (x > 30.5 and y < 1.45) or outside(x, y)
        for line in clusters([p for p in paths if p["dest"] == "drop:glyph"], 0.3):
            inside = sum(all(templated(x, y) for x, y in p["pts"]) for p in line)
            for p in line:
                p["dest"] = "title" if (template and inside > 0.5 * len(line)) else "sheet:glyph"
        if kind == "plan":
            stroke_lettering(paths)
        for r in runs:
            if r["kind"] is None:
                r["kind"] = "stroke-text"
    elif cfg.get("stroke_lettering"):
        stroke_lettering(paths)              # lettering the text layer leaves out

    # ---------------------------------------------------------- match lines
    mruns = [r for r in runs if r["kind"] is None and
             (MATCH.match(r["text"]) or r["text"].strip().upper() in ("MATCH", "MATCHLINE"))]
    for r in mruns:
        r["kind"] = "match"
    for p in paths:
        if p["dest"] is not None or p["lw"] < 1.3 or p["dash"] or len(p["pts"]) > 3:
            continue
        a, b = p["pts"][0], p["pts"][-1]
        if math.dist(a, b) < 0.15:
            continue
        for r in mruns:
            d, t = alignfit.dist_seg(r["center"], a, b)
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if d < 0.45 and abs(((ang - r["rot"]) + 90) % 180 - 90) < 4:
                p["dest"] = "sheet:match"; break
    grown = True
    while grown:
        grown = False
        ms = [p for p in paths if p["dest"] == "sheet:match"]
        mgrid = Grid(0.5)
        for q in ms:
            mgrid.add(q, q["bbox"])
        for p in paths:
            if p["dest"] is not None or p["lw"] < 1.3 or p["dash"] or len(p["pts"]) > 3:
                continue
            a, b = p["pts"][0], p["pts"][-1]
            for q in mgrid.near(p["bbox"], 0.17):
                qa, qb = q["pts"][0], q["pts"][-1]
                gap = min(math.dist(u, v) for u in (a, b) for v in (qa, qb))
                if gap > 0.16:
                    continue
                ux, uy = qb[0] - qa[0], qb[1] - qa[1]
                Lq = math.hypot(ux, uy) or 1.0
                off = lambda pt: abs((pt[0] - qa[0]) * uy - (pt[1] - qa[1]) * ux) / Lq
                if off(a) < 0.01 and off(b) < 0.01:
                    p["dest"] = "sheet:match"; grown = True; break
                if gap < 0.02 and math.dist(a, b) < 1.4:
                    p["dest"] = "sheet:match"; grown = True; break

    # ---------------------------------------------------------- callouts
    callouts = []
    rid = {r["id"]: r for r in runs}
    if text_mode == "layer":
        live = [p for p in paths if p["dest"] is None]
        thin = [p for p in live if p["lw"] <= 0.6 and not p["dash"] and not p["fill"]]
        others = [p for p in paths if p["dest"] in (None, "sheet:match", "title", "sheet:line")]
        taken = set()
        alnum = lambda t: sum(ch.isalnum() for ch in t)
        cands = [r for r in runs if r["kind"] is None and alnum(r["text"]) >= 2 and
                 not WIDTH.match(r["text"]) and not NUMBER.match(r["text"]) and
                 not PLUS.match(r["text"]) and not re.match(r"^[\d.]+\s*%$", r["text"].strip()) and
                 not re.match(r"^\d+\s*[-–]\s*\d+$", r["text"].strip())]      # an index's sheet range
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
                comp = component(land, leg, [], [], thin_grid=Live(tgrid), other_grid=ogrid)
                if sum(plen(p["pts"]) for p in comp) > 25:
                    continue
                mid = ((r["x"] + r["end"][0]) / 2, (r["y"] + r["end"][1]) / 2)
                text_end, tips, deco = ends_of(comp, leg, mid)
                if not tips:
                    continue
                if not free_end(text_end, {p["id"] for p in comp}):
                    continue                 # a cell line or a road edge, not a landing
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
                        if abs(r["h"] - r0["h"]) > 0.2 * r0["h"]:
                            continue
                        dy = (last["y"] - r["y"]) * direction
                        if not 0.12 < dy < last["h"] * 2.2 + 0.02:
                            continue
                        dx = r["x"] - r0["x"]
                        if abs(dx) < 0.06 or (direction == 1 and -0.06 < dx < 1.0):
                            nxt = r; break
                    if nxt is None:
                        break
                    keep.append(nxt); nxt["kind"] = "callout"; last = nxt
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
                    if p["dest"] is not None or extent(p["pts"]) > 0.16 or len(p["pts"]) < 4:
                        continue
                    if (closed(p) or p["fill"]) and extent(p["pts"]) > 0.05 and \
                            any(math.dist(q, t) < 0.02 for q in p["pts"]):
                        p["dest"] = "drop:arrowhead"; c["arrow"] = True
                    elif not closed(p) and extent(p["pts"]) < 0.09 and \
                            min(math.dist(p["pts"][0], t), math.dist(p["pts"][-1], t)) < 0.006:
                        p["dest"] = "sheet:squiggle"
        for r in runs:
            if r["kind"] is None and r["text"] == "~":
                r["kind"] = "squiggle"

    # ---------------------------------------------------------- regions
    regions = [tuple(b) for b in cfg.get("sheet_regions", [])]

    def in_regions(pts):
        return any(all(b[0] <= x <= b[2] and b[1] <= y <= b[3] for x, y in pts) for b in regions)

    # ---------------------------------------------------------- plan view
    aligns, twist = [], cfg.get("twist")
    twist_how = "config" if twist is not None else None
    traced_words = 0
    if kind == "plan":
        cand = [p for p in paths if p["dest"] is None and not p["fill"] and not in_regions(p["pts"])
                and plen(p["pts"]) > 0.05 and
                ((p["lw"] >= 1.85 and not p["dash"]) or
                 (p["dash"] and len(p["dash"]) >= 4) or is_dotted(p) or p["lw"] >= 0.9)]
        # station ticks (some carry the centerline's dash pattern, which a tick this
        # short never shows)
        segs = [(p["pts"][0], p["pts"][-1]) for p in paths
                if p["dest"] is None and len(p["pts"]) == 2 and
                0.035 < math.dist(p["pts"][0], p["pts"][-1]) < 0.24]
        free_runs = [r for r in runs if r["kind"] is None or
                     (r["kind"] in ("stroke-text", "invisible") and text_mode == "strokes" and
                      (alignfit.NUMBER.match(r["text"].strip()) or
                                                      '"' in r["text"]))]
        # a line's name lettered in pieces ('"', 'B1"', 'LI', 'NE') reads joined
        free_runs += [{**{k: v for k, v in r.items() if k != "center"}, "id": f"{r['id']}+"}
                      for r in join_lines(free_runs, gap=0.12)
                      if alignfit.NAME.match(r["text"].strip()) and
                      not any(alignfit.NAME.match(q["text"].strip()) for q in free_runs if q["id"] == r["id"])]
        if not cfg.get("no_alignments"):
            heavy = [p for p in cand if p["lw"] >= 1.85 and not p["dash"]]
            aligns = alignfit.fit(heavy, segs, free_runs, fpi, hints=cfg.get("stations"))
            got = {pid for al in aligns for pid in al["paths"]}
            light_c = [p for p in cand if p["id"] not in got and not (p["lw"] >= 1.85 and not p["dash"])
                       and plen(p["pts"]) > 0.3]
            more = alignfit.fit(light_c, segs, free_runs, fpi, min_len=3.0, hints=cfg.get("stations"))
            aligns += [al for al in more if al["name"] or len(al["ticks"]) >= 3]
            aligns, dupes = alignfit.tidy(aligns, fpi)
            dup_ids = {pid for al in dupes for pid in al["paths"]}
            for p in paths:
                if p["id"] in dup_ids and p["dest"] is None:
                    p["dest"] = "drop:centerline"     # drawn again by the alignment it doubles
        if twist is None and aligns:
            twist = alignfit.twist_from_bearings(aligns, free_runs)
            twist_how = "bearing" if twist is not None else None
        used = set()
        for k, al in enumerate(aligns):
            if not al["name"]:
                al["name"] = f"CL{k + 1}"
            for pid in al["paths"]:
                used.add(pid)
            for rid_ in al["labels"]:
                if rid_ and rid[rid_]["kind"] is None:
                    rid[rid_]["kind"] = "station"
            if al.get("hinted"):
                # a line numbered from the config's readings: the numbers the sheet draws
                # as strokes beside its ticks go, and the builder letters the stationing.
                # They stand in one band beside the line; the band most ticks have is theirs.
                near = []
                for along, m, half in al["ticks"]:
                    u = al["chain"].locate(m)[2]
                    got = []
                    for q in pgrid.near((m[0], m[1], m[0], m[1]), 0.5):
                        if q["dest"] not in (None, "drop:glyph", "sheet:glyph") or q["id"] in used:
                            continue
                        xs = [v[0] for v in q["pts"]]; ys = [v[1] for v in q["pts"]]
                        if math.hypot(max(xs) - min(xs), max(ys) - min(ys)) > 0.2:
                            continue
                        c = centroid(q["pts"])
                        da = (c[0] - m[0]) * u[0] + (c[1] - m[1]) * u[1]
                        dp = -(c[0] - m[0]) * u[1] + (c[1] - m[1]) * u[0]
                        if abs(da) < 0.24 and 0.05 < abs(dp) < 0.45:
                            got.append((dp, q))
                    near.append(got)
                best = (0, None)
                for k in range(-22, 23):
                    d0 = k * 0.02
                    n = sum(1 for got in near if any(abs(dp - d0) < 0.09 for dp, _q in got))
                    if abs(d0) >= 0.06 and n > best[0]:
                        best = (n, d0)
                if best[1] is not None and best[0] >= 0.6 * len(near):
                    for got in near:
                        for dp, q in got:
                            if abs(dp - best[1]) < 0.09:
                                q["dest"] = "drop:station-number"
            for along, m, half in (al["ticks"] if text_mode != "strokes" or al.get("hinted") else []):
                for p in pgrid.near((m[0], m[1], m[0], m[1]), 0.02):
                    if p["dest"] is None and len(p["pts"]) == 2 and \
                            math.dist(centroid(p["pts"]), m) < 0.01:
                        p["dest"] = "drop:tick"
        for p in paths:
            if p["id"] in used:
                p["dest"] = "drop:centerline"
        for r in runs:
            if r["kind"] is not None:
                continue
            t = r["text"].strip()
            if alignfit.NAME.match(t) or alignfit.BEARING.search(t.replace(" ", "")):
                if any(al["chain"].locate(r["center"])[0] < 0.7 for al in aligns):
                    r["kind"] = "align-text"
        arrows = mark_symbols(paths, runs)
        if twist is None:
            norths = [n for _, n in arrows if n is not None]
            if norths:
                # north on the sheet at angle n means the model's +y turned to n: twist = n - 90
                twist = ((norths[0] - 90.0) + 180.0) % 360.0 - 180.0
                twist_how = "north arrow"
        if twist is None:
            twist, twist_how = 0.0, "none"
        # lettering drawn as strokes with no text layer: routed like the rest, then
        # drawn on its base file's trace layer
        traced_words = traced.mark(paths, keep=lambda p: not in_regions(p["pts"]),
                                   exclude=[tuple(b) for b in cfg.get("trace_exclude", [])])
        for p in paths:
            if p["dest"] is not None:
                continue
            if in_regions(p["pts"]):
                p["dest"] = "sheet:line"
            elif is_dotted(p):
                p["dest"] = "bb01"
            elif fam == "drainage" and p["lw"] >= 1.85 and not p["dash"]:
                p["dest"] = "aa02"
            else:
                p["dest"] = "aa01"
        # small symbols ride with the line they sit on (a solid one keeps its own style)
        longp = [p for p in paths if p["dest"] in ("aa01", "aa02", "bb01") and plen(p["pts"]) >= 0.25]
        lgrid = Grid(0.5)
        for q in longp:
            lgrid.add(q, q["bbox"])
        for p in paths:
            if p["dest"] not in ("aa01", "aa02") or plen(p["pts"]) >= 0.25:
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
        dotted = [p for p in paths if p["dest"] == "bb01" and is_dotted(p)]
        dgrid = Grid(0.5)
        for p in dotted:
            dgrid.add(p, p["bbox"])
        for r in runs:
            if r["kind"] is not None or in_regions([r["center"]]):
                continue
            t = r["text"].strip()
            if t in ("R/W", "F", "C", "C/F", "F/C"):
                r["kind"] = "design-label"
            elif NUMBER.match(t) and len(t) >= 2 and any(
                    poly_dist(r["center"], p["pts"]) < 0.25 for p in dgrid.near((r["center"][0], r["center"][1]) * 2, 0.25)):
                r["kind"] = "topo-label"
    else:
        for p in paths:
            if p["dest"] is None:
                p["dest"] = "sheet:line"
    for r in runs:
        if r["kind"] is None:
            r["kind"] = "text"
    for r in light:
        r["kind"] = "light"
        r["center"] = run_center(r)
    runs += light
    for r in invisible:
        r["kind"] = "invisible"
        r["center"] = run_center(r)
    runs += invisible

    return {"id": ppm_id, "rel": rel, "family": fam, "kind": kind, "fpi": fpi,
            "twist": twist, "twist_how": twist_how, "calibration": [s, ox, oy], "calibration_how": how,
            "lw_scale": lw_scale, "template": bool(template), "fields": fields, "text_mode": text_mode,
            "runs": runs, "paths": paths, "callouts": callouts,
            "drawn_title": text_mode == "strokes" and template,
            "aligns": [dict({k: v for k, v in al.items() if k != "chain"}, length=al["chain"].length())
                       for al in aligns],
            "counts": dict(Counter(str(p["dest"]) for p in paths)),
            "traced": {"words": traced_words, "strokes": sum(1 for p in paths if p.get("traced"))},
            "text_counts": dict(Counter(r["kind"] for r in runs))}
