"""The icon builder (packaging/make_icons.py): the artwork's black corners go,
the icon sits on Apple's grid, and the .icns files come out whole."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat, features

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "make_icons", ROOT / "packaging" / "make_icons.py")
make_icons = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_icons)

pytestmark = pytest.mark.skipif(not features.check("webp"),
                                reason="this Pillow cannot read WebP")


@pytest.fixture(scope="module")
def art():
    return Image.open(make_icons.ART).convert("RGB")


def test_the_rounded_square_is_found_inside_the_black(art):
    x0, y0, x1, y1 = make_icons.body_box(art)
    assert x1 - x0 == y1 - y0
    assert 30 < x0 < 50 and 30 < y0 < 50  # the black margin is left out
    assert max(art.getpixel((x0 - 5, (y0 + y1) // 2))) <= 4  # WebP's black


def test_the_app_icon_sits_on_apples_grid(art):
    icon = make_icons.app_icon(art)
    assert icon.size == (1024, 1024)
    alpha = icon.getchannel("A")
    assert alpha.getpixel((0, 0)) == 0
    assert alpha.getpixel((105, 105)) < 8   # beyond the corner's curve: no black
    assert alpha.getpixel((512, 512)) == 255
    assert alpha.getpixel((512, 108)) == 255  # the shape reaches the grid line
    assert alpha.getpixel((512, 60)) < 5      # and leaves the margin clear


def test_the_document_icon_is_a_labelled_page(art):
    doc = make_icons.document_icon(art)
    assert doc.size == (1024, 1024)
    assert doc.getchannel("A").getpixel((20, 20)) == 0
    assert doc.getpixel((300, 200))[:3] == (252, 252, 253)  # the page
    label = doc.crop((340, 780, 690, 890))
    assert min(px[0] for px in label.getdata()) < 120     # the extension's text


def test_the_small_document_icon_has_no_label(art):
    doc = make_icons.document_icon(art, small=True)
    label = doc.crop((340, 850, 690, 900))  # below the larger artwork
    assert min(px[0] for px in label.getdata()) > 240


@pytest.mark.skipif(not shutil.which("iconutil"), reason="needs macOS iconutil")
def test_the_icns_files_take_small_sizes_from_the_small_art(tmp_path,
                                                            monkeypatch):
    monkeypatch.setattr(make_icons, "OUT", tmp_path)
    assert make_icons.main() == 0
    for name in ("RoadDraft.icns", "RoadDraft-document.icns"):
        assert (tmp_path / name).read_bytes()[:4] == b"icns"
    assert Image.open(tmp_path / "RoadDraft.png").size == (1024, 1024)
    assert (tmp_path / "preview.png").is_file()

    unpacked = tmp_path / "unpacked.iconset"
    subprocess.run(["iconutil", "-c", "iconset", str(tmp_path / "RoadDraft.icns"),
                    "-o", str(unpacked)], check=True)
    large = make_icons.app_icon(Image.open(make_icons.ART).convert("RGB"))
    small = make_icons.app_icon(Image.open(make_icons.ART_SMALL).convert("RGB"))

    def distance(png, master):
        """Mean difference over every band. (iconutil re-encodes the 16 px
        slot in the old icns format, so not even it matches exactly.)"""
        got = Image.open(unpacked / png).convert("RGBA")
        diff = ImageChops.difference(got, master.resize(got.size, Image.LANCZOS))
        return sum(ImageStat.Stat(diff).mean)

    for png in ("icon_16x16.png", "icon_32x32.png", "icon_32x32@2x.png"):
        assert distance(png, small) < distance(png, large), png
    for png in ("icon_128x128.png", "icon_512x512@2x.png"):
        assert distance(png, large) == 0 < distance(png, small), png
