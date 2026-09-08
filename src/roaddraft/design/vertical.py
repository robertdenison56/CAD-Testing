"""Vertical profiles: PVIs with symmetric parabolic vertical curves.

Grades are stored as ratios (0.02) and reported as percents (``2.0``) with
a ``_pct`` key suffix.  ``A_pct = |g2 - g1| * 100`` is always positive; the
``type`` (``crest``/``sag``/``break``) carries the sense.  PVI stations are
RAW stations on the parent alignment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from roaddraft.core.units import format_station
from roaddraft.design.errors import DesignError

GEOM_EPS = 1e-6


def _pct(g: float) -> str:
    return f"{g * 100.0:+.2f}%"


@dataclass
class PVI:
    """A point of vertical intersection with an optional symmetric VC."""

    station: float  # RAW station on the parent alignment
    elevation: float
    length: float = 0.0  # symmetric parabolic VC length; 0 = grade break

    def to_dict(self) -> dict:
        return {"station": float(self.station), "elevation": float(self.elevation),
                "length": float(self.length)}

    @classmethod
    def from_dict(cls, d) -> "PVI":
        if isinstance(d, dict):
            try:
                return cls(station=float(d["station"]), elevation=float(d["elevation"]),
                           length=float(d.get("length", 0.0) or 0.0))
            except (KeyError, TypeError, ValueError) as e:
                raise DesignError(f"PVI needs station and elevation: {e}")
        if isinstance(d, (list, tuple)) and len(d) in (2, 3):
            return cls(station=float(d[0]), elevation=float(d[1]),
                       length=float(d[2]) if len(d) == 3 else 0.0)
        raise DesignError(f"PVI must be [station, elevation], [station, elevation, L] or a dict, not {d!r}")


@dataclass
class _VC:
    """Derived data for one interior PVI (internal)."""

    index: int  # 1-based interior index (== PVI list index, 1-based, of the PVI)
    pvi: PVI
    g1: float
    g2: float
    pvc_station: float
    pvc_elevation: float
    pvt_station: float
    pvt_elevation: float

    @property
    def length(self) -> float:
        return float(self.pvi.length)

    @property
    def r(self) -> float:
        return (self.g2 - self.g1) / self.length if self.length > 0 else 0.0


@dataclass
class Profile:
    """A vertical profile bound (by name) to a horizontal alignment."""

    name: str
    alignment: str
    pvis: List[PVI] = field(default_factory=list)
    description: str = ""

    # ------------------------------------------------------- validation
    def validate(self) -> None:
        """Raise ``DesignError`` on any invalid PVI list (spec section 2.4)."""
        pvis = self.pvis
        if len(pvis) < 2:
            raise DesignError(f"profile {self.name} needs at least 2 PVIs")
        for k in range(1, len(pvis)):
            if pvis[k].station - pvis[k - 1].station <= GEOM_EPS:
                raise DesignError(
                    f"PVI-{k + 1} station {format_station(pvis[k].station)} must be after "
                    f"PVI-{k} ({format_station(pvis[k - 1].station)})")
        if float(pvis[0].length) != 0.0:
            raise DesignError("PVI-1 (the first PVI) cannot carry a vertical curve length")
        if float(pvis[-1].length) != 0.0:
            raise DesignError(f"PVI-{len(pvis)} (the last PVI) cannot carry a vertical curve length")
        for k in range(len(pvis)):
            if pvis[k].length < 0:
                raise DesignError(f"PVI-{k + 1}: vertical curve length must be >= 0")
        vcs = self._vcs()
        for vc in vcs:
            k = vc.index  # 1-based list index of this PVI
            if vc.length > 0 and abs(vc.g2 - vc.g1) < 1e-12:
                raise DesignError(
                    f"PVI-{k}: grades in ({_pct(vc.g1)}) and out ({_pct(vc.g2)}) are equal; "
                    f"set length to 0 or change the elevation")
            back = pvis[k - 1].station - pvis[k - 2].station
            ahead = pvis[k].station - pvis[k - 1].station
            half = vc.length / 2.0
            if half > back + GEOM_EPS:
                raise DesignError(
                    f"PVI-{k}: vertical curve L={vc.length:.2f} does not fit ({back:.2f} ft to PVI-{k - 1})")
            if half > ahead + GEOM_EPS:
                raise DesignError(
                    f"PVI-{k}: vertical curve L={vc.length:.2f} does not fit ({ahead:.2f} ft to PVI-{k + 1})")
        for a, b in zip(vcs, vcs[1:]):
            if b.pvc_station < a.pvt_station - GEOM_EPS:
                raise DesignError(
                    f"vertical curves at PVI-{a.index} and PVI-{b.index} overlap by "
                    f"{a.pvt_station - b.pvc_station:.2f} ft")

    # -------------------------------------------------------- derived
    def _vcs(self) -> List[_VC]:
        out: List[_VC] = []
        p = self.pvis
        for k in range(1, len(p) - 1):
            g1 = (p[k].elevation - p[k - 1].elevation) / (p[k].station - p[k - 1].station)
            g2 = (p[k + 1].elevation - p[k].elevation) / (p[k + 1].station - p[k].station)
            L = float(p[k].length)
            out.append(_VC(index=k + 1, pvi=p[k], g1=g1, g2=g2,
                           pvc_station=p[k].station - L / 2.0, pvc_elevation=p[k].elevation - g1 * L / 2.0,
                           pvt_station=p[k].station + L / 2.0, pvt_elevation=p[k].elevation + g2 * L / 2.0))
        return out

    def station_range(self) -> Tuple[float, float]:
        if not self.pvis:
            raise DesignError(f"profile {self.name} has no PVIs")
        return float(self.pvis[0].station), float(self.pvis[-1].station)

    def curves(self) -> List[dict]:
        """One ``vc_data`` row per interior PVI (grade breaks included)."""
        return [vc_data(self, n) for n in range(1, len(self.pvis) - 1)]

    def _require_in_range(self, station_raw: float) -> None:
        s0, s1 = self.station_range()
        if station_raw < s0 - GEOM_EPS or station_raw > s1 + GEOM_EPS:
            raise DesignError(
                f"station {format_station(station_raw)} is outside profile {self.name} "
                f"({format_station(s0)} to {format_station(s1)})")

    def _segment(self, station_raw: float) -> Tuple[Optional[_VC], int]:
        """``(vc, k)``: the VC containing the station (or None) and the index k of
        the PVI-to-PVI segment ``[S_k, S_{k+1})`` the station lies in."""
        p = self.pvis
        for vc in self._vcs():
            if vc.length > 0 and vc.pvc_station <= station_raw <= vc.pvt_station:
                return vc, 0
        k = 0
        for i in range(len(p) - 1):
            if station_raw >= p[i].station:
                k = i
        return None, k

    def elevation_at(self, station_raw: float) -> float:
        """Profile elevation at a RAW station (DesignError outside the PVIs)."""
        station_raw = float(station_raw)
        self._require_in_range(station_raw)
        vc, k = self._segment(station_raw)
        if vc is not None:
            x = station_raw - vc.pvc_station
            return vc.pvc_elevation + vc.g1 * x + (vc.r / 2.0) * x * x
        p = self.pvis
        g = (p[k + 1].elevation - p[k].elevation) / (p[k + 1].station - p[k].station)
        return p[k].elevation + g * (station_raw - p[k].station)

    def grade_at(self, station_raw: float) -> float:
        """Grade (ratio) at a RAW station; at a grade break the AHEAD grade."""
        station_raw = float(station_raw)
        self._require_in_range(station_raw)
        vc, k = self._segment(station_raw)
        if vc is not None:
            return vc.g1 + vc.r * (station_raw - vc.pvc_station)
        p = self.pvis
        return (p[k + 1].elevation - p[k].elevation) / (p[k + 1].station - p[k].station)

    # ---------------------------------------------------- serialization
    def to_dict(self) -> dict:
        return {"name": self.name, "alignment": self.alignment, "description": self.description,
                "pvis": [p.to_dict() for p in self.pvis]}

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        if not isinstance(d, dict) or not d.get("name"):
            raise DesignError("profile needs a name")
        if not d.get("alignment"):
            raise DesignError(f"profile {d['name']} needs an alignment name")
        prof = cls(name=str(d["name"]), alignment=str(d["alignment"]),
                   pvis=[PVI.from_dict(p) for p in (d.get("pvis") or [])],
                   description=str(d.get("description") or ""))
        prof.validate()
        return prof


def vc_data(profile: Profile, n: int) -> dict:
    """Vertical-curve row for interior PVI ``n`` (1-based interior index).

    Station ``_text`` fields use plain ``format_station`` (no equations); the
    query layer re-fills them through the parent alignment.
    """
    vcs = profile._vcs()
    if n < 1 or n > len(vcs):
        raise DesignError(
            f"VC-{n} does not exist: {profile.name} has {len(vcs)} interior PVI"
            f"{'' if len(vcs) == 1 else 's'}")
    vc = vcs[n - 1]
    L = vc.length
    g1, g2 = vc.g1, vc.g2
    a_pct = abs(g2 - g1) * 100.0
    if L == 0:
        vtype = "break"
    else:
        vtype = "crest" if g2 < g1 else "sag"
    k_val = (L / a_pct) if (a_pct > 0 and L > 0) else None
    high_low = None
    if L > 0 and g1 * g2 < 0:
        x = g1 * L / (g1 - g2)
        sta = vc.pvc_station + x
        elev = vc.pvc_elevation + g1 * x + (vc.r / 2.0) * x * x
        high_low = {"kind": "high" if vtype == "crest" else "low", "x_from_pvc": x,
                    "station": sta, "elevation": elev}
    return {
        "profile": profile.name, "alignment": profile.alignment, "index": n, "ref": f"VC-{n}",
        "type": vtype, "length": L, "pvi_station": float(vc.pvi.station),
        "pvi_elevation": float(vc.pvi.elevation), "pvc_station": vc.pvc_station,
        "pvc_elevation": vc.pvc_elevation, "pvt_station": vc.pvt_station,
        "pvt_elevation": vc.pvt_elevation, "g1_pct": g1 * 100.0, "g2_pct": g2 * 100.0,
        "A_pct": a_pct, "K": k_val, "external": a_pct * L / 800.0, "high_low": high_low,
        "pvi_station_text": format_station(vc.pvi.station),
        "pvc_station_text": format_station(vc.pvc_station),
        "pvt_station_text": format_station(vc.pvt_station),
        "high_low_station_text": format_station(high_low["station"]) if high_low else None,
    }


__all__ = ["PVI", "Profile", "vc_data", "GEOM_EPS"]
