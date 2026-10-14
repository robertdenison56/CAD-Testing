# Runpod serverless: open-weight models for the probe runs

The local GPU (RTX 4060, 8 GB) needed ~35 h for Qwen3.5-9B at k = 3, so that run was stopped and deleted on
Oct 9 2026 (654e434). This folder records the serverless endpoint that replaces it. The runner needs nothing
Runpod-specific: Runpod's vLLM worker speaks the OpenAI chat-completions API, so `--backend openai` drives it
with a different base URL and key.

**Status, 2026-10-12: set up, nothing run yet; prefix caching stays on (decided 2026-10-12, see below).** No probe has gone through the endpoint. One smoke job was
submitted by mistake and cancelled while still queued (`5e840173-…-u2`, CANCELLED, never ran).

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
