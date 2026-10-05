"""setup_runs.py LABEL [TAG] -> one fresh project + server.json per probe (optionally only a tag).

Same as the Ollama rig's, minus the `rd` shell shim: the LM Studio runner is a
native MCP client and nothing here needs a shell.
"""
import json, sys
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
    print(probe.id, "->", probe.start)
