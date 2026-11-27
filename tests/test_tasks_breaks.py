"""The training-only type ``plan-sheet-breaks`` (``tasks.breaks``) and its check
(``verify.breaks``): the sheet count and the breaks left to the drafter."""
import re

import pytest

from roaddraft.design.horizontal import TangentElement
from roaddraft.document.document import Document
from roaddraft.tasks import breaks
from roaddraft.tasks import generator as gen
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import reference_solution, session_for_task, solution_commands
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.tasks.types import (HARD_TASK_TYPES, OPEN_BREAKS, REAL_JOB_TYPES, REAL_TASK_TYPES,
                                   TASK_TYPES, TRAIN_TASK_TYPES, task_type)
from roaddraft.verify import VERIFIER_VERSION, verify
from roaddraft.verify.breaks import CHECK, read

LEVELS = ("explicit", "vague")
#: (seed, curves, sheets, twist) of tasks the set holds: one, two and three sheets, turned or not
ONE = (17004, 1, 1, False)
TWO = (17002, 3, 2, False)
TWO_TURNED = (17005, 2, 2, True)
THREE = (17001, 2, 3, False)
SAMPLE = (ONE, TWO, TWO_TURNED, THREE)
#: a line on one sheet with a whole station a match line could stand at, and one on two
#: sheets with another break the generator's own rule would fit
ONE_SPLIT = (17000, 1, 1, False)
TWO_OTHER = (17010, 3, 2, False)


def _task(seed, curves, sheets, twist=False):
    return generate_task(seed, curves=curves, task_type=breaks.TYPE, sheets=sheets, twist=twist)


def _drafted(task, commands=None):
    session = session_for_task(task)
    if commands is None:
        reference_solution(task, session)
    else:
        for name, params in commands:
            result = session.execute(name, params)
            assert result["ok"], (name, result.get("error"))
    return session


def _part(report):
    return report.check(CHECK["id"])


# ------------------------------------------------------------ the type and its prompts


def test_the_type_lives_in_a_registry_no_held_out_cycle_reads():
    # (the base lettering types joined the registry on 2026-11-25: tasks.bulk)
    assert list(TRAIN_TASK_TYPES)[0] == breaks.TYPE
    assert [n for n, t in TRAIN_TASK_TYPES.items() if OPEN_BREAKS in t.asks] == [breaks.TYPE]
    for registry in (TASK_TYPES, HARD_TASK_TYPES, REAL_TASK_TYPES, REAL_JOB_TYPES):
        assert breaks.TYPE not in registry
        assert not any(OPEN_BREAKS in t.asks for t in registry.values())
    from roaddraft.eval import taskset
    assert breaks.TYPE not in taskset.SEEDED_TYPES + taskset.HARD_SEEDED_TYPES
    assert breaks.TYPE not in DRAFTING_SPEC_V1["task_types"]
    ttype = task_type(breaks.TYPE)
    # the whole plan sheet job, plus the mark that sends its truth to verify.breaks
    assert ttype.asks == TASK_TYPES["plan-sheet"].asks | {OPEN_BREAKS}
    assert ttype.solution_phases() == TASK_TYPES["plan-sheet"].solution_phases()


@pytest.mark.parametrize("dials", SAMPLE)
def test_the_prompt_gives_the_line_the_scale_and_the_first_sheet_and_not_the_layout(dials):
    task = _task(*dials)
    D = task.brief.deliverable
    scale = f"1\" = {D['feet_per_inch']:g}'"
    names = [sh["name"] for sh in D["sheets"]]
    cuts = [m["station_text"] for sh in D["sheets"] for m in sh["matches"]]
    for level in LEVELS:
        text = task.brief.prompts[level]
        assert "ALIGN-1" in text and scale in text and f"numbered from {names[0]}" in text
        for name in names[1:]:
            assert name not in text
        for cut in cuts:
            assert cut not in text
        # no count: not in a number, a word, or the grammar of the sheets (every explicit
        # prompt says a line that fits one sheet gets one, whatever the line)
        said = text.replace("A line that fits one sheet gets one sheet and no match line.", "")
        assert not re.search(r"\b(one|two|three|four) (ANSI \w )?(plan )?sheets?\b", said)
        assert f"of {len(names)}" not in text and "breaking at" not in text
        if dials[3]:
            assert f"every viewport turned {D['view_rotation']:.2f}°" in text
        else:
            assert "turned" not in text
    assert task.brief.prompts["vague"].startswith("Draft the plan sheets for ALIGN-1 at ")
    assert "ANSI D" in task.brief.prompts["explicit"]
    assert "ANSI D" not in task.brief.prompts["vague"]


def test_one_sheet_and_three_sheets_read_alike_but_for_the_line():
    """The prompt of a line that fits one sheet and of one that takes three
    differ only in what the document itself differs in: nothing of the layout."""
    one, three = _task(*ONE), _task(*THREE)

    def shape(task):
        text = task.brief.prompts["explicit"]
        text = re.sub(r"\d+\+\d+\.\d+", "#", text)
        text = re.sub(r"1\" = \d+'", "1\" = N'", text)
        text = re.sub(r"\d+ ft each side", "H ft each side", text)
        return re.sub(r"project .*?, agency .*?,|on the .*? project \(.*?\)|dated \S+", "@", text)

    assert shape(one) == shape(three)
    assert one.brief.prompts["vague"].split(" at ")[0] == three.brief.prompts["vague"].split(" at ")[0]


# ------------------------------------------------------------ the rules


def test_the_office_breaks_are_whole_stations_on_tangents_clear_of_their_ends():
    task = _task(*THREE)
    align, fpi, turn, own, _names = breaks.layout_of(task.truth)
    begin = float(align.begin_station)
    cuts = breaks.office_breaks(align)
    assert cuts and set(own) <= set(cuts)
    for d in cuts:
        assert (begin + d) % breaks.STATION_FT == 0
        el = align.elements[align.element_at(d)[0]]
        assert isinstance(el, TangentElement)
        assert d - el.start_dist >= breaks.CLEAR_FT and el.end_dist - d >= breaks.CLEAR_FT
        assert breaks.unsound(align, d) is None
    # the generator's own options are among them (it also keeps 300 ft from the line's ends)
    for options in gen._match_options(align, 2):
        assert options[0] in cuts


def test_a_match_line_is_unsound_near_a_lettered_point_and_sound_on_a_curve_clear_of_them():
    task = _task(*TWO)
    align = breaks.layout_of(task.truth)[0]
    curve = align.curves()[0]
    assert "BC of curve 1" in breaks.unsound(align, curve.start_dist - 20.0)
    assert "EC of curve 1" in breaks.unsound(align, curve.end_dist + 59.0)
    assert "middle of curve 1" in breaks.unsound(align, (curve.start_dist + curve.end_dist) / 2.0)
    assert "beginning" in breaks.unsound(align, 30.0)
    assert "end of the line" in breaks.unsound(align, align.length - 30.0)
    assert breaks.unsound(align, 0.0) and breaks.unsound(align, align.length + 5.0)
    # sixty feet is the generator's own distance, to the foot
    assert breaks.CLEAR_FT == gen.MATCH_CLEAR_FT == 60.0
    assert breaks.unsound(align, curve.start_dist - 60.0) is None
    quarter = curve.start_dist + (curve.end_dist - curve.start_dist) / 4.0
    if quarter - curve.start_dist >= 60.0:  # a long curve: a break on it, clear of its lettering
        assert breaks.unsound(align, quarter) is None


@pytest.mark.parametrize("dials", SAMPLE)
def test_the_fewest_sheets_is_the_generators_count_and_one_fewer_never_fits(dials):
    task = _task(*dials)
    align, fpi, turn, own, names = breaks.layout_of(task.truth)
    assert breaks.fewest(align, fpi, turn) == len(names) == dials[2]
    laid = gen._laid(align, turn)
    bounds = [0.0] + own + [min(align.length, laid.length)]
    assert all(breaks.stretch_fits(laid, a, b, fpi) for a, b in zip(bounds, bounds[1:]))
    if len(names) > 1:  # two of its stretches together are more than a sheet holds
        assert not any(breaks.stretch_fits(laid, a, c, fpi) for a, c in zip(bounds, bounds[2:]))
    # at a scale that shows four times as much, one sheet carries any of them
    assert breaks.fewest(align, 4 * fpi, turn) == 1


def test_a_layout_the_generator_spreads_over_more_sheets_than_carry_it_is_no_task():
    """``opened`` refuses a line laid on more sheets than it takes: its own
    breaks would fail the count.  (Found by scanning: of seeds 17000-17029 at
    three sheets and two or four curves, a few fit two.)"""
    refused = []
    for seed in range(17000, 17030):
        for curves in (2, 4):
            try:
                generate_task(seed, curves=curves, task_type=breaks.TYPE, sheets=3)
            except ValueError as why:
                if "sheet(s) where" in str(why):
                    refused.append((seed, curves, str(why)))
                    plain = generate_task(seed, curves=curves, task_type="plan-sheet", sheets=3)
                    align, fpi, turn, _own, names = breaks.layout_of(plain.truth)
                    assert breaks.fewest(align, fpi, turn) < len(names) == 3
            except AssertionError:
                pass
            if refused:
                break
        if refused:
            break
    assert refused, "no seed in the scan was laid on more sheets than it takes"


@pytest.mark.parametrize("dials", SAMPLE)
def test_the_layout_is_derived_from_its_breaks_as_the_generator_derives_it(dials):
    """``sheets_for`` gives the generator's sheets back from the generator's
    breaks, and ``rebuilt`` the task's own truth: the derivation a drafter's
    breaks are graded by is the one the generator's are."""
    task = _task(*dials)
    D = task.brief.deliverable
    align, fpi, turn, own, names = breaks.layout_of(task.truth)
    assert breaks.sheets_for(align, fpi, turn, own, names, D["sheets"][0]["title_block_fields"],
                             D["sheets"][0]["size"]) == D["sheets"]
    again = breaks.rebuilt(task.truth, own, names)
    assert again.sheets == task.truth.sheets and again.curve_tables == task.truth.curve_tables
    assert again.counts == task.truth.counts and again.labels == task.truth.labels
    assert OPEN_BREAKS in task.truth.scope and OPEN_BREAKS not in again.scope
    assert again.scope == generate_task(dials[0], curves=dials[1], task_type="plan-sheet",
                                        sheets=dials[2], twist=dials[3]).truth.scope
    assert breaks.sheet_names(3) == ["C-101", "C-102", "C-103"]


# ------------------------------------------------------------ the check


@pytest.mark.parametrize("dials", SAMPLE)
def test_the_reference_scores_100_and_the_start_0_at_both_levels(dials):
    task = _task(*dials)
    session = _drafted(task)
    for level in LEVELS:
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.effective_score == 100.0, [(c.id, c.credit) for c in report.in_scope()]
        assert report.verifier_version == VERIFIER_VERSION
        assert _part(report).credit == 1.0 and _part(report).weight == CHECK["weight"]
        assert OPEN_BREAKS in report.scope
        start = verify(Document.from_dict(task.baseline), task.truth, prompt_level=level)
        assert start.effective_score == 0.0 and _part(start).credit == 0.0
    found = read(session.doc, task.truth, DRAFTING_SPEC_V1)
    assert [ps.name for ps in found.sheets] == [sh["name"] for sh in task.truth.sheets]
    assert found.breaks == pytest.approx(breaks.layout_of(task.truth)[3])


def test_a_truth_without_the_mark_is_graded_as_it_always_was():
    """The same drawing against the plain plan sheet job's truth: the spec's
    checks alone, no ``D1-17``, and the same credits the marked truth's D1
    checks get for the generator's breaks."""
    task = _task(*TWO)
    plain = generate_task(TWO[0], curves=TWO[1], task_type="plan-sheet", sheets=TWO[2])
    assert OPEN_BREAKS not in plain.truth.scope
    session = _drafted(task)
    for level in LEVELS:
        was = verify(session.doc, plain.truth, prompt_level=level)
        now = verify(session.doc, task.truth, prompt_level=level)
        assert CHECK["id"] not in [c.id for c in was.checks]
        assert [(c.id, c.credit, c.in_scope) for c in was.checks] == [
            (c.id, c.credit, c.in_scope) for c in now.checks if c.id != CHECK["id"]]


def _other_breaks(task):
    """Other sets of office breaks that lay the line on as many sheets, each
    stretch fitting with its lettering as the generator fits its own."""
    align, fpi, turn, own, names = breaks.layout_of(task.truth)
    laid = gen._laid(align, turn)
    labels = gen._label_boxes(align, fpi, turn)
    out = []
    for d in breaks.office_breaks(align):
        other = sorted([d] + own[1:])
        if d in own or len(set(other)) != len(own):
            continue
        bounds = [0.0] + other + [align.length]
        if all(gen._fits_window(gen._sheet_box(laid, a, b, fpi, labels), fpi, pad=0.0)
               for a, b in zip(bounds, bounds[1:])):
            out.append(other)
    return out


@pytest.mark.parametrize("dials", (TWO_OTHER, TWO_TURNED, THREE))
def test_another_sound_set_of_breaks_scores_100(dials):
    task = _task(*dials)
    others = _other_breaks(task)
    assert others, "the line has only the generator's own breaks"
    own = breaks.layout_of(task.truth)[3]
    # the ones furthest from the generator's own, each way
    for other in sorted({tuple(others[0]), tuple(others[-1])}):
        other = list(other)
        assert other != own
        session = _drafted(breaks.with_breaks(task, other))
        for level in LEVELS:
            report = verify(session.doc, task.truth, prompt_level=level)
            assert report.effective_score == 100.0, (other, [(c.id, c.credit, [f.note for f in c.findings])
                                                             for c in report.in_scope() if c.credit < 1])
        # and against the generator's own breaks, as a stated-break task grades it, it fails
        plain = generate_task(dials[0], curves=dials[1], task_type="plan-sheet", sheets=dials[2],
                              twist=dials[3])
        assert verify(session.doc, plain.truth).effective_score < 100.0


def test_a_break_on_a_curve_clear_of_its_lettering_scores_100():
    """The generator never breaks on a curve; the pilot grader takes a break
    anywhere.  Here one is sound sixty feet from the curve's BC, middle and EC."""
    from roaddraft.design.horizontal import CurveElement
    task = _task(*TWO)
    align, fpi, turn, own, _names = breaks.layout_of(task.truth)
    laid, begin = gen._laid(align, turn), float(align.begin_station)
    on_curve = [d for d in (100.0 * k - begin for k in range(int(begin // 100) + 1,
                                                             int((begin + align.length) // 100)))
                if isinstance(align.elements[align.element_at(d)[0]], CurveElement)
                and breaks.unsound(align, d) is None
                and breaks.stretch_fits(laid, 0.0, d, fpi)
                and breaks.stretch_fits(laid, d, align.length, fpi)]
    assert on_curve and on_curve[0] not in breaks.office_breaks(align)
    session = _drafted(breaks.with_breaks(task, [on_curve[0]]))
    for level in LEVELS:
        assert verify(session.doc, task.truth, prompt_level=level).effective_score == 100.0


def test_more_sheets_than_the_line_takes_scores_under_100():
    task = _task(*TWO)
    align, fpi, turn, own, _names = breaks.layout_of(task.truth)
    cuts = breaks.office_breaks(align)
    third = next(d for d in cuts if d > own[0] + 150.0)
    session = _drafted(breaks.with_breaks(task, [own[0], third]))
    for level in LEVELS:
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.effective_score < 100.0
        assert _part(report).credit == pytest.approx(0.8)
        assert any("the line takes 2" in (f.note or "") for f in _part(report).findings)
        # everything else was drafted right for the three sheets it used
        assert [c.id for c in report.in_scope() if c.credit < 1.0] == [CHECK["id"]]
    # a line that fits one sheet, drafted on two
    one = _task(*ONE_SPLIT)
    align = breaks.layout_of(one.truth)[0]
    split = breaks.office_breaks(align)
    session = _drafted(breaks.with_breaks(one, [split[len(split) // 2]]))
    report = verify(session.doc, one.truth)
    assert report.effective_score < 100.0
    assert any("the line takes 1" in (f.note or "") for f in _part(report).findings)


def test_a_stretch_cut_by_its_frame_scores_under_100():
    task = _task(*TWO)
    session = _drafted(task)
    sheet = session.doc.sheet_by_ref("C-101")
    vp = sheet.viewports[0]
    result = session.execute("modify_viewport", {"sheet": "C-101", "viewport_id": vp.id,
                                                 "changes": {"width_in": vp.width_in / 2.0}})
    assert result["ok"]
    for level in LEVELS:
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.effective_score < 100.0
        notes = [f.note or "" for f in _part(report).findings]
        assert any("shows all of its stretch" in n for n in notes)
        assert _part(report).credit == pytest.approx(0.8)
        assert report.check("D1-00").credit < 1.0


def test_lettering_of_a_stretch_left_outside_its_frame_scores_under_100():
    """The frame still holds the centerline of its stretch, but not all of the
    stretch's lettering: the curve points' labels stand an inch off the line."""
    task = _task(*TWO)
    session = _drafted(task)
    found = read(session.doc, task.truth, DRAFTING_SPEC_V1)
    align = found.align
    cut = None
    for ps, (lo, hi) in zip(found.sheets, found.stretches()):
        vp, transform, _window = ps.views[0]
        pts = [transform.to_paper(align.point_at(lo + (hi - lo) * k / 200.0)) for k in range(201)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        tight = {"width_in": round(max(xs) - min(xs) + 0.1, 3),
                 "height_in": round(max(ys) - min(ys) + 0.1, 3),
                 "model_center": transform.to_model([(min(xs) + max(xs)) / 2.0,
                                                     (min(ys) + max(ys)) / 2.0])}
        assert session.execute("modify_viewport", {"sheet": ps.name, "viewport_id": vp.id,
                                                   "changes": tight})["ok"]
        cut = ps.name
    assert cut
    report = verify(session.doc, task.truth)
    assert report.effective_score < 100.0
    assert any("not shown whole" in (f.note or "") for f in _part(report).findings)


def test_a_missing_match_line_scores_under_100():
    task = _task(*TWO)
    commands = [(name, params) for name, params in solution_commands(task)
                if name != "draw_station_offset"
                and not (name == "place_label" and params.get("kind") == "custom")]
    assert len(commands) == len(solution_commands(task)) - 3
    session = _drafted(task, commands)
    for level in LEVELS:
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.effective_score < 100.0
        assert any("2 plan sheet(s) but 0 break(s)" in (f.note or "")
                   for f in _part(report).findings)
        assert _part(report).credit == pytest.approx(0.4)  # the count and the numbering stand
        assert report.check("D1-00").credit < 1.0          # and the sheet check misses it too
    # the line drawn but lettered on neither sheet: the break is read, its labels are missed
    commands = [(name, params) for name, params in solution_commands(task)
                if not (name == "place_label" and params.get("kind") == "custom")]
    session = _drafted(task, commands)
    report = verify(session.doc, task.truth)
    assert _part(report).credit == 1.0 and report.check("D1-00").credit < 1.0
    assert report.effective_score < 100.0


def test_a_break_too_near_a_curve_point_scores_under_100():
    task = _task(*TWO)
    align, fpi, turn, own, _names = breaks.layout_of(task.truth)
    el = align.elements[align.element_at(own[0])[0]]
    near = el.end_dist - 25.0 if el.end_dist < align.length else el.start_dist + 25.0
    assert breaks.unsound(align, near)
    session = _drafted(breaks.with_breaks(task, [near]))
    report = verify(session.doc, task.truth, prompt_level="vague")
    assert report.effective_score < 100.0
    assert any("not where a match line is sound" in (f.note or "")
               for f in _part(report).findings)


def test_sheets_numbered_another_way_score_under_100():
    task = _task(*TWO)
    own = breaks.layout_of(task.truth)[3]
    session = _drafted(breaks.with_breaks(task, own, names=["C-201", "C-202"]))
    for level in LEVELS:
        report = verify(session.doc, task.truth, prompt_level=level)
        assert report.effective_score < 100.0
        assert any("not numbered on from C-101" in (f.note or "") for f in _part(report).findings)
        # the rest is graded under the names the drafter gave its sheets
        assert [c.id for c in report.in_scope() if c.credit < 1.0] == [CHECK["id"]]
    # the wrong total lettered in a title block, which D1-10 lets through at the vague level
    session = _drafted(task)
    assert session.execute("fill_title_block", {"sheet": "C-102",
                                                "fields": {"total_sheets": "3"}})["ok"]
    report = verify(session.doc, task.truth, prompt_level="vague")
    assert report.check("D1-10").credit == 1.0 and _part(report).credit == pytest.approx(0.8)


def test_another_scale_does_not_buy_fewer_sheets():
    """At the vague level D1-00 takes any standard scale; the count is at the
    scale the task gives, so a line squeezed onto one sheet at a smaller scale
    is not the fewest sheets."""
    task = _task(*TWO)
    session = session_for_task(task)
    for name, params in solution_commands(breaks.with_breaks(task, [])):
        if name == "create_viewport":
            params = {**params, "feet_per_inch": 100.0}
        assert session.execute(name, params)["ok"]
    report = verify(session.doc, task.truth, prompt_level="vague")
    assert any("not at the scale asked" in (f.note or "") for f in _part(report).findings)
    assert report.effective_score < 100.0
