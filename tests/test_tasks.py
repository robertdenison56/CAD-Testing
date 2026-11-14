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
from roaddraft.tasks.generator import (DOCUMENT_PEOPLE, PAD_FT, TWIST_MIN_DEG, generate_task,
                                       seed_twist)
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


def test_the_document_carries_who_designed_drew_and_checked_it_and_its_date():
    # under the title block's own field names, so a title block the prompt does not spell
    # out can be filled from what the document says (Robert, 2026-11-11); the base drawing
    # of a basefile type carries them too.  The task's payload always held them, so the id
    # is the one the manifests froze
    for ttype in ("title-block", "plan-sheet", "stationing", "annotate-base"):
        task = generate_task(1000, task_type=ttype)
        fields = task.brief.deliverable["sheets"][0]["title_block_fields"]
        for doc in [task.baseline] + list(task.files.values()):
            assert {k: doc["meta"][k] for k in DOCUMENT_PEOPLE} == {
                k: fields[k] for k in DOCUMENT_PEOPLE}
        assert not any(fields[k] in task.brief.prompts["vague"] for k in ("date",))
    assert DOCUMENT_PEOPLE == ("designed_by", "drawn_by", "checked_by", "date")


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


# ------------------------------------------------------------ the twist dial (2026-11-11)


def _paper(task, dist: float, sheet: int = 0):
    """Where the point ``dist`` along the task's line falls on a sheet's paper."""
    align = Alignment.from_dict(task.brief.design["alignments"]["ALIGN-1"])
    vp = task.brief.deliverable["sheets"][sheet]["viewport"]
    t = geo.ViewportTransform(vp["center_paper"], vp["model_center"], vp["feet_per_inch"],
                              vp.get("rotation_deg", 0.0))
    return t.to_paper(align.point_at(min(dist, align.length)))


def test_the_twist_dial_leaves_the_untwisted_task_as_it_was():
    """Off is the default and adds nothing to the task: no key, no turn, the
    same id.  (The manifests' own check holds every board set to its ids.)"""
    for kwargs in ({"task_type": "stationing"}, {"task_type": "plan-sheet", "sheets": 2},
                   {"task_type": "pavement", "curves": 2, "equations": True}):
        plain = generate_task(1000, **kwargs)
        for off in (False, None, 0, 0.0, 360.0):
            assert generate_task(1000, twist=off, **kwargs).task_id == plain.task_id
        D = plain.brief.deliverable
        assert "view_rotation" not in D
        assert all(sh["viewport"]["rotation_deg"] == 0.0 and "north_arrow" not in sh
                   and "twist_deg" not in sh for sh in D["sheets"])
        assert "turned" not in plain.brief.prompts["explicit"]


def test_a_seeds_twist_is_its_own_and_never_slight():
    twists = [seed_twist(seed) for seed in range(13000, 13600)]
    assert twists == [seed_twist(seed) for seed in range(13000, 13600)]
    assert all(TWIST_MIN_DEG <= abs(t) <= 180.0 and round(t, 2) == t for t in twists)
    assert min(twists) < -150.0 and max(twists) > 150.0 and len(set(twists)) > 590
    assert seed_twist(13001) == 62.48  # the stream is the seed's, not the process's


@pytest.mark.parametrize("ttype, sheets", [("annotate-sheet", 1), ("stationing", 2),
                                           ("sheet-setup", 2), ("plan-sheet", 1)])
def test_a_twisted_task_turns_the_road_under_the_same_sheet(ttype, sheets):
    """The seed's road, stationing and paper layout are its untwisted task's,
    to the hundredth of a foot its PIs are rounded to: the road is turned under
    the sheet and the viewport turned back, so every point of the line plots
    where it did."""
    seed = 13001
    plain = generate_task(seed, curves=2, task_type=ttype, sheets=sheets)
    turned = generate_task(seed, curves=2, task_type=ttype, sheets=sheets, twist=True)
    twist = seed_twist(seed)
    assert turned.task_id != plain.task_id
    P, T = plain.brief.deliverable, turned.brief.deliverable
    assert T["view_rotation"] == twist and T["feet_per_inch"] == P["feet_per_inch"]
    for a, b in zip(P["sheets"], T["sheets"]):
        assert b["viewport"]["rotation_deg"] == twist
        assert b["viewport"]["center_paper"] == a["viewport"]["center_paper"]
        # a two-sheet viewport is sized round its lettering, and the turned road's bearings
        # read differently (other letters, other widths): the same frame to a few hundredths
        assert [b["viewport"][k] for k in ("width_in", "height_in")] == pytest.approx(
            [a["viewport"][k] for k in ("width_in", "height_in")], abs=0.05)
        assert b["station_range"] == pytest.approx(a["station_range"], abs=0.05)
        assert [m["station"] for m in b["matches"]] == [m["station"] for m in a["matches"]]
        assert b["north_arrow"] == {"position": [31.6, 19.2], "scale": 0.9, "rotation_deg": twist}
        # only a task that lays the sheet out is held to the viewport's turn
        assert (b.get("twist_deg") == twist) == ("sheet" in TASK_TYPES[ttype].asks)
    length = Alignment.from_dict(plain.brief.design["alignments"]["ALIGN-1"]).length
    for i in range(sheets):
        for k in range(11):
            p, q = _paper(plain, length * k / 10.0, i), _paper(turned, length * k / 10.0, i)
            assert geo.distance(p, q) < 0.01, (i, k, p, q)
    # the road itself is turned by the twist, the other way
    a0 = Alignment.from_dict(plain.brief.design["alignments"]["ALIGN-1"]).elements[0]
    a1 = Alignment.from_dict(turned.brief.design["alignments"]["ALIGN-1"]).elements[0]
    assert (a0.direction_deg - a1.direction_deg - twist + 180.0) % 360.0 - 180.0 == pytest.approx(
        0.0, abs=0.01)


@pytest.mark.parametrize("ttype, sheets, curves", [("annotate-sheet", 2, 3), ("stationing", 1, 1),
                                                   ("title-block", 2, 2), ("sheet-setup", 2, 2),
                                                   ("plan-sheet", 1, 2), ("annotate-base", 1, 3),
                                                   ("curve-table", 1, 2), ("bearings", 2, 2),
                                                   ("pavement-widths", 1, 2), ("pavement", 2, 3),
                                                   ("plan-sheet-pavement", 2, 3)])
def test_the_reference_scores_100_on_a_twisted_task_and_the_start_scores_0(ttype, sheets, curves):
    from roaddraft.verify import verify
    task = generate_task(13010 + curves, curves=curves, task_type=ttype, sheets=sheets,
                         equations=bool(curves % 2), twist=True)
    for level in ("explicit", "vague"):
        session = session_for_task(task)
        assert verify(session.doc, task.truth, prompt_level=level).rubric_score == 0.0
        reference_solution(task, session)
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.rubric_score == 100.0, [(c.id, c.credit) for c in report.in_scope()]


def test_lettering_that_ignores_the_twist_reads_upside_down_and_loses_for_it():
    """What the dial is for: on a sheet turned half a turn, lettering made to
    read in the model plots upside down (D1-08), and an arrow left pointing up
    the sheet is not pointing north (D1-11)."""
    from roaddraft.tasks.reference import solution_commands
    from roaddraft.verify import verify
    task = generate_task(13002, curves=2, task_type="annotate-sheet", twist=180.0)
    assert task.brief.deliverable["view_rotation"] == 180.0
    session = session_for_task(task)
    for name, params in solution_commands(task):
        params = {k: v for k, v in params.items() if k != "view_rotation"}
        if name == "insert_block":
            params.pop("rotation_deg", None)
        assert session.execute(name, params)["ok"]
    report = verify(session.doc, task.truth, prompt_level="vague")
    lost = {c.id: c for c in report.in_scope() if c.credit < 1.0}
    assert set(lost) == {"D1-08", "D1-11"}
    assert {f.code for f in lost["D1-08"].findings} == {"upside_down"}
    assert lost["D1-11"].credit == 0.5 and report.rubric_score < 95.0


def test_the_twist_dial_refuses_a_task_it_cannot_twist():
    for ttype in ("draw-alignment", "layer-setup", "create-alignment"):
        with pytest.raises(ValueError, match="no sheet"):
            generate_task(13000, task_type=ttype, twist=True)
    assert generate_task(13000, task_type="pavement-edges", twist=True).brief.deliverable[
        "view_rotation"] == seed_twist(13000)
    # a width dimension's text reads through the twist since place_dimension takes
    # view_rotation (training plan decision 9, 2026-11-13): the width types twist too
    for ttype in ("pavement-widths", "pavement", "plan-sheet-pavement"):
        task = generate_task(13000, curves=2, task_type=ttype, twist=True)
        assert task.brief.deliverable["view_rotation"] == seed_twist(13000)
        assert task.brief.deliverable["width_dimensions"]


def test_the_reference_gives_a_twisted_width_dimension_the_viewports_turn():
    """The reference's dimensions carry the twist as the lettering does, and a
    dimension made without it can plot upside down on a sheet turned half a
    turn and lose for it (D1-08).  Not every one does: the verifier reads text
    square to a line as far round as 135 degrees, so a number set between -90
    and -45 in the model still passes, which is why the drafter's keep rule
    looks at the twist itself (``grounded.twist_ignored``)."""
    from roaddraft.tasks.reference import solution_commands
    from roaddraft.verify import verify
    task = generate_task(13005, curves=2, task_type="pavement-widths", twist=180.0)
    dims = [params for name, params in solution_commands(task) if name == "place_dimension"]
    assert dims and all(p["view_rotation"] == 180.0 for p in dims)
    plain = generate_task(13005, curves=2, task_type="pavement-widths")
    assert all("view_rotation" not in params for name, params in solution_commands(plain)
               if name == "place_dimension")
    session = session_for_task(task)
    made = []
    for name, params in solution_commands(task):
        r = session.execute(name, {k: v for k, v in params.items() if k != "view_rotation"})
        assert r["ok"], r
        made += r["created"] if name == "place_dimension" else []
    report = verify(session.doc, task.truth, prompt_level="vague")
    lost = {c.id: c for c in report.in_scope() if c.credit < 1.0}
    assert set(lost) == {"D1-08"} and len(made) == 3
    assert {f.code for f in lost["D1-08"].findings} == {"upside_down"}
    flipped = {i for f in lost["D1-08"].findings for i in f.entity_ids}
    assert len(flipped) == 2 and flipped < set(made)
    # the width itself is still read right: the number, at the station
    assert all(c.credit == 1.0 for c in report.in_scope() if c.id == "D1-13")
    # with the twist, nothing is lost
    session = session_for_task(task)
    reference_solution(task, session)
    assert verify(session.doc, task.truth, prompt_level="vague").rubric_score == 100.0


def test_a_twisted_width_prompt_gives_the_turn_at_the_explicit_level_and_where_a_layout_is_asked():
    twist = f"{seed_twist(16001):.2f}°"
    for ttype in ("pavement-widths", "pavement"):
        prompts = generate_task(16001, curves=2, task_type=ttype, twist=True).brief.prompts
        assert prompts["explicit"].endswith(
            f" The viewport is turned {twist}, so set the dimension text to read upright on "
            f"the plotted sheet.")
        assert "turned" not in prompts["vague"]  # the drafter has to look at the sheet
        plain = generate_task(16001, curves=2, task_type=ttype).brief.prompts
        assert prompts["vague"] == plain["vague"]
        assert plain["explicit"] == prompts["explicit"][:len(plain["explicit"])]
    whole = generate_task(16001, curves=2, task_type="plan-sheet-pavement", sheets=2,
                          twist=True).brief.prompts
    assert f", the viewports turned {twist}, with the pavement edges" in whole["vague"]
    assert (f"the viewports turned {twist}. ALIGN-1 is already in the design and is two "
            in whole["explicit"])
    assert ("Letter model-space labels to read upright on the plotted sheets. Set the dimension "
            "text to read upright on the plotted sheets too.\n- ") in whole["explicit"]
    plain = generate_task(16001, curves=2, task_type="plan-sheet-pavement", sheets=2).brief.prompts
    assert "turned" not in plain["vague"] and "upright" not in plain["explicit"]


def test_a_twisted_prompt_gives_the_turn_where_the_layout_is_asked_and_leaves_it_to_be_seen_otherwise():
    twist = f"{seed_twist(13001):.2f}°"
    lettered = generate_task(13001, curves=2, task_type="stationing", twist=True).brief.prompts
    assert f"viewport is turned {twist}" in lettered["explicit"]
    assert "read upright on the plotted sheet" in lettered["explicit"]
    assert lettered["vague"] == "Station ALIGN-1."  # the drafter has to look at the sheet
    for ttype in ("sheet-setup", "plan-sheet"):
        prompts = generate_task(13001, curves=2, task_type=ttype, twist=True).brief.prompts
        assert f"turned {twist}" in prompts["explicit"]
        assert prompts["vague"].endswith(f", the viewport turned {twist}.")
    titled = generate_task(13001, curves=2, task_type="title-block", twist=True).brief.prompts
    assert f"turned {twist} to point to true north" in titled["explicit"]
    assert "turned" not in titled["vague"]


def test_every_real_type_sits_in_one_question_group():
    """The real-sheet types by question type (decided 2026-10-24): the draw and
    the real board's columns rest on every real type having exactly one group,
    and on the seeded types having none."""
    from roaddraft.tasks.types import (D1_REAL_GROUPS, REAL_GROUP_OF, REAL_GROUP_ORDER, REAL_GROUPS,
                                       REAL_JOB_TYPES, REAL_TASK_TYPES, real_group)
    listed = [ty for _, _, types in REAL_GROUPS for ty in types]
    assert len(listed) == len(set(listed)), "a type sits in one group"
    assert set(listed) == set(REAL_TASK_TYPES) | set(REAL_JOB_TYPES), \
        "every real type has a group; every grouped type exists"
    assert REAL_GROUP_ORDER == ("draft", "letter", "sheet", "notes", "job")
    assert {real_group(ty) for ty in REAL_TASK_TYPES} == {"draft", "letter", "sheet", "notes"}
    # the whole job (2026-11-03): its own group, the composites only, which d1-real does not draw
    assert REAL_GROUPS[4][:2] == ("job", "the whole job") and set(REAL_GROUPS[4][2]) == set(REAL_JOB_TYPES)
    assert D1_REAL_GROUPS == ("draft", "letter", "sheet", "notes")
    assert not any(ty in REAL_GROUP_OF for ty in TASK_TYPES), "the seeded types are not grouped"
    with pytest.raises(ValueError, match="REAL_GROUPS"):
        real_group("plan-sheet")


# ------------------------------------------------------------ the crowd dial (2026-11-12)

CROWDED = [("annotate-sheet", 3, True), ("stationing", 1, False), ("bearings", 2, True),
           ("curve-callouts", 2, False), ("annotate-base", 1, True)]


def _crowded(ttype, curves, twist, seed=14100):
    return generate_task(seed + curves, curves=curves, task_type=ttype, twist=twist, crowd=True)


def test_the_crowd_dial_leaves_the_uncrowded_task_as_it_was():
    """Off is the default and adds nothing to the task: no key, no pose, no
    list of what was handed over, the same id and prompts."""
    for kwargs in ({"task_type": "stationing"}, {"task_type": "annotate-base", "curves": 2},
                   {"task_type": "annotate-sheet", "curves": 2, "twist": True}):
        plain = generate_task(1000, **kwargs)
        assert generate_task(1000, crowd=False, **kwargs).task_id == plain.task_id
        D = plain.brief.deliverable
        assert "crowd" not in D and "label_poses" not in D
        assert not any("given_entities" in sh for sh in plain.truth.sheets)
        assert "crowded" not in plain.brief.prompts["vague"]
        assert "ALIGN-2" not in plain.brief.prompts["explicit"]


@pytest.mark.parametrize("ttype, curves, twist", CROWDED)
def test_a_crowded_task_is_the_seeds_own_road_on_a_sheet_already_worked_on(ttype, curves, twist):
    from roaddraft.document.document import Document
    from roaddraft.tasks.crowd import CROWD_NAME, NOTE_LAYER
    seed = 14100 + curves
    plain = generate_task(seed, curves=curves, task_type=ttype, twist=twist)
    task = _crowded(ttype, curves, twist)
    assert task.task_id != plain.task_id
    assert task.task_id == _crowded(ttype, curves, twist).task_id  # the seed's own crowd
    assert task.brief.design == plain.brief.design
    P, D = plain.brief.deliverable, task.brief.deliverable
    assert {k: v for k, v in D.items() if k not in ("crowd", "label_poses")} == P
    crowd = D["crowd"]
    assert crowd["alignment"]["name"] == CROWD_NAME and 1 <= len(crowd["notes"]) <= 2
    assert D["label_poses"]  # something has to move for the reference to clear it
    # the second line is in the design the sheet shows, drawn and lettered; the notes on the paper
    doc = Document.from_dict(task.baseline)
    holder = (Document.from_dict(task.files[D["basefile"]]) if ttype == "annotate-base" else doc)
    assert CROWD_NAME in holder.design.alignments
    assert list(holder.design.alignments)[0] == "ALIGN-1"
    lettered = [e for e in doc.model_entities.values()
                if (e.anchor or {}).get("alignment", "").endswith(CROWD_NAME)]
    assert {e.anchor["kind"] for e in lettered} >= {"station", "bearing", "tick"}
    sheet = doc.sheet_by_ref("C-101")
    notes = [e for e in sheet.entities.values() if e.layer == NOTE_LAYER]
    assert sorted(e.content for e in notes) == sorted(n["content"] for n in crowd["notes"])
    # everything handed over is listed, so only new work is charged for sitting on it
    given = set(doc.model_entities) | set(sheet.entities)
    assert all(set(sh["given_entities"]) == given for sh in task.truth.sheets)
    assert doc.meta["task_id"] == task.task_id
    # and the prompts say so, at each level in its own words
    assert "The sheet is crowded; keep everything already on it." in task.brief.prompts["vague"]
    assert f"another line, {CROWD_NAME}, across ALIGN-1" in task.brief.prompts["explicit"]
    assert "ALIGN-1" in task.brief.prompts["vague"]  # with two lines the request names its own


@pytest.mark.parametrize("ttype, curves, twist", CROWDED)
def test_the_default_poses_land_on_the_crowd_and_the_truths_poses_clear_it(ttype, curves, twist):
    """What the dial is for: the engine's default poses put a label on the
    second line's lettering and one on each note (D1-08), and the reference,
    with the truth's poses, scores 100 at both levels from a start that
    scores 0."""
    import copy
    from roaddraft.tasks.brief import Task
    from roaddraft.verify import verify
    task = _crowded(ttype, curves, twist)
    for level in ("explicit", "vague"):
        session = session_for_task(task)
        assert verify(session.doc, task.truth, prompt_level=level).rubric_score == 0.0
        reference_solution(task, session)
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.rubric_score == 100.0, [(c.id, c.credit) for c in report.in_scope()]
    brief = copy.deepcopy(task.brief)
    del brief.deliverable["label_poses"]
    blind = Task(brief=brief, truth=task.truth, baseline=task.baseline, files=task.files)
    session = session_for_task(blind)
    reference_solution(blind, session)
    report = verify(session.doc, task.truth)
    lost = {c.id: c for c in report.in_scope() if c.credit < 1.0}
    assert set(lost) == {"D1-08"} and {f.code for f in lost["D1-08"].findings} == {"overlap"}
    given = set(task.truth.sheets[0]["given_entities"])
    pairs = [f.entity_ids for f in lost["D1-08"].findings]
    assert all(any(i in given for i in pair) and any(i not in given for i in pair)
               for pair in pairs)
    assert len(pairs) >= 1 + len(task.brief.deliverable["crowd"]["notes"])


def test_the_crowd_dial_refuses_a_task_it_cannot_crowd():
    for ttype in ("plan-sheet", "sheet-setup", "curve-table", "title-block", "draw-alignment"):
        with pytest.raises(ValueError, match="crowd dial fits"):
            generate_task(14000, task_type=ttype, crowd=True)
    with pytest.raises(ValueError, match="one sheet"):
        generate_task(14000, task_type="stationing", sheets=2, crowd=True)


# ------------------------------------------------------------ the revision dial (2026-11-12)


def _revised_entry(ttype: str, kind: str, twist: bool = False):
    from roaddraft.eval import taskset as tasksets
    return next(e for e in tasksets.load("d1-train-revise")["tasks"]
                if e["task_type"] == ttype and e["revise"] == kind
                and bool(e.get("twist")) == twist and "dialed" not in e)


REVISED = [("annotate-base", "radius", False), ("annotate-base", "pi", True),
           ("annotate-base", "station", False), ("annotate-sheet", "radius", True),
           ("annotate-sheet", "pi", False), ("annotate-sheet", "station", True)]


def _revised(ttype, kind, twist):
    e = _revised_entry(ttype, kind, twist)
    return (generate_task(e["seed"], curves=e["curves"], task_type=ttype, twist=twist),
            generate_task(e["seed"], curves=e["curves"], task_type=ttype, twist=twist,
                          revise=kind))


def test_the_revision_dial_leaves_the_unrevised_task_as_it_was():
    for kwargs in ({"task_type": "annotate-base", "curves": 2},
                   {"task_type": "annotate-sheet", "curves": 3, "twist": True}):
        plain = generate_task(1000, **kwargs)
        assert generate_task(1000, revise=None, **kwargs).task_id == plain.task_id
        assert generate_task(1000, revise=False, **kwargs).task_id == plain.task_id
        assert "revision" not in plain.brief.deliverable
        assert "revised" not in plain.brief.prompts["explicit"]


@pytest.mark.parametrize("ttype, kind, twist", REVISED)
def test_a_revised_task_is_the_finished_sheet_with_its_design_changed_under_it(ttype, kind, twist):
    from roaddraft.tasks.revise import station_text
    plain, task = _revised(ttype, kind, twist)
    assert task.task_id != plain.task_id
    R = task.brief.deliverable["revision"]
    assert R["kind"] == kind
    old = Alignment.from_dict(plain.brief.design["alignments"]["ALIGN-1"])
    new = Alignment.from_dict(task.brief.design["alignments"]["ALIGN-1"])
    if kind == "station":
        assert new.begin_station == old.begin_station + R["by"]
        assert [p.point for p in new.pis] == [p.point for p in old.pis]
        assert R["to"] == station_text(new.begin_station)
    elif kind == "radius":
        assert new.begin_station == old.begin_station
        assert new.curves()[R["curve"] - 1].radius == R["to"]
        assert old.curves()[R["curve"] - 1].radius == R["from"]
        assert [p.point for p in new.pis] == [p.point for p in old.pis]
    else:
        moved = [i for i, (a, b) in enumerate(zip(old.pis, new.pis)) if a.point != b.point]
        assert len(moved) == 1 and [p.radius for p in new.pis] == [p.radius for p in old.pis]
    # in a base drawing the designer has made the change, its linework redrawn to it; in this
    # file's own design the change is the drafter's to make, and the design is graded
    doc = Document.from_dict(task.baseline)
    scope = set(task.truth.scope)
    assert "revision" in scope
    if ttype == "annotate-base":
        base = Document.from_dict(task.files[task.brief.deliverable["basefile"]])
        assert base.design.alignments["ALIGN-1"].to_dict() == new.to_dict()
        assert not doc.design.alignments
        assert not R["by_drafter"] and not {"design", "linework"} & scope
    else:
        assert doc.design.alignments["ALIGN-1"].to_dict() == old.to_dict()
        assert R["by_drafter"] and {"design", "linework"} <= scope and R["stale"] == []
    # the lettering is the old design's, and the notes cite the old stations
    sheet = doc.sheet_by_ref("C-101")
    assert all(i in doc.model_entities or i in sheet.entities for i in R["stale"])
    if ttype == "annotate-base":
        assert ("TB-001" in R["stale"]) == (kind != "station")
    assert 1 <= len(R["notes"]) <= 2
    for note in R["notes"]:
        assert sheet.entities[note["id"]].content == note["before"]
    if kind != "pi" or len(new.curves()) > 1:
        assert R["notes"][0]["after"] != R["notes"][0]["before"]
    # the prompts: the change at both levels, the notes only where the conventions are stated
    said = (f"radius is now {R['to']:g}'" if kind == "radius" else
            f"has moved {abs(R['by']):.2f} ft" if kind == "pi" else
            f"restationed to begin at {R['to']}")
    for level in ("explicit", "vague"):
        assert said in task.brief.prompts[level]
        assert ("Make the change" in task.brief.prompts[level]) == (ttype == "annotate-sheet")
    assert "restationed" in task.brief.prompts["explicit"]
    assert "note" not in task.brief.prompts["vague"]


@pytest.mark.parametrize("ttype, kind, twist", REVISED)
def test_the_reference_takes_off_the_old_lettering_and_restations_the_notes(ttype, kind, twist):
    from roaddraft.tasks.revise import left_stale
    from roaddraft.verify import verify
    _plain, task = _revised(ttype, kind, twist)
    start = session_for_task(task)
    assert verify(start.doc, task.truth, prompt_level="vague").effective_score < 100.0
    R = task.brief.deliverable["revision"]
    if R["stale"] or any(n["after"] != n["before"] for n in R["notes"]):
        assert left_stale(task, start.doc)
    for level in ("explicit", "vague"):
        session = session_for_task(task)
        reference_solution(task, session)
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.rubric_score == 100.0, [(c.id, c.credit) for c in report.in_scope()]
        assert left_stale(task, session.doc) == []


def test_lettering_again_beside_the_old_or_leaving_a_note_is_left_stale():
    """What the keep rule's leg sees: the line lettered again with what was there
    left on, or every note left as it read."""
    import copy
    from roaddraft.tasks.reference import solution_commands
    from roaddraft.tasks.revise import left_stale
    _plain, task = _revised("annotate-base", "radius", False)
    commands = solution_commands(task)
    for drop in ("delete_entities", "modify_entity"):
        session = session_for_task(task)
        for name, params in commands:
            if name != drop:
                assert session.execute(name, copy.deepcopy(params))["ok"]
        left = left_stale(task, session.doc)
        R = task.brief.deliverable["revision"]
        if drop == "delete_entities":
            assert set(R["stale"]) <= set(left)
        else:
            assert [n["id"] for n in R["notes"] if n["after"] != n["before"]] == left


def test_where_the_drafter_makes_the_change_the_old_design_loses_on_the_design_itself():
    from roaddraft.verify import verify
    _plain, task = _revised("annotate-sheet", "radius", True)
    report = verify(session_for_task(task).doc, task.truth, prompt_level="vague")
    lost = {c.id for c in report.in_scope() if c.credit < 1.0}
    assert {"D1-15", "D1-01"} <= lost  # the design and the centerline drawn from it


def test_the_revision_dial_refuses_what_it_cannot_revise():
    for ttype in ("plan-sheet", "stationing", "curve-table"):
        with pytest.raises(ValueError, match="revision dial fits"):
            generate_task(15000, task_type=ttype, revise="radius")
    with pytest.raises(ValueError, match="one sheet"):
        generate_task(15000, task_type="annotate-base", sheets=2, revise="radius")
    with pytest.raises(ValueError, match="station equation"):
        generate_task(15000, task_type="annotate-base", equations=True, revise="station")
    with pytest.raises(ValueError, match="not both"):
        generate_task(15000, task_type="annotate-base", crowd=True, revise="station")
