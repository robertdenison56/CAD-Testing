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
3. **The converter and the dataset card**: episode files to chat-template conversations, with the tool digest,
   prompt hash, spec, generator and verifier versions in the header, and the token histogram that sizes T1.
4. **T0's two pieces**: the convention sheet and the `--system-extra` flag. Ready to queue when the local hard
   sets finish (about Nov 15).

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

## 6. Decisions for Robert

1. **The rig for base, T0 and checkpoints.** PC only: free, one to one and a half nights per 100 episodes, and
   each checkpoint needs merging and a Q4_K_M GGUF conversion. Runpod bf16 on vLLM: minutes and a few dollars a
   set, the rig the Cost Plan assumed. I recommend Runpod for the loop, since training has to rent a card anyway,
   and a GGUF copy of the final checkpoints for a local board row.
2. **A budget line for training.** The $71 left of November's $100 is set aside for the large-model queue.
   Through a first trained row I estimate $30-60 on top (smoke, T1, lean evals).
3. **The pin.** A new one from main with the base rerun on it (recommended), or the board's `0334fd4a`.
4. **Frontier teacher data**: leave out (recommended) or check the terms.
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
   hold.

7. **What may train the pilots** (2026-11-11, §8). Keep every sheet a held-out pilot uses out of training
   (recommended; training is then on generated sheets and the pilots stay a transfer test), or allow new
   parameters on the same sheets (cheap for five families, and the model has then seen the test's sheets).
8. **A seeded task that leaves the sheet breaks to the drafter** (2026-11-11, the open half of build 1). It
   needs a new task type whose prompt gives no breaks and a check that takes any sound set of them, as the
   `p05` grader does from the plotted sheets; the D1 sheet check grades against the generator's own breaks.
   Build it as a training-only type with a check of its own (recommended: no board set or id moves), or
   leave `p05` to transfer from the stated-break layouts.
9. **Width dimensions through a turned viewport** (2026-11-11). `place_dimension` has no `view_rotation`;
   giving it one moves the tool surface. Until then the three width types stay untwisted, and they are the
   207 tasks the drafter does not cover.
10. **What the engine tells a drafter about lettering that collides** (2026-11-12, the clearing step). Today
    nothing: a text is reported by its box on the model's axes, and a model that cannot look at a render has
    to work out the rest. The three ways on:
    - Leave the surface as it is. The step is built on it and 534 of 600 crowded recordings are kept. The
      cost is calls, and a method a model has to learn.
    - Let the listing of what a sheet shows carry each text's four corners on the paper. One read then
      replaces steps 1 and 2. It moves the tool surface, so every board row ran without it.
    - A query that lists the pairs that collide on a sheet. That hands over the verifier's own answer; I
      would not.
    I recommend the second, in the same cut as a new pin if decision 3 goes that way, and the first until
    then.
11. **Letting a seeded revision task make the change itself** (2026-11-12, build 4). **Decided 2026-11-12:
    "Yes, revision only".** `modify_alignment` and `update_labels` are shown only on a revised task's list
    (its scope carries a `revision` mark), and where the design lives in the sheet file the drafter makes
    the change, graded by D1-15 and D1-01. No board task's list or digest moves. The base file
    (`open_document` and `reload_references` in a D1 episode) is still open, for the pin.
12. **The labels' follow guessed a twist on an untwisted sheet** (2026-11-12, found by build 4). **Decided
    2026-11-12: "Fix it now".** `commands/label_updates.py::_view_rotation` keeps no twist when no twist poses
    every label of a set as it stands, and guesses only when it does not. Stored rows stand as recorded.

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
sheets a line takes and where they break, which no seeded task asks yet (decision 8); the 207 width tasks
wait on the width dimensions. What build 2 does not reach in `p17`: the pilots' sheets carry other lines and
published lettering, and what the best row misses there is new lettering over other lettering as well as
lettering upside down. The first of those is build 3, built 2026-11-12 (the status above): `d1-train-crowd`,
600 crowded sheets, 534 recorded a level. Build 4 followed the same day: `d1-train-revise`, 600 revised
sheets, all 600 recorded a level. Build 5 (the reasoning families) and the open half of build 1 are left.

**A validation set on real sheets.** `pilot-dev`: `p17`, `p04`, `p05` and `p11` instances on the 9 clean
sheets, registered outside the pilot package. For choosing a checkpoint only, like `d1-real-dev`.

**One thing the base rerun will show first.** Of the 59.8 points the best row loses on the pilots, 9.8 are
`annotate_stationing` failing and never working, on the tool surface the board's rows ran. Main has had the
stationing hint since Nov 4. The base rerun on the training pin measures how much of that comes back with no
training.
