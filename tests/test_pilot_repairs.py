"""The redraft's leftovers are repaired on every pilot's start (probes/pilot/repairs.py):
what GPT-6-Astra marked on the clean QA-review control on 2026-10-23."""
from __future__ import annotations

from roaddraft.api.session import Session
from roaddraft.document.entities import Line, Polyline, Table, Text
from roaddraft.probes import fixture
from roaddraft.probes.pilot import common, repairs
from roaddraft.probes.pilot.layout import STALE_TRACED


def _sheet(session: Session):
    return next(iter(session.doc.sheets.values()))


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _texts(container):
    return [e for e in container.values() if isinstance(e, Text)]


def test_l1_is_staged_without_its_stroked_labels_and_in_one_creek(tmp_path):
    files = common.stage(tmp_path, repairs.PPM045)
    s = Session.load(files[common.sheet_file(repairs.PPM045)])
    sheet = _sheet(s)
    names = [t.content for t in _texts(sheet.entities)]
    assert "Orchard Creek" in names and "d" not in names and "rcha" not in names
    assert max(t.height for t in _texts(sheet.entities)) < 0.4
    to_paper = sheet.viewports[0].transform().to_paper
    for name, layers in repairs.PPM_STROKE_LAYERS.items():
        base = Session.load(files[name])
        for e in base.doc.model_entities.values():
            if e.layer in layers and isinstance(e, (Line, Polyline)):
                pts = [to_paper(p) for p in repairs._points(e)]
                assert not any(repairs._within(pts, box) for box in repairs.PPM_STROKES.values()), e.id


def test_pd1_lettering_prints_once_and_the_notes_sit_a_line_apart(tmp_path):
    files = common.stage(tmp_path, repairs.PPM160)
    s = Session.load(files[common.sheet_file(repairs.PPM160)])
    sheet = _sheet(s)
    for eid, (text, position, height) in repairs.PPM160_TEXTS.items():
        e = sheet.entities[eid]
        assert e.content == text and e.height == height and list(e.position) == position
    assert repairs.strip_doubled_strokes(s) == []     # nothing left under a text
    box = repairs.PPM160_NOTES_BOX
    for e in sheet.entities.values():
        if not isinstance(e, Text) and repairs._within(repairs._points(e), box):
            raise AssertionError(f"{e.id} ({e.layer}) still drawn across the notes")


def test_d10_has_no_placeholders_doubled_landing_or_lettering_under_the_divider(tmp_path):
    files = common.stage(tmp_path, repairs.WFL19)
    s = Session.load(files[common.sheet_file(repairs.WFL19)])
    sheet = _sheet(s)
    assert [t.content for t in _texts(sheet.entities)].count(repairs.WFL19_DETAIL) == 2
    assert repairs.WFL19_PLACEHOLDER not in [t.content for t in _texts(sheet.entities)]
    assert repairs.WFL19_DOUBLED_LANDING[1] not in sheet.entities
    to_paper = sheet.viewports[0].transform().to_paper
    ali = Session.load(files[repairs.WFL19_ALI])
    for e in ali.doc.model_entities.values():
        if e.anchor and e.anchor.get("kind") in ("station", "tick"):
            pts = repairs._points(e) or [list(e.position)]
            assert not all(to_paper(p)[1] < repairs.WFL19_DIVIDER_Y_IN and to_paper(p)[0] < 16.3
                           for p in pts), e.id


def test_stripped_lines_leave_no_empty_bubble_rings_or_traced_callouts(tmp_path):
    """A stripped line's curve bubbles, digitised as rings of vertices, go with
    the line (tasks.real.strip_alignment, since 2026-10-31). A ring that is no
    line's bubble stays: L-7's kept CURVE DATA table has one round its header's
    "No. (X)" legend, the X lost in the redraft."""
    from roaddraft.design.horizontal import Alignment
    from roaddraft.probes.pilot.layout import _task
    from roaddraft.tasks.real import BUBBLE_REACH_IN
    for pid, start, sheet_file, sheet_id, names in (
            ("p04-crowded-ppm045", "p04-crowded-ppm045", "0000000000ea001.rdraft", "PPM-045",
             ("D13", "TB2", "TB1")),
            ("p04-crowded-ppm050", "p04-crowded-ppm050", "0000000000ea007.rdraft", "PPM-050",
             ("D13", "F3", "F6", "FR", "F2"))):
        out = tmp_path / pid
        doc = fixture.start_document(out, start)
        s = Session.load(doc, out_dir=out)
        sheet = _sheet(s)
        to_paper = sheet.viewports[0].transform().to_paper
        mids = []
        for name in names:
            align = Alignment.from_dict(_task(sheet_id, name).brief.design["alignments"][name])
            mids += [to_paper(align.point_at(c.start_dist + c.length / 2.0)) for c in align.curves()]
        for e in sheet.entities.values():
            if e.layer == "S-ANNO-TAG" and isinstance(e, Polyline) and len(e.vertices) >= 8:
                centre = [sum(v[0] for v in e.vertices) / len(e.vertices),
                          sum(v[1] for v in e.vertices) / len(e.vertices)]
                if any(_dist(centre, m) <= BUBBLE_REACH_IN for m in mids):
                    raise AssertionError(f"{pid}: bubble ring {e.id} left on the sheet")
        boxes = [b for line in STALE_TRACED.get(sheet_id, {}).values() for b, _ in line]
        for name in ("0000000000aa01.rdraft", "0000000000bb01.rdraft"):
            base = Session.load(out / name)
            for e in base.doc.model_entities.values():
                pts = [to_paper(p) for p in repairs._points(e)]
                assert not any(repairs._within(pts, b) for b in boxes), f"{pid}: {e.id} ({e.layer})"


def test_l1_redline_start_keeps_tb2s_curve_data(tmp_path):
    """The strip keeps TB2's row of the published CURVE DATA table (digitised as
    texts) and takes TB1's ring; the start numbers TB2's curve 2 in that row
    and in its ring, beside the reference's TB1 table and bubble numbered 1."""
    doc = fixture.start_document(tmp_path, "p11-station-ppm045")
    s = Session.load(doc, out_dir=tmp_path)
    sheet = _sheet(s)
    tables = [e for e in sheet.entities.values() if isinstance(e, Table)]
    assert len(tables) == 1                     # the reference's, TB1's curve
    assert [str(row[0]) for row in tables[0].rows] == ["1"]
    header = [t for t in _texts(sheet.entities) if t.content.strip().upper() == "NO."]
    assert len(header) == 1                     # the published table's No. column
    cells = [t for t in _texts(sheet.entities) if t.content.strip().isdigit()
             and abs(t.position[0] - header[0].position[0]) <= 0.6
             and 0 < header[0].position[1] - t.position[1] <= 1.0]
    assert [t.content for t in cells] == ["2"]  # TB2's kept row, renumbered
    rings = {e.id: e for e in sheet.entities.values()
             if e.layer == "S-ANNO-TAG" and isinstance(e, Polyline) and len(e.vertices) >= 8}
    assert "PL-005" not in rings                # TB1's empty ring went with the strip
    assert "PL-004" in rings                    # TB2's, numbered 2 below
    for rid, ring in rings.items():
        centre = [sum(v[0] for v in ring.vertices) / len(ring.vertices),
                  sum(v[1] for v in ring.vertices) / len(ring.vertices)]
        inside = [t.content for t in _texts(sheet.entities)
                  if abs(t.position[0] - centre[0]) <= 0.1 and abs(t.position[1] - centre[1]) <= 0.1]
        if rid == "PL-004":
            assert inside == ["2"]
        else:                                   # the kept table's "No. (X)" legend ring
            assert _dist(centre, header[0].position) <= 0.8, rid

