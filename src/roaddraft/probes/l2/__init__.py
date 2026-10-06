"""Caltrans sheet L-2 (03-But-70, PM 46.0/47.0, LAYOUT), rebuilt as a two-file
plan set: ``build_model`` writes the design file, ``build_sheet`` the sheet file
that references it.

It lives in the package because the tier-3 probes start from it (``fixture``
start ``l2``); ``examples/caltrans_l2/`` drives the same builders to rebuild
the published sheet, render it, and seed variants of it.
"""
