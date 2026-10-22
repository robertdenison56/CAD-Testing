"""Pilot 2 (sources): the probes build, the scripted corrections pass while the
untouched starts fail, and the naive "make them agree" fixes fail."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, qa_review as qa, sources

IDS = ["p02-sources-wfl19a", "p02-sources-wfl19b", "p02-sources-ppm045"]
BY_ID = {p.id: p for p in sources.PROBES}


def test_probes_build():
    assert [p.id for p in sources.PROBES] == IDS
    for p in sources.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "finding" in p.prompt and "one place" in p.prompt


@pytest.mark.parametrize("pid", IDS)
def test_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", probe.start)
    assert not probe.check(Session.load(doc), Session.load(doc)).passed


def _scored(tmp_path, pid, act):
    probe = BY_ID[pid]
    doc = fixture.start_document(tmp_path, probe.start)
    s = Session.load(doc, out_dir=tmp_path)
    act(s, tmp_path)
    common.save(s, doc)
    return probe.check(Session.load(doc), Session.load(doc, out_dir=tmp_path))


def test_making_them_agree_the_wrong_way_fails(tmp_path):
    # a: the design bent to the table's wrong radius
    def design_to_table(s, folder):
        ali = common.load(folder / qa.WFL_ALI)
        pis, _begin = qa.wfl19_pis(radius=sources.WFL_TABLE_R)
        common.ok(ali.execute("modify_alignment", {"name": qa.WFL_ALIGN, "redraw": True,
                                                   "changes": {"pis": pis}}))
        common.save(ali, folder / qa.WFL_ALI)
        common.ok(s.execute("set_meta", {"updates": {"finding": "design R did not match the table"}}))
    assert not _scored(tmp_path / "a", "p02-sources-wfl19a", design_to_table).passed

    # b: the sheet re-lettered from the broken design
    def reletter(s, folder):
        cv = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "ALI:MAIN 01"}))["rows"][0]
        for eid, text in (("TX-042", f"R = {cv['radius']:.2f}'"), ("TX-040", f"T = {cv['tangent']:.2f}'"),
                          ("TX-039", f"L = {cv['length']:.2f}'"), ("TX-051", f"PT {cv['pt_station_text']}")):
            common.ok(s.execute("modify_entity", {"id": eid, "changes": {"content": text}}))
        common.ok(s.execute("set_meta", {"updates": {"finding": "the curve data did not match the design"}}))
    r = _scored(tmp_path / "b", "p02-sources-wfl19b", reletter)
    assert not r.passed and "R 680.00" in r.detail

    # b: the radius restored but the old centerline left drawn
    def no_redraw(s, folder):
        ali = common.load(folder / qa.WFL_ALI)
        pis, _begin = qa.wfl19_pis()
        common.ok(ali.execute("modify_alignment", {"name": qa.WFL_ALIGN, "changes": {"pis": pis}}))
        common.save(ali, folder / qa.WFL_ALI)
        common.ok(s.execute("set_meta", {"updates": {"finding": "R was 680"}}))
    r = _scored(tmp_path / "c", "p02-sources-wfl19b", no_redraw)
    assert not r.passed and "centerline" in r.detail

    # c: the label fixed, but the EC beside it touched too
    def and_more(s, folder):
        common.ok(s.execute("modify_entity", {"id": "TX-084", "changes": {"content": "426.42’"}}))
        common.ok(s.execute("modify_entity", {"id": "TX-126", "changes": {"content": '"TB2" 639+92.73 BC'}}))
        common.ok(s.execute("set_meta", {"updates": {"finding": "x"}}))
    assert not _scored(tmp_path / "d", "p02-sources-ppm045", and_more).passed


def test_relettering_the_label_another_way_passes(tmp_path):
    def replace(s, folder):
        sheet = next(iter(s.doc.sheets.values()))
        e = sheet.entities["TX-084"]
        common.ok(s.execute("delete_entities", {"ids": ["TX-084"]}))
        common.ok(s.execute("place_text", {"space": sheet.name, "layer": "S-ANNO-NOTE",
                                           "position": [e.position[0] + 0.05, e.position[1]],
                                           "rotation_deg": e.rotation_deg, "height": e.height,
                                           "content": "426.42'"}))
        common.ok(s.execute("set_meta", {"updates": {"finding": "TB2's length had two digits transposed"}}))
    assert _scored(tmp_path, "p02-sources-ppm045", replace).passed
