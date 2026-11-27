"""The grounded drafter on the real training sheets (``d1-train-real``, 2026-11-27): the
task kinds it did not cover before: a real sheet's base files, an agency border's title
block, a sheet set up on an agency border, and a curve table on a sheet too full to read whole."""
import pytest

from roaddraft.eval import taskset as ts
from roaddraft.tasks.real import TRAIN_SHEET_IDS, real_sheets, train_sheets
from roaddraft.trajectories import grounded as g


def _entry(sheet_id: str, task_type: str) -> dict:
    return next(e for e in ts.entries("d1-train-real")
                if e["sheet_id"] == sheet_id and e["task_type"] == task_type)


def test_the_training_sheets_are_no_catalogue_sheets():
    catalogue = {s.id for s in real_sheets()}
    assert not catalogue & TRAIN_SHEET_IDS
    assert {s.id for s in train_sheets()} == set(TRAIN_SHEET_IDS)
    held = {e["sheet_id"] for name in ("d1-real", "d1-real-hard", "d1-real-dev")
            for e in ts.load(name)["tasks"]}
    held |= {e["sheet_id"] for e in ts.load("pilot-dev")["tasks"] if e.get("sheet_id")}
    assert not held & TRAIN_SHEET_IDS


def test_the_real_training_set_names_only_training_sheets_and_shares_none():
    manifest = ts.load("d1-train-real")
    assert {e["sheet_id"] for e in manifest["tasks"]} <= set(TRAIN_SHEET_IDS)
    for name in ts.NAMES:
        assert ts.shared(manifest, ts.load(name)) == []


def test_a_title_block_in_an_agency_borders_words_is_read_both_ways():
    full = "Fill in the title block of sheet SC-1 of a Caltrans plan set (PPM-128): " \
           "Project number & phase: PROJECT NUMBER & PHASE; Sheet: SC-1."
    assert g.stated_border_title(full, "caltrans") == [
        ("Project number & phase", "project_number_phase", "PROJECT NUMBER & PHASE"),
        ("Sheet", "sheet_id", "SC-1")]
    short = "Sheet L-39 is blank. Annotate the SB10 line; title block: route 65, sheet L-39."
    assert g.stated_border_title(short, "caltrans") == [("Route", "route", "65"),
                                                        ("Sheet", "sheet_id", "L-39")]
    assert g.stated_border_title(short, "standard") is None
    assert g.stated_border_title("Station the A line.", "caltrans") is None


def test_stated_layout_reads_the_border_a_task_names():
    text = ("Set up plan sheet SC-1 for the A line: ANSI D, on the caltrans border (create_sheet "
            "title_block_template 'caltrans'), the viewport turned -79.47° as published.")
    ask = g.stated_layout(text)
    assert ask["border"] == "caltrans" and ask["size"] == "ANSI_D" and ask["twist"] == -79.47


@pytest.mark.parametrize("task_type", ["real-attach-reference", "real-title-block",
                                       "real-sheet-setup", "real-curve-table"])
@pytest.mark.parametrize("level", ["vague", "explicit"])
def test_the_drafter_records_the_kinds_it_did_not_cover(task_type, level, tmp_path):
    task = ts.task_from_entry(_entry("PPM-128", task_type))
    row = g.record_task(task, level, out_root=tmp_path, run_id="t")
    assert row["kept"], (row["termination"], row["effective"], row["error"], row["ungrounded"])


def test_two_bearings_that_meet_are_set_apart(tmp_path):
    # PPM-129's line ends in two 46 ft tangents: their bearings, each at its tangent's middle,
    # stand on one another until one of the two is moved
    task = ts.task_from_entry(_entry("PPM-129", "real-bearings"))
    row = g.record_task(task, "vague", out_root=tmp_path, run_id="t")
    assert row["kept"], (row["termination"], row["effective"], row["error"], row["lost"])
