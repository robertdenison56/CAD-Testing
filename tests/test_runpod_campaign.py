"""The Runpod campaign script's Track D spread rules (2026-10-28, Robert): a model whose Track D row runs on
RobertsPC is not duplicated on Runpod (``trackd_local``; ``e3`` refuses it without --force), and a Runpod public
endpoint (``public: true``, served and billed per token by Runpod) is never created, armed, warmed or deleted
by the script. Written while the PC was busy with a run and NOT RUN that evening (Robert: no tests)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmarks" / "runpod" / "runpod_campaign.py"
SPECS = ROOT / "benchmarks" / "runpod" / "models.json"
PRICES = ROOT / "src" / "roaddraft" / "eval" / "prices.json"


def load_script():
    spec = importlib.util.spec_from_file_location("runpod_campaign_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def e3_args(name: str, **over) -> argparse.Namespace:
    base = dict(name=name, taskset="d1-test", samples=1, limit=None, mode="single", level="explicit",
                concurrency=4, run_id=None, dry_run=False, print=True, force=False)
    base.update(over)
    return argparse.Namespace(**base)


def test_the_spread_marks_the_local_rows_and_the_public_endpoint():
    data = json.loads(SPECS.read_text())
    m = data["models"]
    for name in ("qwen3.5-4b", "qwen3.5-9b", "gemma-4-12b"):
        assert m[name]["trackd_local"], name
    assert "trackd_local" not in m["qwen3.6-35b-a3b"]
    glm = m["glm-5.3"]
    assert glm["public"] is True and glm["endpoint"] == "b1dd8hy2hqo1nb" and glm["context"] == 262144
    assert glm["pricing_usd_per_m"] == {"input": 0.77, "cached_input": 0.143, "output": 2.42}
    prices = json.loads(PRICES.read_text())["models"]["glm-5.3"]
    assert prices == {"input": 0.77, "output": 2.42, "cache_read": 0.143, "cache_write": 0.0}


def test_e3_refuses_a_model_whose_track_d_row_is_local_unless_forced(capsys):
    c = load_script()
    with pytest.raises(SystemExit) as ex:
        c.cmd_e3(e3_args("qwen3.5-9b"))
    assert "runs on RobertsPC" in str(ex.value)
    assert c.cmd_e3(e3_args("qwen3.5-9b", force=True)) == 0      # --print: shows the command, runs nothing
    out = capsys.readouterr().out
    assert "roaddraft.eval" in out and "Qwen/Qwen3.5-9B" in out


def test_e3_on_the_public_endpoint_routes_by_its_id_and_passes_its_window(capsys):
    c = load_script()
    assert c.cmd_e3(e3_args("glm-5.3")) == 0
    out = capsys.readouterr().out
    assert "https://api.runpod.ai/v2/b1dd8hy2hqo1nb/openai/v1" in out
    assert "--context-tokens 262144" in out
    assert "--model glm-5.3" in out


def test_a_public_endpoint_is_never_armed_created_warmed_or_deleted():
    c = load_script()
    data = c.load()
    glm = data["models"]["glm-5.3"]
    assert c.is_public(glm) and not c.is_public(data["models"]["qwen3.6-35b-a3b"])
    assert c.arm(glm) is None                                        # returns before any request
    for fn, args in ((c.cmd_create, argparse.Namespace(names=["glm-5.3"], dry_run=True, again=False)),
                     (c.cmd_delete, argparse.Namespace(names=["glm-5.3"], yes=True)),
                     (c.cmd_workers, argparse.Namespace(name="glm-5.3", max=0)),
                     (c.cmd_warm, argparse.Namespace(name="glm-5.3", wait=1))):
        with pytest.raises(SystemExit) as ex:
            fn(args)
        assert "public endpoint" in str(ex.value)
