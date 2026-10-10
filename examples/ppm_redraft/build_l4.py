"""Build the redraft of Caltrans PPM example "65 LAYOUT-4" (sheet L-4) as a Caltrans
CADD-manual file set:

    <project>bb01.rdraft    Master Topographic file: existing features (UPRR, existing
                            Industrial Avenue, existing fence), dropped-out linework
    <project>aa01.rdraft    Master Design file, roadway: the "IND1", "D13" and "IN4"
                            alignments as design data, centerlines, stationing, alignment
                            annotation, and the proposed roadway linework.  References bb01.
    <project>ea004.rdraft   the contract plan sheet L-4 (print sequence code "ea" = Layout,
                            sheet 004): border, title block, a 1" = 50' viewport over both
                            base files clipped at the match lines, and every sheet note,
                            callout, match line, table and symbol, placed in sheet view.

No drainage appears on this layout, so there is no aa02 (drainage base) for it.

    python build_l4.py --out DIR
"""
import argparse
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import l4_geometry as G                                          # noqa: E402
from leaders import poly_dist, plen                              # noqa: E402
from roaddraft import Session                                    # noqa: E402

PROJECT = "0000000000"            # "PROJECT NUMBER & PHASE 00000000001": project, phase 1
BB = f"{PROJECT}bb01"
AA = f"{PROJECT}aa01"
SH = f"{PROJECT}ea004"
SHEET = "L-4"
PROJECT_NAME = "Route 65 Bypass, 03-Pla-65 PM R11.9/R24.1 (Caltrans PPM example 65 LAYOUT-4)"
FT = G.FEET_PER_INCH
HEIGHTS = (0.10, 0.12, 0.14, 0.175, 0.20, 0.25, 0.29)

WORK = HERE.parents[0] / "output" / "ppm_redraft"
DIG = json.load(open(WORK / "l4_digitized.json"))
RUNS = {r["id"]: r for r in DIG["runs"]}


def snap_h(h):
    return min(HEIGHTS, key=lambda v: abs(v - h))


def simplify(pts, tol=0.0015):
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        best, bi = -1.0, None
        for k in range(i + 1, j):
            d = poly_dist(pts[k], [pts[i], pts[j]])
            if d > best:
                best, bi = d, k
        if best > tol:
            keep[bi] = True
            stack += [(i, bi), (bi, j)]
    return [p for p, k in zip(pts, keep) if k]


def is_closed(pts):
    return len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.012


class Doc:
    """A Session with fail-fast command and query helpers."""

    def __init__(self, out, quiet=False):
        self.s = Session(project_name=PROJECT_NAME, out_dir=out)
        self.say = (lambda *a: None) if quiet else print

    def run(self, name, params):
        r = self.s.execute(name, params)
        if not r["ok"]:
            raise SystemExit(f"{name} failed:\n{json.dumps(r['error'], indent=2)}\n"
                             f"params: {json.dumps(params)[:600]}")
        return r

    def ask(self, name, params=None):
        r = self.s.query(name, params or {})
        if not r["ok"]:
            raise SystemExit(f"{name} failed: {r['error']}")
        return r

    def created(self, r):
        return r.get("created") or []

    def save(self, path):
        return self.ask("save_document", {"path": str(path)})["path"]


def model_pts(pts):
    return [list(G.sheet_to_model(p)) for p in pts]


def draw_path(d, space, pts, layer, closed=False, to_model=True):
    pts = simplify(pts)
    if closed and len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.012:
        pts = pts[:-1]
    verts = model_pts(pts) if to_model else [list(p) for p in pts]
    if len(verts) == 2 and not closed:
        r = d.run("draw_line", {"space": space, "start": verts[0], "end": verts[1], "layer": layer})
    else:
        if len(verts) < 2:
            return None
        r = d.run("draw_polyline", {"space": space, "vertices": verts, "layer": layer,
                                    "closed": bool(closed and len(verts) > 2)})
    ids = d.created(r)
    return ids[0] if ids else None


def place_model_text(d, r, layer, content=None):
    """A sheet text run, placed in the model at true position, height and rotation."""
    h = snap_h(r["h"])
    d.run("place_text", {"space": "model", "position": list(G.sheet_to_model((r["x"], r["y"]))),
                         "content": content or r["text"], "height": h * FT,
                         "rotation_deg": r["rot"] - G.TWIST_DEG, "halign": "left",
                         "valign": "bottom", "layer": layer})


def place_sheet_text(d, r, layer, content=None, height=None):
    d.run("place_text", {"space": SHEET, "position": [r["x"], r["y"]],
                         "content": content or r["text"], "height": height or snap_h(r["h"]),
                         "rotation_deg": r["rot"], "halign": "left", "valign": "bottom",
                         "layer": layer})


# ====================================================================== bb01
BB_LAYERS = [
    ("E-RAIL", "black", "dot", 0.18, "Union Pacific Railroad tracks (existing)"),
    ("E-TOPO", "black", "dot", 0.18, "Existing roads, curbs, fences and other topography"),
    ("E-TOPO-HVY", "black", "dot", 0.35, "Existing topography, heavy"),
    ("E-TOPO-TEXT", "black", "continuous", 0.18, "Existing-feature names"),
]


def build_bb(out, quiet=False):
    d = Doc(out, quiet)
    d.run("set_meta", {"updates": {"description":
          "Master Topographic file (Caltrans CADD Users Manual 3.8 B, the \"bb\" file): the "
          "existing features under sheet L-4 -- Union Pacific Railroad, existing Industrial "
          "Avenue, existing fence -- digitised off the PPM example sheet. Local project datum: "
          "\"IND1\" 55+90.29 POT at E 10,000 N 10,000 (the example prints no coordinates)."}})
    for name, color, lt, lw, desc in BB_LAYERS:
        d.run("create_layer", {"name": name, "color": color, "linetype": lt,
                               "lineweight_mm": lw, "description": desc})
    d.run("set_annotation_scale", {"scale": FT})
    ids = {}
    n = 0
    for p in DIG["paths"]:
        if p["dest"] != "bb01":
            continue
        ys = [q[1] for q in p["pts"]]
        if p["lw"] > 0.9:
            layer = "E-TOPO-HVY"
        elif 13.25 < min(ys) and max(ys) < 14.05 and p["pts"][0][0] > 5.0:
            layer = "E-RAIL"
        else:
            layer = "E-TOPO"
        eid = draw_path(d, "model", p["pts"], layer, closed=is_closed(p["pts"]))
        if eid:
            ids[p["id"]] = eid
            n += 1
    for r in DIG["runs"]:
        if r["kind"] == "topo-label":
            place_model_text(d, r, "E-TOPO-TEXT")
    path = d.save(out / f"{BB}.rdraft")
    d.say(f"bb01: {n} existing-feature polylines -> {Path(path).name}")
    return ids


# ====================================================================== aa01
AA_LAYERS = [
    ("V-ALIGN-CNTR", "continuous", 0.70, 'Alignment lines: "IND1", "D13", "IN4"'),
    ("V-ANNO-STAT", "continuous", 0.35, "Stationing ticks and numbers"),
    ("V-ANNO-ALGN", "continuous", 0.35, "Alignment names, bearings, POT / POC / EC marks"),
    ("V-ANNO-TEXT", "continuous", 0.25, "Design lettering: R/W, catch points (C, F), wall names"),
    ("V-ROW", "continuous", 0.35, "Right of way"),
    ("V-ROAD-EDGE", "continuous", 0.50, "Edges of shoulder and structure, heavy"),
    ("V-ROAD", "continuous", 0.35, "Proposed roadway features: curbs, sidewalks, barriers, "
                                    "fence, bridges, islands"),
    ("V-ROAD-THIN", "continuous", 0.18, "Edges of traveled way, approach slabs, minor lines"),
    ("V-ROAD-HTCH", "continuous", 0.25, "Island pattern"),
    ("V-ROAD-CATCH", "dashed", 0.35, "Catch lines, fill (F)"),
    ("V-ROAD-CATCH-THIN", "dashed", 0.18, "Catch lines, thin"),
    ("V-ROAD-CUT", "hidden", 0.35, "Catch lines, cut (C)"),
    ("V-ROAD-PHAN", "phantom", 0.35, "Phantom line"),
]


def aa_layer(p):
    lw, dash = p["lw"], tuple(p["dash"]) if p["dash"] else None
    if dash is None:
        if lw >= 1.4:
            return "V-ROAD-EDGE"
        if lw >= 0.9:
            if is_closed(p["pts"]) and max(abs(a - b) for a, b in zip(
                    (min(q[0] for q in p["pts"]), min(q[1] for q in p["pts"])),
                    (max(q[0] for q in p["pts"]), max(q[1] for q in p["pts"])))) < 0.06:
                return "V-ROAD-HTCH"
            return "V-ROAD"
        return "V-ROAD-THIN"
    if dash[:2] == (3.6, 2.88):
        return "V-ROAD-CUT"
    if dash[:2] == (9.36, 3.6):
        return "V-ROAD-CATCH" if lw > 0.9 else "V-ROAD-CATCH-THIN"
    return "V-ROAD-PHAN"


def row_paths(paths):
    """0.96 solid lines lettered R/W (and the lines that continue them): right of way."""
    labels = [r for r in DIG["runs"] if r["kind"] == "design-label" and r["text"] == "R/W"]
    cand = [p for p in paths if aa_layer(p) == "V-ROAD" and plen(p["pts"]) > 0.25]

    def direction(p):
        a, b = p["pts"][0], p["pts"][-1]
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180

    def straight(p):
        return poly_dist(p["pts"][len(p["pts"]) // 2], [p["pts"][0], p["pts"][-1]]) < 0.01

    row = set()
    for r in labels:
        c = (r["x"] + 0.2 * math.cos(math.radians(r["rot"])), r["y"])
        best = None
        for p in cand:
            if not straight(p):
                continue
            dd = abs((direction(p) - r["rot"] % 180 + 90) % 180 - 90)
            dist = poly_dist(c, p["pts"])
            if dd < 6 and dist < 0.35 and (best is None or dist < best[0]):
                best = (dist, p)
        if best:
            row.add(best[1]["id"])
    grew = True
    while grew:
        grew = False
        for p in cand:
            if p["id"] in row or not straight(p):
                continue
            for q in cand:
                if q["id"] not in row:
                    continue
                touching = min(math.dist(a, b) for a in (p["pts"][0], p["pts"][-1])
                               for b in (q["pts"][0], q["pts"][-1])) < 0.012
                same = abs((direction(p) - direction(q) + 90) % 180 - 90) < 2
                if touching and same:
                    row.add(p["id"]); grew = True
                    break
    return row


def caltrans_station(station):
    """Plan lettering: the whole station at each 500 ft, otherwise its last digit."""
    hundreds = int(round(station / 100.0))
    return str(hundreds) if hundreds % 5 == 0 else str(hundreds % 10)


def sheet_upright(rot):
    rot = (rot + 180.0) % 360.0 - 180.0
    if rot > 90.0:
        rot -= 180.0
    elif rot <= -90.0:
        rot += 180.0
    return rot


STATIONING = {        # alignment: (range, label centre right of the line, ft)
    "IND1": ((5000.0, 6400.0), 10.0),
    "D13": ((65500.0, 69000.0), 10.4),
    "IN4": ((67800.0, 68300.0), 9.6),
}
MARKERS = [("IND1", G.IND1_POT, "POT"), ("IND1", G.IND1_POT_IN4, "POT"), ("IN4", G.IN4_EC, "EC")]


def build_aa(out, bb_ids, quiet=False):
    d = Doc(out, quiet)
    d.run("set_meta", {"updates": {"description":
          "Master Design file, roadway (Caltrans CADD Users Manual 3.8 C, the \"aa\" file): "
          "alignments \"IND1\" (Industrial Avenue), \"D13\" (Route 65, curve 3) and \"IN4\" "
          "(NB exit ramp, curve 36) as design data, their centerlines, stationing and "
          "annotation, and the proposed roadway linework of sheet L-4. References the bb01 "
          "topographic file. Local datum: \"IND1\" 55+90.29 POT at E 10,000 N 10,000."}})
    for name, lt, lw, desc in AA_LAYERS:
        d.run("create_layer", {"name": name, "color": "black", "linetype": lt,
                               "lineweight_mm": lw, "description": desc})
    d.run("set_annotation_scale", {"scale": FT})

    # ------------------------------------------------------------- alignments
    d.run("create_alignment", {"name": "IND1", "begin_station": G.IND1_RANGE[0],
                               "pis": G.ind1_pis(),
                               "description": '"IND1" LINE, Industrial Avenue: N 17°31\'07" E, '
                                              "one tangent (4833.49' in all; this file carries "
                                              "50+00 to 64+00)"})
    d13, _ = G.d13_pis()
    d.run("create_alignment", {"name": "D13", "begin_station": G.D13_BC, "pis": d13,
                               "description": '"D13" LINE, Route 65: curve 3, R 5000\', '
                                              "BC 654+06.40 to EC 690+10.44 (sheets L-2 to L-5)"})
    d.run("create_alignment", {"name": "IN4", "begin_station": G.IN4_BC, "pis": G.in4_pis(),
                               "description": '"IN4" LINE, NB exit ramp to Industrial Avenue: '
                                              "curve 36 to EC 681+58.69, then N 72°28'52.9\" W "
                                              "181.44' to POT 683+40.13 = \"IND1\" 59+72.49"})
    for name in ("IND1", "D13", "IN4"):
        d.run("draw_alignment", {"alignment": name, "layer": "V-ALIGN-CNTR"})
        for row in d.ask("get_design_data", {"kind": "curves", "alignment": name})["rows"]:
            d.say(f"    {name} curve: R {row['radius']:.2f}' D {row['delta_dms']} "
                  f"T {row['tangent']:.2f}' L {row['length']:.2f}' "
                  f"BC {row['pc_station_text']} EC {row['pt_station_text']}")

    # ------------------------------------------------------------- stationing
    for name, (rng, centre) in STATIONING.items():
        r = d.run("annotate_stationing", {
            "space": "model", "alignment": name, "interval": 100.0,
            "station_range": list(rng), "include_pc_pt": False,
            # a negative label_offset letters the stations right of the line; they are
            # then lettered the Caltrans way, upright on the sheet and centred on it
            "tick_half_len": 3.5, "text_height": 0.14 * FT, "label_offset": -centre,
            "layer": "V-ANNO-STAT"})
        labels = [e for e in d.ask("find_entities", {"space": "model", "layer": "V-ANNO-STAT",
                                                     "type": "text", "limit": 500})["entities"]]
        for e in labels:
            a = e.get("anchor") or {}
            if a.get("kind") != "station" or a.get("alignment") != name:
                continue
            q = d.ask("station_to_xy", {"alignment": name, "station": a["station"]})
            rot_sheet = sheet_upright(90.0 - q["azimuth_deg"] + G.TWIST_DEG)
            d.run("modify_entity", {"id": e["id"], "changes": {
                "content": caltrans_station(a["station"]),
                "rotation_deg": rot_sheet - G.TWIST_DEG, "valign": "middle"}})
        d.say(f"    {name}: {r['message']}")

    # ------------------------------------------------- alignment annotation
    for name, station, what in MARKERS:
        q = d.ask("station_to_xy", {"alignment": name, "station": station})
        d.run("draw_circle", {"space": "model", "center": q["point"], "radius": 0.05 * FT,
                              "layer": "V-ANNO-ALGN"})
    for r in DIG["runs"]:
        if r["kind"] not in ("align-name", "bearing"):
            continue
        a = math.radians(r["rot"])
        L = math.dist((r["x"], r["y"]), r["end"])
        h = snap_h(r["h"])
        centre = (r["x"] + math.cos(a) * L / 2 - math.sin(a) * h / 2,
                  r["y"] + math.sin(a) * L / 2 + math.cos(a) * h / 2)
        m = G.sheet_to_model(centre)
        best = None
        for name in ("IND1", "D13", "IN4"):
            q = d.s.query("xy_to_station", {"alignment": name, "point": list(m)})
            if q.get("ok") and q.get("station") is not None and \
                    (best is None or abs(q["offset"]) < abs(best[2])):
                best = (name, q["station"], q["offset"])
        name, station, offset = best
        res = d.run("place_label", {"space": "model", "alignment": name,
                                    "anchor": {"station": station, "offset": offset},
                                    "kind": "custom", "content": r["text"], "height": h * FT,
                                    "halign": "center", "valign": "middle",
                                    "layer": "V-ANNO-ALGN"})
        for eid in d.created(res):
            d.run("modify_entity", {"id": eid, "changes": {
                "position": list(m), "rotation_deg": r["rot"] - G.TWIST_DEG}})
    for r in DIG["runs"]:
        if r["kind"] == "design-label":
            place_model_text(d, r, "V-ANNO-TEXT")

    # ------------------------------------------------------------- linework
    paths = [p for p in DIG["paths"] if p["dest"] == "aa01"]
    row = row_paths(paths)
    by_id = {p["id"]: p for p in paths}
    ids = {}
    counts = {}
    for p in paths:
        layer = "V-ROW" if p["id"] in row else aa_layer(p)
        host = p.get("symbol_of")
        if host in row:
            layer = "V-ROW"
        eid = draw_path(d, "model", p["pts"], layer, closed=is_closed(p["pts"]))
        if eid:
            ids[p["id"]] = eid
            counts[layer] = counts.get(layer, 0) + 1
    d.say("    linework: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

    # the topography is referenced to the design file, the way the manual has it
    path = out / f"{AA}.rdraft"
    d.save(path)
    d.run("attach_reference", {"name": "BB01", "path": f"{BB}.rdraft", "space": "model"})
    d.save(path)
    d.say(f"aa01: 3 alignments, {sum(counts.values())} roadway polylines -> {path.name}")
    return ids


# ====================================================================== sheet
SHEET_LAYERS = [
    ("S-ANNO-NOTE", 0.25, "Sheet notes and place names"),
    ("S-ANNO-CALL", 0.18, "Callouts: text, landing, leader"),
    ("S-ANNO-MTCH", 0.50, "Match lines"),
    ("S-ANNO-CURV", 0.25, "Curve number bubbles and the curve data table"),
    ("S-ANNO-SYMB", 0.25, "North arrow and direction-of-travel arrows"),
    ("S-ANNO-DIM", 0.18, "Widths and station pluses"),
    ("S-TBLK", 0.25, "Title block additions: Caltrans logo"),
]

TITLE = {
    "dist": "03", "county": "Pla", "route": "65", "post_miles": "R11.9/R24.1",
    "sheet_number": "", "total_sheets": "",
    "agency": "STATE OF CALIFORNIA  -  DEPARTMENT OF TRANSPORTATION",
    "registered_civil_engineer": "", "re_date": "", "plans_approval_date": "",
    "disclaimer": "THE STATE OF CALIFORNIA OR ITS OFFICERS\nOR AGENTS SHALL NOT BE "
                  "RESPONSIBLE FOR\nTHE ACCURACY OR COMPLETENESS OF SCANNED\nCOPIES OF "
                  "THIS PLAN SHEET.",
    "seal_name": " ", "seal_number": "No.", "seal_expires": "Exp.",
    "unit": "UNIT  0000", "project_number_phase": "PROJECT NUMBER & PHASE       00000000001",
    "border_revised": "BORDER LAST REVISED 7/2/2010",
    "username": "USERNAME =>  s116122", "dgn_file": "DGN FILE =>  ea-65 L-004.dgn",
    "date_plotted": "DATE PLOTTED =>  29-DEC-2011", "time_plotted": "TIME PLOTTED =>  09:13",
    "last_revision": "00-00-00",
    "sheet_title": "LAYOUT", "scale": "SCALE:  1\" = 50'", "sheet_id": "L-4",
}

ANCHOR = re.compile(r'(?:([\d.]+)’\s+(Lt|Rt)\s+)?"(\w+)"\s+(\d+)\+(\d+(?:\.\d+)?)')

CURVE_TABLE = {
    "position": [2.405, 3.598], "title": "CURVE DATA", "text_height": 0.14,
    "columns": [("No.  ⊗", 1.395), ("R", 1.398), ("Δ", 2.098), ("T", 1.398), ("L", 1.398)],
    "rows": [["3", "5000'", "41°17'58\"", "1884.32'", "3604.04'"],
             ["36", "330'", "74°50'50\"", "251.05'", "428.58'"]],
}



def split_leader(c):
    """A leader that splits in two: (where the callout's own leader ends, the branch paths
    to draw as published).  Where the split is out on the leader, the callout runs to the
    split; where the branches leave the landing itself, it runs to the first tip."""
    P = {p["id"]: p for p in DIG["paths"]}
    comp = [P[i] for i in c["paths"] if i not in c.get("deco", [])]
    leg = c["landing"]
    tips = [tuple(t) for t in c["tips"]]
    best = None
    for p in comp:
        for q in (p["pts"][0], p["pts"][-1]):
            if poly_dist(q, leg) < 0.006:
                continue
            w = 0
            for o in comp:
                if math.dist(q, o["pts"][0]) < 0.006 or math.dist(q, o["pts"][-1]) < 0.006:
                    w += 1
                elif poly_dist(q, o["pts"]) < 0.006:
                    w += 2
            if w >= 3 and (best is None or w > best[0]):
                best = (w, tuple(q))
    if best:
        junction = best[1]
        branch = [p for p in comp if any(math.dist(t, e) < 0.006 for t in tips
                                         for e in (p["pts"][0], p["pts"][-1]))]
        return list(junction), branch
    # branches off the landing: draw every tip's chain after the first back to the landing
    chain = []
    for t in tips[1:]:
        cur = t
        for _ in range(6):
            p = next((p for p in comp if p not in chain and
                      (math.dist(p["pts"][0], cur) < 0.006 or math.dist(p["pts"][-1], cur) < 0.006)), None)
            if p is None:
                break
            chain.append(p)
            cur = p["pts"][-1] if math.dist(p["pts"][0], cur) < 0.006 else p["pts"][0]
            if poly_dist(cur, leg) < 0.006:
                break
    return list(tips[0]), chain


def aim_at(d, tip, tol_ft=0.75, shortest_ft=3.0):
    """(referenced element id, fraction along it) under a sheet point, or None."""
    m = G.sheet_to_model(tip)
    hits = d.ask("hit_test", {"space": "model", "point": list(m), "tolerance": tol_ft})["hits"]
    for h in hits:
        if h["type"] not in ("line", "polyline") or not h.get("reference"):
            continue
        e = d.ask("get_entity", {"id": h["id"]})["entity"]
        pts = [e["start"], e["end"]] if e["type"] == "line" else e["vertices"]
        if e.get("closed"):
            pts = pts + [pts[0]]
        total = plen(pts)
        if total < shortest_ft:
            continue
        run_, along, near = 0.0, 0.0, None
        for a, b in zip(pts, pts[1:]):
            seg = math.dist(a, b)
            dd = poly_dist(m, [a, b])
            if near is None or dd < near:
                t_ = max(0.0, min(1.0, ((m[0] - a[0]) * (b[0] - a[0]) + (m[1] - a[1]) * (b[1] - a[1]))
                                  / max(seg * seg, 1e-12)))
                along, near = run_ + t_ * seg, dd
            run_ += seg
        return h["id"], along / total
    return None


def build_sheet(out, aa_ids, bb_ids, quiet=False):
    d = Doc(out, quiet)
    d.run("set_meta", {"updates": {"description":
          "Contract plan sheet L-4, LAYOUT, 1\" = 50' (Caltrans PPM example \"65 LAYOUT-4\", "
          "Route 65 Bypass). Owns no design: the roadway (aa01) and topography (bb01) are "
          "referenced and clipped at the match lines; this file holds the sheet: border, "
          "title block, notes, callouts, match lines, curve data and symbols."}})
    doc_path = out / f"{SH}.rdraft"
    d.save(doc_path)
    clip = [list(G.sheet_to_model(p)) for p in DIG["clip"]]
    for name, f in (("AA01", AA), ("BB01", BB)):
        r = d.run("attach_reference", {"name": name, "path": f"{f}.rdraft", "space": "model",
                                       "clip": clip})
        d.say(f"    {r['message']}")
    d.run("create_sheet", {"name": SHEET, "size": "ANSI_D", "title_block_template": "caltrans"})
    d.run("fill_title_block", {"sheet": SHEET, "fields": TITLE})
    cx, cy = (1.904 + 33.497) / 2, (0.503 + 21.497) / 2
    d.run("create_viewport", {"sheet": SHEET, "center_paper": [cx, cy],
                              "width_in": 33.497 - 1.904, "height_in": 21.497 - 0.503,
                              "model_center": list(G.sheet_to_model((cx, cy))),
                              "feet_per_inch": FT, "rotation_deg": G.TWIST_DEG})
    for name, lw, desc in SHEET_LAYERS:
        d.run("create_layer", {"name": name, "color": "black", "lineweight_mm": lw,
                               "description": desc})

    # ------------------------------------------------------------- lettering
    kinds = {"note": "S-ANNO-NOTE", "road-name": "S-ANNO-NOTE", "travel": "S-ANNO-SYMB",
             "width": "S-ANNO-DIM", "station-plus": "S-ANNO-DIM", "match": "S-ANNO-MTCH",
             "squiggle": "S-ANNO-CALL"}
    for r in DIG["runs"]:
        if r["kind"] in kinds:
            place_sheet_text(d, r, kinds[r["kind"]])
    # sheet linework copied as drawn: north arrow, travel arrows, width arcs, squiggles
    for p in DIG["paths"]:
        dest = p["dest"]
        layer = {"sheet:arrow": "S-ANNO-SYMB", "sheet:width-arc": "S-ANNO-DIM",
                 "sheet:squiggle": "S-ANNO-CALL"}.get(dest)
        if layer:
            draw_path(d, SHEET, p["pts"], layer, closed=is_closed(p["pts"]), to_model=False)

    # north arrow and the Caltrans logo as blocks (cells)
    def block(name, desc, paths, base):
        ents = []
        for p in paths:
            pts = simplify(p["pts"], 0.001)
            ents.append({"type": "polyline", "vertices": [[x - base[0], y - base[1]] for x, y in pts],
                         "closed": False})
        d.run("define_block", {"name": name, "base_point": [0, 0], "entities": ents,
                               "description": desc})
        return base
    north = [p for p in DIG["paths"] if p["dest"] == "sheet:north"]
    nb = block("NORTH-ARROW", "Plan north arrow, as drawn on sheet L-4", north, (23.98, 20.12))
    d.run("insert_block", {"space": SHEET, "block_name": "NORTH-ARROW", "position": list(nb),
                           "layer": "S-ANNO-SYMB"})
    logo = [p for p in DIG["paths"] if p["dest"] == "drop:title"
            and all(1.33 < x < 1.67 and 0.6 < y < 3.1 for x, y in p["pts"])]
    lb = block("CALTRANS-LOGO", "Caltrans logo, left binding strip", logo, (1.5, 1.8))
    d.run("insert_block", {"space": SHEET, "block_name": "CALTRANS-LOGO", "position": list(lb),
                           "layer": "S-TBLK"})

    # ------------------------------------------------------------- match lines
    for p in DIG["paths"]:
        if p["dest"] == "drop:match":
            draw_path(d, SHEET, p["pts"], "S-ANNO-MTCH", to_model=False)

    # ------------------------------------------------------------- curve data
    t = CURVE_TABLE
    title = next(r for r in DIG["runs"] if r["text"] == t["title"])
    place_sheet_text(d, title, "S-ANNO-CURV")
    d.run("place_table", {"space": SHEET, "position": t["position"],
                          "columns": [{"header": h, "width": w} for h, w in t["columns"]],
                          "rows": t["rows"], "text_height": t["text_height"],
                          "layer": "S-ANNO-CURV"})

    # ------------------------------------------------------------- bubbles
    for b in DIG["bubbles"]:
        cx_, cy_ = b["center"]
        rad = round(b["radius"], 3)
        d.run("draw_circle", {"space": SHEET, "center": [cx_, cy_], "radius": rad,
                              "layer": "S-ANNO-CURV"})
        d.run("place_text", {"space": SHEET, "position": [cx_, cy_], "content": b["text"],
                             "height": 0.14, "halign": "center", "valign": "middle",
                             "layer": "S-ANNO-CURV"})
        if b["leader"]:
            name = "D13" if b["text"] == "3" else "IN4"
            tip = b["leader"][1]
            q = d.ask("xy_to_station", {"alignment": f"AA01:{name}",
                                        "point": list(G.sheet_to_model(tip))})
            on = d.ask("station_to_xy", {"alignment": f"AA01:{name}", "station": q["station"],
                                         "sheet": SHEET})["on_sheet"]["sheet_point"]
            ang = math.atan2(on[1] - cy_, on[0] - cx_)
            start = [cx_ + rad * math.cos(ang), cy_ + rad * math.sin(ang)]
            d.run("draw_line", {"space": SHEET, "start": start, "end": list(on),
                                "layer": "S-ANNO-CURV"})

    # ------------------------------------------------------------- callouts
    targets = {}
    for pid, eid in aa_ids.items():
        targets[pid] = f"AA01:{eid}"
    for pid, eid in bb_ids.items():
        targets[pid] = f"BB01:{eid}"
    base_paths = [p for p in DIG["paths"] if p["id"] in targets]
    report = []
    for c in DIG["callouts"]:
        lines = [RUNS[i] for i in c["lines"]]
        h = snap_h(lines[0]["h"])
        leg = c["landing"]
        outer = c["text_end"]
        elbow = leg[0] if math.dist(leg[1], outer) < 1e-6 else leg[1]
        landing = math.dist(outer, elbow)
        content = c["text"]
        tip = c["tips"][0]
        branches = []
        if len(c["tips"]) > 1:
            tip, branches = split_leader(c)
        params = {"space": SHEET, "position": list(outer), "content": content, "height": h,
                  "landing": landing, "arrow": bool(c.get("arrow")), "arrow_size": 0.10,
                  "layer": "S-ANNO-CALL"}
        how = None
        m = ANCHOR.search(content)
        if m:
            off = float(m.group(1) or 0.0) * (-1 if m.group(2) == "Lt" else 1)
            station = int(m.group(4)) * 100 + float(m.group(5))
            name = m.group(3)
            q = d.ask("station_to_xy", {"alignment": f"AA01:{name}", "station": station,
                                        "offset": off, "sheet": SHEET})
            at = q["on_sheet"]["sheet_point"]
            miss = math.dist(at, tip)
            if miss < 0.05:
                params.update({"target_anchor": {"station": station, "offset": off},
                               "alignment": f"AA01:{name}"})
                how = f"anchor AA01:{name} {q['station_text']} {abs(off):.2f}' " \
                      f"{'Lt' if off < 0 else 'Rt'} ({miss:.3f} in from the published tip)"
            else:
                report.append(f"  ! {content.splitlines()[0]}: the stated station lands "
                              f"{miss:.2f} in from the published leader; aimed at the leader")
        if how is None:
            # the referenced element the published leader touches -- asked of the sheet
            # file itself, so the id is the one its clipped reference shows -- and where
            # along it the tip sits
            aim = aim_at(d, tip)
            if aim:
                params.update({"target_entity": aim[0], "at": round(aim[1], 5)})
                how = f"entity {aim[0]} at {aim[1]:.3f}"
            else:
                params["target"] = list(tip)
                how = "point (the leader ends in the open, on an area)"
        r = d.run("place_callout", params)
        created = d.created(r)
        # Caltrans letters the callout above its landing, left-aligned as published:
        # put the text back where the sheet has it
        for eid in created:
            ent = d.ask("get_entity", {"id": eid}).get("entity", {})
            if ent.get("type") == "text":
                top = lines[0]
                d.run("modify_entity", {"id": eid, "changes": {
                    "position": [top["x"], top["y"] + h], "halign": "left", "valign": "top"}})
        for p in branches:
            draw_path(d, SHEET, p["pts"], "S-ANNO-CALL", to_model=False)
        report.append(f"  {content.splitlines()[0][:40]:40} -> {how}"
                      + (f", then {len(c['tips'])} branches as drawn" if branches else ""))
    d.say("\n".join(report))
    path = d.save(doc_path)
    d.say(f"sheet: {SHEET} -> {Path(path).name}")
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print("== bb01  topography")
    bb_ids = build_bb(out, args.quiet)
    print("== aa01  roadway design")
    aa_ids = build_aa(out, bb_ids, args.quiet)
    print("== ea004 sheet L-4")
    build_sheet(out, aa_ids, bb_ids, args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
