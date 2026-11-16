"""Plan §8 (2026-11-15): the generated plan-and-profile sheets (``tasks.planprofile``,
the ``p06`` family) as probe tasks on the pilots' harness, set ``train-profile``, and
their grounded drafter (``trajectories.reasoning_profile``)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from roaddraft.api.session import Session
from roaddraft.eval import probe_tasks
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents.basic import NullAgent
from roaddraft.eval.episode import EpisodeConfig
from roaddraft.eval.probe_tasks import ProbeEpisode, ProbeOracleAgent
from roaddraft.probes import fixture
from roaddraft.probes.pilot import profile as pilot
from roaddraft.tasks import planprofile
from roaddraft.trajectories import reasoning, reasoning_profile

NAME = "train-profile"
LEVELS = ("explicit", "vague")
#: a sample: 1" = 40' on a 17 x 22 sheet; the grade beginning on the sheet and the line
#: running onto a curve; a high point; the sheet past the line's end, curves dialed
SAMPLE = (25000, 25001, 25002, 25005)


def _row(seed: int) -> dict:
    return next(t for t in tasksets.load(NAME)["tasks"] if t["seed"] == seed)


def _run(seed: int, agent, level: str):
    task = tasksets.task_from_entry(_row(seed), level=level)
    return ProbeEpisode(task, agent, EpisodeConfig(level=level)).run()


def _sessions(seed: int, tmp_path):
    t = planprofile.profile_task(seed)
    path = fixture.EXTRA_STARTS[t.probe.start](Path(tmp_path))
    return t, Session.load(path, out_dir=tmp_path), Session.load(path, out_dir=tmp_path)


# ------------------------------------------------------------ the set


def test_the_set_is_its_own_seeds_and_shares_nothing():
    assert NAME in tasksets.PROBE_TRAIN_NAMES
    assert NAME not in tasksets.NAMES + tasksets.TRAIN_NAMES
    assert tasksets.train_overlap() == []
    m = tasksets.load(NAME)
    assert m["harness"] == "probe"
    seeds = [t["seed"] for t in m["tasks"]]
    assert seeds == [s for s in planprofile.SEEDS if s not in m["skipped_seeds"]]
    assert list(planprofile.SEEDS) == list(range(25000, 25300))
    assert len(seeds) >= 0.9 * len(planprofile.SEEDS)
    assert all(t["generated"] == NAME and t["family"] == "p06" for t in m["tasks"])
    ids = [t["task_id"] for t in m["tasks"]] + [t["vague_task_id"] for t in m["tasks"]]
    assert len(set(ids)) == len(ids)
    from roaddraft.tasks import deeds, planted
    others = (set(tasksets.TRAIN_SEEDS) | set(tasksets.TRAIN_HARD_SEEDS)
              | set(tasksets.TRAIN_TWIST_SEEDS) | set(tasksets.TRAIN_CROWD_SEEDS)
              | set(tasksets.TRAIN_REVISE_SEEDS) | set(tasksets.TRAIN_TWIST_WIDTH_SEEDS)
              | set(tasksets.TRAIN_REVISE_BASE_SEEDS) | set(tasksets.TRAIN_BREAKS_SEEDS)
              | set(deeds.SEEDS) | set(planted.SEEDS))
    assert others.isdisjoint(planprofile.SEEDS)


def test_it_is_registered_outside_the_pilot_package():
    """A probe added to ``probes/pilot`` joins the held-out set and moves its hashes."""
    held = {p.id for p in probe_tasks.pilots() + probe_tasks.dev_probes()}
    probe = planprofile.profile_task(SAMPLE[0]).probe
    assert probe.id not in held and probe_tasks.generated_set(probe.id) == NAME
    assert probe_tasks.by_id(probe.id) is probe
    assert not any(probe_tasks.generated_set(i) for i in held)
    sources = probe_tasks.check_sources(NAME)
    assert sources[:-1] == probe_tasks.check_sources()
    assert sources[-1].samefile(planprofile.__file__)
    generator, verifier = probe_tasks.pins_of(probe)
    assert generator == tasksets.load(NAME)["generator_version"] == tasksets.current_generator(NAME)
    assert verifier == tasksets.current_verifier(NAME) != tasksets.current_verifier("hard-pilots")
    assert verifier.startswith("pilot-check-")
    assert tasksets.default_budgets(NAME) == probe_tasks.BUDGETS


def test_the_generator_is_deterministic():
    """The same seed gives the same sheet, profile, prompts and start document, made
    again from nothing (``profile_task`` keeps what it made)."""
    for seed in SAMPLE[:2]:
        first = planprofile.profile_task(seed)
        start = copy.deepcopy(planprofile._STARTS[seed])
        again = planprofile.profile_task.__wrapped__(seed)
        assert again.lay == first.lay and again.facts == first.facts
        assert (again.probe.prompt, again.probe.vague) == (first.probe.prompt, first.probe.vague)
        assert planprofile._STARTS[seed] == start
        for level in LEVELS:
            assert again.task_id(level) == first.task_id(level)


def test_the_manifest_rebuilds_to_its_ids():
    """A sample; ``python -m roaddraft.eval taskset train-profile`` checks all."""
    for entry in tasksets.load(NAME)["tasks"][:4]:
        fresh = planprofile.entry(entry["seed"])
        assert {**fresh, "generated": NAME} == entry
        for level in LEVELS:
            task = tasksets.task_from_entry(entry, level=level)
            assert task.task_id == entry["vague_task_id" if level == "vague" else "task_id"]
            assert task.task_type == planprofile.TASK_TYPE


def test_the_set_covers_what_the_pilots_vary():
    rows = tasksets.load(NAME)["tasks"]
    assert {r["feet_per_inch"] for r in rows} == {40.0, 50.0}
    assert {(r["feet_per_inch"], r["vertical_feet_per_inch"]) for r in rows} == {
        (50.0, 5.0), (50.0, 10.0), (40.0, 4.0), (40.0, 10.0)}
    assert {r["size"] for r in rows} == {"ANSI_B", "ANSI_C", "ANSI_D"}
    assert {r["template"] for r in rows} == set(planprofile.TEMPLATES)
    for trap in ("point_without_pvi", "curve_without_pvi", "grade_break",
                 "grade_begins_on_sheet", "grade_ends_on_sheet", "past_the_line",
                 "onto_a_curve", "profile_layers"):
        assert 5 <= sum(bool(r[trap]) for r in rows) < len(rows), trap
    assert any(not r["high_low"] for r in rows) and any(r["high_low"] for r in rows)
    assert any(r["curves_lettered"] == 0 for r in rows)


def test_no_generated_sheet_is_a_pilots():
    """Not a redrafted sheet, and none of a pilot's parameters: its line is the seeded
    generator's, and no PVI, datum or station range is a pilot's."""
    theirs = pilot.JOBS + pilot.NEW_JOBS
    pvis = {(p[0], p[1]) for job in theirs for p in job.pvis}
    for seed in SAMPLE:
        t = planprofile.profile_task(seed)
        lay = t.lay
        assert lay.alignment == "ALIGN-1" and t.base_task_id.startswith("D1-")
        assert not pvis & {(p[0], p[1]) for p in lay.pvis}
        assert all((lay.s0, lay.s1) != (j.s0, j.s1) and lay.sheet != j.sheet for j in theirs)
        doc = planprofile._STARTS[seed]
        assert not doc.get("references")


# ------------------------------------------------------------ the check


@pytest.mark.parametrize("seed", SAMPLE)
def test_the_oracle_passes_and_doing_nothing_fails(seed):
    for level in LEVELS:
        assert _run(seed, ProbeOracleAgent(), level).effective_score == 100.0
        assert _run(seed, NullAgent(), level).effective_score == 0.0


@pytest.mark.parametrize("seed", (25000, 25002))
def test_the_naive_answers_fail_as_they_do_on_the_pilots(seed, tmp_path):
    """The plan turned 3 degrees off level fails the line-up (the pilots' usual miss);
    the grade drawn PVI to PVI fails the grade line.  At 1" = 40' (25000) the items
    are read in the stated grid's frame and judge the same way."""
    t, base, _ = _sessions(seed, tmp_path)
    for kw, item in (({"twist_off": 3.0}, "plan stations line up with the profile"),
                     ({"curves": False}, "profile grade line")):
        s = Session.load(base.doc._path, out_dir=tmp_path)
        planprofile.solve_lay(t.lay, s, **kw)
        for level in LEVELS:
            result = t.probe.check_at(level)(base, s)
            assert not result.passed
            assert dict(result.items)[item] is False
            assert sum(not done for _n, done in result.items) == 1, result.items


def test_a_plan_off_the_profiles_stations_fails(tmp_path):
    """The plan level and stationed, but its middle 5 ft along the line from the grid's:
    every station 0.1 in off the profile's."""
    t, base, s = _sessions(25002, tmp_path)
    planprofile.solve_lay(t.lay, s)
    sheet = next(x for x in s.doc.sheets.values() if x.name == t.lay.sheet)
    vp = sheet.viewports[0]
    cx, cy = vp.center_paper
    r = s.execute("modify_viewport", {"sheet": t.lay.sheet, "viewport_id": vp.id,
                                      "changes": {"center_paper": [cx + 0.1, cy]}})
    assert r["ok"], r
    for level in LEVELS:
        result = t.probe.check_at(level)(base, s)
        assert not result.passed and "on the profile" in result.detail


def test_at_fifty_scale_the_check_is_the_pilots_own():
    t = planprofile.profile_task(25002)
    assert t.lay.h_scale == 50.0
    assert t.probe.check.__qualname__ == pilot.make_check(t.lay).__qualname__
    assert t.probe.vague_check.__qualname__ == pilot.make_vague_check(t.lay).__qualname__
    assert planprofile.profile_task(25000).lay.h_scale == 40.0


def test_the_prompts_are_the_pilots_wording():
    t = planprofile.profile_task(25002)
    assert t.probe.prompt == pilot._prompt(t.lay) and t.probe.vague == pilot._vague(t.lay)
    forty = planprofile.profile_task(25000)
    assert forty.probe.prompt == pilot._prompt(forty.lay).replace("1\"=50'", "1\"=40'")
    assert "1\"=50'" not in forty.probe.prompt
    for level in LEVELS:
        brief = reasoning_profile.read_brief(probe_tasks.brief_text(forty.probe, level))
        assert (brief["sheet"], brief["alignment"], brief["profile"]) == (
            forty.lay.sheet, forty.lay.alignment, forty.lay.profile)
        assert (brief["s0"], brief["s1"]) == (forty.lay.s0, forty.lay.s1)
        assert ("h" in brief) == (level == "explicit")
    # and a pilot's own brief reads the same way
    job = pilot.WFL
    brief = reasoning_profile.read_brief(probe_tasks.brief_text(pilot.PROBES[1], "explicit"))
    assert (brief["alignment"], brief["profile"], brief["x0"], brief["e1"]) == (
        job.alignment, job.profile, job.x0, job.e1)


# ------------------------------------------------------------ the drafter


@pytest.mark.parametrize("seed", SAMPLE)
def test_the_drafter_records_clean_at_both_levels(seed, tmp_path):
    for level in LEVELS:
        task = tasksets.task_from_entry(_row(seed), level=level)
        row = reasoning.record_task(task, level, out_root=tmp_path)
        assert row["kept"], row
        assert row["termination"] == "submit" and not row["ungrounded"]
        with open(row["path"]) as f:
            header = json.loads(f.readline())
        assert header["budgets"]["steps"] == probe_tasks.BUDGETS.steps


def _recording(seed: int, level: str, tmp_path):
    task = tasksets.task_from_entry(_row(seed), level=level)
    episode = ProbeEpisode(task, reasoning.ReasoningAgent(),
                           EpisodeConfig(level=level, budgets=probe_tasks.BUDGETS),
                           out_root=tmp_path)
    episode.run()
    return episode


def test_the_audit_holds_the_drafter_to_what_it_read(tmp_path):
    """A value moved in a call, a number changed in the shown work, a label's value
    changed, a rounding done wrong: each is found."""
    episode = _recording(25002, "vague", tmp_path)
    brief, tools = episode.brief_text, episode.tools
    turns = json.loads(json.dumps(episode.turns))
    assert reasoning.audit(brief, tools, turns) == []

    def broken(change):
        t = json.loads(json.dumps(turns))
        change(t)
        return reasoning.audit(brief, tools, t)

    def move_view(t):
        call = next(c for c in t[2]["assistant"]["tool_calls"] if c["name"] == "create_viewport")
        call["params"]["center_paper"][0] += 0.37

    def relabel(t):
        call = next(c for c in t[4]["assistant"]["tool_calls"]
                    if str(c["params"].get("content", "")).startswith("PVI "))
        call["params"]["content"] = call["params"]["content"].replace("EL ", "EL 1")

    def wrong_rounding(t):
        said = t[1]["assistant"]["text"]
        assert "rounds down to 45, a whole 5" in said
        t[1]["assistant"]["text"] = said.replace("rounds down to 45, a whole 5",
                                                 "rounds down to 35, a whole 5")
        for turn in t:
            for c in turn["assistant"].get("tool_calls") or []:
                if c["params"].get("content") == "45":
                    c["params"]["content"] = "35"

    def invent_layer(t):
        call = next(c for c in t[3]["assistant"]["tool_calls"] if c["name"] == "draw_line")
        call["params"]["layer"] = "MY-GRID"

    assert [f["path"] for f in broken(move_view)] == ["center_paper[0]"]
    assert [f["path"] for f in broken(relabel)] == ["content"]
    assert any(f["value"] in (35.0, "35") for f in broken(wrong_rounding))
    assert [f["value"] for f in broken(invent_layer)] == ["MY-GRID"]


def test_the_audits_forms_are_this_familys_only():
    """The rounding form and the label forms ground nothing in a deed's or a review's
    audit: ``reasoning.audit`` adds them for a plan-and-profile brief alone."""
    turn = {"n": 1, "assistant": {"text": "312.47 rounds down to 310, a whole 5.",
                                  "tool_calls": [{"name": "place_text", "params": {
                                      "content": "310", "layer": "PROF-TEXT"}}]},
            "results": [{"ok": True}]}
    task = "The lowest grade is 312.47."
    found = reasoning.audit(task, [], [turn])
    assert {f["value"] for f in found} == {310.0, "310", "PROF-TEXT"}
    ours = probe_tasks.brief_text(planprofile.profile_task(25002).probe, "vague") + task
    assert reasoning.audit(ours, [], [turn]) == []
    assert reasoning_profile.rounded([turn]) == (310.0,)
    for wrong in ("312.47 rounds down to 305, a whole 5", "312.47 rounds up to 310, a whole 5",
                  "312.47 rounds down to 312, a whole 4"):
        assert reasoning_profile.rounded([{"assistant": {"text": wrong}}]) == ()


def test_the_converter_takes_the_recordings(tmp_path):
    from roaddraft.trajectories import conversations as cv
    src, out = tmp_path / "src", tmp_path / "out"
    for level in LEVELS:
        index = reasoning.record(NAME, src / f"{NAME}-{level}", level=level, limit=2)
        assert index["kept"] == 2
    summary = cv.run([NAME], list(LEVELS), source=src, out=out, jobs=1)
    for level in LEVELS:
        tally = summary["sets"][f"{NAME}-{level}"]
        assert tally["harness"] == "probe" and tally["by_type"] == {planprofile.TASK_TYPE: 2}
        lines = (out / f"{NAME}-{level}.jsonl").read_text().splitlines()
        assert len(lines) == 2
        head = json.loads(lines[0])["header"]
        assert head["taskset"] == NAME and head["seed"] == 25000 and head["probe"] == "t06-profile-25000"
    assert cv.PROBE_ORDER[:2] == ("train-deeds", "train-qa")
