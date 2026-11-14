"""Plan §8 build 5 (2026-11-13): the generated deeds (``tasks.deeds``, the ``p03``
survey traps) and planted-error sheets (``tasks.planted``, the ``p14`` QA
reviews), run as probe tasks on the pilots' harness, and their grounded drafter
(``trajectories.reasoning``, ``reasoning_qa``)."""
from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import Agent, ToolCall
from roaddraft.eval.agents.basic import NullAgent
from roaddraft.eval.episode import EpisodeConfig
from roaddraft.eval.probe_tasks import ProbeEpisode, ProbeOracleAgent
from roaddraft.tasks import deeds, planted
from roaddraft.trajectories import reasoning

LEVELS = ("explicit", "vague")


def _row(name: str, seed: int) -> dict:
    return next(t for t in tasksets.load(name)["tasks"] if t["seed"] == seed)


def _run(name: str, seed: int, agent, level: str):
    task = tasksets.task_from_entry(_row(name, seed), level=level)
    return ProbeEpisode(task, agent, EpisodeConfig(level=level)).run()


class _Script(Agent):
    """Hands the episode a fixed list of calls, then submits."""
    name = "script"

    def __init__(self, make):
        self.make, self.done = make, False

    def reset(self, task, level, mode):
        self.done = False

    def act(self, observation):
        if self.done:
            return [ToolCall("submit", {"note": "done"})]
        self.done = True
        return self.make(observation)


# ------------------------------------------------------------ the sets


def test_the_generated_sets_are_their_own_seeds_and_share_nothing():
    assert tasksets.PROBE_TRAIN_NAMES == ("train-deeds", "train-qa")
    assert not set(tasksets.PROBE_TRAIN_NAMES) & set(tasksets.NAMES + tasksets.TRAIN_NAMES)
    assert tasksets.train_overlap() == []
    for name, module in (("train-deeds", deeds), ("train-qa", planted)):
        m = tasksets.load(name)
        assert m["harness"] == "probe"
        seeds = [t["seed"] for t in m["tasks"]]
        assert seeds == [s for s in module.SEEDS if s not in m["skipped_seeds"]]
        assert len(seeds) >= 0.9 * len(module.SEEDS)
        assert all(t["generated"] == name for t in m["tasks"])
        ids = [t["task_id"] for t in m["tasks"]] + [t["vague_task_id"] for t in m["tasks"]]
        assert len(set(ids)) == len(ids)
    assert set(deeds.SEEDS).isdisjoint(planted.SEEDS)
    others = (set(tasksets.TRAIN_SEEDS) | set(tasksets.TRAIN_HARD_SEEDS)
              | set(tasksets.TRAIN_TWIST_SEEDS) | set(tasksets.TRAIN_CROWD_SEEDS)
              | set(tasksets.TRAIN_REVISE_SEEDS))
    assert others.isdisjoint(deeds.SEEDS) and others.isdisjoint(planted.SEEDS)


def test_the_generated_manifests_rebuild_to_their_ids():
    """A sample; ``python -m roaddraft.eval taskset train-deeds train-qa`` checks all."""
    for name, module in (("train-deeds", deeds), ("train-qa", planted)):
        for entry in tasksets.load(name)["tasks"][:4]:
            fresh = module.entry(entry["seed"])
            assert fresh["task_id"] == entry["task_id"]
            assert fresh["vague_task_id"] == entry["vague_task_id"]
            for level in LEVELS:
                task = tasksets.task_from_entry(entry, level=level)
                assert task.task_id == (entry["task_id"] if level == "explicit"
                                        else entry["vague_task_id"])


def test_nothing_is_registered_inside_the_pilot_package():
    """A probe added to ``probes/pilot`` joins the held-out set and moves its hashes."""
    from roaddraft.eval import probe_tasks
    deeds.deed_task(19000)
    planted.qa_task(20002)
    pilots = {p.id for p in probe_tasks.pilots()}
    assert len(pilots) == 112
    assert not any(p.startswith(("t03-", "t14-")) for p in pilots)
    assert tasksets.check("hard-pilots") == []


# ------------------------------------------------------------ the deeds


def test_a_deed_as_written_does_not_close_and_its_check_is_the_pilots():
    for seed in (19000, 19001):
        d = deeds.deed_task(seed)
        assert deeds.MISS_FT[0] <= d.misclosure <= deeds.MISS_FT[1]
        assert deeds.PRECISION[0] <= d.precision <= deeds.PRECISION[1]
        assert d.probe.vague and d.probe.vague_check is not None
        assert "compass" in d.probe.prompt and "set_meta" in d.probe.vague
        assert "V-PROP" in d.probe.prompt and "V-PROP" not in d.probe.vague
    kinds = {t["curve"] for t in tasksets.load("train-deeds")["tasks"]}
    assert kinds == {True, False}


@pytest.mark.parametrize("level", LEVELS)
def test_the_deed_oracle_passes_and_the_untouched_start_fails(level):
    for seed in (19000, 19001):  # a deed with a curve course, and one without
        assert _run("train-deeds", seed, ProbeOracleAgent(), level).effective_score == 100.0
        assert _run("train-deeds", seed, NullAgent(), level).effective_score == 0.0


def test_the_deed_drawn_as_written_with_a_closing_course_fails():
    """The naive answer: plotted as given and closed with the closing course."""
    from roaddraft.probes.pilot import survey
    for seed in (19000, 19001):
        d = deeds.deed_task(seed)
        naive = replace(d.probe, id=d.probe.id + "-naive",  # the oracle's cache is by id
                        solve=lambda s, deed=d.deed: survey.solve_deed(deed, s, balance=False))
        task = tasksets.task_from_entry(_row("train-deeds", seed), level="explicit")
        task = replace(task, probe=naive)
        result = ProbeEpisode(task, ProbeOracleAgent(), EpisodeConfig(level="explicit")).run()
        assert result.effective_score == 0.0
        assert "compass-rule" in result.report.detail or "corner" in result.report.detail


@pytest.mark.parametrize("level", LEVELS)
def test_the_grounded_drafter_balances_a_deed_and_is_kept(level, tmp_path):
    for seed in (19000, 19001):
        task = tasksets.task_from_entry(_row("train-deeds", seed), level=level)
        row = reasoning.record_task(task, level, out_root=tmp_path)
        assert row["kept"], row
        assert row["ungrounded"] == []


def test_the_audit_flags_a_corner_nobody_worked_out(tmp_path):
    task = tasksets.task_from_entry(_row("train-deeds", 19001), level="vague")
    episode = ProbeEpisode(task, reasoning.ReasoningAgent(), EpisodeConfig(level="vague"))
    episode.run()
    assert reasoning.audit(episode.brief_text, episode.tools, episode.turns) == []
    turns = json.loads(json.dumps(episode.turns))
    for turn in turns:
        for call in (turn.get("assistant") or {}).get("tool_calls") or []:
            if call["name"] == "draw_polyline":
                call["params"]["vertices"][1][0] += 0.25
    found = reasoning.audit(episode.brief_text, episode.tools, turns)
    assert any(f["tool"] == "draw_polyline" for f in found)


def test_the_audit_reads_grouped_numbers_and_area_labels():
    from roaddraft.trajectories.grounded import Seen
    assert reasoning.ungrouped("N 20,005.68, E 9,518.63; 132,346 SQ FT") == \
        "N 20005.68, E 9518.63; 132346 SQ FT"
    seen = Seen("")
    seen.numbers.append(35929.167)
    assert reasoning.area_label("35,929 SQ FT", seen)
    assert not reasoning.area_label("35,931 SQ FT", seen)


# ------------------------------------------------------------ the QA reviews


def test_one_review_in_three_is_a_clean_control_and_plants_are_apart():
    m = tasksets.load("train-qa")["tasks"]
    controls = sum(t["control"] for t in m)
    assert 0.25 * len(m) <= controls <= 0.42 * len(m)
    assert {k for t in m for k in t["plants"]} == set(planted.KINDS)
    for t in m:
        assert t["control"] == (not t["plants"])
        assert not t["plants"] or planted.PLANTS[0] <= len(t["plants"]) <= planted.PLANTS[1]
        assert len(set(t["plants"])) == len(t["plants"])
    q = planted.qa_task(20005)
    from roaddraft.api.session import Session
    from roaddraft.document.document import Document
    start = Session(_document=Document.from_dict(planted._STARTS[20005]))
    spots = []
    for plant in q.plants:
        texts, segs = planted.plant_marks(20005, start, plant)
        spots.append(texts[0].center() if texts else segs[0].mid())
    for i, a in enumerate(spots):
        for b in spots[i + 1:]:
            assert math.dist(a, b) >= planted.APART_IN - 0.5


@pytest.mark.parametrize("level", LEVELS)
def test_the_review_oracle_passes_and_the_untouched_start_fails(level):
    for seed in (20000, 20002):  # a control, and a sheet with four plants
        assert _run("train-qa", seed, ProbeOracleAgent(), level).effective_score == 100.0
        assert _run("train-qa", seed, NullAgent(), level).effective_score == 0.0


def _clean_text(observation):
    return [ToolCall("create_layer", {"name": "QA-REVIEW"}),
            ToolCall("place_text", {"space": "C-101", "layer": "QA-REVIEW",
                                    "position": [3.0, 2.0], "height": 0.1,
                                    "content": "NO ERRORS FOUND"})]


def test_calling_a_planted_sheet_clean_fails_and_a_clean_one_passes():
    assert _run("train-qa", 20002, _Script(_clean_text), "vague").effective_score == 0.0
    assert _run("train-qa", 20000, _Script(_clean_text), "vague").effective_score == 100.0


def test_marking_more_than_the_errors_fails_on_false_alarms():
    """Every plant marked, then two queries more: one false alarm is allowed, two fail it;
    on a clean control, a single mark fails it."""
    from roaddraft.eval.probe_tasks import oracle_calls
    q = planted.qa_task(20002)
    extra = [ToolCall("place_callout", {"space": "C-101", "layer": "QA-REVIEW", "target": t,
                                        "position": [t[0] + 0.75, t[1] + 0.75],
                                        "content": "QA: CHECK"})
             for t in ([20.0, 4.0], [12.0, 5.0])]

    def marked(count):
        return lambda observation: [ToolCall(n, p) for n, p in oracle_calls(q.probe)] + extra[:count]
    assert _run("train-qa", 20002, _Script(marked(1)), "vague").effective_score == 100.0
    result = _run("train-qa", 20002, _Script(marked(2)), "vague")
    assert result.effective_score == 0.0 and "point at no planted" in result.report.detail

    def one_mark(observation):  # called clean, and one query besides
        return _clean_text(observation) + extra[:1]
    result = _run("train-qa", 20000, _Script(one_mark), "vague")
    assert result.effective_score == 0.0 and "sheet with no errors" in result.report.detail


def test_fixing_an_error_instead_of_marking_it_fails():
    q = planted.qa_task(20007)
    plant = next(p for p in q.plants if p.get("model"))
    from roaddraft.api.session import Session
    from roaddraft.document.document import Document
    clean = Document.from_dict(planted._CLEAN[20007])
    content = clean.model_entities[plant["model"][0]].content

    def fix(observation):
        return [ToolCall("modify_entity", {"id": plant["model"][0], "changes": {"content": content}})]
    result = _run("train-qa", 20007, _Script(fix), "vague")
    assert result.effective_score == 0.0
    del Session


@pytest.mark.parametrize("level", LEVELS)
def test_the_grounded_checker_marks_every_plant_and_is_kept(level, tmp_path):
    for seed in (20000, 20002, 20005):
        task = tasksets.task_from_entry(_row("train-qa", seed), level=level)
        row = reasoning.record_task(task, level, out_root=tmp_path)
        assert row["kept"], row


def test_a_qa_note_is_grounded_only_with_a_phrase_and_a_value_seen():
    from roaddraft.trajectories.grounded import Seen
    seen = Seen("")
    seen.add({"bearing": "N 83°11'01\" E", "length": 171.3397, "ref": "108+00.00"})
    assert reasoning.review_note("QA: NORTH ARROW DOES NOT POINT NORTH", seen)
    assert reasoning.review_note("QA: BEARING SHOULD READ N 83°11'01\" E 171.34'", seen)
    assert reasoning.review_note("QA: STATION TICK MISSING AT 108+00.00", seen)
    assert not reasoning.review_note("QA: BEARING SHOULD READ N 83°11'01\" E 171.94'", seen)
    assert not reasoning.review_note("QA: LOOKS WRONG", seen)
