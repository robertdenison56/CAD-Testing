# Plan: Track D on Runpod, the model tree (drafted 2026-10-28 evening)

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
