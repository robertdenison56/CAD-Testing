"""Raster (PNG) and PDF rendering via matplotlib.

Sheets render at true paper size (1 figure inch = 1 sheet inch), so text
heights and lineweights are WYSIWYG. Viewport contents are model geometry
mapped through the viewport similarity transform and clipped to the viewport
rectangle. PNG renders are the vision observation for AI agents.

Printing (``print_pdf``) is the plot side of the same drawing code: a page is
a *paper* of some size with the content -- a sheet, or a window of model space
-- centered on it at a chosen scale. A sheet plotted at 0.5 is a half-size
set; model space plotted at 50 is 1" = 50'.
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
    Arc, Circle, Hatch, Line, Point, Polyline, Text, expand_entities, loop_points,
)
from roaddraft.document.sheets import SHEET_SIZES  # noqa: E402

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


def _props(doc, e, dark=False, mono=False, lw_scale=1.0):
    layer = doc.layers.get(e.layer)
    color = e.color or (layer.color if layer else "black")
    try:
        hex_color = colorlib.to_hex(color)
    except ValueError:
        hex_color = "#000000"
    if mono:                                  # monochrome plot: everything black
        hex_color = "#000000"
    elif dark:
        hex_color = _DARK_FLIP.get(hex_color, hex_color)
    linetype = e.linetype or (layer.linetype if layer else "continuous")
    dashes = DASH_PATTERNS.get(linetype)
    lw_mm = getattr(e, "_lw_mm", None) or (layer.lineweight_mm if layer else 0.25)
    lw = max(lineweight_points(lw_mm) * lw_scale, 0.4)
    return hex_color, dashes, lw


def _visible(doc, e):
    layer = doc.layers.get(e.layer)
    return layer.visible if layer else True


def _linestyle(dashes):
    return "solid" if dashes is None else (0, dashes)


def draw_primitives(ax, doc, prims, ppd, clip=None, dark=False, mono=False,
                    lw_scale=1.0):
    """Draw primitive entities on ax. ppd = font points per drawing unit (72
    for sheets drawn at paper size). clip is an optional Patch already on ax.
    mono plots every color black; lw_scale scales plotted lineweights (a
    half-size plot with 'scale lineweights' on passes 0.5)."""
    for e in prims:
        if not _visible(doc, e):
            continue
        color, dashes, lw = _props(doc, e, dark=dark, mono=mono, lw_scale=lw_scale)
        artists = []
        if isinstance(e, Line):
            artists = ax.plot([e.start[0], e.end[0]], [e.start[1], e.end[1]],
                              color=color, lw=lw, linestyle=_linestyle(dashes),
                              solid_capstyle="butt")
        elif isinstance(e, Polyline):
            verts = e.points()
            artists = ax.plot([v[0] for v in verts], [v[1] for v in verts],
                              color=color, lw=lw, linestyle=_linestyle(dashes),
                              solid_capstyle="butt")
        elif isinstance(e, Point):
            draw_primitives(ax, doc, e.primitives(doc), ppd, clip=clip, dark=dark,
                            mono=mono, lw_scale=lw_scale)
            continue
        elif isinstance(e, Hatch):
            artists = _hatch_artists(ax, e, color, lw)
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


def _hatch_artists(ax, e, color, lw):
    """A hatch: its fill (SOLID) or its pattern's dashes, inside its loops."""
    from matplotlib.collections import LineCollection
    from matplotlib.patches import PathPatch
    from matplotlib.path import Path as MplPath

    from roaddraft.document import hatching, regions

    loops = regions.oriented(e.loops)  # outer CCW, islands CW: holes stay holes
    polygons = [loop_points(loop, 3.0) for loop in loops]
    if e.solid:
        verts, codes = [], []
        for poly in polygons:
            verts += [tuple(v) for v in poly] + [tuple(poly[0])]
            codes += [MplPath.MOVETO] + [MplPath.LINETO] * (len(poly) - 1) + \
                [MplPath.CLOSEPOLY]
        patch = PathPatch(MplPath(verts, codes), facecolor=color, edgecolor="none",
                          alpha=e.opacity, lw=0)
        ax.add_patch(patch)
        return [patch]
    segments, _too_dense = hatching.pattern_segments(polygons, e.pattern, e.scale,
                                                     e.angle_deg)
    if not segments:
        return []
    collection = LineCollection([(tuple(a), tuple(b)) for a, b in segments],
                                colors=color, linewidths=max(lw * 0.6, 0.3),
                                alpha=e.opacity, capstyle="round")
    ax.add_collection(collection)
    return [collection]


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


def draw_sheet(ax, doc, sheet, show_viewport_frames=True, ppd=72.0, mono=False,
               lw_scale=1.0):
    """Draw a whole sheet -- border, title block, viewport contents, paper-space
    annotation -- on ax, whose data units are sheet inches. ppd is 72 times the
    printed inches per sheet inch (72 at full size)."""
    from roaddraft.render.titleblock import title_block_entities

    ax.add_patch(Rectangle((0, 0), sheet.width_in, sheet.height_in,
                           fill=False, edgecolor="#CCCCCC", lw=0.5))
    draw_primitives(ax, doc, title_block_entities(sheet), ppd=ppd, mono=mono,
                    lw_scale=lw_scale)

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
            draw_primitives(ax, props_doc, transformed, ppd=ppd, clip=frame,
                            mono=mono, lw_scale=lw_scale)

    for props_doc, prims in _space_groups(doc, sheet.id):
        draw_primitives(ax, props_doc, prims, ppd=ppd, mono=mono,
                        lw_scale=lw_scale)


def sheet_figure(doc, sheet, show_viewport_frames=True):
    fig, ax = _new_axes(sheet.width_in, sheet.height_in)
    draw_sheet(ax, doc, sheet, show_viewport_frames)
    return fig


def render_sheet_png(doc, sheet, path, dpi=150, show_viewport_frames=True):
    fig = sheet_figure(doc, sheet, show_viewport_frames)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)


def model_window(doc, bounds=None):
    """The model window a render or print covers: the window asked for, or the
    extents of everything visible (own entities + references) with a margin."""
    from roaddraft.document.references import extents_with_references

    explicit = bounds is not None
    bounds = bounds or extents_with_references(doc, "model") \
        or (0.0, 0.0, 100.0, 100.0)
    if bounds[2] - bounds[0] <= 0 or bounds[3] - bounds[1] <= 0:
        bounds = geo.bbox_expand(bounds, 50.0)
    if not explicit:  # margin only around auto-fit; zoom windows stay exact
        bounds = geo.bbox_expand(bounds, 0.05 * max(bounds[2] - bounds[0],
                                                    bounds[3] - bounds[1]))
    return tuple(bounds)


def fit_aspect(bounds, aspect):
    """Grow a window about its centre to width / height = ``aspect``: the
    shape of the screen area it is shown in, as a CAD window shows more of
    model space when it is wider than the drawing."""
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    if w / h < aspect:
        grow = (h * aspect - w) / 2
        return (x0 - grow, y0, x1 + grow, y1)
    grow = (w / aspect - h) / 2
    return (x0, y0 - grow, x1, y1 + grow)


def model_figure(doc, bounds=None, max_size_in=14.0, dark=False, aspect=None):
    """Build a figure of model space (own entities + visible references).
    dark=True renders on the AutoCAD-style dark canvas; ``aspect`` (width /
    height) widens the window to fill a screen area of that shape. Returns
    (figure, bounds_drawn)."""
    bounds = model_window(doc, bounds)
    if aspect:
        bounds = fit_aspect(bounds, aspect)
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
    draw_model(ax, doc, ppd=scale * 72.0, dark=dark)
    return fig, bounds


def draw_model(ax, doc, ppd, dark=False, mono=False, lw_scale=1.0):
    """Draw model space -- own entities and everything the references show --
    on ax, whose data units are model feet."""
    for props_doc, prims in _space_groups(doc, "model"):
        draw_primitives(ax, props_doc, prims, ppd=ppd, dark=dark, mono=mono,
                        lw_scale=lw_scale)


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


# --------------------------------------------------------------- printing

def paper_size(name, orientation="landscape"):
    """(width_in, height_in) of a named paper, turned to the orientation.
    SHEET_SIZES are stored landscape."""
    if name not in SHEET_SIZES:
        raise KeyError(name)
    w, h = SHEET_SIZES[name]
    return (h, w) if orientation == "portrait" else (w, h)


def printable_area(paper, margin_in=0.0):
    """The paper minus an unprintable margin on all four sides."""
    return (paper[0] - 2 * margin_in, paper[1] - 2 * margin_in)


def fit_scale(content, area):
    """Largest uniform scale that puts a content rectangle inside an area.
    Both are (width, height) in the same units."""
    return min(area[0] / content[0], area[1] / content[1])


def _page_axes(fig, paper, window, scale):
    """Axes covering `window` (x0, y0, x1, y1 in data units), centered on the
    page, at `scale` printed inches per data unit."""
    pw, ph = paper
    w = (window[2] - window[0]) * scale
    h = (window[3] - window[1]) * scale
    ax = fig.add_axes([(pw - w) / 2.0 / pw, (ph - h) / 2.0 / ph, w / pw, h / ph])
    ax.set_xlim(window[0], window[2])
    ax.set_ylim(window[1], window[3])
    ax.set_aspect("equal")
    ax.axis("off")
    return ax


def page_figure(doc, page):
    """One plotted page. `page` is a resolved page setup:

    sheet: {kind: 'sheet', sheet: Sheet, paper: (w, h), scale: printed inches
            per sheet inch, mono: bool, lw_scale: float}
    model: {kind: 'model', bounds: (x0, y0, x1, y1), paper: (w, h),
            feet_per_inch: float, mono: bool, lw_scale: float}
    """
    paper = page["paper"]
    mono = page.get("mono", False)
    lw_scale = page.get("lw_scale", 1.0)
    fig = plt.figure(figsize=paper, facecolor="white")
    if page["kind"] == "sheet":
        sheet, scale = page["sheet"], page["scale"]
        window = (0.0, 0.0, sheet.width_in, sheet.height_in)
        ax = _page_axes(fig, paper, window, scale)
        draw_sheet(ax, doc, sheet, show_viewport_frames=False, ppd=72.0 * scale,
                   mono=mono, lw_scale=lw_scale)
    else:
        scale = 1.0 / page["feet_per_inch"]        # printed inches per foot
        ax = _page_axes(fig, paper, page["bounds"], scale)
        draw_model(ax, doc, ppd=72.0 * scale, mono=mono, lw_scale=lw_scale)
    return fig


def print_pdf(doc, path, pages):
    """Plot resolved pages to a multi-page PDF, one page per setup. Each page
    is its own paper size, so a print job may mix papers."""
    with PdfPages(path) as pdf:
        for page in pages:
            fig = page_figure(doc, page)
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return path
