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
              | set(tasksets.TRAIN_REVISE_SEEDS) | set(tasksets.TRAIN_TWIST_WIDTH_SEEDS)
              | set(tasksets.TRAIN_REVISE_BASE_SEEDS) | set(tasksets.TRAIN_BREAKS_SEEDS))
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


def _header(path) -> dict:
    with open(path) as f:
        return json.loads(f.readline())


@pytest.mark.parametrize("name,seed", [("train-deeds", 19000), ("train-qa", 20000)])
def test_the_recorder_runs_on_the_pilots_budgets(name, seed, tmp_path):
    """A recorded conversation states the budgets a pilot run is told (600 steps, 12
    faults), not D1's 150 and 8: the converter builds the system prompt from the header."""
    from roaddraft.eval import probe_tasks
    from roaddraft.trajectories.conversations import budgets_of
    task = tasksets.task_from_entry(_row(name, seed), level="vague")
    row = reasoning.record_task(task, "vague", out_root=tmp_path)
    assert row["kept"], row
    header = _header(row["path"])
    assert header["budgets"] == probe_tasks.BUDGETS.for_mode("single").to_dict()
    assert (header["budgets"]["steps"], header["budgets"]["faults"]) == (600, 12)
    said = probe_tasks.system_prompt("single", budgets_of(header))
    assert "You have 600 steps, and 12 failed calls in a row end the task" in said
    assert tasksets.default_budgets(name) == probe_tasks.BUDGETS


@pytest.mark.parametrize("name", tasksets.PROBE_TRAIN_NAMES)
def test_the_runner_runs_a_generated_set_as_it_runs_the_pilots(name, tmp_path):
    """``python -m roaddraft.eval run --taskset train-deeds`` (and ``train-qa``): the
    oracle passes and the null agent fails through the loop, at both levels, each
    episode filed under the id of its level and on the pilots' budgets."""
    from roaddraft.eval import probe_tasks
    from roaddraft.eval.runner import Cell, RunSpec, cell_path, run
    spec = RunSpec(taskset=name, agents=("oracle", "null"), levels=LEVELS, limit=2,
                   results_root=str(tmp_path), run_id="gen",
                   budgets=tasksets.default_budgets(name))
    summary = run(spec)
    assert summary["episodes"] == 8 and not summary.get("errors")
    for level in LEVELS:
        assert summary["groups"][f"oracle|{level}|single"]["mean_effective"] == 100.0
        assert summary["groups"][f"oracle|{level}|single"]["n"] == 2
        assert summary["groups"][f"null|{level}|single"]["mean_effective"] == 0.0
        for entry in tasksets.entries(name, limit=2):
            cell = Cell(entry, "oracle", level, "single", 0)
            assert cell.task_id == entry["vague_task_id" if level == "vague" else "task_id"]
            header = _header(cell_path(spec, cell))
            assert header["task_id"] == cell.task_id and header["level"] == level
            assert header["budgets"]["steps"] == probe_tasks.BUDGETS.steps


def test_a_generated_episode_carries_its_own_sets_pins(tmp_path, monkeypatch):
    """A training episode is stamped with its own set's hashes: the generator version
    its manifest names and a check hash over the pilot checks and the module that
    generates it.  The held-out pilots' two hashes are theirs alone and do not move."""
    from roaddraft.eval import probe_tasks
    held = (probe_tasks.generator_version(probe_tasks.pilots()), probe_tasks.check_version())
    assert held == (tasksets.current_generator("hard-pilots"),
                    tasksets.current_verifier("hard-pilots"))
    for name, module, seed in (("train-deeds", deeds, 19000), ("train-qa", planted, 20000)):
        result = _run(name, seed, ProbeOracleAgent(), "vague")
        probe = tasksets.task_from_entry(_row(name, seed)).probe
        assert probe_tasks.generated_set(probe.id) == name
        generator, verifier = probe_tasks.pins_of(probe)
        assert generator == tasksets.load(name)["generator_version"] \
            == tasksets.current_generator(name) != held[0]
        assert verifier == tasksets.current_verifier(name) != held[1]
        assert result.report.to_dict()["verifier_version"] == verifier
        task = tasksets.task_from_entry(_row(name, seed), level="vague")
        episode = ProbeEpisode(task, NullAgent(), EpisodeConfig(level="vague"))
        episode.reset()
        header = episode.header()
        assert (header["generator_version"], header["verifier_version"]) == (generator, verifier)
        # the hash is over the generating module too, so an edit to it moves the pin
        sources = probe_tasks.check_sources(name)
        assert sources[:-1] == probe_tasks.check_sources() and sources[-1].samefile(module.__file__)
        edited = tmp_path / sources[-1].name
        edited.write_bytes(sources[-1].read_bytes() + b"\n# edited\n")
        assert probe_tasks.check_version(sources[:-1] + [edited]) != verifier
    assert len({tasksets.current_verifier(n) for n in tasksets.PROBE_TRAIN_NAMES}) == 2
    # a pilot and a pilot-dev instance keep their sets' pins
    from roaddraft.probes import pilot_dev
    assert probe_tasks.generated_set(probe_tasks.pilots()[0].id) is None
    assert probe_tasks.pins_of(probe_tasks.pilots()[0]) == held
    assert probe_tasks.pins_of(pilot_dev.PROBES[0]) == (
        tasksets.current_generator("pilot-dev"), tasksets.current_verifier("pilot-dev"))
    assert not any(probe_tasks.generated_set(p.id)
                   for p in probe_tasks.pilots() + probe_tasks.dev_probes())


def test_nothing_is_registered_inside_the_pilot_package():
    """A probe added to ``probes/pilot`` joins the held-out set and moves its hashes."""
    from roaddraft.eval import probe_tasks
    deeds.deed_task(19000)
    planted.qa_task(20002)
    pilots = {p.id for p in probe_tasks.pilots()}
    assert len(pilots) == 112
    assert not any(p.startswith(("t03-", "t14-")) for p in pilots)
    assert tasksets.check("hard-pilots") == []


def _plain(text) -> str:
    return str(text).replace("\u2019", "'").replace("\u2032", "'").replace("\u201d", '"')


def _course(leg: dict) -> tuple:
    if "bearing" in leg:
        return ("line", _plain(leg["bearing"]), round(leg["distance"], 2))
    return ("curve", round(leg["radius"], 2), _plain(leg["delta"]))


def test_no_generated_deed_repeats_a_held_out_deed():
    """The three held-out deeds (``p03-misclosure-*``) against all 300 generated:
    no course, no point of beginning and no (misclosure, precision) answer in
    common, and a generated deed is set on no sheet."""
    from roaddraft.design import cogo
    from roaddraft.probes.pilot import survey
    held = [(survey.MIS_POB, [{"bearing": b, "distance": d} for b, d in survey.MIS_DEED]),
            (survey.DEED_PPM049.pob, list(survey.DEED_PPM049.legs)),
            (survey.DEED_FDOT915.pob, list(survey.DEED_FDOT915.legs))]
    held_courses = {_course(leg) for _, legs in held for leg in legs}
    held_pobs = {(round(x, 2), round(y, 2)) for (x, y), _ in held}
    held_answers = set()
    for pob, legs in held:
        m = cogo.run_traverse(pob, [dict(leg) for leg in legs], close=True).misclosure()
        held_answers.add((round(m["distance"], 2), round(m["perimeter"] / m["distance"])))
    assert len(held_courses) == 22 and len(held_answers) == 3
    made = [deeds.deed_task(t["seed"]) for t in tasksets.load("train-deeds")["tasks"]]
    assert len(made) == 300
    for d in made:
        assert d.deed.sheet_id == ""
        assert not {_course(leg) for leg in d.deed.legs} & held_courses, d.seed
        assert (round(d.deed.pob[0], 2), round(d.deed.pob[1], 2)) not in held_pobs, d.seed
        assert (round(d.misclosure, 2), round(d.precision)) not in held_answers, d.seed


def test_no_generated_review_sheet_letters_a_held_out_sheets_values(tmp_path):
    """The nine held-out QA reviews (``p14``) against all 300 generated sheets:
    no bearing, station or curve value lettered on a generated sheet is lettered
    in a held-out pilot's files, and no plant is one of theirs."""
    import re
    from roaddraft.document.fileformat import read_document
    from roaddraft.eval import probe_tasks
    from roaddraft.probes import fixture
    from roaddraft.probes.pilot import qa_review
    value = re.compile(r"\d+°\d+'\d+|\d+\+\d\d\.\d\d|\d{3,}\.\d\d")

    def lettered(node, out):
        if isinstance(node, str):
            if value.search(_plain(node)):
                out.add(_plain(node))
        elif isinstance(node, dict):
            for v in node.values():
                lettered(v, out)
        elif isinstance(node, (list, tuple)):
            for v in node:
                lettered(v, out)
        return out

    pilots = [p for p in probe_tasks.pilots() if p.id.startswith("p14-")]
    assert len(pilots) == 9
    theirs = set()
    for p in pilots:
        doc = fixture.start_document(tmp_path / p.id, p.start)
        for path in doc.parent.rglob("*.rdraft"):
            lettered(read_document(path), theirs)
    their_plants = {_plain(pl["what"]) for name in dir(qa_review) if name.endswith("_PLANTS")
                    for pl in getattr(qa_review, name)}
    assert len(theirs) > 100 and len(their_plants) > 25
    ours, our_plants = set(), set()
    for row in tasksets.load("train-qa")["tasks"]:
        task = planted.qa_task(row["seed"])
        lettered(planted._STARTS[task.seed], ours)
        our_plants |= {_plain(pl["what"]) for pl in task.plants}
    assert len(ours) > 2000 and len(our_plants) > 300
    # a whole station (``142+00.00``) is on any line stationed through it: not a sheet's value
    both = {s for s in ours & theirs if not re.fullmatch(r"\d+\+00\.00", s)}
    assert not both, sorted(both)
    assert not our_plants & their_plants


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
