"""score_runs.py LABEL -> score every probe's left-behind document and summarise its trace."""
import json, sys, tempfile
from collections import Counter
from pathlib import Path
from roaddraft.api.session import Session
from roaddraft.probes import fixture, tasks

root = Path(__file__).parent / "runs" / sys.argv[1]
tmp = Path(tempfile.mkdtemp())
_m, pristine = fixture.build(tmp)
passed = 0
rows = []
for probe in tasks.PROBES:
    folder = root / probe.id
    doc = folder / "project" / fixture.SHEET_FILE
    trace = folder / "trace.jsonl"
    calls = [json.loads(l) for l in trace.read_text().splitlines()] if trace.exists() else []
    if not calls:
        print(f"-- {probe.id}: no tool calls yet"); continue
    result = probe.check(Session.load(pristine, out_dir=tmp), Session.load(doc, out_dir=folder))
    passed += result.passed
    faults = [c for c in calls if not c["ok"]]
    callouts = [c for c in calls if c["tool"] == "place_callout" and c["ok"]]
    spaces = Counter(("model" if c["arguments"].get("space") == "model" else "sheet") for c in callouts)
    aims = Counter(next((k for k in ("target_entity", "target_anchor", "target") if k in c["arguments"]), "?")
                   for c in callouts)
    warned = sum(1 for c in calls if c.get("warnings"))
    print(f"{'PASS' if result.passed else 'FAIL'}  {probe.id}")
    print(f"      {result.detail}")
    print(f"      {len(calls)} calls, {len(faults)} faults, {warned} with warnings | callouts: "
          f"{dict(spaces) or '-'} aimed by {dict(aims) or '-'}")
    print(f"      tools: {dict(Counter(c['tool'] for c in calls))}")
    for c in faults:
        print(f"      FAULT {c['tool']}: {c['error'].get('message', '')[:170]}")
    for c in calls:
        for w in c.get("warnings", []):
            print(f"      WARN  {c['tool']}: {w[:170]}")
print(f"\n{passed}/{len(tasks.PROBES)} passed")
