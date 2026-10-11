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
| D1-02 ticks | matched ticks / expected ticks (per region, through equations) | — | `missing`, `misplaced` |
| D1-03 station labels (+ equation labels) | correct anchored visible / expected | a matched label with wrong content | `missing`, `wrong_value`, `not_visible`, `unanchored` |
| D1-04 PC/PT (+ PCC/PRC, + C-n callouts) | same | same | same |
| D1-05 bearings | same, one per tangent `T-n` | same | same |
| D1-06 curve table | 0.2 table present, anchored, headers right + 0.8 × correct rows / curves | any wrong cell | `missing`, `wrong_value`, `unanchored`, `wrong_field` |
| D1-07 anchored position | consistent / matched required labels | — | `misplaced`, `anchor_inconsistent` |
| D1-08 legibility | max(0, 1 − 0.25 × (overlapping pairs + items outside the usable area)), computed in **paper space** over everything visible on the sheet (model labels mapped through their viewport, sheet text, tables, the north arrow) | — | `overlap`, `off_sheet` |
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

Each of these changes `spec_hash` and therefore every task id. Batch them, decide once, then freeze `draft-v1` → `v1`.

1. Add **D1-00 sheet setup** (weight 5, taken from D1-02 → 10 and D1-11 → 2, or as the PE prefers). Without it, a sheet with no viewport scores 0 on nine checks with no finding that says why. *Decided 2026-10-09 (Robert): added at weight 5. Those two cuts free only 3 points, so the weights are D1-02 12 → 9 and D1-11 3 → 1 (sum 100).*
2. ~~Add `placed_by` to the anchor record (§2.7) and the bus stamp (§3.5 item 3).~~ **Done 2026-09-10** — no decision left, but note it is a key on every anchor record and so is visible to agents through `get_entity`.
3. Write the **hard-fail rule** into the spec text: "missing costs credit; a wrong value shown on the sheet is a hard fail; the effective score of a hard-failed sheet is 0". *Decided 2026-10-09: kept as written; `DRAFTING_SPEC_V1["scoring"]` states it, and the text and geometry credit rules (items 5, 6).*
4. **Assign `mc` and `equation` labels to checks.** `labels.mc.required` is true and `required_label_kinds` includes `mc`, but no D1 check covers the C-n callouts, and equation labels are likewise uncovered. Proposal: D1-04 covers PC/PT/PCC/PRC and C-n; D1-03 covers station and equation labels. *Decided 2026-10-09: as proposed; the check names say so.*
5. Confirm **credit rules for unanchored work**: geometry-matched linework and ticks earn credit; text and tables only through anchors.
6. Confirm **legibility is judged in paper space** at the deliverable scale, including model-space labels seen through the viewport.
7. Review tolerances (0.005 ft, 1 second, 0.05 in) and the `_upright` west-heading gotcha already flagged in Phase 1.
8. Task ids and any published number are tied to the frozen spec. **No leaderboard is published on `draft-v1`.**
9. **Reconcile `draft-v1` with the Caltrans PPM**, now indexed under `benchmarks/knowledge/caltrans-ppm/` (README there lists each departure with page citations): BC/EC versus PC/PT wording, full annotation at 500-ft stations with single digits between versus every 100-ft station in `12+34.56` form, 0.14 in ticks with labels below the line versus 0.40 in ticks with labels on the left, PPM `TX` text sizes versus 0.10 in labels, and tangent distances beside bearings. Decide per item whether the neutral spec follows the PPM or keeps the genericized value, and record the citation next to the value in `spec_v1.py`. *Decided 2026-10-05 (Robert): BC/EC wording follows the PPM; `spec_v1.py` and the engine letter BC/EC, citation recorded. The other items are still open.*

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

The brief's project carries a typical section (two 11- or 12-ft lanes). **D1-12** matches the edge pieces geometrically like the centerline (any layer; layer judged in D1-09); linework on the edge layer that is off the pavement width is `geometry_mismatch` (hard fail). **D1-13** wants a model-space linear/aligned dimension whose two points sit on the two edges at one station of the tangent and whose text reads the width: explicit = at the stated station, text exact; vague = anywhere on the tangent, text by value; a wrong number hard-fails. The dimension's text counts in D1-08 legibility. A 24-ft pavement is too narrow for its own dimension text at plan scale, so the engine sets the text past the right edge of pavement; the reference dimensions at the half station (xx+50) nearest each tangent's midpoint, 0.1 in ahead, with a 1.5× text gap that puts the text beyond 0.5 in right of the centerline, outside the band the BC/EC labels use, and keeps 1.6 in from an equation label. A seed with no tangent that allows this cannot make a widths task (`generate_task` raises; the task-set builder skips it); none of seeds 1–70 do that. **D1-14** is structural: a reference whose path names the shipped base file, in model space at identity, visible and unclipped (0.5 attached + 0.25 placement + 0.25 visible); the file itself is never read by the verifier. `Task.files` ships the base drawing; `session_for_task` writes it beside the document so `attach_reference` resolves it. D1-09 judges only the layers the asked-for work is drawn on (all six for `layer-setup`; at the vague level a layer need only exist).

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

**Validation as built:** every task type × 1 and 2 sheets × both levels: reference = 100 with no findings, starting document = 0 (40 seeds, 1,440 verifications; `tests/test_verify_scope.py` keeps 6 seeds of it); the whole-sheet suite of §3.6 (200-seed oracle, 50-seed null, determinism, 34 mutations, 11 hack probes, p95 < 50 ms) still passes; two-sheet mutations (match line deleted, label wrong or missing, second sheet deleted) move D1-00 and the per-sheet checks by the expected amounts.

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
- A test regenerates each manifest and asserts identical task ids; a changed spec or generator fails that test, which is the intended tripwire.
- Publishing: briefs and the generator are public with the harness; the truth is derivable from them by design (that is what makes the benchmark reproducible). The open-core boundary from PRD §8 sits at D3/D4 generators and the full check list, not at D1.

### 4.9 Reports

`python -m roaddraft.eval report results/<run_id>` writes `summary.json`, `leaderboard.md`, `per_check.csv`, `taxonomy.csv`, `episodes.csv`:

- **Leaderboard** rows per (model, dialect, mode, effort): effective score mean ± 95% CI (bootstrap over tasks), rubric score, hard-fail rate, clean-sheet rate, submit rate, steps, invalid-call rate, `run_check` uses, cost per sheet, n.
- **Per-check heatmap**: mean credit per check per model.
- **Failure taxonomy**: finding codes rolled up to completeness / value / anchoring / placement / legibility / standards / sheet_setup, plus harness-level tool_use (invalid params, unknown command, faults, recovery) and termination. This table is the writeup's spine.
- **Transfer gap** table when more than one dialect ran.
- Published runs copy `summary.json` and `leaderboard.md` into `benchmarks/runs/<run_id>/`; the README leaderboard is generated from them, never edited by hand.

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

1. Run E0 as a workflow (stages 2–4 of the Phase 1 spec plus the two contract additions), with the same disjoint-ownership discipline.
2. Decide the §3.7 spec items and freeze `DRAFTING_SPEC_V1` → `v1`; regenerate the task-set manifests.
3. Build E1 and E2 in parallel; run the human playtest on seed 42 and commit the expert journal.
4. E3 smoke run on five dev tasks with one model; replace the §8 numbers.
5. E4: `d1-variance`, then `d1-test`; generate the leaderboard; write *"Why frontier models can't draft a plan sheet (yet)"* from the taxonomy table.
