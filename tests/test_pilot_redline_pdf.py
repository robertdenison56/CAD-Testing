"""Pilot 18 (redline understanding): the probes build, each start carries the
marked-up page and an untouched sheet, the scripted solutions pass while the
untouched starts fail, and the naive answers named in the module docstring
fail."""
from __future__ import annotations

import shutil

import pytest

from roaddraft.api.session import Session
from roaddraft.document.entities import Text
from roaddraft.document.fileformat import read_document
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, redline_pdf as rp

IDS = ["p18-redline-pdf-ppm045", "p18-redline-pdf-wfl19", "p18-redline-pdf-cflpla",
       "p18-redline-pdf-fdot915"]
BY_ID = {p.id: p for p in rp.PROBES}
BY_INST = {i.id: i for i in rp.INSTANCES}


@pytest.fixture(scope="module")
def starts(tmp_path_factory):
    """Each start built once: the page is rendered at 200 dpi."""
    root = tmp_path_factory.mktemp("starts")
    built = {}
    for pid in IDS:
        built[pid] = fixture.start_document(root / pid, pid)
    return built


def _fresh(tmp_path, starts, pid):
    """A copy of the start to work on, and the start itself as the baseline."""
    start = starts[pid]
    work = tmp_path / "work"
    shutil.copytree(start.parent, work)
    return start, work / start.name


def _score(pid, start, mine):
    return BY_ID[pid].check(Session.load(start, out_dir=start.parent),
                            Session.load(mine, out_dir=mine.parent))


def test_probes_build():
    assert [p.id for p in rp.PROBES] == IDS
    kinds = {m.kind for i in rp.INSTANCES for m in i.markups}
    assert kinds == {"replace", "delete", "move", "add", "comment", "field"}
    for p in rp.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "redline-understanding" in p.tags and p.server_args == rp.SERVER_ARGS
        assert "view_attachment" in p.prompt and "markups" in p.prompt


@pytest.mark.parametrize("pid", IDS)
def test_the_start_is_the_page_and_an_untouched_sheet(starts, pid, tmp_path):
    inst = BY_INST[pid]
    doc = starts[pid]
    page = doc.parent / rp.MARKUPS
    assert (page / f"{inst.page}.png").stat().st_size > 10000
    assert (page / f"{inst.page}.pdf").read_bytes()[:5] == b"%PDF-"
    # the sheet file is the redraft as staged (repaired as every pilot start is,
    # repairs.py): nothing to find on it
    common.stage(tmp_path / "staged", inst.sheet_id)
    staged = tmp_path / "staged" / common.sheet_file(inst.sheet_id)
    mine, theirs = read_document(doc), read_document(staged)
    for d in (mine, theirs):
        d.pop("meta", None)
        d.pop("journal", None)
    assert mine == theirs
    # every marked text exists, and the look-alikes the notes name are distinct entities
    sheet = next(s for s in Session.load(doc, out_dir=doc.parent).doc.sheets.values()
                 if s.name == inst.sheet)
    for m in inst.markups:
        for i in m.ids:
            assert isinstance(sheet.entities[i], Text), (pid, m.kind, i)
        if m.kind == "field":
            assert m.old in str(sheet.title_block_fields[m.key])


@pytest.mark.parametrize("pid", IDS)
def test_selftest(tmp_path, starts, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", start_dir=starts[pid].parent, plots=False)
    assert ref.result.passed, ref.result.detail
    assert all(done for _item, done in ref.result.items)
    doc = starts[pid]
    untouched = probe.check(Session.load(doc, out_dir=doc.parent), Session.load(doc, out_dir=doc.parent))
    assert not untouched.passed
    # the untouched start has only the no-change items: the comment and nothing-else
    assert sum(done for _item, done in untouched.items) == 2


def _attempt(tmp_path, starts, pid, **how):
    start, mine = _fresh(tmp_path, starts, pid)
    session = Session.load(mine, out_dir=mine.parent)
    rp.make_solve(BY_INST[pid], **how)(session)
    common.save(session, mine)
    return _score(pid, start, mine)


def test_acting_on_the_blue_comment_fails(tmp_path, starts):
    r = _attempt(tmp_path, starts, "p18-redline-pdf-ppm045", wrong="comment")
    assert not r.passed
    assert "blue cloud" in r.detail
    assert not dict(r.items)["the curve table, clouded in blue, left as it was"]


def test_the_new_value_beside_the_old_fails(tmp_path, starts):
    r = _attempt(tmp_path, starts, "p18-redline-pdf-wfl19", wrong="keep_old")
    assert not r.passed
    assert "still reads" in r.detail
    assert not dict(r.items)["e = 6.0% reads e = 8.0%"]


def test_revising_the_look_alike_fails(tmp_path, starts):
    # TX-120 reads FENCE (TYPE CL-6) too; the mark is on TX-107
    r = _attempt(tmp_path, starts, "p18-redline-pdf-ppm045", wrong="twin")
    assert not r.passed
    done = dict(r.items)
    assert not done['FENCE (TYPE CL-6) at the south fence reads FENCE (TYPE CL-8)']
    assert not done["nothing unrelated changed"]


def test_lettering_the_handwriting_fails(tmp_path, starts):
    r = _attempt(tmp_path, starts, "p18-redline-pdf-fdot915", wrong="handwriting")
    assert not r.passed
    assert "handwriting" in r.detail
    assert not dict(r.items)["nothing unrelated changed"]


def test_a_mark_left_undone_fails_only_its_item(tmp_path, starts):
    r = _attempt(tmp_path, starts, "p18-redline-pdf-cflpla", skip=("field",))
    assert not r.passed
    done = dict(r.items)
    assert not done["the title block's station range reads 29+67.45 to 41+32.03"]
    assert sum(not d for d in done.values()) == 1
