"""make_deliverables.py LABEL -> the PDFs a reviewer looks at, beside the scores.

For every probe that ran under runs/LABEL, this prints what the model left
behind the way a drafter would plot it, and puts a correct answer next to it:

    runs/LABEL/deliverables/<probe>.pdf             the model's document: the sheet(s) the
                                                    probe names (all three for title-blocks),
                                                    or model space for the drafting probes
    runs/LABEL/deliverables/<probe>.reference.pdf   the probe's scripted solution (Probe.solve)
                                                    applied to a fresh start document, printed
                                                    the same way and, in model space, to the
                                                    same window
    runs/LABEL/deliverables/<probe>.reference/      that solution as a finished RoadDraft project:
                                                    the start project with the handed document
                                                    completed under its own name, and its journal
    runs/LABEL/deliverables/OVERVIEW.pdf            one row per probe: verdict, the check's
                                                    detail, calls and faults; the model's
                                                    result; the reference
    runs/LABEL/deliverables/OVERVIEW.png            the grid: every probe's result, framed
                                                    green for pass and red for fail

Verdicts come from Probe.check on the document on disk, exactly as in
score_runs.py; the prints are made with the engine's own print_pdf (the PLOT
dialog), so a sheet prints on its own paper and model space prints fit to
ANSI D. Re-run after a re-score: it rebuilds everything.
"""
import json
import re
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from roaddraft.api.session import Session
from roaddraft.mcp.server import journal_path
from roaddraft.probes import fixture, tasks
from roaddraft.render import mpl as mpl_render

ROOT = Path(__file__).parent
GREEN, RED, INK, FAINT = "#2e7d32", "#c62828", "#222222", "#777777"


def sheets_named(probe):
    """The sheets a find-probe is about, from its prompt; all of them when it names none."""
    if probe.start != "sheets":
        return []
    named = sorted(set(re.findall(r"C-10\d", probe.prompt)))
    return named or list(fixture.SHEETS)


def load_pair(label, probe, work):
    """(verdict, submitted, reference): the model's document scored against a pristine
    start, and the scripted solution on another pristine start."""
    folder = ROOT / "runs" / label / probe.id
    doc = folder / "project" / fixture.START[probe.start]
    pristine = fixture.start_document(work / "baseline", probe.start)
    baseline = Session.load(pristine, out_dir=work)
    verdict = probe.check(baseline, Session.load(doc, out_dir=work))
    submitted = Session.load(doc, out_dir=work)
    reference = Session.load(fixture.start_document(work / "reference", probe.start),
                             out_dir=work)
    if probe.solve:
        probe.solve(reference)
    return verdict, submitted, reference


def save_reference(probe, reference, out):
    """The reference as a finished RoadDraft project beside its PDF: its start
    project, with the handed document completed under its own name and the
    journal of every command the solution ran. Returns the completed document."""
    folder = out / f"{probe.id}.reference"
    if folder.exists():
        shutil.rmtree(folder)
    home = Path(reference.doc._path)
    shutil.copytree(home.parent, folder)
    document = folder / home.name
    reference.query("save_document", {"path": str(document)})
    reference.query("save_journal", {"path": str(journal_path(document))})
    return document


def trace_counts(label, probe):
    trace = ROOT / "runs" / label / probe.id / "trace.jsonl"
    calls = [json.loads(l) for l in trace.read_text().splitlines()] if trace.exists() else []
    return len(calls), sum(not c["ok"] for c in calls)


def union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def print_pair(probe, submitted, reference, sheets, out):
    """Both documents to PDF through the engine's print_pdf. Returns the model window
    (None for sheets) so the overview draws the same one."""
    bounds = None
    if sheets:
        params = {"sheets": sheets}
    else:
        bounds = union(mpl_render.model_window(submitted.doc),
                       mpl_render.model_window(reference.doc))
        params = {"space": "model", "bounds": list(bounds)}
    submitted.query("print_pdf", {**params, "path": str(out / f"{probe.id}.pdf")})
    reference.query("print_pdf", {**params, "path": str(out / f"{probe.id}.reference.pdf")})
    return bounds


def draw_panel(ax, doc, sheet=None, bounds=None):
    """Draw one document into an existing axes: a sheet in paper inches or model space in
    feet, at the line weights its on-paper size calls for."""
    fig = ax.figure
    width_in = fig.get_size_inches()[0] * ax.get_position().width
    if sheet is not None:
        window = (0.0, 0.0, sheet.width_in, sheet.height_in)
    else:
        window = bounds
    ax.set_xlim(window[0], window[2])
    ax.set_ylim(window[1], window[3])
    ax.set_aspect("equal")
    ax.axis("off")
    ppd = 72.0 * width_in / (window[2] - window[0])
    if sheet is not None:
        mpl_render.draw_sheet(ax, doc, sheet, show_viewport_frames=False, ppd=ppd)
    else:
        mpl_render.draw_model(ax, doc, ppd=ppd)


def frame(ax, color, lw=2.5):
    ax.add_patch(Rectangle((0, 0), 1, 1, transform=ax.transAxes, fill=False,
                           edgecolor=color, linewidth=lw, clip_on=False))


def panel_sheet(doc, sheets):
    """The first named sheet, by name (doc.sheets is keyed by id)."""
    if not sheets:
        return None
    return next(s for s in doc.sheets.values() if s.name == sheets[0])


def overview_pdf(rows, label, out):
    """Three probes per landscape letter page: text, the model's result, the reference."""
    per_page = 3
    with PdfPages(out / "OVERVIEW.pdf") as pdf:
        for start in range(0, len(rows), per_page):
            page = rows[start:start + per_page]
            fig = plt.figure(figsize=(11, 8.5), facecolor="white")
            fig.text(0.04, 0.965, f"RoadDraft probes -- {label}: what the model left behind, "
                     f"beside a correct answer", fontsize=11, color=INK, weight="bold")
            fig.text(0.04, 0.945, "Verdicts are Probe.check on the document on disk. Left: the "
                     "model's document. Right: the probe's scripted solution, same sheet or "
                     "same model window.", fontsize=7.5, color=FAINT)
            fig.text(0.405, 0.925, "MODEL'S RESULT", fontsize=8, color=FAINT, ha="center")
            fig.text(0.795, 0.925, "REFERENCE", fontsize=8, color=FAINT, ha="center")
            row_h = 0.285
            for i, row in enumerate(page):
                top = 0.905 - i * row_h
                verdict, sub, ref, sheets, bounds, probe, calls, faults = row
                color = GREEN if verdict.passed else RED
                fig.text(0.04, top - 0.01, probe.id, fontsize=10, color=INK, weight="bold",
                         va="top")
                fig.text(0.04, top - 0.045, "PASS" if verdict.passed else "FAIL", fontsize=13,
                         color=color, weight="bold", va="top")
                where = (f"sheet {sheets[0]}" + (f" (of {len(sheets)})" if len(sheets) > 1 else "")
                         if sheets else "model space")
                fig.text(0.04, top - 0.085, f"{where} - {calls} calls, {faults} faults",
                         fontsize=7, color=FAINT, va="top")
                fig.text(0.04, top - 0.11, textwrap.fill(verdict.detail, 34), fontsize=6.4,
                         color=INK, va="top", linespacing=1.25)
                for x0, doc in ((0.22, sub.doc), (0.61, ref.doc)):
                    ax = fig.add_axes([x0, top - row_h + 0.035, 0.37, row_h - 0.055])
                    draw_panel(ax, doc, panel_sheet(doc, sheets), bounds)
                    frame(ax, color if x0 < 0.5 else FAINT, lw=2.5 if x0 < 0.5 else 0.8)
            fig.text(0.96, 0.02, f"page {start // per_page + 1} of "
                     f"{(len(rows) + per_page - 1) // per_page}", fontsize=7, color=FAINT,
                     ha="right")
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)


def overview_png(rows, label, out, cols=4):
    """The grid: every probe's result, framed by its verdict."""
    n = len(rows)
    nrows = (n + cols - 1) // cols
    fig = plt.figure(figsize=(4.2 * cols, 3.2 * nrows + 0.9), facecolor="white")
    passed = sum(r[0].passed for r in rows)
    fig.text(0.5, 1 - 0.35 / fig.get_size_inches()[1],
             f"{label}: {passed} of {n} probes pass -- the model's result for each, green = pass, red = fail",
             fontsize=13, ha="center", va="center", color=INK, weight="bold")
    cell_w, cell_h = 1.0 / cols, 1.0 / (nrows + 0.9 / 3.2)
    for k, row in enumerate(rows):
        verdict, sub, ref, sheets, bounds, probe, calls, faults = row
        r, c = divmod(k, cols)
        left = c * cell_w + 0.012
        bottom = 1 - (r + 1) * cell_h * (1 - 0.9 / (3.2 * nrows + 0.9)) - 0.9 / (3.2 * nrows + 0.9)
        ax = fig.add_axes([left, bottom + 0.012, cell_w - 0.024, cell_h * 0.72])
        draw_panel(ax, sub.doc, panel_sheet(sub.doc, sheets), bounds)
        color = GREEN if verdict.passed else RED
        frame(ax, color, lw=3)
        fig.text(left, bottom + 0.012 + cell_h * 0.72 + 0.01,
                 f"{probe.id}", fontsize=9.5, weight="bold", color=INK, va="bottom")
        fig.text(left + cell_w - 0.024, bottom + 0.012 + cell_h * 0.72 + 0.01,
                 "PASS" if verdict.passed else "FAIL", fontsize=9.5, weight="bold",
                 color=color, va="bottom", ha="right")
    fig.savefig(out / "OVERVIEW.png", dpi=130, facecolor="white")
    plt.close(fig)


def main(label):
    out = ROOT / "runs" / label / "deliverables"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for probe in tasks.PROBES:
        folder = ROOT / "runs" / label / probe.id
        if not (folder / "trace.jsonl").exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            verdict, submitted, reference = load_pair(label, probe, work)
            sheets = sheets_named(probe)
            bounds = print_pair(probe, submitted, reference, sheets, out)
            save_reference(probe, reference, out)
            calls, faults = trace_counts(label, probe)
            rows.append((verdict, submitted, reference, sheets, bounds, probe, calls, faults))
            print(f"{'PASS' if verdict.passed else 'FAIL'}  {probe.id:24s} -> {probe.id}.pdf, "
                  f"{probe.id}.reference.pdf, {probe.id}.reference/  "
                  f"({'sheets ' + ','.join(sheets) if sheets else 'model'})")
    overview_pdf(rows, label, out)
    overview_png(rows, label, out)
    print(f"\n{sum(r[0].passed for r in rows)}/{len(rows)} pass; OVERVIEW.pdf and OVERVIEW.png in {out}")


if __name__ == "__main__":
    main(sys.argv[1])
