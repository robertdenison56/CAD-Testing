"""setup_runs.py LABEL SELECTOR... -> one fresh project, server.json and prompt per probe.

A SELECTOR is a probe tag (tier3) or a probe id (row-data); a probe is set up
when it matches any of them. The 2026-10-04 LM Studio rig's script with the
2026-10-06 rig's selectors, and `prompt.txt` is now `prompting.task_text`,
the same words the trajectory recorder hands a model, rather than a copy of
them kept in the runner. Nothing here needs a shell: the runner is a native
MCP client.
"""
import json, sys
from pathlib import Path
from roaddraft.probes import fixture, prompting, tasks

root = Path(__file__).parent
label, selectors = sys.argv[1], set(sys.argv[2:])
venv = Path(sys.executable).parent
for probe in tasks.PROBES:
    if selectors and not (selectors & set(probe.tags)) and probe.id not in selectors:
        continue
    folder = root / "runs" / label / probe.id
    folder.mkdir(parents=True, exist_ok=True)
    doc = fixture.start_document(folder / "project", probe.start)
    (folder / "server.json").write_text(json.dumps({"cmd": [
        str(venv / "roaddraft-mcp"), "--doc", str(doc), "--autosave",
        "--trace", str(folder / "trace.jsonl"), "--out-dir", str(folder / "renders")]}))
    (folder / "prompt.txt").write_text(prompting.task_text(probe))
    print(probe.id, "->", probe.start)
