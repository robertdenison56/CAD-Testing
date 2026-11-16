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

def _episode(folder, name, end=None, body=1, last_turn=None):
    """An episode file: a header, ``body`` turn records (then ``last_turn``, a full turn record, when given) and,
    unless ``end`` is None, an end record."""
    import json
    lines = [json.dumps({"type": "header", "run_id": "r"})]
    lines += [json.dumps({"type": "turn", "n": i}) for i in range(body)]
    if last_turn is not None:
        lines.append(json.dumps(dict({"type": "turn", "n": body}, **last_turn)))
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


def test_a_silent_last_turn_after_steps_is_a_stall_too(tmp_path):
    """2026-11-04: the 9B's D1-001003 to 001009 ended turn_time after 1 to 10 steps with a last turn the engine never
    answered (no tokens, nothing said); the 0-step rule missed them and each cost 30 minutes. A turn-limit end whose
    last turn carried tokens is still the model's own over-long turn."""
    import argparse
    c = load_script()
    eps = tmp_path / "episodes"
    eps.mkdir()
    silent = {"assistant": {"text": "", "tool_calls": [], "submit": False}, "results": [], "usage": {}, "elapsed_ms": 1800009}
    spoke = {"assistant": {"text": "", "tool_calls": [{"name": "draw_line"}]}, "usage": {"output_tokens": 812},
             "elapsed_ms": 1800012}
    a = _episode(eps, "D1-001003-aaaa", end={"budget_tripped": "turn_time", "steps": 4}, last_turn=silent)
    b = _episode(eps, "D1-001014-bbbb", end={"budget_tripped": "turn_time", "steps": 17}, last_turn=spoke)
    first = _episode(eps, "D1-001004-cccc", end={"budget_tripped": "turn_time", "steps": 0})
    keep = _episode(eps, "D1-001007-dddd", end={"termination": "submit", "steps": 2, "budget_tripped": None})
    assert c.last_turn(a)["usage"] == {} and c.silent_record(c.last_turn(a)) and not c.silent_record(c.last_turn(b))
    assert not c.silent_record({"n": 0})                       # a record without a usage key is not judged
    assert c.stalled(c.end_record(a), c.last_turn(a)) and not c.stalled(c.end_record(b), c.last_turn(b))
    assert not c.stalled({"budget_tripped": "turn_time", "steps": 4})    # without the turn record: the old rule
    assert c.stalled_episodes(tmp_path, {}) == [a, first]
    assert c.cmd_clear_errors(argparse.Namespace(run_id=str(tmp_path), apply=True, stalled=True, turn_time=False)) == 0
    assert not a.exists() and not first.exists() and b.exists() and keep.exists()


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


# ------------------------------------------------------------------ the base rerun and T0 (2026-11-14)

def _e3_args(worktree, **more):
    import argparse
    base = dict(name="m", taskset="d1-test", samples=1, mode="single", level="vague", limit=None, run_id="r",
                pilots="all", worktree=str(worktree), dry_run=False, print=True, system_extra=None, thinking=None)
    return argparse.Namespace(**dict(base, **more))


def _pin(tmp_path, name, flags):
    """A stand-in worktree whose harness has ``flags`` on its command line, with a convention sheet in it."""
    d = tmp_path / name / "src" / "roaddraft" / "eval"
    d.mkdir(parents=True)
    (d / "__main__.py").write_text("".join(f'p.add_argument("{f}")\n' for f in flags))
    sheet = tmp_path / name / "benchmarks" / "training" / "conventions-v1.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_text("# House rules\n")
    return tmp_path / name


def test_e3_passes_the_system_extra_and_the_thinking_switch_to_the_harness(tmp_path, monkeypatch, capsys):
    c = load_script()
    monkeypatch.setattr(c, "load", lambda: {"models": {"m": {"label": "m-lms", "lms_key": "org/m",
                                                              "quantization": "Q4_K_M", "context": 131072}}})
    pin = _pin(tmp_path, "pin", ["--lms-context", "--context-tokens", "--system-extra", "--thinking"])
    assert c.cmd_e3(_e3_args(pin)) == 0
    plain = capsys.readouterr().out
    assert "--system-extra" not in plain and "--thinking" not in plain      # neither asked for: the old command
    assert c.cmd_e3(_e3_args(pin, system_extra="benchmarks/training/conventions-v1.md", thinking="off")) == 0
    out = capsys.readouterr().out
    # a relative sheet is the worktree's own copy, given to the harness as an absolute path
    assert f"--system-extra {pin / 'benchmarks' / 'training' / 'conventions-v1.md'}" in out
    assert "--thinking off" in out and "--level vague" in out
    assert out.replace(f" --system-extra {pin / 'benchmarks' / 'training' / 'conventions-v1.md'}", "") \
              .replace(" --thinking off", "") == plain
    elsewhere = tmp_path / "sheet.md"
    elsewhere.write_text("# Other rules\n")
    assert c.cmd_e3(_e3_args(pin, system_extra=str(elsewhere))) == 0
    assert f"--system-extra {elsewhere}" in capsys.readouterr().out


def test_e3_refuses_a_flag_the_pinned_harness_lacks_and_a_sheet_that_is_not_there(tmp_path, monkeypatch):
    import pytest
    c = load_script()
    monkeypatch.setattr(c, "load", lambda: {"models": {"m": {"label": "m-lms", "lms_key": "org/m",
                                                              "quantization": "Q4_K_M", "context": 131072}}})
    old = _pin(tmp_path, "old", ["--lms-context", "--context-tokens", "--system-extra"])
    with pytest.raises(SystemExit, match="has no --thinking"):
        c.cmd_e3(_e3_args(old, thinking="off"))
    older = _pin(tmp_path, "older", ["--lms-context", "--context-tokens"])
    with pytest.raises(SystemExit, match="has no --system-extra"):
        c.cmd_e3(_e3_args(older, system_extra="benchmarks/training/conventions-v1.md"))
    with pytest.raises(SystemExit, match="no file at"):
        c.cmd_e3(_e3_args(old, system_extra="benchmarks/training/missing.md"))
    assert c.harness_takes("--thinking", tmp_path / "missing")      # preflight's to report, as with the context


def test_a_copy_in_a_worktree_runs_with_the_main_checkouts_interpreter_and_results(tmp_path):
    c = load_script()
    main = tmp_path / "CAD Testing"
    assert c.home_repo(main) == main
    assert c.home_repo(main / ".claude" / "worktrees" / "pin") == main
    assert c.home_repo(main / "worktrees" / "pin") == main / "worktrees" / "pin"
    assert c.PYTHON == c.HOME / ".venv" / "bin" / "python" and c.E3_OUT == c.HOME / "results" / "e3-lms"
    assert c.HOME == c.home_repo(ROOT)


def _thought(folder, name, thinking, output, reasoning, end=True, termination="submit"):
    import json
    header = {"type": "header", "provider_config": {"thinking": thinking} if thinking else {}}
    lines = [header] + ([{"type": "end", "termination": termination,
                          "usage_total": {"output_tokens": output, "reasoning_tokens": reasoning}}] if end else [])
    (folder / name).write_text("".join(json.dumps(x) + "\n" for x in lines))


def test_the_thinking_check_fails_a_no_think_run_that_carries_reasoning_tokens(tmp_path, capsys):
    import argparse
    c = load_script()
    for run in ("held", "ignored", "thinking", "empty"):
        (tmp_path / run / "episodes").mkdir(parents=True)
    _thought(tmp_path / "held" / "episodes", "a.jsonl", "off", 900, 0)
    _thought(tmp_path / "held" / "episodes", "b.jsonl", "off", 0, 0, end=False)      # still running: not judged
    _thought(tmp_path / "ignored" / "episodes", "a.jsonl", "off", 900, 700)
    _thought(tmp_path / "ignored" / "episodes", "b.jsonl", "off", 100, 0)
    _thought(tmp_path / "thinking" / "episodes", "a.jsonl", None, 1000, 760)
    _thought(tmp_path / "empty" / "episodes", "a.jsonl", "off", 0, 0, end=False)

    def check(run):
        return c.cmd_thinking(argparse.Namespace(run_id=str(tmp_path / run)))

    assert check("held") == 0
    assert "1 finished episode(s), 900 output tokens, 0 of them reasoning (0.0%); 1 run with thinking off, 0 of" \
        in capsys.readouterr().out
    assert check("ignored") == 1
    out = capsys.readouterr().out
    assert "700 of them reasoning (70.0%); 2 run with thinking off, 1 of those thought anyway" in out
    assert "did not obey --thinking off" in out
    assert check("thinking") == 0                       # a run left to the model may think
    assert "(76.0%); 0 run with thinking off" in capsys.readouterr().out
    assert check("empty") == 1                          # nothing finished: nothing to judge by
    assert c.thinking_tally(tmp_path / "ignored") == {"episodes": 2, "output_tokens": 1000, "reasoning_tokens": 700,
                                                       "off": 2, "off_judged": 2, "off_but_thought": 1}


def test_the_thinking_check_does_not_pass_on_an_errored_episode_or_one_without_tokens(tmp_path, capsys):
    import argparse
    c = load_script()
    for run in ("refused", "silent", "mixed", "errored-thinking"):
        (tmp_path / run / "episodes").mkdir(parents=True)
    # the server refused the request: the episode ended in error before a token came back
    _thought(tmp_path / "refused" / "episodes", "a.jsonl", "off", 0, 0, termination="error")
    # ended in error after some output: still not an episode that shows the server obeyed
    _thought(tmp_path / "refused" / "episodes", "b.jsonl", "off", 40, 0, termination="error")
    _thought(tmp_path / "silent" / "episodes", "a.jsonl", "off", 0, 0)             # ended, no usage on record
    _thought(tmp_path / "mixed" / "episodes", "a.jsonl", "off", 0, 0, termination="error")
    _thought(tmp_path / "mixed" / "episodes", "b.jsonl", "off", 900, 0)            # one sound episode is evidence
    _thought(tmp_path / "errored-thinking" / "episodes", "a.jsonl", None, 0, 0, termination="error")

    def check(run):
        return c.cmd_thinking(argparse.Namespace(run_id=str(tmp_path / run)))

    assert check("refused") == 1
    assert "nothing shows the server obeyed --thinking off" in capsys.readouterr().out
    assert c.thinking_tally(tmp_path / "refused")["off_judged"] == 0
    assert check("silent") == 1
    assert "nothing shows the server obeyed" in capsys.readouterr().out
    assert check("mixed") == 0
    assert "nothing shows" not in capsys.readouterr().out
    assert c.thinking_tally(tmp_path / "mixed")["off_judged"] == 1
    assert check("errored-thinking") == 0               # not a thinking-off run: nothing asked of it here


# ------------------------------------------------------------------ where a run stands, and the pin's queue script

def _run_folder(folder, commit, cells, ended, report=False):
    """A stand-in run folder: ``run.json`` at ``commit`` with ``cells`` cells, ``ended`` episodes with an end
    record and one more still being written when there is room, the report folder when ``report``."""
    import json
    (folder / "episodes").mkdir(parents=True)
    (folder / "run.json").write_text(json.dumps({"pins": {"commit": commit}, "cells": cells}))
    for i in range(ended):
        _thought(folder / "episodes", f"e{i}.jsonl", None, 100, 60)
    if ended < cells:
        _thought(folder / "episodes", "open.jsonl", None, 0, 0, end=False)
    if report:
        (folder / "report").mkdir()


def test_run_state_tells_a_new_run_a_partial_one_a_finished_one_and_another_pins(tmp_path, capsys):
    import argparse
    c = load_script()
    _run_folder(tmp_path / "partial", "abc123", 3, 1)
    _run_folder(tmp_path / "ended", "abc123", 2, 2)
    _run_folder(tmp_path / "finished", "abc123", 2, 2, report=True)
    assert c.run_state(tmp_path / "none", "abc123")[0] == "new"
    assert c.run_state(tmp_path / "partial", "abc123") == ("partial", "1 of 3 episodes ended")
    assert c.run_state(tmp_path / "ended", "abc123") == ("partial", "2 of 2 episodes ended, no report")
    assert c.run_state(tmp_path / "finished", "abc123") == ("finished", "2 of 2 episodes ended, report written")
    assert c.run_state(tmp_path / "finished", "def456")[0] == "other"       # another commit made it
    assert c.run_state(tmp_path / "finished")[0] == "finished"             # no commit asked for
    (tmp_path / "bare" / "episodes").mkdir(parents=True)
    assert c.run_state(tmp_path / "bare", "abc123")[0] == "new"
    _thought(tmp_path / "bare" / "episodes", "a.jsonl", None, 0, 0, end=False)
    assert c.run_state(tmp_path / "bare", "abc123")[0] == "partial"        # started, stopped before run.json
    assert c.main(["run-state", str(tmp_path / "partial"), "--commit", "abc123"]) == 0
    assert capsys.readouterr().out == "partial 1 of 3 episodes ended\n"


QUEUE = ROOT / "benchmarks" / "lmstudio" / "queue-base-pin.sh"

# The queue's lms_campaign.py in the stand-in pin: e3, watch and clear-errors are recorded and faked, link_ok says
# yes, and every other subcommand (thinking, run-state) is the real script's, reading the stand-in results folder.
STUB_CAMPAIGN = '''import importlib.util, json, os, pathlib, sys
STUB = pathlib.Path(os.environ["STUB_DIR"])
OUT = pathlib.Path(os.environ["STUB_OUT"])


def link_ok():
    return True


def flag(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def e3(argv):
    with (STUB / "calls.log").open("a") as f:
        f.write(" ".join(argv) + "\\n")
    run_id = flag(argv, "--run-id")
    if "--print" in argv or "--dry-run" in argv:
        print(" ".join(argv) + f" \\nrun {run_id}: 2 episodes")
        return 0
    off = flag(argv, "--thinking") == "off"
    bad = off and "nothink-check" in run_id and os.environ.get("STUB_CHECK") == "error"
    folder = OUT / run_id / "episodes"
    folder.mkdir(parents=True, exist_ok=True)
    (OUT / run_id / "run.json").write_text(json.dumps({"pins": {"commit": os.environ["STUB_COMMIT"]}, "cells": 2}))
    for name in ("a", "b"):
        header = {"type": "header", "provider_config": {"thinking": "off"} if off else {}}
        end = {"type": "end", "termination": "error" if bad else "submit",
               "usage_total": {"output_tokens": 0 if bad else 100, "reasoning_tokens": 0 if off else 60}}
        (folder / f"{name}.jsonl").write_text(json.dumps(header) + "\\n" + json.dumps(end) + "\\n")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "e3":
        sys.exit(e3(sys.argv[1:]))
    if sys.argv[1] in ("watch", "clear-errors"):
        sys.exit(0)
    spec = importlib.util.spec_from_file_location("real_campaign", os.environ["REAL_CAMPAIGN"])
    real = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real)
    real.E3_OUT = OUT
    sys.exit(real.main(sys.argv[1:]))
'''

# The stand-in pin's harness: it names the two flags the queue looks for, and `report RUN` writes the report folder.
STUB_HARNESS = '''import pathlib, sys
FLAGS = ["--system-extra", "--thinking"]
if sys.argv[1] == "report":
    (pathlib.Path(sys.argv[2]) / "report").mkdir(exist_ok=True)
'''

# pgrep: a stall watcher is never there; other queue scripts are the pids in queue-pids; a local run shows when the
# next line of busy-answers is 1 (no line left: none shows). Every look for a local run is recorded.
STUB_PGREP = '''#!/bin/sh
for last; do :; done
case "$last" in
  *"lms_campaign.py watch"*) exit 1 ;;
  *queue-*) test -s "$STUB_DIR/queue-pids" && cat "$STUB_DIR/queue-pids" && exit 0; exit 1 ;;
esac
answer=$(head -n 1 "$STUB_DIR/busy-answers" 2> /dev/null)
test -f "$STUB_DIR/busy-answers" && sed -i.bak 1d "$STUB_DIR/busy-answers"
echo "local-run look: ${answer:-0}" >> "$STUB_DIR/calls.log"
test "$answer" = 1 && echo 4242 && exit 0
exit 1
'''


class _Rig:
    """A stand-in main checkout and pin worktree for queue-base-pin.sh: no model, no server, no real results.
    ``run`` starts the queue for real with every outside command stubbed and returns the finished process."""

    def __init__(self, tmp_path, script=None):
        import os
        import shutil
        import sys
        self.repo, self.pin, self.stubs = tmp_path / "CAD Testing", tmp_path / "pin", tmp_path / "stubs"
        self.out = self.repo / "results" / "e3-lms"
        for d in (self.out, self.repo / ".venv" / "bin", self.stubs, self.pin / "benchmarks" / "lmstudio",
                  self.pin / "benchmarks" / "training", self.pin / "src" / "roaddraft" / "eval"):
            d.mkdir(parents=True)
        self._tool(self.repo / ".venv" / "bin" / "python", f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
        self._tool(self.stubs / "pgrep", STUB_PGREP)
        self._tool(self.stubs / "sleep", '#!/bin/sh\necho "sleep $1" >> "$STUB_DIR/calls.log"\n')
        self._tool(self.stubs / "caffeinate", '#!/bin/sh\nshift\nexec "$@"\n')
        lm = self.pin / "benchmarks" / "lmstudio"
        (lm / "lms_campaign.py").write_text(STUB_CAMPAIGN)
        shutil.copy(SCRIPT.parent / "models.json", lm / "models.json")
        shutil.copy(script or os.environ.get("QUEUE_UNDER_TEST") or QUEUE, lm / "queue-base-pin.sh")
        (self.pin / "benchmarks" / "training" / "conventions-v1.md").write_text("# House rules\n")
        (self.pin / "src" / "roaddraft" / "__init__.py").write_text("")
        (self.pin / "src" / "roaddraft" / "eval" / "__init__.py").write_text("")
        (self.pin / "src" / "roaddraft" / "eval" / "__main__.py").write_text(STUB_HARNESS)
        (self.pin / ".gitignore").write_text("__pycache__/\n")
        for cmd in (["init", "-q"], ["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "pin"],
                    ["tag", "pin/test"]):
            subprocess.run(["git", "-C", str(self.pin)] + cmd, check=True)
        self.commit = subprocess.run(["git", "-C", str(self.pin), "rev-parse", "HEAD"], check=True,
                                     capture_output=True, text=True).stdout.strip()
        self.env = dict(os.environ, PATH=f"{self.stubs}:{os.environ['PATH']}", REPO=str(self.repo),
                        STUB_DIR=str(self.stubs), STUB_OUT=str(self.out), STUB_COMMIT=self.commit,
                        REAL_CAMPAIGN=str(SCRIPT), PYTHONDONTWRITEBYTECODE="1", QUEUE_NAME="queue-test",
                        GAP_S="0", POLL_S="7", IDLE_POLLS="1", ATTEMPTS="2")
        for name in ("QUEUE_CAFFEINATED", "SUFFIX", "PHASES", "SETS", "MODEL", "NOTHINK_MODEL"):
            self.env.pop(name, None)

    @staticmethod
    def _tool(path, text):
        path.write_text(text)
        path.chmod(0o755)

    def run(self, *args, cwd=None, script="benchmarks/lmstudio/queue-base-pin.sh", **env):
        return subprocess.run(["zsh", script, str(self.pin), "pin/test", *args], cwd=cwd or self.pin,
                              env=dict(self.env, **env), capture_output=True, text=True, timeout=120)

    def calls(self):
        f = self.stubs / "calls.log"
        return f.read_text().splitlines() if f.exists() else []

    def started(self):
        """The run ids the queue started for real, in order (a run started twice is named twice)."""
        return [c.split("--run-id ")[1].split()[0] for c in self.calls()
                if c.startswith("e3 ") and "--print" not in c and "--dry-run" not in c]

    def log(self):
        return (self.out / "queue-test.log").read_text()


def _rig(tmp_path, **kw):
    import shutil
    import pytest
    if not shutil.which("zsh") or not shutil.which("git"):
        pytest.skip("the queue script needs zsh and git")
    return _Rig(tmp_path, **kw)


Q9 = "qwen3.5-9b-q4km-lms"


def test_the_queue_names_its_runs_by_the_model_in_use(tmp_path):
    rig = _rig(tmp_path)
    r = rig.run("--dry-run", SETS="d1-test")
    assert r.returncode == 0, r.stdout + r.stderr
    # today's defaults keep today's ids
    for run_id in (f"e3-d1-test-{Q9}-single-vague-pin1", f"e3-d1-test-{Q9}-single-vague-nothink-pin1",
                   f"e3-d1-test-{Q9}-single-vague-t0-pin1", f"e3-nothink-check-{Q9}-pin1"):
        assert f"--run-id {run_id} " in r.stdout
    assert not (rig.out / "queue-test.log").exists() and list(rig.out.iterdir()) == []      # a dry run writes nothing
    # another model is filed under its own label, the no-think base under its own too
    r = rig.run("--dry-run", SETS="d1-test", MODEL="gemma-4-12b")
    assert "--run-id e3-d1-test-gemma-4-12b-q8-lms-single-vague-pin1 " in r.stdout
    assert "--run-id e3-d1-test-gemma-4-12b-q8-lms-single-vague-nothink-pin1 " in r.stdout
    assert Q9 not in r.stdout
    r = rig.run("--dry-run", SETS="d1-test", NOTHINK_MODEL="gemma-4-12b")
    assert f"--run-id e3-d1-test-{Q9}-single-vague-pin1 " in r.stdout
    assert f"--run-id e3-d1-test-{Q9}-single-vague-t0-pin1 " in r.stdout
    assert "--run-id e3-d1-test-gemma-4-12b-q8-lms-single-vague-nothink-pin1 " in r.stdout
    assert "--run-id e3-nothink-check-gemma-4-12b-q8-lms-pin1 " in r.stdout
    r = rig.run(SETS="d1-test", MODEL="no-such-model")
    assert r.returncode == 1 and "no model no-such-model" in r.stderr and rig.started() == []


def test_the_queue_stores_the_script_that_ran_when_started_by_a_relative_path(tmp_path):
    rig = _rig(tmp_path)
    r = rig.run(PHASES="base", SETS="d1-dev")           # from inside the pin, by the path the usage line gives
    assert r.returncode == 0, r.stdout + r.stderr
    stored = rig.out / "queue-test.sh"
    assert stored.read_bytes() == (rig.pin / "benchmarks" / "lmstudio" / "queue-base-pin.sh").read_bytes()
    assert rig.started() == [f"e3-d1-dev-{Q9}-single-vague-pin1"]
    assert "report written" in rig.log()


def _alive_for(seconds):
    """The pid of a process that lives ``seconds`` and belongs to no one here (so it is gone when it ends)."""
    r = subprocess.run(["/bin/sh", "-c", f"/bin/sleep {seconds} > /dev/null 2>&1 & echo $!"],
                       capture_output=True, text=True, check=True)
    return int(r.stdout)


def _gone(pid):
    import os
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_the_queue_waits_for_the_other_queues_and_for_a_quiet_stretch_before_its_first_run(tmp_path):
    rig = _rig(tmp_path)
    # another queue between two of its steps: no local run at the first two looks, one at the third
    (rig.stubs / "busy-answers").write_text("0\n0\n1\n0\n0\n0\n")
    after, other = _alive_for(1), _alive_for(2)
    (rig.stubs / "queue-pids").write_text(f"{other}\n")
    r = rig.run("--after", str(after), PHASES="base", SETS="d1-dev", IDLE_POLLS="3")
    assert r.returncode == 0, r.stdout + r.stderr
    assert _gone(after) and _gone(other)                # both had ended before the queue went on
    log = rig.log()
    assert f"waiting for pid {after} to end" in log
    assert f"other local queue script(s) alive at the start to end: pids {other}" in log
    assert "another local run is going; waiting until none shows for 3 look(s) in a row, 7 s apart" in log
    calls = rig.calls()
    first_run = next(i for i, c in enumerate(calls) if c.startswith("e3 "))
    looks = [c for c in calls[:first_run] if c.startswith("local-run look")]
    # the run seen at the third look restarts the count: three clear looks in a row, then one more before the attempt
    assert looks == ["local-run look: 0", "local-run look: 0", "local-run look: 1", "local-run look: 0",
                     "local-run look: 0", "local-run look: 0", "local-run look: 0"]
    assert rig.started() == [f"e3-d1-dev-{Q9}-single-vague-pin1"]
    r = rig.run("--after", "soon", PHASES="base", SETS="d1-dev", QUEUE_NAME="queue-other")
    assert r.returncode == 2 and "--after takes a process id" in r.stderr


def test_the_queue_holds_an_attempt_while_another_local_run_is_going(tmp_path):
    rig = _rig(tmp_path)
    # quiet at the start (one look), then another queue's run shows at the look before the first attempt
    (rig.stubs / "busy-answers").write_text("0\n1\n1\n0\n")
    r = rig.run(PHASES="base", SETS="d1-dev")
    assert r.returncode == 0, r.stdout + r.stderr
    calls = rig.calls()
    first_run = next(i for i, c in enumerate(calls) if c.startswith("e3 "))
    assert [c for c in calls[:first_run] if c.startswith("local-run look")] == \
        ["local-run look: 0", "local-run look: 1", "local-run look: 1", "local-run look: 0"]
    assert "start e3-d1-dev" in rig.log().split("no other local run for 1 look(s) in a row")[1]


def test_a_stopped_queue_is_started_again_and_carries_on_where_it_was(tmp_path):
    rig = _rig(tmp_path)
    done, half, new = (f"e3-{s}-{Q9}-single-vague-pin1" for s in ("d1-dev", "d1-real-dev", "pilot-dev"))
    _run_folder(rig.out / done, rig.commit, 2, 2, report=True)
    _run_folder(rig.out / half, rig.commit, 2, 1)
    sets = dict(PHASES="base", SETS="d1-dev d1-real-dev pilot-dev")
    r = rig.run(**sets)
    assert r.returncode == 1 and "exists already" in r.stderr and "--resume" in r.stderr
    assert rig.started() == [] and not (rig.out / "queue-test.log").exists()
    r = rig.run("--resume", "--dry-run", **sets)
    assert f"{done} is finished already" in r.stdout and f"(resumes {half}: 1 of 2 episodes ended)" in r.stdout
    assert rig.started() == []
    r = rig.run("--resume", **sets)
    assert r.returncode == 0, r.stdout + r.stderr
    assert rig.started() == [half, new]                 # the finished run is left alone, the half-run one keeps its id
    log = rig.log()
    assert "started again with --resume" in log and f"{done} is finished already" in log
    assert f"{half} is carried on (1 of 2 episodes ended)" in log
    assert (rig.out / half / "report").is_dir() and (rig.out / new / "report").is_dir()
    # the same queue again, under its own name: its log is carried on and nothing is left to run
    (rig.stubs / "calls.log").unlink()
    r = rig.run("--resume", **sets)
    assert r.returncode == 0 and rig.started() == []
    assert rig.log().count("started again with --resume") == 2
    # a run another commit made is never carried on
    _run_folder(rig.out / f"e3-d1-test-{Q9}-single-vague-pin1", "0" * 40, 2, 1)
    r = rig.run("--resume", PHASES="base", SETS="d1-test")
    assert r.returncode == 1 and "was not run at pin/test" in r.stderr and rig.started() == []


def test_the_queue_leaves_the_nothink_sets_out_when_the_check_episode_ends_in_error(tmp_path):
    rig = _rig(tmp_path)
    check = f"e3-nothink-check-{Q9}-pin1"
    r = rig.run(PHASES="nothink", SETS="d1-dev d1-real-dev", STUB_CHECK="error")
    assert r.returncode == 0, r.stdout + r.stderr
    assert rig.started() == [check]                     # the check ran; no nothink set after it
    log = rig.log()
    assert "nothing shows the server obeyed --thinking off" in log and "NOT run: every nothink set" in log
    assert "thinking off holds" not in log
    # that check episode is not judged again: a plain start refuses it, a relaunch checks on a fresh one
    r = rig.run(PHASES="nothink", SETS="d1-dev", QUEUE_NAME="queue-again")
    assert r.returncode == 1 and f"a check run {check} exists already" in r.stderr
    (rig.stubs / "calls.log").unlink()
    r = rig.run("--resume", PHASES="nothink", SETS="d1-dev")
    assert r.returncode == 0, r.stdout + r.stderr
    assert rig.started() == [f"{check}-r2", f"e3-d1-dev-{Q9}-single-vague-nothink-pin1"]
    assert "thinking off holds on the check episode" in rig.log()


# ------------------------------------------------------------------ a trained checkpoint (2026-11-15)

ADD = ROOT / "benchmarks" / "lmstudio" / "add_checkpoint.py"
CK = "qwen3.5-9b-t1s"
QCK = "qwen3.5-9b-t1s-q4km-lms"


def _add_checkpoint():
    spec = importlib.util.spec_from_file_location("add_checkpoint_under_test", ADD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ckpt_rig(tmp_path, vision=False):
    """The rig with a main checkout that knows a checkpoint: the pin's driver beside a models.json with its entry."""
    import json
    import shutil
    rig = _rig(tmp_path)
    lm = rig.repo / "benchmarks" / "lmstudio"
    lm.mkdir(parents=True)
    shutil.copy(rig.pin / "benchmarks" / "lmstudio" / "lms_campaign.py", lm / "lms_campaign.py")
    data = json.loads((SCRIPT.parent / "models.json").read_text())
    _add_checkpoint().add(data, CK, "qwen3.5-9b", "roaddraft/qwen3.5-9b-t1s", sha256="ab" * 32, today="2026-11-15")
    data["models"][CK]["vision"] = vision
    (lm / "models.json").write_text(json.dumps(data))
    return rig


def test_a_checkpoints_entry_carries_the_bases_sampling_and_its_own_label():
    import json
    import pytest
    mod = _add_checkpoint()
    data = json.loads((SCRIPT.parent / "models.json").read_text())
    base = data["models"]["qwen3.5-9b"]
    e = mod.add(data, CK, "qwen3.5-9b", "roaddraft/qwen3.5-9b-t1s", check={"gguf_sha256": "cd" * 32, "adapter": "runs/x"},
                today="2026-11-15")
    assert e["label"] == QCK and e["lms_key"] == "roaddraft/qwen3.5-9b-t1s" and e["vision"] is False
    assert (e["extra_body"], e["context"], e["quantization"]) == (base["extra_body"], base["context"], "Q4_K_M")
    assert e["checkpoint"]["sha256"] == "cd" * 32 and e["checkpoint"]["base"] == "qwen3.5-9b"
    assert "variant" not in e                           # the file is its own key: no variant to select
    with pytest.raises(ValueError, match="already"):    # never over an entry, never under the base's key or label
        mod.add(data, CK, "qwen3.5-9b", "roaddraft/qwen3.5-9b-t1s")
    with pytest.raises(ValueError, match="already carries"):
        mod.add(data, "another", "qwen3.5-9b", base["lms_key"])
    with pytest.raises(ValueError, match="no base model"):
        mod.add(data, "x", "no-such", "k")


def test_the_queue_runs_a_checkpoint_from_the_main_checkouts_entry_with_thinking_off(tmp_path):
    rig = _ckpt_rig(tmp_path)
    r = rig.run("--dry-run", PHASES="ckpt", CKPT=CK, SETS="d1-dev hard-pilots")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"e3 {CK} --taskset d1-dev --samples 1 --run-id e3-d1-dev-{QCK}-single-vague-nothink-pin1 " in r.stdout
    line = next(l for l in r.stdout.splitlines() if f"--run-id e3-hard-pilots-{QCK}" in l)
    assert "--pilots text" in line and "--thinking off" in line          # no vision tower: the text pilots only
    assert f"--run-id e3-nothink-check-{QCK}-pin1 " in r.stdout and Q9 not in r.stdout
    r = rig.run(PHASES="ckpt", CKPT=CK, SETS="d1-dev d1-real-dev")
    assert r.returncode == 0, r.stdout + r.stderr
    assert rig.started() == [f"e3-nothink-check-{QCK}-pin1", f"e3-d1-dev-{QCK}-single-vague-nothink-pin1",
                             f"e3-d1-real-dev-{QCK}-single-vague-nothink-pin1"]
    log = rig.log()
    assert f"checkpoint {CK} ({QCK}, text pilots only)" in log and "thinking off holds on the check episode (ckpt)" in log
    assert all(f"--worktree {rig.pin}" in c for c in rig.calls() if c.startswith("e3 "))    # the pin's harness


def test_a_checkpoint_that_takes_images_runs_every_pilot(tmp_path):
    rig = _ckpt_rig(tmp_path, vision=True)
    r = rig.run("--dry-run", PHASES="ckpt", CKPT=CK, SETS="hard-pilots")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "--pilots all" in next(l for l in r.stdout.splitlines() if f"--run-id e3-hard-pilots-{QCK}" in l)


def test_the_queue_refuses_a_checkpoint_it_cannot_place(tmp_path):
    rig = _ckpt_rig(tmp_path)
    r = rig.run(PHASES="ckpt")
    assert r.returncode == 1 and "no CKPT=" in r.stderr
    r = rig.run(PHASES="ckpt", CKPT="no-such")
    assert r.returncode == 1 and "no model no-such" in r.stderr
    main_driver = rig.repo / "benchmarks" / "lmstudio" / "lms_campaign.py"
    main_driver.write_text(main_driver.read_text() + "# another version\n")
    r = rig.run(PHASES="ckpt", CKPT=CK)
    assert r.returncode == 1 and "is not the pin's lms_campaign.py" in r.stderr and rig.started() == []
    # the base queue never looks at the main checkout's driver or at CKPT
    r = rig.run(PHASES="base", SETS="d1-dev")
    assert r.returncode == 0 and rig.started() == [f"e3-d1-dev-{Q9}-single-vague-pin1"]
