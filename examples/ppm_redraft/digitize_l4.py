"""Digitise sheet L-4 off the published PDF into what each file of the redraft owns.

Reads ppm048_l4.extract.json.gz (extract_pdf.py, gzipped) and writes
examples/output/ppm_redraft/l4_digitized.json:
  texts     every lettered string, classified (sheet note, callout, match line label,
            road name, width, station plus, alignment label, design label, topo label,
            station number, table, title block)
  callouts  text block + landing + leader tips, read off the leader linework
  paths     every remaining stroke, classified: bb01 (existing, dotted), aa01 (proposed,
            by line style), sheet (north arrow, travel arrows, width arcs, squiggles),
            or dropped (glyphs, border, table, match lines, leaders, rebuilt annotation)
"""
import json, math, re, sys
from pathlib import Path
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import l4_geometry as G
WORK = HERE.parents[0] / "output" / "ppm_redraft"
EXTRACT = HERE / "ppm048_l4.extract.json.gz"
from sheetgeom import Sheet, run_box, in_box, extent
from leaders import landings, component, ends_of, poly_dist

BORDER = (1.904, 0.503, 33.497, 21.497)
def in_title(x, y):
    return (x > 27.65 and y > 18.45) or (x > 27.6 and y < 1.85) or not (
        BORDER[0] + .02 < x < BORDER[2] - .02 and BORDER[1] + .02 < y < BORDER[3] - .02)
TABLE = (2.3, 2.45, 10.3, 3.98)
NORTH = (22.3, 19.4, 25.5, 20.75)
def inside(b, x, y):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]

# text-layer strings whose matrices are corrupt (first glyph origin is good; the
# rotation and length are read off their vector glyphs): text, x, y, rot, size, length
BROKEN = [('"IN4" 681+58.69 EC', 20.114, 7.692, 0.0, 0.125, 2.32),
          ("MATCH LINE (L-5)", 14.897, 19.154, 0.0, 0.125, 2.27),
          ("R/W", 23.481, 14.408, 0.0, 0.125, 0.41),
          ("R/W", 28.297, 12.655, 0.0, 0.125, 0.41),
          ("+00.83", 23.886, 8.425, 0.0, 0.125, 0.79),
          ("24’", 28.458, 10.985, 0.0, 0.125, 0.35),
          ("24’", 28.458, 11.730, 0.0, 0.125, 0.35),
          ("2", 7.444, 10.968, 0.0, 0.125, 0.12),
          ("2", 27.424, 11.055, 0.0, 0.125, 0.12),
          ("2", 23.216, 8.376, 90.0, 0.125, 0.12)]

MATCH = {   # sheet polylines of the match lines, read off their dashes
    "L-66": [(5.230, 10.060), (5.212, 15.333)],
    "L-3": [(7.130, 7.856), (10.912, 3.463)],
    "L-5": [(12.473, 19.091), (19.347, 19.091), (24.054, 15.211), (28.831, 15.211)],
    "L-68": [(28.831, 15.211), (28.852, 8.366)],
    "L-67": [(25.472, 5.827), (21.462, 6.630), (16.737, 4.744)],
}
CLIP = [(5.230, 7.856), (5.230, 10.060), (5.212, 15.333), (5.212, 19.091), (12.473, 19.091),
        (19.347, 19.091), (24.054, 15.211), (28.831, 15.211), (28.852, 8.366), (28.852, 5.827),
        (25.472, 5.827), (21.462, 6.630), (16.737, 4.744), (16.737, 3.463), (10.912, 3.463),
        (7.130, 7.856)]

WIDTH = re.compile(r"^\d{1,2}(\.\d+)?’$")
PLUS = re.compile(r"^\+\d+\.\d+$")
NUMBER = re.compile(r"^\d{1,3}$")
CENTERLINE_LW = 1.92
DOTTED = (0.48, 1.44, 0.72, 1.68, 0.96, 1.68, 0.72, 1.68)


def main():
    sh = Sheet(str(EXTRACT), G.PDF_SCALE, G.PDF_OFFSET)
    WORK.mkdir(parents=True, exist_ok=True)
    runs = [r for r in sh.runs() if r["h"] < 1.0]       # a corrupt size: re-entered below
    for i, (t, x, y, rot, size, length) in enumerate(BROKEN):
        a = math.radians(rot)
        runs.append({"id": f"b{i}", "text": t, "x": x, "y": y, "rot": rot, "size": size,
                     "h": size * 1.12, "end": (x + length * math.cos(a), y + length * math.sin(a))})
    for r in runs:
        r["text"] = r["text"].replace("^", "°")
    paths = sh.paths()
    boxes = [(run_box(r), r["h"]) for r in runs]

    # ------------------------------------------------------------- glyph strokes
    for p in paths:
        p["dest"] = None
        if any(extent(p["pts"]) <= h * 1.5 and in_box(p["pts"], b) for b, h in boxes):
            p["dest"] = "drop:glyph"
    live = [p for p in paths if p["dest"] is None]
    for p in live:
        if all(in_title(x, y) for x, y in p["pts"]) or any(in_title(x, y) for x, y in p["pts"]) and extent(p["pts"]) < 0.5:
            p["dest"] = "drop:title"
        elif all(inside(TABLE, x, y) for x, y in p["pts"]):
            p["dest"] = "drop:table"
        elif all(inside(NORTH, x, y) for x, y in p["pts"]):
            p["dest"] = "sheet:north"
        elif p["lw"] >= 1.9 and not p["dash"]:
            p["dest"] = "drop:centerline"
    live = [p for p in paths if p["dest"] is None]

    # ------------------------------------------------------------- match lines
    for p in live:
        if p["lw"] < 1.4 or p["dash"]:
            continue
        for name, poly in MATCH.items():
            if all(poly_dist(q, poly) < 0.012 for q in p["pts"]):
                p["dest"] = "drop:match"
                break
    live = [p for p in paths if p["dest"] is None]

    # ------------------------------------------------------------- texts
    plan_runs = [r for r in runs if not in_title(r["x"], r["y"])]
    for r in runs:
        r["kind"] = "title" if in_title(r["x"], r["y"]) else None
    for r in plan_runs:
        t = r["text"]
        if inside(TABLE, r["x"], r["y"]):
            r["kind"] = "table"
        elif t.startswith("MATCH LINE"):
            r["kind"] = "match"
        elif t == "~":
            r["kind"] = "squiggle"

    # ------------------------------------------------------------- callouts
    thin = [p for p in live if abs(p["lw"] - 0.48) < .01 and not p["dash"]]
    others = [p for p in paths if p["dest"] in (None, "drop:centerline", "drop:match")]
    callouts = []
    taken = set()
    cands = [r for r in plan_runs if r["kind"] is None and not WIDTH.match(r["text"])
             and not NUMBER.match(r["text"]) and not PLUS.match(r["text"])]
    for r in cands:
        for land, leg in landings(r, thin):
            if land["id"] in taken:
                continue
            comp = component(land, leg, [t for t in thin if t["id"] not in taken],
                             [o for o in others if o not in thin] + thin)
            mid = ((r["x"] + r["end"][0]) / 2, (r["y"] + r["end"][1]) / 2)
            text_end, tips, deco = ends_of(comp, leg, mid)
            for p in comp:
                taken.add(p["id"])
                p["dest"] = "sheet:squiggle" if p["id"] in deco else "drop:leader"
            callouts.append({"run": r["id"], "landing": [list(leg[0]), list(leg[1])],
                             "text_end": list(text_end), "tips": [list(t) for t in tips],
                             "paths": [p["id"] for p in comp], "deco": deco})
            break
    live = [p for p in paths if p["dest"] is None]

    # group callout text blocks: the landing run, left-aligned lines stacked with it, and
    # indented continuation lines below it (Caltrans indents a callout's second line)
    rid = {r["id"]: r for r in runs}
    free = lambda r: (r["kind"] is None and not WIDTH.match(r["text"])
                      and not NUMBER.match(r["text"]) and not PLUS.match(r["text"]))
    for c in callouts:
        r0 = rid[c["run"]]
        keep = [r0]
        for direction in (1, -1):              # 1 = lines below, -1 = lines above
            last = r0
            while True:
                nxt = None
                for r in plan_runs:
                    if r in keep or not free(r) or abs(r["rot"] - r0["rot"]) > 1:
                        continue
                    dy = (last["y"] - r["y"]) * direction
                    if not 0.15 < dy < 0.30:
                        continue
                    dx = r["x"] - r0["x"]
                    ok = abs(dx) < 0.06 or (direction == 1 and -0.06 < dx < 1.4)
                    if ok:
                        nxt = r; break
                if nxt is None:
                    break
                keep.append(nxt); last = nxt
        keep.sort(key=lambda r: -r["y"])
        c["lines"] = [r["id"] for r in keep]
        for r in keep:
            r["kind"] = "callout"
        c["text"] = "\n".join(r["text"] for r in keep)

    # what sits on a leader's tip: a squiggle (two short curves, "pointing at an area")
    # or an arrowhead (a small closed outline).  Both are the callout's, not the design's.
    from leaders import closed as _closed
    for c in callouts:
        c["arrow"] = False
        for t in c["tips"]:
            for p in paths:
                if p["dest"] is not None or extent(p["pts"]) > 0.16 or len(p["pts"]) < 5:
                    continue
                if _closed(p) and extent(p["pts"]) > 0.06 and any(math.dist(q, t) < 0.02 for q in p["pts"]):
                    p["dest"] = "drop:arrowhead"; c["arrow"] = True
                elif not _closed(p) and extent(p["pts"]) < 0.09 and \
                        min(math.dist(p["pts"][0], t), math.dist(p["pts"][-1], t)) < 0.006:
                    p["dest"] = "sheet:squiggle"
    live = [p for p in paths if p["dest"] is None]

    json.dump({"runs": runs, "callouts": callouts, "paths": paths, "match": MATCH, "clip": CLIP},
              open(WORK / "l4_digitized.json", "w"))
    print(f"{len(callouts)} callouts; paths: " + ", ".join(
        f"{k}={sum(1 for p in paths if p['dest'] == k)}" for k in sorted({str(p['dest']) for p in paths})))
    for c in callouts:
        print(f"  {c['text']!r:70} tips {len(c['tips'])}")




# =====================================================================================
# second half: everything that is not a callout
# =====================================================================================
TOPO_TEXT = {"Union Pacific Railroad", "EXISTING", "INDUSTRIAL", "AVENUE"}
ROAD_NAMES = {"INDUSTRIAL AVENUE", "ROUTE 65", "NB EXIT RAMP"}
DESIGN_TEXT = re.compile(r"^(R/W|F|C|SOUND WALL 1)$")
TRAVEL = {"SB", "NB"}
NOTES = ("NOTE:", "FOR ACCURATE", "RIGHT OF WAY ENGINEERING")


def classify_texts(runs):
    for r in runs:
        if r["kind"] is not None:
            continue
        t = r["text"]
        if t.startswith(NOTES):
            r["kind"] = "note"
        elif t in ("\"IND1\" LINE", "\"D13\" LINE", "\"IN4\"", "LINE"):
            r["kind"] = "align-name"
        elif t.startswith(("N17°", "N72°")) or t == "181.44’":
            r["kind"] = "bearing"
        elif t in TOPO_TEXT and (t == "Union Pacific Railroad" or abs(r["rot"] + 63) < 3):
            r["kind"] = "topo-label"
        elif t in ROAD_NAMES:
            r["kind"] = "road-name"
        elif t in TRAVEL:
            r["kind"] = "travel"
        elif DESIGN_TEXT.match(t):
            r["kind"] = "design-label"
        elif WIDTH.match(t):
            r["kind"] = "width"
        elif PLUS.match(t):
            r["kind"] = "station-plus"
        elif NUMBER.match(t):
            r["kind"] = "number"          # station numbers or bubble numbers, decided below
        else:
            r["kind"] = "unclassified"


def centroid(pts):
    return (sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))


def finish(paths, runs, session_align):
    """bubbles, ticks, markers, arrows, width arcs; then bb01 / aa01 by line style."""
    from leaders import closed, plen
    live = [p for p in paths if p["dest"] is None]
    nums = [r for r in runs if r["kind"] == "number"]
    # --- curve bubbles: a circle (r ~0.2 in) with a number inside
    bubbles = []
    for p in live:
        if not closed(p):
            continue
        c = centroid(p["pts"]); rad = sum(math.dist(c, q) for q in p["pts"]) / len(p["pts"])
        if 0.12 < rad < 0.3:
            inner = [r for r in nums if math.dist(((r["x"] + r["end"][0]) / 2, r["y"] + r["h"] / 2), c) < rad]
            if inner:
                p["dest"] = "drop:bubble"
                for r in inner:
                    r["kind"] = "bubble"
                bubbles.append({"center": list(c), "radius": rad, "text": inner[0]["text"],
                                "leader": None})
    for b in bubbles:
        for p in live:
            if p["dest"] is None and abs(p["lw"] - 0.48) < .01 and not closed(p):
                for k in (0, -1):
                    if abs(math.dist(p["pts"][k], b["center"]) - b["radius"]) < 0.02:
                        p["dest"] = "drop:bubble"
                        b["leader"] = [list(p["pts"][k]), list(p["pts"][-1 - k])]
    for r in nums:
        if r["kind"] == "number":
            r["kind"] = "station"
    # --- station ticks and alignment markers (rebuilt from the alignments)
    live = [p for p in paths if p["dest"] is None]
    for p in live:
        if closed(p):
            c = centroid(p["pts"]); rad = max(math.dist(c, q) for q in p["pts"])
            if rad < 0.07:
                hit = session_align(c)
                if hit and abs(hit[2]) < 0.6:
                    p["dest"] = "drop:marker"
            continue
        if len(p["pts"]) != 2 or not 0.10 < plen(p["pts"]) < 0.20 or p["dash"]:
            continue
        c = centroid(p["pts"])
        hit = session_align(c)
        if not hit:
            continue
        name, station, offset, az_sheet = hit
        d = (p["pts"][1][0] - p["pts"][0][0], p["pts"][1][1] - p["pts"][0][1])
        ang = math.degrees(math.atan2(d[1], d[0]))
        perp = abs(((ang - az_sheet) % 180) - 90) < 3
        if perp and abs(offset) < 0.6 and abs(station - round(station / 100) * 100) < 1.0:
            p["dest"] = "drop:tick"
    # --- travel arrows: small closed hollow arrows (7-9 vertices), 0.96
    live = [p for p in paths if p["dest"] is None]
    for p in live:
        if abs(p["lw"] - 0.96) < .01 and not p["dash"] and 6 <= len(p["pts"]) <= 9 \
                and math.dist(p["pts"][0], p["pts"][-1]) < 0.01 and 0.15 < extent(p["pts"]) < 0.5:
            p["dest"] = "sheet:arrow"
    # --- small arcs that lead a width figure to its line
    widths = [r for r in runs if r["kind"] == "width"]
    for p in [p for p in paths if p["dest"] is None]:
        if abs(p["lw"] - 0.48) < .01 and not p["dash"] and not closed(p) and extent(p["pts"]) < 0.3 \
                and len(p["pts"]) > 3:
            c = centroid(p["pts"])
            if any(math.dist(c, ((r["x"] + r["end"][0]) / 2, r["y"] + r["h"] / 2)) < 0.3 for r in widths):
                p["dest"] = "sheet:width-arc"
    # --- the rest: existing (dotted) -> bb01, proposed -> aa01, by line style
    live = [p for p in paths if p["dest"] is None]
    def style_dest(p):
        if p["dash"] and tuple(p["dash"])[:2] == DOTTED[:2]:
            return "bb01"
        return "aa01"
    longp = [p for p in live if plen(p["pts"]) >= 0.25]
    for p in longp:
        p["dest"] = style_dest(p)
    for p in live:
        if p["dest"] is not None:
            continue
        if style_dest(p) == "bb01":          # a dotted stroke is existing, whatever it is near
            p["dest"] = "bb01"
            continue
        c = centroid(p["pts"])
        best, bd = None, 0.12
        for q in longp:
            xs = [v[0] for v in q["pts"]]; ys = [v[1] for v in q["pts"]]
            if not (min(xs) - bd <= c[0] <= max(xs) + bd and min(ys) - bd <= c[1] <= max(ys) + bd):
                continue
            d = poly_dist(c, q["pts"])
            if d < bd:
                best, bd = q, d
        p["dest"] = best["dest"] if best else style_dest(p)
        p["symbol_of"] = best["id"] if best else None
    return bubbles


def main2():
    data = json.load(open(WORK / "l4_digitized.json"))
    runs, paths = data["runs"], data["paths"]
    classify_texts(runs)
    from roaddraft import Session
    s = Session(project_name="probe")
    s.execute("create_alignment", {"name": "IND1", "begin_station": G.IND1_RANGE[0], "pis": G.ind1_pis()})
    s.execute("create_alignment", {"name": "D13", "begin_station": G.D13_BC, "pis": G.d13_pis()[0]})
    s.execute("create_alignment", {"name": "IN4", "begin_station": G.IN4_BC, "pis": G.in4_pis()})
    def session_align(pt):
        m = G.sheet_to_model(pt)
        best = None
        for name in ("IND1", "D13", "IN4"):
            q = s.query("xy_to_station", {"alignment": name, "point": list(m)})
            if not q.get("ok") or q.get("station") is None:
                continue
            off = q.get("offset", 1e9)
            if best is None or abs(off) < abs(best[2]):
                az = q.get("azimuth_deg")
                if az is None:
                    az = s.query("station_to_xy", {"alignment": name, "station": q["station"]})["azimuth_deg"]
                az_sheet = 90.0 - az + G.TWIST_DEG
                best = (name, q["station"], off, az_sheet)
        return best
    bubbles = finish(paths, runs, session_align)
    data["bubbles"] = bubbles
    json.dump(data, open(WORK / "l4_digitized.json", "w"))
    import collections
    print("paths:", dict(collections.Counter(str(p["dest"]) for p in paths)))
    print("texts:", dict(collections.Counter(str(r["kind"]) for r in runs)))
    for r in runs:
        if r["kind"] == "unclassified":
            print("   unclassified:", round(r["x"], 3), round(r["y"], 3), r["rot"], r["text"])
    print("bubbles:", [(b["text"], [round(v, 3) for v in b["center"]], b["leader"]) for b in bubbles])


if __name__ == "__main__":
    main()
    main2()
