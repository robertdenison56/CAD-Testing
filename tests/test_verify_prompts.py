"""The prompt dial: every D1 task is posed in natural language at an explicit
and a vague level over one truth.  The explicit prompt states the standards
and is graded exactly; the vague prompt states only the request, and a
convention it never stated is graded by what is reasonable, not by the
spec's exact value.  What must be on the sheet is graded the same at both."""
from __future__ import annotations

import json

import pytest

from roaddraft.tasks.brief import TaskBrief
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.prompts import LEVELS, RULES, render_prompts, task_text
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1
from roaddraft.verify.semantic import column_key, same_cell, same_label, scale_fpi
from tests.verify_mutations import BASE, SHEET, Base

# ------------------------------------------------------------------ prompts


def test_levels_match_the_spec():
    assert set(LEVELS) == set(DRAFTING_SPEC_V1["prompt_levels"])


def test_explicit_prompt_states_the_standards_and_vague_only_the_request():
    task = generate_task(42, curves=2, equations=True)
    explicit, vague = task.brief.prompts["explicit"], task.brief.prompts["vague"]
    tb = task.brief.deliverable["sheets"][0]["title_block_fields"]
    for word in ("V-ALIGN-CNTR", "V-ROAD-STA", "V-ANNO-TEXT", "V-ANNO-TABL", "0.10 in",
                 "0.40 in", "12+34.56", "BC 16+00.00", "CH BRG", "STA 20+00.00 BK",
                 tb["scale"], tb["date"], "NORTH_ARROW", task.brief.project["name"]):
        assert word in explicit, word
        assert word not in vague, word
    for word in ("C-101", "ALIGN-1"):
        assert word in explicit and word in vague
    assert vague == "Draft plan sheet C-101 for ALIGN-1."
    assert task.brief.instructions.startswith(explicit)
    for level in LEVELS:
        assert task_text(task.brief, level).startswith(RULES)
        assert task_text(task.brief, level).endswith(task.brief.prompts[level])
    with pytest.raises(ValueError):
        task_text(task.brief, "chatty")


def test_no_equation_no_equation_line():
    task = generate_task(6, curves=2, equations=False)
    assert "BK =" not in task.brief.prompts["explicit"]


def test_prompts_ride_the_brief_and_old_briefs_still_load():
    task = generate_task(42)
    d = json.loads(task.brief.to_json())
    assert TaskBrief.from_dict(d).prompts == render_prompts(task.brief)
    d.pop("prompts")
    assert TaskBrief.from_dict(d).prompts == {}
    assert task_text(TaskBrief.from_dict(d), "vague").endswith(task.brief.prompts["vague"])


# ----------------------------------------------------------- by meaning


@pytest.mark.parametrize("kind,actual,expected,same", [
    ("station", "18+00", "18+00.00", True),
    ("station", "STA 18+00.0", "18+00.00", True),
    ("station", "18+00.01", "18+00.00", False),
    ("pc", "PC 16+00.00", "BC 16+00.00", True),
    ("pc", "BC STA 16+00", "BC 16+00.00", True),
    ("pc", "BC", "BC 16+00.00", False),
    ("pc", "EC 16+00.00", "BC 16+00.00", False),
    ("pt", "PT 17+10.5", "EC 17+10.50", True),
    ("mc", "CURVE 2", "C-2", True),
    ("mc", "C2", "C-2", True),
    ("mc", "C-3", "C-2", False),
    ("bearing", "N45-30-15E", "N 45°30'15\" E", True),
    ("bearing", "N 45°30'14\" E", "N 45°30'15\" E", True),
    ("bearing", "N 45°31'15\" E", "N 45°30'15\" E", False),
    ("bearing", "S 45°30'15\" W", "N 45°30'15\" E", False),
    ("equation", "STA 20+00 BACK = STA 25+00 AHEAD", "STA 20+00.00 BK = STA 25+00.00 AH", True),
    ("equation", "STA 20+00 BK = STA 26+00 AH", "STA 20+00.00 BK = STA 25+00.00 AH", False),
])
def test_same_label_by_meaning(kind, actual, expected, same):
    assert same_label(kind, actual, expected) is same


def test_table_cells_and_headers_by_meaning():
    assert column_key("RADIUS") == "radius" and column_key("Δ") == "delta"
    assert column_key("C") == "chord" and column_key("CURVE") == "curve"
    assert column_key("WIDTH") is None
    assert same_cell("radius", "800.0", "800.00'") and not same_cell("radius", "800.1", "800.00'")
    assert same_cell("delta", "25-30-00", "25°30'00\"")
    assert same_cell("direction", "RIGHT", "RT") and not same_cell("direction", "LT", "RT")
    assert same_cell("pi_sta", "STA 12+00", "12+00.00")
    assert scale_fpi("1\"=100'") == 100.0 and scale_fpi("1 in = 50 ft") == 50.0
    assert scale_fpi("1:1200") is None


# ---------------------------------------------- one drawing, two levels


def _score(b: Base):
    return {level: b.verify(level) for level in LEVELS}


def _clean(report, *except_checks):
    return all(c.credit == 1.0 and not c.findings for c in report.checks
               if c.id not in except_checks)


def test_station_written_without_decimals_is_wrong_only_when_the_format_was_stated():
    b = Base(**BASE)
    e = b.labels("station")[3]
    b.ex("modify_entity", {"id": e.id, "changes": {"content": e.content.replace(".00", "")}})
    r = _score(b)
    assert r["explicit"].hard_failed and r["vague"].effective_score == 100.0


def test_pc_wording_is_fine_when_bc_was_not_asked_for():
    b = Base(**BASE)
    e = b.label("PC-1", "pc")
    b.ex("modify_entity", {"id": e.id, "changes": {"content": e.content.replace("BC", "PC")}})
    r = _score(b)
    assert r["explicit"].hard_failed and r["vague"].effective_score == 100.0


def test_a_wrong_value_is_wrong_at_every_level():
    b = Base(**BASE)
    e = b.label("PC-1", "pc")
    b.ex("modify_entity", {"id": e.id, "changes": {"content": e.content[:-1] + "9"}})
    r = _score(b)
    assert r["explicit"].hard_failed and r["vague"].hard_failed


def test_own_layer_names_pass_terse_and_layer_0_fails_both():
    b = Base(**BASE)
    b.ex("create_layer", {"name": "C-ANNO"})
    for e in b.labels():
        b.ex("modify_entity", {"id": e.id, "changes": {"layer": "C-ANNO"}})
    r = _score(b)
    assert r["vague"].effective_score == 100.0
    assert {f.code for f in r["explicit"].check("D1-09").findings} == {"wrong_layer"}
    for e in b.labels():
        b.ex("modify_entity", {"id": e.id, "changes": {"layer": "0"}})
    r = _score(b)
    assert r["vague"].check("D1-09").credit < 1.0 and r["explicit"].check("D1-09").credit < 1.0


def test_legible_but_unstated_text_height():
    b = Base(**BASE)
    fpi = b.D["feet_per_inch"]
    # 0.12 in, not the stated 0.10. Text plots at its cap height in DejaVu Sans, so
    # "194+00.00" is 7.7 heights long: 92 ft at 0.12 in on 1" = 100', clear of the next
    # station 100 ft on; at 0.14 in (108 ft) neighbouring station labels really overlap.
    for e in b.labels():
        b.ex("modify_entity", {"id": e.id, "changes": {"height": 0.12 * fpi}})
    r = _score(b)
    assert r["vague"].effective_score == 100.0
    assert r["explicit"].check("D1-09").credit < 1.0
    for e in b.labels():
        b.ex("modify_entity", {"id": e.id, "changes": {"height": 0.04 * fpi}})
    assert b.verify("vague").check("D1-09").credit < 1.0


def test_ticks_of_another_length_count_when_no_length_was_stated():
    b = Base(**BASE)
    stationing = b.ticks() + b.labels("station") + b.labels("pc") + b.labels("pt") \
        + b.labels("equation")
    b.ex("delete_entities", {"ids": [e.id for e in stationing]})
    b.ex("annotate_stationing", {"space": "model", "alignment": b.A, "interval": 100,
                                 "tick_half_len": 1.5 * b.D["tick_half_len_ft"],
                                 "text_height": b.D["text_heights"]["model_label_ft"],
                                 "label_offset": b.D["label_offset_ft"], "layer": "V-ROAD-STA",
                                 "label_layer": "V-ANNO-TEXT"})
    r = _score(b)
    assert r["vague"].effective_score == 100.0
    assert r["explicit"].check("D1-02").credit == 0.0
    assert {f.code for f in r["explicit"].check("D1-02").findings} == {"misplaced"}


def test_curve_table_columns_reordered():
    b = Base(**BASE)
    t = b.table()
    b.ex("delete_entities", {"ids": [t.id]})
    cols = list(reversed(b.D["curve_table_columns"]))
    b.ex("place_curve_table", {"space": SHEET, "alignment": b.A, "position": list(t.position),
                               "columns": cols, "text_height": t.text_height, "layer": t.layer})
    r = _score(b)
    assert r["vague"].effective_score == 100.0
    assert r["explicit"].check("D1-06").credit == pytest.approx(0.8)
    assert {f.code for f in r["explicit"].check("D1-06").findings} == {"wrong_field"}


def test_core_columns_only_is_a_full_table_when_columns_were_not_stated():
    b = Base(**BASE)
    t = b.table()
    b.ex("delete_entities", {"ids": [t.id]})
    b.ex("place_curve_table", {"space": SHEET, "alignment": b.A, "position": list(t.position),
                               "columns": ["curve", "delta", "radius", "length"],
                               "text_height": t.text_height, "layer": t.layer})
    r = _score(b)
    assert r["vague"].check("D1-06").credit == 1.0
    assert r["explicit"].check("D1-06").credit == 0.0
    b.ex("delete_entities", {"ids": [b.table().id]})
    b.ex("place_curve_table", {"space": SHEET, "alignment": b.A, "position": list(t.position),
                               "columns": ["curve", "radius", "length"],
                               "text_height": t.text_height, "layer": t.layer})
    assert b.verify("vague").check("D1-06").credit == 0.0


def test_title_block_values_the_terse_prompt_never_gave():
    b = Base(**BASE)
    b.ex("fill_title_block", {"sheet": SHEET, "fields": {"designed_by": "JQD",
                                                         "date": "2026-10-10",
                                                         "scale": "1\"=100'"}})
    r = _score(b)
    assert r["vague"].effective_score == 100.0
    assert r["explicit"].check("D1-10").credit == pytest.approx(0.7)
    b.ex("fill_title_block", {"sheet": SHEET, "fields": {"project": "SOMETHING ELSE",
                                                         "scale": "1\" = 50'"}})
    r = _score(b)
    assert r["vague"].check("D1-10").credit == pytest.approx(0.8)
    assert {f.note for f in r["vague"].check("D1-10").findings} == {
        "title block field project on sheet C-101", "title block field scale on sheet C-101"}


def test_any_standard_scale_when_none_was_stated():
    b = Base(**BASE)
    b.ex("modify_viewport", {"sheet": SHEET, "viewport_id": b.viewport.id,
                             "changes": {"feet_per_inch": 200.0}})
    r = _score(b)
    assert r["vague"].check("D1-00").credit == 1.0
    assert r["explicit"].check("D1-00").credit == 0.75
    b.ex("modify_viewport", {"sheet": SHEET, "viewport_id": b.viewport.id,
                             "changes": {"feet_per_inch": 120.0}})
    assert b.verify("vague").check("D1-00").credit == 0.75


def test_what_must_be_on_the_sheet_is_the_same_at_both_levels():
    b = Base(**BASE)
    b.ex("delete_entities", {"ids": [e.id for e in b.labels("bearing")] + [b.north_arrow().id]})
    r = _score(b)
    for level in LEVELS:
        assert r[level].check("D1-05").credit == 0.0 and r[level].check("D1-11").credit == 0.0
        assert _clean(r[level], "D1-05", "D1-11")
    assert r["explicit"].rubric_score == r["vague"].rubric_score
