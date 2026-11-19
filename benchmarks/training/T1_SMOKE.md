# T1 smoke: runbook

Stage *T1 smoke* of `RoadDraft_Training_Plan.md` §4: 50 trajectories, one epoch, on a rented card. It proves
four things before T1 is priced: the training text equals what the server sends, the memory and the tokens a
second at the longest sequence, the adapter merges and quantizes to the board's Q4_K_M and loads, and the
served checkpoint runs 10 `d1-dev` episodes on the PC.

**Nothing here has run on a rented card. Every step below that touches Runpod waits for Robert's go**
(standing rule: "set up" means configure only). Every dollar figure is an **estimate**, with its arithmetic.

Files:

| file | what |
|---|---|
| `scripts/training_render.py` | the training text of a conversation and its trained spans (pure Python, shared) |
| `scripts/training_render_check.py` | the render check: trainer's text against the serving engine's, no GPU |
| `scripts/training_serving_stub.py` | a 74 MB stand-in GGUF (the 9B's tokenizer + template, a random 1-layer body) so llama-server renders and tokenizes as for the 9B |
| `scripts/training_lora.py` | the LoRA trainer (`--smoke`, `--prepare-only`, `--engine unsloth|hf`, `--tiny` for a CPU check) |
| `scripts/training_merge_quantize.py` | adapter into base, bf16 GGUF, Q4_K_M, load check |
| `tests/test_training_render.py` | masking, the note split, the round trip, against a recorded fixture |

## 1. What the render check found (run on this Mac, 2026-11-13)

`scripts/training_render_check.py` on 54 real conversations (up to 4 per file from all 20 files in
`results/training/`: the first, the one with most turns, the ones with a `[harness]` note, one with a masked
turn), **1,529 requests**. Trainer side: transformers 5.5.0 `apply_chat_template` with the 9B's
`tokenizer.json` and `chat_template.jinja` (sha256 `a4aee8af…`, HF revision `c2022362`). Serving side:
**LM Studio's own llama.cpp engine** (`~/.lmstudio/extensions/backends/llama.cpp-mac-arm64-apple-metal-advsimd-2.61.0/llama-server`,
build `b1-f174553`; LM Studio renders with llama.cpp's `jinja::` engine through `common_chat_templates_apply_jinja`,
found in its `libllm_engine.dylib`) on the stand-in GGUF, `/apply-template` and `/tokenize`.

| check | thinking **off** (prompt ends `<think>\n\n</think>\n\n`) | thinking **on** (prompt ends `<think>\n`; LM Studio's default, the board rows) |
|---|---|---|
| trainer render = `training_tokens.py`'s jinja2 render (the one calibrated exact against LM Studio's counts) | 54/54 equal | 54/54 equal |
| server prompt = trainer prompt, every request (tools JSON, tool-call XML, `True`/`None`/`4100.0`, tool results, notes) | 1,529/1,529 equal | 1,529/1,529 equal |
| server prompt is a string prefix of the training sequence | 1,529/1,529 | 1,529/1,529 |
| server token ids are a prefix of the training token ids | **1,529/1,529** | **0/1,529** |
| trained tokens = the turn's completion tokenized alone | **1,488/1,488** (41 weight-0 turns not trained) | **0/1,488** |
| completion parsed back (Qwen3-Coder parser rules) = the recorded calls and text | 1,488/1,488 | 1,488/1,488 |

With `--serve-template nothink` (the base template with the generation prompt always closed, no
`enable_thinking` sent, as LM Studio sends a request) the thinking-off column holds on all 1,529 requests too.

**Two mismatches found, both real, both handled:**

1. **Thinking on cannot be trained to match.** The template renders a past turn as `<think>\n\n</think>\n\n…`,
   which tokenizes as `<think>`, `\n\n` (271), `</think>`; the serving prompt with thinking on ends `<think>`,
   `\n` (198). So with thinking on, every turn's first generated token sits in a context the training data
   never has, and the target starts with a token split (`\n`, `</think>`) the training text never contains.
   This cannot be fixed in the data: later prompts re-tokenize the same text as 271. **Fix: serve the trained
   checkpoint with thinking off.** The merge script embeds the no-think template in the GGUF
   (`training_render.nothink_template`), so this does not depend on LM Studio passing `enable_thinking`. The
   training data has no thinking (shown work is visible text, plan §5 "Open for T1"), so the trained model is
   a no-think model by construction. **Decision for Robert:** the base and T0 rows run with thinking on; the
   trained rows would run with it off. Either accept that (the delta then includes "stopped thinking"), or
   also run base with thinking off on the same pin for a like-for-like base.
2. **The `[harness]` note.** It is a user message, so the template's "last query" moves to it and every
   assistant turn before it renders without its think block in the whole conversation, while the model wrote
   each of those turns after a prompt that had one. A single render of such a conversation trains those turns
   in the wrong context. `plan_segments` trains them in a shorter sequence cut after the last of them.
   Measured on the whole dataset (`--prepare-only`, below): **88 of 12,703 conversations** split, 196 extra
   sequences, **+21.6M tokens (+3.6%)**. A harness change (the note inside the last tool result) would remove
   the split, but it changes the eval surface, so it belongs with a pin cut if at all.

Not covered by this check: what LM Studio's JavaScript layer does to a request before the engine (it parses
the arguments strings; the calibration of 240 requests counting exactly what LM Studio reported is the
evidence there), and the PC's backend version (the Mac's is 2.61.0). Step 7 below closes both on the real file.

Re-run it with:

```bash
~/.unsloth/studio/unsloth_studio/bin/python3 -I scripts/training_render_check.py "/Volumes/RobertsExternalSSD/repos/CAD Testing/results/training" --per-file 4
```

## 2. The library: Unsloth, with plain transformers + PEFT built in as a fallback

**Unsloth** (`--engine unsloth`, default), because the sequences are long and the vocabulary is large:
the longest kept sequence is 122,835 tokens and Qwen3.5's vocabulary is 248,320, so the full logits of one
sequence are 122,835 × 248,320 × 2 bytes ≈ 61 GB in bf16. Unsloth never builds them (fused, chunked
cross-entropy) and its gradient checkpointing offloads the saved activations to CPU memory
(32 layers × 122,835 × 4,096 × 2 bytes ≈ 32 GB otherwise held on the card). With both, one 80 GB card (and
probably a 48 GB one) holds the longest sequence; it also knows `qwen3_5` (its loader forces bf16 for the
Gated DeltaNet layers and routes them to flash-linear-attention).

**Plain transformers + PEFT** (`--engine hf`) is in the same script: the loss is computed here over the
trained positions only, a chunk at a time with recompute (`chunked_loss`; it matched transformers' own loss
to 1e-6 on a test sequence), so the logits problem is solved without Unsloth; what it lacks is the
activation offload, so it needs the 80 GB card at the longest sequences.

**What would flip it:** if on the card Unsloth's Qwen3.5 path fails (an import or kernel error, NaN loss, or a
first-step loss far from the `hf` engine's on the same sequence), or its memory at 122k is not better than
`hf`'s, use `--engine hf` on the 80 GB card. The choice is close on an 80 GB card and clear on a 48 GB one.

Both engines take the same sequences: the trainer tokenizes and masks itself (`training_render`) and hands
the model `input_ids` and `labels`, so no library's chat-template handling touches the text.

## 3. Proven on this Mac, and what only the card can prove

Proven here, for free:

- the render check above (1,529 requests, the serving engine itself);
- `--prepare-only` on the **whole dataset** (8 min, 8 workers): 12,703 conversations → **12,899 sequences,
  616,009,774 tokens, 60,470,292 trained**, 7,894 weight-0 turns masked (= the card's fault count), longest
  **122,835** (`D1-012239-df405d2e6f9a.vague.faults#5`), median 38,933, p90 74,347, p99 115,496, none past
  131,072 — the exact size of a full epoch;
- the smoke's own selection (`--smoke --prepare-only`): 50 conversations → **75 sequences, 5,913,702 tokens,
  407,922 trained**, longest 122,835 (the five longest conversations come first);
- the training loop end to end on a random Qwen3.5-shaped model (`--tiny 256x4`, CPU, two real 31-34k-token
  sequences): LoRA on all ten projection types (`q/k/v/o_proj`, `in_proj_qkv/in_proj_z/out_proj`,
  `gate/up/down_proj`), gradient checkpointing, the chunked loss, checkpoint and adapter saved; the first loss
  12.43 = ln 248,320, as a random model must give;
- merge → no-think template → `convert_hf_to_gguf.py --no-mtp` (llama.cpp b12340) → `llama-quantize Q4_K_M`
  → **LM Studio's llama-server loads it** and generates, on the tiny model; merged logits agree with the
  adapter model's to 3.1e-6, and the served prompt of a real conversation's first request equals the
  trainer's render.

Only the card can prove: Unsloth's Qwen3.5 kernels on CUDA, the memory at 122,835 tokens, tokens a second,
the real 9B's load/merge/convert (the vision tower and the MTP head are dropped: transformers loads the
9B as the text-only `Qwen3_5ForCausalLM`), and the PC loading the result.

### 3a. The sets recorded after the kit was built (run on this Mac, 2026-11-14)

`d1-train-revise-base`, `d1-train-breaks`, `d1-train-twist-widths`, `train-deeds` and `train-qa`, recorded on
the integrated engine and converted with `--no-faults` into a scratch folder (references only):

- Three tool sets, not one: 74 tools (the D1 sets), 78 (`d1-train-revise-base`: `open_document` and
  `reload_references` among them; the 30 vague conversations converted call `open_document` 60 times and
  `reload_references` 30) and 106 (the two probe sets). `prepare` takes each conversation's own set from
  `tools.json` by its header's hash; nothing in the kit needed to change for them.
- Render check on 30 episodes a set of the three D1 sets (14 conversations, 320 requests; `annotate-base`
  with the 78-tool set and `plan-sheet-breaks` included): thinking off **0 issues**, thinking on mismatches
  every turn, as before. On all ten files (20 conversations, 368 requests, the probe sets included),
  thinking off: 0 issues.
- `--prepare-only` on all ten files: 2,982 conversations → 3,021 sequences, **177,735,760 tokens kept,
  17,703,788 trained**, median 54,607, p99 121,729, 33 conversations split by a `[harness]` note (31 of them in
  `d1-train-breaks-vague`).
- **Six sequences are past 131,072 tokens and are dropped**, all in `d1-train-twist-widths`: seed 16287 at
  both levels (132,373 explicit; 132,289 to 134,652 in its four vague segments) and the last segment of seed
  16062 vague (131,455). The whole dataset before these sets had none (longest 122,835). The longest kept
  sequence is now **130,535** (`D1-016062-….vague#2`), so the smoke's memory figure should be read at that
  length once the dataset is rebuilt.

### 3b. Validation loss and resuming

- `--val-fraction 0.02 --val-max 24 --eval-steps N`: a share of the *training* tasks is held out of training
  by seed (both levels and the faulted copies of a held seed leave together) and the loss on up to 24 of
  their reference conversations is logged before the first step, every N steps and after each epoch
  (`eval_loss` rows in `metrics.jsonl`). No eval set is read: `d1-dev` and every held-out set stay unseen.
  Each evaluation costs a forward pass over the sample (24 conversations ≈ 1.2M tokens), so the smoke runs
  without it; use it for T1.
- `--save-steps N` writes `checkpoint-<step>/` (adapter + `trainer_state.pt`: optimizer, step, place in the
  epoch); `--resume runs/x/checkpoint-<step>` with the same arguments continues it. Checked on the tiny model
  (CPU): a run resumed from its step-2 checkpoint gave step 3's loss and gradient norm to the last digit
  (12.437446088358836, 0.17192812263965607). Not checked: `adamw8bit`'s state through a resume (CUDA only).
- `metrics.jsonl` has `host_peak_gib` beside the card's `peak_gib`/`reserved_gib`: Unsloth's checkpointing
  keeps activations in host memory, so the pod's RAM is part of the measurement.

## 4. The pod

| | choice | why |
|---|---|---|
| card | **A100 SXM 80 GB, secure cloud, $2.19/h** (read from `list-gpu-types`, product POD, 2026-11-13: availability MEDIUM; US-MD-1 MEDIUM) | the cheapest 80 GB card in stock; Ampere has every kernel this needs (flash-attn 2, fla, causal-conv1d). H100 SXM $4.39/h (MEDIUM) is the faster T1 card once the smoke measures both; A40 48 GB $0.59/h is the cheap one if Unsloth's offload holds 122k in 48 GB (try at T1, not in the smoke) |
| image | `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04` (confirm the tag in the console at create time) | devel image: `causal-conv1d` may build from source |
| CUDA floor | `minCudaVersion 12.8` | the hosts listed show 13.2 available, which runs a 12.8 image |
| disk | container 50 GB, volume 150 GB at `/workspace` | base 19 GB in the HF cache + merged 18 GB + bf16 GGUF 18 GB + Q4_K_M 5.6 GB + venv ~15 GB + data 0.8 GB ≈ 77 GB |
| ports | SSH (22) | `runpodctl send/receive` and ssh only |

## 5. The commands, in order

**On the Mac, before any pod (free):**

From a checkout that has these scripts (this branch, once merged), with the conversations from the main
checkout's `results/training/` and the 9B's tokenizer folder:

```bash
cd "/Volumes/RobertsExternalSSD/repos/CAD Testing" && mkdir -p /tmp/t1 && cp -R ~/.roaddraft/tokenizers/Qwen3.5-9B /tmp/t1/tokenizer && tar czf /tmp/t1-smoke.tgz scripts/training_render.py scripts/training_lora.py scripts/training_merge_quantize.py scripts/training_render_check.py scripts/training_serving_stub.py scripts/training_tokens.py results/training/*.jsonl results/training/tools.json results/training/tokens.json -C /tmp/t1 tokenizer
```

The scripts import nothing of `roaddraft`, so the pod needs only these files (the conversations are ~690 MB
before compression).
The dataset will be rebuilt once more after the engine cut; re-run the render check on the rebuilt set
before the smoke.

**On Robert's go: top up the Runpod balance (about $11 now), create the pod** (§4), then on the pod:

```bash
cd /workspace && runpodctl receive CODE          # the code printed by `runpodctl send /tmp/t1-smoke.tgz` on the Mac
tar xzf t1-smoke.tgz
pip install "unsloth" flash-linear-attention causal-conv1d bitsandbytes peft
git clone --depth 1 --branch b12340 https://github.com/ggml-org/llama.cpp   # the build the Mac proved (Unsloth's b12340, commit b8645dd) && cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=ON && cmake --build llama.cpp/build -j --target llama-quantize llama-server
pip install -r llama.cpp/requirements/requirements-convert_hf_to_gguf.txt
export HF_HUB_ENABLE_HF_TRANSFER=0
```

1. **Size check, CPU only (1 min)**: `python scripts/training_lora.py --data results/training --out runs/t1-smoke --smoke --prepare-only`
   must print 75 sequences, 5,913,702 tokens, template sha256 `a4aee8af…` (the script refuses another template).
2. **The smoke (measures memory and speed)**:
   `python scripts/training_lora.py --data results/training --out runs/t1-smoke --smoke --grad-accum 4 --lr 1e-4 2>&1 | tee runs/t1-smoke.log`.
   The five longest sequences go first, so an out-of-memory fails in the first minutes. `metrics.jsonl` has
   per step: `peak_gib` (the step holding the 122,835-token sequence is the memory figure for T1),
   `tokens_per_second`, `loss`. **The first loss must be well under 3, not 12.4**: 12.4 (ln 248,320) is a
   model that loaded random weights. If Unsloth fails, run the same with `--engine hf`.
3. **Merge and quantize (~15-20 min)**:
   `python scripts/training_merge_quantize.py --adapter runs/t1-smoke/adapter --out runs/t1-smoke/gguf --llama-cpp /workspace/llama.cpp --conversation results/training/d1-train-vague.jsonl D1-010000-fd165b673b09.vague`.
   `check.json` must show `verify_merge.argmax_agree` 1.0, the GGUF loaded, a reply, and
   `conversation_prompt_equal: true`.
4. **Render check on the real file**: serve it (`llama.cpp/build/bin/llama-server -m runs/t1-smoke/gguf/model-Q4_K_M.gguf -c 4096 --jinja --port 8099 &`),
   then `python scripts/training_render_check.py results/training --server http://127.0.0.1:8099 --serve-template nothink --thinking off --per-file 1`
   `--tokenizer tokenizer/tokenizer.json --template tokenizer/chat_template.jinja` (the base template: the
   trainer's side). Expect 0 issues: this holds the real file's embedded template to the training text.
5. **Carry the GGUF off the pod**: `runpodctl send runs/t1-smoke/gguf/model-Q4_K_M.gguf` (5.6 GB), and
   `runpodctl receive CODE` on the PC (or the Mac, then copy to the PC). Also send back `runs/t1-smoke/*.json*`
   and the log. Check the sha256 against `check.json`.
6. **Stop and delete the pod** as soon as the receive completes and the hash matches: nothing on it is needed
   after (the adapter is in the received files if `runs/t1-smoke/adapter` is sent too; send it, 100-300 MB).
   Read `list-pod-billing` the next day for the real bill.

**On the PC and the Mac (free):**

7. `lms import model-Q4_K_M.gguf` on the PC; `lms ls` gives its key. The first episode's served prompt is
   the last word on what LM Studio sends: after step 8, convert the episodes and run
   `training_tokens.py --calibrate` on them; every request must count what LM Studio reported (it did for the
   base, 240/240).
8. The 10 `d1-dev` episodes from the Mac over LM Link (vague, single, the board's sampling, one at a time):

```bash
cd "/Volumes/RobertsExternalSSD/repos/CAD Testing" && PYTHONPATH="$PWD/src" .venv/bin/python -m roaddraft.eval run --taskset d1-dev --limit 10 --model KEY_FROM_LMS_LS --provider openai --base-url http://localhost:1234/v1 --lms-context 131072 --context-tokens 131072 --mode single --level vague --samples 1 --concurrency 1 --extra-body '{"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5}' --out results/e3-lms --run-id t1-smoke-d1-dev
```

   About 30-40 min (the 9B's `d1-test` vague clock was 4.8 h per 100). The smoke's checkpoint is 50
   conversations of training: the result shows it serves and calls tools, not that it is better.

### 5a. A checkpoint's eval package on the PC (built 2026-11-15; free, on Robert's word)

Step 8 above is the smoke's ten episodes by hand. A checkpoint that is to be read against the base runs
through the pin's queue instead, so its rows are made the way the base's are:

```bash
cd "/Volumes/RobertsExternalSSD/repos/CAD Testing" && .venv/bin/python benchmarks/lmstudio/add_checkpoint.py qwen3.5-9b-t1 --lms-key KEY_FROM_LMS_LS --check runs/t1/gguf/check.json
```

```bash
cd "/Volumes/RobertsExternalSSD/repos/CAD Testing" && PHASES=ckpt CKPT=qwen3.5-9b-t1 SETS="d1-dev d1-real-dev pilot-dev" zsh benchmarks/lmstudio/queue-base-pin.sh .claude/worktrees/pin-cut pin/training-1 --dry-run
```

- `add_checkpoint.py` writes the checkpoint's entry in the main checkout's `models.json` from the base's
  (the same sampling, context and quantization; `vision` false, since the merge drops the vision tower). It
  loads nothing. The entry is uncommitted until Robert says otherwise.
- `PHASES=ckpt` runs the checkpoint with `--thinking off` under run ids
  `e3-<set>-<label>-single-vague-nothink-<suffix>`, after one check episode that must show no reasoning
  tokens. The harness, task sets and budgets are the pin's; the driver must be byte for byte the pin's
  `lms_campaign.py`. The three validation sets are the checkpoint-selection pass; without `SETS` it goes on
  to `d1-test`, `d1-real` and the hard sets. `hard-pilots` runs the 89 text pilots only.
- Drop `--dry-run` and start it under `nohup` as the header of the script shows. Nothing is published.
- Read each set against the no-think base of the same pin, paired by task:

```bash
cd "/Volumes/RobertsExternalSSD/repos/CAD Testing" && PYTHONPATH="$PWD/src" .venv/bin/python -m roaddraft.eval delta results/e3-lms/e3-d1-dev-qwen3.5-9b-t1-q4km-lms-single-vague-nothink-pin1 results/e3-lms/e3-d1-dev-qwen3.5-9b-q4km-lms-single-vague-nothink-pin1
```

  `eval delta RUN BASE` prints the gap with the board's bootstrap interval, the same by task type, the tasks
  at 100 in each, and anything that keeps the two from being like for like (another tool surface, prompt
  level, thinking setting, verifier). T0 minus base is the same command on the `-t0-` and plain runs.
- Publishing a base `-pin1` row is refused while the `-v3` row of the same model, set and prompt is
  published (`report.repeated_keys`): retire the older row first. That is Robert's call.

## 6. Cost, all estimates

**Throughput (unmeasured, the smoke measures it).** The 9B's text model has 8.95B parameters: 6.92B in the
layers, 1.02B embedding (a lookup), 1.02B `lm_head` (applied only at the 9.8% of positions trained:
60.47M / 616.0M). Forward ≈ 2 × 6.92B + 2 × 1.02B × 0.098 ≈ 14.0 GFLOP a token; LoRA training with full
recompute ≈ forward + recomputed forward + backward to the activations ≈ 3 × 14.0 = 42 GFLOP. The 8
full-attention layers (16 heads × 256 = 4,096) add 2 × 4,096 × L FLOP a token a layer forward for context L;
at a token-weighted L ≈ 55k that is 8 × 450M ≈ 3.6 GFLOP, ≈ 16 GFLOP with backward and recompute (×4.5).
Total ≈ **58-60 GFLOP a token**. A100 bf16 dense 312 TFLOP/s at 20-40% utilisation = 62-125 TFLOP/s →
**1,040-2,080 tokens/s**; H100 SXM 989 TFLOP/s, taken at 2,500-5,000 tokens/s (kernels for the DeltaNet
layers are less mature than for attention).

**The smoke on the A100 SXM 80 GB at $2.19/h:**

| step | minutes |
|---|---:|
| pod up, installs (causal-conv1d may compile) | 20 |
| base download, 19.3 GB | 10 |
| prepare (50 conversations) | 1 |
| train: 5,913,702 tokens at 2,080 → 1,040 tokens/s | 47-95 |
| merge, convert, quantize | 15-20 |
| load check, render check, send 5.6 GB off the pod | 15 |
| **total** | **108-161 (1.8-2.7 h)** |

1.8-2.7 h × $2.19 = **$3.94-5.88**; disk 150 GB × $0.10/GB-month ÷ 730 h ≈ $0.02/h, $0.05. Call it
**$4-6, ceiling $10** if every step takes twice as long (4.5 h). The plan's "about $5" holds.

**T1, projected** (token mean 616,009,774 / 12,703 = 48,494 a conversation):

| T1 size | tokens | A100 SXM $2.19/h at 2,080-1,040 tok/s | H100 SXM $4.39/h at 5,000-2,500 tok/s |
|---|---:|---|---|
| all 12,703 conversations, 1 epoch | 616.0M | 82-165 h, **$180-361** | 34-68 h, **$150-300** |
| plan §4: 1,500 references + their 1,500 faulted copies, 3 epochs | 3,000 × 48,494 × 3 = 436.5M | 58-117 h, **$128-256** | 24-49 h, **$106-213** |
| the same 3,000, 1 epoch | 145.5M | 19-39 h, **$43-85** | 8-16 h, **$36-71** |

Arithmetic, one row: 145.5M ÷ 2,080 tok/s = 69,952 s = 19.4 h × $2.19 = $42.5; ÷ 1,040 = 38.9 h → $85.1.
Each checkpoint's merge and quantize adds about 20 min of the card ($0.73 on the A100, $1.46 on the H100).

Against the **$150 line through a first trained row** (plan §6 decision 2): the whole dataset for one epoch
does not fit at these rates (the plan's "one epoch over all 300.8M tokens fits" predates the faulted copies
and the exact count); 3,000 conversations for one epoch fits on either card with room for the smoke and the
conversions; three epochs fits only at the fast end. 59% of every token is the fixed ~28k-token prompt
(12,899 sequences × ~28k ≈ 361M of 616M), so the cost is set by how many conversations train, not how long
their answers are. The smoke's tokens a second replace every rate above.

## 7. What should go into the training plan (not edited here)

- §4 *T1 smoke*: built (this file); its render check run on 1,529 requests, both findings above.
- §5 "Open for T1", *Thinking*: decided by the check, not by taste: train with the empty think block as
  context and serve with thinking off (the no-think template in the GGUF); thinking on mismatches every turn.
- §6 decision 2: the T1 size has to be chosen against the measured rate; at the estimates, about 3,000
  conversations for one epoch is what $150 buys with margin.
- §6, a new decision: base and T0 with thinking on (as the board) or off (like-for-like with the trained rows).
- §7 risk *training text differs from what the server sends*: checked, guard in place (`plan_segments`, the
  no-think template, `training_render_check.py` re-run on each rebuilt dataset and on each served GGUF).
- Open: whether the lmstudio-community base file was quantized with an importance matrix (read its
  `quantize.imatrix.*` keys on the PC with `gguf-dump`); if it was, the checkpoints need one too
  (`--imatrix`), or the base should be re-quantized through the same script for like-for-like.

## 8. The smoke, run 2026-11-18 (Robert: "run the smoke")

Steps 1-6 ran on a Runpod A100 SXM 80 GB, secure cloud, $2.19/h: pod `yo0tozvnf32py3`, up 23:49:49 to
00:31:32 UTC (41.7 min, about **$1.52**), deleted after the files came back. Two pods before it
(`2ll346ojvk1v97`, `c93eqoqe606udi`) lived under a minute each: their 150 GB persistent volume at `/workspace`
came up empty and full (xfs quota, `No space left on device`), so the third ran on a 160 GB container disk with
no volume. The data was the rebuilt dataset (18,693 conversations; render check on the Mac first: thinking
off 0 issues on 90 conversations, 1,989 turns, the striping and profile sets included).

**What changed against §5 on the pod** (the image `runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04`):
- `pip install unsloth … causal-conv1d` fails: the build pulls the newest torch (CUDA 13.2) against the image's
  nvcc 12.8. Install `torch==2.9.1 torchvision==0.24.1` from the cu128 index first, then the rest with
  `-c` a constraint `torch==2.9.1`, then `causal-conv1d` with `--no-build-isolation`. Versions: unsloth
  2026.11.6, transformers 5.17.0, peft 0.21.3, flash-linear-attention 0.6.0, bitsandbytes 0.50.2.
- Do not install llama.cpp's `requirements-convert_hf_to_gguf.txt`: it pins a CPU torch 2.11. The converter
  runs under the trainer's python and needs only `sentencepiece` and `protobuf<5` (it loads `gguf` from the
  checkout).
- The image has no `cmake` (`apt-get install cmake`). b12340's `llama-server` fails on its web UI bundle (the
  downloaded `latest` lacks the file names the check wants): `scripts/ui-assets.cmake` line 137
  `FATAL_ERROR` to `WARNING`. `llama-quantize` builds as is.
- Pass `--workers 16`: the default (cores minus one, 191 here) spawns that many tokenizer workers and
  stalls the preparation.
- Before the merge, `pip uninstall torchaudio torchao`: both are built for another torch and break `import
  peft` (peft 0.21 refuses torchao below 0.16, and 0.16 wants a newer torch).

**Results:**
- Size check on the pod = the Mac: 50 conversations, 51 sequences kept (12 past 131,072 dropped), 3,208,963
  tokens, 321,779 trained, longest 130,837; template `a4aee8af…`.
- Training: 13 steps, 3,208,963 tokens in 1,362.8 s, **2,355 tokens/s overall; 2,800-3,350 tokens/s after the
  first step** (1,186 on step 1, with the compile). First loss **0.275** (the base loaded; 12.4 would be
  random weights), losses 0.25-0.51. Peak **58.8 GiB** on the card at the 130,837-token sequence (reserved
  60.0), host peak 35.4 GiB. 80.2M trainable parameters on 200 modules; every `lora_B` non-zero.
- Merge 61.6 s, convert 71.4 s, quantize 56.2 s: `verify_merge` argmax agree 1.0, the GGUF loads and
  replies, `conversation_prompt_equal` true; `model-Q4_K_M.gguf` 5,629,108,640 bytes, sha256
  `87000bf829ac471df2806851715790c583a667fb390b15f2a1a371351aae93d7` (matched after the transfer).
- Render check against the real GGUF on the pod (step 4): thinking off, 40 conversations, 530 turns, **0
  issues**.
- On the Mac (gitignored): `runs/t1-smoke/t1-smoke/gguf/model-Q4_K_M.gguf`, `runs/t1-smoke/back/` (adapter,
  metrics, run.json, check.json, logs).

**T1 at the measured rate** (A100 SXM $2.19/h, 2,400-3,000 tokens/s; about 50.1k tokens a conversation):

| T1 size | tokens | hours | cost |
|---|---:|---:|---:|
| 3,000 conversations, 1 epoch | ~150M | 14-17 | **$30-38** |
| 3,000 conversations, 3 epochs | ~450M | 42-52 | **$91-114** |
| all 18,693, 1 epoch (+3.6% for the note splits) | ~970M | 90-112 | **$197-246** |

**Steps 7-8, on the PC (2026-11-18 evening).** Robert copied the GGUF to
`C:\Users\Denis\.lmstudio\hub\models\roadraft\qwen3.5-9b-t1-smoke`; LM Studio lists it as `qwen3.5-9b-t1-smoke`
(9.0B, qwen35, 5.63 GB, RobertsPC) and loads it at context 131,072. Run `t1-smoke-d1-dev` (`results/e3-lms`,
not published): `d1-dev --limit 10`, vague, single, the board's sampling, `--thinking off`.

| task | score | end | steps |
|---|---:|---|---:|
| D1-000001 | 73.8 | submit | 24 |
| D1-000002 | 69.0 | submit | 24 |
| D1-000003 | 75.0 | submit | 2 |
| D1-000004 | 80.0 | submit | 9 |
| D1-000005 | 0.0 | submit | 0 |
| D1-000006 | 0.0 | submit | 18 |
| D1-000007 | 76.9 | submit | 20 |
| D1-000008 | 100.0 | submit | 3 |
| D1-000009 | 100.0 | submit | 17 |
| D1-000010 | 0.0 | budget | 0 |

**Effective 57.5** (10 episodes; 2 at 100, 9 submitted, 0% hard-fail). The checkpoint serves and drafts: tool
calls parse, every turn carries its shown work as text, reasoning tokens 0. It is 50 conversations of training,
and there is no base run on these ten with thinking off to read it against, so the number says nothing yet about
whether training helps. The run was started without `caffeinate` and the Mac slept for 5.7 h of it (one turn
per hourly dark wake, all in episode 1); a hand-started eval belongs under `caffeinate -i`.

**Step 7's count against the server**: the two episodes at 100 converted (`convert_episode`, audit off,
into a scratch folder: they are never training data), 20 requests: every one counts **2 tokens under** what
LM Studio reported (27,947 against 27,949 on the first). The 2 are the generation prompt: the server sent
thinking off (`<think>\n\n</think>\n\n`, 4 tokens) where `training_tokens.py` renders the thinking-on
`<think>\n` (2). The conversation itself counts exact, as it did for the base (240/240).
