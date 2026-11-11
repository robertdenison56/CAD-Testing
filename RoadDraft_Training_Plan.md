# RoadDraft training plan: Phases C and D (drafted 2026-11-10)

Robert, Nov 10: "review the repo and plan out the training phase. suggest first steps to get going." This file
plans RQ3 (`RoadDraft_Build_Plan.md` §3.4 and §4: stages T0 to T3) against the repo as it stands at main
`980f5cef`. Companions: `RoadDraft_Cost_Plan.md` Stage 7, `benchmarks/RERUN_PLAN.md` ("Why each model fails"),
`benchmarks/runs/FAILURE_CAUSES.md`. Nothing here is a go for a paid run.

## 1. Where training starts from

**The subject, Qwen3.5-9B** (`Qwen/Qwen3.5-9B`, Apache-2.0, 9.65B parameters, reads images). Its board rows, all
Q4_K_M through LM Studio, k = 1, harness `e3-v3`, tool surface `0334fd4a`, verifier `d1-verify-v8`:

| set | vague (the board's focus) | explicit | best row on the set |
|---|---|---|---|
| `d1-test` | 62.6 [57.7-67.6] | 74.0 | Opus 5.5, 95.5 |
| `d1-real` | 59.6 [54.3-64.6] | 70.8 | Terra, 90.5 |
| `d1-test-hard` | 9.4 [6.4-12.7] | not run | Opus 5.5, 93.7 |
| `d1-real-hard`, `hard-pilots` | in the local queue, due about Nov 15 | 2.7 on the pilots | Opus 5.5, 77.6 and 40.2 |

**Where it loses** (`eval causes`, points a task on the vague rows):

| set | lost | standard not known | reasoning | tool use | budget |
|---|---:|---:|---:|---:|---:|
| `d1-test` | 37.4 | 16.1 (confirmed by the explicit twin) | 16.1 | 5.3 | 0.0 |
| `d1-real` | 40.3 | 11.1 (confirmed) | 22.5 | 6.8 | 0.0 |
| `d1-test-hard` | 90.6 | 56.3 (no twin) | 10.6 | 20.7 | 3.0 |

The largest single items on `d1-test` are all things a reference solution shows: nothing drafted on the right
layer (7.3 points, 2.3 of them lost even when told), submitting an empty drawing (4.0), stationing left off after
`annotate_stationing` failed and was never retried correctly (4.6), lettering through linework (3.3).

**What exists for training.** `roaddraft.trajectories record` and `convert` (probe format only); the 33 probe
solves as conversations (21 faithful) and 3 families of 10 instances, recorded on an older tool surface
(`97c51a`). No training code, no D1 trajectories, no Gymnasium adapter (E6).

## 2. What the review changes in the plan as written

1. **The D1 oracle is not a demonstration yet.** `OracleAgent` replays `solution_commands(task)`: commands only,
   their numbers taken from the generator's truth. The oracle's episode for a curve-table task is two calls,
   `set_meta` and `place_curve_table` at `[28.35, 2.67]`, with no query before either. Trained on as it is, that
   teaches calls whose values come from nowhere the model can see. Tracker steps `c-d1-refs` and `c-faithful` are
   one job: a reference that asks first.
2. **No existing rollout can enter a training set.** Every model run on disk is on a held-out set (`d1-test`,
   `d1-real`, the hard sets, `hard-pilots`, the 33 probes). Build Plan §8 item 5, tracker `c-rollouts` ("rehydrate
   every passing episode") and the Cost Plan's "verified rollouts come from runs already paid for" all need this
   correction: rollouts for training are new runs on training seeds.
3. **There is no clean real-sheet training data.** `d1-real` and `d1-real-hard` between them touch 46 of the
   catalogue's 49 sheets; the other three are the `d1-real-dev` sheets. So training is on seeded tasks only, and
   `d1-real` becomes the transfer test: trained on generated centerlines, tested on agency sheets. That is a
   stronger claim than a mixed set would give. One known gap: no seeded task has a twisted viewport, and 77 of
   `d1-real`'s 100 do.
4. **Track X is gone** (skins dropped Oct 30), and §3.4 still runs it on every checkpoint. Its job, catching a
   checkpoint that memorised instead of learning, passes to `d1-real`, the text pilots and the 33 probes.
5. **A conversation is long before the model says anything.** The system prompt, the 75 tool definitions and the
   task come to about 28,000 tokens. The 9B's episodes end at 32k (median) and 46k (p90) on `d1-test`, 49k and 78k
   on `d1-real`. LoRA at that length needs a 48 to 80 GB card: not the PC's two 16 GB cards, not the Mac (M4,
   16 GB). Training runs on a rented card.
6. **T0 is partly measured already.** The explicit rows tell the model each task's particulars and earn back 11.4
   points on `d1-test` and 11.2 on `d1-real`. T0 proper (one static convention sheet, the vague prompt) should land
   near there; it is still worth running because it is the bar T1 has to clear without the sheet.
7. **Every row is k = 1** (Nov 4 rule), so a delta is read paired by task, not from two intervals. For the Build
   Plan's "non-overlapping CIs" at k = 1 a checkpoint needs roughly 73 or better on `d1-test`.

## 3. Design

**Splits.**

| role | sets | rule |
|---|---|---|
| train | `d1-train`: new seeds 10000-11199, the 16 seeded types; `d1-train-hard`: seeds 12000-12299, the hard whole-sheet types | generated, unlimited; a test asserts no task id, seed or sheet is shared with any other set |
| validation | `d1-dev` (50), `d1-real-dev` (24) | checkpoint selection only; never trained on, never reported |
| test | `d1-test`, `d1-real`, `d1-test-hard`, `d1-real-hard`, `hard-pilots`, the 33 probes | untouched |

**Data, in the order I would build it.**

| source | how | teaches | cost |
|---|---|---|---|
| Grounded references (primary) | the reference solution run phase by phase through the tool surface: the queries that expose each value, a line of shown work, then the command; an audit passes only when every value in a command traces to the task text, an earlier result or a stated rule | standards (what belongs on a sheet, on which layer), the query-first path, correct stationing | Mac CPU |
| Injected faults | take a reference call, break it the way the 9B does (the sub-causes in `report/causes.md`), send it through the bus for the real teaching error, follow with the reference call; loss is masked on the broken turn | recovery, not giving up after one refusal | Mac CPU |
| The subject's own passes (T2) | sample the checkpoint on new training seeds, keep effective = 100 | consolidation; the base already scores 100 on 31 of 100 `d1-test` tasks and 0 of 100 hard ones, so alone it teaches only the easy types | PC nights or about $0.02-0.05 an episode |
| Open-weight teacher passes (optional) | Gemma 4 31B or Qwen3.6 on training seeds, passes only | other routes to the same sheet | about $1.50-3 per 100 episodes on Nov 10's bills |
| Frontier passes (hold) | Opus or Terra on training seeds | the same | check each provider's terms on training other models from outputs first; I have not, and the plan does not need them |

**Format.** A training example is the harness's own conversation, byte for byte what the model sees at eval:
`system_neutral.md` with its budgets filled, the 75 tool definitions, the task at the vague level (about a quarter
at explicit, one truth under two prompts), assistant turns with tool calls, results as the bus's compact JSON,
`submit`. Rendered through the model's chat template; loss on assistant turns only. The recorder writes ordinary
episode files, so one converter serves references and rollouts, and `eval verify` scores every example before it
is kept.

**One pin, one rig.** Cut a training pin from main once the dataset code lands (main carries the stationing-hint
fix, 4d135e7d, that the board's `0334fd4a` surface lacks). On that pin and one rig, run base, T0 and every
checkpoint, so each delta is read like for like. The board's existing 9B rows stay as they are.

**What counts as a result.** Headline: the paired delta against base on `d1-test`, vague, no convention sheet.
Transfer: the same on `d1-real` with no real sheet in training. Guard: the text pilots and the probes do not fall.

## 4. Stages

| stage | work | cost | the number at the end |
|---|---|---|---|
| **C0 data** (`c-d1-refs`, `c-faithful`, `c-faults`) | training manifests and the disjointness test; the grounded recorder; fault injection; episode-to-conversation converter; a dataset card with the pins | $0 | N trajectories, 100% grounded, 100% scoring 100, 0 shared ids; a token-length histogram |
| **T0** (`c-t0`) | the convention sheet, written from spec v1 and from what `eval standards` shows is lost; `--system-extra FILE` in the harness, hashed into the prompt hash; base and T0 on `d1-test` and `d1-real` | PC nights, or about $5-10 | T0 minus base, paired |
| **T1 smoke** | 50 trajectories, one epoch on a rented card: the template render matches the serving path, memory and tokens a second measured, the adapter merges and serves, 10 `d1-dev` episodes run against it | about $5 | a served checkpoint, and the measured price of the full run |
| **T1** (`c-t1`) | LoRA on 1,000-1,500 references plus injected faults, 3 epochs, checkpoint chosen on the validation sets; then the eval package | $15-40 training (Cost Plan estimate, unmeasured) plus evals | T1 minus base and T1 minus T0 on `d1-test`; the `d1-real` delta |
| **T2** (`d-t2`) | sample the T1 checkpoint on fresh training seeds weighted to the types it still fails, keep the 100s, retrain from base; one round, a second if the first pays | $50-140 a round (estimate) | the round's delta; the `d1-test-hard` score |
| **T3** (`d-e6`, `d-t3`) | GRPO through a Gymnasium adapter | $100-350 (estimate) | gated, see below |

T3 is not planned in detail. At 28k tokens of fixed prompt a rollout, online RL is bound by generation, and RQ3's
criterion can be met by T1 and T2. Decide after T2, from what `eval causes` says is left.

## 5. First steps

All free, all on the Mac, none waiting on a decision:

1. **`d1-train` and `d1-train-hard` manifests and the disjointness test** (`eval/taskset.py`,
   `tests/test_eval_taskset.py`). Small; it makes contamination a failing test before any data exists.
2. **The grounded recorder for seeded D1 tasks**, by phase in `tasks/reference.py`'s order, starting with the
   phases behind the 9B's largest losses (layers, stationing, lettering). Acceptance: every training task's
   grounded reference scores 100 at the vague level through the episode loop, and the audit finds no ungrounded
   value. This is the critical path, several working sessions.
3. **The converter and the dataset card**: episode files to chat-template conversations, with the tool digest,
   prompt hash, spec, generator and verifier versions in the header, and the token histogram that sizes T1.
4. **T0's two pieces**: the convention sheet and the `--system-extra` flag. Ready to queue when the local hard
   sets finish (about Nov 15).

Then, on your word: the T1 smoke, the first paid step.

## 6. Decisions for Robert

1. **The rig for base, T0 and checkpoints.** PC only: free, one to one and a half nights per 100 episodes, and
   each checkpoint needs merging and a Q4_K_M GGUF conversion. Runpod bf16 on vLLM: minutes and a few dollars a
   set, the rig the Cost Plan assumed. I recommend Runpod for the loop, since training has to rent a card anyway,
   and a GGUF copy of the final checkpoints for a local board row.
2. **A budget line for training.** The $71 left of November's $100 is set aside for the large-model queue.
   Through a first trained row I estimate $30-60 on top (smoke, T1, lean evals).
3. **The pin.** A new one from main with the base rerun on it (recommended), or the board's `0334fd4a`.
4. **Frontier teacher data**: leave out (recommended) or check the terms.

## 7. Risks

| risk | guard |
|---|---|
| The grounded recorder takes longer than planned | build by phase; ship T0 and a first dataset on the simple task types before the whole-sheet types |
| Imitating a solver that never errs makes a model that cannot recover | injected faults in T1; the subject's own passes in T2 |
| The model learns the generator's layouts, not drafting | `d1-real` as the transfer test, `d1-real-dev` in validation; a twisted-viewport seeded type if `d1-real` lags |
| Training text differs from what the server sends (tool-call syntax, thinking) | the smoke's byte-for-byte check before any full run |
| Contamination | the disjointness test; the dataset card lists every source run and seed range |
| Cost drift on long sequences | the smoke measures tokens a second and memory before T1 is priced |
