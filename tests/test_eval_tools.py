"""The whitelist and the tool definitions (eval plan section 4.1)."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.eval import tools
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import solution_commands
from roaddraft.tasks.types import TASK_TYPES


def test_every_reference_solution_command_of_every_type_is_whitelisted():
    for name in sorted(TASK_TYPES):
        for sheets in (1, 2):
            try:
                task = generate_task(3, task_type=name, sheets=sheets)
            except (ValueError, AssertionError):
                continue
            allowed = tools.allowed_names("single", task.truth.scope)
            missing = {c for c, _ in solution_commands(task)} - allowed
            assert not missing, (name, sheets, missing)


def test_hidden_surface_stays_hidden_in_every_mode():
    hidden = {"save_document", "save_journal", "export_dxf", "export_pdf", "export_landxml",
              "print_pdf", "import_landxml", "get_journal", "list_commands", "modify_alignment",
              "delete_alignment", "create_profile", "delete_profile", "detach_reference",
              "modify_reference", "reload_references"}
    for mode in tools.MODES:
        assert not hidden & tools.allowed_names(mode, ["design", "linework"])


def test_create_alignment_only_when_the_design_is_the_task():
    assert "create_alignment" in tools.allowed_names("single", ["design", "linework"])
    assert "create_alignment" not in tools.allowed_names("single", ["linework"])


def test_render_and_run_check_follow_the_mode():
    single = tools.allowed_names("single")
    assert "run_check" not in single and "render_sheet" not in single
    assert "submit" in single and "get_task_brief" in single
    for mode in ("self_correct", "vision"):
        names = tools.allowed_names(mode)
        assert {"run_check", "render_sheet", "render_model"} <= names


def test_unknown_mode_is_an_error():
    with pytest.raises(ValueError):
        tools.allowed_names("vision2")


def test_tool_definitions_come_from_the_manifest_sorted_with_closed_schemas():
    manifest = Session().manifest()
    defs = tools.tool_definitions(manifest, "self_correct", ["linework"])
    names = [d["name"] for d in defs]
    assert names == sorted(names) and len(names) == len(set(names))
    assert set(names) == tools.allowed_names("self_correct", ["linework"])
    for d in defs:
        schema = d["input_schema"]
        assert schema["type"] == "object" and "required" in schema, d["name"]
        assert schema.get("additionalProperties") is False, d["name"]
        assert d["kind"] in ("command", "query", "harness")
    by_name = {d["name"]: d for d in defs}
    assert "Example:" in by_name["place_label"]["description"]
    assert by_name["run_check"]["kind"] == "harness"


def test_shape_params_strips_a_forged_anchor_from_modify_entity():
    params, notes = tools.shape_params("modify_entity", {"id": "TX-1", "changes": {
        "content": "x", "anchor": {"kind": "pc"}}})
    assert "anchor" not in params["changes"] and params["changes"]["content"] == "x"
    assert notes and "anchor" in notes[0]
    same, none = tools.shape_params("place_label", {"anchor": "PC-1"})
    assert same == {"anchor": "PC-1"} and none == []
