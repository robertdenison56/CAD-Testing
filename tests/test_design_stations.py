"""WP1 tests: design/stations.py on alignment A.

A: begin 1000, length 1518.879, one equation raw 2000 / back 2000 / ahead 2500
(a 500-ft gap).  The overlap variant uses ahead 1800.
"""
from __future__ import annotations

import pytest

from roaddraft.design.errors import DesignError
from roaddraft.design.stations import (
    STATION_EPS,
    Region,
    StationEquation,
    StationSystem,
    build_equations,
    equation_label,
)

BEGIN = 1000.0
LENGTH = 1518.879


@pytest.fixture
def gap():
    return StationSystem(BEGIN, LENGTH, [StationEquation(2000.0, 2000.0, 2500.0)])


@pytest.fixture
def overlap():
    return StationSystem(BEGIN, LENGTH, [StationEquation(2000.0, 2000.0, 1800.0)])


@pytest.fixture
def plain():
    return StationSystem(BEGIN, LENGTH, [])


def test_display_1500_region1(gap):
    disp, region = gap.to_display(1500)
    assert disp == pytest.approx(1500, abs=1e-9)
    assert region == 1


def test_display_2000_is_2500_region2(gap):
    assert gap.to_display(2000) == (pytest.approx(2500, abs=1e-9), 2)
    # just before the equation point still reads in region 1
    disp, region = gap.to_display(2000 - 1e-3)
    assert region == 1
    assert disp == pytest.approx(1999.999, abs=1e-9)


def test_display_2300_is_2800(gap):
    assert gap.to_display(2300) == (pytest.approx(2800, abs=1e-9), 2)


def test_format_2300_28_00_00(gap):
    assert gap.format(2300) == "28+00.00"
    assert gap.format(1500) == "15+00.00"
    assert gap.format(2300, decimals=1) == "28+00.0"


def test_to_raw_2800_is_2300(gap):
    assert gap.to_raw(2800) == pytest.approx(2300, abs=1e-9)
    assert gap.to_raw(1500) == pytest.approx(1500, abs=1e-9)
    assert gap.to_raw(2500) == pytest.approx(2000, abs=1e-9)  # AH reading at the equation point


def test_parse_28_00_is_2300(gap):
    assert gap.parse("28+00") == pytest.approx(2300, abs=1e-9)
    assert gap.parse("28+00.00") == pytest.approx(2300, abs=1e-9)
    assert gap.parse(2800) == pytest.approx(2300, abs=1e-9)
    assert gap.parse(2800.0) == pytest.approx(2300, abs=1e-9)
    with pytest.raises(DesignError):
        gap.parse("abc")


def test_gap_2200_raises(gap):
    with pytest.raises(DesignError) as ei:
        gap.to_raw(2200)
    assert str(ei.value) == ("station 22+00.00 does not exist on this alignment "
                             "(gap between 20+00.00 BK and 25+00.00 AH)")
    with pytest.raises(DesignError):
        gap.to_raw(2000)  # the BK reading itself is not a display station (equation reads AHEAD)


def test_overlap_1800_ambiguous_1900_regions_1_2(overlap):
    with pytest.raises(DesignError) as ei:
        overlap.to_raw(1900)
    assert str(ei.value) == "station 19+00.00 occurs in regions 1 and 2; pass region="
    assert ei.value.hint.startswith("regions: 1 = 10+00.00..20+00.00, 2 = 18+00.00..")


def test_overlap_region2_1900_is_2100(overlap):
    assert overlap.to_raw(1900, region=2) == pytest.approx(2100, abs=1e-9)
    assert overlap.to_raw(1900, region=1) == pytest.approx(1900, abs=1e-9)
    assert overlap.parse("19+00", region=2) == pytest.approx(2100, abs=1e-9)
    with pytest.raises(DesignError):
        overlap.to_raw(1900, region=3)


def test_bad_back_2200_raises():
    items = [{"back": 1500, "ahead": 1500}, {"raw_station": 2000, "back": 2200, "ahead": 2500}]
    with pytest.raises(DesignError) as ei:
        build_equations(BEGIN, LENGTH, items)
    assert str(ei.value) == ("equation 2: back station 22+00.00 does not match 20+00.00 "
                             "computed from the preceding equations")
    assert ei.value.hint == "back = the station reading just before the equation point"


def test_build_equations_derives_raw_and_accepts_strings():
    eqs = build_equations(BEGIN, LENGTH, [{"back": "20+00", "ahead": "25+00"}])
    assert eqs == [StationEquation(2000.0, 2000.0, 2500.0)]
    # second equation: back is read in the shifted region -> raw derived through eq 1
    eqs = build_equations(BEGIN, LENGTH, [{"back": 1500, "ahead": 1700},
                                          {"back": "24+00", "ahead": 2600}])
    assert eqs[1].raw_station == pytest.approx(2200, abs=1e-9)
    # a consistent explicit raw_station is accepted
    eqs = build_equations(BEGIN, LENGTH, [{"raw_station": 2000, "back": 2000, "ahead": 2500}])
    assert eqs[0].raw_station == 2000.0


def test_build_equations_ordering_and_range():
    with pytest.raises(DesignError):
        build_equations(BEGIN, LENGTH, [{"back": 1000, "ahead": 1200}])  # at BEGIN
    with pytest.raises(DesignError):
        build_equations(BEGIN, LENGTH, [{"back": 2600, "ahead": 2700}])  # beyond END
    with pytest.raises(DesignError):
        build_equations(BEGIN, LENGTH, [{"back": 2000, "ahead": 2500}, {"back": 2400, "ahead": 2450}])
    with pytest.raises(DesignError):
        build_equations(BEGIN, LENGTH, [{"back": 2000}])
    assert build_equations(BEGIN, LENGTH, []) == []


def test_raw_outside_alignment_raises(plain, gap):
    with pytest.raises(DesignError) as ei:
        plain.require_in_range(2600, "ALIGN-1")
    assert str(ei.value) == "station 26+00.00 is outside ALIGN-1 (10+00.00 to 25+18.88)"
    with pytest.raises(DesignError):
        plain.require_in_range(999, "ALIGN-1")
    plain.require_in_range(1000, "ALIGN-1")
    plain.require_in_range(BEGIN + LENGTH, "ALIGN-1")
    assert plain.in_range(BEGIN + LENGTH + STATION_EPS / 2)
    assert not plain.in_range(BEGIN + LENGTH + 1e-3)
    with pytest.raises(DesignError) as ei:
        gap.to_raw(3100)
    assert "31+00.00" in str(ei.value)


def test_equation_label_STA_20_BK_25_AH():
    assert equation_label(StationEquation(2000.0, 2000.0, 2500.0)) == "STA 20+00.00 BK = STA 25+00.00 AH"
    assert equation_label(StationEquation(2000.0, 2000.0, 2500.0), decimals=1) == "STA 20+00.0 BK = STA 25+00.0 AH"


def test_end_text_30_18_88(gap, plain):
    assert gap.end_text() == "30+18.88"
    assert gap.format(gap.end_station_raw) == "30+18.88"
    assert plain.end_text() == "25+18.88"
    assert gap.begin_text() == "10+00.00"


def test_regions_shape(gap):
    regions = gap.regions()
    assert [r.index for r in regions] == [1, 2]
    assert regions[0] == Region(1, 1000.0, 2000.0, 1000.0, 2000.0, 0.0)
    assert regions[1].raw_start == 2000.0
    assert regions[1].raw_end == pytest.approx(BEGIN + LENGTH)
    assert regions[1].display_start == 2500.0
    assert regions[1].display_end == pytest.approx(3018.879)
    assert regions[1].shift == 500.0
    assert gap.region_of_raw(1999.9) == 1 and gap.region_of_raw(2000) == 2
    assert gap.region_of_raw(BEGIN + LENGTH) == 2


def test_equation_dict_round_trip():
    eq = StationEquation(2000.0, 2000.0, 2500.0)
    assert eq.to_dict() == {"raw_station": 2000.0, "back": 2000.0, "ahead": 2500.0}
    assert StationEquation.from_dict(eq.to_dict()) == eq
    with pytest.raises(DesignError):
        StationEquation.from_dict({"back": 1})
