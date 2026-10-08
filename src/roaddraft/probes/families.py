"""Probe families: a probe as a generator, one instance per seed.

The 33 fixed probes are the test set, and a model fine-tuned on their
solutions would be trained on the exam. A family is the same kind of task
with its particulars drawn from a seed: which sheet, which station, which
bearing and distance, how many lanes. ``instance(seed)`` is an ordinary
``Probe`` with a prompt in the engineer's words, a check that reads the
document, and a scripted solve that drafts it through the tool surface and
says its arithmetic as it goes, so the trajectories recorded from it show
the work and not only the answer. The fixed probes' particulars are kept out
of every family, so no instance is a test probe under another id.

An instance is named ``family@seed`` and is reachable wherever a probe id is:
``python -m roaddraft.probes setup draft-alignment@17``,
``python -m roaddraft.trajectories record --family draft-alignment --seeds 0-99``.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List

from roaddraft.api.session import Session
from roaddraft.design.angles import format_bearing, format_dms
from roaddraft.probes import fixture
from roaddraft.probes.base import Probe
from roaddraft.probes.drafting import (CL, EOP, SHLD, along, alignment_runs, expected_alignment,
                                       first, on_layer, run, traverse, verdict)
from roaddraft.probes.tasks import TOLERANCE_FT, aimed_at_point, ensure_layer

SEP = "@"


def station_text(raw: float) -> str:
    """``18+37.50``, and ``18+00`` for a whole hundred, as a drafter writes it."""
    whole, rest = divmod(round(float(raw), 2), 100.0)
    text = f"{int(whole)}+{rest:05.2f}"
    return text[:-3] if text.endswith(".00") else text


def _say(session: Session, text: str) -> None:
    """Shown work: kept by the recorder as the assistant's words before the
    next call, and a no-op on a session that is not being recorded."""
    say = getattr(session, "say", None)
    if say is not None:
        say(text)


@dataclass
class Family:
    id: str
    tags: List[str]
    start: str
    describe: str
    #: the particulars a seed draws
    make: Callable[[random.Random], dict]
    #: the probe those particulars make, under the given id
    build: Callable[[dict, str], Probe]

    def params(self, seed: int) -> dict:
        return self.make(random.Random(f"{self.id}{SEP}{seed}"))

    def instance(self, seed: int) -> Probe:
        probe = self.build(self.params(seed), f"{self.id}{SEP}{seed}")
        probe.family, probe.start, probe.tags = self.id, self.start, list(self.tags)
        return probe


# ------------------------------------------------------- 1. a callout by station

#: stations each sheet shows with 1.5 in to spare at 40 ft either side
SHEET_STATIONS = {"C-101": (1100, 2400), "C-102": (2700, 4050), "C-103": (4300, 5650)}

LABELS = ["BEGIN GUARDRAIL", "END GUARDRAIL", "BEGIN CURB AND GUTTER", "END CURB AND GUTTER",
          "BEGIN RETAINING WALL", "END RETAINING WALL", "DRAINAGE INLET", "BEGIN WIDENING",
          "END WIDENING", "BEGIN TAPER", "END TAPER", "RELOCATE SIGN", "UTILITY POLE",
          "BEGIN OVERLAY", "END OVERLAY", "CONFORM TO EXISTING"]


def _make_callout(rng: random.Random) -> dict:
    sheet = rng.choice(fixture.SHEETS)
    lo, hi = SHEET_STATIONS[sheet]
    station = float(rng.randrange(lo, hi + 1, 25))
    offset = rng.choice([0.0, 12.0, 20.0, float(rng.randrange(5, 41))])
    side = rng.choice("LR") if offset else ""
    return {"sheet": sheet, "station": station, "offset": offset, "side": side,
            "label": rng.choice(LABELS)}


def _build_callout(p: dict, pid: str) -> Probe:
    sta, sheet, off, side = station_text(p["station"]), p["sheet"], p["offset"], p["side"]
    signed = off if side == "R" else -off
    if off:
        hand = "right" if side == "R" else "left"
        where = f"the point {off:g} ft {hand} of SR-100 station {sta}"
        what = f"SR-100 {sta}, {off:g}' {'RT' if side == 'R' else 'LT'}"
        anchor = f"{sta}@{off:g}{side}"
    else:
        where = f"SR-100 station {sta}, on the centerline"
        what = f"SR-100 {sta} on the centerline"
        anchor = sta
    prompt = (f"On sheet {sheet}, in paper space, call out {where} as {p['label']}, "
              f"with the station in the text.")

    def at(session: Session) -> dict:
        r = session.query("station_to_xy", {"alignment": f"DESIGN:{fixture.ALIGNMENT}",
                                            "station": sta, "offset": signed, "sheet": sheet})
        if not r["ok"]:
            raise RuntimeError(r["error"]["message"])
        return r

    def check(baseline, submitted):
        return aimed_at_point(baseline, submitted, at(baseline)["point"], what,
                              must_contain=sta, on_sheet=sheet)

    def solve(session):
        r = at(session)
        x, y = r["on_sheet"]["sheet_point"]
        dx = 2.0 if x < 17.0 else -4.5          # the text toward the middle of the sheet
        dy = 2.5 if y < 11.7 else -2.5
        offset_text = f", {off:.2f}' {'RT' if side == 'R' else 'LT'}" if off else ""
        run(session, "place_callout", {
            "space": sheet, "target_anchor": anchor, "alignment": f"DESIGN:{fixture.ALIGNMENT}",
            "position": [x + dx, y + dy], "content": f"STA {r['station_text']}{offset_text}\n{p['label']}",
            "layer": ensure_layer(session, "S-ANNO-CALL")})

    note = (f"A station and an offset, with no entity there to find: the leader must land within "
            f"{TOLERANCE_FT:g} ft of {what} through the viewport, on the sheet, and the text must read {sta}.")
    return Probe(id=pid, prompt=prompt, check=check, solve=solve, note=note, params=dict(p))


# ------------------------------------------------- 2. an alignment, as described

NAMES = ["MAIN-ST", "OAK-AVE", "ELM-AVE", "RAMP-A", "RAMP-B", "RAMP-C", "SR-12", "SR-45",
         "PINE-RD", "MILL-RD", "RIVER-RD", "CANYON-RD", "LAKE-DR", "HILL-ST"]
RADII = [300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0, 1000.0, 1200.0, 1500.0]
CARDINAL = {0.0: "north", 90.0: "east", 180.0: "south", 270.0: "west"}


def _bearing_azimuth(rng: random.Random) -> float:
    """A bearing in whole quarter-minutes, as an azimuth."""
    angle = rng.randrange(5, 86) + rng.choice([0, 15, 30, 45]) / 60.0
    quadrant = rng.choice(["NE", "SE", "SW", "NW"])
    return {"NE": angle, "SE": 180.0 - angle, "SW": 180.0 + angle, "NW": 360.0 - angle}[quadrant]


def _make_alignment(rng: random.Random) -> dict:
    legs = rng.choice([1, 2, 2, 3])
    azimuth = rng.choice([0.0, 90.0, 180.0, 270.0]) if rng.random() < 0.3 else _bearing_azimuth(rng)
    distances = [float(rng.randrange(400, 1601, 50)) for _ in range(legs)]
    turns = []
    for i in range(legs - 1):
        delta = float(rng.randrange(10, 61))
        room = 0.45 * min(distances[i], distances[i + 1])
        fits = [r for r in RADII if r * math.tan(math.radians(delta / 2.0)) <= room]
        if not fits:
            delta = 10.0
            fits = [r for r in RADII if r * math.tan(math.radians(5.0)) <= room]
        turns.append({"delta": delta, "direction": rng.choice(["left", "right"]),
                      "radius": rng.choice(fits)})
    return {"name": rng.choice(NAMES),
            "northing": float(rng.randrange(1000, 9001, 100) + rng.choice([0, 50])),
            "easting": float(rng.randrange(1000, 9001, 100) + rng.choice([0, 50])),
            "begin": float(rng.randrange(10, 61) * 100),
            "azimuth": azimuth, "distances": distances, "turns": turns}


def _legs(p: dict) -> List[tuple]:
    azimuth, legs = p["azimuth"], [(p["azimuth"], p["distances"][0])]
    for turn, distance in zip(p["turns"], p["distances"][1:]):
        azimuth = (azimuth + turn["delta"] * (1 if turn["direction"] == "right" else -1)) % 360.0
        legs.append((azimuth, distance))
    return legs


def _pis(p: dict, points: List[List[float]]) -> list:
    inner = [[*points[i + 1], p["turns"][i]["radius"]] for i in range(len(p["turns"]))]
    return [points[0]] + inner + [points[-1]]


def _bearing_phrase(azimuth: float) -> str:
    return f"due {CARDINAL[azimuth]}" if azimuth in CARDINAL else format_bearing(azimuth)


def _build_alignment(p: dict, pid: str) -> Probe:
    legs = _legs(p)
    begin = station_text(p["begin"])
    name, turns, distances = p["name"], p["turns"], p["distances"]
    text = (f"Create alignment {name}. It begins at N {p['northing']:,.2f}, E {p['easting']:,.2f}, "
            f"station {begin}, and runs {_bearing_phrase(p['azimuth'])} for {distances[0]:,.2f} ft")
    if not turns:
        text += " to its end."
    else:
        for i, turn in enumerate(turns):
            pi = "a PI" if len(turns) == 1 else f"PI-{i + 1}"
            text += (f" to {pi}. There it deflects {format_dms(turn['delta'])} to the "
                     f"{turn['direction']} and continues {distances[i + 1]:,.2f} ft")
            if i == len(turns) - 1:
                text += " to its end."
        if len(turns) == 1:
            text += f" Use a {turns[0]['radius']:g} ft radius curve at the PI."
        else:
            text += (" Use " + ", ".join(f"a {t['radius']:g} ft radius curve at PI-{i + 1}"
                                         for i, t in enumerate(turns)) + ".")
    text += " Draw its centerline on layer V-ALIGN-CNTR."

    def check(baseline, submitted):
        want = expected_alignment(name, _pis(p, traverse([p["easting"], p["northing"]], legs)), begin)
        return verdict(first(alignment_runs(submitted, name, want),
                             on_layer(baseline, submitted, CL, along(want), "the centerline")),
                       f"{name} runs as described from N {p['northing']:.2f}, E {p['easting']:.2f} "
                       f"and is drawn")

    def solve(session):
        x, y = p["easting"], p["northing"]
        lines = [f"Start: N {y:.2f}, E {x:.2f} is [{x:.2f}, {y:.2f}], easting first."]
        points = [[x, y]]
        for k, (azimuth, distance) in enumerate(legs, 1):
            if k > 1:
                turn = turns[k - 2]
                lines.append(f"Deflect {turn['delta']:g}° {turn['direction']}: azimuth "
                             f"{legs[k - 2][0]:.4f}° {'+' if turn['direction'] == 'right' else '-'} "
                             f"{turn['delta']:g}° = {azimuth:.4f}°.")
            nx = x + distance * math.sin(math.radians(azimuth))
            ny = y + distance * math.cos(math.radians(azimuth))
            lines.append(f"Leg {k}: azimuth {azimuth:.4f}°, {distance:.2f} ft. "
                         f"E = {x:.2f} + {distance:.2f} sin = {nx:.2f}; "
                         f"N = {y:.2f} + {distance:.2f} cos = {ny:.2f}.")
            x, y = nx, ny
            points.append([round(x, 2), round(y, 2)])
        _say(session, "\n".join(lines))
        run(session, "create_alignment", {"name": name, "pis": _pis(p, points), "begin_station": begin})
        run(session, "draw_alignment", {"alignment": name, "layer": CL})

    note = ("Bearings and distances, PI to PI, with the start given northing first; the engine "
            "takes [easting, northing] and no bearing, so the PIs are worked out by hand. Each leg's "
            "error carries to the end.")
    return Probe(id=pid, prompt=text, check=check, solve=solve, note=note, params=dict(p))


# ------------------------------------------------- 3. lanes and shoulders, as widths


SHOULDERS = [2.0, 4.0, 5.0, 6.0, 8.0, 10.0]


def _make_offsets(rng: random.Random) -> dict:
    lanes = rng.choice([1, 1, 2, 2, 3])
    lane = rng.choice([10.0, 11.0, 12.0])
    left = right = rng.choice(SHOULDERS)
    if rng.random() < 0.4:                       # inside and outside shoulders differ
        right = rng.choice([s for s in SHOULDERS if s != left])
    if (lanes, lane, left, right) == (1, 12.0, 8.0, 8.0):   # draft-edges-shoulders, a test probe
        left = right = 6.0
    return {"lanes_per_side": lanes, "lane": lane, "shoulder_left": left, "shoulder_right": right}


def _build_offsets(p: dict, pid: str) -> Probe:
    lanes, lane = p["lanes_per_side"], p["lane"]
    shoulders = {"left": p["shoulder_left"], "right": p["shoulder_right"]}
    edge = lanes * lane
    outer = {side: edge + s for side, s in shoulders.items()}
    if shoulders["left"] == shoulders["right"]:
        with_shoulders = f"{shoulders['left']:g} ft paved shoulders"
    else:
        with_shoulders = (f"a {shoulders['left']:g} ft paved shoulder on the left and a "
                          f"{shoulders['right']:g} ft paved shoulder on the right")
    prompt = (f"SR-100 is a {2 * lanes}-lane highway with {lane:g} ft lanes and {with_shoulders}. "
              f"Its alignment is designed and drawn; nothing else is. Draw the edges of pavement on "
              f"layer V-ROAD-EOP and the outside edges of shoulder on layer V-ROAD-SHLD, both sides, "
              f"for the whole length.")

    def check(baseline, submitted):
        a = baseline.doc.design.alignments[fixture.ALIGNMENT]
        problems = []
        for sign, side in ((-1, "left"), (1, "right")):
            problems.append(on_layer(baseline, submitted, EOP, along(a, sign * edge),
                                     f"the {side} edge of pavement, {edge:g} ft {side}"))
            problems.append(on_layer(baseline, submitted, SHLD, along(a, sign * outer[side]),
                                     f"the {side} outside edge of shoulder, {outer[side]:g} ft {side}"))
        return verdict(first(*problems),
                       f"edges of pavement at {edge:g} ft and edges of shoulder at "
                       f"{outer['left']:g} ft left and {outer['right']:g} ft right, the length of SR-100")

    def solve(session):
        _say(session, f"{lanes} lane(s) each side × {lane:g} ft = {edge:g} ft from the centerline to "
                      f"the edge of pavement; plus the shoulder: {edge:g} + {shoulders['left']:g} = "
                      f"{outer['left']:g} ft on the left, {edge:g} + {shoulders['right']:g} = "
                      f"{outer['right']:g} ft on the right. Widths become offsets from the centerline, "
                      f"left negative.")
        run(session, "draw_offset", {"alignment": fixture.ALIGNMENT, "offsets": [-edge, edge],
                                     "layer": EOP})
        run(session, "draw_offset", {"alignment": fixture.ALIGNMENT,
                                     "offsets": [-outer["left"], outer["right"]], "layer": SHLD})

    note = (f"A width is not an offset: the shoulder edges are {edge:g} + {shoulders['left']:g} = "
            f"{outer['left']:g} ft left and {edge:g} + {shoulders['right']:g} = {outer['right']:g} ft "
            f"right of the centerline. Checked through both curves, so a chorded edge fails.")
    return Probe(id=pid, prompt=prompt, check=check, solve=solve, note=note, params=dict(p))


# ----------------------------------------------------------------------- registry

FAMILIES: List[Family] = [
    Family("callout-station", ["family", "find", "station", "paper"], "sheets",
           "a station-and-offset callout on one of the three sheets, in paper space",
           _make_callout, _build_callout),
    Family("draft-alignment", ["family", "draft", "alignment", "cogo"], "blank",
           "an alignment from northing and easting, bearings, distances, deflections and radii",
           _make_alignment, _build_alignment),
    Family("draft-offsets", ["family", "draft", "offsets"], "centerline",
           "edges of pavement and shoulder from lane counts and widths",
           _make_offsets, _build_offsets),
]

BY_ID: Dict[str, Family] = {f.id: f for f in FAMILIES}


def get(family_id: str) -> Family:
    if family_id not in BY_ID:
        raise KeyError(f"no probe family {family_id!r}; families: {', '.join(BY_ID)}")
    return BY_ID[family_id]


def is_instance(ref: str) -> bool:
    family, sep, seed = ref.partition(SEP)
    return bool(sep) and family in BY_ID and seed.isdigit()


def instance(ref: str) -> Probe:
    """The probe ``family@seed`` names."""
    family, sep, seed = ref.partition(SEP)
    if not sep or not seed.isdigit():
        raise KeyError(f"{ref!r} is not family@seed")
    return get(family).instance(int(seed))


def instances(family_id: str, seeds: Iterable[int]) -> List[Probe]:
    family = get(family_id)
    return [family.instance(s) for s in seeds]


def parse_seeds(text: str) -> List[int]:
    """``0-9``, ``3``, or ``0,2,5-7``."""
    out: List[int] = []
    for part in text.split(","):
        a, sep, b = part.strip().partition("-")
        out.extend(range(int(a), int(b) + 1) if sep else [int(a)])
    return out


__all__ = ["SEP", "Family", "FAMILIES", "BY_ID", "SHEET_STATIONS", "station_text", "get",
           "is_instance", "instance", "instances", "parse_seeds"]
