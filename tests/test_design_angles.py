"""WP1 tests: design/angles.py (pure angle, bearing and DMS helpers)."""
from __future__ import annotations

import math

import pytest

from roaddraft.design.angles import (
    azimuth_of,
    azimuth_to_direction,
    direction_of,
    direction_to_azimuth,
    dms_parts,
    format_azimuth,
    format_bearing,
    format_dms,
    left_normal,
    norm_deg,
    parse_bearing,
    parse_dms,
    right_normal,
    signed_delta_deg,
    unit_vector,
)


def test_bearing_45_30_15_E():
    assert format_bearing(45.5041667) == 'N 45°30\'15" E'


def test_bearing_due_east_N90E():
    assert format_bearing(90) == 'N 90°00\'00" E'


def test_bearing_due_north_N00E():
    assert format_bearing(0) == 'N 00°00\'00" E'
    assert format_bearing(360) == 'N 00°00\'00" E'


def test_bearing_135_is_S45E():
    assert format_bearing(135) == 'S 45°00\'00" E'


def test_bearing_180_S00E():
    assert format_bearing(180) == 'S 00°00\'00" E'


def test_bearing_270_S90W():
    assert format_bearing(270) == 'S 90°00\'00" W'


def test_bearing_300_N60W():
    assert format_bearing(300) == 'N 60°00\'00" W'


def test_bearing_5_5_pads_N05():
    assert format_bearing(5.5) == 'N 05°30\'00" E'


def test_bearing_seconds_decimals():
    assert format_bearing(45.5041667, seconds_decimals=1) == 'N 45°30\'15.0" E'
    assert format_bearing(-60) == 'N 60°00\'00" W'


def test_dms_5_5_unpadded():
    assert format_dms(5.5) == '5°30\'00"'
    assert format_dms(5.5, pad_degrees=True) == '05°30\'00"'
    assert format_dms(30) == '30°00\'00"'


def test_dms_carry_59_99999_to_60():
    assert format_dms(59.99999) == '60°00\'00"'
    assert dms_parts(59.99999) == (60, 0, 0.0)
    assert dms_parts(45.5041667) == (45, 30, 15.0)
    d, m, s = dms_parts(7.1619725)
    assert (d, m, s) == (7, 9, 43.0)


def test_dms_parts_with_decimals():
    d, m, s = dms_parts(45.5041667, seconds_decimals=2)
    assert (d, m) == (45, 30)
    assert s == pytest.approx(15.0, abs=1e-6)
    assert format_dms(30.5, seconds_decimals=2) == '30°30\'00.00"'


def test_direction_to_azimuth_30_60_0_90_neg90_180_180_270():
    assert direction_to_azimuth(30) == pytest.approx(60, abs=1e-9)
    assert direction_to_azimuth(0) == pytest.approx(90, abs=1e-9)
    assert direction_to_azimuth(-90) == pytest.approx(180, abs=1e-9)
    assert direction_to_azimuth(180) == pytest.approx(270, abs=1e-9)
    for d in (0, 30, 45, 90, 135, 180, 270, 359.5):
        assert azimuth_to_direction(direction_to_azimuth(d)) == pytest.approx(norm_deg(d), abs=1e-9)


def test_signed_delta_0_30_plus30_0_neg30_170_neg170_plus20():
    assert signed_delta_deg(0, 30) == pytest.approx(30, abs=1e-9)
    assert signed_delta_deg(0, -30) == pytest.approx(-30, abs=1e-9)
    assert signed_delta_deg(170, -170) == pytest.approx(20, abs=1e-9)
    assert signed_delta_deg(-170, 170) == pytest.approx(-20, abs=1e-9)
    assert signed_delta_deg(0, 180) == pytest.approx(180, abs=1e-9)
    assert signed_delta_deg(10, 10) == pytest.approx(0, abs=1e-9)


def test_parse_bearing_S45W_225_roundtrip():
    assert parse_bearing('S 45°00\'00" W') == pytest.approx(225, abs=1e-9)
    assert parse_bearing("S45-00-00E") == pytest.approx(135, abs=1e-9)
    assert parse_bearing("N 45 30 15 W") == pytest.approx(314.4958333, abs=1e-6)
    for az in (0, 5.5, 45.5041667, 90, 135, 180, 225, 270, 300, 359.9):
        back = parse_bearing(format_bearing(az, seconds_decimals=3))
        assert back == pytest.approx(norm_deg(az), abs=1e-6)


def test_parse_dms_forms():
    for text in ('45°30\'15"', "45d30'15\"", "45-30-15", "45 30 15", "45.5041667"):
        assert parse_dms(text) == pytest.approx(45.5041667, abs=1e-6)
    assert parse_dms("-30-30-00") == pytest.approx(-30.5, abs=1e-9)
    with pytest.raises(ValueError):
        parse_dms("abc")
    with pytest.raises(ValueError):
        parse_bearing("45")


def test_format_azimuth_unpadded():
    assert format_azimuth(75) == '75°00\'00"'
    assert format_azimuth(5.5) == '5°30\'00"'


def test_norm_deg_and_vectors():
    assert norm_deg(-90) == pytest.approx(270, abs=1e-9)
    assert norm_deg(720) == pytest.approx(0, abs=1e-9)
    assert norm_deg(360) == 0.0
    assert unit_vector(0) == pytest.approx([1, 0], abs=1e-12)
    assert unit_vector(90) == pytest.approx([0, 1], abs=1e-12)
    assert left_normal(0) == pytest.approx([0, 1], abs=1e-12)
    assert right_normal(0) == pytest.approx([0, -1], abs=1e-12)
    assert right_normal(30) == pytest.approx([math.sin(math.radians(30)), -math.cos(math.radians(30))], abs=1e-12)


def test_direction_of_and_azimuth_of():
    assert direction_of([0, 0], [1, 1]) == pytest.approx(45, abs=1e-9)
    assert direction_of([0, 0], [-1, 0]) == pytest.approx(180, abs=1e-9)
    assert direction_of([0, 0], [0, -1]) == pytest.approx(270, abs=1e-9)
    assert azimuth_of([0, 0], [1, 1]) == pytest.approx(45, abs=1e-9)
    assert azimuth_of([0, 0], [1, 0]) == pytest.approx(90, abs=1e-9)
    assert azimuth_of([0, 0], [0, 1]) == pytest.approx(0, abs=1e-9)
