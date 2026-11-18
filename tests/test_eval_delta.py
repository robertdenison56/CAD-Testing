"""The paired delta between two run reports (``roaddraft.eval.delta``): the number a training stage ends on."""
from __future__ import annotations

import json

import pytest

from roaddraft.eval import delta as deltas
from roaddraft.eval.__main__ import main

KEY = {"model": "base", "provider": "openai", "effort": None, "dialect": "neutral", "mode": "single", "level": "vague"}


def _summary(run_id, means, key=None, types=None, **over):
    types = types or {t: ("letter" if t < "T3" else "sheet") for t in means}
    row = {"label": run_id, "key": dict(KEY, **(key or {})), "task_means": means, "task_types": types,
           "effective_mean": sum(means.values()) / len(means), "n_tasks": len(means), "errors": 0}
    s = {"run_id": run_id, "taskset": "d1-test", "rows": [row], "partial": False, "stale": [], "reverified": False,
         "pins": {"tools_sha256": "sha256:aaa", "instructions_sha256": "sha256:bbb"},
         "versions": {"verifier_version": ["d1-verify-v8"], "harness_version": ["e3-v3"]}}
    s.update(over)
    return s


BASE = _summary("base", {"T1": 50.0, "T2": 100.0, "T3": 0.0, "T4": 80.0})
RUN = _summary("ckpt", {"T1": 100.0, "T2": 90.0, "T3": 60.0, "T4": 80.0, "T9": 100.0}, key={"model": "ckpt"})


def test_the_delta_is_paired_on_the_tasks_both_ran():
    d = deltas.delta(RUN, BASE)
    o = d["all"]
    assert o["n_tasks"] == 4 and d["only_run"] == ["T9"] and d["only_base"] == []
    assert o["gap"] == 25.0 and (o["base_mean"], o["run_mean"]) == (57.5, 82.5)
    assert (o["better"], o["worse"], o["same"]) == (2, 1, 1)
    assert (o["base_full"], o["run_full"], o["gained_full"], o["lost_full"]) == (1, 1, 1, 1)
    assert o["ci_low"] <= o["gap"] <= o["ci_high"]
    by = {t["task_type"]: t for t in d["by_task_type"]}
    assert by["letter"]["gap"] == 20.0 and by["sheet"]["gap"] == 30.0 and by["letter"]["n_tasks"] == 2
    assert d["not_like_for_like"] == []                 # another model is what a delta is between
    assert deltas.delta(RUN, BASE) == d                 # the interval's seed is fixed


def test_what_is_not_like_for_like_is_listed():
    other = _summary("old", dict(BASE["rows"][0]["task_means"]), key={"level": "explicit", "thinking": "off"},
                     pins={"tools_sha256": "sha256:zzz", "instructions_sha256": "sha256:bbb"}, partial=True,
                     versions={"verifier_version": ["d1-verify-v7"], "harness_version": ["e3-v3"]})
    said = " | ".join(deltas.delta(RUN, other)["not_like_for_like"])
    for part in ("level: vague against explicit", "thinking: None against off", "tools_sha256", "verifier_version",
                 "the base is partial"):
        assert part in said
    assert "instructions_sha256" not in said and "harness_version" not in said
    assert "sets differ" in " ".join(deltas.delta(RUN, _summary("x", {"T1": 1.0}, taskset="d1-real"))["not_like_for_like"])


def test_runs_with_no_task_in_common_or_several_rows_are_refused():
    with pytest.raises(ValueError, match="share no task"):
        deltas.delta(RUN, _summary("far", {"Z1": 1.0}))
    two = _summary("two", {"T1": 1.0})
    two["rows"].append(dict(two["rows"][0], label="two · thinking off"))
    with pytest.raises(ValueError, match="2 rows"):
        deltas.delta(two, BASE)
    assert deltas.delta(two, BASE, row="thinking off")["run"]["label"] == "two · thinking off"


def test_the_command_reads_published_and_reported_folders_and_writes_both_files(tmp_path, capsys):
    (tmp_path / "run" / "report").mkdir(parents=True)
    (tmp_path / "run" / "report" / "summary.json").write_text(json.dumps(RUN))
    # a run folder also holds the runner's own summary, which has no rows
    (tmp_path / "run" / "summary.json").write_text(json.dumps({"run_id": "run", "groups": {}, "episodes": 4}))
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "summary.json").write_text(json.dumps(BASE))
    out = tmp_path / "delta.md"
    assert main(["delta", str(tmp_path / "run"), str(tmp_path / "base"), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "# ckpt minus base" in text and "**Effective +25.0" in text and "1 task(s) only the run ran" in text
    assert "| **all** | 4 | 57.5 | 82.5 | +25.0 |" in text and "Like for like" in text
    assert json.loads(out.with_suffix(".json").read_text())["all"]["gap"] == 25.0
    assert main(["delta", str(tmp_path / "none"), str(tmp_path / "base")]) == 1
    assert "no summary.json" in capsys.readouterr().err
