# 2026-10-08 — the LM Studio guards in `roaddraft.runners` (smoke, not a benchmark)

The Tier-3 batch B/C pass (`2026-10-07-lmstudio-t3bc`) added four guards to its own rig: a result cap, a
context-full stop, streamed turns with a call cap, and the `anyOf` rewrite of list-valued types. They are now in
`roaddraft.runners` (`core.RESULT_CAP`, `openai_compat.py`), so the native runner survives the models that broke
the Oct 7 version. These two folders are Qwen3.5-9B on edge-c102 through the ported backend; they are not
leaderboard rows.

| Label | Model | Backend | Probe | Result |
|---|---|---|---|---|
| qwen-attempt1 | Qwen3.5-9B (LM Studio, 65k context, LM Link) | openai | edge-c102 | stopped at turn 23, 405 s: `stream error: {"message": "terminated"}`, the engine died and unloaded the model. The document on disk **passes** (leader on DESIGN:AR-003 at 0.00 ft) |
| qwen | the same | openai | edge-c102 | **PASS**, 4 calls, 0 faults, 91 s; leader on DESIGN:AR-003 at 0.00 ft |

The first attempt found the gap the port had left: streamed, a dead engine is an error inside the stream rather
than the 400 the guard watched for, so nothing reloaded. That stream error now reloads the model when it is no
longer loaded at the guard's context. Before the engine died, Qwen had churned on its callout (23 calls:
`place_callout` 11, `delete_entities` 7); what it left standing was correct, which is why the
document scores PASS although the episode did not end. The second attempt went straight through:
`get_document_state`, `get_sheet_state`, `find_entities`, `place_callout`.

    python -m roaddraft.runners run --backend openai --model qwen/qwen3.5-9b --lms-context 65536 \
        --out benchmarks/probe_runs/2026-10-08-runner-guards --label qwen --budget 9 --max-turns 30 edge-c102
    python -m roaddraft.runners score benchmarks/probe_runs/2026-10-08-runner-guards/runs/qwen
