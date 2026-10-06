"""What sheet L-2 says, and where it says it.

Paper positions are inches from the bottom-left corner of the 34 x 22 sheet,
read off the published plan.  Callouts name a station and offset on "SR70"
rather than a point, so the leaders are aimed through the referenced design
model and land on the geometry they describe.
"""

NOTES = [
    (2.716, 20.453, 0.175, "NOTES:"),
    (2.681, 20.124, 0.140, "1. FOR ACCURATE RIGHT OF WAY DATA, CONTACT"),
    (2.869, 19.914, 0.140, "RIGHT OF WAY ENGINEERING AT THE DISTRICT OFFICE."),
    (2.681, 19.646, 0.140, '2. FOR DETAILS NOT SHOWN, SEE "2018 STANDARD PLANS"'),
    (2.872, 19.436, 0.140, 'AND "2018 REVISED STANDARD PLANS."'),
]

# text that sits on the paper, square to it: (x, y, height, content)
PLACE_NAMES = [
    (8.376, 18.255, 0.175, "PLUMAS NATIONAL FOREST"),
    (14.747, 4.552, 0.175, "PLUMAS NATIONAL FOREST"),
]

# text laid along a feature: (x, y, height, rotation, content)
FEATURE_NAMES = [
    (11.660, 11.166, 0.150, 13.9, "North Fork Feather River"),
    (26.479, 11.470, 0.150, -22.7, "Bear Creek"),
    (14.383, 17.010, 0.150, 14.9, "UPRR"),
]

# text laid along the roadway: (x, y, height, content) -- the rotation comes
# from the alignment's own bearing where the label sits
ROAD_NAMES = [
    (11.889, 8.855, 0.175, "ROUTE 70"),
    (15.700, 9.484, 0.175, '"SR70" LINE'),
]

# curve number bubbles: (curve, x, y) -- radius 0.20 in, leader down to the road
BUBBLES = [(2, 4.383, 10.118), (3, 14.666, 10.987),
           (4, 26.285, 14.506), (5, 29.503, 15.814)]

MATCH_LINES = [
    # (station, sheet, text x, text y, height, rotation, back ft, ahead ft)
    (57450.0, "(L-1)", 2.622, 6.978, 0.140, 90.00, -95.0, 89.0),
    (58950.0, "(L-3)", 31.275, 15.689, 0.140, -55.80, -72.0, 89.0),
]

# (station, offset ft, text x, text y, content) -- offset right of stationing
# positive, so 21.00' Rt is +21.  y is the first line; the block is centred.
CALLOUTS = [
    (58657.73, -20.83, 19.458, 17.345,
     '"SR70" Sta 586+57.73, 20.83\' Lt\nBEGIN SOLDIER PILE WALL'),
    (58584.05, -20.83, 19.093, 16.595,
     '"SR70" Sta 585+84.05, 20.83\' Lt\nEND SOLDIER PILE WALL'),
    (58802.69, 21.00, 29.912, 12.148,
     '"SR 70" 588+02.69, 21.00\' Rt\nALTERNATIVE IN-LINE\nTERMINAL SYSTEM'),
    (58777.96, 21.00, 29.920, 11.374,
     '"SR70" 587+77.96, 21.00\' Rt\nEND MGS (STEEL POST)'),
    (58703.76, 21.00, 29.368, 10.655,
     '"SR70" 587+03.76, 21.00\' Rt\nBeg MGS (STEEL POST)'),
    (58648.00, 21.00, 29.281, 9.990, '"SR70" 586+48.00\nEND BRIDGE'),
    (58654.29, 21.00, 27.139, 8.315,
     '"SR 70" 586+54.29, 21.00\' Rt\nTRANSITION RAILING\n(TYPE WB-31)'),
    (58623.00, 0.00, 26.973, 7.408,
     "BEAR CREEK BRIDGE\nBr No. 12-0207\nREPLACE", 0.175),
    (58453.57, 21.00, 19.057, 8.616,
     '"SR 70" 584+53.57 21.00\' Rt\nALTERNATIVE IN-LINE\nTERMINAL SYSTEM'),
    (58503.57, 21.00, 19.594, 7.929,
     '"SR70" 585+03.57, 21.00\' Rt\nBeg MGS (STEEL POST)'),
    (58578.12, 21.00, 20.389, 7.329,
     '"SR70" 585+78.12, 21.00\' Rt\nEND MGS (STEEL POST)'),
    (58598.00, 0.00, 21.912, 6.548, '"SR70" 585+98.00\nBeg BRIDGE'),
    (58602.86, 21.00, 21.290, 4.344,
     '"SR70" 586+02.86, 21.00\' Rt\nTRANSITION RAILING\n(TYPE WB-31)'),
    (58648.00, 21.00, 21.575, 5.452,
     "INSTALL BRONZE PLAQUE\n4 TOTAL, 1 EACH END OF BRIDGE RAIL\n"
     "SEE LANDSCAPE DETAILS, LD-1"),
]

# right of way and typical-section lettering: (x, y, height, rotation, content)
SECTION_LABELS = [
    (3.257, 9.375, 0.150, 0.0, "R/W"),
    (3.391, 6.459, 0.150, 0.0, "R/W"),
    (30.122, 15.749, 0.150, 33.5, "R/W"),
    (31.507, 13.183, 0.150, 32.3, "R/W"),
    (2.937, 8.418, 0.140, 0.0, "8'"),
    (2.805, 8.219, 0.140, 0.0, "12'"),
    (2.805, 7.972, 0.140, 0.0, "12'"),
    (2.937, 7.777, 0.140, 0.0, "8'"),
]

# cut / fill lettering along the catch line: (x, y, height, content); the
# rotation comes from the roadway where each one sits
CATCH_LABELS = [
    (6.360, 7.656, 0.164, "C/F"), (8.917, 7.833, 0.171, "C/F"),
    (10.961, 8.013, 0.167, "F/C"), (13.320, 8.356, 0.182, "C/F"),
    (15.821, 8.817, 0.199, "C/F"), (18.304, 9.360, 0.177, "F/C"),
    (21.520, 10.230, 0.180, "C/F"), (23.569, 11.004, 0.180, "C/F"),
    (26.724, 12.120, 0.180, "F/C"), (28.361, 12.648, 0.195, "F/C"),
    (30.614, 13.719, 0.206, "C/F"),
]

# direction of travel: (x, y, content, arrow from x, arrow to x, y)
TRAVEL = [(6.466, 8.407, "WB", 7.30, 6.90, 8.470),
          (6.488, 8.168, "EB", 6.90, 7.30, 8.232)]

CURVE_TABLE = {
    "position": (3.923, 4.090),
    "title": "CURVE DATA",
    "title_height": 0.200,
    "text_height": 0.140,
    "row_height": 0.280,
    "columns": [("No.  ⊗", 1.399), ("R", 1.400), ("Δ", 2.100),
                ("T", 1.399), ("L", 1.400)],
}

# The north arrow, as drawn on the plan but turned true north up, so it is
# inserted at the sheet's view twist. Inches, about the compass rose centre.
NORTH_ARROW = [
    ("circle", 0.181),
    ("line", [[-0.230, 0.026], [0.227, -0.026]]),
    ("line", [[0.169, 1.490], [-0.157, -1.391]]),
    ("line", [[-0.157, -1.391], [-0.069, -1.502]]),
    ("line", [[-0.157, -1.391], [-0.268, -1.479]]),
    ("line", [[-0.167, -0.585], [-0.268, -1.479]]),
    ("line", [[0.032, -0.607], [-0.069, -1.502]]),
    ("line", [[-0.056, -0.497], [-0.167, -0.585]]),
    ("line", [[-0.056, -0.497], [0.032, -0.607]]),
    ("line", [[0.068, 0.596], [-0.043, 0.508]]),
    ("line", [[0.068, 0.596], [0.156, 0.485]]),
    ("line", [[-0.043, 0.508], [0.169, 1.490]]),
    ("line", [[0.169, 1.490], [0.156, 0.485]]),
    ("line", [[-0.151, -0.573], [-0.252, -1.467]]),
    ("line", [[-0.135, -0.560], [-0.236, -1.454]]),
    ("line", [[-0.119, -0.547], [-0.220, -1.441]]),
    ("line", [[-0.103, -0.535], [-0.205, -1.429]]),
    ("line", [[-0.088, -0.522], [-0.189, -1.416]]),
    ("line", [[-0.072, -0.510], [-0.173, -1.404]]),
    ("line", [[0.080, 0.580], [0.167, 1.346]]),
    ("line", [[0.093, 0.564], [0.165, 1.203]]),
    ("line", [[0.105, 0.548], [0.163, 1.059]]),
    ("line", [[0.118, 0.533], [0.161, 0.916]]),
    ("line", [[0.131, 0.517], [0.159, 0.773]]),
    ("line", [[0.143, 0.501], [0.158, 0.629]]),
]
NORTH_ARROW_AT = (14.161, 19.185)

TITLE_BLOCK = {
    "dist": "03", "county": "But", "route": "70",
    "post_miles": "46.0/47.0", "sheet_number": "6", "total_sheets": "179",
    "agency": "STATE OF CALIFORNIA  -  DEPARTMENT OF TRANSPORTATION",
    "division": "DESIGN",
    "functional_supervisor": "SOCORRO URENA",
    "designed_by": "NUR TARAKY",
    "checked_by": "JAROSLAW J. KUSZ",
    "registered_civil_engineer": "Jaroslaw Kusz",
    "re_date": "7-25-22",
    "plans_approval_date": "7-25-22",
    "disclaimer": "THE STATE OF CALIFORNIA OR ITS OFFICERS\n"
                  "OR AGENTS SHALL NOT BE RESPONSIBLE FOR\n"
                  "THE ACCURACY OR COMPLETENESS OF SCANNED\n"
                  "COPIES OF THIS PLAN SHEET.",
    "seal_name": "JAROSLAW\nJ. KUSZ",
    "seal_number": "No.  C79834",
    "seal_expires": "Exp. 09/30/22",
    "unit": "UNIT 0335",
    "project_number_phase": "PROJECT NUMBER & PHASE   03180000121",
    "border_revised": "BORDER LAST REVISED 7/2/2010",
    "username": "USERNAME =>  s119538",
    "dgn_file": "DGN FILE =>  0318000012ea002.dgn",
    "date_plotted": "DATE PLOTTED =>  22-SEP-2022",
    "time_plotted": "TIME PLOTTED =>  12:26",
    "sheet_title": "LAYOUT",
    "scale": "SCALE:  1\" = 50'",
    "sheet_id": "L-2",
}
