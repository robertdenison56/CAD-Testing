"""Build the design model file for Caltrans sheet L-2 (03-But-70, PM 46.0/47.0).

This is the file the plan sheets reference.  It owns the road and the ground:

  * the "SR70" horizontal alignment as design data -- four curves rebuilt from
    the sheet's own CURVE DATA table and BC/EC stations, so every station the
    plan prints comes back out of the design model rather than being typed;
  * the linework drawn from that alignment: centerline, 12 ft pavement edges,
    20 ft shoulder edges;
  * the alignment's own annotation -- station ticks and numbers, and the
    BC / EC / PCC callouts -- each one carrying the design anchor it came from;
  * the survey underneath: contours, cut/fill catch line, right of way, and
    the UPRR, digitised from the published sheet (see extract_existing.py).

Nothing about *sheet L-2* lives here.  ``build_sheet`` does that.

    python -m roaddraft.probes.l2.build_model --out DIR

(``examples/caltrans_l2/build_all.py`` builds both files and the renders.)
"""
import argparse
import json
from pathlib import Path

from roaddraft import Session
from roaddraft.probes.l2 import sr70_geometry as G

MODEL_NAME = "SR70-Bear-Creek.model"

LAYERS = [
    ("align_MAIN", "black", "continuous", 0.50, '"SR70" LINE, Route 70 centerline'),
    ("rd_EP", "black", "continuous", 0.40, "Edge of pavement, 12 ft each side"),
    ("rd_ES", "black", "continuous", 0.40, "Edge of shoulder, 20 ft each side"),
    ("rd_SLOPE", "black", "dashed", 0.25, "Cut / fill catch line (C/F, F/C)"),
    ("rd_RIGHT-OF-WAY", "black", "continuous", 0.25, "Right of way"),
    ("align_MAIN-anno", "black", "continuous", 0.18,
     "Stationing ticks and numbers; BC / EC / PCC callouts and tangent bearings"),
    ("align_BARRIER", "black", "continuous", 0.25,
     "Guard railing and MGS symbology on the barrier lines"),
    ("E-TOPO-MINR", "black", "dot", 0.13, "Existing ground, 5 ft contours"),
    ("E-TOPO-MAJR", "black", "dot", 0.25, "Existing ground, index contours"),
    ("E-TOPO-TEXT", "black", "continuous", 0.18, "Contour elevation labels"),
    ("E-RAIL", "black", "continuous", 0.30, "Union Pacific Railroad"),
]

# BC / EC / PCC called out along the centerline: (station, kind, wording)
JUNCTIONS = [
    (G.EC2_STA, "pt", '"SR70" 576+16.93 EC'),
    (G.BC3_STA, "pc", '"SR70" 578+47.69 BC'),
    (G.EC3_STA, "pt", '"SR70" 582+85.52 EC'),
    (G.BC4_STA, "pc", '"SR70" 585+36.75 BC'),
    (G.PCC_STA, "pcc", '"SR70" 588+34.95 PCC'),
]
LEADER_FT = 78.0            # how far off the centerline those callouts sit
CALLOUT_H = 7.0             # 0.14 in of lettering at 1" = 50'
BEARING_H = 8.0


def caltrans_station(display_ft):
    """Caltrans plan lettering: the whole station at each 500 ft, otherwise
    just its last digit -- '575', '6', '7', '8', '9', '580'."""
    hundreds = int(round(display_ft / 100.0))
    return str(hundreds) if hundreds % 5 == 0 else str(hundreds % 10)


def build(out_dir, quiet=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
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

    run("set_meta", {"updates": {"description": "03-3H5404  EA 0318000012  Bear Creek Bridge "
                                    "(Br No 12-0207) replacement, Route 70 PM 46.0/47.0. "
                                    "Design model: horizontal alignment, roadway "
                                    "linework, and existing ground."}})
    say("== layers")
    for name, color, linetype, lw, desc in LAYERS:
        run("create_layer", {"name": name, "color": color, "linetype": linetype,
                             "lineweight_mm": lw, "description": desc})

    # 1" = 50' is the plot scale of every sheet that shows this stretch, so
    # annotation drafted here is sized for it.
    run("set_annotation_scale", {"scale": G.FEET_PER_INCH})

    say("== alignment")
    run("create_alignment", {
        "name": G.ALIGNMENT, "begin_station": G.BEGIN_STA,
        "pis": G.control_points(),
        "description": 'Route 70 "SR70" LINE; curves 2-5 of the project alignment'})
    curves = ask("get_design_data", {"kind": "curves"})["rows"]
    for n, row in zip(sorted(G.DELTA), curves):
        say(f"    curve {n}: R={row['radius']:.2f}' D={row['delta_dms']} "
            f"T={row['tangent']:.2f}' L={row['length']:.2f}'  "
            f"BC {row['pc_station_text']}  EC {row['pt_station_text']}")

    say("== roadway linework")
    run("draw_alignment", {"alignment": G.ALIGNMENT, "layer": "align_MAIN"})
    run("draw_offset", {"alignment": G.ALIGNMENT, "offsets": [-12, 12],
                        "layer": "rd_EP"})
    run("draw_offset", {"alignment": G.ALIGNMENT, "offsets": [-20, 20],
                        "layer": "rd_ES"})

    say("== existing ground")
    existing = json.loads((Path(__file__).parent / "existing.json").read_text())
    for layer in sorted(existing["polylines"]):
        polys = existing["polylines"][layer]
        for poly in polys:
            run("draw_polyline", {"space": "model", "vertices": poly, "layer": layer})
        say(f"    {layer:<13} {len(polys):>5} polylines")
    for label in existing["contour_labels"]:
        run("place_text", {
            "space": "model", "position": label["at"],
            "content": str(label["elevation"]), "height": label["height_ft"],
            "rotation_deg": label["rotation_deg"], "halign": "left",
            "valign": "bottom", "layer": "E-TOPO-TEXT"})
    say(f"    {'E-TOPO-TEXT':<13} {len(existing['contour_labels']):>5} "
        f"elevation labels")

    say("== stationing")
    r = run("annotate_stationing", {
        "space": "model", "alignment": G.ALIGNMENT, "interval": 100.0,
        "station_range": [G.MATCH_W - 150, G.MATCH_E + 150],
        "include_pc_pt": False, "layer": "align_MAIN-anno",
        "text_height": CALLOUT_H, "tick_half_len": 8.0, "label_offset": 9.0})
    say(f"    {r['message']}")
    # Caltrans letters the whole station only every 500 ft
    labels = ask("find_entities", {"space": "model", "layer": "align_MAIN-anno",
                                   "type": "text", "limit": 200})["entities"]
    for ent in labels:
        anchor = ent.get("anchor") or {}
        if anchor.get("kind") != "station":
            continue
        run("modify_entity", {"id": ent["id"],
                              "changes": {"content": caltrans_station(anchor["station"])}})
    say(f"    {len(labels)} station numbers set to Caltrans lettering")

    say("== BC / EC / PCC callouts")
    run("define_block", {
        "name": "BC-EC-MARK", "base_point": [0, 0],
        "description": "Plan mark at a BC / EC / PCC on the centerline",
        "entities": [{"type": "circle", "center": [0, 0], "radius": 2.6},
                     {"type": "line", "start": [-4.0, 0], "end": [4.0, 0]}]})
    for station, kind, wording in JUNCTIONS:
        at = ask("station_to_xy", {"alignment": G.ALIGNMENT, "station": station})
        off = ask("station_to_xy", {"alignment": G.ALIGNMENT, "station": station,
                                    "offset": -LEADER_FT})
        run("draw_line", {"space": "model", "start": at["point"], "end": off["point"],
                          "layer": "align_MAIN-anno"})
        run("place_label", {"space": "model", "alignment": G.ALIGNMENT,
                            "anchor": station, "kind": "custom", "content": wording,
                            "side": "left", "label_offset": LEADER_FT,
                            "rotation": "perpendicular", "halign": "left",
                            "valign": "middle", "height": CALLOUT_H,
                            "layer": "align_MAIN-anno"})
        run("insert_block", {"space": "model", "block_name": "BC-EC-MARK",
                             "position": at["point"],
                             "rotation_deg": 90.0 - at["azimuth_deg"],
                             "layer": "align_MAIN-anno"})
        say(f"    {wording}")

    say("== tangent bearings and distances")
    for row in ask("get_design_data", {"kind": "tangents"})["rows"]:
        if row["length"] < 200.0:          # only the two the plan letters
            continue
        run("place_label", {"space": "model", "alignment": G.ALIGNMENT,
                            "anchor": row["ref"], "kind": "custom",
                            "content": f"{row['length']:.2f}'", "side": "left",
                            "label_offset": 7.0, "height": BEARING_H,
                            "layer": "align_MAIN-anno"})
        run("place_label", {"space": "model", "alignment": G.ALIGNMENT,
                            "anchor": row["ref"], "kind": "bearing", "side": "right",
                            "label_offset": 10.0, "height": BEARING_H,
                            "layer": "align_MAIN-anno"})
        say(f"    {row['ref']}  {row['length']:.2f}'  {row['bearing']}")

    path = ask("save_document", {"path": str(out_dir / f"{MODEL_NAME}.rdraft")})["path"]
    summary = ask("get_document_state", {})["summary"]
    say(f"\nmodel  {Path(path).name}: {summary['model_entity_count']:,} model "
        f"entities on {len(summary['layers'])} layers, "
        f"{len(summary['alignments'])} alignment, "
        f"{summary['journal_length']:,} commands")
    return Path(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
