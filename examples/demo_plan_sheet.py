"""Draft a roadway plan sheet end-to-end through the Session tool surface —
the exact JSON commands an AI agent would issue — using the Phase 1 design
model instead of hand-computed geometry.

Design: alignment ALIGN-1, tangent -> 30-degree circular curve (R=800') ->
tangent, stationed from 10+00, with a profile. The engine draws the
centerline from the alignment, walks its true stations for ticks and labels,
places anchored bearing / mid-curve callouts, and builds the curve data
table; sheet C-101 (ANSI D) carries a 1"=50' viewport, the table, a north
arrow, notes and a filled title block. Every label records the design anchor
it came from, which is what the verifier checks.

Run:  python examples/demo_plan_sheet.py
Outputs land in examples/output/ (override with ROADDRAFT_DEMO_OUT).
"""
import json
import math
import os
from pathlib import Path

from roaddraft import Session

OUT = Path(os.environ.get("ROADDRAFT_DEMO_OUT") or Path(__file__).parent / "output")

PIS = [[1000.0, 1000.0], [1814.359354, 1000.0, 800.0], [2433.012702, 1357.179677]]
HALF_WIDTH = 12.0  # edge of pavement offset, ft


def main(out_dir=OUT, quiet=False):
    out_dir = Path(out_dir)
    session = Session(project_name="SR 100 Resurfacing Demo", out_dir=out_dir)
    say = (lambda *a: None) if quiet else print

    def run(name, params):
        result = session.execute(name, params)
        if not result["ok"]:
            raise SystemExit(f"{name} failed:\n"
                             f"{json.dumps(result['error'], indent=2)}")
        for warning in result["warnings"]:
            say(f"    warning: {warning}")
        return result

    def ask(name, params=None):
        result = session.query(name, params or {})
        if not result["ok"]:
            raise SystemExit(f"{name} failed: {result['error']}")
        return result

    # ------------------------------------------------------------- layers
    say("== layers")
    run("create_layer", {"name": "V-ALIGN-CNTR", "color": "red",
                         "linetype": "center", "lineweight_mm": 0.35,
                         "description": "Roadway centerline"})
    run("create_layer", {"name": "V-ROAD-EDGE", "color": "black",
                         "lineweight_mm": 0.5, "description": "Edge of pavement"})
    run("create_layer", {"name": "V-ROAD-STA", "color": "gray",
                         "lineweight_mm": 0.18, "description": "Station ticks"})
    run("create_layer", {"name": "V-ANNO-TEXT", "color": "black",
                         "lineweight_mm": 0.25, "description": "Annotation"})
    run("create_layer", {"name": "V-ANNO-TABL", "color": "black",
                         "lineweight_mm": 0.25, "description": "Tables"})

    # ------------------------------------------------------------- design
    say("== design model")
    r = run("create_alignment", {"name": "ALIGN-1", "begin_station": "10+00",
                                 "pis": PIS, "description": "SR 100 centerline"})
    say(f"    {r['message']}")
    r = run("create_profile", {"name": "PROF-1", "alignment": "ALIGN-1",
                               "pvis": [[1000, 100.0], [1800, 116.0, 400], [2518.88, 94.4]]})
    say(f"    {r['message']}")

    # ------------------------------------------------- centerline + edges
    say("== centerline and pavement edges")
    r = run("draw_alignment", {"alignment": "ALIGN-1", "layer": "V-ALIGN-CNTR"})
    say(f"    {r['message']}")
    edge = {"layer": "V-ROAD-EDGE", "space": "model"}
    for row in ask("get_design_data", {"kind": "tangents"})["rows"]:
        for side in (+HALF_WIDTH, -HALF_WIDTH):
            a = ask("station_to_xy", {"station": row["start_station"], "offset": side})
            b = ask("station_to_xy", {"station": row["end_station"], "offset": side})
            run("draw_line", {**edge, "start": a["point"], "end": b["point"]})
    for row in ask("get_design_data", {"kind": "curves"})["rows"]:
        cl_arc = session.doc.model_entities[
            next(i for i in r["created"] if session.doc.model_entities[i].TYPE == "arc")]
        for side in (+HALF_WIDTH, -HALF_WIDTH):
            # right offset shrinks a left-turning curve's radius
            radius = row["radius"] - side if row["direction"] == "L" else row["radius"] + side
            run("draw_arc", {**edge, "center": row["center"], "radius": radius,
                             "start_angle_deg": cl_arc.start_angle_deg,
                             "end_angle_deg": cl_arc.end_angle_deg})

    # ----------------------------------------------- stationing and labels
    say("== stationing and anchored labels")
    r = run("annotate_stationing", {"space": "model", "alignment": "ALIGN-1",
                                    "interval": 100, "layer": "V-ROAD-STA",
                                    "label_layer": "V-ANNO-TEXT"})
    say(f"    {r['message']}")
    n_tangents = ask("list_alignments")["alignments"][0]["tangents"]
    n_curves = ask("list_alignments")["alignments"][0]["curves"]
    for n in range(1, n_tangents + 1):
        r = run("place_label", {"space": "model", "alignment": "ALIGN-1",
                                "anchor": f"T-{n}", "kind": "bearing",
                                "layer": "V-ANNO-TEXT", "label_offset": 30})
        say(f"    {r['message']}")
    for n in range(1, n_curves + 1):
        r = run("place_label", {"space": "model", "alignment": "ALIGN-1",
                                "anchor": f"MC-{n}", "kind": "mc", "height": 10,
                                "layer": "V-ANNO-TEXT", "label_offset": 45})
        say(f"    {r['message']}")
    # perpendicular BEGIN/END callouts, justified so the text runs away from the road
    run("place_label", {"space": "model", "alignment": "ALIGN-1", "anchor": "BEGIN",
                        "layer": "V-ANNO-TEXT", "rotation": "perpendicular",
                        "label_offset": 30, "halign": "left"})
    run("place_label", {"space": "model", "alignment": "ALIGN-1", "anchor": "END",
                        "layer": "V-ANNO-TEXT", "rotation": "perpendicular",
                        "label_offset": 30, "halign": "right"})

    # ------------------------------------------------------------- sheet
    say("== sheet C-101")
    run("create_sheet", {"name": "C-101", "size": "ANSI_D"})
    extents = ask("get_extents", {"space": "model"})["extents"]
    model_center = [(extents[0] + extents[2]) / 2, (extents[1] + extents[3]) / 2]
    run("create_viewport", {"sheet": "C-101", "center_paper": [17.0, 11.7],
                            "width_in": 31.0, "height_in": 18.5,
                            "model_center": model_center, "feet_per_inch": 50.0})
    run("insert_block", {"space": "C-101", "block_name": "NORTH_ARROW",
                         "position": [31.6, 19.2], "scale": 0.9})
    r = run("place_curve_table", {"space": "C-101", "alignment": "ALIGN-1",
                                  "position": [23.8, 5.0], "layer": "V-ANNO-TABL"})
    say(f"    {r['message']}")
    run("place_text", {
        "space": "C-101", "position": [1.0, 20.9], "height": 0.13,
        "valign": "top",
        "content": "GENERAL NOTES:\n"
                   "1. STATIONS AND BEARINGS ARE ALONG THE SR 100 CENTERLINE (ALIGN-1).\n"
                   "2. UNITS ARE US SURVEY FEET. PLAN SCALE 1\" = 50'."})
    run("fill_title_block", {"sheet": "C-101", "fields": {
        "project": "SR 100 RESURFACING", "agency": "DEMO DOT",
        "sheet_title": "ROADWAY PLAN", "sheet_number": "C-101",
        "total_sheets": "1", "designed_by": "RD", "drawn_by": "AI",
        "checked_by": "RD", "date": "2026-09-10", "scale": "1\" = 50'"}})

    # ------------------------------------------------------------ outputs
    say("== outputs")
    for query, params in (
            ("render_sheet", {"sheet": "C-101", "dpi": 150}),
            ("render_model", {}),
            ("export_pdf", {}),
            ("export_dxf", {}),
            ("export_landxml", {}),
            ("save_document", {"path": str(out_dir / "demo.rdoc.json")}),
            ("save_journal", {"path": str(out_dir / "demo.journal.jsonl")})):
        result = ask(query, params)
        say(f"    {query}: {result['path']}")

    replayed = Session.replay_journal(out_dir / "demo.journal.jsonl")
    assert replayed.doc.to_dict() == session.doc.to_dict()
    say(f"    replay determinism: OK "
        f"({len(session.bus.journal)} commands re-executed identically)")

    summary = ask("get_document_state", {})["summary"]
    anchored = sum(1 for e in session.doc.model_entities.values() if e.anchor)
    say(f"== done: {summary['model_entity_count']} model entities ({anchored} anchored "
        f"to the design), {len(summary['sheets'])} sheet(s), "
        f"{summary['journal_length']} commands in the journal")
    return session


if __name__ == "__main__":
    main()
