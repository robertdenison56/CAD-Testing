"""A run given ``--thinking off`` or ``--system-extra`` is its own row, and a run given neither is
keyed, labelled and written as it was; ``pilot-dev`` is never reported (roaddraft.eval.report)."""
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from roaddraft.eval import report as R
from roaddraft.eval.runner import RunSpec, run

REPO = Path(__file__).resolve().parents[1]
EXTRA = {"path": "benchmarks/training/conventions-v1.md", "sha256": "sha256:" + "ab12cd34" + "0" * 56}
BASE_KEY = ["model", "provider", "effort", "dialect", "mode", "level"]


@pytest.fixture(scope="module")
def plain_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("results")
    run(RunSpec(agents=("oracle", "null"), levels=("vague",), modes=("single",), taskset="d1-dev",
                limit=2, results_root=str(root), run_id="plain", concurrency=2))
    return root / "plain"


def _variant_copy(src, dest, change, only=lambda header: True):
    """``src`` copied to ``dest`` with ``change`` applied to each episode header ``only`` picks."""
    shutil.copytree(src, dest)
    for f in sorted((dest / "episodes").glob("*.jsonl")):
        lines = f.read_text(encoding="utf-8").splitlines()
        recs = [json.loads(x) for x in lines]
        for rec in recs:
            if rec.get("type") == "header" and only(rec):
                change(rec)
        f.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return dest


def _think_off(header):
    header.setdefault("provider_config", {})["thinking"] = "off"


def _extra(header):
    header["system_extra"] = dict(EXTRA)


def test_a_run_without_either_setting_is_keyed_and_written_as_before(plain_dir):
    s = R.build(plain_dir)
    assert [list(g["key"]) for g in s["rows"]] == [BASE_KEY, BASE_KEY]
    assert sorted(g["label"] for g in s["rows"]) == ["null · single · vague", "oracle · single · vague"]
    assert not any(d in e["row"] for e in s["_episodes"] for d in R.VARIANT_DIMS)
    files = R.files(s)
    assert files["per_check.csv"].splitlines()[0].startswith("rank,model,provider,effort,dialect,mode,level,check,")
    assert files["taxonomy.csv"].splitlines()[0].startswith("rank,model,provider,effort,dialect,mode,level,category,")
    head = files["episodes.csv"].splitlines()[0].split(",")
    assert head[-1] == "findings" and not set(R.VARIANT_DIMS) & set(head)
    assert "thinking" not in files["summary.json"] and "system_extra" not in files["summary.json"]
    assert R.variant_of({"provider_config": {"extra_body": {}}}) == {} and R.variant_label(s["rows"][0]["key"]) == ""


def test_a_thinking_off_run_is_its_own_row_and_says_so(plain_dir, tmp_path):
    s = R.build(_variant_copy(plain_dir, tmp_path / "nothink", _think_off))
    plain = R.build(plain_dir)
    oracle = next(g for g in s["rows"] if g["key"]["model"] == "oracle")
    assert oracle["key"]["thinking"] == "off" and "system_extra" not in oracle["key"]
    assert oracle["label"] == "oracle · single · vague · thinking off"
    assert {json.dumps(g["key"], sort_keys=True) for g in s["rows"]}.isdisjoint(
        json.dumps(g["key"], sort_keys=True) for g in plain["rows"])
    assert "| oracle · single · vague · thinking off |" in R.render_markdown(s)
    # the effort cell says it too: the switch is sent with every request and is not in extra_body
    assert R.effort_label("qwen/qwen3.5-9b", "openai", None, None, "off") == "thinking off"
    assert R.effort_label("qwen/qwen3.5-9b", "openai", None) == R.effort_label("qwen/qwen3.5-9b", "openai", None, None, None)
    assert R.effort_cell({"key": {"model": "qwen/qwen3.5-9b", "provider": "openai", "effort": None,
                                  "thinking": "off"}}) == "thinking off"
    assert R.effort_label("oracle", "harness", None, None, "off") == "–"


def test_a_system_extra_run_is_its_own_row_named_by_the_sheet_and_its_digest(plain_dir, tmp_path):
    s = R.build(_variant_copy(plain_dir, tmp_path / "t0", _extra))
    oracle = next(g for g in s["rows"] if g["key"]["model"] == "oracle")
    assert oracle["key"]["system_extra"] == "conventions-v1@ab12cd34" and "thinking" not in oracle["key"]
    assert oracle["label"] == "oracle · single · vague · system extra conventions-v1@ab12cd34"
    other = R.variant_of({"system_extra": {"path": "x/conventions-v1.md", "sha256": "sha256:" + "f" * 64}})
    assert other == {"system_extra": "conventions-v1@ffffffff"}
    both = R.variant_of({"provider_config": {"thinking": "off"}, "system_extra": EXTRA})
    assert R.variant_label(both) == "thinking off · system extra conventions-v1@ab12cd34"


def test_one_report_keeps_a_variant_apart_from_the_plain_rows(plain_dir, tmp_path):
    first = sorted(json.loads(f.read_text().splitlines()[0])["task_id"]
                   for f in (plain_dir / "episodes").glob("*.jsonl"))[0]
    mixed = _variant_copy(plain_dir, tmp_path / "mixed", _think_off, only=lambda h: h["task_id"] == first)
    s = R.build(mixed)
    assert sorted(g["label"] for g in s["rows"]) == [
        "null · single · vague", "null · single · vague · thinking off",
        "oracle · single · vague", "oracle · single · vague · thinking off"]
    assert all(g["n_tasks"] == 1 for g in s["rows"])
    files = R.files(s)
    assert files["per_check.csv"].splitlines()[0].startswith(
        "rank,model,provider,effort,dialect,mode,level,thinking,check,")
    head = files["episodes.csv"].splitlines()[0].split(",")
    assert head[-1] == "thinking"
    cells = [line.split(",")[-1] for line in files["episodes.csv"].splitlines()[1:]]
    assert sorted(cells) == ["", "", "off", "off"]


def _row(model, eff, **variant):
    key = {"model": model, "provider": "openai", "effort": None, "dialect": "neutral", "mode": "single",
           "level": "vague", **variant}
    return {"label": R.group_label(key), "key": key, "effort": R.effort_cell({"key": key}),
            "effective_mean": eff, "ci_low": eff - 3, "ci_high": eff + 3, "half_width": 3.0,
            "rubric_mean": eff + 5, "hard_fail_rate": 0.1, "clean_sheet_rate": 0.2, "invalid_call_rate": 0.01,
            "cost_per_sheet": None, "n_tasks": 100, "k_min": 1, "k_max": 1}


def _summary(run_id, row, taskset):
    return {"run_id": run_id, "taskset": taskset, "episodes": 100, "versions": {"spec_version": ["v1"]},
            "publish_problems": [], "rows": [row]}


def _three_ways():
    """The 9B as the pin queue runs it: base and thinking off on every set, the convention sheet on two."""
    sums = []
    for name in R.LEADERBOARD_SETS:
        sums.append(_summary(f"base-{name}", _row("qwen/qwen3.5-9b", 70.0), name))
        sums.append(_summary(f"nothink-{name}", _row("qwen/qwen3.5-9b", 40.0, thinking="off"), name))
        if name in ("d1-test", "d1-real"):
            sums.append(_summary(f"t0-{name}", _row("qwen/qwen3.5-9b", 85.0,
                                                    system_extra="conventions-v1@ab12cd34"), name))
    return sums


def test_the_board_and_the_overall_table_rank_each_variant_as_its_own_row():
    b = R.board(_three_ways())
    assert [(r["label"], r["effort"], r["run_id"]) for r in b["boards"]["d1-test"]["ranked"]] == [
        ("qwen/qwen3.5-9b · single · vague · system extra conventions-v1@ab12cd34", "default", "t0-d1-test"),
        ("qwen/qwen3.5-9b · single · vague", "default", "base-d1-test"),
        ("qwen/qwen3.5-9b · single · vague · thinking off", "thinking off", "nothink-d1-test")]
    ov = b["overall"]["vague"]
    assert [(o["label"], o["overall"]) for o in ov["ranked"]] == [
        ("qwen/qwen3.5-9b · single · vague", 70.0), ("qwen/qwen3.5-9b · single · vague · thinking off", 40.0)]
    base, nothink = ov["ranked"]
    assert {c["run_id"] for c in base["sets"].values()} == {f"base-{n}" for n in R.LEADERBOARD_SETS}
    assert {c["run_id"] for c in nothink["sets"].values()} == {f"nothink-{n}" for n in R.LEADERBOARD_SETS}
    assert [(o["label"], o["n_sets"]) for o in ov["partial"]] == [
        ("qwen/qwen3.5-9b · single · vague · system extra conventions-v1@ab12cd34", 2)]
    md = R.render_board(b)
    assert "| qwen/qwen3.5-9b · single · vague · thinking off | thinking off | **40.0** |" in md
    assert "| qwen/qwen3.5-9b · single · vague | default | **70.0** |" in md


def test_the_dashboard_rows_say_the_variant_and_a_plain_row_is_unchanged():
    spec = importlib.util.spec_from_file_location("export_eval_dashboard", REPO / "scripts/export_eval_dashboard.py")
    D = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(D)
    ov = R.board(_three_ways())["overall"]["vague"]
    rows = [D.overall_row(o, len(ov["sets"]), "2026-11-14") for o in ov["ranked"] + ov["partial"]]
    name = D.model_name({"model": "qwen/qwen3.5-9b"}, "base-d1-test")
    assert [(r["key"], r["name"], r["effort"]) for r in rows] == [
        ("model=qwen/qwen3.5-9b|provider=openai|effort=None|mode=single", name, "default"),
        ("model=qwen/qwen3.5-9b|provider=openai|effort=None|mode=single|thinking=off",
         f"{name} · thinking off", "thinking off"),
        ("model=qwen/qwen3.5-9b|provider=openai|effort=None|mode=single|system_extra=conventions-v1@ab12cd34",
         f"{name} · system extra conventions-v1@ab12cd34", "default")]
    assert len({r["key"] for r in rows}) == 3
    plain = _row("qwen/qwen3.5-9b", 70.0)["key"]
    assert D.row_label(plain) == "vague prompt"
    assert D.row_label({**plain, "thinking": "off"}) == "vague prompt · thinking off"
    assert D.row_label({**plain, "system_extra": "conventions-v1@ab12cd34"}) == \
        "vague prompt · system extra conventions-v1@ab12cd34"


def test_pilot_dev_is_a_development_set_and_is_never_reported(tmp_path):
    assert "pilot-dev" in R.NEVER_REPORTED and "pilot-dev" not in R.LEADERBOARD_SETS
    s = {"run_id": "pd", "taskset": "pilot-dev", "incomplete": [], "stale": [], "coverage": None,
         "versions": {"spec_version": ["v1"], "verifier_version": ["v8"], "spec_hash": ["sha256:0"]}}
    s["publish_problems"] = R.publish_problems(s)
    assert s["publish_problems"] == ["pilot-dev is a development set and is never reported"]
    with pytest.raises(ValueError, match="pilot-dev is a development set"):
        R.publish(s, tmp_path / "report", runs_root=tmp_path / "runs")
    assert not (tmp_path / "runs").exists()
    listed = R.board([{**s, "episodes": 19, "rows": []}])["others"]
    assert [(o["run_id"], o["reasons"]) for o in listed] == [
        ("pd", ["pilot-dev is a development set and is never reported"])]
