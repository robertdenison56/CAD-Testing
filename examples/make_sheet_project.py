"""Build a two-file plan set to annotate: a model file and a sheet file that
references it -- the starting condition for the "annotate a sheet" test.

This is how a real project is laid out. The design lives in one document
(alignment, pavement edges, shoulders); the plans live in another that
*references* it, so the sheets never own the geometry and always see the
current design. Each sheet looks at its own stretch of alignment through a
viewport, and the title blocks are left empty, waiting to be filled.

The builder itself lives in ``roaddraft.probes.fixture`` so that this demo and
the find-probes draft exactly the same project; this file is the CLI over it.

Run:  python examples/make_sheet_project.py [--out DIR]

Then point an agent at the sheet file:

    claude mcp add roaddraft-sheets -- /ABS/PATH/.venv/bin/roaddraft-mcp \\
        --doc examples/output/SR-100.sheets.rdoc.json

and ask it to annotate the sheets.
"""
import argparse
from pathlib import Path

from roaddraft.api.session import Session
from roaddraft.probes import fixture

OUT = Path(__file__).parent / "output"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(OUT), help="output directory")
    args = parser.parse_args(argv)
    out = Path(args.out)

    model_path, sheet_path = fixture.build(out)

    model = Session.load(model_path, out_dir=out)
    align = model.doc.design.alignments[fixture.ALIGNMENT]
    print(f"model  {model_path.name}: {fixture.ALIGNMENT} {align.length:,.2f} ft, "
          f"{len(align.elements)} elements, {len(model.doc.model_entities)} entities "
          f"(edges at {fixture.EDGE_OFFSETS}, shoulders at {fixture.SHOULDER_OFFSETS})")

    per_sheet = fixture.VIEWPORT["width_in"] * fixture.FEET_PER_INCH
    print(f"sheets {sheet_path.name}: {len(fixture.SHEETS)} sheets at "
          f"1\"={fixture.FEET_PER_INCH:g}', {per_sheet:,.0f} ft each, referencing "
          f"{model_path.name}")
    print("       title blocks are empty; nothing is annotated yet")

    session = Session.load(sheet_path, out_dir=out)
    render = session.query("render_sheet", {"sheet": fixture.SHEETS[0]})
    if not render["ok"]:
        raise SystemExit(render["error"]["message"])
    print(f"render {Path(render['path']).name}: {render['size_bytes']:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
