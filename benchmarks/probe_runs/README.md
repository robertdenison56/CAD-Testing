# Probe runs — real models through the capability probes

Evidence for the runs of `roaddraft.probes` by real models, one folder per run.
Every score here was taken from the document the run left on disk, never from
what the model said it did; the traces are what make that checkable. These are
capability probes, not the scored benchmark of `RoadDraft_Eval_Plan.md`.

| Run | Models | Probes | Passed | Writeup |
|---|---|---|---|---|
| 2026-09-19 | Fable 5.1, Haiku 4.5 | the 9 find-probes (T2) | 9/9, 9/9 | [RESULTS.md](2026-09-19/RESULTS.md) |
| 2026-09-20-T1 | Fable 5.1, Haiku 4.5 | the 8 drafting-probes (T1) | 8/8, 4/8 | [RESULTS.md](2026-09-20-T1/RESULTS.md) |
| 2026-09-22 | Fable 5.1, Haiku 4.5 | all 17, after the engine fixes | 17/17, 14/17 | [RESULTS.md](2026-09-22/RESULTS.md) |
| 2026-09-24-ollama | gpt-oss:120b-cloud | all 17, three passes | 12, 12, 15 of 17 | [RESULTS.md](2026-09-24-ollama/RESULTS.md) |
| 2026-09-29-lmstudio | Qwen3.5-9B, local through LM Studio | all 17 | 11/17 (T2 8/9, T1 3/8) | [RESULTS.md](2026-09-29-lmstudio/RESULTS.md) |
| 2026-10-04-lmstudio-tier2 | Qwen3.5-9B, local through LM Studio | the 6 Tier-2 probes | 0/6, each on the gap it measures | [RESULTS.md](2026-10-04-lmstudio-tier2/RESULTS.md) |
| 2026-10-06-haiku-t2-t3a | Haiku 4.5 | the 6 Tier-2 probes and Tier-3 batch A (line-data, curve-points, curve-data, stationing) | 6/10: Tier 2 5/6, batch A 1/4 | [RESULTS.md](2026-10-06-haiku-t2-t3a/RESULTS.md) |
| 2026-10-07-runner-smoke | Qwen3.5-9B, Llama 3.1 8B through `roaddraft.runners` | edge-c102 only: the native runner's first live runs, not a benchmark | 1/1, 0/1 (LM Studio could not parse Llama's tool call) | [RESULTS.md](2026-10-07-runner-smoke/RESULTS.md) |
| 2026-10-07-lmstudio-t3bc | Qwen3.5-9B, GLM-4.6V-Flash, Gemma-4-E4B, Llama-3.1-8B, local through LM Studio | Tier-3 batches B and C (equation-data, width-dims, row-data, qa-alignment-data, l2-match-lines, l2-alignment-data) | 0/6 each; Llama never completed a turn | [RESULTS.md](2026-10-07-lmstudio-t3bc/RESULTS.md) |
| 2026-10-08-runner-guards | Qwen3.5-9B through `roaddraft.runners` | edge-c102 only: the LM Studio guards ported into the native runner, not a benchmark | 1/1 (a first attempt's engine died mid-stream; its document still passes) | [RESULTS.md](2026-10-08-runner-guards/RESULTS.md) |
| 2026-10-08-claude-code-smoke | Haiku 4.5 through `roaddraft.runners --backend claude-code` | edge-c102 only: the claude-code backend's first live run, on a subscription, not a benchmark | 1/1 | [RESULTS.md](2026-10-08-claude-code-smoke/RESULTS.md) |
| 2026-10-08-k3 | Haiku 4.5 through `roaddraft.runners --backend claude-code`, k = 3 | all 33 probes, three times | 21, 20, 17 of 33; 15 probes pass every time, 9 fail every time, 9 split | [RESULTS.md](2026-10-08-k3/RESULTS.md) |
| 2026-10-12-k3 | Haiku 4.5, Sonnet 5.5 through `roaddraft.runners --backend claude-code`, k = 3, on the one-convention-set probe set (Gemma 4 E4B and Fable 5.1 to follow) | all 33 probes, three times | Haiku 23, 27, 24; Sonnet 32, 32, 31 of 33 | [RESULTS.md](2026-10-12-k3/RESULTS.md) |

Each folder keeps the rig exactly as it ran, so a writeup and the engine it
measured stay together. The engine version is named in each RESULTS.md.

## Layout

    <run>/RESULTS.md                 the writeup: table, findings, caveats
    <run>/setup_runs.py              one fresh project per probe (fixture.start_document), its server.json and rd shim
    <run>/score_runs.py              scores every left-behind document and summarises its trace
    <run>/bridge.py                  Claude runs: a shell bridge holding ONE persistent roaddraft-mcp over stdio
    <run>/ollama_runner.py           Ollama runs: a minimal native MCP client, the tools passed as function tools
    <run>/lmstudio_runner.py         LM Studio runs: the same client on the OpenAI-compatible API; --budget MIN per probe
    <run>/make_deliverables.py       prints every probe's left-behind document and its scripted reference to PDF,
                                     plus OVERVIEW.pdf / OVERVIEW.png (green = pass, red = fail)
    <run>/runs/<label>/<probe>/
        trace.jsonl                  every tool call as the server saw it (--trace): arguments, outcome, faults
        project/                     the documents left behind, journal beside them: what was scored
        transcript.json, report.txt  Ollama and LM Studio runs: every message including the model's thinking; its final report
        prompt.txt, report.txt       Claude runs from 2026-10-06 on: the exact prompt the runner agent was handed; its final report
        renders/                     what the model looked at        (not tracked: PNGs, regenerable from project/)
        deliverables/                the plots: <probe>.pdf, <probe>.reference.pdf, OVERVIEW.pdf, OVERVIEW.png;
                                     <probe>.reference/ is that reference as a finished RoadDraft project
                                     (the start with the handed document completed, and its journal)
        server.json, rd, *.log       launch shim and logs            (not tracked: absolute paths to one machine)
    <run>/runs/<label>/_attemptN/    a launch the infrastructure ended, kept for the record; the scorers ignore it

`2026-09-19/runs/haiku/_stray_saves/` holds the three files Haiku saved under
names of its own, moved out of the repository root where they landed.

The `<probe>.reference/` projects were added to the two runs with deliverables
on 2026-10-05, written by the engine each run was made with (`06c4246` and
`465640f`). Each was checked three ways: it passes its probe's check read back
from disk, its journal replays to it, and printed again it matches
`<probe>.reference.pdf` pixel for pixel. `make_deliverables.py` now writes them
with the PDFs. The current engine's reference for every probe is in
`benchmarks/probe_references/`.

## Re-scoring

From a run folder, with the venv active:

    python score_runs.py <label>          fable, haiku, t1-fable, t1-haiku, gpt-oss-120b, gpt-oss-120b-r2, qwen3.5-9b ...

`score_runs.py` rebuilds the pristine start document with `fixture.start_document`
and diffs the left-behind document against it, so a re-score runs against the
*current* probe definitions: a probe whose check has changed may score an old
run differently. That is why the documents are kept and not just the numbers.

## Running a new one

From Oct 7 2026 the runner is in the package, one client for every vendor, and
leaves this same layout plus `run.json` (stop reason, turns, seconds, tokens,
cost) and `scores.json`:

    python -m roaddraft.runners run --backend anthropic|claude-code|openai --model MODEL \
        --out benchmarks/probe_runs/<date>-<name> --label <label> [--tag tier2] [PROBE ...] [--repeat 3]
    python -m roaddraft.runners score benchmarks/probe_runs/<date>-<name>/runs/<label>
    python -m roaddraft.runners leaderboard     # regenerate benchmarks/leaderboard/ from every run folder here

The Track P leaderboard (`benchmarks/leaderboard/TRACK_P.md`, with a model
card per row) is generated from these folders and never edited by hand. A
model's k = 3 attempts belong in one folder as `runs/<model>-r1..r3`, the
labels `--repeat 3` writes; a label without `-rN` is a single run and stays
off the board.

The rigs below are how the earlier runs were made and stay with them. To
repeat one of those as it was, copy its rig into a new dated folder rather
than adding labels to an old one.

    python setup_runs.py <label> [tag]    runs/<label>/<probe>/ with a fresh project and server.json
    # drive it: a subagent through each probe's `rd`, `python ollama_runner.py <label> <model>`,
    #           or `python lmstudio_runner.py [--budget MIN] <label> <model>` (see that run's RESULTS.md for the LM Studio setup)
    python score_runs.py <label>
    python make_deliverables.py <label>   the PDFs and the pass/fail overview, beside the scores
