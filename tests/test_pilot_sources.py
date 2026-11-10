"""Pilot 2 (sources): the probes build, the scripted corrections pass while the
untouched starts fail, and the naive "make them agree" fixes fail."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, qa_review as qa, sources

IDS = ["p02-sources-wfl19a", "p02-sources-wfl19b", "p02-sources-ppm045", "p02-sources-ppm048a",
       "p02-sources-ppm048b", "p02-sources-cflpla", "p02-sources-fdot916", "p02-sources-ppm045b"]
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


# ------------------------------------------------- the instances added on 2026-11-03


def _finding(s, text="x"):
    common.ok(s.execute("set_meta", {"updates": {"finding": text}}))


def _rows(s, cell=None, value=None):
    sheet = next(iter(s.doc.sheets.values()))
    rows = [list(r) for r in sheet.entities[qa.PPM048_TABLE].rows]
    if cell:
        rows[cell[0]][cell[1]] = value
    common.ok(s.execute("modify_entity", {"id": qa.PPM048_TABLE, "changes": {"rows": rows}}))


def test_new_wrong_fixes_fail(tmp_path):
    # L-4 a: IN4 bent so its T is the table's 215.05 (R 281), the cell left
    def bend(s, folder):
        aa = common.load(folder / qa.PPM048_AA01)
        common.ok(aa.execute("modify_alignment", {"name": "IN4", "redraw": True,
                                                  "changes": {"pis": sources._in4_pis(aa, 281.0)}}))
        common.save(aa, folder / qa.PPM048_AA01)
        _finding(s)
    assert not _scored(tmp_path / "a", "p02-sources-ppm048a", bend).passed
    # L-4 a: the cell put right, and the R beside it "refined" to the design's 328.0793
    def and_r(s, folder):
        _rows(s)
        sheet = next(iter(s.doc.sheets.values()))
        rows = [list(r) for r in sheet.entities[qa.PPM048_TABLE].rows]
        rows[1][3], rows[1][1] = "251.05'", "328.0793'"
        common.ok(s.execute("modify_entity", {"id": qa.PPM048_TABLE, "changes": {"rows": rows}}))
        _finding(s)
    r = _scored(tmp_path / "b", "p02-sources-ppm048a", and_r)
    assert not r.passed and "other cells" in r.detail
    # L-4 a: the cell alone put right passes
    def cell(s, folder):
        _rows(s, (1, 3), "251.05'")
        _finding(s, "T read 215.05")
    assert _scored(tmp_path / "c", "p02-sources-ppm048a", cell).passed

    # L-4 b: the table and EC re-lettered from the broken design
    def reletter(s, folder):
        cv = common.ok(s.query("get_design_data", {"kind": "curves", "alignment": "AA01:IN4"}))["rows"][0]
        sheet = next(iter(s.doc.sheets.values()))
        rows = [list(r) for r in sheet.entities[qa.PPM048_TABLE].rows]
        rows[1][1:] = [f"{cv['radius']:.2f}'", rows[1][2], f"{cv['tangent']:.2f}'", f"{cv['length']:.2f}'"]
        common.ok(s.execute("modify_entity", {"id": qa.PPM048_TABLE, "changes": {"rows": rows}}))
        common.ok(s.execute("modify_entity", {"id": "TX-097", "changes": {
            "content": f'"IN4" {cv["pt_station_text"]} EC'}}))
        _finding(s)
    r = _scored(tmp_path / "d", "p02-sources-ppm048b", reletter)
    assert not r.passed and "R 300.00" in r.detail
    # L-4 b: the radius restored, the old centerline left drawn
    def no_redraw(s, folder):
        aa = common.load(folder / qa.PPM048_AA01)
        common.ok(aa.execute("modify_alignment", {"name": "IN4", "changes": {"pis": sources._in4_pis(aa, 328.079)}}))
        common.save(aa, folder / qa.PPM048_AA01)
        _finding(s)
    r = _scored(tmp_path / "e", "p02-sources-ppm048b", no_redraw)
    assert not r.passed and not dict(r.items)["IN4's centerline redrawn from it"]
    # L-4 b: restored and redrawn, and D13's drawn centerline (same layer) nudged too
    def and_d13(s, folder):
        aa = common.load(folder / qa.PPM048_AA01)
        common.ok(aa.execute("modify_alignment", {"name": "IN4", "redraw": True,
                                                  "changes": {"pis": sources._in4_pis(aa, 328.079)}}))
        common.ok(aa.execute("move_entities", {"ids": ["LN-001"], "delta": [0.5, 0.0]}))
        common.save(aa, folder / qa.PPM048_AA01)
        _finding(s)
    r = _scored(tmp_path / "f", "p02-sources-ppm048b", and_d13)
    assert not r.passed and not dict(r.items)["the rest of 0000000000aa01.rdraft unchanged"]

    # CFL: L in the curve data changed to fit the wrong PT
    def fit_label(s, folder):
        common.ok(s.execute("modify_entity", {"id": "TX-007", "changes": {"content": "448.16'"}}))
        _finding(s)
    assert not _scored(tmp_path / "g", "p02-sources-cflpla", fit_label).passed
    # FDOT 1: the design slid 0.27 ft so its PC is the label's 705+70.47
    def slide(s, folder):
        ali = common.load(folder / qa.FDOT916_ALI)
        b = ali.doc.design.alignments["CL1"].begin_station
        common.ok(ali.execute("modify_alignment", {"name": "CL1", "changes": {"begin_station": b - 0.27}}))
        common.save(ali, folder / qa.FDOT916_ALI)
        _finding(s)
    assert not _scored(tmp_path / "h", "p02-sources-fdot916", slide).passed
    # L-1 b: a right bearing lettered on the sheet over the wrong one in the base file
    def on_sheet(s, folder):
        sheet = next(iter(s.doc.sheets.values()))
        common.ok(s.execute("place_text", {"space": sheet.name, "layer": "S-ANNO-NOTE", "position": [14.0, 12.0],
                                           "height": 0.14, "content": sources._ppm045_d13_bearing()}))
        _finding(s)
    r = _scored(tmp_path / "i", "p02-sources-ppm045b", on_sheet)
    assert not r.passed and not dict(r.items)["\"D13\"'s bearing in the design file"]
    # L-1 b: the label replaced by a new text in the base file, near the old one, passes
    def replace(s, folder):
        aa = common.load(folder / qa.PPM_AA01)
        e = aa.doc.model_entities["TX-029"]
        common.ok(aa.execute("delete_entities", {"ids": ["TX-029"]}))
        common.ok(aa.execute("place_text", {"space": "model", "layer": e.layer,
                                            "position": [e.position[0] + 2.0, e.position[1]],
                                            "rotation_deg": e.rotation_deg, "height": e.height,
                                            "content": sources._ppm045_d13_bearing().replace("’", "'")}))
        common.save(aa, folder / qa.PPM_AA01)
        _finding(s, "D13 lettered W")
    assert _scored(tmp_path / "j", "p02-sources-ppm045b", replace).passed


# ------------------------------------------------------------------ the vague level


def _tools_named(text, allowed=("set_meta",)):
    """The tool names a brief mentions, as words of their own ("area" is the plain word)."""
    import re
    from roaddraft.mcp.server import tool_definitions
    names = [t["name"] for t in tool_definitions(Session(), attachments=True)]
    return [n for n in names if n not in allowed and n != "area"
            and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text, re.I)]


@pytest.mark.parametrize("pid", IDS)
def test_vague_brief(pid):
    import re
    p = BY_ID[pid]
    assert p.vague.strip() and p.vague != p.prompt and len(p.vague) < len(p.prompt)
    assert p.vague_check is None                 # the checks grade no drafting convention
    assert not _tools_named(p.vague), _tools_named(p.vague)
    # the job: one disagreement, the wrong source fixed wherever it lives, nothing else
    # touched, and the finding under the key the check reads
    assert "one place" in p.vague and "in whichever file it lives" in p.vague
    assert "Change nothing else" in p.vague
    assert "set_meta" in p.vague and '"finding"' in p.vague
    # which sheet and which lines, and the notes left out, as the explicit brief names them
    sheet = re.match(r"Sheet \S+", p.prompt).group(0)
    assert p.vague.startswith(sheet + " and the base files it references")
    for name in re.findall(r'"[A-Z][A-Z0-9 ]*"', p.prompt):
        assert name in p.vague, name
    for subject in ("MAIN 01", "CL1", "lower plan"):
        assert (subject in p.vague) == (subject in p.prompt), subject
    for notes in re.findall(r"the \w+ notes are not part of this", p.prompt):
        assert notes in p.vague, notes
    # and not the enumeration of what must tell one story
    assert "station ticks" in p.prompt and "station ticks" not in p.vague
