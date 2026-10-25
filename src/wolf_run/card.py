"""Where guests hold the card up: the outline on the camera view, and setting it.

The outline starts from CARD_OUTLINE in .env. The host can move it by holding the
card where guests should and asking (POST /card-spot): the outline goes around the
card where the camera sees it right then, a little bigger than the card, and is
remembered next to the screen's place (memory.py), so a restart keeps it.

Boxes are left, top, width, height, as fractions of the camera picture.
"""

import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from wolf_run import config, memory

Box = tuple[float, float, float, float]
FILE = "card-spot.json"
MARGIN = 0.15  # the outline's breathing room around the card, as a share of its size


class CardSpot:
    """The outline's box, shared between the network control and the window."""

    def __init__(self, box: Box | None = None, path: Path | None = None) -> None:
        self._box = box
        self._path = path
        self._lock = threading.Lock()

    @property
    def box(self) -> Box | None:
        with self._lock:
            return self._box

    def set(self, box: Box) -> bool:
        """Move the outline, and remember it. False if it couldn't be saved."""
        with self._lock:
            self._box = box
        if self._path is None:
            return True
        return memory.save(self._path, {"box": list(box)})


def box_around(corners: Sequence[tuple[float, float]], margin: float = MARGIN) -> Box:
    """A box around the card's corners, with some room, kept inside the picture."""
    xs, ys = [x for x, _ in corners], [y for _, y in corners]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    left = max(0.0, min(xs) - width * margin)
    top = max(0.0, min(ys) - height * margin)
    right = min(1.0, max(xs) + width * margin)
    bottom = min(1.0, max(ys) + height * margin)
    return left, top, right - left, bottom - top


def checked(box: Sequence[float]) -> Box:
    """A box from a request or a file, if it fits in the picture. Else ValueError."""
    if len(box) != 4 or not all(
        isinstance(v, int | float) and not isinstance(v, bool) for v in box
    ):
        raise ValueError("A box is [left, top, width, height].")
    left, top, width, height = (float(v) for v in box)
    if not (left >= 0 and top >= 0 and width > 0 and height > 0):
        raise ValueError("A box is fractions of the camera picture, inside it.")
    if left + width > 1 or top + height > 1:
        raise ValueError("A box is fractions of the camera picture, inside it.")
    return left, top, width, height


def spot_from_env(env_path: Path = Path(".env")) -> CardSpot:
    """The outline the host last set, else CARD_OUTLINE from .env, else none."""
    place = memory.path_from_env()
    path = place.with_name(FILE) if place is not None else None
    if path is not None:
        saved = memory.load(path).get("box")
        try:
            return CardSpot(checked(saved), path)
        except (TypeError, ValueError):
            pass
    try:
        start = config.card_outline(config.read_env(env_path))
    except config.ConfigError as error:
        print(f"No card outline: {error}", file=sys.stderr)
        start = None
    return CardSpot(start, path)
