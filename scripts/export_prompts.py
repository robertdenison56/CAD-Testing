"""Write every prompt a model is scored on to one Excel workbook, with the task files beside it.

    PYTHONPATH=src uv run --no-project --python 3.9 --with openpyxl --with jsonschema \\
        --with ezdxf --with matplotlib python scripts/export_prompts.py \\
        [--out benchmarks/prompts/roaddraft_prompts.xlsx] [--seeds 1-6] [--no-files]

Sheets: a read-me, the D1 task catalog, one row per D1 task (every task type on
one and two sheets, explicit and vague prompt per task, links to its files),
one row per real-sheet task (benchmarks/real_tasks/catalog.json, which
scripts/real_tasks.py writes first), the D1 eval sets (the d1-dev, d1-test and
d1-variance manifests under benchmarks/tasksets, each task's prompts and every
published run's score on it), the published D1 runs (benchmarks/runs), the
rules every D1 prompt is prefixed with, the Track P probe prompts with every
ranked model's k = 3 marks beside each, the Track P leaderboard
(benchmarks/leaderboard/track_p.json, which ``python -m roaddraft.runners
leaderboard`` writes) with the Track D (D1) board's state
(benchmarks/runs/leaderboard.json), and the harder-task pilots (off the board)
with a picture of each scripted solution.

A published run's per-task scores come from the ``episodes.csv`` its report
wrote beside the run under ``results/`` (not committed); without it the eval-set
columns for that run stay empty and the D1 runs sheet still shows its totals.

The task files go under ``benchmarks/prompts/tasks/<type>/<n>-sheet/seed-<n>/``
(gitignored; regenerate with this script): the brief and truth, the starting
document (``start.rdoc.json``, plus any base drawing shipped with the task),
the reference solution's finished document and journal, and a PNG of every
sheet (or the model) before and after; the eval sets' tasks the same under
``tasks/eval/<set>/seed-<n>/``.  Each probe's and pilot's start project is
built and plotted under ``tasks/starts/<start>/``, and its reference PDF's
pages go under ``tasks/probe/<id>/`` or ``tasks/pilot/<id>/`` for its
pictures.  Every task and probe row lists the base files its starting
document attaches.  The workbook links to them by
absolute path (``file://`` URLs to this checkout), so a copy of the workbook
opened from anywhere on this Mac still reaches them.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image as PILImage, ImageFilter
from openpyxl.utils import get_column_letter

from roaddraft.api.session import Session
from roaddraft.document.fileformat import read_document
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.episode import HARNESS_VERSION
from roaddraft.eval.report import LEADERBOARD_SET, effort_cell
from roaddraft.probes import fixture, prompting
from roaddraft.probes.pilot import PILOT_PROBES
from roaddraft.probes.tasks import DRAFT_PROBES, FIND_PROBES, PROBES, TIER2_PROBES, TIER3_PROBES
from roaddraft.tasks.brief import GENERATOR_VERSION, Task
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.prompts import RULES_TEMPLATE, rules
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.verify.checks import EXTRA_CHECKS
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash
from roaddraft.tasks.real import REAL_GENERATOR_VERSION, build_real_task
from roaddraft.tasks.types import PHASE_ORDER, REAL_TASK_TYPES, TASK_TYPES, checks_in_scope, task_type
from roaddraft.verify import VERIFIER_VERSION

#: the validated real-sheet tasks (scripts/real_tasks.py writes it)
REAL_CATALOG = Path("benchmarks/real_tasks/catalog.json")
#: the Track P probe leaderboard (python -m roaddraft.runners leaderboard writes it)
TRACK_P = Path("benchmarks/leaderboard/track_p.json")
#: the Track D (D1) leaderboard (scripts/make_leaderboard.py writes it)
D1_BOARD = Path("benchmarks/runs/leaderboard.json")
#: the published D1 runs, one folder each with its summary.json
D1_RUNS = D1_BOARD.parent
#: where harness runs live with their episodes and report (not committed)
RESULTS = Path("results")
#: the 33 probes' scripted solutions (python -m roaddraft.probes reference writes them)
PROBE_REFS = Path("benchmarks/probe_references")
#: the pilots' scripted solutions (python -m roaddraft.probes.pilot reference writes them)
PILOT_REFS = Path("benchmarks/pilot_references")
#: where pilot model runs go (runners run --pilot)
PILOT_RUNS = Path("benchmarks/pilot_runs")
#: a probe's or pilot's pictures show at most this many pages of its PDF
PDF_PAGES = 3
#: the pilots by the brainstorm's numbers (docs/Probes_Pilots.md), from each id's pNN prefix
PILOT_NAMES = {1: "Redraw an alignment from a scanned sheet", 2: "Sources that disagree",
               3: "Survey traps", 4: "Crowded annotation", 5: "The model picks the sheet breaks",
               6: "Plan and profile on one sheet", 10: "Typical section from a description",
               11: "Redlines with knock-on edits", 12: "A small full plan set",
               13: "Striping with no-passing zones", 14: "Open-ended QA review",
               15: "Plan reading", 17: "Twisted variants"}

#: the dev-set dial cycle: every curve count with and without a station equation
DIALS = [(curves, eq) for curves in (1, 2, 3) for eq in (False, True)]
WEIGHTS = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}
WEIGHTS.update({c["id"]: c["weight"] for c in EXTRA_CHECKS})  # the verifier's own (D1-16)
RENDER_DPI = 100
#: the pictures pasted into the workbook: each sheet's render with its lines thickened
#: (a 1-px line vanishes when a plot is shrunk), THUMB_PX wide per sheet, shown
#: THUMB_SHOW_PX high in the cell (the full renders stay linked beside them)
THUMB_PX = 640
THUMB_LINE = 3
THUMB_QUALITY = 80
THUMB_SHOW_PX = 240

FONT = "Arial"
HEAD_FILL = PatternFill("solid", start_color="1F3864")
BAND_FILL = PatternFill("solid", start_color="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOP_WRAP = Alignment(wrap_text=True, vertical="top")

PHASE_WORDS = {"design": "the design", "layers": "layers", "linework": "centerline",
               "edges": "pavement edges", "stationing": "stationing", "bearings": "bearings",
               "callouts": "curve callouts", "widths": "width dimensions",
               "sheet": "sheet + viewport", "reference": "base drawing reference",
               "table": "curve table", "north": "north arrow", "title": "title block"}


def _seeds(text: str):
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def _lines(text: str, width: int) -> int:
    """Rendered lines of ``text`` in a column ``width`` characters wide."""
    return sum(max(1, math.ceil(len(p) / max(width - 2, 1))) for p in str(text).split("\n"))


class Link:
    """A cell that is a hyperlink: shown as ``text``, pointing at ``target``."""

    def __init__(self, text: str, target: str):
        self.text, self.target = text, target


class Img:
    """A cell that shows a picture (a JPEG beside the task's files)."""

    def __init__(self, path: Path):
        self.path = path
        with PILImage.open(path) as im:
            w, h = im.size
        self.height = THUMB_SHOW_PX
        self.width = int(round(THUMB_SHOW_PX * w / h))


def thumbnail(folder: Path, prefix: str) -> Optional[Path]:
    """``thumb-<prefix>.jpg`` in ``folder``: every ``<prefix>-*.png`` there (one per
    sheet, or the model), side by side, lines thickened and shrunk to THUMB_PX
    wide each; None when there is no render."""
    pngs = sorted(folder.glob(f"{prefix}-*.png"))
    if not pngs:
        return None
    parts = []
    for png in pngs:
        im = PILImage.open(png).convert("L").filter(ImageFilter.MinFilter(THUMB_LINE))
        im.thumbnail((THUMB_PX, THUMB_PX), PILImage.LANCZOS)
        parts.append(im)
    h = max(im.height for im in parts)
    sheet = PILImage.new("L", (sum(im.width for im in parts) + 8 * (len(parts) - 1), h), 255)
    x = 0
    for im in parts:
        sheet.paste(im, (x, 0))
        x += im.width + 8
    out = folder / f"thumb-{prefix}.jpg"
    sheet.save(out, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return out


def _pictures(folder: Path, pngs: Dict[str, Optional[str]]) -> List[object]:
    """The start and finished pictures for a task's row (text when there is none)."""
    out = []
    for prefix, missing in (("start", "(nothing drawn yet)"), ("finished", "")):
        thumb = thumbnail(folder, prefix) if pngs.get(prefix) else None
        out.append(Img(thumb) if thumb else missing)
    return out


def base_files(document: Path, depth: int = 0, seen=None) -> List[str]:
    """What ``document`` attaches as references, one ``NAME: file`` line each,
    with what each of those attaches in turn indented under it."""
    seen = set() if seen is None else seen
    try:
        refs = read_document(document).get("references") or {}
    except (OSError, ValueError):
        return []
    lines = []
    for r in refs.values():
        path = (Path(document).parent / r["path"]).resolve()
        lines.append("    " * depth + f"{r['name']}: {r['path']}"
                     + ("" if path.exists() else " (missing)"))
        if path.exists() and path not in seen:
            seen.add(path)
            lines += base_files(path, depth + 1, seen)
    return lines


def _base_cell(document: Optional[Path], baseline: Optional[dict] = None) -> str:
    """The Base files cell: read from the written start document, plus any
    drawing beside it that it does not attach (an attach task's base file); else
    (no files written) the names the starting document's dict attaches."""
    if document is not None:
        seen = set()
        lines = base_files(document, 0, seen)
        skip = {Path(document).name, "finished.rdoc.json"}
        loose = sorted(p.name for p in Path(document).parent.iterdir()
                       if (p.name.endswith(".rdoc.json") or p.suffix == ".rdraft")
                       and p.name not in skip and p.resolve() not in seen)
        if loose:
            lines.append("beside it, not attached: " + ", ".join(loose))
    else:
        lines = [f"{r['name']}: {r['path']}"
                 for r in ((baseline or {}).get("references") or {}).values()]
    return "\n".join(lines) or "none"


def pdf_picture(pdf: Path, folder: Path, prefix: str) -> Optional[Path]:
    """The first PDF_PAGES pages of ``pdf`` rendered into ``folder`` as
    <prefix>-<n>.png (poppler's pdftoppm) and joined into one picture; None when
    pdftoppm is not installed or the PDF does not render."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{prefix}-*.png"):
        old.unlink()
    try:
        subprocess.run(["pdftoppm", "-png", "-r", str(RENDER_DPI), "-l", str(PDF_PAGES),
                        str(pdf), str(folder / prefix)], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return thumbnail(folder, prefix)


#: probe and pilot starts already plotted, by start name: (document, start PDF, picture)
STARTS: Dict[str, tuple] = {}


def plot_start(start: str, tasks_dir: Path) -> tuple:
    """Build a probe's start project under ``tasks/starts/<start>/project/`` and
    plot it the way its reference is plotted (print_pdf of every sheet, or model
    space when it has none): ``(document, start PDF or None, picture or None)``."""
    if start in STARTS:
        return STARTS[start]
    folder = tasks_dir / "starts" / start
    if folder.exists():
        shutil.rmtree(folder)
    document = fixture.start_document(folder / "project", start)
    session = Session.load(document, out_dir=folder / "project")
    sheets = [sheet.name for sheet in session.doc.sheets.values()]
    where = {"sheets": sheets} if sheets else {"space": "model"}
    pdf = picture = None
    if sheets or session.doc.model_entities or session.doc.references:  # else nothing to plot
        result = session.query("print_pdf", {**where, "path": str(folder / "start.pdf")})
        if result["ok"]:
            pdf = Path(result["path"])
            picture = pdf_picture(pdf, folder, "start")
    # a scan pilot hands the model a scanned sheet beside the document: show it too
    scans = sorted((document.parent / "scans").glob("*.png"))
    for i, scan in enumerate(scans, start=1):
        shutil.copy(scan, folder / f"start-scan-{i}.png")
    if scans:
        picture = thumbnail(folder, "start")
    STARTS[start] = (document, pdf, picture)
    return STARTS[start]


def _table(ws, headers, widths, rows, wrap_cols=()):
    for j, (h, w) in enumerate(zip(headers, widths), start=1):
        c = ws.cell(row=1, column=j, value=h)
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HEAD_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        c.border = BORDER
        ws.column_dimensions[get_column_letter(j)].width = w
    for i, row in enumerate(rows, start=2):
        height = 1
        for j, value in enumerate(row, start=1):
            c = ws.cell(row=i, column=j)
            if isinstance(value, Img):
                pic = XLImage(str(value.path))
                pic.width, pic.height = value.width, value.height
                ws.add_image(pic, c.coordinate)
                # the column and row grow to hold it (Excel: ~7 px per width unit,
                # 0.75 pt per px)
                col = ws.column_dimensions[get_column_letter(j)]
                col.width = max(col.width or 0, value.width / 7.0 + 2)
                height = max(height, (value.height * 0.75 + 2) / 13.5)
                c.border = BORDER
                continue
            if isinstance(value, Link):
                c.value = value.text
                c.hyperlink = value.target
                c.font = Font(name=FONT, size=10, color="0563C1", underline="single")
            else:
                c.value = value
                c.font = Font(name=FONT, size=10)
            c.alignment = TOP_WRAP
            c.border = BORDER
            if i % 2 == 1:
                c.fill = BAND_FILL
            if j in wrap_cols and isinstance(value, str):
                height = max(height, _lines(value, widths[j - 1]))
        ws.row_dimensions[i].height = min(409, 13.5 * height + 4)
    ws.freeze_panes = "B2" if len(headers) > 2 else "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"


def _given(ttype) -> str:
    phases = [PHASE_WORDS[p] for p in PHASE_ORDER
              if p in ttype.given and p not in ("layers", "design")]
    if "design" not in ttype.given:
        return "an empty design: the prompt gives the alignment's geometry; the layers exist"
    if not phases and not ttype.basefile:
        return "the design only (nothing drawn, no sheet)"
    start = "design, layers, " if "layers" in ttype.given else ""
    text = start + ", ".join(phases)
    if ttype.basefile:
        base = ", ".join(PHASE_WORDS[p] for p in PHASE_ORDER if p in ttype.basefile)
        text += f"; a base drawing file beside it holding the {base}"
    return text


# ------------------------------------------------------------- task files


def _render(session, folder: Path, prefix: str, sheets: List[dict]) -> Optional[str]:
    """PNG(s) of the document's sheets, or of the model when it has no sheet;
    returns the first file's name."""
    first = None
    done = False
    for sh in sheets:
        if session.doc.sheet_by_ref(sh["name"]) is None:
            continue
        name = f"{prefix}-{sh['name']}.png"
        result = session.query("render_sheet", {"sheet": sh["name"], "dpi": RENDER_DPI,
                                                "path": str(folder / name)})
        if result["ok"]:
            first = first or name
            done = True
    if not done and (session.doc.model_entities or session.doc.references):
        name = f"{prefix}-model.png"
        result = session.query("render_model", {"dpi": RENDER_DPI, "path": str(folder / name)})
        if result["ok"]:
            first = name
    return first


def _existing(task: Task, folder: Path) -> Optional[Dict[str, Optional[str]]]:
    """The PNG names of a task folder already written for this very task, or None."""
    try:
        if json.loads((folder / "brief.json").read_text())["task_id"] != task.task_id:
            return None
    except (OSError, ValueError, KeyError):
        return None
    if not (folder / "finished.rdoc.json").exists():
        return None
    first = lambda prefix: next((p.name for p in sorted(folder.glob(f"{prefix}-*.png"))), None)
    return {"start": first("start"), "finished": first("finished")}


#: reuse task folders already written for the same task id (``--reuse-files``)
REUSE = False


def write_task_files(task: Task, folder: Path) -> Dict[str, Optional[str]]:
    """Write a task's files into ``folder``; returns the PNG names for the
    starting and finished states (None when there is nothing to plot).  With
    ``REUSE``, a folder already holding this task's files is kept as it is."""
    if REUSE:
        done = _existing(task, folder)
        if done is not None:
            # the prompts are not in the task id, so a reused folder still gets today's brief
            (folder / "brief.json").write_text(task.brief.to_json())
            if done["start"] is None:  # a start with no sheet: its model and references
                start = session_for_task(task, out_dir=folder)
                done["start"] = _render(start, folder, "start", task.brief.deliverable["sheets"])
            return done
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / "brief.json").write_text(task.brief.to_json())
    (folder / "truth.json").write_text(task.truth.to_json())
    (folder / "start.rdoc.json").write_text(json.dumps(task.baseline, indent=1))
    sheets = task.brief.deliverable["sheets"]
    start = session_for_task(task, out_dir=folder)  # writes any base drawing beside it
    start_png = _render(start, folder, "start", sheets)
    session = session_for_task(task, out_dir=folder)
    reference_solution(task, session)
    for query, params in (("save_document", {"path": str(folder / "finished.rdoc.json")}),
                          ("save_journal", {"path": str(folder / "reference.journal.jsonl")})):
        result = session.query(query, params)
        if not result["ok"]:
            raise SystemExit(f"{query} failed for {task.task_id}: {result['error']['message']}")
    finished_png = _render(session, folder, "finished", sheets)
    return {"start": start_png, "finished": finished_png}


# -------------------------------------------------------------------- rows

#: the columns task_links fills, after a task's prompts
TASK_LINK_HEADS = ["Files", "Start", "Finished", "Base files", "Start (picture)",
                   "Finished (picture)"]
TASK_LINK_WIDTHS = [8, 8, 9, 30, 12, 12]


def task_links(task: Task, folder: Optional[Path], workbook_dir: Path) -> list:
    """A task's Files, Start and Finished links, the base files its starting
    document attaches, and its start and finished pictures; with no ``folder``
    (``--no-files``) only the base files' names."""
    if folder is None:
        return ["", "", "", _base_cell(None, task.baseline), "", ""]
    pngs = write_task_files(task, folder)
    rel = folder.relative_to(workbook_dir).as_posix()
    uri = folder.resolve().as_uri()  # absolute: the workbook may be opened anywhere
    return [Link(rel + "/", uri + "/"),
            Link("start", f"{uri}/{pngs['start']}") if pngs["start"] else "(nothing drawn yet)",
            Link("finished", f"{uri}/{pngs['finished']}") if pngs["finished"] else "",
            _base_cell(folder / "start.rdoc.json"), *_pictures(folder, pngs)]


def d1_rows(seeds, tasks_dir: Optional[Path], workbook_dir: Path):
    rows = []
    for ttype in TASK_TYPES.values():
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        for sheets in (1, 2):
            for seed in seeds:
                curves, eq = DIALS[(seed - 1) % len(DIALS)]
                try:
                    task = generate_task(seed, curves=curves, equations=eq, task_type=ttype.name,
                                         sheets=sheets)
                except ValueError as why:  # a seed this type cannot be made from
                    rows.append([ttype.name, sheets, seed, "", ttype.summary, _given(ttype), "",
                                 "", "", "", "", f"(no task: {why})", "",
                                 *[""] * len(TASK_LINK_HEADS)])
                    continue
                b, t = task.brief, task.truth
                folder = (None if tasks_dir is None else
                          tasks_dir / ttype.name / f"{sheets}-sheet" / f"seed-{seed}")
                links = task_links(task, folder, workbook_dir)
                rows.append([
                    ttype.name, sheets, seed, b.task_id, ttype.summary, _given(ttype),
                    ", ".join(t.scope), ", ".join(graded), sum(WEIGHTS[c] for c in graded),
                    t.counts["curves"],
                    "yes" if t.counts["equations"] else ("asked, none fit" if eq else "no"),
                    b.prompts["explicit"], b.prompts["vague"], *links])
    return rows


REAL_STARTS = {
    "draw": "the real alignment base file (alignments, corridor) with one alignment in its "
            "design but not drawn, nor annotated",
    "attach": "the real sheet file as published, its base files beside it but not attached",
    "title": "the real sheet file as published, its title block's project fields empty",
    "setup": "the real sheet file's base files attached and one alignment annotated in the "
             "model to read on the published twist; no sheet",
    "blank": "the real sheet set up (border, viewport at the published scale and twist) but "
             "blank and its title block empty; one alignment unannotated",
    "scratch": "the real base files attached and nothing else: no sheet",
    "notes": "the real sheet file as published with a spread of its construction callouts "
             "(note, leader, arrowhead) removed; the notes come back in the prompt with a "
             "station and offset each",
}


def _real_given(ttype) -> str:
    from roaddraft.tasks.real import START_KIND
    kind = START_KIND[ttype.name]
    if kind in REAL_STARTS:
        return REAL_STARTS[kind]
    done = [PHASE_WORDS[p] for p in ("stationing", "bearings", "callouts", "table")
            if p in ttype.given]
    text = ("a real plan sheet file (its border, title block, notes and callouts) referencing "
            "its real base files (alignments, corridor, survey); the alignment's own published "
            "annotation removed")
    return text + (f"; its {', '.join(done)} drafted to the spec" if done else "")


def catalog_rows():
    rows = []
    for ttype in TASK_TYPES.values():
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        rows.append([ttype.name, ttype.summary, _given(ttype), ", ".join(ttype.asks),
                     ", ".join(graded), sum(WEIGHTS[c] for c in graded)])
    for ttype in REAL_TASK_TYPES.values():
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        rows.append([ttype.name, ttype.summary, _real_given(ttype), ", ".join(ttype.asks),
                     ", ".join(graded), sum(WEIGHTS[c] for c in graded)])
    return rows


def real_rows(catalog: dict, tasks_dir: Optional[Path], workbook_dir: Path):
    """One row per validated real-sheet task, with links to its files."""
    rows = []
    for t in catalog["tasks"]:
        task = build_real_task(t["sheet_id"], t["alignment"], t["type"])
        if task.task_id != t["task_id"]:
            raise SystemExit(f"{REAL_CATALOG} is stale ({t['sheet_id']} {t['alignment']} "
                             f"{t['type']}): rerun scripts/real_tasks.py")
        ttype = task_type(t["type"])
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        D = task.brief.deliverable
        src = D["source"]
        folder = (None if tasks_dir is None else
                  tasks_dir / "real" / t["agency"] / t["sheet_id"]
                  / ("whole-sheet" if t.get("per_sheet") else t["alignment"].replace(" ", "-"))
                  / t["type"])
        links = task_links(task, folder, workbook_dir)
        # the published redraft the task's sheet and base files were copied from
        source = Path(src["folder"])
        links.insert(4, Link(source.name + "/", source.resolve().as_uri() + "/")
                     if source.exists() else src["folder"])
        rows.append([
            src["agency_name"], t["sheet_id"], t["sheet"], src["family"],
            f"1\" = {D['feet_per_inch']:g}'", t["twist_deg"],
            "(whole sheet)" if t.get("per_sheet") else t["alignment"],
            ", ".join(src["other_alignments"]), t["type"], t["task_id"],
            ", ".join(task.truth.scope), ", ".join(graded), sum(WEIGHTS[c] for c in graded),
            t["tangents"], t["curves"], t["labels"],
            task.brief.prompts["explicit"], task.brief.prompts["vague"], *links])
    return rows


def probe_set(probe) -> str:
    for name, group in (("T1 draft", DRAFT_PROBES), ("T2 find", FIND_PROBES),
                        ("Tier 2", TIER2_PROBES), ("Tier 3", TIER3_PROBES)):
        if probe in group:
            return name
    return "other"


# --------------------------------------------------------------- eval sets


def published_runs() -> List[dict]:
    """Every published D1 run's summary (benchmarks/runs/<run>/summary.json)."""
    return [json.loads(p.read_text()) for p in sorted(D1_RUNS.glob("*/summary.json"))]


def run_episodes(run_id: str) -> Optional[List[dict]]:
    """A published run's per-episode scores: the episodes.csv its report wrote
    beside the run under results/, or None when the run is not on this machine."""
    hits = sorted(RESULTS.glob(f"**/{run_id}/report/episodes.csv"))
    if not hits:
        return None
    with hits[0].open(newline="") as fh:
        return list(csv.DictReader(fh))


def run_columns(runs: List[dict]):
    """For each row of each published run whose episodes are on this machine, a
    column header and its scores by task: ``{task_id: [effective per sample]}``,
    None for a sample that errored (the report leaves those out of the mean)."""
    cols = []
    for s in runs:
        eps = run_episodes(s["run_id"])
        if eps is None:
            print(f"note: no episodes.csv for {s['run_id']} under {RESULTS}/; "
                  "the eval sets show no scores for it")
            continue
        for g in s["rows"]:
            key = tuple(str(g["key"].get(d) or "") for d in ("model", "provider", "effort",
                                                             "dialect", "mode", "level"))
            scores: Dict[str, List[Optional[float]]] = {}
            mine = [e for e in eps if tuple(e[d] for d in ("model", "provider", "effort",
                                                           "dialect", "mode", "level")) == key]
            for e in sorted(mine, key=lambda e: int(e["sample"])):
                scores.setdefault(e["task_id"], []).append(
                    None if e["termination"] == "error" else float(e["effective_score"]))
            means = [_mean(v) for v in scores.values() if _mean(v) is not None]
            if not means or abs(sum(means) / len(means) - g["effective_mean"]) > 0.05:
                print(f"warning: {s['run_id']} {g['label']}: episodes.csv gives "
                      f"{sum(means) / max(len(means), 1):.2f}, its summary {g['effective_mean']}")
            verifiers = ", ".join(sorted({e["verifier_version"] for e in mine}))
            cols.append((f"{g['key']['model'].split('/')[-1]}, {effort_cell(g)}\n"
                         f"{s['taskset']} x {g['k_max']}, {verifiers}", scores))
    return cols


def _mean(samples: List[Optional[float]]) -> Optional[float]:
    """The mean of the samples that did not error, or None when all did."""
    done = [x for x in samples if x is not None]
    return sum(done) / len(done) if done else None


def eval_set_rows(cols, tasks_dir: Optional[Path], workbook_dir: Path) -> List[list]:
    """One row per task of d1-dev and d1-test (d1-variance is d1-test's first 20),
    its files under ``tasks/eval/<set>/seed-<seed>/``."""
    variance = {t["task_id"] for t in tasksets.load("d1-variance")["tasks"]}
    rows = []
    for name in ("d1-dev", "d1-test"):
        for i, entry in enumerate(tasksets.load(name)["tasks"], start=1):
            task = tasksets.task_from_entry(entry)
            ttype = task_type(entry["task_type"])
            graded = checks_in_scope(ttype.asks, list(WEIGHTS))
            dialed = entry.get("dialed")
            cells = []
            for _, scores in cols:
                s = scores.get(entry["task_id"])
                m = _mean(s) if s else None
                cells += ["" if not s else ("all errored" if m is None else round(m, 1)),
                          ", ".join("error" if x is None else f"{x:.1f}" for x in s) if s else ""]
            rows.append([
                name, i, entry["seed"], entry["task_type"], entry["sheets"], entry["curves"],
                "yes" if task.truth.counts["equations"] else
                ("asked, none fit" if entry["equations"] else "no"),
                entry["task_id"], "yes" if name == "d1-test" and entry["task_id"] in variance else "",
                (f"dialed {dialed['task_type']} on {dialed['sheets']} sheet(s), which this seed "
                 "cannot make" if dialed else ""),
                ", ".join(graded), sum(WEIGHTS[c] for c in graded), *cells,
                task.brief.prompts["explicit"], task.brief.prompts["vague"],
                *task_links(task, None if tasks_dir is None else
                            tasks_dir / "eval" / name / f"seed-{entry['seed']}", workbook_dir)])
    return rows


def _rate(x: Optional[float]) -> str:
    return "" if x is None else f"{100 * x:.0f}%"


def d1_run_rows(runs: List[dict], d1_board: Optional[dict]) -> List[list]:
    """One row per row of every published D1 run, with why it is or is not ranked."""
    status = {}
    if d1_board:
        for r in d1_board.get("ranked") or []:
            status[(r["run_id"], r["label"])] = f"ranked {r['rank']} on {d1_board['leaderboard_set']}"
        for r in d1_board.get("reference") or []:
            status[(r["run_id"], r["label"])] = "reference row (a harness agent)"
        for o in d1_board.get("others") or []:
            for g in o["rows"]:
                status[(o["run_id"], g["label"])] = "not ranked: " + "; ".join(o["reasons"])
    rows = []
    for s in runs:
        v = s["versions"]
        scored = (f"{s['current_versions']['verifier_version']} (re-scored)" if s.get("reverified")
                  else ", ".join(v["verifier_version"]))
        for g in s["rows"]:
            pc = g.get("per_check") or {}
            cost = g.get("cost_per_sheet")
            rows.append([
                s["run_id"], s["taskset"], g["label"], effort_cell(g),
                status.get((s["run_id"], g["label"]), "not on the board"),
                g["effective_mean"], f"[{g['ci_low']:.1f}, {g['ci_high']:.1f}]", g["half_width"],
                f"{g['n_tasks']} x {g['k_max']}", _rate(g["hard_fail_rate"]),
                _rate(g["clean_sheet_rate"]), _rate(g["submit_rate"]),
                f"{100 * g['invalid_call_rate']:.1f}%", _rate(g["recovery_rate"]),
                f"{g['steps_median']:g} / {g['steps_p90']:g}", round(g["output_tokens_mean"]),
                round(g["input_tokens_mean"]), g["elapsed_median_s"],
                f"${cost:.2f}" if cost is not None else "—",
                scored, ", ".join(v["spec_version"]), ", ".join(v["generator_version"]),
                s.get("harness_version") or "", ((s.get("pins") or {}).get("commit") or "")[:8],
                *[round(pc[c]["mean_credit"], 2) if c in pc and pc[c]["n"] else "–"
                  for c in WEIGHTS]])
    return rows


def d1_run_headers() -> List[str]:
    return (["Run", "Task set", "Row", "Effort", "Status", "Effective", "95% CI", "±",
             "Tasks x k", "Hard-fail", "Clean sheet", "Submitted", "Invalid calls", "Recovery",
             "Steps (median / p90)", "Output tokens / episode", "Input tokens / episode",
             "Elapsed median (s)", "Cost / sheet", "Scored by", "Spec", "Generator", "Harness",
             "Engine commit"]
            + [f"{c} credit (weight {w})" for c, w in WEIGHTS.items()])


# ------------------------------------------------------------------- pilots


def pilot_number(probe) -> int:
    """The brainstorm's number of a pilot, from its ``pNN-`` id."""
    return int(probe.id.split("-")[0][1:])


#: the columns probe_links fills
PROBE_LINK_HEADS = ["Scripted solution", "Base files", "Start files", "Reference", "PDF",
                    "Start (picture)", "Reference (picture)"]
PROBE_LINK_WIDTHS = [44, 30, 14, 12, 6, 12, 12]


def probe_links(probe, refs: Path, kind: str, tasks_dir: Optional[Path]) -> list:
    """A probe's (or pilot's) scripted-solution verdict, the base files its start
    document attaches, links to its start project, reference folder and PDF, and
    pictures of its start and of its reference, both plotted with print_pdf.
    The pictures go under ``tasks/<kind>/<id>/``, the start under ``tasks/starts/``."""
    folder = refs / probe.id
    ref = (json.loads((folder / "reference.json").read_text())
           if (folder / "reference.json").exists() else None)
    verdict = ((("PASS: " if ref["passed"] else "FAIL: ") + ref["detail"]) if ref
               else f"(no reference under {refs})")
    uri = folder.resolve().as_uri()
    ref_link = Link(f"{probe.id}/", uri + "/") if ref else ""
    pdf_link = Link("PDF", f"{uri}/{ref['pdf']}") if ref and ref.get("pdf") else ""
    if tasks_dir is None:
        base = _base_cell(folder / ref["document"]) if ref else ""
        return [verdict, base, "", ref_link, pdf_link, "", ""]
    document, start_pdf, start_pic = plot_start(probe.start, tasks_dir)
    start_link = Link(f"{probe.start}/", document.parent.resolve().as_uri() + "/")
    finished = None
    if ref and ref.get("pdf"):
        finished = pdf_picture(folder / ref["pdf"], tasks_dir / kind / probe.id, "finished")
    return [verdict, _base_cell(document), start_link, ref_link, pdf_link,
            Img(start_pic) if start_pic else "(nothing drawn yet)",
            Img(finished) if finished else ""]


def probe_rows(marks, tasks_dir: Optional[Path]) -> List[list]:
    """One row per Track P probe, with every ranked model's marks on it."""
    return [[p.id, probe_set(p), ", ".join(p.tags), p.start, p.prompt,
             *[m.get(p.id, "") for _, m in marks],
             *probe_links(p, PROBE_REFS, "probe", tasks_dir)] for p in PROBES]


def pilot_rows(tasks_dir: Optional[Path]) -> List[list]:
    """One row per pilot, by the brainstorm's numbers, with its scripted solution."""
    return [[pilot_number(p), PILOT_NAMES.get(pilot_number(p), ""), p.id,
             ", ".join(t for t in p.tags if t != "pilot"), p.start, p.prompt, p.note,
             *probe_links(p, PILOT_REFS, "pilot", tasks_dir)]
            for p in sorted(PILOT_PROBES, key=lambda p: (pilot_number(p), p.id))]


def pilot_runs() -> List[str]:
    """The pilot model runs kept so far (folders under benchmarks/pilot_runs)."""
    return sorted(p.name for p in PILOT_RUNS.iterdir() if p.is_dir()) if PILOT_RUNS.exists() else []


# ------------------------------------------------------------- leaderboard


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _board_row(r: dict, tiers: dict, status: str) -> list:
    """One leaderboard row (ranked or not) as the workbook shows it."""
    t = r["tiers"]
    pins = r.get("pins") or {}
    per_tier = [f"{t[k]['passes']}/{t[k]['attempts']} ({_pct(t[k]['rate'])})"
                if k in t else "" for k in tiers]
    cost = r.get("cost_per_task")
    return [r.get("rank", ""), r["name"], r["class"], r["runner"], r["run"],
            r["model"], r.get("backend", ""), r.get("effort_label") or r.get("effort") or "default",
            _pct(r["score"]), f"[{_pct(r['ci'][0])}, {_pct(r['ci'][1])}]", *per_tier,
            f"{r['passes']}/{r['valid']}", r["probes_attempted"], r["always"], r["never"],
            _pct(r["hard_fail"]), _pct(r["invalid_rate"]),
            f"${cost:.2f}" if cost is not None else "—", r.get("cost_source") or "",
            ", ".join(f"{label}: {v['passes']}/{v['valid']}" for label, v in r["per_label"].items()),
            r.get("stale", 0), pins.get("instructions_differ", ""), status]


def board_rows(board: dict):
    """The Track P board: the ranked rows, then those not ranked yet and why."""
    tiers = board["tiers"]
    rows = [_board_row(r, tiers, "ranked") for r in board["ranked"]]
    rows += [_board_row(r, tiers, f"not ranked: {r['why']}") for r in board["unranked"]]
    return rows


def board_headers(board: dict):
    tiers = board["tiers"]
    return (["Rank", "Model", "Class", "Runner", "Run folder", "Model ID", "Backend", "Effort",
             "Pass rate", "95% CI"]
            + [f"{k} ({len(v['probes'])}): {v['name']}" for k, v in tiers.items()]
            + ["Passes / attempts", "Probes attempted", "Always pass", "Never pass",
               "Hard-fail", "Invalid calls", "Cost / task", "Cost source", "Per repeat",
               "Episodes on an earlier task text", "Episodes on earlier server instructions",
               "Status"])


def probe_marks(board: dict):
    """Column header and per-probe marks for every ranked row of the board."""
    cols = []
    for r in board["ranked"]:
        marks = {pid: p["marks"] for pid, p in r["probes"].items()}
        effort = r.get("effort_label") or r.get("effort") or "default"
        cols.append((f"{r['name']}, {effort}{'' if effort.startswith('thinking') else ' effort'}\n"
                     f"{r['run']} (rank {r['rank']})", marks))
    return cols


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="benchmarks/prompts/roaddraft_prompts.xlsx")
    ap.add_argument("--seeds", default="1-6", help="D1 seeds per task type and sheet count")
    ap.add_argument("--no-files", action="store_true",
                    help="prompts only; do not write the task files or link to them")
    ap.add_argument("--reuse-files", action="store_true",
                    help="keep task folders already written for the same task id (renders "
                         "and all), only re-making the pictures")
    ns = ap.parse_args(argv)
    global REUSE
    REUSE = ns.reuse_files
    seeds = list(_seeds(ns.seeds))
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tasks_dir = None if ns.no_files else out.parent / "tasks"
    TASKS_ROOT = str((out.parent / "tasks").resolve())
    if not REAL_CATALOG.exists():
        raise SystemExit(f"{REAL_CATALOG} is missing: run scripts/real_tasks.py first")
    real = json.loads(REAL_CATALOG.read_text())
    board = json.loads(TRACK_P.read_text()) if TRACK_P.exists() else None
    d1_board = json.loads(D1_BOARD.read_text()) if D1_BOARD.exists() else None
    runs = published_runs()
    sets = {name: tasksets.load(name) for name in tasksets.NAMES}
    pilot_done = pilot_runs()

    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    readme = [
        ("RoadDraft prompts", None),
        ("Every prompt a model is scored on, generated from the code on "
         f"{dt.date.today().isoformat()}.", None),
        ("", None),
        ("Sheet", "What it holds"),
        ("Task types", f"The {len(TASK_TYPES)} D1 task types: what the drafter starts with, what "
                       "is asked for, and which checks are graded (renormalised to 100)."),
        ("D1 tasks", f"One row per D1 task: each type on one and two sheets, seeds "
                     f"{seeds[0]}-{seeds[-1]}. Each task has an EXPLICIT prompt (the request as a "
                     "PE would brief a drafter: a few plain sentences that guide the work and name "
                     "the standards it is graded on, such as scale, layers, text heights, label "
                     "forms by example, table columns and title-block values; graded exactly) and "
                     "a VAGUE prompt (the request in a sentence; unstated conventions graded "
                     "leniently). The gap between the two "
                     "scores, paired by task, is the prompt-gap metric. Files, Start and "
                     "Finished link to the task's folder and full-size renders of what the "
                     "drafter starts with and of the reference solution's finished sheet; the "
                     "last two columns show those two renders as pictures (both sheets side by "
                     "side on a two-sheet task). Click a picture and enlarge it to read it. Base "
                     "files lists what the starting document attaches as references (NAME: file, "
                     "anything those attach in turn indented under them); the files are beside "
                     "start.rdoc.json in the task's folder."),
        ("Task files", f"{TASKS_ROOT}/<type>/<n>-sheet/seed-<n>/: brief.json, "
                       "truth.json, start.rdoc.json (the starting document; any base drawing "
                       "beside it), finished.rdoc.json and reference.journal.jsonl (the reference "
                       "solution), start-*.png and finished-*.png (one per sheet, or the model). "
                       "Open the .rdoc.json files in RoadDraft. The links are absolute paths to "
                       "that folder on this Mac, so this workbook can be opened from anywhere; "
                       "if a link does not open, paste the path above into Finder's Go to Folder."),
        ("Real-sheet tasks", f"{len(real['tasks'])} D1 tasks on real plan sheets: the Caltrans, "
                             "FHWA WFL and CFL, and FDOT sample sheets redrafted into RoadDraft "
                             "files. Each sheet file references its real base files (alignments, "
                             "corridor, survey) through a viewport at the published scale and "
                             "twist; the task letters one alignment to the spec, around the "
                             "sheet's own notes, callouts and other alignments. That alignment's "
                             "published annotation is removed from the copies the task ships. "
                             "Only pairings whose reference solution verifies 100 and starting "
                             f"file 0 are kept ({len(real['excluded'])} left out; "
                             f"{REAL_CATALOG} lists why). Base files lists the real base files "
                             "the starting sheet attaches; the Redraft column links to the "
                             "published redraft folder under examples/ they were copied from."),
        ("Real task files", f"{TASKS_ROOT}/real/<agency>/<sheet>/<alignment>/<type>/: as for the "
                            "D1 tasks, plus the real base files beside start.rdoc.json."),
        ("Eval sets", f"The D1 task sets the eval harness runs, as their manifests pin them "
                      f"(benchmarks/tasksets, generator {sets['d1-test']['generator_version']}, "
                      f"spec {sets['d1-test']['spec_version']}): d1-dev = "
                      f"{len(sets['d1-dev']['tasks'])} tasks on seeds 1-50, for iteration and "
                      f"never reported; d1-test = {len(sets['d1-test']['tasks'])} held-out tasks "
                      f"on seeds 1000-1099, the set the {LEADERBOARD_SET} leaderboard ranks on; "
                      f"d1-variance = d1-test's first {len(sets['d1-variance']['tasks'])} tasks, "
                      "sampled k = 5 times to size the interval. One row per task with its dials, "
                      "both prompts, its files, base files and start and finished pictures as on "
                      f"the D1 tasks sheet ({TASKS_ROOT}/eval/<set>/seed-<n>/), and every "
                      "published run's score on it: the mean effective "
                      "score over its samples, then the samples in order (a sample that errored "
                      "shows as error and is left out of the mean, as the run's report does)."),
        ("D1 runs", f"The {len(runs)} published D1 run(s) (benchmarks/runs/<run>/summary.json): "
                    "effective score (0 on a hard fail, else the rubric score; per task over its "
                    "samples, then over tasks) with its bootstrap CI over tasks within task type, "
                    "the behaviour rates, the verifier it was scored with, each check's mean "
                    "credit (0-1, over the episodes whose task grades it), and why it is not "
                    "ranked yet. The check names are listed below the table."),
        ("D1 rules", "The benchmark rules sent ahead of every D1 prompt, at both levels."),
        ("Probes", f"The {len(PROBES)} Track P capability probes (the current leaderboard), "
                   "each a single natural-language request. One column per ranked model "
                   "shows its k = 3 attempts on that probe, in order: P = passed, · = failed, "
                   "B = ended by budget (counts as a failure), X = excluded (infrastructure). "
                   "Then the scripted solution's verdict, the base files the start document "
                   "attaches, links to the start project (" + TASKS_ROOT + "/starts/<start>/"
                   f"project/), the reference folder ({PROBE_REFS}/<id>/: the finished "
                   "document, journal, PDF and DXF) and its PDF, and pictures of the start and "
                   f"of the reference, both plotted with print_pdf (up to {PDF_PAGES} pages)."),
        ("Probe rules", "The rules and report request wrapped around each probe prompt."),
        ("Leaderboard", ("The Track P leaderboard as of "
                         f"{board['as_of']} (k = {board['k']}, {board['probes']} probes, probe "
                         f"set {board['probe_set_sha256'][:19]}): the ranked rows, then those "
                         "not ranked yet and why. Pass rate is the mean over probes of each "
                         "probe's passes over attempts; the CI is a bootstrap over probes then "
                         "attempts. Ties break on hard-fail rate, then invalid-call rate, then "
                         "cost. Overlapping intervals are not separated. The Track D (D1) "
                         "board's state is below the table.") if board else
                        f"{TRACK_P} was missing; run python -m roaddraft.runners leaderboard"),
        ("Pilot probes", f"The {len(PILOT_PROBES)} harder-task pilots (docs/Probes_Pilots.md), "
                         "set on the real example sheets: input that is not clean data, layout "
                         "decisions, changes that ripple, problems nobody named. Off the board: "
                         "the Probes sheet, the probe-set hash and the leaderboard do not include "
                         "them. Each row has the brainstorm's number and name, the prompt, the "
                         "note (what is planted, what a naive answer gets wrong), then the same "
                         "columns as the Probes sheet: verdict, base files, start project, "
                         f"reference ({PILOT_REFS}/<id>/) and the two pictures; a scan pilot's "
                         "start picture also shows the scanned sheet it hands the model "
                         "(scans/ in its start project). Pilot 16 (the 33 "
                         "probes on the basic tool profile) has no rows of its own. Model runs: "
                         + (", ".join(pilot_done) if pilot_done else "none yet") + "."),
        ("", None),
        ("Spec", f"{SPEC_VERSION} ({spec_hash()}), frozen 2026-10-16"),
        ("Generator", f"{GENERATOR_VERSION} (seeded); {REAL_GENERATOR_VERSION} (real sheets)"),
        ("Verifier", f"{VERIFIER_VERSION}; eval harness {HARNESS_VERSION}"),
        ("Two sheets", "A longer alignment laid out on C-101 and C-102, breaking at a match line "
                       "on a tangent; each sheet shows its own part, carries its own curve table, "
                       "north arrow and title block, and a MATCH LINE STA ... SEE SHEET ... label."),
        ("Dial cycle", "D1 tasks sheet: seed 1 = 1 curve, no equation; seed 2 = 1 curve, "
                       "equation; ... cycling through 1-3 curves x equation off/on. The eval sets "
                       "have their own, pinned by the manifests: by position in the set, curves "
                       "cycle 1, 2, 3, the equation flips every three tasks, the sheet count every "
                       "six, and the task type cycles through the seeded types (a seed that cannot "
                       "make its type takes the next one, noted in the Dial fallback column)."),
        ("Regenerate", "see the docstring of scripts/export_prompts.py"),
        ("Source", "src/roaddraft/tasks/{types,prompts,generator,real}.py (D1), "
                   "src/roaddraft/probes/ (Track P)"),
    ]
    for i, (a, b) in enumerate(readme, start=1):
        ca = ws.cell(row=i, column=1, value=a)
        cb = ws.cell(row=i, column=2, value=b)
        ca.font = Font(name=FONT, bold=(i in (1, 4) or b is not None), size=14 if i == 1 else 10)
        cb.font = Font(name=FONT, bold=(i == 4), size=10)
        ca.alignment = cb.alignment = TOP_WRAP if b is not None else Alignment(vertical="top")
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 110
    for i, (_, b) in enumerate(readme, start=1):
        if b:
            ws.row_dimensions[i].height = 13.5 * _lines(b, 110) + 4

    ws = wb.create_sheet("Task types")
    _table(ws, ["Type", "What it asks", "Starts with", "Graded groups", "Checks graded",
                "Points in play"], [16, 44, 52, 40, 44, 10], catalog_rows(), wrap_cols=(2, 3, 4, 5))

    ws = wb.create_sheet("D1 tasks")
    _table(ws, ["Type", "Sheets", "Seed", "Task ID", "What it asks", "Starts with",
                "Graded groups", "Checks graded", "Points", "Curves", "Station equation",
                "EXPLICIT prompt", "VAGUE prompt", *TASK_LINK_HEADS],
           [15, 7, 6, 24, 30, 36, 28, 30, 7, 7, 12, 95, 40, *TASK_LINK_WIDTHS],
           d1_rows(seeds, tasks_dir, out.parent), wrap_cols=(5, 6, 7, 8, 12, 13, 17))

    ws = wb.create_sheet("Real-sheet tasks")
    _table(ws, ["Agency", "Sample sheet", "Sheet", "Kind", "Scale", "Twist °", "Alignment",
                "Other alignments", "Type", "Task ID", "Graded groups", "Checks graded",
                "Points", "Tangents", "Curves", "Labels", "EXPLICIT prompt", "VAGUE prompt",
                *TASK_LINK_HEADS[:4], "Redraft (source of the sheet and base files)",
                *TASK_LINK_HEADS[4:]],
           [16, 22, 9, 12, 9, 8, 10, 18, 18, 24, 28, 30, 7, 8, 7, 7, 95, 40,
            *TASK_LINK_WIDTHS[:4], 24, *TASK_LINK_WIDTHS[4:]],
           real_rows(real, tasks_dir, out.parent), wrap_cols=(8, 11, 12, 17, 18, 22, 23))

    ws = wb.create_sheet("Eval sets")
    cols = run_columns(runs)
    score_heads = [h for head, _ in cols for h in (head, head.split("\n")[0] + "\nsamples")]
    n = 12 + len(score_heads)
    _table(ws, ["Set", "#", "Seed", "Type", "Sheets", "Curves", "Station equation", "Task ID",
                "In d1-variance", "Dial fallback", "Checks graded", "Points", *score_heads,
                "EXPLICIT prompt", "VAGUE prompt", *TASK_LINK_HEADS],
           [8, 5, 6, 16, 7, 7, 11, 24, 10, 22, 30, 7, *[14, 22] * len(cols), 95, 40,
            *TASK_LINK_WIDTHS],
           eval_set_rows(cols, tasks_dir, out.parent),
           wrap_cols=(10, 11, *range(14, n + 1, 2), n + 1, n + 2, n + 6))
    ws.row_dimensions[1].height = 56

    ws = wb.create_sheet("D1 runs")
    rows = d1_run_rows(runs, d1_board)
    _table(ws, d1_run_headers(),
           [30, 11, 30, 16, 34, 9, 13, 6, 8, 8, 8, 9, 8, 8, 10, 10, 10, 9, 8, 18, 6, 9, 8, 9,
            *[9] * len(WEIGHTS)], rows, wrap_cols=(1, 3, 5))
    ws.row_dimensions[1].height = 56
    base = len(rows) + 3
    legend = [("Check", "Weight", "What it grades")] + [
        (c["id"], c["weight"], c["name"]) for c in DRAFTING_SPEC_V1["checks"]]
    for i, line in enumerate(legend):
        for j, value in enumerate(line, start=1):
            c = ws.cell(row=base + i, column=j, value=value)
            c.font = Font(name=FONT, size=10, bold=(i == 0))
            c.alignment = TOP_WRAP
        ws.merge_cells(start_row=base + i, start_column=3, end_row=base + i, end_column=12)
        ws.row_dimensions[base + i].height = 13.5 * _lines(line[2], 150) + 4

    ws = wb.create_sheet("D1 rules")
    _table(ws, ["Sent before every D1 prompt (explicit and vague)"], [120],
           [[RULES_TEMPLATE.format(design="<the design bullet: see below>")],
            ["Design bullet, every task but create-alignment: "
             + rules(generate_task(1).brief).splitlines()[3][2:]],
            ["Design bullet, create-alignment: "
             + rules(generate_task(1, task_type="create-alignment").brief).splitlines()[3][2:]]],
           wrap_cols=(1,))

    ws = wb.create_sheet("Probes")
    marks = probe_marks(board) if board else []
    m = len(marks)
    _table(ws, ["Probe ID", "Set", "Tags", "Starts from", "Prompt", *[h for h, _ in marks],
                *PROBE_LINK_HEADS],
           [26, 10, 28, 12, 100, *[14] * m, *PROBE_LINK_WIDTHS], probe_rows(marks, tasks_dir),
           wrap_cols=(5, 6 + m, 7 + m))
    ws.row_dimensions[1].height = 42

    if board:
        ws = wb.create_sheet("Leaderboard")
        rows = board_rows(board)
        _table(ws, board_headers(board),
               [6, 22, 16, 30, 16, 20, 12, 8, 10, 16, *[14] * len(board["tiers"]),
                11, 9, 8, 8, 9, 9, 9, 30, 36, 12, 12, 44],
               rows, wrap_cols=(4, 19, 20, 23))
        ws.row_dimensions[1].height = 56
        notes = [("Ranked from", ", ".join(board["ranked_from"])),
                 ("Generated by", board["generated_by"]),
                 ("Full board", "benchmarks/leaderboard/TRACK_P.md (one card per row under "
                                "cards/ with the section 3.2 measures, the pins and every "
                                "probe's attempts)")]
        if d1_board is not None:
            state = (f"{len(d1_board['ranked'])} ranked row(s) on {d1_board['leaderboard_set']}"
                     if d1_board.get("ranked") else
                     f"no ranked run yet on {d1_board['leaderboard_set']}: a row needs a "
                     "published run under a frozen spec (v0.1: spec v1, then d1-variance x 5 "
                     "samples, then d1-test x at least three models)")
            others = d1_board.get("others") or []
            if others:
                state += (f"; {len(others)} published run(s) not ranked, on the D1 runs sheet ("
                          + ", ".join(f"{g['label'].split(' · ')[0].split('/')[-1]} "
                                      f"{g['effective_mean']:.1f} on {o['taskset']}"
                                      for o in others for g in o["rows"]) + ")")
            notes.append(("Track D (D1) board", f"{state}; report {d1_board['report_version']}, "
                                                "benchmarks/runs/LEADERBOARD.md"))
        base = len(rows) + 3
        for i, (a, b) in enumerate(notes):
            ca = ws.cell(row=base + i, column=1, value=a)
            cb = ws.cell(row=base + i, column=2, value=b)
            ca.font = Font(name=FONT, bold=True, size=10)
            cb.font = Font(name=FONT, size=10)
            ws.merge_cells(start_row=base + i, start_column=2, end_row=base + i, end_column=12)
            cb.alignment = TOP_WRAP
            ws.row_dimensions[base + i].height = 13.5 * _lines(b, 150) + 4
        if d1_board and d1_board.get("ranked"):  # whatever shape make_leaderboard.py gives it
            ws = wb.create_sheet("D1 leaderboard")
            keys = list(d1_board["ranked"][0].keys())
            _table(ws, keys, [16] * len(keys),
                   [[json.dumps(r.get(k)) if isinstance(r.get(k), (dict, list)) else r.get(k)
                     for k in keys] for r in d1_board["ranked"]])

    ws = wb.create_sheet("Probe rules")
    sample = prompting.RULES.format(extra="[draft probes add:" + prompting.NO_CALCULATOR + "]",
                                    task="<the probe's prompt>",
                                    report="<T1 or T2 report request, below>")
    _table(ws, ["Part", "Text"], [18, 110],
           [["Wrapper", sample], ["T1 report (draft probes)", prompting.T1_REPORT],
            ["T2 report (all others)", prompting.T2_REPORT]], wrap_cols=(2,))

    ws = wb.create_sheet("Pilot probes")
    _table(ws, ["#", "Pilot", "Probe ID", "Tags", "Starts from", "Prompt", "Note",
                *PROBE_LINK_HEADS],
           [5, 22, 28, 24, 16, 90, 60, *PROBE_LINK_WIDTHS], pilot_rows(tasks_dir),
           wrap_cols=(2, 4, 5, 6, 7, 8, 9))

    wb.save(out)
    print(f"wrote {out}: {len(TASK_TYPES)} types x 2 sheet counts x {len(seeds)} seeds x 2 "
          f"levels, {len(real['tasks'])} real-sheet tasks, "
          + ", ".join(f"{name} {len(s['tasks'])}" for name, s in sets.items())
          + f", {len(runs)} published D1 run(s), {len(PROBES)} probes"
          + (f", {len(board['ranked'])} ranked + {len(board['unranked'])} unranked board rows"
             if board else "")
          + f", {len(PILOT_PROBES)} pilots"
          + ("" if tasks_dir is None else f"; task files under {tasks_dir}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
