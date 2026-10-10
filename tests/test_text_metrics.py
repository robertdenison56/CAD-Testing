"""Text is drawn as CAD letters it: a text's height is the height of its capitals,
in renders and plots alike, and its box (geo.text_bbox) is where the letters land.

matplotlib sizes text by the em, which is taller than the capitals (DejaVu Sans:
capitals are 0.729 em), so a 0.14 in note used to plot with 0.10 in capitals.
"""
import numpy as np
import pytest
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

from roaddraft.api.session import Session
from roaddraft.core import geometry as geo
from roaddraft.core import textmetrics
from roaddraft.document.document import Document
from roaddraft.document.entities import Text
from roaddraft.render import mpl as R

DPI = 400
PX = 1.0 / DPI


def _ink(fig, dpi=DPI):
    """Bounds of a figure's dark pixels, in figure inches with y up."""
    fig.set_dpi(dpi)
    fig.canvas.draw()
    img = np.asarray(fig.canvas.buffer_rgba())
    R.plt.close(fig)
    ys, xs = np.nonzero(img[..., 0] < 128)
    h = img.shape[0]
    return (xs.min() / dpi, (h - 1 - ys.max()) / dpi, (xs.max() + 1) / dpi,
            (h - ys.min()) / dpi)


def _drawn(entity, size=(3.0, 2.0)):
    fig, ax = R._new_axes(*size)
    R.draw_primitives(ax, Document(), [entity], ppd=72.0)
    return _ink(fig)


def test_cap_height_ratio_is_the_renderer_fonts_capital_h():
    cap = TextPath((0, 0), "H", size=1.0, prop=FontProperties()).get_extents().y1
    assert textmetrics.cap_height_ratio() == pytest.approx(cap, rel=1e-3)
    assert 0.6 < cap < 0.8        # DejaVu Sans: 1493 / 2048 = 0.729


@pytest.mark.parametrize("valign", ["bottom", "middle", "top"])
def test_a_capital_is_as_tall_as_the_text_height_and_sits_in_its_box(valign):
    e = Text(position=[1.0, 1.0], content="H", height=0.25, valign=valign)
    x0, y0, x1, y1 = _drawn(e)
    assert y1 - y0 == pytest.approx(0.25, rel=0.03)
    box = geo.text_bbox(e.position, e.content, e.height, valign=valign)
    assert y0 == pytest.approx(box[1], abs=2 * PX)     # baseline
    assert y1 == pytest.approx(box[3], abs=2 * PX)     # cap line
    assert box[0] - PX <= x0 and x1 <= box[2] + PX     # side bearings inside


def test_lines_are_text_line_spacing_apart_and_fill_the_box():
    e = Text(position=[1.0, 1.8], content="H\nH\nH", height=0.2, valign="top")
    _x0, y0, _x1, y1 = _drawn(e)
    box = geo.text_bbox(e.position, e.content, e.height, valign="top")
    assert box[3] - box[1] == pytest.approx(0.2 * (1 + 2 * geo.TEXT_LINE_SPACING))
    assert (y0, y1) == pytest.approx((box[1], box[3]), abs=2 * PX)


@pytest.mark.parametrize("halign, x", [("left", 0.3), ("center", 1.5), ("right", 2.7)])
def test_the_box_is_as_wide_as_the_letters(halign, x):
    e = Text(position=[x, 0.5], content="EDGE OF PAVEMENT", height=0.15, halign=halign)
    x0, _y0, x1, _y1 = _drawn(e, size=(3.0, 1.0))
    box = geo.text_bbox(e.position, e.content, e.height, halign=halign)
    assert box[0] - PX <= x0 and x1 <= box[2] + PX
    assert (x1 - x0) / (box[2] - box[0]) > 0.97         # all but E's and T's side bearings


def _sheet_session(tmp_path):
    s = Session(project_name="TextHeight", out_dir=str(tmp_path))
    s.execute("create_sheet", {"name": "T-1", "width_in": 4.0, "height_in": 3.0,
                               "title_block_template": "none"})
    s.execute("place_text", {"space": "T-1", "position": [1.0, 1.0], "content": "H",
                             "height": 0.3})
    s.execute("place_text", {"space": "model", "position": [50.0, 30.0], "content": "H",
                             "height": 10.0})
    return s, next(iter(s.doc.sheets.values()))


def test_render_sheet_letters_paper_text_at_its_height(tmp_path):
    s, sheet = _sheet_session(tmp_path)
    _x0, y0, _x1, y1 = _ink(R.sheet_figure(s.doc, sheet))
    assert (y0, y1) == pytest.approx((1.0, 1.3), abs=2 * PX)


def test_a_half_size_plot_letters_sheet_text_at_half_its_height(tmp_path):
    s, sheet = _sheet_session(tmp_path)
    page = {"kind": "sheet", "sheet": sheet, "paper": (2.0, 1.5), "scale": 0.5}
    _x0, y0, _x1, y1 = _ink(R.page_figure(s.doc, page))
    assert y1 - y0 == pytest.approx(0.15, rel=0.03)


def test_a_model_plot_letters_model_text_at_its_height_over_the_scale(tmp_path):
    s, _sheet = _sheet_session(tmp_path)
    page = {"kind": "model", "bounds": (0.0, 0.0, 100.0, 75.0), "paper": (2.0, 1.5),
            "feet_per_inch": 50.0}
    _x0, y0, _x1, y1 = _ink(R.page_figure(s.doc, page))
    assert y1 - y0 == pytest.approx(10.0 / 50.0, rel=0.03)
    assert y0 == pytest.approx(30.0 / 50.0, abs=2 * PX)  # on its baseline
