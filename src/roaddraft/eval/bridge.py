"""The eval harness's MCP bridge: a stdio MCP server for a headless CLI whose
tools are the harness's.

A headless coding CLI (Claude Code, Codex) drives its own tool-calling loop
against MCP servers it starts itself.  To run one as an agent of the harness
the harness has to be that server, so the CLI starts this bridge as its one
MCP server and speaks newline-delimited JSON-RPC to it over stdio.  The
bridge connects to the socket the harness opened for the episode -- its one
argument, ``unix:/path`` or ``tcp:127.0.0.1:PORT`` -- takes the tool list
from the harness's first message, answers ``initialize``, ``tools/list`` and
``ping`` itself, and forwards every ``tools/call`` to the harness, which runs
it through the episode loop (``agents/cli.py``) and sends the result back.
Several calls may be in flight at once: Claude Code makes parallel calls,
and the harness answers them in order.  Once the harness closes the socket
the episode is over, and any call still waiting or still to come is answered
with an error at once, so a CLI that goes on asking never hangs.

Standard library only, run by file path: it imports nothing of RoadDraft,
so the CLI needs no PYTHONPATH and the tool surface is exactly what the
harness sent.  The wire to the harness is one JSON object per line:
``hello`` and ``tools`` to start, ``call``/``result`` by the request's own
JSON-RPC id, ``close`` from the harness, ``bye`` at the CLI's EOF.
"""
import json
import socket
import sys
import threading

PROTOCOL = "2025-06-18"
SERVER_INFO = {"name": "roaddraft-eval", "version": "1"}
#: what a call gets once the episode is over
OVER = {"content": [{"type": "text",
                     "text": "the episode has ended; this call was not run"}],
        "isError": True}
PARSE_ERROR, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32601, -32602


def connect(address):
    """A socket to the harness at ``unix:/path`` or ``tcp:host:port``."""
    kind, _, rest = address.partition(":")
    if kind == "unix":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(rest)
        return sock
    if kind == "tcp":
        host, _, port = rest.rpartition(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, int(port)))
        return sock
    raise SystemExit("bridge: the address is unix:/path or tcp:host:port, not %r" % address)


class Bridge:
    def __init__(self, sock, stdin, stdout):
        self.rfile = sock.makefile("r", encoding="utf-8")
        self.wfile = sock.makefile("w", encoding="utf-8")
        self.stdin, self.stdout = stdin, stdout
        self.out_lock = threading.Lock()
        self.sock_lock = threading.Lock()
        self.tools = []
        self.closed = False
        self.pending = {}   # JSON-RPC id of each call the harness has not answered

    # ------------------------------------------------------------- harness

    def start(self):
        """Say hello; the harness answers with the tools; then listen for results."""
        self.to_harness({"type": "hello"})
        first = self.rfile.readline()
        hello = json.loads(first) if first.strip() else {}
        self.tools = hello.get("tools") or []
        threading.Thread(target=self.pump, daemon=True).start()

    def pump(self):
        """Results from the harness, each to the CLI as the reply to its call."""
        try:
            for line in self.rfile:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("type") == "result":
                    self.pending.pop(msg.get("id"), None)
                    self.reply(msg.get("id"), {"content": msg.get("content") or [],
                                               "isError": bool(msg.get("isError"))})
                elif msg.get("type") == "close":
                    break
        except (OSError, ValueError):
            pass
        self.closed = True
        for mid in list(self.pending):
            self.reply(mid, OVER)
        self.pending.clear()

    def to_harness(self, payload):
        with self.sock_lock:
            self.wfile.write(json.dumps(payload) + "\n")
            self.wfile.flush()

    # ----------------------------------------------------------------- CLI

    def write(self, payload):
        with self.out_lock:
            self.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.stdout.flush()

    def reply(self, mid, result):
        self.write({"jsonrpc": "2.0", "id": mid, "result": result})

    def error(self, mid, code, message):
        self.write({"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}})

    def handle(self, msg):
        if not isinstance(msg, dict):
            return
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method is None:          # a response to nothing we asked
            return
        if method == "initialize":
            self.reply(mid, {"protocolVersion": params.get("protocolVersion") or PROTOCOL,
                             "capabilities": {"tools": {"listChanged": False}},
                             "serverInfo": dict(SERVER_INFO)})
        elif method == "tools/list":
            self.reply(mid, {"tools": self.tools})
        elif method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str):
                self.error(mid, INVALID_PARAMS, "tools/call needs a tool name")
                return
            if self.closed:
                self.reply(mid, OVER)
                return
            self.pending[mid] = True
            try:
                self.to_harness({"type": "call", "id": mid, "name": name,
                                 "arguments": params.get("arguments") or {}})
            except OSError:
                self.closed = True
                self.pending.pop(mid, None)
                self.reply(mid, OVER)
        elif method == "ping":
            self.reply(mid, {})
        elif method.startswith("notifications/"):
            return
        elif mid is not None:
            self.error(mid, METHOD_NOT_FOUND, "method %r is not supported; this server "
                                              "implements initialize, tools/list, tools/call "
                                              "and ping" % method)

    def serve(self):
        """Read the CLI's JSON-RPC until EOF, then tell the harness."""
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError as ex:
                self.error(None, PARSE_ERROR, "invalid JSON: %s" % ex)
                continue
            for m in (msg if isinstance(msg, list) else [msg]):
                self.handle(m)
        try:
            self.to_harness({"type": "bye"})
        except OSError:
            pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if len(argv) != 1:
        print("usage: bridge.py ADDRESS   (unix:/path or tcp:host:port)", file=sys.stderr)
        return 2
    bridge = Bridge(connect(argv[0]), sys.stdin, sys.stdout)
    bridge.start()
    bridge.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
