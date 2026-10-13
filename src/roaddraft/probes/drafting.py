"""Drafting-probes: can an agent draft design data from a description?

The find-probes ask an agent to locate something that exists and point at it.
These ask for the other half of the job: there is nothing there yet, and an
engineer says what to draw -- an alignment, the pavement on it, a turn lane, a
building -- the way engineers say it: northings and eastings, bearings and
distances, deflections, stations and offsets, lane and shoulder widths.

Like the find-probes these are capability probes, not the scored benchmark: no
rubric, no spec hash, no task ids. And like them they judge what was left
behind, not how it got there. An alignment counts if the document's design
model carries one that *runs where it was described* -- built from PIs or from
elements, it does not matter. Linework counts if it *lies where it should*:
the expected path is sampled every few feet and each sample must have added
linework within ``TOLERANCE_FT`` of it, so an edge of pavement from
``draw_offset`` scores exactly like one composed of lines and arcs by hand,
while a curve faked with a chord does not. Where a description says where
something stops, the check also looks past the end for linework that should
not be there.

``TOLERANCE_FT`` is 0.5 ft (0.01 in at 1"=50'). That is far looser than design
data is kept (0.01 ft) and is set where it is on purpose: coordinates worked
out from a bearing with four-figure sines land inside it, a shoulder drawn at
its width instead of its offset does not, and neither does a swapped northing
and easting.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.design.errors import DesignError
from roaddraft.design.labels import caltrans_station_text
from roaddraft.document.entities import Text, entity_distance
from roaddraft.probes import fixture
from roaddraft.probes.base import Probe, Result

TOLERANCE_FT = 0.5
SAMPLE_FT = 25.0

CL, EOP, SHLD, NOTE = "align_MAIN", "rd_EP", "rd_ES", "rd_LAYOUT-NOTE-anno"


# ------------------------------------------------------------------ geometry


def traverse(start: Sequence[float], legs: Sequence[Tuple[float, float]]) -> List[List[float]]:
    """Points reached from ``start`` [E, N] by ``(azimuth_deg, distance)`` legs.
    Azimuth is clockwise from north, the way a bearing is."""
    points = [[float(start[0]), float(start[1])]]
    for azimuth, distance in legs:
        a = math.radians(azimuth)
        x, y = points[-1]
        points.append([x + distance * math.sin(a), y + distance * math.cos(a)])
    return points


def expected_alignment(name: str, pis, begin_station):
    """The alignment a description means, built by the engine itself."""
    s = Session(project_name="expected")
    r = s.execute("create_alignment", {"name": name, "pis": pis,
                                       "begin_station": begin_station})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return s.doc.design.alignments[name]


def along(alignment, offset: float = 0.0, start: Optional[float] = None,
          end: Optional[float] = None, step: float = SAMPLE_FT) -> List[List[float]]:
    """Points every ``step`` ft along an alignment at an offset (right +),
    between two raw stations, both ends included."""
    lo = alignment.begin_station if start is None else float(start)
    hi = alignment.end_station if end is None else float(end)
    n = max(1, int(math.ceil((hi - lo) / step)))
    stations = [lo + (hi - lo) * i / n for i in range(n + 1)]
    return [alignment.station_to_xy(st, offset)[0] for st in stations]


def between(a, b, step: float = 5.0) -> List[List[float]]:
    n = max(1, int(math.ceil(math.dist(a, b) / step)))
    return [[a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n]
            for i in range(n + 1)]


# ------------------------------------------------------------------- checking


def added(baseline: Session, submitted: Session, layer: Optional[str] = None):
    """Model entities the submission added, optionally only those on a layer."""
    before = set(baseline.doc.model_entities)
    return [e for eid, e in submitted.doc.model_entities.items()
            if eid not in before and not isinstance(e, Text)
            and (layer is None or e.layer == layer)]


def _gap(doc, entities, point) -> float:
    return min((entity_distance(doc, e, point) for e in entities), default=math.inf)


def covered(submitted: Session, entities, points, what: str) -> Optional[str]:
    """None when every point has linework on it; otherwise what is missing."""
    if not entities:
        return f"nothing drawn for {what}"
    misses = [(p, _gap(submitted.doc, entities, p)) for p in points]
    misses = [(p, d) for p, d in misses if d > TOLERANCE_FT]
    if not misses:
        return None
    worst = max(misses, key=lambda m: m[1])
    return (f"{what}: {len(misses)} of {len(points)} check points have no linework "
            f"within {TOLERANCE_FT} ft; the worst is [{worst[0][0]:.2f}, "
            f"{worst[0][1]:.2f}], {worst[1]:.2f} ft from the nearest")


def clear(submitted: Session, entities, points, what: str) -> Optional[str]:
    """None when no point has linework on it; otherwise where it runs on."""
    hits = [p for p in points if _gap(submitted.doc, entities, p) <= TOLERANCE_FT]
    if not hits:
        return None
    return (f"{what}: linework runs through [{hits[0][0]:.2f}, {hits[0][1]:.2f}] "
            f"({len(hits)} of {len(points)} check points), where there should be none")


def on_layer(baseline: Session, submitted: Session, layer: str, points, what: str) -> Optional[str]:
    """Coverage by added linework on the layer that was asked for. When the
    linework is there but on another layer, say so: that is a different
    mistake from not drawing it."""
    problem = covered(submitted, added(baseline, submitted, layer), points, what)
    if problem is None:
        return None
    anywhere = added(baseline, submitted)
    if anywhere and covered(submitted, anywhere, points, what) is None:
        layers = sorted({e.layer for e in anywhere})
        return f"{what} is drawn, but not on {layer} (added linework is on {layers})"
    return problem


def alignment_runs(submitted: Session, name: str, expected) -> Optional[str]:
    """None when the design model has ``name`` running where ``expected`` runs."""
    aligns = submitted.doc.design.alignments
    found = next((a for key, a in aligns.items() if key.upper() == name.upper()), None)
    if found is None:
        if aligns:
            return f"no alignment named {name}; the design model has {sorted(aligns)}"
        drawn = len(submitted.doc.model_entities)
        return (f"the design model has no alignment"
                + (f" ({drawn} entities were drawn, but linework is not an alignment: it "
                   f"has no stations)" if drawn else ""))
    if abs(found.begin_station - expected.begin_station) > 0.01:
        return (f"{name} begins at station {found.stations().begin_text()}, not "
                f"{expected.stations().begin_text()}")
    for label, want, got in (("begins", expected.point_at(0.0), found.point_at(0.0)),
                             ("ends", expected.point_at(expected.length),
                              found.point_at(found.length))):
        off = math.dist(want, got)
        if off > TOLERANCE_FT:
            return (f"{name} {label} at [{got[0]:.2f}, {got[1]:.2f}], {off:.2f} ft from "
                    f"[{want[0]:.2f}, {want[1]:.2f}] where it was described")
    if abs(found.length - expected.length) > TOLERANCE_FT:
        return f"{name} is {found.length:.2f} ft long, not {expected.length:.2f}"
    worst = (0.0, None)
    ends = (found.point_at(0.0), found.point_at(found.length))
    for point in along(expected, step=SAMPLE_FT):
        # A point just past either end has no perpendicular station, and an
        # alignment a hair short of its description is not thereby miles off:
        # measure to the end it ran past instead.
        off = min(math.dist(point, end) for end in ends)
        try:
            off = min(off, abs(found.xy_to_station(point)["offset"]))
        except DesignError:
            pass
        if off > worst[0]:
            worst = (off, point)
    if worst[0] > TOLERANCE_FT:
        return (f"{name} leaves its described path by {worst[0]:.2f} ft near "
                f"[{worst[1][0]:.2f}, {worst[1][1]:.2f}] (a curve of the wrong radius, or "
                f"a PI out of place)")
    return None


def first(*problems: Optional[str]) -> Optional[str]:
    return next((p for p in problems if p), None)


def verdict(problem: Optional[str], good: str) -> Result:
    return Result(False, problem) if problem else Result(True, good)


def run(session: Session, name: str, params: dict) -> dict:
    r = session.execute(name, params)
    if not r["ok"]:
        raise RuntimeError(f"{name}: {r['error']['message']}")
    return r


# --------------------------------------------------------------------- probes

# 1. northing / easting ---------------------------------------------------------

NE = {"name": "MAIN-ST", "pis": [[2000.0, 5000.0], [3200.0, 5000.0]], "begin": "10+00"}


def _check_ne(baseline, submitted):
    want = expected_alignment(NE["name"], NE["pis"], NE["begin"])
    return verdict(first(alignment_runs(submitted, NE["name"], want),
                         on_layer(baseline, submitted, CL, along(want), "the centerline")),
                   "MAIN-ST runs due east from N 5000, E 2000 and is drawn")


def _solve_ne(session):
    run(session, "create_alignment", {"name": NE["name"], "pis": NE["pis"],
                                      "begin_station": NE["begin"]})
    run(session, "draw_alignment", {"alignment": NE["name"], "layer": CL})


# 2. PIs and a curve ------------------------------------------------------------

PIC = {"name": "SR-9", "begin": "50+00",
       "pis": [[1000.0, 1000.0], [2200.0, 1000.0, 800.0], [3100.0, 1900.0]]}


def _check_pi_curve(baseline, submitted):
    want = expected_alignment(PIC["name"], PIC["pis"], PIC["begin"])
    return verdict(first(alignment_runs(submitted, PIC["name"], want),
                         on_layer(baseline, submitted, CL, along(want), "the centerline")),
                   "SR-9 runs through its PIs on an 800 ft curve and is drawn")


def _solve_pi_curve(session):
    run(session, "create_alignment", {"name": PIC["name"], "pis": PIC["pis"],
                                      "begin_station": PIC["begin"]})
    run(session, "draw_alignment", {"alignment": PIC["name"], "layer": CL})


# 3. bearing, distance, deflection ------------------------------------------------

BD = {"name": "RAMP-B", "begin": "10+00", "start": [1000.0, 1000.0],
      "legs": [(62.5, 900.0), (97.5, 1100.0)], "radius": 600.0}


def _bd_pis():
    p = traverse(BD["start"], BD["legs"])
    return [p[0], [p[1][0], p[1][1], BD["radius"]], p[2]]


def _check_bearing(baseline, submitted):
    want = expected_alignment(BD["name"], _bd_pis(), BD["begin"])
    return verdict(first(alignment_runs(submitted, BD["name"], want),
                         on_layer(baseline, submitted, CL, along(want), "the centerline")),
                   "RAMP-B runs N 62°30' E, deflects 35° right on a 600 ft curve, "
                   "and is drawn")


def _solve_bearing(session):
    # The script does the trigonometry in Python. An agent working through the
    # tool surface has no such thing, which is what this probe is here to see.
    run(session, "create_alignment", {"name": BD["name"], "pis": _bd_pis(),
                                      "begin_station": BD["begin"]})
    run(session, "draw_alignment", {"alignment": BD["name"], "layer": CL})


# 4. lanes and shoulders ---------------------------------------------------------


def _sr100(session: Session):
    return session.doc.design.alignments[fixture.ALIGNMENT]


def _check_edges(baseline, submitted):
    a = _sr100(baseline)
    problems = []
    for layer, offset, what in ((EOP, -12.0, "the left edge of pavement"),
                                (EOP, 12.0, "the right edge of pavement"),
                                (SHLD, -20.0, "the left edge of shoulder"),
                                (SHLD, 20.0, "the right edge of shoulder")):
        problems.append(on_layer(baseline, submitted, layer, along(a, offset), what))
    return verdict(first(*problems),
                   "edges of pavement at 12 ft and edges of shoulder at 20 ft, both sides, "
                   "the length of SR-100")


def _solve_edges(session):
    run(session, "draw_offset", {"alignment": fixture.ALIGNMENT, "offsets": [-12, 12],
                                 "layer": EOP})
    run(session, "draw_offset", {"alignment": fixture.ALIGNMENT, "offsets": [-20, 20],
                                 "layer": SHLD})


# 5. a turn lane -----------------------------------------------------------------

TL = {"taper_from": 3000.0, "full_from": 3120.0, "to": 3600.0, "edge": 12.0, "lane": 24.0}


def _turn_lane_points(a):
    p = lambda st, off: a.station_to_xy(st, off)[0]  # noqa: E731
    return {"taper": between(p(TL["taper_from"], TL["edge"]), p(TL["full_from"], TL["lane"])),
            "full": along(a, TL["lane"], TL["full_from"], TL["to"], step=20.0),
            "end": between(p(TL["to"], TL["lane"]), p(TL["to"], TL["edge"]), step=2.0),
            "before": along(a, TL["lane"], TL["taper_from"] - 150.0,
                            TL["full_from"] - 20.0, step=10.0),
            "after": along(a, TL["lane"], TL["to"] + 20.0, TL["to"] + 200.0, step=10.0)}


def _check_turn_lane(baseline, submitted):
    pts = _turn_lane_points(_sr100(baseline))
    new = added(baseline, submitted)
    return verdict(first(
        on_layer(baseline, submitted, EOP, pts["full"], "the full-width edge, 24 ft right"),
        on_layer(baseline, submitted, EOP, pts["taper"], "the 120 ft taper"),
        on_layer(baseline, submitted, EOP, pts["end"], "the square end at 36+00"),
        clear(submitted, new, pts["before"], "24 ft right, back of 31+20"),
        clear(submitted, new, pts["after"], "24 ft right, ahead of 36+00")),
        "taper 30+00 to 31+20, full width to 36+00, squared off, and nothing beyond")


def station_point(session: Session, alignment: str, station, offset: float = 0.0):
    """Where a station and offset is, asked of the engine the way a model asks."""
    r = session.query("station_to_xy", {"alignment": alignment, "station": station,
                                        "offset": offset})
    if not r["ok"]:
        raise RuntimeError(r["error"]["message"])
    return r["point"]


def _solve_turn_lane(session):
    p = lambda st, off: station_point(session, fixture.ALIGNMENT, st, off)  # noqa: E731
    run(session, "draw_line", {"space": "model", "layer": EOP,
                               "start": p(TL["taper_from"], TL["edge"]),
                               "end": p(TL["full_from"], TL["lane"])})
    run(session, "draw_offset", {"alignment": fixture.ALIGNMENT, "offsets": [TL["lane"]],
                                 "station_range": ["31+20", "36+00"], "layer": EOP})
    run(session, "draw_line", {"space": "model", "layer": EOP,
                               "start": p(TL["to"], TL["lane"]), "end": p(TL["to"], TL["edge"])})


# 6. a cul-de-sac ----------------------------------------------------------------

CDS = {"name": "OAK-CT", "begin": "10+00", "pis": [[3000.0, 2000.0], [3000.0, 2400.0]],
       "half_width": 14.0, "bulb": 45.0}


def _cds_throat() -> float:
    """Raw station where a 14 ft edge meets the 45 ft bulb."""
    return 1400.0 - math.sqrt(CDS["bulb"] ** 2 - CDS["half_width"] ** 2)


def _check_cul_de_sac(baseline, submitted):
    want = expected_alignment(CDS["name"], CDS["pis"], CDS["begin"])
    center, r, w = want.point_at(want.length), CDS["bulb"], CDS["half_width"]
    # the bulb, less the mouth between the two edges (a drafter may trim it out)
    bulb = [[center[0] + r * math.cos(math.radians(t)), center[1] + r * math.sin(math.radians(t))]
            for t in range(0, 360, 5)]
    bulb = [q for q in bulb if not (abs(q[0] - center[0]) < w + 1.0 and q[1] < center[1])]
    throat = _cds_throat()
    new = added(baseline, submitted)
    problems = [alignment_runs(submitted, CDS["name"], want),
                on_layer(baseline, submitted, EOP, bulb, "the 45 ft bulb")]
    for side, offset in (("left", -w), ("right", w)):
        problems.append(on_layer(baseline, submitted, EOP,
                                 along(want, offset, 1000.0, throat - 1.0),
                                 f"the {side} edge of pavement up to the bulb"))
        problems.append(clear(submitted, new, along(want, offset, throat + 3.0, 1395.0, 4.0),
                              f"the {side} edge inside the bulb"))
    return verdict(first(*problems),
                   "OAK-CT with its bulb, and edges of pavement that stop where they meet it")


def _solve_cul_de_sac(session):
    run(session, "create_alignment", {"name": CDS["name"], "pis": CDS["pis"],
                                      "begin_station": CDS["begin"]})
    run(session, "draw_alignment", {"alignment": CDS["name"], "layer": CL})
    end = session.query("resolve_anchor", {"alignment": CDS["name"], "anchor": "END"})
    run(session, "draw_circle", {"space": "model", "layer": EOP,
                                 "center": end["anchor_point"], "radius": CDS["bulb"]})
    throat = _cds_throat()
    run(session, "draw_offset", {"alignment": CDS["name"], "layer": EOP,
                                 "offsets": [-CDS["half_width"], CDS["half_width"]],
                                 "station_range": [1000.0, round(throat, 2)]})


# 7. a building ------------------------------------------------------------------

BLDG = {"layer": "BUILDING", "corner": [1500.0, 1200.0], "azimuth": 30.0,
        "long": 60.0, "short": 40.0}


def _bldg_corners():
    c, az = BLDG["corner"], BLDG["azimuth"]
    p1 = traverse(c, [(az, BLDG["long"])])[1]
    p3 = traverse(c, [(az + 90.0, BLDG["short"])])[1]
    p2 = traverse(p1, [(az + 90.0, BLDG["short"])])[1]
    return [c, p1, p2, p3]


def _check_building(baseline, submitted):
    corners = _bldg_corners()
    if BLDG["layer"] not in submitted.doc.layers:
        return Result(False, f"there is no layer {BLDG['layer']}")
    sides = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        sides += between(a, b, step=5.0)
    return verdict(on_layer(baseline, submitted, BLDG["layer"], sides,
                            "the 60 x 40 building footprint"),
                   "a 60 x 40 ft footprint, long side N 30° E, on BUILDING")


def _solve_building(session):
    run(session, "create_layer", {"name": BLDG["layer"], "color": "black"})
    run(session, "draw_polyline", {"space": "model", "layer": BLDG["layer"],
                                   "vertices": _bldg_corners(), "closed": True})


# 8. the whole roadway -----------------------------------------------------------

ELM = {"name": "ELM-AVE", "begin": "10+00", "start": [1000.0, 3000.0],
       "legs": [(100.0, 800.0), (60.0, 700.0), (85.0, 600.0)], "radii": [500.0, 700.0],
       "lane": 11.0, "shoulder": 16.0}


def _elm_pis():
    p = traverse(ELM["start"], ELM["legs"])
    return [p[0], [*p[1], ELM["radii"][0]], [*p[2], ELM["radii"][1]], p[3]]


def _check_roadway(baseline, submitted):
    want = expected_alignment(ELM["name"], _elm_pis(), ELM["begin"])
    problems = [alignment_runs(submitted, ELM["name"], want),
                on_layer(baseline, submitted, CL, along(want), "the centerline")]
    for layer, offset, what in ((EOP, -ELM["lane"], "the left edge of pavement"),
                                (EOP, ELM["lane"], "the right edge of pavement"),
                                (SHLD, -ELM["shoulder"], "the left edge of shoulder"),
                                (SHLD, ELM["shoulder"], "the right edge of shoulder")):
        problems.append(on_layer(baseline, submitted, layer, along(want, offset), what))
    problem = first(*problems)
    if problem:
        return Result(False, problem)
    # a station label every 100 ft: text that reads the station, near that station --
    # in full (12+00) or the Caltrans way (the whole number at each 500 ft, the ones
    # digit elsewhere), which is how the engine letters it
    before = set(baseline.doc.model_entities)
    texts = [e for eid, e in submitted.doc.model_entities.items()
             if eid not in before and isinstance(e, Text)]
    stations = range(1000, int(want.end_station) + 1, 100)
    labelled = 0
    for st in stations:
        reads = f"{st // 100}+00"
        digits = caltrans_station_text(float(st))
        here = want.station_to_xy(float(st))[0]
        if any((reads in t.content or t.content.strip() == digits)
               and math.dist(t.position, here) <= 60.0 for t in texts):
            labelled += 1
    if labelled < 0.8 * len(stations):
        return Result(False, f"only {labelled} of {len(stations)} 100 ft stations carry a "
                             f"label that reads the station, within 60 ft of it")
    return Result(True, f"ELM-AVE from its bearings, lanes and shoulders both sides, "
                        f"{labelled} of {len(stations)} stations labelled")


def _solve_roadway(session):
    run(session, "create_alignment", {"name": ELM["name"], "pis": _elm_pis(),
                                      "begin_station": ELM["begin"]})
    run(session, "draw_alignment", {"alignment": ELM["name"], "layer": CL})
    run(session, "draw_offset", {"alignment": ELM["name"], "layer": EOP,
                                 "offsets": [-ELM["lane"], ELM["lane"]]})
    run(session, "draw_offset", {"alignment": ELM["name"], "layer": SHLD,
                                 "offsets": [-ELM["shoulder"], ELM["shoulder"]]})
    run(session, "annotate_stationing", {"alignment": ELM["name"], "space": "model",
                                         "interval": 100, "layer": NOTE})


DRAFT_PROBES: List[Probe] = [
    Probe(id="draft-tangent-ne", start="blank", tags=["draft", "alignment"],
          prompt="Create an alignment named MAIN-ST. It begins at N 5000.00, E 2000.00, "
                 "station 10+00, and runs due east for 1,200.00 ft. Draw its centerline "
                 "on layer align_MAIN.",
          check=_check_ne, solve=_solve_ne,
          note="Engineers give coordinates northing first; the engine takes [x, y], which "
               "is [easting, northing]. Swapped, the alignment starts 4,243 ft away."),
    Probe(id="draft-pi-curve", start="blank", tags=["draft", "alignment", "curve"],
          prompt="Create alignment SR-9, beginning at station 50+00, through these points "
                 "(easting, northing): begin at (1000, 1000); a PI at (2200, 1000) with an "
                 "800 ft radius curve; end at (3100, 1900). Draw its centerline on layer "
                 "align_MAIN.",
          check=_check_pi_curve, solve=_solve_pi_curve,
          note="The alignment does not pass through its PI: at this 45 degree deflection "
               "the curve runs 65.9 ft inside it. Lines drawn PI to PI are not the road, "
               "and linework alone is not an alignment -- it has no stations."),
    Probe(id="draft-bearing-distance", start="blank", tags=["draft", "alignment", "cogo"],
          prompt="Create alignment RAMP-B. It begins at N 1000.00, E 1000.00, station "
                 "10+00, and runs N 62°30'00\" E for 900.00 ft to a PI. There it "
                 "deflects 35°00'00\" to the right and continues 1,100.00 ft to its "
                 "end. Use a 600 ft radius curve at the PI. Draw its centerline on layer "
                 "align_MAIN.",
          check=_check_bearing, solve=_solve_bearing,
          note="How alignments are actually described. Distances are PI to PI. The engine "
               "reports bearings everywhere but takes none as input, so the PI and the end "
               "have to be worked out: PI = [1798.31, 1415.57], end = [2888.90, 1271.99]."),
    Probe(id="draft-edges-shoulders", start="centerline", tags=["draft", "offsets"],
          prompt="SR-100 is a two-lane highway with 12 ft lanes and 8 ft paved shoulders. "
                 "Its alignment is designed and drawn; nothing else is. Draw the edges of "
                 "pavement on layer rd_EP and the outside edges of shoulder on layer "
                 "rd_ES, both sides, for the whole length.",
          check=_check_edges, solve=_solve_edges,
          note="A width is not an offset: the shoulder edge is 12 + 8 = 20 ft from the "
               "centerline, not 8. Checked through both curves, so a chorded edge fails."),
    Probe(id="draft-turn-lane", start="model", tags=["draft", "offsets", "stations"],
          prompt="Add a right-turn lane to SR-100, on the right side: 12 ft wide, full "
                 "width from station 31+20 to station 36+00, opened by a 120 ft straight "
                 "taper that leaves the existing edge of pavement at station 30+00. Draw "
                 "the new edge of pavement on layer rd_EP -- the taper, the full-width "
                 "edge, and a square end at 36+00 back to the existing edge.",
          check=_check_turn_lane, solve=_solve_turn_lane,
          note="Station-and-offset drafting: the existing edge is 12 ft right, so the new "
               "one is 24 ft right, and only between the stations given. The check looks "
               "past both ends for an edge that ran on."),
    Probe(id="draft-cul-de-sac", start="blank", tags=["draft", "alignment", "geometry"],
          prompt="Create alignment OAK-CT: it begins at N 2000.00, E 3000.00, station "
                 "10+00, and runs due north for 400.00 ft. Draw its centerline on layer "
                 "align_MAIN. It ends in a cul-de-sac: on layer rd_EP draw the bulb, "
                 "a 45 ft radius circle centered on the end of the alignment, and the edges "
                 "of pavement 14 ft either side of the centerline, from the beginning to "
                 "where they meet the bulb -- not through it.",
          check=_check_cul_de_sac, solve=_solve_cul_de_sac,
          note="Where a 14 ft edge meets a 45 ft bulb is sqrt(45^2 - 14^2) = 42.77 ft short "
               "of the end: station 13+57.23. Edges drawn the full length run through the "
               "bulb, which is the mistake the check looks for."),
    Probe(id="draft-building", start="blank", tags=["draft", "geometry", "cogo"],
          prompt="Draw a building footprint on a new layer named BUILDING: a 60 ft by 40 ft "
                 "rectangle. One corner is at N 1200.00, E 1500.00. From that corner the "
                 "60 ft side runs N 30°00'00\" E, and the 40 ft side runs at a right "
                 "angle to it, to the right (S 60°00'00\" E).",
          check=_check_building, solve=_solve_building,
          note="Plain 2D geometry, turned off-axis. The layer does not exist yet. Corners: "
               "[1500, 1200], [1530, 1251.96], [1564.64, 1231.96], [1534.64, 1180]."),
    Probe(id="draft-roadway", start="blank", tags=["draft", "alignment", "cogo", "whole-job"],
          prompt="Draft the design model for ELM-AVE. The alignment begins at N 3000.00, "
                 "E 1000.00, station 10+00. It runs S 80°00'00\" E for 800.00 ft to "
                 "PI-1, where it deflects 40°00'00\" to the left on a 500 ft radius "
                 "curve; then 700.00 ft to PI-2, where it deflects 25°00'00\" to the "
                 "right on a 700 ft radius curve; then 600.00 ft to its end. It has two "
                 "11 ft lanes and 5 ft shoulders. Draw the centerline on align_MAIN, the "
                 "edges of pavement on rd_EP and the outside edges of shoulder on "
                 "rd_ES, and label the stations every 100 ft.",
          check=_check_roadway, solve=_solve_roadway,
          note="The whole T1 job in one instruction: two deflections to carry a bearing "
               "through (S 80 E, then N 60 E, then N 85 E), widths to turn into offsets "
               "(11 and 16), and stationing. Error in the first PI carries to the end."),
]

__all__ = ["TOLERANCE_FT", "DRAFT_PROBES", "traverse", "expected_alignment", "along",
           "between", "added", "covered", "clear", "on_layer", "alignment_runs"]
