"""Raster (PNG) and PDF rendering via matplotlib.

Sheets render at true paper size (1 figure inch = 1 sheet inch), so text
heights and lineweights are WYSIWYG. Viewport contents are model geometry
mapped through the viewport similarity transform and clipped to the viewport
rectangle. PNG renders are the vision observation for AI agents.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.patches import Arc as MplArc  # noqa: E402
from matplotlib.patches import Circle as MplCircle  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from roaddraft.core import colors as colorlib  # noqa: E402
from roaddraft.core import geometry as geo  # noqa: E402
from roaddraft.core.units import lineweight_points  # noqa: E402
from roaddraft.document.entities import (  # noqa: E402
    Arc, Circle, Line, Polyline, Text, expand_entities,
)

DASH_PATTERNS = {
    "continuous": None,
    "dashed": (6, 3),
    "center": (12, 3, 3, 3),
    "hidden": (4, 3),
    "dot": (1, 3),
    "phantom": (12, 3, 3, 3, 3, 3),
}

_VALIGN = {"bottom": "bottom", "middle": "center", "top": "top"}

# AutoCAD-style dark model background; near-black linework flips to light so
# 'black/white' (ACI 7) reads correctly on both paper and screen.
DARK_BG = "#1E2227"
_DARK_FLIP = {"#000000": "#E8E8E8", "#FFFFFF": "#E8E8E8"}


def _props(doc, e, dark=False):
    layer = doc.layers.get(e.layer)
    color = e.color or (layer.color if layer else "black")
    try:
        hex_color = colorlib.to_hex(color)
    except ValueError:
        hex_color = "#000000"
    if dark:
        hex_color = _DARK_FLIP.get(hex_color, hex_color)
    linetype = e.linetype or (layer.linetype if layer else "continuous")
    dashes = DASH_PATTERNS.get(linetype)
    lw_mm = getattr(e, "_lw_mm", None) or (layer.lineweight_mm if layer else 0.25)
    lw = max(lineweight_points(lw_mm), 0.4)
    return hex_color, dashes, lw


def _visible(doc, e):
    layer = doc.layers.get(e.layer)
    return layer.visible if layer else True


def _linestyle(dashes):
    return "solid" if dashes is None else (0, dashes)


def draw_primitives(ax, doc, prims, ppd, clip=None, dark=False):
    """Draw primitive entities on ax. ppd = font points per drawing unit (72
    for sheets drawn at paper size). clip is an optional Patch already on ax."""
    for e in prims:
        if not _visible(doc, e):
            continue
        color, dashes, lw = _props(doc, e, dark=dark)
        artists = []
        if isinstance(e, Line):
            artists = ax.plot([e.start[0], e.end[0]], [e.start[1], e.end[1]],
                              color=color, lw=lw, linestyle=_linestyle(dashes),
                              solid_capstyle="butt")
        elif isinstance(e, Polyline):
            verts = list(e.vertices) + ([e.vertices[0]] if e.closed else [])
            artists = ax.plot([v[0] for v in verts], [v[1] for v in verts],
                              color=color, lw=lw, linestyle=_linestyle(dashes),
                              solid_capstyle="butt")
        elif isinstance(e, Arc):
            s, end = geo.arc_sweep(e.start_angle_deg, e.end_angle_deg)
            patch = MplArc(tuple(e.center), 2 * e.radius, 2 * e.radius,
                           theta1=s, theta2=end, edgecolor=color, lw=lw,
                           linestyle=_linestyle(dashes), fill=False)
            ax.add_patch(patch)
            artists = [patch]
        elif isinstance(e, Circle):
            patch = MplCircle(tuple(e.center), e.radius, edgecolor=color, lw=lw,
                              linestyle=_linestyle(dashes), fill=False)
            ax.add_patch(patch)
            artists = [patch]
        elif isinstance(e, Text):
            style = doc.text_styles.get(e.style)
            stretch = style.width_factor if style else 1.0
            artist = ax.text(e.position[0], e.position[1], e.content,
                             fontsize=max(e.height * ppd, 1.0),
                             rotation=e.rotation_deg, rotation_mode="anchor",
                             ha=e.halign, va=_VALIGN.get(e.valign, "bottom"),
                             color=color, clip_on=clip is not None,
                             linespacing=geo.TEXT_LINE_SPACING,
                             stretch=int(min(max(stretch * 100, 50), 200)))
            artists = [artist]
        if clip is not None:
            for artist in artists:
                artist.set_clip_path(clip)


def _new_axes(width_in, height_in):
    fig = plt.figure(figsize=(width_in, height_in), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width_in)
    ax.set_ylim(0, height_in)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def _space_groups(doc, space_key):
    """(props_doc, primitives) groups for one space: visible references first
    (drawn underneath), then the host's own entities. props_doc supplies layer
    colors/linetypes/visibility for its group."""
    from roaddraft.document.references import reference_groups

    groups = [(base, prims)
              for _ref, base, prims in reference_groups(doc, space_key)]
    if space_key == "model":
        own = list(doc.model_entities.values())
    else:
        own = list(doc.sheets[space_key].entities.values())
    groups.append((doc, expand_entities(doc, own)))
    return groups


def sheet_figure(doc, sheet, show_viewport_frames=True):
    from roaddraft.render.titleblock import title_block_entities

    fig, ax = _new_axes(sheet.width_in, sheet.height_in)
    ax.add_patch(Rectangle((0, 0), sheet.width_in, sheet.height_in,
                           fill=False, edgecolor="#CCCCCC", lw=0.5))
    draw_primitives(ax, doc, title_block_entities(sheet), ppd=72.0)

    model_groups = _space_groups(doc, "model")
    for vp in sheet.viewports:
        bb = vp.paper_bbox()
        frame = Rectangle((bb[0], bb[1]), vp.width_in, vp.height_in, fill=False,
                          edgecolor="#BBBBBB" if show_viewport_frames else "none",
                          lw=0.5, linestyle=(0, (2, 2)))
        ax.add_patch(frame)
        t = vp.transform()
        window = geo.bbox_expand(t.visible_model_bbox(vp.width_in, vp.height_in),
                                 vp.feet_per_inch)  # small cull margin
        for props_doc, prims in model_groups:
            visible = [p for p in prims
                       if p.bbox(props_doc) is None
                       or geo.bbox_intersects(p.bbox(props_doc), window)]
            transformed = [p.transformed(t.to_paper, t.rotation_deg, t.scale)
                           for p in visible]
            draw_primitives(ax, props_doc, transformed, ppd=72.0, clip=frame)

    for props_doc, prims in _space_groups(doc, sheet.id):
        draw_primitives(ax, props_doc, prims, ppd=72.0)
    return fig


def render_sheet_png(doc, sheet, path, dpi=150, show_viewport_frames=True):
    fig = sheet_figure(doc, sheet, show_viewport_frames)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)


def model_figure(doc, bounds=None, max_size_in=14.0, dark=False):
    """Build a figure of model space (own entities + visible references).
    dark=True renders on the AutoCAD-style dark canvas. Returns
    (figure, bounds_drawn)."""
    from roaddraft.document.references import extents_with_references

    explicit = bounds is not None
    bounds = bounds or extents_with_references(doc, "model") \
        or (0.0, 0.0, 100.0, 100.0)
    if bounds[2] - bounds[0] <= 0 or bounds[3] - bounds[1] <= 0:
        bounds = geo.bbox_expand(bounds, 50.0)
    if not explicit:  # margin only around auto-fit; zoom windows stay exact
        bounds = geo.bbox_expand(bounds, 0.05 * max(bounds[2] - bounds[0],
                                                    bounds[3] - bounds[1]))
    dw, dh = bounds[2] - bounds[0], bounds[3] - bounds[1]
    scale = max_size_in / max(dw, dh)
    bg = DARK_BG if dark else "white"
    fig = plt.figure(figsize=(dw * scale, dh * scale), facecolor=bg)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(bg)
    ax.set_xlim(bounds[0], bounds[2])
    ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal")
    ax.axis("off")
    for props_doc, prims in _space_groups(doc, "model"):
        draw_primitives(ax, props_doc, prims, ppd=scale * 72.0, dark=dark)
    return fig, bounds


def render_model_png(doc, path, bounds=None, dpi=150, max_size_in=14.0,
                     dark=False):
    fig, bounds = model_figure(doc, bounds=bounds, max_size_in=max_size_in,
                               dark=dark)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return bounds


def export_pdf(doc, path, sheets):
    with PdfPages(path) as pdf:
        for sheet in sheets:
            fig = sheet_figure(doc, sheet, show_viewport_frames=False)
            pdf.savefig(fig)
            plt.close(fig)
