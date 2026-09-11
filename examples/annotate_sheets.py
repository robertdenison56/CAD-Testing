"""Do the "annotate a sheet" job by hand, the way an agent would have to.

The task, in the words it would be given:

    "annotate sheets C-101 to C-103 pavement edge callouts and populate all
     title blocks"

Nothing here is clever -- it is deliberately the plain sequence of queries and
commands an agent has to find for itself through the MCP tools, so that if a
step is awkward for a script it is awkward for a model too:

  1. open the sheet file            open_document
  2. what sheets are there          list_sheets
  3. which edges does each show     find_entities(anchor={kind, offset},
                                                 visible_on=<sheet>)
     (the design lives in the basefile, so the host owns no geometry; the
      anchors travel through the attachment, so a pavement edge announces
      itself as kind "offset" at +/- 12 ft of SR-100)
  4. call one out                   place_callout(target_entity=..., at="mid")
     (naming the entity rather than a point: the engine puts the leader tip
      on the geometry, which matters on a curve, where the midpoint of the
      endpoints is 15.5 ft off the arc)
  5. fill every title block         fill_title_block
  6. look at the result             render_sheet

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

    if CALLOUT_LAYER not in s.doc.layers:
        check(s.execute("create_layer", {"name": CALLOUT_LAYER, "color": "black"}))

    placed = 0
    for sheet in sheets:
        # 3. the design is referenced, so ask for the edges this sheet shows.
        # One call: the filter and the viewport window are the engine's job.
        found = check(s.query("find_entities", {
            "anchor": {"kind": "offset", "offset": [-EDGE_OFFSET, EDGE_OFFSET]},
            "visible_on": sheet["name"], "limit": 1}))
        if not found["entities"]:
            print(f"  {sheet['name']}: no pavement edge in view")
        else:
            edge = found["entities"][0]
            anchor = edge["anchor"]
            side = "RT" if anchor["offset"] > 0 else "LT"
            # 4. name the entity; the engine puts the leader tip on it
            drop = 120.0 if anchor["offset"] > 0 else -120.0
            check(s.execute("place_callout", {
                "space": "model", "target_entity": edge["id"], "at": "mid",
                "position": [edge["point"][0] + 150.0, edge["point"][1] - drop],
                "content": f"EDGE OF PAVEMENT {abs(anchor['offset']):.0f}' {side} "
                           f"OF {anchor['alignment']}",
                "layer": CALLOUT_LAYER}))
            print(f"  {sheet['name']}: callout on {edge['id']} "
                  f"({edge['type']}, {anchor['ref']}, {abs(anchor['offset']):.0f}' "
                  f"{side}) of {found['total']} edges in view")
            placed += 1

        # 5. and its title block
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
