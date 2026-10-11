"""What the FDOT (FDM 900-series, NexGen) exhibit sheets do differently from the FLH
ones, as a wflsheet.Standard: the border is FDOT's 11 x 17 frame with the title
strip across its foot (revisions, engineer of record, agency, sheet title, sheet
number), sheets are classed by their FDM exhibit number, and the strip is read cell
by cell.  Station ticks are lettered the WFL way (the hundreds, "702", beside the
tick).  The digitiser is wflsheet.digitise under this standard.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wfl_redraft"))

import wflsheet                                                     # noqa: E402
from wflsheet import cell_text, join_lines, run_center               # noqa: E402

FRAME = (0.8, 0.3, 16.2, 10.7)
STRIP_TOP = 1.1
REV_X1, EOR_X1, AGY_X1, TTL_X1 = 6.56, 8.9, 11.9, 15.5
PLAN_FAMILIES = {"plan-profile", "drainage", "drainage-map", "landscape", "soil", "utility",
                 "clearing", "concept"}

# FDM exhibit number -> (family, kind hint)
EXHIBITS = {
    "904": ("landscape", None), "906": ("hydraulics", "sheet"), "907": ("concept", None),
    "910": ("key", "sheet"), "911": ("model-management", "sheet"), "912": ("control", "sheet"),
    "913": ("typical", "sheet"), "914": ("notes", "sheet"), "915": ("plan-profile", None),
    "916": ("drainage", None), "918": ("drainage-map", None), "920": ("soil", None),
    "923": ("utility", None), "924": ("clearing", None), "925": ("xs", "sheet"),
}


def exhibit_of(rel):
    m = re.match(r"^FDOT-(\d{3})-(\d+)", rel.split("/")[-1])
    return (m.group(1), int(m.group(2))) if m else (None, None)


def family_of(rel, fields):
    stem = rel.split("/")[-1].lower()
    ex, n = exhibit_of(rel)
    fam, _ = EXHIBITS.get(ex, ("other", None))
    if ex == "916" and n in (2, 3):
        return "drainage-profile" if n == 2 else "drainage-xs"
    if ex == "916" and n == 4:
        return "tabulation"
    if ex == "920" and n == 2:
        return "borings"
    if ex == "924" and n == 2:
        return "details"
    if "signature" in stem:
        return "signature"
    return fam


def title_fields(runs, has_title_box, chars=(), TB=None):
    """The strip's cells, by where the FDOT border puts them."""
    f = {}
    y0, y1 = FRAME[1], STRIP_TOP
    f["road_no"] = cell_text(chars, EOR_X1, 9.6, y0, 0.619)
    f["county"] = cell_text(chars, 9.6, 10.7, y0, 0.619)
    f["fpid"] = cell_text(chars, 10.7, AGY_X1, y0, 0.619)
    f["sheet_number"] = cell_text(chars, TTL_X1, FRAME[2] + 0.05, y0, 0.7)
    title = [r for r in runs if abs(r["rot"]) < 1 and r["size"] >= 0.09 and
             AGY_X1 < run_center(r)[0] < TTL_X1 and y0 < run_center(r)[1] < y1]
    f["sheet_title"] = "\n".join(r["text"].strip() for r in sorted(join_lines(title), key=lambda r: -r["y"])
                                 if r["text"].strip())
    eor = [r for r in runs if abs(r["rot"]) < 1 and REV_X1 < run_center(r)[0] < EOR_X1 and
           y0 < r["y"] < 0.95]
    for key, r in zip(("eor_name", "eor_license", "eor_firm", "eor_address", "eor_city"),
                      sorted(join_lines(eor), key=lambda r: -r["y"])):
        f[key] = r["text"].strip()
    revs = [r for r in runs if abs(r["rot"]) < 1 and FRAME[0] < run_center(r)[0] < REV_X1 and
            y0 < r["y"] < 0.86 and r["text"].strip()]
    k = 0
    for r in sorted(revs, key=lambda r: (r["x"] > 3.681, -r["y"], r["x"])):
        if r["x"] < 1.281 or 3.681 < r["x"] < 4.16:
            k += 1
            f[f"rev_date_{k}"] = r["text"].strip()
        elif k:
            f[f"rev_desc_{k}"] = (f.get(f"rev_desc_{k}", "") + " " + r["text"].strip()).strip()
    for r in runs:
        x, y = run_center(r)
        t = r["text"].strip()
        if x > FRAME[2] and abs(r["rot"] - 90) < 2 and len(t) > 20:
            f["record_note"] = t
        elif y < FRAME[1] and abs(r["rot"]) < 1:
            if ".dgn" in t.lower():
                f["dgn_file"] = t
            elif re.match(r"^\d{1,2}/\d{1,2}/\d{2,4}$", t):
                f["date_plotted"] = t
            elif re.match(r"^\d{1,2}:\d{2}(:\d{2})?\s*[AP]M$", t, re.I):
                f["time_plotted"] = t
            elif re.match(r"^[A-Za-z][A-Za-z0-9_.-]{2,}$", t):
                f["username"] = t
    return {k: v for k, v in f.items() if v}


class FdotStandard(wflsheet.Standard):
    name = "fdot"
    template = "fdot"
    frame = FRAME
    heavy_lw = 0.4                      # FDOT draws the centerline at 0.6 pt, the same pen as
                                        # its curb lines: every solid line is a candidate, and
                                        # only the one with ticks and station numbers beside
                                        # it fits
    bridge_gap = 0.15                   # a centerline drawn in dashes 0.075 in apart
    screened_refs = True                # the roadway is shown gray on a drainage sheet

    def template_drawn(self, has_line):
        return has_line((FRAME[0], STRIP_TOP), (FRAME[2], STRIP_TOP)) and \
            has_line((TTL_X1, FRAME[1]), (TTL_X1, STRIP_TOP))

    def title_box_drawn(self, has_line, runs):
        return False                    # the title lives in the strip

    def in_title(self, x, y, title_box):
        return y < STRIP_TOP + 0.03

    def portrait_block(self, W, H):
        return (W - 1.5, 0.3, W - 0.8, 0.7)


# the station number sits right under the centerline, 0.1 in off it; the edge of
# pavement is 0.24 in away at 1" = 50', so a number is claimed only from close by
FDOT = FdotStandard("fdot", family_of, title_fields, wflsheet.station_number, PLAN_FAMILIES,
                    label_dist=0.5)
