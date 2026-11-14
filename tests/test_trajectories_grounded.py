"""The grounded reference drafter and its audit (``roaddraft.trajectories.grounded``,
``RoadDraft_Training_Plan.md``): a recording is training data only when the
verifier scores it 100 and every value its calls carry was on the page first."""
from __future__ import annotations

import pytest

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import OracleAgent
from roaddraft.tasks.types import TASK_TYPES
from roaddraft.trajectories import grounded

#: the seeded types whose every phase the drafter covers
COVERED_TYPES = sorted(name for name, t in TASK_TYPES.items()
                       if all(p in grounded.COVERED for p in t.solution_phases()))


def _task(ttype: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-dev")["tasks"] if e["task_type"] == ttype]
    return tasksets.task_from_entry(rows[n])


def _real(ttype: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-real-dev")["tasks"] if e["task_type"] == ttype]
    return tasksets.task_from_entry(rows[n])


def _hard(ttype: str, sheets: int = 2, n: int = 0):
    rows = [e for e in tasksets.load("d1-train-hard")["tasks"]
            if e["task_type"] == ttype and e["sheets"] == sheets]
    return tasksets.task_from_entry(rows[n])


#: who designed, drew and checked a sheet, and its date: in the document's own record
PEOPLE = ("designed_by", "drawn_by", "checked_by", "date")
#: the covered types that fill a title block
TITLED = [name for name in COVERED_TYPES if "title" in TASK_TYPES[name].solution_phases()]


def test_every_seeded_type_is_covered():
    # 2026-11-12: the width dimensions, the last phase of the seeded types (2026-11-11: the
    # sheet and viewport phase, so the sheets themselves are drafted too)
    assert COVERED_TYPES == sorted(TASK_TYPES) and len(COVERED_TYPES) == 16
    assert TITLED == ["annotate-sheet", "plan-sheet", "title-block"]
    assert grounded.covers(_task("stationing")) == []
    assert grounded.covers(_task("plan-sheet")) == []
    assert grounded.covers(_task("pavement-widths")) == []
    assert grounded.covers(_hard("plan-sheet-pavement")) == []
    assert grounded.covers(_hard("create-plan-sheet")) == []
    # a real sheet's construction callouts are not drafted yet
    assert grounded.covers(_real("real-construction-callouts")) == ["notes"]


@pytest.mark.parametrize("ttype", COVERED_TYPES)
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_grounded_reference_scores_100_with_nothing_ungrounded(ttype, level):
    row = grounded.record_task(_task(ttype), level)
    assert row["termination"] == "submit", row["error"]
    assert row["ungrounded"] == []
    assert row["effective"] == 100.0 and row["lost"] == {}
    assert row["kept"]


def _calls(ttype: str, level: str, n: int = 0):
    from roaddraft.eval.episode import Episode, EpisodeConfig
    task = _task(ttype, n)
    episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level=level))
    episode.run()
    return task, [c for turn in episode.turns for c in turn["assistant"]["tool_calls"]]


def test_a_vague_title_block_is_filled_from_the_document():
    # the prompt gives no value; the project, the agency and who designed, drew and
    # checked the sheet and its date are all read off the document (Robert, 2026-11-11)
    task, calls = _calls("title-block", "vague")
    truth = task.brief.deliverable["sheets"][0]["title_block_fields"]
    assert not any(v in task.brief.prompts["vague"] for v in (truth["date"], truth["project"]))
    filled = next(c for c in calls if c["name"] == "fill_title_block")["params"]["fields"]
    assert filled == truth
    assert "blank" not in calls[-1]["params"]["note"]


def test_a_title_block_field_the_document_does_not_give_is_left_blank_not_made_up():
    # a document without the people and the date (every seeded one before 2026-11-11):
    # the drafter fills what it can read, says what it left, and D1-10 marks it short
    task = _task("title-block")
    for key in PEOPLE:
        del task.baseline["meta"][key]
    row = grounded.record_task(task, "vague")
    assert row["termination"] == "submit" and row["ungrounded"] == []
    assert set(row["lost"]) == {"D1-10"} and row["lost"]["D1-10"]["credit"] == 0.6
    assert not row["kept"]
    from roaddraft.eval.episode import Episode, EpisodeConfig
    episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level="vague"))
    episode.run()
    calls = [c for turn in episode.turns for c in turn["assistant"]["tool_calls"]]
    filled = next(c for c in calls if c["name"] == "fill_title_block")["params"]["fields"]
    assert not set(filled) & set(PEOPLE)
    assert ("leaving designed_by, drawn_by, checked_by and date blank"
            in calls[-1]["params"]["note"])


def test_an_explicit_title_block_letters_every_value_the_task_states():
    task, calls = _calls("title-block", "explicit", 1)
    sheets = task.brief.deliverable["sheets"]
    assert len(sheets) == 2
    filled = {c["params"]["sheet"]: c["params"]["fields"] for c in calls
              if c["name"] == "fill_title_block"}
    assert filled == {sh["name"]: sh["title_block_fields"] for sh in sheets}
    assert [c["params"]["space"] for c in calls if c["name"] == "insert_block"] == [
        sh["name"] for sh in sheets]


def test_a_curve_table_goes_only_on_a_sheet_that_shows_a_curve_and_lists_its_own():
    task, calls = _calls("curve-table", "vague")
    sheets = task.brief.deliverable["sheets"]
    assert [sh["curves"] for sh in sheets] == [[], [1]]  # the first sheet shows no curve
    placed = [c["params"] for c in calls if c["name"] == "place_curve_table"]
    assert [(p["space"], p["curves"]) for p in placed] == [(sheets[1]["name"], [1])]
    assert all(set(p) == {"space", "alignment", "position", "layer", "curves"} for p in placed)


# ------------------------------------------------------------ twisted sheets (2026-11-11)

#: the types of ``d1-train-twist`` the drafter covers: all nine
TWISTED = [name for name in tasksets.TWIST_TYPES if name in COVERED_TYPES]


def _twisted(ttype: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-train-twist")["tasks"] if e["task_type"] == ttype]
    return tasksets.task_from_entry(rows[n])


def _run(task, level: str):
    from roaddraft.eval.episode import Episode, EpisodeConfig
    episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level=level))
    episode.run()
    return episode


@pytest.mark.parametrize("ttype", TWISTED)
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_grounded_reference_on_a_twisted_sheet_scores_100_with_nothing_ungrounded(ttype, level):
    assert TWISTED == ["annotate-base", "annotate-sheet", "bearings", "curve-callouts",
                       "curve-table", "plan-sheet", "sheet-setup", "stationing", "title-block"]
    row = grounded.record_task(_twisted(ttype), level)
    assert row["termination"] == "submit", row["error"]
    assert row["ungrounded"] == []
    assert row["effective"] == 100.0 and row["lost"] == {}
    assert row["kept"]


def test_twisted_lettering_carries_the_turn_it_read_off_the_viewport():
    # the vague prompt says nothing of the twist: the drafter reads it off the sheet, and
    # every label goes down with it; no call carries a height, an offset or a side
    task = _twisted("annotate-sheet")
    twist = task.brief.deliverable["view_rotation"]
    assert "turned" not in task.brief.prompts["vague"]
    calls = [c for turn in _run(task, "vague").turns for c in turn["assistant"]["tool_calls"]]
    lettered = [c["params"] for c in calls if c["name"] in ("annotate_stationing", "place_label")]
    assert len(lettered) >= 3 and all(p["view_rotation"] == twist for p in lettered)
    assert all(not set(p) & {"height", "text_height", "label_offset", "side", "rotation"}
               for p in lettered)
    arrows = [c["params"] for c in calls if c["name"] == "insert_block"]
    assert arrows and all(p["rotation_deg"] == twist for p in arrows)
    assert f"{twist:g}° twist" in calls[-1]["params"]["note"]


def test_twisted_lettering_for_two_sheets_reads_the_second_sheet_too():
    # one sheet is read for the scale; when its viewport is turned the others are read as
    # well, since the model is lettered once for all of them
    task = next(tasksets.task_from_entry(e) for e in tasksets.load("d1-train-twist")["tasks"]
                if e["task_type"] == "stationing" and e["sheets"] == 2)
    turns = _run(task, "vague").turns
    read = [[c["params"]["sheet"] for c in t["assistant"]["tool_calls"]
             if c["name"] == "get_sheet_state"] for t in turns]
    assert [r for r in read if r] == [["C-101"], ["C-102"]]
    # an untwisted two-sheet task still reads only the first
    plain = next(tasksets.task_from_entry(e) for e in tasksets.load("d1-dev")["tasks"]
                 if e["task_type"] == "stationing" and e["sheets"] == 2)
    read = [c["params"]["sheet"] for t in _run(plain, "vague").turns
            for c in t["assistant"]["tool_calls"] if c["name"] == "get_sheet_state"]
    assert read == ["C-101"]


def test_a_twisted_curve_table_is_checked_against_what_the_sheet_shows_under_it():
    # the model's extents are no box on a turned sheet's paper: the table goes in the
    # corner, and the model under its box (and a quarter inch round it) is searched
    task = _twisted("curve-table")
    calls = [c for turn in _run(task, "vague").turns for c in turn["assistant"]["tool_calls"]]
    names = [c["name"] for c in calls]
    assert "get_extents" not in names and "model_to_sheet" not in names
    placed = names.index("place_curve_table")
    assert names[placed:] == ["place_curve_table", "get_entity", "sheet_to_model",
                              "sheet_to_model", "sheet_to_model", "sheet_to_model",
                              "find_entities", "submit"]
    search = calls[-2]["params"]
    assert set(search) == {"bounds", "visible_on"} and search["visible_on"] == "C-101"
    # the same job on an untwisted sheet goes by the extents, as before
    _task_, plain = _calls("curve-table", "vague")
    assert "get_extents" in [c["name"] for c in plain]
    assert "sheet_to_model" not in [c["name"] for c in plain]


def test_lettering_made_without_the_twist_is_not_kept_even_at_100():
    # the verifier lets a label made for the model through wherever it happens not to
    # plot upside down, so the keep rule looks at the twist itself (``twist_ignored``)
    from roaddraft.eval.agents.basic import _QueueAgent, calls_from_commands
    from roaddraft.tasks.reference import solution_commands

    class Blind(_QueueAgent):
        """The reference's commands with the twist taken out of the lettering."""
        name = "blind"

        def reset(self, task, level, mode):
            self.queue = calls_from_commands(
                [(name, {k: v for k, v in params.items() if k != "view_rotation"})
                 for name, params in solution_commands(task)])

    task = _twisted("curve-callouts")
    row = grounded.record_task(task, "vague", agent=Blind())
    assert row["effective"] == 100.0 and row["lost"] == {}
    assert row["twist_ignored"] and not row["kept"]
    # with the twist the same commands pass this leg, and an untwisted task has none
    assert grounded.record_task(task, "vague", agent=OracleAgent())["twist_ignored"] == []
    plain = grounded.record_task(_task("curve-callouts"), "vague", agent=Blind())
    assert plain["twist_ignored"] == []
    assert grounded.record_task(task, "vague")["twist_ignored"] == []


@pytest.mark.parametrize("ttype, tool", [("stationing", "annotate_stationing"),
                                         ("curve-table", "place_curve_table"),
                                         ("title-block", "fill_title_block"),
                                         ("sheet-setup", "create_viewport"),
                                         ("pavement-widths", "place_dimension")])
def test_the_audit_flags_the_plain_oracle(ttype, tool):
    """The oracle scores 100 and asks nothing, so its sizes, positions and
    points come from nowhere a model can see: right drawing, not training data."""
    row = grounded.record_task(_task(ttype), "vague", agent=OracleAgent())
    assert row["effective"] == 100.0 and not row["kept"]
    assert tool in {f["tool"] for f in row["ungrounded"]}


def test_the_drafter_is_handed_the_text_and_the_phases_and_nothing_else():
    agent = grounded.GroundedAgent()
    agent.reset(_task("bearings"), "vague", "single")
    kept = {k: v for k, v in vars(agent).items() if v not in (None, "", [])}
    assert kept == {"_phases": ["bearings"]}


def test_a_task_it_does_not_cover_ends_in_error_not_in_a_guess():
    row = grounded.record_task(_real("real-construction-callouts"), "vague")
    assert row["termination"] == "error" and "not covered" in row["error"] and not row["kept"]


def test_stated_alignment_reads_the_points_as_easting_northing():
    text = ("ALIGN-1 begins at N 11270.45, E 11269.90, station 69+00.00; PI-1 at N 11258.60, "
            "E 11591.68, R = 700.00'; ends at N 11236.37, E 13265.72; station equation "
            "74+00.00 BK = 79+00.00 AH. Create it and draw it.")
    assert grounded.stated_alignment(text) == {
        "name": "ALIGN-1", "begin_station": "69+00.00",
        "pis": [[11269.90, 11270.45], [11591.68, 11258.60, 700.0], [13265.72, 11236.37]],
        "equations": [{"back": "74+00.00", "ahead": "79+00.00"}]}
    assert grounded.stated_alignment("Station ALIGN-1.") is None


def test_stated_title_reads_the_shared_fields_and_who_did_what():
    text = ("Fill in the title blocks: project SR 260 WIDENING, agency STATE DOT DISTRICT 4, "
            "sheet title ROADWAY PLAN, sheets C-101 and C-102 of 2, designed and checked by RD, "
            "drawn by AGENT, dated 2026-01-17, scale 1\" = 40'. Put the NORTH_ARROW block in "
            "the upper right of each sheet on pp_PRESENTATION.")
    assert grounded.stated_title(text) == {
        "project": "SR 260 WIDENING", "agency": "STATE DOT DISTRICT 4",
        "sheet_title": "ROADWAY PLAN", "total_sheets": "2", "date": "2026-01-17",
        "scale": "1\" = 40'", "designed_by": "RD", "checked_by": "RD", "drawn_by": "AGENT",
        "sheet_numbers": "C-101 and C-102"}
    assert grounded.stated_title("Finish the title block on sheet C-101.") is None


# ------------------------------------------------------------ the sheets themselves (2026-11-11)

SHEET_SPEC = grounded.SPEC["sheet"]


def _pairs(episode):
    """Every call of an episode with its result."""
    return [(c, r) for turn in episode.turns
            for c, r in zip(turn["assistant"]["tool_calls"], turn["results"])]


def _two_sheets(ttype: str, source: str = "d1-dev"):
    return next(tasksets.task_from_entry(e) for e in tasksets.load(source)["tasks"]
                if e["task_type"] == ttype and e["sheets"] == 2)


def test_stated_layout_reads_what_the_task_gives_of_the_sheets():
    explicit = ("Lay out ALIGN-1 on two ANSI D plan sheets, C-101 and C-102, at 1\" = 50', "
                "breaking at station 150+00.00, with a viewport on each sheet turned -62.48° "
                "showing its part of the line. Draw a match line square across the centerline "
                "at 150+00.00, 100 ft each side, and label it at its end on each sheet.")
    assert grounded.stated_layout(explicit) == {
        "sheets": ["C-101", "C-102"], "breaks": ["150+00.00"], "size": "ANSI_D", "scale": 50.0,
        "twist": -62.48, "match_half_ft": 100.0}
    vague = ("Draft plan sheets C-101, C-102 and C-103 for ALIGN-1, breaking at stations "
             "83+00.00 and 94+00.00.")
    assert grounded.stated_layout(vague) == {
        "sheets": ["C-101", "C-102", "C-103"], "breaks": ["83+00.00", "94+00.00"], "size": None,
        "scale": None, "twist": 0.0, "match_half_ft": None}
    assert grounded.stated_layout("Station ALIGN-1.")["sheets"] == []


def test_stated_alignment_takes_the_name_from_where_the_task_gives_it():
    text = ("ALIGN-1 is not in the design yet: it begins at N 13600.23, E 16967.07, station "
            "121+00.00; PI-1 at N 13523.98, E 17270.64, R = 700.00'; ends at N 13553.10, "
            "E 19058.66. Create it, then draft plan sheet C-101 for it.")
    assert grounded.stated_alignment(text)["name"] == "ALIGN-1"


def test_a_sheet_is_laid_out_through_the_engine_and_centred_on_what_it_reports():
    # the office's plan viewport is set down, the engine is asked where the line falls on
    # the paper and which model point shows at its middle, and the view is centred there:
    # no centre is worked out by hand
    task = _task("sheet-setup")
    sheet = task.brief.deliverable["sheets"][0]
    pairs = _pairs(_run(task, "explicit"))
    names = [c["name"] for c, _r in pairs]
    frame = SHEET_SPEC["viewport"]
    made = next(c["params"] for c, _r in pairs if c["name"] == "create_viewport")
    assert [made[k] for k in ("center_paper", "width_in", "height_in")] == [
        frame["center_paper"], frame["width_in"], frame["height_in"]]
    assert made["feet_per_inch"] == sheet["viewport"]["feet_per_inch"]
    assert next(c["params"] for c, _r in pairs if c["name"] == "create_sheet") == {
        "name": sheet["name"], "size": sheet["size"]}
    assert (names.index("create_viewport") < names.index("model_to_sheet")
            < names.index("sheet_to_model") < names.index("modify_viewport"))
    given = next(r["point"] for c, r in pairs if c["name"] == "sheet_to_model")
    assert [c["params"]["changes"] for c, _r in pairs if c["name"] == "modify_viewport"] == [
        {"model_center": given}]
    # and both ends of the line are seen to show before it is called done
    assert [r["visible"] for c, r in pairs if c["name"] == "model_to_sheet"][-2:] == [True, True]


def test_a_scale_the_task_leaves_open_is_read_off_the_lettering_or_tried_from_the_offices():
    # a model already lettered tells the scale it was made for: one station number is read
    task, calls = _calls("sheet-setup", "vague")
    assert '1" =' not in task.brief.prompts["vague"]
    assert [c["params"] for c in calls if c["name"] == "find_entities"] == [
        {"type": "text", "anchor": {"kind": "station"}, "limit": 1}]
    made = next(c["params"] for c in calls if c["name"] == "create_viewport")
    assert made["feet_per_inch"] == task.brief.deliverable["feet_per_inch"]
    # with nothing lettered yet the larger of the office's scales is tried first; where the
    # line with room for its lettering is past the plan window the view goes to the next,
    # in the same call that centres it, and the lettering and the title follow the viewport
    task, calls = _calls("plan-sheet", "vague", 1)
    made = next(c["params"] for c in calls if c["name"] == "create_viewport")
    assert made["feet_per_inch"] == 40.0 == SHEET_SPEC["allowed_feet_per_inch"][0]
    changed = [c["params"]["changes"] for c in calls if c["name"] == "modify_viewport"]
    assert len(changed) == 1 and set(changed[0]) == {"feet_per_inch", "model_center"}
    assert changed[0]["feet_per_inch"] == 50.0
    assert [c["params"]["scale"] for c in calls if c["name"] == "set_annotation_scale"] == [50.0]
    assert next(c["params"]["fields"]["scale"] for c in calls
                if c["name"] == "fill_title_block") == "1\" = 50'"
    # where the first scale leaves the room, the view stays at it
    _task_, calls = _calls("plan-sheet", "vague", 0)
    changed = [c["params"]["changes"] for c in calls if c["name"] == "modify_viewport"]
    assert len(changed) == 1 and set(changed[0]) == {"model_center"}
    assert [c["params"]["scale"] for c in calls if c["name"] == "set_annotation_scale"] == [40.0]


def test_two_sheets_are_each_framed_round_their_stretch_and_joined_by_a_match_line():
    task = _two_sheets("sheet-setup")
    sheets = task.brief.deliverable["sheets"]
    cut = sheets[0]["matches"][0]
    calls = [c for c, _r in _pairs(_run(task, "explicit"))]
    frame = SHEET_SPEC["viewport"]
    # what each sheet shows of the lettering is read before its frame is trimmed
    seen = [c["params"]["visible_on"] for c in calls
            if c["name"] == "find_entities" and "visible_on" in c["params"]]
    assert seen == [sh["name"] for sh in sheets]
    trimmed = [c["params"]["changes"] for c in calls
               if c["name"] == "modify_viewport" and "width_in" in c["params"]["changes"]]
    assert len(trimmed) == 2
    assert all(ch["width_in"] < frame["width_in"] and ch["height_in"] < frame["height_in"]
               for ch in trimmed)
    # one match line, drawn by station and offset, and lettered on both sheets it joins
    half = cut["half_width_ft"]
    assert [c["params"]["points"] for c in calls if c["name"] == "draw_station_offset"] == [
        [f"{cut['station_text']}@{half:g}L", f"{cut['station_text']}@{half:g}R"]]
    lettered = {c["params"]["space"]: c["params"]["content"] for c in calls
                if c["name"] == "place_label"}
    assert lettered == {sh["name"]: sh["matches"][0]["label"] for sh in sheets}
    # no label is cut by a frame and none is off the paper: the verifier's own word
    for level in ("explicit", "vague"):
        row = grounded.record_task(task, level)
        assert row["kept"], (level, row["error"], row["lost"], row["ungrounded"])


def test_a_frame_that_reaches_past_its_view_is_read_again_from_its_middle():
    # the frame the lettering asks for can reach where the first view showed nothing; it is
    # not trusted until the view has been centred on it and the sheet read again
    task = _two_sheets("plan-sheet")
    episode = _run(task, "explicit")
    says = [turn["assistant"]["text"] for turn in episode.turns]
    assert sum("this frame reaches past that" in say for say in says) == 1
    reread = next(turn["assistant"]["tool_calls"] for turn in episode.turns
                  if turn["assistant"]["text"].startswith("Centre the view of"))
    assert [c["name"] for c in reread][:4] == ["modify_viewport", "find_entities",
                                               "model_to_sheet", "model_to_sheet"]
    assert set(reread[0]["params"]["changes"]) == {"model_center"}
    row = grounded.record_task(task, "explicit")
    assert row["kept"], (row["error"], row["lost"], row["ungrounded"])


def test_a_match_label_through_a_turned_viewport_runs_clear_of_its_line_the_first_time():
    # through this turned viewport the engine used to set the label from the end that ran
    # its text back across the centerline, and the drafter set it again from the other;
    # since training plan decision 13 the engine sets it from the end the paper wants
    task = _two_sheets("sheet-setup", "d1-train-twist")
    pairs = _pairs(_run(task, "explicit"))
    placed = [c["params"] for c, _r in pairs if c["name"] == "place_label"]
    assert len(placed) == 2 and all("halign" not in p for p in placed)
    assert all(p["side"] == "right" for p in placed)
    assert "delete_entities" not in [c["name"] for c, _r in pairs]
    row = grounded.record_task(task, "explicit")
    assert row["kept"], (row["error"], row["lost"], row["ungrounded"])


@pytest.mark.parametrize("ttype", ["plan-sheet", "create-plan-sheet", "base-plan-sheet"])
def test_a_whole_job_on_three_sheets_is_kept_well_inside_the_step_budget(ttype):
    from roaddraft.eval.budget import Budgets
    row = grounded.record_task(_hard(ttype, sheets=3), "vague")
    assert row["kept"], (row["termination"], row["error"], row["lost"], row["ungrounded"])
    assert row["steps"] <= Budgets().steps - 10


# ------------------------------------------------------------ the audit on made-up turns

TOOLS = [{"name": "place_label", "description": "kind is one of station, bearing, mc",
          "input_schema": {"properties": {"space": {"description": "'model' or a sheet"}}}},
         {"name": "draw_offset", "description": "", "input_schema": {}}]


def _turn(n, calls, results, text=""):
    return {"n": n, "assistant": {"text": text, "tool_calls": calls}, "results": results}


def test_audit_a_value_is_grounded_by_the_text_a_result_or_the_tool():
    turns = [
        _turn(1, [{"name": "get_design_data", "params": {"alignment": "ALIGN-1"}}],
              [{"ok": True, "rows": [{"ref": "T-1", "index": 1, "mid_station": 12661.2}]}]),
        _turn(2, [{"name": "place_label", "params": {"space": "model", "alignment": "ALIGN-1",
                                                     "anchor": "T-1", "kind": "bearing"}},
                  {"name": "draw_offset", "params": {"offsets": [-12.0, 12.0]}}],
              [{"ok": True}, {"ok": True}], text="ALIGN-1 has 1 tangent, two 12-ft lanes."),
    ]
    assert grounded.audit("Add bearings to ALIGN-1, two 12-ft lanes.", TOOLS, turns) == []


def test_audit_a_value_from_nowhere_is_reported_with_its_place():
    turns = [_turn(1, [{"name": "place_label", "params": {
        "space": "model", "alignment": "ALIGN-9", "anchor": "T-7", "height": 4.37,
        "position": [28.35, 2.67]}}], [{"ok": True}], text="The table goes at 28.35.")]
    found = grounded.audit("Add bearings to ALIGN-1.", TOOLS, turns)
    assert {(f["path"], f["value"]) for f in found} == {
        ("say", 28.35), ("alignment", "ALIGN-9"), ("anchor", "T-7"), ("height", 4.37),
        ("position[0]", 28.35), ("position[1]", 2.67)}


def test_audit_a_result_grounds_only_the_turns_after_it():
    call = {"name": "draw_offset", "params": {"offsets": [-17.25, 17.25]}}
    late = [_turn(1, [call], [{"ok": True, "half_width": 17.25}])]
    assert len(grounded.audit("Draw the edges.", TOOLS, late)) == 2
    early = [_turn(1, [{"name": "measure", "params": {}}], [{"ok": True, "half_width": 17.25}]),
             _turn(2, [call], [{"ok": True}])]
    assert grounded.audit("Draw the edges.", TOOLS, early) == []


def test_audit_reads_a_station_as_feet_and_a_referenced_alignment_by_its_parts():
    turns = [_turn(1, [{"name": "list_alignments", "params": {}}],
                   [{"ok": True, "alignments": [{"name": "ALIGN-1", "reference": "BASE"}]}]),
             _turn(2, [{"name": "place_label", "params": {"alignment": "BASE:ALIGN-1",
                                                          "anchor": 7300.0}}], [{"ok": True}])]
    assert grounded.audit("ALIGN-1 begins at station 73+00.00.", TOOLS, turns) == []
    assert grounded.numbers_in("at 73+00.00 and 125+50.5") [:2] == [7300.0, 12550.5]


def test_worked_sums_redoes_the_arithmetic_of_the_shown_work():
    text = "Inside the corner: 0.5 + 0.25 = 0.75; the frame ends at 11.7 + 5.67 / 2 = 14.535; 2 + 2 = 5."
    assert grounded.worked_sums(text) == [([0.5, 0.25], 0.75, True),
                                          ([11.7, 5.67, 2.0], 14.535, True),
                                          ([2.0, 2.0], 5.0, False)]


SHEET = {"ok": True, "sheet": {"usable_area": [0.5, 1.75, 33.5, 21.5],
                               "viewports": [{"feet_per_inch": 40.0}]}}
TABLE = {"name": "place_curve_table", "description": "", "input_schema": {}}
TITLE = {"name": "fill_title_block", "input_schema": {},
         "description": "Example: {\"sheet_title\":\"ROADWAY PLAN\",\"scale\":\"1\\\" = 50'\"}"}


def _placed(position, work):
    return [_turn(1, [{"name": "get_sheet_state", "params": {"sheet": "C-101"}}], [SHEET]),
            _turn(2, [{"name": "place_curve_table", "params": {"space": "C-101",
                                                               "position": position}}],
                  [{"ok": True}], text=work)]


def test_audit_a_number_worked_out_in_the_shown_work_is_grounded():
    work = "A quarter inch inside the corner: 0.5 + 0.25 = 0.75 and 21.5 - 0.25 = 21.25."
    assert grounded.audit("Put the curve data on sheet C-101.", [TABLE],
                          _placed([0.75, 21.25], work)) == []
    # the same position with no work shown, and with a sum that is wrong
    bare = grounded.audit("Put the curve data on sheet C-101.", [TABLE],
                          _placed([0.75, 21.25], "The table goes in the corner."))
    assert [(f["path"], f["value"]) for f in bare] == [("position[0]", 0.75),
                                                       ("position[1]", 21.25)]
    wrong = grounded.audit("Put the curve data on sheet C-101.", [TABLE],
                           _placed([28.35, 21.25], "33.5 - 4.9 = 28.35 and 21.5 - 0.25 = 21.25."))
    assert {f["path"] for f in wrong} == {"say", "position[0]"}  # 4.9 was never on the page


def _titled(fields):
    meta = {"ok": True, "summary": {"meta": {
        "project_name": "SR 260 WIDENING",
        "description": "SR 260 WIDENING \u2014 MERCER COUNTY, STATE DOT DISTRICT 4"}}}
    return [_turn(1, [{"name": "get_document_state", "params": {}},
                      {"name": "get_sheet_state", "params": {"sheet": "C-101"}}], [meta, SHEET]),
            _turn(2, [{"name": "fill_title_block", "params": {"sheet": "C-101",
                                                              "fields": fields}}], [{"ok": True}])]


def test_audit_a_title_block_value_is_read_off_the_document_or_it_is_from_nowhere():
    text = "Finish the title block on sheet C-101."
    read = {"project": "SR 260 WIDENING", "agency": "STATE DOT DISTRICT 4",
            "sheet_title": "ROADWAY PLAN", "sheet_number": "C-101", "scale": "1\" = 40'"}
    assert grounded.audit(text, [TITLE], _titled(read)) == []
    made_up = {"scale": "1\" = 60'", "designed_by": "RD", "date": "2026-11-09",
               "agency": "COUNTY ENGINEER"}
    found = grounded.audit(text, [TITLE], _titled(made_up))
    assert {f["path"] for f in found} == {"fields.scale", "fields.designed_by", "fields.date",
                                          "fields.agency"}


def test_audit_a_station_offset_point_and_a_match_label_are_grounded_by_their_parts():
    text = "Set up plan sheets C-101 and C-102 for ALIGN-1, breaking at station 150+00.00."
    tools = [{"name": "draw_station_offset", "description": "", "input_schema": {}},
             {"name": "place_label", "description": "kind is one of station, custom",
              "input_schema": {}}]

    def turn(points, content, work):
        return [_turn(1, [{"name": "draw_station_offset", "params": {"points": points}},
                          {"name": "place_label", "params": {"kind": "custom",
                                                             "content": content}}],
                      [{"ok": True}, {"ok": True}], text=work)]

    # two inches each side is the drafter's own; at the office's 50 ft to the inch, 100 ft
    good = turn(["150+00.00@100L", "150+00.00@100R"],
                "MATCH LINE STA 150+00.00 SEE SHEET C-102", "2 * 50 = 100 ft each side.")
    assert grounded.audit(text, tools, good) == []
    # a reach nothing gives, a station the task never named, a sheet that is not there
    bad = turn(["150+00.00@137L", "151+00.00@100R"],
               "MATCH LINE STA 152+00.00 SEE SHEET C-109", "2 * 50 = 100 ft each side.")
    assert {(f["path"], f["value"]) for f in grounded.audit(text, tools, bad)} == {
        ("points[0]", "150+00.00@137L"), ("points[1]", "151+00.00@100R"),
        ("content", "MATCH LINE STA 152+00.00 SEE SHEET C-109")}
    # and the form is the office's or it is free text like any other
    odd = turn(["150+00.00@100L", "150+00.00@100R"], "MATCH 150+00.00 TO C-102",
               "2 * 50 = 100 ft each side.")
    assert [f["path"] for f in grounded.audit(text, tools, odd)] == ["content"]


# ------------------------------------------------------------ the clearing step (2026-11-12)

#: the types of ``d1-train-crowd``: a sheet already set up, and model lettering asked for
CROWDED = ("annotate-base", "annotate-sheet", "bearings", "curve-callouts", "stationing")


def _crowded(ttype: str, twist: bool = False, n: int = 0):
    rows = [e for e in tasksets.load("d1-train-crowd")["tasks"]
            if e["task_type"] == ttype and bool(e.get("twist")) == twist]
    return tasksets.task_from_entry(rows[n])


def _kept_crowded(ttype: str, level: str, twist: bool = False):
    """The first crowded task of a type whose recording scores 100: ``(the task,
    its episode, the episode's result)``."""
    from roaddraft.eval.episode import Episode, EpisodeConfig
    for n in range(6):
        task = _crowded(ttype, twist, n)
        episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level=level))
        result = episode.run()
        if result.termination == "submit" and result.effective_score == 100.0:
            return task, episode, result
    raise AssertionError(f"no crowded {ttype} task of the first six is kept")


def test_the_line_the_request_names_is_the_one_drafted():
    assert grounded._named("Station ALIGN-1. The sheet is crowded.", ["ALIGN-2", "ALIGN-1"]) == "ALIGN-1"
    # a line reached through a reference is named by its own name
    assert grounded._named("Add the alignment data of ALIGN-1 to sheet C-101.",
                           ["BASE:ALIGN-2", "BASE:ALIGN-1"]) == "BASE:ALIGN-1"
    # the request names both: the first named is the one it is about
    assert grounded._named("Letter ALIGN-1; it already shows another line, ALIGN-2, across it.",
                           ["ALIGN-1", "ALIGN-2"]) == "ALIGN-1"
    assert grounded._named("Annotate it.", ["ALIGN-1", "ALIGN-2"]) == "ALIGN-1"


@pytest.mark.parametrize("ttype", CROWDED)
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_grounded_reference_on_a_crowded_sheet_scores_100_with_nothing_ungrounded(ttype, level):
    task, episode, result = _kept_crowded(ttype, level,
                                          twist=(ttype in ("bearings", "annotate-base")))
    assert grounded.audit(episode.brief_text, episode.tools, episode.turns) == []
    assert grounded.twist_ignored(task, episode.session.doc) == []
    assert result.steps <= 150


def test_a_label_that_lands_on_other_lettering_is_read_back_and_set_again_clear():
    """The step itself: the new lettering is read back with its boxes, the
    paper's own lettering beside it, and a label that meets something is
    deleted and placed again by the same labeler on the other side of its
    line or further off, then read back again."""
    task, episode, _result = _kept_crowded("stationing", "vague")
    pairs = _pairs(episode)
    names = [c["name"] for c, _r in pairs]
    lettered = names.index("annotate_stationing")
    listed = [(c, r) for c, r in pairs[lettered:] if c["name"] == "find_entities"]
    # read back: what the sheet shows from the model, whole, and what is on the paper
    assert listed[0][0]["params"] == {"visible_on": "C-101", "type": "text", "detail": "full",
                                      "limit": grounded.FULL_ROWS}
    assert listed[1][0]["params"]["space"] == "C-101"
    assert all(not r.get("truncated") for _c, r in listed)
    # set again: the label deleted, then the same label by the same labeler, with a side
    again = [(i, c) for i, (c, _r) in enumerate(pairs) if c["name"] == "place_label"]
    assert again
    made = pairs[lettered][1]["created"]
    for i, call in again:
        gone = pairs[i - 1][0]
        assert gone["name"] == "delete_entities"
        p = call["params"]
        assert p["space"] == "model" and p["alignment"] == "ALIGN-1"
        assert p["side"] in ("left", "right") and p["label_offset"] > 0
        assert p["kind"] in ("station", "pc", "pt") and p["content"]
    first_gone = pairs[again[0][0] - 1][0]["params"]["ids"]
    assert set(first_gone) <= set(made)  # what goes is what this drafter lettered
    # every label set again is read back before the work is handed in
    assert names[again[-1][0] + 1:].count("find_entities") >= 1
    note = pairs[-1][0]["params"]["note"]
    assert "checked the new lettering against what C-101 already showed" in note
    # and nothing that was handed over was touched
    from roaddraft.document.document import Document
    start = Document.from_dict(task.baseline)
    after = episode.session.doc
    assert set(start.model_entities) <= set(after.model_entities)
    assert set(start.sheet_by_ref("C-101").entities) <= set(after.sheet_by_ref("C-101").entities)


def test_two_boxes_that_meet_are_measured_along_and_across_the_line():
    """A box round lettering at an angle is mostly empty: where two meet, the
    one's corners are put in the terms of the other's line, and the longer
    label is the one taken from its record."""
    _task_, episode, _result = _kept_crowded("bearings", "vague")
    measured = [c for c, _r in _pairs(episode) if c["name"] == "xy_to_station"]
    assert measured and len(measured) % 4 == 0  # a box's four corners at a time
    said = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "apart across the line" in said or "apart along the line" in said or \
        "they overlap both ways" in said
    # a label's length is bounded from its box, or measured from it and its tangent's run
    # where a bound leaves the two meeting (2026-11-12), never guessed
    assert "no longer than" in said or "reads along its tangent, so it is" in said


def test_a_line_alone_on_its_sheet_is_not_read_back():
    # the engine's labelers set one line's lettering clear of itself; nothing else is there
    episode = _run(_task("stationing"), "vague")
    names = [c["name"] for c, _r in _pairs(episode)]
    assert "find_entities" not in names and "delete_entities" not in names
    assert "checked the new lettering" not in _pairs(episode)[-1][0]["params"]["note"]


def test_the_default_poses_alone_lose_on_a_crowded_sheet():
    # what the step is worth: the same drafter without it leaves its labels where they fell
    from roaddraft.eval.episode import Episode, EpisodeConfig

    task, _episode, _result = _kept_crowded("stationing", "vague")
    original = grounded._clear

    def no_clear(*args, **kwargs):
        return {"carry": "", "done": "left the lettering where it fell"}
        yield  # pragma: no cover (a generator, like the step it stands in for)

    grounded._clear = no_clear
    try:
        episode = Episode(task, grounded.GroundedAgent(), EpisodeConfig(level="vague"))
        result = episode.run()
    finally:
        grounded._clear = original
    assert result.termination == "submit" and result.effective_score < 100.0
    lost = {c.id for c in result.report.in_scope() if c.credit < 1.0}
    assert lost == {"D1-08"}



def test_a_meet_found_by_boxes_alone_is_measured_by_true_sizes_before_a_label_moves():
    """2026-11-12, the crowded bearings: a second line's bearing across this one's.
    By boxes the two meet wherever the label goes; measured by their true sizes
    (the length from the box, the height and the tangent's run, the corners by
    arithmetic along the label's own tangent) they clear, and every true length
    said is the engine's own."""
    import re
    from roaddraft.core import geometry as geo
    task = next(tasksets.task_from_entry(e) for e in tasksets.entries("d1-train-crowd")
                if e["task_id"] == "D1-014044-8bf2d1f16618")
    episode = _run(task, "vague")
    said = _words(episode)
    assert "Those meets rest on boxes" in said and "The true corners of" in said
    lengths = re.findall(r"(TX-\d+)(?:(?!TX-).)*?it reads (?:along|square to) its tangent, so it "
                         r"is (?:(?!TX-).)*? = ([\d.]+) ft long", said)
    assert lengths
    # each text as it was read (a label set again is gone from the finished drawing)
    read = {row["id"]: row["entity"] for _c, r in _pairs(episode)
            for row in r.get("entities") or [] if row.get("entity")}
    for tid, length in lengths:
        e = read[tid]
        assert abs(float(length) - geo.text_size(e["content"], e["height"])[0]) < 0.01, tid
    row = grounded.record_task(task, "vague")
    assert row["kept"], (row["error"], row["lost"], row["ungrounded"])


# ------------------------------------------------------------ a revised design (2026-11-12)


def _revised(ttype: str, kind: str, n: int = 0):
    rows = [e for e in tasksets.load("d1-train-revise")["tasks"]
            if e["task_type"] == ttype and e["revise"] == kind and "dialed" not in e]
    return tasksets.task_from_entry(rows[n])


def test_stated_revision_reads_the_change_the_designer_reports():
    assert grounded.stated_revision(
        "curve 2's radius is now 900' (it was 650'), every PI held")["kind"] == "radius"
    assert grounded.stated_revision(
        "the PI of curve 1 has moved 24.42 ft ahead along its back tangent")["kind"] == "pi"
    assert grounded.stated_revision(
        "ALIGN-1 is restationed to begin at 140+25.00 (it began at 140+00.00)")["kind"] == "station"
    assert grounded.stated_revision("Station ALIGN-1.") is None


@pytest.mark.parametrize("ttype", ["annotate-base", "annotate-sheet"])
@pytest.mark.parametrize("kind", ["radius", "pi", "station"])
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_grounded_reference_on_a_revised_sheet_scores_100_with_nothing_left_stale(ttype, kind,
                                                                                    level):
    row = grounded.record_task(_revised(ttype, kind), level)
    assert row["termination"] == "submit", row["error"]
    assert row["ungrounded"] == [] and row["left_stale"] == []
    assert row["effective"] == 100.0 and row["kept"]


def test_a_revision_takes_off_the_old_lettering_and_restations_a_note_from_its_tick():
    """The step: what was lettered from the line is found by its anchor and taken
    off, its drawn centerline left; a note citing the line is restationed from
    the old tick at the whole station before it, taken to the revised line."""
    from roaddraft.document.document import Document
    task = _revised("annotate-base", "radius")
    R = task.brief.deliverable["revision"]
    episode = _run(task, "vague")
    pairs = _pairs(episode)
    names = [c["name"] for c, _r in pairs]
    found = next(c for c, _r in pairs if c["name"] == "find_entities")
    assert found["params"]["anchor"] == {"alignment": "BASE:ALIGN-1"}
    gone = next(c for c, _r in pairs if c["name"] == "delete_entities")["params"]["ids"]
    assert sorted(gone) == sorted(R["stale"])
    start = Document.from_dict(task.baseline)
    assert not any(start.model_entities[i].anchor.get("kind") in ("element", "offset")
                   for i in gone if i in start.model_entities)  # linework is never taken off
    # each note: the tick's point taken to the revised line, then the note restationed
    asked = [c for c, _r in pairs if c["name"] == "xy_to_station"]
    assert len(asked) == len(R["notes"])
    restationed = {c["params"]["id"]: c["params"]["changes"]["content"]
                   for c, _r in pairs if c["name"] == "modify_entity"}
    assert restationed == {n["id"]: n["after"] for n in R["notes"] if n["after"] != n["before"]}
    # nothing is lettered again before the old lettering is off
    assert names.index("delete_entities") < names.index("annotate_stationing")


def test_a_restation_keeps_the_curve_table_and_a_geometry_change_does_not():
    for kind, table in (("station", False), ("radius", True)):
        episode = _run(_revised("annotate-base", kind), "vague")
        names = [c["name"] for c, _r in _pairs(episode)]
        assert ("place_curve_table" in names) == table, kind


def test_audit_a_note_restationed_is_grounded_only_by_a_station_worked_out():
    text = "THE TASK:\nBring sheet C-101 up to date."
    read = _turn(1, [{"name": "get_sheet_state", "params": {"sheet": "C-101"}}],
                 [{"ok": True, "sheet": {"entities": {"TX-017": {
                     "type": "text", "content": "CONFORM STA 147+40.00"}}}}])
    worked = _turn(2, [{"name": "modify_entity", "params": {
        "id": "TX-017", "changes": {"content": "CONFORM STA 147+65.32"}}}], [{"ok": True}],
        text="14740 - 14700 = 40 and 14725.317 + 40 = 14765.317")
    guessed = _turn(2, [{"name": "modify_entity", "params": {
        "id": "TX-017", "changes": {"content": "CONFORM STA 147+65.32"}}}], [{"ok": True}])
    reworded = _turn(2, [{"name": "modify_entity", "params": {
        "id": "TX-017", "changes": {"content": "CONFORM AT STA 147+40.00"}}}], [{"ok": True}])
    tick = {"ok": True, "station": 14725.317, "anchor": {"station": 14700.0}}
    read["results"][0]["sheet"]["tick"] = tick
    assert grounded.audit(text, [], [read, worked]) == []
    assert [f["value"] for f in grounded.audit(text, [], [read, guessed])] == [
        "CONFORM STA 147+65.32"]
    assert [f["value"] for f in grounded.audit(text, [], [read, reworded])] == [
        "CONFORM AT STA 147+40.00"]


def test_a_restation_moves_every_note_by_the_stated_shift_with_no_tick_needed():
    task = _revised("annotate-base", "station")
    R = task.brief.deliverable["revision"]
    episode = _run(task, "vague")
    pairs = _pairs(episode)
    assert not any(c["name"] == "xy_to_station" for c, _r in pairs)
    restationed = {c["params"]["id"]: c["params"]["changes"]["content"]
                   for c, _r in pairs if c["name"] == "modify_entity"}
    assert restationed == {n["id"]: n["after"] for n in R["notes"]}
    said = " ".join(turn["assistant"]["text"] for turn in episode.turns)
    assert "the same for every station of it" in said


def test_where_the_design_lives_in_the_file_the_drafter_makes_the_change_and_the_labels_follow():
    """Robert, 2026-11-12: "Yes, revision only". modify_alignment changes the line,
    redraws its centerline and brings its labels along; update_labels checks
    nothing is out of step; each note is restationed from its own point before
    and after the change.  Nothing is taken off or lettered again."""
    for kind in ("radius", "pi", "station"):
        task = _revised("annotate-sheet", kind)
        R = task.brief.deliverable["revision"]
        episode = _run(task, "vague")
        pairs = _pairs(episode)
        names = [c["name"] for c, _r in pairs]
        made = next(c for c, _r in pairs if c["name"] == "modify_alignment")["params"]
        assert made["name"] == "ALIGN-1" and made["redraw"] is True
        new = task.brief.design["alignments"]["ALIGN-1"]
        if kind == "station":
            assert made["changes"] == {"begin_station": R["to"]}
        else:  # the PIs as the drafter worked them out are the revised design's, to the bit
            want = [list(p["point"]) + ([p["radius"]] if p.get("radius") else [])
                    for p in new["pis"]]
            assert made["changes"]["pis"] == want
        assert names.index("modify_alignment") < names.index("update_labels")
        assert not {"delete_entities", "annotate_stationing", "place_label",
                    "place_curve_table"} & set(names)
        before = [i for i, n in enumerate(names) if n == "station_to_xy"]
        assert len(before) == len(R["notes"]) and max(before) < names.index("modify_alignment")
        restationed = {c["params"]["id"]: c["params"]["changes"]["content"]
                       for c, _r in pairs if c["name"] == "modify_entity"}
        assert restationed == {n["id"]: n["after"] for n in R["notes"] if n["after"] != n["before"]}
        assert episode.result if hasattr(episode, "result") else True


# ------------------------------------------------------------ the width dimensions


def _train(task_id: str):
    return next(tasksets.task_from_entry(e) for e in tasksets.entries("d1-train")
                if e["task_id"] == task_id)


def _measured(task, episode):
    """Each width dimension the drafter placed: ``(the station its points stand at,
    the station of its line point)``, raw, along the task's line."""
    from roaddraft.design.horizontal import Alignment
    from roaddraft.document.entities import Dimension
    line = Alignment.from_dict(task.brief.design["alignments"][task.brief.alignment_name])
    out = []
    for e in episode.session.doc.model_entities.values():
        if isinstance(e, Dimension):
            a, b = line.xy_to_station(e.p1), line.xy_to_station(e.p2)
            assert abs(a["station"] - b["station"]) < 1e-6 and abs(a["offset"] + b["offset"]) < 1e-6
            out.append((a["station"], line.xy_to_station(e.line_point)["station"]))
    return sorted(out)


def _words(episode) -> str:
    return " ".join(turn["assistant"]["text"] or "" for turn in episode.turns)


def test_a_width_is_measured_between_the_edges_at_one_fraction_along_each():
    """place_dimension takes the two pavement edges of the tangent and the same
    fraction along each, so the engine finds the points; the annotation scale
    sizes the text, so no size is worked out by hand."""
    task = _task("pavement-widths")
    episode = _run(task, "vague")
    pairs = _pairs(episode)
    edges = {row["id"]: row["anchor"] for c, r in pairs
             if c["name"] == "find_entities" and (c["params"].get("anchor") or {}).get("kind") == "offset"
             for row in r["entities"]}
    dims = [c["params"] for c, _r in pairs if c["name"] == "place_dimension"]
    assert len(dims) == len(task.brief.deliverable["width_dimensions"])
    for d in dims:
        first, second = edges[d["from_entity"]], edges[d["to_entity"]]
        assert first["ref"] == second["ref"] and first["ref"].startswith("T-")
        # the BC and EC labels are on the left, so the right edge goes second and the
        # text, which does not fit between the edges, goes out on the right
        assert float(first["offset"]) < 0 < float(second["offset"]) == -float(first["offset"])
        assert d["from_at"] == d["to_at"] and 0 < d["from_at"] < 1
        assert not {"text_height", "text_gap", "p1", "p2"} & set(d)
    assert "set_annotation_scale" in [c["name"] for c, _r in pairs]
    assert "went out on the right" in _words(episode)


def test_a_stated_width_past_a_station_equation_is_measured_where_it_lies_along_the_line():
    """The task states display stations; past an equation a station reads more (or
    less) than its distance along the line, worked out from the equation's own
    numbers, never from a station rounded to the hundredth."""
    task = _task("pavement-widths")  # two sheets, a station equation
    assert task.brief.design["alignments"]["ALIGN-1"]["equations"]
    episode = _run(task, "explicit")
    want = sorted(float(w["station"]) for w in task.brief.deliverable["width_dimensions"])
    got = [s for s, _line in _measured(task, episode)]
    assert len(got) == len(want) and all(abs(g - w) <= 0.005 for g, w in zip(got, want))
    assert "past the station equation" in _words(episode)
    row = grounded.record_task(task, "explicit")
    assert row["kept"], (row["error"], row["lost"], row["ungrounded"])


def test_a_dimension_line_that_would_cross_a_label_moves_off_it_and_keeps_its_station():
    """On a short tangent the stated station sits inside the bearing's stretch of the
    line: the measured points stay at the station and the dimension line moves
    half a text height past the bearing's end."""
    task = _train("D1-010073-e1791f7c6ead")
    episode = _run(task, "explicit")
    measured = _measured(task, episode)
    want = sorted(float(w["station"]) for w in task.brief.deliverable["width_dimensions"])
    assert [round(s, 2) for s, _line in measured] == [round(w, 2) for w in want]
    moved = [(s, line) for s, line in measured if abs(line - s) > 0.5]
    assert moved and all(abs(line - s) < 30.0 for s, line in moved)
    assert "move ahead past its end, half a text height clear" in _words(episode)
    row = grounded.record_task(task, "explicit")
    assert row["kept"], (row["error"], row["lost"], row["ungrounded"])


def test_a_vague_width_takes_the_half_station_nearest_the_middle_that_clears():
    """The office's standard place, the half station nearest the tangent's middle,
    where the bearing lettered at the middle does not take it; else the next."""
    task = _train("D1-010027-f26329d74e60")  # one sheet, 140+00 BK = 145+00 AH
    episode = _run(task, "vague")
    stations = [round(s, 2) for s, line in _measured(task, episode)]
    # 136+50 and, past the equation, 146+50 (14150 along the line): the half stations
    # nearest each middle hold the bearings
    assert stations == [13650.0, 14150.0]
    words = _words(episode)
    assert "The half station 13550: a line at 13550 would cross the bearing at T-1" in words
    assert "The half station 13650 (13550 + 100 = 13650) is clear" in words
    assert ("The half station 14650 (14550 + 100 = 14650, 14650 - 14500 + 14000 = 14150 along "
            "the line, past the station equation at 14000) is clear") in words


def test_a_label_along_a_tangent_is_judged_by_its_true_length_not_its_box():
    """A label at an angle has a box far longer than itself; its true length comes
    from the box, its height and the tangent's run, and is the engine's own."""
    import re
    from roaddraft.core import geometry as geo
    task = _train("D1-010011-cddea4aa1af3")
    episode = _run(task, "vague")
    doc = episode.session.doc
    found = re.findall(r"The bearing at T-\d+, (TX-\d+) reads along T-\d+; .*? = ([\d.]+) ft long",
                       _words(episode))
    assert len(found) == 4
    for tid, length in found:
        e = doc.model_entities[tid]
        assert abs(float(length) - geo.text_size(e.content, e.height)[0]) < 0.01


def test_a_width_text_a_frame_would_cut_is_set_again_where_a_view_shows_it_whole():
    """On a layout of two sheets a frame can run through the place where the text
    lands: the text's box is worked out from the record and the engine's warning
    and checked against each view, and the dimension is set again."""
    task = _train("D1-011195-a1edad034910")
    for level in ("vague", "explicit"):
        episode = _run(task, level)
        words = _words(episode)
        assert "which would cut the text" in words and "Take off DM-" in words
        row = grounded.record_task(task, level)
        assert row["kept"], (level, row["error"], row["lost"], row["ungrounded"])


def test_a_whole_plan_with_widths_on_three_sheets_is_kept_inside_the_step_budget():
    from roaddraft.eval.budget import Budgets
    task = _hard("plan-sheet-pavement", sheets=3)
    row = grounded.record_task(task, "vague")
    assert row["kept"], (row["termination"], row["error"], row["lost"], row["ungrounded"])
    assert row["steps"] <= Budgets().steps
    episode = _run(task, "vague")
    assert "A width dimension is framed round its own box" in _words(episode)


def test_a_station_as_lettered_is_found_along_the_line_past_an_equation():
    line = {"begin_station": 4700.0, "end_station": 6400.0,
            "equations": [{"raw_station": 5900.0, "back": 5900.0, "ahead": 6100.0}]}
    eq = line["equations"][0]
    assert grounded._to_raw(5350.0, line, 4700.0, 6400.0) == [(5350.0, None)]
    assert grounded._to_raw(6550.0, line, 4700.0, 6400.0) == [(6350.0, eq)]
    assert grounded._to_raw(6000.0, line, 4700.0, 6400.0) == []  # the gap the equation skips
    assert grounded._to_raw(6550.0, line, 4700.0, 6000.0) == []  # off the stretch asked about
    back = {"begin_station": 0.0, "end_station": 1000.0,
            "equations": [{"raw_station": 500.0, "back": 500.0, "ahead": 400.0}]}
    assert [raw for raw, _q in grounded._to_raw(450.0, back, 0.0, 1000.0)] == [450.0, 550.0]


def test_audit_a_size_the_tool_gives_as_a_ratio_of_the_text_height_is_grounded():
    dim = {"name": "place_dimension", "description": "",
           "input_schema": {"properties": {"arrow_size": {
               "description": "arrowhead length (default 1.2 x the text height)"}}}}
    turns = [_turn(1, [{"name": "get_sheet_state", "params": {"sheet": "C-101"}}], [SHEET]),
             _turn(2, [], [], text="An arrowhead is 1.2 * 40 = 48 ft.")]
    text = "Dimension the width on C-101."
    assert grounded.audit(text, [dim], turns) == []
    assert {f["value"] for f in grounded.audit(text, TOOLS, turns)} == {1.2, 48.0}
