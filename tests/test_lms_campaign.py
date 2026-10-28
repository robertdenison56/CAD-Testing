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
