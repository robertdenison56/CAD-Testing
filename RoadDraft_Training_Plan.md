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
Transfer: the same on `d1-real` with no real sheet in training. Second headline since 2026-11-11 (§8): the
pilots the subject passes on `hard-pilots`, vague, paired by task against base and read by family. Guard: the
probes do not fall.

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
3. **The converter and the dataset card** (built 2026-11-12, night; status below): episode files to chat-template conversations, with the tool digest,
   prompt hash, spec, generator and verifier versions in the header, and the token histogram that sizes T1.
4. **T0's two pieces** (built 2026-11-12, night; status below): the convention sheet and the `--system-extra` flag. Ready to queue when the local hard
   sets finish (about Nov 15).
5. **The injected faults** (`c-faults`, built 2026-11-13; status below): a faulted copy of each reference,
   the 9B's own mistakes put in and recovered from, the broken turns at weight 0.

Then, on your word: the T1 smoke, the first paid step.

### Status, 2026-11-10 (Robert: "Yes, start")

**Step 1, done.** `benchmarks/tasksets/d1-train.json` (1,200 tasks, seeds 10000-11199, 72 to 78 of each of
the 16 seeded types) and `d1-train-hard.json` (297 tasks, seeds 12000-12299; three seeds no hard type lays out
are left out and named in the manifest). They are not in `taskset.NAMES`, so no board ranks them.
`taskset.train_overlap()` reports any task id or seed a training set shares with an eval set, and
`tests/test_eval_taskset.py` holds it empty.

**Step 2, started: 8 of the 16 seeded types.** `roaddraft.trajectories.grounded`:

- `GroundedAgent` drafts through the ordinary episode loop, handed only the task text and the phases the
  request calls for. It reads the document, the layers, the sheet's scale and the design before it uses any of
  them. It sets the annotation scale to the sheet's scale and lets the engine size the lettering, so no command
  carries a height or offset worked out by hand; that route scores 100 at both prompt levels.
- `audit` reads a finished episode as the model saw it and reports every value in a call that was not in the
  task text, an earlier result, the tool's own definition or spec v1 when the call was made. It knows nothing
  of the agent, so it reads a model's rollout the same way (T2's filter).
- A recording is kept when it submits, scores 100 and the audit finds nothing.
- Covered phases: design, layers, linework, edges, stationing, bearings, callouts, reference. Covered types:
  `draw-alignment`, `stationing`, `bearings`, `curve-callouts`, `pavement-edges`, `attach-reference`,
  `create-alignment`, `layer-setup`. On `d1-dev` all 24 tasks of those types are kept at both levels.
- The audit on the plain oracle, same tasks: 100 on every type and ungrounded on every type (the sizes it
  multiplies out, the curve table's position, the dimension points, the viewport's centre, the title-block
  fields, and a `set_meta` no task asks for).

**Left in step 2**, in the order I would take them: the curve table (where it goes on the sheet, and which
curves each sheet shows), the north arrow and title block (what the vague prompt lets the drafter know of the
project), the sheet and its viewports (scale choice, match lines), the width dimensions. Those four phases are
what stands between the 8 types and all 16, and the whole-sheet types need every one.

One known looseness in the audit: a small round number (5, 6) can match a spec value by chance and pass. It
catches what matters (3.5, 22.5, 28.35, a coordinate), and tightening it per tool is a later refinement.

### Status, 2026-11-11 (Robert: "Table and title block")

**Step 2 now covers 12 of the 16 seeded types.** Three phases were added to the drafter: the curve data
table, the north arrow and the title block. They bring in `curve-table`, `title-block`, `annotate-sheet` and
`annotate-base`.

- **Curve table.** The drafter reads each sheet, then the model's extents, and maps the extents' two corners
  onto the sheet to see where the plan falls on the paper. It puts the table a quarter inch inside the top-left
  corner of the usable area, reads the table back for the box it takes up, and checks that box against the plan
  and against everything already on the paper. On a layout of several sheets it reads the match line lettered
  on each sheet and the station the viewport is centred on, and lists on each sheet the curves between its match
  lines; a sheet that shows no curve gets no table. Columns, text height and title are the engine's own, which
  are the standard's.
- **North arrow.** The office's block at the spec's place and scale, on each sheet that has none.
- **Title block.** A prompt that states the values has them lettered as written. A vague prompt gives none, so
  the drafter takes the project and agency from the document's description, the sheet number from the sheet's
  name, the sheet count from the file, and the scale from the viewport.
- **The audit** now also accepts a number worked out in the turn's own shown work (`21.5 - 0.25 = 21.25`; it
  redoes the sum, and every operand has to be grounded), a scale as a title block letters it, and a part of a
  longer string already read. The one number the drafter picks for itself, the quarter-inch gap, is named in
  `CHOICES`.

**`d1-train`, recorded in full** (as first recorded; the vague row is 903 kept since the ruling below):

| level | tasks | covered | kept | short on the title block only |
|---|---|---|---|---|
| explicit | 1,200 | 903 | 903 | 0 |
| vague | 1,200 | 903 | 753 | 150 |

The top-left corner was clear on every one of the 300 table tasks, so no fallback corner was needed.

**What the vague title block showed.** The verifier wants all ten title block fields filled at every level
(D1-10). Four of them are nowhere in a seeded document: who designed, drew and checked the sheet, and its
date. The drafter leaves those four blank and says so in its note, so a vague `title-block` recording scores
88.9 and a vague `annotate-sheet` recording 97.6, and neither is kept. Every one of the 150 is short for that
reason alone. In Opus 5.5's vague `d1-test` run, the title block episodes that fill every field put in "RD"
and the day's date on their own; one scores 100 and says in its report that "RD" is a placeholder. Left
blank, the four fields cost 0.95 points of 100 on `d1-test` at the vague level (6 `title-block`, 7
`annotate-sheet` and 6 `plan-sheet` tasks). It is decision 5 below.

**Left in step 2:** the sheet and its viewports (scale choice, match lines) and the width dimensions. They
bring in `sheet-setup`, `plan-sheet`, `pavement-widths` and `pavement`, then the three hard types.

### Status, 2026-11-11, later (Robert on decision 5: "do 3")

**The names and the date are in the document.** Every seeded document now carries who designed, drew and
checked it and its date in its own record (`meta`), under the title block's field names
(`tasks.generator.DOCUMENT_PEOPLE`). The base drawing of a basefile type carries them too. The vague prompt
is unchanged and still states none of them. The drafter fills any title block field the document's record
carries under that field's name; a field nothing gives is still left blank and said so.

| level | tasks | covered | kept |
|---|---|---|---|
| explicit | 1,200 | 903 | 903 |
| vague | 1,200 | 903 | 903 |

**What did not move.** No task id: the payload an id hashes always held the four values (`project`), so all
ten manifests check as current. No generator or verifier bump. The oracle scores 100 and the null agent 0 on
all 100 tasks of `d1-test` and of `d1-test-hard`. The board is as it was.

**What did move.** The starting document of every seeded task, by those four entries. Only a task that asks
for a title block is graded on anything they bear on: 19 of `d1-test`'s 100 tasks, 80 of `d1-test-hard`'s.
The explicit rows are untouched in effect (the prompt states the values). The vague rows on those two sets
ran without the names in the document. What each lost to the four blank fields, which is the most a rerun
could add to the row:

| set | title block tasks | rows | lost to the four fields, points of 100 |
|---|---|---|---|
| `d1-test` | 19 | 11 | 0.28 to 0.95 (Opus 5.5 0.34, Terra 0.95, the 9B 0.55) |
| `d1-test-hard` | 80 | 6 | 1.32 to 1.55 (every model left them blank on every one of its title block tasks) |

Adding each row's figure to its score reorders neither board. I kept the rows ranked, on the precedent of
the explicit prompt rewrite of Oct 22 (what the model is shown changed, the graded values did not, no bump,
rerun on Robert's word). The stricter reading is that 99 held-out tasks changed and their rows should rerun
before they rank; that is decision 6 below. Rows from here on carry the commit in their episode headers.

### Status, 2026-11-11, evening (Robert: "Twist dial first")

**The seeded generator has a twist dial.** `generate_task(..., twist=True)` turns every viewport of the
task's sheets by the seed's own twist (`tasks.generator.seed_twist`: anywhere round the circle to the
hundredth of a degree, never within 10° of none). The seed's road, stationing and paper layout are those of
its untwisted task: the road is turned under the sheet by the twist and the viewport turned back, so the
generator's fit, sheet breaks, table corner and match-line labels are the ones it already works out. On a
twisted task the truth letters the model to read upright as plotted (`view_rotation`), the north arrow is
turned to north, and a task that lays the sheet out is held to the viewport's turn. The truth, the reference
and the verifier already did all of this for the real sheets; no verifier change.

**What the prompts say.** Explicit: the turn, and that model lettering reads upright on the plotted sheet.
Vague: nothing on a task that letters or finishes a set-up sheet, so the drafter has to look at the viewport,
as on a real sheet; the turn only where the layout itself is asked for (`sheet-setup`, `plan-sheet`), as the
published twist is stated on a real sheet.

**`d1-train-twist`**, a third training set: 600 tasks on seeds 13000 to 13599, every one twisted, over the
nine seeded types whose work a twist changes (66 or 67 each; one sheet 307, two sheets 293; one, two and
three curves 200 each). The oracle scores 100 and the untouched start 0 on all 600 at both levels. It shares
no id and no seed with any other set.

| level | tasks | covered | kept |
|---|---|---|---|
| explicit | 600 | 467 | 467 |
| vague | 600 | 467 | 467 |

The 133 not covered are `sheet-setup` and `plan-sheet`, which wait on the sheet and viewport phase (build 1
of §8). The drafter reads the turn off the viewport, hands it to each labeler, turns the north arrow, and on
a turned sheet checks the curve table's corner by searching the model under the table's box (102 of the 201
table tasks; the other 99 are clear of the viewport's frame). Median 6 turns and 10 calls.

**What did not move.** Off is the default and adds no key to a task, so no existing id moved (all ten eval
manifests and the two earlier training sets check as current), the 948 prompts of the held-out seeded and
real sets read as they did, and 240 untwisted recordings re-record to the same turns. No generator or
verifier bump; the board is as it was.

**Two findings.**

- *The verifier barely prices the skill.* It takes a label's own record for where the label belongs and
  marks it down only where it plots upside down. The reference's commands with the twist taken out average
  95.7 on `d1-train-twist` at the vague level, and still score 100 on 112 of the 267 tasks that only letter
  the model. A rollout like that never looked at the viewport. The keep rule therefore has a third leg,
  `grounded.twist_ignored`: lettering added on a twisted sheet without the sheet's twist is not kept, at any
  score. The `p17` pilots' own check is the stricter one: every label along its line and reading from the
  bottom or right.
- *Width dimensions cannot be twisted.* A dimension's text reads upright in the model and `place_dimension`
  has no `view_rotation`, so through a twisted viewport it can plot upside down however it is placed. The
  generator refuses to twist the three types that carry width dimensions. Giving the engine that parameter
  moves the tool surface, so it is Robert's call and not done.

### Status, 2026-11-11, night (Robert: "Yes, start it")

**The drafter lays out the sheets.** The `sheet` phase is covered, so 14 of the 16 seeded types and two of
the three harder ones are drafted from the task text alone. Nothing of a viewport is worked out by hand:

- *One view, centred through the engine.* Each sheet is made at the size asked for (the office's ANSI D when
  the task does not say) with the office's plan viewport, set down on the point midway between the two ends
  of its stretch. The engine is asked where the stretch falls on the paper (its ends and the PI of each curve
  on it, which bound it), then which model point shows at the middle of that box, and the view is centred
  there. Both ends are then seen to show.
- *A scale the task leaves open.* A model already lettered tells the scale it was made for: one station
  number is read (6 ft off the line over the office's 0.12 in is 50 ft to the inch). With nothing lettered
  yet the larger of the office's two scales is tried first, and where the line with an inch and a half all
  round for its lettering is past the office's 26 by 15 in plan window the view goes to the next. The spans
  at the second scale are the measured ones times the ratio, so no view is set twice.
- *The lettering after the sheet*, sized for the scale and read through the twist its viewport shows, as on a
  sheet that was handed over set up.
- *Several sheets: each frame trimmed round its own stretch.* What each sheet shows of the lettering is read,
  each label with the point it is set at on the paper. The frame keeps an inch and a quarter clear round
  every label point of its stretch and the ends of the stretch, and a quarter inch round the ends of its
  match line. A label of another sheet's stretch that would show inside the frame nearer an edge than that
  would be cut there, so the edge moves out past it. A station equation's label is the one long enough to
  reach further, so its own box is read. A frame that reaches past what the view showed is not trusted: the
  view is centred on it and the sheet read again.
- *Match lines.* Drawn by station and offset (the reach the task gives, or two inches each side on the
  paper), lettered on both sheets a quarter inch past the end of the line, and read back.

| set | tasks | covered | kept, explicit | kept, vague | before tonight |
|---|---:|---:|---:|---:|---:|
| `d1-train` | 1,200 | 1,053 | 1,051 | 1,051 | 903 |
| `d1-train-twist` | 600 | 600 | 600 | 600 | 467 |
| `d1-train-hard` | 297 | 237 | 235 | 235 | not recorded |
| all | 2,097 | 1,890 | 1,886 | 1,886 | 1,370 |

Every recording kept scores 100 with nothing ungrounded. The 903 and 467 recordings made before tonight
re-record to the same turns at both levels. Setting up one sheet takes 6 turns and 15 to 18 calls. A whole
plan on two or three sheets (the 176 kept of `d1-train-hard`) takes a median of 23 turns and 108 calls, 140
at the most, inside the budget of 150.

**What is not kept or not covered.**

- 4 tasks a level are covered and not recorded, because the drafter stops rather than guess: a frame that
  would be larger than the plan viewport (2), a frame that keeps reaching past its view (1), and a curve
  table whose corner is not clear (1).
- 207 tasks wait on the width dimensions (`pavement`, `pavement-widths`, `plan-sheet-pavement`).

**Three findings.**

- *A label cut by a viewport's edge is what fails a layout of several sheets.* With the reference's own
  lettering, the office's plan viewport centred on each stretch scores 100 on every one-sheet task and
  falls short on one layout in four of two sheets and one in three of three, mostly for a label cut by the
  frame's edge. With the frame sized from the lettering, 286 of the 290 layouts of several sheets are kept
  and the drafter stops on the other 4 (above).
- *A sheet label can run back over its own line.* For a label set square to the line on a sheet, the
  engine picks the end the text is set from by the way it would read in the model (`labels.label_pose`) and
  its rotation by the way it reads on the paper (`labels.sheet_pose`). Through a turned viewport the two
  can disagree, and a match line's label set a quarter inch past the end of the line then runs back across
  the centerline. The drafter reads the label back and sets it again from its other end. I left the engine
  alone: a change there could change how stored runs replay, so it is Robert's call.
- *The task says where the sheets break.* Every seeded layout prompt names its sheets and its break
  stations at both levels, so the drafter has not yet had to choose how many sheets a line takes or where to
  break it. That is what `p05` asks, and it is the open half of build 1 (§8, decision 8).

### Status, 2026-11-12 (Robert: "Clearing step")

Build 3 of §8, in two parts: seeded sheets with something on them to keep clear of, and the step that keeps
clear of it.

**What a crowded pilot is made of.** I lettered the 13 `p04` sheets at the engine's default poses, every
line of each, and counted what the verifier's footprints call an overlap (`D1-08`): 527 new labels, 42
collisions. 9 are a new label on another line's lettering. 33 are a new label on lettering drawn on the
paper itself, the sheet's own notes. None is between two labels of one line. So a seeded crowd needs both
kinds, and the notes matter more.

**The crowd dial** (`tasks/crowd.py`, `generate_task(..., crowd=True)`, `--crowd` on the tasks CLI). The
seed's own road on a sheet somebody has already worked on:

- a second line, `ALIGN-2`, a straight road across the first, drawn and lettered the office's way (ticks,
  station numbers, its bearing). On `annotate-base` the line and its linework are in the base drawing and
  its lettering in the sheet file, anchored through the reference, as a real sheet file carries it;
- one or two notes lettered on the paper.

Each is aimed: the default pose of a label the task asks for lands on the second line's lettering, and
another on each note. A crowded task is kept only when the reference can clear it, so its truth carries the
poses that do (`label_poses`, chosen as `tasks.real` chooses them on a real sheet) and the reference scores
100 from a start that scores 0. Side and offset are not graded, so the drafter is free to clear the sheet
another way. Every truth sheet lists what was handed over (`given_entities`), so an overlap among it is
nobody's and an overlap with it is the drafter's. The dial fits the five types that letter the model on a
sheet already set up, on one sheet. Off is the default: no uncrowded id moves, and no verifier change.

`d1-train-crowd`: 600 tasks on seeds 14000-14599, 300 of them through a turned viewport, 200 at each curve
count. `annotate-base` 154, `curve-callouts` 124, `annotate-sheet` 120, `bearings` 116, `stationing` 86
(38 seeds took the next type because the reference could not clear theirs: 34 `stationing` sheets, where the
reference moves station numbers as a set and the other side of the line already holds the bearings, and 4
`bearings` sheets).

**The clearing step** (`trajectories/grounded.py::_clear`). The engine reports a text by its box on the
model's axes and in no other way: not its length, not its corners, not where it plots. So the drafter
compares in steps, each only for what the one before leaves open:

1. *The boxes as they stand.* Two texts whose boxes in the model do not meet do not meet. For something on
   the paper, a label near enough to reach it has the corners of its box taken to the paper by the engine,
   and that box is compared with the other's.
2. *Along and across a line.* A box round lettering at an angle is mostly empty, so two boxes that meet
   settle nothing. A line's label is known in its own line's terms from its record: it lies from its offset
   to its offset plus its height off the line. The other thing's corners are put in the same terms by
   `xy_to_station`, and the two are compared across the line, then along it. The longer label is the one
   taken from its record. Something on the paper has its corners taken to the model first.
3. *What is left is taken to meet.* The label is deleted and placed again by the same labeler on the other
   side of its line, then two and four text heights further off, read back and compared again, now with its
   own line's lettering on that side as well.

A line alone on its sheet is not read back: the engine's labelers keep one line's lettering clear of
itself. Of two lines in a design, the one drafted is the one the request names.

| | tasks | kept, explicit | kept, vague |
|---|---:|---:|---:|
| `d1-train-crowd` | 600 | 534 | 534 |
| the three sets recorded before | 2,097 | 1,886 | 1,886 |
| all | 2,697 | 2,420 | 2,420 |

- Every kept recording scores 100 with nothing ungrounded. The 1,890 recordings of `d1-train`,
  `d1-train-twist` and `d1-train-hard` re-record to the same turns at both levels.
- By type: `curve-callouts` 124 of 124, `stationing` 84 of 86, `annotate-base` 142 of 154, `annotate-sheet`
  111 of 120, `bearings` 73 of 116.
- A kept recording sets 1 to 5 labels again, 1,210 in all, and takes a median of 19 turns and 52 calls; 7
  take more than 120 of the 150 calls, 139 at the most.
- The same drafter without the step scores under 100 on a crowded sheet, on `D1-08` alone.

**Three findings.**

- *Boxes alone are not a test.* My first version compared boxes only and kept 5 of the first 9 recordings:
  a bearing's box on a line at an angle takes in both sides of the line, so it "meets" its own station
  numbers wherever it is put. With the comparison along and across the line, 18 of the first 19 were kept.
- *On the pilots the comparison finds every collision.* Run offline on the 13 `p04` sheets at the default
  poses: the boxes leave 119 pairs open, the comparison along and across a line flags 64, and all 42 real
  collisions are among them (22 are not real; 60 of the 527 labels would be set again). That is the
  detection only. I have not run the drafter on a pilot, and I have not checked the poses it would move to.
- *What is not kept is one long label against another at an angle.* All 66 are a label that would not clear
  in five tries: 60 bearings, 4 curve point labels, 2 station numbers. The other thing's corners are those
  of its box, which is loose for a second long label or a note across the line. The label's true corners
  can be had by station and offset (`station_to_xy`), but that query takes display stations, so it needs
  care past a station equation. Not built.

**What build 3 does not reach.**

- A `p04` pilot letters every line of its sheet (12 of the 13); a crowded seeded task letters one line among
  lettering that is given. The comparison is the same, the bookkeeping is not.
- A table for each line, titled with its line, and a note's leader running under a label.
- The call count on a dense sheet. On the pilots about 56 pairs of a label and a note a sheet are near enough
  for the label's box to be taken to the paper, at four calls a label.
- `D1-08` on `d1-test`, where a sheet shows one line and the step is not taken. Whatever the 9B loses there
  is something else, and I have not looked at what.

### Status, 2026-11-12, later (build 4: the revision task)

Build 4 of §8: a finished sheet whose design has changed under it.

**What the redline pilots ask, and what the engine does about it.** A `p11` pilot hands over a finished sheet
and one change to its design. Measured first on the 12 pilots: the scripted solution with its re-lettering
replaced by one `update_labels` on the line passes none of them. A curve point lettered with its text given
keeps its old text, a tangent the change brings in gets no bearing, and stations past a new end get no
tick. What does pass is the scripted route: take off everything lettered from the old design, letter the
line again, and restation each note that cites it. That route needs no tool the seeded tasks lack.

**The revision dial** (`tasks/revise.py`, `generate_task(..., revise=KIND)`, `--revise` on the tasks CLI). The
seed's sheet, finished by the reference from the old design (lettering, curve table, and the title block and
north arrow where the type has them), and one change to the design, one of three as on the pilots: a curve's
radius (every PI held), a curve's PI moved along its back tangent (its radius and every other PI held), or
the line restationed. Who makes the change depends on where the design lives:

- *In a base drawing* (`annotate-base`): the designer has made it there, with the centerline and pavement
  edges redrawn. A D1 episode has no way into the base file, so the drafter's half is the lettering.
- *In this file* (`annotate-sheet`): the start keeps the old design and the change is the drafter's to make
  (Robert, 2026-11-12, decision 11: "Yes, revision only"). The truth grades the design (D1-15) and the
  centerline drawn from it (D1-01) beside the lettering.

Either way, one or two notes on the paper cite a station of the line (`EXIST CULVERT STA 112+35.00`), the
first at a point the change restations where the line has one.

The prompt reports the change at both levels (it is the redline's content). The explicit one also states
the lettering conventions and that every note citing the line must be restationed; the vague one says
"Bring sheet C-101 up to date." (with "Make the change and" where the design is the file's) and nothing
about the notes, which is the knock-on edit the pilots leave unnamed. The truth is the revised design's. A
revised task is kept only when the reference scores 100 at both levels and the start does not. One sheet,
no station equation. Off is the default, and no existing id or held-out prompt moves.

**The tool list** (decision 11). A revised task's truth carries a `revision` mark in its scope beside its
groups. That mark, and nothing else, puts `modify_alignment` and `update_labels` on the drafter's tool list
(`eval.tools.REVISION_COMMANDS`), as `design` in the scope puts `create_alignment` there. No check grades
the mark, and no other task's list or tool digest moves.

`d1-train-revise`: 600 tasks on seeds 15000-15599, 300 on base drawings and 300 in the file, every kind of
change with both types, every curve count and both twists. 248 restations, 197 radius changes and 155 PI
moves. 48 seeds took the next kind because their line could not take theirs (a PI moved on a three-curve
line with short tangents drops a tangent below the generator's floor).

**What the drafter does.**

- *The design in a base drawing* (`_revise`, before the lettering): read what was lettered from the line
  (everything the model holds anchored to it, and its curve table; the redrawn centerline stays); restation
  each note; take off everything lettered from the old design (the table stays on a restation, as the
  curve data holds no station); letter the line again with the phases that already exist; then the
  clearing step checks the new lettering against the notes. A note is restationed by the stated shift on a
  restation. On a change of the geometry the old tick at the whole station before the note still marks
  where that old station was, so `xy_to_station` of its point on the revised line, plus how far past it the
  note is, gives the new station. That holds only on a stretch the change left in place, so the tick must
  lie on the revised line and no curve point may fall between it and the note.
- *The design in this file* (`_revise_own`): while the line is still the old one, `station_to_xy` reads
  where each note's station lies; `modify_alignment` makes the change with the centerline redrawn, and the
  engine brings every label lettered from the line along; `update_labels` checks that nothing is out of
  step; `xy_to_station` of each note's point reads its new station. A PI moved along its back tangent is
  worked out from `measure` of that leg: each coordinate plus the leg's difference over its length times
  the move, every number to the thousandth. The dial moves it with the same arithmetic, so the drafter's
  design is the truth's to the bit.

A new leg of the keep rule (`tasks.revise.left_stale`): nothing lettered from the old design left, and every
note reading its restationed text.

| | tasks | kept, explicit | kept, vague |
|---|---:|---:|---:|
| `d1-train-revise` | 600 | 600 | 600 |
| the four sets recorded before | 2,697 | 2,420 | 2,420 |
| all | 3,297 | 3,020 | 3,020 |

- Every kept recording scores 100 with nothing ungrounded and nothing left stale. 585 notes are
  restationed, and some recordings also carry a note whose station the change does not move, which the
  drafter works out and leaves.
- On base drawings a recording takes a median of 17 turns and 31 calls (89 at the most); in the file,
  where the labels follow the change, 7 turns and 13 calls (15 at the most).
- The 2,690 recordings of the four earlier sets re-record to the same turns at both levels (checked before
  the tool-list change, which no earlier task sees).

**An engine bug the labels' follow showed, fixed** (decision 12, Robert: "Fix it now"). When the labels
follow a change of a line (`modify_alignment` on a document's own line, or `update_labels`), the engine
lays each stationing set out again with the settings it reads back off it. A label records the twist it was
lettered for only when there is one, so every label on an untwisted sheet records none, and the engine
guessed a twist from a station number's pose (`commands/label_updates.py::_view_rotation`): the twist that
keeps that number level. On an untwisted sheet that guess is wrong, and a curve point's label laid out
through it could come out upside down: `194+97.76 BC` at 136.9° on seed 15015, where the same sheet
lettered fresh scores 100. The guess was written for base files lettered through a twist before the record
carried it (L-1's "TB1"). Now no twist is kept when no twist poses every label of the set as it stands, and
the guess is made only when it does not. The set laid out again is then the one stationing lettered fresh
on the revised line, and the L-1 case is unchanged (its test passes as it was). Before the fix the dial
left 10 seeds out, all untwisted sheets with the design in the file; with it the set is 600 again, the 590
earlier task ids unchanged. The fix changes what the engine does, not the tool list. A stored pilot run that
called `update_labels` on an untwisted real sheet could replay differently, so the rows stand as recorded.

**On the pilots, offline.** The tick method, run on the 12 `p11` starts against the pilots' own grader:
it agrees on all 20 cited stations that have a tick. Two more (U-1's general note, citing stations off the
sheet) have no tick; that pilot is a restation, which the stated shift covers. I have not run the drafter
on a pilot.

**What build 4 does not reach.**

- *The change in a base file.* On a pilot the model changes the design in the base file (`open_document`,
  `modify_alignment`, save, `reload_references` on the sheet file). A D1 episode cannot open another file,
  so on base drawings the designer has made the change. That is the third way of decision 11, left for the
  pin.
- *The redline and the revision block.* A pilot's markup has to come off and the revision be recorded in the
  border. Neither is seeded.
- *Lettering with its text given.* On the pilots the curve points carry fixed text, which is why
  `update_labels` leaves them stale. The seeded sheets letter everything with the engine's own text, so that
  trap does not arise; taking off and lettering again avoids it on both.

### Status, 2026-11-12, night (the width dimensions; the crowded bearings)

**Every seeded type is covered.** The width phase dimensions the pavement width square across each tangent
with `place_dimension`. It takes the tangent's two pavement edges and the same fraction along each (to the
millionth: a station is graded to 0.005 ft), so the engine finds the points; the annotation scale sizes the
text. At plan scale the text does not fit between the edges and goes out past the second point, so the edge
away from the BC and EC labels goes second. Where a dimension may stand is judged in the line's terms from
each label's record. A label along or square to a tangent is taken at its true length, worked out from its
box, its height and the tangent's run (`(W × len − h × |dy|) / |dx|`, the engine's own width to 0.01 ft),
never its box. The dimension line must miss every label's stretch; the text must miss every label that
reaches past the edge on its side. A stated station is kept and the line moved half a text height off what
it would cross. A station left to the drafter is the half station nearest the tangent's middle that clears
(the spec's standard; at that station itself the bearing blocks the line on 142 of 147 tasks), else the
nearest place just past what is in the way. Past a station equation the station is worked out from the
equation's own numbers; the tangent rows' rounded station texts are off by up to the 0.005 ft tolerance. On
sheets handed over, the text's box is worked out from the record, the engine's warning ("the text needs
21.52") and the tool's defaults, and checked against each view; a dimension a frame would cut is set again
(`find_entities`' `shown` follows the dimension line, not its text). On sheets the drafter lays out, each
frame is trimmed round the dimensions' boxes. The audit now also grounds a size a tool's definition gives as
a ratio of the text height ("1.2 x the text height"); that only loosens it.

| set | before | kept, explicit | kept, vague |
|---|---:|---:|---:|
| `d1-train` | 1,051 | 1,198 | 1,198 |
| `d1-train-hard` | 235 | 294 | 294 |
| `d1-train-crowd` | 534 | 592 | 592 |
| `d1-train-twist`, `d1-train-revise` | 1,200 | 1,200 | 1,200 |
| all | 3,020 | 3,284 | 3,284 |

Width types: `pavement` 72/72, `pavement-widths` 75/75, `plan-sheet-pavement` 59/60 (D1-012124: a frame
that keeps reaching past what its view shows, the frame trimming's existing stop). The widths phase with the
edges adds 9 to 12 calls to a whole plan: `plan-sheet-pavement` takes a median 133 calls at the vague level
and 124 explicit, at most 150 and 141. One vague plan uses the whole 150-step budget and three use 148:
kept, with no slack, so any call added to a whole plan has to be counted.

**The crowded bearings.** Where the clearing step finds two labels meeting only by a loose measure (a length
bounded by its box, or the other's corners those of its box), both are measured by their true sizes first:
the length from the box, the height and the tangent's run, and the other's true corners by arithmetic along
its own tangent. Those corners are projected onto the first one's tangent by arithmetic where they fall on
it, else by `xy_to_station`; no `station_to_xy`, so no display-station trap past an equation. The step now
also tries three and six text heights further off. Crowd went from 534 to 592 a level: 58 gained, none lost.
Kept recordings take a median 58 calls (52 before), at most 137. Every crowd recording and 13 revise
recordings changed (they go through the clearing step); `d1-train`, `d1-train-hard` and `d1-train-twist`
re-record turn for turn identical. The 8 not kept: 7 bearings that truly overlap at all nine places tried,
one over budget. Generator, verifier, engine and tool surface unchanged; widths stay untwisted (decision 9).
The previous recordings are in `results/grounded/before-widths/` (455 MB, duplicates).

### Status, 2026-11-12, night (step 3: the converter and the dataset card)

**The converter.** `roaddraft.trajectories.conversations` turns an eval episode file into the conversation
the harness has with a model, built from the harness's own pieces rather than a copy of them. The system
prompt is the one `agents.llm.system_for` gives an LLM agent under the episode's mode and budgets; a model
run's header carries its own, which is used as is. The tool list is what `eval.tools.tool_definitions`
makes for the episode's scope, held to the header's digest. The task text is taken at its level and held to
the header's prompt hash. Each turn's results come back as `LLMAgent._results` hands them, laid out as the
OpenAI-compatible provider sends them: one tool message per result as compact JSON, and the `[harness]`
note as a user message. A turn keeps its calls in one assistant message, as the harness ran it (the drafter
often asks two or three queries a turn), and the conversation ends on the `submit` call. One path serves
references and rollouts. A test runs an LLM agent through the fake provider and finds the conversation
equal, message for message, to what the provider was sent. Before a conversation is written, its task is
rebuilt from the manifest (prompt, truth and starting document must match), its journal is re-scored (100
or dropped), and the grounded keep rule runs again (audit, `twist_ignored`, `left_stale`).

**The data, rebuilt on the recordings above** (the first pass ran on the 3,020 a level before the width
phase). `convert` wrote `results/training/<set>-<level>.jsonl` for all ten pairs, `tools.json` with four
tool sets (74 tools; 75 with `create_alignment`; 76 with the revision commands; 77 with both) and
`summary.json`; `card` writes `benchmarks/training/DATASET_CARD.md`. 6,568 conversations, none dropped.

| set | kept a level | tokens, median | most |
|---|---:|---:|---:|
| `d1-train` | 1,198 | 32,071 | 69,269 |
| `d1-train-hard` | 294 | 71,718 | 121,294 |
| `d1-train-twist` | 600 | 33,956 | 64,313 |
| `d1-train-crowd` | 592 | 61,421 | 113,596 |
| `d1-train-revise` | 600 | 41,648 | 77,697 |
| all | 3,284 | 37,952 | 121,294 |

The fixed prompt is 27.8k-30.1k tokens; 812 of the 6,568 conversations run past 65,536 tokens and none past
131,072; 300.8M tokens in all. The width phase and the crowd's true-size measure made the whole-sheet and
crowded conversations longer: the hard set's median went from 64k to 72k and its longest to 121k, near the
131k window. **Tokens.** The 9B's own tokenizer is not on the Mac. `scripts/training_tokens.py` builds
Qwen3.5's tokenizer from llama.cpp's qwen35 vocabulary (it agrees on all 51 of llama.cpp's test strings) and
renders through llama.cpp's Qwen3.5 template. Against LM Studio's counts on 240 requests of four 9B
`d1-test` episodes, the first request counts 27,670 against the server's 27,698; the gap grows by about 2
tokens a tool call and 2.3 an argument, at most 1.9% of a request. So the lengths are 1-2% low and the loss
tokens lower still; a recount with the 9B's `tokenizer.json` belongs in the T1 smoke. (Done 2026-11-13: the
9B's own tokenizer counts LM Studio's requests exactly; the references are 302.9M tokens, and the loss tokens
were 5.8% low. See the `c-faults` status.)

**Open for T1.** The drafter's shown work is visible text, and Qwen3.5's template adds an empty think block
to each assistant turn. One in eight conversations runs past 64k tokens, so the T1 sequence length (and its
price) is set by the hard and crowded sets.

### Status, 2026-11-12, night (step 4: T0's two pieces)

**The flag.** `python -m roaddraft.eval run --system-extra FILE` adds a file after every model's system
prompt, one blank line between. API and CLI routes both get it: Claude Code in `--system-prompt`, Codex in
its instructions file; probe tasks (hard-pilots) after their own system prompt. It is refused with a
non-model `--agent` (oracle, null, scripted, replay). `run.json` and every episode header record the file
and its sha256; `prompt_hash` covers the brief and the extra together, and `prompt_sha256` and
`system_prompt` show the prompt as sent. A run will not resume over episodes given a different extra, or
none. With the flag off nothing moves: `tests/test_eval_system_extra.py` pins every brief hash on the seven
held-out sets at both levels and the system prompt for each mode, and the pins match the 7,214 v3 board
headers. The board's v3 rows ran before the stationing hint (4d135e7d), so their system prompt differs from
main's by one line: T0 is read against a base rerun on the same pin, as §3 says.

**The sheet.** `benchmarks/training/conventions-v1.md` (sha256 `89b9a471…`, 4,840 characters, about 1.2-1.5k
tokens, 4-5% of the fixed prompt). It covers what each kind of request covers, layers (never 0), sheet
setup, lettering with the spec's offsets, legibility and a check before submitting, written from
`DRAFTING_SPEC_V1` and from `eval standards` on the 9B and four other vague runs. A test holds every number
in it to the spec, and any station or bearing to the spec's own examples.

**Not run.** Smoke on the fake provider only: same scores, both hashes moved, the base `prompt_hash` equal to
the 9B's recorded header. Base and T0 on `d1-test` and `d1-real` at vague are 400 episodes, about 4-6 PC
nights; they wait on decision 1 (rig) and decision 3 (pin). `lms_campaign.py e3` does not pass the flag yet,
so the PC run calls `python -m roaddraft.eval run` directly.

**Open, for rollouts.** The converter checks a model run's task text against the header's `prompt_hash`
(`trajectories/conversations.py`, the `prompt` drop). A run given an extra hashes the brief and the extra
together, so the converter drops it as `prompt`. T0 runs are on held-out sets and never reach training; a
T2 rollout run with an extra would need the check to use `eval.episode.prompt_hash(brief, extra)`.

### Status, 2026-11-13 (`c-faults`: the injected faults; Robert: "Build fault injection")

**What it is.** `roaddraft.trajectories.faults` makes a faulted copy of each kept reference: at one place
(60%) or two (40%) a call broken the way the 9B breaks it, the engine's own error, then the reference's
call with a line of shown work that reads the error ("This file owns no alignment of its own: the design
is BASE:ALIGN-1, in the attached base drawing, and the call has to name it."). The broken turn's assistant
message carries `"weight": 0` (the OpenAI fine-tuning convention): the model is trained on the recovery
and never on the mistake. A *swap* breaks a reference call and every call after it in the turn that takes
the same mistake (up to 4: a model that leaves the alignment off one label leaves it off the turn's
others), and the next turn redoes them; an *insert* puts an extra call the reference never makes in a turn
of its own before a reference turn.

**The mistakes**, from the 9B's failed calls on its six board rows, tallied by tool and error (only their
shape is taken; every broken call is made from the training reference's own call):

| kind | the 9B's failed calls | how |
|---|---:|---|
| `alignment_left_off`: a label, table, stationing or query on the referenced design with no `alignment` | 488 | swap |
| `alignment_misnamed`: `ALIGN-1` for `BASE:ALIGN-1`, or `BASE:` put on the file's own | 95 | swap |
| `stationing_on_sheet`: alignment stationing given a sheet as its space | 206 | swap |
| `begin_station_given`: a begin station given to alignment-mode stationing | 136 | swap |
| `layer_not_made`: a generic name (`C-ANNO-TEXT`, `C-ROAD-CNTR`) for the file's layer | 110 | swap |
| `draw_referenced`: `draw_alignment` on the base drawing's alignment | 76 | insert |
| `made_twice`: a sheet, reference or layer set up again | 66 | insert |

A kind is drawn by its count among the kinds a reference has a place for, then a tool by its count within
the kind.

**Through the bus.** A copy runs as an episode (`FaultAgent`) that plays the reference's recorded calls back
with the broken turns in place, and is checked as it runs: every broken call must fail with the engine's
`command_failed` or `query_failed`, and every other result must equal the reference's byte for byte. Then
the journal must equal the reference's (a refused call changes nothing), the episode must score 100, and
the grounded audit must find nothing ungrounded outside the broken turns. A copy that misses is tried at
other places, up to three times. On the 6,568 references none missed.

**The data.** `python -m roaddraft.trajectories.faults inject` (2.6 min, 6 jobs) wrote `results/faults/`;
`conversations convert` now converts each set's faulted copies beside its references into
`<set>-<level>-faults.jsonl` (id `<task>.<level>.faults`, header `injected`, `counts.masked`), and the card
has an *Injected faults* section. 6,135 faulted copies of 6,568 references, 7,894 faults; 12,703
conversations in all, none dropped. The 433 without a copy are title-block and layer-setup tasks (nothing
after the set-up for a fault to land on; 66 of them in `d1-train-twist`) and one hard reference already at
the 150-step budget. Mix: misnamed 32%, layer not made 29%, stationing on a sheet 13%, left off 11%, begin
station 8%, made twice 5%, drawn referenced 2%. Left off is below its share of the 9B's failures because
most training tasks own their alignment, where there is nothing to leave off; on the base-drawing tasks it
is the kind taken most. `scripts/training_tokens.py` leaves weight-0 messages out of the loss count. Tests:
`tests/test_trajectories_faults.py` (11), and the converter's 57 with them, pass.

**Tokens** (recounted 2026-11-13; Robert: "Yes, count them"). Unsloth Studio's llama.cpp update to b12340
took away the qwen35 vocabulary the token script read, so it now reads the 9B's own `tokenizer.json` and
`chat_template.jinja` (`Qwen/Qwen3.5-9B` on Hugging Face, revision `c2022362`, kept in
`~/.roaddraft/tokenizers/Qwen3.5-9B`; the template is byte-identical to llama.cpp's Qwen3.5 one); a GGUF
vocabulary is now `--gguf` only. On the same 240 requests of four 9B episodes it counts exactly what LM
Studio reported, every request to the token. The references recount at 302.9M tokens, 0.7% over the
2026-11-12 count, and 31.8M of them trained on, 5.8% over (the old vocabulary's gap sat in the tool calls);
846 run past 65,536 (was 812), none past 131,072. The faulted copies are 291.6M tokens: a copy runs a median
291 tokens past its reference (most 1,868), 30 more cross 65,536, none 131,072. They train on 29.9M, a copy
a median 38 fewer than its reference, because a swap's reference calls before the mistake share the broken
turn's message and its weight 0 (they are trained on in the reference itself). Together: 12,703
conversations, 594.4M tokens, 61.7M trained on.

**Not done.** T1's mix (how many faulted copies beside the references) is the T1 run's choice; every
reference that can have one has one.

**Found, for the pin's cut.** The 9B's most frequent failed call is `place_label` with no alignment in a
sheet file (396 on its six rows; after 184 of them no `place_label` worked again in the episode). The error's hint is "create one with
create_alignment or import_landxml", which sends a model the wrong way when the base drawing carries the
design; `station_to_xy`'s error for the same thing says "its references carry ['BASE:ALIGN-1'] -- name one
of those". Giving `place_label`, `place_curve_table` and `annotate_stationing` the same hint changes no
tool definition, only what a failed call says, so it can go in the pin's cut with decision 3's engine
changes. The faulted copies then need making again, as they will after the training sets are recorded
again on the pin (decision 3): `faults inject`, then `conversations convert`.
**Built 2026-11-13 (3ae2dac7).** With no alignment of the document's own, `place_label`,
`place_curve_table`, `annotate_stationing` and `draw_station_offset` now say "this document owns no
alignments, but its references carry ['BASE:ALIGN-1'] -- name one of those as alignment", and a bare
name the document does not own (`ALIGN-1` for `BASE:ALIGN-1`) gets the same hint. A command that draws
the design itself (`draw_alignment`) and a document with nothing attached are told what they were.

### Status, 2026-11-14 (the pin's branch: `training/pin-cut`)

Everything waiting for the pin is on one branch, `training/pin-cut` (main `1b5ce003` + `pilot-dev`, the T1
smoke kit and build 5), fixed after review and not yet tagged. Robert's rule for this pass: nothing that
affects a score already run.

**Recorded again on the branch.** The eight D1 training sets keep 4,182 of 4,190 tasks a level, the same
eight tasks short as before (`d1-train` 1,198 of 1,200, `-hard` 294 of 297, `-twist` 600, `-crowd` 599 of
600, `-revise` 600, `-twist-widths` 291 of 293, `-revise-base` 300, `-breaks` 300). Build 5,
`train-deeds` (seeds 19000-19299) and `train-qa` (20000-20299), keeps 300 of 300 a level each; they now
record on the pilots' budgets (600 steps, 12 faults; they had the D1 budgets) and carry their own pins
(`pilot-check-417746eb2a92`, `pilot-check-d9a65d2ae684`), and `eval run --taskset train-deeds` works
(oracle 100, null 0). 7,931 faulted copies of the 8,364 D1 references.

**The dataset** (`results/training`, card in `benchmarks/training/DATASET_CARD.md`): 17,495 conversations,
none dropped; the converter takes probe episodes, holds a `--system-extra` run to the prompt as sent, and
no longer writes a closing submit note twice (8,193 conversations had it). The trainer's preparation
gives 17,812 sequences, 17,799 kept, 906.9M tokens, 82.9M trained, median 48,102, longest 130,837. 13
sequences run past 131,072 tokens and are left out: all from `d1-train-twist-widths` seeds 16287 and
16062, references and faulted copies. The two seeds stay in the set.

**The base rerun and T0, set up, not launched.** `benchmarks/lmstudio/queue-base-pin.sh PIN_WORKTREE TAG
[--dry-run] [--after PID] [--resume]` runs base, base with thinking off, and T0. `eval run` and
`lms_campaign.py e3` take `--thinking off` and `--system-extra`; a one-episode check must show the server
obeyed before any thinking-off set starts. The base package measured from the stored 9B rows is about
56 hours on the PC (d1-test 4.8, d1-real 3.9, d1-test-hard 19.1, d1-real-hard 6.6, hard-pilots 15.7, the
dev sets about 6), T0 about 9; with thinking off on every set, up to 56 more. A run given
`--thinking off` or `--system-extra` reports and ranks as its own row (`· thinking off`,
`· system extra <sheet>@<digest>`); a run with neither is keyed and written as before. `pilot-dev` is
never published, like the other dev sets.

**Stored scores, checked.** Under the branch and under its last commit, the reports of all 92 published
runs regenerate byte for byte the same; `make_leaderboard.py --check` is current; the held-out manifests,
the tool digest (`c66b17cd`), `d1-verify-v8` and `e3-v3` are unchanged; seven held-out episodes built
under both trees have the same prompt, budgets and pins.

**The trainer** (`scripts/training_lora.py`): a validation split by seed, `--resume`, `--save-steps`,
`--loss own`. Not verifiable on the Mac: Unsloth's adapter set-up with the target pattern, its loss at
122k tokens (the fallback is `--loss own`), and a resume under `adamw8bit`. The T1 smoke is the check.

**Open.**
- The base `-pin1` 9B runs will share a row key with the published `-v3` 9B vague rows, and the Overall
  table takes the later of two runs with one key without saying so. Retire or supersede the `-v3` rows
  when the rerun is published, or have the board refuse a repeated key; left alone here because either
  moves the board.
- The headline base: thinking on (as the board's 9B rows ran) or off (the only way a trained checkpoint
  can be served). The queue runs both.
- Decision 14, below.
- Found by the check, older than this branch: `report --reverify` gives another score than the published
  one on 16 of 71 D1 runs (by 0.004 to 0.49, real sheets mostly), and 38 summaries are from report
  version `e4-v1`. Stored scores as read do not move; publishing any of them again would.

### Status, 2026-11-15 (the pin is cut; the free builds after it)

The branch of 2026-11-14 is merged into main (`95eed64d`) and tagged `pin/training-1` (Robert: "Merge and
tag"); neither is pushed. Everything below was built after the tag, on main, and none of it moves a tool
definition, a task id, a prompt, a manifest or a stored score: the pin stays the commit every base, T0 and
checkpoint run is made at.

**A checkpoint's eval package.** `benchmarks/lmstudio/queue-base-pin.sh` has a fourth kind, `ckpt`
(`PHASES=ckpt CKPT=<name>`): the checkpoint's GGUF with `--thinking off`, on the pin's harness and task sets,
after its own thinking-off check episode. Its `models.json` entry lives in the main checkout
(`benchmarks/lmstudio/add_checkpoint.py NAME --lms-key KEY --check check.json` writes it from the base's:
the same sampling, context and quantization, `vision` false), because the pin predates any checkpoint; the
driver it runs must be byte for byte the pin's `lms_campaign.py`. A checkpoint without the vision tower runs
the 89 text pilots of `hard-pilots` only. The base, no-think and T0 kinds are unchanged (the real dry run
against the pin worktree prints the same commands as before). The steps are in
`benchmarks/training/T1_SMOKE.md` §5a.

**The number a stage ends on.** `python -m roaddraft.eval delta RUN BASE` (`eval/delta.py`) pairs two run
reports by task: the gap with the board's bootstrap interval, the same by task type, the tasks at 100 in
each (the pilots passed, on a probe set), the tasks only one of the two ran, and everything that keeps the
two from being like for like (set, prompt level, mode, thinking, a system extra, tool surface, instructions,
spec, generator, verifier, harness, a partial or re-scored run). It reads what `eval report` wrote and
scores nothing.

**Two runs under one row.** `report.publish` refuses a run whose row (set, model, provider, effort, mode,
prompt level, thinking, system extra, cost subset, text pilots or all) a published ranked run already holds,
and `make_leaderboard.py` warns of any such pair. No published row is ranked from two runs today, so the
board is byte for byte what it was. When the base rerun is published its `-pin1` rows will be refused until
the `-v3` 9B vague rows are retired: which stays is still Robert's call (the open item of 2026-11-14).

**T2's tooling** (a subagent's build in a worktree of its own, brought into main after its tests ran here;
the runbook is `benchmarks/training/T2.md`). Nothing has been run against a model.
`python -m roaddraft.eval t2 plan RUN_DIR --round 1 --size 600 --name d1-train-t2-r1` reads a checkpoint's
run on `d1-dev`, a training set or an earlier round (a held-out run is refused), takes a miss rate for each
of the 42 cells (training flavour and task type), shrunk toward the run's rate on the same type elsewhere
because a dev run has three or four episodes a type, and builds a manifest on seeds 21000-22999 (1,000 a
round) with the existing entry builders: a quarter of the tasks keep the training mix (`--floor`), the rest
go to what the run misses. An all-pass or all-fail run gives the training mix. The manifest carries the
record it was planned from, `t2 check` rebuilds it from that record, and writing one that shares an id or a
seed with any held-out, training or T2 set is refused. No T2 manifest is in the repo, and the names are in
no tuple the regenerating tests read. `eval run --taskset d1-train-t2-r1` runs it (oracle 100 on 60 of 60).
`python -m roaddraft.trajectories.conversations rollouts RUN_DIR --taskset d1-train-t2-r1` converts a
round's episodes; a rollout is kept when it submitted, was not nudged, matches its task, prompt and tools,
re-scores 100, and passes the two finished-document legs of the keep rule (`twist_ignored`, `left_stale`),
since the verifier gives 100 to some lettering made without the twist. The turn-by-turn grounding audit is
the scripted drafter's and is not applied to a model (`--audit none` is the bare "submitted and 100").
Known: weighting toward what a checkpoint fails lowers the share kept (the plan table prints an estimate);
a revised task untouched scores above 0 as in `d1-train-revise`; the token counter and the trainer's
preparation have not been run on a folder that holds rollout files.

**`train-profile`: plan-and-profile sheets (`p06`)** (a subagent's build in a worktree of its own, brought
into main; `tasks/planprofile.py`, `trajectories/reasoning_profile.py`, seeds 25000-25299). 299 tasks (seed
25150 has no tangent long enough), each a generated two-sheet road with a seeded profile, an empty ANSI B, C
or D sheet (`standard` or `fdot` border), 1"=50' or 1"=40', vertical a tenth of that or 1"=10'. The prompts
are the pilots' own wording and the check is the pilots' own items (`profile.make_check` at 1"=50', the same
item functions in the stated grid's frame at 1"=40', `make_vague_check` at the vague level), so the plan
view's stations lined up over the profile's is graded on every task. Registered beside `train-deeds` and
`train-qa`, outside `probes/pilot`; `hard-pilots` and `pilot-dev` keep their hashes. Recorded in the
subagent's worktree: 299 of 299 kept at each level, a median 6 turns and 41 to 44 calls; the converter takes
all 598 with none dropped. What the five pilots have and the set has not: `wfl` and `caltrans` borders (three
of the five are WFL sheets; their title blocks sit inside the usable area the engine reports), referenced
corridor files in the plan view, agency layer names, a grade break above 1 %. Engine facts: no query gives
the elevation at a station, so the drafter shows 30 to 100 sums an episode; `_grade_item` wants a line at
the exact station a grade begins or ends, which a drafter working to four decimals misses at 1"=40' unless
the station is snapped (the generator snaps it; a model can meet the same edge on a pilot). The audit takes
four new forms, on a plan-and-profile brief only. Not done: recording in main, faulted copies, the token
count, and the dataset rebuild that would take the set in.

**`train-striping`: striping plans (`p13`)** (a subagent's build in a worktree of its own, brought into
main; `tasks/striping.py`, `trajectories/reasoning_striping.py`, seeds 24000-24299). 300 tasks, none skipped
or dialed: a generated line with its edges of pavement, a seeded profile, two empty marking layers and no
sheet; the range is 600 to 1,200 ft, the speed 40 to 70 mph. Six kinds: a no-passing zone for up-station
traffic (75), for down-station traffic (75), one each way (75), the two overlapping into a double solid
(25), a crest that restricts nothing (25), a sag (25). The briefs are the pilots' own wording, the check is
the pilots' `make_check` on the generated line, and the truth is the pilots' sweep. Recorded in the
subagent's worktree: 300 of 300 kept at each level, 4 turns and a median 11 calls; the converter takes all
600 with none dropped. The drafter finds the zones in closed form from `get_design_data kind=vcs` (the least
sight distance on the crest, then the tangent sight line), each step a sum the audit follows; the audit
takes the MUTCD's own numbers and a stated square root, on a striping brief only.
**The limit to know:** every generated crest stands alone, and none of the six pilots' crests does. Applied
by hand to the pilots' profiles with the neighbouring curves ignored, the method lands inside the check's
25 ft on three (wfl15, wfl16, wfl19) and outside on three (wfl17 60 ft, wfl20 42 ft, cflpnp 70 ft). So the
set teaches the table, the eye and object heights, which side the solid goes on, the stripe pattern and
zones clipped by the range, and not the interplay of neighbouring vertical curves or joining zones under
400 ft apart. Engine facts: no query gives an elevation at a station or a sight distance; `array_entities
kind=path` turns each copy by the path's bearing, so a stripe pattern has to be drawn pointing east. Not
done: recording in main, faulted copies, the token count, the dataset rebuild.

**Where this leaves the dataset.** The pin's dataset (17,495 conversations) is unchanged. The two new sets
add 599 tasks a level once recorded in main, faulted and converted; that rebuild is free and not done here,
since it changes the card the T1 smoke is sized from. Checked on the combined tree: every held-out and
training manifest current, `make_leaderboard.py --check` current.

### Status, 2026-11-25 (Robert: "Go with 1": the bulk dial)

T1 loses on the real dev sheets (`benchmarks/training/T1.md` §11): it reads a long list page after page, or
asks again for an answer that came back cut. The reference drafter stops at the same place. Run on the 24
`d1-real-dev` tasks as a diagnostic (nothing kept, nothing trained on), it finishes 4: on 10 it stops at
`get_sheet_state` cut at the harness's 30,000 characters. So no recording could have shown the way past it.
Finding 3 and decision 7 stand (no real sheet trains), so the seeded sheets were given what the real ones
have.

**Measured gap.** A seeded training sheet carries 0 to 4 entities on its paper and one base drawing of 9 or
10 elements attached as `BASE`. The three dev sheets carry 126 to 1,122 entities on the paper and base files
of 121 to 6,621 elements attached as `AA01` and `BB01`.

**Built** (`tasks/bulk.py`, `generate_task(..., bulk=True)`; nothing held out moves, see below):

- three training-only types, `base-stationing`, `base-bearings`, `base-callouts` (`TRAIN_TASK_TYPES`): one
  piece of a line's lettering on a finished sheet whose design lives in the attached base drawing, the
  rest handed over. They are the seeded counterparts of `real-stationing`, `real-bearings` and
  `real-callouts`, with the real vague prompts' words ("Station the SB16 line on sheet PL-203.");
- the bulk dial on them: the line, the sheet, the references and their files named as an office names
  them (drawn from patterns, none copied from a held-out sheet); a survey base attached beside the
  design's (right of way, ticked fences, contours, buildings, trees, a parcel field off the sheet: 370 to
  1,967 elements over a sample of 100); and the paper's own furniture as entities (notes, a legend,
  schedules ruled by hand, revision strips: 237 to 608 entities, a sheet state of 43,000 to 116,000
  characters). Nothing is aimed at the lettering (that is the crowd dial): the survey keeps two inches of
  paper off the line. A bulked task is kept when it starts at 0, its reference scores 100 and its sheet's
  state is over the cap;
- `d1-train-bulk`, seeds 26000-26599: 600 tasks, none skipped, 200 a type, one to three curves, two in
  three through a turned viewport;
- the drafter (`trajectories/grounded.py`): it reads the head of the cut answer for the scale and the
  twist, says the answer was cut and that asking again would cut it at the same place, and then asks by
  kind and by place: its own line's lettering by the line's anchor, the box its new labels take (a quarter
  inch added, its corners taken to the model by `sheet_to_model`), and only what lies in that box.

**Recorded** (`results/grounded-new/d1-train-bulk-{vague,explicit}`): 600 of 600 kept at each level (100,
nothing ungrounded). In every recording the sheet's state is asked for once, comes back cut, and is not asked
for again; no other answer is cut (the largest is 19,363 characters); a search returns 2 rows at the median
and 86 at the most; "the list runs on" is said in 11 of the 600. Median 9 turns and 17 calls.

**Nothing held out moved.** No tool definition, verifier, prompt of an existing type or manifest changed;
`pytest tests` passes with the new set in. `benchmarks/training/DATASET_CARD.md` is not regenerated.

#### The same day, bulk-v2 (Robert: "verify that the training tasks are as realistic as possible. additional references, topo included in plan views")

The first dial was checked against the three dev sheets element by element, as a count of structure only
(what is attached, how much of it lies under the line, what the paper holds; no answer of a held-out task).
The paragraphs above describe bulk-v1; this one replaces its numbers.

| | real dev sheets (3) | bulk-v1 | bulk-v2 (30 sampled) |
|---|---|---|---|
| references on the sheet | 2 | 2 | 2 to 4 (7, 16 and 7 of 30) |
| design file: elements | 177 to 4,576 | 9 to 21 | 154 to 540 |
| design file: layers | 9 to 10 | 2 | 7 to 10 |
| design file: lines (alignments) | 1 or 2 | 1 | 1 or 2 (two in 22 of 30) |
| design file: elements within half an inch of the line on the paper | 12 to 105 | 6 to 14 | 7 to 325 |
| survey: elements within half an inch of the line | 4 to 1,288 | 0 | 56 to 245 |
| survey: elements touching the line | 1 to 555 | 0 | 0 to 86 a file |
| base text within half an inch of the line | 1 to 14 | 0 | 0 |
| paper: entities | 126 to 1,122 | 237 to 608 | 292 to 603 |
| title block | the agency's (`caltrans`) | `standard` | `standard` |

**What v1 had wrong.** It kept every base element two inches of paper off the line, so the plan view
under the lettering was white. On a real sheet the topo runs under the road. Legibility judges text against
text (and a leader or dimension line against text), never linework, so nothing graded needed that band.

**bulk-v2** (`tasks/bulk.py`; `BULK_VERSION`): the survey is one to three files (the topo; the right of way
and parcels; the existing utilities), so a sheet carries two to four references, the design's attached
first or last. The topo crosses the line (contours, culverts, fences, spot shots) and runs along it (the
existing pavement and its stripe, ditches, driveways); mains run under the road. Much of it is drawn a
stroke at a time, as a digitised base is. The design file gains shoulders, hinge and catch lines with
slope ticks, inlets, hatched patches, tags, and in seven of ten a second line, stationed in the file (a
frontage road beside the first or a street across it): `list_alignments` then names two lines and the
brief one. The paper gains details sketched in lines. Only base *text* keeps two inches off the line.

`d1-train-bulk` rebuilt: 594 tasks (6 seeds skipped: the reference did not score 100 on the fuller sheet).
Recorded again: 594 of 594 kept at each level. The sheet's state is asked for once and never twice; the
largest whole answer is 25,270 characters; a search returns 6 rows at the median, 138 at the most; "the list
runs on" in 39 of 594.

**A fault the second line found in the drafter.** One explicit recording lettered the wrong line: the
drafter took the design file's second line, `AN`, as the one the brief named, because "ANSI D" contains
it. `grounded._named` now looks for a name as a word of its own first. The other 1,187 recordings chose
the same line either way (each scored 100).

**Still not a real sheet's.** The title block is the seeded `standard` one. No base text stands inside
the line's lettering (on the real sheets another line's stationing does): the drafter does not yet move a
label off base text on a cut sheet, so such a task would not record. Neither is built.

#### The same day, bulk-v3 (Robert: "Yes, seeded sheets"): the two differences left

| | real dev sheets (3) | bulk-v2 | bulk-v3 (589 of the set) |
|---|---|---|---|
| title block | the agency's (`caltrans`) | `standard` | `caltrans` 341, `wfl` 122, `standard` 126 |
| base text within half an inch of the line | 1 to 14 | 0 | 0 to 9, median 3 (none on 24 sheets) |

**The border.** A bulked sheet is drawn on an agency's border most times (`bulk.borders`): the Caltrans one
the three dev sheets carry, or the Federal Lands one. Its title block floats over the plan and every field
it letters is filled from patterns. On the Caltrans border the plan moves right of the binding strip, the
north arrow stands beside the title block and the curve table keeps to the paper left of it. A sheet whose
line would run under the title block keeps the seeded border. Nothing of the title block or north arrow is
graded on these types (the sheet is handed over finished).

**Base text inside the lettering.** A contour's elevation on the road, the old pavement's and the
shoulder's tags, a main lettered along itself, a cross street stationed through the crossing. Where a
label's default pose lands on one, the truth sets it as a drafter would (`crowd.choose_poses`: the other
side of the line, then further off). That happens on 24 of the 598 sheets.

**The drafter** (`grounded._clear`) can now do that on a sheet too large to read whole: it reads the
label's own text height (the narrow list does not carry it), sets the label again, and where it lands on
paper that was not searched, searches that box too before comparing. Before, it stopped.

`d1-train-bulk` rebuilt: 598 tasks (2 seeds skipped). Recorded again: 598 of 598 kept at each level. The
sheet's state is asked for once and never twice; the largest whole answer is 25,493 characters; a label is
set again in 24 recordings a level and a second search made in 6.

**Still not a real sheet's.** The text near the line is where the ground puts it, not aimed at the
lettering, so only one sheet in twenty-five asks for a label to be moved. The crowd dial (`tasks.crowd`)
is the one that aims; the two are not combined.

**Converted, the same evening (Robert: "Convert the set").** `faults inject --set d1-train-bulk --source
results/grounded-new --out results/faults-new` kept 1,196 of 1,196 faulted copies (752 faults vague, 766
explicit; one fault on about three copies in four, two on the rest; `alignment_left_off` and
`alignment_misnamed` are three quarters of them). `conversations convert --set d1-train-bulk --source
results/grounded-new --faults results/faults-new` wrote four files into `results/training`, 598
conversations each, none dropped, all on the one tool set `0f108e6b…`. Counted with the 9B's tokenizer:

| file | conversations | tokens | trained | median | longest | past 65,536 |
|---|---:|---:|---:|---:|---:|---:|
| `d1-train-bulk-vague` | 598 | 35,465,751 | 1,172,908 | 58,949 | 80,318 | 56 |
| `d1-train-bulk-vague-faults` | 598 | 35,722,098 | 1,130,885 | 59,341 | 80,928 | 61 |
| `d1-train-bulk-explicit` | 598 | 35,583,064 | 1,172,908 | 59,154 | 80,528 | 58 |
| `d1-train-bulk-explicit-faults` | 598 | 35,845,058 | 1,128,968 | 59,491 | 80,761 | 70 |

None is past 131,072. The set is 142.6M tokens (4.6M trained); the vague half alone is 71.2M. The whole of
`results/training` is now 21,085 conversations, 1,078.9M tokens, 96.4M trained, 6 past 131,072 (none of
them bulk). `benchmarks/training/DATASET_CARD.md` is rewritten from the new summary. The conversion took 78
minutes and the faults 40, against minutes for the older sets: the sheets are large.

**Not built.** (a) done, above. (b) Sheet work on a cut sheet (a curve table's corner, a title block's keys: the usable
area and the keys are past the cut), so `annotate-base`, `curve-table` and `title-block` are not bulked yet;
two of T1's seven losses are title blocks. (c) The construction callouts (the `notes` phase), which the
drafter does not cover on any sheet. (d) A second line in the base drawing. (e) No training run: a run on
data that includes this set is Robert's call, as the 10,000-conversation run is.

## 6. Decisions for Robert

1. **The rig for base, T0 and checkpoints.** PC only: free, one to one and a half nights per 100 episodes, and
   each checkpoint needs merging and a Q4_K_M GGUF conversion. Runpod bf16 on vLLM: minutes and a few dollars a
   set, the rig the Cost Plan assumed. I recommend Runpod for the loop, since training has to rent a card anyway,
   and a GGUF copy of the final checkpoints for a local board row.
   **Decided 2026-11-13: the PC, Q4_K_M.** The "nights" above were wrong for the vague runs: the 9B's
   vague episodes took 4.8 h on `d1-test`, 3.9 h on `d1-real` and 15.7 h on `hard-pilots` (the episodes'
   own clocks, queue gaps not counted), so a package is about a day, perhaps two for a trained model that
   works longer. The loop keeps the board's precision. Each checkpoint is merged and quantized to Q4_K_M on
   the training pod before it stops, and the GGUF is carried to the PC.
2. **A budget line for training.** The $71 left of November's $100 is set aside for the large-model queue.
   Through a first trained row I estimate $30-60 on top (smoke, T1, lean evals).
   **Decided 2026-11-13: $150 through a first trained row.** The Track D queues spent the November money
   (balance about $10.79 by the last queue's count, Nov 13 05:05), so the line needs a top-up first. It
   covers the smoke (about $5-10), T1 (the data sized to the throughput the smoke measures: one epoch over
   all 300.8M tokens fits), and the checkpoint conversions; the evals cost nothing on the PC. A budget line
   is not a go: each paid step still waits on Robert's word.
3. **The pin.** A new one from main with the base rerun on it (recommended), or the board's `0334fd4a`.
   **Decided 2026-11-13: a new pin from main.** All 6,568 training conversations were recorded on main's
   tool surface (`9db020d9`); the board's `0334fd4a` has the stationing help from before 011c2008 and no
   revision-only tools, so a model trained on the data would meet other tool descriptions at eval. Four
   engine changes land on main first (decisions 9, 10, 11's base file and 13), the training sets are
   recorded again on the result, and then the pin is cut and the base rerun runs on it.
4. **Frontier teacher data**: leave out (recommended) or check the terms. **Decided 2026-11-13: leave it
   out.** The training data is the grounded recordings, and later the subject's own passes (T2).
5. **The title block from a vague prompt** (found 2026-11-11). **Decided 2026-11-11: the third, "do 3".**
   The document did not say who designed, drew or checked a sheet, or its date, and D1-10 wants those fields
   filled. The three ways out were:
   - Keep the drafter as it is: blank fields, said in the note. The 150 vague recordings then need the keep
     rule to allow that one shortfall, and a model trained on them gives up about a point on `d1-test` vague.
     This is what I recommend for training, whatever is decided for the benchmark.
   - Stop grading fields the page does not give at the vague level. That is a verifier bump (v9) and a free
     re-score of every stored run; rows that left the fields blank go up.
   - Put the names and the date in the document, where a real project file has them. That changes the
     starting document of every title block task, so the held-out rows would be on a different task.
   What I would not do is train the model to write initials and a date it was never given.
6. **The vague rows that ran before the names were in the document** (2026-11-11). Leave them ranked with
   the note above (recommended: the most any row could gain is 0.95 on `d1-test` and 1.55 on `d1-test-hard`,
   and neither board reorders), or rerun them. The local reruns are free and slow; the frontier ones are on
   hold. **Decided 2026-11-13: leave them ranked.** The board carries no note of it yet; one goes in its
   footer at the Track D close-out.

7. **What may train the pilots** (2026-11-11, §8). Keep every sheet a held-out pilot uses out of training
   (recommended; training is then on generated sheets and the pilots stay a transfer test), or allow new
   parameters on the same sheets (cheap for five families, and the model has then seen the test's sheets).
   **Decided 2026-11-13: keep them out.** No task on any of the 42 sheets the pilots use trains; the 9
   clean sheets of §8 carry `pilot-dev`, for choosing a checkpoint only.
8. **A seeded task that leaves the sheet breaks to the drafter** (2026-11-11, the open half of build 1). It
   needs a new task type whose prompt gives no breaks and a check that takes any sound set of them, as the
   `p05` grader does from the plotted sheets; the D1 sheet check grades against the generator's own breaks.
   Build it as a training-only type with a check of its own (recommended: no board set or id moves), or
   leave `p05` to transfer from the stated-break layouts. **Decided 2026-11-13: the training-only type.**
   It touches no tool, so it need not wait for the pin.
9. **Width dimensions through a turned viewport** (2026-11-11). `place_dimension` has no `view_rotation`;
   giving it one moves the tool surface. Until then the three width types stay untwisted. The drafter
   covers them untwisted since 2026-11-12, night (206 of 207 kept a level), so this only decides whether a
   width task may be twisted. **Decided 2026-11-13: build it, before the pin.**
   **Built 2026-11-13.** `place_dimension` takes `view_rotation` in model space, as the labelers do:
   the number is set to read upright on the sheet (its model rotation is the paper one turned back by
   the twist) and on the side of its line that is up on the paper, and a radius leader's landing and
   text run level on the paper. A dimension keeps its twist when it is moved, copied, turned,
   scaled, arrayed or mirrored, and `modify_entity` sets or clears it (both found by an independent
   review before the commit: the first cut dropped the twist on any such edit, and a dimension
   nudged after it was placed went back to reading upright in the model). An untwisted dimension
   draws and is recorded as it always was (the file gets no new key; the same primitives bit for
   bit over 80,000 random dimensions), so no held-out id, document or score moves. Over 24 headings and 10 twists,
   536 of 960 dimension numbers did not read upright on the paper without it and none with it. The
   verifier needed no change: it already judged a dimension's number as lettering (D1-08). It reads
   text as far round as 135 degrees, though, so a number made without the twist is marked down on
   some headings and not on others (at half a turn, 0 of 3 on one seed and 2 of 3 on another); the
   drafter's keep rule (`twist_ignored`) therefore reads a dimension's `view_rotation` as it reads a
   label's. The generator no longer refuses a twisted width task, the reference gives its dimensions
   the twist, and the explicit prompts state it ("The viewport is turned 114.67°, so set the
   dimension text to read upright on the plotted sheet."); a vague `pavement` or `pavement-widths`
   prompt says nothing of it, like a vague lettering prompt, and a vague `plan-sheet-pavement` gives
   the turn with the layout. The tasks are a set of their own, so that `d1-train-twist` keeps its
   nine types and its ids: `d1-train-twist-widths`, seeds 16000-16299, 293 tasks (98
   `pavement-widths`, 98 `plan-sheet-pavement`, 97 `pavement`; 7 seeds with no tangent to dimension
   left out, 10 dialed to the type's other sheet count), the two types handed a sheet on `d1-test`'s
   dials and the whole plan on `d1-test-hard`'s. Oracle 100 and null 0 on all 293 at both levels.
   The drafter reads the twist off the viewport and gives it to each dimension; 291 of 293 are kept
   a level (the two left are whole plans it declines to frame), a `pavement` or `pavement-widths`
   task in a median 16 or 17 calls and a whole plan in 127 (vague, the most 144 of the 150 allowed).
10. **What the engine tells a drafter about lettering that collides** (2026-11-12, the clearing step). Today
    nothing: a text is reported by its box on the model's axes, and a model that cannot look at a render has
    to work out the rest. The three ways on:
    - Leave the surface as it is. The step is built on it and 592 of 600 crowded recordings are kept (534
      before the true-size measure of 2026-11-12, night). The cost is calls (a median 58 a crowded
      recording), and a method a model has to learn.
    - Let the listing of what a sheet shows carry each text's four corners on the paper. One read then
      replaces steps 1 and 2. It moves the tool surface, so every board row ran without it.
    - A query that lists the pairs that collide on a sheet. That hands over the verifier's own answer; I
      would not.
    I recommend the second, in the same cut as a new pin if decision 3 goes that way, and the first until
    then. **Decided 2026-11-13: the second, in the pin's cut.** The corners are the verifier's own
    footprint (`verify.legibility.text_quad`) taken to the paper; the clearing step is rebuilt on them.
    **Built 2026-11-13.** `find_entities` gives a text row `paper_corners`: with `visible_on`, a model
    text's lettering seen through the viewport the row names (its height over the feet per inch, turned
    by the twist), and a sheet's own text where it stands; they match `sheet_items`' footprints to the
    rounding (5e-5 in) on six crowded tasks, one twisted and with lettering read through a base drawing.
    The tool definitions move (`9db020d9` to `cd5e8a86`), the instructions do not. The clearing step
    (`grounded._clear`, 690 lines to 295) now asks nothing of the engine past the two listings: two
    footprints are apart when their boxes are, or when the places of their corners along a side of
    either do not overlap, each place a corner's x times the side's run in x plus its y times its run
    in y. The comparison is written to the corners' ten-thousandths: at thousandths, a BC label 0.006
    in into a station number was rounded apart along its tenth-inch side. `FULL_ROWS` went 25 to 20,
    since rows with corners ran past the 30,000-character cut. `d1-train-crowd`: 599 of 600 kept a
    level (was 592; the one left was not kept before either), and on the 592 kept both ways the median
    calls went 58 to 28 (34,893 to 15,485 in all), turns 21 to 16, the shown work 16% shorter and the
    results 15%. Every other training set keeps what it kept: 3,291 of 3,297 a level in all.
    **Extended to dimensions the same day, with decision 9.** A dimension's number is lettering the
    verifier judges the same way, and the width phase was working its box out by hand: from the
    engine's "the text needs" warning, the tool's default ratios and the dimension's record, against
    each view's window in the model, which is no box at all through a turned viewport. A dimension
    row of `find_entities` now carries the `paper_corners` of its number, and `visible_on` lists a
    dimension where the sheet shows its number as well as where it shows the middle of its line (a
    number too long to fit stands a text length past the line it measures along, so a neighbouring
    sheet's frame can cut it without showing the dimension). The width phase reads each dimension
    back on every sheet handed over and compares the corners with the view's frame on the paper, and
    a layout the drafter lays out is trimmed round each number's corners; one method, turned view or
    not. The tool definitions move again (`cd5e8a86` to `c66b17cd`). On the 147 untwisted width
    tasks of `d1-train` kept both ways, the shown work is 25% shorter (26% at the explicit level)
    for two or three more calls a task (the median 15 to 17 at the vague level, 14 to 17 at the
    explicit), and a number is set again on 6 vague recordings where the looser box had 11, on none
    at the explicit level where it had 3. `d1-train` keeps 1,198 of 1,200 and `d1-train-hard` 294 of
    297 a level, the same tasks as before; `d1-train-twist` 600, `d1-train-crowd` 599 and
    `d1-train-revise` 600 as they were. With the new set that is 3,582 of 3,590 tasks kept a level.
    Recorded again at the commit before and compared turn for turn, results included, the 3,090
    recordings of those five sets with no width dimension are identical; only the 207 that
    dimension a width changed.
11. **Letting a seeded revision task make the change itself** (2026-11-12, build 4). **Decided 2026-11-12:
    "Yes, revision only".** `modify_alignment` and `update_labels` are shown only on a revised task's list
    (its scope carries a `revision` mark), and where the design lives in the sheet file the drafter makes
    the change, graded by D1-15 and D1-01. No board task's list or digest moves. The base file
    (`open_document` and `reload_references` in a D1 episode) was left for the pin. **Decided 2026-11-13:
    allow them, in the pin's cut**, so the drafter can make a revision where the design lives in the base
    drawing too. My proposal for the scope: shown on a revised task's list only, like the two above.
    **Built 2026-11-13** (34e494ad, a subagent's build in a worktree of its own; 1b5ce003 after an
    independent review). The revision dial has a third flavour, `revise="base-radius"`, `"base-pi"`
    or `"base-station"` (`tasks.revise.BASE_KINDS`, `annotate-base` only): the base drawing is
    handed over on the old design and the change is the drafter's to make where the design lives.
    Its truth's scope carries a second mark, `base`, beside `revision`; with both, an episode shows
    `open_document` and `reload_references`, and no other scope's tool list or definitions move
    (519 scope and mode combinations against the old `eval/tools.py`; 380 episodes of 19 other
    tasks run under the old and the new code came out identical, key order included).
    `create_alignment` is not on that list though the design is in the scope: a line of the same
    name made in the sheet file stands in front of the base drawing's and cost a right answer every
    label (41 for the whole reference solution plus that one call). `save_document` stays hidden:
    the episode writes the other document to its file after each command, as the MCP server's
    autosave does. In a D1 episode `open_document` is the harness's own tool: the same name and
    `path` as the MCP server's, with a description of its own that says what the pilots' prompt
    says of saving and of which file is graded. It reaches only the handed document and the files
    the task ships, inside the episode folder. `submit` with the base drawing open is refused with
    the way back and the episode goes on; however an episode ends, the handed document is graded
    with its references read from the files. On a truth marked `base` the verifier reads the
    design, its centerline and its edges (D1-15, D1-01, D1-12) in the base drawing through the
    reference (`verify.context.design_home`); every other truth takes the old path, and the
    verifier's version does not move.
    The route: open the base drawing, `modify_alignment` with the centerline redrawn, `draw_offset
    replace` for the edges on a radius or PI change, back to the sheet file, `reload_references`,
    take the old lettering off, restation the notes, letter again. `update_labels` in place of
    taking off and lettering again was run on all 300 tasks and left 49 short of 100 (after a
    restation the ticks and station numbers stop short of the new stations on 35, and labels come
    out upside down on 14: decision 12's guess again, judged against the revised line), so
    neither the reference nor the drafter uses it; that is decision 14 below.
    The tasks are a set of their own, so `d1-train-revise` keeps its 600 ids:
    `d1-train-revise-base`, seeds 18000-18299, 300 tasks, none skipped, 26 dialed to the next kind
    (126 restations, 99 radius changes, 75 PI moves; every kind at every curve count, 147 through
    a turned viewport). Oracle 100 and null 0 on all 300 at both levels; 300 of 300 kept a level,
    a median 20 turns and 34.5 calls (45 at most).
    Known and left: the converter keeps such an episode only when it scored 100 as it ended as
    well as replayed, because what the sheet file had read of the base drawing when is not all in
    the journal (a replay scored 100 where the episode scored 0, and the other way, on episodes
    made to show it; every stored recording reloads after its one visit and is unaffected). The
    CLI agents (`claude-code`, `codex`) answer their own `submit` before the loop can refuse it
    with the base drawing open, so the flavour is for the model routes the training uses, not
    for a CLI row. `report.tool_use`'s check prefixes and `ReplayAgent` read only the handed
    document's journal on such an episode. `HARNESS_VERSION` stays `e3-v3`: no rule changes for
    any task that existed.
12. **The labels' follow guessed a twist on an untwisted sheet** (2026-11-12, found by build 4). **Decided
    2026-11-12: "Fix it now".** `commands/label_updates.py::_view_rotation` keeps no twist when no twist poses
    every label of a set as it stands, and guesses only when it does not. Stored rows stand as recorded.
13. **A label square to its line on a twisted sheet** (found 2026-11-11, the sheet phase). `place_label` on
    a sheet takes the end the text is set from out of the model direction (`labels.label_pose`, no twist)
    and the rotation out of the paper (`labels.sheet_pose`), so through a turned viewport the text can run
    back across the line; the drafter sets it again from the other end when `get_entity` shows that.
    **Decided 2026-11-13: fix it, before the pin.** The tool list does not move.
    **Built 2026-11-13.** It was wider than the square labels: a label along its line took the edge it sits
    on from the model too, so on half the twists it sat on the line, and `above`/`below` were read in the
    model though the help says on the paper. Swept over 24 twists and ten poses, 104 of 208 sheet labels
    were set wrong, 0 after. `place_label` on a sheet now compiles the label with its viewport's twist (the
    record is unchanged: the viewport it names carries the twist), and the follow lays a sheet label out
    again the same way. The verifier's pose check takes only position and rotation from the paper; the
    text's footprint (D1-08) does follow its end, so a stored run re-verified on the new engine could move
    where a model lettered a twisted sheet without giving the end. Stored rows stand as recorded. The
    reference passes its ends explicitly, so the oracle is 100 on all six held-out and dev sets, and every
    training manifest is current. On `d1-train-twist`'s 133 layouts, 33 recordings lose
    the turn that set a match-line label again (206 calls and 68 turns fewer), all 133 still kept.

14. **The labels' follow after a revision in the base drawing** (2026-11-14, found recording
    `d1-train-revise-base`). `update_labels` set 251 of 300 sheets right after the base drawing was
    revised; the drafter set the rest by hand. A fix is built on `training/dec14-update-labels`
    (`219feed7`): 300 of 300, 35 new tests, and two `d1-train-revise` task ids change (seeds 15239 and
    15436). **Not in the pin** (2026-11-14, under "nothing that affects a score already run"): a stored
    `hard-pilots` row that called `update_labels` could replay differently. To decide after the base
    rerun; taking it then means recording those two tasks again.

## 7. Risks

| risk | guard |
|---|---|
| The grounded recorder takes longer than planned | build by phase; ship T0 and a first dataset on the simple task types before the whole-sheet types |
| Imitating a solver that never errs makes a model that cannot recover | injected faults in T1; the subject's own passes in T2 |
| The model learns the generator's layouts, not drafting | `d1-real` as the transfer test, `d1-real-dev` in validation; twisted seeded sheets in training (`d1-train-twist`, built 2026-11-11) |
| Training text differs from what the server sends (tool-call syntax, thinking) | the smoke's byte-for-byte check before any full run |
| Contamination | the disjointness test; the dataset card lists every source run and seed range |
| Cost drift on long sequences | the smoke measures tokens a second and memory before T1 is priced |

## 8. The hard pilots as a training target (2026-11-11)

Robert, Nov 11: "should also focus on the hard pilots since those have the largest room for improvement."
Until now this plan held the pilots as a guard. This section makes them a target.

**Where the set stands.** 112 pilots, each pass or fail; 89 are text only and 23 come with a scanned or
marked-up page. Pilots passed at the vague level, k = 1:

| family | pilots | with a page | Opus 5.5 | Terra | Sonnet 5.5 | Luna | what the best row misses most |
|---|---:|---:|---:|---:|---:|---:|---|
| p17 twisted sheet | 15 | 0 | 3 | 0 | 0 | 0 | lettering over other lettering or upside down; station ticks |
| p04 crowded annotation | 13 | 0 | 0 | 0 | 0 | 0 | the same legibility item, on 12 of 13 |
| p11 redlines with knock-on edits | 12 | 0 | 1 | 0 | 0 | 0 | stale lettering left behind, on 8 |
| p18 redline understanding | 10 | 10 | 2 | 1 | 1 | 0 | something unrelated changed, on 6 |
| p14 QA review | 9 | 0 | 4 | 1 | 2 | 0 | a planted error missed, or one marked on the clean sheet |
| p02 sources that disagree | 8 | 0 | 8 | 8 | 8 | 1 | |
| p05 sheet breaks | 8 | 0 | 3 | 3 | 0 | 0 | the number of sheets |
| p15 plan reading | 8 | 8 | 6 | 6 | 6 | 2 | |
| p03 survey traps | 7 | 0 | 7 | 6 | 3 | 0 | |
| p13 striping | 6 | 0 | 5 | 3 | 4 | 0 | |
| p01 redraw from a scan | 5 | 5 | 5 | 4 | 3 | 0 | |
| p06 plan and profile | 5 | 0 | 1 | 0 | 0 | 0 | plan stations not lined up with the profile |
| p10 typical section | 5 | 0 | 0 | 0 | 0 | 0 | a dimension or slope label missing |
| p12 plan set | 1 | 0 | 0 | 0 | 0 | 0 | |
| all | 112 | 23 | 45 | 32 | 27 | 3 | |

The subject, the 9B, passes 3 of 112 at the explicit level (one p02, two p14); its vague run is in the local
queue. So the room is about 97 points of 100 for the subject and 60 for the best row.

**What cannot be training data.** The 112 instances and their scripted solutions. I would add every task on
a sheet a held-out pilot uses, even with other parameters: such a task shows the model that sheet's lines and
their right lettering. The pilots use 42 redrafted sheets. Of the 67 redrafted sheets that carry an
alignment, 37 are in a pilot and 51 in `d1-real` or `d1-real-hard`; 9 are in no pilot, no real-sheet set and
not a dev sheet (PPM-206, 207, 214, 215, 218, FDOT-924, the CFL parking-lot SWPPP sheet, WFL Other Sections
p06 and p09). That is decision 7.

**How the families are built** (survey of `probes/pilot`, 2026-11-11). No family has a seed or a random
parameter. `p17`, `p05`, `p13`, `p06` and the deed half of `p03` take a new instance from parameters alone;
`p04` and `p11` from a few lines of per-sheet configuration; `p01`, `p02`, `p12`, `p14`, `p15` and `p18` need
hand work for each new sheet. A probe added to the pilot package joins the held-out set and moves its
hashes, so anything new is registered outside it.

**The proposal: carry the pilots' skills on generated sheets, and keep all 112 as the test.** That is the
`d1-real` claim again, trained on generated centerlines and tested on agency sheets, and it reuses the
grounded drafter. In the order I would build:

| build | pilots it bears on | also serves |
|---|---|---|
| 1. The sheet and viewport phase of the drafter, with the drafter choosing the sheet count and breaks. **The phase is built 2026-11-11** (Robert: "Yes, start it") for sheets and breaks the task gives; choosing the count and the breaks is open (decision 8) | `p05` (8) | the four seeded types not covered yet; it was the next step anyway |
| 2. A twist dial on the seeded generator: the viewport turned, labels reading upright through it. **Built 2026-11-11** (Robert: "Twist dial first"); see the status above | `p17` (15) | `d1-real`, where 77 of 100 tasks are twisted and no seeded task was |
| 3. A clearing step in the drafter (read back its lettering's boxes, find what overlaps, set it again clear), and seeded sheets with several lines. **Built 2026-11-12** (Robert: "Clearing step") for one line lettered among lettering that is given; see the status above | `p04` (13), the legibility misses of `p17` | D1-08 wherever a sheet shows other lettering. Not `d1-test`, where a sheet shows one line |
| 4. A revision task on seeded sheets: a finished sheet, one design change (a radius, the begin station, a PI), everything downstream re-lettered and nothing stale left. **Built 2026-11-12**: the drafter makes the change where the design is in the sheet file (decision 11), and re-letters after it where it is in a base drawing | `p11` (12) | |
| 5. Later, generators for the reasoning families that need none of the sheets: a deed to close (`p03`), planted errors to find (`p14`) | 16 | |

Builds 1 to 4 bear on 48 of the 112 pilots. That is the number of pilots addressed, not a forecast of
passes. The 23 pilots with a page stay out of training for now.

Build 2 is done, and so is the sheet and viewport phase of build 1 (the status of 2026-11-11, night): 516
more tasks a level are recorded, 281 of the 283 layout tasks of `d1-train` and `d1-train-twist` and 235 of
`d1-train-hard`, recorded for the first time. What is left of build 1 is the drafter choosing how many
sheets a line takes and where they break, which no seeded task asks yet (decision 8). The 207 width tasks
are recorded since 2026-11-12, night (206 kept a level), untwisted, and through a turned view since
2026-11-13 (`d1-train-twist-widths`, decision 9). What build 2 does not reach in `p17`: the
pilots' sheets carry other lines and published lettering, and what the best row misses there is new
lettering over other lettering as well as lettering upside down. The first of those is build 3, built
2026-11-12 (the status above): `d1-train-crowd`, 600 crowded sheets, 534 recorded a level, then 592 once
labels were measured by their true sizes (2026-11-12, night). Build 4 followed the same day:
`d1-train-revise`, 600 revised sheets, all 600 recorded a level. Every seeded type is now covered: 3,284 of
3,297 tasks kept a level. Build 5 (the reasoning families) was built 2026-11-13 as `train-deeds` and
`train-qa` (status of 2026-11-14); the open half of build 1 is left.

**A validation set on real sheets.** `pilot-dev`: `p17`, `p04`, `p05` and `p11` instances on the 9 clean
sheets, registered outside the pilot package. For choosing a checkpoint only, like `d1-real-dev`.
**Built 2026-11-13** (`src/roaddraft/probes/pilot_dev.py`, `benchmarks/tasksets/pilot-dev.json`): 19
instances, 6 `p17`, 2 `p04`, 6 `p05`, 5 `p11`, every one of the 9 sheets used (18 on 8 sheets since
2026-11-14: the CFL SWPPP sheet shares its design line with a `d1-real` and a `hard-pilots` task, so
`p05-dev-cflpkg` was dropped; set hash `probe-00949a4813fb`); what each sheet could not
carry, and where an instance is weaker than its held-out counterparts, is in the module's docstring.

**One thing the base rerun will show first.** Of the 59.8 points the best row loses on the pilots, 9.8 are
`annotate_stationing` failing and never working, on the tool surface the board's rows ran. Main has had the
stationing hint since Nov 4. The base rerun on the training pin measures how much of that comes back with no
training.
