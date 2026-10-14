"""The trajectory log (eval plan section 4.6): the record types, the journal
block replays to the same document, and an episode re-verifies to the same
score from its file alone."""
from __future__ import annotations

import json

from roaddraft.eval import taskset as tasksets
from roaddraft.eval.agents import OracleAgent, ScriptedAgent
from roaddraft.eval.episode import HARNESS_VERSION, EpisodeConfig, run_episode
from roaddraft.eval.trajectory import (
    episode_path, is_complete, read_episode, replay_journal, reverify,
)
from roaddraft.tasks.generator import generate_task
from roaddraft.verify import VERIFIER_VERSION, verify

DEV = tasksets.load("d1-dev")["tasks"]


def test_episode_file_has_every_record_in_order(tmp_path):
    task = tasksets.task_from_entry(DEV[2])
    r = run_episode(task, ScriptedAgent(), EpisodeConfig(run_id="t", sample=1), out_root=tmp_path)
    path = episode_path(tmp_path, task.task_id, "scripted", "neutral", "single", "explicit", 1)
    assert r.path == str(path) and path.exists() and is_complete(path)
    kinds = [json.loads(l)["type"] for l in path.read_text().splitlines()]
    assert kinds[0] == "header" and kinds[-4:] == ["journal", "verify", "audit", "end"]
    assert all(k == "turn" for k in kinds[1:-4]) and kinds.count("turn") == r.turns
    rec = read_episode(path)
    h = rec["header"]
    assert h["task_id"] == task.task_id and h["harness_version"] == HARNESS_VERSION
    assert h["verifier_version"] == VERIFIER_VERSION and h["spec_hash"] == task.brief.spec_hash
    assert h["agent"] == "scripted" and h["level"] == "explicit" and h["mode"] == "single"
    assert h["prompt_hash"].startswith("sha256:") and h["budgets"]["steps"] == 150
    assert rec["end"]["termination"] == "submit" and rec["end"]["effective_score"] == r.effective_score
    assert rec["verify"]["effective_score"] == r.effective_score
    assert "commands" in rec["audit"] or rec["audit"]  # the audit block is the verifier's


def test_journal_block_replays_to_the_same_document_and_score(tmp_path):
    task = tasksets.task_from_entry(DEV[3])
    r = run_episode(task, OracleAgent(), out_root=tmp_path)
    rec = read_episode(r.path)
    session = replay_journal(rec["journal"])
    report = verify(session.doc, task.truth, journal=session.bus.journal, prompt_level="explicit")
    assert report.to_json() == r.report.to_json()
    assert reverify(r.path).to_json() == r.report.to_json()
    assert reverify(r.path, level="vague").effective_score == 100.0


def test_replay_carries_the_task_files_for_a_reference_task(tmp_path):
    task = generate_task(5, task_type="attach-reference")
    assert task.files
    r = run_episode(task, OracleAgent(), out_root=tmp_path)
    rec = read_episode(r.path)
    assert set(rec["journal"]["files"]) == set(task.files)
    assert reverify(r.path).effective_score == 100.0


def test_incomplete_file_is_not_complete(tmp_path):
    p = tmp_path / "episodes" / "x.jsonl"
    p.parent.mkdir()
    p.write_text(json.dumps({"type": "header"}) + "\n")
    assert not is_complete(p) and not is_complete(tmp_path / "missing.jsonl")
