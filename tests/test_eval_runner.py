"""The runner (eval plan section 4.7): the matrix, resume, the summary."""
from __future__ import annotations

import json

from roaddraft.eval.runner import RunSpec, matrix, run, summarize
from roaddraft.eval.trajectory import is_complete


def test_matrix_is_taskset_x_agents_x_levels_x_modes_x_samples():
    spec = RunSpec(taskset="d1-dev", agents=("null", "oracle"), levels=("explicit", "vague"),
                   modes=("single",), samples=2, limit=3)
    cells = matrix(spec)
    assert len(cells) == 3 * 2 * 2 * 1 * 2
    assert {c.agent for c in cells} == {"null", "oracle"}
    assert [c.sample for c in cells[:2]] == [0, 1]


def test_run_writes_episodes_and_a_summary_and_resumes(tmp_path):
    spec = RunSpec(taskset="d1-dev", agents=("null", "oracle"), limit=3, results_root=str(tmp_path),
                   run_id="t1", concurrency=2)
    first = run(spec)
    assert first["episodes"] == 6 and first["skipped"] == 0 and not first["failures"]
    groups = first["groups"]
    assert groups["oracle|explicit|single"]["mean_effective"] == 100.0
    assert groups["null|explicit|single"]["mean_effective"] == 0.0
    assert groups["oracle|explicit|single"]["clean_sheet_rate"] == 1.0
    out = tmp_path / "t1"
    assert (out / "run.json").exists() and (out / "summary.json").exists()
    files = sorted((out / "episodes").glob("*.jsonl"))
    assert len(files) == 6 and all(is_complete(f) for f in files)
    again = run(spec)
    assert again["skipped"] == 6 and again["episodes"] == 6
    assert again["groups"]["oracle|explicit|single"]["mean_effective"] == 100.0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["run_id"] == "t1" and summary["taskset"] == "d1-dev"


def test_summarize_rates():
    rows = [{"agent": "a", "level": "explicit", "mode": "single", "effective_score": 100.0,
             "rubric_score": 100.0, "hard_failed": False, "termination": "submit", "steps": 10},
            {"agent": "a", "level": "explicit", "mode": "single", "effective_score": 0.0,
             "rubric_score": 80.0, "hard_failed": True, "termination": "budget", "steps": 20}]
    s = summarize(rows)["groups"]["a|explicit|single"]
    assert s["n"] == 2 and s["mean_effective"] == 50.0 and s["mean_rubric"] == 90.0
    assert s["hard_fail_rate"] == 0.5 and s["submit_rate"] == 0.5 and s["clean_sheet_rate"] == 0.5
    assert s["median_steps"] == 15


def test_cli_dry_run_and_run(tmp_path, capsys):
    from roaddraft.eval.__main__ import main
    assert main(["run", "--taskset", "d1-dev", "--agent", "oracle", "--limit", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2 episodes" in out
    rc = main(["run", "--taskset", "d1-dev", "--agent", "oracle", "--agent", "scripted", "--limit", "2",
               "--out", str(tmp_path), "--run-id", "cli", "--concurrency", "1"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "oracle" in out and "effective 100.00" in out


def test_a_dead_endpoint_stops_the_run_before_any_episode_is_written(tmp_path):
    from roaddraft.eval.agents import NullAgent

    class Dead(NullAgent):
        name = "dead"

        def ready(self):
            return False

    spec = RunSpec(taskset="d1-dev", agents=("dead",), limit=4, results_root=str(tmp_path),
                   run_id="dead", concurrency=1)
    said = []
    summary = run(spec, agent_factory=lambda name, spec: Dead(), progress=said.append)
    # the first cell could not start; the others were never started and no episode file exists
    assert summary["episodes"] == 0 and summary["stopped"] == "engine" and summary["not_run"] == 3
    assert len(summary["failures"]) == 1 and "did not answer" in summary["failures"][0]["error"]
    assert not list((tmp_path / "dead" / "episodes").glob("*.jsonl")) if (tmp_path / "dead" / "episodes").exists() else True
    assert any("endpoint is down" in s for s in said)


def test_episodes_that_die_before_their_first_step_stop_the_run_after_three(tmp_path):
    from roaddraft.eval.agents import NullAgent
    from roaddraft.eval.runner import DEAD_EPISODES

    class Dying(NullAgent):
        name = "dying"

        def act(self, observation):
            raise RuntimeError("HTTP 400: No models loaded")

    spec = RunSpec(taskset="d1-dev", agents=("dying",), limit=6, results_root=str(tmp_path),
                   run_id="dying", concurrency=1)
    summary = run(spec, agent_factory=lambda name, spec: Dying())
    assert summary["episodes"] == DEAD_EPISODES and summary["stopped"] == "errors"
    assert summary["not_run"] == 6 - DEAD_EPISODES
    assert summary["groups"]["dying|explicit|single"]["errors"] == DEAD_EPISODES
    # the three that ran have end records; the rest have no file, so a resume runs them
    files = list((tmp_path / "dying" / "episodes").glob("*.jsonl"))
    assert len(files) == DEAD_EPISODES and all(is_complete(f) for f in files)


def test_a_cell_that_dies_outside_the_episode_keeps_its_traceback(tmp_path):
    spec = RunSpec(taskset="d1-dev", agents=("null",), limit=1, results_root=str(tmp_path),
                   run_id="dies", concurrency=1)

    def factory(name, spec):
        raise ValueError("no such agent today")

    said = []
    summary = run(spec, agent_factory=factory, progress=said.append)
    f = summary["failures"][0]
    assert "ValueError: no such agent today" in f["error"] and "Traceback" in f["traceback"]
    assert any("Traceback" in s and "no such agent today" in s for s in said)
