# Expert playtests

Human-drafted episodes on benchmark tasks, one folder per task id: the saved document, the journal
when the GUI or REPL kept one, the verify report, and (with a journal) the episode file written by
replaying it through the harness loop, so budgets and the whitelist applied to the human's commands
exactly as they do to a model's. The eval plan's E2 acceptance wants one playtest at 100.

    python -m roaddraft.eval human start --task D1-000042-... --taskset d1-dev --out /tmp/playtest-42
    # draft it in RoadDraft (roaddraft-web or the REPL), save over the same file; keep the journal if you can
    python -m roaddraft.eval human score /tmp/playtest-42          # writes benchmarks/expert/<task_id>/

The record is committed; the playtest folder itself is not.
