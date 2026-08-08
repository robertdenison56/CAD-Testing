"""Color handling: named CAD colors or '#RRGGBB' hex strings.

Named colors map to AutoCAD Color Index (ACI) values for DXF export and to hex
for on-screen rendering. Entity color None means ByLayer.
"""
from __future__ import annotations

NAMED_HEX = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#CC0000",
    "yellow": "#B8860B",
    "green": "#007700",
    "cyan": "#008B8B",
    "blue": "#0000CC",
    "magenta": "#AA00AA",
    "gray": "#808080",
    "grey": "#808080",
}

NAMED_ACI = {
    "red": 1,
    "yellow": 2,
    "green": 3,
    "cyan": 4,
    "blue": 5,
    "magenta": 6,
    "black": 7,
    "white": 7,
    "gray": 8,
    "grey": 8,
}


def is_valid(color: str) -> bool:
    return color in NAMED_HEX or _is_hex(color)


def _is_hex(color: str) -> bool:
    if not (isinstance(color, str) and color.startswith("#") and len(color) == 7):
        return False
    try:
        int(color[1:], 16)
        return True
    except ValueError:
        return False


def to_hex(color: str) -> str:
    if _is_hex(color):
        return color.upper()
    if color in NAMED_HEX:
        return NAMED_HEX[color]
    raise ValueError(
        f"unknown color {color!r}; use one of {sorted(set(NAMED_HEX) - {'grey'})} or '#RRGGBB'"
    )


def to_aci(color: str):
    """ACI code for a named color, or None if the color needs DXF true-color."""
    return NAMED_ACI.get(color)


def to_rgb(color: str):
    h = to_hex(color)
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
