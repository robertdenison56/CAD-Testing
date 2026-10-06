"""Build RoadDraft's macOS icons from the artwork in packaging/icon/.

    .venv-build/bin/python packaging/make_icons.py

writes, under build/icons/ (macOS only: iconutil makes the .icns files):

  RoadDraft.icns            the app icon
  RoadDraft-document.icns   the icon a .rdraft file shows in Finder
  RoadDraft.png             the app icon at 1024 px (the desktop window's Dock
                            icon while it runs from the development .venv)
  RoadDraft-document.png    the document icon at 1024 px
  preview.png               both, at the sizes macOS shows them

The artwork is a rounded square on solid black, filling its canvas. Used as
it is, the Dock would show a black square bigger than its neighbours. So the
rounded square is cut out along its own corner curve (circular, about 22% of
its width, as Apple's are), and set on Apple's icon grid: an 824 px shape in
a 1024 px canvas, with the soft shadow macOS icons carry.

Small icons get artwork of their own: the R without the ROADDRAFT wordmark,
which a 16 or 32 point icon cannot show legibly, and a document page with the
R drawn larger and no extension label.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
ART = HERE / "icon" / "roaddraft-art.webp"
ART_SMALL = HERE / "icon" / "roaddraft-art-small.webp"  # the R alone
OUT = HERE.parent / "build" / "icons"

#: Icon slots this many points across and under (1x and 2x) use the small art.
SMALL_POINTS = 32

CANVAS = 1024
BODY = 824                # Apple's macOS icon grid: the shape inside the canvas
CORNER = 0.2225           # corner radius / width, measured on the artwork
INSET = 3                 # px of the artwork's edge left out with the black
SUPERSAMPLE = 4           # masks are drawn this much larger, then reduced

#: The sizes an .iconset holds: (points, scale) -> icon_<p>x<p>[@2x].png
ICONSET = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
           (256, 1), (256, 2), (512, 1), (512, 2)]

LABEL_FONTS = [("/System/Library/Fonts/HelveticaNeue.ttc", 1),  # Bold
               ("/System/Library/Fonts/Helvetica.ttc", 1)]


def body_box(art: Image.Image, threshold: int = 12):
    """The artwork's rounded square: the bounding box of everything brighter
    than the black around it, made square about its centre."""
    lit = art.convert("L").point(lambda v: 255 if v > threshold else 0)
    x0, y0, x1, y1 = lit.getbbox()
    side = min(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return (round(cx - side / 2), round(cy - side / 2),
            round(cx - side / 2) + side, round(cy - side / 2) + side)


def rounded_mask(size: int, radius_ratio: float, inset: float = 0) -> Image.Image:
    """An anti-aliased rounded-square mask, ``size`` px across."""
    big = size * SUPERSAMPLE
    pad = inset * SUPERSAMPLE
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (pad, pad, big - 1 - pad, big - 1 - pad),
        radius=radius_ratio * (big - 2 * pad), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def shadow(mask: Image.Image, opacity: float, blur: float) -> Image.Image:
    alpha = mask.point(lambda v: round(v * opacity))
    shade = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    shade.putalpha(alpha)
    return shade.filter(ImageFilter.GaussianBlur(blur))


def app_body(art: Image.Image, size: int) -> Image.Image:
    """The artwork's rounded square alone, ``size`` px, corners transparent."""
    box = body_box(art)
    scale = size / (box[2] - box[0])
    body = art.crop(box).convert("RGBA").resize((size, size), Image.LANCZOS)
    body.putalpha(rounded_mask(size, CORNER, INSET * scale))
    return body


def app_icon(art: Image.Image) -> Image.Image:
    """The app icon, on Apple's grid with its shadow, at 1024 px."""
    body = app_body(art, BODY)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    margin = (CANVAS - BODY) // 2
    canvas.alpha_composite(shadow(body.getchannel("A"), 0.35, 14),
                           (margin, margin + 10))
    canvas.alpha_composite(body, (margin, margin))
    return canvas


def label_font(size: int):
    for path, index in LABEL_FONTS:
        try:
            return ImageFont.truetype(path, size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def document_icon(art: Image.Image, label: str = "RDRAFT",
                  small: bool = False) -> Image.Image:
    """A page with its corner turned down, the app's artwork on it and the
    file extension under it: how macOS draws an app's document icon. The
    small version draws the artwork larger and leaves the label off, which
    no small icon could show."""
    s = SUPERSAMPLE
    W, top, bottom, fold = 680, 72, 952, 170
    left = (CANVAS - W) // 2
    right = left + W
    big = Image.new("RGBA", (CANVAS * s, CANVAS * s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(big)
    page = [(left * s, top * s), ((right - fold) * s, top * s),
            (right * s, (top + fold) * s), (right * s, bottom * s),
            (left * s, bottom * s)]
    draw.polygon(page, fill=(252, 252, 253, 255), outline=(196, 200, 207, 255),
                 width=5 * s)
    corner = [((right - fold) * s, top * s), ((right - fold) * s, (top + fold) * s),
              (right * s, (top + fold) * s)]
    draw.polygon(corner, fill=(226, 229, 234, 255), outline=(196, 200, 207, 255),
                 width=5 * s)
    page_img = big.resize((CANVAS, CANVAS), Image.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(shadow(page_img.getchannel("A"), 0.25, 10), (0, 8))
    canvas.alpha_composite(page_img)

    size, y = (560, 260) if small else (430, 260)
    body = app_body(art, size)
    canvas.alpha_composite(shadow(body.getchannel("A"), 0.30, 8),
                           ((CANVAS - size) // 2, y + 8))
    canvas.alpha_composite(body, ((CANVAS - size) // 2, y))
    if small:
        return canvas

    font = label_font(92)
    draw = ImageDraw.Draw(canvas)
    l, t, r, b = draw.textbbox((0, 0), label, font=font)
    draw.text(((CANVAS - (r - l)) / 2 - l, 790 - t), label, font=font,
              fill=(88, 96, 110, 255))
    return canvas


def write_icns(master: Image.Image, name: str, out: Path,
               small: Image.Image = None) -> Path:
    """Every size an .iconset holds, reduced from the 1024 px master (from
    ``small`` for the slots of SMALL_POINTS and under), packed with iconutil
    into ``out/<name>.icns``."""
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / f"{name}.iconset"
        iconset.mkdir()
        for points, scale in ICONSET:
            px = points * scale
            source = small if small is not None and points <= SMALL_POINTS \
                else master
            img = source if px == CANVAS else source.resize((px, px), Image.LANCZOS)
            suffix = "@2x" if scale == 2 else ""
            img.save(iconset / f"icon_{points}x{points}{suffix}.png")
        target = out / f"{name}.icns"
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o",
                        str(target)], check=True)
    return target


def preview(app, doc, app_small, doc_small) -> Image.Image:
    """Both icons at the sizes macOS shows them, on a light and a dark ground:
    the 32 and 16 px ones from the small artwork, as the .icns files hold."""
    sizes = [256, 128, 64, 32, 16]
    row_h, pad = 300, 24
    width = pad + sum(s + pad for s in sizes)
    sheet = Image.new("RGBA", (width, row_h * 4), (0, 0, 0, 255))
    grounds = [(245, 245, 247, 255), (30, 30, 32, 255)]
    rows = [(app, app_small, grounds[0]), (app, app_small, grounds[1]),
            (doc, doc_small, grounds[0]), (doc, doc_small, grounds[1])]
    for r, (icon, small, ground) in enumerate(rows):
        band = Image.new("RGBA", (width, row_h), ground)
        x = pad
        for s in sizes:
            source = small if s <= SMALL_POINTS else icon
            band.alpha_composite(source.resize((s, s), Image.LANCZOS),
                                 (x, (row_h - s) // 2))
            x += s + pad
        sheet.alpha_composite(band, (0, r * row_h))
    return sheet


def main(argv=None) -> int:
    if not shutil.which("iconutil"):
        print("make_icons needs macOS: iconutil is not on PATH", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    art = Image.open(ART).convert("RGB")
    small_art = Image.open(ART_SMALL).convert("RGB")
    app, app_small = app_icon(art), app_icon(small_art)
    doc, doc_small = document_icon(art), document_icon(small_art, small=True)
    app.save(OUT / "RoadDraft.png")
    doc.save(OUT / "RoadDraft-document.png")
    for path in (write_icns(app, "RoadDraft", OUT, app_small),
                 write_icns(doc, "RoadDraft-document", OUT, doc_small)):
        print(f"wrote {path}")
    preview(app, doc, app_small, doc_small).save(OUT / "preview.png")
    print(f"wrote {OUT / 'preview.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
