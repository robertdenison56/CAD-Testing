"""Registering the MCP server with a client (roaddraft/mcp/config.py).

What these pin: the command resolves to the venv's console script (or falls
back to ``python -m``), every path in a registration is absolute except in a
project file, where it goes through the client's project variable; each client
gets its own shape; ``--write`` merges in beside other servers and never
overwrites a file it cannot read; and the server's own CLI carries its options
into the registration instead of serving.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from roaddraft.mcp import config, server


def test_server_command_is_the_venv_script_or_python_m(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python = bin_dir / "python"
    python.write_text("")
    # no console script beside the interpreter: run the module
    assert config.server_command(str(python)) == [str(python), "-m", "roaddraft.mcp.server"]
    script = bin_dir / "roaddraft-mcp"
    script.write_text("")
    assert config.server_command(str(python)) == [str(script)]
    # a venv's python is a symlink to the base interpreter; the script is beside the LINK
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(python)
    (venv_bin / "roaddraft-mcp").write_text("")
    assert config.server_command(str(venv_bin / "python")) == [str(venv_bin / "roaddraft-mcp")]
    # the real one, for this interpreter, is one or the other and absolute
    real = config.server_command()
    assert Path(real[0]).is_absolute()
    assert real[0].endswith("roaddraft-mcp") or real[1:] == ["-m", "roaddraft.mcp.server"]


def test_server_args_carry_the_options_with_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    here = tmp_path.resolve()
    args = config.server_args(doc="project/SR-100.sheets.rdoc.json", autosave=True,
                              trace="trace.jsonl", out_dir="renders",
                              only=["draw_line", "place_callout"], exclude=["undo"])
    assert args == ["--doc", str(here / "project" / "SR-100.sheets.rdoc.json"),
                    "--autosave", "--trace", str(here / "trace.jsonl"),
                    "--out-dir", str(here / "renders"),
                    "--only", "draw_line,place_callout", "--exclude", "undo"]
    # a project name only matters for a new document; the default is not carried
    assert config.server_args(project="Untitled") == []
    assert config.server_args(project="SR-100") == ["--project", "SR-100"]
    assert config.server_args(doc="x.rdraft", project="SR-100")[:2] == ["--doc", str(here / "x.rdraft")]


def test_each_client_has_its_shape():
    cmd, args = ["/v/bin/roaddraft-mcp"], ["--doc", "/p/a.rdraft", "--autosave"]
    desktop = json.loads(config.render("claude-desktop", "roaddraft", cmd, args))
    assert desktop == {"mcpServers": {"roaddraft": {"command": "/v/bin/roaddraft-mcp",
                                                     "args": ["--doc", "/p/a.rdraft", "--autosave"]}}}
    assert json.loads(config.render("lmstudio", "rd", cmd, args)) == {"mcpServers": {"rd": desktop["mcpServers"]["roaddraft"]}}
    assert json.loads(config.render("cursor", "rd", cmd, args)) == {"mcpServers": {"rd": desktop["mcpServers"]["roaddraft"]}}
    # Claude Code and VS Code name the transport; VS Code's table is `servers`
    code = json.loads(config.render("claude-code", "roaddraft", cmd, args, project_dir="/elsewhere"))
    assert code["mcpServers"]["roaddraft"] == {"type": "stdio", "command": "/v/bin/roaddraft-mcp",
                                               "args": ["--doc", "/p/a.rdraft", "--autosave"]}
    vscode = json.loads(config.render("vscode", "roaddraft", cmd, args, project_dir="/elsewhere"))
    assert list(vscode) == ["servers"] and vscode["servers"]["roaddraft"]["type"] == "stdio"
    # Codex: a TOML table
    assert config.render("codex", "roaddraft", cmd, args) == (
        '[mcp_servers.roaddraft]\ncommand = "/v/bin/roaddraft-mcp"\n'
        'args = ["--doc", "/p/a.rdraft", "--autosave"]\n')
    # the bare entry
    assert json.loads(config.render("json", "roaddraft", cmd, args)) == {"roaddraft": desktop["mcpServers"]["roaddraft"]}
    # python -m form: the interpreter is the command, the rest leads the args
    e = config.entry(["/v/bin/python", "-m", "roaddraft.mcp.server"], ["--autosave"])
    assert e == {"command": "/v/bin/python", "args": ["-m", "roaddraft.mcp.server", "--autosave"]}
    with pytest.raises(ValueError):
        config.render("emacs", "roaddraft", cmd)


def test_project_files_go_through_the_project_variable(tmp_path):
    """A checked-in .mcp.json must not carry one machine's path: paths under the
    project are written as ${CLAUDE_PROJECT_DIR:-.}/... (the project when Claude
    Code sets the variable, else relative to the server's working directory,
    which is the project); those outside stay absolute."""
    project = tmp_path / "repo with space"
    project.mkdir()
    cmd = [str(project / ".venv" / "bin" / "roaddraft-mcp")]
    args = ["--doc", str(project / "examples" / "a.rdraft"), "--trace", "/elsewhere/trace.jsonl"]
    code = config.document("claude-code", "roaddraft", cmd, args, project_dir=str(project))
    e = code["mcpServers"]["roaddraft"]
    assert e["command"] == "${CLAUDE_PROJECT_DIR:-.}/.venv/bin/roaddraft-mcp"
    assert e["args"] == ["--doc", "${CLAUDE_PROJECT_DIR:-.}/examples/a.rdraft",
                         "--trace", "/elsewhere/trace.jsonl"]
    vs = config.document("vscode", "roaddraft", cmd, args, project_dir=str(project))
    assert vs["servers"]["roaddraft"]["command"] == "${workspaceFolder}/.venv/bin/roaddraft-mcp"
    # a user-level file keeps the absolute path: the variable means nothing there
    lm = config.document("lmstudio", "roaddraft", cmd, args, project_dir=str(project))
    assert lm["mcpServers"]["roaddraft"]["command"] == cmd[0]
    # a venv outside the project cannot be made portable and stays absolute
    outside = config.document("claude-code", "roaddraft", ["/opt/venv/bin/roaddraft-mcp"], [],
                              project_dir=str(project))
    assert outside["mcpServers"]["roaddraft"]["command"] == "/opt/venv/bin/roaddraft-mcp"


def test_claude_mcp_add_quotes_for_the_shell():
    line = config.claude_mcp_add("roaddraft", ["/Volumes/My SSD/.venv/bin/roaddraft-mcp"],
                                 ["--doc", "/p/SR 100.rdraft", "--autosave"], scope="user")
    assert line == ("claude mcp add --scope user roaddraft -- '/Volumes/My SSD/.venv/bin/roaddraft-mcp' "
                    "--doc '/p/SR 100.rdraft' --autosave")
    assert config.codex_mcp_add("rd", ["/v/roaddraft-mcp"]) == "codex mcp add rd -- /v/roaddraft-mcp"


def test_default_files_per_client(tmp_path):
    assert config.default_file("claude-code", str(tmp_path)) == tmp_path / ".mcp.json"
    assert config.default_file("vscode", str(tmp_path)) == tmp_path / ".vscode" / "mcp.json"
    assert config.default_file("lmstudio") == Path.home() / ".lmstudio" / "mcp.json"
    assert config.default_file("codex") == Path.home() / ".codex" / "config.toml"
    assert config.default_file("cursor") == Path.home() / ".cursor" / "mcp.json"
    desktop = config.default_file("claude-desktop")
    assert desktop is not None and desktop.name == "claude_desktop_config.json"
    assert config.default_file("json") is None


def test_write_merges_beside_other_servers_and_backs_up(tmp_path):
    target = tmp_path / "mcp.json"
    target.write_text(json.dumps({"mcpServers": {"other": {"command": "x", "args": []}}, "keep": 1}))
    cmd = ["/v/bin/roaddraft-mcp"]
    config.write("lmstudio", "roaddraft", cmd, ["--autosave"], target)
    doc = json.loads(target.read_text())
    assert doc["keep"] == 1 and doc["mcpServers"]["other"] == {"command": "x", "args": []}
    assert doc["mcpServers"]["roaddraft"] == {"command": "/v/bin/roaddraft-mcp", "args": ["--autosave"]}
    backups = sorted(tmp_path.glob("mcp.json.bak-*"))
    assert len(backups) == 1 and json.loads(backups[0].read_text())["mcpServers"] == {"other": {"command": "x", "args": []}}
    # again: the entry is replaced, not duplicated; a second backup is taken
    config.write("lmstudio", "roaddraft", cmd, [], target)
    assert json.loads(target.read_text())["mcpServers"]["roaddraft"]["args"] == []
    assert len(list(tmp_path.glob("mcp.json.bak-*"))) >= 1
    # a file that is not there yet, in a folder that is not there yet
    fresh = tmp_path / "new" / "mcp.json"
    config.write("claude-desktop", "roaddraft", cmd, [], fresh)
    assert json.loads(fresh.read_text()) == {"mcpServers": {"roaddraft": {"command": "/v/bin/roaddraft-mcp", "args": []}}}
    assert not list((tmp_path / "new").glob("*.bak-*"))
    # a project file is rewritten in place without a backup, in its own shape
    code = tmp_path / ".mcp.json"
    config.write("claude-code", "roaddraft", [str(tmp_path / ".venv/bin/roaddraft-mcp")], [], code,
                 project_dir=str(tmp_path))
    assert json.loads(code.read_text())["mcpServers"]["roaddraft"] == {
        "type": "stdio", "command": "${CLAUDE_PROJECT_DIR:-.}/.venv/bin/roaddraft-mcp", "args": []}
    assert not list(tmp_path.glob(".mcp.json.bak-*"))
    vs = tmp_path / ".vscode" / "mcp.json"
    config.write("vscode", "roaddraft", cmd, [], vs, project_dir=str(tmp_path))
    assert "servers" in json.loads(vs.read_text())


def test_write_leaves_a_file_it_cannot_read_alone(tmp_path):
    target = tmp_path / "mcp.json"
    target.write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        config.write("lmstudio", "roaddraft", ["/v/roaddraft-mcp"], [], target)
    assert target.read_text() == "{not json"
    target.write_text("[1, 2]")
    with pytest.raises(ValueError, match="JSON object"):
        config.write("lmstudio", "roaddraft", ["/v/roaddraft-mcp"], [], target)
    with pytest.raises(ValueError, match="bare entry"):
        config.write("json", "roaddraft", ["/v/roaddraft-mcp"], [], tmp_path / "x.json")


def test_codex_write_replaces_its_own_block_only(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('[model]\nx = 1\n\n[mcp_servers.roaddraft]\ncommand = "old"\nargs = []\n\n'
                      '[mcp_servers.roaddraft.env]\nA = "1"\n\n[mcp_servers.other]\ncommand = "o"\n')
    config.write("codex", "roaddraft", ["/v/roaddraft-mcp"], ["--autosave"], target)
    text = target.read_text()
    assert text == ('[model]\nx = 1\n\n[mcp_servers.roaddraft]\ncommand = "/v/roaddraft-mcp"\n'
                    'args = ["--autosave"]\n\n[mcp_servers.other]\ncommand = "o"\n')
    assert '"old"' not in text and "env" not in text
    # appended when absent, after a blank line; created when there is no file
    config.write("codex", "second", ["/v/roaddraft-mcp"], [], target)
    assert target.read_text().endswith('[mcp_servers.other]\ncommand = "o"\n\n[mcp_servers.second]\n'
                                       'command = "/v/roaddraft-mcp"\nargs = []\n')
    fresh = tmp_path / "fresh.toml"
    config.write("codex", "roaddraft", ["/v/roaddraft-mcp"], [], fresh)
    assert fresh.read_text() == '[mcp_servers.roaddraft]\ncommand = "/v/roaddraft-mcp"\nargs = []\n'
    assert len(list(tmp_path.glob("config.toml.bak-*"))) >= 1


def test_the_servers_cli_prints_a_registration_instead_of_serving(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    here = tmp_path.resolve()
    doc = here / "a.rdraft"
    rc = server.main(["--config", "lmstudio", "--doc", str(doc), "--autosave",
                      "--trace", "t.jsonl", "--name", "rd-a"])
    out, err = capsys.readouterr()
    assert rc == 0
    got = json.loads(out)["mcpServers"]["rd-a"]
    command = config.server_command()
    assert got["command"] == command[0]
    assert got["args"] == command[1:] + ["--doc", str(doc), "--autosave", "--trace", str(here / "t.jsonl")]
    assert "does not exist yet" in err            # the document was never written
    assert ".lmstudio" in err                     # where it goes
    # --write FILE puts it there; stdout still carries the entry
    rc = server.main(["--config", "claude-code", "--write", str(tmp_path / ".mcp.json")])
    out, err = capsys.readouterr()
    assert rc == 0 and json.loads(out)["mcpServers"]["roaddraft"]["type"] == "stdio"
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["roaddraft"]["type"] == "stdio"
    assert "written to" in err and "claude mcp add --scope user roaddraft --" in err
    # --write on its own is a usage error; an unknown client too
    with pytest.raises(SystemExit):
        server.main(["--write"])
    with pytest.raises(SystemExit):
        server.main(["--config", "emacs"])
    assert config.configure("emacs", err=io.StringIO()) == 2


def test_the_projects_own_mcp_json_is_what_the_generator_writes():
    """The checked-in .mcp.json registers this server for Claude Code through
    the project variable, so it is the same file on every machine."""
    root = Path(__file__).resolve().parent.parent
    doc = json.loads((root / ".mcp.json").read_text())
    entry = doc["mcpServers"]["roaddraft"]
    assert entry["type"] == "stdio"
    assert entry["command"] == "${CLAUDE_PROJECT_DIR:-.}/.venv/bin/roaddraft-mcp"
    assert entry["args"] == []
    # and the generator, run from the project, produces exactly that entry --
    # when the venv is in the project, as it is here; elsewhere it stays absolute
    command = config.server_command()
    if Path(command[0]).is_relative_to(root) if hasattr(Path, "is_relative_to") \
            else str(command[0]).startswith(str(root)):
        generated = config.document("claude-code", "roaddraft", command, [], project_dir=str(root))
        assert generated["mcpServers"]["roaddraft"] == entry
