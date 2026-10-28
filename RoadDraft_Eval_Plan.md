# RoadDraft — Evaluation Framework Plan

**Verifier, eval harness, task sets, leaderboard**
Robert Denison, PE · Working plan v1 · September 4, 2026
Companion to [RoadDraft_Build_Plan.md](RoadDraft_Build_Plan.md) (the PRD) and [docs/RoadDraft_Phase1_Build_Spec.md](docs/RoadDraft_Phase1_Build_Spec.md) (the Phase 1 contracts this plan builds on).

---

## 0. Where the repo stands, and what that does to this plan

Snapshot as of 2026-09-04 (229 tests green):

| Landed | Not landed (Phase 1 spec stages 2–4) |
|---|---|
| Design math: `design/{angles,stations,horizontal,vertical,model}.py` — curve data, station equations, `station_to_xy` / `xy_to_station`, profiles, `DesignModel.fingerprint()` | WP1b anchors + labels (`design/anchors.py`, `design/labels.py`: `resolve_anchor`, `compile_label`, `sheet_pose`, `stationing_plan`, `curve_table_rows`) |
| `DRAFTING_SPEC_V1` with 11 weighted checks, `spec_hash()`, `spec_subset()`; DRAFT AASHTO tables | WP4 `Document.design` + `Entity.anchor` (the verifier record) |
| `DESIGN_SCHEMAS` for the nine design commands (`create_alignment` … `import_landxml`) | WP5 LandXML; WP6 design command handlers + alignment-mode `annotate_stationing`; WP7 design queries |
| Entity validators, `modify_entity` hardening, GUI editors | WP9 task generator, `TaskBrief` / `GroundTruth`, `compute_ground_truth`, `match_truth`, `reference_solution`; WP10 docs |

The Phase 1 build workflow (`roaddraft-phase1-build-stages-1-2`, 2026-09-04) completed Stage 1 (WP1a, WP2, WP3). WP1b then failed on a session limit, which took WP4, WP5 and the integration gate with it. Nothing after Stage 1 has been attempted. The Phase 1 spec itself lived only in a temp scratchpad; it is now committed-ready at `docs/RoadDraft_Phase1_Build_Spec.md`.

Consequences for this plan:

1. **The verifier is designed against the Phase 1 contracts, not the current code**: the anchor record (spec §2.7), `GroundTruth` (§7.3), `match_truth` (§7.5) and the reference solution (§7.6). Finishing Phase 1 stages 2–4 is work package E0 below; it gates E1.
2. **The harness does not have to wait.** The episode loop, agents, logging, runner and CLI only need `Session` and a `Task` protocol, both of which exist or are fully specified. E2 can be built against a stub task while E0 lands.
3. **Two small contract additions** are needed in Phase 1 for the anti-reward-hacking layer to hold (§3.5): a bus-stamped `placed_by` field on the anchor record, and `truth.design_fingerprint` enforcement. Both are one-line WP6/WP9 follow-ups and are listed in E0. *(2026-09-10: `placed_by` has landed — see §3.5 item 3.)*

PRD mapping: this plan is M2 (verifier), M3 (eval harness + trajectory logging), the Phase 2/3 leaderboard and writeup, the M4 `run_check` budget and dialect skins as harness features, and the M5 hooks (a Gymnasium-style adapter) without the training run itself.

## 1. Goals and the numbers at the end

**Primary deliverable (v0.1):** one reproducible benchmark run on a frozen, held-out D1 task set, reporting a single headline number:

> *best model scores X/100 on a basic plan sheet* (mean effective score over `d1-test`, with a confidence interval).

**Secondary numbers** the same run yields for free: hard-fail rate, clean-sheet rate, per-check credit profile, invalid-call rate, steps and cost per sheet, and later the dialect transfer gap.

**Non-goals for v0.1:** D2+ checks (profiles, VC tables), the VLM judge, raw-code mode and its sandbox, the GRPO training run (only the environment adapter it needs), and GUI computer-use evals.

**Principles carried over from the PRD** and treated as invariants:

- The verifier is deterministic and contains no model call. Same document, same report, forever.
- Text earns credit only through anchors. Geometry (linework, ticks) earns credit by geometric match. This is the anti-reward-hacking layer, and the verifier enforces it rather than hoping agents behave.
- The agent never sees ground truth. `run_check` returns *what* is wrong, never the expected value.
- Everything that changes a score is versioned and hashed into the run record: spec, generator, verifier, harness, prompts, model id, git commit.
- The playtest rule holds: if the PE cannot draft a 100 through the harness, the harness is wrong, not the model.

## 2. Architecture

```
benchmarks/tasksets/*.json ─┐            results/<run_id>/
 (pinned task ids)          │              episodes/*.jsonl · summary.json · leaderboard.md
                            ▼                       ▲
┌──────────────── roaddraft.eval (harness) ────────────────────────────┐
│ runner ── episode loop ── agent ── provider (Anthropic / OpenAI-compat)│
│   │        │  tools: whitelist(manifest) + get_task_brief/run_check/submit
│   │        │  budgets · dialect skin · trajectory log · observation    │
└───┼────────┼─────────────────────────────────────────────────────────┘
    │        ▼
    │   roaddraft.api.Session  (command bus, queries, renders)   ← unchanged
    │        │
    ▼        ▼
┌── roaddraft.tasks ──┐   ┌──────── roaddraft.verify ─────────────────┐
│ generate_task(seed) │   │ verify(doc, truth, spec, journal) → report │
│ brief · truth ·     │──▶│ match · legibility · geometry · checks     │
│ baseline · reference│   │ rubric (weights, hard fails) · findings    │
└─────────────────────┘   └───────────────────────────────────────────┘
```

Two new packages, one rule each:

- **`src/roaddraft/verify/`** imports `core`, `design`, `document`, and `tasks.{brief,spec_v1}` only. Never `api`, `web`, `eval`, or any network or model library. It is the product the PRD calls the QA linter, so it must run on a saved `.rdoc.json` with no session.
- **`src/roaddraft/eval/`** imports `api`, `tasks`, `verify`. Model providers live behind one interface in `eval/providers/` and are the only place a vendor SDK is imported. Tests never touch the network (a fake provider replays scripted responses).

File layout (owning work package in brackets):

```
src/roaddraft/verify/
  __init__.py        verify(), VerifyReport, VERIFIER_VERSION                        [E1]
  report.py          VerifyReport / CheckResult / Finding dataclasses, to_dict       [E1]
  normalize.py       content normalization (whitespace, primes, quotes)              [E1]
  match.py           anchor index, label matching, expected-pose recomputation       [E1]
  geometry.py        element ↔ entity geometric matching (lines, arcs), ticks        [E1]
  legibility.py      paper-space bboxes of everything visible on the sheet           [E1]
  checks.py          one function per check id (D1-00 … D1-11)                       [E1]
  rubric.py          credit → points, hard-fail rule, effective score                [E1]
  audit.py           journal audit (anchor edits, design edits, provenance)          [E1]
src/roaddraft/eval/
  __init__.py, config.py     RunConfig / EpisodeConfig (frozen, hashable)            [E2]
  task_source.py             Task protocol; from taskset manifest or generator       [E2]
  tools.py                   whitelist → tool defs; dialect naming; result shaping   [E2]
  budget.py                  step / run_check / token / wall-clock / fault budgets   [E2]
  episode.py                 the loop: reset → act → execute → observe → submit      [E2]
  trajectory.py              JSONL writer/reader for episodes                        [E2]
  runner.py                  matrix runs, concurrency, resume, cost cap              [E2]
  taskset.py                 build/verify pinned task-set manifests                  [E2]
  agents/base.py, null.py, oracle.py, scripted.py, replay.py                         [E2]
  agents/llm.py              provider-driven tool-calling agent                      [E3]
  providers/base.py, anthropic.py, openai_compat.py, fake.py                         [E3]
  prompts/system_neutral.md, system_c3d.md, system_ord.md                            [E3]
  dialects.py                alias tables for tool names per skin                    [E3]
  prices.json                dated price table used only at report time             [E3]
  report.py                  summary.json, leaderboard.md, per-check CSV, taxonomy   [E4]
  __main__.py                python -m roaddraft.eval {run,verify,taskset,report,human}
benchmarks/
  tasksets/d1-dev.json, d1-test.json, d1-variance.json   pinned manifests (committed) [E2]
  expert/<task_id>.journal.jsonl                          human playtest trajectories [E2]
  runs/<run_id>/summary.json, leaderboard.md              published runs only         [E4]
  knowledge/manifest.json, caltrans-ppm/*.txt|*.json     reference standards behind the spec (Caltrans PPM text + page index; raw PDFs gitignored) [done]
results/                                                   raw episode logs (gitignored)
```

## 3. The verifier (`roaddraft.verify`)

> **Built 2026-10-10 (E1).** `src/roaddraft/verify/` plus `python -m roaddraft.verify DOC TRUTH [--journal J] [--level full|terse]`. Acceptance met: oracle 200 seeds × all dials × both prompt levels = 100 with no findings, null 50/50 = 0 with `sheet_missing`, determinism (twice and on the replayed journal), 34 mutations, 11 hack probes, p95 ≈ 8 ms on 3 curves with an equation. Decisions taken on the way, and where the build departs from this section, are in §3.8.

### 3.1 Public API and report shape

```python
def verify(doc: Document, truth: GroundTruth, spec: dict = DRAFTING_SPEC_V1,
           journal: Optional[List[dict]] = None, prompt_level: str = "full") -> VerifyReport
```

The built report also carries `prompt_level` and a top-level `findings` list (only `design_tampered` lives there); `timing_ms` is kept off `to_dict()` so reports are byte-stable (`to_dict(include_timing=True)` adds it). `VerifyReport.agent_view()` is the `run_check` payload.

`VerifyReport.to_dict()`:

```json
{"verifier_version": "d1-verify-v1", "spec_version": "draft-v1", "spec_hash": "sha256:…",
 "task_id": "D1-000042-…", "design_fingerprint_ok": true,
 "rubric_score": 71.5, "hard_failed": true, "effective_score": 0.0,
 "checks": [
   {"id": "D1-04", "name": "PC/PT label for every curve…", "weight": 14,
    "credit": 0.5, "points": 7.0, "hard_fail": true, "hard_fail_triggered": true,
    "findings": [
      {"code": "missing",     "anchor": {"alignment": "ALIGN-1", "ref": "PT-2", "kind": "pt"}},
      {"code": "wrong_value", "anchor": {"alignment": "ALIGN-1", "ref": "PC-1", "kind": "pc"},
       "entity_ids": ["TX-014"], "expected": "PC 16+00.00", "actual": "PC 16+00"}]}],
 "counts": {"required_labels": 24, "matched": 20, "anchored_entities": 31, "unanchored_text": 2},
 "timing_ms": 12}
```

Findings are the unit of everything downstream: `run_check` returns them stripped of `expected` / `actual` / `points`; the report generator maps their `code` to the failure taxonomy (§4.9); mutation tests assert on them.

Finding codes (a closed, tested set): `missing`, `wrong_value`, `unanchored`, `anchor_inconsistent`, `misplaced`, `not_visible`, `duplicate`, `overlap`, `off_sheet`, `geometry_mismatch`, `extra_linework`, `wrong_layer`, `wrong_height`, `wrong_layer_props`, `missing_field`, `wrong_field`, `design_tampered`, `sheet_missing`, `viewport_scale`, `not_fitted`.

### 3.2 Scoring semantics

- `rubric_score = Σ weight_i × credit_i` over the spec's `checks`, credit ∈ [0, 1].
- `hard_failed` is true when any check flagged `hard_fail` in the spec produced a **value** finding (`wrong_value`, `geometry_mismatch`, `design_tampered`). Missing work costs credit; wrong work shown on the sheet disqualifies it. This is the PRD's "wrong elevation = hard fail" made precise, and it needs the PE's confirmation (§3.7).
- `effective_score = 0 if hard_failed else rubric_score`. **Effective score is the headline metric.** Rubric score and hard-fail rate are always reported beside it, so a model that is "almost right but wrong" is distinguishable from one that did nothing.
- A precondition runs before any check: `doc.design.fingerprint() == truth.design_fingerprint`. A mismatch is `design_tampered`: hard fail, all checks skipped (the agent edited the given design instead of drafting it).

### 3.3 Label matching (the core of D1-03 … D1-07)

1. **Index the truth** by the triple `(alignment, ref, kind)` from `truth.labels`.
2. **Index the document**: every `Text` in model space and on the deliverable sheet whose `anchor` is a valid record **and** whose `anchor.placed_by` is bus-stamped (§3.5). Unanchored text is listed once as `unanchored` (informational) and never matched.
3. **Match** on the triple. Duplicates (two entities, same triple) count once; the rest are `duplicate` findings.
4. **Content**: `normalize(entity.content) == normalize(truth.content)`. Normalization is whitespace collapse plus curly→straight quotes and primes, nothing else. Station format, DMS format and the `PC ` prefix all count. A mismatch is `wrong_value` (hard fail on value checks).
5. **Position**: recompute the pose the entity's *own* anchor record implies — `compile_label(alignment, resolve_anchor(ref), kind, side=rec.side, label_offset=rec.label_offset, rotation=rec.rotation)` for model space, then `sheet_pose(...)` through the recorded viewport for sheet space — and compare to the entity's actual position within `tolerances.position_model_ft` / `position_paper_in`, rotation within `rotation_deg`. A deliberate legibility nudge made by changing `side` or `label_offset` through the command surface is therefore fine; a label dragged away from its anchor with `move_entities` is `misplaced` (D1-07); an anchor rewritten by hand to point somewhere else is `anchor_inconsistent`.
6. **Visibility**: a model-space label must fall inside the `visible_model_bbox` of a viewport on the deliverable sheet; a sheet-space label must fall inside the sheet's usable area. Otherwise `not_visible`, no credit. Matching is space-agnostic: an anchored label placed on the sheet through the viewport is as good as one in model space.

Ticks and linework are matched geometrically (endpoints within `position_model_ft`, either orientation; arcs by center, radius and angular extent), anchor or not. Tables are matched like labels: a `Table` on the sheet with `anchor.kind == "curve_table"`, headers equal to the spec columns' headers in order, one row per curve, every cell normalized-equal to `truth.curve_table.rows`.

### 3.4 The checks

| Check | Credit | Hard-fail trigger | Main finding codes |
|---|---|---|---|
| **D1-00 sheet setup** (added 2026-10-09, weight 5; D1-02 → 9, D1-11 → 1) | 0.25 sheet exists with the deliverable name and size + 0.25 a viewport at an allowed `feet_per_inch` + 0.5 the alignment bbox lies inside a viewport's visible window and the viewport inside the usable area | — | `sheet_missing`, `viewport_scale`, `not_fitted` |
| D1-01 linework | matched design elements / total elements | any entity on the alignment layer whose geometry matches no element within tolerance | `missing`, `geometry_mismatch`, `extra_linework`, `wrong_layer` |
| D1-02 ticks | matched ticks / expected ticks (per region, through equations); since `d1-verify-v6` (2026-10-21) a tick matches only when an anchoring command placed it | — | `missing`, `misplaced`, `unanchored` |
| D1-03 station labels (+ equation labels) | correct anchored visible / expected | a matched label with wrong content | `missing`, `wrong_value`, `not_visible`, `unanchored` |
| D1-04 PC/PT (+ PCC/PRC, + C-n callouts) | same | same | same |
| D1-05 bearings | same, one per tangent `T-n` | same | same |
| D1-06 curve table | 0.2 table present, anchored, headers right + 0.8 × correct rows / curves | any wrong cell | `missing`, `wrong_value`, `unanchored`, `wrong_field` |
| D1-07 anchored position | consistent / matched required labels | — | `misplaced`, `anchor_inconsistent` |
| D1-08 legibility | max(0, 1 − 0.25 × (overlapping pairs + items outside the usable area)), computed in **paper space** over everything visible on the sheet (model labels mapped through their viewport, sheet text, tables, the north arrow). A pair is two text footprints that overlap deeper than 0.005 in, or — since `d1-verify-v4`, 2026-10-16 — a dimension's line (dimension line, extension lines, stubs, a radial leader) or a callout's leader that runs through another entity's text footprint, judged through the viewport like the text; items cut by their viewport's edge or reading upside down count with those outside | — | `overlap`, `off_sheet`, `clipped`, `upside_down` |
| D1-09 layers and heights | fraction of required labels, ticks, linework and the table on the spec layer with text height within `height_tolerance_pct` (model heights compared as height_ft / feet_per_inch) and layer properties per `layer_props` | — | `wrong_layer`, `wrong_height`, `wrong_layer_props` |
| D1-10 title block | correct fields / required fields; `scale` must equal `scale_text_format` for the viewport actually used; other fields equal the brief's values after normalization | — | `missing_field`, `wrong_field` |
| D1-11 north arrow | 1 if a `NORTH_ARROW` block reference sits inside the usable area | — | `missing`, `off_sheet` |

Weights stay in `DRAFTING_SPEC_V1` (so `spec_hash` covers them); formulas live in `verify/rubric.py` and are covered by `VERIFIER_VERSION`. Both go into every run record.

### 3.5 The anti-reward-hacking layer

Reward hacking is the failure mode that makes an RL environment worthless, so it gets its own list:

1. **Anchors are required for text credit** (3.3 step 2). Right-looking `place_text` is worth zero. This is a deliberate benchmark rule, stated in the brief.
2. **Anchor consistency** (3.3 step 5). A label's credit depends on its position and content agreeing with what its own anchor record implies, recomputed from the design model by the verifier. Spoofing an anchor without also computing the right pose is detected; computing the right pose by hand is just drafting.
3. **Provenance.** Phase 1 spec §4.11 lets `modify_entity` set `anchor` on any entity. The Design-B proposal's answer is the right one: the bus stamps `anchor.placed_by` with the command name that created the entity, handlers overwrite any caller-supplied `placed_by`, and the verifier trusts only `place_label`, `annotate_stationing`, `place_curve_table`, `draw_alignment`. **Landed 2026-09-10**: `as_anchor` accepts `placed_by` (str|None); `CommandBus._stamp_provenance` stamps every entity a command *created* whose anchor is set, with that command's canonical name; `modify_entity` drops a caller-supplied `placed_by` and preserves the entity's existing one, so provenance can be neither claimed nor transferred. `bus.ANCHOR_PRODUCERS` is the trusted set the verifier imports rather than hardcoding. Creation-only stamping is deliberate: renaming an alignment rewrites its labels' anchors, and those labels must keep their provenance. `tests/test_anchor_provenance.py` covers it (10 tests). The harness therefore does **not** need to strip `anchor` from `modify_entity` changes; `audit.py` still reports the count.
4. **Design integrity.** The fingerprint precondition (3.2). `create_alignment` / `modify_alignment` / `delete_alignment` / `import_landxml` are off the D1 whitelist anyway.
5. **No truth leaks through `run_check`.** Findings carry the anchor triple and the code, never `expected`. The model already knows which anchors exist (`get_design_data("anchors")`), so this leaks nothing new; the value it must compute itself.
6. **Duplicates count once; extras are free but must stay legible.** Spraying labels earns nothing and costs legibility.
7. **Journal audit** (`audit.py`, informational in v1): counts of `modify_entity` anchor edits, `move_entities` on anchored text, design commands, unknown/invalid calls. Reported per episode; a later spec version can turn any of these into a check.

### 3.6 Validating the verifier (before it judges anything)

The verifier is the moat and the thing most likely to be quietly wrong, so it gets its own suite (E1 acceptance):

| Test | Assertion | Count |
|---|---|---|
| Oracle | `reference_solution` document → `effective_score == 100`, no findings | 200 seeds, all dials |
| Null | baseline document → 0, `sheet_missing` present | 50 seeds |
| Determinism | two calls, and a call on the replayed journal, produce byte-identical reports | 20 seeds |
| Mutation catalog | one mutation applied to the reference document changes **exactly** the expected check(s) by the expected amount and sets `hard_failed` as expected | ≥ 25 mutations |
| Reward-hack probes | adversarial documents built from the reference score as designed (below) | ≥ 8 |
| Speed | `verify()` p95 < 50 ms on a 3-curve, equations-on task | — |
| Human playtest | the PE drafts seed 42 through the GUI or REPL; report = 100; the journal is saved as the first expert trajectory | 1, repeated after any spec change |

Mutation catalog (each a fixture builder in `tests/verify_mutations.py`):

```
delete PT-2 label                    → D1-04 credit −1/n, no hard fail
station label content "18+00"        → D1-03 wrong_value, hard fail
move PC-1 label +5 ft                → D1-07 misplaced; D1-03/04 unaffected
rewrite anchor ref PC-1 → PC-2       → anchor_inconsistent; original PC-2 now duplicate
delete every tick in region 2        → D1-02 credit = ticks_in_region_1 / total
tick moved 0.1 ft                    → D1-02 credit −1/n (tolerance 0.05 ft)
curve table cell R 800.00' → 800.10' → D1-06 wrong_value, hard fail
drop a curve table row               → D1-06 0.2 + 0.8·(n−1)/n
curve table unanchored               → D1-06 unanchored, credit 0
labels on layer 0                    → D1-09 fraction; D1-03 unaffected
text height 3 ft                     → D1-09 wrong_height
two labels overlapping on paper      → D1-08 credit 0.75
label outside the usable area        → D1-08 off_sheet and D1-03 not_visible
viewport at 1"=40'                   → D1-00 viewport_scale; D1-10 scale string then wrong too
alignment drawn as a polyline        → D1-01 geometry_mismatch, hard fail
alignment on the wrong layer         → D1-01 wrong_layer; D1-09
extra line on the alignment layer    → D1-01 extra_linework, hard fail
title block missing checked_by       → D1-10 credit 9/10
scale text "1\" = 100'" at fpi 50    → D1-10 wrong_field
north arrow deleted / off sheet      → D1-11 0
begin_station edited in the design   → design_tampered, hard fail, everything else skipped
label placed on the sheet via viewport → still matches (space-agnostic)
side/offset changed via place_label  → matches; D1-07 consistent
free-floating text "PC 16+00.00"     → unanchored, no credit anywhere
```

Reward-hack probes: (a) all labels via `place_text` with correct strings → ≤ 40 (linework, ticks and sheet furniture only); (b) anchors spoofed via `modify_entity` on `place_text` entities with correct content at engine-default positions → provenance rejects them, same as (a); (c) spoofed anchors with hand-computed correct poses and bus-stamped provenance absent → still (a), because provenance is required, not just consistency; (d) every label duplicated 5× → no gain, legibility loss; (e) tiny text (0.01 in) to dodge overlaps → D1-09 wrong_height for every label; (f) `annotate_stationing` in entity-chain mode on hand-drawn linework → ticks count, unanchored station labels do not; (g) table built with `place_table` → 0 on D1-06; (h) design re-created under a new name and labels anchored to it → fingerprint still equal (the given design is untouched), but labels reference an alignment not in truth → `missing`.

### 3.7 Spec changes the verifier needs (PE decisions, all pre-freeze)

Each of these changes `spec_hash` and therefore every task id. Batch them, decide once, then freeze `draft-v1` → `v1`. *Frozen 2026-10-16 as `v1`, `spec_hash` `sha256:0e07d5e83c0b1cb8` (`draft-v4` was `sha256:379c247bd02b2190`); the task-set manifests, the real-task catalog and the pinned ids carry it.*

1. Add **D1-00 sheet setup** (weight 5, taken from D1-02 → 10 and D1-11 → 2, or as the PE prefers). Without it, a sheet with no viewport scores 0 on nine checks with no finding that says why. *Decided 2026-10-09 (Robert): added at weight 5. Those two cuts free only 3 points, so the weights are D1-02 12 → 9 and D1-11 3 → 1 (sum 100).*
2. ~~Add `placed_by` to the anchor record (§2.7) and the bus stamp (§3.5 item 3).~~ **Done 2026-09-10** — no decision left, but note it is a key on every anchor record and so is visible to agents through `get_entity`.
3. Write the **hard-fail rule** into the spec text: "missing costs credit; a wrong value shown on the sheet is a hard fail; the effective score of a hard-failed sheet is 0". *Decided 2026-10-09: kept as written; `DRAFTING_SPEC_V1["scoring"]` states it, and the text and geometry credit rules (items 5, 6).*
4. **Assign `mc` and `equation` labels to checks.** `labels.mc.required` is true and `required_label_kinds` includes `mc`, but no D1 check covers the C-n callouts, and equation labels are likewise uncovered. Proposal: D1-04 covers PC/PT/PCC/PRC and C-n; D1-03 covers station and equation labels. *Decided 2026-10-09: as proposed; the check names say so.*
5. Confirm **credit rules for unanchored work**: geometry-matched linework and ticks earn credit; text and tables only through anchors.
6. Confirm **legibility is judged in paper space** at the deliverable scale, including model-space labels seen through the viewport.
7. Review tolerances (0.005 ft, 1 second, 0.05 in) and the `_upright` west-heading gotcha already flagged in Phase 1.
8. Task ids and any published number are tied to the frozen spec. **No leaderboard is published on `draft-v1`.**
9. **Reconcile `draft-v1` with the Caltrans PPM**, now indexed under `benchmarks/knowledge/caltrans-ppm/` (README there lists each departure with page citations): BC/EC versus PC/PT wording, full annotation at 500-ft stations with single digits between versus every 100-ft station in `12+34.56` form, 0.14 in ticks with labels below the line versus 0.40 in ticks with labels on the left, PPM `TX` text sizes versus 0.10 in labels, and tangent distances beside bearings. Decide per item whether the neutral spec follows the PPM or keeps the genericized value, and record the citation next to the value in `spec_v1.py`. *Decided 2026-10-05 (Robert): BC/EC wording follows the PPM; `spec_v1.py` and the engine letter BC/EC, citation recorded. Decided 2026-10-10 (Robert, "set up more layers per Caltrans PPM standards"): layers are Caltrans named levels, from the CADD Users Manual Appendix A10 that the PPM cites, now collected under `benchmarks/knowledge/caltrans-cadd/`; `DRAFTING_SPEC_V1["layer_set"]` is the 16-level set a layout sheet file carries, `layers` maps the roles (alignment `align_MAIN`, stationing and labels `align_MAIN-anno`, curve table `align_CURVE-DATA`, pavement edges `rd_EP`, width dimensions `rd_LAYOUT-NOTE-anno`, north arrow `pp_PRESENTATION`, match lines `border_INSIDE-BORDER-anno`), weights follow CADD §2.7 (main alignment WT 3 = 0.50 mm, EP WT 2 per the PPM checklist, dimensions WT 0), and `caltrans_levels` records the source row of each. Two readings are flagged for PE review (the dimension and match-line levels); display colors are RoadDraft's nearest named color for the A10 index. Decided 2026-10-12 (Robert): plan scales are the common ones, not 1" = 100'; text touching an edge of pavement on a narrow road is ordinary practice (spec draft-v3, §3.8). Decided 2026-10-13 (Robert): the scales are 1" = 40' and 50' only; text sizes stay 0.10 / 0.12 in; every other item of this list (5, 6, 7, the equation wording, the two level readings) is confirmed as built (spec draft-v4). Nothing is left before the freeze.*

### 3.8 As built (E1, 2026-10-10)

**Task types (decided 2026-10-10, Robert: "simpler prompts; start from an empty sheet or model file and ask for one thing; a few whole sheets from scratch; a few across multiple sheets").** A plan sheet is drafted in phases (layers, linework, stationing, bearings, callouts, sheet, table, north arrow, title block), and a task hands the drafter a document with some phases done and asks for others (`tasks/types.py`, `DRAFTING_SPEC_V1["task_types"]`):

| Type | Starts with | Asks for | Checks graded (points in play) |
|---|---|---|---|
| `draw-alignment` | design + layers | the centerline | D1-01, 09 (16) |
| `stationing` | everything but stationing | ticks, station labels, BC/EC (+ equation) | D1-02, 03, 04, 07, 08, 09 (55) |
| `curve-callouts` | everything but C-n | C-n callouts | D1-04, 07, 08, 09 (34) |
| `bearings` | everything but bearings | bearings | D1-05, 07, 08, 09 (30) |
| `curve-table` | everything but the table | the table(s) | D1-06, 08, 09 (26) |
| `title-block` | everything but title + north | title block(s), north arrow(s) | D1-08, 10, 11 (12) |
| `sheet-setup` | the annotated model, no sheet | sheet(s), viewport(s), match line | D1-00, 08 (11) |
| `annotate-sheet` | linework + an empty set-up sheet | every annotation | D1-02…11 (85) |
| `plan-sheet` | the design only | everything | all (100) |

**Plan-prep types (added 2026-10-10, Robert: "more general plan prep tasks, such as adding references, adding dimensions to pavement widths").** Five more types, with their own checks outside the layout sheet's 100 points (in play only when asked for):

| Type | Starts with | Asks for | Checks graded (points in play) |
|---|---|---|---|
| `layer-setup` | the design only | the six standard layers | D1-09 (6) |
| `pavement-edges` | the layout sheet | the edges of pavement at the typical section's width (`draw_offset` ±W, layer `V-ROAD-EOP`) | D1-09, 12 (14) |
| `pavement-widths` | the layout sheet + edges | an aligned dimension across the pavement on each tangent (`place_dimension`, layer `V-ANNO-DIMS`) | D1-08, 09, 13 (18) |
| `pavement` | the layout sheet | both of the above | D1-08, 09, 12, 13 (26) |
| `attach-reference` | the sheet file (design, layers, sheet, viewport) plus a base drawing file holding the model work | the base attached as a reference, model space, identity, visible, unclipped | D1-14 (5) |

**Design input (added 2026-10-11, Robert: the draw-alignment prompt "just says draw alignment" — nothing in it specifies the geometry).** `draw-alignment` is a plan-prep job: the alignment is already in the document's design and the prompt asks for it to be drawn. The new `create-alignment` type starts from an **empty design** and states the geometry in the prompt the way a PE dictates it ("ALIGN-1 begins at N 10415.86, E 6373.77, station 110+00.00; PI-1 at N 10861.77, E 6404.95, R = 600.00'; …; ends at N …; station equation 111+00.00 BK = 114+00.00 AH. Create it and draw it."); the model must `create_alignment` from the PIs and then draw it. Scope `design` + `linework`: **D1-15** (weight 12, hard fail) compares the created alignment with the truth within the spec's tolerances — begin station, each element's ends, centers and radii, each equation — and D1-01 matches the drawn linework against the *truth* geometry (the verifier's `ctx.alignment` now comes from `truth.alignments`, not the document, so a drawing of a wrong alignment fails both). The design-fingerprint precondition is waived for a task whose scope includes `design`; the rules preamble's design bullet changes for it ("The design is empty. Create the alignment exactly as the task gives it…"). Every other type keeps the design as a given, seeded, never drafted.

**Real plan sheets (added 2026-10-13, Robert: "a lot of these tests use the same basefiles; the sheets should be more complicated and built from the converted example sheets").** The seeded generator draws every task from one synthetic centerline on a blank sheet (its base files differ by seed but are all that one template, named from five routes). Five `real-*` types (`tasks/types.py` `REAL_TASK_TYPES`, built by `tasks/real.py`) start instead from a redrafted sample sheet (`examples/Exmple Plans/Redraft`: Caltrans PPM, FHWA WFL and CFL, FDOT): the sheet file with its real base files (alignments, corridor, survey) referenced through the published viewport, scale and twist, and its notes, legend, callouts and other alignments kept. One alignment is lettered per task: `real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table` (the rest of its annotation drafted to the spec on the start sheet) and `real-alignment-data` (all of it). The truth is `compute_ground_truth` on the base file's rebuilt alignment at the sheet's scale; labels anchor through the reference (`AA01:TB1`). That alignment's own published annotation is stripped from the shipped copies by value and proximity (anchored and plain-text stationing and ticks, BC/EC, bearings and lengths, bubbles, Caltrans grid and FDOT/CFL block curve data). Each label takes the spec's pose unless it lands on the sheet's work, then the other side, then further off (side and offset are not graded); the table goes in the clear space nearest the published one. Three engine/verifier changes came with it: `view_rotation` on `place_label` and `annotate_stationing` (model labels under a twisted viewport printed upside down; default 0, records unchanged), an `upside_down` finding in D1-08, and `given_entities` on a real truth sheet (D1-08 charges only overlaps involving new work, the referenced bases' text joins as context, and given lines never earn tick credit). A pairing is kept only when its reference verifies 100 and its start 0 at both levels; `scripts/real_tasks.py` writes `benchmarks/real_tasks/catalog.json` (tasks and the reasons the rest were left out) and `benchmarks/real_tasks/README.md` documents it, with the known gaps (published annotation redrafted as outlined linework stays; one sheet per task, since each sample sheet carries its own copy of its bases). **Converted further the same day (Robert: "convert"):** six more real types put the sheet's other jobs on the same sets -- `real-draw-alignment` (in the alignment base file), `real-attach-reference` (the published sheet with its bases detached), `real-title-block` (the agency border's own fields), `real-sheet-setup` (lay the sheet out on the annotated model at the published scale and twist), `real-annotate-sheet` (the set-up sheet blank) and `real-plan-sheet` (the base files alone) -- so 11 of the 21 types run on real sheets. The checks read three real-only facts from the truth sheet: the border's title fields and which each prompt level states (D1-10), the published twist a fitted viewport must keep (D1-00), and a north arrow turned to north (D1-11, half credit pointing up the paper); a curve's truth piece is its circle, since rebuilt curves store ends a few hundredths off it. Still seeded only: pavement edges and widths, create-alignment, two-sheet layouts, layer setup.

The brief's project carries a typical section (two 11- or 12-ft lanes). **D1-12** matches the edge pieces geometrically like the centerline (any layer; layer judged in D1-09); linework on the edge layer that is off the pavement width is `geometry_mismatch` (hard fail). **D1-13** wants a model-space linear/aligned dimension whose two points sit on the two edges at one station of the tangent and whose text reads the width: explicit = at the stated station, text exact; vague = anywhere on the tangent, text by value; a wrong number hard-fails. The dimension's text counts in D1-08 legibility. A 24-ft pavement is too narrow for its own dimension text at plan scale, so the engine sets the text past the right edge of pavement; the reference dimensions at the half station (xx+50) nearest each tangent's midpoint, else the 5-ft station nearest it, whose dimension line (0.1 in ahead of the station) clears the bearing lettered above the midpoint by 0.05 in and every station number by 0.15 in (fixed 2026-10-16, `d1-v6`: the half station alone ran the line through the bearing on nearly every pavement seed at both scales; D1-08 judged text footprints, not a line through one, so the oracle never saw it; `tests/test_tasks.py` now asserts no width dimension line crosses a bearing text box over seeds 1–40, one and two sheets, and `d1-verify-v4` the same day charges such a line, below), with a 1.5× text gap that puts the text beyond 0.5 in right of the centerline, outside the band the BC/EC labels use, and keeps 1.6 in from an equation label. A tangent shorter than about 110 ft has no room beside a 1.5 in bearing and is left undimensioned; a seed with no tangent that allows this cannot make a widths task (`generate_task` raises; the task-set builder takes the next type), which is 72 three-curve one-sheet layouts of the 3,576 over seeds 1–200 and 1000–1099 at every dial. **D1-14** is structural: a reference whose path names the shipped base file, in model space at identity, visible and unclipped (0.5 attached + 0.25 placement + 0.25 visible); the file itself is never read by the verifier. `Task.files` ships the base drawing; `session_for_task` writes it beside the document so `attach_reference` resolves it. D1-09 judges only the layers the asked-for work is drawn on (all six for `layer-setup`; at the vague level a layer need only exist).

The starting document is the design plus the given phases drafted by the reference solution, so a drafter joins work that already shows the office's standards. `truth.scope` names the groups asked for; the verifier grades only the checks those groups drive and **renormalises the rubric to 100 over the in-scope weights** (`report.scope_weight`), so a one-piece task and a whole sheet score on the same scale. Out-of-scope checks are reported with `in_scope: false` and hidden from the agent's `run_check` view. Wrecking given work is not graded (it is not what was asked); a wrong value in the asked-for work still hard-fails.

**Two sheets.** Any type runs on `sheets=2`: a longer alignment (tangents stretched 2.2×) broken at an even station on a tangent, ≥ 60 ft from any curve point and ≥ 300 ft from the ends, nearest the middle. Each sheet (C-101, C-102) gets a viewport sized to its own segment plus the 100-ft pad (the nearest thing to a viewport clipped at the match line; a full-size viewport let the other sheet's labels show through, under the north arrow and off the edge), its own curve table listing the curves it shows (a sheet with no curve has no table), north arrow and title block (sheet n of 2). One match line is drawn across the centerline at the break (`draw_station_offset`, 2 in each side on paper, on the station layer) and each sheet carries a `MATCH LINE STA … SEE SHEET …` label (`place_label` kind `custom` on the sheet, posed by its actual text box so it stays inside the border and clear of the north arrow). D1-00 scores the match line inside sheet setup: per sheet 0.2 sheet + 0.2 scale + 0.4 fitted + 0.2 (half the line seen on this sheet, half this sheet's label), averaged over sheets (`DRAFTING_SPEC_V1["sheet_setup"]`). At the vague level any line ≥ 1 in crossing square at the station counts and the label is read by meaning (MATCH, the station in any format, the other sheet's name). Per-sheet checks (D1-06, 10, 11) average over sheets; D1-08 adds up overlaps across them; a label is visible if any deliverable sheet shows it.

**The prompt dial (decided 2026-10-10, Robert: "some prompts explicit, others very vague").** Every task is posed in natural language at two levels over one truth (`tasks/prompts.py`, `brief.prompts`, `DRAFTING_SPEC_V1["prompt_levels"]`), one pair per task type:

- `explicit`: the request with the standards it touches spelled out (scale, layers and their properties, text heights, tick length, label wording, table columns, title-block values, the match line). Graded exactly.
- `vague`: the request in a sentence ("Station ALIGN-1.", "Put the curve data on C-101.", "C-101 is blank. Annotate it.", "Draft plan sheets C-101 and C-102 for ALIGN-1, breaking at station 169+00.00."). Knowing what belongs on a layout sheet is the drafter's job. Facts a drafter could not know (the sheet names, the break station) are given at both levels.

What must be on the sheet is graded identically at both levels. A convention the prompt did not state is graded by `DRAFTING_SPEC_V1["lenient"]` instead of the exact value:

| Unstated | Lenient rule |
|---|---|
| scale | any standard engineering scale |
| layers | any layer but 0; layer properties are not graded |
| text heights | 0.08–0.20 in on paper for labels, 0.08–0.25 in for the table |
| tick length | a line crossing the centerline square to it at the station, 0.05–1.0 in on paper |
| label format | read by meaning: `18+00` = `18+00.00`, PC = BC, `N45-30-15E` = `N 45°30'15" E` |
| table columns | headers read by meaning (RADIUS = R); only curve, delta, radius and length are required; cells compared by value |
| title-block values | filled in, except the fields the prompt gave (project, sheet number) and the scale, which must match the viewport |

`RULES` (anchor your labels, leave the design alone, keep what is drawn) go with every level: they belong to the benchmark, not to drafting. **New metric: prompt gap** = effective(explicit) − effective(vague), paired by task (§5). Wrong values hard-fail at both levels. The full catalog of prompts is exported by `scripts/export_prompts.py` to `benchmarks/prompts/roaddraft_prompts.xlsx`.

**Validation as built:** every task type × 1 and 2 sheets × both levels: reference = 100 with no findings, starting document = 0 (40 seeds, 1,440 verifications; `tests/test_verify_scope.py` keeps 6 seeds of it; repeated 2026-10-16 on `d1-v6`, 5,120 verifications over the 16 seeded types, and again under `d1-verify-v4` with the 584 real-sheet pairings of `benchmarks/real_tasks/catalog.json`); the whole-sheet suite of §3.6 (200-seed oracle, 50-seed null, determinism, 34 mutations, 11 hack probes, p95 < 50 ms) still passes; two-sheet mutations (match line deleted, label wrong or missing, second sheet deleted) move D1-00 and the per-sheet checks by the expected amounts.

**Departures from §3.2–3.6:**

- *Design integrity* compares only the **given** design (the truth's alignments and the profiles bound to them) with the truth's fingerprint. An alignment the agent adds is not tampering, which is what probe (h) needs. `doc.design.fingerprint()` covers every alignment, so the literal §3.2 rule would have hard-failed (h).
- *Hand-rewritten anchors* (record station disagrees with its ref, ref doesn't resolve, kind doesn't fit, sheet label names a missing viewport) are `anchor_inconsistent` and are **never matched**. So the PC-1 → PC-2 rewrite leaves PC-1 `missing` and costs D1-07; it does not produce a `duplicate`.
- *Quality checks are ratios over present work*: D1-07 = consistent / (matched + inconsistent), D1-08 = the legibility formula, D1-09 = conforming items / (matched items + the 4 spec layers). With no required work present each scores 0, so an empty sheet earns nothing; otherwise deleting a label moves only its own check.
- *D1-01* credits an element matched on any layer; `wrong_layer` there is informational and D1-09 takes the points. Off-design linework on the alignment layer is `geometry_mismatch` while an element is still unmatched and `extra_linework` once all are; both are value findings and hard-fail.
- *Visibility* requires the label to sit inside a viewport and inside the usable area. A visible duplicate with the wrong content is `wrong_value` (wrong work on the sheet).
- *Legibility* uses oriented text rectangles (the engine's width estimate) with a separating-axis test that must exceed 0.005 in. Axis-aligned boxes of rotated labels collide falsely.
- *Mutation catalog:* "viewport at 1"=40'" became 1"=120'. Nearly every task is at 1"=100', and 120 still fits; the catalog expects D1-09 `wrong_height` as well, because the text then prints off-size.
- *Generator d1-v2:* the reference sheet had real EC/BC and BC/C-n/EC overlaps on short tangents and short curves at 1"=100' (170 of 1,800 variants). The tangent floor is now 120 ft and C-n callouts sit at 2× the label offset; all 1,800 now verify clean. Task ids changed (spec and generator), fixture refreshed.
- *Generator d1-v3 (task types, two sheets):* also a 150-ft curve floor (deltas bumped where the radius is small), because with per-glyph text widths the BC and EC labels of a 105-ft curve ran into each other on the inside of the bend (seed 123). Raw-text probe (a) now scores 42, not 36: legibility is judged once the sheet exists, and legible raw text is legible.
- *Prompt levels* are named `explicit` / `vague` (Robert's words), not `full` / `terse`.
- *One convention set with Track P (2026-10-11, Robert: "fix the three places so the probes and E1 match").* The spec is `draft-v2`: the lettering conventions are the Plans Preparation Manual's, which the Tier 3 probes already enforced — station numbers below the line, the whole number at each 500 ft and the ones digit elsewhere, a 7 ft tick at 1"=50' (0.14 in); BC/EC as station-then-word (`24+05.27 BC`) 0.45 in left of the line, square to it and reading bottom to top; bearing *and* length above the tangent (`N 71°33'54" E 1240.36'`); the curve number in a bubble with a leader to the curve; the curve table No., R, Δ, T, L. The engine's labelers default to these (`design/labels.py`: per-kind sides, rotations and offsets; `above`/`below` resolve to the line's left or right and are recorded so), so a model that takes the default route matches the truth. The lenient matcher reads either word order, bare curve numbers, a bearing with or without the length (the length must agree when the truth has one), and a station number lettered in full or as the Caltrans digit. **Credit route:** `place_label`, `annotate_stationing`, `place_curve_table` and `draw_station_offset` now anchor through a referenced alignment (`BASE:ALIGN-1`, the reference at identity), the anchor records the qualified name, and the verifier resolves it to the truth's alignment (`Context.aliases`; `given_design` reads the base drawing's design through the reference, and a base that is not attached is *absent*, not tampered). The new task type **`annotate-base`** (given layers, reference, sheet; base drawing carries linework and edges; asks for stationing, bearings, callouts and the curve table through the reference) is the benchmark's version of the Tier 3 probes, whose scripted solutions now letter by the same route. **Layers:** the probe fixtures use the Caltrans named levels (`align_MAIN`, `rd_EP`, `rd_ES`, `rd_LAYOUT-NOTE-anno`, `rd_RIGHT-OF-WAY`, the L-2 sheet's `pp_LEGEND-anno`, `align_CURVE-DATA`, `border_INSIDE-BORDER-anno`, `pp_PRESENTATION`). Versions: generator `d1-v4`, verifier `d1-verify-v3`; the equation is kept a match-line's clearance from the break so the two square labels never overlap. The probe set hash changed, so the leaderboard counts only episodes whose task text is current (Haiku's 2026-10-08 row waits for a rerun). *Follow-up the same night (the E1 session's sweep of 192 finished documents):* the square labels reach about 1.35 in past the centerline, further than a two-sheet viewport's 100 ft pad, so the render cut them off; the generator now sizes a two-sheet viewport round the centerline and the labels anchored on that sheet's share, with a 0.25 in margin, and grows it until no label of the other share crosses its edge (`_label_boxes`, `_sheet_box`; the fit check uses the same box). D1-08 gained the finding `clipped`: a model-space text whose position is inside a viewport but whose footprint crosses the viewport's edge counts like an off-sheet item. *Closed 2026-10-12 (the PE question on text over the edges of pavement; spec `draft-v3`, generator `d1-v5`):* a sweep of the 560 reference documents of the four types that draw edges showed the one real contact was the bearing: set 0.06 in above the line in 0.10 in text, the 12 ft edge of pavement at 1" = 100' (0.12 in) ran through the middle of every bearing (134 of 140 pavement seeds were at 1" = 100'); the station digits only touched the 12 ft edge or cleared an 11 ft edge by 0.01 in. Robert's ruling: text touching an edge line on a narrow road is ordinary practice and nothing to worry about, and the benchmark should use the common plan scales, 1" = 10', 20', 40' and 50'. So `sheet.allowed_feet_per_inch` became `[10, 20, 40, 50]` in draft-v3 and `[40, 50]` in draft-v4 (2026-10-13, Robert: 10 and 20 would need alignments under 520 ft and never occurred); the generator fits each layout at the largest of them that shows it (1" = 50' for about 85 % of the seeds, 1" = 40' for the rest), and station numbers and bearings keep the PPM placement whatever the pavement width (an edge-clearance rule was built and validated the same day, then dropped as contrary to the ruling: at 1" = 50' the bearing sits inside a 12 ft lane with 0.08 in to spare and the digits' bottoms meet an 11 ft edge, which is the accepted look). Fitting at 1" = 50' means the design shrinks to the sheet: one-sheet alignments run 790-1,330 ft (median 1,079; 5 % under 700 ft), two-sheet 1,700-2,670 ft (the PPM's plates show about 1,500 ft). The fit loop (`d1-v5`) shrinks the tangents and radii gently (0.85 / 0.92 per attempt on one sheet, 0.8 / 0.9 on two, `SHRINK`; the old 0.7 / 0.85 overshot the window and left a quarter of the sheets under 700 ft), keeps the end pad and the legibility floors as paper lengths at the coarsest scale in use (`PAD_IN` 1.5, `MIN_EXTRA_IN` 1.2, `MIN_CURVE_IN` 1.5: 75, 60 and 75 ft at 1" = 50'), steps the design speed down a notch per attempt from the eighth (`SLOWER_ATTEMPT`; a 50-55 mph road with three curves is longer than one sheet shows at these scales: 18 of 200 seeds step, so 35-55 mph stay evenly mixed; a speed the caller pinned is never stepped, and a pinned design that cannot fit raises `ValueError`), lays the chord along the window's diagonal from the ninth (`DIAGONAL_ATTEMPT`), and tries every legal match-line break nearest the even split first (`_match_options`; a single-curve two-sheet layout may need its break well off the middle so the share with the curve fits). Every seed 1-200 on one sheet and 1-70 on two fits; the 1,260 tests pass (six that assumed 1" = 100' or the 100 ft pad were made scale-aware). The PPM's own sizes stay a separate PE item: its station numbers and bearings are TX 7 = 0.14 in at 1" = 50' (CADD Users Manual 2.6; the digitised L-4 agrees), this spec letters at 0.10 in. Offsets are not graded (the verifier poses each label from its own anchor record). The engine's labelers keep the PPM defaults.
- *Lines through text (2026-10-16, `d1-verify-v4`; the gap the `d1-v6` generator fix exposed: an agent that dimensioned through the bearing was not penalised).* D1-08 now charges a **line through a text footprint** as an overlapping pair, on the same formula and under the same `overlap` code: the lines of a dimension (`dimgeom.primitives`: the dimension line, both extension lines, the two stubs when the text and arrows flip outside, a radial dimension's leader and landing; never the arrowheads) and a callout's leader. A leader is recognised structurally, since the engine stamps no anchor on it: the line with an end at a text's insertion point and, when that line is the level shoulder `place_callout` draws from the elbow, the line meeting its far end (`legibility._leaders`); nothing else the engine draws ends at a label's insertion point (ticks sit on the centerline, a curve bubble's leader starts on the bubble). Strokes are judged in paper space like the text (`sheet_strokes`): a model-space line through each viewport that shows it, clipped to the viewport since the plot shows no more; a sheet-space line as drawn. A stroke counts when it crosses an edge of the text's footprint drawn in by 0.005 in or ends inside it (`crosses`), so a leader that stops at a text, or a line along its edge, is not charged. The pair is owned by the dimension and the text, or by the callout's text and the text its leader runs through, so a dimension never crosses its own text nor a leader the text it belongs to; a pair already charged for its text counts once; on a real sheet a pair of two `given_entities` is not charged, as before, and the referenced bases' text is context the strokes are tested against. Ordinary linework (the centerline, the edges of pavement, a real sheet's pipes and right of way) is not a stroke: text touching an edge of pavement on a narrow road is ordinary practice (2026-10-12). Mutation 35, *the T-1 width dimensioned through the bearing* (`tests/verify_mutations.py`, on the `pavement-widths` base): D1-08 0.75 with one `overlap` naming the dimension and the bearing, D1-13 `misplaced` at the explicit level, nothing else moves. That mutation was the first to put a D1-13 finding in front of the agent-view leak test, which found the finding's anchor carrying the stated station (`station`) beside the tangent (`ref`); the anchor now names the tangent only, the station staying the `expected` of the `misplaced` finding, which the agent view strips. **Scores of runs made under `d1-verify-v3` change** where an agent dimensioned or pointed through text: rescore them with `python -m roaddraft.eval report RUN --reverify` (the report flags a run scored under an older verifier as stale and will not publish it). Validation: the oracle at 100 with no findings and the start at 0 on every seeded type × 1–2 sheets × seeds 1–40 × both levels (5,104 verifications; the generator refuses four one-sheet widths layouts with no tangent to dimension), and the real-task catalog rebuilt with the same 584 pairings kept and 26 left out.
- *Ticks by the anchoring commands (2026-10-21, `d1-verify-v6`; Robert: "make D1-02 give tick credit only to ticks stamped by an anchoring command").* Labels have earned credit only through a trusted `placed_by` stamp since v1, but D1-02 matched ticks on geometry alone, so a `draw_line` at the station, a copy of a stamped tick, or entity-chain stationing (`annotate_stationing` with `path_ids`, which draws no anchor) earned full tick credit. D1-02 now matches a truth tick only against lines whose `placed_by` is in `bus.ANCHOR_PRODUCERS`; a line that would have matched otherwise is reported `unanchored` (not a value code, so no hard fail) and earns nothing, and it is no longer a D1-09 item. Hack probe *k* (`tests/test_verify_hacks.py`: ticks redrawn with `draw_line`, or copied into place) scores D1-02 0 with one `unanchored` per tick and moves no other check; probe *f* (chain-mode stationing on hand linework) now scores D1-02 0 as well. **Scores of runs made under `d1-verify-v5` change** where an agent ticked by hand or by chain mode: rescore them with `python -m roaddraft.eval report RUN --reverify`. Of the published runs only Qwen3.6-35B-A3B on `d1-variance` moves, 86.80 → 86.69: one episode of 100 (annotate-sheet, sample 4) stationed its own drawn centerline in chain mode, 66.5 → 55.9; Gemma 4 12B stays 69.34. Validation: the oracle at 100 and the start at 0 over the 16 seeded types × 1–2 sheets × seeds 1–40 × both levels (5,104 verifications, the same four layouts refused), and the real-task catalog rebuilt with the same 584 tasks and 26 left out.

## 4. The harness (`roaddraft.eval`)

### 4.1 Episode protocol

```
reset(task)      Session on task.baseline (design pre-seeded, no entities, no sheets)
observe          brief + drafting_spec + tool list (+ a state summary each turn)
loop             agent → one or more tool calls → harness executes on the Session
                 → results (diff, warnings, teaching errors) back to the agent
submit()         or a budget trips
verify()         on session.doc with truth; audit on session.bus.journal
record           trajectory JSONL: config, turns, journal, report, usage, cost
```

Harness-owned tools, in addition to the whitelisted Session surface:

- `get_task_brief()` → the brief (same JSON as the initial observation, so the agent can re-read it).
- `run_check(scope?)` → `{"budget_remaining": n, "hard_fail": bool, "checks": [{"id", "status": "pass|partial|fail", "findings": [≤ 5 stripped findings]}]}`. Budget default 3 per episode (0 in single-shot mode). Counts as a step.
- `submit()` → ends the episode. Not calling it before the step budget is a recorded outcome (`termination = "budget"`), not an error.

**Tool whitelist, D1 neutral** (in `tools.py`, per level): commands `create_layer`, `modify_layer`, `set_current_layer`, `create_text_style`, `draw_alignment`, `annotate_stationing`, `place_label`, `place_curve_table`, `create_sheet`, `create_viewport`, `modify_viewport`, `insert_block`, `fill_title_block`, `place_text`, `draw_line`, `draw_arc`, `move_entities`, `modify_entity` (with `anchor` stripped until provenance lands), `delete_entities`, `undo`, `redo`; queries `list_alignments`, `get_design_data`, `station_to_xy`, `xy_to_station`, `resolve_anchor`, `get_document_state`, `get_sheet_state`, `get_entity`, `get_extents`, `list_layers`, `list_sheets`, `list_blocks`, `list_text_styles`, and `render_sheet` in self-correct and vision modes. Hidden: everything that saves, exports, attaches references, imports LandXML, edits the design model, or reads the journal. `place_text` and `draw_line` / `draw_arc` stay available on purpose: the benchmark should show whether models take the semantic path when the coordinate path exists.

Budgets (`budget.py`, all recorded): steps 150, `run_check` 3, consecutive faults 8, output tokens per episode 60k, wall clock 20 min, and a per-run cost cap that stops the runner, not the episode.

### 4.2 Observation and tool definitions

- **Text-first.** The system prompt carries the role, the drafting rules (anchor everything, compute nothing by hand that a query provides, finish with `submit`), the budgets, and the dialect vocabulary. The first user message is the brief. *As of 2026-10-10 that is `tasks.prompts.task_text(brief, level)`: the rules, then the natural-language prompt at the run's prompt level (§3.8). Prompt level (`explicit` / `vague`) is a run dimension like dialect and mode, and the episode passes it to `verify(prompt_level=...)`; task type and sheet count are task-set dimensions (`generate_task(seed, task_type=..., sheets=...)`), and `reset` opens the task's starting document, which already carries the given phases.* Tool definitions come straight from the manifest: `params_schema` → `input_schema` (every schema is already a closed object with a `required` list, so `strict: true` is free), `description` + `example` → the tool description. Tool order is deterministic (sorted by name) so the cached prefix is stable.
- **Tool results** are the bus result JSON verbatim, with two shapings: `get_document_state(detail="full")` is capped (entities truncated with a count and a hint to use filtered queries), and file results never inline base64 unless the mode is vision, where the PNG goes back as an image block after each `render_sheet`.
- **Parallel calls.** If the model issues several tool calls in one turn, the harness executes them in order on the bus and returns all results in one user message (dropping some silently trains models not to parallelize).
- **Faults** come back as `is_error` tool results carrying the bus's teaching error (message, hint, schema, example), untouched. That error text is part of the environment and is logged as such.

### 4.3 Agents

One interface, `Agent.act(observation) -> list[ToolCall] | Submit`, and five implementations:

| Agent | Purpose | Expected score |
|---|---|---|
| `OracleAgent` | replays `reference_solution` **through the episode loop** (whitelist, budgets, logging) | 100, proving the harness does not lose points |
| `NullAgent` | submits immediately | 0 |
| `ScriptedAgent` | a deliberately naive drafter: sheet, viewport, `draw_alignment`, `annotate_stationing`; no bearings, callouts, table, title block or north arrow | ≈ 65, proving the rubric discriminates |
| `ReplayAgent` | replays any saved journal (a human GUI session, an earlier LLM episode) | whatever it earned; used for regression and SFT curation |
| `LLMAgent` | provider-driven tool-calling loop (E3) | the thing being measured |

### 4.4 Providers

- `providers/base.py`: `complete(system, messages, tools, config) -> Turn` with normalized tool calls, text, stop reason and usage (input, output, cache read, cache write). One class per vendor.
- `providers/anthropic.py`: the Messages API with tool use. `tool_choice: auto` everywhere (forced tool choice is a 400 on Fable 5.1, and forcing would bias the benchmark anyway), adaptive thinking on, `effort` as a run dimension (default `high`), `strict: true` on every tool, prompt caching with the cached prefix = tools + system + brief. Refusals (`stop_reason == "refusal"`) end the episode with `termination = "refusal"` and are **not** rescued by server-side fallbacks, since a fallback model answering would contaminate the row. Model ids from the current table: `claude-opus-5` (default), `claude-sonnet-5`, `claude-haiku-4-5`, `claude-fable-5-1`. Sampling parameters are not a control on these models, so no "temperature 0" claim appears anywhere in the writeup.
- `providers/openai_compat.py`: chat-completions tool calling for other vendors and for local open models served by vLLM or Ollama, which is the path the Phase 5 training run needs.
- `providers/fake.py`: scripted responses for tests; every E3 test runs against it.
- Usage is recorded per turn; cost is computed at report time from `eval/prices.json`, dated to when it was checked, never hard-coded.

### 4.5 Dialects and modes

- **Dialects** are tool-name skins over the same manifest: `neutral` (canonical names), `c3d` and `ord` (the aliases every command spec already carries, e.g. `ADDALIGNMENTSTAOFFLABEL`, `place label`). The harness presents the skin's names and resolves calls back through `CommandBus.resolve`. Each skin's system prompt uses that vocabulary (view frames versus named boundaries and so on, per PRD §4). Transfer gap = mean effective score (neutral) − mean effective score (skin), paired by task.
- **Modes**: `single` (no `run_check`, no render), `self_correct` (`run_check` budget 3, `render_sheet` allowed, PNG path only), `vision` (self-correct plus the PNG returned as an image). Mode and dialect are independent run dimensions.

### 4.6 Trajectory log

One JSONL file per episode, `results/<run_id>/episodes/<task_id>.<model>.<dialect>.<mode>.<sample>.jsonl`:

```
{"type": "header", "run_id", "task_id", "spec_hash", "generator_version", "verifier_version",
 "harness_version", "prompt_hash", "git_commit", "model", "provider", "dialect", "mode",
 "effort", "sample", "seed", "budgets", "started_at"}
{"type": "turn", "n", "assistant": {"text", "tool_calls": [...]}, "results": [...],
 "usage": {...}, "elapsed_ms"}
{"type": "journal", "baseline": <doc>, "entries": [...]}        ← replayable; the SFT trajectory
{"type": "verify", ...VerifyReport...}
{"type": "audit", ...}
{"type": "end", "termination": "submit|budget|refusal|error", "steps", "run_check_uses",
 "usage_total", "cost_usd", "elapsed_ms"}
```

The journal block alone is a valid `save_journal` file: any episode can be replayed and re-verified with a newer verifier, which is how a verifier fix re-scores old runs without re-running models.

### 4.7 Runner

```
python -m roaddraft.eval run --taskset d1-test --models claude-opus-5,claude-sonnet-5 \
    --dialect neutral --mode single --samples 3 --concurrency 8 --cost-cap 150
```

- Matrix = taskset × models × dialects × modes × samples; each cell is keyed and skipped on resume if its episode file has an `end` record.
- Concurrency is a thread pool; a `Session` is a plain object, so the limit is provider rate limits, not the engine. Transient API errors retry with backoff; a persistent error records `termination = "error"` and moves on.
- `--dry-run` prints the matrix and the projected cost from the last measured cost per episode.

### 4.8 Task sets

`benchmarks/tasksets/<name>.json`: `{"taskset", "generator_version", "spec_hash", "tasks": [{"seed", "curves", "equations", "task_id"}]}`.

- `d1-dev`: seeds 1–50, all dials mixed. For iteration; never reported.
- `d1-test`: seeds 1000–1099, held out; balanced over curves 1/2/3 and equations on/off; 100 tasks. The leaderboard set. Never used during development.
- `d1-variance`: 20 tasks from `d1-test` for k = 5 sampling, to size the confidence interval before spending on the full set.
- `d1-real` (*added 2026-10-22*; Robert: the eval set should use the sample sheets; *redrawn 2026-10-27*; Robert, Oct 24: "make sure real sheets are separated similar to the probes for question type"): 100 held-out tasks on the redrafted sample plan sheets, 25 from each of the four question groups of `tasks.types.REAL_GROUPS`, the real-sheet counterpart of the probe board's tiers: **draft linework** (`real-draw-alignment`), **letter alignment data** (`real-stationing`, `real-bearings`, `real-callouts`, `real-curve-table`, `real-alignment-data`), **produce the sheet** (`real-attach-reference`, `real-title-block`, `real-sheet-setup`, `real-annotate-sheet`, `real-plan-sheet`) and **notes and dimensions** (`real-construction-callouts`); a fifth group, **the whole job**, waits for a composite task and would get its own small set and board like `hard-pilots`. A group's quota is split as evenly as its types allow (5 each in the two five-type groups, 25 in the one-type groups), so the blended score weighs every question type the same and a type added to a group shares its quota rather than growing the set. Drawn from the validated catalogue `benchmarks/real_tasks/catalog.json` (§3.8): within a type every agency that has the type (Caltrans, WFL, CFL, FDOT) is drawn once before any is drawn again, then the sheet the set has used least, then a hashed id; the result is 54 Caltrans, 22 WFL, 12 CFL and 12 FDOT on 51 sheets, 77 of them on a twisted viewport. Ranked on its own board beside `d1-test`, with a column per group beside the blended score (`report.by_group`); a model's two rows are not averaged. A real run is judged against the real-sheet generator (`real-v1`), not the seeded one. The per-type draw it replaces (nine of each type, 99 tasks of eleven types from Oct 22, 108 of twelve from Oct 24) had the letter and sheet groups at 45 tasks each and the other two at 9; the first ranked row, the 9B's 99-task run of Oct 23 to 26, shares 58 tasks with the new draw and none of its notes.
- `d1-real-dev`: 24 tasks, two of each real type, on three Caltrans sheets (PPM-052, PPM-054, PPM-201, taken in hashed order until every type has two) that `d1-real` never uses. Stays per type, since it is for smoke runs and iteration and should touch every type; never reported. WFL, CFL and FDOT have too few sheets to spare one for development, so all of theirs stay held out.
- `hard-pilots` (*added 2026-10-22*; Robert: "the harder tasks should make it into the eval set as well"): the 29 harder-task pilots (`docs/Probes_Pilots.md`) as probe tasks (`eval/probe_tasks.py`), the route the 2026-10-12 review called *wrap*. Each runs on its own start project on a sample sheet with the MCP server's tools in-process (autosave, `open_document`, `view_attachment`), the server's instructions as the system prompt and the probe runner's task text; it is graded by its own check, 100 on a pass and 0 on a fail, the rubric column being the share of its items done. Track P's budgets by default (600 steps, 30 min, 200k output tokens). The changed files are kept beside the trajectory so `report --reverify` re-grades them. Oracle 100 and null 0 on all 29 through the loop. Ranked on its own board. Its generator version is a hash over the pilots' ids and task texts, so a changed prompt makes earlier runs stale.
- A test regenerates each manifest and asserts identical task ids; a changed spec or generator fails that test, which is the intended tripwire. For the real sets it also rebuilds every task from the redrafted sheets and checks its id, and fails when the catalogue was validated under another verifier (rebuild it with `scripts/real_tasks.py`, then `taskset --write`).
- Publishing: briefs and the generator are public with the harness; the truth is derivable from them by design (that is what makes the benchmark reproducible). The open-core boundary from PRD §8 sits at D3/D4 generators and the full check list, not at D1.

### 4.9 Reports

`python -m roaddraft.eval report results/<run_id>` writes `summary.json`, `leaderboard.md`, `per_check.csv`, `taxonomy.csv`, `episodes.csv`:

- **Leaderboard** rows per (model, dialect, mode, effort): effective score mean ± 95% CI (bootstrap over tasks), rubric score, hard-fail rate, clean-sheet rate, submit rate, steps, invalid-call rate, `run_check` uses, cost per sheet, n.
- **Per-check heatmap**: mean credit per check per model.
- **Failure taxonomy**: finding codes rolled up to completeness / value / anchoring / placement / legibility / standards / sheet_setup, plus harness-level tool_use (invalid params, unknown command, faults, recovery) and termination. This table is the writeup's spine.
- **Transfer gap** table when more than one dialect ran.
- Published runs copy `summary.json` and `leaderboard.md` into `benchmarks/runs/<run_id>/`; the README leaderboard is generated from them, never edited by hand.

### 4.10 As built (E3, 2026-10-14)

`agents/llm.py`, `providers/{base,anthropic,openai_compat,fake}.py`, `prompts/system_{neutral,c3d,ord}.md`, `dialects.py`, `prices.json` + `prices.py`, `tests/test_eval_llm.py` (34 tests, fake provider and stubbed HTTP only); `HARNESS_VERSION` `e3-v1`. `python -m roaddraft.eval run --model ID [--provider anthropic|openai|fake] [--effort] [--dialect] [--cost-cap]`. Acceptance so far: the **fake oracle** (the reference solution replayed as model turns through the agent, the provider's turn shape and the dialect's tool names) scores 100 on d1-dev in all three dialects, the E3 counterpart of E2's oracle-through-the-loop test; the full suite passes. **The live smoke run (`d1-dev[:5]` × one model × single) has not run**: this machine has no `ANTHROPIC_API_KEY`, and the model and route are Robert's call (§8 keeps its estimate until then). Decisions taken on the way, and where the build departs from §4.2–4.5:

- *Providers over the standard library.* The current `anthropic` SDK needs Python 3.10 and the engine runs on 3.9, so the Anthropic provider uses the Track P runner's HTTP client (`runners.anthropic_api`: credentials, retries) and the OpenAI-compatible provider the runner's streamed client with its LM Studio guards. The conversation is kept provider-neutral by the agent and translated on every request; each provider keeps the vendor's own assistant message, so the history is append-only and Anthropic's thinking blocks go back untouched.
- *`strict` is off by default* (departure from §4.4). Nine whitelisted tools take a free-form object by design (`fill_title_block` and `create_sheet` fields, `modify_entity` / `modify_layer` / `modify_viewport` changes, `set_meta` updates, `find_entities` anchor, `attach_reference` symbology, `define_block` entities), which strict mode would close to nothing, and the schemas use numeric and length bounds strict grammars are not promised to take. Off, an invalid call is a teaching error for every vendor alike, so the invalid-call rate compares. `--strict` marks only the tools closed all the way down.
- *Thinking and effort per model.* Adaptive thinking on every model that takes it, with `display: "summarized"` where the default omits the text, so the trajectory keeps the reasoning summary; Haiku 4.5 runs without (it takes only a fixed budget). `effort` defaults to `high` and is always sent (Opus 5.5 and Haiku 5.5 default to `medium` otherwise), except to models that reject it. Model ids moved on since §4.4: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-1` are current, and the price table carries them and their predecessors.
- *How a turn ends.* A turn with no tool call is the model's final answer: an implicit submit, recorded (`end.implicit_submit`, the turn's `implicit_submit`), termination `submit`. A turn cut off at the output limit without a call is answered with a one-line request to go on, twice at most; a third ends the episode as a budget, `budget_tripped = "output_limit"`. A conversation past the context the model is served at is `context`, a turn past the provider's time limit `turn_time` (`providers.base.LimitReached`): the model's outcomes, scored like any budget. `error` is left to the harness's own failures (HTTP, credentials), which the E4 report keeps out of scores.
- *Results.* Every result of a turn goes back in one message, in call order, as compact JSON of the bus result; a call the episode did not run (the turn stopped at a budget or at `submit`) gets a `not_run` error result so every tool call has its result. When 15 steps or 3 faults remain, the results carry a one-line `[harness]` note. In the vision mode a render's PNG goes back as an image beside its result and never into the trajectory.
- *Dialects.* A skin name is the first of a command's aliases for that program that is a valid tool name for every vendor (an ORD phrase written with `_`) and not already taken; queries and harness tools keep their names (43 commands renamed in `c3d`, 37 in `ord`). The system prompt, the task text and the tool descriptions are rewritten to the skin's names (multi-word names only: `trim` and `undo` stay English in prose); tool results stay the engine's words. Each skin has its own system prompt in the program's vocabulary. The transfer runs are E5.
- *Cost.* Usage is recorded per turn under Anthropic's key names whatever the vendor (an OpenAI-compatible prompt is split into uncached input and `cache_read_input_tokens`). The episode prices each turn from `prices.json` (dated 2026-10-06; Haiku 5.5's 100k-prompt tier makes cost a per-turn sum) into `end.cost_usd` and `end.prices_checked`; an unpriced model's cost is null, not zero. The runner's `--cost-cap` starts episodes only as workers free up and starts none once the finished ones (the resumed included) have spent the cap; `--dry-run` projects the cost from the model's measured episodes under `results/`.

## 5. Metrics

| Metric | Definition | Reported as |
|---|---|---|
| Effective score (headline) | `0 if hard_failed else rubric_score` | mean ± CI, per model |
| Rubric score | Σ weight × credit | mean |
| Hard-fail rate | episodes with a value finding on a hard-fail check / n | % |
| Clean-sheet rate | effective == 100 | % |
| Per-check credit | mean credit per check id | heatmap |
| Submit rate | ended by `submit` / n | % |
| Steps | tool calls per episode | median, p90 |
| Invalid-call rate | `invalid_params` + `unknown_command` / tool calls | % |
| Fault rate, recovery rate | `command_failed` / calls; faults followed within 3 calls by a successful call of the same command | % |
| `run_check` use | uses per episode and Δ effective score before/after the last check | mean |
| Cost per sheet | recorded usage × price table | USD |
| Transfer gap | effective(neutral) − effective(skin), paired by task | points ± CI |
| Prompt gap | effective(explicit prompt) − effective(vague prompt), paired by task (§3.8) | points ± CI |
| Per task type | every metric above, split by task type and by 1 / 2 sheets (§3.8) | table |

## 6. Adapters (thin, after E4)

- **Gymnasium-style** `RoadDraftEnv` in `eval/gym.py`: `reset(seed) → (obs, info)`, `step({"tool", "params"}) → (obs, reward, terminated, truncated, info)`; terminal reward = effective / 100; optional potential-based shaped reward = Δ rubric / 100 per step, training-only and never in eval runs. This is what the Phase 5 GRPO example consumes, and the sub-50 ms verifier makes per-step shaping affordable.
- **Prime Intellect `verifiers`** (`MultiTurnEnv` + `Rubric`) and **Inspect AI** (`Task` + `Solver` + `Scorer`) wrappers, each under 150 lines, both delegating to `episode.py` and `verify()`. Their current APIs are checked against the projects' docs at implementation time, not assumed.

## 7. Work packages

Same conventions as the Phase 1 spec: disjoint file ownership per stage, an acceptance command, and a number at the end.

| WP | Scope | Owner files | Depends on | Acceptance | The number |
|---|---|---|---|---|---|
| **E0 Phase 1 finish** | WP1b, WP4, WP5, WP6, WP7, WP8, WP9, WP10 per `docs/RoadDraft_Phase1_Build_Spec.md`, plus `placed_by` in `as_anchor` and the bus stamp, and `truth.design_fingerprint` asserted equal to the baseline's | per the spec's §10 table | Stage 1 (done) | `pytest -q`; `python -m roaddraft.tasks 42 --out /tmp/x` writes 6 files; `match_truth` on the reference is clean | 200 seeds: reference replays and matches truth |
| **E1 Verifier** | §3 in full: `verify/*`, `tests/test_verify_{oracle,mutations,hacks,legibility,geometry,report}.py` | E0 | `pytest -q tests/test_verify_*.py` | oracle 200/200 = 100; null 50/50 = 0; ≥ 25 mutations, ≥ 8 probes; p95 < 50 ms |
| **E2 Harness core** | §4.1–4.3, 4.6–4.8: `eval/*` except providers/llm/report, four non-LLM agents, CLI `run` / `taskset` / `verify` / `human`, the three taskset manifests, `results/` gitignored, `tests/test_eval_{episode,budget,tools,trajectory,runner,taskset}.py` | `Session` now; E0 + E1 for the oracle test | `pytest -q tests/test_eval_*.py`; `python -m roaddraft.eval run --taskset d1-dev --agent oracle` | oracle through the loop 50/50 = 100; scripted ≈ 65 and stable; human playtest = 100 with the journal committed under `benchmarks/expert/` |
| **E3 LLM agents** | §4.2, 4.4, 4.5: `agents/llm.py`, `providers/*`, `prompts/*`, `dialects.py`, `prices.json`, `tests/test_eval_llm.py` (fake provider only) | E2 | `pytest -q tests/test_eval_llm.py`; smoke run `d1-dev[:5]` × one model × single | measured cost and steps per sheet; invalid-call rate on the smoke run |
| **E4 Leaderboard v0.1** | §4.9: `eval/report.py`, `scripts/make_leaderboard.py`, README section, the writeup draft | E3, spec frozen at v1 | `d1-variance` × 5 samples first, then `d1-test` × ≥ 3 models × neutral × {single, self_correct} | **best model X/100**, hard-fail rate, taxonomy table, CI half-width < 5 points |
| **E5 Transfer + vision** | dialect system prompts, `c3d` / `ord` runs, vision-mode runs | E4 | same runner | transfer gap per skin ± CI |
| **E6 Adapters** | §6: `eval/gym.py`, `verifiers` / Inspect wrappers, TRL/GRPO example | E4 | oracle scores 100 through each adapter | one measured reward curve (Phase 5) |

Sequencing given the Portfolio arc (RoadDraft is Arc 2, after the EKG arc): E0 is one more workflow-driven session like the Phase 1 build; E1 and E2 are independent of each other after E0 and can run in parallel; E3 is small; E4 is mostly run time and writing. The PE decisions in §3.7 are the only human-gated step before E4 and should be made during E1.

## 8. Cost of the leaderboard run (estimate, replaced by the E3 smoke measurement)

**Measured 2026-10-18 (the E3 smoke run).** `d1-dev[:5]` × Qwen3.6-35B-A3B (bf16, Runpod vLLM, the `openai` provider; no Anthropic key on this machine) × single × explicit, from the worktree pinned at `727fb7f`: effective 62.4 (100 attach-reference, 100 create-alignment, 82.7 annotate-base, 29.4 annotate-sheet, 0 bearings), every episode submitted, 0 invalid calls in 139. Per sheet: 4 to 65 steps, 12 to 316 s, 0.7k to 32.5k output tokens (most of it thinking), 0.1M to 1.7M input tokens (the tool schemas and the history are re-sent every turn, so input grows with the square of the steps). Priced from `prices.json` with the earlier turns' prefix read from cache, those token counts come to Sonnet 5.5 $0.09 to $0.93 a sheet (mean $0.37), Haiku 4.5 $0.18, Opus 5.5 $0.60, Fable 5.1 $1.35; without caching about four times that. So `d1-test` × 3 samples is about $110 a model and mode on Sonnet, $55 on Haiku, $400 on Fable: inside the table's ranges at their low end, with a Claude tokenizer and a Claude model's step count still to measure. An open-weight model on one Runpod card costs worker time instead (the smoke: about 5 min of cold start and 5 min of run at $3.49/h). Results under `results/e3-runpod/e3-smoke-qwen3.6-35b-a3b` (gitignored; d1-dev is never published). Two findings from the episodes, both to settle before `d1-variance`: the engine accepts `annotate_stationing` in path mode with a sheet as `space` and draws the model-space ticks at their model coordinates on the paper (thousands of inches off the sheet), after its own error on the alignment-mode call pointed at path mode; and D1-05 matches a bearing label only by its tangent ref (`T-1`), so a bearing placed by the engine's labeler at the tangent's middle station, as the prompt words it, with the exact text, scores missing. **Both settled 2026-10-18:** the engine now refuses path stationing whose linework is not in the target space, with a teaching error naming `space='model'` (the tool schemas and examples unchanged, tools `sha256:60eeeb21`); and `d1-verify-v5` reads a bearing anchored at a station strictly inside a tangent as that tangent's `T-n` bearing, its placement judged at the tangent's middle (PE decision). Re-verified on the engine the episodes ran on (`727fb7f`) with v5, the smoke reads **66.7** (annotate-sheet 29.4 → 50.6, its three bearings credited; the rest unchanged); the same replay with v4 reproduces 62.4.

*2026-10-15: the table below is the June 2026 price list (cached 2026-06-24) under the predecessor model ids (`claude-opus-5`, `claude-sonnet-5`); the current ids and prices are in `eval/prices.json` (dated 2026-10-06, §4.10), and these numbers stand only until the E3 smoke run measures cost per sheet.*

Assumptions: cached prefix (tools + system + brief) ≈ 15k tokens; 50–80 tool calls per sheet; ≈ 300 output tokens per call plus thinking; tool results ≈ 1k tokens each; prompt caching on. Per sheet that is roughly 20–30k output tokens, 50–80k uncached input tokens and 1–2M cached-read tokens.

| Model (first-party prices, table cached 2026-06-24) | ≈ cost per sheet | 100 tasks × 1 sample | × 3 samples |
|---|---|---|---|
| `claude-opus-5` ($5 / $25 per MTok) | $1.0–1.5 | $100–150 | $300–450 |
| `claude-sonnet-5` ($2 / $10) | $0.4–0.6 | $40–60 | $120–180 |
| `claude-haiku-4-5` ($1 / $5) | $0.2–0.3 | $20–30 | $60–90 |
| `claude-fable-5-1` ($10 / $50) | $2–3 | $200–300 | $600–900 |

Plan on the order of $500–1,000 for a four-model v0.1 with `d1-variance` at k = 5 and `d1-test` at k = 1–3, and treat `--cost-cap` as mandatory. The E3 smoke run replaces these numbers before anything larger is launched.

## 9. Risks and open decisions

| Item | Recommendation | Where |
|---|---|---|
| Spec is DRAFT; every fix changes task ids | Batch the §3.7 decisions, freeze v1 before E4, never publish on draft ids | Robert (PE review) |
| Hard-fail semantics could feel harsh (one wrong cell = 0) | Keep it; report rubric score and hard-fail rate beside the headline so the information is not lost | §3.7 |
| Anchor spoofing via `modify_entity` | ~~`placed_by` stamp in E0~~ landed 2026-09-10; no harness stripping needed | done |
| `mc` / `equation` labels uncovered by any check | Assign them (§3.7 item 4) before E1 | §3.7 |
| Model non-determinism | k samples, paired comparisons, bootstrap CIs | E4 |
| Cost | `d1-variance` first, cost cap, cached prefix, effort as a dimension | E3/E4 |
| Fable 5.1 API differences (no forced tool choice, refusals) | `tool_choice: auto` everywhere; refusal is a termination category; no fallbacks in eval runs | E3 |
| Legibility formula is a guess | Tune on the human playtest and the reference document (both must be 1.0), then freeze | E1 |
| `_upright` west-heading gotcha | Engine and truth share it, so scores stay consistent; fix in spec v2 with a new hash | later |
| Harness fidelity | Oracle-through-the-loop = 100 is a permanent test, not a one-time check | E2 |

## 10. Immediate next actions

E0, E1 and E2 are done. E0 landed 2026-09-10 (6df5252, 029658e) and was re-verified 2026-10-13. E1 is `roaddraft.verify` at `d1-verify-v4` on spec `v1` (§3.8; 295e6ea to d4cee1f, 2026-10-10 to 14; 16 seeded and 11 real-sheet task types, 584 real tasks; frozen 2026-10-16; `d1-verify-v4` the same day: a dimension line or callout leader through text is a D1-08 overlap, so earlier runs need `report --reverify`). E2 is `roaddraft.eval` (70e4280, 2026-10-14: oracle through the loop 50/50 = 100, scripted 37.75 on the mixed set, null 0; the three manifests under `benchmarks/tasksets/`); its one open acceptance item is the human playtest. E3 and E4 are built and committed (a4e6a0e, 2026-10-15; §4.10, the fake oracle at 100 in all three dialects; the report, `--publish` and `scripts/make_leaderboard.py`, no ranked run) and have not run against a model. What remains:

1. ~~The one generator fix, then freeze `DRAFTING_SPEC_V1` `draft-v4` → `v1`~~ **Done 2026-10-16:** the width dimension clears the bearing lettering (`d1-v6`, 4f10ecb) and the spec is `v1`, `sha256:0e07d5e83c0b1cb8` (§3.8), with the pinned ids, the three manifests, the real-task catalog and the prompt workbook regenerated on it. Every §3.7 decision is in; the freeze is the version and status lines and the two level readings marked decided, nothing else in the dictionary moved.
2. ~~The E3 smoke run~~ **Done 2026-10-18** on Qwen3.6-35B-A3B through Runpod (§8, measured): 62.4 on `d1-dev[:5]`, 0 invalid calls, Sonnet 5.5 projected at about $0.37 a sheet. Robert: open-weight models first, the frontier route decided later. Both findings settled the same day (§8): the engine refuses sheet-space stationing of model linework, and `d1-verify-v5` credits a bearing anchored at a station on its tangent; the smoke re-verifies at 66.7.
3. The human playtest on seed 42 (`python -m roaddraft.eval human start`, then `human score`); commit the expert journal under `benchmarks/expert/`.
4. E4: `d1-variance` × 5 samples to size the interval (*planned 2026-10-18:* Qwen3.6-35B-A3B on Runpod, `runpod_campaign.py e3 qwen3.6-35b-a3b`: 20 tasks × 5 samples × single × explicit = 100 episodes, 4 at a time, from the worktree pinned at the commit carrying the engine fix and v5; about 1.5 h and $4–8 of worker time at $3.49/h; it measures the within-task spread against the between-task spread, which sets the samples `d1-test` needs for a CI half-width under 5; waits on Robert's go), then `d1-test` × three or more models × neutral × {single, self-correct}; `report --publish`; `scripts/make_leaderboard.py`; write *"Why frontier models can't draft a plan sheet (yet)"* from the taxonomy table.
5. The sample sheets and the harder tasks (*added 2026-10-22*): `d1-real-dev` smoke on one open-weight model, then `d1-real` and `hard-pilots` × the same models as `d1-test` (`hard-pilots` needs an image-capable provider for its five scanned-sheet pilots). The oracle and null agents through the loop on both real sets are the free acceptance check (§4.8).
6. E5 (the `c3d` and `ord` skins exist in `eval/dialects.py`; the transfer and vision runs do not) and E6 (the adapters), after E4.
