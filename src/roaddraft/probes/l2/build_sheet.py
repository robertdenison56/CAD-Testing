"""Build the plan-sheet file: Caltrans sheet L-2, LAYOUT, 1" = 50'.

This document owns nothing about the road.  It *references* the design model
(build_model.py) and composes one sheet over it: the Caltrans border and title
block, a 1" = 50' viewport turned to the plan's view twist, and the annotation
that belongs to this sheet -- the notes, the match lines to L-1 and L-3, the
curve number bubbles, the CURVE DATA table, the north arrow, the place names,
and the fourteen station-and-offset callouts.

Every callout names a station and an offset on "SR70", and the leader is aimed
at the point the *referenced* design model puts there -- so the arrow lands on
the geometry the text describes rather than on a typed coordinate.

    python -m roaddraft.probes.l2.build_sheet --out DIR   (after build_model)
"""
import argparse
import json
import math
from pathlib import Path

from roaddraft import Session
from roaddraft.probes.l2 import sheet_content as C
from roaddraft.probes.l2 import sr70_geometry as G

SHEET_NAME = "SR70-Bear-Creek.sheets"
MODEL_FILE = "SR70-Bear-Creek.model.rdraft"
SHEET = "L-2"
REF = "DESIGN"                       # the design model, as attached here

LAYERS = [
    ("S-ANNO-NOTE", 0.25, "Sheet notes and place names"),
    ("S-ANNO-CALL", 0.25, "Station-and-offset callouts"),
    ("S-ANNO-MTCH", 0.50, "Match lines"),
    ("S-ANNO-CURV", 0.25, "Curve number bubbles and the curve data table"),
    ("S-ANNO-SYMB", 0.25, "North arrow and direction of travel"),
]


def build(out_dir, quiet=False):
    out_dir = Path(out_dir)
    session = Session(project_name="03-But-70 Bear Creek Bridge Replacement",
                      out_dir=out_dir)
    say = (lambda *a: None) if quiet else print

    def run(name, params):
        r = session.execute(name, params)
        if not r["ok"]:
            raise SystemExit(f"{name} failed:\n{json.dumps(r['error'], indent=2)}")
        for w in r["warnings"]:
            say(f"    warning: {w}")
        return r

    def ask(name, params=None):
        r = session.query(name, params or {})
        if not r["ok"]:
            raise SystemExit(f"{name} failed: {r['error']}")
        return r

    def at(station, offset=0.0):
        """Sheet position of a station/offset on the referenced alignment. The
        engine sees it through the viewport -- scale and twist included."""
        q = ask("station_to_xy", {"alignment": f"{REF}:{G.ALIGNMENT}",
                                  "station": station, "offset": offset,
                                  "sheet": SHEET})
        return q["on_sheet"]["sheet_point"], q

    def under(x, y):
        """The model point a spot on the paper is looking at."""
        return ask("sheet_to_model", {"sheet": SHEET, "point": [x, y]})["point"]

    def road_angle(station):
        """How the roadway runs across the paper at a station, degrees CCW."""
        q = ask("station_to_xy", {"alignment": f"{REF}:{G.ALIGNMENT}",
                                  "station": station})
        return 90.0 - q["azimuth_deg"] + G.TWIST_DEG

    run("set_meta", {"updates": {
        "description": "03-3H5404  EA 0318000012  Bear Creek Bridge replacement. "
                       "Plan sheets; the design model is referenced, not owned."}})

    say("== reference the design model")

    def clip_polygon(session):
        """What this sheet shows of the design: everything between MATCH LINE
        (L-1) and MATCH LINE (L-3), out to well beyond the right of way.  The
        design model runs the length of the project; each sheet displays its
        own stretch, cut square on the match lines the way the plans read."""
        from roaddraft.api.session import Session as _S
        model = _S.load(out_dir / MODEL_FILE, out_dir=out_dir)
        corners = []
        for station, offset in ((G.MATCH_W, -900.0), (G.MATCH_E, -900.0),
                                (G.MATCH_E, 500.0), (G.MATCH_W, 500.0)):
            q = model.query("station_to_xy", {"alignment": G.ALIGNMENT,
                                              "station": station, "offset": offset})
            corners.append([round(v, 3) for v in q["point"]])
        return corners

    # Save first, so the relative path resolves against the sheet file's own
    # folder -- the way it will whenever the plans are opened again.
    out_dir.mkdir(parents=True, exist_ok=True)
    doc_path = out_dir / f"{SHEET_NAME}.rdraft"
    ask("save_document", {"path": str(doc_path)})
    r = run("attach_reference", {"name": REF, "path": MODEL_FILE, "space": "model",
                                 "clip": clip_polygon(session)})
    say(f"    {r['message']}")
    aligns = ask("list_alignments", {"include_references": True})["alignments"]
    say(f"    alignments visible: {', '.join(a['name'] for a in aligns)}")

    say("== sheet")
    run("create_sheet", {"name": SHEET, "size": "ANSI_D",
                         "title_block_template": "caltrans"})
    run("fill_title_block", {"sheet": SHEET, "fields": C.TITLE_BLOCK})
    r = run("create_viewport", {
        "sheet": SHEET, "center_paper": list(G.VIEWPORT_CENTER_PAPER),
        "width_in": G.VIEWPORT_W, "height_in": G.VIEWPORT_H,
        "model_center": list(G.VIEWPORT_CENTER_MODEL),
        "feet_per_inch": G.FEET_PER_INCH, "rotation_deg": G.TWIST_DEG})
    say(f"    {r['message']}")
    for name, lw, desc in LAYERS:
        run("create_layer", {"name": name, "color": "black", "lineweight_mm": lw,
                             "description": desc})

    say("== notes and place names")
    for x, y, h, content in C.NOTES:
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-NOTE"})
    for x, y, h, content in C.PLACE_NAMES:
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-NOTE"})
    for x, y, h, rot, content in C.FEATURE_NAMES:
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "rotation_deg": rot, "halign": "left",
                           "valign": "bottom", "layer": "S-ANNO-NOTE"})
    for x, y, h, content in C.ROAD_NAMES:
        station = ask("xy_to_station", {"alignment": f"{REF}:{G.ALIGNMENT}",
                                        "point": under(x, y)})
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "rotation_deg": road_angle(station["station"]),
                           "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-NOTE"})
    for x, y, h, content in C.CATCH_LABELS:
        station = ask("xy_to_station", {"alignment": f"{REF}:{G.ALIGNMENT}",
                                        "point": under(x, y)})
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "rotation_deg": road_angle(station["station"]),
                           "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-NOTE"})
    for x, y, h, rot, content in C.SECTION_LABELS:
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": h, "rotation_deg": rot, "halign": "left",
                           "valign": "bottom", "layer": "S-ANNO-NOTE"})
    for x, y, content, ax0, ax1, ay in C.TRAVEL:
        run("place_text", {"space": SHEET, "position": [x, y], "content": content,
                           "height": 0.152, "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-SYMB"})
        run("draw_line", {"space": SHEET, "start": [ax0, ay], "end": [ax1, ay],
                          "layer": "S-ANNO-SYMB"})
        head = 0.06 if ax1 > ax0 else -0.06
        run("draw_polyline", {"space": SHEET, "layer": "S-ANNO-SYMB", "vertices": [
            [ax1, ay], [ax1 - head, ay + 0.035], [ax1 - head, ay - 0.035]],
            "closed": True})

    say("== match lines")
    for station, tag, tx, ty, th, rot, back, ahead in C.MATCH_LINES:
        a, _ = at(station, back)
        b, _ = at(station, ahead)
        run("draw_line", {"space": SHEET, "start": list(a), "end": list(b),
                          "layer": "S-ANNO-MTCH"})
        run("place_text", {"space": SHEET, "position": [tx, ty],
                           "content": f"MATCH LINE  {tag}", "height": th,
                           "rotation_deg": rot, "halign": "left", "valign": "bottom",
                           "layer": "S-ANNO-MTCH"})
        say(f"    MATCH LINE {tag} at {ask('station_to_xy', {'alignment': f'{REF}:{G.ALIGNMENT}', 'station': station})['station_text']}")

    say("== curve bubbles")
    for curve, x, y in C.BUBBLES:
        run("draw_circle", {"space": SHEET, "center": [x, y], "radius": 0.200,
                            "layer": "S-ANNO-CURV"})
        run("place_text", {"space": SHEET, "position": [x, y], "content": str(curve),
                           "height": 0.140, "halign": "center", "valign": "middle",
                           "layer": "S-ANNO-CURV"})
        tip = _road_below(ask, x, y)
        run("draw_line", {"space": SHEET, "start": [x, y - 0.200], "end": list(tip),
                          "layer": "S-ANNO-CURV"})

    say("== callouts")
    for entry in C.CALLOUTS:
        station, offset, x, y, content = entry[:5]
        height = entry[5] if len(entry) > 5 else 0.140
        lines = content.count("\n") + 1
        # aimed the way the plan reads it -- a station and an offset on the
        # referenced alignment -- and seen through the viewport by the engine
        _, q = at(station, offset)
        run("place_callout", {
            "space": SHEET, "alignment": f"{REF}:{G.ALIGNMENT}",
            "target_anchor": {"station": station, "offset": offset},
            "position": [x, y - (lines - 1) * 0.210 / 2 + height / 2],
            "content": content, "height": height, "landing": 0.30,
            "arrow_size": 0.11, "layer": "S-ANNO-CALL"})
        say(f"    {q['station_text']} {abs(offset):.2f}' "
            f"{'RT' if offset > 0 else 'LT'}  {content.splitlines()[0]}")

    say("== curve data table")
    curves = ask("get_design_data", {"kind": "curves",
                                     "alignment": f"{REF}:{G.ALIGNMENT}"})["rows"]
    t = C.CURVE_TABLE
    rows = [[str(n), f"{row['radius']:.0f}'", row["delta_dms"],
             f"{row['tangent']:.2f}'", f"{row['length']:.2f}'"]
            for n, row in zip(sorted(G.DELTA), curves)]
    run("place_table", {
        "space": SHEET, "position": list(t["position"]), "title": t["title"],
        "columns": [{"header": h, "width": w} for h, w in t["columns"]],
        "rows": rows, "text_height": t["text_height"], "layer": "S-ANNO-CURV"})
    for n, row in zip(sorted(G.DELTA), curves):
        say(f"    curve {n}: R={row['radius']:.0f}'  {row['delta_dms']}  "
            f"T={row['tangent']:.2f}'  L={row['length']:.2f}'")

    say("== north arrow")
    entities = []
    for kind, data in C.NORTH_ARROW:
        if kind == "circle":
            entities.append({"type": "circle", "center": [0, 0], "radius": data})
        else:
            entities.append({"type": "line",
                             "start": _turn(data[0], -G.TWIST_DEG),
                             "end": _turn(data[1], -G.TWIST_DEG)})
    run("define_block", {"name": "NORTH-ARROW", "base_point": [0, 0],
                         "entities": entities,
                         "description": "Plan north arrow, drawn true north up"})
    run("insert_block", {"space": SHEET, "block_name": "NORTH-ARROW",
                         "position": list(C.NORTH_ARROW_AT),
                         "rotation_deg": G.TWIST_DEG, "layer": "S-ANNO-SYMB"})

    path = ask("save_document", {"path": str(doc_path)})["path"]
    state = ask("get_sheet_state", {"sheet": SHEET})["sheet"]
    say(f"\nsheets {Path(path).name}: sheet {SHEET} "
        f"({len(state['entities'])} annotation entities, "
        f"{len(state['viewports'])} viewport at 1\"={G.FEET_PER_INCH:g}', "
        f"twist {G.TWIST_DEG:+.3f}°), referencing {MODEL_FILE}")
    return Path(path), session


def _turn(p, deg):
    a = math.radians(deg)
    return [p[0] * math.cos(a) - p[1] * math.sin(a),
            p[0] * math.sin(a) + p[1] * math.cos(a)]


def _road_below(ask, x, y):
    """Where a bubble's leader meets the centerline: the station whose sheet
    position sits directly below (or above) the bubble."""
    lo, hi = G.MATCH_W - 150, G.MATCH_E + 150
    step, best_pt = 50.0, None
    while step >= 0.5:
        best, at_station = None, lo
        station = lo
        while station <= hi + 1e-9:
            pt = ask("station_to_xy", {
                "alignment": f"{REF}:{G.ALIGNMENT}", "station": station,
                "sheet": SHEET})["on_sheet"]["sheet_point"]
            d = abs(pt[0] - x)
            if best is None or d < best:
                best, at_station, best_pt = d, station, pt
            station += step
        lo, hi, step = at_station - step, at_station + step, step / 5.0
    return best_pt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
