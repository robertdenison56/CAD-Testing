# Probe solves as conversations

Every probe's scripted solution, run through the MCP server with tracing on
and kept as the conversation a model would have had: the server's
instructions, the task as a model is given it, one assistant turn per tool
call, the text the server returned for it, and a report. Queries are in it as
well as commands; the journal beside each reference in
`benchmarks/probe_references` keeps only the commands.

Generated, not edited: `python -m roaddraft.trajectories record --out benchmarks/trajectories/families/callout-station --family callout-station --seeds 0-9`
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
| callout-station@0 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@1 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@2 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@3 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@4 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@5 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@6 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@7 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@8 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
| callout-station@9 | family, find, station, paper | 2 | 2 | 0 | yes | PASS |
