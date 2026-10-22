"""Pilot 14 (qa_review): the probes build, the scripted reviews pass while the
untouched starts fail, the prepared sheets agree with their designs, and the
naive reviews named in the notes fail."""
from __future__ import annotations

import pytest

from roaddraft.api.session import Session
from roaddraft.probes import fixture, reference
from roaddraft.probes.pilot import common, qa_review as qa

IDS = ["p14-qa-review-ppm045a", "p14-qa-review-ppm045b", "p14-qa-review-wfl19"]
BY_ID = {p.id: p for p in qa.PROBES}


def test_probes_build():
    assert [p.id for p in qa.PROBES] == IDS
    for p in qa.PROBES:
        assert p.prompt.strip() and p.note.strip() and p.solve and p.start in fixture.START
        assert "QA-REVIEW" in p.prompt and "NO ERRORS FOUND" in p.prompt
        # the prompt never says how many errors there are, or what kind
        assert not any(w in p.prompt.lower() for w in ("bearing", "north arrow", "upside", "six", "three"))


@pytest.mark.parametrize("pid", IDS)
def test_selftest(tmp_path, pid):
    probe = BY_ID[pid]
    ref = reference.write(probe, tmp_path / "ref", plots=False)
    assert ref.result.passed, ref.result.detail
    doc = fixture.start_document(tmp_path / "start", probe.start)
    untouched = probe.check(Session.load(doc), Session.load(doc))
    assert not untouched.passed


def test_prepared_sheets_agree_with_their_designs(tmp_path):
    # L-1: the lettering is the rebuilt design's, to the hundredth
    qa.prepare_ppm045(tmp_path / "l1")
    s = common.load(tmp_path / "l1" / qa.PPM_FILE)
    sheet = next(iter(s.doc.sheets.values()))
    aa = common.load(tmp_path / "l1" / qa.PPM_AA01)
    v = qa.ppm045_values(aa)
    assert aa.doc.model_entities["TX-036"].content == v["TB1 T-1 bearing"] == 'N 03°57’26" W'
    assert sheet.entities["TX-005"].content == v["TB1 C-1 L"]
    assert sheet.entities["TX-127"].content == f'"TB1" {v["TB1 C-1 PT"]} EC'
    tb2 = common.ok(aa.query("get_design_data", {"kind": "curves", "alignment": "TB2"}))["rows"][0]
    t1 = common.ok(aa.query("get_design_data", {"kind": "tangents", "alignment": "TB2"}))["rows"][0]
    assert tb2["bearing_out"] == t1["bearing"]          # no kink at the EC any more
    # D.10: the design is the whole curve its curve data letters
    qa.prepare_wfl19(tmp_path / "d10")
    d = common.load(tmp_path / "d10" / qa.WFL_FILE)
    cv = common.ok(d.query("get_design_data", {"kind": "curves", "alignment": "ALI:MAIN 01"}))["rows"][0]
    assert (cv["pi_station_text"], cv["pt_station_text"], f"{cv['tangent']:.2f}", f"{cv['length']:.2f}") == \
        ("149+35.83", "152+96.54", "554.92", "915.64")


def _callout(session, target, text):
    sheet = next(iter(session.doc.sheets.values()))
    if qa.QA_LAYER not in session.doc.layers:
        common.ok(session.execute("create_layer", {"name": qa.QA_LAYER}))
    common.ok(session.execute("place_callout", {"space": sheet.name, "layer": qa.QA_LAYER, "target": target,
                                                "position": [target[0] + 1.0, target[1] + 0.8],
                                                "content": text}))


def _scored(tmp_path, pid, act):
    probe = BY_ID[pid]
    doc = fixture.start_document(tmp_path, probe.start)
    s = Session.load(doc, out_dir=tmp_path)
    act(s)
    common.save(s, doc)
    return probe.check(Session.load(doc), Session.load(doc, out_dir=tmp_path))


def _targets(session, plants):
    out = []
    for p in plants:
        texts, segs = qa.plant_marks(session, p)
        out.append(texts[0].center() if texts else segs[len(segs) // 2].mid())
    return out


def test_naive_reviews_fail(tmp_path):
    # the control: one query on the unlabelled match line sinks it
    r = _scored(tmp_path / "a", "p14-qa-review-ppm045a",
                lambda s: _callout(s, [29.75, 9.0], "MATCH LINE HAS NO SHEET NUMBER"))
    assert not r.passed
    # six errors: fixing one instead of marking it fails; missing the arrow fails
    def fix(s):
        qa._modify_text(s, "TX-005", lambda t: "163.42’")
    assert not _scored(tmp_path / "b", "p14-qa-review-ppm045b", fix).passed

    def five(s):
        for p, t in zip(qa.PPM_PLANTS, _targets(s, qa.PPM_PLANTS)):
            if "north" not in p["item"]:
                _callout(s, t, "QA " + p["item"])
    r = _scored(tmp_path / "c", "p14-qa-review-ppm045b", five)
    assert not r.passed and "north arrow" in r.detail
    # all six plus one query passes; plus two queries fails
    def six_plus(n):
        def go(s):
            for p, t in zip(qa.PPM_PLANTS, _targets(s, qa.PPM_PLANTS)):
                _callout(s, t, "QA " + p["item"])
            for k in range(n):
                _callout(s, [26.0 + k, 16.0], "QA QUERY")
        return go
    assert _scored(tmp_path / "d", "p14-qa-review-ppm045b", six_plus(1)).passed
    assert not _scored(tmp_path / "e", "p14-qa-review-ppm045b", six_plus(2)).passed
    # D.10: calling it clean fails
    def clean(s):
        sheet = next(iter(s.doc.sheets.values()))
        common.ok(s.execute("create_layer", {"name": qa.QA_LAYER}))
        common.ok(s.execute("place_text", {"space": sheet.name, "layer": qa.QA_LAYER, "position": [3, 2],
                                           "height": 0.1, "content": "NO ERRORS FOUND"}))
    assert not _scored(tmp_path / "f", "p14-qa-review-wfl19", clean).passed
