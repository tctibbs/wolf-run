"""The wolf-run command."""

import argparse
import os
import queue
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from wolf_run import camera, config, control
from wolf_run.stages import Screen, Stage

CAMERA_HINT = "Check CAMERA_HOST, the login, and that RTSP is on in the Reolink app."
CONTROL_ENV = "WOLF_RUN_CONTROL_PORT"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wolf-run", description="A Halloween party screen for a Raspberry Pi."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    screen = commands.add_parser("screen", help="show the party screen")
    screen.add_argument(
        "--windowed",
        action="store_true",
        help="use a 1024x600 window instead of full screen",
    )
    screen.add_argument(
        "--primed",
        action="store_true",
        help="start with the wolf awake, waiting for a button (or WOLF_RUN_PRIMED=1)",
    )
    screen.add_argument(
        "--control",
        type=port_number,
        metavar="PORT",
        help=(
            "take commands from other computers on the network on this port "
            f"(or {CONTROL_ENV}; default: 0, off)"
        ),
    )

    shot = commands.add_parser("screenshot", help="save one frame of the screen")
    shot.add_argument(
        "--at",
        type=datetime.fromisoformat,
        help="pretend it's this time, like '2026-10-31 21:47' (default: now)",
    )
    shot.add_argument(
        "--seconds",
        type=float,
        default=4.0,
        help="how far into the animation (default: %(default)s)",
    )
    shot.add_argument(
        "--primed",
        type=float,
        metavar="SECONDS",
        help="show it primed, this many seconds ago (default: wolf asleep)",
    )
    shot.add_argument(
        "--out",
        type=Path,
        default=Path("snapshots/screen.png"),
        help="where to save it (default: %(default)s)",
    )

    check = commands.add_parser(
        "camera-check", help="grab one frame from the camera to prove the stream works"
    )
    check.add_argument(
        "--stream", choices=sorted(config.STREAM_PATHS), help="override CAMERA_STREAM"
    )
    check.add_argument(
        "--snapshot",
        type=Path,
        default=Path("snapshots/camera-check.jpg"),
        help="where to save the frame (default: %(default)s)",
    )
    check.add_argument(
        "--env",
        type=Path,
        default=Path(".env"),
        help="the .env file to read (default: %(default)s)",
    )
    args = parser.parse_args(argv)
    if args.command == "screen":
        primed = args.primed or os.environ.get("WOLF_RUN_PRIMED") == "1"
        try:
            port = control_port(args.control)
        except argparse.ArgumentTypeError as error:
            print(error, file=sys.stderr)
            return 1
        return show_screen(args.windowed, primed, port)
    if args.command == "screenshot":
        when = args.at or datetime.now()
        return screenshot(when, args.seconds, args.out, args.primed)
    return camera_check(args.env, args.stream, args.snapshot)


def port_number(text: str) -> int:
    """A port from the command line or the environment, where 0 means off."""
    try:
        port = int(text)
    except ValueError:
        port = -1
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"{text!r} isn't a port number (0 to 65535).")
    return port


def control_port(flag: int | None) -> int:
    """The network control's port: --control, then WOLF_RUN_CONTROL_PORT, then off."""
    if flag is not None:
        return flag
    value = os.environ.get(CONTROL_ENV, "").strip()
    try:
        return port_number(value) if value else 0
    except argparse.ArgumentTypeError as error:
        raise argparse.ArgumentTypeError(f"{CONTROL_ENV}: {error}") from None


def show_screen(windowed: bool, primed: bool = False, port: int = 0) -> int:
    """Show the screen, listening for the network control if given a port."""
    from wolf_run import ui  # Qt only loads for the commands that need it

    if not port:
        return ui.run(windowed, primed)
    commands: queue.Queue[str] = queue.Queue()
    status: dict[str, Any] = {"stage": (Stage.PRIMED if primed else Stage.CLOCK).value}
    try:
        server = control.start(port, commands, lambda: dict(status))
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Taking commands at http://{control.lan_address()}:{server.server_port}")
    try:
        return ui.run(windowed, primed, commands=commands, status=status)
    finally:
        server.shutdown()
        server.server_close()


def screenshot(
    now: datetime, seconds: float, out: Path, primed: float | None = None
) -> int:
    from wolf_run import ui

    screen = Screen()
    if primed is not None:
        screen.prime(seconds - primed)
    try:
        saved = ui.save_snapshot(out, now, seconds, screen.draw)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Saved {saved}")
    return 0


def camera_check(env_path: Path, stream: str | None, snapshot: Path) -> int:
    try:
        settings = config.camera_settings(config.read_env(env_path))
    except config.ConfigError as error:
        print(error, file=sys.stderr)
        return 1
    if stream:
        settings = replace(settings, stream=stream)

    print(f"Connecting to {settings.redacted_url()}")
    try:
        result = camera.check_stream(settings.rtsp_url())
    except camera.StreamError as error:
        print(f"{error} {CAMERA_HINT}", file=sys.stderr)
        return 1
    try:
        saved = camera.save_snapshot(result.frame, snapshot)
    except OSError as error:
        print(error, file=sys.stderr)
        return 1

    print(
        f"Got a {result.width}x{result.height} picture "
        f"after {result.seconds_to_first_frame:.1f}s{_fps(result.fps)}."
    )
    print(f"Saved it to {saved}")
    return 0


def _fps(fps: float) -> str:
    """OpenCV sometimes reports nonsense frame rates for RTSP; only show sane ones."""
    return f" at {fps:.0f} fps" if 0 < fps <= 120 else ""


if __name__ == "__main__":
    sys.exit(main())
