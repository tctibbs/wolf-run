"""Which stage the screen is on, and when it got there.

Clock (wolf asleep) -> primed (wolf up, "press any button") -> the game -> the
basement camera. Times are seconds of animation, the same `t` every scene is
drawn with, so a stage always knows how long it has been showing.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from wolf_run import camera_scene, clock, game_scene
from wolf_run.game import STEPS_PER_SECOND, Game
from wolf_run.pixels import Canvas

MAX_CATCH_UP = 10  # steps; after a long stall, skip ahead rather than fast-forward


class Stage(Enum):
    CLOCK = "clock"
    PRIMED = "primed"
    GAME = "game"
    CAMERA = "camera"


@dataclass
class Screen:
    stage: Stage = Stage.CLOCK
    since: float = 0.0
    game: Game | None = None
    seed: int | None = None
    demo: bool = False
    _clock: float = field(default=0.0, repr=False)

    def prime(self, t: float) -> bool:
        """Wake the wolf. Only the sleeping clock can be primed."""
        if self.stage is not Stage.CLOCK:
            return False
        self._enter(Stage.PRIMED, t)
        return True

    def press(self, t: float) -> list[str]:
        """Any button went down. Starts the game once primed; jumps after that."""
        if self.stage is Stage.PRIMED:
            self._start_game(t)
            return []
        if self.stage is Stage.GAME and self.game:
            return self.game.press()
        return []

    def release(self, t: float) -> None:
        if self.stage is Stage.GAME and self.game:
            self.game.release()

    def skip_to_ending(self, t: float) -> None:
        """For the host: straight to the brick house."""
        if self.stage in (Stage.CLOCK, Stage.PRIMED):
            self._start_game(t)
        if self.game:
            self.game.skip_to_ending()

    def reset(self, t: float) -> None:
        """Back to the sleeping clock, for the host or for testing."""
        self.game = None
        self._enter(Stage.CLOCK, t)

    def update(self, t: float) -> list[str]:
        """Run the game forward to time `t`, and return the sounds it made."""
        if self.stage is not Stage.GAME or not self.game:
            return []
        due = int((t - self._clock) * STEPS_PER_SECOND + 1e-6)  # float slop
        self._clock = t if due > MAX_CATCH_UP else self._clock + due / STEPS_PER_SECOND
        sounds: list[str] = []
        for _ in range(min(due, MAX_CATCH_UP)):
            sounds += self.game.step()
            if self.game.finished:
                self._enter(Stage.CAMERA, t)
                break
        return sounds

    @property
    def wants_camera(self) -> bool:
        if self.stage is Stage.CAMERA:
            return True
        return self.stage is Stage.GAME and bool(self.game and self.game.wants_camera)

    def draw(self, canvas: Canvas, now: datetime, t: float) -> None:
        if self.stage is Stage.GAME and self.game:
            game_scene.draw_game(canvas, self.game, now, t)
        elif self.stage is Stage.CAMERA:
            camera_scene.draw_camera_osd(canvas, now, t, live=False)
        else:
            primed_at = self.since if self.stage is Stage.PRIMED else None
            clock.draw_clock(canvas, now, t, primed_at)

    def _start_game(self, t: float) -> None:
        self.game = Game(rng=random.Random(self.seed), demo=self.demo)
        self._clock = t
        self._enter(Stage.GAME, t)

    def _enter(self, stage: Stage, t: float) -> None:
        self.stage, self.since = stage, t
