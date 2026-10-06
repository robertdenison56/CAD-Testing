"""The design data read off Caltrans sheet L-2 (03-But-70, PM 46.0/47.0), and
the sheet-to-model transform recovered from the published plan.

Everything here comes from what the sheet itself states: the CURVE DATA table
(R, delta, T, L), the BC/EC stations called out along "SR70" LINE, and the two
tangent bearing-and-distance labels. The radii are derived from L and delta
rather than read off the table, because the table rounds R to whole feet while
the stations are given to 0.01 ft -- deriving R is what makes the rebuilt
alignment reproduce every station the sheet prints.

The project has no published coordinates, so the alignment is laid out on a
local project datum with station 569+00 at (10000, 5000). The viewport
transform below was fitted to the published sheet (residual < 0.002 in over
the full 34 in width), so the recreated sheet frames the same ground.
"""
import math

# ---------------------------------------------------------------- curve data


def dms(d, m, s):
    return d + m / 60.0 + s / 3600.0


# CURVE DATA table, sheet L-2.  keys are the sheet's own curve numbers.
DELTA = {2: dms(16, 47, 27), 3: dms(11, 50, 53),
         4: dms(8, 44, 56), 5: dms(21, 17, 31)}
ARC_LEN = {2: 573.51, 3: 437.83, 4: 298.20, 5: 320.33}
TABLE_R = {2: 1957, 3: 2117, 4: 1953, 5: 862}          # as printed, whole feet
TABLE_T = {2: 288.83, 3: 219.70, 4: 149.39, 5: 162.04}

# R = L / delta: exact, and consistent with the printed T to 0.01 ft
RADIUS = {k: ARC_LEN[k] / math.radians(DELTA[k]) for k in DELTA}
TANGENT = {k: RADIUS[k] * math.tan(math.radians(DELTA[k]) / 2) for k in DELTA}

# bearing labelled on the 230.76 ft tangent; every curve turns left
AZ = {2: dms(78, 30, 50)}
AZ[1] = AZ[2] + DELTA[2]            # S 84-41-43 E, into curve 2
AZ[3] = AZ[2] - DELTA[3]            # N 66-39-57 E  (labelled on the sheet)
AZ[4] = AZ[3] - DELTA[4]            # N 57-55-01 E
AZ[5] = AZ[4] - DELTA[5]            # N 36-37-30 E

# BC/EC stations called out along the centerline
EC2_STA = 57616.93        # "SR70" 576+16.93 EC
BC3_STA = 57847.69        # "SR70" 578+47.69 BC
EC3_STA = 58285.52        # "SR70" 582+85.52 EC
BC4_STA = 58536.75        # "SR70" 585+36.75 BC
PCC_STA = 58834.95        # "SR70" 588+34.95 PCC  (EC of 4 = BC of 5)

TAN_2_3 = BC3_STA - EC2_STA        # 230.76, labelled
TAN_3_4 = BC4_STA - EC3_STA        # 251.23, labelled

BEGIN_STA = 56900.0                # where we start the alignment
END_STA = 59300.0
MATCH_W = 57450.0                  # MATCH LINE (L-1), left edge of the sheet
MATCH_E = 58950.0                  # MATCH LINE (L-3), right edge of the sheet

ALIGNMENT = "SR70"
BEGIN_POINT = (10000.0, 5000.0)    # local project datum, station 569+00

# ------------------------------------------------------------------ layout


def unit(az_deg):
    a = math.radians(az_deg)
    return (math.sin(a), math.cos(a))


def step(p, dist, az_deg):
    u = unit(az_deg)
    return (p[0] + dist * u[0], p[1] + dist * u[1])


def control_points():
    """PI list for create_alignment, walked from BEGIN along the stated
    bearings with the derived tangent distances."""
    bc2 = step(BEGIN_POINT, (EC2_STA - ARC_LEN[2]) - BEGIN_STA, AZ[1])
    pi2 = step(bc2, TANGENT[2], AZ[1])
    ec2 = step(pi2, TANGENT[2], AZ[2])
    bc3 = step(ec2, TAN_2_3, AZ[2])
    pi3 = step(bc3, TANGENT[3], AZ[2])
    ec3 = step(pi3, TANGENT[3], AZ[3])
    bc4 = step(ec3, TAN_3_4, AZ[3])
    pi4 = step(bc4, TANGENT[4], AZ[3])
    pcc = step(pi4, TANGENT[4], AZ[4])          # compound: EC4 == BC5
    pi5 = step(pcc, TANGENT[5], AZ[4])
    ec5 = step(pi5, TANGENT[5], AZ[5])
    end = step(ec5, END_STA - (PCC_STA + ARC_LEN[5]), AZ[5])
    return [list(BEGIN_POINT),
            [pi2[0], pi2[1], RADIUS[2]],
            [pi3[0], pi3[1], RADIUS[3]],
            [pi4[0], pi4[1], RADIUS[4]],
            [pi5[0], pi5[1], RADIUS[5]],
            list(end)]


# ---------------------------------------------- sheet <-> model (1" = 50')
# paper = R(TWIST) @ model / 50 + OFFSET, paper inches from the sheet's
# bottom-left corner.  Fitted to the four tangent endpoints of the published
# sheet; north is 6.457 deg clockwise of sheet-up.
FEET_PER_INCH = 50.0
TWIST_DEG = -6.4570
PAPER_OFFSET = (-218.144919, -67.269230)

SHEET_W, SHEET_H = 34.0, 22.0
# the published border: 1.9 in binding strip at the left, 0.5 in elsewhere
BORDER = (1.904, 0.503, 33.497, 21.498)


def _rot():
    a = math.radians(TWIST_DEG)
    return math.cos(a), math.sin(a)


def model_to_paper(p):
    c, s = _rot()
    return ((c * p[0] - s * p[1]) / FEET_PER_INCH + PAPER_OFFSET[0],
            (s * p[0] + c * p[1]) / FEET_PER_INCH + PAPER_OFFSET[1])


def paper_to_model(q):
    c, s = _rot()
    dx, dy = q[0] - PAPER_OFFSET[0], q[1] - PAPER_OFFSET[1]
    return ((c * dx + s * dy) * FEET_PER_INCH,
            (-s * dx + c * dy) * FEET_PER_INCH)


VIEWPORT_CENTER_PAPER = ((BORDER[0] + BORDER[2]) / 2, (BORDER[1] + BORDER[3]) / 2)
VIEWPORT_W = BORDER[2] - BORDER[0]
VIEWPORT_H = BORDER[3] - BORDER[1]
VIEWPORT_CENTER_MODEL = paper_to_model(VIEWPORT_CENTER_PAPER)
