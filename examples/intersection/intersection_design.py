"""The design of the MAIN ST / CROSS AVE intersection, as numbers.

Two straight alignments crossing at 90 degrees.  MAIN ST carries three 12 ft
through lanes each way, CROSS AVE two, both divided by a 16 ft striped median.
Every approach gets a left-turn pocket taken out of the median and a
right-turn lane taken out of the curb line, each 300 ft of storage behind a
120 ft bay taper.  The corners are 50 ft curb returns with 6 ft curb and
gutter carried around them, and a curb ramp on each leg of each corner.

Offsets are feet, right of the direction of stationing positive -- so on MAIN
ST (eastbound stationing) a positive offset is south, and on CROSS AVE
(northbound stationing) it is east.
"""

# ------------------------------------------------------------ cross section
LANE = 12.0             # through and turn lane width
MEDIAN_HALF = 8.0       # 16 ft striped median, centred on the alignment
CURB_WIDTH = 6.0        # curb and gutter: face of curb to back of curb
CURB_HEIGHT = 0.5       # 6 in curb face, which is what a ramp has to climb
RAMP_HALF = 2.0         # 4 ft ramp
LT_SEPARATION = 4.0     # painted separation left of a left-turn pocket

# ------------------------------------------------------------- turn pockets
TURN_STORAGE = 300.0    # full-width storage, measured back from the curb return
BAY_TAPER = 120.0       # 12 ft over 120 ft = 10:1

# ------------------------------------------------------------- intersection
CURB_RETURN_R = 50.0
CROSSWALK_CLEAR = 10.0  # curb face to the far side of a crossing
LIMIT_LINE_SET = 4.0    # striping stops this far back from the crossing

# --------------------------------------------------------------- alignments
INTERSECTION = (5000.0, 5000.0)     # local project datum

ROADS = {
    "MAIN-ST": dict(
        description="MAIN ST, 6-lane divided arterial",
        azimuth=90.0,               # runs east
        thru_lanes=3,
        begin_station=1000.0,       # 10+00
        back_leg=800.0,             # feet of alignment west of the intersection
        ahead_leg=800.0,
    ),
    "CROSS-AVE": dict(
        description="CROSS AVE, 4-lane divided arterial",
        azimuth=0.0,                # runs north
        thru_lanes=2,
        begin_station=2000.0,       # 20+00
        back_leg=700.0,
        ahead_leg=700.0,
    ),
}


def thru_edge(road):
    """Offset of the through-lane curb face: median + the through lanes."""
    return MEDIAN_HALF + ROADS[road]["thru_lanes"] * LANE


def turn_edge(road):
    """Offset of the curb face alongside a right-turn lane."""
    return thru_edge(road) + LANE


def lane_lines(road):
    """Offsets of the lines between through lanes, nearest the median first."""
    return [MEDIAN_HALF + i * LANE for i in range(1, ROADS[road]["thru_lanes"])]


def pocket_edge():
    """Offset of the far edge of a left-turn pocket: it crosses the alignment."""
    return MEDIAN_HALF - LANE          # -4.0


def intersection_station(road):
    return ROADS[road]["begin_station"] + ROADS[road]["back_leg"]


def end_station(road):
    return intersection_station(road) + ROADS[road]["ahead_leg"]


def striping_gap(road):
    """How far from the intersection the striping on `road` stops: clear of the
    *other* road's curb, its crossing, and the limit line setback."""
    other = [r for r in ROADS if r != road][0]
    return thru_edge(other) + CROSSWALK_CLEAR + LIMIT_LINE_SET


# ---------------------------------------------------------------- approaches
# One per leg.  `sign` is +1 when traffic on that approach travels with the
# stationing (so the leg is behind the intersection) and -1 when against it.
APPROACHES = [
    dict(name="MAIN ST EB", road="MAIN-ST", sign=+1),
    dict(name="MAIN ST WB", road="MAIN-ST", sign=-1),
    dict(name="CROSS AVE NB", road="CROSS-AVE", sign=+1),
    dict(name="CROSS AVE SB", road="CROSS-AVE", sign=-1),
]


def approach_stations(road, sign):
    """(limit line, pocket start, taper start) stations on an approach.

    `sign` is the direction of travel; the approach is upstream of the
    intersection, so stations run toward it in the `sign` direction.
    """
    limit = intersection_station(road) - sign * striping_gap(road)
    pocket = limit - sign * TURN_STORAGE
    taper = pocket - sign * BAY_TAPER
    return limit, pocket, taper


def corner(main_off, cross_off):
    """A curb return corner: the two curb offsets it joins, the arc centre,
    and where it meets each curb.

    Both curb lines are straight and square to each other, so the centre sits
    one radius inside each of them and the tangent points are square across.
    Returns (centre_main_off, centre_cross_off).
    """
    r = CURB_RETURN_R
    return (main_off + r * _sgn(main_off), cross_off + r * _sgn(cross_off))


def _sgn(v):
    return 1.0 if v >= 0 else -1.0
