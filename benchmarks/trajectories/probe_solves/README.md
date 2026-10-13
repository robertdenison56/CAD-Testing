# Probe solves as conversations

Every probe's scripted solution, run through the MCP server with tracing on
and kept as the conversation a model would have had: the server's
instructions, the task as a model is given it, one assistant turn per tool
call, the text the server returned for it, and a report. Queries are in it as
well as commands; the journal beside each reference in
`benchmarks/probe_references` keeps only the commands.

Generated, not edited: `python -m roaddraft.trajectories record --out benchmarks/trajectories/probe_solves`
(roaddraft 0.1.0). `tools.json` holds the 103 tool definitions every
conversation was recorded against (sha256:97c51a2415649df4303137bd0361ae52a99db789187d9dde0dc17d545fca17d0).

    <probe>/trace.jsonl        every call: the MCP server's trace line, result included
    <probe>/conversation.json  the run as messages, with the verdict and the audit
    <probe>/record.json        the conversation's header: counts, faithfulness, verdict

A conversation is **faithful** when the run read nothing from the document
except through the tool surface, so a model could have taken every step in
it. A scripted solve that reads the document object directly (`session.doc`)
is listed with where it did so: its commands carry numbers that came from
nowhere a model can see, and it is not training data until that is fixed.

21 of 33 faithful; 33 of 33 pass their check.

| Probe | Tags | Queries | Commands | Faults | Faithful | Check |
|---|---|---|---|---|---|---|
| edge-c102 | find, reference | 3 | 1 | 0 | yes | PASS |
| edge-curve-c102 | find, curve | 3 | 1 | 0 | yes | PASS |
| shoulder-c101 | find, discriminate | 3 | 1 | 0 | yes | PASS |
| centerline-c103 | find, discriminate | 3 | 1 | 0 | yes | PASS |
| both-edges-c101 | find, multiple | 6 | 2 | 0 | yes | PASS |
| title-blocks | sheets | 1 | 3 | 0 | yes | PASS |
| pc-by-station | find, station, reference-design | 2 | 1 | 0 | yes | PASS |
| edge-c102-paper | find, reference, paper | 2 | 1 | 0 | yes | PASS |
| sta-offset-c101-paper | station, reference-design, paper | 2 | 1 | 0 | yes | PASS |
| draft-tangent-ne | draft, alignment | 0 | 2 | 0 | yes | PASS |
| draft-pi-curve | draft, alignment, curve | 0 | 2 | 0 | yes | PASS |
| draft-bearing-distance | draft, alignment, cogo | 0 | 2 | 0 | yes | PASS |
| draft-edges-shoulders | draft, offsets | 0 | 2 | 0 | yes | PASS |
| draft-turn-lane | draft, offsets, stations | 4 | 3 | 0 | yes | PASS |
| draft-cul-de-sac | draft, alignment, geometry | 1 | 4 | 0 | yes | PASS |
| draft-building | draft, geometry, cogo | 0 | 2 | 0 | yes | PASS |
| draft-roadway | draft, alignment, cogo, whole-job | 0 | 5 | 0 | yes | PASS |
| sheet-set-callouts | tier2, paper, sheets, multiple | 30 | 18 | 0 | yes | PASS |
| station-callouts | tier2, paper, station, loop | 1 | 16 | 0 | no: roaddraft/probes/tier2.py:348 in sheet_stations | PASS |
| clean-callouts | tier2, paper, legibility | 6 | 3 | 0 | yes | PASS |
| draft-intersection-corner | tier2, draft, geometry, two-alignments | 2 | 4 | 0 | yes | PASS |
| draft-fix-the-drawing | tier2, draft, qa, edit | 0 | 5 | 0 | no: roaddraft/probes/tier2.py:550 in _sr100; roaddraft/probes/tier2.py:557 in planted; roaddraft/probes/tier2.py:561 in planted; roaddraft/probes/tier2.py:654 in _solve_fix | PASS |
| draft-roadway-sheets | tier2, draft, cogo, whole-job, sheets | 1 | 8 | 0 | yes | PASS |
| line-data | tier3, paper, alignment-data, line | 4 | 4 | 0 | no: roaddraft/probes/tier3.py:563 in _station_anchor; roaddraft/probes/tier3.py:651 in _solve_line_data; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
| curve-points | tier3, paper, alignment-data, station | 5 | 5 | 0 | no: roaddraft/probes/tier3.py:686 in _solve_curve_points; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
| curve-data | tier3, paper, alignment-data, curve, table | 8 | 8 | 0 | no: roaddraft/probes/tier3.py:563 in _station_anchor; roaddraft/probes/tier3.py:732 in _solve_curve_data; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
| stationing | tier3, paper, alignment-data, loop | 1 | 2 | 0 | no: roaddraft/probes/tier2.py:348 in sheet_stations; roaddraft/probes/tier3.py:563 in _station_anchor | PASS |
| width-dims | tier3, paper, dimension | 9 | 5 | 0 | no: roaddraft/probes/tier3.py:545 in _at | PASS |
| row-data | tier3, paper, line, curve, table | 6 | 10 | 0 | no: roaddraft/probes/tier3.py:1144 in _solve_row_data; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
| equation-data | tier3, paper, alignment-data, station | 5 | 4 | 0 | no: roaddraft/probes/tier3.py:1255 in _solve_equation; roaddraft/probes/tier3.py:563 in _station_anchor; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
| qa-alignment-data | tier3, paper, qa, edit | 0 | 6 | 0 | no: roaddraft/probes/tier3.py:1289 in _sheet_texts; roaddraft/probes/tier3.py:1294 in _sheet_tables | PASS |
| l2-match-lines | tier3, paper, caltrans, twist | 7 | 5 | 0 | no: roaddraft/probes/tier3.py:545 in _at | PASS |
| l2-alignment-data | tier3, paper, caltrans, twist, whole-job | 14 | 13 | 0 | no: roaddraft/probes/tier3.py:1608 in _solve_l2_data; roaddraft/probes/tier3.py:563 in _station_anchor; roaddraft/probes/tier3.py:80 in __init__; roaddraft/probes/tier3.py:85 in __init__ | PASS |
