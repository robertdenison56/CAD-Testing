"""WP5 tests: adapters/landxml.py (spec section 6)."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from roaddraft.adapters.landxml import (
    LANDXML_NS, UNIT_FACTORS, LandXMLData, LandXMLError, parse_landxml, write_landxml,
)
from roaddraft.design.horizontal import PI, Alignment, CurveElement, compile_pis
from roaddraft.design.stations import StationEquation
from roaddraft.design.vertical import PVI, Profile

FIX = Path(__file__).parent / "fixtures" / "landxml"
A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]


def make_A(**kw):
    return Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                     begin_station=1000.0, **kw)


def make_P():
    return Profile(name="PROF-1", alignment="ALIGN-1",
                   pvis=[PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90)])


def near(p, q, tol=1e-5):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def test_write_A_start_text_is_northing_easting_1000_1600():
    xml = write_landxml([make_A()], [], "SR 100")
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<LandXML xmlns="' + LANDXML_NS)
    assert '<Line dir="90.000000" length="600.000000"><Start>1000.000000 1000.000000</Start>' \
           '<End>1000.000000 1600.000000</End></Line>' in xml
    assert '<Curve rot="ccw" radius="800.000000" length="418.879020" chord="414.110472" ' \
           'delta="30.000000" dirStart="90.000000" dirEnd="60.000000" tangent="214.359354" ' \
           'external="28.220944" midOrd="27.259339">' in xml
    assert '<Center>1800.000000 1600.000000</Center>' in xml
    assert '<PI>1000.000000 1814.359354</PI>' in xml
    assert 'staStart="1000.000000"' in xml and '<Project name="SR 100"/>' in xml
    assert 'date="2026-01-01" time="00:00:00"' in xml


def test_write_read_A_elements_1e5_equations_pvis():
    A = make_A(equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    xml = write_landxml([A], [make_P()], "SR 100")
    data = parse_landxml(xml)
    assert isinstance(data, LandXMLData) and data.linear_unit == "USSurveyFoot"
    assert data.to_us_ft == 1.0 and data.warnings == [] and data.skipped == []
    B = data.alignments[0]
    assert B.name == "ALIGN-1" and B.begin_station == 1000.0
    assert len(B.elements) == 3
    for x, y in zip(A.elements, B.elements):
        assert x.kind == y.kind
        assert near(x.start, y.start) and near(x.end, y.end)
        if isinstance(x, CurveElement):
            assert near(x.center, y.center)
            assert x.delta_deg == pytest.approx(y.delta_deg, abs=1e-6)
            assert y.direction == "L"
    assert [q.to_dict() for q in B.equations] == [{"raw_station": 2000.0, "back": 2000.0,
                                                   "ahead": 2500.0}]
    prof = data.profiles[0]
    assert prof.name == "PROF-1" and prof.alignment == "ALIGN-1"
    for p, q in zip(make_P().pvis, prof.pvis):
        assert p.station == pytest.approx(q.station, abs=1e-6)
        assert p.elevation == pytest.approx(q.elevation, abs=1e-6)
        assert p.length == pytest.approx(q.length, abs=1e-6)


def test_write_parse_write_byte_identical():
    A = make_A(equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    first = write_landxml([A], [make_P()], "SR 100")
    data = parse_landxml(first)
    second = write_landxml(data.alignments, data.profiles, "SR 100")
    assert first == second


def test_reverse_curve_rot_ccw_then_cw():
    pis = [PI([0.0, 0.0]), PI([600.0, 0.0], 500.0), PI([1200.0, 300.0], 500.0),
           PI([1800.0, 300.0])]
    A = Alignment(name="REV", elements=compile_pis(pis), pis=pis)
    xml = write_landxml([A], [])
    rots = re.findall(r'<Curve rot="(\w+)"', xml)
    assert rots == ["ccw", "cw"]
    back = parse_landxml(xml).alignments[0]
    assert [c.direction for c in back.curves()] == ["L", "R"]
    assert back.source == "pis" and len(back.pis) == 4


def test_metric_304_8m_line_is_999_998_ft():
    data = parse_landxml((FIX / "metric_line.xml").read_text())
    assert data.linear_unit == "meter"
    assert data.to_us_ft == pytest.approx(3937.0 / 1200.0)
    A = data.alignments[0]
    assert A.length == pytest.approx(999.998, abs=1e-3)
    assert near(A.elements[0].end, [999.998, 0.0], 1e-3)


def test_international_foot_factor_0_999998():
    assert UNIT_FACTORS["foot"] == pytest.approx(0.999998, abs=1e-6)
    xml = (FIX / "metric_line.xml").read_text().replace(
        '<Metric linearUnit="meter"', '<Imperial linearUnit="foot"')
    data = parse_landxml(xml)
    assert data.alignments[0].length == pytest.approx(304.8 * 0.999998, abs=1e-6)
    bad = xml.replace('linearUnit="foot"', 'linearUnit="furlong"')
    with pytest.raises(LandXMLError) as ei:
        parse_landxml(bad)
    assert "unsupported linearUnit 'furlong'" in str(ei.value)


def test_spiral_fixture_raises_not_supported():
    with pytest.raises(LandXMLError) as ei:
        parse_landxml((FIX / "spiral_cl.xml").read_text())
    assert str(ei.value) == ("alignment 'SP-1' contains a Spiral element; spirals are not "
                             "supported in this version")
    assert ei.value.hint


def test_gap_fixture_raises_0_050_ft():
    with pytest.raises(LandXMLError) as ei:
        parse_landxml((FIX / "gap_cl.xml").read_text())
    assert str(ei.value) == "alignment 'GAP-1': element 2 starts 0.050 ft from the end of element 1"


def test_unsym_paracurve_raises():
    xml = write_landxml([make_A()], [make_P()]).replace(
        '<ParaCurve length="400.000000">', '<UnsymParaCurve lengthIn="200" lengthOut="200">'
    ).replace("</ParaCurve>", "</UnsymParaCurve>")
    with pytest.raises(LandXMLError) as ei:
        parse_landxml(xml)
    assert "unsymmetrical/circular vertical curves are not supported" in str(ei.value)


def test_namespace_less_file_parses():
    xml = write_landxml([make_A()], [make_P()]).replace(
        f' xmlns="{LANDXML_NS}"', "")
    data = parse_landxml(xml)
    assert data.alignments[0].name == "ALIGN-1" and data.profiles[0].name == "PROF-1"


def test_demo_fixture_warnings_and_skipped():
    data = parse_landxml((FIX / "demo_cl.xml").read_text())
    A = data.alignments[0]
    assert A.description == "demo centerline" and A.begin_station == 1000.0
    assert A.length == pytest.approx(1518.879, abs=1e-3)
    assert data.warnings == ["Alignment ALIGN-1 length 1518.90 in file vs 1518.88 computed"]
    assert data.skipped == ["CgPoints", "ProfSurf", "Surfaces"]
    assert data.profiles[0].description == "finished grade"
    assert A.stations().format(2300.0) == "28+00.00"


def test_pi_recovery_sets_source_pis():
    data = parse_landxml((FIX / "demo_cl.xml").read_text())
    A = data.alignments[0]
    assert A.source == "pis" and len(A.pis) == 3
    assert near([A.pis[1].point[0], A.pis[1].point[1]], [1814.359354, 1000.0], 1e-6)
    assert A.pis[1].radius == pytest.approx(800.0)


def test_center_missing_computed_from_radius_rot():
    xml = write_landxml([make_A()], [])
    xml = re.sub(r"<Center>[^<]*</Center>", "", xml)
    data = parse_landxml(xml)
    c = data.alignments[0].curves()[0]
    assert near(c.center, [1600.0, 1800.0], 1e-4)
    assert c.delta_deg == pytest.approx(30.0, abs=1e-6)
    # PI missing -> computed from PC + T along the incoming heading
    xml2 = re.sub(r"<PI>[^<]*</PI>", "", xml)
    c2 = parse_landxml(xml2).alignments[0].curves()[0]
    assert near(c2.pi, [1814.359354, 1000.0], 1e-4)
    # neither radius nor Center is an error
    xml3 = xml.replace(' radius="800.000000"', "")
    with pytest.raises(LandXMLError):
        parse_landxml(xml3)


def test_parse_error_reports_line_and_column():
    with pytest.raises(LandXMLError) as ei:
        parse_landxml("<LandXML><Alignments><Alignment name='x'></LandXML>")
    assert str(ei.value).startswith("LandXML parse error at line 1 column ")
    with pytest.raises(LandXMLError):
        parse_landxml("<Foo/>")
    with pytest.raises(LandXMLError) as ei:
        parse_landxml(f'<LandXML xmlns="{LANDXML_NS}"><Alignments><Alignment name="E">'
                      '<CoordGeom/></Alignment></Alignments></LandXML>')
    assert "no CoordGeom geometry" in str(ei.value)


def test_duplicate_names_get_suffixes_and_top_level_profile_binds():
    xml = write_landxml([make_A()], [make_P()])
    body = xml[xml.index("<Alignments>"):xml.index("</Alignments>") + len("</Alignments>")]
    inner = body[len("<Alignments>"):-len("</Alignments>")]
    doubled = xml.replace(body, "<Alignments>" + inner + inner + "</Alignments>")
    data = parse_landxml(doubled)
    assert [a.name for a in data.alignments] == ["ALIGN-1", "ALIGN-1-2"]
    assert [p.name for p in data.profiles] == ["PROF-1", "PROF-1-2"]
    assert any("renamed" in w for w in data.warnings)
    top = xml.replace("</Alignments>", "</Alignments>"
                      '<Profiles><Profile name="TOP"><ProfAlign name="TOP-FG">'
                      "<PVI>1000 10</PVI><PVI>2000 20</PVI></ProfAlign></Profile></Profiles>")
    data = parse_landxml(top)
    assert [p.name for p in data.profiles] == ["PROF-1", "TOP-FG"]
    assert data.profiles[1].alignment == "ALIGN-1"


def test_no_forbidden_imports_in_adapters():
    root = Path(__file__).resolve().parents[1] / "src" / "roaddraft" / "adapters"
    forbidden = re.compile(r"^\s*(from|import)\s+roaddraft\.(commands|api|web|document|tasks)\b",
                           re.MULTILINE)
    for name in os.listdir(root):
        if name.endswith(".py"):
            text = (root / name).read_text()
            assert not forbidden.search(text), f"{name} imports a forbidden package"
            assert "ezdxf" not in text and "matplotlib" not in text
