"""The grounded checker for the generated QA reviews (``tasks.planted``, the ``p14``
family): read the design, read what the sheet shows, check every item that can be
checked against the design, mark each one that is wrong with a callout on
QA-REVIEW, and letter NO ERRORS FOUND when nothing is.  Nothing is fixed.

The checks, each from queries only:

- a bearing and distance: ``xy_to_station`` of the text names the tangent it sits
  on; the design's bearing and length for that tangent, as the sheet letters them;
- a curve point (``106+82.91 BC``): the curve point nearest the station the text
  sits at (``xy_to_station``), its kind and its station as the design gives them;
- a station number: the station its own anchor record names, lettered as its
  hundreds or their last digit;
- a tick: every numbered station has one (the ticks' anchor records);
- the curve table: each cell against the design's curve data;
- the north arrow: turned the viewport's twist;
- every text: its four corners on the paper read left to right (or bottom to top),
  not upside down.

A callout's tip is the item's own point on the paper (the text's ``sheet_point``,
the tick's ``station_to_xy`` on the sheet, the table cell's middle worked out from
the table's columns and rows, the arrow's insertion point); its text sits
``OFFSET_IN`` off toward the middle of the view.
"""
from __future__ import annotations

import math
import re
from typing import Dict, Generator, List, Optional

from roaddraft.trajectories.grounded import Turn, _q
from roaddraft.trajectories.reasoning import _n, _ok

#: how far a callout's text sits off the item, toward the middle of the view (paper inches)
OFFSET_IN = 0.75
QA_LAYER = "QA-REVIEW"
CLEAN_TEXT = "NO ERRORS FOUND"

_BEARING = re.compile(r"^[NS] \d+°\d+'\d+\" [EW] \d+\.\d+'$")
_CURVE_POINT = re.compile(r"^(\d+\+\d{2}\.\d{2}) (BC|EC)$")
_SHEET = re.compile(r"Sheet (\S+) is back from drafting")


def _all(rows: List[dict]) -> List[dict]:
    return [r for r in rows if float(r.get("shown", 1.0)) >= 1.0]


def _upside_down(corners) -> bool:
    from roaddraft.verify.legibility import reads_upside_down
    rot = math.degrees(math.atan2(corners[1][1] - corners[0][1], corners[1][0] - corners[0][0]))
    return reads_upside_down(rot)


def solve_review(text: str) -> Generator[Turn, List[dict], Turn]:
    m = _SHEET.search(text)
    if not m:
        raise ValueError("the task names no sheet")
    sheet = m.group(1).rstrip(".")
    calls = [_q("get_document_state", detail="summary"), _q("get_sheet_state", sheet=sheet)]
    results = yield Turn(f"Sheet {sheet} is to be checked against the design. See what the "
                         "document holds and how the sheet is set up first.", calls)
    _ok(results, calls)
    summary, state = results[0]["summary"], results[1]["sheet"]
    alignment = (summary.get("alignments") or [None])[0]
    if alignment is None:
        raise ValueError("the document holds no alignment")
    paper = (summary.get("settings") or {}).get("annotation_paper") or {}
    height = float(paper.get("text_height_in") or 0.0)
    vp = state["viewports"][0]
    twist = float(vp["rotation_deg"])

    calls = [_q("get_design_data", alignment=alignment, kind="tangents"),
             _q("get_design_data", alignment=alignment, kind="curves"),
             _q("find_entities", visible_on=sheet, type="text", limit=100),
             _q("find_entities", visible_on=sheet, type="line", limit=100)]
    results = yield Turn(
        f"Read the design of {alignment} (its tangents and curves) and what the sheet shows of "
        "the model: the lettering and the lines, with where each sits on the paper.", calls)
    _ok(results, calls)
    tangents = {r["ref"]: r for r in results[0]["rows"]}
    curves = {r["index"]: r for r in results[1]["rows"]}
    texts, lines = results[2], results[3]
    for r in (texts, lines):
        if (r.get("more") or {}).get("remaining"):
            raise ValueError("the sheet shows more than one page of rows")
    texts, lines = _all(texts["entities"]), _all(lines["entities"])

    # -- where the bearings and curve points sit on the line
    placed = [row for row in texts
              if _BEARING.match(row.get("content") or "") or _CURVE_POINT.match(row.get("content") or "")]
    table_id = next((eid for eid, e in state["entities"].items() if e["type"] == "table"), None)
    arrow = next((e for e in state["entities"].values()
                  if e["type"] == "blockref" and e.get("block_name") == "NORTH_ARROW"), None)
    calls = [_q("xy_to_station", alignment=alignment, point=row["point"]) for row in placed]
    if table_id:
        calls.append(_q("get_entity", id=table_id))
    results = yield Turn(
        "The bearings and the curve points carry no record of what they letter, so find where "
        "each sits on the line" + (", and read the curve table cell by cell." if table_id else "."),
        calls)
    _ok(results, calls)
    where = {row["id"]: res for row, res in zip(placed, results)}
    table = results[len(placed)] if table_id else None

    findings: List[dict] = []
    said: List[str] = []
    # -- bearings and distances
    for row in placed:
        content = row["content"]
        at = where[row["id"]]
        if _BEARING.match(content):
            ref = at.get("element_ref")
            t = tangents.get(ref)
            if t is None:
                continue
            want = f"{t['bearing']} {float(t['length']):.2f}'"
            if content != want:
                findings.append({"at": row["sheet_point"],
                                 "note": f"QA: BEARING SHOULD READ {want}"})
                said.append(f"{row['id']} reads {content} on {ref}, whose design is {want}: wrong.")
            else:
                said.append(f"{row['id']} on {ref} agrees with the design.")
        else:
            got = _CURVE_POINT.match(content)
            s = float(at["station"])
            points = [(abs(s - float(c["pc_station"])), c["pc_station_text"], "BC", c["ref"])
                      for c in curves.values()]
            points += [(abs(s - float(c["pt_station"])), c["pt_station_text"], "EC", c["ref"])
                       for c in curves.values()]
            _d, st, word, ref = min(points)
            want = f"{st} {word}"
            if content != want:
                findings.append({"at": row["sheet_point"], "note": f"QA: STATION SHOULD READ {want}"})
                said.append(f"{row['id']} reads {content} at {at['station_text']}, at the "
                            f"{word} of {ref}, which is {want}: wrong.")
            else:
                said.append(f"{row['id']} is the {word} of {ref} as designed.")
            del got
    # -- station numbers and ticks
    numbers = [row for row in texts if (row.get("anchor") or {}).get("kind") == "station"]
    ticks = {round(float(r["anchor"]["station"]), 3) for r in lines
             if (r.get("anchor") or {}).get("kind") == "tick"}
    bare: List[dict] = []
    for row in numbers:
        st = float(row["anchor"]["station"])
        hundreds = int(round(st)) // 100
        if (row.get("content") or "") not in (str(hundreds), str(hundreds % 10)):
            findings.append({"at": row["sheet_point"],
                             "note": f"QA: STATION NUMBER DOES NOT MATCH STATION {row['anchor']['ref']}"})
            said.append(f"{row['id']} reads {row['content']} at {row['anchor']['ref']}: wrong.")
        if round(st, 3) not in ticks:
            bare.append(row)
    # -- the curve table
    if table is not None:
        e = table["entity"]
        widths = [float(c["width"]) for c in e["columns"]]
        heads = [c["header"] for c in e["columns"]]
        x0, y0 = float(e["position"][0]), float(table["bbox"][1])
        h_total = float(table["properties"]["height"])
        n_rows = len(e["rows"])
        pitch = None
        for i, cells in enumerate(e["rows"]):
            c = curves.get(int(cells[0])) if cells[0].isdigit() else None
            if c is None:
                continue
            want = {"R": f"{float(c['radius']):.2f}'", "Δ": c["delta_dms"],
                    "T": f"{float(c['tangent']):.2f}'", "L": f"{float(c['length']):.2f}'"}
            for j, head in enumerate(heads):
                if head not in want or cells[j] == want[head]:
                    continue
                if pitch is None:
                    rows_plus = n_rows + 2
                    pitch = h_total / rows_plus
                    said.append(f"The table's rows: {n_rows} + 2 = {rows_plus} with the title and "
                                f"the headings, each {_n(h_total)} / {rows_plus} = {_n(pitch)} in.")
                xs = " + ".join(_n(w) for w in widths[:j])
                x = x0 + sum(widths[:j]) + widths[j] / 2.0
                above = n_rows - i
                y = y0 + above * pitch - pitch / 2.0
                said.append(
                    f"Curve {cells[0]}'s {head} reads {cells[j]}, the design {want[head]}: wrong; its "
                    f"cell's middle is x = {_n(x0)}{' + ' + xs if xs else ''} + {_n(widths[j])} / 2 "
                    f"= {_n(x)}, y = {_n(y0)} + " + " + ".join([_n(pitch)] * above)
                    + f" - {_n(pitch)} / 2 = {_n(y)}.")
                findings.append({"at": [round(x, 4), round(y, 4)],
                                 "note": f"QA: CURVE DATA SHOULD READ {want[head]}"})
    # -- the north arrow
    if arrow is not None:
        turn = float(arrow.get("rotation_deg") or 0.0)
        off = abs((turn - twist + 180.0) % 360.0 - 180.0)
        if off > 0.01:
            findings.append({"at": list(arrow["position"]), "note": "QA: NORTH ARROW DOES NOT POINT NORTH"})
            said.append(f"The north arrow is turned {_n(turn)} degrees on a view turned "
                        f"{_n(twist)}: it does not point north.")
        else:
            said.append("The north arrow is turned with the view and points north.")
    # -- lettering upside down
    for row in texts:
        corners = row.get("paper_corners")
        if corners and _upside_down(corners):
            findings.append({"at": row["sheet_point"], "note": "QA: LABEL READS UPSIDE DOWN"})
            said.append(f"{row['id']} ({row.get('content')}) runs from {_pt(corners[0])} to "
                        f"{_pt(corners[1])} on the paper: it reads upside down.")

    # -- a numbered station with no tick: where the tick belongs
    if bare:
        calls = [_q("station_to_xy", alignment=alignment, station=row["anchor"]["ref"], sheet=sheet)
                 for row in bare]
        results = yield Turn(" ".join(said + [
            "The station numbered at " + " and ".join(r["anchor"]["ref"] for r in bare)
            + " has no tick: find where it belongs on the paper."]), calls)
        _ok(results, calls)
        said = []
        for row, res in zip(bare, results):
            point = res["on_sheet"]["sheet_point"]
            findings.append({"at": point,
                             "note": f"QA: STATION TICK MISSING AT {row['anchor']['ref']}"})

    cx, cy = (float(v) for v in vp["center_paper"])
    w, hgt = float(vp["width_in"]), float(vp["height_in"])
    calls = [_q("create_layer", name=QA_LAYER)]
    if not findings:
        x = cx - w / 2.0 + OFFSET_IN
        y = cy - hgt / 2.0 + OFFSET_IN
        said.append(f"Nothing on the sheet disagrees with the design. Letter {CLEAN_TEXT} on "
                    f"{QA_LAYER} inside the view's lower left corner: x = {_n(cx)} - {_n(w)} / 2 + "
                    f"{_n(OFFSET_IN)} = {_n(x)}, y = {_n(cy)} - {_n(hgt)} / 2 + {_n(OFFSET_IN)} = "
                    f"{_n(y)}, at the standard text height.")
        calls.append(_q("place_text", space=sheet, layer=QA_LAYER, position=[_r(x), _r(y)],
                        content=CLEAN_TEXT, height=height))
    else:
        said.append(f"{len(findings)} error(s) to mark, each with a callout on {QA_LAYER}: the tip "
                    f"on the item, the note {_n(OFFSET_IN)} in off toward the middle of the view.")
        for f in findings:
            px, py = float(f["at"][0]), float(f["at"][1])
            sx = "+" if px < cx else "-"
            sy = "+" if py < cy else "-"
            tx = px + OFFSET_IN if sx == "+" else px - OFFSET_IN
            ty = py + OFFSET_IN if sy == "+" else py - OFFSET_IN
            said.append(f"{f['note'][4:].capitalize()}: text at {_n(px)} {sx} {_n(OFFSET_IN)} = "
                        f"{_n(tx)}, {_n(py)} {sy} {_n(OFFSET_IN)} = {_n(ty)}.")
            calls.append(_q("place_callout", space=sheet, layer=QA_LAYER,
                            target=[_r(px), _r(py)], position=[_r(tx), _r(ty)], content=f["note"]))
    results = yield Turn(" ".join(said), calls)
    _ok(results[1:], calls[1:])
    note = (f"Sheet {sheet} checked against the design of {alignment}: "
            + (f"{CLEAN_TEXT}, lettered on {QA_LAYER}." if not findings else
               f"{len(findings)} error(s) marked with callouts on {QA_LAYER}: "
               + "; ".join(f["note"][4:].lower() for f in findings) + ". Nothing was fixed."))
    return Turn("Done.", [_q("submit", note=note)])


def _r(v: float) -> float:
    return round(float(v) + 0.0, 4)


def _pt(p) -> str:
    return f"[{_n(p[0])}, {_n(p[1])}]"


__all__ = ["solve_review", "OFFSET_IN"]
