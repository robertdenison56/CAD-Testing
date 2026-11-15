"""The grounded drafter for the reasoning families (training plan §8 build 5).

``trajectories.grounded`` drafts the seeded D1 tasks.  The generated deeds
(``tasks.deeds``, the ``p03`` survey traps) and planted-error sheets
(``tasks.planted``, the ``p14`` QA reviews) are probe tasks instead: they run on
the harness the pilots run on (``eval.probe_tasks.ProbeEpisode``: the MCP
server's tools, graded by the task's own pass/fail check).  This module drafts
them the same grounded way -- a line of shown work, then the calls, every value
read from the task text, from a result, or worked out in the shown work -- and
audits each recording with ``grounded.audit``, with the forms these families
add:

- a number written with thousands separators (``N 20,005.68``) is that number;
- an area lettered to the square foot (``29,393 SQ FT``) is grounded when a
  result gave the area;
- a QA note (``QA: ...``) is grounded when what follows the colon is a fixed
  phrase of the review, optionally followed by a value seen.

A recording is kept when the episode submitted, its check passed and the audit
finds nothing ungrounded.  ``python -m roaddraft.trajectories.reasoning
--taskset train-deeds --out DIR --level vague`` records a set.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence

from roaddraft.eval.agents import Agent, ToolCall
from roaddraft.trajectories.grounded import Seen, Turn, _q, audit as grounded_audit, numbers_in

# ------------------------------------------------------------ the audit's forms

_GROUPED = re.compile(r"(?<![\d,])(\d{1,3}(?:,\d{3})+)(\.\d+)?")


def ungrouped(text: str) -> str:
    """``text`` with every number written with thousands separators written without."""
    return _GROUPED.sub(lambda m: m.group(1).replace(",", "") + (m.group(2) or ""), text)


_AREA = re.compile(r"^(?:.*\n)?(\d{1,3}(?:,\d{3})*|\d+) SQ FT$")


def area_label(value: str, seen: Seen) -> bool:
    """An area lettered to the square foot, from an area a result gave."""
    m = _AREA.match(value)
    if not m:
        return False
    n = float(m.group(1).replace(",", ""))
    head = value[:m.start(1)].strip()
    return (any(abs(abs(x) - n) <= 0.5 for x in seen.numbers)
            and (not head or head in REVIEW_WORDS or head in seen.text))


#: the words a QA note is made of: the review's own phrases (``tasks.planted`` marks
#: each error with one of them), and the clean sheet's text
REVIEW_WORDS = ("PARCEL", "NO ERRORS FOUND")


def review_note(value: str, seen: Seen) -> bool:
    """``QA: <phrase>[ <value seen>]``: a phrase of the review's, and a value
    that was read (a bearing, a station, a table cell)."""
    if not value.startswith("QA: "):
        return False
    rest = value[4:]
    from roaddraft.tasks.planted import NOTE_PHRASES
    for phrase in NOTE_PHRASES:
        if rest == phrase:
            return True
        if rest.startswith(phrase + " "):
            tail = rest[len(phrase) + 1:]
            return seen.string(tail, "") or all(seen.number(n, standards=False)
                                                for n in numbers_in(tail)) and bool(numbers_in(tail))
    return False


RULES = (area_label, review_note)
#: what these drafters choose for themselves where no standard speaks: how far a QA
#: callout's note sits off the item (``reasoning_qa.OFFSET_IN``)
CHOICES = (0.75,)


def audit(text: str, tools: Sequence[dict], turns: Sequence[dict]) -> List[dict]:
    """``grounded.audit`` with this module's forms."""
    return grounded_audit(text + "\n" + ungrouped(text), tools, turns, rules=RULES,
                          numbers=CHOICES)


# ------------------------------------------------------------ helpers

def _ok(results: Sequence[dict], calls: Sequence[ToolCall]) -> None:
    for call, result in zip(calls, results):
        if not result.get("ok"):
            raise RuntimeError(f"{call.name} failed: {(result.get('error') or {}).get('message')}")


def _r4(value: float) -> float:
    return round(float(value) + 0.0, 4)


def _n(value: float) -> str:
    """A number as the shown work writes it: four decimals at most, no trailing zeros."""
    text = f"{_r4(value):.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


def _plus(a: float, b: float, c: float, d: float) -> tuple:
    """``a +/- |b| * c / d`` as the shown work writes it, and its value at four decimals."""
    b4, c4, d4, a4 = _r4(b), _r4(c), _r4(d), _r4(a)
    value = _r4(a4 + b4 * c4 / d4)
    sign = "+" if b4 >= 0 else "-"
    return f"{_n(a4)} {sign} {_n(abs(b4))} * {_n(c4)} / {_n(d4)} = {_n(value)}", value


# ------------------------------------------------------------ the deed

_POB = re.compile(r"at N ([\d,]+\.\d+), E ([\d,]+\.\d+)")
_COURSE = re.compile(r"([NS] \d+°\d+'\d+\" [EW]) (\d+\.\d+) feet"
                     r"|tangent curve to the (left|right), having a radius of (\d+\.\d+) feet, "
                     r"through a central angle of (\d+°\d+'\d+\")")


def read_deed(text: str) -> dict:
    """The point of beginning and the courses of the deed the task quotes."""
    deed = text[text.index("The deed reads:"):] if "The deed reads:" in text else text
    m = _POB.search(deed)
    if not m:
        raise ValueError("no point of beginning in the deed")
    pob = [float(m.group(2).replace(",", "")), float(m.group(1).replace(",", ""))]
    legs = []
    for c in _COURSE.finditer(deed):
        if c.group(1):
            legs.append({"bearing": c.group(1), "distance": float(c.group(2))})
        else:
            legs.append({"radius": float(c.group(4)), "turn": c.group(3), "delta": c.group(5)})
    if len(legs) < 3:
        raise ValueError("fewer than three courses in the deed")
    return {"pob": pob, "legs": legs,
            "pob_words": f"N {m.group(1)}, E {m.group(2)}"}


def solve_deed(text: str) -> Generator[Turn, List[dict], Turn]:
    """Plot the deed as written, read its misclosure, balance it by the compass
    rule holding the POB, draw the balanced parcel closed on the property-line
    layer, letter its area inside it and record the three answers."""
    deed = read_deed(text)
    pob, legs = deed["pob"], deed["legs"]
    calls = [_q("traverse", start=pob, close=True, legs=legs), _q("list_layers"),
             _q("list_annotation_scales")]
    results = yield Turn(
        f"The deed begins at {deed['pob_words']}, which the engine takes as [easting, northing] "
        f"= [{_n(pob[0])}, {_n(pob[1])}], and runs {len(legs)} courses. Plot it as written with "
        "traverse, closed, to see how far it misses its start; and see the layers and the scale "
        "the file is drawn at.", calls)
    _ok(results, calls)
    tr, layers, scales = results
    closure = tr["closure"]
    raw, courses = tr["points"], tr["courses"]
    dx, dy, per = float(closure["dx"]), float(closure["dy"]), float(closure["perimeter"])
    layer = next((row["name"] for row in layers["layers"]
                  if "property" in str(row.get("description") or "").lower()), None)
    if layer is None:
        raise RuntimeError("the file has no property-line layer")
    height = float(scales["model_sizes"]["text_height"])
    lengths = [float(c.get("distance", c.get("length"))) for c in courses]
    lines = [f"As written the deed misses its start by {_n(closure['distance'])} ft over a "
             f"perimeter of {_n(per)} ft, precision {closure['precision_text']}: from where the "
             f"last course ends, the point of beginning is dx = {_n(dx)} ft in E and "
             f"dy = {_n(dy)} ft in N. The "
             "compass rule holds the POB and moves each corner by the misclosure times its share "
             "of the perimeter run to it: E + dx * run / perimeter, N + dy * run / perimeter."]
    corners = [list(pob)]
    run = 0.0
    for i in range(len(courses) - 1):
        before, run = run, _r4(run + lengths[i])
        if i == 0:
            lines.append(f"Run to corner 2: {_n(lengths[0])}.")
        else:
            lines.append(f"Run to corner {i + 2}: {_n(before)} + {_n(lengths[i])} = {_n(run)}.")
        ex, e = _plus(raw[i + 1][0], dx, run, per)
        ny, n = _plus(raw[i + 1][1], dy, run, per)
        lines.append(f"Corner {i + 2}: E {ex}; N {ny}.")
        corners.append([e, n])
    curve = next((i for i, c in enumerate(courses) if c["kind"] == "curve"), None)
    if curve is None:
        calls = [_q("draw_polyline", space="model", layer=layer, vertices=corners, closed=True)]
        lines.append(f"Draw the balanced parcel as one closed boundary on {layer}, the layer the "
                     "file keeps for property lines.")
        results = yield Turn(" ".join(lines), calls)
        _ok(results, calls)
        ids = list(results[0]["created"])
    else:
        a, b = corners[curve], corners[(curve + 1) % len(corners)]
        calls = [_q("measure", **{"from": a, "to": b})]
        lines.append(f"Course {curve + 1} is a curve, and the balance moves its ends: it keeps its "
                     "radius between the balanced corners, so measure the chord between them to "
                     "draw it.")
        results = yield Turn(" ".join(lines), calls)
        _ok(results, calls)
        chord = results[0]
        leg = legs[curve]
        path = corners[curve + 1:] + corners[:curve + 1]
        calls = [_q("draw_polyline", space="model", layer=layer, vertices=path, closed=False),
                 _q("draw_traverse", space="model", layer=layer, start=a,
                    legs=[{"radius": leg["radius"], "turn": leg["turn"],
                           "chord": chord["distance"], "chord_bearing": chord["bearing"]}])]
        results = yield Turn(
            f"Draw the straight courses from corner {curve + 2} round to corner {curve + 1} as "
            f"one polyline on {layer}, the layer the file keeps for property lines, and the curve "
            f"from corner {curve + 1}: radius {_n(leg['radius'])} to the {leg['turn']}, on the "
            f"chord just measured ({_n(chord['distance'])} ft, {chord['bearing']}).", calls)
        _ok(results, calls)
        ids = [i for r in results for i in r["created"]]
    calls = [_q("area", ids=ids)]
    results = yield Turn("Check that the boundary closes and read its area and centroid.", calls)
    _ok(results, calls)
    area = results[0]
    sqft = float(area["area"])
    label = f"{round(sqft):,} SQ FT"
    calls = [_q("place_text", space="model", layer=layer, position=area["centroid"],
                content=label, height=height, halign="center", valign="middle"),
             _q("set_meta", updates={"misclosure_ft": round(float(closure["distance"]), 3),
                                     "precision": closure["precision_text"],
                                     "area_sqft": round(sqft, 3)})]
    results = yield Turn(
        f"Letter the area inside the parcel at its centroid, at the drawing's model text height "
        f"({_n(height)} ft at its annotation scale), and record the answers.", calls)
    _ok(results, calls)
    note = (f"Plotted the deed as written: it misses its start by "
            f"{_n(round(float(closure['distance']), 3))} ft. Balanced by the compass rule holding "
            f"the point of beginning and drawn closed on {layer}; area {_n(round(sqft, 3))} sq ft, "
            "lettered inside it. misclosure_ft, precision and area_sqft are recorded with "
            "set_meta.")
    return Turn("Done.", [_q("submit", note=note)])


# ------------------------------------------------------------ the agent

SOLVERS = {"train-survey-traps": solve_deed}


def _solver(task_type: str):
    if task_type == "train-qa-review":
        from roaddraft.trajectories.reasoning_qa import solve_review
        return solve_review
    return SOLVERS[task_type]


class ReasoningAgent(Agent):
    """The grounded drafter for a generated probe task: it takes the task text
    from the first observation and nothing else of the task."""
    name = "grounded"

    def __init__(self):
        self._gen = None
        self._type = ""
        self._say = ""

    def reset(self, task, level: str, mode: str) -> None:
        self._gen, self._type, self._say = None, task.task_type, ""

    def act(self, observation: dict):
        try:
            if self._gen is None:
                self._gen = _solver(self._type)(observation["brief"])
                turn = next(self._gen)
            else:
                turn = self._gen.send(observation["results"])
        except StopIteration as finished:
            turn = finished.value
        self._say = turn.say
        return list(turn.calls)

    def turn_record(self) -> dict:
        return {"text": self._say}

    def describe(self) -> dict:
        return {"model": "grounded-reference", "provider": "harness"}


# ------------------------------------------------------------ recording

def record_task(task, level: str = "vague", out_root=None, run_id: str = "") -> dict:
    """Run one generated probe task under the grounded drafter and audit it.
    The episode runs on the pilots' budgets (``probe_tasks.BUDGETS``), not D1's:
    the header and the system prompt then state what a pilot run is told."""
    from roaddraft.eval.episode import EpisodeConfig
    from roaddraft.eval.probe_tasks import BUDGETS, ProbeEpisode
    episode = ProbeEpisode(task, ReasoningAgent(),
                           EpisodeConfig(level=level, run_id=run_id, budgets=BUDGETS),
                           out_root=out_root)
    result = episode.run()
    ungrounded = audit(episode.brief_text, episode.tools, episode.turns)
    report = result.report
    return {"task_id": task.task_id, "task_type": task.task_type, "level": level,
            "termination": result.termination, "error": result.error,
            "effective": result.effective_score, "turns": result.turns, "steps": result.steps,
            "passed": bool(getattr(report, "passed", False)),
            "detail": getattr(report, "detail", ""), "ungrounded": ungrounded,
            "path": result.path,
            "kept": (result.termination == "submit" and result.effective_score == 100.0
                     and not ungrounded)}


def record(taskset: str, out, level: str = "vague", limit: Optional[int] = None) -> dict:
    """Record every task of a generated probe set under ``out``: the episode
    files and ``index.json``."""
    from roaddraft.eval import taskset as tasksets
    out = Path(out)
    rows: List[dict] = []
    for entry in tasksets.entries(taskset)[:limit]:
        task = tasksets.task_from_entry(entry, level=level)
        try:
            row = record_task(task, level, out_root=out, run_id=out.name)
        except Exception as exc:  # a drafter that stops is a recording not kept
            row = {"task_id": task.task_id, "task_type": task.task_type, "level": level,
                   "termination": "error", "error": f"{type(exc).__name__}: {exc}",
                   "effective": 0.0, "ungrounded": [], "kept": False}
        row.update({k: entry[k] for k in ("seed", "kind") if k in entry})
        rows.append(row)
    by_kind: Dict[str, Counter] = {}
    for row in rows:
        tally = by_kind.setdefault(str(row.get("kind") or row["task_type"]), Counter())
        tally["tasks"] += 1
        tally["kept"] += bool(row["kept"])
    index = {"taskset": taskset, "level": level, "tasks": len(rows),
             "kept": sum(bool(r["kept"]) for r in rows),
             "by_kind": {k: dict(c) for k, c in sorted(by_kind.items())}, "rows": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories.reasoning",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--taskset", default="train-deeds")
    parser.add_argument("--out", required=True)
    parser.add_argument("--level", default="vague", choices=("vague", "explicit"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    index = record(args.taskset, args.out, args.level, args.limit)
    print(f"{args.taskset} at the {args.level} level: {index['tasks']} tasks, "
          f"{index['kept']} kept (passed, nothing ungrounded)")
    for kind, tally in index["by_kind"].items():
        print(f"  {kind:24s} {tally.get('kept', 0):4d} kept of {tally['tasks']:4d}")
    bad = [r for r in index["rows"] if not r["kept"]]
    for row in bad[:10]:
        print(f"  NOT KEPT {row['task_id']}: {row['termination']} {row['effective']} "
              f"{row.get('error') or ''} {str(row.get('detail') or '')[:120]} "
              f"{row['ungrounded'][:3]}")
    return 1 if bad else 0


__all__ = ["audit", "ungrouped", "area_label", "review_note", "RULES", "read_deed", "solve_deed",
           "ReasoningAgent", "record_task", "record"]

if __name__ == "__main__":
    sys.exit(main())
