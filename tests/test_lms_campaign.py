"""The LM Studio campaign script's window rule (2026-10-28, Robert): each local model loads at the highest context
that fits on the PC, found by ``fit`` down a ladder from the ceiling; a model that does not load at the floor is
dropped from the local list."""
from __future__ import annotations

import importlib.util
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmarks" / "lmstudio" / "lms_campaign.py"
KV = "Error: Failed to load model.\n\nFailed to initialize the context: failed to allocate buffer for kv cache"


def load_script():
    spec = importlib.util.spec_from_file_location("lms_campaign_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_ladder_runs_from_the_ceiling_down_to_the_floor():
    c = load_script()
    assert c.LADDER[0] == c.CONTEXT == 131072
    assert c.LADDER[-1] == c.FLOOR_CONTEXT == 65536
    assert list(c.LADDER) == sorted(set(c.LADDER), reverse=True)


def test_the_default_context_is_the_ceiling_and_a_fitted_one_is_kept():
    c = load_script()
    assert c.context({}) == c.CONTEXT
    assert c.context({"context": None}) == c.CONTEXT
    assert c.context({"context": 65536}) == 65536
    assert c.dropped_problem({}) is None


def test_fit_records_the_highest_rung_that_loads_and_clears_an_old_drop(monkeypatch):
    c = load_script()
    loads_at, tried = 98304, []

    def fake_load_alone(m, gpu=None, ctx=None):
        tried.append(ctx)
        ok = ctx <= loads_at
        return subprocess.CompletedProcess([], 0 if ok else 1, "", "" if ok else KV)

    monkeypatch.setattr(c, "load_alone", fake_load_alone)
    monkeypatch.setattr(c, "loaded_problem", lambda m, ctx=None: None)
    m = {"lms_key": "x/y", "quantization": "Q4_K_M", "dropped": {"date": "2026-10-01", "reason": "old"}}
    rec = c.fit(m)
    assert tried == [131072, 114688, 98304]
    assert m["context"] == loads_at and "dropped" not in m
    assert rec is m["fit"] and rec["context"] == loads_at
    assert [t["loaded"] for t in rec["tried"]] == [False, False, True]
    assert rec["tried"][0]["why"].endswith("failed to allocate buffer for kv cache")
    assert c.context(m) == loads_at


def test_a_model_that_misses_the_floor_is_dropped_and_the_drop_is_a_preflight_problem(monkeypatch):
    c = load_script()
    monkeypatch.setattr(c, "load_alone", lambda m, gpu=None, ctx=None: subprocess.CompletedProcess([], 1, "", KV))
    m = {"lms_key": "x/y", "quantization": "Q8_0", "context": 131072, "fit": {"context": 131072}}
    rec = c.fit(m)
    assert m["context"] is None and "fit" not in m and rec is m["dropped"]
    assert len(rec["tried"]) == len(c.LADDER) and not any(t["loaded"] for t in rec["tried"])
    assert "65,536" in rec["reason"] and "kv cache" in rec["reason"]
    assert "dropped from the local list" in c.dropped_problem(m)
    assert c.context(m) == c.CONTEXT   # what a fresh fit would try first


def test_a_rung_the_server_loads_at_another_size_does_not_count(monkeypatch):
    c = load_script()
    monkeypatch.setattr(c, "load_alone", lambda m, gpu=None, ctx=None: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(c, "loaded_problem",
                        lambda m, ctx=None: None if ctx == 65536 else f"x/y is loaded at 32768, not {ctx}")
    m = {"lms_key": "x/y", "quantization": "Q4_K_M"}
    c.fit(m)
    assert m["context"] == 65536
    assert [t["loaded"] for t in m["fit"]["tried"]] == [False, False, False, False, True]


# ------------------------------------------------------------------ stalls (2026-10-28)

def _episode(folder, name, end=None, body=1):
    """An episode file: a header, ``body`` turn records and, unless ``end`` is None, an end record."""
    import json
    lines = [json.dumps({"type": "header", "run_id": "r"})]
    lines += [json.dumps({"type": "turn", "n": i}) for i in range(body)]
    if end is not None:
        lines.append(json.dumps(dict({"type": "end", "termination": "budget", "steps": 0}, **end)))
    f = folder / f"{name}.model.neutral.single.explicit.0.jsonl"
    f.write_text("\n".join(lines) + "\n")
    return f


def test_a_stall_is_a_turn_time_trip_with_no_steps():
    c = load_script()
    assert c.stalled({"termination": "budget", "budget_tripped": "turn_time", "steps": 0})
    assert not c.stalled({"termination": "budget", "budget_tripped": "turn_time", "steps": 17})   # Gemma's D1-001014
    assert not c.stalled({"termination": "budget", "budget_tripped": "wall_clock", "steps": 0})
    assert not c.stalled({"termination": "error", "steps": 0})
    assert not c.stalled({"termination": "submit", "steps": 2})


def test_the_end_record_is_the_last_line_or_none_while_the_episode_runs(tmp_path):
    c = load_script()
    done = _episode(tmp_path, "D1-000001-aaaa", end={"budget_tripped": "turn_time"})
    partial = _episode(tmp_path, "D1-000002-bbbb", end=None)
    assert c.end_record(done)["budget_tripped"] == "turn_time"
    assert c.end_record(partial) is None


def test_stalled_episodes_skip_partials_and_ones_already_rerun(tmp_path):
    c = load_script()
    eps = tmp_path / "episodes"
    eps.mkdir()
    a = _episode(eps, "D1-000001-aaaa", end={"budget_tripped": "turn_time"})
    b = _episode(eps, "D1-000002-bbbb", end={"budget_tripped": "turn_time"})
    _episode(eps, "D1-000003-cccc", end={"termination": "submit", "steps": 3, "budget_tripped": None})
    _episode(eps, "D1-000004-dddd", end=None)
    _episode(eps, "D1-000005-eeee", end={"budget_tripped": "turn_time", "steps": 5})
    assert c.stalled_episodes(tmp_path, {}) == [a, b]
    assert c.stalled_episodes(tmp_path, {b.name: 1}) == [a]
    assert c.stalled_episodes(tmp_path, {a.name: 1, b.name: 1}) == []
    assert c.stalled_episodes(tmp_path, {a.name: 1}, max_reruns=2) == [a, b]
    assert c.stalled_episodes(tmp_path / "missing", {}) == []


def test_set_aside_moves_into_a_dated_folder_and_keeps_a_second_copy(tmp_path):
    import time
    c = load_script()
    eps = tmp_path / "episodes"
    eps.mkdir()
    a = _episode(eps, "D1-000001-aaaa", end={"budget_tripped": "turn_time"})
    dest = c.set_aside(tmp_path, [a])
    assert dest == tmp_path / f"errored-{time.strftime('%Y-%m-%d')}"
    assert (dest / a.name).exists() and not a.exists()
    again = _episode(eps, "D1-000001-aaaa", end={"budget_tripped": "turn_time"})
    c.set_aside(tmp_path, [again])
    assert (dest / f"{a.name}.1").exists() and not again.exists()
    assert list(eps.glob("*.jsonl")) == []


def test_clear_errors_takes_stalled_episodes_only_when_asked(tmp_path, capsys):
    import argparse
    c = load_script()
    eps = tmp_path / "episodes"
    eps.mkdir()
    err = _episode(eps, "D1-000001-aaaa", end={"termination": "error", "error": "boom"})
    stall = _episode(eps, "D1-000002-bbbb", end={"budget_tripped": "turn_time"})
    keep = _episode(eps, "D1-000003-cccc", end={"termination": "submit", "steps": 4, "budget_tripped": None})
    assert c.cmd_clear_errors(argparse.Namespace(run_id=str(tmp_path), apply=False, stalled=False)) == 0
    assert "dry run" in capsys.readouterr().out and err.exists() and stall.exists()
    assert c.cmd_clear_errors(argparse.Namespace(run_id=str(tmp_path), apply=True, stalled=False)) == 0
    assert not err.exists() and stall.exists() and keep.exists()
    assert c.cmd_clear_errors(argparse.Namespace(run_id=str(tmp_path), apply=True, stalled=True)) == 0
    out = capsys.readouterr().out
    assert "stalled" in out and not stall.exists() and keep.exists()


def test_a_silent_turn_is_any_turn_time_trip_and_clear_errors_takes_them_with_turn_time(tmp_path, capsys):
    import argparse
    c = load_script()
    assert c.silent_turn({"termination": "budget", "budget_tripped": "turn_time", "steps": 57})   # the 9B's D1-001032
    assert c.silent_turn({"termination": "budget", "budget_tripped": "turn_time", "steps": 0})
    assert not c.silent_turn({"termination": "budget", "budget_tripped": "wall_clock", "steps": 0})
    assert not c.stalled({"termination": "budget", "budget_tripped": "turn_time", "steps": 57})
    eps = tmp_path / "episodes"
    eps.mkdir()
    err = _episode(eps, "D1-000001-aaaa", end={"termination": "error", "error": "boom"})
    stall = _episode(eps, "D1-000002-bbbb", end={"budget_tripped": "turn_time"})
    silent = _episode(eps, "D1-000003-cccc", end={"budget_tripped": "turn_time", "steps": 13})
    keep = _episode(eps, "D1-000004-dddd", end={"termination": "submit", "steps": 4, "budget_tripped": None})
    ns = dict(run_id=str(tmp_path), apply=True)
    assert c.cmd_clear_errors(argparse.Namespace(stalled=True, turn_time=False, **ns)) == 0
    assert not err.exists() and not stall.exists() and silent.exists() and keep.exists()
    assert c.cmd_clear_errors(argparse.Namespace(stalled=False, turn_time=True, **ns)) == 0
    out = capsys.readouterr().out
    assert "silent" in out and not silent.exists() and keep.exists()


def test_e3_leaves_the_context_budget_out_for_a_harness_pin_without_the_flag(tmp_path, monkeypatch, capsys):
    import argparse
    c = load_script()
    models = {"models": {"m": {"label": "m-lms", "lms_key": "org/m", "quantization": "Q4_K_M", "context": 131072}}}
    monkeypatch.setattr(c, "load", lambda: models)

    def e3(worktree):
        return argparse.Namespace(name="m", taskset="d1-real", samples=1, mode="single", level="explicit", limit=None,
                                  run_id="r", pilots="text", worktree=str(worktree), dry_run=False, print=True)

    for name, flags in (("old", ["--lms-context"]), ("new", ["--lms-context", "--context-tokens"])):
        d = tmp_path / name / "src" / "roaddraft" / "eval"
        d.mkdir(parents=True)
        (d / "__main__.py").write_text("".join(f'p.add_argument("{f}", type=int)\n' for f in flags))
    assert c.cmd_e3(e3(tmp_path / "old")) == 0
    out = capsys.readouterr().out
    assert "--lms-context 131072" in out and "--context-tokens" not in out
    assert c.cmd_e3(e3(tmp_path / "new")) == 0
    assert "--context-tokens 131072" in capsys.readouterr().out
    assert c.context_budget_in(tmp_path / "missing")      # preflight's to report, not this check's
