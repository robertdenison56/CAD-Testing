"""The reference solutions, kept as finished RoadDraft projects.

A probe's scripted solution used to live in memory and in the PDFs printed
from it. ``roaddraft.probes.reference`` keeps it as the project the probe
starts from, finished: the completed document under the name the agent is
handed it, its journal, a PDF and a DXF. These tests hold that the kept
document is the work (read back from disk, it passes the check the untouched
start fails), that the journal rebuilds it, and that the tracked set under
benchmarks/probe_references covers every probe and still passes.
"""
from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference, tasks
from roaddraft.probes.__main__ import main

TRACKED = Path(__file__).resolve().parents[1] / "benchmarks" / "probe_references"
REGENERATE = "python -m roaddraft.probes reference --out benchmarks/probe_references"


def test_start_names_the_document_each_start_hands_over(tmp_path, l2_build):
    for start, name in fixture.START.items():
        if start == "l2":
            assert (l2_build / name).is_file()
        else:
            assert fixture.start_document(tmp_path / start, start).name == name


def test_a_reference_is_the_finished_project_scored_from_disk(tmp_path, monkeypatch):
    probe = tasks.get("curve-data")
    folder = tmp_path / probe.id
    ref = reference.write(probe, folder)
    assert ref.result.passed, ref.result.detail
    assert sorted(p.name for p in folder.iterdir()) == [
        "SR-100.model.rdoc.json", "SR-100.sheets.jsonl", "SR-100.sheets.rdoc.json",
        "curve-data.dxf", "curve-data.pdf", "reference.json"]
    # the work is in the file: a fresh start's check passes it and fails the start itself
    base = Session.load(fixture.start_document(tmp_path / "fresh", probe.start),
                        out_dir=tmp_path)
    assert probe.check(base, Session.load(ref.document, out_dir=tmp_path)).passed
    assert not probe.check(base, base).passed
    # the journal is the start and every command the solution ran: it rebuilds the
    # document from any folder, reading the design through the reference beside it
    monkeypatch.chdir(tmp_path)
    replayed = Session.replay_journal(ref.journal)
    assert replayed.doc.to_dict() == Session.load(ref.document).doc.to_dict()
    record = json.loads((folder / reference.RECORD).read_text())
    assert record["passed"] and record["document"] == "SR-100.sheets.rdoc.json"
    assert record["references"] == {"DESIGN": "SR-100.model.rdoc.json"}
    assert record["prompt"] == probe.prompt
    # and the DXF opens as CAD: a layout per sheet, the curve table on C-102
    dxf = ezdxf.readfile(ref.dxf)
    assert {"C-101", "C-102", "C-103"} <= set(dxf.layout_names())
    lettered = [e.dxf.text for e in dxf.layouts.get("C-102") if e.dxftype() == "TEXT"]
    assert "CURVE DATA" in lettered


def test_a_drafting_reference_plots_model_space(tmp_path):
    probe = tasks.get("draft-tangent-ne")
    ref = reference.write(probe, tmp_path / probe.id)
    assert ref.result.passed, ref.result.detail
    assert ref.document.name == fixture.START["blank"] and ref.pdf.is_file()
    assert json.loads((tmp_path / probe.id / reference.RECORD).read_text())["references"] == {}


def test_the_cli_keeps_references_and_indexes_them(tmp_path, capsys):
    assert main(["reference", "line-data", "draft-building", "--out", str(tmp_path)]) == 0
    assert "2/2 references pass" in capsys.readouterr().out
    index = (tmp_path / "README.md").read_text()
    assert "[SR-100.sheets.rdoc.json](line-data/SR-100.sheets.rdoc.json)" in index
    assert "| draft-building |" in index and "2 of 2 pass" in index
    # a second run replaces its own folders, and the index keeps every probe found
    assert main(["reference", "line-data", "--no-plots", "--out", str(tmp_path)]) == 0
    assert not (tmp_path / "line-data" / "line-data.pdf").exists()
    assert "| draft-building |" in (tmp_path / "README.md").read_text()
    # but it will not replace a folder it did not write
    (tmp_path / "curve-data").mkdir()
    (tmp_path / "curve-data" / "mine.txt").write_text("not a reference")
    assert main(["reference", "curve-data", "--out", str(tmp_path)]) == 2
    assert (tmp_path / "curve-data" / "mine.txt").is_file()
    assert main(["reference", "no-such-probe", "--out", str(tmp_path)]) == 2


#: what each probe that asks for more than one thing asks for, item by item:
#: scope completion counts against these
ITEMS_ASKED = {
    "both-edges-c101": 2, "title-blocks": 3, "draft-tangent-ne": 2, "draft-pi-curve": 2,
    "draft-bearing-distance": 2, "draft-edges-shoulders": 4, "draft-turn-lane": 3,
    "draft-cul-de-sac": 4, "draft-roadway": 7, "sheet-set-callouts": 18, "station-callouts": 15,
    "clean-callouts": 3, "draft-intersection-corner": 3, "draft-fix-the-drawing": 3,
    "draft-roadway-sheets": 9, "line-data": 3, "curve-points": 4, "curve-data": 7,
    "stationing": 16, "width-dims": 4, "row-data": 14, "equation-data": 3,
    "qa-alignment-data": 5, "l2-match-lines": 2, "l2-alignment-data": 12,
}


def test_the_tracked_references_cover_every_probe_and_still_pass(tmp_path, l2_build):
    asked = {}
    for probe in tasks.PROBES:
        folder = TRACKED / probe.id
        assert (folder / reference.RECORD).is_file(), f"no reference for {probe.id}: {REGENERATE}"
        record = json.loads((folder / reference.RECORD).read_text())
        if probe.start == "l2":
            base = Session.load(l2_build / fixture.L2_SHEET_FILE, out_dir=tmp_path)
        else:
            base = Session.load(fixture.start_document(tmp_path / probe.id, probe.start),
                                out_dir=tmp_path)
        result = probe.check(base, Session.load(folder / record["document"], out_dir=tmp_path))
        assert result.passed, f"{probe.id}: {result.detail} -- {REGENERATE}"
        # the reference does every item asked, and the untouched start none of them
        done, asked[probe.id] = result.scope()
        assert done == asked[probe.id], f"{probe.id} passes missing {result.items}"
        untouched = probe.check(base, base)
        assert untouched.scope() == (0, asked[probe.id]), f"{probe.id}'s start does {untouched.items}"
        for kept in ("journal", "pdf", "dxf"):
            assert (folder / record[kept]).is_file(), f"{probe.id} has no {kept}: {REGENERATE}"
        for name, path in record["references"].items():
            assert (folder / path).is_file(), f"{probe.id}: reference {name} is not beside it"
    assert {pid: n for pid, n in asked.items() if n > 1} == ITEMS_ASKED


def _edits_its_base_file(session: Session) -> None:
    """A solution that saves a change over the referenced design file, as a
    pilot that edits a base drawing through open_document does."""
    base_path = session.doc._path.parent / fixture.MODEL_FILE
    base = Session.load(base_path, out_dir=base_path.parent)
    assert base.execute("draw_line", {"space": "model", "start": [0, 0], "end": [10, 0]})["ok"]
    assert base.query("save_document", {"path": str(base_path)})["ok"]
    assert session.execute("create_layer", {"name": "SOLVED"})["ok"]


def _referenced_count(session: Session) -> int:
    return session.query("get_model_state", {"include_references": True})["count"]


def test_the_baseline_is_the_start_even_when_the_solve_edits_a_base_file(tmp_path):
    """The baseline loaded its references lazily, from the folder the solve
    edits, so it showed the edited base file instead of the start (pilot work,
    2026-10-19). It now reads a copy of the start, with or without start_dir."""
    from roaddraft.probes.base import Probe, Result

    def check(baseline: Session, finished: Session) -> Result:
        before, after = _referenced_count(baseline), _referenced_count(finished)
        return Result(after == before + 1, f"{before} -> {after}")

    probe = Probe(id="edits-base", prompt="draw a line in the design file", check=check,
                  solve=_edits_its_base_file)
    ref = reference.write(probe, tmp_path / "built", plots=False)
    assert ref.result.passed, ref.result.detail
    start_dir = tmp_path / "start"
    fixture.start_document(start_dir, probe.start)
    ref = reference.write(probe, tmp_path / "copied", start_dir=start_dir, plots=False)
    assert ref.result.passed, ref.result.detail
    # the start the folder was copied from is untouched, and no copy is left behind
    start = Session.load(start_dir / fixture.SHEET_FILE, out_dir=tmp_path)
    assert _referenced_count(start) + 1 == _referenced_count(
        Session.load(ref.document, out_dir=tmp_path))
    assert sorted(p.name for p in (tmp_path / "copied").iterdir()) == [
        "SR-100.model.jsonl", "SR-100.model.rdoc.json", "SR-100.sheets.jsonl",
        "SR-100.sheets.rdoc.json", "reference.json"]


def test_a_base_file_the_solution_edits_keeps_its_journal_beside_it(tmp_path):
    """The journal held only the handed document's commands, so a design
    changed in its base file left no record of how (pilot work, 2026-10-19).
    Each file the solution saves now has its journal beside it, and it
    rebuilds the file as saved."""
    from roaddraft.probes.base import Probe, Result

    probe = Probe(id="edits-base", prompt="draw a line in the design file",
                  check=lambda base, done: Result(True, "kept"), solve=_edits_its_base_file)
    folder = tmp_path / "built"
    ref = reference.write(probe, folder, plots=False)
    base_journal = folder / "SR-100.model.jsonl"
    assert ref.base_journals == [base_journal.resolve()]
    record = json.loads((folder / reference.RECORD).read_text())
    assert record["base_journals"] == ["SR-100.model.jsonl"]
    replayed = Session.replay_journal(base_journal)
    saved = Session.load(folder / fixture.MODEL_FILE)
    assert replayed.doc.to_dict() == saved.doc.to_dict()
    assert [e["name"] for e in replayed.bus.journal] == ["draw_line"]
    # a solution that edits only the handed document records no base journal
    plain = reference.write(tasks.get("line-data"), tmp_path / "plain", plots=False)
    assert plain.base_journals == []
    assert "base_journals" not in json.loads((tmp_path / "plain" / reference.RECORD).read_text())


def test_journals_beside_saves_is_only_on_inside_its_block(tmp_path):
    from roaddraft.api.session import journals_beside_saves

    s = Session(project_name="j", out_dir=tmp_path)
    s.execute("create_layer", {"name": "A"})
    s.query("save_document", {"path": str(tmp_path / "outside.rdraft")})
    assert not (tmp_path / "outside.jsonl").exists()
    with journals_beside_saves() as written:
        s.query("save_document", {"path": str(tmp_path / "inside.rdraft")})
        s.query("save_document", {"path": str(tmp_path / "inside.rdraft")})
    assert written == [(tmp_path / "inside.jsonl").resolve()]
    assert Session.replay_journal(tmp_path / "inside.jsonl").doc.to_dict() == s.doc.to_dict()
    s.query("save_document", {"path": str(tmp_path / "after.rdraft")})
    assert not (tmp_path / "after.jsonl").exists()
