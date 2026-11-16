"""Training plan §8, the ``p13`` family as a training set (2026-11-15): generated
striping plans (``tasks.striping``) run as probe tasks on the pilots' harness and
graded by the pilots' own check, and their grounded drafter
(``trajectories.reasoning_striping``)."""
from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from roaddraft.eval import probe_tasks
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents.basic import NullAgent
from roaddraft.eval.episode import EpisodeConfig
from roaddraft.eval.probe_tasks import ProbeEpisode, ProbeOracleAgent
from roaddraft.probes.pilot import striping as p13
from roaddraft.tasks import striping
from roaddraft.trajectories import reasoning, reasoning_striping

NAME = "train-striping"
LEVELS = ("explicit", "vague")


def _rows() -> list:
    return tasksets.load(NAME)["tasks"]


def _row(seed: int) -> dict:
    return next(t for t in _rows() if t["seed"] == seed)


def _sample() -> list:
    """The first seed of every kind the set holds."""
    first = {}
    for t in _rows():
        first.setdefault(t["kind"], t["seed"])
    return sorted(first.values())


def _run(seed: int, agent, level: str, probe=None):
    task = tasksets.task_from_entry(_row(seed), level=level)
    if probe is not None:
        task = replace(task, probe=probe)
    return ProbeEpisode(task, agent, EpisodeConfig(level=level, budgets=probe_tasks.BUDGETS)).run()


# ------------------------------------------------------------ the set


def test_the_set_is_registered_beside_the_other_generated_sets_and_shares_nothing():
    assert NAME in tasksets.PROBE_TRAIN_NAMES
    assert NAME not in tasksets.NAMES + tasksets.TRAIN_NAMES
    assert tasksets.train_overlap() == []
    m = tasksets.load(NAME)
    assert m["harness"] == "probe"
    seeds = [t["seed"] for t in m["tasks"]]
    assert list(striping.SEEDS) == list(range(24000, 24300))
    assert seeds == [s for s in striping.SEEDS if s not in m["skipped_seeds"]]
    assert len(seeds) >= 0.9 * len(striping.SEEDS)
    assert all(t["generated"] == NAME and t["family"] == "p13" for t in m["tasks"])
    ids = [t["task_id"] for t in m["tasks"]] + [t["vague_task_id"] for t in m["tasks"]]
    assert len(set(ids)) == len(ids)
    from roaddraft.tasks import deeds, planted
    others = (set(tasksets.TRAIN_SEEDS) | set(tasksets.TRAIN_HARD_SEEDS)
              | set(tasksets.TRAIN_TWIST_SEEDS) | set(tasksets.TRAIN_CROWD_SEEDS)
              | set(tasksets.TRAIN_REVISE_SEEDS) | set(tasksets.TRAIN_TWIST_WIDTH_SEEDS)
              | set(tasksets.TRAIN_REVISE_BASE_SEEDS) | set(tasksets.TRAIN_BREAKS_SEEDS)
              | set(deeds.SEEDS) | set(planted.SEEDS))
    assert others.isdisjoint(striping.SEEDS)
    assert tasksets.default_budgets(NAME) == probe_tasks.BUDGETS


def test_the_set_covers_every_kind_and_what_the_pilots_vary():
    rows = _rows()
    kinds = {t["kind"] for t in rows}
    assert kinds == set(striping.KINDS)
    assert {t["mph"] for t in rows} == set(striping.SPEEDS)
    assert len({t["range"][1] - t["range"][0] for t in rows}) >= 4
    assert {t["curve"]["type"] for t in rows} == {"crest", "sag"}
    for t in rows:
        ra, rb = t["range"]
        up, down = t["zones_up"], t["zones_down"]
        want = {"up": (1, 0), "down": (0, 1), "both": (1, 1), "double": (1, 1),
                "gentle": (0, 0), "sag": (0, 0)}[t["kind"]]
        assert (len(up), len(down)) == want, t["seed"]
        overlap = any(min(b, d) - max(a, c) > 0.5 for a, b in up for c, d in down)
        assert overlap == (t["kind"] == "double"), t["seed"]
        cuts = sorted({ra, rb} | {v for z in up + down for v in z})
        assert min(b - a for a, b in zip(cuts, cuts[1:])) >= striping.MIN_PIECE, t["seed"]
    # a zone inside the range, one that runs on past its begin, and one past its end
    ends = {(z[0] > t["range"][0], z[1] < t["range"][1])
            for t in rows for z in t["zones_up"] + t["zones_down"]}
    assert {(True, True), (False, True), (True, False)} <= ends


def test_a_task_is_made_from_its_seed_alone():
    """Made twice, a seed gives the same line, profile, briefs, start and ids."""
    for seed in (24000, 24007):
        first = striping.striping_task(seed)
        start = json.dumps(striping._STARTS[seed], sort_keys=True)
        again = striping.striping_task.__wrapped__(seed)
        assert again.job == first.job and again.kind == first.kind
        assert (again.probe.prompt, again.probe.vague) == (first.probe.prompt, first.probe.vague)
        assert json.dumps(striping._STARTS[seed], sort_keys=True) == start
        assert [again.task_id(level) for level in LEVELS] == [first.task_id(level) for level in LEVELS]


def test_the_manifest_rebuilds_to_its_ids():
    """A sample; ``python -m roaddraft.eval taskset train-striping`` checks all."""
    for entry in _rows()[:4]:
        fresh = striping.entry(entry["seed"])
        assert fresh["task_id"] == entry["task_id"]
        assert fresh["vague_task_id"] == entry["vague_task_id"]
        for level in LEVELS:
            task = tasksets.task_from_entry(entry, level=level)
            assert task.task_id == (entry["task_id"] if level == "explicit"
                                    else entry["vague_task_id"])
            assert task.task_type == striping.TASK_TYPE


def test_the_briefs_are_the_pilots_less_the_sheet():
    t = striping.striping_task(24000)
    job = t.job
    assert t.probe.prompt == p13._prompt(job).replace(f" (sheet {job.sheet})", "")
    assert t.probe.vague == p13._vague(job).replace(f" (sheet {job.sheet})", "")
    assert "sheet" not in t.probe.prompt and "sheet" not in t.probe.vague
    assert "0.33" in t.probe.prompt and "0.33" not in t.probe.vague
    assert "per the MUTCD" in t.probe.vague and "Table 3B-1" not in t.probe.vague
    # the start: one file, the line, its profile, the two marking layers, no stripe
    from roaddraft.api.session import Session
    from roaddraft.document.document import Document
    start = Session(_document=Document.from_dict(striping._STARTS[24000]))
    assert list(start.doc.design.profiles) == [job.profile]
    assert {striping.YELLOW, striping.WHITE} <= set(start.doc.layers)
    assert not any(e.layer in (striping.YELLOW, striping.WHITE)
                   for e in start.doc.model_entities.values())
    assert "design_speed_mph" not in (start.doc.meta or {})


def test_the_set_carries_its_own_pins_and_nothing_joins_the_pilot_package():
    held = (probe_tasks.generator_version(probe_tasks.pilots()), probe_tasks.check_version())
    assert held == (tasksets.current_generator("hard-pilots"),
                    tasksets.current_verifier("hard-pilots"))
    probe = striping.striping_task(24000).probe
    assert probe_tasks.generated_set(probe.id) == NAME
    assert probe_tasks.by_id(probe.id) is probe
    generator, verifier = probe_tasks.pins_of(probe)
    assert generator == tasksets.load(NAME)["generator_version"] != held[0]
    assert verifier == tasksets.current_verifier(NAME) != held[1]
    assert verifier.startswith("pilot-check-")
    assert verifier not in {tasksets.current_verifier(n) for n in tasksets.PROBE_TRAIN_NAMES
                            if n != NAME}
    sources = probe_tasks.check_sources(NAME)
    assert sources[:-1] == probe_tasks.check_sources() and sources[-1].samefile(striping.__file__)
    pilots = {p.id for p in probe_tasks.pilots()}
    assert len(pilots) == 112 and not any(p.startswith("t13-") for p in pilots)
    assert len([p for p in pilots if p.startswith("p13-")]) == 6
    assert tasksets.check("hard-pilots") == []


def test_no_generated_plan_repeats_a_held_out_plan():
    """The six held-out striping pilots against all the generated: no PVI, no (range,
    speed) and no zone in common, and a generated plan is on no sheet."""
    held_pvis = {(round(p[0], 2), round(p[1], 2)) for job in p13.JOBS for p in job.pvis}
    held_jobs = {(job.ra, job.rb, job.mph) for job in p13.JOBS}
    held_zones = {(round(a), round(b)) for job in p13.JOBS for zs in p13.truth(job) for a, b in zs}
    held_names = {job.alignment for job in p13.JOBS} | {job.profile for job in p13.JOBS}
    assert len(held_jobs) == 6 and len(held_zones) >= 6
    rows = _rows()
    assert len(rows) == 300
    for row in rows:  # the manifest carries each plan's profile, range, speed and zones
        assert not {(round(p[0], 2), round(p[1], 2)) for p in row["pvis"]} & held_pvis, row["seed"]
        assert (row["range"][0], row["range"][1], row["mph"]) not in held_jobs, row["seed"]
        assert not {(round(a), round(b)) for a, b in row["zones_up"] + row["zones_down"]} \
            & held_zones, row["seed"]
        assert row["profile"] not in held_names
    for seed in _sample():  # and the manifest's rows are the tasks'
        t, row = striping.striping_task(seed), _row(seed)
        assert t.job.redraft == "" and t.job.refs == ()
        assert [list(p) for p in t.job.pvis] == row["pvis"] and t.job.profile == row["profile"]
        assert [t.job.ra, t.job.rb, t.job.mph] == row["range"] + [row["mph"]]
        assert [list(z) for z in t.up] == row["zones_up"]
        assert not {t.job.alignment, t.job.profile} & held_names


# ------------------------------------------------------------ the zones by hand


def test_the_closed_form_is_the_pilots_sweep_on_a_crest_standing_alone():
    for g1, g2, length, mph in ((1.0, -3.0, 400.0, 55), (4.5, -0.2, 150.0, 70),
                                (5.9, -6.3, 500.0, 50), (6.0, -2.0, 800.0, 40)):
        psd = float(p13.MUTCD_PSD[mph])
        pvis = ((0.0, 500.0), (5000.0, 500.0 + 50.0 * g1, length),
                (10000.0, 500.0 + 50.0 * g1 + 50.0 * g2))
        up, down = p13.zones(pvis, psd, 2000.0, 8000.0)
        by_hand = striping.closed_form(5000.0 - length / 2, 5000.0 + length / 2, g1 - g2, psd,
                                       2000.0, 8000.0)
        assert [len(z) for z in by_hand] == [len(up), len(down)] == [1, 1]
        for mine, theirs in zip(by_hand, (up, down)):
            assert all(abs(x - y) <= 2.0 for x, y in zip(mine[0], theirs[0]))
    # a crest with sight distance to spare restricts nothing, by hand and by the sweep
    assert striping.reach(1.2, 650.0, 600.0) is None
    pvis = ((0.0, 500.0), (5000.0, 425.0, 650.0), (10000.0, 290.0))
    assert p13.zones(pvis, 600.0, 2000.0, 8000.0) == ([], [])


# ------------------------------------------------------------ the check


@pytest.mark.parametrize("level", LEVELS)
def test_the_oracle_passes_and_the_untouched_start_fails_on_every_kind(level):
    for seed in _sample():
        assert _run(seed, ProbeOracleAgent(), level).effective_score == 100.0, seed
        assert _run(seed, NullAgent(), level).effective_score == 0.0, seed


def _naive(t, name: str, **how):
    return replace(t.probe, id=f"{t.probe.id}-{name}",  # the oracle's cache is by id
                   solve=lambda s, job=t.job: p13.solve_job(job, s, **how))


def test_the_naive_answers_fail_as_they_fail_the_pilots():
    """The solid on the wrong side; double yellow from PVC to PVT; no zone at all; and,
    on a crest that restricts nothing, a zone over it."""
    rows = {t["kind"]: t for t in reversed(_rows())}
    for kind in ("up", "both"):
        t = striping.striping_task(rows[kind]["seed"])
        assert _run(t.seed, ProbeOracleAgent(), "vague", _naive(t, "swap", swap=True)
                    ).effective_score == 0.0
        assert _run(t.seed, ProbeOracleAgent(), "vague", _naive(t, "none", up=[], down=[])
                    ).effective_score == 0.0
        facts = dict(t.facts)
        over = [(max(facts["pvc"], t.job.ra), min(facts["pvt"], t.job.rb))]
        if over[0][1] - over[0][0] > 60.0:
            assert _run(t.seed, ProbeOracleAgent(), "vague", _naive(t, "pvc-pvt", up=over, down=over)
                        ).effective_score == 0.0
    t = striping.striping_task(rows["gentle"]["seed"])
    facts = dict(t.facts)
    over = [(max(facts["pvc"], t.job.ra), min(facts["pvt"], t.job.rb))]
    result = _run(t.seed, ProbeOracleAgent(), "explicit", _naive(t, "crest", up=over, down=over))
    assert result.effective_score == 0.0 and "nowhere on this range" in result.report.detail


# ------------------------------------------------------------ the drafter


@pytest.mark.parametrize("level", LEVELS)
def test_the_grounded_drafter_stripes_every_kind_and_is_kept(level, tmp_path):
    for seed in _sample():
        task = tasksets.task_from_entry(_row(seed), level=level)
        row = reasoning.record_task(task, level, out_root=tmp_path)
        assert row["kept"], row
        assert row["ungrounded"] == [] and row["termination"] == "submit"


def test_the_recorder_runs_on_the_pilots_budgets(tmp_path):
    task = tasksets.task_from_entry(_row(24000), level="vague")
    row = reasoning.record_task(task, "vague", out_root=tmp_path)
    assert row["kept"], row
    with open(row["path"]) as f:
        header = json.loads(f.readline())
    assert header["budgets"] == probe_tasks.BUDGETS.for_mode("single").to_dict()
    assert header["verifier_version"] == tasksets.current_verifier(NAME)
    assert header["task_type"] == striping.TASK_TYPE


def test_the_drafter_queries_first_and_works_the_zones_out_in_the_shown_work():
    task = tasksets.task_from_entry(_row(24000), level="vague")
    episode = ProbeEpisode(task, reasoning.ReasoningAgent(), EpisodeConfig(level="vague"))
    episode.run()
    turns = episode.turns
    first = [c["name"] for c in turns[0]["assistant"]["tool_calls"]]
    assert set(first) <= {"get_design_data", "list_layers"} and "get_design_data" in first
    drawn = [c["name"] for t in turns[1:] for c in t["assistant"]["tool_calls"]]
    assert drawn[0] == "draw_offset" and "array_entities" in drawn and drawn[-1] == "submit"
    work = turns[1]["assistant"]["text"]
    assert "sqrt(" in work and " = " in work
    assert reasoning.audit(episode.brief_text, episode.tools, turns) == []


def test_the_audit_flags_a_zone_nobody_worked_out():
    task = tasksets.task_from_entry(_row(24000), level="vague")
    episode = ProbeEpisode(task, reasoning.ReasoningAgent(), EpisodeConfig(level="vague"))
    episode.run()
    turns = json.loads(json.dumps(episode.turns))
    moved = 0
    for turn in turns:
        for call in (turn.get("assistant") or {}).get("tool_calls") or []:
            if call["name"] == "draw_offset" and call["params"]["offsets"] == [0.33]:
                call["params"]["station_range"][0] += 37.0
                moved += 1
    assert moved == 1
    found = reasoning.audit(episode.brief_text, episode.tools, turns)
    assert [f["tool"] for f in found] == ["draw_offset"]
    # and a root that is not the root of what it says grounds nothing
    turns = json.loads(json.dumps(episode.turns))
    text = turns[1]["assistant"]["text"]
    stated = reasoning_striping._ROOT.search(text)
    wrong = f"sqrt({stated.group(1)}) = {float(stated.group(2)) + 1.5:.4f}"
    turns[1]["assistant"]["text"] = text.replace(stated.group(0), wrong, 1)
    assert reasoning.audit(episode.brief_text, episode.tools, turns)


def test_the_audits_striping_forms_are_held_to_a_striping_task():
    """``sqrt(X) = Y`` counts when Y is the root of X; the MUTCD's values and the roots
    are taken only on a task that names the MUTCD's passing sight distance."""
    say = "The sight distance is 900 ft. sqrt(70000) = 264.5751. sqrt(70000) = 250."
    turns = [{"n": 1, "assistant": {"text": say, "tool_calls": []}, "results": []}]
    assert reasoning_striping.roots(turns) == (264.5751,)
    brief = striping.striping_task(24000).probe.vague
    assert reasoning_striping.is_striping(brief)
    on = {f["value"] for f in reasoning.audit(brief, [], turns)}
    assert on == {70000.0, 250.0}       # the radicand nobody worked out, and the wrong root
    deed = "Plot the deed: thence N 10°00'00\" E 100.00 feet to the point of beginning."
    assert not reasoning_striping.is_striping(deed)
    off = {f["value"] for f in reasoning.audit(deed, [], turns)}
    assert {900.0, 264.5751} <= off
    assert math.isclose(reasoning_striping.PSD[55], p13.MUTCD_PSD[55])
    assert reasoning_striping.PSD == p13.MUTCD_PSD


# ------------------------------------------------------------ the converter


def test_the_converter_takes_the_recordings(tmp_path):
    from roaddraft.trajectories import conversations as cv
    src, out = tmp_path / "src", tmp_path / "out"
    for level in LEVELS:
        index = reasoning.record(NAME, src / f"{NAME}-{level}", level=level, limit=2)
        assert index["kept"] == 2 and set(index["by_kind"]) <= set(striping.KINDS)
    summary = cv.run([NAME], list(LEVELS), source=src, out=out, log=lambda *_: None)
    assert {k: t["kept"] for k, t in summary["sets"].items()} == {
        f"{NAME}-explicit": 2, f"{NAME}-vague": 2}
    assert all(t["dropped"] == {} for t in summary["sets"].values())
    tally = summary["sets"][f"{NAME}-vague"]
    assert tally["harness"] == "probe" and tally["by_type"] == {striping.TASK_TYPE: 2}
    assert tally["seeds"] == [24000, 24001]
    line = json.loads((out / f"{NAME}-vague.jsonl").read_text().splitlines()[0])
    assert line["header"]["probe"] == "t13-striping-24000"
