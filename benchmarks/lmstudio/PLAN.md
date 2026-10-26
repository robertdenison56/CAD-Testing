# Plan: the Track D eval sets on RobertsPC (drafted 2026-10-23 evening)

Robert's decision of Oct 23: no more Runpod spend on the evals beyond what has run; run whatever models the
PC can hold through LM Studio instead. The currency here is PC hours, not dollars: the PC runs one model and
one episode at a time, so every set is a night or more per model. This file is the order of work; the rig
itself (specs, commands, guards) is `README.md` and `models.json` next door, and nothing starts without
Robert's go (`lms_campaign.py e3 NAME --taskset ... --samples ...`).

## What is running right now

`e3 qwen3.5-9b` on `d1-variance` x 5 (run id `e3-d1-variance-qwen3.5-9b-q4km-lms-single`), started 19:34 PDT
Oct 23. The single test episode before it ran to the 20-minute wall clock (122 steps, score 0), so the 9B is
budget-bound on this hardware. d1-variance is the sizing set: it is listed on the board but never ranked, and
at 100 episodes of 8 to 20 minutes it costs 13 to 33 hours of the PC. The same hours on `d1-test` x 1 give a
ranked row. Suggested: let two or three episodes finish to prove the harness, then stop it and restart on
`d1-test --samples 1` (the campaign script resumes nothing across task sets, so this is a fresh run).

## Time per episode on the PC

| model | file | fits | gen tok/s | minutes per episode | 100 episodes |
|---|---|---|---|---|---|
| Qwen3.5-9B | Q4_K_M 6.6 GB, on the PC | fully on the cards | 35.8 measured | 8-20 (test hit the 20-min cap) | 13-33 h |
| Gemma 4 12B | Q6_K 9.8 GB, to download | partly on the CPU | ~13 (Q8_0 measured 12.8) | 6-10 (Gemma writes little: 1.8k out tokens an episode on Runpod) | 10-17 h |
| Qwen3.5-4B | BF16 8.4 GB, to download | fully on the cards | not measured, ~2x the 9B | 5-12 | 8-20 h |
| Devstral Small 2 24B | Q3_K_L 13.3 GB, on the PC | tight; context spills to the CPU | not measured, ~8-10 | unknown, smoke first | 15-30 h |
| Ministral 3 14B reasoning | Q6_K 12.0 GB, on the PC | partly on the CPU | not measured, ~10 | reasoning model at 10 tok/s: likely cap-bound | 25-33 h |
| GLM-4.6V-Flash 9.4B, Gemma 4 E4B, Llama 3.1 8B | Q4_K_M, on the PC | fully | fast | 3-8 | 5-13 h each |
| Qwen3.6-35B-A3B, Gemma 4 26B-A4B, gpt-oss-20b | Q4_K_M 21 / 16 / 12 GB, to download | experts in the PC's RAM only | 3-5x slower than Runpod | likely cap-bound | 25-35 h |

The minutes are from the measured token rates and the Runpod rows' tokens per episode (`results/e3-runpod`):
the 9B wrote 9-13k output tokens an episode with thinking on, Qwen3.6 12.8k, Gemma 12B 1.8k. Prefill is
3,157 tok/s on the 9B with llama.cpp's prompt cache taking most of each turn's repeated prefix.

## The wall-clock question (Robert's call before the first ranked run)

The harness budget is 150 steps or 20 minutes an episode (`eval/budget.py`). On Runpod's vLLM that was never
the binding limit for Qwen3.6 (0 cut-offs) and bound Gemma 12B ten times in 100 episodes; on the PC the 9B hit
it in its one test episode. Two ways to run the local rows:

1. **Same budget as every other row** (`--wall-clock` left at 20). The rows are comparable on paper, and the
   PC's speed becomes part of the score: a slow local file loses points a vLLM row of the same weights keeps.
2. **A longer wall clock for local rows** (e.g. `--wall-clock 45`), the step budget unchanged. The score then
   measures the model, not the cards; the row's card records the budget, and the board already keeps the
   local GGUF rows apart from the bf16 vLLM rows (different model ids, "local small" class). Episodes run up
   to 45 minutes, so 100 episodes can take two nights.

Recommendation: option 2 for the ranked runs, recorded in the run id (`...-wc45`), and the 9B test episode
repeated under it first to see whether the 122 steps were the model flailing or the clock.

## Order of work

Each line is one model-night (10 to 20 hours) unless marked. `d1-test` x 1 (100 episodes) gives a ranked row
inside ±5 for a strong model and ±6 or so for a noisy one; k = 3 is three nights and only worth it for a row
that lands near another.

1. **Qwen3.5-9B, d1-test x 1.** The file is loaded, the harness is proven on it. First ranked local row.
2. **Downloads on the PC** (they land where `lms get` runs, so from the PC, not the Mac): Gemma 4 12B Q6_K and
   Qwen3.5-4B BF16 as `README.md` step 1 says; then `lms_campaign.py check NAME` for each (one 29k prompt at
   65k, writes `measured`).
3. **Gemma 4 12B Q6_K, d1-test x 1.** Its Runpod row is 69.3; the local row shows what Q6_K and llama.cpp's
   Gemma template cost it.
4. **Qwen3.5-4B BF16, d1-test x 1.** Bottom of the ladder at the board row's precision.
5. **Smoke the models already on the PC** (one d1-dev episode each, `e3 NAME --taskset d1-dev --limit 1
   --samples 1`, ~2 hours in all): Devstral Small 2, Ministral 3 14B reasoning, GLM-4.6V-Flash, Gemma 4 E4B,
   Llama 3.1 8B. Keep a model if the episode makes valid tool calls and submits; drop it if it never calls a
   tool (GLM-4.6V-Flash, E4B and Llama scored 0 of 24 on the Tier-3 probes in October, so expect to drop them).
   Mistral 7B v0.3 stays out: LM Studio strips its tools and 32k of context is under the schema.
   Each needs a `models.json` entry (lms_key, variant, quantization, extra_body) before `e3` will take it.
6. **Keepers from step 5, d1-test x 1**, one night each. Devstral Small 2 is the one to hope for: an agentic
   coding model with tool calling, the largest dense model the cards hold.
7. **The MoE rows, if the PC's RAM allows** (needs about 24 GB free RAM beside the cards for Qwen3.6-35B-A3B
   Q4_K_M; Robert to confirm the PC's RAM). Qwen3.6-35B-A3B is the best open model on the board (86.7 on
   d1-variance), so a local row for it matters most; Q4_K_M keeps the earlier quantization rule. gpt-oss-20b
   stays out (Robert, Oct 20). A `check` first; expect a cap-bound run that takes a weekend.
8. **d1-real x 1 (99 episodes) for the two best local rows.** The first real-sheet rows on the board. Real
   sheets carry more linework, so allow 1.3x the d1-test time.
9. **hard-pilots, text-only 24 of 29, for the best local row**, k = 1 (24 episodes under Track P's budgets).
   The five scanned-sheet pilots need image input the OpenAI-compatible route does not pass.

Total: about six model-nights for the d1-test rows that exist today (steps 1, 3, 4, and two or three keepers),
two more for d1-real, a weekend for Qwen3.6 if it fits. Nothing else is needed for the board except the
`NAMES` entries in `src/roaddraft/runners/leaderboard.py` the README names, so the rows read "Qwen3.5-9B
(Q4_K_M, LM Studio)" and so on.

## Rules carried over

- The PC must not sleep during a run (Windows power settings); the Mac holds itself awake with `caffeinate -i`.
- One local run at a time: the campaign script refuses while another is going.
- Quantization stays as recorded in `models.json`; a precision change is asked first (Qwen = Q4_K_M).
- Runs are pinned to the campaign worktree (`lms_campaign.py pins`); a pin change between a model's episodes
  makes a new row, not a resume.
- After each run: `lms_campaign.py score NAME`, then `report --publish` and `python scripts/make_leaderboard.py`
  as `benchmarks/runs/LEADERBOARD.md` describes; the episodes stay in `results/e3-lms/` (gitignored).

## Resuming the 9B's d1-real run (set up 2026-10-26, not started)

**What happened.** `e3-d1-real-qwen3.5-9b-q4km-lms-single` ran 20:21 PDT Oct 23 to 09:08 Oct 24 and lost 61 of its
99 episodes to the server, not the model (`results/e3-lms/<run>.log`, LM Studio's `~/.lmstudio/server-logs`):

1. 22:27:52 Oct 23: "LM Link client transport disposed" mid-stream. The guard reloaded; `lms load` came back
   with rc=1 while the load was still going, and the next request met HTTP 400 "No models loaded", which was not
   a reload marker. That episode and the next 40 died on it in ten seconds (22:27:58 to 22:28:07), one request
   each, until the load finished on its own and episode 53 ran normally.
2. About 01:50 Oct 24: generation stopped mid-prompt on the PC with nothing in LM Studio's log (the engine hung).
   The harness waited its 30-minute read timeout (client disconnect 02:20:49), then every request took the
   server five minutes to answer "Engine protocol predict request failed: fetch failed" while the model stayed
   listed as loaded, so the guard "asked again" instead of reloading: four attempts, 20 minutes an episode, 20
   episodes, seven hours, until the task list ran out. Why the engine hung is still open; the Mac's log shows
   nothing, so the PC's LM Studio log (and its GPU state at 01:50) is the place to look.

The 38 episodes that ran scored 63.8 effective (median 75.6; 30 submitted, 8 at the budget, no hard fails).

**What is built (uncommitted on main, 2026-10-26).**

- `runners/openai_compat.py`: "No models loaded" is a reload marker; `LmStudioGuard.reload` waits until the
  server lists the model at the run's context (`LOAD_WAIT` 180 s) instead of trusting the CLI's exit;
  `probe()` is a one-token unstreamed completion with a 90 s timeout; `ensure_alive()` reloads and probes every
  30 s for up to 30 min and returns False when the engine never answers; `post_chat` asks again once on a
  reload marker with the model still listed and reloads on the next such error.
- `eval/providers` and `eval/agents`: `ready()` on providers and agents (the openai-compatible provider's calls
  `ensure_alive`); `eval/runner.py` asks it before every episode and stops the run (`stopped = "engine"`)
  without writing the episode when it says no, and stops after three episodes in a row that errored before
  their first step (`stopped = "errors"`). Stopped episodes have no end record, so the resume runs them.
- `lms_campaign.py`: `clear-errors RUN_ID [--apply]` and `e3 --worktree PATH`.
- Tests: four in `tests/test_runners.py`, two in `tests/test_eval_runner.py`.

**Done already.** The 61 errored episode files are in `results/e3-lms/<run>/errored-2026-10-26/`; `episodes/`
holds the 38 good ones. A detached worktree `.claude/worktrees/lms-9b-resume` is checked out at the run's pin
3777cb00 (its d1-real is the run's 99-task draw; main's d1-real at 9dd9af1e has 108 tasks and 14 of the run's
ids are gone from it, so a resume from main would not be the same run).

**To resume (each step waits on Robert's go).**

1. Commit the guard on main, then put it on the worktree:
   `git -C .claude/worktrees/lms-9b-resume cherry-pick <that commit>` (the worktree must be clean in `src` and
   `tests` for preflight). The resumed episodes then carry that commit in their pins; tools, instructions and
   verifier (d1-verify-v6) are the same as the first 38.
2. Load the model alone at 65k and start the resume (the campaign script does both):
   `python benchmarks/lmstudio/lms_campaign.py e3 qwen3.5-9b --taskset d1-real --samples 1 --run-id
   e3-d1-real-qwen3.5-9b-q4km-lms-single --worktree .claude/worktrees/lms-9b-resume`
   (`--print` shows the command; `--dry-run` lists the 99 cells, of which 38 are complete). It keeps the run's
   20-minute wall clock; a 45-minute clock would be a new run id, not a resume.
3. When it ends: `python -m roaddraft.eval report results/e3-lms/<run>` then `--publish`, and
   `scripts/make_leaderboard.py`. `run.json` is rewritten by the resume (its `started_at` and pins are the
   resume's); the per-episode headers keep each episode's own pins.
