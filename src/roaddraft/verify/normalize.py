"""Content normalization for label, table and title-block comparison.

Whitespace runs collapse to one space and curly quotes and primes fold to
their straight forms, and nothing else: station format, DMS format, case and
the ``BC `` prefix all still count (eval plan section 3.3 step 4).
"""
from __future__ import annotations

_FOLD = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "´": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
})


def normalize(text) -> str:
    """``text`` with whitespace collapsed and quotes/primes straightened."""
    return " ".join(str(text).translate(_FOLD).split())


__all__ = ["normalize"]
