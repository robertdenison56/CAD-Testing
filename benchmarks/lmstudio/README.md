# The local rig: leaderboard models on RobertsPC through LM Studio

RobertsPC got a second RTX 4060 on 2026-10-20: two 8 GB cards, 16 GB that llama.cpp splits the layers across.
LM Studio serves the PC's models to the Mac over LM Link (`localhost:1234`), so the runners need nothing new:
`--backend openai` (probes) and `--provider openai` (E3) with the `--lms-context N` reload guard at the model's own
window (`context` in `models.json`, 131,072 at most; see *The window* below).
`models.json` holds the specs and `lms_campaign.py` the commands, built like the Runpod rig next door.

**Status, 2026-10-23 evening: first run going.** A single d1-dev test episode on the 9B ran clean through the
harness (20-min wall clock, score 0), then Robert started `e3 qwen3.5-9b` (d1-variance x 5, run id
`e3-d1-variance-qwen3.5-9b-q4km-lms-single`). Found on the way: `lms load` right behind `lms unload --all`
can hang at "97%" for good; `load_alone` now waits for the unload, gives the CLI a deadline and trusts the
server's `loaded` state.

## Which leaderboard models fit (2026-10-20)

Measured: one ~29k-token prompt at context 65536 (`lms_campaign.py check`). Estimated: weights plus context
memory from each model's config, scaled from the measured rates.

| board row | here | window (`fit`, Oct 28 2026) | speed | k = 3 |
|---|---|---|---|---|
| Qwen3.5-9B (bf16, vLLM), 44.4% | Q4_K_M, on the PC | 131,072, fully on the cards | 3,157 tok/s prefill, 35.8 tok/s gen | ~8-10 h |
| Qwen3.5-4B (bf16, vLLM), 33.3% | BF16 GGUF, to download | to fit after the download | not measured | ~10 h |
| Gemma 4 12B (bf16, vLLM), 41.4% | Q8_0, on the PC (Robert, Oct 27, in place of the Q6_K pick) | 98,304 (`fit`, Oct 28; 131k and 114k refused), partly on the CPU | Q8_0 measured 1,140 / 12.8 tok/s at 65k | ~6-8 h |
| gpt-oss-20b (mxfp4, vLLM), 13.1% | left out (Robert) | ~14 GB, tight | | ~2-3 h |
| Gemma 4 26B-A4B, Qwen3.6-35B-A3B, GLM-4.7-Flash | stay on Runpod | only with experts in the PC's RAM | 3-5x slower than Runpod | 8-17 h |
| Qwen3.8-27B, Gemma 4 31B, gpt-oss-120b, Qwen3.5-122B | stay on Runpod | no | | |

The file choices are Robert's (2026-10-20): the 9B stays on Q4_K_M, the file of every earlier local run; the 4B
goes to BF16, the board row's precision; Gemma 4 12B to Q6_K, changed on 2026-10-27 to the Q8_0 already on the PC
(Robert's call, no download). These are **new board rows**, not replacements of
the bf16 vLLM ones: GGUF weights on llama.cpp, with LM Studio's own chat templates and tool-call parsing.

## Getting ready

1. On the PC (downloads land on the machine that runs `lms get`, so they cannot be started from the Mac):
   `lms get https://huggingface.co/unsloth/Qwen3.5-4B-GGUF --select` (pick BF16). Over LM Link `lms load` takes only
   the bare key and loads the variant selected on the PC. Gemma 4 12B needs no download: it runs as the Q8_0 that is
   there (Robert, 2026-10-27).
2. `python benchmarks/lmstudio/lms_campaign.py status` names the 4B's model key; put it in `models.json`
   (`lms_key`, and `variant` from `lms ls --json`).
3. `lms_campaign.py fit NAME` for every new file: the highest window it loads at, 131,072 down to 65,536, written to
   `models.json` as `context`; a model that does not load at 65,536 is dropped from the list (Robert, Oct 28). Then
   `lms_campaign.py check NAME` loads it alone at that window (all layers on the cards if they fit, LM Studio's split
   otherwise), times one prompt and records it under `measured`.
4. `lms_campaign.py pins`: the worktree `.claude/worktrees/runpod-k3` at `2658fa0`, clean help text.

## Running (on Robert's go)

    python benchmarks/lmstudio/lms_campaign.py smoke qwen3.5-9b          # edge-c102 as -r1
    python benchmarks/lmstudio/lms_campaign.py k3 qwen3.5-9b             # r1..r3 in one detached process
    python benchmarks/lmstudio/lms_campaign.py e3 qwen3.5-9b             # d1-variance x 5, single, explicit
    python benchmarks/lmstudio/lms_campaign.py score qwen3.5-9b
    python benchmarks/lmstudio/lms_campaign.py watch RUN_ID               # a stalled episode: stop the run for the queue's retry
    python benchmarks/lmstudio/lms_campaign.py clear-errors RUN_ID --apply [--stalled] [--turn-time]   # episodes aside, to rerun

`--print` shows any of them without running it. Probe runs go to `benchmarks/probe_runs/2026-10-20-lms-k3`,
E3 runs to `results/e3-lms/` (gitignored). Every `e3` run carries `--context-tokens N` beside the reload
guard's `--lms-context N`, N the model's `context` (since 2026-10-27): the harness ends an episode whose prompt reaches the window as a
`context` budget trip, as vLLM refuses one on the hosted rows, where LM Studio alone would cut the middle of the
prompt and answer. On `hard-pilots`, `--pilots text|images|all` picks the 24 text pilots, the nine that come with
a page, or every one (the default); the page goes to the model as a data URL in the harness's own request shape,
so the nine need a model LM Studio lists with vision (`vision` in `models.json`, from `lms ls --json`), and
`lms_campaign.py vision NAME` sends one lettered image that way first and records whether the model read it and
what the image cost in prompt tokens (`vision_check`). It loads the model, so it waits for an idle server. Before each launch the script checks the link, starts the
server, refuses while another local run is going, unloads everything, loads the model at its `context` / parallel 1,
and refuses unless the PC's selected variant and the loaded quantization are the spec's, and the model is not dropped.

## The window (2026-10-28, Robert)

"Have the models run at the highest context possible that will fit on my local machine; if a model is unable to run
with enough context for these tasks remove it from the list of local tested models." So each model has its own
window: `lms_campaign.py fit NAME` walks the ladder 131,072, 114,688, 98,304, 81,920, 65,536 from the ceiling
(`CONTEXT`, the Oct 26 decision: the largest the two cards hold for the 9B) down to the floor (`FLOOR_CONTEXT`,
65,536: the hosted vLLM rows' window, and the reading of "enough context for these tasks": 17 of the 9B's 100
d1-test episodes peaked past it, the largest at 104,370 tokens, so a row at the floor loses about that share to
context trips), records the first rung LM Studio loads the model at as `context` in `models.json` (with the rungs
tried under `fit`), and below the floor marks the model `dropped` with the reason; `e3`, `check`, `smoke`, `k3`
and `vision` refuse a dropped model, `fit` alone takes it again. Every load, the runner guard's reload and the
harness's `--context-tokens` use the model's `context`, and the window is on the row's card. Oct 28: at 131,072
the cards load the 9B Q4, GLM-4.6V-Flash Q4 and Gemma 4 E4B Q4 and refuse Gemma 4 12B Q8_0, Devstral Small 2
Q3_K_L, Ministral 3 14B Q6_K and Llama 3.1 8B Q4 ("failed to allocate buffer for kv cache"); the window, not the
weights, is the limit (131k of KV cache for an 8B dense model is about 16 GB on its own). Their fits ran from
`results/e3-lms/queue-2026-10-28.sh` at 11:57 to 12:08: Gemma 4 12B Q8_0 loads at 98,304, Llama 3.1 8B at 65,536
(the floor), and Devstral Small 2 Q3_K_L and Ministral 3 14B Q6_K at no rung, so both are dropped from the local list
(`dropped` in `models.json`, with the rungs tried); the rest of the queue is Llama's smoke and Gemma's d1-test night.

## Stalls (2026-10-28)

The dead-engine guard (Oct 26) catches an engine that is gone: "No models loaded", "fetch failed", "terminated" in
the stream, a one-token probe before every episode that gets no answer. Gemma 4 12B Q8_0 at 98,304 on d1-test
showed a stall it cannot see: from 12:53 (the 18th turn of D1-001014, after 17 turns of seven seconds each) the
engine answered every probe and then streamed empty chunks on the real prompt for the whole 30-minute turn limit,
nine episodes in a row over five hours (D1-001015 to 001023), each scored 0 with 0 steps, LM Studio listing the
model GENERATING throughout. Stopping the client and reloading cleared it (the model went IDLE the moment the client
died). The rule, in `lms_campaign.py`: an episode whose end record says `turn_time` with 0 steps is a *stall*, the
engine's outcome rather than the model's, once. `watch RUN_ID` (one per run, detached, log `results/e3-lms/watch-<run
id>.log`) polls the run's episode files every minute and, on a stall, stops the run's eval process so a queue
script's `run_e3` retry loop reloads the model and resumes the run, moves the episode into `<run>/errored-<date>/`
so the resume runs it again, and records it in `<run>/watch.json`; a stall of the same episode after that stays as
the model's result. `clear-errors RUN_ID --apply --stalled` does the move by hand. The harness has the guard
too since the evening of Oct 28 (`roaddraft/runners/openai_compat.py`, committed 31774181 at 22:19 on Robert's go): a stream whose chunks carry
nothing (no text, no reasoning under any key, no call fragment, no finish) for `STALL_LIMIT` 300 s, at least
`STALL_CHUNKS` 50 of them, is a stall; with the LM Studio guard the model is reloaded and the request sent again
once, and a second stall, or one on an endpoint without the guard, ends the turn as `turn_limit` with `stalled`
in the reply, which the eval harness records as a `turn_time` budget trip that names the stall. Tokens arrive in
every chunk of a healthy stream, so no model is cut by it; a long prompt's processing sends no chunks and is not
touched. A run gets it only from a worktree at a commit that holds it, so tonight's nights (pinned to 291ae711)
rely on `watch`. The same scan found the shape in the rows already published: four of the 9B's d1-test episodes
(its "over-long turns": D1-001032, 001034, 001069, 001071, after 57, 6, 13 and 1 steps) and one of its d1-real
episodes (D1-000000-8e8d02fad1d1, after 6) ended on a silent 30-minute turn. Robert, 21:20 Oct 28: rerun them.
`results/e3-lms/queue-2026-10-28c.sh` (queue 4, started 21:32, restarted 22:21 re-pointed, log beside it) waits for queue 3's "queue done" and
an idle server, then for each run sets the episodes aside with `clear-errors RUN --apply --turn-time` (every
`turn_time` trip, after steps too; the d1-real run's one errored episode of Oct 26, D1-000000-f1825a08b736, goes
with them, so that row fills to 99), starts a `watch`, and resumes the run with `e3 ... --worktree` from the
worktree at the run's own pin: `lms-d1-test` at 291ae711 for d1-test, `lms-9b-resume` at d98e7025 for d1-real,
whose harness predates `--context-tokens` (`e3` leaves the flag out for a worktree without it, and the run keeps
the budgets it had). Neither pin held the harness stall guard, so on Robert's "Yes, commit" (22:19) the guard went in
as its own commit (31774181) and was cherry-picked onto each pin in its rerun worktree: `lms-9b-rerun-test` at 97469b45
(291ae711 + the guard; the running nights keep `lms-d1-test` untouched) and `lms-9b-resume` at c1719489 (d98e7025 + the
guard; the cherry-pick kept the stall test alone of the four new tests, the rest need the context budget that pin lacks;
its 77 tests pass), both tagged `pin/<run id>-rerun` so the detached pins stay reachable; queue 4 was restarted at 22:21
pointing at them. A five-minute stall now reloads the model and asks again once, and the `watch` stays beside each run
for the zero-step kind. The reports are written (d1-real's with `--reverify`,
as its published row was), not published: the two rows change after a look at the numbers, with
`report --publish` and `scripts/make_leaderboard.py`.

How the rig differs from the Runpod rows, for the writeup:
- one model and one episode at a time (Runpod ran r1-r3 as three processes on one vLLM worker);
- no 570 s proxy cut-off: a turn ends at the runner's own 1,800 s limit, and the 30-minute budget is wall
  clock on the PC's speed;
- the PC must not sleep during a run (Windows power settings); the Mac is held awake by `caffeinate -i`;
- an LM Link drop shows as connection refused: the runner's guard waits up to 15 min and reloads at the run's context.

Before the board: add `NAMES` entries in `src/roaddraft/runners/leaderboard.py` for the three model ids
(`qwen/qwen3.5-9b` reads "Qwen3.5-9B" today), naming the file and LM Studio, e.g. "Qwen3.5-9B (Q4_K_M, LM
Studio)". The rows come out as class "local small", runner "openai (LM Studio)"; their model ids differ from the
vLLM rows', so neither supersedes the other.

Afterwards, Robert's everyday load: `lms load qwen/qwen3.5-9b -c 107776 --parallel 4 -y`.
