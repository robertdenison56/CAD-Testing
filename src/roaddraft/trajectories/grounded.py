"""Grounded reference solutions: the reference drafter, working as a model must.

``tasks.reference`` drafts a task from the generator's truth.  Its commands
are right, and they carry values no tool ever returned: a size already
multiplied out for a scale nobody read, a count of tangents nobody asked
for.  Replayed as a conversation (``OracleAgent``) that is two calls and no
question, and a model trained on it learns to write numbers from nowhere.

``GroundedAgent`` drafts the same tasks the way a model has to: it is given
the task text and the work the request calls for (the phases of
``TaskType.solution_phases``, which is what reading the request means), and
everything else it reads through the tool surface before it uses it -- the
sheets, the layers and their descriptions, the scale a sheet shows the model
at, the tangents and curves of the alignment.  It runs through the ordinary
episode loop, so what it leaves is an ordinary episode file, scored by the
verifier like any model's.

Where the engine has a convention it takes the engine's route instead of
doing arithmetic: the annotation scale is set to the sheet's scale and the
labelers size their own lettering, so no command carries a height or an
offset worked out by hand.

``audit`` is the check that makes a recording training data.  It reads a
finished episode the way the model saw it and reports every value in a tool
call that was not *grounded* when the call was made:

- in the task text, or
- in the result of an earlier call, or
- in the called tool's own definition (an enum value, a word of its
  description), or
- a drafting standard of spec v1 (``STANDARDS``: the layer properties, the
  north arrow's place; what the vague prompt leaves to the drafter and what
  training is meant to teach), or
- written another way of one of those: a station as feet (``73+00.00`` is
  7300), a distance to the left as a negative offset, a design point named
  by its index (``T-2``, ``MC-1``).

A recording is kept when the verifier scores it 100 and the audit finds
nothing.  The audit knows nothing of the agent, so it reads a model's
rollout the same way.

    python -m roaddraft.trajectories.grounded --taskset d1-train --out results/grounded/d1-train
                                              [--level vague] [--type TYPE ...] [--limit N]

Phases covered so far are ``COVERED``; a task that needs another is listed
as not covered and not run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, Iterable, List, Optional, Sequence

from roaddraft.eval.agents import Agent, ToolCall
from roaddraft.tasks.brief import Task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import PHASE_ORDER, task_type

#: the phases the grounded drafter can do; a task needing any other is not covered yet
COVERED = ("design", "layers", "linework", "edges", "stationing", "bearings", "callouts",
           "reference")
#: the phases that letter the model, sized for the sheet that shows it
MODEL_LETTERING = ("stationing", "bearings", "callouts")

SPEC = DRAFTING_SPEC_V1
ROLE_LAYER: Dict[str, str] = SPEC["layers"]
#: the office's standard layers, in the spec's order
LAYER_SET: List[str] = list(SPEC.get("layer_set") or dict.fromkeys(ROLE_LAYER.values()))


class NotCovered(Exception):
    """The task needs something the grounded drafter cannot do yet, or the
    document did not show what it needed to go on."""


@dataclass
class Turn:
    """One assistant turn: a line of shown work and the calls it makes."""
    say: str
    calls: List[ToolCall] = field(default_factory=list)


def _q(tool: str, /, **params) -> ToolCall:
    return ToolCall(tool, params)


# ------------------------------------------------------------ reading the task text

_STATION = re.compile(r"(?<![\d.])(\d+)\+(\d{2}(?:\.\d+)?)")
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
_N = r"(\d+(?:\.\d+)?)"
_S = r"(\d+\+\d+(?:\.\d+)?)"
_BEGIN = re.compile(rf"(\S+) begins at N {_N}, E {_N}, station {_S}")
_PI = re.compile(rf"PI-\d+ at N {_N}, E {_N}(?:, R = {_N}')?")
_END = re.compile(rf"ends at N {_N}, E {_N}")
_EQUATION = re.compile(rf"{_S} BK = {_S} AH")
_LANES = re.compile(r"two (\d+(?:\.\d+)?)-ft lanes")
_BASEFILE = re.compile(r"(\S+\.rdoc\.json)")


def request_of(text: str) -> str:
    """The request itself: what follows the rules in the task text."""
    return text.split("THE TASK:", 1)[-1].strip()


def stated_alignment(text: str) -> Optional[dict]:
    """The alignment a task states (``create-alignment``), as the parameters
    of ``create_alignment``: the PIs as [easting, northing(, radius)], the
    stations as the text gives them."""
    begin, end = _BEGIN.search(text), _END.search(text)
    if not begin or not end:
        return None
    pis = [[float(begin.group(3)), float(begin.group(2))]]
    for n, e, r in _PI.findall(text):
        pis.append([float(e), float(n)] + ([float(r)] if r else []))
    pis.append([float(end.group(2)), float(end.group(1))])
    params = {"name": begin.group(1), "begin_station": begin.group(4), "pis": pis}
    equations = [{"back": back, "ahead": ahead} for back, ahead in _EQUATION.findall(text)]
    if equations:
        params["equations"] = equations
    return params


# ------------------------------------------------------------ the drafter


def _ok(results: Sequence[dict], calls: Sequence[ToolCall]) -> None:
    for call, result in zip(calls, results):
        if not result.get("ok"):
            why = (result.get("error") or {}).get("message")
            raise NotCovered(f"{call.name} failed: {why}")
        if result.get("truncated"):
            raise NotCovered(f"{call.name}: the result was cut; nothing to read it from")


def solve(text: str, phases: Sequence[str]) -> Generator[Turn, List[dict], str]:
    """Draft ``phases`` for the task ``text`` asks, a turn at a time: yields a
    ``Turn``, is sent that turn's results, and returns the note it submits
    with.  It is handed nothing else, so every value it sends was read from
    ``text``, from a result, or from spec v1's standards."""
    request = request_of(text)
    todo = [p for p in PHASE_ORDER if p in phases]
    left = [p for p in todo if p not in COVERED]
    if left:
        raise NotCovered(f"phases not covered: {', '.join(left)}")
    done: List[str] = []

    # -- what the document holds
    calls = [_q("get_document_state", detail="summary"), _q("list_layers")]
    results = yield Turn("See what the document holds first: its sheets, layers and design.", calls)
    _ok(results, calls)
    summary = results[0]["summary"]
    layers = {row["name"] for row in results[1]["layers"]}
    sheets = [s["name"] for s in summary.get("sheets") or []]
    own = list(summary.get("alignments") or [])

    def layer(role: str) -> str:
        name = ROLE_LAYER[role]
        if name not in layers:
            raise NotCovered(f"the document has no layer {name}")
        return name

    # -- the design: created from the task, or found in the document or its base drawing
    alignment: Optional[str] = None
    if "design" in todo:
        params = stated_alignment(request)
        if params is None:
            raise NotCovered("the task states no alignment to create")
        calls = [_q("create_alignment", **params)]
        results = yield Turn(
            f"The design is empty, so {params['name']} is created from the points the task gives. "
            "The task writes northing then easting; the engine takes [easting, northing], with "
            "the radius after it at each PI.", calls)
        _ok(results, calls)
        alignment = params["name"]
        done.append(f"created {alignment}")
    elif own:
        alignment = own[0]
    elif any(p in todo for p in MODEL_LETTERING + ("linework", "edges")):
        calls = [_q("list_alignments", include_references=True)]
        results = yield Turn("This file holds no alignment of its own, so look for one in the "
                             "attached base drawing.", calls)
        _ok(results, calls)
        rows = results[0].get("alignments") or []
        if not rows:
            raise NotCovered("no alignment in the document or its references")
        alignment = rows[0]["name"]

    # -- the layers
    if "layers" in todo:
        wanted = [n for n in LAYER_SET if n in request] or list(LAYER_SET)
        missing = [n for n in wanted if n not in layers]
        if missing:
            calls = [_q("create_layer", name=n, **SPEC["layer_props"][n]) for n in missing]
            results = yield Turn("Create the levels that are not there yet, each with its "
                                 "standard color and weight.", calls)
            _ok(results, calls)
            layers.update(missing)
            done.append(f"created {len(missing)} layers")

    # -- model linework
    if "linework" in todo:
        calls = [_q("draw_alignment", alignment=alignment, layer=layer("alignment"))]
        results = yield Turn(f"Draw the centerline of {alignment} from the design, on the "
                             f"alignment's own level, {layer('alignment')}.", calls)
        _ok(results, calls)
        done.append(f"drew {alignment} on {layer('alignment')}")
    if "edges" in todo:
        lanes = _LANES.search(request)
        if not lanes:
            raise NotCovered("the task gives no lane width")
        width = float(lanes.group(1))
        calls = [_q("draw_offset", alignment=alignment, offsets=[-width, width],
                    layer=layer("edges"))]
        results = yield Turn(
            f"Two {width:g}-ft lanes put an edge of pavement {width:g} ft each side of the "
            f"centerline: offsets left (negative) and right, on {layer('edges')}.", calls)
        _ok(results, calls)
        done.append(f"drew the pavement edges {width:g} ft each side on {layer('edges')}")

    # -- model lettering, sized for the sheet that shows it
    lettering = [p for p in todo if p in MODEL_LETTERING]
    if lettering:
        if not sheets:
            raise NotCovered("no sheet to read the plan scale from")
        calls = [_q("get_sheet_state", sheet=sheets[0])]
        if "bearings" in lettering:
            calls.append(_q("get_design_data", kind="tangents", alignment=alignment))
        if "callouts" in lettering:
            calls.append(_q("get_design_data", kind="curves", alignment=alignment))
        results = yield Turn(
            f"The lettering goes in the model and is read on the sheet, so read {sheets[0]} for "
            "its scale" + (", and the design for what there is to letter." if len(calls) > 1
                           else "."), calls)
        _ok(results, calls)
        viewports = results[0]["sheet"].get("viewports") or []
        if not viewports:
            raise NotCovered(f"{sheets[0]} has no viewport to read a scale from")
        scale = viewports[0]["feet_per_inch"]
        rows = {c.params["kind"]: r["rows"] for c, r in zip(calls[1:], results[1:])}
        if summary.get("annotation_scale") != scale:
            calls = [_q("set_annotation_scale", scale=scale)]
            results = yield Turn(
                f"{sheets[0]} shows the model at {scale:g} ft to the inch. Set the annotation "
                "scale to match, so the engine sizes the lettering for that sheet.", calls)
            _ok(results, calls)
        anno = layer("labels")
        if "stationing" in lettering:
            calls = [_q("annotate_stationing", space="model", alignment=alignment,
                        layer=layer("ticks"), label_layer=anno)]
            results = yield Turn(
                f"Station {alignment} in model space, where every sheet shows it: ticks, station "
                f"numbers and the curve points, all on {anno}.", calls)
            _ok(results, calls)
            done.append(f"stationed {alignment} on {anno}")
        if "bearings" in lettering:
            refs = [row["ref"] for row in rows["tangents"]]
            calls = [_q("place_label", space="model", alignment=alignment, anchor=ref,
                        kind="bearing", layer=anno) for ref in refs]
            results = yield Turn(
                f"{alignment} has {len(refs)} tangent{'s' if len(refs) != 1 else ''}. Letter the "
                f"bearing and length of each at its middle, on {anno}.", calls)
            _ok(results, calls)
            done.append(f"lettered {len(refs)} bearing{'s' if len(refs) != 1 else ''} on {anno}")
        if "callouts" in lettering:
            numbers = [row["index"] for row in rows["curves"]]
            calls = [_q("place_label", space="model", alignment=alignment, anchor=f"MC-{n}",
                        kind="mc", layer=anno) for n in numbers]
            results = yield Turn(
                f"{alignment} has {len(numbers)} curve{'s' if len(numbers) != 1 else ''}. Number "
                f"each at its midpoint, on {anno}.", calls)
            _ok(results, calls)
            done.append(f"numbered {len(numbers)} curve{'s' if len(numbers) != 1 else ''} on {anno}")

    # -- the base drawing
    if "reference" in todo:
        base = _BASEFILE.search(request)
        if not base:
            raise NotCovered("the task names no base drawing")
        ref = SPEC["reference"]
        calls = [_q("attach_reference", name=ref["name"], path=base.group(1), space=ref["space"])]
        results = yield Turn(
            f"Attach {base.group(1)} in model space as {ref['name']}, at its own coordinates, so "
            "the sheet's viewport shows it.", calls)
        _ok(results, calls)
        done.append(f"attached {base.group(1)} as {ref['name']}")

    return "Done: " + "; ".join(done) + "."


def covers(task: Task) -> List[str]:
    """The phases ``task`` needs that the grounded drafter cannot do yet:
    empty when it can do the task."""
    ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
    return [p for p in ttype.solution_phases() if p not in COVERED]


class GroundedAgent(Agent):
    """The grounded reference drafter as an episode agent.  It takes the
    task's asked phases at ``reset`` and the task text from the first
    observation, and nothing else of the task."""
    name = "grounded"

    def __init__(self):
        self._solver: Optional[Generator[Turn, List[dict], str]] = None
        self._phases: List[str] = []
        self._say = ""

    def reset(self, task: Task, level: str, mode: str) -> None:
        ttype = task_type(task.brief.deliverable.get("task_type", "plan-sheet"))
        self._phases = ttype.solution_phases()
        self._solver = None
        self._say = ""

    def act(self, observation: dict):
        try:
            if self._solver is None:
                self._solver = solve(observation["brief"], self._phases)
                turn = next(self._solver)
            else:
                turn = self._solver.send(observation["results"])
        except StopIteration as finished:
            self._say = ""
            return [ToolCall("submit", {"note": finished.value or ""})]
        self._say = turn.say
        return list(turn.calls)

    def turn_record(self) -> dict:
        return {"text": self._say}

    def describe(self) -> dict:
        return {"model": "grounded-reference", "provider": "harness"}


# ------------------------------------------------------------ the audit


def _flatten(value, strings: set, numbers: list) -> None:
    """Every string (keys too) and number in a JSON value; the numbers a
    string writes (``text 5 ft``, ``125+00.00``) count as well."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        numbers.append(float(value))
    elif isinstance(value, str):
        strings.add(value)
        numbers.extend(numbers_in(value))
    elif isinstance(value, dict):
        for key, item in value.items():
            strings.add(str(key))
            _flatten(item, strings, numbers)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _flatten(item, strings, numbers)


def numbers_in(text: str) -> List[float]:
    """The numbers a text writes: plain ones, and each station as feet."""
    found = [int(a) * 100 + float(b) for a, b in _STATION.findall(text)]
    found += [float(m) for m in _NUMBER.findall(text)]
    return found


def _standards():
    strings: set = set()
    numbers: list = []
    _flatten(SPEC, strings, numbers)
    return strings, numbers


#: what spec v1 fixes, as the audit reads it: a value found here is a drafting standard
STANDARDS = _standards()
#: a design point named by its index: the kind is the engine's word, the index a number seen
_ANCHOR = re.compile(r"^(BEGIN|END|PI|PC|PT|BC|EC|MC|T|C|EQ)-(\d+)$")
TOLERANCE = 0.005


class Seen:
    """What the model has in front of it at a point in an episode."""

    def __init__(self, text: str):
        self.text = text
        self.strings: set = set()
        self.numbers: List[float] = numbers_in(text)

    def add(self, result) -> None:
        _flatten(result, self.strings, self.numbers)

    def number(self, value: float, standards: bool = True) -> bool:
        target = abs(float(value))  # a distance to the left is written negative
        return (any(abs(abs(n) - target) <= TOLERANCE for n in self.numbers)
                or (standards and any(abs(abs(n) - target) <= TOLERANCE for n in STANDARDS[1])))

    def string(self, value: str, tool_text: str) -> bool:
        if not value or value in self.strings or value in self.text or value in STANDARDS[0]:
            return True
        if value in tool_text:
            return True
        anchor = _ANCHOR.match(value)
        if anchor:  # the index has to be one the design showed: no standard names a curve
            return self.number(float(anchor.group(2)), standards=False)
        if _STATION.fullmatch(value):
            return self.number(numbers_in(value)[0], standards=False)
        if ":" in value:  # an alignment named through its reference
            return all(self.string(part, tool_text) for part in value.split(":"))
        return False


def _walk(value, path: str):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _walk(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            yield from _walk(item, f"{path}[{i}]")
    else:
        yield path, value


def audit(text: str, tools: Sequence[dict], turns: Sequence[dict]) -> List[dict]:
    """Every value an episode's calls carry that was not grounded when the
    call was made, and every number its shown work states that was not:
    ``[{"turn", "tool", "path", "value"}]``, empty for a grounded episode.
    ``text`` is the task as the model was given it, ``tools`` the definitions
    it was shown, ``turns`` the episode's turn records."""
    tool_text = {t["name"]: json.dumps(t, ensure_ascii=False) for t in tools}
    seen = Seen(text)
    findings: List[dict] = []
    for turn in turns:
        assistant = turn.get("assistant") or {}
        n = turn.get("n")
        for number in numbers_in(assistant.get("text") or ""):
            if not seen.number(number):
                findings.append({"turn": n, "tool": None, "path": "say", "value": number})
        for call in assistant.get("tool_calls") or []:
            name, params = call.get("name"), call.get("params") or {}
            if name == "submit":
                for number in numbers_in(str(params.get("note") or "")):
                    if not seen.number(number):
                        findings.append({"turn": n, "tool": name, "path": "note", "value": number})
                continue
            for path, value in _walk(params, ""):
                if isinstance(value, bool) or value is None:
                    continue
                grounded = (seen.number(value) if isinstance(value, (int, float))
                            else seen.string(str(value), tool_text.get(name, "")))
                if not grounded:
                    findings.append({"turn": n, "tool": name, "path": path, "value": value})
        # what the calls put on the page counts from the next turn on
        for call, result in zip(assistant.get("tool_calls") or [], turn.get("results") or []):
            if result.get("ok"):
                seen.add(call.get("params") or {})
            seen.add(result)
    return findings


# ------------------------------------------------------------ recording


def record_task(task: Task, level: str = "vague", out_root=None, agent: Optional[Agent] = None,
                run_id: str = "") -> dict:
    """Run one task under ``agent`` (the grounded drafter by default) and
    audit what it did.  The row says whether the recording is training data:
    ``kept`` when it submitted, scored 100 and nothing was ungrounded."""
    from roaddraft.eval.episode import Episode, EpisodeConfig
    episode = Episode(task, agent or GroundedAgent(), EpisodeConfig(level=level, run_id=run_id),
                      out_root=out_root)
    result = episode.run()
    ungrounded = audit(episode.brief_text, episode.tools, episode.turns)
    return {"task_id": task.task_id, "task_type": task.brief.task_type, "level": level,
            "termination": result.termination, "error": result.error,
            "effective": result.effective_score, "turns": result.turns, "steps": result.steps,
            "ungrounded": ungrounded, "path": result.path,
            "kept": (result.termination == "submit" and result.effective_score == 100.0
                     and not ungrounded)}


def record(taskset: str, out, level: str = "vague", limit: Optional[int] = None,
           types: Optional[Iterable[str]] = None) -> dict:
    """Record the grounded reference of every task of ``taskset`` the drafter
    covers, under ``out``: the episode files and ``index.json``."""
    from roaddraft.eval import taskset as tasksets
    out = Path(out)
    rows: List[dict] = []
    entries = [e for e in tasksets.entries(taskset) if not types or e["task_type"] in set(types)]
    for entry in entries[:limit]:
        task = tasksets.task_from_entry(entry)
        missing = covers(task)
        if missing:
            rows.append({"task_id": task.task_id, "task_type": entry["task_type"], "level": level,
                         "covered": False, "missing": missing, "kept": False})
            continue
        rows.append({"covered": True, **record_task(task, level, out_root=out, run_id=out.name)})
    by_type: Dict[str, Counter] = {}
    for row in rows:
        tally = by_type.setdefault(row["task_type"], Counter())
        tally["tasks"] += 1
        tally["covered"] += bool(row.get("covered"))
        tally["kept"] += bool(row["kept"])
    index = {"taskset": taskset, "level": level, "covered_phases": list(COVERED),
             "tasks": len(rows), "covered": sum(bool(r.get("covered")) for r in rows),
             "kept": sum(bool(r["kept"]) for r in rows),
             "by_type": {t: dict(c) for t, c in sorted(by_type.items())}, "rows": rows}
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    return index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories.grounded",
                                     description=__doc__.split("\n\n")[0])
    parser.add_argument("--taskset", default="d1-train")
    parser.add_argument("--out", required=True)
    parser.add_argument("--level", default="vague", choices=("vague", "explicit"))
    parser.add_argument("--type", action="append", dest="types")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    index = record(args.taskset, args.out, args.level, args.limit, args.types)
    print(f"{args.taskset} at the {args.level} level: {index['tasks']} tasks, "
          f"{index['covered']} covered, {index['kept']} kept (scored 100, nothing ungrounded)")
    for ttype, tally in index["by_type"].items():
        print(f"  {ttype:20s} {tally.get('kept', 0):4d} kept of {tally.get('covered', 0):4d} covered "
              f"of {tally['tasks']:4d}")
    bad = [r for r in index["rows"] if r.get("covered") and not r["kept"]]
    for row in bad[:10]:
        print(f"  NOT KEPT {row['task_id']} {row['task_type']}: {row['termination']} "
              f"{row['effective']} {row.get('error') or ''} {row['ungrounded'][:3]}")
    return 1 if bad else 0


__all__ = ["COVERED", "NotCovered", "Turn", "GroundedAgent", "solve", "covers", "audit",
           "record_task", "record", "request_of", "stated_alignment", "numbers_in", "STANDARDS"]

if __name__ == "__main__":
    sys.exit(main())
