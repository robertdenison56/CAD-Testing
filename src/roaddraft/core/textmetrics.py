"""Lettering metrics of the font the renderer draws text in.

A text's height is the height of its capital letters: what CAD, the DXF export
and Caltrans drafting standards all mean by text height, so a 0.14 in note has
0.14 in capitals. A font's em, which matplotlib's fontsize sets, is taller than
its capitals: DejaVu Sans, matplotlib's default font and so the renderer's, has
capitals 0.729 em high. These measure that font, so the renderer can size text
by its capitals and the engine's text box is as wide as the letters drawn.

Each font file is read once, lazily (matplotlib's font machinery loads with the
first text measured), and each character's advance is cached.
"""
from __future__ import annotations

import threading
from functools import lru_cache

CAP_GLYPH = "H"  # flat-topped and on the baseline: its height is the cap height


def font_path() -> str:
    """The font file text is drawn in: matplotlib's default font, which the
    renderer uses for every text. A text style names a font, but the renderer
    does not draw in it, so it is not measured either."""
    from matplotlib.font_manager import FontProperties, findfont
    return findfont(FontProperties())


class FontMetrics:
    """Cap height and character advances of one font file, in ems."""

    def __init__(self, path: str):
        from matplotlib import ft2font
        flags = getattr(ft2font, "LoadFlags", None)       # matplotlib >= 3.10
        self._no_hinting = flags.NO_HINTING if flags else ft2font.LOAD_NO_HINTING
        self._font = ft2font.FT2Font(path, hinting_factor=1)
        self._em = float(self._font.units_per_EM)
        self._font.set_size(self._em, 72)                 # one pixel per font unit
        self._lock = threading.Lock()                     # FT2Font is not thread safe
        self._advances = {}
        with self._lock:
            glyph = self._font.load_char(ord(CAP_GLYPH), flags=self._no_hinting)
        self.cap_height = glyph.horiBearingY / 64.0 / self._em

    def advance(self, char: str) -> float:
        """How far one character moves the pen, in ems. A character the font
        lacks gets the font's missing-glyph box, as the renderer draws it."""
        a = self._advances.get(char)
        if a is None:
            with self._lock:
                glyph = self._font.load_char(ord(char), flags=self._no_hinting)
            a = self._advances[char] = glyph.linearHoriAdvance / 65536.0 / self._em
        return a


@lru_cache(maxsize=None)
def metrics(path: str) -> FontMetrics:
    return FontMetrics(path)


@lru_cache(maxsize=1)
def _renderer_metrics() -> FontMetrics:
    return metrics(font_path())


def cap_height_ratio() -> float:
    """Cap height over em of the renderer's font (0.729 for DejaVu Sans): a
    text of height h is drawn at an em, matplotlib's fontsize, of h / this."""
    return _renderer_metrics().cap_height


def line_width(line: str, height: float) -> float:
    """Advance width of one line of text whose capitals are ``height`` tall, in
    the units of height. Kerning is left out: it moves drafting text by well
    under 1 %."""
    m = _renderer_metrics()
    return sum(m.advance(c) for c in line) * height / m.cap_height
