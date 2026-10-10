"""The redraft pipeline for one FLH division's sample sheets, shared by run_wfl.py and
run_cfl.py: each sheet is digitised (wflsheet, under the division's Standard), built
(wflbuild, under its Naming), plotted, exported and overlaid on its published sheet, into
<redraft>/<source set>/<sheet>/.  Per-sheet settings live in <configs>/<sheet>.json.  A
summary row per sheet goes to <work>/results/<sheet>.json; --summary collects them into
<redraft>/redraft-manifest.csv.
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
DPI = 100
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PPM))


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


class Pipeline:
    def __init__(self, name, script, sheets_dir, redraft_dir, work_dir, configs_dir, std, naming,
                 manual, roles, readme_dir):
        self.name = name                    # "wfl" / "cfl"
        self.script = Path(script)          # the runner invoked per sheet (--one)
        self.SHEETS = Path(sheets_dir)
        self.REDRAFT = Path(redraft_dir)
        self.WORK = Path(work_dir)
        self.EXTRACT = self.WORK / "extract"
        self.RESULTS = self.WORK / "results"
        self.CONFIGS = Path(configs_dir)
        self.std = std
        self.naming = naming
        self.manual = manual                # how the README names the naming convention
        self.roles = roles                  # {SUR/ALI/HYD/COR: README wording}
        self.readme_dir = readme_dir        # the pipeline README path, relative to the repo

    # ------------------------------------------------------------------ sheets
    def sheets(self):
        return {f.stem: f for f in sorted(self.SHEETS.glob("*.pdf"))}

    @staticmethod
    def group_of(stem):
        """The source PDF a split sheet came from: WFL-Plan-Profile-Sheets-p14 -> WFL-Plan-Profile-Sheets"""
        return stem.rsplit("-p", 1)[0] if stem[-3:-2] == "p" and stem[-2:].isdigit() else stem

    def folder_of(self, pid):
        """<redraft>/<source set>/<sheet>/, or <redraft>/<sheet>/ for a one-sheet source."""
        group = self.group_of(pid)
        return self.REDRAFT / group / pid if group != pid else self.REDRAFT / pid

    @staticmethod
    def raster_area(pdf):
        """Square inches of raster images on the published page (an aerial photograph,
        a logo): what the redraft cannot reproduce."""
        r = subprocess.run(["pdfimages", "-list", str(pdf)], capture_output=True, text=True)
        area = 0.0
        for line in r.stdout.splitlines()[2:]:
            f = line.split()
            if len(f) > 13 and f[2] == "image":
                try:
                    area += int(f[3]) / float(f[12]) * int(f[4]) / float(f[13])
                except (ValueError, ZeroDivisionError):
                    pass
        return round(area, 1)

    def extract(self, pid, pdf):
        self.EXTRACT.mkdir(parents=True, exist_ok=True)
        dst = self.EXTRACT / f"{pid}.json"
        if not dst.exists():
            py = shutil.which("python3") or "python3"
            subprocess.run([py, str(PPM / "extract_pdf.py"), str(pdf), str(dst), "1.0"],
                           check=True, capture_output=True)
        return json.loads(dst.read_text())

    # ------------------------------------------------------------------ README
    def readme(self, dig, rep, folder, pdf):
        f = dig["fields"]
        title = f.get("sheet_title", "").replace("\n", " ") or dig["family"]
        lines = [f"# {pdf.stem} -- redraft", "",
                 f"{self.name.upper()} sample plan sheet **{rep['sheet']}** ({title}), redrafted as a RoadDraft "
                 f"file set named per {self.manual}. Source: `Sheets/{self.SHEETS.name}/{pdf.name}`.", "",
                 "| File | What it holds |", "|---|---|"]
        for k in ("SUR", "ALI", "HYD", "COR"):
            if k in rep["bases"]:
                role = self.roles[k]
                if k == "ALI":
                    role += (f" alignment(s) {', '.join(rep['alignments'])} rebuilt from the centerline, ticks "
                             "and station numbers, with stationing." if rep["alignments"] else
                             " centerlines kept as drawn.")
                lines.append(f"| `{rep['bases'][k]}` | **{k}** {role} |")
        if dig["kind"] == "plan":
            pr = dig["plan_rect"]
            lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}**: references the design "
                         f"files through a 1\" = {dig['fpi']:g}' viewport over the plan view "
                         f"({pr[0]:.2f}-{pr[2]:.2f} x {pr[1]:.2f}-{pr[3]:.2f} in; twist {dig['twist']:.3f}°); "
                         "border, title block, notes, callouts, tables and the profile grid in sheet view. |")
        else:
            lines.append(f"| `{rep['sheet_file']}` | Sheet **{rep['sheet']}**: a sheet drawing with no plan "
                         "view (no model, so no design files); every line, table and note is in sheet view. |")
        stem = Path(rep["sheet_file"]).stem
        lines += [f"| `{stem}.pdf` / `.dxf` / `.png` | Plot, CAD exchange, render |",
                  f"| `{stem}-overlay.png` | Check: published sheet blue, redraft red, black where they agree |", ""]
        c = rep["callouts"]
        lines += [f"Callouts: {sum(c.values())} placed in sheet view with `place_callout` "
                  f"({c['anchor']} at a stated station of a rebuilt alignment, {c['entity']} at the "
                  f"element the published leader touches, {c['point']} at a point).", ""]
        notes = [f"File names: `{rep['sheet_file']}` {rep['prefix_how']}" +
                 ("." if rep["suffix_in_manual"] else
                  "; its type is not in the convention's table (none is listed for this kind of sheet).")]
        if dig["kind"] == "plan":
            if dig.get("profile_divider"):
                notes.append("The profile grid below the plan view is sheet linework; the viewport covers the plan view only.")
            if "HYD" not in rep["bases"] and dig["family"] == "drainage":
                notes.append("No heavy drainage linework was found, so there is no drainage design file.")
            notes.append("Scale: the sheet prints no numeric scale; 1\" = " + f"{dig['fpi']:g}' comes from " +
                         ("the station tick spacing." if rep["alignments"] else "the graphic scale bar or the config."))
            notes.append("Coordinates: the sample prints none for its linework; the model sits on a local datum "
                         f"(plan view centre at E 10,000 N 10,000), turned by the view twist " + {
                             "bearing": "so the lettered bearings read true.",
                             "config": "set in the sheet's config.",
                         }.get(dig.get("twist_how"), "of 0 (no bearing lettered along a rebuilt alignment, so north is sheet-up)."))
            notes.append("Station ticks: the sheet draws them to one side of the line; RoadDraft's are centred on it, the same length.")
        if rep.get("raster_in2", 0) > 1.0:
            notes.append(f"The published sheet carries {rep['raster_in2']:g} sq in of raster images (an aerial "
                         "photograph or logos); the redraft holds the vector linework and lettering only.")
        if not dig["template"]:
            notes.append("The border and title block are kept as drawn instead of RoadDraft's FLH (wfl) border template "
                         "(a portrait cross-section sheet, a non-standard border, or set so in the sheet's config).")
        elif not dig.get("title_box"):
            notes.append("No sheet title box is drawn on this sheet (plan-profile sheets carry the title in the plot stamp).")
        notes.append("Text heights are the lettered cap heights (MicroStation sizes text by its capitals, and the "
                     "drawn outlines agree)." if dig.get("text_native") else
                     "The lettering is not outlined (a sheet made from a spreadsheet), so its sizes are PDF font "
                     "sizes and the cap height is taken as 0.72 of the size.")
        lines += ["## Notes", ""] + [f"- {n}" for n in notes] + [
            "", f"Rebuild: `.venv/bin/python {self.script.relative_to(REPO)} {dig['id']}` "
                f"(pipeline: {self.readme_dir}).", ""]
        (folder / "README.md").write_text("\n".join(lines))

    # ------------------------------------------------------------------ one sheet
    def one(self, pid):
        import wflbuild
        import wflsheet
        from roaddraft.api.session import Session
        pdf = self.sheets()[pid]
        folder = self.folder_of(pid)
        t0 = time.time()
        cfg_path = self.CONFIGS / f"{pid}.json"
        cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
        if cfg.get("skip"):
            return {"id": pid, "status": "skipped", "reason": cfg.get("reason", "")}
        D = self.extract(pid, pdf)
        if len(D["paths"]) < 50:
            return {"id": pid, "status": "not redrafted",
                    "reason": "raster page: no vector linework to digitise"}
        dig = wflsheet.digitise(pid, pdf.name, D, cfg, self.std)
        if folder.exists():
            for f in folder.iterdir():
                if f.suffix in (".rdraft", ".pdf", ".dxf", ".png") or f.name == "README.md":
                    f.unlink()
        rep = wflbuild.build(dig, folder, self.naming)
        rep["raster_in2"] = self.raster_area(pdf)
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
        self.readme(dig, rep, folder, pdf)
        return {"id": pid, "status": "ok", "folder": str(folder.relative_to(REPO)), "family": dig["family"],
                "kind": dig["kind"], "fpi": dig["fpi"], "twist": dig["twist"], "twist_how": dig["twist_how"],
                "template": dig["template"], "title_box": dig["title_box"], "text_native": dig.get("text_native"),
                "calibration": dig["calibration"], "calibration_how": dig["calibration_how"],
                "plan_rect": dig["plan_rect"], "fields": dig["fields"], **rep, "paths": dig["counts"],
                "texts": dig["text_counts"], "seconds": round(time.time() - t0, 1)}

    def run_one_subprocess(self, pid):
        self.RESULTS.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, str(self.script), "--one", pid], capture_output=True, text=True)
        out = self.RESULTS / f"{pid}.json"
        if out.exists():
            res = json.loads(out.read_text())
        else:
            res = {"id": pid, "status": "error", "error": (r.stderr or r.stdout)[-1500:]}
            out.write_text(json.dumps(res, indent=1))
        return res

    # ------------------------------------------------------------------ manifest
    def summary(self):
        rows = []
        for pid, pdf in self.sheets().items():
            f = self.RESULTS / f"{pid}.json"
            res = json.loads(f.read_text()) if f.exists() else {}
            fields = res.get("fields", {})
            rows.append({"id": pid, "source": self.group_of(pid), "sheet": fields.get("sheet_number", ""),
                         "project": fields.get("project", ""), "status": res.get("status", "not run"),
                         "kind": res.get("kind", ""), "family": res.get("family", ""), "fpi": res.get("fpi", ""),
                         "sheet_file": res.get("sheet_file", ""), "bases": " ".join(res.get("bases", {}).values()),
                         "alignments": " ".join(res.get("alignments", [])),
                         "callouts": sum(res.get("callouts", {}).values()) if res.get("callouts") else "",
                         "note": res.get("reason") or res.get("note") or res.get("error", "")[-200:]})
        self.REDRAFT.mkdir(parents=True, exist_ok=True)
        path = self.REDRAFT / "redraft-manifest.csv"
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        from collections import Counter
        print(Counter(r["status"] for r in rows), "->", path)

    # ------------------------------------------------------------------ CLI
    def main(self, argv=None):
        ap = argparse.ArgumentParser(description=f"Redraft the {self.name.upper()} sample plan sheets")
        ap.add_argument("ids", nargs="*")
        ap.add_argument("--all", action="store_true")
        ap.add_argument("--family")
        ap.add_argument("--workers", type=int, default=6)
        ap.add_argument("--one")
        ap.add_argument("--summary", action="store_true")
        a = ap.parse_args(argv)
        if a.one:
            self.RESULTS.mkdir(parents=True, exist_ok=True)
            try:
                res = self.one(a.one)
            except Exception as ex:
                res = {"id": a.one, "status": "error", "error": f"{ex}\n{traceback.format_exc()[-1500:]}"}
            (self.RESULTS / f"{a.one}.json").write_text(json.dumps(res, indent=1, default=str))
            print(json.dumps({k: res.get(k) for k in ("id", "status", "kind", "family", "fpi", "sheet_file", "bases",
                                                        "alignments", "callouts", "seconds", "error")}, default=str))
            return 0
        if a.summary:
            self.summary()
            return 0
        ids = list(a.ids)
        if a.all or a.family:
            for pid in self.sheets():
                if a.family:
                    f = self.RESULTS / f"{pid}.json"
                    fam = json.loads(f.read_text()).get("family") if f.exists() else None
                    if fam != a.family:
                        continue
                ids.append(pid)
        with ThreadPoolExecutor(a.workers) as ex:
            for res in ex.map(self.run_one_subprocess, ids):
                print(f"{res['id']}: {res['status']} {res.get('kind', '')} {res.get('family', '')} "
                      f"fpi={res.get('fpi')} {res.get('sheet_file', '')} bases={list(res.get('bases', {}))} "
                      f"aligns={res.get('alignments', [])} callouts={res.get('callouts')} "
                      f"{res.get('seconds', '')}s {res.get('error', '')[-300:]}", flush=True)
        self.summary()
        return 0
