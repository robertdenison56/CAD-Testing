# Probe solves as conversations

Every probe's scripted solution, run through the MCP server with tracing on
and kept as the conversation a model would have had: the server's
instructions, the task as a model is given it, one assistant turn per tool
call, the text the server returned for it, and a report. Queries are in it as
well as commands; the journal beside each reference in
`benchmarks/probe_references` keeps only the commands.

Generated, not edited: `python -m roaddraft.trajectories record --out benchmarks/trajectories/families/draft-alignment --family draft-alignment --seeds 0-9`
(roaddraft 0.1.0). `tools.json` holds the 78 tool definitions every
conversation was recorded against (sha256:56e836778cd8da5d616462b15357626dbc619158d101949a660d1488e2283ef4).

    <probe>/trace.jsonl        every call: the MCP server's trace line, result included
    <probe>/conversation.json  the run as messages, with the verdict and the audit
    <probe>/record.json        the conversation's header: counts, faithfulness, verdict

A conversation is **faithful** when the run read nothing from the document
except through the tool surface, so a model could have taken every step in
it. A scripted solve that reads the document object directly (`session.doc`)
is listed with where it did so: its commands carry numbers that came from
nowhere a model can see, and it is not training data until that is fixed.

10 of 10 faithful; 10 of 10 pass their check.

| Probe | Tags | Queries | Commands | Faults | Faithful | Check |
|---|---|---|---|---|---|---|
| draft-alignment@0 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@1 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@2 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@3 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@4 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@5 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@6 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@7 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@8 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-alignment@9 | family, draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
