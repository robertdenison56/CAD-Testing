"""Overlay a published plan sheet on its redraft: the published sheet in blue, the
redraft in red, black where they agree.

The published PDF is a reduced print, so it is registered onto the redraft's paper
with the calibration measured off its border (l4_geometry.PDF_SCALE / PDF_OFFSET):
an extracted point e (2 x page inches) is a full-size sheet point at (e - offset) / scale.

    python overlay.py <published page PNG at 2*dpi> <redraft PNG at dpi> <out.png>
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

Image.MAX_IMAGE_PIXELS = None
SHEET_W, SHEET_H = 34.0, 22.0


def overlay(orig_png, redraft_png, out_png, scale=None, offset=None, page_h=SHEET_H):
    if scale is None or offset is None:
        sys.path.insert(0, str(Path(__file__).parent))
        import l4_geometry as G
        scale, offset = G.PDF_SCALE, G.PDF_OFFSET
    red = Image.open(redraft_png).convert("L")
    W, H = red.size
    dpi = W / SHEET_W
    page = Image.open(orig_png).convert("L")
    # the published page is rendered at 2 x dpi per page inch, i.e. dpi per extract unit
    # redraft pixel (u, v) -> published pixel: e = full * scale + offset, e * dpi
    ox, oy = offset
    matrix = (scale, 0, ox * dpi, 0, scale, (page_h - oy - SHEET_H * scale) * dpi)
    pub = page.transform((W, H), Image.AFFINE, matrix, resample=Image.BILINEAR, fillcolor=255)
    r, o = ImageOps.invert(red), ImageOps.invert(pub)
    rgb = Image.merge("RGB", (ImageOps.invert(o), ImageOps.invert(ImageChops.lighter(r, o)),
                              ImageOps.invert(r)))
    rgb.save(out_png)
    return out_png


if __name__ == "__main__":
    overlay(*sys.argv[1:4])
