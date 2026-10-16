"""WP9 tests: the D1 task generator, ground truth, and reference solution."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.core import geometry as geo
from roaddraft.design.horizontal import Alignment
from roaddraft.design.vertical import Profile
from roaddraft.document import dimgeom
from roaddraft.document.document import Document
from roaddraft.document.entities import Dimension, Line, Text
from roaddraft.tasks.brief import GENERATOR_VERSION, GroundTruth, Task, TaskBrief, compute_task_id
from roaddraft.tasks.generator import PAD_FT, generate_task
from roaddraft.tasks.ground_truth import compute_ground_truth, match_truth
from roaddraft.tasks.reference import check_replay, reference_solution, session_for_task
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.standards import max_grade, min_k, min_radius
from roaddraft.tasks.types import TASK_TYPES
from roaddraft.verify.legibility import OVERLAP_EPS_IN, overlap_depth, text_quad
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1 as _SPEC
_L = _SPEC["layers"]

FIXTURE = Path(__file__).parent / "fixtures" / "task_ids_d1_v1.json"


def test_seed_42_twice_identical_json_and_id():
    a, b = generate_task(42), generate_task(42)
    assert isinstance(a, Task) and isinstance(a.brief, TaskBrief) and isinstance(a.truth, GroundTruth)
    assert a.brief.to_json() == b.brief.to_json()
    assert a.truth.to_json() == b.truth.to_json()
    assert a.baseline == b.baseline and a.task_id == b.task_id
    assert a.task_id.startswith("D1-000042-") and len(a.task_id) == len("D1-000042-") + 12
    assert a.brief.generator_version == GENERATOR_VERSION
    assert a.brief.spec_hash == spec_hash() and a.brief.spec_version == "v1"
    assert a.truth.task_id == a.task_id
    # round trips
    assert TaskBrief.from_dict(json.loads(a.brief.to_json())).to_dict() == a.brief.to_dict()
    assert GroundTruth.from_dict(json.loads(a.truth.to_json())).to_dict() == a.truth.to_dict()


def test_seed_43_differs():
    a, b = generate_task(42), generate_task(43)
    assert a.task_id != b.task_id and a.brief.design != b.brief.design
    assert compute_task_id(1, "D1", {"x": 1.0000001}) == compute_task_id(1, "D1", {"x": 1.0})
    assert compute_task_id(1, "D1", {"x": 1.0}) != compute_task_id(1, "D1", {"x": 2.0})


def test_task_ids_match_pinned_fixture_seeds_1_2_3_42_100():
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["generator_version"] == GENERATOR_VERSION
    assert fixture["spec_hash"] == spec_hash()
    for seed, task_id in fixture["task_ids"].items():
        assert generate_task(int(seed)).task_id == task_id, seed


def test_200_seeds_R_ge_min_radius_grade_le_max_K_ge_min_compile_ok_fits_window():
    fit_w, fit_h = DRAFTING_SPEC_V1["sheet"]["fit_window_in"]
    for seed in range(1, 201):
        task = generate_task(seed)
        v = task.brief.project["design_speed_mph"]
        assert v in (35, 40, 45, 50, 55)
        design = task.brief.design
        align = Alignment.from_dict(design["alignments"]["ALIGN-1"])
        assert align.source == "pis" and 1 <= len(align.curves()) <= 3
        for c in align.curves():
            assert c.radius >= min_radius(v)
            assert 14.9 <= c.delta_deg <= 60.6  # PIs are rounded to 0.01 ft
        profile = Profile.from_dict(design["profiles"]["PROF-1"])
        assert profile.pvis[0].station == align.begin_station
        assert profile.pvis[-1].station == pytest.approx(align.end_station)
        for row in profile.curves():
            assert abs(row["g1_pct"]) <= max_grade(v) + 1e-9
            assert abs(row["g2_pct"]) <= max_grade(v) + 1e-9
            assert abs(row["g1_pct"]) >= 0.1 - 1e-9 and abs(row["g2_pct"]) >= 0.1 - 1e-9
            if row["length"] > 0:
                assert 200.0 <= row["length"] <= 500.0
                assert row["K"] >= min_k(v, row["type"]) - 1e-9
        fpi = task.brief.deliverable["feet_per_inch"]
        assert fpi in (40.0, 50.0)
        bb = align.bbox()
        assert (bb[2] - bb[0]) + 2.0 * PAD_FT <= fit_w * fpi + 1e-6
        assert (bb[3] - bb[1]) + 2.0 * PAD_FT <= fit_h * fpi + 1e-6
        assert task.brief.deliverable["text_heights"]["model_label_ft"] == 0.10 * fpi


def test_truth_label_count_equals_reference_entities():
    task = generate_task(42)
    truth = task.truth
    assert truth.counts["labels"] == len(truth.labels)
    assert truth.counts["ticks"] == len(truth.ticks)
    n_station = truth.counts["ticks"]
    n_junction = 2 * truth.counts["curves"]  # PC + PT per curve (no back-to-back curves)
    n_bearing = truth.counts["tangents"]
    n_mc = truth.counts["curves"]
    assert truth.counts["labels"] == n_station + n_junction + n_bearing + n_mc + truth.counts["equations"]
    assert {l["kind"] for l in truth.labels} >= {"station", "pc", "pt", "bearing", "mc"}
    assert all(l["required"] and l["space"] == "model" for l in truth.labels)
    assert truth.curve_table["title"] == "CURVE DATA" and len(truth.curve_table["rows"]) == 1
    assert truth.elements[0]["ref"] == "T-1" and truth.elements[1]["kind"] == "curve"
    assert truth.sheet["viewport"]["feet_per_inch"] == task.brief.deliverable["feet_per_inch"]
    assert truth.design_fingerprint.startswith("sha256:")
    assert compute_ground_truth(task.brief).to_dict() == truth.to_dict()


def test_reference_solution_200_seeds_zero_faults_matches_truth_replays(tmp_path):
    """E0's acceptance number: over 200 seeds the reference drafts a clean
    sheet -- no fault, no warning, every truth label matched, the given design
    untouched, every anchor bus-stamped -- and its journal replays to the same
    document."""
    for seed in range(1, 201):
        task = generate_task(seed)
        session = session_for_task(task, out_dir=tmp_path)
        journal = reference_solution(task, session)
        assert journal and journal[0]["name"] == "set_meta", seed
        assert session.reference_warnings == [], seed
        assert session.doc.meta["task_id"] == task.task_id, seed
        m = match_truth(session.doc, task.truth)
        assert m["matched"] == task.truth.counts["labels"], (seed, m)
        assert not m["missing"] and not m["content_mismatch"], (seed, m)
        assert not m["position_mismatch"] and not m["extra"], (seed, m)
        assert session.doc.design.fingerprint() == task.truth.design_fingerprint, seed
        anchored = list(session.doc.model_entities.values())
        for sheet in session.doc.sheets.values():
            anchored += list(sheet.entities.values())
        stamps = {e.anchor.get("placed_by") for e in anchored if e.anchor}
        assert stamps <= set(ANCHOR_PRODUCERS), (seed, stamps)
        assert check_replay(session, tmp_path / f"ref-{seed}.journal.jsonl"), seed


def test_reference_matches_truth_missing_empty_content_empty_position_empty(tmp_path):
    for seed in (42, 7, 100):
        task = generate_task(seed, equations=(seed == 7))
        session = session_for_task(task, out_dir=tmp_path)
        reference_solution(task, session)
        m = match_truth(session.doc, task.truth)
        assert m["missing"] == [] and m["content_mismatch"] == [] and m["position_mismatch"] == []
        assert m["extra"] == [] and m["matched"] == task.truth.counts["labels"]
        # the design was not touched
        assert session.doc.design.fingerprint() == task.truth.design_fingerprint
        # ticks and elements are anchored on the spec'd layers
        ticks = [e for e in session.doc.model_entities.values()
                 if e.anchor and e.anchor["kind"] == "tick"]
        assert len(ticks) == task.truth.counts["ticks"]
        assert all(t.layer == _L["ticks"] for t in ticks)
        sheet = next(iter(session.doc.sheets.values()))
        tables = [e for e in sheet.entities.values() if e.TYPE == "table"]
        assert tables[0].rows == task.truth.curve_table["rows"]
        assert (sheet.title_block_fields["scale"]
                == task.brief.deliverable["sheets"][0]["title_block_fields"]["scale"])
    # a moved label shows up as a position mismatch, a missing one as missing
    tid = next(e.id for e in session.doc.model_entities.values()
               if e.anchor and e.anchor["kind"] == "pc")
    session.execute("move_entities", {"ids": [tid], "delta": [1.0, 0.0]})
    m = match_truth(session.doc, task.truth)
    assert len(m["position_mismatch"]) == 1 and m["position_mismatch"][0]["id"] == tid
    session.execute("delete_entities", {"ids": [tid]})
    m = match_truth(session.doc, task.truth)
    assert len(m["missing"]) == 1 and m["missing"][0].startswith("pc @ PC-")


def test_width_dimension_lines_clear_the_bearing_lettering_seeds_1_40(tmp_path):
    """2026-10-16: on every pavement seed the width dimension line ran through the
    bearing and distance lettered above the tangent's midpoint, at both plan
    scales, on one and two sheets (D1-08 judges text footprints, not a line
    through one, so the oracle still scored 100).  Now no line of a width
    dimension the reference draws -- dimension line, extension lines, stubs --
    crosses or ends inside a bearing text box, and its text clears the bearing;
    a tangent with no room for that is left undimensioned."""
    pavement = sorted(n for n, t in TASK_TYPES.items() if "widths" in t.shown())
    assert pavement == ["pavement", "pavement-widths"]
    scales, dimensioned, undimensioned, skipped = set(), 0, 0, 0
    for ttype in pavement:
        for sheets in (1, 2):
            for seed in range(1, 41):
                try:
                    task = generate_task(seed, task_type=ttype, sheets=sheets)
                except ValueError:  # no tangent of this layout has room for a dimension
                    skipped += 1
                    continue
                scales.add(task.brief.deliverable["feet_per_inch"])
                session = session_for_task(task, out_dir=tmp_path)
                reference_solution(task, session)
                doc = session.doc
                boxes = {e.id: text_quad(e.position, e.content, e.height, e.rotation_deg,
                                         e.halign, e.valign)
                         for e in doc.model_entities.values()
                         if isinstance(e, Text) and e.anchor and e.anchor.get("kind") == "bearing"}
                assert len(boxes) == task.truth.counts["tangents"], (ttype, sheets, seed)
                dims = [e for e in doc.model_entities.values() if isinstance(e, Dimension)]
                assert dims and len(dims) == len(task.brief.deliverable["width_dimensions"])
                dimensioned += len(dims)
                undimensioned += task.truth.counts["tangents"] - len(dims)
                for dm in dims:
                    for prim in dimgeom.primitives(dm, doc):
                        for tid, box in boxes.items():
                            where = (ttype, sheets, seed, dm.id, prim.id, tid)
                            if isinstance(prim, Line):
                                assert not geo.segment_polygon_params(prim.start, prim.end, box), where
                                assert not geo.point_in_polygon(prim.start, box), where
                                assert not geo.point_in_polygon(prim.end, box), where
                            elif isinstance(prim, Text) and prim.content:
                                quad = text_quad(prim.position, prim.content, prim.height,
                                                 prim.rotation_deg, prim.halign, prim.valign)
                                fpi = task.brief.deliverable["feet_per_inch"]
                                assert overlap_depth(quad, box) <= OVERLAP_EPS_IN * fpi, where
    assert scales == {40.0, 50.0}  # both plan scales of the spec were exercised
    assert dimensioned > 2 * undimensioned  # most tangents still carry their dimension
    assert skipped <= 4


def test_check_replay_true(tmp_path):
    task = generate_task(42)
    session = session_for_task(task, out_dir=tmp_path)
    reference_solution(task, session)
    assert check_replay(session, tmp_path / "ref.journal.jsonl") is True


def test_render_sheet_png_over_20kB(tmp_path):
    task = generate_task(42)
    session = session_for_task(task, out_dir=tmp_path)
    reference_solution(task, session)
    r = session.query("render_sheet", {"sheet": "C-101", "dpi": 100})
    assert r["ok"] and r["size_bytes"] > 20_000


def test_equations_dial_produces_EQ1_label(tmp_path):
    task = generate_task(7, equations=True)
    align = task.brief.design["alignments"]["ALIGN-1"]
    assert len(align["equations"]) == 1 and task.truth.counts["equations"] == 1
    eq_labels = [l for l in task.truth.labels if l["kind"] == "equation"]
    assert len(eq_labels) == 1 and eq_labels[0]["anchor"] == "EQ-1"
    assert eq_labels[0]["content"].startswith("STA ") and " BK = STA " in eq_labels[0]["content"]
    assert "equation" in task.brief.deliverable["required_label_kinds"]
    session = session_for_task(task, out_dir=tmp_path)
    reference_solution(task, session)
    texts = [e for e in session.doc.model_entities.values()
             if e.anchor and e.anchor["kind"] == "equation"]
    assert len(texts) == 1 and texts[0].content == eq_labels[0]["content"]
    assert match_truth(session.doc, task.truth)["missing"] == []
    assert generate_task(7, equations=True).task_id != generate_task(7).task_id


def test_baseline_has_design_no_entities_no_sheets():
    task = generate_task(42)
    doc = Document.from_dict(task.baseline)
    assert list(doc.design.alignments) == ["ALIGN-1"] and list(doc.design.profiles) == ["PROF-1"]
    assert doc.model_entities == {} and doc.sheets == {}
    assert doc.meta["task_id"] == task.task_id and doc.meta["spec_version"] == "v1"
    assert doc.meta["design_speed_mph"] == task.brief.project["design_speed_mph"]
    assert "NORTH_ARROW" in doc.blocks and list(doc.layers) == ["0"]
    assert doc.design.fingerprint() == task.truth.design_fingerprint


def test_generator_options_curves_and_speed():
    # a pinned design speed is never stepped down to fit; three 55 mph curves need two
    # sheets at the plan scales in use, and asking for them on one is an error, not a
    # slower road
    task = generate_task(5, curves=3, design_speed_mph=55, sheets=2)
    align = Alignment.from_dict(task.brief.design["alignments"]["ALIGN-1"])
    assert len(align.curves()) == 3 and task.brief.project["design_speed_mph"] == 55
    assert all(c.radius >= min_radius(55) for c in align.curves())
    assert task.truth.counts["tangents"] == 4
    with pytest.raises(ValueError):
        generate_task(5, curves=3, design_speed_mph=55)
    with pytest.raises(ValueError):
        generate_task(5, curves=0)
