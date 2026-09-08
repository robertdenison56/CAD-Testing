"""WP1 tests: design/vertical.py.

Profile P: PVIs (1000, 100), (2000, 120, L=400), (3000, 90):
g1 = +2 %, g2 = -3 %, A = 5, K = 80, crest, PVC (1800, 116), PVT (2200, 114),
E = 2.5, high point x = 160 -> STA 19+60, elev 117.6.
"""
from __future__ import annotations

import pytest

from roaddraft.design.errors import DesignError
from roaddraft.design.vertical import PVI, Profile, vc_data


@pytest.fixture
def P():
    prof = Profile("PROF-1", "ALIGN-1", [PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90)])
    prof.validate()
    return prof


def test_P_g1_2_g2_neg3_A5_K80_crest_pvc_1800_116_pvt_2200_114_E2_5(P):
    row = vc_data(P, 1)
    assert row["profile"] == "PROF-1" and row["alignment"] == "ALIGN-1"
    assert row["index"] == 1 and row["ref"] == "VC-1"
    assert row["type"] == "crest"
    assert row["length"] == 400.0
    assert row["g1_pct"] == pytest.approx(2.0, abs=1e-9)
    assert row["g2_pct"] == pytest.approx(-3.0, abs=1e-9)
    assert row["A_pct"] == pytest.approx(5.0, abs=1e-9)
    assert row["K"] == pytest.approx(80.0, abs=1e-9)
    assert row["pvi_station"] == 2000.0 and row["pvi_elevation"] == 120.0
    assert row["pvc_station"] == pytest.approx(1800.0, abs=1e-9)
    assert row["pvc_elevation"] == pytest.approx(116.0, abs=1e-9)
    assert row["pvt_station"] == pytest.approx(2200.0, abs=1e-9)
    assert row["pvt_elevation"] == pytest.approx(114.0, abs=1e-9)
    assert row["external"] == pytest.approx(2.5, abs=1e-9)
    assert row["pvi_station_text"] == "20+00.00"
    assert row["pvc_station_text"] == "18+00.00"
    assert row["pvt_station_text"] == "22+00.00"
    assert P.curves() == [row]
    assert P.station_range() == (1000.0, 3000.0)


def test_P_high_point_1960_117_6(P):
    hl = vc_data(P, 1)["high_low"]
    assert hl["kind"] == "high"
    assert hl["x_from_pvc"] == pytest.approx(160.0, abs=1e-9)
    assert hl["station"] == pytest.approx(1960.0, abs=1e-9)
    assert hl["elevation"] == pytest.approx(117.6, abs=1e-9)
    assert vc_data(P, 1)["high_low_station_text"] == "19+60.00"
    assert P.grade_at(1960) == pytest.approx(0.0, abs=1e-12)


def test_P_elev_2000_117_5_1900_117_375_grade_1900_0_75(P):
    assert P.elevation_at(2000) == pytest.approx(117.5, abs=1e-9)
    assert P.elevation_at(1900) == pytest.approx(117.375, abs=1e-9)
    assert P.grade_at(1900) == pytest.approx(0.0075, abs=1e-12)
    assert P.elevation_at(1800) == pytest.approx(116.0, abs=1e-9)
    assert P.elevation_at(2200) == pytest.approx(114.0, abs=1e-9)
    assert P.grade_at(1800) == pytest.approx(0.02, abs=1e-12)
    assert P.grade_at(2200) == pytest.approx(-0.03, abs=1e-12)


def test_P_elev_1500_110_2600_102(P):
    assert P.elevation_at(1500) == pytest.approx(110.0, abs=1e-9)
    assert P.elevation_at(2600) == pytest.approx(102.0, abs=1e-9)
    assert P.elevation_at(1000) == pytest.approx(100.0, abs=1e-9)
    assert P.elevation_at(3000) == pytest.approx(90.0, abs=1e-9)
    assert P.grade_at(1500) == pytest.approx(0.02, abs=1e-12)
    assert P.grade_at(2600) == pytest.approx(-0.03, abs=1e-12)


def test_P_elev_999_raises(P):
    with pytest.raises(DesignError):
        P.elevation_at(999)
    with pytest.raises(DesignError):
        P.elevation_at(3001)
    with pytest.raises(DesignError):
        P.grade_at(999)


def test_sag_g1_neg2_g2_3_low_1960_102_4_elev_2000_102_5():
    S = Profile("SAG", "ALIGN-1", [PVI(1000, 120), PVI(2000, 100, 400), PVI(3000, 130)])
    S.validate()
    row = vc_data(S, 1)
    assert row["type"] == "sag"
    assert row["g1_pct"] == pytest.approx(-2.0, abs=1e-9)
    assert row["g2_pct"] == pytest.approx(3.0, abs=1e-9)
    assert row["A_pct"] == pytest.approx(5.0, abs=1e-9)
    assert row["K"] == pytest.approx(80.0, abs=1e-9)
    hl = row["high_low"]
    assert hl["kind"] == "low"
    assert hl["station"] == pytest.approx(1960.0, abs=1e-9)
    assert hl["elevation"] == pytest.approx(102.4, abs=1e-9)
    assert S.elevation_at(2000) == pytest.approx(102.5, abs=1e-9)
    assert row["pvc_elevation"] == pytest.approx(104.0, abs=1e-9)
    assert row["pvt_elevation"] == pytest.approx(106.0, abs=1e-9)


def test_same_sign_2_1_no_high_low_K400():
    Q = Profile("Q", "ALIGN-1", [PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 130)])
    Q.validate()
    row = vc_data(Q, 1)
    assert row["high_low"] is None
    assert row["high_low_station_text"] is None
    assert row["K"] == pytest.approx(400.0, abs=1e-9)
    assert row["A_pct"] == pytest.approx(1.0, abs=1e-9)
    assert row["type"] == "crest"


def test_equal_grades_L200_raises():
    with pytest.raises(DesignError) as ei:
        Profile("E", "A", [PVI(1000, 100), PVI(2000, 120, 200), PVI(3000, 140)]).validate()
    assert str(ei.value) == ("PVI-2: grades in (+2.00%) and out (+2.00%) are equal; "
                             "set length to 0 or change the elevation")
    # equal grades with L == 0 is a legal (degenerate) grade break
    Profile("E", "A", [PVI(1000, 100), PVI(2000, 120, 0), PVI(3000, 140)]).validate()


def test_overlap_500_500_on_400_raises_100():
    with pytest.raises(DesignError) as ei:
        Profile("O", "A", [PVI(1000, 100), PVI(2000, 120, 500), PVI(2400, 110, 500),
                           PVI(3000, 90)]).validate()
    assert str(ei.value) == "vertical curves at PVI-2 and PVI-3 overlap by 100.00 ft"
    # touching VCs (PVT == PVC) are fine
    Profile("O", "A", [PVI(1000, 100), PVI(2000, 120, 400), PVI(2400, 110, 400),
                       PVI(3000, 90)]).validate()


def test_L800_on_300_does_not_fit_raises():
    with pytest.raises(DesignError) as ei:
        Profile("F", "A", [PVI(1000, 100), PVI(1300, 110, 800), PVI(3000, 90)]).validate()
    assert str(ei.value) == "PVI-2: vertical curve L=800.00 does not fit (300.00 ft to PVI-1)"
    with pytest.raises(DesignError) as ei:
        Profile("F", "A", [PVI(1000, 100), PVI(2700, 110, 800), PVI(3000, 90)]).validate()
    assert str(ei.value) == "PVI-2: vertical curve L=800.00 does not fit (300.00 ft to PVI-3)"


def test_end_pvi_length_raises():
    with pytest.raises(DesignError):
        Profile("X", "A", [PVI(1000, 100), PVI(2000, 120, 400), PVI(3000, 90, 100)]).validate()
    with pytest.raises(DesignError):
        Profile("X", "A", [PVI(1000, 100, 100), PVI(2000, 120, 400), PVI(3000, 90)]).validate()
    with pytest.raises(DesignError):
        Profile("X", "A", [PVI(1000, 100)]).validate()


def test_non_increasing_raises():
    with pytest.raises(DesignError):
        Profile("N", "A", [PVI(1000, 100), PVI(1000, 120), PVI(3000, 90)]).validate()
    with pytest.raises(DesignError):
        Profile("N", "A", [PVI(1000, 100), PVI(2000, 120), PVI(1500, 90)]).validate()


def test_grade_break_returns_ahead_grade():
    G = Profile("G", "A", [PVI(1000, 100), PVI(2000, 120, 0), PVI(3000, 90)])
    G.validate()
    assert G.grade_at(2000) == pytest.approx(-0.03, abs=1e-12)
    assert G.grade_at(1999.999) == pytest.approx(0.02, abs=1e-12)
    assert G.elevation_at(2000) == pytest.approx(120.0, abs=1e-9)
    row = vc_data(G, 1)
    assert row["type"] == "break" and row["K"] is None and row["high_low"] is None
    assert row["external"] == 0.0
    assert row["pvc_station"] == 2000.0 and row["pvt_station"] == 2000.0
    assert G.grade_at(3000) == pytest.approx(-0.03, abs=1e-12)  # end: last segment grade


def test_profile_dict_round_trip_and_validation_in_from_dict(P):
    d = P.to_dict()
    assert list(d.keys()) == ["name", "alignment", "description", "pvis"]
    assert d["pvis"][1] == {"station": 2000.0, "elevation": 120.0, "length": 400.0}
    assert Profile.from_dict(d) == P
    assert PVI.from_dict([1000, 100]) == PVI(1000.0, 100.0, 0.0)
    assert PVI.from_dict([1000, 100, 400]) == PVI(1000.0, 100.0, 400.0)
    with pytest.raises(DesignError):
        Profile.from_dict({"name": "B", "alignment": "A",
                           "pvis": [{"station": 1000, "elevation": 1}, {"station": 900, "elevation": 2}]})
    with pytest.raises(DesignError):
        Profile.from_dict({"alignment": "A", "pvis": []})
    with pytest.raises(DesignError):
        vc_data(P, 2)
