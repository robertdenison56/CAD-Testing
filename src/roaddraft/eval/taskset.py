"""Task sets (eval plan section 4.8): ``benchmarks/tasksets/<name>.json``
manifests, ``{"taskset", "generator_version", "spec_hash", "tasks": [{"seed",
"curves", "equations", "task_type", "sheets", "task_id"}]}``.

- ``d1-dev``: seeds 1-50, every dial mixed.  For iteration; never reported.
- ``d1-test``: seeds 1000-1099, held out, balanced over curves 1/2/3 and
  equations on/off, the task types and the sheet count cycling.  The
  leaderboard set.
- ``d1-variance``: the first 20 tasks of ``d1-test``, for k = 5 sampling.
- ``d1-real``: 100 held-out tasks on the redrafted sample plan sheets
  (``examples/Exmple Plans/Redraft``), 25 from each of the four question
  groups of ``tasks.types.REAL_GROUPS`` (draft linework, letter alignment
  data, produce the sheet, notes and dimensions: the real-sheet counterpart of
  the probe board's tiers, decided 2026-10-24), the group's quota split as
  evenly as its types allow, drawn from the validated catalogue
  ``benchmarks/real_tasks/catalog.json`` (``scripts/real_tasks.py`` writes it).
  Within a type, every agency that has the type is drawn once before any is
  drawn again, then the sheet the set has used least.  Ranked beside
  ``d1-test``, with a column per group beside the blended score.  (Until
  2026-10-27 it was nine of each type, so two groups held 45 tasks and two
  held 9.)
- ``d1-real-dev``: 24 tasks, two of each real type, on a few Caltrans sheets
  that ``d1-real`` never uses.  For smoke runs and iteration, so it covers
  every type rather than balancing the groups; never reported.
- ``d1-test-hard`` (2026-11-03): 100 held-out seeds 2000-2099, whole-sheet
  jobs only (``plan-sheet``, ``annotate-base`` and the three
  ``tasks.types.HARD_TASK_TYPES``: the plan sheet with its pavement edges and
  width dimensions, the alignment created from the stated geometry and then
  the sheet, and the sheet file laid out and lettered through its base
  drawing), at three to five curves on two or three sheets, one task in five
  with a station equation (``hard_equation``; every one had one until
  2026-11-03, when Robert found equations too uncommon in practice to be the
  set's focus).  Its own board.
- ``d1-real-hard`` (2026-11-03): every whole job on the redrafted sheets
  (``tasks.types.REAL_JOB_TYPES``: a sheet drafted from its base files, or a
  blank sheet annotated, with its construction callouts as well) off the dev
  sheets, from ``benchmarks/real_tasks/catalog-jobs.json``, then the heaviest
  tasks of the three types that letter a whole line that ``d1-real`` did not
  draw, to 100.  Its own board.
- ``hard-pilots``: the harder-task pilots (33 until 2026-11-03, 112 since) (``probes/pilot``, all of them),
  run as probe tasks (``eval/probe_tasks.py``): each its own start project on a
  sample sheet, the MCP server's tools, graded pass or fail by its own check.
  Ranked on its own board.  Too few instances per family to spare a dev split.
- ``pilot-dev`` (2026-11-13, ``RoadDraft_Training_Plan.md`` §8 and decision 7):
  that dev split, built apart: instances of the ``p17``, ``p04``, ``p05`` and
  ``p11`` families on the nine sample sheets no pilot, no real-sheet set and no
  dev set uses (``probes/pilot_dev.py``, outside the pilot package, so the
  held-out set does not move).  Run like ``hard-pilots``; for choosing a
  checkpoint only, like ``d1-real-dev``: never trained on, not on the board.

- ``d1-train``, ``d1-train-hard`` (2026-11-10, ``RoadDraft_Training_Plan.md``):
  the training sets, seeds 10000-11199 on ``d1-test``'s dials and seeds
  12000-12299 on ``d1-test-hard``'s.  What a training set is built from:
  reference trajectories, and rollouts sampled for rejection-sampling
  fine-tuning.  Not in ``NAMES``: no board ranks them and the default
  ``taskset`` check leaves them alone (name them to check or write them).
  ``train_overlap`` is the tripwire between them and every eval set.
- ``d1-train-twist`` (2026-11-11, Robert: "Twist dial first"): a third training
  set, seeds 13000-13599 on ``d1-test``'s dials, every sheet looked at through
  viewports turned the seed's own twist (``tasks.generator.seed_twist``), over
  the nine types whose work a twist changes (``TWIST_TYPES``).  The seeded
  counterpart of the twisted sample sheets (three ``d1-real`` tasks in four)
  and of the ``p17`` pilots, none of which can be trained on.  An entry
  carries ``"twist": true``; no other set's entry has the key.
- ``d1-train-crowd`` (2026-11-12, Robert: "Clearing step"): a fourth training
  set, seeds 14000-14599, every sheet handed over already worked on
  (``tasks.crowd``): a second lettered line across the first and a note or two
  on the paper, on the default poses of labels the task asks for.  Over the
  five types that letter the model on a sheet already set up (``CROWD_TYPES``),
  one sheet each, half of them through a turned viewport.  The seeded
  counterpart of the crowded pilots (``p04``).  An entry carries
  ``"crowd": true``; a seed whose sheet cannot be crowded so that the reference
  clears it is left out and named under ``skipped_seeds``.
- ``d1-train-revise`` (2026-11-12, plan §8 build 4): a fifth training set, seeds
  15000-15599, every sheet handed over finished after the designer changed its
  design (``tasks.revise``): a curve's radius, a PI moved, or the line
  restationed, with notes on the paper that cite the line.  Over the two types
  that letter a whole line on a sheet set up (``REVISE_TYPES``), one sheet each,
  no station equation, half of them through a turned viewport.  The seeded
  counterpart of the redline pilots (``p11``).  An entry carries
  ``"revise": <kind>``; a seed its kind cannot revise takes the next kind and
  says so under ``dialed``.
- ``d1-train-twist-widths`` (2026-11-13, plan decision 9): a sixth training
  set, seeds 16000-16299, the three types that dimension the pavement width
  (``TWIST_WIDTH_TYPES``) through viewports turned the seed's own twist.  A
  dimension's text could not be set to read through a twist until
  ``place_dimension`` took ``view_rotation``; ``d1-train-twist`` was drawn
  before that and keeps its nine types and its ids.  The two types handed a
  sheet are on ``d1-test``'s dials and the whole plan on ``d1-test-hard``'s.
  An entry carries ``"twist": true``.
- ``d1-train-revise-base`` (2026-11-13, plan §6 decision 11's leftover): a seventh
  training set, seeds 18000-18299, the same three changes left for the drafter to make where the
  design lives, in the base drawing the sheet file references
  (``tasks.revise.BASE_KINDS``): the base drawing is handed over on the old
  design, and the episode's tool list gains ``open_document`` and
  ``reload_references``.  ``annotate-base`` only, one sheet, no station
  equation, every kind at every curve count, half through a turned viewport.
  An entry carries ``"revise": "base-<kind>"``.
- ``d1-train-breaks`` (2026-11-13, plan §6 decision 8): a training set of the
  one training-only type, ``plan-sheet-breaks`` (``tasks.breaks``), seeds
  17000-17299: the whole plan sheet job with the number of sheets and the
  breaks between them left to the drafter, graded by ``verify.breaks``.  Lines
  that take one, two or three sheets, one to four curves (three at most on
  three sheets), half of them through turned viewports, no station equation.
  The seeded counterpart of the sheet break pilots (``p05``).  A seed whose line the generator lays on more sheets
  than carry it takes another sheet count and says so under ``dialed``.

The prompt level is a run dimension, not a task-set one.  A test regenerates
each manifest and asserts identical task ids: a changed spec or generator
fails it, which is the tripwire; ``python -m roaddraft.eval taskset --write``
regenerates them once the change is meant.  For the real sets the tripwire
also rebuilds every task from the redrafted sheets and checks its id, and
fails when the catalogue was validated under another verifier: rebuild it with
``python scripts/real_tasks.py`` first, then write the manifests.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from roaddraft.tasks.brief import GENERATOR_VERSION, Task
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.types import (D1_REAL_GROUPS, HARD_TASK_TYPES, REAL_GROUPS, REAL_JOB_TYPES,
                                   REAL_TASK_TYPES, TASK_TYPES, real_group)

REPO = Path(__file__).resolve().parents[3]
TASKSETS_DIR = REPO / "benchmarks" / "tasksets"
#: the sets the seeded generator makes, one synthetic centerline per task
SEEDED_NAMES = ("d1-dev", "d1-test", "d1-variance")
#: the sets on the redrafted sample plan sheets
REAL_NAMES = ("d1-real", "d1-real-dev")
#: the sets of probe tasks, each graded by its probe's own check (eval/probe_tasks.py)
PROBE_NAMES = ("hard-pilots", "pilot-dev")
#: the harder sets (2026-11-03): whole-sheet jobs on the seeded generator, and the whole job
#: plus the heaviest whole-line tasks on the redrafted sheets; each ranked on its own board
HARD_NAMES = ("d1-test-hard", "d1-real-hard")
NAMES = SEEDED_NAMES + REAL_NAMES + PROBE_NAMES + HARD_NAMES
#: the validated real-sheet tasks the real sets are drawn from
REAL_CATALOG = REPO / "benchmarks" / "real_tasks" / "catalog.json"
#: the validated whole-job tasks (tasks.types.REAL_JOB_TYPES), ``d1-real-hard``'s own
#: (``scripts/real_tasks.py --jobs`` writes it)
JOB_CATALOG = REPO / "benchmarks" / "real_tasks" / "catalog-jobs.json"
#: ``d1-real-hard`` (2026-11-03): every whole job the catalogue holds off the dev sheets,
#: then the heaviest tasks of the three types that letter a whole line, as evenly as the
#: types allow, to this many
REAL_HARD_SIZE = 100
REAL_HARD_FILL = ("real-plan-sheet", "real-annotate-sheet", "real-alignment-data")
#: tasks of each question group (tasks.types.REAL_GROUPS) in d1-real, and of each
#: real type in d1-real-dev
REAL_PER_GROUP = 25
REAL_DEV_PER_TYPE = 2
#: the agency the dev sheets are taken from: the only one with sheets to spare
#: (WFL has 6 sheets, FDOT 3, CFL 1; every one of them stays in d1-real)
REAL_DEV_AGENCY = "Caltrans-PPM"
SEEDED_TYPES = tuple(sorted(TASK_TYPES))
CURVES = (1, 2, 3)
VARIANCE_SIZE = 20
#: ``d1-test-hard`` (2026-11-03): whole-sheet jobs only, on seeds no other set draws
HARD_SEEDS = range(2000, 2100)
HARD_SEEDED_TYPES = tuple(sorted(("plan-sheet", "annotate-base") + tuple(HARD_TASK_TYPES)))
HARD_CURVES = (3, 4, 5)
HARD_SHEETS = (2, 3)
#: the training sets (2026-11-10): seeded tasks on seeds no eval set draws, ``d1-train`` on
#: ``d1-test``'s dials and ``d1-train-hard`` on ``d1-test-hard``'s.  Kept out of ``NAMES``:
#: every set there is held out of training, and nothing here is ever run for a score.
TRAIN_NAMES = ("d1-train", "d1-train-hard", "d1-train-twist", "d1-train-crowd", "d1-train-revise",
               "d1-train-twist-widths", "d1-train-revise-base")
#: ... and the set of the training-only type (2026-11-13), last, on a line of its own so that
#: a name added to the tuple above merges without touching it
TRAIN_NAMES += ("d1-train-breaks",)
TRAIN_SEEDS = range(10000, 11200)
TRAIN_HARD_SEEDS = range(12000, 12300)
#: ``d1-train-twist`` (2026-11-11): twisted sheets on seeds of their own, over the seeded
#: types whose work a twist changes: the model lettering read through it, the north arrow
#: turned to north, the viewport laid out at it.  Left out: the three types with no sheet,
#: the two with width dimensions (when the set was drawn a dimension's text could not be
#: lettered through a twist; they are ``d1-train-twist-widths`` now, on seeds of their own,
#: so that no id here moves), and ``pavement-edges`` and ``attach-reference``, whose work
#: is the same on a twisted sheet
TRAIN_TWIST_SEEDS = range(13000, 13600)
TWIST_TYPES = tuple(sorted(("stationing", "bearings", "curve-callouts", "curve-table",
                            "title-block", "sheet-setup", "annotate-sheet", "plan-sheet",
                            "annotate-base")))


#: ``d1-train-crowd`` (2026-11-12): crowded sheets on seeds of their own, over the types
#: that letter the model on a sheet already set up (``tasks.crowd.CROWD_TYPES``)
TRAIN_CROWD_SEEDS = range(14000, 14600)
#: ``d1-train-revise`` (2026-11-12): finished sheets whose design has since changed, on seeds
#: of their own, over the types that letter a whole line on a sheet set up
TRAIN_REVISE_SEEDS = range(15000, 15600)
#: ``d1-train-twist-widths`` (2026-11-13): the types that dimension the pavement width, on
#: twisted sheets and seeds of their own (``place_dimension`` reads a dimension's text
#: through the viewport's twist since plan decision 9)
TRAIN_TWIST_WIDTH_SEEDS = range(16000, 16300)
TWIST_WIDTH_TYPES = ("pavement", "pavement-widths", "plan-sheet-pavement")
#: ``d1-train-revise-base`` (2026-11-13): the same changes, left for the drafter to make in
#: the base drawing that holds the design, on seeds of their own
TRAIN_REVISE_BASE_SEEDS = range(18000, 18300)
#: ``d1-train-breaks`` (2026-11-13): the sheet count and the breaks left to the drafter
#: (``tasks.breaks``), on seeds of their own
TRAIN_BREAKS_SEEDS = range(17000, 17300)
#: the sheet counts its lines are stretched for, in the order dialed: two tasks in five take
#: two sheets, two take three, one takes one (no break is a right answer too)
BREAKS_SHEETS = (2, 3, 2, 3, 1)
BREAKS_CURVES = (1, 2, 3, 4)


def dials(index: int) -> dict:
    """The dials of the ``index``-th task of a set: curves cycle 1, 2, 3;
    equations flip every three; the sheet count flips every six; the task
    type cycles through the seeded types."""
    return {"curves": CURVES[index % len(CURVES)],
            "equations": bool((index // len(CURVES)) % 2),
            "sheets": 1 + (index // (2 * len(CURVES))) % 2,
            "task_type": SEEDED_TYPES[index % len(SEEDED_TYPES)]}


def make_task(seed: int, curves: int, equations: bool, task_type: str, sheets: int,
              twist: bool = False, crowd: bool = False, revise=None) -> Task:
    return generate_task(seed, curves=curves, equations=equations, task_type=task_type,
                         sheets=sheets, twist=twist, crowd=crowd, revise=revise)


def revise_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-revise``: the kind of
    change cycling through its three, the type through its two every three
    tasks, the curve count every six and the twist every eighteen, so every
    kind meets every type, curve count and twist; one sheet, no equation."""
    from roaddraft.tasks.revise import KINDS, REVISE_TYPES
    return {"revise": KINDS[index % len(KINDS)],
            "task_type": REVISE_TYPES[(index // len(KINDS)) % len(REVISE_TYPES)],
            "curves": CURVES[(index // (len(KINDS) * len(REVISE_TYPES))) % len(CURVES)],
            "twist": bool((index // (len(KINDS) * len(REVISE_TYPES) * len(CURVES))) % 2),
            "equations": False, "sheets": 1}


def _revise_entry(seed: int, index: int) -> dict:
    """The ``index``-th entry of ``d1-train-revise``.  A kind of change the
    seed's line cannot take takes the next kind; ``RuntimeError`` when none can."""
    from roaddraft.tasks.revise import KINDS
    d = revise_dials(index)
    start = KINDS.index(d["revise"])
    for k in range(len(KINDS)):
        kind = KINDS[(start + k) % len(KINDS)]
        try:
            task = make_task(seed, d["curves"], False, d["task_type"], 1, d["twist"],
                             revise=kind)
        except (ValueError, AssertionError):
            continue
        entry = {"seed": seed, "curves": d["curves"], "equations": False,
                 "task_type": d["task_type"], "sheets": 1, "task_id": task.task_id,
                 "revise": kind}
        if d["twist"]:
            entry["twist"] = True
        if kind != d["revise"]:
            entry["dialed"] = {"revise": d["revise"]}
        return entry
    raise RuntimeError(f"seed {seed}: no revised task generates")


def revise_base_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-revise-base``: the kind of
    change cycling through the three of ``tasks.revise.BASE_KINDS``, the curve
    count every three tasks and the twist every nine, so every kind meets every
    curve count both ways round; ``annotate-base``, one sheet, no equation."""
    from roaddraft.tasks.revise import BASE_KINDS
    return {"revise": BASE_KINDS[index % len(BASE_KINDS)], "task_type": "annotate-base",
            "curves": CURVES[(index // len(BASE_KINDS)) % len(CURVES)],
            "twist": bool((index // (len(BASE_KINDS) * len(CURVES))) % 2),
            "equations": False, "sheets": 1}


def _revise_base_entry(seed: int, index: int) -> dict:
    """The ``index``-th entry of ``d1-train-revise-base``.  A kind of change the
    seed's line cannot take takes the next kind; ``RuntimeError`` when none can."""
    from roaddraft.tasks.revise import BASE_KINDS
    d = revise_base_dials(index)
    start = BASE_KINDS.index(d["revise"])
    for k in range(len(BASE_KINDS)):
        kind = BASE_KINDS[(start + k) % len(BASE_KINDS)]
        try:
            task = make_task(seed, d["curves"], False, d["task_type"], 1, d["twist"],
                             revise=kind)
        except (ValueError, AssertionError):
            continue
        entry = {"seed": seed, "curves": d["curves"], "equations": False,
                 "task_type": d["task_type"], "sheets": 1, "task_id": task.task_id,
                 "revise": kind}
        if d["twist"]:
            entry["twist"] = True
        if kind != d["revise"]:
            entry["dialed"] = {"revise": d["revise"]}
        return entry
    raise RuntimeError(f"seed {seed}: no revised task generates")


def breaks_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-breaks``: the sheet
    count the line is stretched for cycling through ``BREAKS_SHEETS`` and the
    curve count through ``BREAKS_CURVES`` (five and four share no factor, so
    every sheet count draws every curve count), the viewports turned on every
    other round of the curve counts (so every sheet count meets every curve
    count both ways round); no station equation.  A line for three sheets
    carries three curves at most: the whole plan of four curves on three sheets
    takes the grounded drafter up to 149 of an episode's 150 calls."""
    from roaddraft.tasks.breaks import TYPE
    sheets = BREAKS_SHEETS[index % len(BREAKS_SHEETS)]
    curves = BREAKS_CURVES[index % len(BREAKS_CURVES)]
    return {"sheets": sheets, "curves": min(curves, 3) if sheets == 3 else curves,
            "twist": bool((index // len(BREAKS_CURVES)) % 2),
            "equations": False, "task_type": TYPE}


def _breaks_entry(seed: int, index: int) -> dict:
    """The ``index``-th entry of ``d1-train-breaks``.  A line the generator
    cannot lay on the sheets dialed, or lays on more sheets than carry it (its
    own breaks would then fail the count, ``tasks.breaks.opened``), takes the
    next sheet count down, then the ones above; ``RuntimeError`` when none does."""
    d = breaks_dials(index)
    counts = sorted(set(BREAKS_SHEETS))
    order = [d["sheets"]] + [n for n in reversed(counts) if n < d["sheets"]] + [
        n for n in counts if n > d["sheets"]]
    for sheets in order:
        if sheets == 3 and d["curves"] > 3:
            continue  # (the budget: see breaks_dials)
        try:
            task = make_task(seed, d["curves"], False, d["task_type"], sheets, d["twist"])
        except (ValueError, AssertionError):
            continue
        entry = {"seed": seed, "curves": d["curves"], "equations": False,
                 "task_type": d["task_type"], "sheets": sheets, "task_id": task.task_id}
        if d["twist"]:
            entry["twist"] = True
        if sheets != d["sheets"]:
            entry["dialed"] = {"sheets": d["sheets"]}
        return entry
    raise RuntimeError(f"seed {seed}: no {d['task_type']} task generates")


def crowd_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-crowd``: one sheet, the
    type cycling through the five crowded types and the curve count through
    its three (five and three share no factor, so every type draws every
    count), the equation flipping every three, and the viewport turned on
    every other round of the types."""
    from roaddraft.tasks.crowd import CROWD_TYPES
    return {"curves": CURVES[index % len(CURVES)],
            "equations": bool((index // len(CURVES)) % 2), "sheets": 1,
            "task_type": CROWD_TYPES[index % len(CROWD_TYPES)],
            "twist": bool((index // len(CROWD_TYPES)) % 2)}


def _crowd_entry(seed: int, index: int) -> dict:
    """The ``index``-th entry of ``d1-train-crowd``.  A type the seed's sheet
    cannot be crowded for takes the next in the cycle; ``RuntimeError`` when
    none can."""
    from roaddraft.tasks.crowd import CROWD_TYPES
    d = crowd_dials(index)
    start = CROWD_TYPES.index(d["task_type"])
    for k in range(len(CROWD_TYPES)):
        ttype = CROWD_TYPES[(start + k) % len(CROWD_TYPES)]
        try:
            task = make_task(seed, d["curves"], d["equations"], ttype, 1, d["twist"], crowd=True)
        except (ValueError, AssertionError):
            continue
        entry = {"seed": seed, "curves": d["curves"], "equations": d["equations"],
                 "task_type": ttype, "sheets": 1, "task_id": task.task_id, "crowd": True}
        if d["twist"]:
            entry["twist"] = True
        if ttype != d["task_type"]:
            entry["dialed"] = {"task_type": d["task_type"], "sheets": 1}
        return entry
    raise RuntimeError(f"seed {seed}: no crowded task generates")


def twist_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-twist``: ``d1-test``'s,
    with the type cycling through ``TWIST_TYPES``.  That cycle is nine long and
    the curve counts' three, so the curve count steps on one each time round
    the types, or a type would always draw the same number of curves."""
    d = dials(index)
    d["task_type"] = TWIST_TYPES[index % len(TWIST_TYPES)]
    d["curves"] = CURVES[(index + index // len(TWIST_TYPES)) % len(CURVES)]
    return d


def twist_width_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-train-twist-widths``: the type
    cycles through ``TWIST_WIDTH_TYPES``, and each turn of the types steps the
    rest.  The two types handed a sheet take ``d1-test``'s dials (curves 1, 2,
    3; an equation every other three turns; one sheet or two, flipping every
    six) and the whole plan ``d1-test-hard``'s (curves 3, 4, 5; two sheets or
    three, flipping every three turns; an equation on one turn in five)."""
    ttype = TWIST_WIDTH_TYPES[index % len(TWIST_WIDTH_TYPES)]
    turn = index // len(TWIST_WIDTH_TYPES)
    if ttype in HARD_TASK_TYPES:
        return {"curves": HARD_CURVES[turn % len(HARD_CURVES)], "equations": hard_equation(turn),
                "sheets": HARD_SHEETS[(turn // len(HARD_CURVES)) % len(HARD_SHEETS)],
                "task_type": ttype}
    return {"curves": CURVES[turn % len(CURVES)], "equations": bool((turn // len(CURVES)) % 2),
            "sheets": 1 + (turn // (2 * len(CURVES))) % 2, "task_type": ttype}


def _twist_width_entry(seed: int, index: int) -> dict:
    """The ``index``-th entry of ``d1-train-twist-widths``.  A seed the
    generator cannot lay out on the dialed sheets takes the type's other count
    (one sheet, or three for the whole plan), and the entry says so;
    ``RuntimeError`` when it has no tangent long enough to dimension either
    way (the seed is then left out, as ``d1-train-hard`` leaves one)."""
    d = twist_width_dials(index)
    other = 3 if d["task_type"] in HARD_TASK_TYPES else 1
    for sheets in ((d["sheets"], other) if d["sheets"] != other else (other,)):
        try:
            task = make_task(seed, d["curves"], d["equations"], d["task_type"], sheets, True)
        except (ValueError, AssertionError):
            continue
        entry = {"seed": seed, "curves": d["curves"], "equations": d["equations"],
                 "task_type": d["task_type"], "sheets": sheets, "task_id": task.task_id,
                 "twist": True}
        if sheets != d["sheets"]:
            entry["dialed"] = {"task_type": d["task_type"], "sheets": d["sheets"]}
        return entry
    raise RuntimeError(f"seed {seed}: no twisted width task generates")


def _entry(seed: int, index: int, twist: bool = False) -> dict:
    """The ``index``-th entry of a set on ``d1-test``'s dials; ``twist`` for a
    twisted task on ``twist_dials`` (the entry then says so)."""
    d = twist_dials(index) if twist else dials(index)
    types = TWIST_TYPES if twist else SEEDED_TYPES
    # a type the seed cannot make (a widths task with no dimensionable tangent)
    # takes the next type in the cycle, so every seed stays in the set
    start = types.index(d["task_type"])
    # a seed the generator cannot lay out on two sheets (its own assertion) takes
    # one sheet, so every seed stays in the set; the entry records the fallback
    for sheets in ((d["sheets"], 1) if d["sheets"] != 1 else (1,)):
        for k in range(len(types)):
            ttype = types[(start + k) % len(types)]
            try:
                task = make_task(seed, d["curves"], d["equations"], ttype, sheets, twist)
            except ValueError:
                continue
            except AssertionError:
                break
            entry = {"seed": seed, "curves": d["curves"], "equations": d["equations"],
                     "task_type": ttype, "sheets": sheets, "task_id": task.task_id}
            if twist:
                entry["twist"] = True
            if ttype != d["task_type"] or sheets != d["sheets"]:
                entry["dialed"] = {"task_type": d["task_type"], "sheets": d["sheets"]}
            return entry
    raise RuntimeError(f"seed {seed}: no task type generates")


#: One task in each block of five carries a station equation, the slot stepping
#: on by two a block (indices 0, 7, 14, 16, 23, 25, ...): the twenty equation
#: tasks of ``d1-test-hard`` then fall on every type four times, on the curve
#: counts 6/7/7 and the sheet counts 11/9, where a fixed slot would be one type
#: (the type cycle is five long too).  Every task had one until 2026-11-03
#: (Robert: station equations are not that common, so not the set's focus).
HARD_EQUATION_EVERY = 5


def hard_equation(index: int) -> bool:
    """Whether the ``index``-th task of ``d1-test-hard`` has a station equation."""
    block, slot = divmod(index, HARD_EQUATION_EVERY)
    return slot == (2 * block) % HARD_EQUATION_EVERY


def hard_dials(index: int) -> dict:
    """The dials of the ``index``-th task of ``d1-test-hard``: curves cycle 3, 4,
    5; two sheets or three, flipping every three; a station equation on one
    task in five (``hard_equation``); the type cycles through
    ``HARD_SEEDED_TYPES``, every one a whole sheet."""
    return {"curves": HARD_CURVES[index % len(HARD_CURVES)], "equations": hard_equation(index),
            "sheets": HARD_SHEETS[(index // len(HARD_CURVES)) % len(HARD_SHEETS)],
            "task_type": HARD_SEEDED_TYPES[index % len(HARD_SEEDED_TYPES)]}


def _hard_entry(seed: int, index: int) -> dict:
    d = hard_dials(index)
    start = HARD_SEEDED_TYPES.index(d["task_type"])
    # a seed the generator cannot lay out on two sheets (five curves often cannot keep a
    # match line clear of them) takes three; a type the seed cannot make (no tangent to
    # dimension) takes the next type; the entry records the fallback
    for sheets in ((d["sheets"], 3) if d["sheets"] != 3 else (3,)):
        for k in range(len(HARD_SEEDED_TYPES)):
            ttype = HARD_SEEDED_TYPES[(start + k) % len(HARD_SEEDED_TYPES)]
            try:
                task = make_task(seed, d["curves"], d["equations"], ttype, sheets)
            except ValueError:
                continue
            except AssertionError:
                break
            entry = {"seed": seed, "curves": d["curves"], "equations": d["equations"],
                     "task_type": ttype, "sheets": sheets, "task_id": task.task_id}
            if ttype != d["task_type"] or sheets != d["sheets"]:
                entry["dialed"] = {"task_type": d["task_type"], "sheets": d["sheets"]}
            return entry
    raise RuntimeError(f"seed {seed}: no hard task type generates")


def is_real(name: str) -> bool:
    """Whether ``name`` is a set on the redrafted sample sheets."""
    return name in REAL_NAMES or name == "d1-real-hard"


def is_probe(name: str) -> bool:
    """Whether ``name`` is a set of probe tasks."""
    return name in PROBE_NAMES


def current_generator(name: Optional[str]) -> str:
    """The generator version a run on ``name`` is held to: the seeded
    generator's, the real-sheet builder's, or the probe set's own hash."""
    if name is not None and is_real(name):
        from roaddraft.tasks.real import REAL_GENERATOR_VERSION
        return REAL_GENERATOR_VERSION
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.generator_version(probe_tasks.probes_of(name))
    return GENERATOR_VERSION


def current_verifier(name: Optional[str]) -> str:
    """The verifier version a run on ``name`` is held to: the D1 verifier's,
    or, for a probe set, the pilot checks' source hash
    (``probe_tasks.check_version``), since a pilot is graded by its own check."""
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.check_version(probe_tasks.check_sources(name))
    from roaddraft.verify import VERIFIER_VERSION
    return VERIFIER_VERSION


def default_budgets(name: Optional[str]):
    """The budgets a run on ``name`` takes when it sets none: Track P's for the
    probe tasks (eval/probe_tasks.BUDGETS), the harness's otherwise."""
    from roaddraft.eval.budget import Budgets
    if name is not None and is_probe(name):
        from roaddraft.eval import probe_tasks
        return probe_tasks.BUDGETS
    return Budgets()


def build_probes(name: str) -> dict:
    """A probe set's manifest: every pilot, in the brainstorm's order (``pilot-dev``:
    its instances, family by family, each with the sheet it is set on)."""
    from roaddraft.eval import probe_tasks
    if name not in probe_tasks.SETS:
        raise ValueError(f"unknown probe task set {name!r}; sets: {', '.join(PROBE_NAMES)}")
    probes = probe_tasks.probes_of(name)
    manifest = {"taskset": name, "generator_version": probe_tasks.generator_version(probes),
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1),
                "source": "src/roaddraft/probes/pilot (docs/Probes_Pilots.md)",
                "grading": "each probe's own check, pass = 100, fail = 0",
                "tasks": [probe_tasks.entry(p) for p in probes]}
    if name == probe_tasks.DEV_SET:
        from roaddraft.probes.pilot_dev import sheet_of
        manifest["source"] = ("src/roaddraft/probes/pilot_dev.py (the pilot families' builders "
                              "and checks on the clean sample sheets)")
        manifest["use"] = "checkpoint selection only: never trained on, never reported"
        for row in manifest["tasks"]:
            row["sheet_id"] = sheet_of(row["probe"])
    return manifest


def _h(text: str) -> str:
    """A fixed order that is not the catalogue's own (which runs sheet by sheet)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_catalog(path=None) -> dict:
    """The real-task catalogue (``scripts/real_tasks.py`` writes it)."""
    path = Path(path or REAL_CATALOG)
    if not path.exists():
        raise FileNotFoundError(f"no real-task catalogue at {path}; python scripts/real_tasks.py")
    return json.loads(path.read_text())


def real_dev_sheets(tasks: Sequence[dict]) -> List[str]:
    """The sheets ``d1-real-dev`` is drawn from: Caltrans sheets in a fixed
    hashed order, each one taken while it adds a type still short of
    ``REAL_DEV_PER_TYPE`` tasks, until every real type has that many.  No
    other sheet is in d1-real-dev, and none of these is in d1-real."""
    by_sheet: Dict[str, Counter] = {}
    for t in tasks:
        if t["agency"] == REAL_DEV_AGENCY:
            by_sheet.setdefault(t["sheet_id"], Counter())[t["type"]] += 1
    have: Counter = Counter()
    picked: List[str] = []
    for sheet in sorted(by_sheet, key=_h):
        if all(have[ty] >= REAL_DEV_PER_TYPE for ty in REAL_TASK_TYPES):
            break
        if any(have[ty] < REAL_DEV_PER_TYPE for ty in by_sheet[sheet]):
            picked.append(sheet)
            have.update(by_sheet[sheet])
    short = [ty for ty in REAL_TASK_TYPES if have[ty] < REAL_DEV_PER_TYPE]
    if short:
        raise RuntimeError(f"the {REAL_DEV_AGENCY} sheets cannot give {REAL_DEV_PER_TYPE} tasks "
                           f"of {', '.join(short)}")
    return sorted(picked)


def real_quotas(per_group: int = REAL_PER_GROUP) -> Dict[str, int]:
    """How many tasks of each real type ``d1-real`` draws: ``per_group`` for
    every question group that has types (``REAL_GROUPS``), split as evenly as
    the group's types allow, the first types of the group taking the
    remainder.  So the blended score weighs every question type the same,
    whatever the number of types each holds, and a type added to a group
    shares the group's quota rather than growing the set."""
    quotas: Dict[str, int] = {}
    for key, _, types in REAL_GROUPS:
        if not types or key not in D1_REAL_GROUPS:  # the whole job is d1-real-hard's
            continue
        base, extra = divmod(per_group, len(types))
        for i, ty in enumerate(types):
            quotas[ty] = base + (1 if i < extra else 0)
    return {ty: quotas[ty] for ty in REAL_TASK_TYPES if ty in quotas}


def _pick(pool: Sequence[dict], quotas: Dict[str, int]) -> List[dict]:
    """``quotas[type]`` tasks of each real type from ``pool``, picked round by
    round over the types in ``REAL_TASK_TYPES`` order (every type still owed
    a task gets one before any type gets its next).  Within a type, an agency
    the type has not drawn yet comes first, then the sheet the set has used
    least so far, then the hashed task id.  So a set holds every agency's
    sheets wherever the agency has the type, and spreads over sheets instead
    of taking one sheet's whole catalogue."""
    by_type = {ty: sorted((t for t in pool if t["type"] == ty), key=lambda t: _h(t["task_id"]))
               for ty in REAL_TASK_TYPES}
    for ty, rows in by_type.items():
        if len(rows) < quotas.get(ty, 0):
            raise RuntimeError(f"{ty}: {len(rows)} tasks to draw from, {quotas[ty]} wanted")
    used_sheet: Counter = Counter()
    used_agency = {ty: Counter() for ty in REAL_TASK_TYPES}
    taken = set()
    out: List[dict] = []
    for round_ in range(max(quotas.values(), default=0)):
        for ty in REAL_TASK_TYPES:
            if round_ >= quotas.get(ty, 0):
                continue
            best = min((t for t in by_type[ty] if t["task_id"] not in taken),
                       key=lambda t: (min(used_agency[ty][t["agency"]], 1),
                                      used_sheet[t["sheet_id"]], _h(t["task_id"])))
            taken.add(best["task_id"])
            used_sheet[best["sheet_id"]] += 1
            used_agency[ty][best["agency"]] += 1
            out.append(best)
    return out


def _real_entry(t: dict) -> dict:
    return {"agency": t["agency"], "sheet_id": t["sheet_id"], "sheet": t["sheet"],
            "alignment": t["alignment"], "task_type": t["type"], "group": real_group(t["type"]),
            "sheets": 1, "feet_per_inch": t["feet_per_inch"], "twist_deg": t["twist_deg"],
            "task_id": t["task_id"]}


def _pick_heavy(pool: Sequence[dict], quotas: Dict[str, int]) -> List[dict]:
    """``quotas[type]`` tasks of each type from ``pool``, round by round over
    the types, each pick from an agency the type has not drawn yet, then the
    sheet the set has used least, then the heaviest task (most labels, then
    curves), then the hashed id."""
    by_type = {ty: [t for t in pool if t["type"] == ty] for ty in quotas}
    for ty, rows in by_type.items():
        if len(rows) < quotas[ty]:
            raise RuntimeError(f"{ty}: {len(rows)} tasks to draw from, {quotas[ty]} wanted")
    used_sheet: Counter = Counter()
    used_agency = {ty: Counter() for ty in quotas}
    taken = set()
    out: List[dict] = []
    for round_ in range(max(quotas.values(), default=0)):
        for ty in quotas:
            if round_ >= quotas[ty]:
                continue
            best = min((t for t in by_type[ty] if t["task_id"] not in taken),
                       key=lambda t: (min(used_agency[ty][t["agency"]], 1),
                                      used_sheet[t["sheet_id"]], -t.get("labels", 0),
                                      -t.get("curves", 0), _h(t["task_id"])))
            taken.add(best["task_id"])
            used_sheet[best["sheet_id"]] += 1
            used_agency[ty][best["agency"]] += 1
            out.append(best)
    return out


def build_real_hard(catalog_path=None, jobs_path=None) -> dict:
    """``d1-real-hard``: every whole job (``REAL_JOB_TYPES``) off the dev sheets,
    then the heaviest whole-line tasks ``d1-real`` did not draw, to
    ``REAL_HARD_SIZE``."""
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    cat = load_catalog(catalog_path)
    jobs = load_catalog(jobs_path or JOB_CATALOG)
    dev = set(real_dev_sheets(cat["tasks"]))
    taken = {t["task_id"] for t in build_real("d1-real", catalog_path)["tasks"]}
    whole = sorted((t for t in jobs["tasks"] if t["sheet_id"] not in dev),
                   key=lambda t: (t["type"], t["sheet_id"], t["alignment"]))
    left = REAL_HARD_SIZE - len(whole)
    base, extra = divmod(max(left, 0), len(REAL_HARD_FILL))
    quotas = {ty: base + (1 if i < extra else 0) for i, ty in enumerate(REAL_HARD_FILL)}
    pool = [t for t in cat["tasks"] if t["sheet_id"] not in dev and t["task_id"] not in taken]
    entries = [_real_entry(t) for t in whole + _pick_heavy(pool, quotas)]
    groups = Counter(e["group"] for e in entries)
    return {"taskset": "d1-real-hard", "generator_version": REAL_GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "source": "benchmarks/real_tasks/catalog-jobs.json + catalog.json",
            "catalog_verifier": cat.get("verifier_version"),
            "jobs_verifier": jobs.get("verifier_version"),
            "groups": {key: groups[key] for key, _, _ in REAL_GROUPS if groups[key]},
            "tasks": entries}


def build_real(name: str, catalog_path=None) -> dict:
    """A real set's manifest, drawn from the catalogue."""
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    cat = load_catalog(catalog_path)
    tasks = cat["tasks"]
    dev = set(real_dev_sheets(tasks))
    if name == "d1-real":
        chosen = _pick([t for t in tasks if t["sheet_id"] not in dev], real_quotas())
    elif name == "d1-real-hard":
        return build_real_hard(catalog_path)
    elif name == "d1-real-dev":
        chosen = _pick([t for t in tasks if t["sheet_id"] in dev],
                       {ty: REAL_DEV_PER_TYPE for ty in REAL_TASK_TYPES})
    else:
        raise ValueError(f"unknown real task set {name!r}; sets: "
                         f"{', '.join(REAL_NAMES + ('d1-real-hard',))}")
    entries = [_real_entry(t) for t in chosen]
    groups = Counter(e["group"] for e in entries)
    return {"taskset": name, "generator_version": REAL_GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "source": "benchmarks/real_tasks/catalog.json",
            "catalog_verifier": cat.get("verifier_version"),
            "groups": {key: groups[key] for key, _, _ in REAL_GROUPS if groups[key]},
            "tasks": entries}


def build(name: str) -> dict:
    """Generate a manifest."""
    if is_real(name):
        return build_real(name)
    if is_probe(name):
        return build_probes(name)
    if name == "d1-dev":
        seeds = range(1, 51)
    elif name == "d1-test":
        seeds = range(1000, 1100)
    elif name == "d1-variance":
        manifest = build("d1-test")
        return {**manifest, "taskset": name, "parent": "d1-test",
                "tasks": manifest["tasks"][:VARIANCE_SIZE]}
    elif name == "d1-train":
        seeds = TRAIN_SEEDS
    elif name == "d1-train-twist":
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1),
                "tasks": [_entry(seed, i, twist=True)
                          for i, seed in enumerate(TRAIN_TWIST_SEEDS)]}
    elif name == "d1-train-crowd":
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_CROWD_SEEDS):
            try:
                tasks.append(_crowd_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    elif name == "d1-train-revise":
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_REVISE_SEEDS):
            try:
                tasks.append(_revise_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    elif name == "d1-train-twist-widths":
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_TWIST_WIDTH_SEEDS):
            try:
                tasks.append(_twist_width_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    elif name == "d1-train-revise-base":
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_REVISE_BASE_SEEDS):
            try:
                tasks.append(_revise_base_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    elif name == "d1-test-hard":
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1),
                "tasks": [_hard_entry(seed, i) for i, seed in enumerate(HARD_SEEDS)]}
    elif name == "d1-train-hard":
        # a seed no hard type lays out is left out (a held-out set keeps every seed; a
        # training set need not), its place in the dial cycle with it, and named in the manifest
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_HARD_SEEDS):
            try:
                tasks.append(_hard_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    elif name == "d1-train-breaks":
        # (a seed no sheet count makes a task of is left out and named, as above)
        tasks, skipped = [], []
        for i, seed in enumerate(TRAIN_BREAKS_SEEDS):
            try:
                tasks.append(_breaks_entry(seed, i))
            except RuntimeError:
                skipped.append(seed)
        return {"taskset": name, "generator_version": GENERATOR_VERSION,
                "spec_version": DRAFTING_SPEC_V1["version"],
                "spec_hash": spec_hash(DRAFTING_SPEC_V1), "skipped_seeds": skipped,
                "tasks": tasks}
    else:
        raise ValueError(f"unknown task set {name!r}; sets: {', '.join(NAMES + TRAIN_NAMES)}")
    tasks = [_entry(seed, i) for i, seed in enumerate(seeds)]
    return {"taskset": name, "generator_version": GENERATOR_VERSION,
            "spec_version": DRAFTING_SPEC_V1["version"], "spec_hash": spec_hash(DRAFTING_SPEC_V1),
            "tasks": tasks}


def manifest_path(name: str, root=None) -> Path:
    return Path(root or TASKSETS_DIR) / f"{name}.json"


def write(name: str, root=None) -> Path:
    path = manifest_path(name, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(name), indent=1) + "\n")
    return path


def load(name: str, root=None) -> dict:
    path = manifest_path(name, root)
    if not path.exists():
        raise FileNotFoundError(f"no manifest for task set {name!r} at {path}; "
                                f"python -m roaddraft.eval taskset --write {name}")
    return json.loads(path.read_text())


def check(name: str, root=None) -> List[str]:
    """Differences between the committed manifest and a fresh build: empty
    when the spec and generator are the ones the manifest was written on."""
    saved, fresh = load(name, root), build(name)
    problems: List[str] = []
    keys = ("generator_version", "spec_hash") + (("catalog_verifier",) if is_real(name) else ()) \
        + (("jobs_verifier",) if name == "d1-real-hard" else ())
    for key in keys:
        if saved.get(key) != fresh.get(key):
            problems.append(f"{key}: manifest {saved.get(key)} != current {fresh.get(key)}")
    saved_ids = [t["task_id"] for t in saved["tasks"]]
    fresh_ids = [t["task_id"] for t in fresh["tasks"]]
    if saved_ids != fresh_ids:
        changed = sum(1 for a, b in zip(saved_ids, fresh_ids) if a != b) + abs(len(saved_ids) - len(fresh_ids))
        problems.append(f"task ids: {changed} of {len(fresh_ids)} differ")
    # a probe set's vague ids too (2026-11-08): each carries the hash of its vague brief
    saved_v = [t.get("vague_task_id") for t in saved["tasks"]]
    fresh_v = [t.get("vague_task_id") for t in fresh["tasks"]]
    if saved_v != fresh_v:
        changed = sum(1 for a, b in zip(saved_v, fresh_v) if a != b) + abs(len(saved_v) - len(fresh_v))
        problems.append(f"vague task ids: {changed} of {len(fresh_v)} differ")
    if is_real(name):
        problems += _check_real(saved)
    return problems


def _check_real(saved: dict) -> List[str]:
    """A real set's own tripwire: the catalogue it was drawn from is current
    (its generator, spec and the verifier it was validated under), and every
    task still builds to its id from the redrafted sheets."""
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    from roaddraft.verify import VERIFIER_VERSION
    problems: List[str] = []
    catalogues = [(load_catalog(), "python scripts/real_tasks.py")]
    if saved.get("taskset") == "d1-real-hard":
        catalogues.append((load_catalog(JOB_CATALOG), "python scripts/real_tasks.py --jobs"))
    for cat, how in catalogues:
        for key, now in (("generator_version", REAL_GENERATOR_VERSION),
                         ("spec_hash", spec_hash(DRAFTING_SPEC_V1)),
                         ("verifier_version", VERIFIER_VERSION)):
            if cat.get(key) != now:
                problems.append(f"the catalogue's {key} is {cat.get(key)}, current {now}: rebuild "
                                f"it ({how}), then write the manifests")
    broken = []
    for entry in saved["tasks"]:
        try:
            task_from_entry(entry)
        except ValueError as why:
            broken.append(f"{entry['task_type']} on {entry['sheet_id']} {entry['alignment']}: {why}")
    if broken:
        problems.append(f"{len(broken)} of {len(saved['tasks'])} tasks no longer build to their "
                        f"ids; first: {broken[0]}")
    return problems


def shared(train: dict, held_out: dict) -> List[str]:
    """What training manifest ``train`` shares with manifest ``held_out``: a
    task id, or a seed (two seeded tasks on one seed are one design, whatever
    their types).  A training set is seeded, so an entry of its own on a real
    sheet or a probe is reported too: every sample sheet and every pilot is in
    an eval set, and none can be trained on."""
    a, b = train.get("taskset"), held_out.get("taskset")
    problems = [f"{a}: {e.get('task_id')} is not a seeded task; a training set holds no real sheet "
                "and no probe" for e in train["tasks"] if "seed" not in e]
    ids = {e["task_id"] for e in train["tasks"]} | {e["vague_task_id"] for e in train["tasks"]
                                                    if e.get("vague_task_id")}
    theirs = {e["task_id"] for e in held_out["tasks"]} | {e["vague_task_id"]
                                                          for e in held_out["tasks"]
                                                          if e.get("vague_task_id")}
    both = sorted(ids & theirs)
    if both:
        problems.append(f"{a} and {b} share {len(both)} task id(s); first: {both[0]}")
    seeds = sorted({e["seed"] for e in train["tasks"] if "seed" in e}
                   & {e["seed"] for e in held_out["tasks"] if "seed" in e})
    if seeds:
        problems.append(f"{a} and {b} share {len(seeds)} seed(s); first: {seeds[0]}")
    return problems


def train_overlap(root=None) -> List[str]:
    """Everything a training set shares with an eval set or with the other
    training set, from the manifests on disk: empty when the training data is
    clean.  The tripwire the training plan rests on; a test holds it empty."""
    problems: List[str] = []
    trains = {name: load(name, root) for name in TRAIN_NAMES}
    for name, manifest in trains.items():
        for other in NAMES:
            problems += shared(manifest, load(other, root))
    names = list(trains)
    for i, first in enumerate(names):  # every pair of training sets, once
        for second in names[i + 1:]:
            problems += shared(trains[first], trains[second])
    return problems


def task_from_entry(entry: dict, strict: bool = True, level: str = "explicit") -> Task:
    """The task a manifest entry names; with ``strict`` its id must match.  A
    real-sheet entry (it names a ``sheet_id``) is rebuilt from the redrafted
    sheet by ``tasks.real.build_real_task``; a probe entry (it names a
    ``probe``) is a ``probe_tasks.ProbeTask``, not a ``Task``, posed at prompt
    ``level`` (a D1 task is the same at every level: the episode picks its prompt)."""
    if "probe" in entry:
        from roaddraft.eval import probe_tasks
        return probe_tasks.task_from_entry(entry, strict=strict, level=level)
    if "sheet_id" in entry:
        from roaddraft.tasks.real import build_real_task
        task = build_real_task(entry["sheet_id"], entry["alignment"], entry["task_type"])
        if strict and task.task_id != entry["task_id"]:
            raise ValueError(f"task id of {entry['task_type']} on {entry['sheet_id']} "
                             f"{entry['alignment']} is {task.task_id}, the manifest says "
                             f"{entry['task_id']}: the redrafts, spec or real generator changed; "
                             "rebuild the catalogue (python scripts/real_tasks.py), then "
                             "python -m roaddraft.eval taskset --write")
        return task
    task = make_task(entry["seed"], entry["curves"], entry["equations"], entry["task_type"],
                     entry["sheets"], bool(entry.get("twist")), bool(entry.get("crowd")),
                     entry.get("revise"))
    if strict and task.task_id != entry["task_id"]:
        raise ValueError(f"task id of seed {entry['seed']} ({entry['task_type']}, "
                         f"{entry['sheets']} sheet) is {task.task_id}, the manifest says "
                         f"{entry['task_id']}: the spec or generator changed; regenerate with "
                         "python -m roaddraft.eval taskset --write")
    return task


def entries(name: str, limit: Optional[int] = None, task_ids: Optional[Iterable[str]] = None,
            root=None) -> List[dict]:
    """The manifest's entries, filtered to ``task_ids`` and cut to ``limit``."""
    rows = load(name, root)["tasks"]
    if task_ids:
        wanted = set(task_ids)
        rows = [r for r in rows if r["task_id"] in wanted or r.get("vague_task_id") in wanted]
    if limit is not None:
        rows = rows[:limit]
    return rows


__all__ = ["NAMES", "SEEDED_NAMES", "REAL_NAMES", "REAL_CATALOG", "REAL_PER_GROUP",
           "REAL_DEV_PER_TYPE", "SEEDED_TYPES", "TASKSETS_DIR", "VARIANCE_SIZE", "dials",
           "make_task", "is_real", "is_probe", "current_generator", "current_verifier", "default_budgets",
           "build_probes", "PROBE_NAMES", "load_catalog", "real_dev_sheets", "real_quotas", "build_real", "build",
           "manifest_path", "write", "load", "check", "task_from_entry", "entries", "HARD_NAMES",
           "HARD_SEEDS", "HARD_SEEDED_TYPES", "hard_dials", "JOB_CATALOG", "REAL_HARD_SIZE",
           "REAL_HARD_FILL", "build_real_hard", "TRAIN_NAMES", "TRAIN_SEEDS", "TRAIN_HARD_SEEDS",
           "TRAIN_TWIST_SEEDS", "TWIST_TYPES", "twist_dials", "TRAIN_CROWD_SEEDS", "crowd_dials",
           "TRAIN_REVISE_SEEDS", "revise_dials", "TRAIN_TWIST_WIDTH_SEEDS", "TWIST_WIDTH_TYPES",
           "twist_width_dials", "TRAIN_REVISE_BASE_SEEDS", "revise_base_dials", "shared",
           "train_overlap", "TRAIN_BREAKS_SEEDS", "breaks_dials"]
