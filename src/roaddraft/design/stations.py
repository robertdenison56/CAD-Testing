"""Station systems: raw <-> display stations through station equations.

* Raw station = ``begin_station + distance_along`` (continuous; stored
  everywhere internally).
* Display station = raw mapped through the equations; what labels print.

Regions are half-open ``[raw_start, raw_end)`` except the last, which is
closed at ``begin + length``.  The equation point itself reads AHEAD (it
belongs to the region that starts there), matching LandXML ``staAhead``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from roaddraft.core.units import format_station, parse_station
from roaddraft.design.errors import DesignError

STATION_EPS = 1e-6


@dataclass
class StationEquation:
    """One station equation (``STA back BK = STA ahead AH`` at ``raw_station``)."""

    raw_station: float  # raw station where the equation sits (== LandXML staInternal)
    back: float  # display station reading just before it (== staBack)
    ahead: float  # display station reading at and after it (== staAhead)

    def to_dict(self) -> dict:
        return {"raw_station": float(self.raw_station), "back": float(self.back),
                "ahead": float(self.ahead)}

    @classmethod
    def from_dict(cls, d: dict) -> "StationEquation":
        try:
            return cls(raw_station=float(d["raw_station"]), back=float(d["back"]),
                       ahead=float(d["ahead"]))
        except (KeyError, TypeError, ValueError) as e:
            raise DesignError(f"station equation needs raw_station, back and ahead: {e}")


@dataclass
class Region:
    """A stationing region (derived from the equations; never serialized)."""

    index: int  # 1-based
    raw_start: float
    raw_end: float  # [raw_start, raw_end) except the last region, which is closed
    display_start: float
    display_end: float
    shift: float  # display = raw + shift within this region


def _display_text(value: Union[float, str], decimals: int = 2) -> str:
    return format_station(float(value), decimals)


def _parse_display(value: Union[float, int, str]) -> float:
    """Display-station input: a number (feet) or ``'12+34.56'``."""
    if isinstance(value, bool):
        raise DesignError(f"station must be a number or '12+34.56', not {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(parse_station(value))
        except ValueError:
            raise DesignError(f"cannot parse station {value!r}",
                              hint="use feet (1600) or station notation '16+00.00'")
    raise DesignError(f"station must be a number or '12+34.56', not {value!r}")


class StationSystem:
    """Raw/display station mapping for one alignment."""

    def __init__(self, begin_station: float, length: float, equations: List[StationEquation]):
        self.begin_station = float(begin_station)
        self.length = float(length)
        self.equations = list(equations or [])
        self._regions = self._build_regions()

    # ----------------------------------------------------------- regions
    @property
    def end_station_raw(self) -> float:
        return self.begin_station + self.length

    def _build_regions(self) -> List[Region]:
        regions: List[Region] = []
        start = self.begin_station
        shift = 0.0
        for k, eq in enumerate(self.equations):
            end = float(eq.raw_station)
            regions.append(Region(index=len(regions) + 1, raw_start=start, raw_end=end,
                                  display_start=start + shift, display_end=end + shift,
                                  shift=shift))
            start = end
            shift = float(eq.ahead) - float(eq.raw_station)
        end = self.end_station_raw
        regions.append(Region(index=len(regions) + 1, raw_start=start, raw_end=end,
                              display_start=start + shift, display_end=end + shift,
                              shift=shift))
        return regions

    def regions(self) -> List[Region]:
        """All regions in travel order (region 1 starts at BEGIN)."""
        return list(self._regions)

    def region_of_raw(self, raw: float) -> int:
        """1-based region index containing ``raw`` (equation point -> AHEAD region)."""
        raw = float(raw)
        for r in self._regions[:-1]:
            if raw < r.raw_end:
                return r.index
        return self._regions[-1].index

    def region(self, index: int) -> Region:
        """Region by 1-based index."""
        if index < 1 or index > len(self._regions):
            raise DesignError(f"region {index} does not exist; regions are 1..{len(self._regions)}")
        return self._regions[index - 1]

    # ----------------------------------------------------------- mapping
    def to_display(self, raw: float) -> Tuple[float, int]:
        """Raw station -> ``(display, region)``."""
        idx = self.region_of_raw(raw)
        return float(raw) + self._regions[idx - 1].shift, idx

    def _regions_containing_display(self, display: float) -> List[Region]:
        found: List[Region] = []
        last = self._regions[-1]
        for r in self._regions:
            if r is last:
                if r.display_start - STATION_EPS <= display <= r.display_end + STATION_EPS:
                    found.append(r)
            elif r.display_start - STATION_EPS <= display < r.display_end:
                found.append(r)
        return found

    def to_raw(self, display: float, region: Optional[int] = None) -> float:
        """Display station -> raw.  Gaps and ambiguous overlaps raise ``DesignError``."""
        display = float(display)
        if region is not None:
            r = self.region(int(region))
            return display - r.shift
        found = self._regions_containing_display(display)
        if not found:
            for eq in self.equations:
                if float(eq.back) < display < float(eq.ahead):
                    raise DesignError(
                        f"station {_display_text(display)} does not exist on this alignment "
                        f"(gap between {_display_text(eq.back)} BK and {_display_text(eq.ahead)} AH)")
            first, last = self._regions[0], self._regions[-1]
            raise DesignError(
                f"station {_display_text(display)} does not exist on this alignment "
                f"({_display_text(first.display_start)} to {_display_text(last.display_end)})")
        if len(found) > 1:
            names = [str(r.index) for r in found]
            hint = "regions: " + ", ".join(
                f"{r.index} = {_display_text(r.display_start)}..{_display_text(r.display_end)}"
                for r in self._regions)
            raise DesignError(
                f"station {_display_text(display)} occurs in regions "
                f"{' and '.join(names) if len(names) == 2 else ', '.join(names)}; pass region=",
                hint=hint)
        return display - found[0].shift

    def format(self, raw: float, decimals: int = 2) -> str:
        """Display text (``'28+00.00'``) of a raw station."""
        disp, _ = self.to_display(raw)
        return format_station(disp, decimals)

    def parse(self, value: Union[float, int, str], region: Optional[int] = None) -> float:
        """Display input (number of feet or ``'12+34.56'``) -> RAW station."""
        return self.to_raw(_parse_display(value), region)

    # ----------------------------------------------------------- range
    def in_range(self, raw: float) -> bool:
        return self.begin_station - STATION_EPS <= float(raw) <= self.end_station_raw + STATION_EPS

    def require_in_range(self, raw: float, alignment_name: str) -> None:
        """Raise ``DesignError`` when ``raw`` lies outside the alignment."""
        if not self.in_range(raw):
            raise DesignError(
                f"station {self.format(raw)} is outside {alignment_name} "
                f"({self.format(self.begin_station)} to {self.format(self.end_station_raw)})")

    def begin_text(self, decimals: int = 2) -> str:
        return self.format(self.begin_station, decimals)

    def end_text(self, decimals: int = 2) -> str:
        return self.format(self.end_station_raw, decimals)


def build_equations(begin_station: float, length: float, items: List[dict]) -> List[StationEquation]:
    """Validate and build station equations from user items.

    Each item is ``{"back": display, "ahead": display}`` or
    ``{"raw_station", "back", "ahead"}``; ``back``/``ahead`` may be
    ``'12+34.56'`` strings.  The raw station is derived from ``back`` through
    the preceding equations; a given ``raw_station`` must agree within
    ``STATION_EPS``.
    """
    begin = float(begin_station)
    end = begin + float(length)
    result: List[StationEquation] = []
    shift = 0.0
    prev_raw = begin
    for n, item in enumerate(items or [], start=1):
        if isinstance(item, StationEquation):
            item = item.to_dict()
        if not isinstance(item, dict):
            raise DesignError(f"equation {n}: expected an object with back and ahead")
        if "back" not in item or "ahead" not in item:
            raise DesignError(f"equation {n}: back and ahead are required",
                              hint="{'back': '20+00', 'ahead': '25+00'}")
        back = _parse_display(item["back"])
        ahead = _parse_display(item["ahead"])
        if item.get("raw_station") is not None:
            raw = _parse_display(item["raw_station"])
            expected_back = raw + shift
            if abs(expected_back - back) > STATION_EPS:
                raise DesignError(
                    f"equation {n}: back station {_display_text(back)} does not match "
                    f"{_display_text(expected_back)} computed from the preceding equations",
                    hint="back = the station reading just before the equation point")
        else:
            raw = back - shift
        if raw <= prev_raw + STATION_EPS:
            if n == 1:
                raise DesignError(
                    f"equation {n}: raw station {_display_text(raw)} must lie after BEGIN "
                    f"({_display_text(begin)})")
            raise DesignError(
                f"equation {n}: raw station {_display_text(raw)} must lie after equation "
                f"{n - 1} ({_display_text(prev_raw)})")
        if raw >= end - STATION_EPS:
            raise DesignError(
                f"equation {n}: raw station {_display_text(raw)} must lie before END "
                f"({_display_text(end)})")
        result.append(StationEquation(raw_station=raw, back=back, ahead=ahead))
        shift = ahead - raw
        prev_raw = raw
    return result


def equation_label(eq: StationEquation, decimals: int = 2) -> str:
    """``'STA 20+00.00 BK = STA 25+00.00 AH'``."""
    return (f"STA {format_station(eq.back, decimals)} BK = "
            f"STA {format_station(eq.ahead, decimals)} AH")
