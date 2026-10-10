"""What the CFL (Central Federal Lands) sample sheets do differently from WFL's, as a
wflsheet.Standard: the sheets are classed by their source file, the title block letters
the project number over the project name, and station ticks are labelled with the whole
station ("15+00").  The border is the same FLH 11 x 17 frame, so the digitiser is
wflsheet.digitise under this standard.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "wfl_redraft"))

import wflsheet                                                     # noqa: E402
from wflsheet import TB, cell_text                                  # noqa: E402

PLAN_FAMILIES = {"plan-profile", "approach", "parking", "erosion", "drainage", "wall",
                 "signing", "detour", "layout", "site"}


def family_of(rel, fields):
    """The kind of sheet, from the CFL sample set's file name (its section letter and
    subject) and, failing that, the sheet title."""
    stem = rel.split("/")[-1].lower()
    title = (fields.get("sheet_title") or "").upper()
    if "cross-section-title" in stem:
        return "xst"
    if "cross-section" in stem:
        return "xs"
    if "typical" in stem:
        return "typical"
    if "summary" in stem or "summaries" in stem:
        return "soq"
    if "amend-plan-sheets" in stem:
        return "details"
    if "plan-and-profile" in stem or "plan-and-plan" in stem:
        return "approach" if "approach" in stem else "plan-profile"
    if "parking-lot-geometric" in stem:
        return "layout"
    if "parking-lot" in stem:
        return "parking"
    if "swppp" in stem:
        return "erosion"
    if "wall" in stem:
        return "wall"
    if "culvert" in stem:
        return "drainage"
    if "signing" in stem:
        return "signing"
    if "traffic-control" in stem or "detour" in stem:
        return "detour"
    if "TYPICAL" in title:
        return "typical"
    if "DETAIL" in title:
        return "details"
    return "other"


def title_fields(runs, has_title_box, chars=(), TB=TB):
    """WFL's title block, with the CFL value cell read as two lines: the project number
    over the project name."""
    f = wflsheet.title_fields(runs, has_title_box, chars, TB)
    px0 = TB[0] + 0.4 if "state" in f else TB[0]
    sx = TB[2] - 0.4
    mid = TB[1] + 0.1
    number = cell_text(chars, px0, sx, mid, TB[1] + 0.2)
    name = cell_text(chars, px0, sx, TB[1], mid)
    if number or name:
        f["project"] = number
        f["project_name"] = name
    return f


# CFL letters the station ("15+00") square to the line at the top of the plan band, up to
# 3 in off the centerline, at every 500 ft tick
CFL = wflsheet.Standard("cfl", family_of, title_fields, wflsheet.station_number_full, PLAN_FAMILIES,
                        label_dist=3.2)
