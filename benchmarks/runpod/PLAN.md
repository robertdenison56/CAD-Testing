# Plan: Track D on Runpod, the model tree (drafted 2026-10-28 evening)

## Closed with Track D (2026-11-16)

Robert, Nov 16, closing Track D: "drop kimi", "delete old runpod endpoints". Nothing below this section is a plan
any more; it is the record of what ran.

- **Kimi K2.6 is dropped.** Its smoke on the public `moonshot-kimi` route (`queue-trackd-v4.sh`, Nov 10 21:05) came
  back with empty replies: 5 episodes, 0 steps, $0 (`results/e3-runpod/e3-smoke-v3-kimi-k2.6`), so its `d1-test` was
  skipped. The cause was never diagnosed (a route or request-format problem, not the model's drafting). No retry and
  no row; the `kimi-k2.6` spec and its price row stay in the tree, marked dropped.
- **The two old endpoints are deleted** (Nov 16, read back gone): `d1aaw4ddzlsghg` (`roaddraft-qwen3.5-122b-a10b`)
  and `7maayov2g1xjoi` (`roaddraft-gpt-oss-120b`), both REST-created on Oct 17, never run, and replaced by the Hub
  redeploys `8jlpbwp0bkjooj` and `ioe4cjrhf39vp3`. Thirteen endpoints remain, every one parked at 0 max workers
  (nothing bills idle).
- **What the spread bought:** five queues, $150.27, the open-weight rows of the vague board
  (`docs/Track_D_Findings.md`). Not run and not planned: Qwen3.5-122B (its endpoint is redeployed and parked), a
  Gemma 26B pilot rerun with an output cap. Any further Runpod spend belongs to training (phase C) and needs
  Robert's go.

## The second queue: the large models, $120 in all (2026-11-10, SET UP, NOT run)

Robert, Nov 10, after the first queue: "still want to use the 100 for model testing, plan out those models and
runs". The first queue (`queue-trackd-v3.sh`, Nov 10 09:20-17:16) spent $28.62 for eight runs, none with an episode
in error; $71.38 is left, $68 under the same $3 reserve. Every run below is vague, single, k = 1, pin ad6bf5e3 (the first queue ran at f6725cbb), d1-test
whole and the other sets as `cost5`, as the first queue.

What the first queue measured (balance read before and after each run), against the plan's estimates:

| run | est. (mid) | billed | time |
|---|---|---|---|
| Qwen3.6 d1-test / d1-real cost5 | $5 / $4 | $1.46 / $0.88 | 23 / 14 min |
| Qwen3.6 hard-pilots / d1-test-hard / d1-real-hard, cost5 | $9 / $4 / $3 | $12.28 / $2.04 / $0.59 | 214 / 32 / 11 min |
| Gemma 4 31B d1-test / d1-real cost5 | $13 / $10 | $2.92 / $2.63 | 53 / 44 min |
| GLM-5.3 d1-test (87% of input cached) | $25 | $4.31 | 27 min |

So a d1 run costs a quarter of its estimate and hard-pilots is the one dear set ($12 for a 9.1). gpt-oss-120b did
not run: its warm-up job sat 25 min in the queue with no worker (AMPERE_80 only, stock LOW on Nov 4 and Nov 10).

**Redrawn the same day** (Robert: "i would like larger models on the test and hard pilots if possible"): the 27-31B
rows and the hard D1 sets are out; the queue is the models past 100B on d1-test and hard-pilots. What is possible:

| model | size | reads images | d1-test | hard-pilots cost5 |
|---|---|---|---|---|
| GLM-5.3 (public, per token) | 753B | no (text-generation; `vision: false`) | done, 66.5 | the 51 text pilots, marked text only: $22-30 |
| gpt-oss-120b (`ioe4cjrhf39vp3`) | 117B | no | $4 (high 7) | the 51 text pilots, marked text only: $10-18 |
| Qwen3.5-122B-A10B FP8 (`d1aaw4ddzlsghg`, H200 $6.99/h) | 125B | yes | $10-15 | no: the card leaves 9 GB of KV, one or two 65k streams, and 37 of Qwen3.6's 66 pilot episodes sent a prompt past 65k; about $100 at that pace |
| Kimi K2.6 (public `moonshot-kimi`) | 1,027B | yes | $27 (no cached rate listed) | no: about $120 uncached (1.7 M input tokens an episode at $0.95) |

Sizes and image support from the models' Hugging Face cards, Nov 10. The subset holds 15 image pilots of its 66, so a
text-only model cannot fill it. Robert, Nov 10 (after a `--no-images` variant, built and withdrawn the same evening,
in which the model attempted the image pilots without their page): "mark any hard pilots that are text only as such,
do not move off the board", and, asked, "Skip the photo pilots". So: a `hard-pilots` run that holds every text pilot
of its set or subset and none of the image pilots is no longer "partial, not scored"; it stays in its table, its row
marked **text only (51 of 66 pilots)**, scored on its text pilots alone (`report.coverage` `text_only`; the board
footer states the rule). A spec with `"vision": false` in `models.json` (GLM-5.3, gpt-oss-120b) runs the text pilots
by default (`e3 --subset cost5` passes the subset's 51 text ids; run id `...-cost5-text-v3`). Worktree c195f63a,
then ad6bf5e3 with Kimi's price row; `TRACKD_PIN` ad6bf5e3; the same changes uncommitted on main. No published run is text only today.

Robert, Nov 10: "add kimi". Kimi K2.6 is in, on d1-test, second in the order:

| order | model | runs | est. $ (mid, high) | set-up it needs first |
|---|---|---|---|---|
| 1 | gpt-oss-120b | smoke; d1-test | 4, 7 | add BLACKWELL_96 ($3.49/h, stock HIGH) beside AMPERE_80 (LOW; no worker in 25 min on Nov 10) |
| 2 | Kimi K2.6 | smoke under a $5 cap; d1-test under a cost cap, only if the smoke projects under the cap | 27, 32 | a `models.json` spec (public, `moonshot-kimi`, model id read off the endpoint) and a `prices.json` row ($0.95 in, $4.00 out per M) |
| 3 | GLM-5.3 | hard-pilots cost5, its 51 text pilots, under a cost cap | 25, 32 | none |
| 4 | Qwen3.5-122B-A10B | smoke; d1-test at 65k context, concurrency 2 | 12, 18 | redeploy from the Hub (its REST-created endpoint never ran); rate in `models.json` is $5.93, now $6.99 |
| 5 | gpt-oss-120b | hard-pilots cost5, its 51 text pilots (if its d1-test calls tools) | 14, 20 | as 1 |

About $85 with the warm-ups and smokes. Robert, Nov 10: "Yes, raise to $120", so the queue has $91.38 ($120 less
the first queue's $28.62), $88 under its $3 reserve, and all five rows fit at their mid estimates. Kimi's smoke also
shows whether Runpod caches its input unlisted, which would cut its row to a few dollars.

**Set up on Nov 10 (no cost; every endpoint read back parked at max 0 workers):**
- gpt-oss-120b `ioe4cjrhf39vp3`: pools AMPERE_80 -> AMPERE_80 + BLACKWELL_96;
- Qwen3.5-122B-A10B REDEPLOYED from the Hub as `8jlpbwp0bkjooj` (deploy-hub-repo, release v2.30.3, template
  `vzneteh98d`; image set back to the ladder's `b7212acc6`, the exact CUDA 13.0 pin cleared for a 13.0 floor,
  `MAX_MODEL_LEN` 65536, idle 600 s, HOPPER_141); the REST-created `d1aaw4ddzlsghg` never ran and is left parked for
  Robert to delete, beside `7maayov2g1xjoi`;
- Kimi K2.6: `models.json` spec `kimi-k2.6` (public `moonshot-kimi`, model id `kimi-k2.6` read off the route's
  `/models`) and a `prices.json` row ($0.95 in, $4.00 out, a cached token priced as input until a bill says otherwise);
- `queue-trackd-v4.sh`: the five rows in order, the first queue's balance guard at `BUDGET` 91, Kimi's projection
  gate ($35 for 100 episodes) under `--cost-cap 40`, GLM-5.3's pilots under `--cost-cap 40`, the 122B's warm job given
  50 minutes for its 125 GB and run at `--concurrency 2`, a warm job that meets no worker purged from its queue;
- a `--dry-run` of each of the five runs passes the preflight at ad6bf5e3 (100, 100, 51, 100 and 51 episodes).

Launch, after Robert's go:
`nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v4.sh > results/e3-runpod/queue-trackd-v4.out 2>&1 &`

Estimates: GLM-5.3 from $0.043 a d1-test episode scaled by input tokens (the text pilots sent 1.96 M an episode on
Qwen3.6, against 0.30 M on d1-test); gpt-oss-120b from Qwen3.6's bill on the same sets (a like-sized active set on
the same card); Qwen3.5-122B from Qwen3.6's d1-test episode-hours at twice the time and half the concurrency.

## The $100 plan (2026-11-04, supersedes set A below)

Robert, Nov 4: "begin setting up the containers for runpod runs, select appropriate models and keep budget to $100
for finishing track D". The Nov 3 retirement (`../runs/RETIRED.md`) left every open-weight row to be rerun under
harness e3-v3, and the board now has five sets, so $100 buys depth on the strongest open model and breadth on the
two core sets, not set A's seven d1-test rows. Set up, nothing run: `queue-trackd-v3.sh` beside this file.

*2026-11-08: vague prompts only* (Robert: "focus on the vague prompts only", then "Update the runpod batches with
vague prompts only"; `../RERUN_PLAN.md`, top). Every run and every smoke in the queue is at the vague level
(`--level vague`; `e3-smoke` now defaults to vague), run ids `-single-vague-v3` and `-single-vague-cost5-v3`, so
the rows rank on the main (vague) board; explicit rows have a board of their own since Nov 8. Qwen3.6's
hard-pilots cost5 run and the image pilot that gates it were out for a few hours, while a pilot had one fixed brief,
and are back at the vague level: since Nov 8 every pilot has a vague brief too (Robert: "Check if any of the eval
tasks do not have a vague prompt style first, add them if needed"). The pinned worktree must carry that vague-pilot
code before a go (the same patch the local and CLI pilot queues run from, `results/e3-lms/vague-pilots.patch`). The
costs do not change with the level beyond the shorter prompt. Still set up, not run: it waits on the top-up and
Robert's go.

Robert, later on Nov 4: "the llms suggested are very similar, should i try others?" -> "Yes, swap them" (Gemma 4
26B-A4B and Qwen3.6's d1-test-hard / d1-real-hard out; GLM-5.3 and gpt-oss-120b in), then, asked whether to drop
d1-test as saturated, "Yes, keep d1-test" (its 100.0 rows are all self-correct or vision; in single mode it still
spreads: Terra 96.2, Sonnet 88.3).

Then: "for the runpod evals i want to limit the amount of episodes to save cost but still get at least 5 tasks from
each category" and "let the board rank these runpod runs and explicitly state the runs are partial to save costs.
only these runs would be allowed on the board with this tag and runs that end early or fail would be marked partial
and unscorable". So every set but d1-test runs as its **cost subset `cost5`**: 5 tasks of each task type (every task
of a smaller type), a fixed seeded draw committed in `benchmarks/tasksets/cost-subsets.json` (d1-real 60 of 100,
hard-pilots 66 of 112, d1-test-hard 25 of 100, d1-real-hard 25 of 100; `roaddraft.eval.subsets`). d1-test runs whole:
its types hold 6-7 tasks, so a subset would save a fifth, and its 10 ranked rows are the comparison.

| order | model | endpoint, pool, $/h | runs | est. $ (mid, high) |
|---|---|---|---|---|
| A | Qwen3.6-35B-A3B, bf16 (Track P 67.7%, d1-variance 86.7) | `wn6oehzs020wpc`, BLACKWELL_96, $3.49 | smoke d1-dev[:5]; 1 image pilot; d1-test; d1-real cost5 | 11, 17 |
| B | Gemma 4 31B, bf16 (Track P 74.7%) | `kgu6d0ogfm0oyu`, BLACKWELL_96, $3.49 | smoke; d1-test; d1-real cost5 | 25, 34 |
| C | GLM-5.3 (Runpod public endpoint) | `b1dd8hy2hqo1nb`, per token: $0.77 in, $0.143 cached, $2.42 out per M | smoke under a $5 cap; d1-test under `--cost-cap 30` if the smoke projects 100 episodes at $33 or less | 27, 36 |
| D | gpt-oss-120b, mxfp4 (`--send-reasoning`) | `ioe4cjrhf39vp3`, AMPERE_80, $2.72 | smoke; d1-test and d1-real cost5 if the smoke calls tools | 11, 16 |
| E | Qwen3.6-35B-A3B on the hard sets | as A | hard-pilots cost5 (only if it read the image pilot); d1-test-hard cost5; d1-real-hard cost5 | 17, 24 |

About $91 mid with the smokes and warm-ups, under the guard's $97. How the board takes these (report `e4-v2`):
- a run that declares `--subset cost5` ranks only when it holds every task of the subset with no episode in error or
  unfinished, and only from a Runpod route (`api.runpod.ai`); it goes in a table of its own under the set, headed
  "Cost subset `cost5`: partial runs, to save cost", beside every full run of the set re-scored on the same tasks
  (from the per-task means each published row now carries), since a subset's mean weights its task types alike;
- every other run on a board set that misses a task, has an episode in error, or has one unfinished is
  **partial, not scored**: listed with no score (before Nov 4 only hard-pilots was held to coverage). The 15
  ranked rows are complete, error-free and unchanged; their summaries gained `task_means` / `task_types` from
  their own episodes (each row's mean of them equals its published score);
- a GLM-5.3 d1-test cut short by its $30 cap would be partial and not scored, which is why the smoke's projection
  gates it.


Left out: Gemma 4 26B-A4B (a third Gemma, 49.5%; its endpoint stays at 131k, parked), Qwen3.8-27B ($14-18 a row;
thinks past the 570 s cut), GLM-4.7-Flash (38.4%), gpt-oss-20b (no tool call in 76% of its probes), Qwen3.5-122B-A10B
(H200 at $6.99/h now), Kimi (K2.6 $0.95 in / $4.00 out per M with no cache rate listed: $57-95 a row), Granite 4.0
H Small and Qwen3 32B AWQ (a generation old, no listed price). Self-correct and vision stay with the local
three and the frontier rows.

**Done on Nov 4 (no cost; endpoints parked at max 0 workers, read back after each write):**
- Qwen3.6's, Gemma 31B's and Gemma 26B's `MAX_MODEL_LEN` 65536 -> 131072 (the local rows' ceiling; the full-attention KV at 131k is
  about 2.6 GB for Qwen3.6 and Gemma 26B and 10.5 GB for Gemma 31B, against 20-23 GB free on their cards, from the
  models' config.json), the env otherwise unchanged; `context` 131072 in `models.json`, passed as `--context-tokens`;
- their `allowedCudaVersions ["13.0"]` (an exact set; most hosts now report 13.2) cleared for a `minCudaVersion` 13.0
  floor;
- Gemma 26B's pools AMPERE_80 + ADA_80_PRO -> AMPERE_80 + BLACKWELL_96: ADA_80_PRO (H100) bills $5.39/h serverless
  now (list-gpu-types, Nov 4), not the $2.72 of Oct 16;
- stock on Nov 4 (list-gpu-types, serverless): RTX PRO 6000 (BLACKWELL_96) MEDIUM, A100 80 GB LOW;
- gpt-oss-120b REDEPLOYED from the Hub as `ioe4cjrhf39vp3` (deploy-hub-repo; only the listed release v2.30.1 deploys,
  so its image was set back to v2.29.0's `b7212acc6`, the rest of the ladder's), AMPERE_80 only, `MAX_MODEL_LEN`
  131072, CUDA floor 13.0, parked; the REST-created `7maayov2g1xjoi` never ran and is left parked for Robert to
  delete; the Hub listing names the endpoint's template `yzft33ihtn`;
- the harness: Runpod's 570 s proxy cut (`stream did not complete within 570 seconds`, 10 of Gemma 4 12B's 100
  d1-variance episodes on Oct 20, all left out of its score as errors) and vLLM's HTTP 400 for a prompt past its
  window now end the episode as the `turn_time` and `context` stops (`eval/providers/openai_compat.py`
  `hosted_limit`, tested); no other provider's path changes; and `--send-reasoning` (off by default) hands a tool
  turn's reasoning back as the probe runner's flag did for gpt-oss-20b (7.1% -> 13.1% on Track P), tested;
- `runpod_campaign.py`: `e3` / `e3-smoke` run from their own worktree `runpod-trackd` at `TRACKD_PIN` (preflight
  refuses until it is set), `--pilots all|text|images`, `--cost-cap` (and on `e3-smoke`), `--send-reasoning` from
  a spec's `send_reasoning`, run ids end `-v3`; `warm` needs only the key;
- `queue-trackd-v3.sh`: A-E above, the balance guard, GLM-5.3's projection from its smoke (cost an episode x 100,
  and the cached share, in the log), endpoints parked after each model and on any exit.

**Before the go:**
1. DONE Nov 4: the harness change committed on main (463a9707) and cherry-picked onto the v3 reruns' 3b7e7fe9 as
   9f7c02bb on the local branch `runpod-trackd-v3`, checked out at `.claude/worktrees/runpod-trackd` (pins read
   there: tools 0334fd4aaade, instructions 4dff2849, harness e3-v3, clean; 110 eval tests pass), `TRACKD_PIN`
   9f7c02bb. Not main's surface: the stationing help (4d135e7d) moves it to 9db020d9af1e and edits the prompt.
   Nov 9: the vague-pilot patch committed there as f6725cbb (841 eval and pilot tests pass), `TRACKD_PIN` f6725cbb.
2. Balance: $161.85 on Nov 9 (runpodctl user; $11.85 on Nov 4), so the top-up is done and the queue's guard
   ($97 spent), not the balance, is the stop.
3. Launch: `nohup caffeinate -i zsh benchmarks/runpod/queue-trackd-v3.sh > results/e3-runpod/queue-trackd-v3.out 2>&1 &`
   (about 15-25 h, one endpoint at a time). Publish each row after a look, as the local ones.

Robert's decisions of Oct 28 evening: "i can budget about $110 for the spread" and "build out the model tree for the
runpod runs, do not duplicate any that are being run locally". This file is that tree: every model Track D can reach
through Runpod, what each row costs, the order, and what has to happen before a go. The rig itself is `README.md`,
`models.json` and `runpod_campaign.py` beside it. **Nothing here starts a worker or sends a request**; every run
waits on Robert's go, and the Oct 24 local-only rule stands until he lifts it. Robert, Oct 28 22:45: Track D is pushed
through locally first (`benchmarks/lmstudio/PLAN.md`, "The local push"); Runpod starts after that, at Stage 0. The local plan is
`benchmarks/lmstudio/PLAN.md`. The costs from here to the writeup (self-correct, k = 5, d1-real and the pilots, the
paired gaps, the frontier rows, T0 to T3 and the checkpoint evals) are `RoadDraft_Cost_Plan.md` at the repo root.

The one rule of the tree: a model with a Track D row on RobertsPC gets no Runpod row. `models.json` marks those
`trackd_local` and `runpod_campaign.py e3` refuses them without `--force`.

## The tree

Costs are one `d1-test` x 1 row (100 episodes, single mode, explicit prompts, k = 1), from the measured bills: the
Track P k = 3 campaign's per-episode cost x 100 for the nine rungs that ran (the Oct 20 d1-variance runs came in
under those, so they lean high), the Oct 16 estimates / 3 for the two that never ran, and the token counts of the
published runs at the listed per-token rates for the public endpoint.

**Local, not duplicated** (RobertsPC through LM Studio; `benchmarks/lmstudio/PLAN.md`):

| model | local row | the Runpod rung it excludes |
|---|---|---|
| Qwen3.5-9B Q4_K_M | d1-test 62.5, d1-real 63.6, hard-pilots partial (published) | `qwen3.5-9b` bf16, $4-6 |
| Gemma 4 12B Q8_0 | d1-test x 1, the night of Oct 28 (running) | `gemma-4-12b` bf16, $4-6 |
| GLM-4.6V-Flash Q4_K_M | d1-test x 1, queued behind Gemma | none on the ladder (the 4.7 Flash below is a different model) |
| Qwen3.5-4B BF16 GGUF | planned, waits on the download | `qwen3.5-4b` bf16, $2-3 |
| Gemma 4 E4B Q4_K_M | undecided (no submit on its smoke) | none on the ladder |

Devstral Small 2, Ministral 3 14B and Llama 3.1 8B are dropped locally and have no Runpod rung.

**Runpod, self-hosted bf16 on the Hub vLLM worker** (the Track P endpoints, parked at zero workers, bill nothing idle):

| # | rung | model | pool, $/h | endpoint | d1-test x 1 | Track P (k = 3) | note |
|---|---|---|---|---|---|---|---|
| 1 | 35B MoE, 3B active | `qwen3.6-35b-a3b` | BLACKWELL_96, $3.49 | `wn6oehzs020wpc` | $5-8 | 67.7%, 3rd | the best open row so far (86.7 on d1-variance); first |
| 2 | 31B dense | `gemma-4-31b` | BLACKWELL_96 / ADA_80_PRO, $3.49 | `kgu6d0ogfm0oyu` | $10-14 | 74.7%, 2nd | the top open-weight probe row |
| 3 | 27B dense | `qwen3.8-27b` | AMPERE_80 / ADA_80_PRO, $2.72 | `jbwqugdj3bxts8` | $14-18 | 64.6%, 4th | thinks at xhigh by default, hence the price |
| 4 | 26B MoE, 4B active | `gemma-4-26b-a4b` | AMPERE_80 / ADA_80_PRO, $2.72 | `lnljvntj92giid` | $8-10 | 49.5%, 6th | |
| 5 | 30B MoE, 3B active | `glm-4.7-flash` | BLACKWELL_96 / ADA_80_PRO, $3.49 | `cwvlr4nqczsrvl` | $7-9 | 38.4%, 9th | kin of the local GLM-4.6V-Flash, not the same model; Robert may strike it |
| 6 | 21B MoE, 3.6B active | `gpt-oss-20b` | AMPERE_48, $1.22 | `823ffmdxxfz2v2` | $1-2 | 13.1%, 11th | no tool call in 76% of its probe episodes; expect a row near 0 |
| 7 | 117B MoE, 5.1B active | `gpt-oss-120b` | AMPERE_80 / ADA_80_PRO, $2.72 | `7maayov2g1xjoi` | $4-6 | never run | REST-created; redeploy from the Hub first; the 20b's harmony troubles likely |
| 8 | 122B MoE, 10B active | `qwen3.5-122b-a10b` | HOPPER_141 (H200), $5.93 | `d1aaw4ddzlsghg` | $7-10 | never run | FP8 (Qwen's release); redeploy first; H200 stock was Low |

**Runpod public endpoints** (Runpod serves the model, per-token billing, the same `/openai/v1` route and key; read with
`list-public-endpoints` on 2026-10-28 21:40 PDT):

| # | model | endpoint | $ per M tokens | d1-test x 1 | note |
|---|---|---|---|---|---|
| 9 | GLM-5.3 (`glm-5.3`) | `b1dd8hy2hqo1nb` | in 0.77, cached in 0.143, out 2.42 | $20-35 cached, $50-85 not | 262K context, function calling, thinking shown; the largest open-weight model Track D can reach; smoke first |

Live but not in the tree: Kimi (`moonshot-kimi`: K2.6 / K2.7 Code $0.95 in / $4.00 out, K3 $3 / $15, K3.1 Pro $2 / $10 per M;
$30-95 a row at best, $300 for K3), IBM Granite 4.0 H Small 32B (`granite-4-0-h-small`) and Qwen3 32B AWQ
(`qwen3-32b-awq`), both without a listed price and a generation old. GLM-4.7-Flash's public endpoint is offline.

Why the public endpoint prices this way: each turn of an episode resends the transcript, so one d1-test episode sends
0.6 to 1.0 million cumulative input tokens (d1-real 1.5M, hard-pilots 2.7M) and writes 10 to 22 thousand; input is the
bill, and Runpod's prompt cache (the $0.143 rate on the resent prefix) decides whether a row is $20-35 or $50-85. The
harness records cached input per turn (`prompt_tokens_details.cached_tokens` -> `cache_read_input_tokens`), so a
five-episode smoke measures the cached share before a ranked run. `glm-5.3` is priced in
`src/roaddraft/eval/prices.json`, so `--cost-cap` holds its run and the board shows cost per sheet.

## The $110

| set | rows | cost |
|---|---|---|
| **A. recommended** | rungs 1-5 (the five measured mid and large rungs) | $44-59 |
| | + rung 9, GLM-5.3, `--cost-cap 40` | $20-40 |
| | + rung 6, gpt-oss-20b, for completeness | $1-2 |
| | **total** | **$65-101** |
| B. no public endpoint | rungs 1-8, the whole self-hosted ladder | $57-77, leaving $30 for d1-real x 1 on the top two rows ($24) |
| C. the big ones | rung 9 uncapped + rungs 1-4 | $70-125 |

Set A gives the board nine d1-test rows beside the local three (the headline needs three or more) and the one row
that reaches past a single card. What is left of the $110 after it, if the cache works, goes to the two redeploys
(rungs 7 and 8, $11-16) or is held for d1-real x 1 on the top row. Self-correct mode (the eval plan's second column),
k = 3 for an interval under 5, and the nine image pilots stay off this budget.

## APIs instead of Runpod (Robert's question, Oct 28 evening)

The harness takes any OpenAI-compatible endpoint (`--provider openai --base-url ... --api-key-env ...`), so an API
costs nothing to hook up. Whether it is cheaper turns on the same arithmetic as the public endpoint: a row sends
60 to 100 million input tokens, so the input rate and the provider's prompt cache set the price, and output hardly
matters. Per 100 d1-test episodes, uncached unless said (API rates from third-party trackers on Oct 28, 2026, to
be read off the provider's own page before a run):

| model | Runpod self-hosted | per-token APIs |
|---|---|---|
| Qwen3.6-35B-A3B | $5-8 | OpenRouter about $0.14 in / $1.00 out, DeepInfra $0.10-0.15 / $0.95: $10-16 |
| Gemma 4 31B | $10-14 | OpenRouter $0.10-0.13 / $0.34-0.38, DeepInfra $0.09-0.20 / $0.34-0.40 (turbo: cached in $0.05), Together $0.20 / $0.50: $9-20 |
| GLM-5.3 | (no single card holds it) | Runpod public $0.77 / $2.42 (cached $0.143): $50-85, $20-35 cached; Z.ai $1.40 / $4.40 (cache read $0.26): $90-150, $30-50 cached; DeepInfra from $1.20 in: $80-130 |
| GLM-5.3 FlashX (a smaller sibling) | | OpenRouter $0.37 / $1.25: $25-40 |

So: for the rungs a card holds, an API is about even with self-hosting (a little dearer for the MoEs, since four
episodes share one worker and vLLM's prefix cache is free) and buys no cold start, no 570 s cut-off, no stock waits
and free concurrency; it costs the row its known precision (the board's bf16 vLLM class; a provider serves what it
serves and may change it), adds rate limits, and the bill scales with tokens rather than hours, so a thinking model's
long turns cost instead of merely taking time. For the models past one card (GLM-5.3, Kimi, DeepSeek) the API is the
only route short of a $12-48/h multi-GPU node, and Runpod's public endpoint is the lowest GLM-5.3 price found on Oct 28.
Sources: [GLM-5.3 on pricepertoken](https://pricepertoken.com/pricing-page/model/z-ai-glm-5.3),
[GLM-5.3 on developersdigest](https://www.developersdigest.tech/models/glm-5-3),
[GLM-5.3 on computeprices](https://computeprices.com/providers/openrouter/models/glm-5-3),
[GLM-5.3 FlashX on anotherwrapper](https://anotherwrapper.com/llm-pricing/glm-5.3-flashx),
[Qwen3.6-35B-A3B on anotherwrapper](https://anotherwrapper.com/llm-pricing/qwen3.6-35b-a3b),
[Qwen3.6-35B-A3B on computeprices](https://computeprices.com/providers/openrouter/models/qwen3-6-35b-a3b),
[Qwen3.6-35B-A3B on OpenRouter](https://openrouter.ai/compare/qwen/qwen3.6-35b-a3b),
[Gemma 4 31B on computeprices (DeepInfra)](https://computeprices.com/providers/deep-infra/models/gemma-4-31b-it),
[Gemma 4 31B on llmreference (Together)](https://www.llmreference.com/model/gemma-4-31b-it/together-ai),
[Gemma 4 31B on computeprices (OpenRouter)](https://computeprices.com/providers/openrouter/models/gemma-4-31b-it).

## Before a go (no cost)

1. **Robert lifts the Oct 24 local-only rule** for Runpod, and tops up the balance: $11.99 on Oct 20, the last figure
   on record; set A needs about $100 above it.
2. **Re-pin the campaign worktree.** `runpod_campaign.py` pins runs to `.claude/worktrees/runpod-k3` at `PIN`
   2658fa0 (Oct 19): verifier v5, the old d1-real, no `--context-tokens`, no stall guard. A Track D run today needs
   a worktree at a main commit that holds d1-verify-v7, the question groups (2cce1ef6), the harness context budget
   (291ae711), the CLI route (798f05c6) and the stall guard once it is committed (uncommitted on main, Oct 28
   evening). Then `git worktree add --detach .claude/worktrees/runpod-trackd <commit>` and move `WORKTREE` / `PIN`.
3. **The 570 s cut-off.** Runpod's proxy ends a streamed request after 570 s; a thinking model's long turn reaches
   it. The eval provider records it as an infrastructure `error` and the report leaves the episode out of the
   score (ten of Gemma 4 12B's hundred on Oct 20), where the probe board counts it as the model's budget stop. Score
   it as a `turn_time` budget trip before any ranked row. Whether the public endpoint has the same limit, the smoke
   shows.
4. **The window.** `common_env` sets `MAX_MODEL_LEN` 65536 on every self-hosted endpoint, where vLLM refuses a
   longer prompt and the episode ends as a context trip (about 17 in 100 d1-test episodes at the 9B's transcript
   sizes). Set 131072 per endpoint where the card has room (`env` on the spec, `create --again` or an update), as
   the local rows run; the public endpoint has 262K and the spec passes it as `--context-tokens`.
5. **Redeploy rungs 7 and 8 from the Hub** if they are in (`deploy-hub-repo`, as `wn6oehzs020wpc` was on Oct 17);
   their REST-created endpoints never ran.
6. **Smoke GLM-5.3**: `e3-smoke glm-5.3` (d1-dev[:5], $1-4) for the cached share, the thinking format on the stream,
   tool calls, and any per-request limit, then its `models.json` sampling if the endpoint's defaults misbehave.
7. Each self-hosted rung: `warm` (the queue route), then `e3 NAME --taskset d1-test --samples 1`, then `workers NAME 0`;
   several endpoints may run at once (the account's spend limit is $80/h; set A at once is about $16/h).
8. After each run: `python -m roaddraft.eval report results/e3-runpod/<run id>` then `--publish`, and
   `scripts/make_leaderboard.py`; the episodes stay in `results/e3-runpod/` (gitignored). The display names in
   `src/roaddraft/runners/leaderboard.py` `NAMES` want the new ids so the rows read as the ladder does.

## Commands (shown with `--print`, run nothing)

    python benchmarks/runpod/runpod_campaign.py list                                   # the tree, local rows marked
    python benchmarks/runpod/runpod_campaign.py e3-smoke glm-5.3 --print               # the public endpoint, five d1-dev episodes
    python benchmarks/runpod/runpod_campaign.py e3 qwen3.6-35b-a3b --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 gemma-4-31b --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 qwen3.8-27b --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 gemma-4-26b-a4b --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 glm-4.7-flash --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 gpt-oss-20b --taskset d1-test --samples 1 --print
    python benchmarks/runpod/runpod_campaign.py e3 qwen3.5-9b --taskset d1-test --samples 1      # refused: local row (--force overrides)

## Rules carried over

- No run without Robert's go; `create` and `list` cost nothing, `warm`, `smoke`, `k3`, `e3` and `e3-smoke` bill.
- Precision as recorded in `models.json` (bf16 where one card holds it, the release's FP8 / mxfp4 otherwise; a public
  endpoint serves what Runpod serves and the card says so); a change is asked first.
- One row per model per run folder; a rig change (window, worktree pin) between episodes is a new run id, not a resume.
- Park every self-hosted endpoint (`workers NAME 0`) when its run ends; the account allows 10 max workers in all.
- The local-duplicate rule above: `trackd_local` in `models.json`, refused by `e3` without `--force`.
