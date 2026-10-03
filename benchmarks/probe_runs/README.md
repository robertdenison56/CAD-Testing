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
        renders/                     what the model looked at        (not tracked: PNGs, regenerable from project/)
        deliverables/                the plots: <probe>.pdf, <probe>.reference.pdf, OVERVIEW.pdf, OVERVIEW.png
        server.json, rd, *.log       launch shim and logs            (not tracked: absolute paths to one machine)

`2026-09-19/runs/haiku/_stray_saves/` holds the three files Haiku saved under
names of its own, moved out of the repository root where they landed.

## Re-scoring

From a run folder, with the venv active:

    python score_runs.py <label>          fable, haiku, t1-fable, t1-haiku, gpt-oss-120b, gpt-oss-120b-r2, qwen3.5-9b ...

`score_runs.py` rebuilds the pristine start document with `fixture.start_document`
and diffs the left-behind document against it, so a re-score runs against the
*current* probe definitions: a probe whose check has changed may score an old
run differently. That is why the documents are kept and not just the numbers.

## Running a new one

Copy a rig into a new dated folder rather than adding labels to an old one.

    python setup_runs.py <label> [tag]    runs/<label>/<probe>/ with a fresh project and server.json
    # drive it: a subagent through each probe's `rd`, `python ollama_runner.py <label> <model>`,
    #           or `python lmstudio_runner.py [--budget MIN] <label> <model>` (see that run's RESULTS.md for the LM Studio setup)
    python score_runs.py <label>
    python make_deliverables.py <label>   the PDFs and the pass/fail overview, beside the scores
