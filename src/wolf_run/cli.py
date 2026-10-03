"""The wolf-run command."""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from wolf_run import camera, config

CAMERA_HINT = "Check CAMERA_HOST, the login, and that RTSP is on in the Reolink app."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wolf-run", description="A Halloween party screen for a Raspberry Pi."
    )
    commands = parser.add_subparsers(dest="command", required=True)
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
    return camera_check(args.env, args.stream, args.snapshot)


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
