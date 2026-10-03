"""Which stage the screen is on, and when it got there.

Times are seconds of animation, the same `t` every scene is drawn with, so a
stage always knows how long it has been showing.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from wolf_run import clock
from wolf_run.pixels import Canvas


class Stage(Enum):
    CLOCK = "clock"
    PRIMED = "primed"


@dataclass
class Screen:
    stage: Stage = Stage.CLOCK
    since: float = 0.0

    def prime(self, t: float) -> bool:
        """Wake the wolf. Only the sleeping clock can be primed."""
        if self.stage is not Stage.CLOCK:
            return False
        self.stage, self.since = Stage.PRIMED, t
        return True

    def reset(self, t: float) -> None:
        """Back to the sleeping clock, for the host or for testing."""
        self.stage, self.since = Stage.CLOCK, t

    def draw(self, canvas: Canvas, now: datetime, t: float) -> None:
        primed_at = self.since if self.stage is Stage.PRIMED else None
        clock.draw_clock(canvas, now, t, primed_at)
