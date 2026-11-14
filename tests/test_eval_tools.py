"""The whitelist and the tool definitions (eval plan section 4.1)."""
from __future__ import annotations

import hashlib
import json

import pytest

from roaddraft.api.session import Session
from roaddraft.eval import tools
from roaddraft.eval.agents import NullAgent
from roaddraft.eval.episode import Episode
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


def test_modify_alignment_and_update_labels_only_on_a_revised_task():
    """Robert, 2026-11-12: "Yes, revision only". A revised task's scope carries the
    revision mark beside its groups; no other task's list, nor its digest, moves."""
    for mode in tools.MODES:
        plain = tools.allowed_names(mode, ["design", "linework", "ticks"])
        revised = tools.allowed_names(mode, ["design", "linework", "ticks", tools.REVISION_SCOPE])
        assert revised - plain == tools.REVISION_COMMANDS == {"modify_alignment", "update_labels"}
    task = generate_task(15021, curves=1, task_type="annotate-sheet", revise="radius")
    assert tools.REVISION_SCOPE in task.truth.scope
    allowed = tools.allowed_names("single", task.truth.scope)
    assert {c for c, _ in solution_commands(task)} <= allowed
    for name in sorted(TASK_TYPES):
        assert tools.REVISION_SCOPE not in generate_task(3, task_type=name).truth.scope


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


def test_repair_params_reads_a_one_item_list_as_the_value_where_the_schema_takes_one():
    # e3-v3 (2026-11-03): LM Studio's Gemma 4 template sent kind: ["curves"] in a quarter of
    # its calls; the same weights under vLLM never did
    schema = {"type": "object", "properties": {
        "kind": {"enum": ["alignments", "curves"]}, "side": {"enum": ["left", "right"]},
        "limit": {"type": "integer"}, "flag": {"type": "boolean"},
        "offsets": {"type": "array", "items": {"type": "number"}},
        "station": {"type": ["number", "string"]}, "changes": {"type": "object"}},
        "required": [], "additionalProperties": False}
    params, repairs = tools.repair_params(
        {"kind": ["curves"], "limit": [50], "flag": [True], "station": ["84+00"],
         "offsets": [15], "side": ["left", "right"], "changes": [{"a": 1}]}, schema)
    assert params["kind"] == "curves" and params["limit"] == 50 and params["flag"] is True
    assert params["station"] == "84+00"
    assert params["offsets"] == [15]                 # the schema takes a list
    assert params["side"] == ["left", "right"]       # two items: nothing to read
    assert params["changes"] == [{"a": 1}]           # not a scalar inside
    assert len(repairs) == 4 and repairs[0].startswith('kind: ["curves"] was read as "curves"')
    # a value the enum does not hold is still read, and validation then says so
    read, notes = tools.repair_params({"kind": ["profiles"]}, schema)
    assert read["kind"] == "profiles" and len(notes) == 1
    # no schema, an unknown key, or a plain value: nothing changes
    assert tools.repair_params({"kind": ["curves"]}, None) == ({"kind": ["curves"]}, [])
    assert tools.repair_params({"other": ["x"]}, schema) == ({"other": ["x"]}, [])
    assert tools.repair_params({"kind": "curves"}, schema) == ({"kind": "curves"}, [])


def test_shape_params_strips_a_forged_anchor_from_modify_entity():
    params, notes = tools.shape_params("modify_entity", {"id": "TX-1", "changes": {
        "content": "x", "anchor": {"kind": "pc"}}})
    assert "anchor" not in params["changes"] and params["changes"]["content"] == "x"
    assert notes and "anchor" in notes[0]
    same, none = tools.shape_params("place_label", {"anchor": "PC-1"})
    assert same == {"anchor": "PC-1"} and none == []


# ------------------------------------------- a revision made in the base drawing

@pytest.fixture(scope="module")
def base_task():
    """The third revision flavour: the drafter makes the change in the base drawing."""
    return generate_task(18000, curves=1, task_type="annotate-base", revise="base-radius")


@pytest.fixture(scope="module")
def designer():
    """The first flavour: the designer changed the base drawing, the sheet file follows."""
    return generate_task(15000, curves=1, task_type="annotate-base", revise="radius")


@pytest.fixture(scope="module")
def own():
    """The second flavour: the design lives in the sheet file and is changed there."""
    return generate_task(15021, curves=1, task_type="annotate-sheet", revise="radius")


def _digest(mode, scope):
    """An episode header's ``tools_sha256`` for a scope (``Episode.header``)."""
    defs = tools.tool_definitions(Session().manifest(), mode, scope)
    return "sha256:" + hashlib.sha256(json.dumps(defs, sort_keys=True).encode("utf-8")).hexdigest()


def test_open_document_and_reload_references_only_on_a_revision_made_in_the_base_drawing(
        base_task, designer, own):
    """Robert, 2026-11-13: "allow them, in the pin's cut". The two tools take both marks,
    the revision's and the base drawing's; one alone opens neither, and nothing opens
    save_document."""
    groups = ["design", "linework", "ticks"]
    for mode in tools.MODES:
        plain = tools.allowed_names(mode, groups)
        revised = tools.allowed_names(mode, groups + [tools.REVISION_SCOPE])
        in_base = tools.allowed_names(mode, groups + [tools.REVISION_SCOPE, tools.BASE_SCOPE])
        assert in_base - revised == tools.BASE_COMMANDS == {"open_document", "reload_references"}
        # the design is changed where it lives, never made again in the sheet file
        assert revised - in_base == {"create_alignment"}
        assert tools.allowed_names(mode, groups + [tools.BASE_SCOPE]) == plain
        assert not any("save_document" in names for names in (plain, revised, in_base))
    assert {tools.REVISION_SCOPE, tools.BASE_SCOPE} <= set(base_task.truth.scope)
    allowed = tools.allowed_names("single", base_task.truth.scope)
    assert {c for c, _ in solution_commands(base_task)} <= allowed
    for task in (designer, own):
        assert tools.REVISION_SCOPE in task.truth.scope and tools.BASE_SCOPE not in task.truth.scope
        for mode in tools.MODES:
            assert not tools.BASE_COMMANDS & tools.allowed_names(mode, task.truth.scope)
    for name in sorted(TASK_TYPES):
        assert tools.BASE_SCOPE not in generate_task(3, task_type=name).truth.scope


def _names_pin(names):
    """How many tools, and the digest of their sorted names."""
    return len(names), hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()[:16]


#: the tool list in the single mode of each scope that stood before the base-drawing revision
#: (2026-11-13): how many tools, and the digest of their sorted names.  Checked against the
#: old eval/tools.py at 3ae2dac7 over these eleven scopes in all three modes: the names and
#: the digest of the definitions (an episode header's ``tools_sha256``) were the same in all
#: 33.  The names are pinned, not the definitions' digest, which moves with any tool's help
SINGLE_NAMES = {
    "no scope": (74, "7d2b8ef83e42588e"),
    "stationing": (74, "7d2b8ef83e42588e"),
    "plan-sheet": (74, "7d2b8ef83e42588e"),
    "create-alignment": (75, "e63bf640393dbbf6"),
    "annotate-base": (74, "7d2b8ef83e42588e"),
    "attach-reference": (74, "7d2b8ef83e42588e"),
    "pavement": (74, "7d2b8ef83e42588e"),
    "curve-table": (74, "7d2b8ef83e42588e"),
    "layer-setup": (74, "7d2b8ef83e42588e"),
    "revision, the designer's": (76, "60229d9f17565584"),
    "revision, in the sheet file": (77, "4283dd51a1d4761c"),
}


def test_no_other_tasks_tool_list_or_digest_moved_with_the_base_drawing_tools(
        base_task, designer, own):
    """The pin: every scope that stood before keeps its list, and its definitions are the
    manifest's and the three harness tools' as they always were, so its digest stands; the
    base-drawing flavour alone has a list of its own, the designer's flavour's and three more."""
    scopes = {"no scope": []}
    for name in ("stationing", "plan-sheet", "create-alignment", "annotate-base",
                 "attach-reference", "pavement", "curve-table", "layer-setup"):
        scopes[name] = generate_task(3, task_type=name).truth.scope
    scopes["revision, the designer's"] = designer.truth.scope
    scopes["revision, in the sheet file"] = own.truth.scope
    assert {label: _names_pin(tools.allowed_names("single", scope))
            for label, scope in scopes.items()} == SINGLE_NAMES
    manifest = Session().manifest()
    entries = {e["name"]: e for kind in ("commands", "queries") for e in manifest[kind]}
    for scope in scopes.values():
        for mode in tools.MODES:
            allowed = tools.allowed_names(mode, scope)
            assert not tools.BASE_COMMANDS & allowed
            # each definition is the manifest's entry or one of the three harness tools, as
            # before: nothing of the new tools' reaches a list that does not show them
            defs = tools.tool_definitions(manifest, mode, scope)
            assert [d["name"] for d in defs] == sorted(allowed)
            for d in defs:
                if d["kind"] == "harness":
                    assert d["name"] in tools.HARNESS_TOOLS
                    assert d["description"] == tools.HARNESS_DEFINITIONS[d["name"]]["description"]
                else:
                    assert d["input_schema"] == entries[d["name"]]["params_schema"]
    theirs = tools.allowed_names("single", designer.truth.scope)
    mine = tools.allowed_names("single", base_task.truth.scope)
    # the two tools and no other.  Not create_alignment, though the design is graded here
    # (D1-15) as in the sheet-file flavour: the line lives in the base drawing, and one of
    # its name made in the sheet file would stand in front of it and cost a right answer
    # every label lettered through the reference
    assert mine - theirs == {"open_document", "reload_references"}
    assert not theirs - mine
    assert mine - tools.allowed_names("single", own.truth.scope) == tools.BASE_COMMANDS
    assert tools.allowed_names("single", own.truth.scope) - mine == {"create_alignment"}
    assert _names_pin(mine) == (78, "71194756ba755694")
    digest = _digest("single", base_task.truth.scope)
    assert digest not in {_digest("single", scope) for scope in scopes.values()}
    # the digest worked out here is the one an episode's header records
    for task in (base_task, designer):
        episode = Episode(task, NullAgent())
        episode.reset()
        assert episode.header()["tools_sha256"] == _digest("single", task.truth.scope)


def test_open_document_is_defined_as_the_harnesss_own_beside_the_engines_reload_references(
        base_task, designer):
    manifest = Session().manifest()
    defs = tools.tool_definitions(manifest, "single", base_task.truth.scope)
    names = [d["name"] for d in defs]
    assert names == sorted(names) and len(names) == len(set(names))
    assert set(names) == tools.allowed_names("single", base_task.truth.scope)
    by_name = {d["name"]: d for d in defs}
    opener = by_name["open_document"]
    assert opener["kind"] == "harness" and tools.DOCUMENT_TOOLS == ("open_document",)
    schema = opener["input_schema"]
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert schema["required"] == ["path"] and list(schema["properties"]) == ["path"]
    assert "reload_references" in opener["description"] and "graded" in opener["description"]
    assert by_name["reload_references"]["kind"] == "command"
    assert by_name["reload_references"]["input_schema"]["additionalProperties"] is False
    assert {d["name"] for d in defs if d["kind"] == "harness"} == {
        "get_task_brief", "open_document", "submit"}
    # where the scope does not open them, neither is defined
    shown = {d["name"] for d in tools.tool_definitions(manifest, "single", designer.truth.scope)}
    assert not tools.BASE_COMMANDS & shown
