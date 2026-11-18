"""The run report and the D1 leaderboard (eval plan section 4.9, E4)."""
import json
import shutil

import pytest

from roaddraft.eval import report as R
from roaddraft.eval.__main__ import main as eval_main
from roaddraft.eval.agents import OracleAgent, ToolCall
from roaddraft.eval.runner import RunSpec, make_agent, run
from roaddraft.verify.report import FINDING_CODES


class Fumbler(OracleAgent):
    """A clumsy model: an unknown tool and a malformed call first, then half
    the reference solution, a run_check, and the rest."""
    name = "fumbler"

    def reset(self, task, level, mode):
        super().reset(task, level, mode)
        sol = self.queue
        half = len(sol) // 2
        self.queue = [ToolCall("no_such_tool", {}), ToolCall("create_layer", {"bogus": 1}),
                      *sol[:half], ToolCall("run_check", {}), *sol[half:]]

    def describe(self):
        return {"model": "fumbler-1", "provider": "fake", "effort": "low"}


def _factory(name, spec):
    return Fumbler() if name == "fumbler" else make_agent(name, spec)


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("results")
    base = dict(taskset="d1-dev", limit=3, results_root=str(root), run_id="e4-test",
                concurrency=2)
    run(RunSpec(agents=("oracle", "null"), levels=("explicit", "vague"), modes=("single",), **base))
    run(RunSpec(agents=("oracle", "fumbler"), levels=("explicit",), modes=("self_correct",), **base),
        agent_factory=_factory)
    return root / "e4-test"


@pytest.fixture(scope="module")
def summary(run_dir):
    return R.build(run_dir)


def _row(s, label):
    return next(g for g in s["rows"] if g["label"] == label)


def test_taxonomy_covers_every_finding_code_once():
    codes = [c for _, cs in R.TAXONOMY for c in cs]
    assert sorted(codes) == sorted(FINDING_CODES)
    assert len(codes) == len(set(codes))
    assert R.CATEGORIES == ("completeness", "value", "anchoring", "placement", "legibility",
                            "standards", "sheet_setup")


def test_bootstrap_is_seeded_and_stratified():
    vals = [0, 10, 50, 60, 90, 100]
    assert R.bootstrap(vals) == R.bootstrap(vals)
    lo, hi = R.bootstrap(vals)
    assert lo < 52 < hi
    # the spread is all between the types: within each it is nil
    assert R.bootstrap([0, 0, 100, 100], ["a", "a", "b", "b"]) == (50.0, 50.0)
    assert R.bootstrap([42.0]) == (42.0, 42.0)
    assert R.bootstrap([]) == (None, None)


def _turn(calls):
    return {"assistant": {"tool_calls": [{"name": n, "params": {}} for n, _ in calls]},
            "results": [r for _, r in calls]}


def test_tool_use_counts_invalid_faults_recovery_and_check_prefix():
    ok = lambda cid=None: {"ok": True, **({"command_id": cid} if cid else {})}  # noqa: E731
    err = lambda t: {"ok": False, "error": {"type": t, "message": "x"}}  # noqa: E731
    turns = [_turn([("no_such", err("unknown_command")), ("place_label", err("invalid_params")),
                    ("place_label", ok(1)), ("draw_line", err("command_failed"))]),
             _turn([("get_extents", ok()), ("draw_line", ok(2)), ("run_check", ok()),
                    ("place_text", ok(3)), ("run_check", ok())])]
    u = R.tool_use(turns)
    assert u["tool_calls"] == 9
    assert u["invalid_calls"] == 2 and u["failed_calls"] == 1 and u["faults"] == 3
    assert u["repaired_calls"] == 0
    # a repaired call (e3-v3: a one-item list read as its value) is counted apart, not as invalid
    fixed = dict(ok(4), repaired=['kind: ["curves"] was read as "curves"'])
    assert R.tool_use([_turn([("get_design_data", fixed)])])["repaired_calls"] == 1
    # place_label and draw_line came back within three calls; the unknown tool never did
    assert u["recovered"] == 2
    assert u["coordinate_calls"] == 2 and u["semantic_calls"] == 1
    assert u["check_prefixes"] == [2, 3]
    assert u["errors"] == {"unknown_command": 1, "invalid_params": 1, "command_failed": 1}


def test_rows_rank_and_score(summary):
    labels = [g["label"] for g in summary["rows"]]
    assert labels[-2:] == ["null · single · explicit", "null · single · vague"] or \
        labels[-2:] == ["null · single · vague", "null · single · explicit"]
    for label in ("oracle · single · explicit", "oracle · single · vague",
                  "oracle · self_correct · explicit", "fumbler-1 (low) · self_correct · explicit"):
        g = _row(summary, label)
        assert g["effective_mean"] == 100.0 and g["n_tasks"] == 3 and g["hard_fail_rate"] == 0
        assert (g["ci_low"], g["ci_high"]) == (100.0, 100.0)
    null = _row(summary, "null · single · explicit")
    assert null["effective_mean"] == 0.0 and null["submit_rate"] == 1.0
    assert null["taxonomy"]["completeness"]["episodes"] > 0
    assert [g["rank"] for g in summary["rows"]] == list(range(1, len(summary["rows"]) + 1))


def test_fumbler_row_records_tool_use_and_the_check_delta(summary):
    g = _row(summary, "fumbler-1 (low) · self_correct · explicit")
    assert g["key"]["provider"] == "fake" and g["key"]["effort"] == "low"
    assert g["tool_errors"].get("unknown_command") == 3
    assert g["invalid_call_rate"] > 0
    assert g["run_check_mean"] == 1.0
    assert g["check_delta_n"] == 3 and g["check_delta_mean"] >= 0
    eps = [e for e in summary["_episodes"] if e["row"]["model"] == "fumbler-1"]
    assert all(e["row"]["effective_at_last_check"] <= e["row"]["effective_score"] for e in eps)
    assert any(e["row"]["effective_at_last_check"] < 100 for e in eps)


def test_gaps_pair_by_task(summary):
    names = {(p["gap_name"], p["row"]) for p in summary["gaps"]}
    assert ("prompt gap", "oracle · single") in names
    assert ("prompt gap", "null · single") in names
    assert ("self-correct gain", "oracle · explicit") in names
    for p in summary["gaps"]:
        assert p["gap"] == 0.0 and p["n_tasks"] == 3 and not p["separated"]


def test_versions_and_publish_problems(summary):
    assert summary["taskset"] == "d1-dev"
    assert len(summary["versions"]["verifier_version"]) == 1
    assert any("development set" in p for p in summary["publish_problems"])
    if summary["versions"]["spec_version"][0].startswith("draft"):
        assert any("draft" in p for p in summary["publish_problems"])


def test_reverify_gives_the_same_scores(run_dir, summary):
    again = R.build(run_dir, reverify=True, check_delta=False)
    assert again["reverified"]
    assert {g["label"]: g["effective_mean"] for g in again["rows"]} == \
        {g["label"]: g["effective_mean"] for g in summary["rows"]}


def test_files_and_cli(run_dir, tmp_path):
    out = tmp_path / "rep"
    assert eval_main(["report", str(run_dir), "--out", str(out)]) == 0
    names = {p.name for p in out.iterdir()}
    assert {"summary.json", "leaderboard.md", "per_check.csv", "taxonomy.csv",
            "episodes.csv", "per_check.svg"} <= names
    import xml.etree.ElementTree as ET
    svg = ET.parse(out / "per_check.svg").getroot()
    assert svg.tag.endswith("svg")
    cells = [t for t in svg.iter() if t.tag.endswith("title") and "mean credit" in (t.text or "")]
    # every row's in-scope checks are cells with a tooltip (6 rows here)
    assert len(cells) % 6 == 0 and cells
    s = json.loads((out / "summary.json").read_text())
    assert "_episodes" not in s and s["report_version"] == R.REPORT_VERSION
    md = (out / "leaderboard.md").read_text()
    assert "fumbler-1 (low) · self_correct · explicit" in md and "## Failure taxonomy" in md
    assert "Not rankable" in md
    assert len((out / "episodes.csv").read_text().strip().splitlines()) == 1 + 3 * 6
    # publishing a dev-set run is refused unless asked, and then it is listed, not ranked
    runs = tmp_path / "runs"
    assert eval_main(["report", str(run_dir), "--out", str(out), "--publish",
                      "--runs", str(runs)]) == 1
    assert not runs.exists()
    assert eval_main(["report", str(run_dir), "--out", str(out), "--publish", "--allow-unrankable",
                      "--runs", str(runs)]) == 0
    assert {p.name for p in (runs / "e4-test").iterdir()} == {"summary.json", "leaderboard.md",
                                                             "per_check.svg"}
    b = R.board(R.published(runs))
    assert b["headline"] is None and not b["ranked"]
    assert b["others"][0]["run_id"] == "e4-test" and b["others"][0]["reasons"]


def _fake_summary(run_id, rows, taskset="d1-test", problems=()):
    return {"run_id": run_id, "taskset": taskset, "episodes": 10,
            "versions": {"spec_version": ["v1"]}, "publish_problems": list(problems),
            "rows": rows}


def _fake_row(model, provider, eff, hf=0.1, level="vague"):
    return {"label": f"{model} · single · {level}",
            "key": {"model": model, "provider": provider, "effort": None, "dialect": "neutral",
                    "mode": "single", "level": level},
            "effective_mean": eff, "ci_low": eff - 3, "ci_high": eff + 3, "half_width": 3.0,
            "rubric_mean": eff + 5, "hard_fail_rate": hf, "clean_sheet_rate": 0.2,
            "invalid_call_rate": 0.01, "cost_per_sheet": 0.5, "n_tasks": 100, "k_min": 3,
            "k_max": 3}


def test_a_row_says_the_effort_it_ran_at():
    high = _fake_row("claude-a", "anthropic", 61.0)
    high["key"]["effort"] = "high"
    b = R.board([_fake_summary("2026-11-01-d1-test", [high])])
    assert b["ranked"][0]["effort"] == "high"
    assert "| claude-a · single · vague | high |" in R.render_board(b)
    assert R.effort_cell({"provider": "anthropic", "effort": None}) == "default"
    assert R.effort_cell({"provider": "harness", "effort": None}) == "–"
    # a model left at its default shows it, from its chat template
    assert R.effort_label("Qwen/Qwen3.8-27B", "openai", None) == "xhigh (default)"
    assert R.effort_label("Qwen/Qwen3.8-27B", "openai", "low") == "low"
    assert R.effort_label("google/gemma-4-31B-it", "openai", None,
                          {"chat_template_kwargs": {"enable_thinking": True}}) == "thinking on"


def test_board_ranks_only_rankable_model_rows():
    good = _fake_summary("2026-11-01-d1-test", [_fake_row("claude-a", "anthropic", 61.0),
                                                _fake_row("claude-b", "anthropic", 72.5),
                                                _fake_row("oracle", "harness", 100.0)])
    draft = _fake_summary("draft-run", [_fake_row("claude-c", "anthropic", 90.0)],
                          problems=["spec draft-v4 is a draft"])
    variance = _fake_summary("var", [_fake_row("claude-a", "anthropic", 60.0)],
                             taskset="d1-variance")
    b = R.board([good, draft, variance])
    assert [r["label"].split(" ")[0] for r in b["ranked"]] == ["claude-b", "claude-a"]
    assert b["ranked"][0]["rank"] == 1
    assert b["headline"].startswith("best model 72.5/100 on d1-test")
    assert [r["label"].split(" ")[0] for r in b["reference"]] == ["oracle"]
    others = {o["run_id"]: o["reasons"] for o in b["others"]}
    assert others["draft-run"] == ["spec draft-v4 is a draft"]
    assert others["var"] == ["run on d1-variance, not a leaderboard set (d1-test, d1-real, hard-pilots, "
                             "d1-test-hard, d1-real-hard)"]
    md = R.render_board(b)
    assert "**Best model 72.5/100" in md and "Published runs that are not ranked" in md
    assert "| Model · mode · prompt | Effort |" in md
    assert "| claude-b · single · vague | default |" in md and "| oracle · single · vague | – |" in md
    assert "claude-c · single · vague, effort default" in md
    block = R.render_board(b, readme=True)
    text = f"intro\n{R.README_BEGIN}\nold\n{R.README_END}\nafter\n"
    new = R.replace_block(text, block)
    assert "old" not in new and new.startswith("intro\n") and new.endswith(f"{R.README_END}\nafter\n")
    with pytest.raises(ValueError):
        R.replace_block("no markers", block)


def test_d1_real_is_ranked_on_its_own_board():
    seeded = _fake_summary("t", [_fake_row("claude-a", "anthropic", 70.0)])
    real = _fake_summary("r", [_fake_row("claude-a", "anthropic", 55.0),
                               _fake_row("claude-b", "anthropic", 58.0),
                               _fake_row("oracle", "harness", 100.0)], taskset="d1-real")
    dev = _fake_summary("rd", [_fake_row("claude-a", "anthropic", 50.0)], taskset="d1-real-dev",
                        problems=["d1-real-dev is a development set and is never reported"])
    b = R.board([seeded, real, dev])
    # the top level is d1-test's, as before
    assert [r["run_id"] for r in b["ranked"]] == ["t"] and b["leaderboard_set"] == "d1-test"
    one = b["boards"]["d1-real"]
    assert [r["label"].split(" ")[0] for r in one["ranked"]] == ["claude-b", "claude-a"]
    assert [r["rank"] for r in one["ranked"]] == [1, 2]
    assert one["headline"].startswith("best model 58.0/100 on d1-real")
    assert [r["label"].split(" ")[0] for r in one["reference"]] == ["oracle"]
    assert {o["run_id"]: o["reasons"] for o in b["others"]} == {
        "rd": ["d1-real-dev is a development set and is never reported"]}
    md = R.render_board(b)
    assert "## `d1-test`: seeded sheets" in md and "## `d1-real`: the sample plan sheets" in md
    assert "**Best model 58.0/100 on d1-real" in md and "**Best model 70.0/100 on d1-test" in md
    assert "### `d1-real`" in R.render_board(b, readme=True)


def test_each_set_ranks_its_prompt_levels_apart():
    # Robert, 2026-11-08: the vague runs are the board's focus, the explicit runs a ranking of their own
    test = _fake_summary("t", [_fake_row("claude-a", "anthropic", 70.0),
                               _fake_row("claude-b", "anthropic", 60.0),
                               _fake_row("claude-a", "anthropic", 95.0, level="explicit"),
                               _fake_row("claude-c", "anthropic", 99.0, level="explicit"),
                               _fake_row("oracle", "harness", 100.0, level="explicit")])
    hard = _fake_summary("th", [_fake_row("claude-a", "anthropic", 80.0, level="explicit")],
                         taskset="d1-test-hard")
    pilots = _fake_summary("hp", [_fake_row("claude-a", "anthropic", 40.0, level="explicit")],
                           taskset="hard-pilots")
    pilots["coverage"] = {"tasks_run": 112, "tasks_in_set": 112, "missing": [], "foreign": []}
    b = R.board([test, hard, pilots])
    one = b["boards"]["d1-test"]
    assert one["prompt"] == "vague" and list(one["other_prompts"]) == ["explicit"]
    assert [(r["label"], r["rank"]) for r in one["ranked"]] == [
        ("claude-a · single · vague", 1), ("claude-b · single · vague", 2)]
    explicit = one["other_prompts"]["explicit"]
    assert [(r["label"], r["rank"]) for r in explicit["ranked"]] == [
        ("claude-c · single · explicit", 1), ("claude-a · single · explicit", 2)]
    assert b["headline"].startswith("best model 70.0/100 on d1-test with the vague prompt")
    assert explicit["headline"].startswith("best model 99.0/100 on d1-test with the explicit prompt")
    assert [r["label"] for r in one["reference"]] == ["oracle · single · explicit"]   # the harness: one list
    # a set with explicit runs only has no vague ranking yet
    th = b["boards"]["d1-test-hard"]
    assert th["ranked"] == [] and th["headline"] is None
    assert [r["run_id"] for r in th["other_prompts"]["explicit"]["ranked"]] == ["th"]
    # every pilot has a vague brief too since 2026-11-08: hard-pilots splits by level like the rest
    hp = b["boards"]["hard-pilots"]
    assert hp["prompt"] == "vague" and hp["ranked"] == []
    assert [r["run_id"] for r in hp["other_prompts"]["explicit"]["ranked"]] == ["hp"]
    # the explicit rows ranked apart on a board of their own (Robert, 2026-11-08) until that board was
    # retired (Robert, 2026-11-16): no file for the level, and an explicit run still published is listed
    # on the main board, not ranked
    md = R.render_board(b)
    section = md.split("## `d1-test`: seeded sheets")[1].split("## `d1-real`")[0]
    assert "**Best model 70.0/100" in section and "99.0/100" not in md and "LEADERBOARD_EXPLICIT.md" not in md
    assert "The explicit-prompt board was retired on 2026-11-16; its rows are listed in [RETIRED.md](RETIRED.md)." in md
    assert ("No vague-prompt run on `d1-test-hard` yet; its explicit-prompt runs are listed below, "
            "not ranked (that board is retired).") in md
    assert "No vague-prompt run on `hard-pilots` yet" in md
    unranked = md.split("## Published runs that are not ranked")[1]
    for run_id, name, label in (("t", "d1-test", "claude-c · single · explicit 99.0 ±"),
                                ("th", "d1-test-hard", "claude-a · single · explicit 80.0 ±"),
                                ("hp", "hard-pilots", "claude-a · single · explicit 40.0 ±")):
        assert f"- `{run_id}` ({name}, explicit prompt): {label}" in unranked
    assert unranked.count("Not ranked: the explicit-prompt board was retired on 2026-11-16") == 4
    assert "oracle · single" not in unranked   # the reference agents are no model row
    ex = R.render_board(b, level="explicit")
    assert ex.startswith("# RoadDraft eval leaderboard: explicit prompts")
    assert "**Best model 99.0/100 on d1-test with the explicit prompt" in ex and "70.0/100" not in ex
    assert "**Best model 40.0/100 on hard-pilots with the explicit prompt" in ex
    assert "oracle · single" not in ex   # the reference agents stay on the main board
    assert R.LEVEL_BOARD_FILES == {} and R.RETIRED_BOARDS == {"explicit": ("2026-11-16", "RETIRED.md")}
    readme = R.render_board(b, readme=True)
    assert "99.0/100" not in readme and "listed in [RETIRED.md](benchmarks/runs/RETIRED.md)." in readme
    svg = R.render_board_svg(b)
    assert "d1-test, vague prompt: seeded sheets" in svg and "explicit prompt" not in svg


def test_a_partial_probe_run_is_listed_not_ranked():
    whole = _fake_summary("hp-all", [_fake_row("claude-a", "anthropic", 40.0, level="explicit")],
                          taskset="hard-pilots")
    whole["partial"], whole["coverage"] = False, {"tasks_run": 33, "tasks_in_set": 33,
                                                  "missing": [], "foreign": []}
    part = _fake_summary("hp-text", [_fake_row("claude-b", "anthropic", 60.0, level="explicit")],
                         taskset="hard-pilots")
    part["partial"], part["coverage"] = True, {"tasks_run": 24, "tasks_in_set": 33,
                                               "missing": ["PR-x"] * 9, "foreign": []}
    b = R.board([whole, part])
    assert [r["run_id"] for r in b["boards"]["hard-pilots"]["other_prompts"]["explicit"]["ranked"]] == ["hp-all"]
    assert [o["run_id"] for o in b["others"]] == ["hp-text"]
    assert b["others"][0]["reasons"] == ["partial, not scored: covers 24 of the set's 33 tasks; a row ranks "
                                         "once the run holds every task with none in error or unfinished"]
    md = R.render_board(b)
    assert "**Best model 40.0/100 on hard-pilots" in R.render_board(b, level="explicit")
    # partial and unscorable (Robert, 2026-11-04): listed with no score
    assert "- `hp-text` (hard-pilots, 10 episodes, **partial, not scored: 24 of 33 tasks**)" in md
    assert "claude-b · single · explicit, effort default (100 tasks × 3)" in md and "60.0 ±" not in md


def _ep(task_id, task_type, score, hard=False):
    return {"row": {"task_id": task_id, "task_type": task_type, "effective_score": score,
                    "hard_failed": hard, "termination": "submit"}}


def test_real_rows_split_by_question_group(summary):
    # the groups of tasks.types.REAL_GROUPS, in board order, each over its tasks
    eps = [_ep("a", "real-draw-alignment", 100), _ep("b", "real-draw-alignment", 100),
           _ep("c", "real-stationing", 50), _ep("d", "real-bearings", 70, hard=True),
           _ep("e", "real-title-block", 80), _ep("e", "real-title-block", 60),   # two samples of one task
           _ep("f", "plan-sheet", 10)]                                           # a seeded type: no group
    g = R.by_group(eps)
    assert list(g) == ["draft", "letter", "sheet"]
    assert g["draft"]["effective_mean"] == 100 and g["draft"]["n_tasks"] == 2 and g["draft"]["half_width"] == 0
    assert g["letter"] == {**g["letter"], "name": "letter alignment data", "n": 2, "n_tasks": 2,
                           "effective_mean": 60.0, "hard_fail_rate": 0.5,
                           "types": ["real-bearings", "real-stationing"]}
    assert g["sheet"]["effective_mean"] == 70.0 and g["sheet"]["n"] == 2 and g["sheet"]["n_tasks"] == 1
    assert "job" not in g and "notes" not in g
    # a seeded run's rows carry no groups
    assert _row(summary, "oracle · single · explicit")["by_group"] == {}
    assert R.group_columns([{"by_group": g}, {"by_group": {"notes": {}}}]) == ["draft", "letter", "sheet", "notes"]
    # the board: the real table gets a column per group beside the blended score, the seeded one none
    real_row = _fake_row("claude-a", "anthropic", 55.0)
    real_row["by_group"] = {k: {"effective_mean": 50.0 + i, "half_width": 4.0, "n_tasks": 25,
                                "hard_fail_rate": 0.0} for i, k in enumerate(("draft", "letter", "sheet", "notes"))}
    ref_row = _fake_row("oracle", "harness", 100.0)   # written before rows carried by_group
    b = R.board([_fake_summary("t", [_fake_row("claude-a", "anthropic", 70.0)]),
                 _fake_summary("r", [real_row, ref_row], taskset="d1-real")])
    assert b["boards"]["d1-real"]["groups"] == ["draft", "letter", "sheet", "notes"]
    assert b["boards"]["d1-test"]["groups"] == [] and b["ranked"][0]["by_group"] == {}
    assert b["boards"]["d1-real"]["ranked"][0]["by_group"]["notes"]["effective_mean"] == 53.0
    assert [x["key"] for x in b["groups"]] == ["draft", "letter", "sheet", "notes", "job"]
    md = R.render_board(b)
    real_table = md.split("## `d1-real`")[1].split("## `hard-pilots`")[0]
    assert "| Effective | 95% CI | Draft | Letter | Sheet | Notes | Rubric |" in real_table
    assert ("| **55.0** | 52.0–58.0 | 50.0 ± 4.0 (n 25) | 51.0 ± 4.0 (n 25) | 52.0 ± 4.0 (n 25) "
            "| 53.0 ± 4.0 (n 25) | 60.0 |") in real_table
    assert "| **100.0** | 97.0–103.0 | – | – | – | – |" in real_table   # the reference row has none
    assert "Question groups (`tasks.types.REAL_GROUPS`" in real_table and "Letter = letter alignment data (`real-stationing`, `real-bearings`" in real_table
    assert "| Draft |" not in md.split("## `d1-real`")[0]
    assert "| Draft | Letter |" in R.render_board(b, readme=True)


def test_a_real_set_is_judged_against_the_real_generator():
    from roaddraft.tasks.brief import GENERATOR_VERSION
    from roaddraft.tasks.real import REAL_GENERATOR_VERSION
    assert R.current_versions("d1-real")["generator_version"] == REAL_GENERATOR_VERSION
    assert R.current_versions("d1-real-dev")["generator_version"] == REAL_GENERATOR_VERSION
    assert R.current_versions("d1-test")["generator_version"] == GENERATOR_VERSION
    assert R.current_versions()["generator_version"] == GENERATOR_VERSION
    assert "d1-real-dev" in R.NEVER_REPORTED and "d1-real" in R.LEADERBOARD_SETS
    assert set(R.NEVER_REPORTED) == {"d1-dev", "d1-real-dev", "pilot-dev"}


def test_board_notes_print_under_their_set(tmp_path):
    # Robert, 2026-11-16 (the Track D close-out): the board carries hand-kept notes, a set's and a row's
    test = _fake_summary("t", [_fake_row("claude-a", "anthropic", 70.0), _fake_row("claude-b", "anthropic", 60.0)])
    assert R.board_notes(tmp_path) == {}
    (tmp_path / R.BOARD_NOTES_FILE).write_text(json.dumps({
        "board": ["Track D closed."],
        "sets": {"d1-test": ["every row ran before the names were in the document"], "d1-real": ["unused"]},
        "rows": {"t": "stalled twice", "gone": "a run no longer published"}}), encoding="utf-8")
    notes = R.board_notes(tmp_path)
    assert notes["rows"]["t"] == "stalled twice"
    b = R.board([test])
    assert "Notes on" not in R.render_board(b)
    b["notes"] = notes
    md = R.render_board(b)
    section = md.split("## `d1-test`: seeded sheets")[1].split("## `d1-real`")[0]
    assert "Notes on `d1-test`:" in section and "- every row ran before the names were in the document" in section
    assert section.count("(`t`): stalled twice") == 1   # once a run, on its first row
    assert "- claude-a · single · vague (`t`): stalled twice" in section
    assert "a run no longer published" not in md
    assert "Notes on `d1-real`:" in md and "- unused" in md   # a set's note shows with no row yet
    assert md.index("Track D closed.") < md.index("![Effective score")   # the board's own notes, at its head
    readme = R.render_board(b, readme=True)
    assert "Notes on `d1-test`:" in readme and "Track D closed." in readme
    ex = R.render_board(b, level="explicit")
    assert "Notes on" not in ex and "Track D closed." not in ex


def test_readme_board_is_current():
    import subprocess
    import sys
    from pathlib import Path
    script = Path(R.REPO) / "scripts" / "make_leaderboard.py"
    res = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr


def test_cost_is_priced_turn_by_turn_at_report_time():
    prices = pytest.importorskip("roaddraft.eval.prices")
    model = next(iter(prices.load()["models"]))
    turns = [{"usage": {"input_tokens": 2000, "output_tokens": 300,
                        "cache_read_input_tokens": 15000}},
             {"usage": {"input_tokens": 500, "output_tokens": 900,
                        "cache_read_input_tokens": 18000}}]
    end = {"usage_total": {"input_tokens": 2500, "output_tokens": 1200,
                           "cache_read_input_tokens": 33000}, "cost_usd": 99.0}
    cost, checked = R._cost({"model": model}, end, turns)
    assert cost == pytest.approx(sum(prices.cost_usd(model, t["usage"]) for t in turns))
    assert checked == prices.load()["checked"]
    # an unpriced model keeps the episode's own figure; no usage at all, nothing
    assert R._cost({"model": "no-such-model"}, end, turns) == (99.0, None)
    assert R._cost({"model": model}, {"usage_total": {}}, []) == (None, None)


# ------------------------------------------------ cost subsets and partial runs (2026-11-04)

def test_every_board_set_is_held_to_coverage_and_errors_or_unfinished_make_a_run_partial():
    from roaddraft.eval.taskset import load
    ids = [r["task_id"] for r in load("d1-test")["tasks"]]
    whole = R.coverage("d1-test", ids)
    assert whole["missing"] == [] and whole["tasks_in_set"] == 100
    assert not R.run_partial(whole, 0, 0)
    assert R.run_partial(whole, 1, 0) and R.run_partial(whole, 0, 1)       # an error, an unfinished episode
    short = R.coverage("d1-test", ids[:60])
    assert R.run_partial(short, 0, 0) and len(short["missing"]) == 40
    assert R.coverage("d1-variance", ids) is None                          # not a board set
    why = R.partial_reason(short, errors=2, unfinished=1)
    assert why.startswith("partial, not scored: covers 60 of the set's 100 tasks; 2 episode(s) ended in error; "
                          "1 episode(s) unfinished")


def test_cost_subsets_are_five_a_type_fixed_and_cover_every_type():
    import collections
    from roaddraft.eval import subsets as S
    from roaddraft.eval.taskset import load
    drawn = S.load_subsets()
    assert drawn == S.build(), "benchmarks/tasksets/cost-subsets.json is stale: python -c 'from roaddraft.eval import subsets; subsets.write()'"
    assert "d1-test" not in drawn["subsets"] and drawn["tag"] == S.COST_TAG == "cost5"
    for name, one in drawn["subsets"].items():
        rows = load(name)["tasks"]
        have = collections.Counter(r["task_type"] for r in rows)
        got = collections.Counter(r["task_type"] for r in rows if r["task_id"] in set(one["task_ids"]))
        assert set(got) == set(have)                                         # every category
        assert all(got[t] == min(5, have[t]) for t in have)                  # five, or all of a smaller one
    assert [drawn["subsets"][n]["tasks"] for n in S.SETS] == [60, 66, 25, 25]
    assert S.route_allowed("https://api.runpod.ai/v2/wn6oehzs020wpc/openai/v1")
    assert not S.route_allowed("http://localhost:1234/v1") and not S.route_allowed(None)


def test_a_cost_subset_run_ranks_tagged_only_complete_and_from_runpod():
    from roaddraft.eval.subsets import subset_ids
    ids = subset_ids("d1-real", "cost5")
    cov = R.coverage("d1-real", ids, "cost5")
    assert cov["tasks_in_set"] == 60 and cov["set_size"] == 100 and cov["missing"] == [] and cov["subset_known"]
    assert not R.run_partial(cov, 0, 0)
    assert R.run_partial(R.coverage("d1-real", ids[:59], "cost5"), 0, 0)  # ended early
    assert R.run_partial(cov, 1, 0)                                         # an episode failed
    assert R.run_partial(R.coverage("d1-real", ids, "no-such"), 0, 0)
    base = {"versions": {"spec_version": ["v1"], "verifier_version": ["v8"], "spec_hash": ["h"]},
            "stale": [], "incomplete": [], "taskset": "d1-real", "coverage": cov}
    assert R.publish_problems({**base, "route": "https://api.runpod.ai/v2/x/openai/v1"}) == []
    assert any("Runpod route" in p for p in R.publish_problems({**base, "route": "http://localhost:1234/v1"}))


def test_the_board_ranks_subset_runs_in_their_own_table_beside_full_runs_rescored():
    from roaddraft.eval.subsets import subset_ids
    from roaddraft.eval.taskset import load
    rows = load("d1-real")["tasks"]
    ids = subset_ids("d1-real", "cost5")
    full_row = _fake_row("claude-a", "anthropic", 90.0)
    full_row["task_means"] = {r["task_id"]: (100.0 if r["task_id"] in set(ids) else 0.0) for r in rows}
    full_row["task_types"] = {r["task_id"]: r["task_type"] for r in rows}
    full = _fake_summary("full-real", [full_row], taskset="d1-real")
    sub_row = _fake_row("qwen-x", "openai", 70.0)
    sub = _fake_summary("sub-real", [sub_row], taskset="d1-real")
    sub["cost_subset"] = {"tag": "cost5", "tasks": 60, "set_size": 100}
    broken = _fake_summary("sub-broken", [_fake_row("qwen-y", "openai", 99.0)], taskset="d1-real")
    broken["partial"], broken["coverage"] = True, {"tasks_run": 59, "tasks_in_set": 60, "subset": "cost5",
                                                   "missing": ["x"], "foreign": []}
    # a full run at the other prompt level is not re-scored into the vague subset's table
    other_row = _fake_row("claude-z", "anthropic", 95.0, level="explicit")
    other_row["task_means"], other_row["task_types"] = dict(full_row["task_means"]), full_row["task_types"]
    other = _fake_summary("full-real-explicit", [other_row], taskset="d1-real")
    b = R.board([full, sub, broken, other])
    one = b["boards"]["d1-real"]
    assert [r["run_id"] for r in one["ranked"]] == ["full-real"]           # the full table: full runs only
    assert [r["run_id"] for r in one["other_prompts"]["explicit"]["ranked"]] == ["full-real-explicit"]
    assert one["other_prompts"]["explicit"]["subsets"] == {}
    t = one["subsets"]["cost5"]
    assert [(r["run_id"], r["effective_mean"], r["rank"]) for r in t["rows"]] == [
        ("full-real", 100.0, 1), ("sub-real", 70.0, 2)]                     # re-scored on the subset's 60
    assert t["rows"][0]["scored_as"] == "full run, re-scored on the subset's 60"
    assert t["rows"][1]["scored_as"] == "subset run (60 of 100)"
    assert [o["run_id"] for o in b["others"]] == ["sub-broken"]
    md = R.render_board(b)
    assert ("**Cost subset `cost5` on `d1-real`, vague prompt: partial runs, to save cost.** 60 of the set's "
            "100 tasks") in md
    assert "| 2 | qwen-x · single · vague | default | **70.0** |" in md
    assert "**partial, not scored: 59 of 60 tasks**" in md
    assert "cost subset cost5, partial to save cost (60 of 100 tasks)" in R.render_board_svg(b)


def test_a_vague_subset_table_rescores_full_runs_under_their_vague_ids():
    # a probe set's cost subset is drawn on its explicit ids, while a vague run's per-task means are
    # keyed by the vague ids; the vague table must re-score the full runs on the same tasks under those
    # (2026-11-10: the hard-pilots vague table showed the Runpod subset run alone, every full run dropped)
    from roaddraft.eval.subsets import subset_ids
    from roaddraft.eval.taskset import load
    rows = load("hard-pilots")["tasks"]
    picked = set(subset_ids("hard-pilots", "cost5"))
    assert len(picked) == 66 and all(r.get("vague_task_id") for r in rows)
    full_row = _fake_row("claude-a", "anthropic", 40.0)
    full_row["task_means"] = {r["vague_task_id"]: (100.0 if r["task_id"] in picked else 0.0) for r in rows}
    full_row["task_types"] = {r["vague_task_id"]: r["task_type"] for r in rows}
    full = _fake_summary("full-pilots", [full_row], taskset="hard-pilots")
    sub = _fake_summary("sub-pilots", [_fake_row("qwen-x", "openai", 9.0)], taskset="hard-pilots")
    sub["cost_subset"] = {"tag": "cost5", "tasks": 66, "set_size": 112}
    t = R.board([full, sub])["boards"]["hard-pilots"]["subsets"]["cost5"]
    assert [(r["run_id"], r["effective_mean"], r["rank"]) for r in t["rows"]] == [
        ("full-pilots", 100.0, 1), ("sub-pilots", 9.0, 2)]                   # re-scored on the subset's 66
    assert t["tasks"] == 66 and t["rows"][0]["scored_as"] == "full run, re-scored on the subset's 66"
    # the explicit level keeps the explicit ids
    assert R._subset_ids_at("hard-pilots", sorted(picked), ["explicit"]) == sorted(picked)
    assert R._subset_at("d1-real", ["a", "b"], ["vague"]) == {"a", "b"}      # not a probe set: as drawn


def test_a_hard_pilots_run_on_the_text_pilots_alone_is_text_only_not_partial():
    """Robert, 2026-11-10: "mark any hard pilots that are text only as such, do not move off the board". A run
    with every text pilot and no image pilot (a model that takes no images) is not partial; one that also
    misses a text pilot, or ran some image pilots, still is."""
    from roaddraft.eval.report import coverage, image_ids, run_partial, set_ids
    from roaddraft.eval.subsets import subset_ids
    pages = image_ids("hard-pilots")
    for ids in (set_ids("hard-pilots"), set(subset_ids("hard-pilots", "cost5"))):
        subset = "cost5" if len(ids) < 100 else None
        text = sorted(ids - pages)
        assert pages & ids and text
        cov = coverage("hard-pilots", text, subset)
        assert cov["missing"] == [] and not run_partial(cov, 0, 0)
        assert cov["text_only"] == {"tasks": len(text), "of": len(ids), "images_not_run": len(pages & ids)}
        assert run_partial(coverage("hard-pilots", text[1:], subset), 0, 0)             # a text pilot missing
        some = text + sorted(pages & ids)[:1]
        part = coverage("hard-pilots", some, subset)
        assert "text_only" not in part and run_partial(part, 0, 0)                      # some pages, not all
        assert "text_only" not in coverage("hard-pilots", sorted(ids), subset)           # a whole run
    assert image_ids("d1-test") == set() and "text_only" not in coverage("d1-test", [])


def test_overall_is_the_mean_over_every_set_and_ranks_only_complete_models():
    # Robert, 2026-11-13: one overall score on top of the vague board
    sums = []
    for i, name in enumerate(R.LEADERBOARD_SETS):
        rows = [_fake_row("claude-a", "anthropic", 50.0 + 10 * i)]
        if name != "hard-pilots":
            rows.append(_fake_row("claude-b", "anthropic", 90.0))
        rows.append(_fake_row("claude-c", "anthropic", 70.0, level="explicit"))
        sums.append(_fake_summary(f"r-{name}", rows, taskset=name))
    b = R.board(sums)
    ov = b["overall"]["vague"]
    # scores 50..90 over the sets in order, weights 1, 2, 2, 1, 2 (real sheets and hard pilots double)
    want = round((50 + 2 * 60 + 2 * 70 + 80 + 2 * 90) / 8, 2)
    assert [(o["label"], o["rank"], o["overall"]) for o in ov["ranked"]] == [("claude-a · single · vague", 1, want)]
    assert ov["ranked"][0]["half_width"] == round((3 * 36.0 + 2 * 9.0) ** 0.5 / 8, 2)
    assert [(o["label"], o["missing"]) for o in ov["partial"]] == [("claude-b · single · vague", ["hard-pilots"])]
    assert [o["overall"] for o in b["overall"]["explicit"]["ranked"]] == [70.0]
    md = R.render_board(b)
    assert md.index("## Overall: every set, vague prompt") < md.index("## `d1-test`")
    assert f"**Best model overall {want:.1f}/100" in md and "| 4 of 5 |" in md and "`d1-real` ×2" in md
    assert "## Overall: every set, explicit prompt" in R.render_board(b, level="explicit")
    assert "### Overall: every set, vague prompt" in R.render_board(b, readme=True)
