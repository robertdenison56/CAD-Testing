"""Build the RoadDraft file set for any digitised PPM sheet (ppmsheet.digitise).

    build(dig, out_dir) -> report dict

Plan sheets get base files and a sheet file that references them:
    <project>bb01.rdraft   existing features (dotted linework, contour labels)
    <project>aa01.rdraft   roadway: rebuilt alignments, stationing, proposed linework
    <project>aa02.rdraft   drainage (drainage plans: the heavy drainage system)
    <project><code><nnn>.rdraft   the sheet: border, title block, viewport, annotation
Other sheets are a sheet file only.  Names follow the Caltrans CADD Users Manual:
project number, then the code (bb / aa for base files, the print sequence code and
sheet number for the sheet).
"""
import json
import math
import re
from pathlib import Path

from leaders import poly_dist, plen
from roaddraft import Session

MODEL0 = (10000.0, 10000.0)
SHEET0 = (17.70, 11.0)
HEIGHTS = (0.08, 0.10, 0.12, 0.14, 0.175, 0.20, 0.25, 0.29, 0.35, 0.50)
MM = (0.13, 0.18, 0.25, 0.35, 0.50, 0.70, 1.00, 1.40, 2.00)

# Caltrans CADD Users Manual 2.1: plan sheet ID -> print sequence code
PRINT_CODE = {
    "X": "ca", "K": "da", "AI": "db", "PC": "dc", "L": "ea", "P": "fa", "PS": "fb", "SE": "fc",
    "C": "ga", "WPC": "gb", "G": "ha", "D": "ia", "DP": "ib", "DD": "ic", "DQ": "id",
    "U": "ka", "UP": "kb", "UD": "kc", "UQ": "kd", "CS": "la", "MI": "lb", "MID": "lc",
    "MIQ": "ld", "SC": "ma", "SCD": "mb", "SCQ": "mc", "TH": "md", "THD": "me", "THQ": "mf",
    "DE": "mg", "PD": "na", "PDD": "nb", "PDQ": "nc", "S": "oa", "SD": "ob", "SDS": "oc",
    "SQ": "od", "Q": "pa", "LK": "sc", "LL": "sj", "LD": "sk", "LQ": "sl", "ISS": "sm",
    "IR": "sn", "IPP": "so", "IP": "sp", "ID": "sq", "IQ": "sr", "PL": "st", "PP": "su",
    "PLD": "sv", "PQ": "sw", "EC": "te", "ECL": "tc", "ECD": "tf", "ECQ": "tg",
    "E": "ua", "ED": "ub", "EQ": "uc", "IOP": "ac", "LC": "ba", "IPS": "bc",
    "WPCD": "gc", "WPCQ": "gd", "W": "gi", "WP": "gj", "WD": "gk", "WQ": "gl",
    "SB": "ie", "SBP": "if", "SBD": "ig", "SBQ": "ih", "SS": "ja", "SSP": "jb", "SSD": "jc",
    "SSQ": "jd", "DEQ": "mh", "KW": "pf", "AT": "pg", "R1": "qa", "R2": "qb", "SW1": "ra",
    "SW2": "rb", "XR": "sa", "RC": "sd", "PR": "se", "MEPA": "sf", "EEP": "sg", "SRRA": "si",
    "ECK": "ta", "SES": "uh", "LOTB": "ul", "GP": "wa", "A": "wc", "ST": "we", "M": "wg",
    "MP": "wh", "EE": "wj",
}


def snap_h(h):
    return min(HEIGHTS, key=lambda v: abs(v - h))


def snap_mm(lw_pt, s):
    return min(MM, key=lambda v: abs(v - lw_pt / s * 0.3528))


def linetype(dash):
    if not dash:
        return None
    d = list(dash)
    if d[0] <= 1.0 and len(d) >= 2 and d[1] >= d[0]:
        return "dot"
    if len(d) >= 6:
        return "phantom"
    if len(d) >= 4:
        return "center"
    if d[0] < 6.0:
        return "hidden"
    return "dashed"


#: lettering the published sheet draws as linework (traced.py): each base file keeps
#: it on a layer of its own, as drawn
TRACE_DESC = "Lettering the published sheet draws as linework, kept as drawn (no text layer)"


def trace_layer(d, name):
    return d.layer(name, 0.18, None, TRACE_DESC)


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


def names_for(dig):
    f = dig["fields"]
    digits = re.sub(r"\D", "", f.get("project_number_phase", ""))
    project = digits[:10] if len(digits) >= 10 else "0000000000"
    sid = (f.get("sheet_id") or "").strip()
    if not sid:
        hits = re.findall(r"-([A-Z]{1,4})-(\d{1,3}[a-z]?)(?=-|\.pdf|$)", dig["rel"].split("/")[-1])
        hits = [h for h in hits if h[0] in PRINT_CODE]
        sid = f"{hits[-1][0]}-{hits[-1][1]}" if hits else ""
    m = re.match(r"^([A-Z]+)\s*-?\s*(\d+)([a-zA-Z]?)", sid.replace(" ", ""))
    generic = re.match(r"^([A-Z]+)-X+$", sid.replace(" ", ""))
    if m:
        code = PRINT_CODE.get(m.group(1), "zz")
        num = f"{int(m.group(2)):03d}{m.group(3).lower()}"
    elif generic:                     # a generic example sheet, "SE-XX"
        code, num = PRINT_CODE.get(generic.group(1), "zz"), "000"
    elif dig["family"] == "title":
        code, num = "ab", "001"
    else:
        code, num = "zz", "001"
    return project, code, num, sid


class Doc:
    def __init__(self, name, out):
        self.s = Session(project_name=name, out_dir=out)
        self.layers = set()

    def run(self, name, params):
        r = self.s.execute(name, params)
        if not r["ok"]:
            raise RuntimeError(f"{name} failed: {json.dumps(r['error'])[:500]} :: {json.dumps(params)[:300]}")
        return r

    def fast(self, name, params, quiet=False):
        """Run a drawing command's handler straight on the document: the same schema
        check and geometry code as execute(), without the whole-document undo snapshot
        the bus takes per command (which makes tens of thousands of strokes quadratic).
        Bulk linework and lettering only; nothing here needs undo or a journal."""
        bus = self.s.bus
        spec = bus.resolve(name)
        from jsonschema.exceptions import best_match
        err = best_match(bus._validator(spec).iter_errors(params))
        if err is not None:
            if quiet:
                return None
            raise RuntimeError(f"{name}: {err.message} :: {json.dumps(params)[:300]}")
        try:
            _msg, diff, _warn = spec.handler(bus.doc, params)
        except Exception as ex:
            if quiet:
                return None
            raise RuntimeError(f"{name} failed: {ex} :: {json.dumps(params)[:300]}")
        return {"created": diff["created"]}

    def try_run(self, name, params):
        r = self.s.execute(name, params)
        return r if r["ok"] else None

    def ask(self, name, params=None):
        r = self.s.query(name, params or {})
        if not r["ok"]:
            raise RuntimeError(f"{name} failed: {r['error']}")
        return r

    def layer(self, name, mm=0.25, lt=None, desc=""):
        if name in self.layers:
            return name
        p = {"name": name, "color": "black", "lineweight_mm": mm, "description": desc}
        if lt:
            p["linetype"] = lt
        self.run("create_layer", p)
        self.layers.add(name)
        return name

    def save(self, path):
        return self.ask("save_document", {"path": str(path)})["path"]


class Xf:
    """sheet inches <-> model feet for a plan sheet"""
    def __init__(self, fpi, twist):
        self.fpi, self.twist = fpi, twist

    def to_model(self, p):
        t = math.radians(-self.twist)
        dx, dy = (p[0] - SHEET0[0]) * self.fpi, (p[1] - SHEET0[1]) * self.fpi
        return [MODEL0[0] + dx * math.cos(t) - dy * math.sin(t),
                MODEL0[1] + dx * math.sin(t) + dy * math.cos(t)]


def draw(d, space, pts, layer, closed=False, lt=None, fill=False, xf=None):
    pts = simplify(pts)
    if closed and len(pts) > 3 and math.dist(pts[0], pts[-1]) < 0.012:
        pts = pts[:-1]
    verts = [xf.to_model(p) if xf else list(p) for p in pts]
    if len(verts) < 2:
        return None
    if fill and len(verts) >= 3:
        r = d.fast("hatch", {"space": space, "points": verts, "pattern": "SOLID", "layer": layer}, quiet=True)
        if r:
            return (r.get("created") or [None])[0]
    extra = {"linetype": lt} if lt else {}
    if len(verts) == 2 and not closed:
        r = d.fast("draw_line", {"space": space, "start": verts[0], "end": verts[1], "layer": layer, **extra},
                   quiet=True)
    else:
        r = d.fast("draw_polyline", {"space": space, "vertices": verts, "layer": layer,
                                     "closed": bool(closed and len(verts) > 2), **extra}, quiet=True)
    if r is None:
        return None
    return (r.get("created") or [None])[0]


def fill_groups(paths):
    """Filled paths made of several loops (a letter with counters, a ring): one hatch
    with islands, not each loop filled solid."""
    by = {}
    for p in paths:
        if p["fill"]:
            by.setdefault(p["id"].split(".")[0], []).append(p)
    groups = []
    for k, ps in by.items():
        if len(ps) > 1:
            for p in ps:
                p["_in_group"] = True
            groups.append(ps)
    return groups


def draw_filled(d, space, group, layer, xf=None):
    ids = []
    for p in group:
        pts = simplify(p["pts"])
        verts = [xf.to_model(q) if xf else list(q) for q in pts]
        if len(verts) >= 3:
            r = d.fast("draw_polyline", {"space": space, "vertices": verts, "layer": layer, "closed": True},
                       quiet=True)
            if r and r.get("created"):
                ids.append(r["created"][0])
    if ids:
        d.fast("hatch", {"space": space, "boundary": ids, "pattern": "SOLID", "layer": layer}, quiet=True)


def text_in(d, space, r, layer, xf=None, content=None):
    h = snap_h(r["h"])
    pos = xf.to_model((r["x"], r["y"])) if xf else [r["x"], r["y"]]
    d.fast("place_text", {"space": space, "position": pos, "content": content or r["text"],
                         "height": h * (xf.fpi if xf else 1.0),
                         "rotation_deg": r["rot"] - (xf.twist if xf else 0.0),
                         "halign": "left", "valign": "bottom", "layer": layer})


# ------------------------------------------------------------------ base files
def model_layer(d, p, s):
    lw, dash = p["lw"], tuple(p["dash"]) if p["dash"] else None
    if dash is None:
        xs = [q[0] for q in p["pts"]]; ys = [q[1] for q in p["pts"]]
        if is_closed(p["pts"]) and max(max(xs) - min(xs), max(ys) - min(ys)) < 0.06:
            return d.layer("V-ROAD-HTCH", 0.25, None, "Island and area patterns")
        if lw >= 1.85:
            return d.layer("V-ROAD-HVY", 0.70, None, "Heavy proposed linework")
        if lw >= 1.3:
            return d.layer("V-ROAD-EDGE", 0.50, None, "Edges of shoulder and structure, heavy")
        if lw >= 0.8:
            return d.layer("V-ROAD", 0.35, None, "Proposed roadway features")
        return d.layer("V-ROAD-THIN", 0.18, None, "Edges of traveled way, minor lines")
    lt = linetype(dash)
    if lt == "hidden":
        return d.layer("V-ROAD-CUT", 0.35, "hidden", "Catch lines, cut, and short-dash lines")
    if lt == "dashed":
        return d.layer("V-ROAD-CATCH", snap_mm(lw, s), "dashed", "Catch lines, fill, and dashed lines")
    return d.layer("V-ROAD-PHAN", 0.35, lt or "phantom", "Other patterned lines")


def row_ids(dig, paths):
    labels = [r for r in dig["runs"] if r["kind"] == "design-label" and r["text"] == "R/W"]
    cand = [p for p in paths if not p["dash"] and 0.8 <= p["lw"] < 1.3 and plen(p["pts"]) > 0.25]

    def direction(p):
        a, b = p["pts"][0], p["pts"][-1]
        return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180

    def straight(p):
        return poly_dist(p["pts"][len(p["pts"]) // 2], [p["pts"][0], p["pts"][-1]]) < 0.01
    row = set()
    for r in labels:
        c = r["center"]
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
                if touching and abs((direction(p) - direction(q) + 90) % 180 - 90) < 2:
                    row.add(p["id"]); grew = True
                    break
    return row


def caltrans_station(station):
    hundreds = int(round(station / 100.0))
    return str(hundreds) if hundreds % 5 == 0 else str(hundreds % 10)


def upright(rot):
    rot = (rot + 180.0) % 360.0 - 180.0
    if rot > 90.0:
        rot -= 180.0
    elif rot <= -90.0:
        rot += 180.0
    return rot


def build_bases(dig, out, names, title):
    s = dig["calibration"][0]
    xf = Xf(dig["fpi"], dig["twist"])
    project = names[0]
    made = {}
    runs = dig["runs"]
    desc_tail = (f" Local datum: sheet point ({SHEET0[0]}, {SHEET0[1]}) at E {MODEL0[0]:,.0f} "
                 f"N {MODEL0[1]:,.0f}, view twist {dig['twist']:.4f} deg (the example prints no "
                 f"coordinates).")
    # ------------------------------------------------------------- bb01
    bbp = [p for p in dig["paths"] if p["dest"] == "bb01"]
    bbt = [r for r in runs if r["kind"] == "topo-label"]
    if bbp or bbt:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              "Master Topographic file (Caltrans CADD Users Manual 3.8 B, the \"bb\" file): "
              f"existing features under sheet {names[3]}, digitised off the PPM example." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        groups = fill_groups(bbp)
        for p in bbp:
            if p.get("_in_group"):
                continue
            if p.get("traced"):
                draw(d, "model", p["pts"], trace_layer(d, "E-TOPO-TRACE"), is_closed(p["pts"]),
                     linetype(p["dash"]), p["fill"], xf)
                continue
            if p["dash"]:
                lay = d.layer("E-TOPO-HVY" if p["lw"] > 0.9 else "E-TOPO", 0.35 if p["lw"] > 0.9 else 0.18,
                              "dot", "Existing topography (dropped out)")
                lt = None if linetype(p["dash"]) == "dot" else linetype(p["dash"])
            else:
                lay = d.layer("E-TOPO-SYMB", snap_mm(p["lw"], s), None,
                              "Existing features drawn solid: fence marks, symbols")
                lt = None
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), lt, p["fill"], xf)
        for g in groups:
            lay = trace_layer(d, "E-TOPO-TRACE") if all(q.get("traced") for q in g) else \
                d.layer("E-TOPO-SYMB", 0.18, None, "Existing features drawn solid")
            draw_filled(d, "model", g, lay, xf)
        for r in bbt:
            text_in(d, "model", r, d.layer("E-TOPO-TEXT", 0.18, None, "Contour elevations, names"), xf)
        path = out / f"{project}bb01.rdraft"
        d.save(path)
        made["BB01"] = path
    # ------------------------------------------------------------- aa02
    dp = [p for p in dig["paths"] if p["dest"] == "aa02"]
    if dp:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              "Drainage base file (AA02): the proposed drainage system of sheet "
              f"{names[3]} -- pipes, culverts, inlets, end sections." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        for p in dp:
            lay = trace_layer(d, "D-DRAIN-TRACE") if p.get("traced") else \
                d.layer("D-DRAIN" if p["lw"] >= 1.85 else "D-DRAIN-SYMB",
                        0.70 if p["lw"] >= 1.85 else 0.35, None, "Drainage system")
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), linetype(p["dash"]), p["fill"], xf)
        path = out / f"{project}aa02.rdraft"
        d.save(path)
        made["AA02"] = path
    # ------------------------------------------------------------- aa01
    ap = [p for p in dig["paths"] if p["dest"] == "aa01"]
    if ap or dig["aligns"]:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              "Master Design file, roadway (Caltrans CADD Users Manual 3.8 C, the \"aa\" file): "
              f"alignments rebuilt from sheet {names[3]}'s centerlines and stationing, and its "
              "proposed roadway linework." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        # the alignment lines are drawn as the sheet draws its centerlines: heavy on a
        # layout, thin (often a center pattern) on a delineation or planting plan
        pmap = {p["id"]: p for p in dig["paths"]}
        cl = [pmap[pid] for al in dig["aligns"] for pid in al["paths"] if pid in pmap]
        mm, lt = 0.70, None
        if cl:
            lws = sorted(p["lw"] for p in cl)
            mm = snap_mm(lws[len(lws) // 2], s)
            dashed = [p["dash"] for p in cl if p["dash"]]
            lt = linetype(dashed[0]) if len(dashed) > len(cl) / 2 else None
        d.layer("V-ALIGN-CNTR", mm, lt, "Alignment lines")
        d.layer("V-ANNO-STAT", 0.35, None, "Stationing ticks and numbers")
        d.layer("V-ANNO-ALGN", 0.35, None, "Alignment names and bearings")
        built = []
        for al in dig["aligns"]:
            els = []
            for e in al["elements"]:
                if e[0] == "tangent":
                    els.append({"kind": "tangent", "start": xf.to_model(e[1]), "end": xf.to_model(e[2])})
                else:
                    c = e[3]
                    a, b = e[1], e[2]
                    mid = e[5]
                    cross = (mid[0] - a[0]) * (c[1] - a[1]) - (mid[1] - a[1]) * (c[0] - a[0])
                    els.append({"kind": "curve", "pc": xf.to_model(a), "pt": xf.to_model(b),
                                "center": xf.to_model(c), "radius": e[4] * dig["fpi"],
                                "direction": "L" if cross > 0 else "R"})
            # join ends exactly (continuity is checked to 0.001 ft)
            for i in range(1, len(els)):
                prev_end = els[i - 1].get("end") or els[i - 1].get("pt")
                key = "start" if els[i]["kind"] == "tangent" else "pc"
                els[i][key] = list(prev_end)
            name = al["name"]
            r = d.try_run("create_alignment", {"name": name, "begin_station": al["begin_station"],
                                               "elements": els,
                                               "description": f'"{name}" LINE, rebuilt from sheet '
                                                              f'{names[3]} (ticks fit to '
                                                              f'{al["fit_residual_ft"]:.2f} ft)'})
            if r is not None:
                got = next(a for a in d.ask("list_alignments")["alignments"] if a["name"] == name)
                if abs(got["length"] - al["length"] * dig["fpi"]) > 0.02 * got["length"] + 2.0:
                    d.run("delete_alignment", {"name": name})
                    r = None
            if r is None:
                # not a clean alignment after all: keep the centerline as drawn
                pmap = {p["id"]: p for p in dig["paths"]}
                for pid in al["paths"]:
                    if pid in pmap:
                        draw(d, "model", pmap[pid]["pts"], "V-ALIGN-CNTR", False, None, False, xf)
                continue
            d.run("draw_alignment", {"alignment": name, "layer": "V-ALIGN-CNTR"})
            built.append(al)
            if dig["text_mode"] == "strokes" and not al.get("hinted"):
                continue      # the sheet's own ticks and numbers stay, as drawn
            # stationing, lettered the Caltrans way, on the side the sheet letters it
            ticks = al["ticks"]
            end_sta = al["begin_station"] + al["length"] * dig["fpi"]
            lo = max(min(al["stations"]) - 1, al["begin_station"])
            hi = min(max(al["stations"]) + 1, end_sta)
            offs = []
            for (along, m, half), rid in zip(ticks, al["labels"]):
                if not rid:
                    continue
                rr = next(x for x in runs if x["id"] == rid)
                q = d.s.query("xy_to_station", {"alignment": name, "point": xf.to_model(rr["center"])})
                if q.get("ok") and q.get("offset") is not None:
                    offs.append(q["offset"])
            centre = sorted(offs)[len(offs) // 2] if offs else 10.0
            half_ft = (sorted(t[2] for t in ticks)[len(ticks) // 2]) * dig["fpi"]
            d.run("annotate_stationing", {"space": "model", "alignment": name, "interval": 100.0,
                                          "station_range": [lo, hi], "include_pc_pt": False,
                                          "tick_half_len": half_ft, "text_height": 0.14 * dig["fpi"],
                                          "label_offset": -centre, "layer": "V-ANNO-STAT"})
            labels, start = [], 0
            while True:
                page = d.ask("find_entities", {"space": "model", "layer": "V-ANNO-STAT", "type": "text",
                                               "limit": 500, "start": start})["entities"]
                labels += page
                start += len(page)
                if len(page) < 500:
                    break
            for e in labels:
                a = e.get("anchor") or {}
                if a.get("kind") != "station" or a.get("alignment") != name:
                    continue
                q = d.ask("station_to_xy", {"alignment": name, "station": a["station"], "offset": centre})
                rot = upright(90.0 - q["azimuth_deg"] + dig["twist"])
                d.run("modify_entity", {"id": e["id"], "changes": {
                    "content": caltrans_station(a["station"]), "position": q["point"],
                    "rotation_deg": rot - dig["twist"], "valign": "middle", "halign": "center",
                    "annotative": None}})
        for r in runs:
            if r["kind"] == "align-text":
                text_in(d, "model", r, "V-ANNO-ALGN", xf)
            elif r["kind"] == "design-label":
                text_in(d, "model", r, d.layer("V-ANNO-TEXT", 0.25, None, "R/W, catch points"), xf)
        row = row_ids(dig, ap)
        for p in ap:
            if p.get("traced"):
                draw(d, "model", p["pts"], trace_layer(d, "V-ANNO-TRACE"), is_closed(p["pts"]),
                     linetype(p["dash"]), p["fill"], xf)
                continue
            lay = d.layer("V-ROW", 0.35, None, "Right of way") if p["id"] in row or \
                p.get("symbol_of") in row else model_layer(d, p, s)
            lt = linetype(p["dash"])
            lay_lt = None if lay in ("V-ROAD-CATCH", "V-ROAD-CUT", "V-ROAD-PHAN") else lt
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), lay_lt, p["fill"], xf)
        path = out / f"{project}aa01.rdraft"
        d.save(path)
        if "BB01" in made:
            d.run("attach_reference", {"name": "BB01", "path": made["BB01"].name, "space": "model"})
            d.save(path)
        made["AA01"] = path
        made["_aligns"] = [a["name"] for a in built]
    return made


# ------------------------------------------------------------------ sheet
def aim_at(d, space, xf, tip, tol=0.012, shortest=0.06):
    """(element id, fraction) under a sheet point, model (via the reference) or sheet."""
    if xf:
        m = xf.to_model(tip)
        hits = d.ask("hit_test", {"space": "model", "point": m, "tolerance": tol * xf.fpi})["hits"]
        scale = xf.fpi
    else:
        m = list(tip)
        hits = d.ask("hit_test", {"space": space, "point": m, "tolerance": tol})["hits"]
        scale = 1.0
    for h in hits:
        if h["type"] not in ("line", "polyline"):
            continue
        if xf and not h.get("reference"):
            continue
        e = d.ask("get_entity", {"id": h["id"]})["entity"]
        pts = [e["start"], e["end"]] if e["type"] == "line" else e["vertices"]
        if e.get("closed"):
            pts = pts + [pts[0]]
        total = plen(pts)
        if total < shortest * scale:
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


ANCHOR = re.compile(r'(?:([\d.]+)[\'’]\s+(Lt|Rt|LT|RT)\.?\s+)?"([A-Za-z0-9]+)"\s+(\d+)\+(\d+(?:\.\d+)?)')


def split_leader(dig, c):
    P = {p["id"]: p for p in dig["paths"]}
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
        branch = [p for p in comp if any(math.dist(t, e) < 0.006 for t in tips
                                         for e in (p["pts"][0], p["pts"][-1]))]
        return list(best[1]), branch
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


def build_sheet(dig, out, names, title, bases):
    project, code, num, sid = names
    sheet = re.sub(r"[^A-Za-z0-9 ._-]", "", sid).strip() or f"{code.upper()}-{num}"
    s = dig["calibration"][0]
    plan = dig["kind"] == "plan"
    xf = Xf(dig["fpi"], dig["twist"]) if plan else None
    d = Doc(title, out)
    path = out / f"{project}{code}{num}.rdraft"
    d.run("set_meta", {"updates": {"description":
          f"Contract plan sheet {sheet} ({dig['fields'].get('sheet_title', '').replace(chr(10), ' ')}), "
          f"Caltrans PPM example {dig['id']}." + (
              " Owns no base geometry: the base files are referenced; this file holds the sheet."
              if plan else " A sheet drawing with no model: everything is on the sheet.")}})
    d.save(path)
    for name in ("AA01", "AA02", "BB01"):
        if name in bases:
            d.run("attach_reference", {"name": name, "path": bases[name].name, "space": "model"})
    fields = {k: v for k, v in dig["fields"].items() if not k.startswith("_")}
    if dig["template"]:
        d.run("create_sheet", {"name": sheet, "size": "ANSI_D", "title_block_template": "caltrans"})
        tb = {"agency": "STATE OF CALIFORNIA  -  DEPARTMENT OF TRANSPORTATION",
              "disclaimer": "THE STATE OF CALIFORNIA OR ITS OFFICERS\nOR AGENTS SHALL NOT BE "
                            "RESPONSIBLE FOR\nTHE ACCURACY OR COMPLETENESS OF SCANNED\nCOPIES OF "
                            "THIS PLAN SHEET.",
              "seal_name": " ", "seal_number": "No.", "seal_expires": "Exp."}
        tb.update(fields)
        if dig.get("drawn_title"):        # the sheet's own title and scale are kept as drawn
            tb.update({"sheet_title": " ", "scale": " "})
        d.run("fill_title_block", {"sheet": sheet, "fields": tb})
    else:
        d.run("create_sheet", {"name": sheet, "size": "ANSI_D", "title_block_template": "none"})
    if plan:
        cx, cy = (1.904 + 33.497) / 2, (0.503 + 21.497) / 2
        d.run("create_viewport", {"sheet": sheet, "center_paper": [cx, cy], "width_in": 33.497 - 1.904,
                                  "height_in": 21.497 - 0.503, "model_center": xf.to_model((cx, cy)),
                                  "feet_per_inch": dig["fpi"], "rotation_deg": dig["twist"]})
    # ---------------------------------------------------- sheet linework
    S = lambda nm, mm, desc: d.layer(nm, mm, None, desc)
    sheet_dests = ("sheet:line", "sheet:match", "sheet:north", "sheet:squiggle", "sheet:arrow",
                   "sheet:tag", "sheet:glyph")
    for g in fill_groups([p for p in dig["paths"] if p["dest"] in sheet_dests or
                          (p["dest"] == "title" and not dig["template"])]):
        draw_filled(d, sheet, g, S(f"S-FILL", 0.13, "Filled shapes"))
    for p in dig["paths"]:
        if p.get("_in_group"):
            continue
        dest = p["dest"]
        if dest in ("sheet:line", "sheet:match", "sheet:north", "sheet:squiggle", "sheet:arrow",
                    "sheet:tag", "sheet:glyph") or (dest == "title" and not dig["template"]) or \
                (dest == "drop:glyph" and dig["text_mode"] == "strokes"):
            mm = snap_mm(p["lw"], s)
            nm = {"sheet:match": "S-ANNO-MTCH", "sheet:squiggle": "S-ANNO-CALL",
                  "sheet:north": "S-ANNO-SYMB", "sheet:arrow": "S-ANNO-SYMB",
                  "sheet:tag": "S-ANNO-TAG", "title": "S-BRDR"}.get(dest)
            if dest in ("drop:glyph", "sheet:glyph"):
                nm = f"S-TEXT-{int(round(mm * 100)):03d}"
            lay = S(nm or f"S-LINE-{int(round(mm * 100)):03d}", mm, "Sheet linework")
            draw(d, sheet, p["pts"], lay, is_closed(p["pts"]), linetype(p["dash"]), p["fill"])
    # ---------------------------------------------------- lettering
    if dig["text_mode"] == "layer":
        for r in dig["runs"]:
            k = r["kind"]
            if k in ("text", "match", "squiggle", "station-plus") or (k == "title" and not dig["template"]) \
                    or (not plan and k in ("design-label", "topo-label", "align-text", "station")):
                lay = {"match": "S-ANNO-MTCH", "title": "S-BRDR"}.get(k, "S-ANNO-NOTE")
                text_in(d, sheet, r, S(lay, 0.25, "Sheet lettering"))
    # ---------------------------------------------------- callouts
    runs = {r["id"]: r for r in dig["runs"]}
    report = {"anchor": 0, "entity": 0, "point": 0}
    if dig["text_mode"] == "layer":
        lay = S("S-ANNO-CALL", 0.18, "Callouts")
        aligned = bases.get("_aligns", [])
        for c in dig["callouts"]:
            lines = [runs[i] for i in c["lines"]]
            h = snap_h(lines[0]["h"])
            leg = c["landing"]
            outer = c["text_end"]
            elbow = leg[0] if math.dist(leg[1], outer) < 1e-6 else leg[1]
            tip = c["tips"][0]
            branches = []
            if len(c["tips"]) > 1:
                tip, branches = split_leader(dig, c)
            rotated = abs(lines[0]["rot"]) > 1.0
            # a callout lettered at an angle keeps its landing as drawn: the engine's
            # shoulder is horizontal, so the leader runs to the elbow and the landing is
            # drawn beside it
            params = {"space": sheet, "position": list(elbow if rotated else outer),
                      "content": c["text"], "height": h,
                      "landing": 0.0 if rotated else math.dist(outer, elbow),
                      "arrow": bool(c.get("arrow")), "arrow_size": 0.10, "layer": lay}
            if rotated:
                d.run("draw_line", {"space": sheet, "start": list(elbow), "end": list(outer), "layer": lay})
            how = None
            m = ANCHOR.search(c["text"])
            if plan and m and m.group(3) in aligned:
                off = float(m.group(1) or 0.0) * (-1 if (m.group(2) or "").lower().startswith("l") else 1)
                station = int(m.group(4)) * 100 + float(m.group(5))
                q = d.s.query("station_to_xy", {"alignment": f"AA01:{m.group(3)}", "station": station,
                                                "offset": off, "sheet": sheet})
                if q.get("ok") and q.get("on_sheet") and math.dist(q["on_sheet"]["sheet_point"], tip) < 0.05:
                    params.update({"target_anchor": {"station": station, "offset": off},
                                   "alignment": f"AA01:{m.group(3)}"})
                    how = "anchor"
            if how is None:
                aim = aim_at(d, sheet, xf, tip)
                if aim:
                    params.update({"target_entity": aim[0], "at": round(aim[1], 5)})
                    how = "entity"
                else:
                    params["target"] = list(tip)
                    how = "point"
            r = d.try_run("place_callout", params)
            if r is None:
                params.pop("target_anchor", None); params.pop("alignment", None)
                params.pop("target_entity", None); params.pop("at", None)
                params["target"] = list(tip)
                how = "point"
                r = d.run("place_callout", params)
            report[how] += 1
            for eid in r.get("created") or []:
                ent = d.ask("get_entity", {"id": eid}).get("entity", {})
                if ent.get("type") == "text":
                    top = lines[0]
                    d.run("modify_entity", {"id": eid, "changes": {
                        "position": [top["x"], top["y"] + h], "halign": "left", "valign": "top",
                        "rotation_deg": top["rot"]}})
            for p in branches:
                draw(d, sheet, p["pts"], lay)
    d.save(path)
    return path, sheet, report


def build(dig, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names = names_for(dig)
    title = f"Caltrans PPM {dig['id']}: {dig['fields'].get('sheet_title', '').replace(chr(10), ' ')} " \
            f"{names[3]}".strip()
    bases = build_bases(dig, out, names, title) if dig["kind"] == "plan" else {}
    path, sheet, report = build_sheet(dig, out, names, title, bases)
    return {"sheet_file": path.name, "sheet": sheet,
            "bases": {k: v.name for k, v in bases.items() if not k.startswith("_")},
            "alignments": bases.get("_aligns", []), "callouts": report}
