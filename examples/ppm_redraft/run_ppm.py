"""Redraft PPM example sheets in bulk.

    .venv/bin/python examples/ppm_redraft/run_ppm.py --all [--workers 6]
    .venv/bin/python examples/ppm_redraft/run_ppm.py PPM-095 PPM-037      (some sheets)
    .venv/bin/python examples/ppm_redraft/run_ppm.py --family drainage

Each sheet is digitised (ppmsheet), built (ppmbuild), plotted, exported and overlaid on
its published sheet, into examples/Exmple Plans/Redraft/Caltrans-PPM/<section>/<name>/.
Per-sheet settings live in configs/<PPM-nnn>.json.  A summary row per sheet goes to
examples/output/ppm_redraft/results/<PPM-nnn>.json; --summary collects them into
examples/Exmple Plans/Redraft/Caltrans-PPM/redraft-manifest.csv.

PPM-048 (L-4) is built by make_l4.py and is skipped here.  Scanned sheets have no
vector content to digitise and are listed in the manifest as not redrafted.
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SHEETS = REPO / "examples" / "Exmple Plans" / "Sheets" / "Caltrans-PPM"
REDRAFT = REPO / "examples" / "Exmple Plans" / "Redraft" / "Caltrans-PPM"
WORK = REPO / "examples" / "output" / "ppm_redraft"
EXTRACT = WORK / "extract"
RESULTS = WORK / "results"
CONFIGS = HERE / "configs"
DPI = 100
HANDMADE = {"PPM-048"}
sys.path.insert(0, str(HERE))


def sheets():
    out = {}
    for f in sorted(SHEETS.glob("*/*.pdf")):
        out[f.name[:7]] = f
    return out


def is_scan(pdf):
    """A scanned page: almost no vector paths to digitise (its extract, or poppler)."""
    ext = EXTRACT / f"{pdf.name[:7]}.json"
    if ext.exists():
        return len(json.loads(ext.read_text())["paths"]) < 200
    r = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True)
    big = [l for l in r.stdout.splitlines()[2:] if l.split() and int(l.split()[3]) * int(l.split()[4]) > 4e6]
    return bool(big)


def extract(pid, pdf):
    EXTRACT.mkdir(parents=True, exist_ok=True)
    dst = EXTRACT / f"{pid}.json"
    if not dst.exists():
        py = shutil.which("python3") or "python3"
        subprocess.run([py, str(HERE / "extract_pdf.py"), str(pdf), str(dst), "2.0"],
                       check=True, capture_output=True)
    return json.loads(dst.read_text())


def readme(dig, rep, folder, pdf):
    f = dig["fields"]
    title = f.get("sheet_title", "").replace("\n", " ")
    lines = [f"# {pdf.stem} -- redraft", "",
             f"Caltrans PPM example sheet **{rep['sheet']}** ({title}), redrafted as a RoadDraft "
             f"file set named per the Caltrans CADD Users Manual. Source: "
             f"`Sheets/Caltrans-PPM/{pdf.parent.name}/{pdf.name}`.", "", "| File | What it holds |", "|---|---|"]
    roles = {"BB01": "Master Topographic (\"bb\"): existing features -- the sheet's dotted linework "
                     "(existing roads, railroad, fence, contours) and contour elevations.",
             "AA01": "Master Design, roadway (\"aa\"): " + (
                 f"alignment(s) {', '.join(rep['alignments'])} rebuilt from the centerline, ticks and "
                 "station numbers, with stationing; " if rep["alignments"] else "") +
                 "the proposed roadway linework. References BB01.",
             "AA02": "Drainage: the drainage system drawn heavy on the plan (pipes, culverts, inlets)."}
    for k, v in rep["bases"].items():
        lines.append(f"| `{v}` | **{k}** {roles[k]} |")
    if dig["kind"] == "plan":
        lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}**: references the base files "
                     f"through a 1\" = {dig['fpi']:g}' viewport (twist {dig['twist']:.3f}°); border, title "
                     "block, notes, callouts, match lines, tables and symbols in sheet view. |")
    else:
        lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}**: a sheet drawing with no plan view "
                     "(no model, so no base files); every line, table and note is in sheet view. |")
    stem = Path(rep["sheet_file"]).stem
    lines += [f"| `{stem}.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |",
              f"| `{stem}-overlay.png` | Check: published sheet blue, redraft red, black where they agree |", ""]
    c = rep["callouts"]
    lines += [f"Callouts: {sum(c.values())} placed in sheet view with `place_callout` "
              f"({c['anchor']} at a stated station and offset of a rebuilt alignment, {c['entity']} at the "
              f"element the published leader touches, {c['point']} at a point).", ""]
    notes = []
    if dig["kind"] == "plan" and not rep["bases"].get("AA02"):
        notes.append("No drainage is drawn on this sheet, so there is no AA02.")
    if dig["text_mode"] == "strokes":
        notes.append("The PDF's text layer is OCR and does not line up with the drawn lettering, so the "
                     "lettering is kept as the drawn strokes (S-TEXT-* layers) and leaders as linework; "
                     "the text layer is only read for the title block.")
    if dig.get("twist_how") == "north arrow":
        notes.append("No bearing is lettered along a rebuilt alignment, so the view twist is read off "
                     "the north arrow.")
    if not dig["template"]:
        notes.append("The border and title block are kept as drawn instead of RoadDraft's Caltrans "
                     "title block template (a title sheet or other non-standard border, or set so in "
                     "the sheet's config).")
    if dig["kind"] == "plan":
        notes.append("Coordinates: the example prints none; the model sits on a local datum (sheet centre "
                     "at E 10,000 N 10,000), turned by the view twist " + {
                         "bearing": "so the lettered bearings read true.",
                         "north arrow": "read off the north arrow.",
                         "config": "set in the sheet's config.",
                     }.get(dig.get("twist_how"), "of 0 (no bearing or north arrow found, so north is sheet-up)."))
    notes.append("Text heights are the Caltrans values; RoadDraft's renderer draws a height as the font size, "
                 "so the PNG/PDF lettering looks smaller than the Caltrans font.")
    lines += ["## Notes", ""] + [f"- {n}" for n in notes] + ["", "Rebuild: `.venv/bin/python examples/ppm_redraft/run_ppm.py "
                                                            f"{dig['id']}` (pipeline: examples/ppm_redraft/README.md).", ""]
    (folder / "README.md").write_text("\n".join(lines))


def one(pid):
    import ppmbuild
    import ppmsheet
    from roaddraft.api.session import Session
    pdf = sheets()[pid]
    folder = REDRAFT / pdf.parent.name / pdf.stem
    t0 = time.time()
    cfg_path = CONFIGS / f"{pid}.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    if cfg.get("skip"):
        return {"id": pid, "status": "skipped", "reason": cfg.get("reason", "")}
    D = extract(pid, pdf)
    dig = ppmsheet.digitise(pid, f"{pdf.parent.name}/{pdf.name}", D, cfg)
    if folder.exists():
        for f in folder.iterdir():
            if f.suffix in (".rdraft", ".pdf", ".dxf", ".png") or f.name == "README.md":
                f.unlink()
    rep = ppmbuild.build(dig, folder)
    s = Session.load(folder / rep["sheet_file"], out_dir=folder)
    stem = Path(rep["sheet_file"]).stem
    s.query("render_sheet", {"sheet": rep["sheet"], "dpi": DPI, "path": str(folder / f"{stem}.png")})
    s.query("print_pdf", {"space": rep["sheet"], "path": str(folder / f"{stem}.pdf"), "paper": "sheet", "scale": 1})
    s.query("export_dxf", {"path": str(folder / f"{stem}.dxf")})
    import overlay
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(2 * DPI), "-png", str(pdf), str(Path(tmp) / "o")],
                       check=True, capture_output=True)
        src = next(Path(tmp).glob("o*.png"))
        cal = dig["calibration"]
        overlay.overlay(src, folder / f"{stem}.png", folder / f"{stem}-overlay.png", cal[0], (cal[1], cal[2]),
                        page_h=D["page_in"][1])
    readme(dig, rep, folder, pdf)
    res = {"id": pid, "status": "ok", "folder": str(folder.relative_to(REPO)), "family": dig["family"],
           "kind": dig["kind"], "fpi": dig["fpi"], "twist": dig["twist"], "template": dig["template"],
           "text_mode": dig["text_mode"], "calibration": dig["calibration"], **rep,
           "paths": dig["counts"], "texts": dig["text_counts"], "seconds": round(time.time() - t0, 1)}
    return res


def run_one_subprocess(pid):
    RESULTS.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, str(Path(__file__)), "--one", pid], capture_output=True, text=True)
    out = RESULTS / f"{pid}.json"
    if out.exists():
        res = json.loads(out.read_text())
    else:
        res = {"id": pid, "status": "error", "error": (r.stderr or r.stdout)[-1500:]}
        out.write_text(json.dumps(res, indent=1))
    return res


def summary():
    rows = []
    allsheets = sheets()
    for pid, pdf in allsheets.items():
        f = RESULTS / f"{pid}.json"
        res = json.loads(f.read_text()) if f.exists() else {}
        if pid in HANDMADE:
            res = {"status": "ok", "kind": "plan", "family": "layout", "sheet_file": "0000000000ea004.rdraft",
                   "bases": {"BB01": "0000000000bb01.rdraft", "AA01": "0000000000aa01.rdraft"},
                   "alignments": ["IND1", "D13", "IN4"], "note": "hand-built (make_l4.py)"}
        elif is_scan(pdf):
            res = {"status": "not redrafted", "reason": "scanned raster page: no vector linework to digitise"}
        rows.append({"id": pid, "section": pdf.parent.name, "sheet": pdf.stem, "status": res.get("status", "not run"),
                     "kind": res.get("kind", ""), "family": res.get("family", ""),
                     "sheet_file": res.get("sheet_file", ""), "bases": " ".join(res.get("bases", {}).values()),
                     "alignments": " ".join(res.get("alignments", [])),
                     "note": res.get("reason") or res.get("note") or res.get("error", "")[-200:]})
    path = REDRAFT / "redraft-manifest.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r["status"] for r in rows), "->", path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--family")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--one")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args(argv)
    if a.one:
        RESULTS.mkdir(parents=True, exist_ok=True)
        try:
            res = one(a.one)
        except Exception as ex:
            res = {"id": a.one, "status": "error", "error": f"{ex}\n{traceback.format_exc()[-1500:]}"}
        (RESULTS / f"{a.one}.json").write_text(json.dumps(res, indent=1, default=str))
        print(json.dumps({k: res.get(k) for k in ("id", "status", "kind", "sheet_file", "bases", "alignments",
                                                    "callouts", "seconds", "error")}, default=str))
        return 0
    if a.summary:
        summary(); return 0
    allsheets = sheets()
    ids = list(a.ids)
    if a.all or a.family:
        import ppmsheet
        for pid, pdf in allsheets.items():
            if pid in HANDMADE:
                continue
            if a.family and ppmsheet.family_of(f"{pdf.parent.name}/{pdf.name}") != a.family:
                continue
            if is_scan(pdf):
                continue
            ids.append(pid)
    with ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(run_one_subprocess, ids):
            print(f"{res['id']}: {res['status']} {res.get('sheet_file', '')} bases={list(res.get('bases', {}))} "
                  f"aligns={res.get('alignments', [])} callouts={res.get('callouts')} "
                  f"{res.get('seconds', '')}s {res.get('error', '')[-300:]}", flush=True)
    summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
