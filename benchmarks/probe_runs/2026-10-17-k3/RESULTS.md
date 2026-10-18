# 2026-10-17 — the open-weight ladder at k = 3 on Runpod serverless (vLLM), on the scrubbed help text

The campaign folder for the Runpod runs planned on 2026-10-16 (`benchmarks/runpod/README.md`, "The ladder"):
open-weight models from 4B to 122B parameters, each served by the Hub vLLM worker on one GPU, driven by
`python -m roaddraft.runners run --backend openai` from the worktree pinned at `e7178a2` (spec v1, generator
d1-v6, verifier d1-verify-v4, the scrubbed tool help `60eeeb21` / server instructions `4dff2849`). Each model's
three repeats run as three processes on one worker, labels `runs/<label>-r1..r3`; the smoke probe `edge-c102`
runs first as `-r1`. Budgets: 120 turns, 30 minutes a probe (the hosted open-weight setting of the Qwen3.5-9B row).


## Result, the first seven rows (Oct 17, 21:47 to Oct 18, 02:50 UTC): Qwen3.6-35B-A3B 23, 20, 24 of 33

Robert's go came in two batches ("run 1-4 now", then "start LLMs 6, 7 and 9" an hour later). Every row below ran all 33
probes three times on its own endpoint; the three repeats of a model ran as three processes against one worker.
Pass rates and intervals are the board's (`benchmarks/leaderboard/TRACK_P.md`, regenerated Oct 18 02:50 UTC).

| model | worker | cold start | r1, r2, r3 | pass rate [95% CI] | rank | hard-fail | invalid | mean episode | bill |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B (bf16) | RTX PRO 6000 96 GB, EUR-IS-2 (Hub endpoint `wn6oehzs020wpc`) | warm job 212 s | **23, 20, 24** | **67.7% [52.5, 81.8]** | 5 of 13 | 27% (9/33) | 4.0% | 108 s, 9.7 turns | $4.72 |
| Gemma 4 26B-A4B (bf16) | H100 80 GB, US-NE-1 then US-MO-1 | two lost to the 570 s limit, then 354 s by the queue route | 14, 19, 16 | 49.5% [33.3, 65.7] | 7 | 39% (13/33) | 13.2% | 121 s, 11.1 turns | $8.43 |
| Qwen3.5-9B (bf16), clean help text | A40, CA-MTL-1 (the Oct 14 worker) | FlashBoot, under 5 min | 16, 17, 11 | 44.4% [29.3, 59.6] | 8 | 42% (14/33) | 8.0% | 388 s, 16.4 turns | $4.96 |
| Gemma 4 12B (bf16) | RTX PRO 6000 MIG 48 GB, US-PA-1 | 3 min 41 s (compile 54 s) | 14, 13, 14 | 41.4% [26.3, 57.6] | 9 | 42% (14/33) | 20.4% | 212 s, 15.8 turns | $4.34 |
| GLM-4.7-Flash (bf16) | H100 80 GB, US-NE-1 | 8 min 4 s (5 min of download), lost to the 570 s limit; 212 s warm | 14, 11, 13 | 38.4% [24.2, 53.5] | 10 | 45% (15/33) | 12.1% | 91 s, 16.8 turns | $6.96 |
| Qwen3.5-4B (bf16) | RTX PRO 6000 MIG 24 GB, US-PA-1 | about 3.5 min | 10, 10, 13 | 33.3% [20.2, 47.5] | 11 | 42% (14/33) | 15.5% | 340 s, 20.9 turns | $2.29 |
| gpt-oss-20b (mxfp4) | A40, CA-MTL-1 | 1 min 52 s (Marlin mxfp4, 95 tok/s) | 0, 3, 4 | 7.1% [1.0, 14.1] | 13 | 85% (28/33) | 21.8% | 102 s, 3.7 turns | $1.28 |

The bill is `list-serverless-billing` per endpoint over the two UTC days, $32.97 for the seven together (GPU $32.82, disk
$0.15), smoke probes, warm-up jobs and the reruns described below included. The estimate had been $45-70.

**Rig.** `python -m roaddraft.runners run --backend openai` from the worktree pinned at `e7178a2`, so every
`run.json` carries the clean help text (`tools sha256:60eeeb21…`, `instructions sha256:4dff2849…`), the first rows
on the board to do so; 120 turns and 30 minutes a probe; the Hub vLLM worker v2.29.0 (vLLM v0.31.0) with each
card's parsers and sampling (`benchmarks/runpod/models.json`): Qwen `qwen3_coder` + `qwen3` with the thinking-mode
sampling, Gemma `gemma4` + `gemma4` with the recipe's `tool_chat_template_gemma4.jinja` and thinking turned on
through `chat_template_kwargs` (vLLM confirmed the card's `generation_config.json` sampling, temperature 1.0, top_k
64, top_p 0.95), GLM `glm47` + `glm45`, gpt-oss `openai` + `openai_gptoss` at its defaults. Prefix caching on
everywhere; `MAX_MODEL_LEN` 65,536. The run folders, the per-probe marks and the §3.2 measures are on the cards.

**What the rows say.**

- *Qwen3.6-35B-A3B is the best open-weight row by a wide margin*, fifth on the board above GPT-6-Luna (66.7%) and
  below Haiku 4.5 (74.7%), with 3B active parameters: 96% on Tier 1, the only open model to pass
  `draft-roadway-sheets` and `stationing` (three of three each), 4.0% invalid calls (Haiku's figure). Its misses
  are the curve data and the Caltrans L-2 sheet, like Haiku's, plus `curve-data` and `draft-fix-the-drawing`
  twice each on the context: a single thinking turn ran the 65k context out (`length`, 8 of 99 episodes).
- *Gemma 4 26B-A4B (49.5%) beats Gemma 4 12B (41.4%), and both beat the local E4B (29.3%)*: the Gemma 4 family
  scales on this benchmark. Both Gemmas fail the drafting probes with long turns rather than wrong calls: 17 of the
  12B's 99 episodes and 4 of the 26B's ended with one turn past the proxy's 570 s limit (`draft-fix-the-drawing`
  on every repeat for the 12B, `sheet-set-callouts`, `draft-intersection-corner`, `clean-callouts`). The 12B's
  20.4% invalid-call rate is the second worst on the board.
- *The 9B rerun on the scrubbed help text reads 44.4% against 47.5% on the Oct 12 text*, inside its interval
  (Tier 1 80% against 78%, Tier 3 7% against 13%): the fixture values in the old examples were not what the 9B was
  passing on. The Oct 12 row is marked superseded on the board.
- *GLM-4.7-Flash (38.4%) is the fastest row (91 s an episode) and passes nothing beyond Tier 1*; it is the
  strongest 30B-class model on its own card's benchmarks and the weakest 30B-class model here.
- *Qwen3.5-4B (33.3%) sits where its size suggests*, a third of the 9B's Tier 3 and most of its Tier 1.
- *gpt-oss-20b (7.1%) does not use the tools*: 82 of 99 episodes ended in one to four turns with a report of
  tool calls it never made (the September Ollama finding on the 120b, now at k = 3 on the 20b), and 17 ended with
  vLLM's harmony parser rejecting its own malformed tool header (`unexpected tokens remaining in message header`,
  `could not decode header`), which the board counts as the model's failures (`MODEL_ERRORS`). Its 6 of 51 Tier 1
  passes are the paper-space finds.
- *Still unpassed by every open model*: `qa-alignment-data`, `l2-alignment-data`, `l2-match-lines`,
  `draft-roadway-sheets` (Qwen3.6 excepted), `line-data` (one Gemma 26B pass), `curve-data`, `width-dims`.

**Two rig findings, both now in the script.**

1. *Runpod's proxy ends a streamed request after 570 seconds.* A cold start longer than that loses the first
   probe before any turn (GLM-4.7-Flash, Gemma 26B-A4B and Qwen3.6-35B-A3B all did, 0 turns; three probes rerun as
   infrastructure errors, the old folders under `runs/_superseded/`), so a 50 GB-plus model is now started through
   the queue route first (`runpod_campaign.py warm`: a tiny `/run` job, polled; GLM 212 s, Gemma 26B 354 s). The
   same limit reached by a model's own turn is a different thing: the model outlasted the rig's effective turn
   limit (the runner's own is 1,800 s), so the board counts it as a budget failure (`BUDGET_ERRORS`,
   `leaderboard.py`), as it counts the runner's `turn_limit` and Fable's CLI cap. Before that rule was settled
   the 21 Gemma cut-offs had been rerun once (9 answered, 8 cut off again on the 12B; 2 and 2 on the 26B); the
   reruns were discarded and the first-pass episodes restored, so every row is three first attempts; the discarded
   reruns are under `runs/_superseded/*-rerun-discarded-*`.
2. *An endpoint created by the REST API with the Hub image can draw a host that cannot pull it* ("Failed to get
   Hub registry auth", EUR-IS-2 on the Qwen3.6-35B-A3B endpoint `y27c5iljez2qon`, deleted); the hosts that had
   the image cached ran fine. The replacement was deployed from the Hub release (`deploy-hub-repo`,
   `wn6oehzs020wpc`) and drew a host at once. The big rungs still to run are REST-created; redeploy from the Hub
   if a worker sits in Initializing with that line in its system log.

Other notes from the worker logs: the idle timeout was raised to 600 s on the three big endpoints so a warm
worker survives the gap between warm-up, smoke and campaign; GLM and Gemma 26B landed on H100 80 GB hosts (the
$4.79/h pool) although cheaper pools were listed first; the gpt-oss worker logged "we ignore
--enable-auto-tool-choice and always enable tool use", so the parser flag was not the cause of its behaviour.

**Per-probe marks** (P pass, · fail, B budget: turn or context limit, including the 570 s turn cut-offs):

| probe | qwen3.5-4b-bf16-vllm | qwen3.5-9b-bf16-vllm | gemma-4-12b-bf16-vllm | gpt-oss-20b-mxfp4-vllm | gemma-4-26b-a4b-bf16-vllm | glm-4.7-flash-bf16-vllm | qwen3.6-35b-a3b-bf16-vllm |
|---|---|---|---|---|---|---|---|
| both-edges-c101 | P P P | P P P | P P P | . . . | P P P | P . P | P P P |
| centerline-c103 | . P P | P P P | P P P | . . . | P P P | P P P | P P P |
| clean-callouts | . . P | . P . | B B . | . . . | . P . | . . . | P P P |
| curve-data | . . . | . . B | . . . | . . . | . . . | . . . | B B . |
| curve-points | P . . | . . B | P B . | . . . | . . . | . . . | P P P |
| draft-bearing-distance | P P P | P P P | P P . | . . . | P P P | P P P | P P P |
| draft-building | . P . | P P . | P P P | . . . | P P P | . . P | P P P |
| draft-cul-de-sac | B . P | P P P | . P . | . . . | P P P | . . . | P P P |
| draft-edges-shoulders | . . P | P . . | . P P | . . . | P P P | P . . | P P P |
| draft-fix-the-drawing | . . . | . . . | B B B | . . . | B B . | . . . | B B . |
| draft-intersection-corner | . . . | . . B | B B . | . . . | B P B | . P . | P . P |
| draft-pi-curve | P B B | P P P | P . P | . . . | . P P | P P P | P P P |
| draft-roadway | . . P | P P B | . . P | . . . | . P . | P P P | P . P |
| draft-roadway-sheets | . . . | . . . | . . . | . . . | . . . | . . . | P P P |
| draft-tangent-ne | . P . | P P P | P P P | . . . | P P P | . . P | P P P |
| draft-turn-lane | . . . | . B . | P . . | . . . | . . P | P . P | P P P |
| edge-c102 | P P P | P P P | P P P | . . . | P P P | P P P | P P P |
| edge-c102-paper | P P P | P P P | P P P | . P P | P P P | P P P | P P P |
| edge-curve-c102 | P P P | P P P | . B P | . P P | P P P | P P P | P P P |
| equation-data | P . . | P . . | . . . | . . P | . . . | . . . | P . P |
| l2-alignment-data | . B . | . . B | B B . | . . . | . . . | . . . | . . . |
| l2-match-lines | . B . | . . . | . . B | . . . | . . B | . . . | . . . |
| line-data | . . . | . . . | . . . | . . . | . P . | . . . | . . B |
| pc-by-station | . P P | P P . | P P P | . . . | P P P | P P . | P P P |
| qa-alignment-data | . . . | . . . | . . . | . . . | . . . | . . . | . . . |
| row-data | B . B | . P B | P . B | . . . | . . . | . . . | B . B |
| sheet-set-callouts | . . . | B . . | B B B | . . . | . . . | P . . | . . . |
| shoulder-c101 | P . . | P P . | P P P | . P . | P P P | . . . | . P P |
| sta-offset-c101-paper | . . P | . P P | P P P | . . P | P P P | P P P | P P P |
| station-callouts | . B . | B B . | . . . | . . . | . . . | P . . | P . P |
| stationing | . . . | . . . | . . B | . . . | . . . | . . . | P P P |
| title-blocks | P P P | P P P | . P P | . . . | P P P | . P P | P P P |
| width-dims | . . . | . . B | . . B | . . . | . . . | . . . | . B . |
| **passes** | **10, 10, 13** | **16, 17, 11** | **14, 13, 14** | **0, 3, 4** | **14, 19, 16** | **14, 11, 13** | **23, 20, 24** |

## Result, rungs 5 and 8 (Oct 18, 02:46 to 07:05 UTC): Gemma 4 31B 23, 27, 24 of 33, level with Haiku 4.5

Robert: "run 5 and 8" (Oct 17, 19:46 PDT). Both endpoints had been created by the REST API with the Hub image, and
both had to be replaced from the Hub release before a probe ran: Qwen3.8-27B's first host (AP-IN-1) looped on
container start for lack of Hub registry auth; Gemma 31B's first worker (an H100 80 GB in AP-IN-1) came up, served
one job and never polled the queue again, and its second ran out of GPU memory at startup, vLLM reporting that
80 GB holds the 62.5 GB of weights with about 16k tokens of context, not the rig's 65,536. The replacements
(`jbwqugdj3bxts8` on AMPERE_80 / ADA_80_PRO; `kgu6d0ogfm0oyu` on BLACKWELL_96 only) were warmed through the queue
route (273 s and 257 s), passed the smoke probe (Qwen3.8 6 turns in 98 s, Gemma 31B 3 turns in 57 s) and ran the
three repeats in 3 h 46 min each, side by side. Board regenerated Oct 18 07:15 UTC: 15 rows ranked.

| model | worker | r1, r2, r3 (board) | pass rate [95% CI] | rank | hard-fail | invalid | mean episode | bill |
|---|---|---|---|---|---|---|---|---|
| Gemma 4 31B (bf16) | RTX PRO 6000 96 GB (Hub endpoint) | **23, 27, 24** | **74.7% [59.6, 87.9]** | 5 of 15 | 15% (5/33) | 23.7% | 278 s, 7.5 turns | $10.30 (+ $1.53 on the replaced endpoint) |
| Qwen3.8-27B (bf16) | H100 / A100 80 GB (Hub endpoint) | 22, 21, 21 | 64.6% [48.5, 79.8] | 8 | 24% (8/33) | 2.4% | 396 s, 8.2 turns | $15.34 (+ $0.55) |

The two UTC days' bill for the nine rows is $65.44 (GPU $65.17, disk $0.27, eleven endpoint ids), the two replaced
REST endpoints' $2.08 included; the estimate for these nine had been $85-130.

**What the rows say.**

- *Gemma 4 31B ties Claude Haiku 4.5 on pass rate and hard-fail rate (74.7%, 5 of 33 never passed) and loses the
  tie-break on invalid calls (23.7% against 4.2%)*: it reaches the same drawings by trying more wrong calls. It is
  the first open model to pass more than half of Tier 3 (16 of 30: `curve-points`, `equation-data`, `row-data`,
  `stationing`, `width-dims` three of three each, `line-data` and `station-callouts` once) and the only model on
  the board besides Astra and Sonnet to pass `draft-roadway-sheets` every time. Its five never-passed probes are
  `curve-data`, `qa-alignment-data`, the two L-2 probes and `draft-building`, which it lost three times to the
  30-minute budget, the only budget stops it took; no turn of its outlasted the 570 s limit on the 96 GB card.
- *Qwen3.8-27B (64.6%) thinks itself out of the context*: 25 of 99 episodes ended on `length` (a single thinking
  turn past 65,536 tokens, `qa-alignment-data`, `curve-data`, `clean-callouts` and `l2-match-lines` three of three
  each), and its first turn on `draft-roadway-sheets` outlasted the proxy's 570 s limit on all three repeats, on a
  warm worker, which the board counts as a budget failure. On what it finishes it is the most accurate open model:
  2.4% invalid calls (Sonnet 2.0%, Astra 0.4%), 96% on Tier 1, and the sheets it left behind on six of the `length`
  episodes pass the check (the `score` command reads 23, 22, 23); the board does not credit a budget stop. Its
  `reasoning_effort` default is `xhigh`; a row at `medium` is a different rig setting and Robert's call.
- *Size and architecture*: the two dense 27-31B models (64.6%, 74.7%) and the 35B MoE (67.7%) sit together above
  GPT-6-Luna; the 26B MoE (49.5%) and everything smaller sit below Qwen3.5-9B's class. Within families: Gemma 4
  E4B 29.3% < 12B 41.4% < 26B-A4B 49.5% < 31B 74.7%; Qwen3.5-4B 33.3% < 9B 44.4% < Qwen3.8-27B 64.6% and
  Qwen3.6-35B-A3B 67.7%.

**Per-probe marks** (P pass, · fail, B budget: turn, context or 570 s turn limit):

| probe | qwen3.8-27b-bf16-vllm | gemma-4-31b-bf16-vllm |
|---|---|---|
| both-edges-c101 | P P P | P P P |
| centerline-c103 | P P P | P P P |
| clean-callouts | B B B | . P . |
| curve-data | B B B | . . . |
| curve-points | P P P | P P P |
| draft-bearing-distance | P P P | P P P |
| draft-building | P P P | B B B |
| draft-cul-de-sac | P P P | P P P |
| draft-edges-shoulders | P P P | P P P |
| draft-fix-the-drawing | . B B | . . P |
| draft-intersection-corner | P P P | P P P |
| draft-pi-curve | P P P | P P P |
| draft-roadway | P P P | P P P |
| draft-roadway-sheets | B B B | P P P |
| draft-tangent-ne | P P P | P P P |
| draft-turn-lane | P P P | P P P |
| edge-c102 | P P P | P P P |
| edge-c102-paper | P P P | P P P |
| edge-curve-c102 | B B P | P P P |
| equation-data | B B P | P P P |
| l2-alignment-data | B . B | . . . |
| l2-match-lines | B B B | . . . |
| line-data | P P . | . P . |
| pc-by-station | P P P | P P P |
| qa-alignment-data | B B B | . . . |
| row-data | B . P | P P P |
| sheet-set-callouts | B . B | . P . |
| shoulder-c101 | P P P | P P P |
| sta-offset-c101-paper | P P P | P P P |
| station-callouts | P P . | . P . |
| stationing | P P B | P P P |
| title-blocks | P P P | P P P |
| width-dims | P B . | P P P |
| **passes** | **22, 21, 21** | **23, 27, 24** |
