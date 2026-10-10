"""Write every prompt a model is scored on to one Excel workbook.

    PYTHONPATH=src uv run --no-project --python 3.9 --with openpyxl --with jsonschema \\
        --with ezdxf --with matplotlib python scripts/export_prompts.py \\
        [--out benchmarks/prompts/roaddraft_prompts.xlsx] [--seeds 1-6]

Sheets: a read-me, the D1 task catalog (every task type on one and two
sheets, explicit and vague prompt per task), the rules every D1 prompt is
prefixed with, and the Track P probe prompts.  Prompts are generated, not
stored, so rerun this after a spec or generator change.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from roaddraft.probes import prompting
from roaddraft.probes.tasks import DRAFT_PROBES, FIND_PROBES, PROBES, TIER2_PROBES, TIER3_PROBES
from roaddraft.tasks.brief import GENERATOR_VERSION
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.prompts import RULES
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, SPEC_VERSION, spec_hash
from roaddraft.tasks.types import PHASE_ORDER, TASK_TYPES, checks_in_scope

#: the dev-set dial cycle: every curve count with and without a station equation
DIALS = [(curves, eq) for curves in (1, 2, 3) for eq in (False, True)]
WEIGHTS = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}

FONT = "Arial"
HEAD_FILL = PatternFill("solid", start_color="1F3864")
BAND_FILL = PatternFill("solid", start_color="F2F2F2")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOP_WRAP = Alignment(wrap_text=True, vertical="top")

PHASE_WORDS = {"layers": "layers", "linework": "centerline", "stationing": "stationing",
               "bearings": "bearings", "callouts": "curve callouts", "sheet": "sheet + viewport",
               "table": "curve table", "north": "north arrow", "title": "title block"}


def _seeds(text: str):
    lo, _, hi = text.partition("-")
    return range(int(lo), int(hi or lo) + 1)


def _lines(text: str, width: int) -> int:
    """Rendered lines of ``text`` in a column ``width`` characters wide."""
    return sum(max(1, math.ceil(len(p) / max(width - 2, 1))) for p in str(text).split("\n"))


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
            c = ws.cell(row=i, column=j, value=value)
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
    phases = [PHASE_WORDS[p] for p in PHASE_ORDER if p in ttype.given and p != "layers"]
    if not phases:
        return "the design only (nothing drawn, no sheet)"
    start = "design, layers, " if "layers" in ttype.given else ""
    return start + ", ".join(phases)


def d1_rows(seeds):
    rows = []
    for ttype in TASK_TYPES.values():
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        for sheets in (1, 2):
            for seed in seeds:
                curves, eq = DIALS[(seed - 1) % len(DIALS)]
                task = generate_task(seed, curves=curves, equations=eq, task_type=ttype.name,
                                     sheets=sheets)
                b, t = task.brief, task.truth
                rows.append([
                    ttype.name, sheets, seed, b.task_id, ttype.summary, _given(ttype),
                    ", ".join(t.scope), ", ".join(graded), sum(WEIGHTS[c] for c in graded),
                    t.counts["curves"],
                    "yes" if t.counts["equations"] else ("asked, none fit" if eq else "no"),
                    b.prompts["explicit"], b.prompts["vague"]])
    return rows


def catalog_rows():
    rows = []
    for ttype in TASK_TYPES.values():
        graded = checks_in_scope(ttype.asks, list(WEIGHTS))
        rows.append([ttype.name, ttype.summary, _given(ttype), ", ".join(ttype.asks),
                     ", ".join(graded), sum(WEIGHTS[c] for c in graded)])
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
    ns = ap.parse_args(argv)
    seeds = list(_seeds(ns.seeds))

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
                     "scores, paired by task, is the prompt-gap metric."),
        ("D1 rules", "The benchmark rules sent ahead of every D1 prompt, at both levels."),
        ("Probes", f"The {len(PROBES)} Track P capability probes (the current leaderboard), "
                   "each a single natural-language request."),
        ("Probe rules", "The rules and report request wrapped around each probe prompt."),
        ("", None),
        ("Spec", f"{SPEC_VERSION} ({spec_hash()}), DRAFT for PE review"),
        ("Generator", GENERATOR_VERSION),
        ("Two sheets", "A longer alignment laid out on C-101 and C-102, breaking at a match line "
                       "on a tangent; each sheet shows its own part, carries its own curve table, "
                       "north arrow and title block, and a MATCH LINE STA ... SEE SHEET ... label."),
        ("Dial cycle", "seed 1 = 1 curve, no equation; seed 2 = 1 curve, equation; ... cycling "
                       "through 1-3 curves x equation off/on. Provisional: the E2 taskset "
                       "manifests will pin the final assignment."),
        ("Regenerate", "see the docstring of scripts/export_prompts.py"),
        ("Source", "src/roaddraft/tasks/{types,prompts,generator}.py (D1), "
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
                "EXPLICIT prompt", "VAGUE prompt"],
           [15, 7, 6, 24, 30, 36, 28, 30, 7, 7, 12, 95, 40], d1_rows(seeds),
           wrap_cols=(5, 6, 7, 8, 12, 13))

    ws = wb.create_sheet("D1 rules")
    _table(ws, ["Sent before every D1 prompt (explicit and vague)"], [120], [[RULES]],
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

    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"wrote {out}: {len(TASK_TYPES)} types x 2 sheet counts x {len(seeds)} seeds x 2 "
          f"levels, {len(PROBES)} probes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
