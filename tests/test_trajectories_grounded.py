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


def test_the_covered_types_are_the_eight_single_phase_ones():
    assert COVERED_TYPES == ["attach-reference", "bearings", "create-alignment", "curve-callouts",
                             "draw-alignment", "layer-setup", "pavement-edges", "stationing"]
    assert grounded.covers(_task("stationing")) == []
    assert "table" in grounded.covers(_task("plan-sheet"))


@pytest.mark.parametrize("ttype", COVERED_TYPES)
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_a_grounded_reference_scores_100_with_nothing_ungrounded(ttype, level):
    row = grounded.record_task(_task(ttype), level)
    assert row["termination"] == "submit", row["error"]
    assert row["effective"] == 100.0
    assert row["ungrounded"] == []
    assert row["kept"]


@pytest.mark.parametrize("ttype, tool", [("stationing", "annotate_stationing"),
                                         ("curve-table", "place_curve_table"),
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
    row = grounded.record_task(_task("curve-table"), "vague")
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
