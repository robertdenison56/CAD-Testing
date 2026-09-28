"""setup_runs.py LABEL -> one fresh project + bridge folder per probe."""
import json, os, stat, sys
from pathlib import Path
from roaddraft.probes import fixture, tasks

root = Path(__file__).parent
label = sys.argv[1]
venv = Path(sys.executable).parent
for probe in tasks.PROBES:
    folder = root / "runs" / label / probe.id
    folder.mkdir(parents=True, exist_ok=True)
    _model, sheets = fixture.build(folder / "project")
    (folder / "server.json").write_text(json.dumps({"cmd": [
        str(venv / "roaddraft-mcp"), "--doc", str(sheets), "--autosave",
        "--trace", str(folder / "trace.jsonl"), "--out-dir", str(folder / "renders")]}))
    rd = folder / "rd"
    rd.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{root / "bridge.py"}" "{folder}" "$@"\n')
    rd.chmod(rd.stat().st_mode | stat.S_IXUSR)
    print(probe.id, "->", rd)
