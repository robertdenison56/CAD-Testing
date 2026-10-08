# RoadDraft — Research Plan

**Benchmarking and training LLMs on 2D drafting software, through MCP**
Robert Denison, PE · PRD v2 · October 6, 2026
Supersedes the v1 build plan of August 2, 2026 (in git history through `5d4ab4a`). The filename is kept so links hold; references elsewhere to v1 sections (§4, §5.1, §5.4, §8, M2 to M5) resolve through §6 below.
Companions: [RoadDraft_Eval_Plan.md](RoadDraft_Eval_Plan.md) (the scored verifier and harness, September 4), [docs/Probes_Tier2_Proposal.md](docs/Probes_Tier2_Proposal.md), [docs/Probes_Tier3_Proposal.md](docs/Probes_Tier3_Proposal.md), and [benchmarks/probe_runs/README.md](benchmarks/probe_runs/README.md) (every model run so far).

---

## 0. What changed from v1

v1 was a plan to build an RL environment for roadway drafting. The application it called for now exists: a headless 2D CAD engine with a command bus, an MCP server exposing 78 tools, a design model, a D1 task generator with reference solutions, 33 capability probes whose references are kept as finished drawings, and seven runs across four models. What v1 did not say is what the research is.

v2 frames the project as a research program with three questions, and the app as the instrument that answers them:

1. **Measure.** How well do LLMs operate a real 2D drafting program through MCP, and where exactly do they fail?
2. **Rank.** Put every model, frontier and local, through the same tool surface and the same scorer, and publish a leaderboard that reproduces.
3. **Train.** Use the app's own output (reference trajectories, verified rollouts, expert sessions, the verifier as a reward) to fine-tune open models, and measure the climb on the same leaderboard.

The engine is no longer the deliverable; the measurements and the trained models are. Engine work continues only where a probe, a verifier check or a training loop needs it.

---

## 1. Research statement

**Claim under test.** Drafting is a tool-use task with computable ground truth. Every number on a roadway plan sheet derives from the design, and every placement follows a published convention. That makes it a benchmark where right and wrong are decided from the drawing on disk rather than by a judge, and a training environment whose reward cannot be argued with. No such benchmark exists for drafting; the mechanical text-to-CAD benchmarks score geometry, not the use of a drafting program.

**Research questions and hypotheses**

| | Question | Hypothesis | Evidence so far |
|---|---|---|---|
| RQ1 | Can an LLM, given only an MCP tool surface, locate, draft and annotate correctly in a 2D CAD program? | Frontier models can; smaller models fail on specific, nameable skills rather than uniformly. | Fable 17/17, Haiku 14/17, gpt-oss:120b 12 to 15 of 17, Qwen3.5-9B 11/17; each miss names a skill (§2.2). |
| RQ2 | Does a probe-and-verifier benchmark rank models stably and discriminate between them? | Yes: tiers saturate for strong models and discriminate for the rest, so a tiered score orders the field. | The T2 find-probes are saturated (a 9B model scores 8/9); T1, Tier 2 and Tier 3 spread the models. |
| RQ3 | Does fine-tuning on the app's own trajectories and rewards raise a small open model's rank, and does the gain hold on held-out tasks and renamed tool surfaces? | SFT on reference trajectories closes the schema and convention gaps; RL with the verifier closes the arithmetic and scope gaps; a dialect skin exposes tool memorisation. | Untested. No training code exists yet. |

**What is novel.**

- A tool-use benchmark on a real application, scored deterministically from the saved document, where the report the model gives is checked against the file it left.
- A training environment whose expert demonstrations are generated with the tasks, because the generator knows the truth.
- The dialect transfer gap: the same tasks through neutral, Civil 3D-style and ORD-style tool names, which separates "learned drafting" from "memorised a schema".
- Domain knowledge encoded as checks by a licensed PE, each cited to a page of the Caltrans Plans Preparation Manual.

---

## 2. Where the project stands (October 6, 2026)

### 2.1 The instrument that exists

| Component | State | Where |
|---|---|---|
| CAD engine | 787 tests. Model space and sheets, layers, blocks, viewports, references, dimensions, a design model (alignments, profiles, station equations, anchors), DXF, PDF, PNG and LandXML out. | `src/roaddraft/{core,document,design,commands,render,adapters}` |
| Command bus | Every mutation is a validated JSON command: atomic, journaled, undoable, replayable; faults return teaching errors; the bus stamps anchor provenance. | `commands/bus.py` |
| MCP server | `roaddraft-mcp`: 78 tools (45 commands, 32 queries, `open_document`) from one manifest; `--autosave`, `--trace`, `--only` / `--exclude`; `--config CLIENT [--write]` registers it with Claude Code (the project `.mcp.json`), Claude Desktop, LM Studio, Codex, Cursor or VS Code. Stdlib JSON-RPC on Python 3.9. | `mcp/server.py`, `mcp/config.py` |
| Probes | 33 pass/fail tasks in three tiers (9 find, 8 draft, 6 Tier 2, 10 Tier 3), each with a scripted solve that passes its own check, an untouched start that fails it, and tests (Tier 2 and 3 with trap tests that prove each trap fails). References kept as finished projects with journal, PDF and DXF. | `probes/`, `benchmarks/probe_references/` |
| Task generator | D1 plan-sheet tasks from a seed, with brief, ground truth and a reference solution that replays; draft spec v1 ("Caltrans-flavored but genericized") of 11 weighted checks. | `tasks/` |
| Knowledge base | The Caltrans PPM indexed by page, so every spec value and probe convention cites its source. | `benchmarks/knowledge/` |
| Runners | `roaddraft.runners` (Oct 7 2026): one native MCP client with three backends, the Anthropic API, Claude Code headless on a subscription, and any OpenAI-compatible endpoint (LM Studio with its reload guard, Ollama, vLLM); `score` scores from disk and reads the §3.2 measures off the traces. The earlier rigs, a shell bridge (`rd`) for Claude and per-run native clients for Ollama and LM Studio, stay with their runs; `make_deliverables.py` prints every document and reference to PDF with a pass/fail overview. | `runners/`, `benchmarks/probe_runs/<run>/` |
| Human interfaces | Web GUI, terminal REPL and RoadDraft.app on the same bus, so a human session leaves the same journal an agent does. | `web/`, `cli/`, `desktop/`, `scripts/build_app.sh` |

Not built: the scored verifier (`roaddraft.verify`), the eval harness (`roaddraft.eval`), pinned task sets, the leaderboard generator, and any training code. The eval plan specifies the first four as work packages E0 to E6.

### 2.2 Current standings

Seven runs, four models, every score taken from the document the run left on disk. These are capability probes at n = 1, not the scored benchmark, and no model has run every tier.

| Model | Runner | All 17 (9 find + 8 draft) | Tier 2 (6) | Tier 3 batch A (4) |
|---|---|---|---|---|
| Fable 5.1 | shell bridge | 17/17 (Sep 22) | not run | not run |
| Haiku 4.5 | shell bridge | 14/17 (Sep 22: find 7/9, draft 7/8) | 5/6 | 1/4 |
| gpt-oss:120b (cloud) | native MCP client | 12, 12, 15 of 17 over three passes | not run | not run |
| Qwen3.5-9B (local) | native MCP client | 11/17 (find 8/9, draft 3/8) | 0/6 | not run |

What the runs already say, and what v2 turns into measurements:

- **Skills, not models, are the unit of failure.** Draft-probe misses cluster on hand arithmetic (bearing and distance, the COGO gap), width versus offset, stopping an offset at a station, and losing track of one's own entities. Tier 3 batch A misses are lettering conventions: the data was read right every time and the text went in the wrong place or faced the wrong way.
- **Reports and documents disagree.** gpt-oss:120b reported work it had not done (Sep 24); Haiku reported rotated labels that sit at 0° (Oct 6). Scoring from disk is the rule, and the disagreement rate becomes a published column.
- **The first call to a tool usually faults.** Haiku's faults are almost all a missing required property on a tool's first use, fixed on the next call; one loop repeated the same fault 47 times. Schema compliance and recovery are measurable per model.
- **The protocol is not yet uniform.** Claude models see the tools through a shell bridge; open models see them as native function tools. One runner for every vendor comes before any cross-vendor ranking is published.

---

## 3. Method

### 3.1 The loop

```
                 ┌─────────────── model under test ─────────────────┐
                 │  frontier API · hosted open · local (LM Studio,   │
                 │  vLLM, Ollama) · fine-tuned checkpoints (RQ3)     │
                 └───────────────┬──────────────────▲───────────────┘
                  MCP tool calls │                  │ results, faults, renders
                 ┌───────────────▼──────────────────┴───────────────┐
                 │  roaddraft-mcp  (78 tools, one manifest;          │
                 │  a dialect skin is the same tools renamed)        │
                 │  --autosave  → document + journal on disk         │
                 │  --trace     → every call, query and fault        │
                 └───────────────┬──────────────────────────────────┘
                                 │
     ┌───────────────────────────▼────────────────────────────┐
     │  scorer: probe checks (pass/fail) · verifier (0 to 100) │
     │  reads the document from disk, never the report         │
     └──────────┬─────────────────────────────┬────────────────┘
                │ leaderboard (RQ1, RQ2)      │ reward, filtered trajectories (RQ3)
                ▼                             ▼
     benchmarks/runs/<run>/             training data → SFT / RFT / GRPO → checkpoint
                                                               │
                                                               └── served back through the same MCP server
```

Invariants, already in force for the probe runs and carried into everything below:

1. The model under test touches the app only through MCP. Same tools, descriptions and schemas for every model; the only permitted differences are the dialect skin and the mode (text, self-correct, vision).
2. Scores come from the document on disk. The model's report is kept and compared, never scored.
3. Every run folder keeps its rig: runner, prompts, traces, documents, journals, engine commit. A re-score runs against the current checks, which is why the documents are kept and not just the numbers.
4. Every reference solution is a finished drawing that opens in the app, replays from its journal, and passes its own check.
5. Versions are pinned into the record: engine commit, probe set or spec hash, prompt hash, model id, runner.

### 3.2 Measuring MCP use (RQ1)

Each run yields, per model and per task, from `trace.jsonl`:

| Measure | Definition | Why it matters |
|---|---|---|
| Pass, or effective score | the probe check, or the verifier's effective score | the outcome |
| Invalid-call rate | schema faults / calls | whether the model reads a JSON Schema before its first call |
| Fault recovery | faults followed within 3 calls by a successful call of the same tool | whether it learns from the teaching error |
| Repeated-fault loops | the same fault made 5 or more times in a row | the Haiku stationing case |
| Query before compute | design queries used where arithmetic was needed (`station_to_xy`, `get_design_data`, `measure`) versus hand calculation | the COGO gap is a tool-use gap as much as a reasoning one |
| Report fidelity | claims in the final report that the document contradicts | fabricated completion |
| Steps, wall clock, tokens, cost | per task | the price of a sheet |
| Render use | `render_sheet` calls, and whether a fix followed | whether looking helps |
| Scope completion | items done / items asked on multi-sheet tasks | stopping early |

These are the columns of the model card that accompanies every leaderboard row.

### 3.3 Ranking (RQ2)

**RoadDraft-Bench** has three tracks. A model's rank is its position on Track D once that track exists, and on Track P until then. Track X qualifies a rank rather than setting it.

| Track | Content | Score | State |
|---|---|---|---|
| P: probes | the 33 probes, three tiers | pass rate over k = 3 attempts, per tier and overall | built; four models partially run |
| D: drafted sheets | the eval plan's `d1-test` set, 100 held-out generated plan sheets | effective score mean ± 95% CI; hard-fail rate; clean-sheet rate | generator built; verifier and harness not |
| X: transfer | Track P and D tasks through the `c3d` and `ord` dialect skins, and in vision mode | transfer gap = neutral − skin, paired by task | aliases exist on every command; skins not wired |

Ranking rules:

- Same prompt, same tool surface, same budgets (steps, wall clock, tokens) for every model. The no-calculator rule holds: the app's queries are the only arithmetic allowed.
- k ≥ 3 attempts per task. The Sep 22 rerun moved Haiku's draft score by three probes with no change to the reasoning; n = 1 says which traps a model falls into, not how often.
- Ties on score break on hard-fail rate, then invalid-call rate, then cost per task.
- Attempts ended by infrastructure are recorded and excluded; attempts ended by budget count as failures.
- Model classes run side by side: frontier API models, hosted open-weight models, local small models, and the RQ3 checkpoints. The leaderboard marks the class and the runner for each row.
- The leaderboard file is generated from the run folders, never edited by hand.

### 3.4 Training (RQ3)

**Subject model.** Qwen3.5-9B: the weakest model measured (11/17, 0/6), it runs locally and is small enough for LoRA on one rented GPU. A second subject in the 30B class follows if the first climbs.

**Data the app produces**, all in the trace format the server writes (`--trace`: one line per call, with the result the agent was shown), converted to tool-calling conversations by `roaddraft.trajectories convert`:

| Source | How it is made | What it teaches |
|---|---|---|
| Reference trajectories | every probe family instance's scripted solve and every generated D1 task's reference solution, recorded under `roaddraft.trajectories` so the queries are captured and not just the commands, and marked *faithful* only when the solve read nothing except through the tool surface (`benchmarks/trajectories/`) | the schema, the semantic path (anchors, queries), the conventions, and the arithmetic the solve says as it goes |
| Verified rollouts | k samples per task from a strong model (Fable, Haiku) and from the subject itself; only those the scorer passes are kept (a rig's run folders convert with `convert --runs`, the document each left scored on the way) | the subject's own successful behaviour, and distillation from the stronger model |
| Fault-and-recovery pairs | mined from traces: a schema fault, the teaching error, the corrected call | first-call compliance |
| Expert sessions | the PE drafts through RoadDraft.app or the GUI; the journal is the trajectory (the eval plan's human playtest, kept under `benchmarks/expert/`) | how a drafter actually works |

Generated tasks are unlimited and carry their own truth, so training data costs compute, not labelling.

**Stages**, each measured on the same leaderboard before the next starts:

| Stage | Method | Question it answers |
|---|---|---|
| T0 | prompt only: the lettering conventions and tool guidance in the system prompt, no weights changed | how much of the gap is knowledge the model was never given |
| T1 | SFT (LoRA) on reference trajectories and fault-and-recovery pairs | whether imitation closes the schema and convention gaps |
| T2 | rejection-sampling fine-tuning: sample, score, keep the passes, retrain; two or three rounds | whether the subject learns from its own verified successes |
| T3 | GRPO with the verifier as reward through the eval plan's Gymnasium adapter (terminal reward = effective score / 100; probe reward = pass), with TRL or `verifiers` | whether RL closes the gaps imitation did not: arithmetic, scope, restraint |

**Held-out evaluation.** The 33 fixed probes and the `d1-test` seeds are the test and stay out of every training set. Training draws on `d1-dev` seeds and on probe families (`probes/families.py`): the same kinds of task with their particulars drawn from a seed, built so that no instance repeats a fixed probe. Every stage also runs Track X: a checkpoint whose transfer gap widens has memorised tool names, not drafting.

**Serving.** Checkpoints are served through an OpenAI-compatible endpoint (vLLM, or LM Studio for GGUF conversions) and driven by the same native MCP client as every other open model, so a trained model's leaderboard row is produced exactly as a base model's is.

**Anti-reward-hacking**, carried from the eval plan §3.5: anchors required for label credit, anchor consistency recomputed from the design, bus-stamped provenance, the design fingerprint precondition, no truth leaking through `run_check`, duplicates counted once. Probe checks judge geometry and text as plotted, never vocabulary, so an alternate correct route passes and a decorated wrong one fails.

---

## 4. Program

Each phase ends shippable. Targets assume the existing pace of about 8 to 10 hours a week.

| Phase | Scope | Deliverable | Target |
|---|---|---|---|
| **A. Close Track P** | Fable on Tier 2 and Tier 3 batch A; batch B and C runs; one native MCP runner for Anthropic, OpenAI-compatible and local endpoints, replacing the shell bridge (built Oct 7 2026, `roaddraft.runners`, with a Claude Code headless backend for runs on a subscription; no model has run through it yet); k = 3 reruns of all 33 probes on all four models; the §3.2 measures computed from traces; the leaderboard generated from run folders | RoadDraft-Bench v0.1: probe leaderboard, four or more models, model cards | October 2026 |
| **B. Track D** | eval plan E0 to E4: finish Phase 1, build `roaddraft.verify` and `roaddraft.eval`, freeze spec v1 after PE review, pin `d1-dev` and `d1-test`, run the leaderboard set | the headline number, best model X/100, with CI and failure taxonomy | November 2026 |
| **C. Training data and SFT** | trace-to-conversation converter (built Oct 6 2026: `roaddraft.trajectories convert`, and the 33 solves recorded through the server with tracing on); reference trajectories for every probe and 500+ generated tasks; T0 and T1 on Qwen3.5-9B; re-rank | the first trained checkpoint on the leaderboard, with its delta and transfer gap | December 2026 |
| **D. RFT and RL** | T2 and T3 through the Gymnasium adapter; Track X on every checkpoint | a measured reward curve and a ranked checkpoint | January 2027 |
| **E. Publish** | writeup, public leaderboard, trajectory dataset and checkpoints on Hugging Face, environment listings (Prime Intellect hub, `verifiers`, Inspect) | the paper and the artefacts | February 2027 |

Phases B and C are independent once A has produced the runner, so they can interleave. The engine changes only when a probe, check or training loop needs it, and every such change is recorded in the run that motivated it, as the Tier 3 lettering fixes were.

---

## 5. Deliverables and success criteria

| RQ | Done when |
|---|---|
| RQ1 measure | every model on the leaderboard has a model card with the §3.2 measures, computed from traces, at k ≥ 3 |
| RQ2 rank | Track P covers four or more models across all 33 probes at k = 3; Track D reports best model X/100 with a CI half-width under 5 points; the ordering is stable across k |
| RQ3 train | a fine-tuned checkpoint beats its base on held-out Tier 2, Tier 3 and `d1-test` with non-overlapping CIs, without widening its transfer gap; the data and recipe reproduce from the repo |

Secondary signals: inbound from labs, environment vendors and AEC firms; the probe set adopted by anyone else; and the verifier pointed at human-drawn sheets as a QA tool (the v1 product probe, unchanged).

---

## 6. Retained from v1

These decisions stand and are not repeated here. v1 section numbers are listed for the references in the eval plan and the README.

| v1 | Decision | Where it lives now |
|---|---|---|
| §3, §5.1 | the command bus as action space, trajectory and replay; zero CAD-program imports in core | `README.md`, `commands/bus.py` |
| §4 | one ontology with Civil 3D and ORD dialects; the transfer gap as a headline metric | every command's `c3d` / `ord` aliases; Track X |
| §5.2 | text-first, a diff and warnings on every action, teaching errors, anchors not coordinates, a `run_check` budget | the engine; eval plan §4 |
| §5.4 | human-play mode: if a PE cannot score 100 through the tools, the tools are wrong | GUI, REPL, RoadDraft.app; the eval plan's human playtest |
| M2 to M5 | verifier, harness, dialect skins, RL mode | eval plan E0 to E6 |
| §8 | open-core: harness, D1 generator, probes and leaderboard public; full spec depth, D3/D4 generators and the QA linter internal | unchanged |
| §9 | IP hygiene: own time, own hardware, procedural and public data only; no employer or client files | unchanged |
| §6 | the D2 to D5 curriculum (profiles, multi-sheet sets, redlines, dialect transfer) | deferred; Tier 2 and 3 already cover redlines (`draft-fix-the-drawing`, `qa-alignment-data`) and multi-sheet scope |

---

## 7. Risks and guardrails

| Risk | Guardrail |
|---|---|
| Rankings compared across different runners | Phase A's single native MCP client before any cross-vendor table is published |
| n = 1 noise | k = 3 minimum; paired comparisons; bootstrap CIs; an ordering is reported only where the CIs separate |
| Reward hacking in training | the eval plan §3.5 layer; mutation and hack probes pass before any reward is computed; a journal audit per episode |
| Contamination | held-out seeds and tiers never enter a training set; task ids carry the spec hash, so a changed spec mints new ids |
| Tool memorisation masquerading as skill | Track X on every checkpoint |
| Cost | lean runner agents, cached prefixes, `--budget` on local models, a cost cap per run; the Sep 20 draft run's $27 in 20 minutes came mostly from orchestrator overhead, not the models |
| The spec is DRAFT | PE review and freeze before Track D publishes; the knowledge base cites every value to a PPM page |
| Fabricated completion | report fidelity as a published column; the disk is the only scorer |
| Time | each phase ships on its own; Phase A alone is a publishable benchmark |

---

## 8. Immediate next actions

1. Run Fable on Tier 2 and Tier 3 batch A through the existing rig, so the batch-A ceiling is measured before batch C runs.
2. Rerun the 33 probes at k = 3 on all four models through `roaddraft.runners` (built Oct 7 2026): Claude on the `claude-code` backend with a signed-in CLI until an API key is warranted, the open models on `openai`.
3. Generate the Track P leaderboard and model cards from the run folders; commit the Oct 6 run with them.
4. Start the eval plan's E0 (finish Phase 1) and E1 (verifier) for Track D.
5. Grow the probe families (callouts by entity, turn lanes, curb returns, lettering) and record the first few hundred instances; rehydrate the passing episodes of the seven runs as verified rollouts.
