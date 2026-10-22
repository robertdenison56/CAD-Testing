"""Registering the server with an MCP client: ``roaddraft-mcp --config CLIENT``.

Every client wants the same three things -- a name, the command and its
arguments -- in a file and a shape of its own: Claude Code reads a project
``.mcp.json``, Claude Desktop, LM Studio and Cursor an ``mcpServers`` table in
JSON, VS Code a ``servers`` table, Codex a ``[mcp_servers.NAME]`` block in
TOML. Each wants an absolute path to an executable that lives inside this
project's virtualenv, which is the part nobody should type by hand: the README
used to say ``/ABSOLUTE/PATH/TO/.venv/bin/roaddraft-mcp``, and this
project's own path has a space in it.

So the server's command line is the one source. ``roaddraft-mcp --doc X
--autosave --config lmstudio`` prints the registration for exactly the server
invocation those flags describe -- the command resolved for the Python it runs
under, the paths made absolute -- and ``--write`` puts it in the client's file,
merged in beside whatever servers are already there. The entry on stdout is the
thing to paste; what to do next goes to stderr, as the server's own messages do.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shlex
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

#: The clients this knows how to register with, and where each keeps its servers.
CLIENTS: Dict[str, str] = {
    "claude-code": "Claude Code: the project's .mcp.json (checked in; approved once per project)",
    "claude-desktop": "Claude Desktop: claude_desktop_config.json in the app's support folder",
    "lmstudio": "LM Studio: ~/.lmstudio/mcp.json",
    "codex": "Codex CLI: a [mcp_servers.NAME] block in ~/.codex/config.toml",
    "cursor": "Cursor: ~/.cursor/mcp.json",
    "vscode": "VS Code: the project's .vscode/mcp.json, under `servers`",
    "json": "the bare server entry, for any other mcpServers-style client",
}

#: Clients whose file belongs to the project (no backup when it is rewritten:
#: the file is in version control, or is meant to be), and the variable each
#: expands to the project folder, so the file carries no path from one machine.
#: Claude Code documents ``${CLAUDE_PROJECT_DIR}`` for exactly this ("relative
#: paths in stdio command") -- but the CLI bundled with the desktop app (2.1.289,
#: Oct 2026) does not set it when it reads the file: ``claude mcp list`` warns
#: the variable is missing, and the session spawned the literal string and got
#: ENOENT. With ``:-.`` as the default the command falls back to a path relative
#: to the server's working directory, which for a project .mcp.json is the
#: project; a Claude Code that sets the variable gets the absolute path.
#: VS Code has ``${workspaceFolder}``.
PROJECT_FILE_CLIENTS = ("claude-code", "vscode")
PROJECT_VARIABLE = {"claude-code": "${CLAUDE_PROJECT_DIR:-.}", "vscode": "${workspaceFolder}"}

DEFAULT_NAME = "roaddraft"


# ------------------------------------------------------------ the command

def server_command(python: Optional[str] = None) -> List[str]:
    """How to start the server from the given Python (default: this one).

    The console script beside the interpreter when the package is installed
    (``.venv/bin/roaddraft-mcp``); otherwise ``python -m roaddraft.mcp.server``,
    which works from a bare checkout with ``src`` on the path.
    """
    # absolute, but NOT resolved: a venv's python is a symlink to the base
    # interpreter, and the console script lives beside the link, not the target
    interpreter = Path(python or sys.executable).absolute()
    script = interpreter.parent / ("roaddraft-mcp.exe" if os.name == "nt" else "roaddraft-mcp")
    if script.is_file():
        return [str(script)]
    return [str(interpreter), "-m", "roaddraft.mcp.server"]


def server_args(doc: Optional[str] = None, autosave: bool = False,
                trace: Optional[str] = None, out_dir: Optional[str] = None,
                only: Optional[Sequence[str]] = None, exclude: Optional[Sequence[str]] = None,
                project: Optional[str] = None, root: Optional[str] = None,
                profile: str = "default", attachments: Optional[str] = None) -> List[str]:
    """The server's own options as an argument list, every path absolute: a
    client starts the server from a working directory of its own choosing, so
    a relative path in a registration would resolve somewhere else."""
    args: List[str] = []
    if doc:
        args += ["--doc", _absolute(doc)]
    elif project and project != "Untitled":
        args += ["--project", project]
    if autosave:
        args.append("--autosave")
    if trace:
        args += ["--trace", _absolute(trace)]
    if out_dir:
        args += ["--out-dir", _absolute(out_dir)]
    if only:
        args += ["--only", ",".join(only)]
    if exclude:
        args += ["--exclude", ",".join(exclude)]
    if root:
        args += ["--root", _absolute(root)]
    if profile and profile != "default":
        args += ["--profile", profile]
    if attachments:
        args += ["--attachments", _absolute(attachments)]
    return args


def _absolute(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def portable(words: Sequence[str], client: str, project_dir: Optional[str] = None) -> List[str]:
    """``words`` with every absolute path under the project folder rewritten
    through the client's project variable -- for the files that live in the
    project and are checked in. Other clients get the words unchanged."""
    variable = PROJECT_VARIABLE.get(client)
    if not variable:
        return list(words)
    root = Path(project_dir or os.getcwd())
    roots = {root.absolute(), root.resolve()}
    out = []
    for word in words:
        rel = None
        if Path(word).is_absolute():
            for form in (Path(word), Path(word).resolve()):
                for base in roots:
                    try:
                        rel = form.relative_to(base)
                        break
                    except ValueError:
                        continue
                if rel is not None:
                    break
        out.append(f"{variable}/{rel.as_posix()}" if rel is not None else word)
    return out


# -------------------------------------------------------------- the entry

def entry(command: Sequence[str], args: Sequence[str] = (), client: str = "json") -> dict:
    """One server entry in the client's shape. All of them take ``command`` and
    ``args``; Claude Code and VS Code name the transport too."""
    first, rest = command[0], list(command[1:]) + list(args)
    out: Dict[str, object] = {}
    if client in ("claude-code", "vscode"):
        out["type"] = "stdio"
    out["command"] = first
    out["args"] = rest
    return out


def document(client: str, name: str, command: Sequence[str], args: Sequence[str] = (),
             project_dir: Optional[str] = None) -> dict:
    """The whole file for a JSON client with just this server in it."""
    return {_table_key(client): {name: entry(portable(command, client, project_dir),
                                             portable(args, client, project_dir), client)}}


def _table_key(client: str) -> str:
    return "servers" if client == "vscode" else "mcpServers"


def toml_block(name: str, command: Sequence[str], args: Sequence[str] = ()) -> str:
    """Codex's ``[mcp_servers.NAME]`` block."""
    e = entry(command, args, "codex")
    lines = [f"[mcp_servers.{name}]",
             f"command = {json.dumps(e['command'])}",
             "args = [" + ", ".join(json.dumps(a) for a in e["args"]) + "]"]
    return "\n".join(lines) + "\n"


def claude_mcp_add(name: str, command: Sequence[str], args: Sequence[str] = (),
                   scope: Optional[str] = None) -> str:
    """The ``claude mcp add`` line, quoted for a shell (paths carry spaces)."""
    words = ["claude", "mcp", "add"]
    if scope:
        words += ["--scope", scope]
    words += [name, "--"] + list(command) + list(args)
    return " ".join(shlex.quote(w) for w in words)


def codex_mcp_add(name: str, command: Sequence[str], args: Sequence[str] = ()) -> str:
    words = ["codex", "mcp", "add", name, "--"] + list(command) + list(args)
    return " ".join(shlex.quote(w) for w in words)


# ------------------------------------------------------------- the files

def default_file(client: str, project_dir: Optional[str] = None) -> Optional[Path]:
    """Where the client reads its servers from, on this platform. None for
    ``json``, which is not a file."""
    home = Path.home()
    project = Path(project_dir or os.getcwd())
    if client == "claude-code":
        return project / ".mcp.json"
    if client == "vscode":
        return project / ".vscode" / "mcp.json"
    if client == "claude-desktop":
        if sys.platform == "darwin":
            return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        if os.name == "nt":
            return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"
        return home / ".config" / "Claude" / "claude_desktop_config.json"
    if client == "lmstudio":
        return home / ".lmstudio" / "mcp.json"
    if client == "codex":
        return home / ".codex" / "config.toml"
    if client == "cursor":
        return home / ".cursor" / "mcp.json"
    return None


def render(client: str, name: str, command: Sequence[str], args: Sequence[str] = (),
           project_dir: Optional[str] = None) -> str:
    """What ``--config CLIENT`` prints: the registration, ready to paste."""
    if client not in CLIENTS:
        raise ValueError(f"unknown client {client!r}; one of {', '.join(CLIENTS)}")
    if client == "codex":
        return toml_block(name, command, args)
    if client == "json":
        return json.dumps({name: entry(command, args, client)}, indent=2) + "\n"
    return json.dumps(document(client, name, command, args, project_dir), indent=2) + "\n"


def guidance(client: str, name: str, command: Sequence[str], args: Sequence[str],
             path: Optional[Path], written: bool) -> str:
    """What to do with it (stderr)."""
    where = str(path) if path else "the client's MCP settings"
    if client == "claude-code":
        lines = [(f"written to {where}" if written else f"the project's .mcp.json ({where}); --write puts it there"),
                 "Claude Code asks once per project to approve the servers in .mcp.json; "
                 "`claude mcp reset-project-choices` asks again.",
                 "For every project instead of this one:",
                 "  " + claude_mcp_add(name, command, args, scope="user")]
    elif client == "codex":
        lines = [(f"written to {where}" if written else f"goes in {where}; --write puts it there, or let Codex do it:"),
                 "  " + codex_mcp_add(name, command, args)]
    elif client == "json":
        lines = ["one entry for an mcpServers table; the client's own file says where"]
    else:
        lines = [(f"written to {where}" if written else f"goes in {where} under {_table_key(client)!r}; --write merges it in"),
                 "restart the client, or reload its MCP servers, to pick it up"]
    return "\n".join(lines)


def write(client: str, name: str, command: Sequence[str], args: Sequence[str] = (),
          path: Optional[Path] = None, project_dir: Optional[str] = None) -> Path:
    """Put the entry in the client's file, keeping every other server there.

    A JSON file is parsed, the one entry set, and the file written back; a file
    that does not parse is left alone and reported, never overwritten. Codex's
    TOML gets its ``[mcp_servers.NAME]`` block replaced or appended. A user-level
    file that existed is backed up beside itself first.
    """
    if client == "json":
        raise ValueError("`json` is the bare entry, not a client; name the client to write to")
    target = Path(path) if path else default_file(client, project_dir)
    assert target is not None
    existed = target.is_file()
    if existed and client not in PROJECT_FILE_CLIENTS:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.with_name(f"{target.name}.bak-{stamp}")
        backup.write_bytes(target.read_bytes())
    target.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        text = target.read_text() if existed else ""
        target.write_text(_replace_toml_block(text, name, toml_block(name, command, args)))
        return target
    doc: dict = {}
    if existed and target.read_text().strip():
        try:
            doc = json.loads(target.read_text())
        except ValueError as ex:
            raise ValueError(f"{target} is not valid JSON ({ex}); fix or move it first, "
                             f"nothing was written") from None
        if not isinstance(doc, dict):
            raise ValueError(f"{target} does not hold a JSON object; nothing was written")
    key = _table_key(client)
    table = doc.get(key)
    if not isinstance(table, dict):
        table = doc[key] = {}
    table[name] = entry(portable(command, client, project_dir),
                        portable(args, client, project_dir), client)
    target.write_text(json.dumps(doc, indent=2) + "\n")
    return target


def _replace_toml_block(text: str, name: str, block: str) -> str:
    """``text`` with its ``[mcp_servers.NAME]`` table (and sub-tables such as
    ``[mcp_servers.NAME.env]``) replaced by ``block``, or ``block`` appended."""
    header = f"[mcp_servers.{name}]"
    sub = f"[mcp_servers.{name}."
    lines = text.splitlines()
    out: List[str] = []
    i, replaced = 0, False
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == header or stripped.startswith(sub):
            # skip this table up to the next table header
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("["):
                i += 1
            if not replaced:
                out.extend(block.rstrip("\n").split("\n"))
                out.append("")
                replaced = True
            continue
        out.append(line)
        i += 1
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.extend(block.rstrip("\n").split("\n"))
    return "\n".join(out).rstrip("\n") + "\n"


# ------------------------------------------------------------------ main

def configure(client: str, name: str = DEFAULT_NAME, args: Sequence[str] = (),
              write_to: Optional[str] = None, python: Optional[str] = None,
              project_dir: Optional[str] = None, out=None, err=None) -> int:
    """The ``--config`` entry point: print the registration, or write it."""
    out = out or sys.stdout
    err = err or sys.stderr
    if client not in CLIENTS:
        print(f"unknown client {client!r}; one of: {', '.join(CLIENTS)}", file=err)
        return 2
    command = server_command(python)
    path = (Path(write_to) if write_to and write_to != "-" else None) or default_file(client, project_dir)
    written = False
    if write_to is not None:
        try:
            path = write(client, name, command, args, path, project_dir)
        except ValueError as ex:
            print(str(ex), file=err)
            return 1
        written = True
    out.write(render(client, name, command, args, project_dir))
    out.flush()
    print(guidance(client, name, command, args, path, written), file=err)
    return 0
