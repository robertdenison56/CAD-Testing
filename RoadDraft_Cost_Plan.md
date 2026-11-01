# RoadDraft cost plan: the rest of the project (drafted 2026-10-28 evening)

Robert, Oct 28 evening: "im ok with removing the local only rule once everything gets nailed down and working
first. plan the costs out through the rest of the project, self testing, K=5 etc." This file prices every paid run
and training step from here to the writeup, in the order the build plan runs them (`RoadDraft_Build_Plan.md` §4:
Phase B Track D, C training data and SFT, D RFT and RL, E publish). Dollars are Runpod unless marked; the PC's
nights are free and slow. Nothing in this file is a go: each stage waits on Robert, and the local-only rule of
Oct 24 holds until Stage 0 is through. Robert, Oct 28 22:45: Track D is pushed through locally first (about 22 PC
nights, `benchmarks/lmstudio/PLAN.md`); the Runpod stages start after that. The Runpod model tree and the rig are `benchmarks/runpod/PLAN.md`; the local
rig is `benchmarks/lmstudio/PLAN.md`; the eval design is `RoadDraft_Eval_Plan.md`.

## 1. What a run costs

**Self-hosted rows** bill worker time (one worker, four episodes at once). The per-episode figures are the Track P
k = 3 campaign's bill over 99 episodes (Oct 17-18) and lean high: the Oct 20 d1-variance runs came in under them.

| rung | $ per d1-test episode | 100 episodes |
|---|---|---|
| gpt-oss-20b (A40 $1.22/h) | 0.012 | $1-2 |
| Qwen3.5-4B ($0.69/h) · Qwen3.5-9B · Gemma 4 12B ($1.22/h) | 0.023 · 0.050 · 0.044 | $2-3 · $4-6 · $4-6 (local rows; the 9B figure prices the subject's checkpoints) |
| Qwen3.6-35B-A3B ($3.49/h) | 0.048 | $5-8 |
| GLM-4.7-Flash ($3.49/h) | 0.070 | $7-9 |
| Gemma 4 26B-A4B ($2.72/h) | 0.085 | $8-10 |
| Gemma 4 31B ($3.49/h) | 0.119 | $10-14 |
| Qwen3.8-27B ($2.72/h, thinks at xhigh) | 0.161 | $14-18 |
| gpt-oss-120b · Qwen3.5-122B-A10B FP8 (never run; estimates) | ~0.05 · ~0.085 | $4-6 · $7-10 |

**Per-token rows** (Runpod's public endpoints, any API) bill tokens, and this harness resends the transcript every
turn, so an episode sends 0.6 to 1.0 million cumulative input tokens on d1-test (1.5M on d1-real, 2.7M on the
pilots) and writes 10 to 22 thousand. The input rate and the provider's prompt cache set the price.

| row | rate per M tokens (in / cached in / out) | 100 d1-test episodes |
|---|---|---|
| GLM-5.3, Runpod public endpoint `b1dd8hy2hqo1nb` | 0.77 / 0.143 / 2.42 | $20-35 cached, $50-85 not |
| Claude Haiku 5.5, API (list, `prices.json`) | 0.10 / 0.01 / 0.50 (0.50 / 2.50 past 100k) | $3-8 |
| Claude Sonnet 5.5, API | 2.00 / 0.20 / 10.00 | $60-100 with the harness's caching, about 3x without |
| Claude Opus 5.5, API | 4.00 / 0.20 / 20.00 | $120-190 |
| Claude Fable 5.1, API | 10.00 / 0.25 / 50.00 | $330-520 |
| Claude or Codex through the CLI route (`--provider claude-code` / `codex`), a subscription | $0 marginal | days of usage windows a row (Track P's k = 3 took several per model) |

**Multipliers**, to be measured on the first run of each kind and corrected here:

| what | x a d1-test single row | why |
|---|---|---|
| k samples | x k | each sample is a full pass over the set |
| `d1-real` x 1 | 1.4 | real sheets carry more linework; episodes ran 1.4x longer on the 9B |
| `hard-pilots` x 1 (33 tasks) | 1.0 | 33 episodes at 3x the length (Track P budgets, 30 min); the nine page pilots need a vision model |
| self-correct mode | 1.4 | `run_check` up to 3 uses and `render_sheet`: more turns, each resending a longer transcript (assumption) |
| vision mode | 1.6 | self-correct plus the PNG as an image each render, 1-2k tokens a render (assumption) |
| vague prompt level | 1.0 | the same tasks at the other level; the prompt gap is paired by task |
| ~~a dialect skin (`c3d`, `ord`)~~ | – | *dropped 2026-10-30 (Robert): no run renames the tools; the stage and package totals below still count the skins* |

The interval: d1-variance sized d1-test's 95% half-width at about 4.3 (k = 1), 3.2 (k = 3) and 2.9 (k = 5) for a steady
model (Qwen3.6) and 6.0 / 4.0 / 3.5 for a noisy one (Gemma 12B). RQ2 wants under 5, so k = 1 does it for a steady row and
k = 3 for a noisy one; k = 5 is for resolving a training delta of a few points on the subject (RQ3 wants non-overlapping
intervals between a checkpoint and its base), where the 9B's price makes it cheap.

## 2. The stages

**Stage 0, the gate ("nailed down and working first"), $6-12.** The local nights finish and publish (Gemma 4 12B,
GLM-4.6V-Flash, the 4B; queue 4's reruns of the silent-turn episodes). The stall guard is on main (31774181). Then, from
`benchmarks/runpod/PLAN.md`: re-pin the campaign worktree to current main; score Runpod's 570 s stream cut-off as a
`turn_time` budget trip, not an error; `MAX_MODEL_LEN` 131072 per endpoint where the card has room; redeploy the two
big rungs if they are in; the GLM-5.3 smoke (`e3-smoke glm-5.3`, five d1-dev episodes, $1-4) for its cached share and
its stream; and one dress rehearsal, Qwen3.6-35B-A3B on d1-test x 1 ($5-8), carried through `warm`, `e3`, `workers 0`,
`report --publish` and `make_leaderboard` before any other paid row. Robert lifts the local-only rule when that row is on
the board and nothing had to be done by hand.

**Stage 1, the spread, $60-93 more.** The rest of set A: Gemma 4 31B, Qwen3.8-27B, Gemma 4 26B-A4B, GLM-4.7-Flash
($39-51), GLM-5.3 capped at $40 ($20-40), gpt-oss-20b ($1-2). With Stage 0, the $110: ten d1-test rows (seven Runpod,
three local), one past a single card. Optional: gpt-oss-120b and the 122B, $11-16.

**Stage 2, self-correct ("self testing"), $40-56.** d1-test x 1 in self-correct mode on the three best open rows
(Qwen3.6 $7-11, Gemma 31B $14-20, Qwen3.8-27B $20-25). The report pairs it with the single row by task: the
self-correct gap, the eval plan's second headline column. GLM-5.3 in self-correct is $30-50 cached, optional. The local
rows run it on PC nights for free (one night a model).

**Stage 3, k = 5 where the interval matters, $85-113.** Four more samples of d1-test single on the top two open rows
(Qwen3.6 $20-32, Gemma 31B $40-56) and five samples of the subject's bf16 baseline (Qwen3.5-9B on vLLM, 500 episodes,
$25; the rig every checkpoint will run on, not a duplicate of the local Q4 row, Robert's call). Qwen3.8-27B at k = 5
is another $56-72 if its interval overlaps a neighbour's; k = 3 ($28-36) is the cheaper read. GLM-5.3 stays at k = 1.

**Stage 4, the other two boards, $60-80.** `d1-real` x 1 on the three best open rows ($7-11, $14-20, $20-25) and
`hard-pilots` x 1 on the two that take images (Gemma 31B $12-15; Qwen3.6 $5-7 for the 24 text pilots if it has no
vision). GLM-5.3 on both: $43-70 cached, optional. This is what makes the real-sheet board and the pilot board a ranking
instead of one local row each.

**Stage 5, the paired gaps, $85-115.** On the top two open rows and the 9B baseline: the vague prompt level on
d1-test ($5-8, $10-14, $5), the two dialect skins ($10-16, $20-28, $10) and vision mode on the two with vision
(Gemma 31B $16-22, 9B $8). Prompt gap, transfer gap and the vision column, each paired by task. Track X (the transfer
gap on every checkpoint) reuses this on each checkpoint in Stage 7.

**Stage 6, the frontier rows, $0-40.** Sonnet 5.5, Opus 5.5 and GPT-6.1-Sol through the CLI route on the
subscriptions: no bill, days a row, one at a time (a Plus account answers parallel runs with 429s). Haiku 5.5 through
the API as the one priced frontier control: $3-8 at k = 1, $15-40 at k = 5. Sonnet through the API at $60-100 a row only
if the CLI route proves too slow. Fable and Opus through the API are not planned ($120-520 a row).

**Phase B total (Stages 0-6): $335-510**, of which the $110 covers Stages 0 and 1. Lean path, Stages 0-3 only:
$190-275. Wall time on Runpod: Stage 1 a day or two, Stages 2-5 a day each when the pools have stock.

**Phase C, training data, $0.** Reference trajectories for the 500+ generated tasks and the probe families are recorded
through the server on the Mac's CPU; the verified rollouts come from runs already paid for; the expert sessions are
Robert's hours. Re-recording after the engine branches merge is CPU time.

**Stage 7, the checkpoints (Phases C and D).** Every checkpoint is served the same way (the LoRA merged into bf16,
pushed to the Hub, the vLLM worker on an A40 at $1.22/h) and evaluated with the same package, so the deltas are
read on one rig:

| checkpoint eval package | episodes | cost |
|---|---|---|
| lean: d1-test k = 5 single + d1-real x 1 | 600 | $30-35 |
| full: lean + hard-pilots + the two skins (Track X) + vision mode + self-correct | 1,100 | $55-65 |

| step | compute | cost | with its eval |
|---|---|---|---|
| T0, prompt-only (the convention sheet in the system prompt, no weights changed) | none | $0 | $30-65 |
| T1, SFT LoRA on Qwen3.5-9B: 1,000-3,000 trajectories of 20-30k tokens, 3 epochs on one 80 GB card, 6-12 h | a pod, $2-3.5/h | $15-40 | $45-105 |
| T2, rejection-sampling fine-tuning, per round: sample k = 5 on 150-300 tasks (750-2,400 episodes at $0.05), keep the passes, LoRA SFT on them | serverless + a pod | $50-140 a round | 2-3 rounds $160-500 |
| T3, GRPO with the verifier as reward: online rollouts through the environment, generation-bound; 150-500 steps x 32-64 rollouts, 15-60 h on one H100 class card, restarts included | a pod, $2.7-3.5/h | $100-350 | $130-415 |
| Track X on every checkpoint | in the full package | | |

**Phase C/D total: $365-1,085** (lean, with the lean eval package, one T2 round and a short T3: $285-520).

**Phase E, publish, $0.** Hugging Face hosts the dataset and checkpoints; the leaderboard is generated into the repo;
the writeup is hours.

## 3. The whole project

| | lean | full |
|---|---|---|
| Phase B, Track D (Stages 0-6) | $190-275 | $335-510 |
| Phases C-D, training (Stage 7) | $285-520 | $365-1,085 |
| Phase E | $0 | $0 |
| **total from here** | **$475-795** | **$700-1,595** |

By month at the build plan's targets: November (Phase B) $200-500; December (T0, T1, the first T2 round) $100-250;
January (T2 rounds, T3, Track X) $150-500; February $0. The $110 of Oct 28 is Stage 0 and Stage 1.

What the PC takes off the bill: anything on the 9B or its checkpoints can run locally at one episode a time (d1-test
k = 5 is five nights; a checkpoint needs a GGUF conversion, a quantization step the bf16 rows do not have, so a local
checkpoint row is a second rig row rather than the same one). The three local rows' self-correct runs are nights, not
dollars.

## 4. What is not in this plan

A frontier row through the API above Haiku (Sonnet $60-100, Opus $120-190, Fable $330-520 a d1-test row); k = 5 on GLM-5.3
($100-175 cached); the multi-GPU rungs the ladder marked out of range (Qwen3.8-Flash-Next, DeepSeek-V4.1-Flash, Kimi-K3,
MiniMax-M2.7 at $12-48/h a node, or Kimi's public endpoint at $30-300 a row); the human playtest and expert sessions
(hours); and any rerun forced by a verifier or generator bump, which `report --reverify` re-scores from the kept
episodes for free.

## 5. Before the first paid run, each time

- Robert's go for the stage, with its ceiling; `--cost-cap` on every per-token row.
- The balance read from `list-billing` and topped up ahead of the stage.
- The pins: one worktree at one main commit for the stage; a pin change is a new run id, not a resume.
- `warm` before a self-hosted row, `workers NAME 0` after; the account's spend limit is $80/h.
- After every run: `report --publish`, `make_leaderboard.py`, the tracker row, and the multiplier table above corrected
  from the run's own tokens and worker time.
