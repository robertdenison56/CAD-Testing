"""setup_runs.py LABEL [TAG] -> one fresh project + bridge folder per probe (optionally only a tag)."""
import json, stat, sys
from pathlib import Path
from roaddraft.probes import fixture, tasks

root = Path(__file__).parent
label = sys.argv[1]
tag = sys.argv[2] if len(sys.argv) > 2 else None
venv = Path(sys.executable).parent
for probe in tasks.PROBES:
    if tag and tag not in probe.tags:
        continue
    folder = root / "runs" / label / probe.id
    folder.mkdir(parents=True, exist_ok=True)
    doc = fixture.start_document(folder / "project", probe.start)
    (folder / "server.json").write_text(json.dumps({"cmd": [
        str(venv / "roaddraft-mcp"), "--doc", str(doc), "--autosave",
        "--trace", str(folder / "trace.jsonl"), "--out-dir", str(folder / "renders")]}))
    rd = folder / "rd"
    rd.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{root / "bridge.py"}" "{folder}" "$@"\n')
    rd.chmod(rd.stat().st_mode | stat.S_IXUSR)
    print(probe.id, "->", probe.start)
