"""Build a two-file plan set to annotate: a model file and a sheet file that
references it -- the starting condition for the "annotate a sheet" test.

This is how a real project is laid out. The design lives in one document
(alignment, pavement edges); the plans live in another that *references* it,
so the sheets never own the geometry and always see the current design. Each
sheet looks at its own stretch of alignment through a viewport, and the title
blocks are left empty, waiting to be filled.

Run:  python examples/make_sheet_project.py [--out DIR]

Then point an agent at the sheet file:

    claude mcp add roaddraft-sheets -- /ABS/PATH/.venv/bin/roaddraft-mcp \\
        --doc examples/output/SR-100.sheets.rdoc.json

and ask it to annotate the sheets.
"""
import argparse
from pathlib import Path

from roaddraft.api.session import Session

OUT = Path(__file__).parent / "output"

#: ~4,600 ft of two-lane highway: tangent, 1,200 ft curve right, tangent,
#: 900 ft curve left, tangent. Long enough to need three sheets at 1"=50'.
PIS = [
    [1000.0, 1000.0],
    [2600.0, 1000.0, 1200.0],
    [4100.0, 1500.0, 900.0],
    [5600.0, 1500.0],
]
BEGIN_STATION = "10+00"
EDGE_OFFSETS = [-12.0, 12.0]        # a 24 ft pavement
SHOULDER_OFFSETS = [-20.0, 20.0]    # 8 ft shoulders

LAYERS = [
    {"name": "V-ALIGN-CNTR", "color": "red", "linetype": "center", "lineweight_mm": 0.35},
    {"name": "V-ROAD-EOP", "color": "yellow", "lineweight_mm": 0.35},
    {"name": "V-ROAD-SHLD", "color": "gray", "linetype": "dashed", "lineweight_mm": 0.18},
    {"name": "V-ANNO-TEXT", "color": "black", "lineweight_mm": 0.25},
]

SHEETS = ["C-101", "C-102", "C-103"]
FEET_PER_INCH = 50.0
VIEWPORT = {"center_paper": [17.0, 11.7], "width_in": 31.0, "height_in": 18.5}


def build_model(out: Path) -> Path:
    """The design: alignment, pavement edges, shoulders. No sheets, no labels."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    check(s.execute("create_alignment", {"name": "SR-100", "begin_station": BEGIN_STATION,
                                         "pis": PIS, "description": "SR-100 mainline"}))
    check(s.execute("draw_alignment", {"alignment": "SR-100", "layer": "V-ALIGN-CNTR"}))
    check(s.execute("draw_offset", {"alignment": "SR-100", "offsets": EDGE_OFFSETS,
                                    "layer": "V-ROAD-EOP"}))
    check(s.execute("draw_offset", {"alignment": "SR-100", "offsets": SHOULDER_OFFSETS,
                                    "layer": "V-ROAD-SHLD"}))
    path = out / "SR-100.model.rdoc.json"
    check(s.query("save_document", {"path": str(path)}))
    align = s.doc.design.alignments["SR-100"]
    print(f"model  {path.name}: SR-100 {align.length:,.2f} ft, "
          f"{len(align.elements)} elements, {len(s.doc.model_entities)} entities")
    return path


def build_sheets(out: Path, model_path: Path) -> Path:
    """The plans: three sheets over the referenced model, title blocks empty."""
    s = Session(project_name="SR-100 Widening", out_dir=out)
    for layer in LAYERS:
        s.execute("create_layer", layer)
    path = out / "SR-100.sheets.rdoc.json"
    # Save first so the relative reference path resolves from the sheet file's
    # own folder, the way it will when the file is opened again later.
    check(s.query("save_document", {"path": str(path)}))
    check(s.execute("attach_reference", {"name": "DESIGN", "space": "model",
                                         "path": model_path.name}))

    reference = Session.load(model_path, out_dir=out)
    align = reference.doc.design.alignments["SR-100"]
    x0, y0, x1, y1 = align.bbox()
    per_sheet = VIEWPORT["width_in"] * FEET_PER_INCH
    mid_y = (y0 + y1) / 2.0
    for i, name in enumerate(SHEETS):
        check(s.execute("create_sheet", {"name": name, "size": "ANSI_D"}))
        check(s.execute("create_viewport", {
            "sheet": name, "feet_per_inch": FEET_PER_INCH,
            "model_center": [x0 + per_sheet * (i + 0.5), mid_y], **VIEWPORT}))
    check(s.query("save_document", {"path": str(path)}))
    print(f"sheets {path.name}: {len(SHEETS)} sheets at 1\"={FEET_PER_INCH:g}', "
          f"{per_sheet:,.0f} ft each, referencing {model_path.name}")
    print("       title blocks are empty; nothing is annotated yet")
    return path


def check(result: dict) -> dict:
    if not result.get("ok"):
        raise SystemExit(f"{result.get('name')}: {result['error']['message']}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(OUT), help="output directory")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model_path = build_model(out)
    sheet_path = build_sheets(out, model_path)
    session = Session.load(sheet_path, out_dir=out)
    render = check(session.query("render_sheet", {"sheet": SHEETS[0]}))
    print(f"render {Path(render['path']).name}: {render['size_bytes']:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
