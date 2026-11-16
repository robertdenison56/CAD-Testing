"""Stage T2's task sets and keep rule (``RoadDraft_Training_Plan.md`` §3 and §4;
``roaddraft.eval.t2``, ``taskset.t2_overlap``, ``conversations.run_rollouts``): a
round's manifest is planned from a run's per-type miss rates on seeds no other
set draws, and a rollout on it is training data only when it submitted and
re-scores 100.  No model is needed: the runs here are synthetic folders and
the harness's own oracle, null and scripted agents."""
from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path

import pytest

from roaddraft.eval import t2
from roaddraft.eval import taskset as tasksets
from roaddraft.eval.__main__ import main
from roaddraft.eval.runner import RunSpec, run
from roaddraft.trajectories import conversations as cv

NAME = "d1-train-t2-r1"
SIZE = 48


def _fake_run(root: Path, run_id: str, taskset, rows, tasksets_root=None) -> Path:
    """A run folder holding what ``t2.observe`` reads: ``run.json`` and, for each
    ``(task_id, task_type, score[, termination[, level]])``, an episode file's
    header and end records."""
    run_dir = root / run_id
    (run_dir / "episodes").mkdir(parents=True)
    spec = {"taskset": taskset, "tasksets_root": str(tasksets_root) if tasksets_root else None}
    (run_dir / "run.json").write_text(json.dumps({"spec": spec}))
    for i, row in enumerate(rows):
        task_id, ttype, score = row[:3]
        termination = row[3] if len(row) > 3 else "submit"
        level = row[4] if len(row) > 4 else "vague"
        records = [{"type": "header", "task_id": task_id, "task_type": ttype, "level": level,
                    "agent": "checkpoint", "model": "checkpoint"}]
        if termination is not None:
            records.append({"type": "end", "termination": termination, "effective_score": score})
        (run_dir / "episodes" / f"{task_id}.checkpoint.neutral.single.{level}.{i}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in records))
    return run_dir


def _dev_rows(score_of) -> list:
    return [(e["task_id"], e["task_type"], score_of(e)) for e in tasksets.load("d1-dev")["tasks"]]


def _observed(score_of) -> list:
    """The per-cell counts of a ``d1-dev`` run scoring ``score_of(entry)``."""
    counts = Counter()
    misses = Counter()
    for e in tasksets.load("d1-dev")["tasks"]:
        counts[e["task_type"]] += 1
        misses[e["task_type"]] += score_of(e) < 100.0
    return [{"flavour": "plain", "task_type": t, "n": counts[t], "misses": misses[t]}
            for t in sorted(counts)]


#: a checkpoint that still fails the lettering and the whole sheets, and passes the rest
FAILS = ("bearings", "curve-callouts", "curve-table", "plan-sheet", "annotate-base")


def _mixed(entry) -> float:
    return 62.5 if entry["task_type"] in FAILS else 100.0


# ------------------------------------------------------------ the cells

def test_every_training_set_is_a_flavour_and_every_cell_is_dialed_by_its_own_set():
    assert [f.taskset for f in t2.FLAVOURS] == list(tasksets.TRAIN_NAMES)
    base = t2.base_counts()
    assert len(base) == 42 and sum(base.values()) == sum(
        len(tasksets.load(n)["tasks"]) for n in tasksets.TRAIN_NAMES)
    assert {t for f, t in base if f == "plain"} == set(tasksets.SEEDED_TYPES)
    assert {t for f, t in base if f == "twist"} == set(tasksets.TWIST_TYPES)
    assert {t for f, t in base if f == "breaks"} == {"plan-sheet-breaks"}
    for flavour, ttype in base:
        picked = [t2.nth_index(flavour, ttype, k) for k in range(40)]
        assert picked == sorted(set(picked))   # each its own index, in the cycle's order
        assert {t2.FLAVOUR[flavour].dials(i)["task_type"] for i in picked} == {ttype}
    # a type's tasks turn the other dials as its set does: every curve count, both equations
    plain = [tasksets.dials(t2.nth_index("plain", "stationing", k)) for k in range(12)]
    assert {d["curves"] for d in plain} == {1, 2, 3} and {d["equations"] for d in plain} == {True, False}
    assert {d["sheets"] for d in plain} == {1, 2}
    with pytest.raises(ValueError, match="never give"):
        t2.nth_index("crowd", "title-block", 0)


def test_no_t2_name_is_a_generated_set_and_the_seeds_are_no_other_sets():
    everything = tasksets.NAMES + tasksets.TRAIN_NAMES + tasksets.PROBE_TRAIN_NAMES
    assert not any(tasksets.is_t2(n) for n in everything)
    assert tasksets.is_t2(NAME) and not tasksets.is_t2("d1-train-t2-") and not tasksets.is_t2(None)
    with pytest.raises(ValueError, match="unknown task set"):
        tasksets.build(NAME)
    # `eval taskset` neither writes one by name nor finds one that was never planned
    never = "d1-train-t2-never-planned"
    assert main(["taskset", "--write", never]) == 1 and main(["taskset", never]) == 1
    assert not tasksets.manifest_path(never).exists()
    used = {e["seed"] for n in everything for e in tasksets.load(n)["tasks"] if "seed" in e}
    assert not used & set(tasksets.T2_SEEDS)
    first, second = tasksets.t2_round_seeds(1), tasksets.t2_round_seeds(2)
    assert (first.start, first.stop, second.start, second.stop) == (21000, 22000, 22000, 23000)
    for bad in (0, 3):
        with pytest.raises(ValueError, match="rounds 1 to 2"):
            tasksets.t2_round_seeds(bad)


def test_a_t2_manifest_in_the_repo_is_current_and_shares_nothing():
    # none is committed until a round is planned; one that is must stay clean
    for name in tasksets.t2_names():
        assert t2.check(name) == [], name


# ------------------------------------------------------------ the weighting

def test_allocate_gives_whole_tasks_that_add_up_one_a_cell_when_there_are_enough():
    weights = [0.5, 0.3, 0.15, 0.05]
    assert t2.allocate(weights, 100) == [49, 30, 15, 6]   # one each, 96 by weight
    assert sum(t2.allocate(weights, 7)) == 7 and min(t2.allocate(weights, 7)) >= 1
    assert t2.allocate(weights, 3) == [2, 1, 0, 0]   # fewer tasks than cells: by weight alone
    assert t2.allocate([0.25] * 4, 6) == [2, 2, 1, 1]   # a tie goes to the earlier cell
    assert t2.allocate(weights, 0) == [0, 0, 0, 0]


def test_the_plan_is_a_function_of_the_runs_counts_and_weighs_what_fails():
    seen = _observed(_mixed)
    p = t2.plan(seen, 1, 600)
    shuffled = list(seen)
    random.Random(7).shuffle(shuffled)
    assert t2.plan(shuffled, 1, 600) == p and t2.plan(seen, 1, 600) == p
    cells = {(c["flavour"], c["task_type"]): c for c in p["cells"]}
    assert sum(c["count"] for c in p["cells"]) == 600 and p["seeds"] == [21000, 21999]
    assert abs(sum(c["weight"] for c in p["cells"]) - 1.0) < 1e-4
    # the floor: no cell under a quarter of its training share, and every cell has a task
    for c in p["cells"]:
        assert c["weight"] >= t2.FLOOR * c["base"] - 1e-6 and c["count"] >= 1
    # d1-train holds as many of each of these types; the failed one draws more
    assert cells[("plain", "bearings")]["base"] == cells[("plain", "stationing")]["base"]
    assert cells[("plain", "bearings")]["count"] > 2 * cells[("plain", "stationing")]["count"]
    assert cells[("plain", "bearings")]["source"] == "run"
    # three of three and none of three, each shrunk toward the run's own rate
    assert cells[("plain", "bearings")]["miss_rate"] > 0.7 > 0.2 > cells[("plain", "stationing")]["miss_rate"]
    # a cell the run never met takes the type's rate from where it was met, else the run's
    assert cells[("twist", "bearings")]["source"] == "type" and cells[("twist", "bearings")]["n"] == 0
    assert cells[("twist", "bearings")]["miss_rate"] > cells[("twist", "stationing")]["miss_rate"]
    assert cells[("breaks", "plan-sheet-breaks")]["source"] == "overall"
    assert cells[("breaks", "plan-sheet-breaks")]["miss_rate"] == p["observed"]["miss_rate"]
    # a higher floor flattens the round toward the training mix
    flat = {(c["flavour"], c["task_type"]): c for c in t2.plan(seen, 1, 600, floor=1.0)["cells"]}
    assert all(abs(c["weight"] - c["base"]) < 1e-6 for c in flat.values())
    assert flat[("plain", "bearings")]["count"] < cells[("plain", "bearings")]["count"]
    table = t2.render_table(p)
    assert "plain         bearings" in table and "kept (est.)" in table


def test_a_run_that_passes_everything_or_nothing_draws_the_training_mix():
    passed = t2.plan(_observed(lambda e: 100.0), 1, 600)
    failed = t2.plan(_observed(lambda e: 0.0), 1, 600)
    assert passed["observed"]["miss_rate"] == 0.0 and failed["observed"]["miss_rate"] == 1.0
    for p in (passed, failed):
        assert all(abs(c["weight"] - c["base"]) < 1e-6 for c in p["cells"])
        assert sum(c["count"] for c in p["cells"]) == 600 and min(c["count"] for c in p["cells"]) >= 1
    assert [c["count"] for c in passed["cells"]] == [c["count"] for c in failed["cells"]]
    # what a round of each would keep, by the table's own estimate: all of it, none of it
    assert sum(c["expected_kept"] for c in passed["cells"]) == 600.0
    assert sum(c["expected_kept"] for c in failed["cells"]) == 0.0


def test_a_plan_needs_episodes_a_round_that_has_seeds_and_a_floor_that_is_a_share():
    seen = _observed(_mixed)
    with pytest.raises(ValueError, match="no finished episode"):
        t2.plan([], 1, 60)
    with pytest.raises(ValueError, match="rounds 1 to 2"):
        t2.plan(seen, 3, 60)
    with pytest.raises(ValueError, match="floor"):
        t2.plan(seen, 1, 60, floor=1.5)
    with pytest.raises(ValueError, match="unknown flavour"):
        t2.plan(seen, 1, 60, flavours=["wide"])
    only = t2.plan(seen, 2, 30, flavours=["hard", "breaks"])
    assert {c["flavour"] for c in only["cells"]} == {"hard", "breaks"} and only["seeds"] == [22000, 22999]
    assert sum(c["count"] for c in only["cells"]) == 30


# ------------------------------------------------------------ reading a run

def test_observe_counts_finished_episodes_by_cell_and_leaves_the_rest_out(tmp_path):
    rows = _dev_rows(_mixed)
    extra = [("t-err", "stationing", 0.0, "error"), ("t-open", "stationing", 0.0, None),
             ("t-explicit", "stationing", 0.0, "submit", "explicit"),
             ("t-budget", "stationing", 40.0, "budget")]
    run_dir = _fake_run(tmp_path, "ckpt-d1-dev", "d1-dev", rows + extra)
    seen = t2.observe([run_dir], level="vague")
    row = seen["runs"][0]
    assert (row["run_id"], row["taskset"], row["agents"], row["levels"]) == (
        "ckpt-d1-dev", "d1-dev", ["checkpoint"], ["vague"])
    assert (row["episodes"], row["errors"], row["unfinished"], row["other_level"]) == (51, 1, 1, 1)
    want = {(r["flavour"], r["task_type"]): (r["n"], r["misses"]) for r in _observed(_mixed)}
    n, m = want[("plain", "stationing")]
    want[("plain", "stationing")] = (n + 1, m + 1)   # the one that ran out of budget is a miss
    assert {(r["flavour"], r["task_type"]): (r["n"], r["misses"]) for r in seen["cells"]} == want
    assert row["misses"] == sum(m for _, m in want.values())
    # every level when none is named; two runs add up
    assert t2.observe([run_dir])["runs"][0]["episodes"] == 52
    both = t2.observe([run_dir, run_dir], level="vague")
    assert sum(r["n"] for r in both["cells"]) == 102


def test_a_run_on_a_training_set_or_an_earlier_round_is_read_by_its_own_flavour(tmp_path, manifest_root):
    hard = tasksets.load("d1-train-hard")["tasks"][:6]
    a = _fake_run(tmp_path, "ckpt-hard", "d1-train-hard",
                  [(e["task_id"], e["task_type"], 100.0) for e in hard])
    assert {r["flavour"] for r in t2.observe([a])["cells"]} == {"hard"}
    tasks = tasksets.load(NAME, manifest_root)["tasks"]
    b = _fake_run(tmp_path, "ckpt-r1", NAME, [(e["task_id"], e["task_type"], 0.0) for e in tasks]
                  + [("gone", "stationing", 0.0)], tasksets_root=manifest_root)
    seen = t2.observe([b])
    assert seen["runs"][0]["unplaced"] == 1 and seen["runs"][0]["episodes"] == len(tasks)
    assert Counter({(r["flavour"], r["task_type"]): r["n"] for r in seen["cells"]}) == Counter(
        (e["flavour"], e["task_type"]) for e in tasks)


@pytest.mark.parametrize("taskset, why", [("d1-test", "held-out"), ("d1-test-hard", "held-out"),
                                          ("hard-pilots", "held-out"), ("train-deeds", "planned from"),
                                          (None, "no named task set")])
def test_a_round_is_never_planned_from_a_held_out_run(tmp_path, taskset, why):
    run_dir = _fake_run(tmp_path, "ckpt-test", taskset, [("t1", "stationing", 100.0)])
    with pytest.raises(ValueError, match=why):
        t2.observe([run_dir])
    assert main(["t2", "plan", str(run_dir), "--round", "1", "--root", str(tmp_path / "sets")]) == 2
    assert not (tmp_path / "sets").exists()
    with pytest.raises(FileNotFoundError):
        t2.observe([tmp_path / "no-such-run"])


# ------------------------------------------------------------ the manifest

@pytest.fixture(scope="module")
def planned(tmp_path_factory):
    """A small round planned through the CLI from a synthetic ``d1-dev`` run:
    the folder its manifest is in, the manifest, and what the CLI printed."""
    tmp = tmp_path_factory.mktemp("t2")
    run_dir = _fake_run(tmp, "ckpt-d1-dev", "d1-dev", _dev_rows(_mixed))
    root = tmp / "tasksets"
    import contextlib
    import io
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert main(["t2", "plan", str(run_dir), "--round", "1", "--size", str(SIZE), "--dry-run",
                     "--root", str(root)]) == 0
        assert not root.exists()   # a dry run builds and writes nothing
        assert main(["t2", "plan", str(run_dir), "--round", "1", "--size", str(SIZE),
                     "--root", str(root)]) == 0
    return {"root": root, "run_dir": run_dir, "manifest": tasksets.load(NAME, root),
            "printed": out.getvalue(), "tmp": tmp}


@pytest.fixture(scope="module")
def manifest_root(planned):
    return planned["root"]


def test_the_cli_prints_the_type_table_and_writes_the_manifest(planned):
    printed, m = planned["printed"], planned["manifest"]
    assert "ckpt-d1-dev (d1-dev; checkpoint; vague):" in printed
    assert f"round 1: {SIZE} tasks on seeds 21000-21999" in printed
    assert "dry run: d1-train-t2-r1 not built" in printed
    assert f"{NAME}: {SIZE} tasks" in printed and "shares nothing with any other set" in printed
    assert sorted(p.name for p in planned["root"].iterdir()) == [f"{NAME}.json"]
    assert m["taskset"] == NAME and m["generator_version"] == tasksets.GENERATOR_VERSION
    record = m["t2"]
    assert (record["round"], record["size"], record["floor"]) == (1, SIZE, t2.FLOOR)
    assert record["runs"][0]["run_id"] == "ckpt-d1-dev" and record["observed"]["episodes"] == 50
    assert record["cells"] == t2.plan(_observed(_mixed), 1, SIZE)["cells"]
    # nothing of this checkout's own task sets was written or changed
    assert tasksets.t2_names() == [] or all(t2.check(n) == [] for n in tasksets.t2_names())


def test_the_manifest_holds_the_planned_mix_as_the_training_sets_tasks(planned):
    m = planned["manifest"]
    tasks = m["tasks"]
    assert len(tasks) == SIZE
    want = {(c["flavour"], c["task_type"]): c["count"] for c in m["t2"]["cells"]}
    assert Counter((e["flavour"], e["task_type"]) for e in tasks) == Counter(want)
    # the cells take turns, so a run cut short with --limit still meets every cell
    assert len({(e["flavour"], e["task_type"]) for e in tasks[:42]}) == 42
    # each flavour's entries are its training set's kind of entry
    for e in tasks:
        f = e["flavour"]
        assert bool(e.get("twist")) or f not in ("twist", "twist-widths")
        assert bool(e.get("crowd")) == (f == "crowd")
        assert (e.get("revise") in ("radius", "pi", "station")) == (f == "revise")
        assert str(e.get("revise", "")).startswith("base-") == (f == "revise-base")
        assert set(e) <= {"seed", "curves", "equations", "task_type", "sheets", "task_id", "twist",
                          "crowd", "revise", "dialed", "flavour"}
        assert "sheet_id" not in e and "probe" not in e
    hard = [e for e in tasks if e["flavour"] == "hard"]
    assert {e["task_type"] for e in hard} == set(tasksets.HARD_SEEDED_TYPES)
    assert all(e["curves"] in tasksets.HARD_CURVES and e["sheets"] in tasksets.HARD_SHEETS for e in hard)
    # every entry rebuilds to its id, as any manifest's does
    for e in tasks:
        assert tasksets.task_from_entry(e).task_id == e["task_id"]


def test_the_manifest_is_rebuilt_the_same_from_its_own_record(planned):
    m, root = planned["manifest"], planned["root"]
    again = t2.build(NAME, t2.plan(m["t2"]["observed_cells"], 1, SIZE), m["t2"]["runs"])
    assert t2.text(again) == tasksets.manifest_path(NAME, root).read_text()
    assert t2.check(NAME, root) == []
    assert main(["t2", "check", "--root", str(root)]) == 0
    assert main(["t2", "check", NAME, "--root", str(root)]) == 0


def test_its_ids_seeds_and_sheets_are_no_other_sets(planned):
    m, root = planned["manifest"], planned["root"]
    assert tasksets.t2_overlap(m, root) == []
    seeds = [e["seed"] for e in m["tasks"]]
    assert len(set(seeds)) == len(seeds) == SIZE and set(seeds) <= set(tasksets.t2_round_seeds(1))
    assert seeds == sorted(seeds)   # the round's seeds in order
    assert not set(seeds) & set(m["skipped_seeds"])
    ids = {e["task_id"] for e in m["tasks"]}
    assert len(ids) == SIZE
    for other in tasksets.NAMES + tasksets.TRAIN_NAMES + tasksets.PROBE_TRAIN_NAMES:
        theirs = tasksets.load(other)["tasks"]
        assert not ids & {e[k] for e in theirs for k in ("task_id", "vague_task_id", "base_task_id")
                          if e.get(k)}, other
        assert not set(seeds) & {e["seed"] for e in theirs if "seed" in e}, other
    # the existing tripwire is as it was
    assert tasksets.train_overlap() == []


def test_a_manifest_that_shares_anything_is_refused_and_not_written(planned, tmp_path):
    m = planned["manifest"]
    stolen = tasksets.load("d1-train")["tasks"][0]
    bad = {**m, "tasks": m["tasks"][:5] + [{**stolen, "flavour": "plain"}]}
    problems = tasksets.t2_overlap(bad)
    assert any("d1-train share 1 task id" in p for p in problems)
    assert any("d1-train share 1 seed" in p for p in problems)
    assert any("outside 21000-21999" in p for p in problems)
    with pytest.raises(ValueError, match="is not written"):
        t2.write(bad, tmp_path)
    assert list(tmp_path.iterdir()) == []
    # a held-out seed, a real sheet and a task there twice are named too
    held = tasksets.load("d1-test")["tasks"][0]
    real = tasksets.load("d1-real")["tasks"][0]
    for entry, what in ((held, "d1-test share 1 seed"), (real, "not a seeded task"),
                        (m["tasks"][0], "more than once")):
        found = tasksets.t2_overlap({**m, "tasks": m["tasks"][:5] + [entry]})
        assert any(what in p for p in found), (what, found)
    # another round on this round's seeds, and a round whose seeds are another round's
    other = {**m, "taskset": "d1-train-t2-r1b"}
    tasksets.manifest_path("d1-train-t2-r1b", tmp_path).write_text(t2.text(other))
    assert any("d1-train-t2-r1b share" in p for p in tasksets.t2_overlap(m, tmp_path))
    second = {**m, "t2": {**m["t2"], "round": 2}}
    assert any("outside 22000-22999" in p for p in tasksets.t2_overlap(second))
    with pytest.raises(ValueError, match="not a T2 set name"):
        t2.write({**m, "taskset": "d1-train"}, tmp_path)
    with pytest.raises(ValueError, match="not a T2 set name"):
        t2.build("d1-test", m["t2"])


def test_a_rounds_manifest_is_not_replaced_without_force_and_a_stale_one_is_caught(planned, tmp_path):
    m = planned["manifest"]
    path = t2.write(m, tmp_path)
    assert t2.write(m, tmp_path) == path   # the same manifest again is no change
    smaller = t2.build(NAME, t2.plan(m["t2"]["observed_cells"], 1, 6, flavours=["revise"]))
    with pytest.raises(ValueError, match="holds another manifest"):
        t2.write(smaller, tmp_path)
    assert tasksets.load(NAME, tmp_path) == m
    t2.write(smaller, tmp_path, force=True)
    assert len(tasksets.load(NAME, tmp_path)["tasks"]) == 6 and t2.check(NAME, tmp_path) == []
    # a task list its record does not build is stale
    broken = json.loads(json.dumps(smaller))
    broken["tasks"][0]["task_id"] = "d1-000000000000"
    tasksets.manifest_path(NAME, tmp_path).write_text(t2.text(broken))
    assert any("task ids: 1 of 6 differ" in p for p in t2.check(NAME, tmp_path))
    assert main(["t2", "check", "--root", str(tmp_path)]) == 1


def test_a_round_its_seeds_cannot_fill_says_so(planned, monkeypatch):
    monkeypatch.setattr(tasksets, "T2_ROUND_SEEDS", 4)
    p = t2.plan(planned["manifest"]["t2"]["observed_cells"], 1, 6, flavours=["revise"])
    assert p["seeds"] == [21000, 21003]
    with pytest.raises(ValueError, match="ran out after 4 of 6 tasks"):
        t2.build(NAME, p)


# ------------------------------------------------------------ running it, and the keep rule

@pytest.fixture(scope="module")
def rollouts(planned):
    """The round's manifest run through the CLI by the oracle and the null agent."""
    results = planned["tmp"] / "results"
    assert main(["run", "--taskset", NAME, "--tasksets-root", str(planned["root"]),
                 "--agent", "oracle", "--agent", "null", "--level", "vague",
                 "--out", str(results), "--run-id", "t2-r1"]) == 0
    return results / "t2-r1"


def test_eval_run_takes_the_manifest_and_the_oracle_scores_100_the_null_agent_none(planned, rollouts):
    meta = json.loads((rollouts / "run.json").read_text())
    assert meta["spec"]["taskset"] == NAME and meta["spec"]["tasksets_root"] == str(planned["root"])
    flavour = {e["task_id"]: e["flavour"] for e in planned["manifest"]["tasks"]}
    rows = json.loads((rollouts / "episodes.json").read_text())
    oracle = [r for r in rows if r["agent"] == "oracle"]
    null = [r for r in rows if r["agent"] == "null"]
    assert len(oracle) == len(null) == SIZE
    assert all(r["effective_score"] == 100.0 and r["termination"] == "submit" for r in oracle)
    assert all(r["effective_score"] < 100.0 for r in null)
    # a revised sheet is handed over finished and scores something untouched, as in
    # d1-train-revise; every other start scores nothing
    assert all(r["effective_score"] == 0.0 for r in null if flavour[r["task_id"]] != "revise")
    # ... and the round after can be planned from this one: every cell met, by its flavour
    seen = t2.observe([rollouts], root=planned["root"])
    assert {(r["flavour"], r["task_type"]) for r in seen["cells"]} == {
        (c["flavour"], c["task_type"]) for c in planned["manifest"]["t2"]["cells"]}
    assert seen["runs"][0]["episodes"] == 2 * SIZE and seen["runs"][0]["misses"] == SIZE
    nxt = t2.plan(seen["cells"], 2, 100)
    assert {c["source"] for c in nxt["cells"]} == {"run"} and nxt["seeds"] == [22000, 22999]


def test_a_run_without_the_root_does_not_find_a_manifest_written_elsewhere(planned, tmp_path):
    with pytest.raises(FileNotFoundError):
        run(RunSpec(taskset=NAME, agents=("null",), results_root=str(tmp_path)))


def _only(run_dir: Path, out: Path, agent: str, change=None) -> Path:
    """A run folder of one agent's episodes of ``run_dir``, each rewritten by ``change``."""
    (out / "episodes").mkdir(parents=True)
    (out / "run.json").write_text((run_dir / "run.json").read_text())
    for path in sorted((run_dir / "episodes").glob(f"*.{agent}.*.jsonl")):
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        if change:
            change(records)
        (out / "episodes" / path.name).write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    return out


def test_the_oracles_rollouts_are_all_kept_and_the_null_agents_all_dropped(planned, rollouts, tmp_path):
    root, out = planned["root"], tmp_path / "training"
    summary = cv.run_rollouts(rollouts, NAME, out, root, log=lambda *_: None)
    tally = summary["sets"][f"{NAME}-vague"]
    assert summary["audit"] == cv.DOCUMENT and tally["variant"] == "rollouts"
    assert (tally["episodes"], tally["kept"], tally["dropped"]) == (2 * SIZE, SIZE, {"score": SIZE})
    assert tally["more_samples"] == 0 and tally["run_id"] == "t2-r1" and tally["level"] == "vague"
    assert tally["manifest_seeds"][0] >= 21000 and tally["manifest_seeds"][1] <= 21999
    assert tally["by_type"] == dict(sorted(Counter(e["task_type"] for e in planned["manifest"]["tasks"]).items()))
    lines = [json.loads(line) for line in (out / f"{NAME}-vague.jsonl").read_text().splitlines()]
    assert sorted(c["header"]["task_id"] for c in lines) == sorted(
        e["task_id"] for e in planned["manifest"]["tasks"])
    assert all(c["header"]["taskset"] == NAME and c["header"]["agent"] == "oracle"
               and c["header"]["score"]["effective"] == 100.0 for c in lines)
    assert all(c["messages"][-1]["role"] == "assistant" for c in lines)
    tools = json.loads((out / "tools.json").read_text())
    assert set(tools) == {c["header"]["tools_sha256"] for c in lines}
    # the dataset card takes the set, and says what it is
    card = cv.card(out, tmp_path / "CARD.md").read_text()
    assert f"`{NAME}` are a model's own rollouts" in card and f"| `{NAME}` | 21" in card

    # the null agent alone: nothing kept, every episode with its reason
    nothing = cv.run_rollouts(_only(rollouts, tmp_path / "null-run", "null"), NAME, tmp_path / "none",
                              root, log=lambda *_: None)["sets"][f"{NAME}-vague"]
    assert (nothing["kept"], nothing["dropped"]) == (0, {"score": SIZE})
    assert len(nothing["dropped_examples"]["score"]) == 5
    assert (tmp_path / "none" / f"{NAME}-vague.jsonl").read_text() == ""


def test_a_rollout_that_did_not_submit_is_dropped_whatever_it_drew(planned, rollouts, tmp_path):
    def out_of_steps(records):
        for r in records:
            if r["type"] == "end":
                r["termination"], r["budget_tripped"] = "budget", "steps"

    stopped = _only(rollouts, tmp_path / "stopped", "oracle", out_of_steps)
    tally = cv.run_rollouts(stopped, NAME, tmp_path / "out", planned["root"],
                            log=lambda *_: None)["sets"][f"{NAME}-vague"]
    assert (tally["kept"], tally["dropped"]) == (0, {"not_submitted": SIZE})


def test_the_scripted_drafter_keeps_only_what_it_finished(planned, tmp_path):
    # a failing drafter: the reasons are the tally, and the kept are its 100s and no others
    root = planned["root"]
    spec = RunSpec(taskset=NAME, agents=("scripted",), levels=("vague",), tasksets_root=str(root),
                   results_root=str(tmp_path), run_id="scripted")
    rows = json.loads(json.dumps(run(spec)["groups"]))["scripted|vague|single"]
    episodes = json.loads((tmp_path / "scripted" / "episodes.json").read_text())
    clean = sorted(r["task_id"] for r in episodes if r["effective_score"] == 100.0)
    assert 0 < len(clean) < SIZE and rows["n"] == SIZE
    tally = cv.run_rollouts(tmp_path / "scripted", NAME, tmp_path / "out", root, audit=False,
                            log=lambda *_: None)["sets"][f"{NAME}-vague"]
    assert tally["kept"] == len(clean) and tally["dropped"] == {"score": SIZE - len(clean)}
    lines = (tmp_path / "out" / f"{NAME}-vague.jsonl").read_text().splitlines()
    assert sorted(json.loads(line)["header"]["task_id"] for line in lines) == clean


def test_a_rollout_is_held_to_the_document_checks_and_not_to_the_grounded_audit(planned, rollouts, tmp_path):
    from roaddraft.eval.agents.basic import _QueueAgent, calls_from_commands
    from roaddraft.tasks.reference import solution_commands
    root = planned["root"]
    twisted = [e for e in planned["manifest"]["tasks"] if e["flavour"] == "twist"]
    one = next(e for e in twisted if e["task_type"] == "curve-callouts")
    path = next((rollouts / "episodes").glob(f"{one['task_id']}.oracle.*.jsonl"))
    # the whole of rule 4 reads the scripted drafter's shown work: the plain oracle fails it
    assert cv.convert(path, NAME, audit=True, root=root).drop == "ungrounded"
    assert cv.convert(path, NAME, audit=cv.DOCUMENT, root=root).conversation is not None
    assert cv.convert(path, NAME, audit=False, root=root).conversation is not None
    lost = cv.convert(path, NAME, audit=cv.DOCUMENT)   # without the root: no such manifest here
    assert lost.drop == "error" and "FileNotFoundError" in lost.detail

    class Blind(_QueueAgent):
        """The reference's commands with the twist taken out of the lettering."""
        name = "blind"

        def reset(self, task, level, mode):
            self.queue = calls_from_commands(
                [(name, {k: v for k, v in params.items() if k != "view_rotation"})
                 for name, params in solution_commands(task)])

    spec = RunSpec(taskset=NAME, agents=("blind",), levels=("vague",), tasksets_root=str(root),
                   results_root=str(tmp_path), run_id="blind",
                   task_ids=[e["task_id"] for e in twisted])
    run(spec, agent_factory=lambda name, spec: Blind())
    episodes = json.loads((tmp_path / "blind" / "episodes.json").read_text())
    passed = sum(r["effective_score"] == 100.0 for r in episodes)
    assert passed   # the verifier lets some twist-blind lettering through at 100
    held = cv.run_rollouts(tmp_path / "blind", NAME, tmp_path / "held", root,
                           log=lambda *_: None)["sets"][f"{NAME}-vague"]
    bare = cv.run_rollouts(tmp_path / "blind", NAME, tmp_path / "bare", root, audit=False,
                           log=lambda *_: None)["sets"][f"{NAME}-vague"]
    assert bare["kept"] == passed and set(bare["dropped"]) <= {"score"}
    assert held["dropped"].get("twist_ignored", 0) > 0
    assert held["kept"] == passed - held["dropped"]["twist_ignored"]


def test_of_several_samples_of_a_task_one_conversation_is_written(planned, tmp_path):
    root = planned["root"]
    spec = RunSpec(taskset=NAME, agents=("oracle",), levels=("vague", "explicit"), samples=2, limit=3,
                   tasksets_root=str(root), results_root=str(tmp_path), run_id="k2")
    run(spec)
    summary = cv.run_rollouts(tmp_path / "k2", NAME, tmp_path / "out", root, log=lambda *_: None)
    for level in ("vague", "explicit"):   # a file a level, as the references have
        tally = summary["sets"][f"{NAME}-{level}"]
        assert (tally["episodes"], tally["kept"], tally["more_samples"]) == (6, 3, 3)
        ids = [json.loads(line)["id"] for line in
               (tmp_path / "out" / f"{NAME}-{level}.jsonl").read_text().splitlines()]
        assert len(ids) == len(set(ids)) == 3 and all(i.endswith(f".{level}") for i in ids)


def test_only_a_t2_rounds_own_run_converts_as_rollouts(planned, rollouts, tmp_path, capsys, monkeypatch):
    root = planned["root"]
    with pytest.raises(ValueError, match="T2 round's set only"):
        cv.run_rollouts(rollouts, "d1-dev", tmp_path / "out", root)
    with pytest.raises(ValueError, match="T2 round's set only"):
        cv.run_rollouts(rollouts, "d1-train", tmp_path / "out", root)
    # a run made on another set is not this manifest's
    other = tmp_path / "sets"
    renamed = {**planned["manifest"], "taskset": "d1-train-t2-x"}
    with pytest.raises(ValueError, match="shares with another set"):   # ... nor is a copy of a round
        tasksets.manifest_path("d1-train-t2-x", root).write_text(t2.text(renamed))
        try:
            cv.run_rollouts(rollouts, NAME, tmp_path / "out", root)
        finally:
            tasksets.manifest_path("d1-train-t2-x", root).unlink()
    tasksets.manifest_path("d1-train-t2-x", other).parent.mkdir(parents=True)
    tasksets.manifest_path("d1-train-t2-x", other).write_text(t2.text(renamed))
    with monkeypatch.context() as patched:   # (whatever rounds the repo holds by then)
        patched.setattr(tasksets, "t2_overlap", lambda manifest, root=None: [])
        with pytest.raises(ValueError, match=f"is a run on {NAME}, not on d1-train-t2-x"):
            cv.run_rollouts(rollouts, "d1-train-t2-x", tmp_path / "out", other)
    assert not (tmp_path / "out").exists()
    # the command line: the same refusal, and the tally of a run it takes
    assert cv.main(["rollouts", str(rollouts), "--taskset", "d1-dev", "--out", str(tmp_path / "out")]) == 2
    assert "T2 round's set only" in capsys.readouterr().err
    assert cv.main(["rollouts", str(rollouts), "--taskset", NAME, "--tasksets-root", str(root),
                    "--out", str(tmp_path / "cli"), "--jobs", "1", "--limit", "8"]) == 0
    printed = capsys.readouterr().out
    assert f"{NAME}-vague.jsonl: 4 kept of 8 episodes; dropped: score 4" in printed
    assert "4 conversations written to" in printed
