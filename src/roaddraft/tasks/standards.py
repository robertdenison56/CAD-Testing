"""Design-standard lookup tables for the task generator.  Frozen with spec v1 (2026-10-16).

Every table below is a transcription of AASHTO "A Policy on Geometric Design
of Highways and Streets", 7th ed. (2018) made from memory, without page
citations.  They exist so that the D1 task generator draws *plausible*
alignments and profiles (radius >= minimum, grade <= maximum, K >= minimum);
they are NOT a published standard.  They were frozen as they stand with
``DRAFTING_SPEC_V1`` v1 (the PE's freeze, 2026-10-16), since every design the
task sets carry was drawn within them; a corrected table changes those
designs, so it mints new task ids (the generator version in every id)
instead of silently re-scoring old ones.

This module imports only the standard library.
"""
from __future__ import annotations

from typing import Dict

STANDARDS_STATUS = "FROZEN — with the drafting spec v1, 2026-10-16; AASHTO 2018 values as transcribed, not a published standard"

# AASHTO "A Policy on Geometric Design of Highways and Streets", 7th ed. (2018), Table 3-7,
# minimum radius (ft) for e_max = 6 %. DRAFT: transcribed from memory; a PE must verify before release.
MIN_RADIUS_FT_EMAX6: Dict[int, int] = {15: 39, 20: 81, 25: 144, 30: 231, 35: 340, 40: 485, 45: 643, 50: 833,
                                       55: 1060, 60: 1330, 65: 1660, 70: 2040, 75: 2500, 80: 3050}

# AASHTO 2018, rural collectors, level terrain, maximum grade (%). DRAFT.
MAX_GRADE_PCT: Dict[int, int] = {30: 7, 35: 7, 40: 7, 45: 7, 50: 6, 55: 6, 60: 5}

# AASHTO 2018 Tables 3-34 (crest, stopping sight distance) and 3-36 (sag), minimum K (ft per % A). DRAFT.
MIN_K_CREST: Dict[int, int] = {30: 19, 35: 29, 40: 44, 45: 61, 50: 84, 55: 114, 60: 151, 65: 193, 70: 247}
MIN_K_SAG: Dict[int, int] = {30: 37, 35: 49, 40: 64, 45: 79, 50: 96, 55: 115, 60: 136, 65: 157, 70: 181}

MIN_VC_LENGTH_FT = 200.0          # simplification of "L >= 3V" for V <= 65; DRAFT

CURVE_TYPES = ("crest", "sag")


def _lookup(table: Dict[int, int], v_mph: float, what: str) -> float:
    """Return ``table[v_mph]`` as a float, with a teaching error for unknown speeds."""
    try:
        return float(table[v_mph])
    except (KeyError, TypeError):
        speeds = ", ".join(str(v) for v in sorted(table))
        raise ValueError(
            "no %s value for design speed %r mph; tabulated speeds: %s" % (what, v_mph, speeds)
        ) from None


def min_radius(v_mph: float) -> float:
    """Minimum horizontal curve radius (ft) for design speed ``v_mph`` at e_max = 6 %.

    Exact table lookup (no interpolation); ``min_radius(45) == 643``.  Raises
    ``ValueError`` listing the tabulated speeds when ``v_mph`` is not in the table.
    """
    return _lookup(MIN_RADIUS_FT_EMAX6, v_mph, "minimum radius")


def max_grade(v_mph: float) -> float:
    """Maximum grade (percent) for design speed ``v_mph`` (rural collector, level terrain).

    Exact table lookup; ``max_grade(50) == 6``.  Raises ``ValueError`` for speeds
    outside the table.
    """
    return _lookup(MAX_GRADE_PCT, v_mph, "maximum grade")


def min_k(v_mph: float, curve_type: str) -> float:
    """Minimum rate of vertical curvature K (ft per % of A) for a crest or sag curve.

    ``curve_type`` is ``"crest"`` (stopping sight distance) or ``"sag"``
    (headlight sight distance); ``min_k(45, "crest") == 61`` and
    ``min_k(45, "sag") == 79``.  Raises ``ValueError`` for an unknown curve type
    or a speed outside the table.
    """
    if curve_type == "crest":
        return _lookup(MIN_K_CREST, v_mph, "minimum K (crest)")
    if curve_type == "sag":
        return _lookup(MIN_K_SAG, v_mph, "minimum K (sag)")
    raise ValueError("curve_type must be 'crest' or 'sag', not %r" % (curve_type,))
