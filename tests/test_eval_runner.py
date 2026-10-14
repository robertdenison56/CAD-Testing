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
