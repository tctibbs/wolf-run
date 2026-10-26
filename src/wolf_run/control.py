"""A small network control, so another computer or a phone can drive the screen.

    GET  /state                  which stage it's on, and the house while playing;
                                 with a card watch, whether the card reads, the
                                 outline ("card_spot": [l, t, w, h]) and, while it
                                 reads, the card ("card_corners": [[x, y] x4]), as
                                 fractions of the camera picture
    POST /prime /skip /reset     the same as the host's Ctrl+P, Ctrl+E, and Ctrl+R
    POST /card                   whether the camera can read the card, and where:
                                 {"found": true, "corners": [[x, y] x4],
                                  "frame": [width, height]}, or {"found": false}
    POST /card-spot              put the card outline around the card, where the
                                 camera sees it now (or {"box": [l, t, w, h]})

Something watching the camera sends /card every second or so while the card reads;
the camera view outlines it until the reports stop for STALE_SECONDS.

The server runs on its own thread and never touches Qt. Commands go into a queue
that the window drains on the main thread, and the window keeps a status dict up
to date for the server to read.
"""

import errno
import json
import queue
import socket
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from wolf_run import card
from wolf_run.stages import Screen, Stage

COMMANDS = ("prime", "skip", "reset")
HELP = "Try GET /state, or POST /prime, /skip, /reset, /card, or /card-spot."
NO_CARD = (
    "The camera can't see the card. Hold it up where guests should, then try again."
)
ALL_INTERFACES = "0.0.0.0"
MAX_BODY = 64 * 1024  # bytes; only /card and /card-spot read a body
STALE_SECONDS = 3.0  # the card counts as seen this long after the last report

Corners = tuple[tuple[float, float], ...]


class Sightings:
    """The latest word on the card, shared between the server and the window."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._corners: Corners | None = None
        self._at = -STALE_SECONDS

    def report(self, corners: Corners | None) -> None:
        """Where the card is, as fractions of the camera picture, or None if gone."""
        with self._lock:
            self._corners, self._at = corners, self._clock()

    def seen(self) -> Corners | None:
        """The card's corners, if a recent report says it reads."""
        with self._lock:
            if self._clock() - self._at > STALE_SECONDS:
                return None
            return self._corners


def parse_card(body: bytes) -> Corners | None:
    """A /card report: its four corners as fractions of the frame, or None when the
    card isn't there. Raises ValueError, saying what's wrong."""
    try:
        report = json.loads(body or b"{}")
    except ValueError:
        raise ValueError('Send JSON, like {"found": false}.') from None
    if not isinstance(report, dict) or not isinstance(report.get("found"), bool):
        raise ValueError('Say whether the card was found: {"found": true or false}.')
    if not report["found"]:
        return None
    corners, frame = report.get("corners"), report.get("frame")
    if not _numbers(frame, 2) or min(frame) <= 0:
        raise ValueError('Give the frame\'s size: "frame": [width, height].')
    if not isinstance(corners, list) or len(corners) != 4:
        raise ValueError('Give the card\'s four corners: "corners": [[x, y], ...].')
    if not all(_numbers(corner, 2) for corner in corners):
        raise ValueError("Each corner is [x, y].")
    width, height = frame
    return tuple((x / width, y / height) for x, y in corners)


def _numbers(value: Any, count: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == count
        and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
    )


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
    sightings: Sightings | None = None,
    spot: card.CardSpot | None = None,
) -> ThreadingHTTPServer:
    """Serve the control on a background thread. Port 0 picks a free one. With
    sightings, it also takes /card reports, and with a spot, /card-spot."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self._route() == "state":
                state = status()
                if sightings is not None:
                    seen = sightings.seen()
                    state["card"] = "reading" if seen else "waiting"
                    if seen:
                        state["card_corners"] = [[round(v, 4) for v in c] for c in seen]
                if spot is not None and spot.box is not None:
                    state["card_spot"] = [round(v, 4) for v in spot.box]
                self._reply(200, state)
            else:
                self._reply(404, {"error": HELP})

        def do_POST(self) -> None:
            body = self._body()
            name = self._route()
            if name == "card-spot" and spot is not None:
                self._set_spot(body)
                return
            if name == "card" and sightings is not None:
                try:
                    sightings.report(parse_card(body))
                except ValueError as error:
                    self._reply(400, {"error": str(error)})
                    return
                self._reply(200, {"ok": name})
                return
            if name not in COMMANDS:
                self._reply(404, {"error": HELP})
                return
            commands.put(name)
            self._reply(200, {"ok": name})

        def _set_spot(self, body: bytes) -> None:
            """Move the outline: to the box sent, or around the card seen now."""
            try:
                asked = json.loads(body) if body.strip() else {}
                if not isinstance(asked, dict):
                    raise ValueError('Send {} or {"box": [left, top, width, height]}.')
                if "box" in asked:
                    box = card.checked(asked["box"])
                else:
                    seen = sightings.seen() if sightings is not None else None
                    if not seen:
                        self._reply(409, {"error": NO_CARD})
                        return
                    box = card.box_around(seen)
            except (ValueError, TypeError) as error:
                self._reply(400, {"error": str(error)})
                return
            spot.set(box)  # type: ignore[union-attr]
            self._reply(200, {"ok": "card-spot", "box": [round(v, 4) for v in box]})

        def _route(self) -> str:
            return urlsplit(self.path).path.strip("/")

        def _body(self) -> bytes:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            return self.rfile.read(min(length, MAX_BODY)) if length > 0 else b""

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
