"""Print to PDF: page setup (paper, orientation, scale, margin, monochrome).

The PDF's own MediaBox is the assertion of record -- a plot that claims a
paper size has to *be* that size on the page.
"""
import re
from pathlib import Path

import pytest

from roaddraft.api.lines import print_params
from roaddraft.api.session import Session, _paper_scale
from roaddraft.render import mpl
from tests.test_render import draft_small_project


def page_sizes_in(path):
    """(width, height) in inches of every page of a PDF, from its MediaBox."""
    data = Path(path).read_bytes()
    return [(round(float(box.split()[2]) / 72.0, 4),
             round(float(box.split()[3]) / 72.0, 4))
            for box in re.findall(rb"/MediaBox \[([^\]]+)\]", data)]


def test_a_sheet_prints_at_its_own_size(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {})
    assert r["ok"] and r["page_count"] == 1
    page = r["pages"][0]
    assert page["space"] == "C-101" and page["paper"] == "ANSI_D"
    assert page["scale"] == "1:1 (full size)"
    assert page["printed_in"] == [34.0, 22.0]
    assert page_sizes_in(r["path"]) == [(34.0, 22.0)]


def test_fitting_a_d_sheet_on_b_paper_is_a_half_size_set(tmp_path):
    s = draft_small_project(tmp_path)
    s.execute("create_sheet", {"name": "C-102", "size": "ANSI_D"})
    r = s.query("print_pdf", {"paper": "ANSI_B"})
    assert r["ok"] and r["page_count"] == 2
    assert [p["space"] for p in r["pages"]] == ["C-101", "C-102"]
    assert all(p["scale"] == "1:2 (half size)" for p in r["pages"])
    assert page_sizes_in(r["path"]) == [(17.0, 11.0), (17.0, 11.0)]


@pytest.mark.parametrize("scale", [0.5, "1:2", "50%", "half"])
def test_half_size_says_the_same_thing_four_ways(tmp_path, scale):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_B",
                              "scale": scale})
    assert r["ok"] and r["pages"][0]["printed_in"] == [17.0, 11.0]


def test_model_prints_at_the_plot_scale_asked_for(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "model", "paper": "ANSI_D",
                              "scale": 50, "bounds": [1000, 900, 2600, 1300]})
    page = r["pages"][0]
    assert page["feet_per_inch"] == 50.0 and page["scale"] == "1\"=50'"
    assert page["window_ft"] == [1000, 900, 2600, 1300]   # exact, no margin
    assert page["printed_in"] == [32.0, 8.0]              # 1600 ft / 50, 400/50
    assert page_sizes_in(r["path"]) == [(34.0, 22.0)]


def test_model_scale_strings_match_the_annotation_scale_grammar(tmp_path):
    s = draft_small_project(tmp_path)
    fpi = [s.query("print_pdf", {"space": "model", "scale": v})
           ["pages"][0]["feet_per_inch"] for v in (50, "1\"=50'", "1:600")]
    assert fpi == [50.0, 50.0, 50.0]


def test_fit_uses_the_whole_page_in_one_direction(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "model", "paper": "ANSI_B"})
    printed = r["pages"][0]["printed_in"]
    assert printed[0] == pytest.approx(17.0) or printed[1] == pytest.approx(11.0)
    assert printed[0] <= 17.0 + 1e-6 and printed[1] <= 11.0 + 1e-6


def test_portrait_turns_the_paper(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "model", "paper": "ANSI_A",
                              "orientation": "portrait"})
    assert r["pages"][0]["paper_in"] == [8.5, 11.0]
    assert page_sizes_in(r["path"]) == [(8.5, 11.0)]


def test_a_margin_shrinks_the_fit(tmp_path):
    s = draft_small_project(tmp_path)
    full = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_B"})
    inset = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_B",
                                  "margin_in": 1.0})
    assert inset["pages"][0]["printed_in"][0] < full["pages"][0]["printed_in"][0]
    assert inset["pages"][0]["printed_in"] == [13.909, 9.0]   # 15 x 9 in area
    assert page_sizes_in(inset["path"]) == [(17.0, 11.0)]     # paper is unchanged


def test_a_model_plot_that_would_not_fit_names_a_scale_that_does(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "model", "paper": "ANSI_B", "scale": 10})
    assert not r["ok"]
    assert "1\"=10'" in r["error"]["message"] and "ANSI_B" in r["error"]["message"]
    hint = r["error"]["hint"]
    assert "fit" in hint and "1\"=100'" in hint        # the next standard scale
    assert s.query("print_pdf", {"space": "model", "paper": "ANSI_B",
                                 "scale": 100})["ok"]  # and it really does fit


def test_a_sheet_plot_that_would_not_fit_says_so(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_A", "scale": 1})
    assert not r["ok"]
    assert "34 x 22 in" in r["error"]["message"]
    assert "fit" in r["error"]["hint"]


def test_a_margin_that_eats_the_paper_fails_cleanly(tmp_path):
    s = draft_small_project(tmp_path)
    r = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_A",
                              "margin_in": 6})
    assert not r["ok"] and "printable area" in r["error"]["message"]


def test_printing_faults_teach_the_way_back(tmp_path):
    s = draft_small_project(tmp_path)
    both = s.query("print_pdf", {"space": "C-101", "sheets": ["C-101"]})
    assert not both["ok"] and "not both" in both["error"]["message"]
    windowed = s.query("print_pdf", {"space": "C-101", "bounds": [0, 0, 1, 1]})
    assert not windowed["ok"] and "model-space window" in windowed["error"]["message"]
    no_paper = s.query("print_pdf", {"space": "model", "paper": "sheet"})
    assert not no_paper["ok"] and "ANSI_D" in no_paper["error"]["hint"]
    empty = Session(out_dir=str(tmp_path)).query("print_pdf", {})
    assert not empty["ok"] and "create_sheet" in empty["error"]["hint"]
    assert "space='model'" in empty["error"]["hint"]      # and the other way out


def test_sheets_print_as_one_job(tmp_path):
    s = draft_small_project(tmp_path)
    s.execute("create_sheet", {"name": "C-102", "size": "ANSI_B"})
    r = s.query("print_pdf", {"sheets": ["C-102", "C-101"]})
    assert [p["space"] for p in r["pages"]] == ["C-102", "C-101"]
    assert page_sizes_in(r["path"]) == [(17.0, 11.0), (34.0, 22.0)]  # own papers


def test_monochrome_plots_every_color_black(tmp_path):
    s = draft_small_project(tmp_path)
    line = list(s.doc.model_entities.values())[0]         # on layer CL (red)
    assert mpl._props(s.doc, line)[0] == "#CC0000"     # the CAD palette's red
    assert mpl._props(s.doc, line, mono=True)[0] == "#000000"
    r = s.query("print_pdf", {"space": "C-101", "monochrome": True})
    assert r["ok"] and r["monochrome"] is True


def test_lineweights_only_scale_when_asked(tmp_path):
    s = draft_small_project(tmp_path)
    line = list(s.doc.model_entities.values())[0]
    s.doc.layers["CL"].lineweight_mm = 1.0                # thick enough to halve
    assert mpl._props(s.doc, line, lw_scale=0.5)[2] == \
        pytest.approx(mpl._props(s.doc, line)[2] / 2)
    plain = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_B"})
    scaled = s.query("print_pdf", {"space": "C-101", "paper": "ANSI_B",
                                   "scale_lineweights": True,
                                   "path": str(tmp_path / "thin.pdf")})
    assert plain["ok"] and scaled["ok"]                   # same page, thinner ink


def test_default_names_say_what_was_printed(tmp_path):
    s = draft_small_project(tmp_path)
    s.execute("create_sheet", {"name": "C-102", "size": "ANSI_D"})
    assert s.query("print_pdf", {"space": "C-101"})["path"].endswith(
        "C-101-print.pdf")
    assert s.query("print_pdf", {"space": "model"})["path"].endswith(
        "RenderTest-model-print.pdf")
    assert s.query("print_pdf", {})["path"].endswith("RenderTest-print.pdf")


def test_paper_scale_grammar():
    assert _paper_scale(0.5) == 0.5
    assert _paper_scale("1:4") == 0.25
    assert _paper_scale("25%") == 0.25
    assert _paper_scale("full") == 1.0
    for bad in ("1:0", "0", -1, "wat", True):
        with pytest.raises(ValueError):
            _paper_scale(bad)


def test_a_print_line_prints_the_space_you_are_in():
    assert print_params([], "SH-001")[0] == {"space": "SH-001"}
    assert print_params(["model"], "SH-001")[0] == {"space": "model"}
    assert print_params(["all"], "SH-001")[0] == {}          # every sheet
    assert print_params(["paper=ANSI_B", "scale=1:2"], "model")[0] == {
        "space": "model", "paper": "ANSI_B", "scale": "1:2"}
    assert "space" not in print_params(['sheets=["C-101"]'], "SH-001")[0]


def test_fit_scale_and_paper_size_are_plain_arithmetic():
    assert mpl.paper_size("ANSI_D") == (34.0, 22.0)
    assert mpl.paper_size("ANSI_D", "portrait") == (22.0, 34.0)
    assert mpl.printable_area((34.0, 22.0), 0.5) == (33.0, 21.0)
    assert mpl.fit_scale((34.0, 22.0), (17.0, 11.0)) == 0.5
