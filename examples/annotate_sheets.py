"""Do the "annotate a sheet" job by hand, the way an agent would have to.

The task, in the words it would be given:

    "annotate sheets C-101 to C-103 pavement edge callouts and populate all
     title blocks"

Nothing here is clever -- it is deliberately the plain sequence of queries and
commands an agent has to find for itself through the MCP tools, so that if a
step is awkward for a script it is awkward for a model too:

  1. open the sheet file            open_document
  2. what sheets are there          list_sheets
  3. what does each one show        get_sheet_state -> viewport visible_model_bbox
  4. what is in the reference       get_model_state include_references=true
     (the design lives in the basefile, so the host owns no geometry; the
      anchors travel through the attachment, so a pavement edge announces
      itself as kind "offset" at +/- 12 ft of SR-100)
  5. call out one edge per sheet    place_callout
  6. fill every title block         fill_title_block
  7. look at the result             render_sheet

Run:  python examples/make_sheet_project.py && python examples/annotate_sheets.py
"""
import argparse
from pathlib import Path

from roaddraft.api.session import Session

OUT = Path(__file__).parent / "output"
SHEET_FILE = "SR-100.sheets.rdoc.json"
EDGE_OFFSET = 12.0                  # the pavement edge, not the shoulder
CALLOUT_LAYER = "V-ANNO-TEXT"

TITLE_BLOCK = {
    "project": "SR-100 WIDENING",
    "agency": "STATE DEPARTMENT OF TRANSPORTATION",
    "sheet_title": "ROADWAY PLAN",
    "designed_by": "R. DENISON, PE",
    "drawn_by": "ROADDRAFT",
    "checked_by": "",
    "date": "2026-09-10",
    "scale": "1\" = 50'",
}


def check(result: dict) -> dict:
    if not result.get("ok"):
        raise SystemExit(f"{result.get('name')}: {result['error']['message']}")
    return result


def midpoint(entity: dict):
    if entity["type"] == "line":
        s, e = entity["start"], entity["end"]
        return [(s[0] + e[0]) / 2.0, (s[1] + e[1]) / 2.0]
    return None


def inside(point, bbox) -> bool:
    return bbox[0] <= point[0] <= bbox[2] and bbox[1] <= point[1] <= bbox[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args(argv)
    out = Path(args.out)
    path = out / SHEET_FILE
    if not path.is_file():
        raise SystemExit(f"{path} not found -- run examples/make_sheet_project.py first")

    # 1-2. open the plans and see what is in them
    s = Session.load(path, out_dir=out)
    sheets = check(s.query("list_sheets", {}))["sheets"]
    print(f"opened {path.name}: {len(sheets)} sheets, "
          f"{len(s.doc.model_entities)} entities of its own")

    # 4. the design is referenced, so ask the attachment what it shows
    state = check(s.query("get_model_state", {"include_references": True}))
    edges = [e for e in state["entities"]
             if e.get("anchor", {}).get("kind") == "offset"
             and abs(e["anchor"]["offset"]) == EDGE_OFFSET]
    print(f"reference shows {state['count']} entities, "
          f"{len(edges)} of them pavement edge at +/-{EDGE_OFFSET:g} ft")

    if CALLOUT_LAYER not in s.doc.layers:
        check(s.execute("create_layer", {"name": CALLOUT_LAYER, "color": "black"}))

    placed = 0
    for sheet in sheets:
        # 3. what stretch of model does this sheet show?
        detail = check(s.query("get_sheet_state", {"sheet": sheet["name"]}))["sheet"]
        window = detail["viewports"][0]["visible_model_bbox"]

        # 5. call out the first edge whose midpoint falls in this sheet's window
        for edge in edges:
            target = midpoint(edge)
            if target is None or not inside(target, window):
                continue
            anchor = edge["anchor"]
            side = "RT" if anchor["offset"] > 0 else "LT"
            # put the text clear of the pavement, on the same side as the edge
            drop = 120.0 if anchor["offset"] > 0 else -120.0
            check(s.execute("place_callout", {
                "space": "model", "target": target,
                "position": [target[0] + 150.0, target[1] - drop],
                "content": f"EDGE OF PAVEMENT {abs(anchor['offset']):.0f}' {side} "
                           f"OF {anchor['alignment']}",
                "layer": CALLOUT_LAYER}))
            print(f"  {sheet['name']}: callout on {edge['id']} "
                  f"({anchor['ref']}, {abs(anchor['offset']):.0f}' {side}) at "
                  f"[{target[0]:,.1f}, {target[1]:,.1f}]")
            placed += 1
            break
        else:
            print(f"  {sheet['name']}: no pavement edge midpoint in view")

        # 6. and its title block
        check(s.execute("fill_title_block", {
            "sheet": sheet["name"],
            "fields": {**TITLE_BLOCK, "sheet_title": f"ROADWAY PLAN {sheet['name']}"}}))

    check(s.query("save_document", {"path": str(path)}))
    filled = sum(1 for sheet in sheets
                 if s.doc.sheet_by_ref(sheet["name"]).title_block_fields)
    print(f"{placed} callouts placed, {filled}/{len(sheets)} title blocks populated")

    # 7. look at it
    for sheet in sheets:
        render = check(s.query("render_sheet", {"sheet": sheet["name"]}))
        print(f"  {Path(render['path']).name}: {render['size_bytes']:,} bytes")
    print(f"journal: {len(s.bus.journal)} commands (replayable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
