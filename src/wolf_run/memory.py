"""Where the screen is, kept on disk so a power cut doesn't undo the night.

The window writes the screen's place whenever it changes: the stage, and the house
reached while playing. Starting up, the screen picks up from there (see
Screen.restore). Each write goes to a spare file that's then swapped in, so a cut
mid-write leaves the last good place, and a file that can't be read just means the
clock.

The file lives at ~/.local/state/wolf-run/place.json, or wherever WOLF_RUN_STATE
says. WOLF_RUN_STATE=off starts at the clock every time and remembers nothing.
"""

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ENV = "WOLF_RUN_STATE"
DEFAULT = Path("~/.local/state/wolf-run/place.json")
OFF = "off"


def path_from_env(environ: Mapping[str, str] = os.environ) -> Path | None:
    """Where to keep the place, or None when remembering is off."""
    value = environ.get(ENV, "").strip()
    if value.lower() == OFF:
        return None
    return Path(value or DEFAULT).expanduser()


def load(path: Path) -> dict[str, Any]:
    """The remembered place, or {} when there's none to read."""
    try:
        place = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return place if isinstance(place, dict) else {}


def save(path: Path, place: Mapping[str, Any]) -> bool:
    """Write the place whole, then swap it in. A full or read-only card returns
    False instead of stopping the screen."""
    spare = path.with_name(path.name + ".part")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with spare.open("w") as file:
            json.dump(dict(place), file)
            file.flush()
            os.fsync(file.fileno())
        os.replace(spare, path)
    except OSError:
        return False
    return True
