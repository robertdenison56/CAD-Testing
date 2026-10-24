"""D1 tasks on the redrafted example plan sheets (roaddraft.tasks.real), and the
engine and verifier pieces they need: labels lettered upright through a twisted
viewport (view_rotation), text that reads upside down as plotted, and a real
sheet's own overlaps left out of legibility."""
from __future__ import annotations

import json

import pytest

from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.horizontal import Alignment
from roaddraft.design.labels import compile_label, stationing_plan
from roaddraft.document.document import Document
from roaddraft.document.entities import Line, Polyline, Table, Text
from roaddraft.tasks.real import (
    AGENCIES, TABLE_TITLE, _Targets, _own_rows, build_real_task, candidates, real_sheets,
    usable_alignment, validate,
)
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.tasks.types import REAL_TASK_TYPES, TASK_TYPES, task_type
from roaddraft.verify import verify
from roaddraft.verify.legibility import reads_upside_down

L1 = ("PPM-045", "TB1")  # Caltrans Route 65 layout L-1, a ramp line with one curve, twist -89.94


@pytest.fixture(scope="module")
def l1_task():
    return build_real_task(*L1, "real-alignment-data")


def _paper(rotation_deg: float, twist: float) -> float:
    return (rotation_deg + twist + 180.0) % 360.0 - 180.0


# ------------------------------------------------------------- view rotation


def test_view_rotation_letters_model_labels_upright_on_a_twisted_sheet():
    align = Alignment.from_dict({
        "name": "A", "begin_station": 1000.0,
        "elements": [{"kind": "tangent", "start": [0.0, 0.0], "end": [-20.0, 400.0]}]})
    twist = -89.94  # the line runs up the model, across the sheet
    ap = resolve_anchor(align, parse_anchor("T-1"))
    flat = compile_label(align, ap, "bearing")
    turned = compile_label(align, ap, "bearing", view_rotation=twist)
    assert reads_upside_down(flat.rotation_deg + twist)
    assert not reads_upside_down(turned.rotation_deg + twist)
    assert turned.anchor_record()["view_rotation"] == pytest.approx(twist)
    assert "view_rotation" not in flat.anchor_record()  # untwisted records are unchanged
    for item in stationing_plan(align, view_rotation=twist).labels():
        assert not reads_upside_down(item.rotation_deg + twist), item.content


def test_view_rotation_zero_is_the_old_placement_exactly():
    align = Alignment.from_dict({
        "name": "A", "begin_station": 0.0,
        "elements": [{"kind": "tangent", "start": [0.0, 0.0], "end": [300.0, 120.0]}]})
    ap = resolve_anchor(align, parse_anchor("T-1"))
    a = compile_label(align, ap, "bearing")
    b = compile_label(align, ap, "bearing", view_rotation=0.0)
    assert (a.rotation_deg, a.position, a.side) == (b.rotation_deg, b.position, b.side)


# ------------------------------------------------------------- catalogue


def test_the_catalogue_reaches_every_agency_and_skips_traced_centerlines():
    sheets = real_sheets()
    assert {s.agency for s in sheets} == set(AGENCIES)
    traced = Alignment.from_dict({
        "name": "T", "begin_station": 0.0,
        "elements": [{"kind": "tangent", "start": [10.0 * i, 0.0], "end": [10.0 * (i + 1), 1.0]}
                     for i in range(20)]})
    assert "tangents" in usable_alignment(traced)
    pairs = candidates()
    assert {t for _s, _a, t in pairs} == set(REAL_TASK_TYPES)


def test_real_types_are_found_by_name_but_kept_apart_from_the_seeded_ones():
    assert not set(REAL_TASK_TYPES) & set(TASK_TYPES)
    for name, ttype in REAL_TASK_TYPES.items():
        assert task_type(name) is ttype
        # the design lives in the real base file: a sheet file reaches it through the
        # reference; drawing the alignment is done in that base file itself
        assert ttype.design_referenced == (name != "real-draw-alignment")


# ------------------------------------------------------------- one real task


def test_a_real_sheet_task_verifies_100_and_its_start_0(l1_task):
    v = validate(l1_task)
    assert v["ok"], v
    D = l1_task.brief.deliverable
    assert D["design_reference"] == "AA01" and D["view_rotation"] == pytest.approx(-89.94, abs=0.01)
    assert l1_task.brief.prompts["vague"] == "Letter the alignment data of the TB1 line on sheet L-1."
    assert "AA01:TB1" in l1_task.brief.prompts["explicit"]


def test_the_alignments_own_annotation_is_stripped_and_the_rest_kept(l1_task):
    base = l1_task.files["0000000000aa01.rdraft"]
    ents = base["model"]["entities"]
    ents = list(ents.values()) if isinstance(ents, dict) else ents
    by = lambda al: [e for e in ents if (e.get("anchor") or {}).get("alignment") == al
                     and (e.get("anchor") or {}).get("placed_by") == "annotate_stationing"]
    assert not by("TB1")           # its stationing is the task
    assert by("D13") and by("TB2")  # the other lines keep theirs
    stripped = l1_task.truth.sheets[0]["stripped"]
    assert stripped["sheet"]["curve_points"] and stripped["sheet"]["table"]
    start = Document.from_dict(l1_task.baseline)
    sheet = start.sheet_by_ref("L-1")
    texts = [e.content for e in sheet.entities.values() if hasattr(e, "content")]
    assert not any("642+81.23 BC" in t for t in texts)
    assert "NOTES:" in texts  # the sheet's own notes stay
    # L-1's CURVE DATA table tabulates TB2's curve (No. 1, R 835') and TB1's (No. 2,
    # R 3280'): TB1's row goes, TB2's stays, and the table stays with it
    assert "CURVE DATA" in texts and "835’" in texts and "3280’" not in texts
    assert stripped["sheet"]["table_rows"] == ["TX-015:2"]
    sh = l1_task.brief.deliverable["sheets"][0]
    assert not sh["curve_table_replaces"]
    # the reference's table for TB1 goes below the kept one
    kept_bottom = min(e.start[1] for e in sheet.entities.values()
                      if isinstance(e, Line) and e.layer == "S-LINE-035"
                      and 7.0 < e.start[0] < 15.0 and 2.5 < e.start[1] < 4.5)
    assert sh["curve_table_position"][1] < kept_bottom
    assert sh["curve_table_position"][0] == pytest.approx(7.15, abs=0.1)


def test_a_shared_curve_table_loses_only_the_lines_rows_and_closes_up():
    """L-7's CURVE DATA table lists six curves of four lines; stripping F3 takes
    its two rows (43 and 47, R 855' and 265'), the rows below move up and the
    grid shrinks by two rows, title and headers in place."""
    task = build_real_task("PPM-050", "F3", "real-curve-table")
    sheet = Document.from_dict(task.baseline).sheet_by_ref("L-7")
    texts = {e.id: e for e in sheet.entities.values() if isinstance(e, Text)}
    cells = {t.content: t for t in texts.values() if 2.6 < t.position[0] < 10.4
             and 17.0 < t.position[1] < 19.3}
    assert "855’" not in cells and "265’" not in cells
    assert {"3280’", "180’", "460’", "1500’", "No.", "R", "T", "L"} <= set(cells)
    rows = sorted({round(cells[k].position[1], 1) for k in ("3280’", "180’", "460’", "1500’")},
                  reverse=True)
    assert rows == pytest.approx([18.6, 18.3, 18.0, 17.8], abs=0.1)  # 44 45 46 48, closed up
    assert cells["R"].position[1] == pytest.approx(18.93, abs=0.02)   # the header did not move
    rules = sorted({round(e.start[1], 2) for e in sheet.entities.values() if isinstance(e, Line)
                    and abs(e.start[1] - e.end[1]) < 0.02 and 2.6 < e.start[0] < 10.4
                    and 17.0 < e.start[1] < 19.3}, reverse=True)
    assert rules == pytest.approx([19.21, 18.82, 18.54, 18.26, 17.98], abs=0.02)
    border = next(e for e in sheet.entities.values() if isinstance(e, Polyline)
                  and e.layer == "S-LINE-050" and len(e.vertices) == 4 and e.vertices[0][0] < 3)
    assert min(v[1] for v in border.vertices) == pytest.approx(17.70, abs=0.02)
    stripped = task.truth.sheets[0]["stripped"]["sheet"]
    assert len(stripped["table_rows"]) == 2 and len(stripped["table"]) == 12  # 10 cells, 2 rules
    sh = task.brief.deliverable["sheets"][0]
    assert sh["curve_table_position"][1] < 17.70 and not sh["curve_table_replaces"]
    assert validate(task)["ok"]


def test_a_table_entity_shared_by_two_lines_keeps_the_other_lines_row():
    task = build_real_task("PPM-048", "IN4", "real-curve-table")
    sheet = Document.from_dict(task.baseline).sheet_by_ref("L-4")
    table = next(e for e in sheet.entities.values() if isinstance(e, Table))
    assert [r[0] for r in table.rows] == ["3"]  # D13's curve stays, IN4's (No. 36) went
    assert task.truth.sheets[0]["stripped"]["sheet"]["table_rows"] == ["TB-001:1"]
    assert "TB-001" in task.truth.sheets[0]["given_entities"]


def test_ring_bubbles_go_with_their_digit_and_leader_and_the_other_lines_stay(l1_task):
    """L-1's bubbles are rings of 20 vertices (S-ANNO-TAG), not circles: TB1's
    ring and its leader go, TB2's ring stays."""
    stripped = l1_task.truth.sheets[0]["stripped"]["sheet"]
    assert stripped["bubbles"] == ["PL-005"] and "LN-023" in stripped["leaders"]
    sheet = Document.from_dict(l1_task.baseline).sheet_by_ref("L-1")
    assert "PL-004" in sheet.entities and "PL-005" not in sheet.entities
    assert "LN-023" not in sheet.entities


def test_table_rows_go_to_the_curves_they_fit_best():
    """Route 65 L-3's ramps have curves of 4,850 to 5,000 ft beside D13's 5,000
    ft curve: each curve takes the one row it fits best by radius, then by
    length, so the three lines split the six rows without a row counted twice."""
    headers = ["No.", "R", "Δ", "T", "L"]
    rows = [["3", "5000’", "41°17’58\"", "1884.32’", "3604.04’"],
            ["30", "4935’", "03°48’22\"", "164.03’", "327.93’"],
            ["31", "5065’", "03°03’45\"", "135.34’", "270.62’"],
            ["32", "4600’", "09°12’24\"", "369.83’", "738.07’"],
            ["33", "3280’", "02°51’53\"", "82.04’", "164.04’"],
            ["34", "855’", "40°58’06\"", "318.66’", "609.94’"]]
    d13 = [(4998.85, 1178.66)]
    in4 = [(4847.25, 192.52), (4586.62, 486.94)]
    in3 = [(4914.34, 258.13), (3148.05, 164.01), (853.02, 432.4)]

    def own(mine, others):
        tg = _Targets([], [], [], [r for r, _l in mine], 1.0, [], mine, others)
        return _own_rows(rows, headers, tg)

    assert own(d13, in4 + in3) == [0]
    assert own(in4, d13 + in3) == [1, 3]
    assert own(in3, d13 + in4) == [2, 4, 5]
    # alone on a sheet, a line within 5 % takes the row; a stranger's radius does not
    assert own([(3280.0, 164.0)], []) == [4]
    assert own([(2000.0, 500.0)], []) == []


def test_legibility_counts_new_work_only_and_flags_upside_down_labels(l1_task):
    session = session_for_task(l1_task)
    reference_solution(l1_task, session)
    report = verify(session.doc, l1_task.truth)
    assert report.check("D1-08").credit == 1.0  # the real sheet's own overlaps don't count
    # a bearing lettered without the view's twist reads upside down on L-1
    result = session.execute("place_label", {
        "space": "model", "alignment": "AA01:TB1", "anchor": "T-1", "kind": "bearing",
        "height": 5.0, "label_offset": 30.0, "layer": "align_MAIN-anno"})
    assert result["ok"], result
    report = verify(session.doc, l1_task.truth)
    flipped = [f for f in report.check("D1-08").findings if f.code == "upside_down"]
    assert flipped and report.check("D1-08").credit < 1.0


def test_a_real_task_survives_a_save_and_reopen(l1_task, tmp_path):
    session = session_for_task(l1_task, out_dir=tmp_path)
    reference_solution(l1_task, session)
    path = tmp_path / "finished.rdoc.json"
    assert session.query("save_document", {"path": str(path)})["ok"]
    doc = Document.from_dict(json.loads(path.read_text()))
    doc._path = path
    assert verify(doc, l1_task.truth).effective_score == 100.0


@pytest.mark.parametrize("sheet_id, alignment, type_name", [
    ("PPM-045", "TB1", "real-stationing"),
    ("PPM-045", "TB1", "real-bearings"),
    ("PPM-045", "TB1", "real-callouts"),
    ("PPM-045", "TB1", "real-curve-table"),
    ("PPM-045", "TB1", "real-draw-alignment"),
    ("PPM-045", "D13", "real-attach-reference"),
    ("PPM-045", "D13", "real-title-block"),
    ("PPM-045", "TB1", "real-sheet-setup"),
    ("PPM-045", "TB1", "real-annotate-sheet"),
    ("PPM-045", "TB1", "real-plan-sheet"),
    ("CFL-D-Plan-and-Plan", "CL1", "real-plan-sheet"),
])
def test_each_real_type_on_l1(sheet_id, alignment, type_name):
    task = build_real_task(sheet_id, alignment, type_name)
    v = validate(task)
    assert v["ok"], v


def test_each_start_cuts_the_real_files_for_its_job():
    draw = build_real_task("PPM-045", "TB1", "real-draw-alignment")
    assert draw.baseline["meta"]["project_name"] != "" and not draw.baseline["sheets"]
    assert "0000000000aa01.rdraft" not in draw.files  # the base file is the document
    attach = build_real_task("PPM-045", "D13", "real-attach-reference")
    assert not attach.baseline["references"]
    assert {r["file"] for r in attach.truth.references} == {"0000000000aa01.rdraft",
                                                            "0000000000bb01.rdraft"}
    title = build_real_task("PPM-045", "D13", "real-title-block")
    sheet = Document.from_dict(title.baseline).sheet_by_ref("L-1")
    assert "route" not in sheet.title_block_fields and "agency" in sheet.title_block_fields
    assert title.truth.sheets[0]["title_block_fields"]["route"] == "65"
    plan = build_real_task("PPM-045", "TB1", "real-plan-sheet")
    assert Document.from_dict(plan.baseline).sheet_by_ref("L-1") is None
    na = plan.truth.sheets[0]["north_arrow"]
    assert na["rotation_deg"] == pytest.approx(-89.94, abs=0.01)  # north on the turned sheet
    assert plan.truth.sheets[0]["twist_deg"] == pytest.approx(-89.94, abs=0.01)


def test_a_layout_turned_off_the_published_twist_loses_the_fit():
    task = build_real_task("PPM-045", "TB1", "real-sheet-setup")
    session = session_for_task(task)
    reference_solution(task, session)
    vp = session.doc.sheet_by_ref("L-1").viewports[0]
    assert verify(session.doc, task.truth).check("D1-00").credit == 1.0
    assert session.execute("modify_viewport", {"sheet": "L-1", "viewport_id": vp.id,
                                               "changes": {"rotation_deg": 0.0}})["ok"]
    report = verify(session.doc, task.truth)
    assert report.check("D1-00").credit < 1.0
    assert any(f.code == "not_fitted" for f in report.check("D1-00").findings)
