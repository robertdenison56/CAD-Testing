"""WP1 tests: design/labels.py on alignment A (spec section 3.6)."""
from __future__ import annotations

import math

import pytest

from roaddraft.core.geometry import ViewportTransform
from roaddraft.design.anchors import parse_anchor, resolve_anchor
from roaddraft.design.errors import DesignError
from roaddraft.design.horizontal import PI, Alignment, compile_pis
from roaddraft.design.labels import (
    CURVE_COLUMNS, DEFAULT_CURVE_COLUMNS, LABEL_KINDS, LabelSpec, TickSpec, compile_label,
    curve_table_rows, label_content, sheet_pose, stationing_plan, upright,
)
from roaddraft.design.stations import StationEquation

A_PIS = [PI([1000.0, 1000.0]), PI([1814.359354, 1000.0], 800.0), PI([2433.012702, 1357.179677])]
TOL = 1e-3


def make_A(**kw):
    return Alignment(name="ALIGN-1", elements=compile_pis(A_PIS), pis=list(A_PIS),
                     begin_station=1000.0, **kw)


@pytest.fixture
def A():
    return make_A()


def near(p, q, tol=TOL):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def label(A, anchor, kind, **kw):
    return compile_label(A, resolve_anchor(A, parse_anchor(anchor)), kind, **kw)


def _engine_upright(angle_deg):
    a = angle_deg % 360.0
    if 90.0 < a <= 270.0:
        a -= 180.0
    return ((a + 180.0) % 360.0) - 180.0


def test_upright_matches_engine_grid_0_to_360():
    for tenth in range(0, 3601):
        a = tenth / 10.0
        assert upright(a) == _engine_upright(a)
        assert -90.0 < upright(a) <= 90.0 or math.isclose(upright(a), -90.0)


def test_pc1_default_right_16_position_1600_984_valign_top(A):
    s = label(A, "PC-1", "pc")
    assert isinstance(s, LabelSpec)
    assert s.content == "BC 16+00.00" and s.content_auto
    assert near(s.position, [1600.0, 984.0]) and s.rotation_deg == 0.0
    assert s.halign == "center" and s.valign == "top" and s.side == "right"
    rec = s.anchor_record()
    assert rec["alignment"] == "ALIGN-1" and rec["ref"] == "PC-1" and rec["kind"] == "pc"
    assert rec["station"] == pytest.approx(1600.0, abs=TOL) and rec["offset"] == 0.0
    assert rec["side"] == "right" and rec["label_offset"] == 16.0
    assert rec["rotation"] == "along" and rec["viewport"] is None and rec["content_auto"] is True
    assert s.anchor_record("VP-001")["viewport"] == "VP-001"


def test_station_1300_left_1016_valign_bottom(A):
    s = label(A, "13+00", "station")
    assert s.content == "13+00.00"
    assert near(s.position, [1300.0, 1016.0]) and s.valign == "bottom" and s.side == "left"


def test_bearing_T2_N60E_rotation_30_position_2208_506_1246_036(A):
    s = label(A, "T-2", "bearing")
    assert s.content == 'N 60°00\'00" E'
    assert near(s.position, [2208.506, 1246.036])
    assert s.rotation_deg == pytest.approx(30.0, abs=1e-6)
    assert label(A, "T-1", "bearing").content == 'N 90°00\'00" E'


def test_perpendicular_18_00_reads_bottom_to_top_at_104_324(A):
    # square to the line at 14.324 deg, reading bottom to top (PPM 2-1.2): not
    # folded to -75.676, which reads top to bottom
    s = label(A, "18+00", "station", rotation="perpendicular")
    assert s.rotation_deg == pytest.approx(104.324, abs=1e-3)
    assert label(A, "18+00", "station", rotation="horizontal").rotation_deg == 0.0
    with pytest.raises(DesignError):
        label(A, "18+00", "station", rotation="diagonal")


def test_bearing_on_MC1_raises(A):
    with pytest.raises(DesignError) as ei:
        label(A, "MC-1", "bearing")
    assert str(ei.value) == "bearing labels go on tangents; MC-1 is on curve C-1 (use T-1 or T-2)"
    # a station anchor on a tangent is fine
    assert label(A, "12+00", "bearing").content == 'N 90°00\'00" E'


def test_kind_pc_anchor_PT1_raises(A):
    with pytest.raises(DesignError):
        label(A, "PT-1", "pc")
    with pytest.raises(DesignError):
        label(A, "PC-1", "pt")
    with pytest.raises(DesignError):
        label(A, "T-1", "mc")
    with pytest.raises(DesignError):
        label(A, "PC-1", "pcc")  # tangent-to-curve junction, not curve-to-curve
    with pytest.raises(DesignError):
        label(A, "PC-1", "bogus")
    assert label(A, "PT-1", "pt").content == "EC 20+18.88"
    assert label(A, "PI-1", "pi").content == "PI 18+14.36"
    assert label(A, "BEGIN", "begin").content == "BEGIN STA 10+00.00"
    assert label(A, "END", "end").content == "END STA 25+18.88"
    assert label(A, "MC-1", "mc").content == "C-1"


def test_custom_requires_content(A):
    with pytest.raises(DesignError) as ei:
        label(A, "PC-1", "custom")
    assert "kind custom requires content" in str(ei.value)
    s = label(A, "PC-1", "custom", content="MATCH LINE", side="left")
    assert s.content == "MATCH LINE" and not s.content_auto and s.valign == "bottom"
    s = label(A, "PC-1", "pc", content="PC 16+00")
    assert s.content == "PC 16+00" and s.content_auto is False


def test_curve_data_multiline_C1_R800_T214_36_L418_88(A):
    s = label(A, "MC-1", "curve_data")
    assert s.content == "C-1\nΔ = 30°00'00\"\nR = 800.00'\nT = 214.36'\nL = 418.88'"
    assert label(A, "PI-1", "curve_data").content == s.content
    with pytest.raises(DesignError):
        label(A, "T-1", "curve_data")


def test_equation_label_content_and_anchor():
    A = make_A(equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    s = label(A, "EQ-1", "equation")
    assert s.content == "STA 20+00.00 BK = STA 25+00.00 AH" and s.side == "right"
    assert s.station == pytest.approx(2000.0)


def test_sheet_pose_pc1_15_0_8_38_and_twist20(A):
    s = label(A, "PC-1", "pc")
    t = ViewportTransform([17.0, 11.7], [1700.0, 1150.0], 50.0, 0.0)
    pos, rot = sheet_pose(s, t, 0.0, 0.32)
    assert near(pos, [15.0, 8.38], 1e-6) and rot == 0.0
    t20 = ViewportTransform([17.0, 11.7], [1700.0, 1150.0], 50.0, 20.0)
    pos, rot = sheet_pose(s, t20, 20.0, 0.32)
    q = t20.to_paper([1600.0, 1000.0])
    expect = [q[0] + 0.32 * math.cos(math.radians(-70.0)),
              q[1] + 0.32 * math.sin(math.radians(-70.0))]
    assert near(pos, expect, 1e-6) and rot == pytest.approx(20.0)


def test_curve_table_default_row_C1_18_14_36_30_LT_800_214_36_418_88_414_11_N75E(A):
    headers, rows, widths = curve_table_rows(A)
    assert headers == ["CURVE", "PI STA", "DELTA", "DIR", "R", "T", "L", "C", "CH BRG"]
    assert rows == [["C-1", "18+14.36", "30°00'00\"", "LT", "800.00'", "214.36'", "418.88'",
                     "414.11'", "N 75°00'00\" E"]]
    assert widths == [0.8, 1.1, 1.3, 0.6, 1.0, 1.0, 1.0, 1.0, 1.6]
    assert list(CURVE_COLUMNS) == ["curve", "pi_sta", "pc_sta", "pt_sta", "delta", "direction",
                                   "radius", "tangent", "length", "external", "mid_ordinate",
                                   "chord", "chord_bearing"]
    headers, rows, widths = curve_table_rows(A, ["curve", "pc_sta", "pt_sta", "external",
                                                 "mid_ordinate"])
    assert rows == [["C-1", "16+00.00", "20+18.88", "28.22'", "27.26'"]]
    with pytest.raises(DesignError) as ei:
        curve_table_rows(A, ["curve", "bogus"])
    assert "unknown curve table column 'bogus'" in str(ei.value) and "chord_bearing" in ei.value.hint
    with pytest.raises(DesignError):
        curve_table_rows(A, curves=[2])
    assert DEFAULT_CURVE_COLUMNS[0] == "curve"


def test_stationing_plan_A_16_ticks_BC_EC(A):
    plan = stationing_plan(A)
    assert plan.n_ticks == 16 and plan.n_junctions == 2 and plan.n_equations == 0
    assert plan.begin_text == "10+00.00" and plan.end_text == "25+18.88"
    ticks = plan.ticks()
    assert len(ticks) == 16 and isinstance(ticks[0], TickSpec)
    assert ticks[0].station_text == "10+00.00" and ticks[-1].station_text == "25+00.00"
    # interleaved: tick, label, tick, label ...
    kinds = [type(i).__name__ for i in plan.items[:4]]
    assert kinds == ["TickSpec", "LabelSpec", "TickSpec", "LabelSpec"]
    first = ticks[0]
    assert near(first.start, [1000.0, 990.0]) and near(first.end, [1000.0, 1010.0])
    assert first.anchor_record("ALIGN-1") == {"alignment": "ALIGN-1", "ref": "10+00.00",
                                             "kind": "tick", "station": 1000.0, "offset": 0.0}
    labels = plan.labels()
    station_labels = [l for l in labels if l.kind == "station"]
    assert len(station_labels) == 16
    assert near(station_labels[3].position, [1300.0, 1016.0])
    junctions = [l for l in labels if l.kind in ("pc", "pt")]
    assert [l.content for l in junctions] == ["BC 16+00.00", "EC 20+18.88"]
    assert [l.ref for l in junctions] == ["PC-1", "PT-1"]
    assert near(junctions[0].position, [1600.0, 984.0]) and junctions[0].valign == "top"
    for l in labels:
        assert -90.0 < l.rotation_deg <= 90.0


def test_stationing_plan_equation_2000_2500_labels_19_25_30_not_20_24():
    A = make_A(equations=[StationEquation(2000.0, 2000.0, 2500.0)])
    plan = stationing_plan(A)
    texts = [l.content for l in plan.labels() if l.kind == "station"]
    assert plan.n_ticks == 16 and len(texts) == 16
    assert "19+00.00" in texts and "25+00.00" in texts and "30+00.00" in texts
    assert "20+00.00" not in texts and "24+00.00" not in texts
    assert plan.end_text == "30+18.88"
    eq = [l for l in plan.labels() if l.kind == "equation"]
    assert len(eq) == 1 and eq[0].ref == "EQ-1"
    assert eq[0].content == "STA 20+00.00 BK = STA 25+00.00 AH"
    assert eq[0].label_offset == 24.0 and eq[0].side == "right"
    # region-2 ticks carry region 2 and raw stations
    t25 = next(t for t in plan.ticks() if t.station_text == "25+00.00")
    assert t25.region == 2 and t25.station == pytest.approx(2000.0)
    assert plan.items[-1] is eq[0]  # equation labels come last


def test_stationing_plan_range_12_00_18_00_7_ticks(A):
    plan = stationing_plan(A, station_range=(1200.0, 1800.0))
    assert plan.n_ticks == 7
    assert [t.station_text for t in plan.ticks()][0] == "12+00.00"
    assert [t.station_text for t in plan.ticks()][-1] == "18+00.00"
    assert plan.n_junctions == 1  # only the PC at 16+00 is inside the range
    plan50 = stationing_plan(A, interval=50.0, include_pc_pt=False)
    assert plan50.n_ticks == 31 and plan50.n_junctions == 0


def test_label_kinds_list_and_content_helper(A):
    assert len(LABEL_KINDS) == 13 and "curve_data" in LABEL_KINDS
    ap = resolve_anchor(A, parse_anchor("PT-1"))
    assert label_content(A, ap, "station") == "20+18.88"
