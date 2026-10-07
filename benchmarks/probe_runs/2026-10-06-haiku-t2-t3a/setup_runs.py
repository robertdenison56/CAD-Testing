"""setup_runs.py LABEL SELECTOR... -> one fresh project, bridge folder and prompt per probe.

A SELECTOR is a probe tag (tier2) or a probe id (line-data); a probe is set up
when it matches any of them. The 2026-09-22 rig's script, plus `prompt.txt`:
the exact text the runner agent is handed, kept beside the trace so the run
is reproducible from the folder alone. The prompt is the LM Studio runner's
RULES / T1_REPORT / T2_REPORT (2026-10-04-lmstudio-tier2/lmstudio_runner.py)
with the `rd` shell bridge in place of native tools.
"""
import json, stat, sys
from pathlib import Path
from roaddraft.probes import fixture, tasks

T2_REPORT = """When finished, reply briefly with:
1. What you placed, in which space, and what it points at.
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages."""
T1_REPORT = """When finished, reply briefly with:
1. What you created and drew (names, layers, key coordinates).
2. The tool calls that mattered, in order (tool name + the key arguments).
3. Anything that failed, confused you, or that you had to work around -- quote error messages. If you had to compute coordinates yourself, show the arithmetic."""
RULES = """Do one drafting task in a headless CAD engine called RoadDraft. Your ENTIRE tool surface is one command, a bridge to the engine's MCP server. Call it by its full path:

    RD="{rd}"

    "$RD" instructions          the engine's instructions: read these first
    "$RD" tools                 the tool names, one line each
    "$RD" describe TOOL         a tool's full description and its JSON input schema
    "$RD" call TOOL 'JSON'      call a tool; the arguments are one JSON object
    "$RD" call TOOL -           the same, with the JSON read from stdin

Use the stdin form whenever an argument holds a quote mark (feet ', inches or seconds "), for example:

    "$RD" call TOOL - <<'EOF'
    {{"...": "N 45°00'00\\" E 1234.56'"}}
    EOF

Rules:
- Every change to the drawing must go through an `rd call`. Run nothing else: no other programs, no file edits, no copies.
- The document is already open and saves itself after each command. Do not save it under another name.
- Nobody can answer questions. Work until you judge the task done, then stop and give your report.{extra}

THE TASK:
{task}

{report}
"""

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
    rd = folder / "rd"
    rd.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{root / "bridge.py"}" "{folder}" "$@"\n')
    rd.chmod(rd.stat().st_mode | stat.S_IXUSR)
    draft = "draft" in probe.tags
    extra = ("\n- You have no calculator and no code execution. Any arithmetic you need, do yourself."
             if draft else "")
    (folder / "prompt.txt").write_text(RULES.format(
        rd=rd, extra=extra, task=probe.prompt, report=T1_REPORT if draft else T2_REPORT))
    print(probe.id, "->", probe.start, "(draft)" if draft else "")
