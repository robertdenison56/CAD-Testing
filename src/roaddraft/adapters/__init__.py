"""Program/file-format adapters at the edges of the engine.

Adapters translate between external formats and the canonical design model.
They import only ``roaddraft.core`` and ``roaddraft.design`` — never commands,
api, web, document, or tasks — and no CAD-program libraries.

- ``landxml``: LandXML 1.2 alignments (Line/Curve CoordGeom, station
  equations) and profiles (PVI/ParaCurve) in and out, stdlib XML only.
"""
