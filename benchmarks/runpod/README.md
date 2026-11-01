# Runpod serverless: open-weight models for the probe runs

**Track D on Runpod (2026-10-28): the model tree, the $110 spread and what comes before a go are in [`PLAN.md`](PLAN.md)**;
this file is the rig and the run records.

The local GPU (RTX 4060, 8 GB) needed ~35 h for Qwen3.5-9B at k = 3, so that run was stopped and deleted on
Oct 9 2026 (654e434). This folder records the serverless endpoint that replaces it. The runner needs nothing
Runpod-specific: Runpod's vLLM worker speaks the OpenAI chat-completions API, so `--backend openai` drives it
with a different base URL and key.

**Status, 2026-10-16 night: the ladder is packaged, nothing run.** Eleven endpoints exist (the Qwen3.5-9B one from Oct 9 and
ten new ones, parked at max workers 0, so nothing bills); `models.json` and `runpod_campaign.py` hold the specs and the
commands; the runs start on Robert's word (see "The ladder" at the end of this file). Earlier: the Qwen3.5-9B k = 3 row ran
Oct 13 to 14 (the run record below); before that, one smoke job was submitted by mistake on Oct 12 and cancelled while
still queued (`5e840173-…-u2`, CANCELLED, never ran).

## The endpoint

| | |
|---|---|
| name / id | `roaddraft-qwen3.5-9b` / `zee0sos76mivwk` (template `txoq97fpbu`), created 2026-10-09 20:12 UTC |
| worker | Hub `runpod-workers/worker-vllm` release v2.29.0 (`hubReleaseId cmuxgi0a3000407jv5igk1ezr`), image `registry.runpod.net/runpod-workers-worker-vllm-main-dockerfile:b7212acc6`, CUDA 13.0 only |
| model | `Qwen/Qwen3.5-9B`, bf16 safetensors, served under that name |
| env set | `MAX_MODEL_LEN=65536`, `ENABLE_AUTO_TOOL_CHOICE=true`, `TOOL_CALL_PARSER=qwen3_coder`, `REASONING_PARSER=qwen3`, `ENABLE_PREFIX_CACHING=true`; the rest are release defaults (`GPU_MEMORY_UTILIZATION=0.95`, `MAX_CONCURRENCY=30`) |
| GPU | pools `AMPERE_48` (A40, RTX A6000: $1.22/hr serverless) and `ADA_48_PRO` (L40S, L40, RTX 6000 Ada, PRO 6000 MIG 48 GB: $1.75/hr), 1 GPU, 60 GB container disk |
| scaling | workers 0..1, idle timeout 120 s, FlashBoot on, queue-delay scaler 4 s |
| job timeout | 1,800 s, the runner's `TURN_LIMIT`: one turn is one job |

The parser flags are the model card's own `vllm serve` line (`--reasoning-parser qwen3 --enable-auto-tool-choice
--tool-call-parser qwen3_coder`). `qwen3_coder` is not in the Hub form's option list; the worker passes it through.

**Sizing.** 9.65B parameters (HF metadata); the four shards are 19.3 GB at bf16. Only 8 of the 32 layers are
full attention (`full_attention_interval` 4), each with 4 KV heads of dim 256, so the KV cache is 2 × 8 × 4 × 256
× 2 bytes = 32 KiB a token: 2.0 GiB for one 65,536-token conversation. The 24 linear-attention layers keep a
fixed state of about 50 MB per conversation. A 24 GB card leaves ~3 GB after the weights at 0.95 utilisation, too
tight for 65k plus activations; a 48 GB card leaves room for about ten 65k conversations, so the three repeats can
share one worker (vLLM batches them).

**Speed, an estimate, not measured.** Decode is bandwidth-bound: the A40 moves 696 GB/s, so one stream tops out
near 696 / 19.3 ≈ 36 tokens/s, and three concurrent streams cost about the same per step. The local run was
11-15 tokens/s at Q4_K_M.

**Not comparable with the local Qwen rows.** Those ran LM Studio's Q4_K_M GGUF at its own sampling; this is bf16
weights on vLLM. Label the rows so the two cannot be confused.

## Sampling

vLLM takes sampling defaults from a repo's `generation_config.json`, and Qwen3.5-9B ships none, so without help
every request would sample at temperature 1 over the whole vocabulary. The runner's `--extra-body` sends the model
card's thinking-mode settings with every request and writes them into each `run.json` as `extra_body`:

    {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}

## Running (when decided)

    export RUNPOD_API_KEY="$(jq -r '.mcpServers.runpod.headers.Authorization | sub("^Bearer ";"")' ~/.claude.json)"
    python -m roaddraft.runners run --backend openai --model Qwen/Qwen3.5-9B \
        --base-url https://api.runpod.ai/v2/zee0sos76mivwk/openai/v1 --api-key-env RUNPOD_API_KEY \
        --extra-body '{"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}' \
        --out benchmarks/probe_runs/2026-10-12-k3 --label qwen3.5-9b-bf16-vllm-r1 --budget 30 [PROBE ...]

`--out` is the folder of the campaign in progress (2026-10-12-k3: Haiku, Sonnet 5.5, Gemma on commit 2697ee5), so the board ranks this row beside them. The label carries `bf16-vllm` so the rows cannot be read as the deleted Q4_K_M LM Studio rows. The r2 and r3 repeats go in parallel as separate processes, as the Haiku k = 3 run did. Leave out `--lms-context`:
the LM Studio guard reloads models through `lms` and means nothing here. Launch detached (`nohup … & disown`);
a probe run outlives a tool call.

Still unverified, to check on the first probe (edge-c102, as with LM Studio):
- the first request's cold start: image pull, the 19.3 GB download, vLLM start-up. The runner waits up to
  1,800 s for a response and retries a 5xx three times, but no number is measured yet;
- that the OpenAI route streams tool-call deltas and the `include_usage` chunk the runner reads;
- that vLLM keeps prefix caching on for this hybrid model: the start-up log must show the `align` cache mode and
  the block size it chose (the Prefix caching section below says what to look for);
- the per-probe budget: a wall-clock budget means something different on this hardware than on the 4060.

## Prefix caching: on (decided 2026-10-12)

`ENABLE_PREFIX_CACHING=true` stays. Caching reuses the key/value state of a prefix an earlier request already
computed; the reused values are what recomputation would produce, so the model sees the same context and samples
the same distribution. It is a compute shortcut, not a modelling change, and it does not bias what the probes
measure.

It matters because the runner resends the whole conversation every turn with the ~22k-token tool schema in front.
The local Q4 r1 sent 25.4M input tokens per repeat to produce 0.5M new ones. Without caching every turn re-prefills
the transcript, late turns of long probes slow down, and the 30-minute wall-clock budget ends more episodes for
reasons that have nothing to do with the model. Every other row runs cached (Anthropic prompt caching on the
claude-code backend, LM Studio's prompt cache, Ollama cloud), so caching on is the like-for-like setting. It also
halves the bill.

What the hybrid changes. 24 of the 32 layers are Gated DeltaNet with a recurrent state, so vLLM can only resume
from a block boundary. The worker image pins vLLM v0.31.0 (`vllm/vllm-openai`), which handles this itself when
prefix caching is on: it switches Qwen3.5 to `--mamba-cache-mode align` (logged as set "by default when prefix
caching is enabled", marked experimental), requires chunked prefill (the template has `ENABLE_CHUNKED_PREFILL=true`),
and overrides the template's `BLOCK_SIZE=16` with a block big enough to hold the recurrent state, about 500 to 800
tokens ("Setting attention block size to N tokens" in the log). A hit then covers the schema and every completed
turn down to the last block boundary; the tail under one block is re-prefilled, negligible against the schema.
The three parallel repeats share the worker's cache, so the schema is prefilled once per worker lifetime.

On the first probe, read the worker log for the two lines above (Runpod MCP `stream-worker-logs`, or the console)
and write the block size into this file next to the run. The worker's `VLLM_EXTRA_ARGS` env is a raw passthrough to
`vllm serve` if a flag ever has to be forced. A bf16 recurrent-state cache (`--mamba-ssm-cache-dtype bfloat16`)
would halve the block but is a precision change and is not needed for this workload; leave it.

## Run record: 2026-10-14, the k = 3 campaign row

Robert's go on Oct 13 ("run Qwen 3.5 9B"). Smoke probe `edge-c102` first, as label `qwen3.5-9b-bf16-vllm-r1` in
`benchmarks/probe_runs/2026-10-12-k3`, then the three repeats as three parallel processes (r1 skipping the probe it
had). Worker `1rfpvxo1y90v5d`, one A40 in CA-MTL-1, image `b7212acc6`, vLLM v0.31.0.

| checked on the first probe | measured |
|---|---|
| cold start | container start 04:23:34 UTC, `Application startup complete` 04:28:44: **5 min 7 s** (weights 3.3 s to load from cache, model load 28 s and 17.65 GiB, engine init 188 s of which 21 s compilation) |
| prefix caching on this hybrid | `Mamba cache mode is set to 'align' for Qwen3_5ForConditionalGeneration by default when prefix caching is enabled` |
| block size | `Setting attention block size to 528 tokens to ensure that attention page size is >= mamba page size` (mamba page padded 0.76%); `kv lcm block sizes 528` |
| KV cache | 677,872 tokens on the A40: maximum concurrency 10.34x at 65,536 tokens per request, so the three repeats share one worker |
| throughput | prompt 4,023 tokens/s on the first (cold-cache) turn; generation 20 to 28 tokens/s; prefix-cache hit rate 49% -> 73% -> 79% across the first probe's turns |
| the smoke probe | PASS: 5 calls, 0 faults, 6 turns, 367 s wall clock including the cold start; 247k input tokens counted (the schema resent each turn; cached server-side), 1,130 output of which 588 reasoning |
| streaming | tool-call deltas and the usage chunk came through the OpenAI route as the runner expects; no retries, no truncated results |

A note in the vLLM log worth knowing: the chat template is system-first, so vLLM merges any inline system
messages into the leading system prompt; the runner sends one system message, so nothing is merged.

**The campaign's bill.** 99 episodes plus the smoke probe and two reruns, 21:29 to 01:45 PDT on one A40 worker
(the three repeats shared it): 1,689 turns served, 14 failed on the proxy side (two of them ended episodes: a
connection reset and the 570-second limit on one streamed turn; rerun). `list-serverless-billing` for the week:
GPU $4.19, disk $0.03, **$4.22**; the balance read $94.65 at the end, $5.35 down, the difference the billing
bucket's lag. The estimate was $6 to $10.

## Cost and teardown

Nothing bills while no worker runs (min workers 0). A worker bills per second from start until it stops,
including the 120 s idle window after the last request.

Estimate, 2026-10-12 (nothing measured yet). Flex rates from the serverless pricing docs: `AMPERE_48` (A40, A6000)
$0.00034/s = $1.22/h; `ADA_48_PRO` (L40S, L40, 6000 Ada) $0.00053/s = $1.91/h (the $1.75 above was the console's
figure on Oct 9). Which pool serves decides the rate. The local Q4 r1 produced 507k output tokens over 11.7 h
(12 tokens/s); at the A40's ~30-36 tokens/s one repeat is 4 to 5 h, and the three repeats batched on one worker
take about the same wall time, plus one cold start and the idle tail (~$0.20).

| case | cost |
|---|---|
| expected, prefix caching working | $6 (A40) to $10 (L40S) |
| prefix caching silently off (76M tokens of prefill) | $12 to $20 |
| ceiling: every probe hits the 30-min budget on every repeat, repeats batched | 16.5 h, $20 to $32 |

Account on 2026-10-12: balance $100, spend limit $80, no spend. gpt-oss:120b-cloud on Ollama cloud is billed by
plan, not per token: $0 on the Free plan (the Sep 24/27 passes ran on it; glm was refused as not in free usage) if
the 5-hour and weekly GPU-time windows allow ~99 episodes, otherwise one month of Pro at $20. Teardown when done: delete endpoint `zee0sos76mivwk`,
then template `txoq97fpbu` (Runpod MCP `delete-endpoint` / `delete-template`, or the console).

## The ladder (packaged 2026-10-16, for the Oct 17 campaign)

Robert's ask (Oct 16 evening): run the probes and other models through Runpod, a range of parameter counts, as
ready as possible for a "go" the next day. What was searched, decided and built that night:

**What the field says (Oct 2026).** No single authority ranks open-weight tool use; the aggregators disagree, and most
figures are vendor-reported. [Morph's guide](https://www.morphllm.com/best-open-source-llm) puts Kimi K3 first overall
and names DeepSeek-V4.1-Flash the best MIT-licensed agentic model; [BenchLM's tool-use board](https://benchlm.ai/best/tool-use)
has GLM-5.1 as the top open-weight entry; [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/) picks
Qwen3.6-35B-A3B or GLM-4.7-Flash for a 24-32 GB card; [BFCL snapshots](https://llm-stats.com/benchmarks/bfcl-v4) keep
Qwen3.5-family rows near the top; [Meta's Muse Spark Open](https://research.meta.ai/blog/muse-spark-open) (816B, Oct 15)
and [Reflection's Beam](https://www.unite.ai/reflection-releases-beams-open-weights-under-apache-2-0-license/) (501B,
Oct 16) landed the same week. Everything at the top of those lists is 300B to 1T parameters (Hugging Face metadata, read
Oct 16: Kimi-K3 ~1T, DeepSeek-V4.1-Flash 763B, GLM-5.3-Flash 321B, MiniMax-M2.7 229B, Qwen3.8-Flash-Next 180B), which is
a multi-GPU node per model, $12 to $48 an hour. The ladder below stays inside one card (the `out_of_range` block in
`models.json` lists the rest), and covers four families from 4B to 122B.

**The ladder.** All on the Hub vLLM worker (v2.29.0, image `b7212acc6`, vLLM v0.31.0, CUDA 13.0 hosts), one GPU, workers
0..1, idle 120 s, 1,800 s job timeout, prefix caching on, 65,536-token context, the worker's parsers from each model
card or the vLLM recipe (all present in v0.31.0's registries, checked), sampling from each card as `extra_body`. Rates are
the serverless flex price of the cheapest pool (`list-gpu-types`, Oct 16); the campaign estimate is 99 episodes in 4 to
7 hours on one worker and stands until the first probe measures it.

| rung | model (HF id) | precision | pool, $/h | k = 3 est. | endpoint |
|---|---|---|---|---|---|
| 4B dense | `Qwen/Qwen3.5-4B` | bf16 | AMPERE_24 (3090 / A5000), $0.69 | $3-5 | `06vht0xd9ntlps` |
| 9B dense, rerun on the clean help text | `Qwen/Qwen3.5-9B` | bf16 | AMPERE_48 / ADA_48_PRO, $1.22 | $4-6 (measured $4.22) | `zee0sos76mivwk` |
| 12B dense | `google/gemma-4-12B-it` | bf16 | AMPERE_48 / ADA_48_PRO, $1.22 | $5-8 | `opp76sn4ruhsd0` |
| 21B MoE, 3.6B active | `openai/gpt-oss-20b` | mxfp4 (the release) | AMPERE_48, $1.22 | $4-7 | `823ffmdxxfz2v2` |
| 27B dense | `Qwen/Qwen3.8-27B` | bf16 | AMPERE_80 (A100) / ADA_80_PRO (H100), $2.72 | $14-20 | `q1q8usgljl3fwt` |
| 31B dense | `google/gemma-4-31B-it` | bf16 | BLACKWELL_96 (RTX PRO 6000) / ADA_80_PRO, $3.49 | $17-25 | `8hawhgdmvgbe2a` |
| 30B MoE, 3B active | `zai-org/GLM-4.7-Flash` | bf16 | BLACKWELL_96 / ADA_80_PRO, $3.49 | $12-18 | `cwvlr4nqczsrvl` |
| 35B MoE, 3B active | `Qwen/Qwen3.6-35B-A3B` | bf16 | BLACKWELL_96, $3.49 | $10-15 | `y27c5iljez2qon` |
| 26B MoE, 4B active | `google/gemma-4-26B-A4B-it` | bf16 | AMPERE_80 / ADA_80_PRO, $2.72 | $9-14 | `lnljvntj92giid` |
| 117B MoE, 5.1B active | `openai/gpt-oss-120b` | mxfp4 (the release) | AMPERE_80 / ADA_80_PRO, $2.72 | $11-16 | `7maayov2g1xjoi` |
| 122B MoE, 10B active | `Qwen/Qwen3.5-122B-A10B-FP8` | FP8 (Qwen's release; bf16 needs two cards) | HOPPER_141 (H200), $5.93 | $20-30 | `d1aaw4ddzlsghg` |

The whole ladder is roughly $110-160; the account's balance read $94.65 after the Oct 14 run and its spend limit is
$80/hour by default, so the day's set is a choice. Parsers: Qwen `qwen3_coder` + `qwen3`; Gemma `gemma4` + `gemma4`
with the recipe's `tool_chat_template_gemma4.jinja` through `VLLM_EXTRA_ARGS`; gpt-oss `openai` + `openai_gptoss`;
GLM `glm47` + `glm45`. Stock on CUDA 13.0 hosts the night of Oct 16: A100 SXM High, H100 SXM Medium, everything else Low
(`get-capacity`); a Low pool can throttle a worker for a while, which the `/health` read shows as `throttled`.

**Decisions open for Robert (each a one-line change in `models.json`):**

1. Which rungs, in what order. A sensible first day: the 4B, the 27B (Qwen3.8), one Gemma (12B or 31B), GLM-4.7-Flash,
   gpt-oss-120b, about $50-70; the 9B rerun ($4) whenever; the 122B last.
2. Precision. bf16 wherever one card holds it, as the Qwen3.5-9B row was run. FP8 releases by the model makers would
   put Qwen3.8-27B (28 GB) and Qwen3.6-35B-A3B (36 GB) on a $1.22 A40 instead of $2.72-3.49 cards; the 122B is FP8 by
   necessity. Changing precision is Robert's call (the Oct 12 rule).
3. Thinking. Qwen and gpt-oss think by default and run so; Gemma 4's card default is thinking off, and the spec turns it
   on through `chat_template_kwargs` so every row is the model's best effort. Qwen3.8's `reasoning_effort` is `xhigh`
   by default (`medium` and `low` exist); gpt-oss's is `medium`.
4. The E3 smoke (Track D, `d1-dev[:5]` × single × explicit) rides on any of these endpoints: `e3-smoke NAME`, about
   $1-2; Qwen3.8-27B is the natural pick.

**The script.** `benchmarks/runpod/runpod_campaign.py` (stdlib only, run with the repo's `.venv/bin/python`):

| command | what it does |
|---|---|
| `list` | the ladder as a table, with endpoint ids |
| `key-check` | the key is in `~/.claude.json` (the Runpod MCP header; never printed) and lists the account's endpoints and max-worker total |
| `pins` | the worktree's engine commit and tool/instruction digests; exits 1 unless they are `e7178a2`, `60eeeb21…`, `4dff2849…`, clean |
| `create NAME…` | POST `/v2/serverless` from the spec; writes the id back into `models.json` (done for all eleven) |
| `workers NAME N` | max workers; 0 parks an endpoint (bills nothing, frees one of the account's **10 max workers across all endpoints**, pauses the gateway) |
| `status` | `/health` per endpoint: workers by state, jobs by state (free) |
| `smoke NAME` | arms the endpoint (max 1, 30 s), runs `edge-c102` as `<label>-r1` in the foreground, prints the run.json pins |
| `k3 NAME [PROBE…]` | three detached processes, labels `-r1..r3`, logs `run-<label>-rN.log` in the campaign folder |
| `e3-smoke NAME [--dry-run]` | `roaddraft.eval run --taskset d1-dev --limit 5 --provider openai …` into `results/e3-runpod/` |
| `score NAME` | `runners score` on the three labels (worktree code), then the board from the main checkout |
| `bill` | `/v2/billing/serverless` totals |
| `delete NAME… --yes` | the teardown, on Robert's word |

Every run uses the worktree `.claude/worktrees/runpod-k3` (detached at `e7178a2`) through `PYTHONPATH`, so the runner and
the MCP server it starts both come from the pinned code whatever happens on `main` meanwhile; `preflight` refuses a moved
or dirty worktree. The campaign folder is `benchmarks/probe_runs/2026-10-17-k3` (its RESULTS.md header is written); the
board's `NAMES` table knows the eleven ids. Checked Oct 16 night without spend: `pins` passes, `create --dry-run` bodies
match the Oct 9 endpoint's shape, `smoke`/`k3`/`e3-smoke --print` print the exact commands, the E3 `--dry-run` lists the
five d1-dev cells, 34 runner tests pass, `leaderboard --check` is clean, and `/v2/billing/serverless` for the evening
reads $0 (an endpoint's Initializing/Idle workers are scaled-down and unbilled; the docs' worker-lifecycle table).

**Tomorrow, per model, on "go":**

    python benchmarks/runpod/runpod_campaign.py smoke qwen3.8-27b      # ~5-8 min cold start + 1 probe; read the worker log
    python benchmarks/runpod/runpod_campaign.py k3 qwen3.8-27b         # three repeats, detached; tail the three logs
    python benchmarks/runpod/runpod_campaign.py status                 # workers / jobs while it runs
    python benchmarks/runpod/runpod_campaign.py score qwen3.8-27b      # scores.json x3, then the board
    python benchmarks/runpod/runpod_campaign.py workers qwen3.8-27b 0  # park it: frees the quota for the next endpoint
    python benchmarks/runpod/runpod_campaign.py bill

On the first probe of each model, read the worker log (Runpod MCP `stream-worker-logs`, or the console) for the vLLM
start-up lines: the attention block size and the mamba cache mode (Qwen hybrids), that the tool parser loaded, and the
first turn's prefix-cache hit rate; write them into this file's run record with the cold start and the bill. Then a
RESULTS.md section in the campaign folder, regenerate the board, commit. When the ladder is done: `delete … --yes`.

## Run record: 2026-10-17, rungs 1-4, 6, 7, 9 (seven rows at k = 3)

Robert: "run 1-4 now" (Oct 17 14:47 PDT), "start LLMs 6, 7, and 9" (15:55). Smoke `edge-c102` first on each, then
the three repeats as three processes on one worker. Results, the marks and the two rig findings (the proxy's 570 s
streamed-request limit; Hub registry auth on REST-created endpoints) are in
`benchmarks/probe_runs/2026-10-17-k3/RESULTS.md`; the board ranks all seven (Qwen3.6-35B-A3B 67.7%, 5th overall).

| endpoint | worker and host | cold start | campaign | bill (two UTC days) |
|---|---|---|---|---|
| `06vht0xd9ntlps` Qwen3.5-4B | RTX PRO 6000 MIG 24 GB, US-PA-1 | ~3.5 min; 4,017 tok/s prompt, 24 tok/s generation, prefix hits 49% on the first probe | 4.0 h | $2.29 |
| `zee0sos76mivwk` Qwen3.5-9B | A40, CA-MTL-1 (worker `1rfpvxo1y90v5d`, the Oct 14 one) | FlashBoot | 4.0 h | $4.96 |
| `opp76sn4ruhsd0` Gemma 4 12B | RTX PRO 6000 MIG 48 GB, US-PA-1 | 3 min 41 s, torch.compile 54 s, KV 20.9 GiB, block size 64 | 2.6 h + reruns | $4.34 |
| `823ffmdxxfz2v2` gpt-oss-20b | A40, CA-MTL-1 | 1 min 52 s: weights 17 s, 12.8 GiB, Marlin mxfp4 MoE, KV 1,067,841 tokens | 1.1 h | $1.28 |
| `cwvlr4nqczsrvl` GLM-4.7-Flash | H100 80 GB, US-NE-1 | 8 min 4 s the first time (58 GB download 302 s), lost to the 570 s limit; recycled, warm job 212 s | 1.0 h | $6.96 |
| `wn6oehzs020wpc` Qwen3.6-35B-A3B (Hub) | RTX PRO 6000 96 GB, EUR-IS-2 | the REST endpoint's host could not pull the image; Hub redeploy, warm job, smoke 14 s | 1.2 h | $4.72 |
| `lnljvntj92giid` Gemma 4 26B-A4B | H100 80 GB, US-NE-1 then US-MO-1 | two cold starts lost to the 570 s limit (the engine restarted once); warm job 354 s | 1.2 h + reruns | $8.43 |

$32.97 for the seven (`list-serverless-billing`, GPU $32.82 + disk $0.15; the estimate was $45-70). All seven endpoints
parked at max workers 0 afterwards (`key-check`: 0 max workers in all). Script additions that day: `warm` (queue-route
cold start), `rerun` (infrastructure errors only: resets, 5xx, a 570 s cut-off with no turn finished), `workers`.
Board rules added the same day (`leaderboard.py`): vLLM's harmony-parser rejections are the model's failures
(`MODEL_ERRORS`), a 570 s cut-off of a model's own turn is a budget failure (`BUDGET_ERRORS`), and a row's class
and runner are read from an episode that carries a `base_url`.

## Run record: 2026-10-18, rungs 5 and 8 (nine rows at k = 3 in all)

Robert: "run 5 and 8" (Oct 17 19:46 PDT). Both REST-created endpoints were replaced from the Hub release first (see
`RESULTS.md`): Qwen3.8-27B `q1q8usgljl3fwt` -> `jbwqugdj3bxts8` (template `eut9etktaf`; the AP-IN-1 host looped on
container start without Hub registry auth), Gemma 4 31B `8hawhgdmvgbe2a` -> `kgu6d0ogfm0oyu` (template `emvezgpnkp`,
BLACKWELL_96 only: an H100 80 GB ran out of GPU memory at startup, about 16k tokens of context possible beside the
62.5 GB of weights). `warm` gained a retry on the 409 the gateway answers for a while after arming. Results: Gemma 4
31B 23, 27, 24 = 74.7% (5th, level with Haiku 4.5), Qwen3.8-27B 64.6% on the board (8th; 25 context-outs and three
first-turn 570 s cut-offs counted as budget stops, so `rerun` no longer touches 570 s cut-offs at all).

| endpoint | pool | cold start (warm job) | campaign | bill |
|---|---|---|---|---|
| `jbwqugdj3bxts8` Qwen3.8-27B (Hub) | AMPERE_80 / ADA_80_PRO | 273 s | 3 h 46 min | $15.34 (+ $0.55 on `q1q8usgljl3fwt`) |
| `kgu6d0ogfm0oyu` Gemma 4 31B (Hub) | BLACKWELL_96 | 257 s | 3 h 46 min | $10.30 (+ $1.53 on `8hawhgdmvgbe2a`) |

Nine rows, two UTC days: **$65.44** (`list-serverless-billing`, GPU $65.17 + disk $0.27). Every endpoint is parked at
max workers 0 (`key-check`: 0 max workers in all); the two unrun rungs (gpt-oss-120b `7maayov2g1xjoi`,
Qwen3.5-122B-A10B-FP8 `d1aaw4ddzlsghg`) are still REST-created and should be redeployed from the Hub before a run.

## Run record: 2026-10-18, gpt-oss-20b again with `--send-reasoning`

Robert: "do number 1" (Oct 18 evening): rerun gpt-oss-20b at k = 3 with the runner's `--send-reasoning` (`727fb7f`),
which sends a tool-call turn's thinking back as harmony's analysis channel. `models.json` gained `send_reasoning`
(both gpt-oss rungs) and `campaign` (this row's folder, `2026-10-18-gpt-oss-k3`, since the board makes one row of a
model per folder); `runpod_campaign.py` reads both, and `PIN` is now `727fb7f` (the runner and board rules past
`e7178a2`; engine and tool surface unchanged). Same endpoint `823ffmdxxfz2v2` (A40), smoke then three processes on
one worker, 01:08 to 01:53 UTC; parked at max workers 0 afterwards.

Result in `benchmarks/probe_runs/2026-10-18-gpt-oss-k3/RESULTS.md`: 6, 5, 2 of 33 = 13.1% [4.0, 24.2], last of the
board's nine, superseding the Oct 17 row (7.1%). The flag ended the harmony parser rejections (17 to 0) and 13 of
the 22 tool-using episodes passed (7 of 32 before), but 77 of 99 episodes made no tool call at all, which the flag
cannot reach. Bill: about $1 by worker time; $0.43 posted for Oct 19 UTC by 02:30 UTC.
gpt-oss-120b (`7maayov2g1xjoi`, still REST-created) would run with `send_reasoning` too; not run.

## Run record: 2026-10-18, the E3 smoke run (Track D) on Qwen3.6-35B-A3B

Robert picked Qwen3.6-35B-A3B for the smoke, and open-weight models first for Track D (the frontier route decided
once the smoke had measured tokens per sheet). The reference agent and the fake oracle first scored 100 on the
same five tasks from the pinned worktree (`727fb7f`). `runpod_campaign.py warm qwen3.6-35b-a3b` (the queue route,
288 s to a warm worker), then `e3-smoke qwen3.6-35b-a3b`: `d1-dev[:5]` × single × explicit, three at a time,
316 s for the longest episode; the endpoint `wn6oehzs020wpc` was parked at max workers 0 straight after. Effective
62.4 on five task types, 0 invalid calls; the measurements and the two findings are in the eval plan §8. Results
in `results/e3-runpod/e3-smoke-qwen3.6-35b-a3b` (gitignored). Bill: about $0.60 by worker time at $3.49/h.


## Run record: 2026-10-20, `d1-variance` × 5 on the five cheapest rows (Track D)

Robert: "run d1 variance x 5 for the 5 cheapest models" (Oct 19 19:50 PDT), after the harness's file-access fix
(`89f7a130`, `e3-v2`) was merged first at his word: the runs are pinned to `2658fa0d` (main `a1c0038b` + the fix;
in main as `821ac291`), oracle 100 and null 0 on all 20 tasks there, 154 eval/verifier tests green. Each model:
`warm` (queue route), `e3 NAME` (`d1-variance` × 5 × single × explicit, 4 at a time, into
`results/e3-runpod/e3-d1-variance-<name>-single`, gitignored), then parked. Started 02:57 UTC Oct 20; Robert
cancelled the rest at 04:38 UTC ("cancel all runpod runs"): the two running evals were stopped and every endpoint
parked (per-worker reads 0 workers on all five, account spend $0/h). Robert then had the unfinished runs removed
("remove any unfinished runs and commit the rest"): Qwen3.5-9B (70 of 100 episodes) and Qwen3.5-4B (56) went to
the SSD Trash, and gpt-oss-20b never started (two 25-min warm waits throttled: no A40 in AMPERE_48; an A100
fallback pool was not set). The two finished runs are published (`report --publish`) to `benchmarks/runs/<run id>/`
and listed, not ranked, on `benchmarks/runs/LEADERBOARD.md`; their episodes stay in `results/e3-runpod/` (gitignored).

| row | episodes | effective | read |
|---|---|---|---|
| Qwen3.6-35B-A3B `wn6oehzs020wpc` | 100 of 100 | 86.8 (report [84.2, 89.4]; over the 20 tasks [76.1, 95.6]) | all submitted, 0 cut-offs; SD within a task 17.7, between tasks 22.4 |
| Gemma 4 12B `opp76sn4ruhsd0` | 100 of 100 | 69.3 by the report (10 episodes left out as `error`), 66.3 with them as budget stops | the 10 are Runpod's 570 s cut-off of a model turn; SD within 28.2, between 30.0; hard-fail 12% |

Two harness findings: the eval provider records Runpod's 570 s stream cut-off as an infrastructure `error`, so
the report leaves it out of the score, where the Track P board counts it as the model's budget stop
(`BUDGET_ERRORS`); and the report's interval sizing on `d1-variance` uses the type-stratified bootstrap, which
has one or two tasks per type to resample here and reads too narrow (Gemma ±3.0 → "7 tasks for the target"; the ± on `benchmarks/runs/LEADERBOARD.md` is that figure).
A by-type projection from the within-task and within-type spread puts `d1-test` (100 tasks) at a half-width of
about 4.3 (k = 1) / 3.2 (k = 3) for Qwen3.6 and 6.0 / 4.0 for Gemma 12B (rough: four types hold two tasks).
Bill: the balance read $22.35 before and $11.99 after ($10.36); `list-serverless-billing` had posted $5.32 for
Oct 20 UTC by 04:40 (Qwen3.6 $2.39, Gemma 12B $1.22, 9B $1.22, 4B $0.48).
