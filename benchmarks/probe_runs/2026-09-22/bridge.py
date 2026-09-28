"""A command-line bridge to a live MCP server, for an agent that has a shell
but no native MCP client.

    bridge.py DIR instructions        the server's MCP `instructions`
    bridge.py DIR tools               tool names and the first line of each description
    bridge.py DIR describe TOOL       full description and JSON input schema
    bridge.py DIR call TOOL 'JSON'    tools/call; prints the result content
    bridge.py DIR stop                shut the server down

DIR holds `server.json` ({"cmd": [...]}) and gets `port`, `pid`, `bridge.log`.
The first use starts one daemon that owns ONE long-lived server process over
stdio -- so the session (undo history, journal, ids) lives as long as a native
client's would -- and serves requests on 127.0.0.1. Everything the agent sees
comes from the server: nothing is added, summarised or filtered here, except
that an image content block is replaced by a note (the text block beside it
already carries the file path).
"""
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


def daemon(folder: Path) -> None:
    cmd = json.loads((folder / "server.json").read_text())["cmd"]
    log = (folder / "bridge.log").open("a")
    # run the server from the project folder, not wherever the agent's shell is:
    # a model that saves under a relative name then writes beside the project
    # instead of into someone's repository (seen in the 2026-09-19 Haiku run)
    home = folder / "project"
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=log, text=True, bufsize=1,
                            cwd=str(home) if home.is_dir() else None)
    lock = threading.Lock()
    counter = [0]

    def rpc(method, params=None, notify=False):
        with lock:
            message = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                message["params"] = params
            if not notify:
                counter[0] += 1
                message["id"] = counter[0]
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
            if notify:
                return None
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError("the MCP server closed its output")
                reply = json.loads(line)
                if reply.get("id") == message["id"]:
                    return reply

    init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "probe-bridge", "version": "1"}})
    rpc("notifications/initialized", notify=True)
    state = {"init": init["result"], "tools": rpc("tools/list")["result"]["tools"]}

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    (folder / "pid").write_text(str(os.getpid()))
    (folder / "port").write_text(str(srv.getsockname()[1]))

    def serve(conn):
        with conn:
            data = b""
            while not data.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            request = json.loads(data)
            op = request["op"]
            if op == "instructions":
                out = {"text": state["init"].get("instructions", "")}
            elif op == "tools":
                out = {"tools": state["tools"]}
            elif op == "call":
                reply = rpc("tools/call", {"name": request["tool"],
                                           "arguments": request["arguments"]})
                out = reply.get("result") or {"rpc_error": reply.get("error")}
            elif op == "stop":
                out = {"stopped": True}
            else:
                out = {"rpc_error": f"unknown op {op}"}
            conn.sendall(json.dumps(out).encode() + b"\n")
            if op == "stop":
                proc.stdin.close()
                proc.wait(timeout=10)
                os._exit(0)

    while True:
        conn, _addr = srv.accept()
        threading.Thread(target=serve, args=(conn,), daemon=True).start()


def ask(folder: Path, request: dict) -> dict:
    port_file = folder / "port"
    if not port_file.exists():
        subprocess.Popen([sys.executable, __file__, str(folder), "--daemon"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(100):
            if port_file.exists():
                break
            time.sleep(0.1)
        else:
            raise SystemExit("the bridge did not start; see bridge.log")
    with socket.create_connection(("127.0.0.1", int(port_file.read_text())), timeout=120) as s:
        s.sendall(json.dumps(request).encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk:
                break
            data += chunk
    return json.loads(data)


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    folder, op = Path(argv[0]).resolve(), argv[1]
    if op == "--daemon":
        daemon(folder)
        return 0
    if op == "instructions":
        print(ask(folder, {"op": "instructions"})["text"])
    elif op == "tools":
        for tool in ask(folder, {"op": "tools"})["tools"]:
            first = tool["description"].split("\n")[0]
            print(f"{tool['name']}: {first}")
    elif op == "describe":
        tools = {t["name"]: t for t in ask(folder, {"op": "tools"})["tools"]}
        if len(argv) < 3 or argv[2] not in tools:
            print(f"no tool {argv[2:]!r}; run `tools` for the names")
            return 1
        tool = tools[argv[2]]
        print(tool["description"])
        print("\ninputSchema:")
        print(json.dumps(tool["inputSchema"], indent=1))
    elif op == "call":
        if len(argv) < 3:
            print("usage: call TOOL 'JSON arguments'")
            return 2
        try:
            arguments = json.loads(argv[3]) if len(argv) > 3 else {}
        except json.JSONDecodeError as ex:
            print(f"arguments are not valid JSON: {ex}")
            return 2
        result = ask(folder, {"op": "call", "tool": argv[2], "arguments": arguments})
        if "rpc_error" in result:
            print(f"protocol error: {result['rpc_error']}")
            return 1
        if result.get("isError"):
            print("[tool error]")
        for block in result.get("content", []):
            if block.get("type") == "text":
                print(block["text"])
            else:
                print(f"[{block.get('type')} content omitted by the bridge -- the file "
                      f"path is in the text above; open it to look]")
        return 1 if result.get("isError") else 0
    elif op == "stop":
        if (folder / "port").exists():
            try:
                ask(folder, {"op": "stop"})
            except Exception:
                pass
            for name in ("port", "pid"):
                (folder / name).unlink(missing_ok=True)
        print("stopped")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
