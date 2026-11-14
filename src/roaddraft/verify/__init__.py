"""The RoadDraft verifier: a deterministic score for a drafted D1 task.

``verify(doc, truth)`` judges a document against a task's ground truth and
returns a ``VerifyReport``: per-check credit and findings, the rubric score,
whether the sheet hard-failed, and the effective score (0 if hard-failed,
otherwise the rubric score), which is the headline number.  The truth's
``scope`` says which groups of work the task asked for; only the checks
those drive are graded, renormalised to 100.  No model call, no session, no
network: it runs on a saved ``.rdoc.json`` and the same document always
gets the same report (eval plan section 3).

The layers, outermost first: ``context`` (the deliverable sheets, viewports,
the given design, the scope), ``match`` (anchored labels), ``geometry``
(linework and ticks), ``legibility`` (paper-space footprints), ``checks``
(one formula per check id), ``rubric`` (weights and scope), ``audit`` (the
journal), ``report``.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional, Union

from roaddraft.commands.bus import ANCHOR_PRODUCERS
from roaddraft.document.document import Document
from roaddraft.tasks.brief import GroundTruth
from roaddraft.tasks.spec_v1 import DRAFTING_SPEC_V1, spec_hash
from roaddraft.tasks.types import CHECK_GROUPS, DESIGN_GROUPS, GROUPS, OPEN_BREAKS
from roaddraft.verify.audit import audit_journal
from roaddraft.verify.checks import CHECKS, analyze
from roaddraft.verify.context import Context, given_design
from roaddraft.verify.normalize import normalize
from roaddraft.verify.report import (
    FINDING_CODES, VALUE_CODES, CheckResult, Finding, VerifyReport,
)
from roaddraft.verify.rubric import score_checks

VERIFIER_VERSION = "d1-verify-v8"  # (2026-11-03) D1-16 judges a callout's tip through the viewport the deliverable sheet is drawn through (checks.expected_callout_tip), not the sample sheet's: a job that leaves the viewport to the drafter is scored as drawn; v7 (2026-10-24) D1-16, the verifier's own check for a real sheet's construction callouts (checks.EXTRA_CHECKS), in play only for tasks that ask for notes; v6 (2026-10-21) D1-02 credits only ticks an anchoring command placed; v5 (2026-10-18) a bearing anchored at a station on its tangent is that tangent's bearing; v4 (2026-10-16) D1-08 charges a dimension line or callout leader through text; v3 (2026-10-11) anchors through references, PPM label forms by meaning
DEFAULT_LEVEL = "explicit"


def verify(doc: Document, truth: Union[GroundTruth, dict], spec: Optional[dict] = None,
           journal: Optional[List[dict]] = None, prompt_level: str = DEFAULT_LEVEL) -> VerifyReport:
    """Score ``doc`` against ``truth`` under ``spec`` (default ``DRAFTING_SPEC_V1``).

    ``prompt_level`` is the level the task was posed at (the spec's
    ``prompt_levels``): conventions that prompt did not state are graded by
    the spec's lenient rules.  ``journal`` (a bus journal or the records of a
    saved one) adds the informational audit.  The document is not modified."""
    t0 = time.perf_counter()
    spec = DRAFTING_SPEC_V1 if spec is None else spec
    if isinstance(truth, dict):
        truth = GroundTruth.from_dict(truth)
    if OPEN_BREAKS in truth.scope:
        # a training-only layout whose sheet count and breaks were the drafter's to choose
        # (tasks.breaks): graded against the truth of the breaks it chose, with a check of
        # its own on the choice.  No other truth carries the mark
        from roaddraft.verify.breaks import verify_open
        return verify_open(doc, truth, spec, journal=journal, prompt_level=prompt_level)
    ctx = Context.build(doc, truth, spec, prompt_level)
    scope = [g for g in GROUPS if g in ctx.scope]
    groups = check_groups(truth)
    # the given design must come back untouched -- unless creating it is the task, in
    # which case D1-15 judges what was created; a design that lives only in a base
    # drawing (annotate-base) and is not attached is not tampered with, just absent,
    # so the labels simply find nothing to match
    given = given_design(doc, truth)
    fingerprint_ok = (ctx.asks(*DESIGN_GROUPS)
                      or (bool(truth.references) and not given.alignments)
                      or given.fingerprint() == truth.design_fingerprint)
    findings: List[Finding] = []
    if fingerprint_ok:
        analysis = analyze(ctx)
        checks = score_checks(spec, analysis, scope, groups)
        labels = analysis.labels
        counts = {"required_labels": len(labels.matches),
                  "matched": sum(1 for m in labels.matches if m.credited),
                  "anchored_entities": _anchored_entities(doc, ctx),
                  "unanchored_text": len(labels.unanchored),
                  "required_ticks": len(analysis.ticks) if ctx.asks("ticks") else 0,
                  "matched_ticks": (sum(1 for t in analysis.ticks if t.hits)
                                    if ctx.asks("ticks") else 0),
                  "elements": (len(analysis.linework.elements)
                               if analysis.linework and ctx.asks("linework") else 0),
                  "matched_elements": (sum(1 for e in analysis.linework.elements if e.hits)
                                       if analysis.linework and ctx.asks("linework") else 0),
                  "sheets": len(truth.sheets),
                  "edges": len(analysis.edges.elements) if analysis.edges else 0,
                  "matched_edges": (sum(1 for e in analysis.edges.elements if e.hits)
                                    if analysis.edges else 0),
                  "dimensions": len(analysis.dimensions),
                  "matched_dimensions": sum(1 for d in analysis.dimensions if d.credited),
                  "callouts": len(analysis.callouts),
                  "matched_callouts": sum(1 for m in analysis.callouts if m.chosen is not None
                                          and m.distance is not None
                                          and m.distance <= float(ctx.tol["position_paper_in"]))}
    else:
        checks = score_checks(spec, None, scope, groups)
        findings.append(Finding("design_tampered",
                                note="the given design was changed; a drafter draws it as given"))
        counts = {"required_labels": len(truth.labels), "sheets": len(truth.sheets)}
    report = VerifyReport(verifier_version=VERIFIER_VERSION, spec_version=spec.get("version", ""),
                          spec_hash=spec_hash(spec), task_id=truth.task_id,
                          prompt_level=prompt_level, scope=scope,
                          design_fingerprint_ok=fingerprint_ok, checks=checks, counts=counts,
                          findings=findings)
    if journal is not None:
        report.audit = audit_journal(journal, doc)
    report.timing_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    return report


def check_groups(truth: GroundTruth) -> dict:
    """The groups each check draws from for this truth: ``CHECK_GROUPS``, plus
    the sheet group on D1-09 when a two-sheet layout gives the match line and
    its labels a level to be judged on."""
    groups = dict(CHECK_GROUPS)
    if any(sh.get("matches") for sh in truth.sheets):
        groups["D1-09"] = groups["D1-09"] + ("sheet",)
    return groups


def _anchored_entities(doc: Document, ctx: Context) -> int:
    spaces = [doc.model_entities] + [sv.sheet.entities for sv in ctx.sheets
                                     if sv.sheet is not None]
    return sum(1 for ents in spaces for e in ents.values()
               if e.anchor and e.anchor.get("placed_by") in ANCHOR_PRODUCERS)


def read_journal(path) -> List[dict]:
    """The records of a saved journal file (JSON lines)."""
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def verify_files(document_path, truth_path, journal_path=None, spec: Optional[dict] = None,
                 prompt_level: str = DEFAULT_LEVEL) -> VerifyReport:
    """``verify`` on files: a saved document, a ``.truth.json``, optionally a journal."""
    from roaddraft.document.fileformat import read_document
    doc = Document.from_dict(read_document(document_path))
    truth = GroundTruth.from_dict(json.loads(Path(truth_path).read_text()))
    journal = read_journal(journal_path) if journal_path else None
    return verify(doc, truth, spec=spec, journal=journal, prompt_level=prompt_level)


__all__ = ["VERIFIER_VERSION", "DEFAULT_LEVEL", "verify", "verify_files", "read_journal",
           "VerifyReport", "CheckResult", "Finding", "FINDING_CODES", "VALUE_CODES", "CHECKS",
           "normalize"]
