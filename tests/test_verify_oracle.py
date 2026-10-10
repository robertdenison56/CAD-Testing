"""The verifier's acceptance numbers (eval plan section 3.6) on the whole-sheet
task: the reference solution scores 100 with no findings on 200 seeds over
every dial and both prompt levels, the empty baseline scores 0, reports are
byte-stable (twice, and on the replayed journal), and verify() is fast enough
to shape rewards.  Every other task type is covered in test_verify_scope."""
from __future__ import annotations

import time

import pytest

from roaddraft.api.session import Session
from roaddraft.document.document import Document
from roaddraft.tasks.generator import generate_task
from roaddraft.tasks.reference import reference_solution, session_for_task
from roaddraft.verify import VERIFIER_VERSION, verify, verify_files

DIALS = [(curves, eq) for curves in (1, 2, 3) for eq in (False, True)]


def _drafted(seed: int):
    curves, eq = DIALS[seed % len(DIALS)]
    task = generate_task(seed, curves=curves, equations=eq)
    session = session_for_task(task)
    reference_solution(task, session)
    return task, session


def test_oracle_200_seeds_all_dials_score_100_with_no_findings():
    seen = set()
    for seed in range(1, 201):
        task, session = _drafted(seed)
        seen.add((task.truth.counts["curves"], bool(task.truth.counts["equations"])))
        for level in ("explicit", "vague"):
            r = verify(session.doc, task.truth, journal=session.bus.journal, prompt_level=level)
            assert r.effective_score == 100.0 and r.rubric_score == 100.0, (seed, level)
            assert not r.hard_failed and r.design_fingerprint_ok
            assert not r.all_findings(), (seed, level, [f.to_dict() for f in r.all_findings()])
            assert r.counts["matched"] == r.counts["required_labels"] == len(task.truth.labels)
            assert r.counts["unanchored_text"] == 0
    assert seen == {(c, e) for c, e in DIALS}


def test_null_50_seeds_baseline_scores_0_with_sheet_missing():
    for seed in range(1, 51):
        curves, eq = DIALS[seed % len(DIALS)]
        task = generate_task(seed, curves=curves, equations=eq)
        doc = Document.from_dict(task.baseline)
        for level in ("explicit", "vague"):
            r = verify(doc, task.truth, prompt_level=level)
            assert r.rubric_score == 0.0 and r.effective_score == 0.0, (seed, level)
            assert r.design_fingerprint_ok and not r.hard_failed
            assert "sheet_missing" in {f.code for f in r.check("D1-00").findings}
            assert all(c.credit == 0.0 for c in r.checks)


def test_determinism_20_seeds_twice_and_on_the_replayed_journal(tmp_path):
    for seed in range(1, 21):
        task, session = _drafted(seed)
        first = verify(session.doc, task.truth).to_json()
        assert verify(session.doc, task.truth).to_json() == first
        path = tmp_path / f"{seed}.journal.jsonl"
        assert session.query("save_journal", {"path": str(path)})["ok"]
        replayed = Session.replay_journal(path)
        assert verify(replayed.doc, task.truth).to_json() == first
        assert '"timing_ms"' not in first


def test_verify_does_not_modify_the_document():
    task, session = _drafted(7)
    before = session.doc.to_dict()
    verify(session.doc, task.truth, journal=session.bus.journal, prompt_level="vague")
    assert session.doc.to_dict() == before


def test_speed_p95_under_50_ms_on_three_curves_with_an_equation():
    times = []
    for seed in range(1, 41):
        task = generate_task(seed, curves=3, equations=True)
        session = session_for_task(task)
        reference_solution(task, session)
        for _ in range(3):
            t0 = time.perf_counter()
            verify(session.doc, task.truth)
            times.append((time.perf_counter() - t0) * 1000.0)
    times.sort()
    assert times[int(0.95 * len(times))] < 50.0, times[-10:]


def test_verify_files_on_saved_task_outputs(tmp_path):
    from roaddraft.tasks.__main__ import write_task
    task = generate_task(42, curves=2, equations=True)
    out = write_task(task, tmp_path, render=False)
    p = out["paths"]
    r = verify_files(p["document"], p["truth"], p["journal"])
    assert r.effective_score == 100.0 and r.verifier_version == VERIFIER_VERSION
    assert r.audit["commands"] == out["commands"] and r.audit["design_commands"] == 0
    assert r.audit["anchor_edits"] == 0 and r.audit["raw_text"] == 0


@pytest.mark.parametrize("level", ["explicit", "vague"])
def test_unknown_level_is_refused(level):
    task, session = _drafted(3)
    verify(session.doc, task.truth, prompt_level=level)
    with pytest.raises(ValueError, match="prompt level"):
        verify(session.doc, task.truth, prompt_level="chatty")
