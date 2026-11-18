# Track D: what the board found

Track D closed on 2026-11-16 (Robert). This is the summary to come back to: what was measured, what it showed,
what was retired or dropped on the way, and what was left open. Every number is from the files named in
[Where things are](#where-things-are) as they stood at the close.

Track D asked one question (research plan, phase B): **how well can a model draft a roadway plan sheet in RoadDraft
when it is asked the way a PE would ask, in a sentence?** The deliverable was the headline number, best model X/100
with its interval, and a taxonomy of why models fail.

## The answer

| Set | What it is | Best model | Score | 95% CI |
|---|---|---|---:|---|
| `d1-test` | 100 seeded sheets, one task each | GPT-6 Astra | 96.6 | 96.1–97.1 |
| `d1-real` | 100 tasks on the redrafted sample plan sheets | GPT-6.1 Terra | 90.5 | 87.9–93.1 |
| `d1-test-hard` | 100 seeded whole-sheet jobs | Claude Opus 5.5 | 93.7 | 93.1–94.3 |
| `d1-real-hard` | 100 whole jobs on the sample sheets | Claude Opus 5.5 | 77.6 | 72.7–82.3 |
| `hard-pilots` | 112 harder tasks, pass or fail | Claude Opus 5.5 | 40.2 (45 of 112) | 33.9–46.4 |

Overall, the weighted mean of the five sets (the real sheets and the hard pilots count double), for the six models
with a full run on every set:

| # | Model | Overall | ± | `d1-test` | `d1-real` | `hard-pilots` | `d1-test-hard` | `d1-real-hard` |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | Claude Opus 5.5 (claude-code, medium) | **74.8** | 2.2 | 95.5 | 86.7 | 40.2 | 93.7 | 77.6 |
| 2 | GPT-6.1 Terra (codex, medium) | **71.0** | 2.0 | 92.8 | 90.5 | 28.6 | 92.9 | 72.1 |
| 3 | Claude Sonnet 5.5 (claude-code, medium) | **53.8** | 1.9 | 76.0 | 75.1 | 24.1 | 54.5 | 50.8 |
| 4 | GPT-6 Luna (codex, medium) | **46.3** | 1.7 | 76.1 | 71.8 | 2.7 | 43.2 | 51.0 |
| 5 | Gemma 4 12B (local, Q8) | **32.9** | 1.5 | 67.2 | 59.0 | 0.0 | 3.0 | 37.5 |
| 6 | Qwen3.5-9B (local, Q4_K_M) | **32.5** | 1.7 | 62.6 | 59.6 | 0.9 | 9.4 | 33.5 |

Every score is at the vague prompt, single mode (no self-correction, no page images beyond what a task ships),
one sample a task. The board ranks 45 rows on the five sets, 4,859 episodes.

## What it showed

1. **The seeded sheets are nearly solved at the top; the real sheets and whole jobs are not; the harder tasks are
   far from it.** The best two or three models score 93 to 97 on both seeded sets. The sample plan sheets take 2 to
   9 points off the best two (Terra 90.5, Opus 86.7), the whole jobs on them another 9 to 18 (Opus 77.6, Terra
   72.1), and the best model passes 45 of 112 hard pilots. The benchmark's headroom is in `d1-real-hard` and
   `hard-pilots`.

2. **What the best models lose on a D1 sheet is drafting standards they were not told, almost nothing else.** Of
   Opus's 4.5 lost points on `d1-test`, 4.3 are a convention not applied with no failed attempt at it; Terra 6.4 of
   7.2; Astra 3.3 of 3.4. On `d1-real` it is 10.7 of 13.3 for Opus and 8.6 of 9.5 for Terra. Their tool use loses
   0.0 to 0.7 points. A vague-prompt score at the top is a measure of drafting knowledge, not of agent skill.

3. **Telling the model the standards gets most of those points back.** Where the same model ran the explicit prompt
   on the same harness and tools, the standards it lost at the vague prompt were mostly earned when told
   (`eval standards`): Luna 18.2
   of 20.8 on `d1-test`, Opus 14.4 of 15.1 and Sonnet 36.2 of 41.8 on `d1-real-hard`, Terra 5.1 of 6.0 on
   `d1-test-hard`. The small local models recover less (the 9B 21.2 of 32.7 on `d1-test`, Gemma 12B 13.6 of 26.3):
   for them part of the loss is not knowing the standard and part is not managing it even when told.

4. **Below the frontier the loss shifts to reasoning and tool use.** The 9B loses 16.1 points to standards and 16.1
   to reasoning on `d1-test` (5.3 to tool use); Gemma 12B 10.9 and 18.0; GLM-4.6V-Flash, the third local model, loses 35.0 to
   tool use and 34.5 to reasoning and submits with nothing drawn on about a fifth of its tasks. On the whole-sheet
   jobs the small models hard-fail most tasks (`d1-test-hard`: the 9B 65%, Gemma 12B 90%).

5. **On the hard pilots the cause is reasoning, even for the best.** Opus's 59.8 lost points are 33.9 reasoning,
   15.2 standards (all earned back when told) and 10.7 tool use; Sonnet's 75.9 are 56.3 reasoning; Luna's 97.3 are
   75.0 reasoning. The rubric column tells the same story from the other side: Opus does 85.8% of the items across
   the pilots and passes 40.2% of them, since one wrong item fails a pilot.

6. **The hard pilots split by family, not evenly.** Passes of the top three (Opus / Terra / Sonnet):

   | Family | Pilots | Opus | Terra | Sonnet |
   |---|---:|---:|---:|---:|
   | p02 sources that disagree | 8 | 8 | 8 | 8 |
   | p15 plan reading | 8 | 6 | 6 | 6 |
   | p01 redraw an alignment from a scan | 5 | 5 | 4 | 3 |
   | p03 survey traps | 7 | 7 | 6 | 3 |
   | p13 striping with no-passing zones | 6 | 5 | 3 | 4 |
   | p14 open-ended QA review | 9 | 4 | 1 | 2 |
   | p05 the model picks the sheet breaks | 8 | 3 | 3 | 0 |
   | p17 twisted variants | 15 | 3 | 0 | 0 |
   | p18 redline understanding (a marked-up PDF) | 10 | 2 | 1 | 1 |
   | p06 plan and profile on one sheet | 5 | 1 | 0 | 0 |
   | p11 redlines with knock-on edits | 12 | 1 | 0 | 0 |
   | p04 crowded annotation | 13 | 0 | 0 | 0 |
   | p10 typical section from a description | 5 | 0 | 0 | 0 |
   | p12 a small full plan set | 1 | 0 | 0 | 0 |

   Finding the right source and reading a plan are solved. Crowded and twisted annotation, typical sections,
   plan and profile, and redlines with knock-on edits are passed almost never (5 of 50 for Opus, 0 of 50 for the
   other two).

7. **Open-weight models in the 26B to 120B class match the mid frontier on the seeded sheets and fall off the hard
   pilots.** On `d1-test`: Nemotron 3.5 Super VL 82.4, Gemma 4 31B 80.1, Qwen3.6-35B 76.3, level with or above Luna
   (76.1) and Sonnet (76.0); gpt-oss-120b 70.3, GLM-5.3 66.5, Mistral Small 4 64.0. On `hard-pilots` the best of
   them, Qwen3.6-35B, passes 8.0%, and nine of the twelve rows pass under 10%. Their D1 loss is standards (15.6 of
   17.6 for Nemotron, 17.4 of 19.9 for Gemma 31B), like the frontier's.

8. **The explicit prompt hides the differences that matter.** With every standard stated, Terra scored 95.4 to 98.5
   on all four D1 sets and Opus 96.1 and 98.5 on the two hard ones; with self-correction both reached 99.8 to 100.0
   on `d1-test` and `d1-real`. At the vague prompt the same two models run from 72 to 96. The gap between the two
   prompts grows with the
   job: Opus 98.5 explicit against 93.7 vague on `d1-test-hard`, 96.1 against 77.6 on `d1-real-hard`, 61.6 against
   40.2 on `hard-pilots`; Sonnet 90.8 against 54.5 and 84.5 against 50.8 on the two hard D1 sets. This is why the
   vague prompt became the board's focus on Nov 8 and the explicit board was retired at the close.

9. **The base for training is known.** Qwen3.5-9B at the vague prompt: 62.6, 59.6, 9.4, 33.5 and 0.9 on the five
   sets, 32.5 overall. Its lost points say what a trained checkpoint has to learn: the drafting standards a vague
   prompt leaves out (the largest cause on the two hard D1 sets, 56.3 and 44.1 points, and level with reasoning on
   `d1-test`), reasoning on the real sheets (22.5 points on `d1-real`), and finishing a whole sheet without a hard
   fail.

## How it was measured

- **Sets.** Five held-out sets (above); a row ranks only when its run covers every task of its set with no episode
  in error. Each task has a vague prompt (the request in a sentence) and an explicit one (every standard stated).
- **Score.** Effective score: 0 on a hard fail, else the rubric score, per task; the mean over tasks with a 95%
  bootstrap interval over tasks within task type. A pilot is 100 on a pass and 0 on a fail by its own check.
- **One sample a task** (k = 1) on every row (Robert, Nov 4: no k = 5 anywhere).
- **Versions.** Harness `e3-v3`, verifier `d1-verify-v8`, generator `d1-v6` (the seeded sets), spec v1. The run code is pinned and
  tagged: 3b7e7fe9 (the frontier and local D1 rows), `pin/trackd-runpod-queue1` and `pin/trackd-runpod-queues2-7`
  (the Runpod rows), `pin/trackd-local-hard-pilots` (the pilot rows).
- **Routes.** Claude models through the Claude Code CLI and GPT models through the Codex CLI, both at medium
  effort; the local models through LM Studio on the PC's two RTX 4060s at the largest context that fits; the
  larger open-weight models on Runpod serverless (vLLM) or its public endpoints.
- **Causes.** `eval causes` gives every lost point one cause from the trajectory (standard, tool use, reasoning,
  budget), and `eval standards` splits the standards by whether the model's explicit run earned them. The final
  pass over all 51 published vague runs ran at the close (`benchmarks/runs/FAILURE_CAUSES.md`). No score and no
  cause comes from a judge model.

## Caveats to carry

- **`hard-pilots` misses the 5-point interval target.** Its leading row's half-width is 6.2 points (33.9 to 46.4);
  the leading rows of the four D1 sets are under 5. A pass-or-fail set of 112 cannot reach 5 at k = 1, and it was
  not rerun.
- **The seeded-set rows ran before the names were in the document.** Every `d1-test` and `d1-test-hard` vague row
  ran on pinned code from before the seeded documents carried the title block's four names and date (234773ec,
  Nov 12), which a vague prompt does not state. It costs a row 0.3 to 0.95 points on `d1-test` and 1.3 to 1.55 on
  `d1-test-hard` and reorders nothing; the rows stay ranked (board note).
- **Astra has one set.** GPT-6 Astra leads `d1-test` and has no other finished set: its `d1-real` run stopped at 49
  of 100 on the ChatGPT account's weekly limit. See [Still open](#still-open-at-the-close).
- **Gemma 12B's pilot row had stalls.** Eight pilots ended on the 30-minute turn limit and were rerun once; four
  did so again and stand as fails. The row is 0 of 112 either way (board note).
- **Cost-subset rows are not full rows.** The Runpod rows on `d1-real` and the two hard D1 sets ran five tasks of
  each task type to save cost; they rank in a table of their own beside the full runs re-scored on the same tasks,
  and those models have no overall score.
- **Open-weight pilot failures are mostly unresolved by cause.** Those models have no explicit run of the pilots, so
  a failed pilot with no tool fault cannot be split between standards and reasoning (40 to 78 of the 92 to 99
  points each loses).
- **Some explicit-versus-vague pairs are not same-surface.** Terra's and Sonnet's explicit `d1-test` and `d1-real`
  rows ran on the earlier harness (`e3-v2`) and tool surface; `eval causes` pairs a vague run only with an
  explicit twin on the same harness and tools, so those pairs are not in finding 3.

## What ran, what was retired, what it cost

- **Ran:** 45 ranked vague rows (d1-test 14, d1-real 7, hard-pilots 12, d1-test-hard 6, d1-real-hard 6), four
  cost-subset tables, 4,859 episodes; before the retirement, 40 ranked explicit rows and 4,196 episodes more.
- **Retired** (`benchmarks/runs/RETIRED.md`): 34 rows on Nov 3 (the harness and tool-help fixes changed what they
  recorded), 2 on Nov 10 and 5 on Nov 13 (superseded or duplicated by a rerun), and the explicit-prompt board with
  its 40 rows on Nov 16 (retired with its board, not for a fix).
- **Dropped:** tool-name skins (Oct 30); the 4B and Sol rows (Oct 31); GLM-4.6V-Flash on the hard sets (Nov 10);
  Kimi K2.6 (Nov 16: its smoke returned empty replies on the public route, never diagnosed, no row).
- **Runpod:** five queues, $150.27, for the open-weight rows. The two never-run endpoints (`d1aaw4ddzlsghg`,
  `7maayov2g1xjoi`) were deleted at the close; 13 remain, parked at 0 workers.
- **Frontier:** through the subscription CLIs. Priced at list API rates, Opus costs $0.37 a `d1-test` sheet,
  $0.76 on `d1-real`, about $1.00 a whole job and $1.20 a pilot; Sonnet about half that.

## Still open at the close

- **GPT-6 Astra's remaining sets.** The queue is re-armed to start when the account limit resets (Nov 20, 22:34):
  `d1-real` (resumes at 49 of 100), then `d1-test-hard`
  (`results/e3-codex/queue-2026-11-16-astra-vague-codex-rearm.sh`). Each publishes itself and is appended to the
  board; `d1-real-hard` and `hard-pilots` are not queued. Astra has an overall score only with all five.
- **Three harness bugs on main, not fixed** (they did not change a published score; the pinned run code has them
  too): `traverse` raises on an escaped bearing instead of failing the call; `save_journal` into a folder raises;
  `find_entities` crashes on an anchor filter holding a null value.
- **Three vague-brief calls on the pilots, not made:** p05 keeps its scale and border, p12 names Caltrans and does
  not ask for the total sheets, p06's vague check reads the grid datum from the elevation lettering.
- **Carried into phase C or the backlog:** re-recording the trajectories on the merged engine and two verifier
  items (annotation sizes in the redraft files; traced lettering near the lettered alignment); the `d1-variance`
  reverify under v8.
- **Not run:** Qwen3.5-122B (endpoint parked), a Gemma 26B pilot rerun with an output cap.

## Where things are

| What | Where |
|---|---|
| The board (generated) | `benchmarks/runs/LEADERBOARD.md`, `leaderboard.json`, `leaderboard.svg`, the README block |
| The board's hand-kept notes | `benchmarks/runs/BOARD_NOTES.json` |
| Each published run | `benchmarks/runs/<run id>/` (summary, report, heatmap); raw episodes in `results/e3-*/<run id>/` |
| Causes, every vague run | `benchmarks/runs/FAILURE_CAUSES.md`; per run, `results/e3-*/<run id>/report/causes.md` and `standards.md` |
| Retired rows and the explicit board | `benchmarks/runs/RETIRED.md`; folders in `results/_retired-*/published/` |
| Board and report code | `src/roaddraft/eval/report.py`, `scripts/make_leaderboard.py` |
| Cause analysis | `src/roaddraft/eval/causes.py`, `src/roaddraft/eval/standards.py` |
| Local, Runpod and CLI run records | `benchmarks/lmstudio/`, `benchmarks/runpod/` (PLAN.md, README.md), `results/e3-*/queue-*.sh` and `.log` |
| The eval dashboard and the research tracker | artifacts `Vr9ftxKwjEbAEfiqnPjxqi` and `G2QQus7JPAhLhUCBBSDupJ` |
