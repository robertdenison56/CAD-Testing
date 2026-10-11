"""Build the RoadDraft file set for a digitised WFL sheet (wflsheet.digitise).

    build(dig, out_dir) -> report dict

Files are named per the FLH OpenRoads Designer User Manual, chapter 3C (the WFLHD
ORD file naming convention): the project's prefix, then a file type suffix.

Plan sheets get design files in model space and a sheet file that references them:
    <prefix>_sur.rdraft        existing survey features: the sheet's dashed linework
                               and contour elevations
    <prefix>_ali.rdraft        alignments rebuilt from the centerlines, with stationing
    <prefix>_cor.rdraft        the proposed linework (edges, limits, slope stakes);
                               references _ali and _sur
    <prefix>_hyd_cor.rdraft    drainage plans: the heavy drainage system
    <prefix>_pln_<type>.rdraft the sheet: border, title block, viewport, annotation
Other sheets are a sheet file only.  The sheet's type suffix is the one stamped in
the published sheet's margin (SamplePlan_pln_pp1.dgn -> _pln_pp1), else the manual's
suffix for the kind of sheet (_pln_typ, _pln_qtab, _pln_gen, ...).
"""
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ppm_redraft"))

from leaders import poly_dist, plen                                   # noqa: E402
from ppmbuild import (Doc, draw, draw_filled, fill_groups, is_closed, snap_mm,   # noqa: E402
                      linetype, aim_at, split_leader)
from wflsheet import snap_h, SHEET_W, SHEET_H                         # noqa: E402

MODEL0 = (10000.0, 10000.0)

# family -> the manual's plan sheet file type suffix (after the project prefix)
SUFFIX = {"general": "pln_gen", "soq": "pln_soq", "typical": "pln_typ", "survey": "pln_ctrl",
          "qtab": "pln_qtab", "plan-profile": "pln_pp", "approach": "pln_pp", "erosion": "pln_ec",
          "drainage": "hyd_pln_pp", "wall": "pln_wall", "detour": "pln_ttc", "traffic": "pln_ptc",
          "signing": "pln_ptc", "details": "pln_misc", "demolition": "pln_demo", "layout": "pln_pp",
          "site": "pln_pp", "parking": "pln_pp", "xs": "xs", "other": "pln_misc"}
NOT_IN_MANUAL = {"pln_soq", "pln_ctrl"}
STAMP = re.compile(r"([A-Za-z0-9][A-Za-z0-9\-]*)_(?:(hyd|sur|brd|geo|rw|utl)_)?(pln_[A-Za-z0-9]+|xs)\.dgn$", re.I)
PROJECT = re.compile(r"([A-Za-z]{2,6})\s*([\d]+(?:-\d+)?)\s*\((\d+)\)")
ANCHOR = re.compile(r'"([A-Za-z0-9 \-]+)"\s+(\d+)\+(\d+(?:\.\d+)?)')
# the project prefixes the sample sheets stamp (their ORD file names), for the sheets
# of the same project that carry no stamp or an older MicroStation one
PREFIXES = {"AK NPS SAMP 14(1)": "SamplePlan", "WA NP FOVA 10(1)": "WA-NP-FOVA-101",
            "WY NPS YELL 12(2)": "yell12-2", "ID FLAP ADA 60(5)": "ida-ada60-5",
            "WA FLAP JEFF 1(23)": "waa-jeff1-23", "MT NPS GLAC 10(22)": "glac10-22"}


class Naming:
    """How one FLH division names its files: the sheet file from the sheet, and the
    design files the plan's model is split into."""
    name = "wfl"
    manual = "the FLH OpenRoads Designer User Manual, chapter 3C (WFLHD ORD file naming)"
    roles = {"SUR": "Survey ORD file (FLH ORD manual 3C.4.a, the \"_sur\" file)",
             "ALI": "Alignments ORD file (FLH ORD manual 3C.4.b, the \"_ali\" file)",
             "HYD": "Drainage design file (FLH ORD manual 3C.5, functional code \"hyd\")",
             "COR": "Corridor ORD file (FLH ORD manual 3C.4.b, the \"_cor\" file)"}

    def names_for(self, dig):
        return names_for(dig)

    @staticmethod
    def road_name(dig):
        """The road a plan sheet is of, where a note letters it ("Main Road", "Davis
        Dam Rd"): the alignment descriptor for a CFL file, failing a lettered name."""
        for r in dig["runs"]:
            m = re.match(r"^([A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+){0,3})\s+(Road|Rd\.?|Loop|Drive|Dr\.?|Highway|Hwy\.?)$",
                         r["text"].strip())
            if m:
                return m.group(1)
        return None

    def design_file(self, prefix, key, align_names):
        return {"SUR": f"{prefix}_sur.rdraft", "ALI": f"{prefix}_ali.rdraft",
                "HYD": f"{prefix}_hyd_cor.rdraft", "COR": f"{prefix}_cor.rdraft"}[key]

    def sheet_file(self, prefix, suffix):
        return f"{prefix}_{suffix}.rdraft"

    def in_manual(self, suffix):
        return suffix not in NOT_IN_MANUAL

    @staticmethod
    def station_text(station):
        """How a 100 ft tick is lettered: WFL letters the hundreds ("111")."""
        return station_label(station)

    def inline(self, key, dig):
        """Does the convention keep this design file's content in the sheet file?"""
        return False


def names_for(dig):
    """(project prefix, sheet file suffix, sheet number, how the prefix was found)"""
    f = dig["fields"]
    stamp = (f.get("dgn_file") or "").replace("\\", "/").split("/")[-1]
    m = STAMP.search(stamp)
    prefix = suffix = None
    how = ""
    if m:
        prefix = m.group(1)
        suffix = (m.group(2).lower() + "_" if m.group(2) else "") + m.group(3).lower()
        how = f"from the plot stamp ({stamp})"
    if not prefix:
        pm = PROJECT.search(f.get("project") or "")
        known = PREFIXES.get(re.sub(r"\s+", " ", f.get("project") or "").strip())
        if known:
            prefix, how = known, f"the project's stamped prefix ({f.get('project')})"
        elif pm:
            prefix = f"{pm.group(1).lower()}{pm.group(2)}-{pm.group(3)}"
            how = f"from the project number ({f.get('project')})"
        else:
            prefix, how = "wfl", "no project number on the sheet"
    if not suffix:
        suffix = SUFFIX.get(dig["family"], "pln_misc")
    sid = (f.get("sheet_number") or "").strip()
    return prefix, suffix, sid, how


class Xf:
    """sheet inches <-> model feet for a plan sheet: the plan view's centre sits at
    MODEL0, turned by the view twist"""
    def __init__(self, fpi, twist, sheet0):
        self.fpi, self.twist, self.sheet0 = fpi, twist, sheet0

    def to_model(self, p):
        t = math.radians(-self.twist)
        dx, dy = (p[0] - self.sheet0[0]) * self.fpi, (p[1] - self.sheet0[1]) * self.fpi
        return [MODEL0[0] + dx * math.cos(t) - dy * math.sin(t),
                MODEL0[1] + dx * math.sin(t) + dy * math.cos(t)]


def text_in(d, space, r, layer, xf=None, content=None):
    h = snap_h(r["h"])
    pos = xf.to_model((r["x"], r["y"])) if xf else [r["x"], r["y"]]
    d.fast("place_text", {"space": space, "position": pos, "content": content or r["text"],
                         "height": h * (xf.fpi if xf else 1.0),
                         "rotation_deg": r["rot"] - (xf.twist if xf else 0.0),
                         "halign": "left", "valign": "bottom", "layer": layer})


def model_layer(d, p):
    """A layer for a piece of proposed linework, by its weight (points) and pattern."""
    lw, dash = p["lw"], p["dash"]
    if not dash:
        xs = [q[0] for q in p["pts"]]; ys = [q[1] for q in p["pts"]]
        if is_closed(p["pts"]) and max(max(xs) - min(xs), max(ys) - min(ys)) < 0.06:
            return d.layer("P_ROAD_HATCH", 0.25, None, "Island and area patterns")
        if lw >= 1.2:
            return d.layer("P_ROAD_HEAVY", 0.50, None, "Heavy proposed linework")
        if lw >= 0.9:
            return d.layer("P_ROAD_EDGE", 0.35, None, "Edges of pavement and shoulder")
        if lw >= 0.6:
            return d.layer("P_ROAD", 0.25, None, "Proposed roadway features")
        return d.layer("P_ROAD_THIN", 0.18, None, "Minor proposed lines")
    lt = linetype(dash)
    if lt == "dot":
        return d.layer("P_ROAD_LIMITS", 0.35, "dot", "Slope stake and construction limits")
    if lt == "hidden":
        return d.layer("P_ROAD_HIDDEN", 0.25, "hidden", "Short-dash proposed lines")
    if lt == "dashed":
        return d.layer("P_ROAD_DASHED", snap_mm(lw, 1.0), "dashed", "Long-dash proposed lines")
    return d.layer("P_ROAD_PHANTOM", 0.35, lt or "phantom", "Other patterned lines")


def station_label(station):
    return str(int(round(station / 100.0)))


# ------------------------------------------------------------------ design files
def build_bases(dig, out, names, title, naming=None):
    naming = naming or Naming()
    prefix = names[0]
    anames = [a["name"] for a in dig["aligns"]]
    xf = Xf(dig["fpi"], dig["twist"], ((dig["plan_rect"][0] + dig["plan_rect"][2]) / 2,
                                       (dig["plan_rect"][1] + dig["plan_rect"][3]) / 2))
    runs = dig["runs"]
    rid = {r["id"]: r for r in runs}
    made = {}
    desc_tail = (f" Local datum: the plan view's centre at E {MODEL0[0]:,.0f} N {MODEL0[1]:,.0f}, "
                 f"view twist {dig['twist']:.4f} deg (the sample sheet prints no coordinates for "
                 "its linework).")
    # ------------------------------------------------------------- _sur
    sp = [p for p in dig["paths"] if p["dest"] == "sur"]
    st = [r for r in runs if r["kind"] == "topo-label"]
    if sp or st:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              f"{naming.roles['SUR']}: existing features "
              f"under sheet {names[2]}, digitised off the sample sheet -- its dashed linework "
              "and contour elevations." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        groups = fill_groups(sp)
        for p in sp:
            if p.get("_in_group"):
                continue
            lt = linetype(p["dash"])
            lay = d.layer("E_TOPO" if p["lw"] <= 0.5 else "E_TOPO_HEAVY", snap_mm(p["lw"], 1.0),
                          lt or "dashed", "Existing features (dashed)")
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), None, p["fill"], xf)
        for g in groups:
            draw_filled(d, "model", g, d.layer("E_TOPO_SYMB", 0.18, None, "Existing symbols"), xf)
        for r in st:
            text_in(d, "model", r, d.layer("E_TOPO_TEXT", 0.18, None, "Contour elevations, names"), xf)
        path = out / naming.design_file(prefix, "SUR", anames)
        d.save(path)
        made["SUR"] = path
    # ------------------------------------------------------------- _ali
    built = []
    if dig["aligns"]:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              f"{naming.roles['ALI']}: the alignments "
              f"rebuilt from sheet {names[2]}'s centerlines, station ticks and station numbers, "
              "with stationing. FLH names the ORD feature ALI_<type>_<id> (ALI_MAIN_01); the "
              "alignment here keeps the name the plan letters." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        d.layer("P_ALIGN", 0.50, None, "Alignment lines")
        d.layer("P_ALIGN_STA", 0.25, None, "Stationing ticks and numbers")
        d.layer("P_ALIGN_TEXT", 0.25, None, "Alignment names and bearings")
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
            for i in range(1, len(els)):
                prev_end = els[i - 1].get("end") or els[i - 1].get("pt")
                key = "start" if els[i]["kind"] == "tangent" else "pc"
                els[i][key] = list(prev_end)
            name = al["name"]
            r = d.try_run("create_alignment", {"name": name, "begin_station": al["begin_station"],
                                               "elements": els,
                                               "description": f'"{name}" Line, rebuilt from sheet '
                                                              f'{names[2]} (ticks fit to '
                                                              f'{al["fit_residual_ft"]:.2f} ft)'})
            if r is not None:
                got = next(a for a in d.ask("list_alignments")["alignments"] if a["name"] == name)
                if abs(got["length"] - al["length"] * dig["fpi"]) > 0.02 * got["length"] + 2.0:
                    d.run("delete_alignment", {"name": name})
                    r = None
            if r is None:
                pmap = {p["id"]: p for p in dig["paths"]}
                for pid in al["paths"]:
                    if pid in pmap:
                        draw(d, "model", pmap[pid]["pts"], "P_ALIGN", False, None, False, xf)
                continue
            d.run("draw_alignment", {"alignment": name, "layer": "P_ALIGN"})
            built.append(al)
            # stationing the WFL way: a tick every 100 ft, the station number lettered
            # square to the line at the offset the sheet uses
            end_sta = al["begin_station"] + al["length"] * dig["fpi"]
            lo = max(min(al["stations"]) - 1, al["begin_station"])
            hi = min(max(al["stations"]) + 1, end_sta)
            offset = -al["label_offset_in"] * dig["fpi"]          # RoadDraft: right is positive
            h = snap_h(al["label_h"]) * dig["fpi"]
            d.run("annotate_stationing", {"space": "model", "alignment": name,
                                          "interval": al.get("label_interval", 100.0),
                                          "station_range": [lo, hi], "include_pc_pt": False,
                                          "tick_half_len": al["tick_len_in"] * dig["fpi"] / 2,
                                          "text_height": h, "label_offset": offset,
                                          "layer": "P_ALIGN_STA"})
            labels, start = [], 0
            while True:
                page = d.ask("find_entities", {"space": "model", "layer": "P_ALIGN_STA", "type": "text",
                                               "limit": 500, "start": start})["entities"]
                labels += page
                start += len(page)
                if len(page) < 500:
                    break
            for e in labels:
                a = e.get("anchor") or {}
                if a.get("kind") != "station" or a.get("alignment") != name:
                    continue
                q = d.ask("station_to_xy", {"alignment": name, "station": a["station"], "offset": offset})
                rot = (90.0 - q["azimuth_deg"] + al["label_rot_rel"] + 180.0) % 360.0 - 180.0
                d.run("modify_entity", {"id": e["id"], "changes": {
                    "content": naming.station_text(a["station"]), "position": q["point"],
                    "rotation_deg": rot, "valign": "middle", "halign": "center", "annotative": None}})
        for r in runs:
            if r["kind"] == "align-text":
                text_in(d, "model", r, "P_ALIGN_TEXT", xf)
        path = out / naming.design_file(prefix, "ALI", anames)
        d.save(path)
        made["ALI"] = path
    # ------------------------------------------------------------- _hyd_cor
    hp = [p for p in dig["paths"] if p["dest"] == "hyd"]
    if hp and naming.inline("HYD", dig):
        made.setdefault("_inline", {})["HYD"] = hp
        hp = []
    if hp:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              f"{naming.roles['HYD']}: the proposed "
              f"drainage system of sheet {names[2]} -- pipes, culverts, inlets." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        for p in hp:
            lay = d.layer("P_DRAIN" if p["lw"] >= 1.2 else "P_DRAIN_SYMB", 0.50 if p["lw"] >= 1.2 else 0.35,
                          None, "Drainage system")
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), linetype(p["dash"]), p["fill"], xf)
        path = out / naming.design_file(prefix, "HYD", anames)
        d.save(path)
        made["HYD"] = path
    # ------------------------------------------------------------- _cor
    cp = [p for p in dig["paths"] if p["dest"] == "cor"]
    if cp:
        d = Doc(title, out)
        d.run("set_meta", {"updates": {"description":
              f"{naming.roles['COR']}: the proposed "
              f"linework of sheet {names[2]} -- edges of pavement, construction and slope stake "
              "limits, symbols. References the alignment and survey files." + desc_tail}})
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        groups = fill_groups(cp)
        for p in cp:
            if p.get("_in_group"):
                continue
            lay = model_layer(d, p)
            lt = linetype(p["dash"])
            lay_lt = None if lay in ("P_ROAD_LIMITS", "P_ROAD_HIDDEN", "P_ROAD_DASHED", "P_ROAD_PHANTOM") else lt
            draw(d, "model", p["pts"], lay, is_closed(p["pts"]), lay_lt, p["fill"], xf)
        for g in groups:
            draw_filled(d, "model", g, d.layer("P_ROAD_SYMB", 0.18, None, "Filled symbols"), xf)
        for r in runs:
            if r["kind"] == "design-label":
                text_in(d, "model", r, d.layer("P_ROAD_TEXT", 0.25, None, "R/W, catch points"), xf)
        path = out / naming.design_file(prefix, "COR", anames)
        d.save(path)
        for key in ("ALI", "SUR"):
            if key in made:
                d.run("attach_reference", {"name": key, "path": made[key].name, "space": "model"})
        d.save(path)
        made["COR"] = path
    made["_aligns"] = [a["name"] for a in built]
    return made


# ------------------------------------------------------------------ sheet
def build_sheet(dig, out, names, title, bases, naming=None):
    naming = naming or Naming()
    prefix, suffix, sid, _ = names
    sheet = re.sub(r"[^A-Za-z0-9 ._-]", "", sid).strip() or suffix.upper()
    plan = dig["kind"] == "plan"
    xf = Xf(dig["fpi"], dig["twist"], ((dig["plan_rect"][0] + dig["plan_rect"][2]) / 2,
                                       (dig["plan_rect"][1] + dig["plan_rect"][3]) / 2)) if plan else None
    d = Doc(title, out)
    path = out / naming.sheet_file(prefix, suffix)
    d.run("set_meta", {"updates": {"description":
          f"Plan sheet {sheet} ({dig['fields'].get('sheet_title', '').replace(chr(10), ' ') or dig['family']}), "
          f"{naming.name.upper()} sample plan sheet {dig['id']}, named per {naming.manual}." + (
              " Owns no design geometry: the design files are referenced; this file holds the sheet."
              if plan else " A sheet drawing with no model: everything is on the sheet.")}})
    d.save(path)
    for name in ("COR", "HYD", "ALI", "SUR"):
        if name in bases:
            d.run("attach_reference", {"name": name, "path": bases[name].name, "space": "model"})
    # a design file the convention keeps in the sheet file itself (FDOT's DRPRRD holds
    # the drainage structures and the drainage sheets) is drawn into this file's model
    inline = bases.get("_inline", {})
    if plan and inline:
        d.run("set_annotation_scale", {"scale": dig["fpi"]})
        for key, paths_ in inline.items():
            for p in paths_:
                lay = d.layer("P_DRAIN" if p["lw"] >= 1.2 else "P_DRAIN_SYMB", 0.50 if p["lw"] >= 1.2 else 0.35,
                              None, "Drainage system (this file's own model)")
                draw(d, "model", p["pts"], lay, is_closed(p["pts"]), linetype(p["dash"]), p["fill"], xf)
    fields = {k: v for k, v in dig["fields"].items() if not k.startswith("_")}
    size = {"size": "ANSI_B"} if not (dig["portrait"] or dig.get("oversize")) else {
        "width_in": dig["sheet_size"][0], "height_in": dig["sheet_size"][1]}
    if dig["template"]:
        d.run("create_sheet", {"name": sheet, **size, "title_block_template": dig.get("template_name", "wfl")})
        tb = dict(fields)
        if not dig.get("title_box"):
            tb.pop("sheet_title", None)       # no title box on this sheet (plan-profile)
        d.run("fill_title_block", {"sheet": sheet, "fields": tb})
    else:
        d.run("create_sheet", {"name": sheet, **size, "title_block_template": "none"})
    if plan:
        x0, y0, x1, y1 = dig["plan_rect"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d.run("create_viewport", {"sheet": sheet, "center_paper": [cx, cy], "width_in": x1 - x0,
                                  "height_in": y1 - y0, "model_center": xf.to_model((cx, cy)),
                                  "feet_per_inch": dig["fpi"], "rotation_deg": dig["twist"]})
    # ---------------------------------------------------- sheet linework
    S = lambda nm, mm, desc: d.layer(nm, mm, None, desc)
    sheet_dests = ("sheet:line", "sheet:match", "sheet:north", "sheet:squiggle", "sheet:arrow",
                   "sheet:tag", "sheet:glyph")
    for g in fill_groups([p for p in dig["paths"] if p["dest"] in sheet_dests or
                          (p["dest"] == "title" and not dig["template"])]):
        draw_filled(d, sheet, g, S("S_FILL", 0.13, "Filled shapes"))
    for p in dig["paths"]:
        if p.get("_in_group"):
            continue
        dest = p["dest"]
        if dest in sheet_dests or (dest == "title" and not dig["template"]):
            mm = snap_mm(p["lw"], 1.0)
            nm = {"sheet:match": "S_ANNO_MATCH", "sheet:squiggle": "S_ANNO_CALLOUT",
                  "sheet:north": "S_ANNO_SYMB", "sheet:arrow": "S_ANNO_SYMB",
                  "sheet:tag": "S_ANNO_TAG", "title": "S_BORDER", "sheet:glyph": "S_TEXT"}.get(dest)
            lay = S(nm or f"S_LINE_{int(round(mm * 100)):03d}", mm, "Sheet linework")
            draw(d, sheet, p["pts"], lay, is_closed(p["pts"]), linetype(p["dash"]), p["fill"])
    # ---------------------------------------------------- lettering
    for r in dig["runs"]:
        k = r["kind"]
        if k in ("text", "match", "squiggle") or (k == "title" and not dig["template"]) \
                or (not plan and k in ("design-label", "topo-label", "align-text", "station")):
            lay = {"match": "S_ANNO_MATCH", "title": "S_BORDER"}.get(k, "S_ANNO_NOTE")
            text_in(d, sheet, r, S(lay, 0.25, "Sheet lettering"))
    # ---------------------------------------------------- callouts
    runs = {r["id"]: r for r in dig["runs"]}
    report = {"anchor": 0, "entity": 0, "point": 0}
    lay = S("S_ANNO_CALLOUT", 0.18, "Callouts")
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
        params = {"space": sheet, "position": list(elbow if rotated else outer),
                  "content": c["text"], "height": h,
                  "landing": 0.0 if rotated else math.dist(outer, elbow),
                  "arrow": bool(c.get("arrow")), "arrow_size": 0.08, "layer": lay}
        if rotated:
            d.run("draw_line", {"space": sheet, "start": list(elbow), "end": list(outer), "layer": lay})
        how = None
        m = ANCHOR.search(c["text"])
        if plan and m and m.group(1).strip() in aligned:
            station = int(m.group(2)) * 100 + float(m.group(3))
            q = d.s.query("station_to_xy", {"alignment": f"ALI:{m.group(1).strip()}", "station": station,
                                            "offset": 0.0, "sheet": sheet})
            if q.get("ok") and q.get("on_sheet") and math.dist(q["on_sheet"]["sheet_point"], tip) < 0.05:
                params.update({"target_anchor": {"station": station, "offset": 0.0},
                               "alignment": f"ALI:{m.group(1).strip()}"})
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
            for k in ("target_anchor", "alignment", "target_entity", "at"):
                params.pop(k, None)
            params["target"] = list(tip)
            how = "point"
            r = d.run("place_callout", params)
        report[how] += 1
        # the callout's text entity letters its head line where the sheet does; the
        # lines under it are lettered as the sheet letters them (their own sizes and
        # spacing), so the note reads as published while the callout keeps the
        # whole note for its anchor
        for eid in r.get("created") or []:
            ent = d.ask("get_entity", {"id": eid}).get("entity", {})
            if ent.get("type") == "text":
                top = lines[0]
                d.run("modify_entity", {"id": eid, "changes": {
                    "content": top["text"], "position": [top["x"], top["y"] + h],
                    "halign": "left", "valign": "top", "rotation_deg": top["rot"]}})
        for line in lines[1:]:
            text_in(d, sheet, line, lay)
        for p in branches:
            draw(d, sheet, p["pts"], lay)
    d.save(path)
    return path, sheet, report


def build(dig, out, naming=None):
    naming = naming or Naming()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names = naming.names_for(dig)
    title = (f"{naming.name.upper()} sample plan {dig['id']}: sheet {names[2]} "
             f"{dig['fields'].get('sheet_title', '').replace(chr(10), ' ')}").strip()
    bases = build_bases(dig, out, names, title, naming) if dig["kind"] == "plan" else {}
    path, sheet, report = build_sheet(dig, out, names, title, bases, naming)
    return {"sheet_file": path.name, "sheet": sheet, "prefix": names[0], "suffix": names[1],
            "prefix_how": names[3], "suffix_in_manual": naming.in_manual(names[1]),
            "inline": sorted(bases.get("_inline", {})),
            "bases": {k: v.name for k, v in bases.items() if not k.startswith("_")},
            "alignments": bases.get("_aligns", []), "callouts": report}
