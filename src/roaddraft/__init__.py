"""RoadDraft — headless 2D CAD engine for AI drafting agents (and humans).

Core structure mirrors production CAD:
  - Model space (AutoCAD model space / MicroStation design model), US survey feet
  - Sheets (AutoCAD paper-space layouts / MicroStation sheet models), inches,
    with viewports that window into model space at a plot scale
  - Layers (levels), text styles, blocks (cells), title blocks

Every mutation goes through the command bus as a serializable command; the full
document state is always available as JSON. See RoadDraft_Build_Plan.md.
"""
from roaddraft.api.session import Session
from roaddraft.document.document import Document

__version__ = "0.1.0"
__all__ = ["Session", "Document", "__version__"]
