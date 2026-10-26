# Probe references

Every probe's scripted solution (`Probe.solve`), kept as a finished RoadDraft
project. Each folder is the project the probe starts from, with the document
the agent is handed completed and saved under its own name: open it in
RoadDraft and it reads its design through the reference beside it, as the
start does. The solution drafts through the engine's command bus, with the
same commands an agent sends over MCP, and the journal beside the document
holds every one of them; `Session.replay_journal` rebuilds the document from it.

Generated, not edited: `python -m roaddraft.probes reference --out benchmarks/pilot_references`
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
| p01-redraw-alignment-fdot915 | pilot, scan, redraw, draft, alignment | [ALGNRD01.rdraft](p01-redraw-alignment-fdot915/ALGNRD01.rdraft) | none | PASS: CL1 rebuilt from the scan: on its tie, its bearings, curve data and curve point stations as lettered, and drawn |
| p01-redraw-alignment-ppm045 | pilot, scan, redraw, draft, alignment | [0000000000aa01.rdraft](p01-redraw-alignment-ppm045/0000000000aa01.rdraft) | BB01: 0000000000bb01.rdraft | PASS: TB1 rebuilt from the scan: on its tie, its bearings, curve data and curve point stations as lettered, and drawn |
| p02-sources-ppm045 | pilot, sources, caltrans, edit | [0000000000ea001.rdraft](p02-sources-ppm045/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: "TB2"'s tangent length corrected to 426.42, every other source unchanged, the finding recorded |
| p02-sources-wfl19a | pilot, sources, wfl, edit | [SamplePlan_pln_pp6.rdraft](p02-sources-wfl19a/SamplePlan_pln_pp6.rdraft) | COR: SamplePlan_cor.rdraft, ALI: SamplePlan_ali.rdraft, SUR: SamplePlan_sur.rdraft | PASS: the curve data's R corrected to 643.00, every other source unchanged, the finding recorded |
| p02-sources-wfl19b | pilot, sources, wfl, edit, basefile | [SamplePlan_pln_pp6.rdraft](p02-sources-wfl19b/SamplePlan_pln_pp6.rdraft) | COR: SamplePlan_cor.rdraft, ALI: SamplePlan_ali.rdraft, SUR: SamplePlan_sur.rdraft | PASS: MAIN 01 restored to R 643.00 in the alignment file and its centerline redrawn; the sheet, the corridor and the stationing untouched; the finding recorded |
| p03-grid-ground-wfl20 | pilot, survey, grid-ground, wfl | [SamplePlan_sur.rdraft](p03-grid-ground-wfl20/SamplePlan_sur.rdraft) | none | PASS: all five ties on grid within 0.05 ft |
| p03-intl-feet-ppm047 | pilot, survey, units, caltrans | [0000000000aa01.rdraft](p03-intl-feet-ppm047/0000000000aa01.rdraft) | BB01: 0000000000bb01.rdraft | PASS: all six points in US survey feet within 0.05 ft |
| p03-misclosure-ppm045 | pilot, survey, cogo, caltrans | [0000000000aa01.rdraft](p03-misclosure-ppm045/0000000000aa01.rdraft) | BB01: 0000000000bb01.rdraft | PASS: balanced parcel on V-PROP, misclosure 0.275 ft, 1:6,534, 132,346 sq ft |
| p04-crowded-ppm045 | pilot, layout, crowded, caltrans, twist, verifier | [0000000000ea001.rdraft](p04-crowded-ppm045/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: all 3 lines of L-1 lettered in full and to the spec, every table titled with its line, and nothing over anything |
| p04-crowded-ppm050 | pilot, layout, crowded, caltrans, twist, verifier | [0000000000ea007.rdraft](p04-crowded-ppm050/0000000000ea007.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: all 5 lines of L-7 lettered in full and to the spec, every table titled with its line, and nothing over anything |
| p05-breaks-cfl | pilot, layout, sheet-breaks, match-line, CFL | [PLA(Sample).rdraft](p05-breaks-cfl/PLA(Sample).rdraft) | SUR: TERSample.rdraft, ALI: ALI(MAIN)Sample.rdraft, COR: COR(MAIN)Sample.rdraft | PASS: 3 sheets at 1" = 50' on the wfl border (the stretch needs 2), every station shown, stationing left to right on each, match lines square and lettered alike at 15+00.00, 20+00.00 |
| p05-breaks-fdot904 | pilot, layout, sheet-breaks, match-line, FDOT | [PLANRD01.rdraft](p05-breaks-fdot904/PLANRD01.rdraft) | ALI: ALGNRD01.rdraft, COR: DSGNRD01.rdraft | PASS: 3 sheets at 1" = 50' on the fdot border (the stretch needs 2), every station shown, stationing left to right on each, match lines square and lettered alike at 478+00.00, 484+00.00 |
| p06-plan-profile-cflpnp | pilot, pilot-06, plan-profile, layout | [PNP(Sample).rdraft](p06-plan-profile-cflpnp/PNP(Sample).rdraft) | COR: COR(MAIN)Sample.rdraft, TER: TERSample.rdraft | PASS: Plan 1: plan over profile, grade line within 0.10 ft, stations lined up, curves lettered |
| p06-plan-profile-wfl14 | pilot, pilot-06, plan-profile, layout | [SamplePlan_pln_pp1.rdraft](p06-plan-profile-wfl14/SamplePlan_pln_pp1.rdraft) | COR: SamplePlan_cor.rdraft, SUR: SamplePlan_sur.rdraft | PASS: D.5: plan over profile, grade line within 0.10 ft, stations lined up, curves lettered |
| p10-typical-cfl01 | pilot, typical-section, cfl | [TYP(Sample)4R.rdraft](p10-typical-cfl01/TYP(Sample)4R.rdraft) | none | PASS: section drawn to the description: catch points -27.49 and 26.95 ft, shown at 1" = 10' |
| p10-typical-wfl07 | pilot, typical-section, wfl | [yell12-2_pln_typ.rdraft](p10-typical-wfl07/yell12-2_pln_typ.rdraft) | none | PASS: section drawn to the description: catch points -42.00 and 40.34 ft, shown at 1" = 10' |
| p11-radius-ppm160 | pilot, redline, edit, caltrans, base-file, radius | [0000000000na001.rdraft](p11-radius-ppm160/0000000000na001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: the redline picked up: curve 1 of "WS" revised to R = 1500' in AA01, PIs held, the alignment data on PD-1 re-lettered from it with nothing stale left, the revision recorded and the markup removed |
| p11-station-ppm045 | pilot, redline, edit, caltrans, base-file, station | [0000000000ea001.rdraft](p11-station-ppm045/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: the redline picked up: "TB1" restationed +25.00 ft in AA01, the alignment data on L-1 re-lettered from it with nothing stale left, the callouts restationed, the revision recorded and the markup removed |
| p12-route65-d13 | pilot, plan-set, sheets, caltrans, quantities, whole-job | [route65-d13-plans.rdraft](p12-route65-d13/route65-d13-plans.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: a five-sheet set: title sheet with a matching index, three layouts at 1" = 50' showing 640+00 to 672+00 with agreeing match lines, numbers and totals consistent, and the quantities (28,444 SY, 2,761 LF) within 1 % |
| p13-striping-wfl15 | pilot, pilot-13, striping, sight-distance | [SamplePlan_pln_pp2.rdraft](p13-striping-wfl15/SamplePlan_pln_pp2.rdraft) | COR: SamplePlan_cor.rdraft, SUR: SamplePlan_sur.rdraft | PASS: D.6 striped 115+00.00 to 122+50.00 at 55 mph (PSD 900 ft): zones up-station 116+60.00 to 121+29.00, broken lines 10/30, edge lines |
| p13-striping-wfl16 | pilot, pilot-13, striping, sight-distance | [SamplePlan_pln_pp3.rdraft](p13-striping-wfl16/SamplePlan_pln_pp3.rdraft) | COR: SamplePlan_cor.rdraft, SUR: SamplePlan_sur.rdraft | PASS: D.7 striped 122+50.00 to 130+00.00 at 50 mph (PSD 800 ft): zones down-station 125+75.00 to 129+21.00, broken lines 10/30, edge lines |
| p14-qa-review-ppm045a | pilot, qa, caltrans, twist | [0000000000ea001.rdraft](p14-qa-review-ppm045a/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: called clean: NO ERRORS FOUND on QA-REVIEW and no marks |
| p14-qa-review-ppm045b | pilot, qa, caltrans, twist | [0000000000ea001.rdraft](p14-qa-review-ppm045b/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: all 6 errors marked on QA-REVIEW, at most 1 false alarm, nothing else changed |
| p14-qa-review-wfl19 | pilot, qa, wfl | [SamplePlan_pln_pp6.rdraft](p14-qa-review-wfl19/SamplePlan_pln_pp6.rdraft) | COR: SamplePlan_cor.rdraft, ALI: SamplePlan_ali.rdraft, SUR: SamplePlan_sur.rdraft | PASS: all 3 errors marked on QA-REVIEW, at most 1 false alarm, nothing else changed |
| p15-plan-reading-cflpla | pilot, scan, reading | [plan-check.rdraft](p15-plan-reading-cflpla/plan-check.rdraft) | none | PASS: all 6 answers read right off the scan |
| p15-plan-reading-ppm046 | pilot, scan, reading | [plan-check.rdraft](p15-plan-reading-ppm046/plan-check.rdraft) | none | PASS: all 6 answers read right off the scan |
| p15-plan-reading-wflp14 | pilot, scan, reading | [plan-check.rdraft](p15-plan-reading-wflp14/plan-check.rdraft) | none | PASS: all 6 answers read right off the scan |
| p17-twist-fdot916 | pilot, layout, twist, verifier | [DRPRRD01.rdraft](p17-twist-fdot916/DRPRRD01.rdraft) | COR: DSGNRD01.rdraft, ALI: ALGNRD01.rdraft | PASS: "CL1" lettered in full on the re-cut sheet 1, every label along (or square to) its line and reading from the bottom or right as plotted |
| p17-twist-ppm160 | pilot, layout, twist, verifier | [0000000000na001.rdraft](p17-twist-ppm160/0000000000na001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: "NWR" lettered in full on the re-cut sheet PD-1, every label along (or square to) its line and reading from the bottom or right as plotted |
| p18-redline-pdf-cflpla | pilot, redline-understanding, markup, scan, edit, cfl | [PLA(Sample).rdraft](p18-redline-pdf-cflpla/PLA(Sample).rdraft) | COR: COR(MAIN)Sample.rdraft, ALI: ALI(MAIN)Sample.rdraft | PASS: every mark on PLA-redlines.pdf picked up on PLA(SAMPLE), and nothing else touched |
| p18-redline-pdf-fdot915 | pilot, redline-understanding, markup, scan, edit, fdot | [PLPRRD02.rdraft](p18-redline-pdf-fdot915/PLPRRD02.rdraft) | COR: DSGNRD01.rdraft, ALI: ALGNRD01.rdraft | PASS: every mark on sheet-12-redlines.pdf picked up on 12, and nothing else touched |
| p18-redline-pdf-ppm045 | pilot, redline-understanding, markup, scan, edit, caltrans | [0000000000ea001.rdraft](p18-redline-pdf-ppm045/0000000000ea001.rdraft) | AA01: 0000000000aa01.rdraft, BB01: 0000000000bb01.rdraft | PASS: every mark on L-1-redlines.pdf picked up on L-1, and nothing else touched |
| p18-redline-pdf-wfl19 | pilot, redline-understanding, markup, scan, edit, wfl | [SamplePlan_pln_pp6.rdraft](p18-redline-pdf-wfl19/SamplePlan_pln_pp6.rdraft) | COR: SamplePlan_cor.rdraft, ALI: SamplePlan_ali.rdraft, SUR: SamplePlan_sur.rdraft | PASS: every mark on D-10-redlines.pdf picked up on D.10, and nothing else touched |
