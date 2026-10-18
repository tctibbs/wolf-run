"""A small network control, so another computer or a phone can drive the screen.

    GET  /state                  which stage it's on, and the house while playing
    POST /prime /skip /reset     the same as the host's Ctrl+P, Ctrl+E, and Ctrl+R

The server runs on its own thread and never touches Qt. Commands go into a queue
that the window drains on the main thread, and the window keeps a status dict up
to date for the server to read.
"""

import errno
import json
import queue
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from wolf_run.stages import Screen, Stage

COMMANDS = ("prime", "skip", "reset")
HELP = "Try GET /state, or POST /prime, /skip, or /reset."
ALL_INTERFACES = "0.0.0.0"
MAX_BODY = 64 * 1024  # bytes; commands carry no body, so anything sent is ignored

Status = Callable[[], dict[str, Any]]


def apply_command(screen: Screen, name: str, t: float) -> None:
    """Do what a command asks, at animation time `t`. Unknown names do nothing."""
    if name == "prime":
        screen.prime(t)
    elif name == "skip":
        screen.skip_to_ending(t)
    elif name == "reset":
        screen.reset(t)


def state_of(screen: Screen) -> dict[str, Any]:
    """What GET /state reports: the stage, plus the house (1 to 3) while playing."""
    state: dict[str, Any] = {"stage": screen.stage.value}
    if screen.stage is Stage.GAME and screen.game is not None:
        state["house"] = screen.game.level + 1
    return state


def publish(status: dict[str, Any], screen: Screen) -> None:
    """Bring the shared status in line with the screen, in place.

    Keys that no longer apply go first, so the server thread never reads a house
    number alongside a stage it doesn't belong to.
    """
    fresh = state_of(screen)
    for gone in status.keys() - fresh.keys():
        del status[gone]
    status.update(fresh)


def start(
    port: int,
    commands: queue.Queue[str],
    status: Status,
    host: str = ALL_INTERFACES,
) -> ThreadingHTTPServer:
    """Serve the control on a background thread. Port 0 picks a free one."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self._route() == "state":
                self._reply(200, status())
            else:
                self._reply(404, {"error": HELP})

        def do_POST(self) -> None:
            self._skip_body()
            name = self._route()
            if name not in COMMANDS:
                self._reply(404, {"error": HELP})
                return
            commands.put(name)
            self._reply(200, {"ok": name})

        def _route(self) -> str:
            return urlsplit(self.path).path.strip("/")

        def _skip_body(self) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > 0:
                self.rfile.read(min(length, MAX_BODY))

        def _reply(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            """Stay quiet: every request would otherwise print a line."""

    try:
        server = ThreadingHTTPServer((host, port), Handler)
    except OSError as error:
        raise RuntimeError(_bind_problem(port, error)) from error
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _bind_problem(port: int, error: OSError) -> str:
    if error.errno == errno.EADDRINUSE:
        return (
            f"Port {port} is busy. Is another wolf-run screen already running? "
            "Stop it, or pick another port with --control."
        )
    return f"Couldn't listen on port {port}: {error.strerror or error}."


def lan_address() -> str:
    """This computer's address on the home network, for another computer to reach."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))  # picks a route; sends nothing
        return str(probe.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()
