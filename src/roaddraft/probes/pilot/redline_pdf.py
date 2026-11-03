"""Pilot 18, redline understanding: the brief is a marked-up PDF and nothing else.

A sheet comes back from the checker as a PDF with handwriting on it: a value
struck through with the new one written beside it, a green X over a callout,
an arrow carrying a label to a new place, a note to add with an arrow to where
it goes, a struck title block entry, and a blue cloud with a remark that asks
for nothing. The prompt says only that the markups are the whole brief. The
model has to read the page (``view_attachment`` on the PNG of the same page,
zooming to read the hand), decide what each mark means by the key at the foot
of the page (red: revise as marked; green: delete; blue: comment only, no
change), find the entity each mark sits on among its look-alikes (the sheet
letters FENCE (TYPE CL-6) twice; the mark is on one of them), and make the
edit the right way: a text's content changed in place, a callout and its
leader taken off, a label moved to where the arrow points, a note placed where
the arrow points, a title block field refilled. Everything the markups do not
touch has to stay as it was, and the checker's handwriting must not end up on
the sheet.

The markups are drawn by this module on a render of the sheet at 200 dpi
(``markups/<sheet>-redlines.png`` and the same page as ``.pdf``) in a
handwriting face, so no text layer and no entity carries the instruction. The
sheet file the model opens is the redraft as staged, untouched: there is
nothing on it to find, only the page to read.

Instances, one per agency:

* ``p18-redline-pdf-ppm045`` (Caltrans L-1, 22 x 34): CL-6 -> CL-8 on one of
  the two FENCE callouts; one of the two REMOVE FENCE callouts deleted; the
  EXISTING ROUTE 65 NB label moved along the road; a fifth general note added;
  the post miles struck in the title block; a blue cloud round the curve table.
* ``p18-redline-pdf-wfl19`` (WFL D.10, 11 x 17): e = 6.0% -> 8.0%; one of the
  two See Section X for details lines deleted; a Profile grade label moved; a
  match line note added at the end of the plan; a blue cloud round the
  vertical curve data.
* ``p18-redline-pdf-cflpla`` (CFL Davis Dam Road, 11 x 17): a headwall note
  reworded; the Place boulder callout deleted; END PROJECT lettered at the end
  of the road; the title block's station range struck; a blue cloud round a
  curve data block.
* ``p18-redline-pdf-fdot915`` (FDOT sheet 12, 11 x 17): TYPE F -> TYPE E on
  one of the curb callouts; one of the three sidewalk callouts deleted; the
  BEGIN PROJECT block moved down in the profile; a survey note added; the
  county struck in the title block; a blue cloud round the curve data.

Six more (2026-11-03), on sheets the family had not used, 5 to 7 marks each:

* ``p18-redline-pdf-ppm051`` (Caltrans L-38): FENCE (TYPE CL-6) -> WM on one of
  four, REMOVE -> RESET on one of two REMOVE FENCE notes, one of six REMOVE /
  FENCE callouts deleted, END FENCE (TYPE CL-6) added, the county struck, a
  blue cloud round a POT callout.
* ``p18-redline-pdf-ppm049`` (Caltrans L-5): one of four 10' CHAIN LINK GATE
  cells -> 16', one of two APPROACH SLAB callouts deleted, SOUND WALL 1 moved,
  a bike path note added, the post miles struck, a blue cloud round two of the
  fence and gates table's 22 rows.
* ``p18-redline-pdf-fdot916`` (FDOT sheet 1): TYPE 1 -> TYPE 2 on one of six
  inlet notes, one of two CONST. 47 LF callouts deleted, S-110's notes moved, a
  note added, the county struck, a blue cloud round a pipe callout.
* ``p18-redline-pdf-fdot923`` (FDOT sheet 102, utility adjustments): one of four
  (TO REMAIN) -> (TO BE RELOCATED), one of four vault callouts deleted, SR 22 WB
  moved, a SUE note added, the FPID struck, a blue cloud round one of two EXIST.
  BRIDGE labels.
* ``p18-redline-pdf-wflp04`` (WFL F.4 site plan): three legend and callout
  revisions (4-inch and 6-inch on two of the legend's look-alike lines), a
  callout deleted, a note added, the project struck, a blue cloud round a legend
  entry.
* ``p18-redline-pdf-cfld1`` (CFL parking lot D1): three culvert callout
  revisions (one Riprap apron, Rt of three), one of two Install gate callouts
  deleted, a note added, a blue cloud round a culvert callout.

Graded from the documents on disk, one item per markup and one for the rest:
a revised text reads the new wording where the old one was (the old wording
gone from that spot); a deleted text is gone from its spot; a moved label's
texts sit within 0.5 in of where the arrow put them and not where they were;
an added note containing the words lies within 1 in of the arrow's tip (its box, so a long note may run on from the tip); a
clouded comment's entities are byte-for-byte as they were; a struck field
reads the new value; and nothing unrelated changed: every other entity of the
sheet and its model space, every other title block field and every base file
as staged, no new entity but text (and a leader near an added or moved note),
and none of the checker's own words lettered onto the sheet.

Naive wrong answers the tests try: acting on the blue comment; writing the new
value beside the old instead of changing it; changing the look-alike instead
of the marked one; lettering the handwriting (DELETE, MOVE) onto the sheet.
"""
from __future__ import annotations

import copy
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.core import textmetrics
from roaddraft.document.document import Document
from roaddraft.document.entities import Arc, Line, Polyline, Text
from roaddraft.document.fileformat import read_document
from roaddraft.probes.base import Probe, Result, Tally
from roaddraft.probes.pilot import common

#: the folder in the project that holds the marked-up page, served through
#: ``view_attachment``; the PDF sits beside the PNG for the record
MARKUPS = "markups"
SERVER_ARGS = ["--attachments", "{project}/" + MARKUPS]
DPI = 200
#: the key at the foot of the page, and who signed it
CHECKER = "RD"
CHECKED_ON = "10-26-26"
KEY_STRIP_IN = 0.85
KEY_TEXT = [("RED = REVISE AS MARKED", "red"), ("GREEN = DELETE", "green"),
            ("BLUE = COMMENT ONLY, NO CHANGE", "blue")]
COLORS = {"red": (210, 28, 28), "green": (22, 140, 62), "blue": (34, 78, 212)}
KIND_COLOR = {"replace": "red", "delete": "green", "move": "red", "add": "red",
              "comment": "blue", "field": "red"}
#: handwriting faces, the first one found is used; the check never needs it
HAND_FONTS = ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
              "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
              "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]

NEAR_IN = 0.6        # a revised or deleted text: the spot it must read at, or be gone from
MOVE_IN = 0.5        # a moved text against where the arrow put it
ADD_IN = 1.0         # an added note against the arrow's tip
LEADER_IN = 0.3      # a line ending this close to a callout's box is its leader
NEW_LINE_IN = 1.2    # a new line this close to an added or moved note is a leader, allowed
PAD_IN = 0.06        # round a struck or crossed text
CLOUD_PAD_IN = 0.16  # round a clouded group


@dataclass
class Markup:
    """One mark on the page. ``ids`` are the sheet texts it sits on."""
    kind: str                       # replace | delete | move | add | comment | field
    ids: Sequence[str] = ()
    old: str = ""                   # replace: the words struck (a substring); field: the substring to go
    new: str = ""                   # replace / field: what must read; add: the words to letter
    tip: Optional[Tuple[float, float]] = None   # move / add: where the arrow points, paper inches
    note: str = ""                  # the handwriting (default by kind)
    note_at: Optional[Tuple[float, float]] = None
    key: str = ""                   # field: the title block key
    item: str = ""                  # the check item's name

    def words(self) -> str:
        if self.note:
            return self.note
        if self.kind == "replace" or self.kind == "field":
            return self.new
        if self.kind == "delete":
            return "DELETE"
        if self.kind == "move":
            return "MOVE"
        if self.kind == "add":
            return "ADD: " + self.new
        return "NO CHANGE"


@dataclass
class Instance:
    id: str
    sheet_id: str
    sheet: str
    page: str                       # the file stem of the PNG and PDF
    markups: List[Markup]
    note: str = ""
    hand_in: float = 0.22           # handwriting size, paper inches (font size)
    text_in: float = 0.14           # the height of a note the solution letters
    tags: List[str] = field(default_factory=list)


# ------------------------------------------------------------------ instances

PPM045 = Instance(
    id="p18-redline-pdf-ppm045", sheet_id="PPM-045", sheet="L-1", page="L-1-redlines",
    hand_in=0.26, text_in=0.14, tags=["caltrans"],
    markups=[
        Markup("replace", ids=["TX-107"], old="CL-6", new="CL-8", note="CL-8", note_at=(21.7, 5.05),
               item='FENCE (TYPE CL-6) at the south fence reads FENCE (TYPE CL-8)'),
        Markup("delete", ids=["TX-118"], note_at=(28.55, 11.95),
               item="the REMOVE FENCE callout at the north-east fence deleted"),
        Markup("move", ids=["TX-027"], tip=(12.0, 8.6), note_at=(9.9, 8.85),
               item="EXISTING ROUTE 65 NB moved along the road to where the arrow points"),
        Markup("add", new="5. SEE SHEET L-2 FOR CONTINUATION", tip=(2.95, 18.62),
               note="ADD NOTE 5: SEE SHEET L-2 FOR CONTINUATION", note_at=(8.2, 18.25),
               item="note 5, SEE SHEET L-2 FOR CONTINUATION, added under the general notes"),
        Markup("field", key="post_miles", old="R24.1", new="R24.3", note="R24.3",
               item="the title block's post miles read R11.9/R24.3"),
        Markup("comment", ids=[f"TX-{n:03d}" for n in range(1, 16)], note="OK PER SURVEY - NO CHANGE",
               note_at=(15.4, 3.75), item="the curve table, clouded in blue, left as it was"),
    ],
    note=("Six marks on L-1: CL-6 struck for CL-8 on the FENCE callout at the south fence (TX-107; "
          "TX-120 is the look-alike); a green X on the REMOVE FENCE callout at the north-east fence "
          "(TX-118; TX-114 is the look-alike); EXISTING ROUTE 65 NB arrowed 3 in east; ADD NOTE 5 "
          "arrowed under note 4; R24.1 struck for R24.3 in the post miles box; a blue cloud round "
          "the curve table reading OK PER SURVEY - NO CHANGE."))

WFL19 = Instance(
    id="p18-redline-pdf-wfl19", sheet_id="WFL-Plan-Profile-Sheets-p19", sheet="D.10",
    page="D-10-redlines", hand_in=0.2, text_in=0.08, tags=["wfl"],
    markups=[
        Markup("replace", ids=["TX-036"], old="6.0%", new="8.0%", note="8.0%", note_at=(7.9, 6.0),
               item="e = 6.0% reads e = 8.0%"),
        Markup("delete", ids=["TX-029"], note_at=(9.1, 5.1),
               item="the See Section X for details line under the guardrail callout deleted"),
        Markup("move", ids=["TX-024"], tip=(12.3, 3.3), note_at=(12.75, 3.65),
               item="the right-hand Profile grade label moved below the grade line"),
        Markup("add", new="SEE SHEET D.11", tip=(15.1, 5.95),
               note="ADD: MATCH LINE STA 152+50 - SEE SHEET D.11", note_at=(10.2, 5.42),
               item="a match line note reading SEE SHEET D.11 lettered at the end of the plan"),
        Markup("comment", ids=["TX-017", "TX-018", "TX-019"], note="OK - CHECKED", note_at=(4.75, 3.3),
               item="the vertical curve data, clouded in blue, left as it was"),
    ],
    note=("Five marks on D.10: 6.0% struck for 8.0% in the curve block; a green X on the See "
          "Section X for details line under the guardrail callout (TX-029; TX-037 is the "
          "look-alike); the right profile's Profile grade label arrowed below the grade line; a "
          "match line note arrowed to the end of the plan; a blue cloud round HLSD / K / VC reading "
          "OK - CHECKED."))

CFLPLA = Instance(
    id="p18-redline-pdf-cflpla", sheet_id="CFL-D-Plan-and-Plan", sheet="PLA(SAMPLE)",
    page="PLA-redlines", hand_in=0.2, text_in=0.08, tags=["cfl"],
    markups=[
        Markup("replace", ids=["TX-071"], old="Do not disturb existing headwall",
               new="Protect existing headwall in place", note="PROTECT EXISTING HEADWALL IN PLACE",
               note_at=(4.6, 6.12), item="the headwall note reads Protect existing headwall in place"),
        Markup("delete", ids=["TX-065", "TX-066"], note_at=(7.75, 4.2),
               item="the Place boulder / See special 251-A callout deleted"),
        Markup("add", new="END PROJECT 41+00", tip=(14.2, 4.55), note="ADD: END PROJECT 41+00",
               note_at=(11.3, 5.2), item="END PROJECT 41+00 lettered at the end of the road"),
        Markup("field", key="sheet_title", old="41+00", new="41+32.03", note="41+32.03",
               item="the title block's station range reads 29+67.45 to 41+32.03"),
        Markup("comment", ids=[f"TX-{n:03d}" for n in range(6, 16)], note="OK PER SURVEY 4/2",
               note_at=(7.35, 5.3), item="the curve data block, clouded in blue, left as it was"),
    ],
    note=("Five marks on the Davis Dam Road plan: the headwall note struck and reworded; a green X "
          "on the Place boulder / See special 251-A callout; ADD: END PROJECT 41+00 arrowed to the "
          "end of the road in the lower plan; 41+00 struck for 41+32.03 in the title block; a blue "
          "cloud round the curve data block reading OK PER SURVEY 4/2."))

FDOT915 = Instance(
    id="p18-redline-pdf-fdot915", sheet_id="FDOT-915-1-Roadway-Plan-Profile", sheet="12",
    page="sheet-12-redlines", hand_in=0.2, text_in=0.07, tags=["fdot"],
    markups=[
        Markup("replace", ids=["TX-127"], old="TYPE F", new="TYPE E", note="TYPE E", note_at=(5.6, 8.75),
               item="the south-west curb callout reads TYPE E CURB AND GUTTER"),
        Markup("delete", ids=["TX-130"], note_at=(2.0, 10.2),
               item="the sidewalk callout at the west end deleted"),
        Markup("move", ids=["TX-016", "TX-018", "TX-019", "TX-020"], tip=(3.4, 2.55), note_at=(3.65, 2.8),
               item="the BEGIN PROJECT block moved down below the grade line"),
        Markup("add", new="EXISTING GROUND FROM SURVEY DATED 6-2025", tip=(12.3, 2.45),
               note="ADD: EXISTING GROUND FROM SURVEY DATED 6-2025", note_at=(8.4, 2.1),
               item="EXISTING GROUND FROM SURVEY DATED 6-2025 lettered in the profile"),
        Markup("field", key="county", old="WAKULLA", new="LEON", note="LEON",
               item="the title block's county reads LEON"),
        Markup("comment", ids=["TX-048", "TX-049", "TX-051", "TX-052", "TX-055", "TX-056", "TX-057",
                               "TX-058", "TX-059", "TX-060", "TX-065", "TX-066", "TX-069", "TX-070",
                               "TX-075", "TX-076", "TX-082"], note="VERIFIED - NO CHANGE",
               note_at=(13.8, 10.2), item="the curve data, clouded in blue, left as it was"),
    ],
    note=("Six marks on sheet 12: TYPE F struck for TYPE E on the south-west curb callout (TX-127; "
          "TX-046, TX-040 and TX-122 are the look-alikes); a green X on the west sidewalk callout "
          "(TX-130; TX-120 and TX-128 are the look-alikes); the BEGIN PROJECT block arrowed down "
          "below the grade line; a survey note arrowed into the profile; WAKULLA struck for LEON in "
          "the title block; a blue cloud round the curve data reading VERIFIED - NO CHANGE."))

# ----------------------------------------------- more instances (2026-11-03)

PPM051 = Instance(
    id="p18-redline-pdf-ppm051", sheet_id="PPM-051", sheet="L-38", page="L-38-redlines",
    hand_in=0.26, text_in=0.14, tags=["caltrans"],
    markups=[
        Markup("replace", ids=["TX-104"], old="CL-6", new="WM", note="WM", note_at=(6.45, 16.02),
               item="FENCE (TYPE CL-6) at the north-west fence reads FENCE (TYPE WM)"),
        Markup("replace", ids=["TX-095"], old="REMOVE", new="RESET", note="RESET", note_at=(15.3, 4.62),
               item="the REMOVE FENCE note on the south side of the road reads RESET FENCE"),
        Markup("delete", ids=["TX-100"], note_at=(17.3, 10.0),
               item="the REMOVE FENCE callout east of the NB10 line deleted"),
        Markup("add", new="END FENCE (TYPE CL-6)", tip=(7.95, 18.95),
               note="ADD: END FENCE (TYPE CL-6)", note_at=(2.6, 18.2),
               item="END FENCE (TYPE CL-6) lettered at the top of the west fence"),
        Markup("field", key="county", old="Pla", new="Sut", note="Sut",
               item="the title block's county reads Sut"),
        Markup("comment", ids=["TX-098"], note="TIES OK - NO CHANGE", note_at=(2.6, 7.1),
               item="the SB10 / WIS1 POT callout, clouded in blue, left as it was"),
    ],
    note=("Six marks on L-38, none a move: CL-6 struck for WM on the north-west FENCE (TYPE CL-6) "
          "(TX-104; TX-103, TX-091 and TX-092 read the same); REMOVE struck for RESET in the REMOVE "
          "FENCE note on the south side (TX-095; TX-093 reads the same, and six more read "
          "REMOVE / FENCE on two lines); a green X on the REMOVE FENCE callout east of the NB10 "
          "line (TX-100); ADD: END FENCE (TYPE CL-6) arrowed to the top of the west fence, words "
          "that contain a look-alike; Pla struck for Sut in the county box; a blue cloud round the "
          "SB10 / WIS1 POT callout (the NB10 one is its look-alike) reading TIES OK - NO CHANGE."))

PPM049 = Instance(
    id="p18-redline-pdf-ppm049", sheet_id="PPM-049", sheet="L-5", page="L-5-redlines",
    hand_in=0.26, text_in=0.14, tags=["caltrans"],
    markups=[
        Markup("replace", ids=["TX-031"], old="10’", new="16’", note="16'", note_at=(32.55, 9.38),
               item="FC13's note in the fence and gates table reads 16’ CHAIN LINK GATE"),
        Markup("delete", ids=["TX-025", "TX-021"], note_at=(18.7, 8.2),
               item="the APPROACH SLAB callout at the south end of the bridges deleted"),
        Markup("move", ids=["TX-121", "TX-122", "TX-123"], tip=(12.6, 11.55), note_at=(12.9, 12.25),
               item="SOUND WALL 1 moved west along the wall to where the arrow points"),
        Markup("add", new="PROTECT EXISTING BIKE PATH", tip=(18.9, 4.6),
               note="ADD: PROTECT EXISTING BIKE PATH", note_at=(22.8, 4.45),
               item="PROTECT EXISTING BIKE PATH lettered at the bike path"),
        Markup("field", key="post_miles", old="R11.9", new="R12.0", note="R12.0",
               item="the title block's post miles read R12.0/R24.1"),
        Markup("comment", ids=["TX-072", "TX-073", "TX-074", "TX-075", "TX-076", "TX-077"],
               note="IND1 TIES OK - NO CHANGE", note_at=(24.0, 14.65),
               item="the FB1 and FB2 rows of the fence and gates table, clouded in blue, left as they were"),
    ],
    note=("Six marks on L-5: 10’ struck for 16’ in FC13's NOTE cell (TX-031; FC2, FC4 and FC19 "
          "read 10’ CHAIN LINK GATE too, a row apart); a green X on the APPROACH SLAB / (SEE "
          "STRUCTURE PLANS) callout at the south end of the bridges (TX-025, TX-021; TX-051 and "
          "TX-047 are its look-alike at the north end); SOUND WALL 1 clouded and arrowed west along "
          "the wall; ADD: PROTECT EXISTING BIKE PATH arrowed to the bike path; R11.9 struck for "
          "R12.0 in the post miles; a blue cloud round the FB1 and FB2 rows (twenty FC rows read "
          "alike) reading IND1 TIES OK - NO CHANGE."))

FDOT916 = Instance(
    id="p18-redline-pdf-fdot916", sheet_id="FDOT-916-1-Drainage-Network-Plan-Sheet", sheet="1",
    page="sheet-1-redlines", hand_in=0.2, text_in=0.07, tags=["fdot"],
    markups=[
        Markup("replace", ids=["TX-043"], old="TYPE 1", new="TYPE 2", note="TYPE 2", note_at=(10.15, 8.0),
               item="S-105's inlet reads CONST. CURB INLET TYPE 2"),
        Markup("delete", ids=["TX-073", "TX-074"], note_at=(9.45, 5.75),
               item="the CONST. 47 LF / OF 18\" PIPE callout at S-104 deleted"),
        Markup("move", ids=["TX-016", "TX-014", "TX-012", "TX-010", "TX-008"], tip=(11.75, 2.75),
               note_at=(12.85, 3.15), item="the S-110 notes moved down and to the right, clear of the pipe"),
        Markup("add", new="SEE SHEET 2 FOR PIPE DATA", tip=(3.6, 8.25),
               note="ADD: SEE SHEET 2 FOR PIPE DATA", note_at=(5.2, 8.9),
               item="SEE SHEET 2 FOR PIPE DATA lettered above the structure notes"),
        Markup("field", key="county", old="BAY", new="GULF", note="GULF",
               item="the title block's county reads GULF"),
        Markup("comment", ids=["TX-067", "TX-068"], note="LF CHECKED - OK", note_at=(5.3, 3.7),
               item="the CONST. 197 LF callout, clouded in blue, left as it was"),
    ],
    note=("Six marks on FDOT sheet 1: TYPE 1 struck for TYPE 2 in S-105's notes (TX-043; five more "
          "notes read CONST. CURB INLET TYPE 1 and S-107's already reads TYPE 2); a green X on the "
          "CONST. 47 LF / OF 18\" PIPE callout at S-104 (TX-073, TX-074; TX-069 and TX-070 read the "
          "same at S-106); the five lines of S-110's notes clouded and arrowed clear of the pipe; "
          "ADD: SEE SHEET 2 FOR PIPE DATA arrowed above the notes; BAY struck for GULF; a blue cloud "
          "round the CONST. 197 LF callout (six CONST. ... LF callouts) reading LF CHECKED - OK."))

FDOT923 = Instance(
    id="p18-redline-pdf-fdot923", sheet_id="FDOT-923-1-Utility-Adjustments", sheet="102",
    page="sheet-102-redlines", hand_in=0.2, text_in=0.07, tags=["fdot"],
    markups=[
        Markup("replace", ids=["TX-016"], old="TO REMAIN", new="TO BE RELOCATED", note="TO BE RELOCATED",
               note_at=(11.2, 8.47),
               item="the AT&T / Century Link conduit east of the bridge reads (TO BE RELOCATED)"),
        Markup("delete", ids=["TX-073", "TX-074"], note_at=(3.75, 9.55),
               item="the VAULT - AT&T FLORIDA (TO BE REMOVED) callout at the north-west deleted"),
        Markup("move", ids=["TX-012"], tip=(9.6, 6.55), note_at=(8.3, 6.85),
               item="SR 22 WB moved east along the westbound lanes to where the arrow points"),
        Markup("add", new="UTILITY DEPTHS TO BE VERIFIED BY SUE", tip=(3.3, 2.35),
               note="ADD: UTILITY DEPTHS TO BE VERIFIED BY SUE", note_at=(1.3, 1.75),
               item="UTILITY DEPTHS TO BE VERIFIED BY SUE lettered at the south-west"),
        Markup("field", key="fpid", old="1-52", new="2-52", note="2-52",
               item="the title block's financial project ID reads 123456-2-52-01"),
        Markup("comment", ids=["TX-011"], note="OK PER STRUCTURES", note_at=(14.55, 6.35),
               item="EXIST. BRIDGE NO. 234567 north of the road, clouded in blue, left as it was"),
    ],
    note=("Six marks on FDOT sheet 102 (utility adjustments): TO REMAIN struck for TO BE RELOCATED "
          "on the east conduit (TX-016; three more read (TO REMAIN)); a green X on the north-west "
          "VAULT - AT&T FLORIDA / (TO BE REMOVED) callout (TX-073, TX-074; three more vault callouts "
          "read the same); SR 22 WB clouded and arrowed east (SR 22 EB is its look-alike); ADD: "
          "UTILITY DEPTHS TO BE VERIFIED BY SUE; 1-52 struck for 2-52 in the FPID; a blue cloud round "
          "the north EXIST. BRIDGE NO. 234567 (the south one reads the same) reading OK PER STRUCTURES."))

WFLP04 = Instance(
    id="p18-redline-pdf-wflp04", sheet_id="WFL-Parking-Lot-Section-p04", sheet="F.4",
    page="F-4-redlines", hand_in=0.2, text_in=0.084, tags=["wfl"],
    markups=[
        Markup("replace", ids=["TX-032"], old="Dectable", new="Detectable", note="Detectable",
               note_at=(9.15, 9.05), item="the warning panel callout reads Detectable warning panel"),
        Markup("replace", ids=["TX-005"], old="4-inch", new="5-inch", note="5-inch", note_at=(14.6, 8.52),
               item="the third sidewalk in the legend reads (5-inch depth)"),
        Markup("replace", ids=["TX-001"], old="6-inch", new="8-inch", note="8-inch", note_at=(14.6, 7.7),
               item="the last sidewalk in the legend reads (8-inch depth)"),
        Markup("delete", ids=["TX-021"], note_at=(12.35, 6.62),
               item="the Sidewalk, aggregate callout east of the lot deleted"),
        Markup("add", new="Bike rack", tip=(11.6, 5.6), note="ADD: BIKE RACK", note_at=(12.3, 4.9),
               item="Bike rack lettered east of the parking lot"),
        Markup("field", key="project", old="10(1)", new="10(2)", note="10(2)",
               item="the title block's project reads WA NP FOVA 10(2)"),
        Markup("comment", ids=["TX-009", "TX-010"], note="COLOR OK PER NPS", note_at=(12.3, 10.05),
               item="the minor concrete pavement legend entry, clouded in blue, left as it was"),
    ],
    note=("Seven marks on WFL F.4 (site plan): Dectable struck for Detectable; 4-inch struck for "
          "5-inch on the third sidewalk in the legend (TX-005; TX-003 also reads 4-inch, the line "
          "above); 6-inch struck for 8-inch on the last sidewalk in the legend (TX-001; the "
          "minor concrete pavement's 6-inch depth (rustic brown color) is the one clouded in "
          "blue); a green X on the Sidewalk, aggregate "
          "callout east of the lot (TX-021; the legend's three Sidewalk, exposed aggregate concrete "
          "entries read nearly the same); ADD: BIKE RACK arrowed east of the lot; 10(1) struck for 10(2) "
          "in the project box; a blue cloud round the minor concrete pavement legend entry reading "
          "COLOR OK PER NPS."))

CFLD1 = Instance(
    id="p18-redline-pdf-cfld1", sheet_id="CFL-F-Parking-Lot", sheet="D1", page="D1-redlines",
    hand_in=0.2, text_in=0.084, tags=["cfl"],
    markups=[
        Markup("replace", ids=["TX-013"], old="44'", new="48'", note="48'", note_at=(15.0, 8.3),
               item="the east culvert reads Install 24\" x 48' CMP"),
        Markup("replace", ids=["TX-020"], old="Rt", new="Lt and Rt", note="LT AND RT", note_at=(13.35, 9.2),
               item="the north culvert's riprap reads Riprap apron, Lt and Rt"),
        Markup("delete", ids=["TX-016"], note_at=(12.95, 8.75), item="the Install gate callout at the east end deleted"),
        Markup("replace", ids=["TX-018"], old="28", new="28'", note="28'", note_at=(13.95, 10.05),
               item="the north culvert reads Install 24\" x 28' CMP"),
        Markup("add", new="Install cattle guard", tip=(15.6, 4.75), note="ADD: INSTALL CATTLE GUARD",
               note_at=(12.6, 2.7), item="Install cattle guard lettered at the east end of the road"),
        Markup("comment", ids=["TX-006", "TX-007", "TX-008"], note="SIZE OK - NO CHANGE", note_at=(1.2, 4.95),
               item="the west culvert callout, clouded in blue, left as it was"),
    ],
    note=("Six marks on the CFL parking lot plan D1: 44' struck for 48' on the east culvert (TX-013; "
          "the other two culverts read 52' and 28); Rt struck for Lt and Rt in the north culvert's "
          "Riprap apron, Rt (TX-020; TX-006 and TX-015 read the same, and End section, Lt and Rt "
          "sits a line away); a green X on the east Install gate (TX-016; TX-012 reads the same); "
          "28 struck for 28' on the north culvert, the line above it; ADD: INSTALL CATTLE GUARD "
          "arrowed to the east end of the road; a blue cloud round the west culvert's three lines "
          "reading SIZE OK - NO CHANGE. No title block mark: the two-line sheet title does not "
          "take a clean strike."))

INSTANCES = [PPM045, WFL19, CFLPLA, FDOT915, PPM051, PPM049, FDOT916, FDOT923, WFLP04, CFLD1]


def _instance(inst_id: str) -> Instance:
    return next(i for i in INSTANCES if i.id == inst_id)


# ------------------------------------------------------------------ reading the sheet


def _sheet(session: Session, name: str):
    return next((s for s in session.doc.sheets.values() if s.name == name), None)


def _norm(text: str) -> str:
    text = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"') \
        .replace("”", '"').replace("°", "°")
    return " ".join(text.upper().split())


def _bbox(doc: Document, entities: Sequence[Text]) -> Tuple[float, float, float, float]:
    boxes = [e.bbox(doc) for e in entities]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _center(doc: Document, e: Text) -> Tuple[float, float]:
    b = e.bbox(doc)
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _texts(sheet) -> List[Text]:
    return [e for e in sheet.entities.values() if isinstance(e, Text)]


def _points(e) -> List[List[float]]:
    if isinstance(e, Line):
        return [list(e.start), list(e.end)]
    if isinstance(e, Polyline):
        return [list(v) for v in e.vertices]
    if isinstance(e, Arc):
        return [list(p) for p in (e.start_point(), e.end_point())] if hasattr(e, "start_point") else []
    return []


def _near_box(points, box, within: float) -> bool:
    x0, y0, x1, y1 = box[0] - within, box[1] - within, box[2] + within, box[3] + within
    return any(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in points)


def _leaders(doc: Document, sheet, texts: Sequence[Text]) -> List[str]:
    """Lines and polylines of the sheet that end at a callout's box: its leader."""
    if not texts:
        return []
    box = _bbox(doc, texts)
    return [e.id for e in sheet.entities.values()
            if isinstance(e, (Line, Polyline)) and _near_box(_points(e), box, LEADER_IN)]


def _same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    da, db = a.to_dict(), b.to_dict()
    da.pop("id", None)
    db.pop("id", None)
    return da == db


def _targets(inst: Instance, kind: str) -> List[Markup]:
    return [m for m in inst.markups if m.kind == kind]


# ------------------------------------------------------------------ the page


def _font(size_px: int):
    from PIL import ImageFont
    for path in HAND_FONTS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size_px)
            except OSError:
                continue
    return ImageFont.load_default()


class _Page:
    """The rendered sheet with the checker's hand drawn over it, in pixels."""

    def __init__(self, image, height_in: float, dpi: int, hand_in: float):
        from PIL import ImageDraw
        self.im = image
        self.draw = ImageDraw.Draw(image)
        self.h_in = height_in
        self.dpi = dpi
        self.font = _font(max(12, round(hand_in * dpi)))
        self.stroke = max(2, round(0.024 * dpi))

    def px(self, p) -> Tuple[float, float]:
        return (p[0] * self.dpi, (self.h_in - p[1]) * self.dpi)

    def line(self, a, b, color, width=None):
        self.draw.line([self.px(a), self.px(b)], fill=COLORS[color], width=width or self.stroke)

    def text(self, at, words: str, color, anchor="ls"):
        self.draw.text(self.px(at), words, fill=COLORS[color], font=self.font, anchor=anchor)

    def text_width_in(self, words: str) -> float:
        left, _top, right, _bottom = self.draw.textbbox((0, 0), words, font=self.font, anchor="ls")
        return (right - left) / self.dpi

    def arrow(self, a, b, color):
        """From ``a`` to the tip ``b``, with a filled head at the tip."""
        self.line(a, b, color)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        size = 0.16
        for side in (1, -1):
            back = (b[0] - size * math.cos(ang - side * 0.45),
                    b[1] - size * math.sin(ang - side * 0.45))
            self.draw.polygon([self.px(b), self.px(back),
                               self.px((b[0] - 0.6 * size * math.cos(ang),
                                        b[1] - 0.6 * size * math.sin(ang)))],
                              fill=COLORS[color])

    def cross(self, box, color):
        x0, y0, x1, y1 = box
        self.line((x0, y0), (x1, y1), color)
        self.line((x0, y1), (x1, y0), color)

    def cloud(self, box, color, step: float = 0.32):
        """Scallops round a box, bulging outward."""
        x0, y0, x1, y1 = box
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            n = max(1, int(round(_dist(a, b) / step)))
            for k in range(n):
                p = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                q = (a[0] + (b[0] - a[0]) * (k + 1) / n, a[1] + (b[1] - a[1]) * (k + 1) / n)
                mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
                r = _dist(p, q) / 2
                base = math.atan2(p[1] - mid[1], p[0] - mid[0])
                # counter-clockwise round the box: outward is to the right of travel,
                # so the arc from p sweeps clockwise (through the outside) to q
                pts = [(mid[0] + r * math.cos(base - math.pi * t / 10),
                        mid[1] + r * math.sin(base - math.pi * t / 10)) for t in range(11)]
                self.draw.line([self.px(pt) for pt in pts], fill=COLORS[color], width=self.stroke)


def _strike(page: _Page, doc: Document, e: Text, old: str, color: str) -> None:
    """A line through ``old`` inside the text, along the text's own direction."""
    wf = 1.0
    style = doc.text_styles.get(e.style)
    if style is not None:
        wf = style.width_factor
    lines = e.content.split("\n")
    w, h = geo.text_size(e.content, e.height, wf)
    x0 = {"center": -w / 2.0, "right": -w}.get(e.halign, 0.0)
    y0 = {"middle": -h / 2.0, "top": -h}.get(e.valign, 0.0)
    for i, line in enumerate(lines):
        at = line.find(old) if old else 0
        if at < 0:
            continue
        piece = old or line
        lx0 = x0 + textmetrics.line_width(line[:at], e.height) * wf if at else x0
        lx1 = lx0 + textmetrics.line_width(piece or " ", e.height) * wf
        ly = y0 + h - e.height / 2.0 - i * e.height * geo.TEXT_LINE_SPACING
        a = geo.translate_point(geo.rotate_point([lx0 - PAD_IN, ly], e.rotation_deg), e.position)
        b = geo.translate_point(geo.rotate_point([lx1 + PAD_IN, ly], e.rotation_deg), e.position)
        page.line(a, b, color)
        if old:
            return


def _field_box(doc: Document, sheet, key: str, dpi: int) -> Optional[Tuple[float, float, float, float]]:
    """Where the title block letters ``key``: the sheet rendered with the field
    blank, against the sheet as it is; the pixels that differ are the field."""
    import numpy as np
    from PIL import Image
    from roaddraft.render.mpl import render_sheet_png
    blank = copy.deepcopy(doc)
    bs = next(s for s in blank.sheets.values() if s.name == sheet.name)
    bs.title_block_fields = dict(bs.title_block_fields or {})
    bs.title_block_fields[key] = ""
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.png", Path(tmp) / "b.png"
        render_sheet_png(doc, sheet, a, dpi=dpi, show_viewport_frames=False)
        render_sheet_png(blank, bs, b, dpi=dpi, show_viewport_frames=False)
        with Image.open(a) as ia, Image.open(b) as ib:
            da = np.asarray(ia.convert("L"), dtype=np.int16)
            db = np.asarray(ib.convert("L"), dtype=np.int16)
    diff = np.abs(da - db) > 40
    rows = np.where(diff.any(axis=1))[0]
    cols = np.where(diff.any(axis=0))[0]
    if not len(rows) or not len(cols):
        return None
    h_in = sheet.height_in
    return (cols.min() / dpi, h_in - (rows.max() + 1) / dpi, (cols.max() + 1) / dpi, h_in - rows.min() / dpi)


def draw_markups(inst: Instance, session: Session, folder: Path) -> Dict[str, Path]:
    """Render the sheet and draw the checker's marks over it: the PNG the model
    looks at and the PDF beside it. Returns ``{"png": ..., "pdf": ...}``."""
    from PIL import Image
    from roaddraft.render.mpl import render_sheet_png
    doc = session.doc
    sheet = _sheet(session, inst.sheet)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "sheet.png"
        render_sheet_png(doc, sheet, base, dpi=DPI, show_viewport_frames=False)
        with Image.open(base) as im:
            page_im = im.convert("RGB")
    w_px, h_px = page_im.size
    canvas = Image.new("RGB", (w_px, h_px + round(KEY_STRIP_IN * DPI)), "white")
    canvas.paste(page_im, (0, 0))
    page = _Page(canvas, sheet.height_in, DPI, inst.hand_in)
    by_id = {e.id: e for e in sheet.entities.values()}

    for m in inst.markups:
        color = KIND_COLOR[m.kind]
        texts = [by_id[i] for i in m.ids]
        if m.kind == "replace":
            e = texts[0]
            _strike(page, doc, e, m.old if m.old != e.content else "", color)
            box = _bbox(doc, texts)
            at = m.note_at or (box[0], box[3] + 0.12)
            page.text(at, m.words(), color)
        elif m.kind == "delete":
            box = _bbox(doc, texts)
            box = (box[0] - PAD_IN, box[1] - PAD_IN, box[2] + PAD_IN, box[3] + PAD_IN)
            page.cross(box, color)
            at = m.note_at or (box[2] + 0.15, box[1])
            page.text(at, m.words(), color)
        elif m.kind == "move":
            box = _bbox(doc, texts)
            box = (box[0] - PAD_IN, box[1] - PAD_IN, box[2] + PAD_IN, box[3] + PAD_IN)
            page.cloud(box, color, step=0.22)
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            # the arrow leaves the box on the side facing the tip
            dx, dy = m.tip[0] - cx, m.tip[1] - cy
            if abs(dx) * (box[3] - box[1]) > abs(dy) * (box[2] - box[0]):
                start = (box[2] if dx > 0 else box[0], cy)
            else:
                start = (cx, box[3] if dy > 0 else box[1])
            page.arrow(start, m.tip, color)
            at = m.note_at or ((start[0] + m.tip[0]) / 2, (start[1] + m.tip[1]) / 2 + 0.12)
            page.text(at, m.words(), color)
        elif m.kind == "add":
            at = m.note_at
            page.text(at, m.words(), color)
            width = page.text_width_in(m.words())
            # the arrow starts at the end of the note nearer the tip
            ends = [(at[0] - 0.1, at[1] + 0.06), (at[0] + width + 0.1, at[1] + 0.06)]
            start = min(ends, key=lambda p: _dist(p, m.tip))
            page.arrow(start, m.tip, color)
        elif m.kind == "comment":
            box = _bbox(doc, texts)
            box = (box[0] - CLOUD_PAD_IN, box[1] - CLOUD_PAD_IN, box[2] + CLOUD_PAD_IN, box[3] + CLOUD_PAD_IN)
            page.cloud(box, color)
            at = m.note_at or (box[2] + 0.2, box[1] + 0.1)
            page.text(at, m.words(), color)
        elif m.kind == "field":
            box = _field_box(doc, sheet, m.key, DPI)
            if box is None:
                raise RuntimeError(f"{inst.id}: the title block does not letter {m.key!r}")
            # the line of the field that carries the words, and roughly their run along it
            value = str((sheet.title_block_fields or {}).get(m.key, ""))
            lines = value.split("\n")
            row = next((k for k, ln in enumerate(lines) if m.old and m.old in ln), 0)
            band = (box[3] - box[1]) / max(1, len(lines))
            cy = box[3] - (row + 0.5) * band
            x0, x1 = box[0], box[2]
            line = lines[row] if lines else ""
            if m.old and m.old in line and len(line) > len(m.old):
                at = line.find(m.old)
                x0 = box[0] + (box[2] - box[0]) * at / len(line)
                x1 = box[0] + (box[2] - box[0]) * (at + len(m.old)) / len(line)
            page.line((x0 - PAD_IN, cy), (x1 + PAD_IN, cy), color)
            at = m.note_at or (x0, box[1] - 0.1 - inst.hand_in * 0.6)
            page.text(at, m.words(), color)
        else:
            raise ValueError(f"unknown markup kind {m.kind!r}")

    # the key at the foot of the page
    y = -KEY_STRIP_IN * 0.55
    x = 0.5
    page.text((x, y), f"REDLINES  {CHECKER}  {CHECKED_ON}", "red")
    x += page.text_width_in(f"REDLINES  {CHECKER}  {CHECKED_ON}") + 1.0
    for words, color in KEY_TEXT:
        page.text((x, y), words, color)
        x += page.text_width_in(words) + 0.8

    png = folder / f"{inst.page}.png"
    pdf = folder / f"{inst.page}.pdf"
    canvas.save(png, format="PNG", optimize=True)
    canvas.save(pdf, format="PDF", resolution=DPI)
    return {"png": png, "pdf": pdf}


def _builder(inst: Instance):
    def build(out: Path) -> Path:
        out = Path(out)
        files = common.stage(out, inst.sheet_id)
        doc_path = files[common.sheet_file(inst.sheet_id)]
        session = common.load(doc_path)
        draw_markups(inst, session, out / MARKUPS)
        return doc_path
    return build


for _inst in INSTANCES:
    common.register(_inst.id, common.sheet_file(_inst.sheet_id), _builder(_inst))


# ------------------------------------------------------------------ the check


def _quote(text: str, limit: int = 60) -> str:
    text = " ".join((text or "").split())
    return repr(text if len(text) <= limit else text[:limit - 1] + "…")


def _reads_near(texts: Sequence[Text], doc: Document, words: str, at, within: float,
                contains: bool = False) -> Optional[Text]:
    want = _norm(words)
    for e in texts:
        have = _norm(e.content)
        if (want in have if contains else have == want) and _dist(_center(doc, e), at) <= within:
            return e
    return None


def _replace_problem(m: Markup, bdoc: Document, sdoc: Document, before: Dict[str, Text],
                     after: List[Text]) -> Optional[str]:
    e = before[m.ids[0]]
    at = _center(bdoc, e)
    want = e.content.replace(m.old, m.new) if m.old and m.old != e.content else m.new
    if _reads_near(after, sdoc, e.content, at, NEAR_IN) is not None and _norm(want) != _norm(e.content):
        return f"{_quote(e.content)} still reads as it did at its place on {m.item.split(' reads')[0]}"
    if _reads_near(after, sdoc, want, at, NEAR_IN) is None:
        return f"no text reads {_quote(want)} where {_quote(e.content)} was"
    return None


def _delete_problem(m: Markup, bdoc: Document, sdoc: Document, before: Dict[str, Text],
                    after_by_id: Dict[str, object], after: List[Text]) -> Optional[str]:
    for i in m.ids:
        e = before[i]
        if i in after_by_id:
            return f"{_quote(e.content)} ({i}) is still on the sheet; the green X asked for it to go"
        if _reads_near(after, sdoc, e.content, _center(bdoc, e), NEAR_IN) is not None:
            return f"a text still reads {_quote(e.content)} where the crossed-out one was"
    return None


def _move_problem(m: Markup, bdoc: Document, sdoc: Document, before: Dict[str, Text],
                  after: List[Text]) -> Optional[str]:
    group = [before[i] for i in m.ids]
    box = _bbox(bdoc, group)
    gc = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    for e in group:
        old = _center(bdoc, e)
        want_at = (m.tip[0] + old[0] - gc[0], m.tip[1] + old[1] - gc[1])
        if _reads_near(after, sdoc, e.content, want_at, MOVE_IN) is None:
            return (f"no text reads {_quote(e.content)} within {MOVE_IN} in of where the arrow "
                    f"points ({want_at[0]:.2f}, {want_at[1]:.2f})")
        if _reads_near(after, sdoc, e.content, old, MOVE_IN) is not None:
            return f"{_quote(e.content)} is still at its old place as well"
    return None


def _box_dist(box, p) -> float:
    """From a point to the nearest point of a box (0 inside it)."""
    dx = max(box[0] - p[0], 0.0, p[0] - box[2])
    dy = max(box[1] - p[1], 0.0, p[1] - box[3])
    return math.hypot(dx, dy)


def _add_problem(m: Markup, sdoc: Document, after: List[Text]) -> Optional[str]:
    want = _norm(m.new)
    for e in after:
        if want in _norm(e.content) and _box_dist(e.bbox(sdoc), m.tip) <= ADD_IN:
            return None
    return (f"no text reading {_quote(m.new)} within {ADD_IN} in of the arrow's tip "
            f"({m.tip[0]:.2f}, {m.tip[1]:.2f})")


def _comment_problem(m: Markup, before: Dict[str, Text], after_by_id: Dict[str, object]) -> Optional[str]:
    for i in m.ids:
        mine = after_by_id.get(i)
        if mine is None:
            return f"{_quote(before[i].content)} ({i}) was removed; the blue cloud asked for no change"
        if not _same(before[i], mine):
            return f"{_quote(before[i].content)} ({i}) was changed; the blue cloud asked for no change"
    return None


def _field_problem(m: Markup, fb: Dict[str, str], fs: Dict[str, str]) -> Optional[str]:
    old, new = str(fb.get(m.key, "")), str(fs.get(m.key, ""))
    want = old.replace(m.old, m.new) if m.old and m.old in old else m.new
    if _norm(new) != _norm(want):
        return f"the title block's {m.key} reads {_quote(new)}, not {_quote(want)}"
    return None


def _base_files(folder: Path, sheet_file: str) -> Dict[str, dict]:
    out = {}
    for p in sorted(Path(folder).glob("*.rdraft")):
        if p.name == sheet_file:
            continue
        d = read_document(p)
        d.pop("meta", None)
        d.pop("journal", None)
        out[p.name] = d
    return out


def _unchanged_problem(inst: Instance, baseline: Session, submitted: Session, touched: set,
                       near: List[Tuple[float, float]], handwriting: List[str]) -> Optional[str]:
    sb, ss = _sheet(baseline, inst.sheet), _sheet(submitted, inst.sheet)
    if ss is None:
        return f"sheet {inst.sheet} is gone"
    bdoc, sdoc = baseline.doc, submitted.doc
    # the sheet's own entities
    for i, e in sb.entities.items():
        if i in touched:
            continue
        mine = ss.entities.get(i)
        if mine is not None and _same(e, mine):
            continue
        if any(_same(e, f) for f in ss.entities.values()):
            continue
        what = f"the text {_quote(e.content)}" if isinstance(e, Text) else f"{type(e).__name__} {i}"
        return f"{what} on {inst.sheet} was changed or removed, and no mark touched it"
    hand = {_norm(h) for h in handwriting}
    for i, e in ss.entities.items():
        if i in sb.entities:
            continue
        if isinstance(e, Text):
            if _norm(e.content) in hand:
                return f"the checker's handwriting {_quote(e.content)} was lettered onto the sheet"
            continue
        if isinstance(e, (Line, Polyline, Arc)) and near and \
                min(_dist(p, q) for p in _points(e) or [(1e9, 1e9)] for q in near) <= NEW_LINE_IN:
            continue
        return f"a new {type(e).__name__} ({i}) was added to {inst.sheet} that no mark asked for"
    # the title block
    fb, fs = dict(sb.title_block_fields or {}), dict(ss.title_block_fields or {})
    fields = {m.key for m in _targets(inst, "field")}
    for k in sorted(set(fb) | set(fs)):
        if k in fields:
            continue
        if str(fb.get(k, "")).strip() != str(fs.get(k, "")).strip():
            return f"the title block's {k} was changed ({fb.get(k)!r} -> {fs.get(k)!r})"
    # the other sheets, model space, and the base files
    for other in bdoc.sheets.values():
        if other.name == inst.sheet:
            continue
        mine = _sheet(submitted, other.name)
        if mine is None or len(mine.entities) != len(other.entities) or \
                any(not _same(e, mine.entities.get(i)) for i, e in other.entities.items() if i in mine.entities):
            return f"sheet {other.name} was changed"
    if len(sdoc.model_entities) != len(bdoc.model_entities) or \
            any(sdoc.model_entities.get(i) is None or not _same(e, sdoc.model_entities[i])
                for i, e in bdoc.model_entities.items()):
        return "model space of the sheet file was changed"
    sheet_file = common.sheet_file(inst.sheet_id)
    before = _base_files(Path(bdoc._path).parent, sheet_file)
    after = _base_files(Path(sdoc._path).parent, sheet_file)
    for name, d in before.items():
        if name not in after:
            return f"the base file {name} is gone"
        if after[name] != d:
            return f"the base file {name} was changed"
    return None


def make_check(inst: Instance):
    def check(baseline: Session, submitted: Session) -> Result:
        t = Tally()
        bdoc, sdoc = baseline.doc, submitted.doc
        sb = _sheet(baseline, inst.sheet)
        ss = _sheet(submitted, inst.sheet)
        before = {e.id: e for e in _texts(sb)}
        after = _texts(ss) if ss is not None else []
        after_by_id = dict(ss.entities) if ss is not None else {}
        fb, fs = dict(sb.title_block_fields or {}), dict(ss.title_block_fields or {}) if ss else {}
        touched: set = set()
        near: List[Tuple[float, float]] = []
        for m in inst.markups:
            if ss is None:
                t.add(m.item, f"sheet {inst.sheet} is gone")
                continue
            if m.kind == "replace":
                touched.update(m.ids)
                t.add(m.item, _replace_problem(m, bdoc, sdoc, before, after))
            elif m.kind == "delete":
                touched.update(m.ids)
                touched.update(_leaders(bdoc, sb, [before[i] for i in m.ids]))
                t.add(m.item, _delete_problem(m, bdoc, sdoc, before, after_by_id, after))
            elif m.kind == "move":
                touched.update(m.ids)
                near.append(m.tip)
                t.add(m.item, _move_problem(m, bdoc, sdoc, before, after))
            elif m.kind == "add":
                near.append(m.tip)
                t.add(m.item, _add_problem(m, sdoc, after))
            elif m.kind == "comment":
                t.add(m.item, _comment_problem(m, before, after_by_id))
            elif m.kind == "field":
                t.add(m.item, _field_problem(m, fb, fs))
        handwriting = [m.words() for m in inst.markups] + [w for w, _c in KEY_TEXT]
        t.add("nothing unrelated changed",
              _unchanged_problem(inst, baseline, submitted, touched, near, handwriting))
        return t.result(f"every mark on {inst.page}.pdf picked up on {inst.sheet}, and nothing else touched")
    return check


# ------------------------------------------------------------------ the solution


def make_solve(inst: Instance, skip: Sequence[str] = (), wrong: str = ""):
    """The scripted solution, each mark picked up the way the check wants it.
    ``skip`` leaves out marks of those kinds; ``wrong`` makes one of the naive
    mistakes the tests try: ``comment`` (acts on the blue cloud), ``keep_old``
    (letters the new value beside the old), ``twin`` (revises the look-alike,
    not the marked text), ``handwriting`` (letters the marks' words onto the
    sheet)."""
    def solve(session: Session) -> None:
        sheet = _sheet(session, inst.sheet)
        doc = session.doc
        layer = next((e.layer for e in _texts(sheet)), "S-ANNO-NOTE")
        for m in inst.markups:
            if m.kind in skip:
                continue
            texts = [sheet.entities[i] for i in m.ids if i in sheet.entities]
            if m.kind == "replace":
                e = texts[0]
                want = e.content.replace(m.old, m.new) if m.old and m.old != e.content else m.new
                if wrong == "keep_old":
                    b = e.bbox(doc)
                    common.ok(session.execute("place_text", {
                        "space": sheet.name, "layer": e.layer, "position": [b[0], b[3] + 0.05],
                        "height": e.height, "content": want}))
                    continue
                target = e
                if wrong == "twin":
                    twin = next((o for o in _texts(sheet) if o.id != e.id
                                 and _norm(o.content) == _norm(e.content)), None)
                    target = twin or e
                common.ok(session.execute("modify_entity", {"id": target.id,
                                                            "changes": {"content": want}}))
            elif m.kind == "delete":
                ids = [e.id for e in texts] + _leaders(doc, sheet, texts)
                common.ok(session.execute("delete_entities", {"ids": ids}))
            elif m.kind == "move":
                box = _bbox(doc, texts)
                gc = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                common.ok(session.execute("move_entities", {
                    "ids": [e.id for e in texts], "delta": [m.tip[0] - gc[0], m.tip[1] - gc[1]]}))
            elif m.kind == "add":
                common.ok(session.execute("place_text", {
                    "space": sheet.name, "layer": layer, "position": list(m.tip),
                    "height": inst.text_in, "content": m.new, "halign": "left", "valign": "middle"}))
            elif m.kind == "comment":
                if wrong == "comment":
                    common.ok(session.execute("delete_entities", {"ids": [e.id for e in texts]}))
            elif m.kind == "field":
                old = str((sheet.title_block_fields or {}).get(m.key, ""))
                want = old.replace(m.old, m.new) if m.old and m.old in old else m.new
                common.ok(session.execute("fill_title_block", {"sheet": sheet.name,
                                                               "fields": {m.key: want}}))
            if wrong == "handwriting" and m.kind in ("delete", "move"):
                at = m.note_at or (m.tip if m.tip else (1.0, 1.0))
                common.ok(session.execute("place_text", {
                    "space": sheet.name, "layer": layer, "position": list(at),
                    "height": inst.text_in, "content": m.words()}))
    return solve


# ------------------------------------------------------------------ the probes


PROMPT = (
    "Sheet {sheet} came back from checking as a marked-up PDF, {page}.pdf in the project's "
    "{folder} folder; {page}.png beside it is the same page as an image. Look at it with "
    "view_attachment, zooming in with region to read the handwriting. The markups are the whole "
    "brief: nothing else says what to change. Pick up every one of them on {sheet} by the key at "
    "the foot of the page (red: revise as marked; green: delete; blue: a comment only, nothing to "
    "change), make each edit where the mark sits, and leave everything else exactly as it is.")


def _probe(inst: Instance) -> Probe:
    prompt = PROMPT.format(sheet=inst.sheet, page=inst.page, folder=MARKUPS)
    return Probe(id=inst.id, prompt=prompt, check=make_check(inst), solve=make_solve(inst),
                 note=inst.note, tags=["redline-understanding", "markup", "scan", "edit"] + list(inst.tags),
                 start=inst.id, server_args=list(SERVER_ARGS))


PROBES: List[Probe] = [_probe(i) for i in INSTANCES]

__all__ = ["PROBES", "INSTANCES", "Instance", "Markup", "draw_markups", "make_check", "make_solve",
           "MARKUPS", "SERVER_ARGS", "DPI"]
