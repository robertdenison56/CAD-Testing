"""RoadDraft task generation: design standards, drafting specs, task briefs.

Phase 1 contents (see the Phase 1 build spec, section 7):

- ``standards``  -- DRAFT AASHTO-derived lookup tables (minimum radius,
  maximum grade, minimum K) used by the task generator to draw plausible
  designs.  Every value is marked for PE review.
- ``spec_v1``    -- ``DRAFTING_SPEC_V1``, the DRAFT drafting specification a
  D1 plan-sheet task is graded against, plus ``spec_hash`` / ``spec_subset``.
- ``brief``, ``generator``, ``ground_truth``, ``reference``, ``__main__`` --
  task briefs, the seeded D1 generator, verifier ground truth and the
  reference solution (added by a later work package).

``standards`` and ``spec_v1`` are pure data with tiny helpers and import only
the standard library; the other modules may import ``design``, ``api`` and
``document``.  Nothing in ``design``, ``adapters`` or ``document`` imports
this package.
"""
