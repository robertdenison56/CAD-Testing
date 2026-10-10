"""Sheet L-4 (Route 65, "65 LAYOUT-4"): the design data the sheet states, and the
sheet <-> model transform fitted to the published PDF.

The PPM example prints no coordinates, so the model sits on a local project datum:
the "D13" 678+43.61 POC = "IND1" 55+90.29 POT crossing is at E 10,000, N 10,000.
Paper positions are full-size inches on the 34 x 22 sheet (the PDF is an 11 x 17
print, shrunk to 95.445 % of half size; see PDF_SCALE / PDF_OFFSET).
"""
import math

# ------------------------------------------------------------- PDF calibration
# extracted coordinates are 2 x the 11x17 page; the drawing inside is 0.95445 of a
# 34 x 22 sheet, trim corner at (0.7602, 0.5002) -- measured off the border lines
PDF_SCALE = 0.95445
PDF_OFFSET = (0.7602, 0.5002)

FEET_PER_INCH = 50.0

def dms(d, m, s):
    return d + m / 60.0 + s / 3600.0

# "IND1" LINE: Industrial Avenue, one tangent N 17 31'07" E, 4833.49' long
IND1_AZ = dms(17, 31, 7.0)
IND1_POT = 5590.29                    # "IND1" 55+90.29 POT = "D13" 678+43.61 POC
IND1_POT_IN4 = 5972.49                # "IND1" 59+72.49 POT = "IN4" 683+40.13 POT
IND1_RANGE = (5000.0, 6400.0)         # what this base file carries of it

# "D13" LINE: Route 65, curve 3 (R 5000', D 41 17'58", T 1884.32', L 3604.04'),
# a left curve, BC 654+06.40 (sheet L-2) to EC 690+10.44 (sheet L-5)
D13_POC = 67843.61
D13_BC, D13_EC = 65406.40, 69010.44
D13_DELTA = dms(41, 17, 58.0)
D13_R = (D13_EC - D13_BC) / math.radians(D13_DELTA)     # 4999.97: reproduces the stations

# "IN4" LINE: the NB exit ramp, curve 36 (R 330', D 74 50'50", T 251.05', L 428.58'),
# a left curve, EC 681+58.69, then N 72 28'52.9" W 181.44' to the POT on "IND1"
IN4_POT = 68340.13
IN4_EC = 68158.69
IN4_TAN_AZ = 360.0 - dms(72, 28, 52.9)
IN4_DELTA = dms(74, 50, 50.0)
IN4_L = 428.58
IN4_R = IN4_L / math.radians(IN4_DELTA)                 # 328.08, see README: the table prints 330'
IN4_BC = IN4_EC - IN4_L

# model datum: the POC / POT
MODEL0 = (10000.0, 10000.0)
# where that point sits on the sheet, and the sheet's view twist -- fitted to the
# PDF: "IND1" ticks every 2.000 in, "D13" a 100.00 in (5000 ft) circle through
# its ticks 675-682 (rms 0.0013 in), crossing "IND1" at 55+90.29 (0.05 ft)
SHEET0 = (15.3242, 11.2702)
IND1_SHEET_ANGLE = 0.16947
TWIST_DEG = IND1_SHEET_ANGLE - (90.0 - IND1_AZ)          # -72.3119: model turned CW on paper


def az_vec(az):
    a = math.radians(az)
    return (math.sin(a), math.cos(a))


def sheet_to_model(p):
    t = math.radians(-TWIST_DEG)
    dx, dy = (p[0] - SHEET0[0]) * FEET_PER_INCH, (p[1] - SHEET0[1]) * FEET_PER_INCH
    return (MODEL0[0] + dx * math.cos(t) - dy * math.sin(t),
            MODEL0[1] + dx * math.sin(t) + dy * math.cos(t))


def model_to_sheet(p):
    t = math.radians(TWIST_DEG)
    dx, dy = (p[0] - MODEL0[0]) / FEET_PER_INCH, (p[1] - MODEL0[1]) / FEET_PER_INCH
    return (SHEET0[0] + dx * math.cos(t) - dy * math.sin(t),
            SHEET0[1] + dx * math.sin(t) + dy * math.cos(t))


def ind1_point(station):
    ux, uy = az_vec(IND1_AZ)
    d = station - IND1_POT
    return (MODEL0[0] + ux * d, MODEL0[1] + uy * d)


def ind1_pis():
    return [list(ind1_point(IND1_RANGE[0])), list(ind1_point(IND1_RANGE[1]))]


def _rot(v, deg):
    a = math.radians(deg)
    return (v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a))


def d13_pis():
    """BC, PI (with R) and EC of curve 3.  The POC is MODEL0; the curve's direction there
    comes from the sheet (the fitted circle's tangent), turned into the model."""
    # tangent direction at the POC, on the sheet: perpendicular to the radius, CCW
    cx, cy = D13_CENTER_SHEET
    rx, ry = SHEET0[0] - cx, SHEET0[1] - cy
    tang_sheet = math.degrees(math.atan2(rx, -ry))        # radius turned +90
    tang_model = tang_sheet - TWIST_DEG                   # math angle in the model
    poc_az = (90.0 - tang_model) % 360.0
    R = D13_R
    # left curve: centre to the left of travel
    left = az_vec(poc_az - 90.0)
    centre = (MODEL0[0] + left[0] * R, MODEL0[1] + left[1] * R)
    def on_arc(station):
        turn = math.degrees((station - D13_POC) / R)       # positive ahead = CCW
        v = (MODEL0[0] - centre[0], MODEL0[1] - centre[1])
        w = _rot(v, turn)
        return (centre[0] + w[0], centre[1] + w[1])
    bc, ec = on_arc(D13_BC), on_arc(D13_EC)
    az_bc = poc_az + math.degrees((D13_POC - D13_BC) / R)  # left curve: azimuth falls ahead
    T = R * math.tan(math.radians(D13_DELTA) / 2)
    u = az_vec(az_bc)
    pi = (bc[0] + u[0] * T, bc[1] + u[1] * T)
    return [list(bc), [pi[0], pi[1], R], list(ec)], poc_az

D13_CENTER_SHEET = (-56.07511, 81.28425)


def in4_pis():
    end = ind1_point(IND1_POT_IN4)
    u = az_vec(IN4_TAN_AZ)
    ec = (end[0] - u[0] * (IN4_POT - IN4_EC), end[1] - u[1] * (IN4_POT - IN4_EC))
    T = IN4_R * math.tan(math.radians(IN4_DELTA) / 2)
    pi = (ec[0] - u[0] * T, ec[1] - u[1] * T)
    back = az_vec(IN4_TAN_AZ + IN4_DELTA)                # left curve: back azimuth larger
    bc = (pi[0] - back[0] * T, pi[1] - back[1] * T)
    return [list(bc), [pi[0], pi[1], IN4_R], list(end)]
