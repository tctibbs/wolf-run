"""The pigs' houses: the clock builds each of its houses while that house's pig is home.

PIG_HOUSES_URL in .env points at whatever knows where the pigs are (for the party,
an ESP32 with an NFC reader under each of three little houses). The screen asks its
GET /state every half second: a "houses" list, left to right, each with the "pig"
sitting on it and the "owner" it belongs to. The straw, stick, and brick house, from
the left, go up from the ground while their own pig sits on them, and come back down
when it's lifted off. Once all three stand, the wolf wakes. Without PIG_HOUSES_URL
every house stays up, as it always was.
"""

import http.client
import json
import threading
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

HOUSES = 3
ALL_UP = (True,) * HOUSES
POLL_SECONDS = 0.5
TIMEOUT_SECONDS = 2.0
BUILD_SECONDS = 0.8  # from the ground to the roof, or back down

Fetch = Callable[[str], bytes]


def pigs_home(state: object) -> tuple[bool, ...]:
    """Which houses have their own pig on them, left to right. Raises ValueError
    for an answer that isn't three houses."""
    houses = state.get("houses") if isinstance(state, dict) else None
    if not isinstance(houses, list) or len(houses) != HOUSES:
        raise ValueError("Expected a list of three houses.")
    return tuple(
        isinstance(house, dict)
        and isinstance(house.get("pig"), str)
        and house["pig"] == house.get("owner")
        for house in houses
    )


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


class PigWatch:
    """Asks the pig houses who's home, on a background thread. A missed answer
    keeps the last good one, so a dropped request never knocks a house down."""

    def __init__(self, url: str, fetch: Fetch = _get) -> None:
        self.url = url.rstrip("/") + "/state"
        self._fetch = fetch
        self._lock = threading.Lock()
        self._home: tuple[bool, ...] = (False,) * HOUSES
        self._stop = threading.Event()

    def home(self) -> tuple[bool, ...]:
        """The latest word: whether each house has its own pig, left to right."""
        with self._lock:
            return self._home

    def check(self) -> bool:
        """Ask once; False if there was no good answer."""
        try:
            home = pigs_home(json.loads(self._fetch(self.url)))
        except (OSError, ValueError, http.client.HTTPException):
            return False
        with self._lock:
            self._home = home
        return True

    def start(self) -> None:
        threading.Thread(target=self._run, name="pigs", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.check()
            self._stop.wait(POLL_SECONDS)


def watch_from_env(env_path: Path = Path(".env")) -> PigWatch | None:
    """A watch on PIG_HOUSES_URL, or None when it isn't set."""
    from wolf_run import config

    url = config.read_env(env_path).get("PIG_HOUSES_URL", "").strip()
    return PigWatch(url) if url else None


@dataclass
class Building:
    """Which houses are up, and when each last started going up or coming down,
    in seconds of animation. Every house starts down."""

    up: list[bool] = field(default_factory=lambda: [False] * HOUSES)
    changed: list[float] = field(default_factory=lambda: [-BUILD_SECONDS] * HOUSES)

    def follow(self, home: Sequence[bool], t: float) -> None:
        """Start building a house whose pig just came home, and take down one whose
        pig just left. A house caught halfway turns around where it is."""
        for i, now in enumerate(home):
            if bool(now) == self.up[i]:
                continue
            done = self.height(i, t)
            self.up[i] = bool(now)
            self.changed[i] = t - (done if now else 1 - done) * BUILD_SECONDS

    def all_standing(self, t: float) -> bool:
        """Every house up and finished."""
        return all(self.height(i, t) >= 1 for i in range(HOUSES))

    def height(self, i: int, t: float) -> float:
        """How much of house `i` stands, from 0 (a bare plot) to 1 (all of it)."""
        progress = min(1.0, max(0.0, (t - self.changed[i]) / BUILD_SECONDS))
        return progress if self.up[i] else 1 - progress
