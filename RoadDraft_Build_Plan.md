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

## 2. Where the project stands (October 15, 2026)

### 2.1 The instrument that exists

| Component | State | Where |
|---|---|---|
| CAD engine | 1,397 tests. Model space and sheets, layers, blocks, viewports, references, dimensions, a design model (alignments, profiles, station equations, anchors), DXF, PDF, PNG and LandXML out. Since Oct 9: COGO input (bearing and distance, traverses), the modify toolbox (trim, extend, break, join, fillet, chamfer, offset, copy, rotate, mirror, scale, array), COGO points and tables, segment labels, hatching; labelers that letter to the PPM by default and through a referenced base drawing, with `view_rotation` for a twisted viewport. | `src/roaddraft/{core,document,design,commands,render,adapters}` |
| Command bus | Every mutation is a validated JSON command: atomic, journaled, undoable, replayable; faults return teaching errors; the bus stamps anchor provenance. | `commands/bus.py` |
| MCP server | `roaddraft-mcp`: 103 tools (66 commands, 36 queries, `open_document`) from one manifest, 78 before the Oct 9 drafting-tools merge; `--autosave`, `--trace`, `--only` / `--exclude`; `--config CLIENT [--write]` registers it with Claude Code (the project `.mcp.json`), Claude Desktop, LM Studio, Codex, Cursor or VS Code. Stdlib JSON-RPC on Python 3.9. Since Oct 14 (fe26ce2) the tool descriptions' examples, hints and errors refer to a drawing of their own, not to the probe fixtures (tools `sha256:60eeeb21`, instructions `sha256:4dff2849`). | `mcp/server.py`, `mcp/config.py` |
| Probes | 33 pass/fail tasks in three tiers (9 find, 8 draft, 6 Tier 2, 10 Tier 3), each with a scripted solve that passes its own check, an untouched start that fails it, and tests (Tier 2 and 3 with trap tests that prove each trap fails). References kept as finished projects with journal, PDF and DXF. Since Oct 12 the fixtures sit on Caltrans named levels and the checks read the PPM's lettering, the same conventions as the verifier (§4, one convention set); the checks also count items done of items asked. | `probes/`, `benchmarks/probe_references/` |
| Task generator | D1 tasks from a seed, with brief, ground truth and a reference solution that replays: 16 seeded task types (the phases of a layout sheet from `draw-alignment` to `plan-sheet`, the plan-prep types, `create-alignment`, `annotate-base`), on 1 or 2 sheets, each posed at an explicit and a vague prompt level over one truth; 11 `real-*` types on the redrafted sample sheets (584 tasks in `benchmarks/real_tasks/catalog.json`). Spec `draft-v4` (checks D1-00 to D1-15, plan scales 1" = 40' and 50'), generator `d1-v5`; manifests `d1-dev` (50), `d1-test` (100, held out), `d1-variance` (20 of `d1-test`). | `tasks/`, `benchmarks/tasksets/` |
| Verifier | `roaddraft.verify` (E1, Oct 10 to 14, `d1-verify-v3`): the effective score 0 to 100 from the document on disk over the checks the task's scope drives, renormalised to 100; labels match by anchor and hand-rewritten anchors never match; legibility in paper space; the anti-reward-hacking layer; reference = 100 and start = 0 for every type, sheet count and prompt level; 34 mutations and 11 hack probes; p95 under 50 ms. Eval plan §3.8. | `verify/`, `tests/test_verify_*.py` |
| Harness | `roaddraft.eval` (E2 to E4, Oct 14 to 15, `e3-v1`): the episode loop with budgets and the D1 whitelist; `oracle`, `null`, `scripted` and `replay` agents (oracle 50/50 = 100 on `d1-dev`, scripted 37.75, null 0); LLM agents through `anthropic`, `openai`-compatible and `fake` providers with the `c3d` and `ord` dialect skins, a dated price table and `--cost-cap`; `report` writes the run's leaderboard, taxonomy and paired gaps, `--publish` copies to `benchmarks/runs/`, `scripts/make_leaderboard.py` the Track D board (no ranked run yet). The live E3 smoke run has not run. Eval plan §4.10. | `eval/`, `benchmarks/runs/`, `scripts/make_leaderboard.py` |
| Knowledge base | The Caltrans PPM indexed by page, so every spec value and probe convention cites its source; the CADD Users Manual beside it (Oct 11). | `benchmarks/knowledge/` |
| Runners | `roaddraft.runners` (Oct 7 2026): one native MCP client with four backends, the Anthropic API (unrun), Claude Code headless on a subscription, Codex headless on a subscription (Oct 13), and any OpenAI-compatible endpoint (LM Studio with its reload guard, Ollama, vLLM, Runpod); `score` scores from disk and reads the §3.2 measures off the traces, `claims` reads each report against the document, `leaderboard` writes Track P. The earlier rigs, a shell bridge (`rd`) for Claude and per-run native clients for Ollama and LM Studio, stay with their runs; `make_deliverables.py` prints every document and reference to PDF with a pass/fail overview. | `runners/`, `benchmarks/probe_runs/<run>/`, `benchmarks/leaderboard/` |
| Trajectories | `roaddraft.trajectories record` and `convert` (Oct 6): a server trace becomes a tool-calling conversation, audited faithful only when the solve read nothing except through the tool surface. The 33 probe solves recorded (33 pass, 21 faithful) and 3 probe families with 10 instances each; both on the Oct 12 tool surface (`sha256:97c51a`), before the help-text change. | `trajectories/`, `benchmarks/trajectories/` |
| Sample sheets | The PPM, FDOT, CFL and WFL sample plan sets split one sheet to a PDF (`Sheets/manifest.csv`) and redrafted as RoadDraft file sets under each agency's naming and title block (Oct 9 to 11); the `real-*` tasks start from these sheets with their real base files. | `examples/Exmple Plans/` |
| Human interfaces | Web GUI, terminal REPL and RoadDraft.app on the same bus, so a human session leaves the same journal an agent does. | `web/`, `cli/`, `desktop/`, `scripts/build_app.sh` |

Not built: the Track D runs (E4's `d1-variance` and `d1-test` wait on the E3 smoke run and the spec v1 freeze), the Track X runs (E5; the skins exist), the Gymnasium, `verifiers` and Inspect adapters (E6), and any training code. The Track P leaderboard is generated (`python -m roaddraft.runners leaderboard`, `benchmarks/leaderboard/`); Track D's generator exists and has no ranked run.

### 2.2 Current standings

Track P at k = 3: seven models, all 33 probes, every model through `roaddraft.runners`, every episode re-scored from the document it left on disk (`benchmarks/probe_runs/2026-10-12-k3`, probe set `sha256:2fce3b5c1c75`; the board is `benchmarks/leaderboard/TRACK_P.md`, generated, with a card per row).

| Rank | Model | Class · backend | Pass rate [95% CI] | T1 (17) | T2 (6) | T3 (10) | Hard-fail | Invalid calls | Cost / task |
|---|---|---|---|---|---|---|---|---|---|
| 1 | GPT-6-Astra (medium) | frontier API · Codex headless | 96.0% [87.9, 100.0] | 100% | 94% | 90% | 1/33 | 0.4% | subscription |
| 2 | Claude Sonnet 5.5 | frontier API · Claude Code headless | 96.0% [87.9, 100.0] | 100% | 100% | 87% | 1/33 | 2.0% | $0.10 |
| 3 | Claude Fable 5.1 | frontier API · Claude Code headless | 89.9% [79.8, 98.0] | 100% | 83% | 77% | 2/33 | 1.0% | $1.37 |
| 4 | Claude Haiku 4.5 | frontier API · Claude Code headless | 74.7% [60.6, 86.9] | 96% | 67% | 43% | 5/33 | 4.2% | $0.11 |
| 5 | GPT-6-Luna (medium) | frontier API · Codex headless | 66.7% [52.5, 80.8] | 90% | 50% | 37% | 6/33 | 5.0% | subscription |
| 6 | Qwen3.5-9B (bf16, vLLM) | hosted open-weight · Runpod | 47.5% [32.3, 63.6] | 78% | 17% | 13% | 12/33 | 6.7% | $4.22 billed for the run |
| 7 | Gemma 4 E4B | local small · LM Studio | 29.3% [16.2, 44.4] | 57% | 0% | 0% | 20/33 | 47.7% | local |

Read with these caveats, all of them on the board and the cards:

- **Every row ran on the earlier help text.** Until fe26ce2 (Oct 14) the server's instructions and the tool descriptions' examples carried values from the probe fixtures, so the surface could prompt a probe's answer. The scrubbed surface (tools `sha256:60eeeb21`, instructions `sha256:4dff2849`) has no ranked row yet; whether the seven rows are rerun on it is open (§8).
- **The top two are a tie.** Astra and Sonnet share the rate and the hard fail; Astra leads on the next tie-break, invalid calls. Every neighbouring pair's intervals overlap, so no adjacent ordering is separated; the intervals separate only rows further apart, such as Sonnet from Haiku and Luna from Gemma.
- **Fable's rank is the spend cap's, not the drawing's.** On disk Fable passes 96 of 99 (everything but `l2-alignment-data`, all three times); seven passing episodes ended on the $3 CLI cap, which the board counts as failures. Without the cap it would read 97.0%, above Sonnet. Raising the cap and rerunning the seven is open (§8).
- **Two tool surfaces.** Haiku and Sonnet ran on the Oct 12 surface (`97c51a`), and Gemma's pins say the same though 82 of its 99 episodes were served the next one (another session's edit under the run); Fable, the GPT-6 rows and Qwen ran on the one with `view_rotation` (`20fe0603`). The argument was never passed by Astra or Fable and decided nothing for Luna (the Oct 15 RESULTS note).
- **One probe nobody passes:** `l2-alignment-data`, the whole-job Tier 3 probe on the Caltrans L-2 sheet with its turned viewport.

What the k = 3 campaign says, and what §3.2 now measures:

- **Skills, not models, are the unit of failure.** The top rows lose almost nowhere but the turned L-2 sheet; Haiku's misses are the full PPM forms (`line-data`, `curve-data`, the bubbles), the redline edit and the L-2 sheet; Luna's are leaders, the sheet number in the title block and the same forms; Qwen's are guessed layers, anchors on alignments the sheet does not own and a full context; Gemma's are the schema itself. Haiku's climb from the Oct 8 row (21, 20, 17) to 23, 27, 24 is mostly the engine's: the labelers now default to the PPM's forms, so a model that takes the default route matches without knowing the convention.
- **Reports and documents disagree, and it is a column now.** `roaddraft.runners.claims` reads each report's completion, clean-run and entity-id claims against the document and the trace without a model (125 of 133 failed episodes agree with hand labels, 84 of 86 held out). Luna's reports said the task was done on 20 of its 33 failed episodes; Astra's on all four of its failures.
- **Invalid calls run from 0.4% to 47.7%.** Astra 0.4%, Fable 1.0%, Sonnet 2.0%, Haiku 4.2%, Luna 5.0%, Qwen 6.7%, Gemma 47.7%: half of Gemma's calls are the engine teaching it the schema, and on the probes beyond Tier 1 it never reaches the drawing. The Oct 8 Haiku row had 6.4%; the fall to 4.2% is the labelers accepting the referenced-alignment names the models reach for.
- **The protocol is uniform.** One runner, four backends, the server's instructions as the whole system prompt, 120 turns and 15 minutes a probe (30 for the local and hosted open models); the subscription rows carry no price. Codex shows the model tool results under its own output limit rather than the runner's 30,000 characters; the run's RESULTS records that difference.

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
                 │  roaddraft-mcp  (103 tools, one manifest;         │
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
| P: probes | the 33 probes, three tiers | pass rate over k = 3 attempts, per tier and overall | built; seven models ranked at k = 3 (§2.2) |
| D: drafted sheets | the eval plan's `d1-test` set, 100 held-out generated plan sheets | effective score mean ± 95% CI; hard-fail rate; clean-sheet rate | generator, verifier and harness built; no ranked run (the spec is `draft-v4`; the E3 smoke run and the freeze come first) |
| X: transfer | Track P and D tasks through the `c3d` and `ord` dialect skins, and in vision mode | transfer gap = neutral − skin, paired by task | aliases exist on every command; the skins are wired in `roaddraft.eval` (43 and 37 commands renamed); no transfer run yet |

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
| **A. Close Track P** | Fable on Tier 2 and Tier 3 batch A (Oct 7, 10/10); batch B and C runs (Oct 7 to 8, the local models 0/24); one native MCP runner for Anthropic, OpenAI-compatible and local endpoints, replacing the shell bridge (built Oct 7 2026, `roaddraft.runners`; Claude Code headless Oct 8 and Codex headless Oct 13, both on a subscription); k = 3 reruns of all 33 probes (done Oct 12 to 14 for seven models, `2026-10-12-k3`); the §3.2 measures computed from traces (built Oct 8 2026; report fidelity and scope completion added Oct 13 2026: the probe checks count items done of items asked, and `roaddraft.runners.claims` reads each report's completion, clean-run and entity-id claims against the document and the trace without a model, agreeing with hand labels on 125 of 133 failed episodes and on 84 of 86 held out); the leaderboard generated from run folders (built Oct 8 2026: `python -m roaddraft.runners leaderboard`; seven rows ranked at 3010183, Oct 14). Open: the three decisions in §8 (the clean-surface rerun, Fable's cap, gpt-oss). | RoadDraft-Bench v0.1: probe leaderboard, four or more models, model cards | October 2026: the deliverable exists (§2.2), every row with the help-text caveat |
| **B. Track D** | eval plan E0 to E4: E0 finished Sep 10 (6df5252, 029658e; re-verified Oct 13); E1 `roaddraft.verify` built Oct 10 to 14 (295e6ea, dec3aa0, 2697ee5, 6bf396e, d4cee1f: spec `draft-v4`, `d1-verify-v3`, 16 seeded and 11 real-sheet task types); E2 `roaddraft.eval` Oct 14 (70e4280: oracle 50/50 = 100, scripted 37.75, null 0); E3 LLM agents and E4 run report Oct 14 to 15 (a4e6a0e; the fake oracle scores 100 in all three dialects). Left: the one generator fix, then the spec v1 freeze after PE review (every §3.7 decision is in); the E3 smoke run; the human playtest; `d1-variance` × 5, then `d1-test` × three or more models | the headline number, best model X/100, with CI and failure taxonomy | November 2026 |
| **C. Training data and SFT** | trace-to-conversation converter (built Oct 6 2026: `roaddraft.trajectories convert`, and the 33 solves recorded through the server with tracing on: 33 pass, 21 faithful; 3 families × 10 instances; all recorded on the Oct 12 tool surface, to re-record on the current one); reference trajectories for every probe and 500+ generated tasks; T0 and T1 on Qwen3.5-9B; re-rank | the first trained checkpoint on the leaderboard, with its delta and transfer gap | December 2026 |
| **D. RFT and RL** | T2 and T3 through the Gymnasium adapter; Track X on every checkpoint | a measured reward curve and a ranked checkpoint | January 2027 |
| **E. Publish** | writeup, public leaderboard, trajectory dataset and checkpoints on Hugging Face, environment listings (Prime Intellect hub, `verifiers`, Inspect) | the paper and the artefacts | February 2027 |

Phases B and C are independent once A has produced the runner, so they can interleave. The engine changes only when a probe, check or training loop needs it, and every such change is recorded in the run that motivated it, as the Tier 3 lettering fixes were.

**One convention set (2026-10-11).** Track P and Track D share the lettering conventions (the PPM's: Caltrans station numbers below the line, `24+05.27 BC` square to the line, bearing and length above the tangent, curve numbers in bubbles, the No./R/Δ/T/L table), the credit route (the engine's anchored labelers, which now work through a referenced base drawing; the Tier 3 solutions and the new `annotate-base` task type both letter that way) and the layer names (Caltrans named levels in the probe fixtures as in the spec). Spec `draft-v2`, generator `d1-v4`, verifier `d1-verify-v3` at the time; since then `draft-v3` and `draft-v4` (Oct 12 to 13) set the plan scales to 1" = 40' and 50' and the generator is `d1-v5`; eval plan §3.8 has the detail. A rank that moves from Track P to Track D, a training set drawn from both, and a T0 convention sheet all depend on this.

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

1. The E3 smoke run, `d1-dev[:5]` × one model × single. It needs a model and a route (this machine has no `ANTHROPIC_API_KEY`; the `openai` provider reaches LM Studio or the Runpod endpoint); it replaces the eval plan's §8 estimate with measured cost, steps and invalid-call rate per sheet.
2. The generator fix, then the spec v1 freeze: the width dimension line through the bearing text on pavement sheets is the one flaw that would move frozen ids again; then `draft-v4` → `v1` (the DRAFT status and its two tests, the standards table's own status), regenerate the fixtures, the prompt workbook, the real-task catalog and the three manifests. Every PE decision is in.
3. Track P decisions, Robert's: (a) rerun the seven rows on the scrubbed help text (fe26ce2), or publish v0.1 with the caveat; (b) Fable's $3 CLI cap: raise it (say `--max-budget-usd 6`) and `--force` the seven capped episodes (about $30, one 5-hour window), or keep the cap as part of the rig; (c) gpt-oss:120b on Ollama cloud ($0 to $20), the one Oct 6 model without a k = 3 row. Regenerate the board after each.
4. Track D: `d1-variance` × 5 samples to size the interval, then `d1-test` × three or more models × {single, self-correct}; `report --publish`, `make_leaderboard.py`, and the writeup draft from the taxonomy table. The human playtest (`python -m roaddraft.eval human start`, record under `benchmarks/expert/`) is E2's last acceptance item and does not block the runs.
5. Training data: re-record the 33 probe solves and the family instances on the current tool surface (`60eeeb21` / `4dff2849`), make the 12 unfaithful solves faithful, grow the families, and rehydrate the passing episodes of the k = 3 runs as verified rollouts.
