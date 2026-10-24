"""Task types and two-sheet layouts (decided 2026-10-10): a task starts from a
document with some drafting done and asks for one piece of work; only the
checks that work drives are graded, renormalised to 100; a two-sheet layout
breaks at a match line that D1-00 wants drawn and labelled on each sheet."""
from __future__ import annotations

import pytest

from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Text
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.prompts import LEVELS
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import (
    CHECK_GROUPS, GROUPS, LAYOUT_GROUPS, REAL_TASK_TYPES, TASK_TYPES, checks_in_scope, task_type,
)
from roaddraft.verify import check_groups, verify
from roaddraft.verify.checks import EXTRA_CHECKS
from tests.verify_mutations import Base
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1 as _SPEC
_L = _SPEC["layers"]

WEIGHTS = {c["id"]: c["weight"] for c in DRAFTING_SPEC_V1["checks"]}
TYPES = sorted(TASK_TYPES)
#: a two-sheet seed whose alignment puts a curve on each sheet (two curve tables)
TWO_TABLE_SEED = next(sd for sd in range(1, 30)
                      if len(generate_task(sd, curves=[1, 2, 3][sd % 3], equations=bool(sd % 2),
                                           sheets=2).truth.curve_tables) == 2)


def _drafted(seed, ttype, sheets):
    task = generate_task(seed, curves=[1, 2, 3][seed % 3], equations=bool(seed % 2),
                         task_type=ttype, sheets=sheets)
    session = session_for_task(task)
    reference_solution(task, session)
    return task, session


# ---------------------------------------------------------------- the catalog


def test_every_group_is_asked_for_by_some_type_and_plan_sheet_asks_for_the_layout():
    # the seeded types ask for every group but the notes, which a real sheet's
    # construction-callout type asks for
    assert set(GROUPS) - {"notes"} == {g for t in TASK_TYPES.values() for g in t.asks}
    assert set(GROUPS) == {g for t in (*TASK_TYPES.values(), *REAL_TASK_TYPES.values())
                           for g in t.asks}
    assert task_type("plan-sheet").asks == frozenset(LAYOUT_GROUPS)
    assert task_type("plan-sheet").given == frozenset({"design"})  # the design is handed over
    assert task_type("annotate-base").design_referenced and task_type("annotate-base").start == "sheet"
    assert task_type("annotate-base").solution_phases() == ["stationing", "bearings", "callouts", "table"]
    assert task_type("attach-reference").basefile == {"linework", "edges", "stationing",
                                                       "bearings", "callouts"}
    assert task_type("attach-reference").solution_phases() == ["reference"]
    assert task_type("pavement").solution_phases() == ["edges", "widths"]
    assert task_type("create-alignment").solution_phases() == ["design", "linework"]
    assert "design" in task_type("plan-sheet").given and "design" not in task_type(
        "create-alignment").given
    assert "design" not in task_type("plan-sheet").shown()  # seeded, never drafted
    assert task_type("annotate-sheet").given == {"design", "layers", "linework", "sheet"}
    assert task_type("draw-alignment").start == "model" and task_type("bearings").start == "sheet"
    assert set(DRAFTING_SPEC_V1["task_types"]) == set(TASK_TYPES)
    with pytest.raises(ValueError, match="unknown task type"):
        task_type("coffee")


def test_checks_in_scope_follow_the_groups():
    ids = list(WEIGHTS)
    assert checks_in_scope([], ids) == ids
    assert checks_in_scope(["bearings"], ids) == ["D1-05", "D1-07", "D1-08", "D1-09"]
    assert checks_in_scope(["linework"], ids) == ["D1-01", "D1-09"]
    # the north arrow's level is judged (D1-09) along with its presence (D1-11)
    assert checks_in_scope(["title", "north"], ids) == ["D1-08", "D1-09", "D1-10", "D1-11"]
    assert checks_in_scope(["sheet"], ids) == ["D1-00", "D1-08"]
    # ... and the match level only on a two-sheet layout
    two = check_groups(generate_task(TWO_TABLE_SEED, sheets=2).truth)
    assert checks_in_scope(["sheet"], ids, two) == ["D1-00", "D1-08", "D1-09"]
    assert checks_in_scope(["sheet"], ids, check_groups(generate_task(1).truth)) == ["D1-00", "D1-08"]
    assert checks_in_scope(["edges"], ids) == ["D1-09", "D1-12"]
    assert checks_in_scope(["widths"], ids) == ["D1-08", "D1-09", "D1-13"]
    assert checks_in_scope(["reference"], ids) == ["D1-14"]
    assert checks_in_scope(["layers"], ids) == ["D1-09"]
    assert checks_in_scope(["design"], ids) == ["D1-15"]
    # the verifier's own check joins only for a scope that asks for its group
    extra = [c["id"] for c in EXTRA_CHECKS]
    assert checks_in_scope(["notes"], ids + extra) == ["D1-08", "D1-16"]
    assert checks_in_scope(["bearings"], ids + extra) == ["D1-05", "D1-07", "D1-08", "D1-09"]
    assert set(CHECK_GROUPS) == set(ids) | set(extra)


# --------------------------------------------------------- oracle and null


@pytest.mark.parametrize("sheets", [1, 2])
@pytest.mark.parametrize("ttype", TYPES)
def test_reference_scores_100_and_the_starting_document_0(ttype, sheets):
    refused = []
    for seed in (1, 2, 3, 4, 5, 6):
        try:
            task, session = _drafted(seed, ttype, sheets)
        except ValueError:
            # a widths type on a layout with no tangent that has room for a dimension
            # beside its bearing (seed 5: three curves and an equation on one sheet);
            # the task-set builder takes the next type there
            refused.append(seed)
            continue
        assert task.truth.scope == sorted(task_type(ttype).asks, key=GROUPS.index)
        assert task.brief.task_type == ttype and task.brief.sheets == sheets
        assert len(task.truth.sheets) == sheets
        base = Document.from_dict(task.baseline)
        for level in LEVELS:
            r = verify(session.doc, task.truth, prompt_level=level)
            assert r.effective_score == 100.0 and not r.all_findings(), (
                seed, ttype, sheets, level, [f.to_dict() for f in r.all_findings()])
            assert r.scope == task.truth.scope
            assert {c.id for c in r.in_scope()} == set(
                checks_in_scope(r.scope, list(WEIGHTS), check_groups(task.truth)))
            assert r.scope_weight == sum(WEIGHTS[c.id] for c in r.in_scope())
            r0 = verify(base, task.truth, prompt_level=level)
            assert r0.effective_score == 0.0 and not r0.hard_failed, (seed, ttype, sheets, level)
    assert refused == ([5] if "widths" in task_type(ttype).asks and sheets == 1 else []), (
        ttype, sheets, refused)


def test_starting_documents_carry_exactly_the_given_phases():
    for ttype in TYPES:
        task = generate_task(7, curves=2, equations=True, task_type=ttype)
        doc = Document.from_dict(task.baseline)
        given = task_type(ttype).given
        assert bool(doc.sheets) == ("sheet" in given)
        assert (len(doc.layers) > 1) == ("layers" in given)
        kinds = {e.anchor["kind"] for e in doc.model_entities.values() if e.anchor}
        assert ("element" in kinds) == ("linework" in given)
        assert ("tick" in kinds) == ("stationing" in given)
        assert ("bearing" in kinds) == ("bearings" in given)
        assert ("mc" in kinds) == ("callouts" in given)
        if doc.sheets:
            sheet = next(iter(doc.sheets.values()))
            assert any(e.TYPE == "table" for e in sheet.entities.values()) == ("table" in given)
            assert any(e.TYPE == "blockref" for e in sheet.entities.values()) == ("north" in given)
            assert bool(sheet.title_block_fields) == ("title" in given)
        if "design" in given:
            assert doc.design.fingerprint() == task.truth.design_fingerprint
        else:
            assert doc.design.alignments == {} and task.brief.design["profiles"] == {}


def test_task_ids_differ_by_type_and_sheets():
    ids = {generate_task(1, task_type=t, sheets=s).task_id for t in TYPES for s in (1, 2)}
    assert len(ids) == 2 * len(TYPES)


# ------------------------------------------------------------- renormalising


def test_a_bearings_task_scores_only_its_checks_on_100():
    task, session = _drafted(1, "bearings", 1)
    b = Base.__new__(Base)
    b.task, b.session, b.truth, b.D, b.A = task, session, task.truth, task.brief.deliverable, "ALIGN-1"
    n = len(b.labels("bearing"))
    b.ex("delete_entities", {"ids": [b.labels("bearing")[0].id]})
    r = b.verify()
    assert [c.id for c in r.in_scope()] == ["D1-05", "D1-07", "D1-08", "D1-09"]
    assert r.scope_weight == 30
    assert r.check("D1-05").credit == pytest.approx((n - 1) / n)
    assert r.check("D1-07").credit == 1.0 and r.check("D1-08").credit == 1.0
    assert r.check("D1-09").credit == 1.0  # the bearings left are on the right layer and height
    assert r.rubric_score == pytest.approx(100.0 * (10 * (n - 1) / n + 8 + 6 + 6) / 30, abs=1e-3)
    # a wrong bearing hard-fails the task
    e = b.labels("bearing")[0]
    flipped = (e.content.replace(" E ", " W ") if " E " in e.content
               else e.content.replace(" W ", " E "))  # the quadrant, not the length
    b.ex("modify_entity", {"id": e.id, "changes": {"content": flipped}})
    assert b.verify().effective_score == 0.0


def test_given_work_is_not_graded_in_a_partial_task():
    task, session = _drafted(2, "curve-callouts", 1)
    b = Base.__new__(Base)
    b.task, b.session, b.truth, b.D, b.A = task, session, task.truth, task.brief.deliverable, "ALIGN-1"
    # wreck the given stationing and bearings: out of scope, no effect
    b.ex("delete_entities", {"ids": [e.id for e in b.labels("station")[:5]]
                             + [e.id for e in b.labels("bearing")]})
    assert b.verify().effective_score == 100.0
    # but the asked-for callouts count
    b.ex("delete_entities", {"ids": [b.labels("mc")[0].id]})
    r = b.verify()
    n = b.truth.counts["curves"]
    assert r.check("D1-04").credit == pytest.approx((n - 1) / n)
    assert r.effective_score < 100.0


def test_draw_alignment_task_is_linework_and_standards_only():
    task, session = _drafted(3, "draw-alignment", 1)
    r = verify(session.doc, task.truth)
    assert [c.id for c in r.in_scope()] == ["D1-01", "D1-09"] and r.scope_weight == 16
    assert r.effective_score == 100.0
    # the agent's view shows only the checks in play
    assert [c["id"] for c in r.agent_view()["checks"]] == ["D1-01", "D1-09"]


# ------------------------------------------------------------- two sheets


def _two_sheet(seed=TWO_TABLE_SEED, ttype="plan-sheet"):
    task, session = _drafted(seed, ttype, 2)
    b = Base.__new__(Base)
    b.task, b.session, b.truth, b.D, b.A = task, session, task.truth, task.brief.deliverable, "ALIGN-1"
    return b


def _match_line(b):
    m = b.truth.sheets[0]["matches"][0]
    for e in b.doc.model_entities.values():
        if isinstance(e, Line) and e.anchor is None and abs(
                (e.start[0] + e.end[0]) / 2 - (m["start"][0] + m["end"][0]) / 2) < 1e-6:
            return e, m
    raise AssertionError("no match line")


def test_two_sheet_truth_shape():
    b = _two_sheet()
    t = b.truth
    assert [s["name"] for s in t.sheets] == ["C-101", "C-102"]
    assert t.sheets[0]["station_range"][1] == t.sheets[1]["station_range"][0]
    assert t.sheets[0]["matches"][0]["other_sheet"] == "C-102"
    assert t.sheets[1]["matches"][0]["other_sheet"] == "C-101"
    assert t.sheets[0]["matches"][0]["station"] == t.sheets[1]["matches"][0]["station"]
    assert t.counts["match_lines"] == 1 and t.counts["sheets"] == 2
    curves = sorted(c for tb in t.curve_tables for c in tb["curves"])
    assert curves == list(range(1, t.counts["curves"] + 1))  # every curve tabled once
    for tb in t.curve_tables:
        assert len(tb["rows"]) == len(tb["curves"])
    fields = [s["title_block_fields"] for s in t.sheets]
    assert fields[0]["sheet_number"] == "C-101" and fields[0]["total_sheets"] == "2"
    assert fields[1]["sheet_number"] == "C-102"


def test_match_line_deleted_costs_both_sheets_their_match_line_credit():
    b = _two_sheet()
    line, m = _match_line(b)
    b.ex("delete_entities", {"ids": [line.id]})
    r = b.verify()
    assert r.check("D1-00").credit == pytest.approx(0.9)  # 0.2 x 0.5 on each of two sheets
    codes = [(f.code, f.anchor["kind"]) for f in r.check("D1-00").findings]
    assert codes == [("missing", "match_line"), ("missing", "match_line")]
    assert r.effective_score == pytest.approx(100.0 - 0.5)


def test_match_label_wrong_or_missing_on_one_sheet():
    b = _two_sheet()
    sheet = b.doc.sheet_by_ref("C-101")
    label = next(e for e in sheet.entities.values()
                 if isinstance(e, Text) and e.anchor and e.anchor["kind"] == "custom")
    b.ex("modify_entity", {"id": label.id, "changes": {"content": label.content.replace(
        "C-102", "C-103")}})
    r = b.verify()
    assert r.check("D1-00").credit == pytest.approx(0.95)
    assert [f.code for f in r.check("D1-00").findings] == ["wrong_value"]
    assert not r.hard_failed  # D1-00 is not a hard-fail check
    b.ex("delete_entities", {"ids": [label.id]})
    r = b.verify()
    assert r.check("D1-00").credit == pytest.approx(0.95)
    assert [f.code for f in r.check("D1-00").findings] == ["missing"]


def test_vague_level_reads_the_match_label_by_meaning_and_takes_any_long_line():
    b = _two_sheet()
    sheet = b.doc.sheet_by_ref("C-101")
    label = next(e for e in sheet.entities.values()
                 if isinstance(e, Text) and e.anchor and e.anchor["kind"] == "custom")
    m = b.truth.sheets[0]["matches"][0]
    short = m["station_text"].replace(".00", "")
    b.ex("modify_entity", {"id": label.id, "changes": {"content": f"MATCH LINE {short} - SEE C-102"}})
    assert b.verify("vague").check("D1-00").credit == 1.0
    assert b.verify("explicit").check("D1-00").credit == pytest.approx(0.95)
    # a match line of another length: fine when the length was not stated
    line, _ = _match_line(b)
    b.ex("scale_entities", {"ids": [line.id], "base": [(line.start[0] + line.end[0]) / 2,
                                                       (line.start[1] + line.end[1]) / 2],
                            "factor": 0.75})
    assert b.verify("vague").check("D1-00").credit == 1.0
    # explicit: the reworded label (0.05) and the short line on both sheets (0.1)
    assert b.verify("explicit").check("D1-00").credit == pytest.approx(0.85)


def test_second_sheet_deleted_halves_the_per_sheet_checks():
    b = _two_sheet()
    assert len(b.truth.curve_tables) == 2  # a curve on each sheet for this seed
    b.ex("delete_sheet", {"sheet": "C-102"})
    r = b.verify()
    assert r.check("D1-10").credit == 0.5 and r.check("D1-11").credit == 0.5
    assert r.check("D1-06").credit == 0.5
    # sheet 1 is whole (its match line and label still stand), sheet 2 is gone
    assert r.check("D1-00").credit == pytest.approx(0.5)
    assert {f.code for f in r.check("D1-00").findings} == {"sheet_missing"}
    assert r.counts["matched"] < r.counts["required_labels"]  # sheet 2's labels unseen


def test_labels_seen_on_either_sheet_count_once():
    b = _two_sheet()
    r = b.verify()
    assert r.counts["matched"] == r.counts["required_labels"] == len(b.truth.labels)
    assert r.check("D1-08").credit == 1.0


def test_two_sheet_partial_types_grade_both_sheets():
    b = _two_sheet(seed=5, ttype="curve-table")
    r = b.verify()
    assert r.effective_score == 100.0 and r.scope == ["table"]
    tables = [e for sh in b.doc.sheets.values() for e in sh.entities.values() if e.TYPE == "table"]
    b.ex("delete_entities", {"ids": [tables[0].id]})
    r = b.verify()
    assert r.check("D1-06").credit == pytest.approx(0.5 if len(tables) == 2 else 0.0)


# ---------------------------------------------------------------- plan prep


def _prep(ttype, seed=2, sheets=1):
    task, session = _drafted(seed, ttype, sheets)
    b = Base.__new__(Base)
    b.task, b.session, b.truth, b.D, b.A = task, session, task.truth, task.brief.deliverable, "ALIGN-1"
    return b


def _edge_entities(b):
    return [e for e in b.doc.model_entities.values()
            if e.anchor and e.anchor["kind"] == "offset"]


def test_pavement_edges_match_by_geometry_and_a_wrong_offset_hard_fails():
    b = _prep("pavement-edges")
    assert b.verify().effective_score == 100.0 and b.verify().scope == ["edges"]
    assert [c.id for c in b.verify().in_scope()] == ["D1-09", "D1-12"]
    edges = _edge_entities(b)
    n = len(b.truth.edges)
    assert len(edges) == n
    b.ex("delete_entities", {"ids": [edges[0].id]})
    r = b.verify()
    assert r.check("D1-12").credit == pytest.approx((n - 1) / n)
    assert [f.code for f in r.check("D1-12").findings] == ["missing"]
    # an edge at the wrong width on the edge layer is wrong work
    half = b.D["pavement"]["half_width_ft"]
    b.ex("draw_offset", {"alignment": b.A, "offsets": [half + 2.0], "layer": _L["edges"]})
    r = b.verify()
    assert r.hard_failed and "geometry_mismatch" in {f.code for f in r.check("D1-12").findings}


def test_pavement_edges_drawn_by_hand_count_and_layer_is_judged_separately():
    b = _prep("pavement-edges")
    edges = _edge_entities(b)
    rows = [(e, e.to_dict()) for e in edges]
    b.ex("delete_entities", {"ids": [e.id for e in edges]})
    b.ex("create_layer", {"name": "EOP"})
    for e, d in rows:  # the same geometry as raw lines and arcs on another layer
        if d["type"] == "line":
            b.ex("draw_line", {"space": "model", "start": d["start"], "end": d["end"], "layer": "EOP"})
        else:
            b.ex("draw_arc", {"space": "model", "center": d["center"], "radius": d["radius"],
                              "start_angle_deg": d["start_angle_deg"],
                              "end_angle_deg": d["end_angle_deg"], "layer": "EOP"})
    explicit, vague = b.verify("explicit"), b.verify("vague")
    assert explicit.check("D1-12").credit == 1.0 and vague.check("D1-12").credit == 1.0
    assert vague.effective_score == 100.0
    assert explicit.check("D1-09").credit < 1.0  # layers were stated


def test_pavement_width_dimension_value_station_and_level():
    b = _prep("pavement-widths")
    r = b.verify()
    assert r.effective_score == 100.0 and r.scope == ["widths"]
    assert [c.id for c in r.in_scope()] == ["D1-08", "D1-09", "D1-13"]
    dims = [e for e in b.doc.model_entities.values() if e.TYPE == "dimension"]
    n = len(b.truth.dimensions)
    assert len(dims) == n
    # a wrong number hard-fails at both levels
    b.ex("modify_entity", {"id": dims[0].id, "changes": {"text_override": "23.00'"}})
    for level in LEVELS:
        r = b.verify(level)
        assert r.hard_failed and [f.code for f in r.check("D1-13").findings] == ["wrong_value"]
    b.ex("modify_entity", {"id": dims[0].id, "changes": {"text_override": None}})
    # moved along its tangent (as far as the tangent allows): fine when no station was stated
    align = b.doc.design.alignments[b.A]
    want = b.truth.dimensions[0]
    lo, hi = want["tangent_range"]
    station = float(want["station"])
    raw = station - 50.0 if station - 50.0 >= lo + 10.0 else min(station + 50.0, hi - 10.0)
    assert abs(raw - station) > 1.0
    half = b.D["pavement"]["half_width_ft"]
    b.ex("modify_entity", {"id": dims[0].id, "changes": {
        "p1": align.station_to_xy(raw, -half)[0], "p2": align.station_to_xy(raw, half)[0],
        "line_point": align.station_to_xy(raw + 10.0, 0.0)[0]}})
    assert b.verify("vague").check("D1-13").credit == 1.0
    r = b.verify("explicit")
    assert r.check("D1-13").credit == pytest.approx((n - 1) / n)
    assert [f.code for f in r.check("D1-13").findings] == ["misplaced"]
    # gone: missing
    b.ex("delete_entities", {"ids": [dims[0].id]})
    r = b.verify()
    assert [f.code for f in r.check("D1-13").findings] == ["missing"]
    assert r.check("D1-13").credit == pytest.approx((n - 1) / n)


def test_width_dimension_reading_the_right_number_in_another_format():
    b = _prep("pavement-widths")
    dims = [e for e in b.doc.model_entities.values() if e.TYPE == "dimension"]
    width = b.truth.dimensions[0]["value"]
    b.ex("modify_entity", {"id": dims[0].id, "changes": {"text_override": f"{width:.1f} FT"}})
    assert b.verify("vague").check("D1-13").credit == 1.0
    assert b.verify("explicit").hard_failed


def test_attach_reference_structural_checks():
    b = _prep("attach-reference")
    r = b.verify()
    assert r.effective_score == 100.0 and r.scope == ["reference"]
    assert [c.id for c in r.in_scope()] == ["D1-14"] and r.scope_weight == 5
    ref = next(iter(b.doc.references.values()))
    assert ref.path == b.D["basefile"]
    b.ex("modify_reference", {"name": ref.name, "changes": {"offset": [10.0, 0.0]}})
    r = b.verify()
    assert r.check("D1-14").credit == 0.75
    assert [f.code for f in r.check("D1-14").findings] == ["misplaced"]
    b.ex("modify_reference", {"name": ref.name, "changes": {"offset": [0.0, 0.0],
                                                             "visible": False}})
    r = b.verify()
    assert r.check("D1-14").credit == 0.75
    assert [f.code for f in r.check("D1-14").findings] == ["not_visible"]
    b.ex("detach_reference", {"name": ref.name})
    r = b.verify()
    assert r.effective_score == 0.0 and [f.code for f in r.check("D1-14").findings] == ["missing"]


def test_attach_reference_starting_document_has_no_model_work_but_the_base_does():
    task = generate_task(4, task_type="attach-reference")
    doc = Document.from_dict(task.baseline)
    assert doc.model_entities == {} and doc.sheets and not doc.references
    assert list(task.files) == [task.brief.deliverable["basefile"]]
    base = Document.from_dict(task.files[task.brief.deliverable["basefile"]])
    kinds = {e.anchor["kind"] for e in base.model_entities.values() if e.anchor}
    assert kinds >= {"element", "offset", "tick", "station", "bearing", "mc"}
    assert base.design.fingerprint() == task.truth.design_fingerprint


def test_layer_setup_names_at_vague_properties_at_explicit():
    b = _prep("layer-setup")
    r = b.verify()
    assert r.effective_score == 100.0 and r.scope == ["layers"]
    assert [c.id for c in r.in_scope()] == ["D1-09"]
    n = len(_SPEC["layer_set"])
    assert n == 16 and set(_L.values()) <= set(_SPEC["layer_set"])
    b.ex("modify_layer", {"name": _L["edges"], "changes": {"color": "green"}})
    assert b.verify("vague").effective_score == 100.0
    r = b.verify("explicit")
    assert r.check("D1-09").credit == pytest.approx((n - 1) / n)
    assert [f.code for f in r.check("D1-09").findings] == ["wrong_layer_props"]
    # the standard set is the Caltrans named levels; the starting document had only layer 0
    doc = Document.from_dict(b.task.baseline)
    assert list(doc.layers) == ["0"]
    r0 = verify(doc, b.truth, prompt_level="vague")
    assert r0.effective_score == 0.0 and len(r0.check("D1-09").findings) >= n


def test_pavement_combo_asks_for_both():
    b = _prep("pavement")
    r = b.verify()
    assert r.scope == ["edges", "widths"] and r.effective_score == 100.0
    assert [c.id for c in r.in_scope()] == ["D1-08", "D1-09", "D1-12", "D1-13"]


# ------------------------------------------------------------ design input


def _creation(seed=2):
    """A create-alignment task and a session on its empty-design start."""
    task = generate_task(seed, curves=2, equations=True, task_type="create-alignment")
    return task, session_for_task(task)


def _create(session, task, radius_delta=0.0, begin_delta=0.0, equations=True, name="ALIGN-1"):
    al = task.brief.design["alignments"]["ALIGN-1"]
    pis = [[p["point"][0], p["point"][1]] + ([p["radius"] + radius_delta] if p["radius"] else [])
           for p in al["pis"]]
    params = {"name": name, "pis": pis, "begin_station": al["begin_station"] + begin_delta}
    if equations and al["equations"]:
        params["equations"] = [{"back": q["back"], "ahead": q["ahead"]} for q in al["equations"]]
    r = session.execute("create_alignment", params)
    assert r["ok"], r.get("error")
    return r


def test_create_alignment_prompt_states_the_geometry_and_the_rules_change():
    task, _ = _creation()
    from roaddraft.tasks.prompts import rules, task_text
    for level in LEVELS:
        text = task.brief.prompts[level]
        assert "begins at N " in text and "PI-1 at N " in text and "R = " in text
        assert "ends at N " in text and "station equation" in text and "ALIGN-1" in text
    assert "The design is empty" in rules(task.brief)
    assert "already in the document" in rules(generate_task(2).brief)
    assert task_text(task.brief, "vague").endswith("Create it and draw it.")


def test_create_alignment_exact_scores_100_and_the_empty_start_0():
    task, session = _creation()
    assert verify(Document.from_dict(task.baseline), task.truth).effective_score == 0.0
    _create(session, task)
    session.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": _L["alignment"]})
    r = verify(session.doc, task.truth)
    assert r.effective_score == 100.0 and r.scope == ["design", "linework"]
    assert [c.id for c in r.in_scope()] == ["D1-01", "D1-09", "D1-15"] and r.scope_weight == 28
    assert r.design_fingerprint_ok


def test_create_alignment_created_but_not_drawn():
    task, session = _creation()
    _create(session, task)
    r = verify(session.doc, task.truth)
    assert r.check("D1-15").credit == 1.0 and r.check("D1-01").credit == 0.0
    assert {f.code for f in r.check("D1-01").findings} == {"missing"} and not r.hard_failed


def test_create_alignment_wrong_radius_hard_fails_and_the_linework_misses():
    task, session = _creation()
    _create(session, task, radius_delta=10.0)
    session.execute("draw_alignment", {"alignment": "ALIGN-1", "layer": _L["alignment"]})
    r = verify(session.doc, task.truth)
    assert r.hard_failed and r.effective_score == 0.0
    codes = [f.code for f in r.check("D1-15").findings]
    assert codes and set(codes) == {"wrong_value"}
    n = len(task.truth.elements)
    assert r.check("D1-15").credit < 1.0
    # the drawing follows the wrong design: curves and the tangents between them move
    assert r.check("D1-01").credit < 1.0


def test_create_alignment_wrong_begin_station_and_missing_equation():
    task, session = _creation()
    _create(session, task, begin_delta=100.0, equations=False)
    r = verify(session.doc, task.truth)
    kinds = sorted(f.anchor["kind"] for f in r.check("D1-15").findings)
    assert kinds == ["begin_station", "equations"]
    total = 1 + len(task.truth.elements) + task.truth.counts["equations"]
    assert r.check("D1-15").credit == pytest.approx(len(task.truth.elements) / total)
    assert r.hard_failed


def test_create_alignment_under_another_name_is_missing():
    task, session = _creation()
    _create(session, task, name="MAIN")
    r = verify(session.doc, task.truth)
    assert r.check("D1-15").credit == 0.0
    assert [f.code for f in r.check("D1-15").findings] == ["missing"]
