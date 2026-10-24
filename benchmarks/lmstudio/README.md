# The local rig: leaderboard models on RobertsPC through LM Studio

RobertsPC got a second RTX 4060 on 2026-10-20: two 8 GB cards, 16 GB that llama.cpp splits the layers across.
LM Studio serves the PC's models to the Mac over LM Link (`localhost:1234`), so the runners need nothing new:
`--backend openai` (probes) and `--provider openai` (E3) with the `--lms-context 65536` reload guard.
`models.json` holds the specs and `lms_campaign.py` the commands, built like the Runpod rig next door.

**Status, 2026-10-23 evening: first run going.** A single d1-dev test episode on the 9B ran clean through the
harness (20-min wall clock, score 0), then Robert started `e3 qwen3.5-9b` (d1-variance x 5, run id
`e3-d1-variance-qwen3.5-9b-q4km-lms-single`). Found on the way: `lms load` right behind `lms unload --all`
can hang at "97%" for good; `load_alone` now waits for the unload, gives the CLI a deadline and trusts the
server's `loaded` state.

## Which leaderboard models fit (2026-10-20)

Measured: one ~29k-token prompt at context 65536 (`lms_campaign.py check`). Estimated: weights plus context
memory from each model's config, scaled from the measured rates.

| board row | here | fits at 65k | speed | k = 3 |
|---|---|---|---|---|
| Qwen3.5-9B (bf16, vLLM), 44.4% | Q4_K_M, on the PC | fully on the cards, measured | 3,157 tok/s prefill, 35.8 tok/s gen | ~8-10 h |
| Qwen3.5-4B (bf16, vLLM), 33.3% | BF16 GGUF, to download | ~13 GB, estimated | not measured | ~10 h |
| Gemma 4 12B (bf16, vLLM), 41.4% | Q6_K, to download | partly on the CPU, expected | Q8_0 measured 1,140 / 12.8 tok/s | ~6-8 h |
| gpt-oss-20b (mxfp4, vLLM), 13.1% | left out (Robert) | ~14 GB, tight | | ~2-3 h |
| Gemma 4 26B-A4B, Qwen3.6-35B-A3B, GLM-4.7-Flash | stay on Runpod | only with experts in the PC's RAM | 3-5x slower than Runpod | 8-17 h |
| Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b, Qwen3.5-122B | stay on Runpod | no | | |

The file choices are Robert's (2026-10-20): the 9B stays on Q4_K_M, the file of every earlier local run; the 4B
goes to BF16, the board row's precision; Gemma 4 12B to Q6_K. These are **new board rows**, not replacements of
the bf16 vLLM ones: GGUF weights on llama.cpp, with LM Studio's own chat templates and tool-call parsing.

## Getting ready

1. On the PC (downloads land on the machine that runs `lms get`, so they cannot be started from the Mac):
   `lms get google/gemma-4-12b@q6_k` and `lms get https://huggingface.co/unsloth/Qwen3.5-4B-GGUF --select`
   (pick BF16). Then select the Q6_K variant for `google/gemma-4-12b` in LM Studio: over LM Link `lms load`
   takes only the bare key and loads the selected variant, and the Q8_0 is there too.
2. `python benchmarks/lmstudio/lms_campaign.py status` names the 4B's model key; put it in `models.json`
   (`lms_key`, and `variant` from `lms ls --json`).
3. `lms_campaign.py check NAME` for the 4B and Gemma: loads the model alone at 65k (all layers on the cards
   if they fit, LM Studio's split otherwise), times one prompt and records it under `measured`.
4. `lms_campaign.py pins`: the worktree `.claude/worktrees/runpod-k3` at `2658fa0`, clean help text.

## Running (on Robert's go)

    python benchmarks/lmstudio/lms_campaign.py smoke qwen3.5-9b          # edge-c102 as -r1
    python benchmarks/lmstudio/lms_campaign.py k3 qwen3.5-9b             # r1..r3 in one detached process
    python benchmarks/lmstudio/lms_campaign.py e3 qwen3.5-9b             # d1-variance x 5, single, explicit
    python benchmarks/lmstudio/lms_campaign.py score qwen3.5-9b

`--print` shows any of them without running it. Probe runs go to `benchmarks/probe_runs/2026-10-20-lms-k3`,
E3 runs to `results/e3-lms/` (gitignored). Before each launch the script checks the link, starts the
server, refuses while another local run is going, unloads everything, loads the model at 65536 / parallel 1,
and refuses unless the PC's selected variant and the loaded quantization are the spec's.

How the rig differs from the Runpod rows, for the writeup:
- one model and one episode at a time (Runpod ran r1-r3 as three processes on one vLLM worker);
- no 570 s proxy cut-off: a turn ends at the runner's own 1,800 s limit, and the 30-minute budget is wall
  clock on the PC's speed;
- the PC must not sleep during a run (Windows power settings); the Mac is held awake by `caffeinate -i`;
- an LM Link drop shows as connection refused: the runner's guard waits up to 15 min and reloads at 65536.

Before the board: add `NAMES` entries in `src/roaddraft/runners/leaderboard.py` for the three model ids
(`qwen/qwen3.5-9b` reads "Qwen3.5-9B" today), naming the file and LM Studio, e.g. "Qwen3.5-9B (Q4_K_M, LM
Studio)". The rows come out as class "local small", runner "openai (LM Studio)"; their model ids differ from the
vLLM rows', so neither supersedes the other.

Afterwards, Robert's everyday load: `lms load qwen/qwen3.5-9b -c 107776 --parallel 4 -y`.
