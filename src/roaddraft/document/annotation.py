"""Annotation scales: AutoCAD's annotation scale / Civil 3D's drawing scale.

Annotation is designed in *paper* units (a 0.10 in label, a 0.20 in tick,
a 0.32 in label offset) and drafted in *model* units. The document keeps a
list of named plot scales (``1"=50'`` = 50 feet per inch), a current
annotation scale, and the paper-unit defaults; annotation commands convert
paper sizes to feet through the current scale when a caller omits explicit
sizes, and stamp the entities they create with an ``annotative`` record
(``{"scale", "height_in", "offset_in" | "half_len_in"}``) so
``set_annotation_scale`` can re-size them for another plot scale.

With the annotation scale **off** (``settings.annotation_scale`` = null, the
default) the engine's fixed feet defaults apply unchanged (8 ft text, 10 ft
ticks, 16 ft offsets) and nothing is stamped.

This module is pure data helpers; it imports nothing from commands/api/web.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

DEFAULT_SCALES = (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 100.0, 200.0, 500.0)  # feet per inch
DEFAULT_PAPER = {"text_height_in": 0.10, "tick_half_len_in": 0.20, "label_offset_in": 0.32}
PAPER_KEYS = tuple(DEFAULT_PAPER)
# engine defaults in feet when the annotation scale is off
FIXED_MODEL_SIZES = {"text_height": 8.0, "tick_half_len": 10.0, "label_offset": 16.0}
_PAPER_TO_MODEL = {"text_height_in": "text_height", "tick_half_len_in": "tick_half_len",
                   "label_offset_in": "label_offset"}

_EQ_RE = re.compile(r"""^\s*1\s*(?:"|''|in(?:ch)?)?\s*=\s*(\d+(?:\.\d+)?)\s*(?:'|ft|feet)?\s*$""",
                    re.IGNORECASE)
_RATIO_RE = re.compile(r"^\s*1\s*:\s*(\d+(?:\.\d+)?)\s*$")
_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*$")


def format_scale(feet_per_inch: float) -> str:
    """``50 -> 1"=50'``."""
    return f"1\"={float(feet_per_inch):g}'"


def parse_scale(value) -> float:
    """A plot scale as feet per inch from ``50``, ``"1\\"=50'"``, ``"1:600"``
    or ``"50"``.  Raises ``ValueError`` for anything else or a non-positive
    value."""
    if isinstance(value, bool):
        raise ValueError(f"scale must be a number or '1\"=50\\'', not {value!r}")
    if isinstance(value, (int, float)):
        fpi = float(value)
    elif isinstance(value, str):
        text = value.strip()
        m = _EQ_RE.match(text)
        if m:
            fpi = float(m.group(1))
        else:
            m = _RATIO_RE.match(text)
            if m:
                fpi = float(m.group(1)) / 12.0
            else:
                m = _NUM_RE.match(text)
                if not m:
                    raise ValueError(f"cannot parse scale {value!r}; use 50, '1\"=50\\'' or "
                                     f"'1:600'")
                fpi = float(m.group(1))
    else:
        raise ValueError(f"scale must be a number or '1\"=50\\'', not {value!r}")
    if fpi <= 0:
        raise ValueError("scale must be positive (feet per inch)")
    return fpi


def default_scale_list() -> List[Dict[str, object]]:
    return [{"name": format_scale(f), "feet_per_inch": float(f)} for f in DEFAULT_SCALES]


def default_settings() -> dict:
    """Annotation keys of a new document's ``settings``."""
    return {"annotation_scale": None, "annotation_scales": default_scale_list(),
            "annotation_paper": dict(DEFAULT_PAPER)}


# ------------------------------------------------------------ document


def current_scale(doc) -> Optional[float]:
    """The current annotation scale in feet per inch, or None when off."""
    value = doc.settings.get("annotation_scale")
    return None if value is None else float(value)


def scale_list(doc) -> List[Dict[str, object]]:
    return [dict(s) for s in (doc.settings.get("annotation_scales") or [])]


def scale_name(doc, feet_per_inch: Optional[float]) -> str:
    """The list name for a scale (``1"=50'``), or its formatted value."""
    if feet_per_inch is None:
        return "off"
    for s in scale_list(doc):
        if abs(float(s["feet_per_inch"]) - float(feet_per_inch)) < 1e-9:
            return str(s["name"])
    return format_scale(feet_per_inch)


def paper_defaults(doc) -> Dict[str, float]:
    return {**DEFAULT_PAPER, **{k: float(v) for k, v in
                                (doc.settings.get("annotation_paper") or {}).items()
                                if k in DEFAULT_PAPER}}


def model_sizes(doc) -> Optional[Dict[str, float]]:
    """Paper defaults × the current scale as model feet
    (``text_height``, ``tick_half_len``, ``label_offset``), or None when off."""
    scale = current_scale(doc)
    if scale is None:
        return None
    paper = paper_defaults(doc)
    return {_PAPER_TO_MODEL[k]: paper[k] * scale for k in PAPER_KEYS}


def size_defaults(doc) -> Dict[str, float]:
    """Model sizes to use when a command omits them: scaled paper defaults
    when the annotation scale is on, the fixed engine defaults otherwise."""
    return model_sizes(doc) or dict(FIXED_MODEL_SIZES)


def text_record(doc, height_ft: float, label_offset_ft: Optional[float] = None) -> Optional[dict]:
    """``annotative`` record for a model-space text (None when the scale is off)."""
    scale = current_scale(doc)
    if scale is None:
        return None
    rec = {"scale": scale, "height_in": float(height_ft) / scale}
    if label_offset_ft is not None:
        rec["offset_in"] = float(label_offset_ft) / scale
    return rec


def tick_record(doc, half_len_ft: float) -> Optional[dict]:
    """``annotative`` record for a station tick line (None when off)."""
    scale = current_scale(doc)
    if scale is None:
        return None
    return {"scale": scale, "half_len_in": float(half_len_ft) / scale}


__all__ = ["DEFAULT_SCALES", "DEFAULT_PAPER", "PAPER_KEYS", "FIXED_MODEL_SIZES", "format_scale",
           "parse_scale", "default_scale_list", "default_settings", "current_scale",
           "scale_list", "scale_name", "paper_defaults", "model_sizes", "size_defaults",
           "text_record", "tick_record"]
