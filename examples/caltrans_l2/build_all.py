"""Rebuild Caltrans sheet L-2 end to end: model file, sheet file, renders.

    python examples/caltrans_l2/build_all.py [--out DIR] [--pdf PLANSHEET.pdf]

--pdf re-digitises the existing ground from the published plan; without it the
checked-in existing.json is used.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from roaddraft.api.session import Session                      # noqa: E402
from roaddraft.probes.l2 import build_model, build_sheet       # noqa: E402
from roaddraft.probes.l2 import sr70_geometry as G             # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "output"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--pdf", help="re-digitise existing ground from this plan sheet")
    args = ap.parse_args(argv)
    out = Path(args.out)

    if args.pdf:
        import extract_existing
        print("== digitise existing ground")
        extract_existing.main(["--pdf", args.pdf])
        print()

    print("### MODEL FILE")
    model_path = build_model.build(out)
    print("\n### SHEET FILE")
    sheet_path, _ = build_sheet.build(out)

    print("\n### OUTPUT")
    session = Session.load(sheet_path, out_dir=out)
    png = session.query("render_sheet", {"sheet": build_sheet.SHEET, "dpi": 150})
    pdf = session.query("export_pdf", {"path": str(out / "SR70-Bear-Creek-L-2.pdf")})
    dxf = session.query("export_dxf", {"path": str(out / "SR70-Bear-Creek-L-2.dxf")})
    for label, r in (("png", png), ("pdf", pdf), ("dxf", dxf)):
        print(f"   {label}  {r['path']}  {r['size_bytes']:,} bytes")

    # the sheet owns no design: prove it reads its stations through the reference
    print("\n### THE SPLIT")
    state = session.query("get_document_state", {})["summary"]
    print(f"   sheet file: {state['model_entity_count']} model entities, "
          f"{len(state['alignments'])} alignments of its own")
    names = [a["name"] for a in
             session.query("list_alignments", {"include_references": True})["alignments"]]
    print(f"   visible through the reference: {', '.join(names)}")
    for station in ("576+16.93", "588+34.95"):
        q = session.query("station_to_xy", {"alignment": f"{build_sheet.REF}:"
                                                         f"{G.ALIGNMENT}",
                                            "station": station})
        print(f"   {q['station_text']}  {q['bearing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
