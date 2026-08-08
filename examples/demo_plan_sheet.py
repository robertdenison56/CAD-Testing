"""Draft a small roadway plan sheet end-to-end through the Session tool
surface — the exact JSON commands an AI agent would issue.

Alignment: tangent -> 30-degree circular curve (R=800') -> tangent, stationed
from 10+00. Model space carries centerline, edges of pavement, station ticks
and labels; sheet C-101 (ANSI D) carries a 1"=50' viewport, north arrow, curve
table, notes, and a filled title block.

Station/bearing values here are hand-computed in this script; the procedural
design generator + ground-truth label engine is the next milestone (PRD
Phase 1) and will replace them.

Run:  python examples/demo_plan_sheet.py
Outputs land in examples/output/.
"""
import json
import math
from pathlib import Path

from roaddraft import Session
from roaddraft.core.units import format_station

OUT = Path(__file__).parent / "output"

# ------------------------------------------------------- alignment geometry
BEGIN_STA = 1000.0          # station 10+00 at the POB
P0 = [1000.0, 1000.0]       # POB, heading due east
T1_LEN = 600.0              # tangent 1 length -> PC
R = 800.0                   # curve radius (left)
DELTA = 30.0                # central angle, degrees
CENTER = [1600.0, 1800.0]   # curve center (left of travel)
L_CURVE = R * math.radians(DELTA)            # 418.879'
T_DIST = R * math.tan(math.radians(DELTA / 2))  # 214.359'
T2_LEN = 500.0
PC_D, PT_D = T1_LEN, T1_LEN + L_CURVE
END_D = PT_D + T2_LEN


def point_at(d):
    """Centerline point at distance d from the POB."""
    if d <= PC_D:
        return [P0[0] + d, P0[1]]
    if d <= PT_D:
        ang = -90.0 + math.degrees((d - PC_D) / R)
        return [CENTER[0] + R * math.cos(math.radians(ang)),
                CENTER[1] + R * math.sin(math.radians(ang))]
    pt = point_at(PT_D)
    return [pt[0] + (d - PT_D) * math.cos(math.radians(30.0)),
            pt[1] + (d - PT_D) * math.sin(math.radians(30.0))]


def dir_at(d):
    """Tangent direction (degrees CCW from +X) at distance d."""
    if d <= PC_D:
        return 0.0
    if d <= PT_D:
        return math.degrees((d - PC_D) / R)
    return 30.0


def offset(p, angle_deg, dist):
    a = math.radians(angle_deg)
    return [p[0] + dist * math.cos(a), p[1] + dist * math.sin(a)]


def sta(d):
    return format_station(BEGIN_STA + d)


def main():
    session = Session(project_name="SR 100 Resurfacing Demo", out_dir=OUT)

    def run(name, params):
        result = session.execute(name, params)
        if not result["ok"]:
            raise SystemExit(f"{name} failed:\n"
                             f"{json.dumps(result['error'], indent=2)}")
        for warning in result["warnings"]:
            print(f"    warning: {warning}")
        return result

    # ------------------------------------------------------------- layers
    print("== layers")
    run("create_layer", {"name": "V-ALIGN-CNTR", "color": "red",
                         "linetype": "center", "lineweight_mm": 0.35,
                         "description": "Roadway centerline"})
    run("create_layer", {"name": "V-ROAD-EDGE", "color": "black",
                         "lineweight_mm": 0.5, "description": "Edge of pavement"})
    run("create_layer", {"name": "V-ROAD-STA", "color": "gray",
                         "lineweight_mm": 0.18, "description": "Station ticks"})
    run("create_layer", {"name": "V-ANNO-TEXT", "color": "black",
                         "lineweight_mm": 0.25, "description": "Annotation"})

    # -------------------------------------------------- centerline + edges
    print("== centerline and pavement edges")
    pc, pt = point_at(PC_D), point_at(PT_D)
    end = point_at(END_D)
    cl = {"layer": "V-ALIGN-CNTR", "space": "model"}
    run("draw_line", {**cl, "start": P0, "end": pc})
    run("draw_arc", {**cl, "center": CENTER, "radius": R,
                     "start_angle_deg": -90.0, "end_angle_deg": -60.0})
    run("draw_line", {**cl, "start": pt, "end": end})

    edge = {"layer": "V-ROAD-EDGE", "space": "model"}
    for side in (+12.0, -12.0):
        run("draw_line", {**edge, "start": [P0[0], P0[1] + side],
                          "end": [pc[0], pc[1] + side]})
        run("draw_arc", {**edge, "center": CENTER, "radius": R - side,
                         "start_angle_deg": -90.0, "end_angle_deg": -60.0})
        p_start = offset(pt, 30.0 + 90.0, side)
        run("draw_line", {**edge, "start": p_start,
                          "end": offset(p_start, 30.0, T2_LEN)})

    # -------------------------------------------- station ticks and labels
    print("== stationing")
    d = 0.0
    while d <= END_D + 1e-6:
        p, ang = point_at(d), dir_at(d)
        run("draw_line", {"space": "model", "layer": "V-ROAD-STA",
                          "start": offset(p, ang + 90.0, -10.0),
                          "end": offset(p, ang + 90.0, 10.0)})
        run("place_text", {"space": "model", "layer": "V-ANNO-TEXT",
                           "position": offset(p, ang + 90.0, 16.0),
                           "content": sta(d), "height": 8.0,
                           "rotation_deg": ang, "halign": "center",
                           "valign": "bottom"})
        d += 100.0

    for d_key, label in ((PC_D, "PC"), (PT_D, "PT")):
        p, ang = point_at(d_key), dir_at(d_key)
        run("place_text", {"space": "model", "layer": "V-ANNO-TEXT",
                           "position": offset(p, ang - 90.0, 20.0),
                           "content": f"{label} {sta(d_key)}", "height": 9.0,
                           "rotation_deg": ang, "halign": "center",
                           "valign": "top"})

    run("place_text", {"space": "model", "layer": "V-ANNO-TEXT",
                       "position": offset(point_at(T1_LEN / 2), 90.0, 30.0),
                       "content": 'N 90°00\'00" E', "height": 9.0,
                       "halign": "center"})
    mid2 = point_at(PT_D + T2_LEN / 2)
    run("place_text", {"space": "model", "layer": "V-ANNO-TEXT",
                       "position": offset(mid2, 30.0 + 90.0, 30.0),
                       "content": 'N 60°00\'00" E', "height": 9.0,
                       "rotation_deg": 30.0, "halign": "center"})
    run("place_text", {"space": "model", "layer": "V-ANNO-TEXT",
                       "position": offset(point_at((PC_D + PT_D) / 2),
                                          dir_at((PC_D + PT_D) / 2) - 90.0, 45.0),
                       "content": "C-1", "height": 10.0, "halign": "center"})

    # ------------------------------------------------------------- sheet
    print("== sheet C-101")
    run("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    extents = session.query("get_extents", {"space": "model"})["extents"]
    model_center = [(extents[0] + extents[2]) / 2, (extents[1] + extents[3]) / 2]
    run("create_viewport", {"sheet": "C-101", "center_paper": [17.0, 11.7],
                            "width_in": 31.0, "height_in": 18.5,
                            "model_center": model_center, "feet_per_inch": 50.0})
    run("insert_block", {"space": "C-101", "block_name": "NORTH_ARROW",
                         "position": [31.6, 19.2], "scale": 0.9})
    run("place_table", {
        "space": "C-101", "position": [26.3, 8.3], "title": "CURVE DATA",
        "columns": [{"header": "CURVE", "width": 0.9},
                    {"header": "Δ", "width": 1.5},
                    {"header": "R", "width": 1.2},
                    {"header": "T", "width": 1.2},
                    {"header": "L", "width": 1.2}],
        "rows": [["C-1", '30°00\'00"', "800.00'",
                  f"{T_DIST:.2f}'", f"{L_CURVE:.2f}'"]],
        "text_height": 0.12})
    run("place_text", {
        "space": "C-101", "position": [1.0, 20.9], "height": 0.13,
        "valign": "top",
        "content": "GENERAL NOTES:\n"
                   "1. STATIONS AND BEARINGS ARE ALONG THE SR 100 CENTERLINE.\n"
                   "2. UNITS ARE US SURVEY FEET. PLAN SCALE 1\" = 50'."})
    run("fill_title_block", {"sheet": "C-101", "fields": {
        "project": "SR 100 RESURFACING", "agency": "DEMO DOT",
        "sheet_title": "ROADWAY PLAN", "sheet_number": "C-101",
        "total_sheets": "1", "designed_by": "RD", "drawn_by": "AI",
        "checked_by": "RD", "date": "2026-08-02", "scale": "1\" = 50'"}})

    # ------------------------------------------------------------ outputs
    print("== outputs")
    for query, params in (
            ("render_sheet", {"sheet": "C-101", "dpi": 150}),
            ("render_model", {}),
            ("export_pdf", {}),
            ("export_dxf", {}),
            ("save_document", {"path": str(OUT / "demo.rdoc.json")}),
            ("save_journal", {"path": str(OUT / "demo.journal.jsonl")})):
        result = session.query(query, params)
        if not result["ok"]:
            raise SystemExit(f"{query} failed: {result['error']}")
        print(f"    {query}: {result['path']}")

    replayed = Session.replay_journal(OUT / "demo.journal.jsonl")
    assert replayed.doc.to_dict() == session.doc.to_dict()
    print(f"    replay determinism: OK "
          f"({len(session.bus.journal)} commands re-executed identically)")

    summary = session.query("get_document_state")["summary"]
    print(f"== done: {summary['model_entity_count']} model entities, "
          f"{len(summary['sheets'])} sheet(s), "
          f"{summary['journal_length']} commands in the journal")


if __name__ == "__main__":
    main()
