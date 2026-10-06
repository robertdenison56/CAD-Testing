"""RoadDraft — headless 2D CAD engine for AI drafting agents (and humans).

Core structure mirrors production CAD:
  - Model space (AutoCAD model space / MicroStation design model), US survey feet
  - Sheets (AutoCAD paper-space layouts / MicroStation sheet models), inches,
    with viewports that window into model space at a plot scale
  - Layers (levels), text styles, blocks (cells), title blocks

Every mutation goes through the command bus as a serializable command; the full
document state is always available as JSON. See RoadDraft_Build_Plan.md.
"""
__version__ = "0.1.0"
__all__ = ["Session", "Document", "__version__"]


def __getattr__(name):
    """``Session`` and ``Document`` load on first use, not with the package:
    Session brings in matplotlib, and the desktop app has to choose
    matplotlib's cache folder before anything imports it."""
    if name == "Session":
        from roaddraft.api.session import Session as value
    elif name == "Document":
        from roaddraft.document.document import Document as value
    else:
        raise AttributeError(f"module 'roaddraft' has no attribute {name!r}")
    globals()[name] = value
    return value
