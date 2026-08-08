# RoadDraft — Build Plan

**An RL environment that teaches AI models to draft roadway plan sets**
Robert Denison, PE · Working plan v1 · August 2, 2026
*(Working name — rename freely.)*

---

## 1. Concept

RoadDraft is a training/evaluation environment ("game") where an AI agent receives finished roadway design data plus a drafting specification, and must produce annotated plan sheets. A deterministic verifier scores the output — every label value on a plan sheet (station, elevation, curve data, grade, K value) derives exactly from the design data, so right and wrong are computable, not judged.

**Why this niche:** mechanical text-to-CAD is crowded (Zoo, Adam, Spectral Labs SGS-1) and benchmarked (Text2CAD-Bench, where frontier models hit 70–90% invalid outputs on harder tasks). Infrastructure *drafting* has no environment, no benchmark, and no one building one — and it requires exactly the domain knowledge a roadway PE has and AI researchers don't. The verifier — the encoded knowledge of what a correct sheet contains — is the moat, and it doubles as a standalone plan-set QA tool.

**Core design principle (your call, and the right one):** the thinking lives in the environment's internal models and verifiers, not in any CAD program. Civil 3D, OpenRoads, or anything else are thin adapters at the edges. What the environment teaches — what must appear on a sheet, where, and why — is program-agnostic and transfers.

---

## 2. Why roadway drafting works as an RL environment

- **Ground truth is computable.** PC/PT stations, bearings, Δ/R/T/L, profile elevations, K values — all derive deterministically from the alignment and profile. Label verification is exact math, not fuzzy matching.
- **Standards are codified.** AASHTO / Caltrans HDM govern design values; DOT CADD manuals (Caltrans, SCDOT, etc.) govern layers, text heights, stationing format, required annotations. Published rules convert directly into checker code.
- **Tasks are generatable.** A procedural design generator produces unlimited alignments/profiles that are standards-compliant by construction — infinite tasks with known answers, no data licensing problems.
- **Failure is informative.** Partial credit (85% of labels correct, two overlaps, one missing curve table) gives the dense reward signal RL training needs.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Harness / API                       │
│   Gymnasium-style episodes · eval runner · leaderboard  │
│   MCP server mode (any agent can connect and play)      │
├────────────────┬───────────────────┬────────────────────┤
│ Task Generator │  Agent Interface  │      Verifier      │
│ procedural     │  semantic actions │  completeness      │
│ designs w/     │  or raw-code mode │  value correctness │
│ known truth    │  (sandboxed)      │  standards, layout │
├────────────────┴───────────────────┴────────────────────┤
│              Canonical models (the core IP)             │
│  Design model: alignments, profiles, surfaces, stations │
│  Sheet model: viewports, labels, tables, title block    │
├─────────────────────────────────────────────────────────┤
│        I/O adapters (edges only, never in core)         │
│  LandXML ↔ · DXF out (ezdxf) · PDF out · later: IFC 4.3,│
│  OpenDRIVE, Civil 3D via APS Design Automation          │
└─────────────────────────────────────────────────────────┘
```

**Canonical design model** — tangents / circular curves / spirals, parabolic vertical curves, stationing with equations, surfaces, project metadata. Serialized as JSON schema; imported/exported as LandXML (natively supported by both Civil 3D and OpenRoads — this is what makes "applicable to multiple programs" real).

**Canonical sheet model** — semantic entities: viewport (station range, scale, rotation), linework references, labels (text + anchor + style), curve/VC data tables, match lines, title block fields. Rendered to DXF and PDF. The agent works at this semantic level; DXF is just a render target.

**Agent interface, two modes:**
1. *Semantic drafting actions* (tool calls / MCP): `place_station_labels`, `add_curve_table`, `annotate_profile`, `set_match_line`, `fill_title_block`… — the mode that transfers across programs, because an adapter can replay the same actions in Civil 3D or OpenRoads later.
2. *Raw-code mode*: agent writes Python against the sheet SDK in a Docker sandbox — closer to how labs eval code agents.

**Verifier** (rubric → 0–100, plus hard fails):
- *Completeness*: every curve has data and PC/PT labels; bearings on tangents; station ticks at spec interval; grades, VC data, PVIs on profile; north arrow, scale, match lines, title block fields.
- *Value correctness*: label values recomputed from design data must match exactly. Wrong elevation = hard fail.
- *Anchoring*: labels must reference the correct geometry (no free-floating text that happens to say the right thing) — this is the anti-reward-hacking layer.
- *Standards*: layer names, text heights, stationing format ("123+45.67"), abbreviations per the drafting spec.
- *Legibility*: bounding-box overlap detection, labels within sheet extents, leader-line targets.
- Optional secondary signal: VLM judge for visual quality (never primary — Text2CAD-Bench pattern).

**Stack:** Python · numpy/shapely (geometry) · ezdxf (DXF) · jsonschema · matplotlib (PDF/renders) · Docker · later rasterio/py3dep for real terrain. No CAD license required to run the environment.

---

## 4. Program parity — staging the environment to feel like C3D and Bentley

Your "applicable to multiple programs" requirement, made concrete: the agent should learn workflows and vocabulary that *already exist* in Civil 3D and OpenRoads/MicroStation, so moving from the test app to a real program — or between the two programs — is a re-skin, not a re-learn.

**One ontology, program dialects.** The core model stays neutral, but every concept carries its C3D and Bentley names, and the environment can present any task in either vocabulary:

| RoadDraft core concept | Civil 3D | Bentley (ORD / MicroStation) |
|---|---|---|
| Layer | Layer | Level |
| Symbol | Block | Cell |
| External reference | Xref / data shortcut | Reference attachment |
| Label style | Label style | Annotation group / element template |
| Sheet frame | View frame (Plan Production) | Named boundary |
| Typical section | Assembly / subassemblies | Template |
| Alignment | Alignment | Horizontal geometry |
| Profile | Profile + profile view | Vertical geometry + profile model |
| Terrain | TIN surface | Terrain model |
| Standards bundle | DOT state kit (styles) | DOT workspace |
| Geometry / annotation / sheet separation | Model space + paper-space layouts | Design / drawing / sheet models |

**Command dialects, not just name maps.** Expose the same semantic actions in three skins: *neutral* (clean JSON tools), *C3D-style* (Plan Production workflow: create view frames → generate sheets → annotate with label styles), and *ORD-style* (key-in flavored: named boundaries, annotation groups). MicroStation key-ins and the AutoCAD command line are **text** interfaces — the modality LLMs are strongest at — so practicing a dialect in the environment is practicing the real program's actual automation surface.

**Stage the workflow, not just the output.** Episodes follow the shared procedure both programs enforce: attach references / data shortcuts → load the standards kit → frame the sheets (view frames / named boundaries) → cut sheets → annotate via styles → final check. A model that internalizes that sequence — and the separation of design geometry, annotation, and sheet composition — already holds the mental model both platforms are built on.

**Standards as swappable kits.** Deliver the drafting spec the way real deployments do: as a workspace / state-kit bundle (layer↔level map, text styles, label formats, title block). Switching DOTs = swapping kits — true to life, and it generates transfer tasks for free ("same design, redraft under a different agency's kit").

**Transfer gap as a headline metric.** Run the same tasks in each dialect and report the spread (neutral vs. C3D-style vs. ORD-style). A small gap means the model learned *drafting*; a large gap means it memorized a tool. Nobody publishes this number for CAD — it's a novel, very legible eval result.

**GUI-parity mode (optional, later).** For computer-use agents: a lightweight web UI over the same backend, skinned like the real programs (ribbon, layer/level manager, style pickers). Only worth building if you target computer-use evals — but it's exactly the kind of environment labs want for agentic GUI work, and a civil-CAD one doesn't exist.

---

## 5. The CADapp — build spec (what the model actually touches)

The environment needs a real application under it. Build it **headless-first**: a CAD engine with clean machine interfaces, and only a thin human viewer on top.

### 5.1 Components

| Component | What it is | Notes |
|---|---|---|
| Document model | Project → design model (alignments, profiles, surfaces, stationing) + sheet set | JSON-serializable; LandXML in/out |
| Command bus | Every mutation is a serializable command; state changes *only* through it | The load-bearing decision: commands = action space, command log = training trajectory, replay = determinism, undo = free, and the C3D/ORD dialects are just command-name translations |
| Geometry engine | Curve/spiral/VC math, stationing, state-plane coordinates, US survey feet | Pure functions, unit-tested against hand calcs |
| Renderer | DXF (ezdxf), PDF, and PNG viewport renders | PNGs are the vision observation; multiple zoom levels to control token cost |
| Verifier service | Rubric checks vs. ground truth, per-check breakdown output | Runs outside the agent sandbox |
| Task service | Procedural generator + versioned, hash-pinned task sets | Same seed → same task, forever |
| Session server | REST/WebSocket + **MCP server**; N parallel seeded sessions | Stateless workers + session store; Docker sandbox for raw-code mode |
| Web viewer (thin) | Replay any session: render, action log, score breakdown | Debugging, demo GIFs, verifier sanity-checks; grows into GUI-parity mode later |

### 5.2 The tool surface (what the model sees)

**Queries:** `get_task_brief()` · `get_design_data(kind)` (paginated tables) · `station_to_xy(sta, offset)` / `xy_to_station(x, y)` · `get_sheet_state()` (compact semantic JSON) · `render(viewport?, dpi)` (PNG) · `run_check(scope?)` — partial verifier feedback, **budget-limited** (e.g., 3 per episode)

**Actions (via command bus):** `create_sheet(template, viewport)` · `set_viewport(...)` · `place_label(kind, anchor_ref, style)` · `add_curve_table(...)` / `add_vc_table(...)` · `draw_station_ticks(interval)` · `set_match_line(sta)` · `fill_title_block(fields)` · `move(id, dxy)` · `delete(id)` · `undo()` · `submit()`

Design rules that make it model-friendly — and trainable:

- **Text-first.** Full state is always available as compact JSON, so text-only models can play; renders are optional confirmation for vision models. Doubles the models you can benchmark.
- **Every action returns a diff + warnings** ("label L-041 placed; overlaps L-032"). Immediate feedback is dense learning signal.
- **Strict schemas, teaching errors.** Invalid calls return *why* and what valid looks like — error messages are training data.
- **Anchors are references, not coordinates.** `place_label(anchor="PC-3")`, never raw XY — forces the model to work in design semantics and lets the verifier check intent.
- **The `run_check` budget** teaches self-QA without turning the verifier into an oracle; "did the model use its checks?" becomes a writeup analysis.

### 5.3 Training modes

| Mode | App provides | Use |
|---|---|---|
| Eval | Terminal rubric score, fixed held-out task sets, leaderboard reports | The Phase 3 artifact |
| Multi-turn self-correction | Render + check results between attempts | How frontier agents actually get used |
| SFT data generation | The generator emits a **reference solution trajectory for every task** (it knows the ground truth), plus record-your-own expert sessions through the same command bus | Free expert demonstrations at scale — a quietly big deal |
| RL (GRPO/PPO) | Seeded parallel sessions, terminal + optional shaped per-action reward, verifiers/Gymnasium wrappers, TRL example script | Phase 5 training-proof |

Performance targets so RL is feasible: **<100 ms per action, <1 s per render, ~50 parallel sessions** on one machine; env/spec/task versions pinned so every result reproduces.

### 5.4 Human-play mode (build this before blaming the models)

A minimal command-line or form UI over the *same* tool surface, so you can draft a sheet through the exact action space. Two payoffs: recorded expert trajectories, and the critical playtest — **if a PE can't produce a 100-score sheet with these tools, the action space is broken, not the model.**

### 5.5 App milestones → phase mapping

| Milestone | Contents | Lands in |
|---|---|---|
| M0 | Schemas, command bus, geometry engine | Phase 1 |
| M1 | Renderer, LandXML I/O, task generator + reference trajectories | Phase 1 |
| M2 | Session server, MCP + tool API, verifier wired in — **first agent plays** | Phase 2 |
| M3 | Eval harness, trajectory logging, thin web viewer | Phase 2–3 |
| M4 | Dialect skins, `run_check` budgets, human-play mode | Phase 4 |
| M5 | RL mode: parallel rollouts, shaped rewards, TRL/GRPO example | Phase 5 |

Vertical-slice rule: drive M0→M2 against D1 tasks only, get one agent scoring end-to-end, *then* widen.

---

## 6. The game — curriculum

**Drafting track (v1):**

| Level | Task | Verifier focus |
|-------|------|----------------|
| D1 | Plan-view sheet, single sheet, tangents + circular curves | Station ticks, bearings, curve data tables, PC/PT |
| D2 | Full plan & profile sheet | + grades, VC data, PVI stations/elevations, datum ties |
| D3 | Multi-sheet run with match lines + sheet layout | Station ranges per sheet, match-line consistency, index |
| D4 | Redline revisions: existing sheet + markup list → corrected sheet | Diff verifier: requested changes made, nothing else broken |
| D5 | Dialect transfer: repeat D1/D2 through the C3D-style and ORD-style dialects | Transfer gap vs. neutral dialect |

Difficulty dials within each level: curve count, spirals, station equations, sheet count, topo/utility clutter density.

**Design track (later, reuses the same core):** G1 horizontal layout to HDM standards → G2 profiles with K/sight-distance checks → G3 corridor + earthwork optimization against terrain. This is where the environment grows from "AI drafter" toward "AI designer."

---

## 7. Phases

Assumes ~8–10 hrs/week alongside EKG. **Every phase ends shippable — stopping at any point still leaves a coherent artifact.**

**Phase 0 — Spec (wk 1).** Write drafting spec v1 as a machine-readable document: ~25–40 checks, Caltrans-flavored but genericized, plus rubric weights and JSON schemas for the design/sheet models. This is your PE knowledge dump — the highest-leverage week of the project. Freeze it; version later changes.

**Phase 1 — Geometry core (wks 2–3).** Alignment/profile math, stationing engine, LandXML import/export, procedural design generator, ground-truth label computer. Unit-test against hand calcs.

**Phase 2 — v0.1 loop (wks 4–5).** D1 end-to-end: task → agent (semantic actions + DXF render) → verifier → score. Run 3–4 frontier models over ~50 tasks via API. First leaderboard numbers.

**Phase 3 — Publish (wk 6). ← the job-search artifact ships here.** GitHub repo, README with leaderboard, 1,500-word writeup — working title: *"Why frontier models can't draft a plan sheet (yet)"* — plus a short GIF of an agent drafting. List on Prime Intellect's Environments Hub. Cross-post LinkedIn/HN.

**Phase 4 — Depth (wks 7–9).** D2/D3, MCP-server mode (directly on-brand with your EKG/MCP story), redline tasks, command-dialect skins (C3D and ORD vocabularies) with first transfer-gap numbers, more models, v0.2 with updated numbers.

**Phase 5 — Options, pulled not pushed (wk 10+).** Pick based on the response v0.1 gets:
- *Training proof*: GRPO run on a small open model — does the environment actually train? (The most impressive technical flex for lab audiences.)
- *Multi-program proof*: Civil 3D adapter via APS Design Automation replaying semantic sheets into real DWG — demonstrates the program-agnostic claim.
- *Product probe (Denison Systems)*: the verifier alone, pointed at human-produced sheets, is an automated plan-set QA linter — a sellable tool independent of AI drafting.
- *Env-vendor conversations*: labs and environment vendors are actively buying domain environments; a working roadway env built by a PE is a rare object.
- *GUI-parity mode*: the web UI skinned like C3D/ORD (section 4) so computer-use agents can practice the click-path versions of the same tasks.

---

## 8. Staged goals — what to open, what to keep internal

Per "both, staged" and keeping the thinking internal:

- **Open**: the environment harness, D1 task generator, a *subset* of the rubric, the leaderboard, the writeup. Enough to be credible, runnable, and citable in interviews.
- **Internal (Denison Systems)**: the full drafting spec, the complete verifier depth, D3/D4 generators, and the QA-linter packaging. This is the open-core split — the public artifact markets the private depth.
- Portfolio narrative: **EKG = teaching AI to *know* AEC; RoadDraft = teaching AI to *do* AEC — and measuring both.** Together they are your positioning sentence made concrete: *"I ship AI into a domain almost nobody in AI understands, and I measure whether it actually works."*

---

## 9. Risks & guardrails

| Risk | Guardrail |
|------|-----------|
| Spec creep (the drafting spec could absorb months) | Freeze v1 at ~25–40 checks; version everything after |
| IP / employment hygiene | Own time, own hardware, procedural + public data only (USGS 3DEP, published DOT manuals, public as-builts). Nothing from employer or client project files. Check your employment agreement's IP clause before Phase 0. |
| Reward hacking | Anchor verification + overlap detection + hard fails on wrong values |
| DXF edge cases | Semantic JSON is the source of truth; DXF is only a render |
| Program-agnostic drift | Rule: zero CAD-program imports in core packages; adapters at edges only |
| Time vs. EKG | Phases sized small; Phase 3 is a legitimate stopping point, not a failure |
| Over-building the app before an agent ever plays | Vertical-slice rule (section 5.5): M0→M2 on D1 tasks only, one agent scoring end-to-end, then widen |

---

## 10. Success criteria

- **v0.1 (6 weeks):** 50+ reproducible tasks, 3+ frontier models on a public leaderboard, writeup published with one headline number ("best model scores X/100 on a basic plan sheet").
- **Signals worth watching after:** inbound from labs/env vendors/AEC firms, repo engagement, and — the actual goal — interview conversations that reference it.

---

## 11. Key resources

- LandXML: [mac999/landxml_parser](https://github.com/mac999/landxml_parser) (or roll a minimal subset)
- [ezdxf](https://github.com/mozman/ezdxf) — DXF generation/parsing
- [Prime Intellect Environments Hub](https://www.primeintellect.ai/blog/environments) + `verifiers` format
- [Text2CAD-Bench](https://arxiv.org/abs/2605.18430) — the mechanical-CAD analog; steal its metric structure
- Example machine-readable-friendly CADD standard: [SCDOT Civil 3D 2026 manual](https://www.scdot.org/content/dam/scdot-legacy/business/pdf/cadd/2026%20Civil%203D%20Manual%20Draft%2020260227.pdf); Caltrans HDM + CADD standards for the spec
- Interop later: [IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell) (IFC 4.3 alignments), [ASAM OpenDRIVE](https://www.asam.net/standards/detail/opendrive/)
- Market context: [TechCrunch on the RL environments land grab](https://techcrunch.com/2025/09/21/silicon-valley-bets-big-on-environments-to-train-ai-agents/), [RL environment vendor directory](https://www.rl-list.com/)

---

## 12. Immediate next actions

1. Decide the real name (RoadDraft is a placeholder).
2. Check employment agreement IP clause.
3. Phase 0: draft the drafting spec — start by listing, from memory, every annotation a Caltrans-style plan & profile sheet must carry. That list *is* the product.
4. Scaffold the repo around the command bus (section 5) — it's the decision everything else hangs off.
