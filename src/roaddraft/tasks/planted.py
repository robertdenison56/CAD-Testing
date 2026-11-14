"""Generated sheets with planted errors to find (2026-11-13, training plan §8 build 5).

The QA-review pilots (``p14``, nine instances on agency sheets, three of them clean
controls) hand a model a finished sheet back from drafting and ask it to mark every
error with a callout on layer QA-REVIEW, fix nothing, and letter NO ERRORS FOUND on a
clean sheet.  None of the pilots' sheets may train (plan decision 7).
``qa_task(seed)`` makes the same task on a generated sheet:

- the start: the seed's ``annotate-sheet`` task finished by the reference (stationing,
  BC/EC, bearings, curve numbers, the curve table, the north arrow, the title block:
  ``tasks.revise._finished``), one sheet, half of them seen through a turned viewport.
  The bearings, curve points and curve numbers are left without anchor records, as an
  agency sheet's lettering is; the station numbers and ticks keep theirs, as the
  redrafts' do;
- the plants: one task in three is a clean control; the others get three to five
  errors of different kinds (``KINDS``, the pilots' own: a bearing's quadrant flipped
  or its distance's digits transposed, a BC/EC station 100 ft off or lettered as the
  other point, a curve-table cell's digits transposed, a station number wrong, a
  station tick missing, a label turned upside down, the north arrow turned half
  round), no two within 2 in of each other on the paper (the pilots' rule, so one mark
  cannot claim two);
- the prompts: the pilots' (``probes.pilot.qa_review.PROMPT`` / ``VAGUE``), with the
  design named where this sheet keeps it (in this file, not in base files);
- the check: the pilots' rule, on the pilots' own code (``qa_review.qa_marks``,
  ``_hit``, ``changed_outside``, ``plant_marks``): each plant found by a QA-REVIEW
  leader tip within 0.5 in of where it plots (a missing tick: where it plotted on the
  finished sheet), at most one false alarm, a control passes only with NO ERRORS FOUND
  on QA-REVIEW and no marks, and nothing outside QA-REVIEW changed.

A probe task of the pilots' harness (``eval.probe_tasks``), registered outside
``probes/pilot`` with ``probes.fixture.register_start`` under ``train-qa-<seed>``.
Every random draw comes from the stream ``qa:<seed>``; the finished sheet is the seed's
own, so its id is the task's too.
"""
from __future__ import annotations

import hashlib
import math
import random
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.probes import fixture
from roaddraft.probes.base import Probe, Result, Tally

#: the training set's seeds (the other sets hold 10000-18299, the deeds 19000-19299)
SEEDS = range(20000, 20300)
FILE = "plan.rdraft"
TASK_TYPE = "train-qa-review"
FAMILY = "p14"
ID_PREFIX = "TR-"
#: a clean control one task in three; the others carry this many plants
CONTROL_SHARE = 1.0 / 3.0
PLANTS = (3, 5)
#: no two plants nearer than this on the paper (the pilots' rule)
APART_IN = 2.0
KINDS = ("bearing_quadrant", "bearing_distance", "curve_station", "curve_kind", "table_cell",
         "station_number", "tick_missing", "upside_down", "north_arrow")
#: what the drafter writes after ``QA: ``, by what it found; a value read may follow
NOTE_PHRASES = ("BEARING SHOULD READ", "STATION SHOULD READ", "CURVE DATA SHOULD READ",
                "STATION NUMBER DOES NOT MATCH STATION", "STATION TICK MISSING AT",
                "LABEL READS UPSIDE DOWN", "NORTH ARROW DOES NOT POINT NORTH")

_BEARING = re.compile(r"^([NS]) (\d+°\d+'\d+\") ([EW]) (\d+\.\d+)'$")
_CURVE_POINT = re.compile(r"^(\d+\+\d{2}\.\d{2}) (BC|EC)$")


def _ok(result: dict) -> dict:
    if not result.get("ok"):
        raise RuntimeError(f"{result.get('name')}: {result['error']['message']}")
    return result


def _transpose(text: str, start: int = 0) -> Optional[str]:
    """Swap two neighbouring different digits of ``text`` at or after digit ``start``."""
    digits = [i for i, ch in enumerate(text) if ch.isdigit()]
    for k in range(start, len(digits) - 1):
        i, j = digits[k], digits[k + 1]
        leading = i == 0 or not text[i - 1].isdigit()
        if text[i] != text[j] and j == i + 1 and not (leading and text[j] == "0"):
            chars = list(text)
            chars[i], chars[j] = chars[j], chars[i]
            return "".join(chars)
    return None


@dataclass
class QATask:
    seed: int
    probe: Probe
    base_task_id: str
    sheet: str
    twist: float
    plants: List[dict] = field(default_factory=list)

    @property
    def control(self) -> bool:
        return not self.plants

    def task_id(self, level: str) -> str:
        from roaddraft.eval.probe_tasks import brief_text
        h = hashlib.sha256((brief_text(self.probe, level) + "\0" + self.base_task_id + "\0"
                            + repr(sorted((p["kind"], p["item"]) for p in self.plants)))
                           .encode("utf-8")).hexdigest()[:10]
        return f"{ID_PREFIX}{self.probe.id}-{h}"


# ------------------------------------------------------------------ the finished sheet


def _finished_sheet(seed: int, rng: random.Random):
    from roaddraft.tasks.generator import generate_task
    from roaddraft.tasks.revise import _finished
    twist = rng.random() < 0.5
    task = generate_task(seed, curves=rng.choice((1, 2, 3)), equations=False,
                         task_type="annotate-sheet", sheets=1, twist=twist)
    session = _finished(task)
    for e in session.doc.model_entities.values():
        if (e.anchor or {}).get("kind") in ("bearing", "pc", "pt", "mc", "pcc", "prc"):
            e.anchor = None
    for key in ("task_id", "spec_version"):
        (session.doc.meta or {}).pop(key, None)
    return task, session


def _rows(session, sheet: str, **filters) -> List[dict]:
    out, start = [], 0
    while True:
        r = _ok(session.query("find_entities", {"visible_on": sheet, "limit": 100,
                                                "start": start, **filters}))
        out += r["entities"]
        more = r.get("more") or {}
        if not more.get("remaining"):
            return [row for row in out if float(row.get("shown", 1.0)) >= 1.0]
        start = more["start"]


# ------------------------------------------------------------------ the plants


def _candidates(session, sheet_name: str) -> Dict[str, List[dict]]:
    """Each kind's possible plants on the finished sheet: ``{kind: [plant]}``, a plant
    being ``{kind, item, what, at (paper point), apply (how to make it), marks keys}``."""
    doc = session.doc
    sheet = doc.sheet_by_ref(sheet_name)
    texts = _rows(session, sheet_name, type="text")
    ticks = [r for r in _rows(session, sheet_name, type="line")
             if (r.get("anchor") or {}).get("kind") == "tick"]
    out: Dict[str, List[dict]] = {k: [] for k in KINDS}
    from roaddraft.verify.legibility import reads_upside_down
    for row in texts:
        content = row.get("content") or ""
        at = row["sheet_point"]
        kind = (row.get("anchor") or {}).get("kind")
        b = _BEARING.match(content)
        if b:
            flipped = content.replace(f" {b.group(3)} ", " W " if b.group(3) == "E" else " E ", 1)
            out["bearing_quadrant"].append(
                {"kind": "bearing_quadrant", "id": row["id"], "content": flipped, "at": at,
                 "item": f"the bearing {content} (quadrant flipped)",
                 "what": f"{content!r} lettered {flipped!r}"})
            dist = b.group(4)
            swapped = _transpose(dist)
            if swapped:
                new = content[:-len(dist) - 1] + swapped + "'"
                out["bearing_distance"].append(
                    {"kind": "bearing_distance", "id": row["id"], "content": new, "at": at,
                     "item": f"the distance of {content} (digits transposed)",
                     "what": f"{content!r} lettered {new!r}"})
        c = _CURVE_POINT.match(content)
        if c:
            station, word = c.groups()
            n = int(station.split("+")[0])
            later = f"{n + 1}+{station.split('+')[1]} {word}"
            out["curve_station"].append(
                {"kind": "curve_station", "id": row["id"], "content": later, "at": at,
                 "item": f"the {word} station {station} (100 ft off)",
                 "what": f"{content!r} lettered {later!r}"})
            other = f"{station} {'EC' if word == 'BC' else 'BC'}"
            out["curve_kind"].append(
                {"kind": "curve_kind", "id": row["id"], "content": other, "at": at,
                 "item": f"the {word} at {station} lettered as the other point",
                 "what": f"{content!r} lettered {other!r}"})
        if kind == "station":
            if len(content) > 1:
                wrong = _transpose(content)
            else:
                wrong = str((int(content) + 3) % 10) if content.isdigit() else None
            if wrong and wrong != content:
                out["station_number"].append(
                    {"kind": "station_number", "id": row["id"], "content": wrong, "at": at,
                     "item": f"the station number at {row['anchor']['ref']}",
                     "what": f"{content!r} lettered {wrong!r}"})
        corners = row.get("paper_corners")
        if corners:
            rot = math.degrees(math.atan2(corners[1][1] - corners[0][1],
                                          corners[1][0] - corners[0][0]))
            if not reads_upside_down(rot) and reads_upside_down(rot + 180.0):
                out["upside_down"].append(
                    {"kind": "upside_down", "id": row["id"], "at": at,
                     "item": f"the label {content!r} upside down",
                     "what": f"{content!r} turned half round"})
    numbered = {round(float(r["anchor"]["station"]), 3) for r in texts
                if (r.get("anchor") or {}).get("kind") == "station"}
    for row in ticks:
        st = round(float(row["anchor"]["station"]), 3)
        if st in numbered and row.get("sheet_point"):
            out["tick_missing"].append(
                {"kind": "tick_missing", "id": row["id"], "at": row["sheet_point"],
                 "item": f"the tick at {row['anchor']['ref']}",
                 "what": f"the station tick at {row['anchor']['ref']} taken off"})
    from roaddraft.probes import plotted as pl
    for e in sheet.entities.values():
        if type(e).__name__ == "Table":
            for i, cells in enumerate(e.rows):
                for j in (1, 3, 4):  # R, T, L: lettered numbers whose digits can swap
                    wrong = _transpose(cells[j])
                    if not wrong:
                        continue
                    cell = next(p for p in e.primitives(doc) if p.id == f"{e.id}:c{i}_{j}")
                    at = pl.plot(session, sheet, [(sheet.id, cell)]).texts[0].center()
                    out["table_cell"].append(
                        {"kind": "table_cell", "id": e.id, "row": i, "col": j, "content": wrong,
                         "at": at, "item": f"curve {cells[0]}'s {e.columns[j]['header']} in the "
                                           "curve table",
                         "what": f"{cells[j]!r} lettered {wrong!r}"})
        if type(e).__name__ == "BlockRef" and e.block_name == "NORTH_ARROW":
            out["north_arrow"].append(
                {"kind": "north_arrow", "id": e.id, "at": list(e.position),
                 "item": "the north arrow (turned half round)",
                 "what": "the north arrow turned 180 degrees"})
    return out


def _apply(session, sheet_name: str, plant: dict) -> dict:
    """Plant it; the plant as the check reads it (``qa_review.plant_marks``' keys)."""
    doc = session.doc
    sheet = doc.sheet_by_ref(sheet_name)
    kind, eid = plant["kind"], plant["id"]
    keys = {"kind": kind, "item": plant["item"], "what": plant["what"]}
    if kind in ("bearing_quadrant", "bearing_distance", "curve_station", "curve_kind",
                "station_number"):
        _ok(session.execute("modify_entity", {"id": eid, "changes": {"content": plant["content"]}}))
        return {**keys, "model": [eid]}
    if kind == "upside_down":
        from roaddraft.probes import plotted as pl
        e = doc.model_entities[eid]
        box = pl.PText(e.content, list(e.position), float(e.rotation_deg), float(e.height),
                       e.halign, e.valign)
        _ok(session.execute("rotate_entities", {"ids": [eid], "base": box.center(),
                                                "angle": 180.0}))
        return {**keys, "model": [eid]}
    if kind == "tick_missing":
        _ok(session.execute("delete_entities", {"ids": [eid]}))
        return {**keys, "gone": [eid]}
    if kind == "table_cell":
        table = sheet.entities[eid]
        rows = [list(r) for r in table.rows]
        rows[plant["row"]][plant["col"]] = plant["content"]
        _ok(session.execute("modify_entity", {"id": eid, "changes": {"rows": rows}}))
        return {**keys, "cell": (eid, plant["row"], plant["col"])}
    if kind == "north_arrow":
        e = sheet.entities[eid]
        _ok(session.execute("modify_entity", {"id": eid, "changes": {
            "rotation_deg": (float(e.rotation_deg) + 180.0 + 180.0) % 360.0 - 180.0}}))
        return {**keys, "sheet": [eid]}
    raise ValueError(f"unknown plant kind {kind!r}")


def _choose(rng: random.Random, candidates: Dict[str, List[dict]]) -> List[dict]:
    kinds = [k for k in KINDS if candidates[k]]
    want = rng.randint(*PLANTS)
    rng.shuffle(kinds)
    chosen: List[dict] = []
    for kind in kinds:
        options = list(candidates[kind])
        rng.shuffle(options)
        for p in options:
            if all(math.dist(p["at"], q["at"]) >= APART_IN for q in chosen) and \
                    all(p["id"] != q["id"] for q in chosen):
                chosen.append(p)
                break
        if len(chosen) == want:
            break
    return chosen


# ------------------------------------------------------------------ the check


def _check(seed: int):
    def check(baseline, submitted) -> Result:
        from roaddraft.probes.pilot import qa_review as qa
        task = qa_task(seed)
        marks, texts = qa.qa_marks(baseline, submitted)
        clean_said = [t for t in texts if qa.CLEAN_TEXT in " ".join(t.content.upper().split())]
        tally = Tally()
        if task.control:
            tally.add("NO ERRORS FOUND on QA-REVIEW",
                      None if clean_said else "the clean sheet was not called clean: no "
                                              "NO ERRORS FOUND text on QA-REVIEW")
            tally.add("no error marked on the clean sheet",
                      None if not marks else f"{len(marks)} QA mark(s) on a sheet with no errors"
                      + qa._said(marks))
        else:
            if clean_said:
                tally.fail("NO ERRORS FOUND lettered on a sheet with errors")
            shapes = [plant_marks(seed, baseline, p) for p in task.plants]
            assigned: Dict[int, List[int]] = {}
            stray = []
            for k, mark in enumerate(marks):
                best = min((qa._hit(mark, sh), i) for i, sh in enumerate(shapes))
                if best[0] <= qa.REACH_IN:
                    assigned.setdefault(best[1], []).append(k)
                else:
                    stray.append(mark)
            for i, plant in enumerate(task.plants):
                if i in assigned:
                    tally.add(plant["item"], None)
                else:
                    near = min((qa._hit(m, shapes[i]) for m in marks), default=None)
                    tally.add(plant["item"], f"not marked: {plant['what']}"
                              + (f" (nearest QA mark {near:.2f} in away)" if near is not None else ""))
            if len(stray) > qa.FALSE_ALARMS:
                tally.fail(f"{len(stray)} QA marks point at no planted error (allowed "
                           f"{qa.FALSE_ALARMS})" + qa._said(stray))
        tally.fail(qa.changed_outside(Path(baseline.doc._path), submitted,
                                      allow_layer=qa.QA_LAYER, model=True))
        good = ("called clean: NO ERRORS FOUND on QA-REVIEW and no marks" if task.control else
                f"all {len(task.plants)} errors marked on QA-REVIEW, at most {qa.FALSE_ALARMS} "
                "false alarm, nothing else changed")
        return tally.result(good)
    return check


def plant_marks(seed: int, truth, plant: dict):
    """Where a plant shows on the sheet (paper inches): the pilots' ``plant_marks``, and
    for a missing tick, where it plotted on the finished sheet."""
    from roaddraft.probes.pilot import qa_review as qa
    if plant.get("gone"):
        from roaddraft.api.session import Session
        from roaddraft.document.document import Document
        from roaddraft.probes import plotted as pl
        clean = Session(_document=Document.from_dict(_CLEAN[seed]))
        sheet = qa._sheet(clean)
        view = pl.plot(clean, sheet, [("model", clean.doc.model_entities[i]) for i in plant["gone"]])
        return view.texts, view.segs
    return qa.plant_marks(truth, plant)


# ------------------------------------------------------------------ the prompts


def _briefs(sheet: str) -> Tuple[str, str]:
    from roaddraft.probes.pilot import qa_review as qa
    explicit = qa.PROMPT.format(sheet=sheet, scope="").replace(
        "the alignments in the base files the sheet references", "the alignment in this file")
    vague = qa.VAGUE.format(sheet=sheet, scope="")
    for text in (explicit, vague):
        assert "base files the sheet" not in text
    explicit = explicit.replace("on the sheet or in the base files", "on the sheet or in the design")
    vague = vague.replace("on the sheet or in the base files", "on the sheet or in the design")
    return explicit, vague


# ------------------------------------------------------------------ the task

_CLEAN: Dict[int, dict] = {}
_STARTS: Dict[int, dict] = {}


@lru_cache(maxsize=None)
def qa_task(seed: int) -> QATask:
    """The generated QA review of ``seed``; ``ValueError`` when it cannot be planted."""
    rng = random.Random(f"qa:{seed}")
    task, session = _finished_sheet(seed, rng)
    sheet_name = task.brief.deliverable["sheets"][0]["name"]
    _CLEAN[seed] = session.doc.to_dict()
    plants: List[dict] = []
    if rng.random() >= CONTROL_SHARE:
        chosen = _choose(rng, _candidates(session, sheet_name))
        if len(chosen) < PLANTS[0]:
            raise ValueError(f"seed {seed}: only {len(chosen)} plants fit 2 in apart")
        plants = [_apply(session, sheet_name, p) for p in chosen]
    explicit, vague = _briefs(sheet_name)
    probe_id = f"t14-qa-{seed}"
    start = _register(seed, session)
    twist = float(task.brief.deliverable.get("view_rotation") or 0.0)
    probe = Probe(id=probe_id, prompt=explicit, vague=vague, check=_check(seed), start=start,
                  tags=["qa", "train"] + (["twist"] if twist else []), family=FAMILY,
                  params={"seed": seed, "plants": [p["kind"] for p in plants]},
                  note=("A clean CONTROL" if not plants else
                        f"{len(plants)} planted: " + "; ".join(p["what"] for p in plants)))
    probe.solve = _scripted(seed, plants, sheet_name)
    return QATask(seed, probe, task.task_id, sheet_name, twist, plants)


def _scripted(seed: int, plants: Sequence[dict], sheet_name: str):
    """The scripted answer, as the pilots' (``qa_review._solve``): a callout on each plant
    as it plots, or NO ERRORS FOUND."""
    def solve(session) -> None:
        from roaddraft.probes.pilot import qa_review as qa
        if qa.QA_LAYER not in session.doc.layers:
            _ok(session.execute("create_layer", {"name": qa.QA_LAYER, "color": "red"}))
        if not plants:
            _ok(session.execute("place_text", {"space": sheet_name, "layer": qa.QA_LAYER,
                                               "position": [3.0, 2.0], "height": 0.14,
                                               "content": qa.CLEAN_TEXT}))
            return
        sheet = qa._sheet(session)
        for plant in plants:
            texts, segs = plant_marks(seed, session, plant)
            target = texts[0].center() if texts else segs[len(segs) // 2].mid()
            x0, y0, x1, y1 = sheet.viewports[0].paper_bbox()
            side = 1.0 if target[0] < (x0 + x1) / 2.0 else -1.0
            pos = [target[0] + side * 1.2, target[1] + (0.9 if target[1] < (y0 + y1) / 2.0 else -0.9)]
            _ok(session.execute("place_callout", {
                "space": sheet.name, "layer": qa.QA_LAYER, "target": target, "position": pos,
                "height": 0.10, "content": "QA: " + plant["item"].upper()}))
    return solve


def _register(seed: int, session) -> str:
    from roaddraft.document.fileformat import write_document
    name = f"train-qa-{seed}"
    _STARTS[seed] = session.doc.to_dict()
    if name in fixture.EXTRA_STARTS:
        return name

    def build(out: Path) -> Path:
        path = Path(out) / FILE
        write_document(path, _STARTS[seed])
        return path

    fixture.register_start(name, FILE, build)
    return name


# ------------------------------------------------------------------ the set


def entry(seed: int) -> dict:
    """A manifest entry of ``train-qa``."""
    t = qa_task(seed)
    return {"seed": seed, "family": FAMILY, "task_type": TASK_TYPE, "kind": "qa",
            "control": t.control, "plants": [p["kind"] for p in t.plants],
            "twist": bool(t.twist), "base_task_id": t.base_task_id,
            "task_id": t.task_id("explicit"), "vague_task_id": t.task_id("vague")}


def probe_task(row: dict, strict: bool = True, level: str = "explicit"):
    from roaddraft.eval.probe_tasks import ProbeTask, brief_text
    t = qa_task(int(row["seed"]))
    tid = t.task_id(level)
    want = row.get("vague_task_id") if level == "vague" else row["task_id"]
    if strict and tid != want:
        raise ValueError(f"{level} task id of QA seed {row['seed']} is {tid}, the manifest says "
                         f"{want}: the generator or prompt changed; python -m roaddraft.eval "
                         "taskset --write train-qa")
    return ProbeTask(t.probe, tid, TASK_TYPE, brief_text(t.probe, level), level)


__all__ = ["SEEDS", "FILE", "TASK_TYPE", "FAMILY", "KINDS", "NOTE_PHRASES", "QATask", "qa_task",
           "plant_marks", "entry", "probe_task"]
