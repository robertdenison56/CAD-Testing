"""The harder-task pilots as eval tasks (``eval/probe_tasks.py``): the
``hard-pilots`` manifest, the episode on the MCP server's own tools, the grade
by each probe's own check, the re-grade from the kept files, and the board."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from roaddraft.eval import probe_tasks as P
from roaddraft.eval import report as R
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import NullAgent, ToolCall
from roaddraft.eval.budget import Budgets
from roaddraft.eval.episode import EpisodeConfig
from roaddraft.eval.runner import RunSpec, run
from roaddraft.probes.pilot import PILOT_PROBES

#: fast pilots: a label fix, a base-file repair (the oracle opens the base), a QA mark-up
FAST = ("p02-sources-wfl19a", "p02-sources-wfl19b", "p14-qa-review-wfl19")


def _ids(probes):
    rows = tasksets.load(P.PILOT_SET)["tasks"]
    return [r["task_id"] for r in rows if r["probe"] in probes]


def test_the_set_is_every_pilot_once_with_current_ids():
    rows = tasksets.load(P.PILOT_SET)["tasks"]
    assert sorted(r["probe"] for r in rows) == sorted(p.id for p in PILOT_PROBES)
    # 33 pilots until 2026-11-03, 112 since (Robert: "expand the hard pilots to a set of at least 100")
    assert len(rows) == 112 and len({r["task_id"] for r in rows}) == 112
    assert all(r["task_id"].startswith(P.ID_PREFIX + r["probe"]) for r in rows)
    assert {r["task_type"] for r in rows} == {"pilot-" + n for n in P.FAMILIES.values()}
    assert sum(r["attachments"] for r in rows) == 23   # the scanned-sheet and marked-up-page pilots
    assert tasksets.load(P.PILOT_SET)["generator_version"] == P.generator_version()
    assert not tasksets.check(P.PILOT_SET)
    task = tasksets.task_from_entry(rows[0])
    assert isinstance(task, P.ProbeTask) and task.brief == P.brief_text(task.probe)
    with pytest.raises(ValueError):
        tasksets.task_from_entry({**rows[0], "task_id": "PR-wrong"})


def test_a_probe_set_runs_on_track_p_budgets_unless_the_run_sets_them():
    assert tasksets.default_budgets(P.PILOT_SET) == P.BUDGETS
    assert tasksets.default_budgets("d1-test") == Budgets()
    assert P.BUDGETS.steps > Budgets().steps and P.BUDGETS.wall_clock_s >= 1800


def test_oracle_passes_and_null_fails_through_the_loop_and_reverify_agrees(tmp_path, monkeypatch):
    spec = RunSpec(taskset=P.PILOT_SET, agents=("oracle", "null"), task_ids=_ids(FAST),
                   results_root=str(tmp_path), run_id="hp", budgets=Budgets(steps=5000))
    summary = run(spec)
    g = summary["groups"]
    assert g["oracle|explicit|single"]["mean_effective"] == 100.0
    assert g["oracle|explicit|single"]["n"] == len(FAST)
    assert g["null|explicit|single"]["mean_effective"] == 0.0
    assert g["null|explicit|single"]["mean_rubric"] == 0.0   # no call, no item done
    run_dir = tmp_path / "hp"
    # the changed files are kept beside the trajectory, and only those
    kept = sorted(p.name for p in (run_dir / "projects").iterdir())
    assert len(kept) == len(FAST) and all(".oracle." in k for k in kept)
    s = R.build(run_dir, check_delta=False)
    assert s["taskset"] == P.PILOT_SET and not s["stale"] and not s["publish_problems"]
    # the episodes are stamped with the pilot checks' version, and the run is held to it
    assert s["versions"]["verifier_version"] == [P.check_version()]
    assert s["current_versions"]["verifier_version"] == P.check_version()
    # three pilots of the set: a partial run, published and listed but not ranked
    n = len(P.current_ids())
    assert s["partial"] and s["coverage"] == {"tasks_run": len(FAST), "tasks_in_set": n,
                                              "missing": sorted(P.current_ids() - set(_ids(FAST))),
                                              "foreign": []}
    b = R.board([{k: v for k, v in s.items() if k != "_episodes"}])
    assert not b["boards"][P.PILOT_SET]["ranked"] and b["others"][0]["run_id"] == "hp"
    assert b["others"][0]["partial"]["tasks_run"] == len(FAST)
    assert b["others"][0]["reasons"] == [f"partial, not scored: covers {len(FAST)} of the set's {n} tasks; "
                                         "a row ranks once the run holds every task with none in error or unfinished"]
    assert f"**partial, not scored: {len(FAST)} of {n} tasks**" in R.render_board(b)
    assert f"> **Partial:** covers {len(FAST)} of the set's {n} tasks" in R.render_markdown(s)
    # the run is held to its task ids, not the set's hash: a grown set leaves it current
    monkeypatch.setattr(P, "generator_version", lambda probes=None: "probe-000000000000")
    grown = R.build(run_dir, check_delta=False)
    assert grown["current_versions"]["generator_version"] == "probe-000000000000"
    assert grown["versions"]["generator_version"] == s["versions"]["generator_version"]
    assert not grown["stale"] and not grown["publish_problems"]
    monkeypatch.undo()
    again = R.build(run_dir, reverify=True, check_delta=False)
    assert ([(r["label"], r["effective_mean"], r["rubric_mean"]) for r in again["rows"]]
            == [(r["label"], r["effective_mean"], r["rubric_mean"]) for r in s["rows"]])
    oracle = next(r for r in s["rows"] if r["label"].startswith("oracle"))
    assert oracle["per_check"][P.CHECK_ID]["mean_credit"] == 1.0


def test_the_episode_serves_the_probe_runners_tools_inside_the_project():
    probe = P.by_id("p02-sources-wfl19b")
    task = P.task_from_entry(P.entry(probe))
    ep = P.ProbeEpisode(task, NullAgent(), EpisodeConfig())
    obs = ep.reset()
    names = {t["name"] for t in obs["tools"]}
    assert {"open_document", "modify_alignment", "submit", "get_task_brief"} <= names
    assert "run_check" not in names and "view_attachment" not in names
    folder = str(ep.project.parent)
    # paths are shown relative to the project, and a relative path resolves there
    base = next(f.name for f in ep.project.iterdir() if f.name.endswith("_ali.rdraft"))
    opened = ep.execute(ToolCall("open_document", {"path": base}))
    assert opened["ok"] and folder not in json.dumps(opened)
    back = ep.execute(ToolCall("open_document", {"path": P.fixture.START[probe.start]}))
    assert back["ok"]
    # nothing outside the episode folder
    out = ep.execute(ToolCall("open_document", {"path": "/etc/hosts"}))
    assert not out["ok"] and "outside" in json.dumps(out)
    refused = ep.execute(ToolCall("export_dxf", {"path": "/tmp/stolen.dxf"}))
    assert not refused["ok"]
    assert not ep.execute(ToolCall("no_such_tool", {}))["ok"]
    ep._workdir.cleanup()


def test_a_one_item_list_is_read_as_the_value_on_the_pilots_route_too():
    # e3-v3 (2026-11-03): the serving stack's list round a single value is read on the
    # pilots' route as on the D1 one, noted to the model and counted as repaired
    probe = P.by_id("p02-sources-wfl19b")
    task = P.task_from_entry(P.entry(probe))
    ep = P.ProbeEpisode(task, NullAgent(), EpisodeConfig())
    ep.reset()
    base = next(f.name for f in ep.project.iterdir() if f.name.endswith("_ali.rdraft"))
    opened = ep.execute(ToolCall("open_document", {"path": [base]}))
    assert opened["ok"] and ep.repaired_calls == 1 and ep.invalid_calls == 0
    assert opened["repaired"] == [f'path: ["{base}"] was read as "{base}" '
                                 "(a one-item list where the schema takes one value)"]
    assert opened["warnings"][-1] == opened["repaired"][0]
    assert ep.execute(ToolCall("open_document", {"path": base}))["ok"] and ep.repaired_calls == 1
    ep._workdir.cleanup()


def test_a_scanned_pilot_shows_its_scan_and_run_check_hides_the_checks_words():
    probe = P.by_id("p15-plan-reading-ppm046")
    task = P.task_from_entry(P.entry(probe))
    ep = P.ProbeEpisode(task, NullAgent(), EpisodeConfig(mode="self_correct"))
    ep.reset()
    listing = ep.execute(ToolCall("view_attachment", {}))
    name = listing["attachments"][0]["name"]
    ep._turn_images = []
    seen = ep.execute(ToolCall("view_attachment", {"name": name, "region": [0, 0, 0.5, 0.5]}))
    assert seen["ok"] and ep._turn_images[-1] and ep._turn_images[-1][0][0] == "image/png"
    check = ep.execute(ToolCall("run_check", {}))
    assert check["status"] == "fail" and set(check) == {
        "ok", "name", "status", "items_done", "items_asked", "budget_remaining"}
    ep._workdir.cleanup()


def test_the_fake_oracle_drives_a_pilot_through_the_llm_agent(tmp_path):
    spec = RunSpec(taskset=P.PILOT_SET, agents=(), models=("fake-oracle",),
                   task_ids=_ids(("p02-sources-wfl19b",)), results_root=str(tmp_path),
                   run_id="fo", budgets=Budgets(steps=5000))
    summary = run(spec)
    assert summary["groups"]["fake-oracle|explicit|single"]["mean_effective"] == 100.0
    ep = next((tmp_path / "fo" / "episodes").glob("*.jsonl"))
    header = json.loads(ep.read_text().splitlines()[0])
    # the model is given the server's instructions, as on Track P, not the D1 rules
    assert header["system_prompt"].startswith(P.INSTRUCTIONS.strip()[:60])
    assert header["generator_version"] == P.generator_version() and header["probe"]


def test_the_check_version_follows_the_pilot_sources(tmp_path):
    from roaddraft.verify import VERIFIER_VERSION
    v = P.check_version()
    assert v.startswith("pilot-check-") and len(v) == len("pilot-check-") + 12 and v == P.check_version()
    sources = P.check_sources()
    assert all(f.suffix == ".py" for f in sources) and {"qa_review.py", "common.py"} <= {f.name for f in sources}
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("def check(): return 1\n"); b.write_text("X = 2\n")
    v1 = P.check_version([a, b])
    assert v1 == P.check_version([b, a]) != v
    b.write_text("X = 3\n")
    assert P.check_version([a, b]) != v1
    # the grade and the header carry it, and a probe set is held to it, not the D1 verifier
    assert P.ProbeReport("p02-sources-wfl19a", True, "ok").to_dict()["verifier_version"] == v
    assert tasksets.current_verifier(P.PILOT_SET) == v
    assert tasksets.current_verifier("d1-test") == VERIFIER_VERSION == tasksets.current_verifier(None)
    assert R.current_versions(P.PILOT_SET)["verifier_version"] == v
    assert R.current_versions("d1-real")["verifier_version"] == VERIFIER_VERSION


def test_a_probe_run_is_held_to_its_task_ids_not_the_sets_hash():
    ids = sorted(P.current_ids())
    n = len(ids)
    assert n == 112 and set(ids) == {r["task_id"] for r in tasksets.load(P.PILOT_SET)["tasks"]}
    cov = R.coverage(P.PILOT_SET, ids[:24])
    assert cov == {"tasks_run": 24, "tasks_in_set": n, "missing": ids[24:], "foreign": []}
    gone = "PR-p99-gone-0123456789"
    cov2 = R.coverage(P.PILOT_SET, ids + [gone])
    assert cov2["foreign"] == [gone] and not cov2["missing"] and cov2["tasks_run"] == n + 1
    # every board set is held to coverage since 2026-11-04: pilot ids on d1-test are all foreign
    on_d1 = R.coverage("d1-test", ids)
    assert len(on_d1["foreign"]) == n and len(on_d1["missing"]) == 100
    assert R.coverage(None, ids) is None and R.coverage("d1-variance", ids) is None
    base = {"taskset": P.PILOT_SET, "stale": [], "incomplete": [],
            "versions": {"spec_version": ["v1"], "spec_hash": ["x"],
                         "verifier_version": [P.check_version()]}}
    # a run on part of the set is not a publish problem; an id the set no longer has is
    assert R.publish_problems({**base, "coverage": cov}) == []
    probs = R.publish_problems({**base, "coverage": cov2})
    assert len(probs) == 1 and probs[0].startswith(f"1 of the run's {n + 1} task ids are not in the current set")
    assert gone in probs[0]
    assert R.partial_reason(cov) == (f"partial, not scored: covers 24 of the set's {n} tasks; a row ranks once "
                                     "the run holds every task with none in error or unfinished")


def test_the_report_holds_a_pilot_run_to_its_task_ids_and_ranks_it_apart():
    assert R.current_versions(P.PILOT_SET)["generator_version"] == P.generator_version()
    assert P.PILOT_SET in R.LEADERBOARD_SETS
    row = {"label": "m · single · explicit",
           "key": {"model": "m", "provider": "anthropic", "effort": None, "dialect": "neutral",
                   "mode": "single", "level": "explicit"},
           "effective_mean": 41.4, "ci_low": 30.0, "ci_high": 52.0, "half_width": 11.0,
           "rubric_mean": 70.0, "hard_fail_rate": 0.59, "clean_sheet_rate": 0.41,
           "invalid_call_rate": 0.02, "cost_per_sheet": None, "n_tasks": 29, "k_min": 3, "k_max": 3}
    full = {"run_id": "hp", "taskset": P.PILOT_SET, "episodes": 87, "partial": False,
            "coverage": {"tasks_run": 29, "tasks_in_set": 29, "missing": [], "foreign": []},
            "versions": {"spec_version": ["v1"]}, "publish_problems": [], "rows": [row]}
    b = R.board([full])
    # an explicit pilot row ranks on the explicit board (2026-11-08: the pilots have vague briefs too)
    assert not b["ranked"] and not b["boards"][P.PILOT_SET]["ranked"]
    assert b["boards"][P.PILOT_SET]["other_prompts"]["explicit"]["ranked"][0]["rank"] == 1
    assert "## `hard-pilots`: the harder tasks (pass or fail)" in R.render_board(b, level="explicit")
    vague = {**full, "run_id": "hp-v", "rows": [{**row, "label": "m · single · vague",
                                                  "key": {**row["key"], "level": "vague"}}]}
    assert R.board([vague])["boards"][P.PILOT_SET]["ranked"][0]["run_id"] == "hp-v"
    # the same run on 24 of 33 tasks: published, listed as partial, not ranked
    part = {**full, "run_id": "hp-text", "partial": True,
            "coverage": {"tasks_run": 24, "tasks_in_set": 33, "missing": ["x"] * 9, "foreign": []},
            "rows": [{**row, "n_tasks": 24}]}
    b = R.board([part])
    assert not b["boards"][P.PILOT_SET]["ranked"]
    assert b["others"][0]["partial"]["tasks_in_set"] == 33 and "partial, not scored: covers 24" in b["others"][0]["reasons"][0]
    md = R.render_board(b)
    assert "No ranked run yet. A row needs a published run on `hard-pilots` that covers every task" in md
    assert "`hp-text` (hard-pilots, 87 episodes, **partial, not scored: 24 of 33 tasks**)" in md


def test_a_pilots_page_reaches_an_openai_request_as_a_data_url():
    """The image route of the nine pilots that come with a page: the
    ``view_attachment`` PNG goes to an OpenAI-compatible endpoint as an
    ``image_url`` data URL in a user message after the tool messages, in
    every mode, and never into the trajectory."""
    from roaddraft.eval.agents import LLMAgent
    from roaddraft.eval.providers.openai_compat import OpenAICompatProvider
    probe = P.by_id("p15-plan-reading-ppm046")
    task = P.task_from_entry(P.entry(probe))
    bodies = []

    def post(body):
        bodies.append(json.loads(json.dumps(body)))
        n = len(bodies)
        usage = {"prompt_tokens": 100 * n, "completion_tokens": 5}
        if n == 1:
            args = "{}"
        elif n == 2:
            listing = json.loads(body["messages"][-1]["content"])      # the tool message
            args = json.dumps({"name": listing["attachments"][0]["name"], "region": [0, 0, 0.5, 0.5]})
        else:
            return {"choices": [{"message": {"content": "done"}, "finish_reason": "stop"}], "usage": usage}
        calls = [{"id": f"c{n}", "type": "function", "function": {"name": "view_attachment", "arguments": args}}]
        return {"choices": [{"message": {"content": "", "tool_calls": calls}, "finish_reason": "tool_calls"}],
                "usage": usage}

    provider = OpenAICompatProvider("local-vision", post=post, lms_context=None)
    r = P.ProbeEpisode(task, LLMAgent(provider), EpisodeConfig(mode="single")).run()
    assert r.termination == "submit" and len(bodies) == 3 and r.steps == 2
    msgs = bodies[2]["messages"]
    assert [m["role"] for m in msgs[-3:]] == ["assistant", "tool", "user"]
    parts = msgs[-1]["content"]
    assert parts[0] == {"type": "text", "text": "The image(s) from the calls above:"}
    assert parts[1]["type"] == "image_url"
    url = parts[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,") and len(url) > 10000
    assert "base64" not in msgs[-2]["content"]          # the tool message is the JSON alone
    assert [m["role"] for m in bodies[1]["messages"][-2:]] == ["assistant", "tool"]   # the listing: no image


# ------------------------------------------------- the vague level (2026-11-08)


def _fake_probe(vague="Letter CL1 on this sheet.", vague_check=None):
    from roaddraft.probes.base import Probe, Result
    return Probe(id="p04-fake", prompt="Letter CL1 on this sheet: ticks every 100 ft, 0.10 in text, layer X.",
                 check=lambda a, b: Result(False, "explicit"), vague=vague, vague_check=vague_check)


def test_a_vague_pilot_is_its_own_task_id_and_the_explicit_id_is_unchanged():
    from roaddraft.probes import prompting
    p = _fake_probe()
    assert P.task_id(p) == P.task_id(p, "explicit")
    assert P.task_id(p, "vague") != P.task_id(p) and P.task_id(p, "vague").startswith("PR-p04-fake-")
    assert "Letter CL1 on this sheet." in P.brief_text(p, "vague") and "0.10 in" not in P.brief_text(p, "vague")
    assert P.levels_of(p) == ("explicit", "vague") and P.levels_of(_fake_probe(vague="")) == ("explicit",)
    assert P.current_ids([p], "vague") == {P.task_id(p, "vague")}
    assert P.current_ids([_fake_probe(vague="")], "vague") == frozenset()
    with pytest.raises(ValueError, match="no vague prompt"):
        prompting.task_text(_fake_probe(vague=""), "vague")


def test_the_vague_check_grades_a_vague_episode_and_only_that():
    from roaddraft.probes.base import Result
    p = _fake_probe(vague_check=lambda a, b: Result(True, "vague"))
    assert p.check_at("explicit") is p.check and p.check_at("vague")(None, None).detail == "vague"
    q = _fake_probe()
    assert q.check_at("vague") is q.check   # no vague check: the one check serves both levels


def test_a_vague_cell_runs_under_the_vague_id_of_its_manifest_row():
    from roaddraft.eval.runner import Cell
    row = {"probe": "p04-fake", "task_id": "PR-p04-fake-aaaa", "vague_task_id": "PR-p04-fake-bbbb"}
    assert Cell(row, "m", "explicit", "single", 0).task_id == "PR-p04-fake-aaaa"
    assert Cell(row, "m", "vague", "single", 0).task_id == "PR-p04-fake-bbbb"
    with pytest.raises(ValueError, match="no vague prompt"):
        Cell({**row, "vague_task_id": None}, "m", "vague", "single", 0).task_id
    d1 = {"task_id": "D1-1", "seed": 1}
    assert Cell(d1, "m", "vague", "single", 0).task_id == "D1-1"   # a D1 task is one id at every level


def test_the_board_holds_a_vague_pilot_run_to_the_vague_ids():
    ex, vg = P.current_ids(level="explicit"), P.current_ids(level="vague")
    assert len(ex) == len(P.pilots()) and not (ex & vg)
    assert R.set_ids(P.PILOT_SET, ["vague"]) == set(vg)
    cov = R.coverage(P.PILOT_SET, sorted(vg), levels=["vague"])
    assert cov["missing"] == [] and cov["foreign"] == [] and cov["tasks_in_set"] == len(vg)
    on_explicit = R.coverage(P.PILOT_SET, sorted(vg))
    assert len(on_explicit["foreign"]) == len(vg)
    rows = {r["probe"]: r for r in tasksets.build(P.PILOT_SET)["tasks"]}
    assert all(r["vague_task_id"] == P.task_id(P.by_id(pid), "vague") for pid, r in rows.items())
    # every pilot has a vague brief (Robert, 2026-11-08: every eval task has a vague prompt)
    assert len(vg) == len(ex) == len(P.pilots())
    assert all(p.vague and p.vague != p.prompt and len(p.vague) < len(p.prompt) for p in P.pilots())
    # the committed manifest carries both ids, and its tripwire watches the vague ones
    assert tasksets.check(P.PILOT_SET) == []
    saved = tasksets.load(P.PILOT_SET)
    assert {r["vague_task_id"] for r in saved["tasks"]} == set(vg)
