"""The grounded drafter on a layout left to it (``grounded._choose_breaks``): the
training-only type ``plan-sheet-breaks`` (``tasks.breaks``, 2026-11-13, training
plan section 6 decision 8).  How many sheets a line takes and where they break
are chosen from what the engine reports, then laid out as any sheets are."""
from __future__ import annotations

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.tasks import breaks
from roaddraft.trajectories import grounded

TOOLS = [{"name": "create_sheet", "description": "", "input_schema": {}}]


def _open(sheets: int, twist: bool = False, n: int = 0):
    rows = [e for e in tasksets.load("d1-train-breaks")["tasks"]
            if e["sheets"] == sheets and bool(e.get("twist")) == twist and "dialed" not in e]
    return tasksets.task_from_entry(rows[n])


def _stated(level: str):
    """A task whose sheets and breaks the prompt names: two sheets of ``d1-dev``."""
    return next(tasksets.task_from_entry(e) for e in tasksets.load("d1-dev")["tasks"]
                if e["task_type"] == "plan-sheet" and e["sheets"] == 2).brief.prompts[level]


def _run(task, level: str):
    from roaddraft.eval.episode import Episode, EpisodeConfig
    episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level=level))
    episode.run()
    return episode


def _pairs(episode):
    return [(c, r) for turn in episode.turns
            for c, r in zip(turn["assistant"]["tool_calls"], turn["results"])]


def _turn(n, calls, results, text=""):
    return {"n": n, "assistant": {"text": text, "tool_calls": calls}, "results": results}


def test_stated_open_reads_the_first_sheet_of_a_layout_left_to_the_drafter():
    vague = _open(2).brief.prompts["vague"]
    assert grounded.stated_open(vague) == "C-101"
    layout = grounded.stated_layout(vague)
    assert layout["sheets"] == [] and layout["breaks"] == [] and layout["scale"] in (40.0, 50.0)
    assert grounded.stated_open(_stated("vague")) is None
    assert grounded.stated_open(_stated("explicit")) is None
    explicit = _open(2, twist=True).brief.prompts["explicit"]
    assert grounded.stated_open(explicit) == "C-101"
    layout = grounded.stated_layout(explicit)
    assert layout["sheets"] == [] and layout["breaks"] == [] and layout["size"] == "ANSI_D"
    assert layout["twist"] and layout["match_half_ft"] in (80.0, 100.0)
    # its title block states every value but the two the layout decides
    title = grounded.stated_title(explicit)
    assert title["sheet_numbers"] is None and "total_sheets" not in title
    assert title["sheet_title"] == "ROADWAY PLAN" and title["designed_by"] == "RD"
    # a title block that numbers its sheets reads as it always did
    assert grounded.stated_title(_stated("explicit"))["sheet_numbers"]
    # the one number the choice adds to the drafter's own, and it is the office's
    assert grounded.MATCH_CLEAR_FT in grounded.CHOICES
    assert grounded.MATCH_CLEAR_FT == breaks.CLEAR_FT and grounded.MARGIN_IN == breaks.MARGIN_IN


@pytest.mark.parametrize("sheets, twist", [(1, False), (2, False), (2, True), (3, True)])
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_layout_left_to_the_drafter_is_chosen_drafted_and_kept(sheets, twist, level):
    from roaddraft.eval.budget import Budgets
    row = grounded.record_task(_open(sheets, twist), level)
    assert row["termination"] == "submit", row["error"]
    assert row["ungrounded"] == []
    assert row["effective"] == 100.0 and row["lost"] == {}
    assert row["kept"] and row["steps"] < Budgets().steps


def test_the_drafter_counts_the_sheets_on_the_paper_and_breaks_at_sound_whole_stations():
    task = _open(3)
    episode = _run(task, "vague")
    pairs = _pairs(episode)
    names = [c["name"] for c, _r in pairs]
    assert [c["params"]["name"] for c, _r in pairs if c["name"] == "create_sheet"] == [
        "C-101", "C-102", "C-103"]
    # the first sheet is made alone, after the line is read, to measure the line on
    made = [i for i, n in enumerate(names) if n == "create_sheet"]
    assert "get_design_data" in names[:made[0]] and made[1] > made[0] + 1
    measured = [c for c, _r in pairs[made[0]:made[1]]
                if c["name"] in ("model_to_sheet", "station_to_xy")]
    align, fpi, turn, _own, _names = breaks.layout_of(task.truth)
    curves = len(align.curves())
    assert all(c["params"]["sheet"] == "C-101" for c in measured)
    # the two ends and each curve's BC and EC by their points, each middle by its station
    assert len([c for c in measured if c["name"] == "model_to_sheet"]) == 2 + 2 * curves
    asked = [c["params"]["station"] for c in measured if c["name"] == "station_to_xy"]
    assert len(asked) >= curves + 2
    # every break drawn was asked of the engine first, and is one the office would make
    drawn = sorted(c["params"]["points"][0].split("@")[0] for c, _r in pairs
                   if c["name"] == "draw_station_offset")
    assert len(drawn) == 2 and set(drawn) <= set(asked)
    stations, begin = align.stations(), float(align.begin_station)
    cuts = [stations.parse(text) - begin for text in drawn]
    assert all(d in breaks.office_breaks(align) for d in cuts)
    assert len(drawn) + 1 == breaks.fewest(align, fpi, turn)
    words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "26 by 15 in plan window" in words and "a quarter inch all round" in words
    assert "A match line keeps 60 ft from a curve point" in words
    assert "101 + 1 = 102" in words and "102 + 1 = 103" in words
    assert "see whether the line breaks evenly" in words
    # the first sheet's view is moved onto its stretch with the others', not made again
    assert names.count("create_viewport") == 3
    # and the title blocks number the sheets it chose, of three
    titles = [c["params"]["fields"] for c, _r in pairs if c["name"] == "fill_title_block"]
    assert [t["sheet_number"] for t in titles] == ["C-101", "C-102", "C-103"]
    assert {t["total_sheets"] for t in titles} == {"3"}


def test_a_line_that_fits_one_sheet_gets_one_sheet_and_no_match_line():
    episode = _run(_open(1), "vague")
    names = [c["name"] for c, _r in _pairs(episode)]
    assert names.count("create_sheet") == 1 and names.count("create_viewport") == 1
    assert "draw_station_offset" not in names
    words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "one sheet carries the whole line: C-101, with no break and no match line" in words
    assert grounded.audit(episode.brief_text, episode.tools, episode.turns) == []


def test_the_explicit_title_block_takes_its_values_from_the_task_and_its_numbers_from_the_layout():
    task = _open(2)
    episode = _run(task, "explicit")
    words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "The task gives every value of the title block but the two the layout decides" in words
    titles = [c["params"]["fields"] for c, _r in _pairs(episode) if c["name"] == "fill_title_block"]
    want = task.truth.sheets
    assert [t["sheet_number"] for t in titles] == [sh["name"] for sh in want]
    for fields, sheet in zip(titles, want):
        assert fields == sheet["title_block_fields"]


def test_a_stated_layout_is_laid_out_as_it_was_before_the_choice_existed():
    """A task that names its sheets never reaches ``_choose_breaks``: its sheets
    are all made in one turn, each with a viewport of its own."""
    task = next(tasksets.task_from_entry(e) for e in tasksets.load("d1-dev")["tasks"]
                if e["task_type"] == "plan-sheet" and e["sheets"] == 2)
    episode = _run(task, "vague")
    made = [turn["n"] for turn in episode.turns for c in turn["assistant"]["tool_calls"]
            if c["name"] == "create_sheet"]
    assert len(made) == 2 and made[0] == made[1]
    words = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "leaves it to the drafter" not in words


def test_audit_a_sheet_numbered_on_has_to_be_counted_from_the_one_the_task_names():
    text = "THE TASK:\nDraft the plan sheets for ALIGN-1 at 1\" = 50', numbered from PL-101."
    call = {"name": "create_sheet", "params": {"name": "PL-102"}}
    said = [_turn(1, [call], [{"ok": True}], text="The next sheet is 101 + 1 = 102.")]
    assert grounded.audit(text, TOOLS, said) == []
    unsaid = [_turn(1, [call], [{"ok": True}])]
    assert [f["value"] for f in grounded.audit(text, TOOLS, unsaid)] == ["PL-102"]
    # a prefix the task never used is from nowhere, whatever its number
    other = [_turn(1, [{"name": "create_sheet", "params": {"name": "XX-102"}}], [{"ok": True}],
                   text="The next sheet is 101 + 1 = 102.")]
    assert [f["value"] for f in grounded.audit(text, TOOLS, other)] == ["XX-102"]
