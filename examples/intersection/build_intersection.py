"""Draft the MAIN ST / CROSS AVE intersection as a RoadDraft model file.

Two alignments crossing at 90 degrees, drafted from the design data in
intersection_design.py: through lanes and a striped median from constant
offsets of each alignment, turn pockets and bay tapers from stations on them,
50 ft curb returns fitted between the curb lines, 6 ft curb and gutter carried
around the corners, and a curb ramp on each leg of each corner.

Nothing here is a typed coordinate. Every line, arc and block lands where
station_to_xy puts it, and every offset run is anchored to the alignment and
the offset it came from, so moving the design moves the drawing.

    python examples/intersection/build_intersection.py [--out DIR]
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import intersection_design as D                                 # noqa: E402
from roaddraft import Session                                   # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output"
DOC_NAME = "Main-Cross-Intersection.model"
PLOT_SCALE = 40.0                    # 1" = 40', the scale this is drafted for
RAMP_SETBACK = 16.0                  # ramp centre, along the curb from the return

LAYERS = [
    ("V-ALIGN-CNTR", "red", "center", 0.35, "Alignment centerlines"),
    ("V-ROAD-EOP", "black", "continuous", 0.50, "Edge of pavement / face of curb"),
    ("V-ROAD-CURB", "black", "continuous", 0.25, "Back of 6 ft curb and gutter"),
    ("V-ROAD-RAMP", "black", "continuous", 0.25, "Curb ramps"),
    ("V-STRP-LANE", "black", "dashed", 0.18, "Lane lines"),
    ("V-STRP-MEDN", "black", "continuous", 0.18, "Median edge lines and hatching"),
    ("V-STRP-TURN", "black", "continuous", 0.18, "Turn pocket edges and bay tapers"),
    ("V-ANNO-STAT", "black", "continuous", 0.13, "Stationing"),
    ("V-ANNO-DIMS", "black", "continuous", 0.18, "Dimensions"),
    ("V-ANNO-TEXT", "black", "continuous", 0.18, "Labels"),
]

# (name, main_side, cross_side): +1 is right of stationing, so on MAIN ST
# (eastbound) +1 is south, and on CROSS AVE (northbound) +1 is east.
CORNERS = [("NE", -1, +1), ("SE", +1, +1), ("SW", +1, -1), ("NW", -1, -1)]


def curb_offset(road, side, leg_sign):
    """Signed offset of the curb face on one side of one leg.

    A leg carries a right-turn lane on the right of the traffic approaching the
    intersection on it, which is the side away from the leg: `side == -leg_sign`.
    """
    widened = side == -leg_sign
    return side * (D.turn_edge(road) if widened else D.thru_edge(road))


def build(out_dir=OUT, quiet=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = Session(project_name="MAIN ST / CROSS AVE Intersection", out_dir=out_dir)
    say = (lambda *a: None) if quiet else print

    def run(name, params):
        r = s.execute(name, params)
        if not r["ok"]:
            raise SystemExit(f"{name} failed:\n{json.dumps(r['error'], indent=2)}")
        for w in r["warnings"]:
            say(f"    warning: {w}")
        return r

    def ask(name, params=None):
        r = s.query(name, params or {})
        if not r["ok"]:
            raise SystemExit(f"{name} failed: {r['error']}")
        return r

    def at(road, station, offset=0.0):
        return ask("station_to_xy", {"alignment": road, "station": station,
                                     "offset": offset})["point"]

    def offset_run(road, offset, sta0, sta1, layer):
        lo, hi = sorted((sta0, sta1))
        return run("draw_offset", {"alignment": road, "offsets": [offset],
                                   "station_range": [lo, hi], "layer": layer})

    def line(road, sta0, off0, sta1, off1, layer):
        return run("draw_line", {"space": "model", "layer": layer,
                                 "start": at(road, sta0, off0),
                                 "end": at(road, sta1, off1)})

    def hatch(road, sta0, sta1, off_lo, off_hi, spacing, layer):
        lo, hi = sorted((sta0, sta1))
        width = abs(off_hi - off_lo)
        n, station = 0, lo + spacing / 2
        while station + width <= hi:
            line(road, station, off_lo, station + width, off_hi, layer)
            station += spacing
            n += 1
        return n

    run("set_meta", {"updates": {"description":
        "MAIN ST / CROSS AVE: two alignments at 90 degrees, 3 and 2 through "
        "lanes each way at 12 ft, 16 ft striped median, 300 ft turn pockets "
        "behind 120 ft bay tapers, 50 ft curb returns, 6 ft curb and gutter, "
        "curb ramps. Drafted at 1\" = 40'."}})

    say("== layers")
    for name, color, linetype, lw, desc in LAYERS:
        run("create_layer", {"name": name, "color": color, "linetype": linetype,
                             "lineweight_mm": lw, "description": desc})
    run("set_annotation_scale", {"scale": PLOT_SCALE})

    # ------------------------------------------------------------ alignments
    say("== alignments")
    for road, spec in D.ROADS.items():
        a = math.radians(spec["azimuth"])
        u = (math.sin(a), math.cos(a))
        back = spec["back_leg"]
        ahead = spec["ahead_leg"]
        begin = [D.INTERSECTION[0] - u[0] * back, D.INTERSECTION[1] - u[1] * back]
        end = [D.INTERSECTION[0] + u[0] * ahead, D.INTERSECTION[1] + u[1] * ahead]
        run("create_alignment", {"name": road, "begin_station": spec["begin_station"],
                                 "pis": [begin, end], "description": spec["description"]})
        run("draw_alignment", {"alignment": road, "layer": "V-ALIGN-CNTR"})
    skew = abs(D.ROADS["MAIN-ST"]["azimuth"] - D.ROADS["CROSS-AVE"]["azimuth"])
    ix = ask("xy_to_station", {"alignment": "CROSS-AVE", "point": list(D.INTERSECTION)})
    say(f"    MAIN-ST x CROSS-AVE at {ix['station_text']} / "
        f"{ask('xy_to_station', {'alignment': 'MAIN-ST', 'point': list(D.INTERSECTION)})['station_text']}"
        f", skew {skew:g}°")

    # --------------------------------------------------------- corner layout
    corners = {}
    for name, ms, cs in CORNERS:
        main_off = curb_offset("MAIN-ST", ms, leg_sign=cs)
        cross_off = curb_offset("CROSS-AVE", cs, leg_sign=-ms)
        corners[(ms, cs)] = dict(
            name=name, main_off=main_off, cross_off=cross_off,
            main_bcr=D.intersection_station("MAIN-ST")
            + cs * (abs(cross_off) + D.CURB_RETURN_R),
            cross_bcr=D.intersection_station("CROSS-AVE")
            - ms * (abs(main_off) + D.CURB_RETURN_R))

    def bcr(road, side, leg_sign):
        if road == "MAIN-ST":
            return corners[(side, leg_sign)]["main_bcr"]
        return corners[(-leg_sign, side)]["cross_bcr"]

    # ------------------------------------------------------- through striping
    say("== through lanes and median")
    for road in D.ROADS:
        gap = D.striping_gap(road)
        ix_sta = D.intersection_station(road)
        legs = [(D.ROADS[road]["begin_station"], ix_sta - gap),
                (ix_sta + gap, D.end_station(road))]
        for sta0, sta1 in legs:
            for off in (-D.MEDIAN_HALF, D.MEDIAN_HALF):
                offset_run(road, off, sta0, sta1, "V-STRP-MEDN")
            for off in D.lane_lines(road):
                offset_run(road, -off, sta0, sta1, "V-STRP-LANE")
                offset_run(road, off, sta0, sta1, "V-STRP-LANE")
        say(f"    {road}: {D.ROADS[road]['thru_lanes']} x {D.LANE:g}' through lanes "
            f"each way, {2 * D.MEDIAN_HALF:g}' striped median, "
            f"curb face at {D.thru_edge(road):g}'")

    # ---------------------------------------------------------- curb and gutter
    say("== curb and gutter")
    for road in D.ROADS:
        far = {-1: D.ROADS[road]["begin_station"], +1: D.end_station(road)}
        for leg_sign in (-1, +1):
            for side in (-1, +1):
                start = bcr(road, side, leg_sign)
                base = side * D.thru_edge(road)
                back = base + side * D.CURB_WIDTH
                if side != -leg_sign:                       # departure: straight run
                    offset_run(road, base, start, far[leg_sign], "V-ROAD-EOP")
                    offset_run(road, back, start, far[leg_sign], "V-ROAD-CURB")
                    continue
                # approach: a right-turn lane, its bay taper, then the normal curb
                rt = side * D.turn_edge(road)
                rt_back = rt + side * D.CURB_WIDTH
                storage = start + leg_sign * D.TURN_STORAGE
                taper = storage + leg_sign * D.BAY_TAPER
                offset_run(road, rt, start, storage, "V-ROAD-EOP")
                offset_run(road, rt_back, start, storage, "V-ROAD-CURB")
                line(road, taper, base, storage, rt, "V-ROAD-EOP")
                line(road, taper, back, storage, rt_back, "V-ROAD-CURB")
                offset_run(road, base, taper, far[leg_sign], "V-ROAD-EOP")
                offset_run(road, back, taper, far[leg_sign], "V-ROAD-CURB")
                # the old curb line carries on as the right-turn lane line
                limit = D.intersection_station(road) + leg_sign * D.striping_gap(road)
                offset_run(road, base, taper, limit, "V-STRP-LANE")

    # ------------------------------------------------------------ curb returns
    say("== curb returns")
    return_arcs = {}
    for (ms, cs), c in corners.items():
        centre = at("MAIN-ST", c["main_bcr"],
                    ms * (abs(c["main_off"]) + D.CURB_RETURN_R))
        p_main = at("MAIN-ST", c["main_bcr"], c["main_off"])
        p_cross = at("CROSS-AVE", c["cross_bcr"], c["cross_off"])
        a_main = math.degrees(math.atan2(p_main[1] - centre[1], p_main[0] - centre[0]))
        a_cross = math.degrees(math.atan2(p_cross[1] - centre[1], p_cross[0] - centre[0]))
        # the quarter that closes the corner is the 90 deg sweep, not the 270
        if abs((a_main - a_cross) % 360.0 - 90.0) < 1e-6:
            start_a, end_a = a_cross, a_main
        else:
            start_a, end_a = a_main, a_cross
        face = run("draw_arc", {"space": "model", "center": centre,
                                "radius": D.CURB_RETURN_R, "start_angle_deg": start_a,
                                "end_angle_deg": end_a, "layer": "V-ROAD-EOP"})
        run("draw_arc", {"space": "model", "center": centre,
                         "radius": D.CURB_RETURN_R - D.CURB_WIDTH,
                         "start_angle_deg": start_a, "end_angle_deg": end_a,
                         "layer": "V-ROAD-CURB"})
        return_arcs[c["name"]] = face["created"][0]
        say(f"    {c['name']}: R={D.CURB_RETURN_R:g}' from MAIN-ST "
            f"{_sta(ask, 'MAIN-ST', c['main_bcr'])} {_off(c['main_off'])} to CROSS-AVE "
            f"{_sta(ask, 'CROSS-AVE', c['cross_bcr'])} {_off(c['cross_off'])}")

    # -------------------------------------------------------- turn pockets
    say("== turn pockets")
    for approach in D.APPROACHES:
        road, sign = approach["road"], approach["sign"]
        limit, pocket, taper = D.approach_stations(road, sign)
        pocket_off = sign * D.pocket_edge()
        median_off = sign * D.MEDIAN_HALF
        line(road, taper, median_off, pocket, pocket_off, "V-STRP-TURN")
        offset_run(road, pocket_off, pocket, limit, "V-STRP-TURN")
        hatch(road, pocket, limit, pocket_off, -median_off, 10.0, "V-STRP-MEDN")
        far = (D.ROADS[road]["begin_station"] if sign > 0 else D.end_station(road))
        n = hatch(road, far, taper, -D.MEDIAN_HALF, D.MEDIAN_HALF, 20.0, "V-STRP-MEDN")
        say(f"    {approach['name']}: left pocket {D.TURN_STORAGE:g}' storage "
            f"behind a {D.BAY_TAPER:g}' bay taper, {_sta(ask, road, taper)} to "
            f"{_sta(ask, road, limit)}; right-turn lane {D.TURN_STORAGE:g}' + "
            f"{D.BAY_TAPER:g}'; {n} median hatch lines")

    # ------------------------------------------------------------ curb ramps
    say("== curb ramps")
    w = D.CURB_WIDTH
    flare = D.CURB_HEIGHT * 10.0          # 1:10 along the curb, so 5 ft for a 6 in curb
    run("define_block", {
        "name": "CURB-RAMP", "base_point": [0, 0],
        "description": f"Perpendicular curb ramp: {2 * D.RAMP_HALF:g} ft ramp "
                       f"across the {w:g} ft curb and gutter, 1:10 flared sides, "
                       f"detectable warning surface at the gutter. Base point at "
                       f"the face of curb, +Y away from the street.",
        "entities": [
            # the ramp itself, open at the curb where the curb line already runs
            {"type": "polyline", "vertices": [[-D.RAMP_HALF, 0], [-D.RAMP_HALF, w],
                                              [D.RAMP_HALF, w], [D.RAMP_HALF, 0]]},
            # flared sides: widest at the curb, where the whole curb height is
            # taken up, and closing to nothing at the top of the ramp
            {"type": "polyline", "vertices": [[-D.RAMP_HALF, w],
                                              [-D.RAMP_HALF - flare, 0]]},
            {"type": "polyline", "vertices": [[D.RAMP_HALF, w],
                                              [D.RAMP_HALF + flare, 0]]},
            # detectable warning surface, 2 ft deep at the bottom of the ramp
            {"type": "polyline", "vertices": [[-D.RAMP_HALF, 0], [D.RAMP_HALF, 0],
                                              [D.RAMP_HALF, 2], [-D.RAMP_HALF, 2]],
             "closed": True},
        ]})
    for (ms, cs), c in corners.items():
        for road, station, off in (
                ("MAIN-ST", c["main_bcr"] + cs * RAMP_SETBACK, c["main_off"]),
                ("CROSS-AVE", c["cross_bcr"] - ms * RAMP_SETBACK, c["cross_off"])):
            q = ask("station_to_xy", {"alignment": road, "station": station,
                                      "offset": off})
            a = math.radians(q["azimuth_deg"])
            outward = (math.copysign(1.0, off) * math.cos(a),
                       -math.copysign(1.0, off) * math.sin(a))
            run("insert_block", {
                "space": "model", "block_name": "CURB-RAMP", "position": q["point"],
                "rotation_deg": math.degrees(math.atan2(-outward[0], outward[1])),
                "layer": "V-ROAD-RAMP"})
    say(f"    8 ramps, two per corner: {2 * D.RAMP_HALF:g}' ramp across the {w:g}' "
        f"curb and gutter, {flare:g}' flares")

    # ------------------------------------------------------------ annotation
    say("== annotation")
    for road in D.ROADS:
        run("annotate_stationing", {"space": "model", "alignment": road,
                                    "interval": 100.0, "include_pc_pt": False,
                                    "layer": "V-ANNO-STAT"})
        run("place_label", {
            "space": "model", "alignment": road, "kind": "custom",
            "anchor": D.ROADS[road]["begin_station"] + 250.0,
            "content": f'"{road}" LINE', "side": "left", "label_offset": 14.0,
            "height": 7.0, "layer": "V-ANNO-TEXT"})

    say("== dimensions")
    dims = [
        ("MAIN-ST", 1050.0, D.MEDIAN_HALF, 1050.0, D.MEDIAN_HALF + D.LANE, 1020.0,
         "through lane"),
        ("MAIN-ST", 1150.0, -D.MEDIAN_HALF, 1150.0, D.MEDIAN_HALF, 1120.0,
         "striped median"),
        ("MAIN-ST", 1250.0, D.thru_edge("MAIN-ST"),
         1250.0, D.thru_edge("MAIN-ST") + D.CURB_WIDTH, 1220.0, "curb and gutter"),
    ]
    for road, s0, o0, s1, o1, sline, what in dims:
        r = run("place_dimension", {
            "space": "model", "kind": "linear", "p1": at(road, s0, o0),
            "p2": at(road, s1, o1), "line_point": at(road, sline, (o0 + o1) / 2),
            "layer": "V-ANNO-DIMS"})
        say(f"    {what}: {r['message'].split('(')[1].split(')')[0]}")
    limit, pocket, taper = D.approach_stations("MAIN-ST", +1)
    for a, b, off, what in ((pocket, limit, -62.0, "left pocket storage"),
                            (taper, pocket, -62.0, "bay taper")):
        r = run("place_dimension", {
            "space": "model", "kind": "aligned", "p1": at("MAIN-ST", a, -4.0),
            "p2": at("MAIN-ST", b, -4.0),
            "line_point": at("MAIN-ST", (a + b) / 2, off), "layer": "V-ANNO-DIMS"})
        say(f"    {what}: {r['message'].split('(')[1].split(')')[0]}")
    r = run("place_dimension", {
        "space": "model", "kind": "radius", "of_entity": return_arcs["SW"],
        "line_point": at("MAIN-ST", 1660.0, 86.0), "layer": "V-ANNO-DIMS"})
    say(f"    SW curb return: {r['message'].split('(')[1].split(')')[0]}")

    path = ask("save_document", {"path": str(out_dir / f"{DOC_NAME}.rdraft")})["path"]
    summary = ask("get_document_state", {})["summary"]
    say(f"\nmodel  {Path(path).name}: {summary['model_entity_count']:,} entities on "
        f"{len(summary['layers'])} layers, {len(summary['alignments'])} alignments, "
        f"{summary['journal_length']:,} commands")
    return Path(path), s


def _sta(ask, road, station):
    return ask("station_to_xy", {"alignment": road, "station": station})["station_text"]


def _off(value):
    return f"{abs(value):g}' {'RT' if value > 0 else 'LT'}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
