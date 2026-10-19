# Probe runs — real models through the capability probes

Evidence for the runs of `roaddraft.probes` by real models, one folder per run.
Every score here was taken from the document the run left on disk, never from
what the model said it did; the traces are what make that checkable. These are
capability probes, not the scored benchmark of `RoadDraft_Eval_Plan.md`.

| Run | Models | Probes | Passed | Writeup |
|---|---|---|---|---|
| 2026-10-17-k3 | nine open-weight models from 4B to 31B, bf16 on Runpod vLLM, k = 3 on the scrubbed help text | all 33 probes, three times | Gemma 4 31B 74.7% to gpt-oss-20b 7.1% | [RESULTS.md](2026-10-17-k3/RESULTS.md) |
| 2026-10-18-gpt-oss-k3 | gpt-oss-20b (mxfp4) on Runpod vLLM again, with its thinking sent back (`--send-reasoning`), k = 3 | all 33 probes, three times | 6, 5, 2 of 33 = 13.1%, still last: no harmony parser errors (17 before) and 13 of 22 tool-using episodes passed, but 77 of 99 made no tool call | [RESULTS.md](2026-10-18-gpt-oss-k3/RESULTS.md) |

Every run from 2026-09-19 to 2026-10-14 was removed on 2026-10-18: they ran on
the tool help and server instructions from before `fe26ce2`, which held probe
answers. Those fourteen folders (Fable, Haiku, Sonnet, GPT-6-Astra and -Luna,
Gemma 4 E4B, the LM Studio and Ollama runs, the smoke runs) are in the history at
`727fb7f`; the board ranks only runs on the current help text.

Each folder keeps the rig exactly as it ran, so a writeup and the engine it
measured stay together. The engine version is named in each RESULTS.md.

## Layout

    <run>/RESULTS.md                 the writeup: table, findings, caveats
    <run>/runs/<label>/<probe>/
        run.json                     stop reason, turns, seconds, tokens, cost, and the pins (engine commit, tools, instructions)
        trace.jsonl                  every tool call as the server saw it (--trace): arguments, outcome, faults
        project/                     the documents left behind, journal beside them: what was scored
        prompt.txt, report.txt       the probe's task text as sent; the model's final report
        transcript.json              every message, the model's thinking included (openai backend)
        renders/                     what the model looked at        (not tracked: PNGs, regenerable from project/)
        server.json, *.log           launch config and logs          (not tracked: absolute paths to one machine)
    <run>/runs/_superseded/          episodes the infrastructure ended, kept for the record; the board ignores them

The current engine's reference for every probe is in `benchmarks/probe_references/`.

## Re-scoring

A re-score rebuilds the pristine start document with `fixture.start_document`
and diffs the left-behind document against it, so it runs against the
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
