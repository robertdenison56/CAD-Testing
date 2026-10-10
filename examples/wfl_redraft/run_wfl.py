"""Redraft the WFL sample plan sheets in bulk.

    .venv/bin/python examples/wfl_redraft/run_wfl.py --all [--workers 6]
    .venv/bin/python examples/wfl_redraft/run_wfl.py WFL-Plan-Profile-Sheets-p14 ...
    .venv/bin/python examples/wfl_redraft/run_wfl.py --family plan-profile

Each sheet is digitised (wflsheet), built (wflbuild), plotted, exported and overlaid on
its published sheet, into examples/Exmple Plans/Redraft/WFL/<source>/<sheet>/.
Per-sheet settings live in configs/<sheet>.json.  A summary row per sheet goes to
examples/output/wfl_redraft/results/<sheet>.json; --summary collects them into
examples/Exmple Plans/Redraft/WFL/redraft-manifest.csv.
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
PPM = HERE.parent / "ppm_redraft"
SHEETS = REPO / "examples" / "Exmple Plans" / "Sheets" / "WFL"
REDRAFT = REPO / "examples" / "Exmple Plans" / "Redraft" / "WFL"
WORK = REPO / "examples" / "output" / "wfl_redraft"
EXTRACT = WORK / "extract"
RESULTS = WORK / "results"
CONFIGS = HERE / "configs"
DPI = 100
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PPM))


def sheets():
    return {f.stem: f for f in sorted(SHEETS.glob("*.pdf"))}


def group_of(stem):
    """The source PDF a split sheet came from: WFL-Plan-Profile-Sheets-p14 -> WFL-Plan-Profile-Sheets"""
    return stem.rsplit("-p", 1)[0]


def extract(pid, pdf):
    EXTRACT.mkdir(parents=True, exist_ok=True)
    dst = EXTRACT / f"{pid}.json"
    if not dst.exists():
        py = shutil.which("python3") or "python3"
        subprocess.run([py, str(PPM / "extract_pdf.py"), str(pdf), str(dst), "1.0"],
                       check=True, capture_output=True)
    return json.loads(dst.read_text())


def overlay(orig_png, redraft_png, out_png, scale, offset, page_h, sheet_w, sheet_h):
    """The published sheet in blue, the redraft in red, black where they agree.  The
    published page is rendered at DPI per page inch; an extracted point e (page inches)
    is the sheet point (e - offset) / scale."""
    from PIL import Image, ImageChops, ImageOps
    Image.MAX_IMAGE_PIXELS = None
    red = Image.open(redraft_png).convert("L")
    W, H = red.size
    dpi = W / sheet_w
    page = Image.open(orig_png).convert("L")
    ox, oy = offset
    matrix = (scale, 0, ox * dpi, 0, scale, (page_h - oy - sheet_h * scale) * dpi)
    pub = page.transform((W, H), Image.AFFINE, matrix, resample=Image.BILINEAR, fillcolor=255)
    r, o = ImageOps.invert(red), ImageOps.invert(pub)
    rgb = Image.merge("RGB", (ImageOps.invert(o), ImageOps.invert(ImageChops.lighter(r, o)),
                              ImageOps.invert(r)))
    rgb.save(out_png)


def readme(dig, rep, folder, pdf):
    f = dig["fields"]
    title = f.get("sheet_title", "").replace("\n", " ") or dig["family"]
    lines = [f"# {pdf.stem} -- redraft", "",
             f"WFL sample plan sheet **{rep['sheet']}** ({title}), redrafted as a RoadDraft file set "
             "named per the FLH OpenRoads Designer User Manual (chapter 3C, WFLHD ORD file naming). "
             f"Source: `Sheets/WFL/{pdf.name}`.", "", "| File | What it holds |", "|---|---|"]
    roles = {"SUR": "Survey file (\"_sur\"): existing features -- the sheet's dashed linework and contour elevations.",
             "ALI": "Alignments file (\"_ali\"): " + (
                 f"alignment(s) {', '.join(rep['alignments'])} rebuilt from the centerline, ticks and "
                 "station numbers, with stationing." if rep["alignments"] else "centerlines kept as drawn."),
             "HYD": "Drainage design file (\"_hyd_cor\"): the drainage system drawn heavy on the plan.",
             "COR": "Corridor file (\"_cor\"): the proposed linework (edges, limits, slope stakes, symbols). References the _ali and _sur files."}
    for k in ("SUR", "ALI", "HYD", "COR"):
        if k in rep["bases"]:
            lines.append(f"| `{rep['bases'][k]}` | **{k}** {roles[k]} |")
    if dig["kind"] == "plan":
        pr = dig["plan_rect"]
        lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}** (\"_{rep['suffix']}\"): references the design "
                     f"files through a 1\" = {dig['fpi']:g}' viewport over the plan view "
                     f"({pr[0]:.2f}-{pr[2]:.2f} x {pr[1]:.2f}-{pr[3]:.2f} in; twist {dig['twist']:.3f}°); "
                     "border, title block, notes, callouts, tables and the profile grid in sheet view. |")
    else:
        lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}** (\"_{rep['suffix']}\"): a sheet drawing with no plan "
                     "view (no model, so no design files); every line, table and note is in sheet view. |")
    stem = Path(rep["sheet_file"]).stem
    lines += [f"| `{stem}.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |",
              f"| `{stem}-overlay.png` | Check: published sheet blue, redraft red, black where they agree |", ""]
    c = rep["callouts"]
    lines += [f"Callouts: {sum(c.values())} placed in sheet view with `place_callout` "
              f"({c['anchor']} at a stated station of a rebuilt alignment, {c['entity']} at the "
              f"element the published leader touches, {c['point']} at a point).", ""]
    notes = [f"File names: project prefix `{rep['prefix']}` {rep['prefix_how']}; the sheet's type suffix "
             f"`_{rep['suffix']}` " + ("is the manual's." if rep["suffix_in_manual"] else
                                       "is not in the manual's table (no suffix is listed for this kind of sheet).")]
    if dig["kind"] == "plan":
        if dig.get("profile_divider"):
            notes.append("The profile grid below the plan view is sheet linework; the viewport covers the plan view only.")
        if "HYD" not in rep["bases"] and dig["family"] == "drainage":
            notes.append("No heavy drainage linework was found, so there is no _hyd_cor file.")
        notes.append("Scale: the sheet prints no numeric scale; 1\" = " + f"{dig['fpi']:g}' comes from " +
                     ("the station tick spacing." if rep["alignments"] else "the graphic scale bar or the config."))
        notes.append("Coordinates: the sample prints none for its linework; the model sits on a local datum "
                     f"(plan view centre at E 10,000 N 10,000), turned by the view twist " + {
                         "bearing": "so the lettered bearings read true.",
                         "config": "set in the sheet's config.",
                     }.get(dig.get("twist_how"), "of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up)."))
        notes.append("Station ticks: WFL draws them to one side of the line; RoadDraft's are centred on it, the same length.")
    if not dig["template"]:
        notes.append("The border and title block are kept as drawn instead of RoadDraft's WFL border template "
                     "(a portrait cross-section sheet, a non-standard border, or set so in the sheet's config).")
    elif not dig.get("title_box"):
        notes.append("No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).")
    notes.append("Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the "
                 "drawn outlines agree)." if dig.get("text_native") else
                 "The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font "
                 "sizes and the cap height is taken as 0.72 of the size.")
    lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [
        "", f"Rebuild: `.venv/bin/python examples/wfl_redraft/run_wfl.py {dig['id']}` "
            "(pipeline: examples/wfl_redraft/README.md).", ""]
    (folder / "README.md").write_text("\n".join(lines))


def one(pid):
    import wflbuild
    import wflsheet
    from roaddraft.api.session import Session
    pdf = sheets()[pid]
    folder = REDRAFT / group_of(pid) / pdf.stem
    t0 = time.time()
    cfg_path = CONFIGS / f"{pid}.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    if cfg.get("skip"):
        return {"id": pid, "status": "skipped", "reason": cfg.get("reason", "")}
    D = extract(pid, pdf)
    if len(D["paths"]) < 50:
        return {"id": pid, "status": "not redrafted",
                "reason": "raster page: no vector linework to digitise"}
    dig = wflsheet.digitise(pid, pdf.name, D, cfg)
    if folder.exists():
        for f in folder.iterdir():
            if f.suffix in (".rdraft", ".pdf", ".dxf", ".png") or f.name == "README.md":
                f.unlink()
    rep = wflbuild.build(dig, folder)
    s = Session.load(folder / rep["sheet_file"], out_dir=folder)
    stem = Path(rep["sheet_file"]).stem
    s.query("render_sheet", {"sheet": rep["sheet"], "dpi": DPI, "path": str(folder / f"{stem}.png")})
    s.query("print_pdf", {"space": rep["sheet"], "path": str(folder / f"{stem}.pdf"), "paper": "sheet", "scale": 1})
    s.query("export_dxf", {"path": str(folder / f"{stem}.dxf")})
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", str(DPI), "-png", str(pdf), str(Path(tmp) / "o")],
                       check=True, capture_output=True)
        src = next(Path(tmp).glob("o*.png"))
        cal = dig["calibration"]
        overlay(src, folder / f"{stem}.png", folder / f"{stem}-overlay.png", cal[0], (cal[1], cal[2]),
                D["page_in"][1], dig["sheet_size"][0], dig["sheet_size"][1])
    readme(dig, rep, folder, pdf)
    res = {"id": pid, "status": "ok", "folder": str(folder.relative_to(REPO)), "family": dig["family"],
           "kind": dig["kind"], "fpi": dig["fpi"], "twist": dig["twist"], "twist_how": dig["twist_how"],
           "template": dig["template"], "title_box": dig["title_box"], "text_native": dig.get("text_native"),
           "calibration": dig["calibration"],
           "calibration_how": dig["calibration_how"], "plan_rect": dig["plan_rect"], "fields": dig["fields"],
           **rep, "paths": dig["counts"], "texts": dig["text_counts"], "seconds": round(time.time() - t0, 1)}
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
    for pid, pdf in sheets().items():
        f = RESULTS / f"{pid}.json"
        res = json.loads(f.read_text()) if f.exists() else {}
        fields = res.get("fields", {})
        rows.append({"id": pid, "source": group_of(pid), "sheet": fields.get("sheet_number", ""),
                     "project": fields.get("project", ""), "status": res.get("status", "not run"),
                     "kind": res.get("kind", ""), "family": res.get("family", ""), "fpi": res.get("fpi", ""),
                     "sheet_file": res.get("sheet_file", ""), "bases": " ".join(res.get("bases", {}).values()),
                     "alignments": " ".join(res.get("alignments", [])),
                     "callouts": sum(res.get("callouts", {}).values()) if res.get("callouts") else "",
                     "note": res.get("reason") or res.get("note") or res.get("error", "")[-200:]})
    REDRAFT.mkdir(parents=True, exist_ok=True)
    path = REDRAFT / "redraft-manifest.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
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
        print(json.dumps({k: res.get(k) for k in ("id", "status", "kind", "family", "fpi", "sheet_file", "bases",
                                                    "alignments", "callouts", "seconds", "error")}, default=str))
        return 0
    if a.summary:
        summary()
        return 0
    ids = list(a.ids)
    if a.all or a.family:
        for pid in sheets():
            if a.family:
                f = RESULTS / f"{pid}.json"
                fam = json.loads(f.read_text()).get("family") if f.exists() else None
                if fam != a.family:
                    continue
            ids.append(pid)
    with ThreadPoolExecutor(a.workers) as ex:
        for res in ex.map(run_one_subprocess, ids):
            print(f"{res['id']}: {res['status']} {res.get('kind', '')} {res.get('family', '')} "
                  f"fpi={res.get('fpi')} {res.get('sheet_file', '')} bases={list(res.get('bases', {}))} "
                  f"aligns={res.get('alignments', [])} callouts={res.get('callouts')} "
                  f"{res.get('seconds', '')}s {res.get('error', '')[-300:]}", flush=True)
    summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
