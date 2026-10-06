# Probe references

Every probe's scripted solution (`Probe.solve`), kept as a finished RoadDraft
project. Each folder is the project the probe starts from, with the document
the agent is handed completed and saved under its own name: open it in
RoadDraft and it reads its design through the reference beside it, as the
start does. The solution drafts through the engine's command bus, with the
same commands an agent sends over MCP, and the journal beside the document
holds every one of them; `Session.replay_journal` rebuilds the document from it.

Generated, not edited: `python -m roaddraft.probes reference --out benchmarks/probe_references`
(roaddraft 0.1.0). Each verdict is `Probe.check` on the saved document read
back from disk, against a fresh start, which is how a model's document is
scored; `python -m roaddraft.probes score <probe> --doc <document>` repeats it.

    <probe>/<document>      the completed document: the file the agent is handed, finished
    <probe>/<design file>   what the document references, untouched
    <probe>/<name>.jsonl    the journal: the start, then every command the solution ran
    <probe>/<probe>.pdf     the sheets as plotted (print_pdf); model space when it has none
    <probe>/<probe>.dxf     for AutoCAD, Civil 3D or MicroStation: each sheet a layout, references bound in
    <probe>/reference.json  the probe, its prompt and the verdict

33 of 33 pass.

| Probe | Tags | Completed document | References | Check, read back from disk |
|---|---|---|---|---|
| edge-c102 | find, reference | [SR-100.sheets.rdoc.json](edge-c102/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands on DESIGN:AR-003 (0.00 ft) |
| edge-curve-c102 | find, curve | [SR-100.sheets.rdoc.json](edge-curve-c102/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands on DESIGN:AR-003 (0.00 ft) |
| shoulder-c101 | find, discriminate | [SR-100.sheets.rdoc.json](shoulder-c101/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands on DESIGN:LN-010 (0.00 ft) |
| centerline-c103 | find, discriminate | [SR-100.sheets.rdoc.json](centerline-c103/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands on DESIGN:AR-002 (0.00 ft) |
| both-edges-c101 | find, multiple | [SR-100.sheets.rdoc.json](both-edges-c101/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: both edges: leader lands on DESIGN:LN-004 (0.00 ft); leader lands on DESIGN:LN-007 (0.00 ft) |
| title-blocks | sheets | [SR-100.sheets.rdoc.json](title-blocks/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all 3 title blocks carry the project, sheet title and scale |
| pc-by-station | find, station, reference-design | [SR-100.sheets.rdoc.json](pc-by-station/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands 0.00 ft from the PC of the first curve and the text carries '24+05.27' |
| edge-c102-paper | find, reference, paper | [SR-100.sheets.rdoc.json](edge-c102-paper/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands on DESIGN:AR-003 (0.00 ft) |
| sta-offset-c101-paper | station, reference-design, paper | [SR-100.sheets.rdoc.json](sta-offset-c101-paper/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: leader lands 0.00 ft from SR-100 18+00, 12' RT and the text carries '18+00' |
| draft-tangent-ne | draft, alignment | [DESIGN.model.rdoc.json](draft-tangent-ne/DESIGN.model.rdoc.json) | none | PASS: MAIN-ST runs due east from N 5000, E 2000 and is drawn |
| draft-pi-curve | draft, alignment, curve | [DESIGN.model.rdoc.json](draft-pi-curve/DESIGN.model.rdoc.json) | none | PASS: SR-9 runs through its PIs on an 800 ft curve and is drawn |
| draft-bearing-distance | draft, alignment, cogo | [DESIGN.model.rdoc.json](draft-bearing-distance/DESIGN.model.rdoc.json) | none | PASS: RAMP-B runs N 62°30' E, deflects 35° right on a 600 ft curve, and is drawn |
| draft-edges-shoulders | draft, offsets | [SR-100.centerline.rdoc.json](draft-edges-shoulders/SR-100.centerline.rdoc.json) | none | PASS: edges of pavement at 12 ft and edges of shoulder at 20 ft, both sides, the length of SR-100 |
| draft-turn-lane | draft, offsets, stations | [SR-100.model.rdoc.json](draft-turn-lane/SR-100.model.rdoc.json) | none | PASS: taper 30+00 to 31+20, full width to 36+00, squared off, and nothing beyond |
| draft-cul-de-sac | draft, alignment, geometry | [DESIGN.model.rdoc.json](draft-cul-de-sac/DESIGN.model.rdoc.json) | none | PASS: OAK-CT with its bulb, and edges of pavement that stop where they meet it |
| draft-building | draft, geometry, cogo | [DESIGN.model.rdoc.json](draft-building/DESIGN.model.rdoc.json) | none | PASS: a 60 x 40 ft footprint, long side N 30° E, on V-BLDG |
| draft-roadway | draft, alignment, cogo, whole-job | [DESIGN.model.rdoc.json](draft-roadway/DESIGN.model.rdoc.json) | none | PASS: ELM-AVE from its bearings, lanes and shoulders both sides, 21 of 21 stations labelled |
| sheet-set-callouts | tier2, paper, sheets, multiple | [SR-100.sheets.rdoc.json](sheet-set-callouts/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: 15 callouts on paper across 3 sheets, each on its edge, the centerline named, title blocks numbered 1 to 3 |
| station-callouts | tier2, paper, station, loop | [SR-100.sheets.rdoc.json](station-callouts/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all 15 stations 11+00 to 25+00 called out on C-101, each leader on its station and each text reading it |
| clean-callouts | tier2, paper, legibility | [SR-100.sheets.rdoc.json](clean-callouts/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: 3 callouts on C-102, each on its line, text clear of all linework by 0.05 in, leaders clear of each other, all inside the drawing area |
| draft-intersection-corner | tier2, draft, geometry, two-alignments | [Main-Cross.model.rdoc.json](draft-intersection-corner/Main-Cross.model.rdoc.json) | none | PASS: a 50 ft return tangent to both curbs at [5082.00, 5044.00] and [5032.00, 5094.00], both curb lines trimmed to it |
| draft-fix-the-drawing | tier2, draft, qa, edit | [SR-100.flawed.rdoc.json](draft-fix-the-drawing/SR-100.flawed.rdoc.json) | none | PASS: the 11 ft piece replaced at 12 ft, the shoulder back on its layer, the callout no longer calls the shoulder the edge, and nothing else touched |
| draft-roadway-sheets | tier2, draft, cogo, whole-job, sheets | [DESIGN.model.rdoc.json](draft-roadway-sheets/DESIGN.model.rdoc.json) | none | PASS: ELM-AVE drafted, and C-101 shows all of it through a 1"=100' viewport inside the border, title block filled |
| line-data | tier3, paper, alignment-data, line | [SR-100.sheets.rdoc.json](line-data/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all 3 tangents lettered with bearing and length on the sheet that shows them: above the line, parallel to it, clear of the linework |
| curve-points | tier3, paper, alignment-data, station | [SR-100.sheets.rdoc.json](curve-points/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all 4 curve points lettered with station and BC/EC, square to the line, reading bottom to top, beside the point |
| curve-data | tier3, paper, alignment-data, curve, table | [SR-100.sheets.rdoc.json](curve-data/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: each sheet's CURVE DATA table lists exactly the curves it shows, numbered along SR-100 with the design's R, Δ, T and L, and every curve carries its numbered bubble with a leader to the curve |
| stationing | tier3, paper, alignment-data, loop | [SR-100.sheets.rdoc.json](stationing/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all 16 stations 26+00 to 41+00 ticked 7 ft across the line and lettered Caltrans-style below it |
| width-dims | tier3, paper, dimension | [SR-100.sheets.rdoc.json](width-dims/SR-100.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: the four widths at 17+00 dimensioned across the road, 8' 12' 12' 8', each number clear of the others |
| row-data | tier3, paper, line, curve, table | [SR-100-row.sheets.rdoc.json](row-data/SR-100-row.sheets.rdoc.json) | DESIGN: SR-100-row.model.rdoc.json | PASS: all 7 pieces of the right of way tagged in order (C1, L1, L2, L3, L4, L5, C2) and tabulated with their full bearings, lengths, radii and deltas |
| equation-data | tier3, paper, alignment-data, station | [SR-100-eq.sheets.rdoc.json](equation-data/SR-100-eq.sheets.rdoc.json) | DESIGN: SR-100-eq.model.rdoc.json | PASS: the equation 35+00.00 BK = 35+50.00 AH lettered at its point, T-2 at 1240.36' (not the 1290.35' its stations differ by), and the BC at 40+81.72 |
| qa-alignment-data | tier3, paper, qa, edit | [SR-100.qa.sheets.rdoc.json](qa-alignment-data/SR-100.qa.sheets.rdoc.json) | DESIGN: SR-100.model.rdoc.json | PASS: all five planted errors corrected (BC station, T-2 length, curve 2's T and L, the restarted curve number, the EC lettered BC) and nothing else touched |
| l2-match-lines | tier3, paper, caltrans, twist | [SR70-Bear-Creek.sheets.rdraft](l2-match-lines/SR70-Bear-Creek.sheets.rdraft) | DESIGN: SR70-Bear-Creek.model.rdraft | PASS: both match lines square to "SR70" on the turned sheet at 574+50 and 589+50, across the roadway, lettered MATCH LINE (L-1) and (L-3) |
| l2-alignment-data | tier3, paper, caltrans, twist, whole-job | [SR70-Bear-Creek.sheets.rdraft](l2-alignment-data/SR70-Bear-Creek.sheets.rdraft) | DESIGN: SR70-Bear-Creek.model.rdraft | PASS: L-2's alignment data restored: both tangents with bearing and length parallel to the turned line, five curve points including the PCC, bubbles 2 to 5 on their curves, the curve table 2 to 5, and no lettering over lettering |
