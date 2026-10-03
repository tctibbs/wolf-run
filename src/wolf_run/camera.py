"""Reading the basement camera's stream."""

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2

OPEN_TIMEOUT_MS = 10000
READ_TIMEOUT_MS = 8000

# TCP so frames don't tear on Wi-Fi, video only because the screen has no use for
# the camera's audio, and a short probe. Together these took the first frame from
# about 5 seconds to about 3 on the Reolink E1 Zoom.
FFMPEG_OPTIONS = "|".join(
    [
        "rtsp_transport;tcp",
        "allowed_media_types;video",
        "analyzeduration;500000",
        "probesize;65536",
    ]
)


class Capture(Protocol):
    """The slice of cv2.VideoCapture this module uses."""

    def isOpened(self) -> bool: ...  # noqa: N802 - OpenCV's name

    def read(self) -> tuple[bool, Any]: ...

    def get(self, prop_id: int) -> float: ...

    def release(self) -> None: ...


class StreamError(Exception):
    """The camera couldn't be reached, or it sent no picture."""


@dataclass(frozen=True)
class StreamCheck:
    """What one frame from the camera told us about the stream."""

    width: int
    height: int
    fps: float
    seconds_to_first_frame: float
    frame: Any


def open_capture(url: str) -> Capture:
    """Open an RTSP stream, giving up after a few seconds."""
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", FFMPEG_OPTIONS)
    return cv2.VideoCapture(
        url,
        cv2.CAP_FFMPEG,
        [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            OPEN_TIMEOUT_MS,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            READ_TIMEOUT_MS,
        ],
    )


def check_stream(
    url: str,
    open_fn: Callable[[str], Capture] = open_capture,
    clock: Callable[[], float] = time.monotonic,
) -> StreamCheck:
    """Connect, grab one frame, and report on it."""
    start = clock()
    capture = open_fn(url)
    try:
        if not capture.isOpened():
            raise StreamError("Couldn't open the stream.")
        ok, frame = capture.read()
        if not ok or frame is None:
            raise StreamError("Connected, but no picture arrived.")
        height, width = frame.shape[:2]
        return StreamCheck(
            width=width,
            height=height,
            fps=capture.get(cv2.CAP_PROP_FPS),
            seconds_to_first_frame=clock() - start,
            frame=frame,
        )
    finally:
        capture.release()


def save_snapshot(frame: Any, path: Path) -> Path:
    """Write a frame to disk as an image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), frame):
        raise OSError(f"Couldn't save a snapshot to {path}.")
    return path


class CameraFeed:
    """Keeps the newest frame from the camera, reconnecting in the background.

    Started when the wolf heads for the chimney, so the picture is ready by the
    time the static clears.
    """

    def __init__(
        self,
        url: str,
        open_fn: Callable[[str], Capture] = open_capture,
        retry_seconds: float = 2.0,
    ) -> None:
        self._url, self._open, self._retry = url, open_fn, retry_seconds
        self._frame: Any = None
        self._live = False
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def live(self) -> bool:
        return self._live

    def latest(self) -> Any:
        """The newest frame, or None if nothing has arrived yet."""
        with self._lock:
            return self._frame

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=OPEN_TIMEOUT_MS / 1000 + 1)
            self._thread = None

    def _run(self) -> None:
        while not self._stopping.is_set():
            capture = self._open(self._url)
            try:
                while not self._stopping.is_set() and capture.isOpened():
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        break
                    with self._lock:
                        self._frame, self._live = frame, True
            finally:
                capture.release()
                self._live = False
            self._stopping.wait(self._retry)
