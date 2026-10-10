"""Redraft Caltrans PPM example "65 LAYOUT-4" (sheet L-4) end to end: digitise the
published sheet, build the bb01 / aa01 base files and the ea004 sheet file, then plot,
export and overlay the result on the published sheet.

    .venv/bin/python examples/ppm_redraft/make_l4.py [--out DIR]

The extracted PDF content is checked in (ppm048_l4.extract.json.gz); to re-extract it
from the sheet PDF, run extract_pdf.py with a Python that has pdfplumber:

    python3 examples/ppm_redraft/extract_pdf.py <sheet.pdf> l4.json 2.0 && gzip -c l4.json > \
        examples/ppm_redraft/ppm048_l4.extract.json.gz
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

SECTION = "2-2.05-Layouts-Profiles-and-Superelevation-Diagrams"
NAME = "PPM-048-Route-65-Layout-Example-65-LAYOUT-4"
SOURCE = REPO / "examples" / "Exmple Plans" / "Sheets" / "Caltrans-PPM" / SECTION / f"{NAME}.pdf"
OUT = REPO / "examples" / "Exmple Plans" / "Redraft" / "Caltrans-PPM" / SECTION / NAME
DPI = 150


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    print("### DIGITISE the published sheet")
    import digitize_l4
    digitize_l4.main()
    digitize_l4.main2()

    print("\n### BUILD the files")
    import build_l4 as B
    print("== bb01  topography")
    bb_ids = B.build_bb(out)
    print("== aa01  roadway design")
    aa_ids = B.build_aa(out, bb_ids)
    print("== ea004 sheet L-4")
    B.build_sheet(out, aa_ids, bb_ids)

    print("\n### PLOT and EXPORT")
    from roaddraft.api.session import Session
    sheet_file = out / f"{B.SH}.rdraft"
    s = Session.load(sheet_file, out_dir=out)
    png = s.query("render_sheet", {"sheet": B.SHEET, "dpi": DPI, "path": str(out / f"{B.SH}.png")})
    pdf = s.query("print_pdf", {"space": B.SHEET, "path": str(out / f"{B.SH}.pdf"),
                                "paper": "sheet", "scale": 1})
    dxf = s.query("export_dxf", {"path": str(out / f"{B.SH}.dxf")})
    for label, r in (("png", png), ("pdf", pdf), ("dxf", dxf)):
        if not r.get("ok"):
            raise SystemExit(f"{label} failed: {r.get('error')}")
        print(f"   {label}  {Path(r['path']).name}  {r.get('size_bytes', 0):,} bytes")

    if shutil.which("pdftoppm") and SOURCE.exists():
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", str(2 * DPI), "-png", str(SOURCE),
                            str(Path(tmp) / "orig")], check=True)
            import overlay
            overlay.overlay(Path(tmp) / "orig-1.png", out / f"{B.SH}.png",
                            out / f"{B.SH}-overlay.png")
        print(f"   overlay  {B.SH}-overlay.png  (published blue, redraft red, black where they agree)")

    print("\n### THE SPLIT, read back from disk")
    state = s.query("get_document_state", {})["summary"]
    print(f"   sheet file: {state['model_entity_count']} model entities, "
          f"{len(state['alignments'])} alignments of its own")
    for ref in s.query("list_references", {})["references"]:
        print(f"   references {ref['name']}: {ref['path']}")
    for a in s.query("list_alignments", {"include_references": True})["alignments"]:
        print(f"   alignment through the reference: {a['name']}")
    for name, station in (("AA01:D13", "678+43.61"), ("AA01:IND1", "55+90.29"),
                          ("AA01:IN4", "681+58.69")):
        q = s.query("station_to_xy", {"alignment": name, "station": station, "sheet": B.SHEET})
        print(f"   {name} {q['station_text']}: sheet {q['on_sheet']['sheet_point']}, {q['bearing']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
