"""Injected faults: the grounded references with the subject's own mistakes
put in, each followed by the reference's way out (training plan section 3,
*Data*, "Injected faults"; stage C0, tracker ``c-faults``).

Imitating a drafter that never errs makes a model that cannot recover: the
9B's largest tool-use loss on ``d1-test`` is stationing left off after
``annotate_stationing`` failed once and was never retried right.  So a
faulted copy of a reference has, at one or two places, a call broken the way
the 9B breaks it, the engine's real error for it, and then the reference's
own call with a line of shown work that reads the error.  The broken turn is
context, not a target: its assistant message goes into the conversation with
``weight: 0`` (``conversations.messages``), so a model is trained on the
recovery and never on the mistake.

**The mistakes** (``KINDS``) are the 9B's most frequent failed calls on its
six board rows (``d1-test`` and ``d1-real`` at both levels, ``d1-test-hard``
and ``d1-real-hard`` vague), tallied by tool and error.  Only their shape is
taken from those rows, never a value: the broken call is made from the
training reference's own call.  Each kind is weighted by how often the 9B
made it with that tool, so the faults fall about where the 9B's do.

- *swap*: a call of the reference goes wrong.  The broken turn is the
  reference turn's calls up to that one, with that one broken; the next turn
  is the reference's call and the calls after it, with the recovery line.
- *insert*: an extra call the reference never makes (drawing an alignment the
  base drawing carries; setting up a sheet, reference or layer a second
  time), as a turn of its own before a reference turn, whose shown work
  starts with the recovery line.

**Through the bus, and checked.**  A faulted copy is run as an episode
(``FaultAgent``): the reference's recorded calls are played back with the
broken turns in place, so the error is the engine's own.  As it runs, every
broken call must fail and every other result must equal the reference's,
byte for byte; at the end the journal must equal the reference's (a failed
call changes nothing), the episode must score 100, and the grounded audit
must find nothing ungrounded outside the broken turns.  A copy that misses
any of these is tried again at other places, up to ``ATTEMPTS`` times.

``python -m roaddraft.trajectories.faults inject`` writes ``results/faults-v2/
<set>-<level>/`` (episode files and ``index.json``, as the recorder lays out
``results/grounded-v2/``); ``conversations convert`` turns them into
``results/training/<set>-<level>-faults.jsonl``.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from roaddraft.eval.agents.basic import Agent, ToolCall

REPO = Path(__file__).resolve().parents[3]
#: the current recordings and their faulted copies.  ``results/grounded`` and
#: ``results/faults`` hold the recordings made before the tool pin (superseded,
#: see the SUPERSEDED.md in each) and are no longer any command's default.
SOURCE = REPO / "results" / "grounded-v2"
OUT = REPO / "results" / "faults-v2"
LEVELS = ("vague", "explicit")
#: a faulted copy is tried at other places this many times before the reference is left out
ATTEMPTS = 3
#: the share of faulted copies with two faults rather than one
TWO = 0.4
#: the errors a broken call may come back with: the engine's, never the harness's
FAILED = ("command_failed", "query_failed")


@dataclass(frozen=True)
class Kind:
    """One of the 9B's mistakes: the tools it made it with and how often
    (its six board rows), how it goes in (``swap`` or ``insert``), and a line
    for the dataset card."""
    name: str
    tools: Dict[str, int]
    layout: str
    what: str


KINDS: Tuple[Kind, ...] = (
    Kind("alignment_left_off",
         {"place_label": 396, "station_to_xy": 35, "annotate_stationing": 24, "resolve_anchor": 18,
          "place_curve_table": 10, "xy_to_station": 5},
         "swap", "a call on the referenced design that does not name its alignment"),
    Kind("alignment_misnamed",
         {"place_curve_table": 39, "annotate_stationing": 24, "get_design_data": 17,
          "resolve_anchor": 7, "place_label": 5, "station_to_xy": 3},
         "swap", "the alignment named without its reference's name, or with one when it is the file's own"),
    Kind("stationing_on_sheet", {"annotate_stationing": 206},
         "swap", "alignment stationing sent to a sheet instead of model space"),
    Kind("begin_station_given", {"annotate_stationing": 136},
         "swap", "a begin station given to alignment-mode stationing"),
    Kind("layer_not_made",
         {"draw_alignment": 51, "draw_offset": 17, "place_curve_table": 15, "place_dimension": 13,
          "place_label": 9, "draw_station_offset": 5},
         "swap", "drafting on a generic layer name the file does not have"),
    Kind("draw_referenced", {"draw_alignment": 76},
         "insert", "drawing an alignment the attached base drawing already carries"),
    Kind("made_twice", {"create_sheet": 27, "attach_reference": 24, "create_layer": 15},
         "insert", "setting up again a sheet, reference or layer made earlier"),
)
KIND = {k.name: k for k in KINDS}

#: the generic name a model reaches for in place of the file's layer, by what the call draws
BAD_LAYER = {"draw_alignment": "C-ROAD-CNTR", "draw_offset": "C-ROAD-EDGE",
             "draw_station_offset": "C-ROAD-EDGE", "place_curve_table": "C-ANNO-TABL",
             "place_dimension": "C-ANNO-DIMS", "place_label": "C-ANNO-TEXT"}

#: the broken turn's shown work, where the reference's would not fit the broken call
THOUGHT = {
    "stationing_on_sheet": "Station {name} on {sheet}: the ticks, the station numbers and the curve points.",
    "draw_referenced": "Draw {name}'s linework first, so the lettering has a line to sit on.",
    "made_twice:create_layer": "Make the layer {name} for this.",
    "made_twice:create_sheet": "Set up the sheet {name}.",
    "made_twice:attach_reference": "Attach {path} as {name}.",
}
#: the line the recovery turn opens with: two wordings each, picked per copy
RECOVERY = {
    "alignment_left_off": (
        "This file owns no alignment of its own: the design is {name}, in the attached base drawing, "
        "and the call has to name it.",
        "That failed because the call named no alignment, and this file owns none; the design is "
        "{name}, in the attached reference."),
    "alignment_misnamed:bare": (
        "{wrong} is not in this file; it is in the attached base drawing, so it goes by its qualified "
        "name, {name}.",
        "The alignment lives in the reference, so its name carries the reference's: {name}, not {wrong}."),
    "alignment_misnamed:prefixed": (
        "{name} is this file's own alignment, not one in a reference, so it goes by its plain name.",
        "No reference carries {wrong}; the alignment is this file's own, {name}."),
    "stationing_on_sheet": (
        "Stationing is drawn in model space, never on a sheet: {name}'s ticks and stations go in the "
        "model, and {sheet} shows them through its viewport.",
        "annotate_stationing works in model space; {sheet} shows the stationing through its viewport, "
        "so it goes in the model."),
    "begin_station_given": (
        "In alignment mode the engine letters {name}'s own stations, so begin_station comes out.",
        "{name} carries its own stationing; alignment mode takes it from there, without a begin_station."),
    "layer_not_made": (
        "{bad} is not a layer in this file; this goes on {good}.",
        "There is no layer {bad} here. The layer for this is {good}."),
    "draw_referenced": (
        "{name}'s linework is in the attached base drawing and already shows through the viewport; "
        "this file draws none of it.",
        "Nothing to draw: {name} lives in the reference, and its linework shows through the viewport "
        "as it is."),
    "made_twice:create_layer": (
        "{name} was made earlier and is there to use.",
        "{name} already exists from earlier, so carry on with it."),
    "made_twice:create_sheet": (
        "{name} was set up earlier and is there to use.",
        "The sheet {name} already exists from earlier, so carry on with it."),
    "made_twice:attach_reference": (
        "{name} is attached already; it does not go on twice.",
        "The reference {name} was attached earlier, so carry on with it."),
}


# ------------------------------------------------------------ where a fault can go

@dataclass
class Site:
    """One place a fault can go: before (``insert``) or from (``swap``) call
    ``call`` of reference turn ``turn`` (0-based); the broken calls (a swap
    breaks every call from ``call`` on that the mistake fits, up to
    ``MOST_BROKEN``, as a model that makes it once makes it for the whole
    turn); and the broken and recovery turns' shown work."""
    kind: str
    tool: str
    turn: int
    call: int
    broken: List[dict]
    thought: Optional[str]
    recovery: Tuple[str, ...]

    def key(self) -> tuple:
        return (self.kind, self.turn, self.call)


#: the most calls one broken turn carries
MOST_BROKEN = 4


def _swap_name(text: str, old: str, new: str) -> str:
    """``text`` with the name ``old`` written ``new``, whole names only
    (``ALIGN-1`` is not part of ``ALIGN-12`` or ``BASE:ALIGN-1``)."""
    import re
    return re.sub(rf"(?<![\w:-]){re.escape(old)}(?![\w-])", new.replace("\\", r"\\"), text)


def _calls(turn: dict) -> List[dict]:
    return list((turn.get("assistant") or {}).get("tool_calls") or [])


def _text(turn: dict) -> str:
    return (turn.get("assistant") or {}).get("text") or ""


def _walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)


class Known:
    """What the conversation has shown before each turn: the task text, then
    each turn's calls and results.  ``before(s, i)``: whether ``s`` appears
    in what was shown before turn ``i``."""

    def __init__(self, brief: str, turns: Sequence[dict]):
        self.brief = brief
        self.chunks = [json.dumps({"calls": _calls(t), "results": t.get("results") or []},
                                  ensure_ascii=False) for t in turns]
        self.turns = turns

    def first(self, s: str) -> Optional[int]:
        """The turn whose calls or results first show ``s`` (-1: the task
        text), or None."""
        if s in self.brief:
            return -1
        for i, chunk in enumerate(self.chunks):
            if s in chunk:
                return i
        return None

    def before(self, s: str, i: int) -> bool:
        at = self.first(s)
        return at is not None and at < i

    def begin_station(self, name: str, i: int) -> Optional[str]:
        """``name``'s begin station as an earlier result gave it."""
        for turn in self.turns[:i]:
            for d in _walk(turn.get("results") or []):
                if d.get("name") == name and isinstance(d.get("begin_station_text"), str):
                    return d["begin_station_text"]
        return None

    def sheets(self, i: int) -> List[str]:
        """The sheet names the calls before turn ``i`` used, in order."""
        out: List[str] = []
        for turn in self.turns[:i]:
            for call in _calls(turn):
                p = call.get("params") or {}
                for key in ("sheet", "space"):
                    v = p.get(key)
                    if isinstance(v, str) and v != "model" and v not in out:
                        out.append(v)
        return out


def _broken(call: dict, **change) -> dict:
    params = dict(call.get("params") or {})
    for k, v in change.items():
        if v is None:
            params.pop(k, None)
        else:
            params[k] = v
    return {"name": call["name"], "params": params}


def _mistakes(call: dict, known: Known, i: int, alone: bool) -> List[Tuple[str, dict, dict]]:
    """The swap mistakes ``call`` (in turn ``i``; ``alone`` when it is the
    turn's only call) can be made to carry: ``(kind, the broken call, the
    names its shown work is written with)``."""
    name, p = call["name"], call.get("params") or {}
    align = p.get("alignment") if isinstance(p.get("alignment"), str) else None
    out: List[Tuple[str, dict, dict]] = []
    if align and ":" in align and name in KIND["alignment_left_off"].tools:
        out.append(("alignment_left_off", _broken(call, alignment=None), {"name": align}))
    if align and name in KIND["alignment_misnamed"].tools:
        # whether the wrong name fails is the engine's to say: the copy is run and checked
        if ":" in align:
            ref, bare = align.split(":", 1)
            wrong, form = (bare if ref == "BASE" else "BASE:" + bare), "bare"
        else:
            wrong, form = "BASE:" + align, "prefixed"
        out.append(("alignment_misnamed", _broken(call, alignment=wrong),
                    {"name": align, "wrong": wrong, "form": form}))
    if name == "annotate_stationing" and align:
        if p.get("space") == "model" and alone:
            sheets = [s for s in known.sheets(i) if known.before(s, i)]
            if sheets:
                out.append(("stationing_on_sheet", _broken(call, space=sheets[0]),
                            {"name": align, "sheet": sheets[0]}))
        if "begin_station" not in p:
            begin = known.begin_station(align, i) or "0+00"
            out.append(("begin_station_given", _broken(call, begin_station=begin), {"name": align}))
    layer = p.get("layer")
    if isinstance(layer, str) and name in KIND["layer_not_made"].tools:
        bad = BAD_LAYER[name]
        if bad != layer and known.first(bad) is None:
            out.append(("layer_not_made", _broken(call, layer=bad), {"bad": bad, "good": layer}))
    return out


def _thought(kind: str, text: str, names: dict) -> str:
    """The broken turn's shown work: the reference's, written with the wrong
    name where the mistake is a name, or a line of its own."""
    if kind == "alignment_misnamed":
        return _swap_name(text, names["name"], names["wrong"])
    if kind == "layer_not_made":
        return _swap_name(text, names["good"], names["bad"])
    key = f"{kind}:{names['tool']}" if kind == "made_twice" else kind
    if key in THOUGHT:
        return THOUGHT[key].format(**names)
    return text


def _recovery(kind: str, names: dict) -> Tuple[str, ...]:
    key = (f"{kind}:{names['form']}" if kind == "alignment_misnamed"
           else f"{kind}:{names['tool']}" if kind == "made_twice" else kind)
    return tuple(r.format(**names) for r in RECOVERY[key])


#: what each set-up command makes, the params that name it, and the params that use it
MAKERS = {"create_layer": ("name", ("layer", "label_layer")),
          "create_sheet": ("name", ("sheet", "space")),
          "attach_reference": ("name", ())}


def sites(brief: str, turns: Sequence[dict]) -> List[Site]:
    """Every place in a reference's turns where one of ``KINDS`` can go.  The
    last turn (the submit) takes no swap; something made twice may go before
    it."""
    known = Known(brief, turns)
    out: List[Site] = []
    drew_first = False
    made: Dict[str, Tuple[int, dict]] = {}     # (command, name) -> (turn, the call that made it)
    twice: set = set()
    last = len(turns) - 1
    for i, turn in enumerate(turns):
        calls, text = _calls(turn), _text(turn)
        # inserts go before this turn
        for call in calls if i < last else []:
            p = call.get("params") or {}
            align = p.get("alignment")
            if (not drew_first and call["name"] in ("annotate_stationing", "place_label")
                    and isinstance(align, str) and ":" in align):
                drew_first = True
                layer = str(p.get("layer") or "")
                line = layer[:-len("-anno")] if layer.endswith("-anno") else layer
                if not known.before(line, i):
                    line = layer
                names = {"name": align}
                out.append(Site("draw_referenced", "draw_alignment", i, -1,
                                [{"name": "draw_alignment", "params": {"alignment": align, "layer": line}}],
                                _thought("draw_referenced", "", names), _recovery("draw_referenced", names)))
                break
        # something made earlier, made again: before the first turn after that uses it (a layer or
        # a sheet, a turn or more on), or the turn right after (a reference)
        for (tool, name), (j, maker) in made.items():
            if (tool, name) in twice:
                continue
            uses = MAKERS[tool][1]
            used = any((c.get("params") or {}).get(key) == name for c in calls for key in uses
                       if c["name"] != tool)
            if (uses and used and j < i - 1) or (not uses and i == j + 1):
                twice.add((tool, name))
                names = {"tool": tool, "name": name, "path": (maker.get("params") or {}).get("path", "")}
                out.append(Site("made_twice", tool, i, -1, [maker], _thought("made_twice", "", names),
                                _recovery("made_twice", names)))
        # swaps: at the first call of the turn each mistake fits, and on through the calls after
        # it that take the same mistake the same way
        firsts: set = set()
        for k, call in enumerate(calls if i < last else []):
            for kind, broken, names in _mistakes(call, known, i, len(calls) == 1):
                if kind in firsts:
                    continue
                firsts.add(kind)
                run = [broken]
                for later in calls[k + 1:]:
                    if len(run) >= MOST_BROKEN or later["name"] != call["name"]:
                        break
                    again = next((b for kd, b, nm in _mistakes(later, known, i, False)
                                  if kd == kind and nm == names), None)
                    if again is None:
                        break
                    run.append(again)
                out.append(Site(kind, call["name"], i, k, run, _thought(kind, text, names),
                                _recovery(kind, names)))
        for call in calls:
            p = call.get("params") or {}
            key = MAKERS.get(call["name"], (None,))[0]
            if key and isinstance(p.get(key), str):
                made.setdefault((call["name"], p[key]), (i, {"name": call["name"], "params": dict(p)}))
    return out


def choose(found: Sequence[Site], rng: random.Random, n: int) -> List[Site]:
    """Up to ``n`` sites: each time a kind by how often the 9B made that
    mistake (all its tools), among the kinds this reference has a place for;
    then a tool by how often it made it with that tool, among the tools here;
    then one of the places.  No two faults of a kind, none in the same turn
    or the turn next to another.  (Weighing (kind, tool) pairs instead lets a
    kind that fits many tools outweigh its own rate.)"""
    chosen: List[Site] = []
    pool = list(found)
    for _ in range(n):
        kinds = sorted({s.kind for s in pool})
        if not kinds:
            break
        kind = rng.choices(kinds, [sum(KIND[k].tools.values()) for k in kinds])[0]
        tools = sorted({s.tool for s in pool if s.kind == kind})
        tool = rng.choices(tools, [KIND[kind].tools[t] for t in tools])[0]
        site = rng.choice([s for s in pool if s.kind == kind and s.tool == tool])
        chosen.append(site)
        pool = [s for s in pool if s.kind != kind and abs(s.turn - site.turn) > 1]
    return sorted(chosen, key=lambda s: (s.turn, s.call))


# ------------------------------------------------------------ the faulted copy as an episode

@dataclass
class Step:
    """One turn of a faulted copy: its calls and shown work, what each result
    must be (the reference's, or None for a broken call, which must fail),
    and the ``fault`` mark its turn record carries."""
    calls: List[dict]
    text: str
    expect: List[Optional[dict]]
    fault: Optional[dict] = None


def plan(turns: Sequence[dict], chosen: Sequence[Site], rng: random.Random) -> List[Step]:
    """The reference's turns with the chosen faults put in."""
    at = {s.turn: s for s in chosen}
    steps: List[Step] = []
    for i, turn in enumerate(turns):
        calls, text, results = _calls(turn), _text(turn), list(turn.get("results") or [])
        site = at.get(i)
        if site is None:
            steps.append(Step(calls, text, results))
            continue
        mark = {"kind": site.kind, "tool": site.tool, "reference_turn": turn.get("n", i + 1)}
        recovery = rng.choice(site.recovery)
        broken = [None] * len(site.broken)
        if site.call < 0:
            steps.append(Step(list(site.broken), site.thought or "", broken, dict(mark, role="broken")))
            steps.append(Step(calls, f"{recovery} {text}".strip(), results, dict(mark, role="recovery")))
        else:
            k = site.call
            steps.append(Step(calls[:k] + list(site.broken),
                              site.thought if site.thought is not None else text,
                              results[:k] + broken, dict(mark, role="broken")))
            steps.append(Step(calls[k:], recovery, results[k:], dict(mark, role="recovery")))
    return steps


class Miss(Exception):
    """A faulted copy that went another way than its reference: a broken call
    that did not fail, or a result that differs from the reference's."""


def _same(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True, ensure_ascii=False) == json.dumps(b, sort_keys=True, ensure_ascii=False)


class FaultAgent(Agent):
    """Plays a faulted copy back through the episode loop, checking each
    turn's results against the reference's as they come."""
    name = "grounded-faults"

    def __init__(self, steps: Sequence[Step]):
        self.steps = list(steps)
        self.i = -1

    def reset(self, task, level: str, mode: str) -> None:
        self.i = -1

    def act(self, observation: dict):
        if self.i >= 0:
            self._check(self.steps[self.i], observation.get("results") or [])
        self.i += 1
        step = self.steps[self.i]
        return [ToolCall(c["name"], dict(c.get("params") or {})) for c in step.calls]

    def _check(self, step: Step, results: Sequence[dict]) -> None:
        if len(results) != len(step.expect):
            raise Miss(f"turn {self.i + 1}: {len(results)} results, the copy expects {len(step.expect)}")
        for k, (got, want) in enumerate(zip(results, step.expect)):
            if want is None:
                etype = (got.get("error") or {}).get("type")
                if got.get("ok") or etype not in FAILED:
                    raise Miss(f"turn {self.i + 1}: the broken {got.get('name')} did not fail "
                               f"({'ok' if got.get('ok') else etype})")
            elif not _same(got, want):
                raise Miss(f"turn {self.i + 1}: {got.get('name')} came back other than in the reference")

    def turn_record(self) -> dict:
        step = self.steps[self.i]
        out = {"text": step.text}
        if step.fault:
            out["fault"] = step.fault
        return out

    def describe(self) -> dict:
        return {"model": "grounded-reference+faults", "provider": "harness"}


def broken_turns(turns: Iterable[dict]) -> set:
    """The numbers of an episode's broken turns."""
    return {t.get("n") for t in turns
            if ((t.get("assistant") or {}).get("fault") or {}).get("role") == "broken"}


def audit_turns(brief: str, tools: Sequence[dict], turns: Sequence[dict]) -> List[dict]:
    """The grounded audit (``grounded.audit``) with the broken turns' own
    findings left out: a broken call is wrong on purpose and is not trained
    on.  What the broken turns showed still counts for the turns after them."""
    from roaddraft.trajectories.grounded import audit
    broken = broken_turns(turns)
    return [f for f in audit(brief, tools, turns) if f.get("turn") not in broken]


def faults_of(turns: Iterable[dict]) -> List[dict]:
    """The faults an episode carries: one row a broken turn."""
    return [dict((t.get("assistant") or {})["fault"], turn=t.get("n")) for t in turns
            if ((t.get("assistant") or {}).get("fault") or {}).get("role") == "broken"]


# ------------------------------------------------------------ one reference

def inject(path, taskset: str, out_root, attempts: int = ATTEMPTS) -> dict:
    """A faulted copy of one reference episode, written under ``out_root``:
    the index row, ``kept`` when the copy passed every check."""
    from roaddraft.eval.episode import Episode, EpisodeConfig
    from roaddraft.eval.trajectory import read_episode
    from roaddraft.tasks.prompts import task_text
    from roaddraft.trajectories.conversations import budgets_of, rebuild_task

    records = read_episode(path)
    header, end, journal, turns = records["header"], records["end"], records["journal"], records["turns"]
    row = {"task_id": header["task_id"], "task_type": header.get("task_type"), "level": header["level"],
           "reference": Path(path).name, "kept": False}
    task = rebuild_task(taskset, header["task_id"])
    brief = task_text(task.brief, header["level"])
    found = sites(brief, turns)
    row["sites"] = dict(sorted(Counter(s.kind for s in found).items()))
    room = budgets_of(header).steps - int(end.get("steps") or 0)
    tried: List[dict] = []
    for attempt in range(attempts):
        rng = random.Random(f"{header['task_id']}|{header['level']}|{attempt}")
        chosen = choose(found, rng, 2 if rng.random() < TWO else 1)
        # every broken call is a step more than the reference took: within the step budget
        while chosen and sum(len(s.broken) for s in chosen) > room:
            chosen.pop()
        if not chosen:
            row["reason"] = "no room" if room <= 0 else ("no site" if not tried else tried[-1]["miss"])
            break
        steps = plan(turns, chosen, rng)
        episode = Episode(task, FaultAgent(steps),
                          EpisodeConfig(level=header["level"], mode=header.get("mode", "single"),
                                        run_id=Path(out_root).name),
                          out_root=out_root)
        result = episode.run()
        miss = _miss(result, episode, journal, brief)
        if miss is None:
            row.update(kept=True, path=result.path, attempt=attempt + 1,
                       faults=[{"kind": s.kind, "tool": s.tool, "turn": s.turn + 1, "broken": len(s.broken)}
                               for s in chosen],
                       turns=result.turns, steps=result.steps)
            return row
        tried.append({"faults": [s.kind for s in chosen], "miss": miss})
        if result.path and Path(result.path).exists():
            Path(result.path).unlink()
        keys = {s.key() for s in chosen}
        found = [s for s in found if s.key() not in keys]
    row["tried"] = tried
    row.setdefault("reason", tried[-1]["miss"] if tried else "no site")
    return row


def _miss(result, episode, journal: dict, brief: str) -> Optional[str]:
    """Why a faulted copy is not kept, or None."""
    if result.termination != "submit":
        return (result.error or result.termination or "")[:300]
    if result.effective_score < 100.0:
        return f"scored {result.effective_score:g}"
    if not _same({"e": list(episode.session.bus.journal)}, {"e": journal.get("entries") or []}):
        return "the journal differs from the reference's"
    found = audit_turns(brief, episode.tools, episode.turns)
    if found:
        return "ungrounded: " + json.dumps(found[:2], ensure_ascii=False)
    return None


def _inject_job(job: Tuple[str, str, str]) -> dict:
    path, taskset, out_root = job
    try:
        return inject(path, taskset, out_root)
    except Exception as exc:  # a broken reference is counted, not fatal to the set
        return {"task_id": Path(path).name.split(".")[0], "reference": Path(path).name, "kept": False,
                "reason": f"error: {type(exc).__name__}: {exc}"[:300]}


# ------------------------------------------------------------ a set

def inject_set(src: Path, taskset: str, out: Path, jobs: int = 1, limit: Optional[int] = None,
               log=None) -> dict:
    """A faulted copy of every reference the recorder kept in ``src``, into
    ``out`` (episode files and ``index.json``)."""
    from roaddraft.trajectories.conversations import sources
    paths, recorder = sources(Path(src))
    paths = paths[:limit] if limit is not None else paths
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    jobs_list = [(str(p), taskset, str(out)) for p in paths]
    started = time.time()
    if jobs > 1 and len(jobs_list) > 1:
        from multiprocessing import get_context
        with get_context("spawn").Pool(jobs) as pool:
            rows = pool.map(_inject_job, jobs_list, chunksize=4)
    else:
        rows = [_inject_job(j) for j in jobs_list]
    kept = [r for r in rows if r["kept"]]
    for r in kept:
        r["path"] = str(Path(r["path"]).relative_to(out)) if Path(r["path"]).is_absolute() else r["path"]
    kinds = Counter(f["kind"] for r in kept for f in r["faults"])
    index = {"taskset": taskset, "level": recorder.get("level"), "source": str(src),
             "tasks": len(rows), "covered": len(rows), "kept": len(kept),
             "faults": sum(kinds.values()), "by_kind": dict(sorted(kinds.items())),
             "by_count": dict(sorted(Counter(len(r["faults"]) for r in kept).items())),
             "not_kept": dict(Counter(r.get("reason", "")[:60] for r in rows if not r["kept"]).most_common(10)),
             "seconds": round(time.time() - started, 1), "rows": rows}
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n")
    if log:
        log(f"{out.name}: {len(kept)} faulted copies of {len(rows)} references, {sum(kinds.values())} faults "
            f"{dict(kinds)}" + (f"; not kept {index['not_kept']}" if len(kept) < len(rows) else ""))
    return index


def run(sets: Sequence[str], levels: Sequence[str] = LEVELS, source: Path = SOURCE, out: Path = OUT,
        jobs: int = 1, limit: Optional[int] = None, log=print) -> Dict[str, dict]:
    """``inject_set`` for every ``<set>-<level>`` recording folder under ``source``."""
    done = {}
    for name in sets:
        for level in levels:
            src = Path(source) / f"{name}-{level}"
            if not (src / "index.json").exists():
                log(f"{src}: no recordings, skipped")
                continue
            done[f"{name}-{level}"] = inject_set(src, name, Path(out) / f"{name}-{level}", jobs=jobs,
                                                 limit=limit, log=log)
    return done


def main(argv=None) -> int:
    from roaddraft.eval import taskset as tasksets
    parser = argparse.ArgumentParser(prog="python -m roaddraft.trajectories.faults",
                                     description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("inject", help="a faulted copy of every kept reference")
    every = tuple(tasksets.TRAIN_NAMES) + tuple(tasksets.REAL_TRAIN_NAMES)
    c.add_argument("--set", action="append", dest="sets", choices=every,
                   help="a training set (default: every D1 training set, seeded and real-sheet)")
    c.add_argument("--level", action="append", dest="levels", choices=LEVELS)
    c.add_argument("--source", type=Path, default=SOURCE, help="the references, <set>-<level>/ each")
    c.add_argument("--out", type=Path, default=OUT)
    c.add_argument("--jobs", type=int, default=max(1, min(6, (os.cpu_count() or 2) - 2)))
    c.add_argument("--limit", type=int, help="the first N references of each folder")
    args = parser.parse_args(argv)
    done = run(args.sets or list(every), args.levels or list(LEVELS), args.source,
               args.out, jobs=args.jobs, limit=args.limit)
    kept = sum(i["kept"] for i in done.values())
    tasks = sum(i["tasks"] for i in done.values())
    print(f"{kept} faulted copies of {tasks} references written to {args.out}")
    return 0


__all__ = ["KINDS", "KIND", "Kind", "Site", "Step", "Known", "Miss", "FaultAgent", "sites", "choose",
           "plan", "broken_turns", "audit_turns", "faults_of", "inject", "inject_set", "run", "main"]

if __name__ == "__main__":
    sys.exit(main())
