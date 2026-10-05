"""score_runs.py LABEL -> score every probe's left-behind document and summarise its trace."""
import json, sys, tempfile
from collections import Counter
from pathlib import Path
from roaddraft.api.session import Session
from roaddraft.probes import fixture, tasks

root = Path(__file__).parent / "runs" / sys.argv[1]
passed = ran = 0
for probe in tasks.PROBES:
    folder = root / probe.id
    trace = folder / "trace.jsonl"
    if not folder.is_dir():
        continue
    calls = [json.loads(l) for l in trace.read_text().splitlines()] if trace.exists() else []
    if not calls:
        print(f"--    {probe.id}: no tool calls"); continue
    ran += 1
    tmp = Path(tempfile.mkdtemp())
    baseline = Session.load(fixture.start_document(tmp, probe.start), out_dir=tmp)
    doc = folder / "project" / fixture.START[probe.start]
    result = probe.check(baseline, Session.load(doc, out_dir=folder))
    passed += result.passed
    faults = [c for c in calls if not c["ok"]]
    print(f"{'PASS' if result.passed else 'FAIL'}  {probe.id}")
    print(f"      {result.detail}")
    print(f"      {len(calls)} calls, {len(faults)} faults")
    print(f"      tools: {dict(Counter(c['tool'] for c in calls))}")
    for c in faults:
        print(f"      FAULT {c['tool']}: {c['error'].get('message', '')[:170]}")
    for c in calls:
        for w in c.get("warnings", []):
            print(f"      WARN  {c['tool']}: {w[:170]}")
print(f"\n{passed}/{ran} passed")
