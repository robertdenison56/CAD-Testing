from roaddraft.core.units import format_station, lineweight_points, parse_station


def test_format_station_basic():
    assert format_station(1234.567) == "12+34.57"
    assert format_station(0) == "0+00.00"
    assert format_station(100000.5) == "1000+00.50"
    assert format_station(99.999) == "1+00.00"  # rounding carries
    assert format_station(2018.879) == "20+18.88"


def test_format_station_negative_and_decimals():
    assert format_station(-50) == "-0+50.00"
    assert format_station(1234.567, decimals=1) == "12+34.6"


def test_parse_station():
    assert parse_station("12+34.57") == 1234.57
    assert parse_station("-0+50.00") == -50.0
    assert parse_station("1500") == 1500.0
    assert abs(parse_station(format_station(87654.32)) - 87654.32) < 0.01


def test_lineweight_points():
    assert abs(lineweight_points(0.25) - 0.7086) < 0.001
