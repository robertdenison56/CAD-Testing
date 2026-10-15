"""Write every prompt a model is scored on to one Excel workbook, with the task files beside it.

    PYTHONPATH=src uv run --no-project --python 3.9 --with openpyxl --with jsonschema \\
        --with ezdxf --with matplotlib python scripts/export_prompts.py \\
        [--out benchmarks/prompts/roaddraft_prompts.xlsx] [--seeds 1-6] [--no-files]

Sheets: a read-me, the D1 task catalog, one row per D1 task (every task type on
one and two sheets, explicit and vague prompt per task, links to its files),
one row per real-sheet task (benchmarks/real_tasks/catalog.json, which
scripts/real_tasks.py writes first), the rules every D1 prompt is prefixed
with, and the Track P probe prompts.

The task files go under ``benchmarks/prompts/tasks/<type>/<n>-sheet/seed-<n>/``
(gitignored; regenerate with this script): the brief and truth, the starting
document (``start.rdoc.json``, plus any base drawing shipped with the task),
the reference solution's finished document and journal, and a PNG of every
sheet (or the model) before and after.  The workbook links to them by
absolute path (``file://`` URLs to this checkout), so a copy of the workbook
opened from anywhere on this Mac still reaches them.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from PIL import Image as PILImage, ImageFilter
from openpyxl.utils import get_column_letter

from roaddraft.probes import prompting
from roaddraft.probes.tasks import DRAFT_PROBES, FIND_PROBES, PROBES, TIER2_PROBES, TIER3_PROBES
from roaddraft.tasks.brief import GENERATOR_VERSION, Task
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.prompts import RULES_TEMPLATE, rules
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash
from roaddraft.tasks.real import REAL_GENERATOR_VERSION, build_real_task
from roaddraft.tasks.types import PHASE_ORDER, REAL_TASK_TYPES, TASK_TYPES, checks_in_scope, task_type

#: the validated real-sheet tasks (scripts/real_tasks.py writes it)
REAL_CATALOG = Path("benchmarks/real_tasks/catalog.json")

#: the dev-set dial cycle: every curve count with and without a station equation
DIALS = [(curves, eq) for curves in (1, 2, 3) for eq in (False, True)]
WEIGHTS = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}
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
                                 "", "", "", "", f"(no task: {why})", "", "", "", "", "", ""])
                    continue
                b, t = task.brief, task.truth
                links = ["", "", "", "", ""]
                if tasks_dir is not None:
                    folder = tasks_dir / ttype.name / f"{sheets}-sheet" / f"seed-{seed}"
                    pngs = write_task_files(task, folder)
                    rel = folder.relative_to(workbook_dir).as_posix()
                    uri = folder.resolve().as_uri()  # absolute: the workbook may be opened anywhere
                    links = [Link(rel + "/", uri + "/"),
                             Link("start", f"{uri}/{pngs['start']}") if pngs["start"]
                             else "(nothing drawn yet)",
                             Link("finished", f"{uri}/{pngs['finished']}") if pngs["finished"]
                             else "", *_pictures(folder, pngs)]
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
        links = ["", "", "", "", ""]
        if tasks_dir is not None:
            folder = (tasks_dir / "real" / t["agency"] / t["sheet_id"]
                      / ("whole-sheet" if t.get("per_sheet") else t["alignment"].replace(" ", "-"))
                      / t["type"])
            pngs = write_task_files(task, folder)
            rel = folder.relative_to(workbook_dir).as_posix()
            uri = folder.resolve().as_uri()
            links = [Link(rel + "/", uri + "/"),
                     Link("start", f"{uri}/{pngs['start']}") if pngs["start"] else "",
                     Link("finished", f"{uri}/{pngs['finished']}") if pngs["finished"] else "",
                     *_pictures(folder, pngs)]
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
                     f"{seeds[0]}-{seeds[-1]}. Each task has an EXPLICIT prompt (the standards it "
                     "touches spelled out, graded exactly) and a VAGUE prompt (the request in a "
                     "sentence; unstated conventions graded leniently). The gap between the two "
                     "scores, paired by task, is the prompt-gap metric. Files, Start and "
                     "Finished link to the task's folder and full-size renders of what the "
                     "drafter starts with and of the reference solution's finished sheet; the "
                     "last two columns show those two renders as pictures (both sheets side by "
                     "side on a two-sheet task). Click a picture and enlarge it to read it."),
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
                             f"{REAL_CATALOG} lists why)."),
        ("Real task files", f"{TASKS_ROOT}/real/<agency>/<sheet>/<alignment>/<type>/: as for the "
                            "D1 tasks, plus the real base files beside start.rdoc.json."),
        ("D1 rules", "The benchmark rules sent ahead of every D1 prompt, at both levels."),
        ("Probes", f"The {len(PROBES)} Track P capability probes (the current leaderboard), "
                   "each a single natural-language request."),
        ("Probe rules", "The rules and report request wrapped around each probe prompt."),
        ("", None),
        ("Spec", f"{SPEC_VERSION} ({spec_hash()}), DRAFT for PE review"),
        ("Generator", f"{GENERATOR_VERSION} (seeded); {REAL_GENERATOR_VERSION} (real sheets)"),
        ("Two sheets", "A longer alignment laid out on C-101 and C-102, breaking at a match line "
                       "on a tangent; each sheet shows its own part, carries its own curve table, "
                       "north arrow and title block, and a MATCH LINE STA ... SEE SHEET ... label."),
        ("Dial cycle", "seed 1 = 1 curve, no equation; seed 2 = 1 curve, equation; ... cycling "
                       "through 1-3 curves x equation off/on. Provisional: the E2 taskset "
                       "manifests will pin the final assignment."),
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
                "EXPLICIT prompt", "VAGUE prompt", "Files", "Start", "Finished",
                "Start (picture)", "Finished (picture)"],
           [15, 7, 6, 24, 30, 36, 28, 30, 7, 7, 12, 95, 40, 8, 8, 9, 12, 12],
           d1_rows(seeds, tasks_dir, out.parent), wrap_cols=(5, 6, 7, 8, 12, 13))

    ws = wb.create_sheet("Real-sheet tasks")
    _table(ws, ["Agency", "Sample sheet", "Sheet", "Kind", "Scale", "Twist °", "Alignment",
                "Other alignments", "Type", "Task ID", "Graded groups", "Checks graded",
                "Points", "Tangents", "Curves", "Labels", "EXPLICIT prompt", "VAGUE prompt",
                "Files", "Start", "Finished", "Start (picture)", "Finished (picture)"],
           [16, 22, 9, 12, 9, 8, 10, 18, 18, 24, 28, 30, 7, 8, 7, 7, 95, 40, 8, 8, 9, 12, 12],
           real_rows(real, tasks_dir, out.parent), wrap_cols=(8, 11, 12, 17, 18))

    ws = wb.create_sheet("D1 rules")
    _table(ws, ["Sent before every D1 prompt (explicit and vague)"], [120],
           [[RULES_TEMPLATE.format(design="<the design bullet: see below>")],
            ["Design bullet, every task but create-alignment: "
             + rules(generate_task(1).brief).splitlines()[3][2:]],
            ["Design bullet, create-alignment: "
             + rules(generate_task(1, task_type="create-alignment").brief).splitlines()[3][2:]]],
           wrap_cols=(1,))

    ws = wb.create_sheet("Probes")
    rows = [[p.id, probe_set(p), ", ".join(p.tags), p.start, p.prompt] for p in PROBES]
    _table(ws, ["Probe ID", "Set", "Tags", "Starts from", "Prompt"],
           [26, 10, 28, 12, 100], rows, wrap_cols=(5,))

    ws = wb.create_sheet("Probe rules")
    sample = prompting.RULES.format(extra="[draft probes add:" + prompting.NO_CALCULATOR + "]",
                                    task="<the probe's prompt>",
                                    report="<T1 or T2 report request, below>")
    _table(ws, ["Part", "Text"], [18, 110],
           [["Wrapper", sample], ["T1 report (draft probes)", prompting.T1_REPORT],
            ["T2 report (all others)", prompting.T2_REPORT]], wrap_cols=(2,))

    wb.save(out)
    print(f"wrote {out}: {len(TASK_TYPES)} types x 2 sheet counts x {len(seeds)} seeds x 2 "
          f"levels, {len(real['tasks'])} real-sheet tasks, {len(PROBES)} probes"
          + ("" if tasks_dir is None else f"; task files under {tasks_dir}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
