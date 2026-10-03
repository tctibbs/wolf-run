"""Stage two: Wolf Run itself. The rules only; game_scene.py draws it.

Grandma runs off as the game starts and hides in the straw hut, then the stick
house, then the brick house. Each house is a level and a checkpoint: reach it and
the wolf huffs and puffs it down, and Grandma runs on to the next one. The brick
house won't fall, so he goes down the chimney instead, and that's the end of her.

The game moves in fixed steps, 30 a second, so it plays the same on a Mac and on
a Pi 3. Every step can return sounds for the screen to play.
"""

import random
from dataclasses import dataclass, field
from enum import Enum

from wolf_run import sprites
from wolf_run.clock import GROUND_Y, STANDING_SHIFT, WOLF_X, W
from wolf_run.pixels import Grid

STEPS_PER_SECOND = 30
START_X = WOLF_X + STANDING_SHIFT  # where he stood on the primed clock
RUN_X = 40
HOUSE_STOPS_AT = 150

# Hold the button to jump higher, like the dinosaur game. A tap is a hop.
JUMP_SPEED = -4.0
GRAVITY = 0.36
HOLD_GRAVITY = 0.16
MAX_HOLD_STEPS = 12
CRASH_PAUSE = 15  # steps before a press can try again, so mashing doesn't skip it

OBSTACLES: dict[str, Grid] = {
    "straw": sprites.STRAW,
    "sticks": sprites.STICKS,
    "bricks": sprites.BRICKS,
}


@dataclass(frozen=True)
class Level:
    name: str
    house: Grid
    seconds: float
    speeds: tuple[float, float]
    gaps: tuple[float, float]
    doubles: float  # chance an obstacle comes with a second one right behind it


# Each house is noticeably faster than the last, with obstacles closer together and
# more of them in pairs, so the timing gets tighter as the night goes on.
LEVELS = (
    Level("STRAW HUT", sprites.STRAW_HUT_BIG, 24, (2.4, 2.8), (120, 180), 0.0),
    Level("STICK HOUSE", sprites.STICK_HOUSE_BIG, 26, (3.0, 3.4), (95, 150), 0.2),
    Level("BRICK HOUSE", sprites.BRICK_HOUSE_BIG, 28, (3.6, 4.0), (75, 125), 0.35),
)


class Phase(Enum):
    INTRO = "intro"  # Grandma spots him and runs for it
    RUN = "run"
    CRASH = "crash"
    ARRIVE = "arrive"  # the house rolls into view
    HUFF = "huff"
    PUFF = "puff"
    COLLAPSE = "collapse"  # straw and sticks fly apart
    FLEE = "flee"  # Grandma runs on to the next house
    FAIL = "fail"  # the bricks don't budge
    CLIMB = "climb"  # up onto the roof and down the chimney
    RUMMAGE = "rummage"  # turning the place upside down looking for her
    INSIDE = "inside"  # found her
    EXIT = "exit"  # out the door, fat, in her nightcap
    GLITCH = "glitch"
    STATIC = "static"
    DONE = "done"


# How many steps each scripted part lasts.
LENGTHS = {
    Phase.INTRO: 60,
    Phase.HUFF: 30,
    Phase.PUFF: 36,
    Phase.COLLAPSE: 36,
    Phase.FLEE: 50,
    Phase.FAIL: 45,
    Phase.CLIMB: 40,
    Phase.RUMMAGE: 90,
    Phase.INSIDE: 60,
    Phase.EXIT: 110,
    Phase.GLITCH: 30,
    Phase.STATIC: 22,
}
INTRO_NOTICE = 10  # Grandma's "!" before she runs
GRANNY_START_X = 88  # between the straw hut and the stick house on the clock
FLEE_NOTICE = 12
GRANNY_SPEED = 3.5
CLIMB_ARC = 28  # steps up onto the chimney; the rest is the drop
EXIT_WALK = 45  # far enough to be clear of the big house
RUMMAGE_FOUND = 72  # steps into the rummage when he finds her: "AHA!"
CAMERA_WARMUP = {
    Phase.CLIMB,
    Phase.RUMMAGE,
    Phase.INSIDE,
    Phase.EXIT,
    Phase.GLITCH,
    Phase.STATIC,
    Phase.DONE,
}


@dataclass
class Obstacle:
    kind: str
    x: float

    @property
    def grid(self) -> Grid:
        return OBSTACLES[self.kind]

    @property
    def width(self) -> int:
        return len(self.grid[0])


@dataclass
class Game:
    rng: random.Random = field(default_factory=random.Random)
    demo: bool = False
    phase: Phase = Phase.INTRO
    level: int = 0
    steps: int = 0
    phase_steps: int = 0
    progress: float = 0.0
    tries: int = 1
    obstacles: list[Obstacle] = field(default_factory=list)
    wolf_x: float = START_X
    wolf_y: float = 0.0
    vy: float = 0.0
    holding: bool = False
    hold_steps: int = 0
    house_x: float = W + 4
    granny_x: float = GRANNY_START_X
    scroll: float = 0.0
    gap: float = 220.0
    banner_steps: int = 0

    @property
    def current(self) -> Level:
        return LEVELS[self.level]

    @property
    def speed(self) -> float:
        slow, fast = self.current.speeds
        return slow + (fast - slow) * self.progress

    @property
    def house_width(self) -> int:
        return len(self.current.house[0])

    @property
    def on_ground(self) -> bool:
        return self.wolf_y == 0 and self.vy == 0

    @property
    def last_level(self) -> bool:
        return self.level == len(LEVELS) - 1

    @property
    def finished(self) -> bool:
        return self.phase is Phase.DONE

    @property
    def wants_camera(self) -> bool:
        """Start connecting to the camera once he's on the roof, so the cut is
        instant."""
        return self.phase in CAMERA_WARMUP

    def press(self) -> list[str]:
        """The button went down: jump, or try the level again after a crash."""
        self.holding = True
        if self.phase is Phase.RUN and self.on_ground:
            self.vy = JUMP_SPEED
            self.hold_steps = 0
            return ["jump"]
        if self.phase is Phase.CRASH and self.phase_steps > CRASH_PAUSE:
            self.tries += 1
            self._start_level(self.level, retry=True)
        return []

    def release(self) -> None:
        """The button came up: a short press is a short hop."""
        self.holding = False

    def skip_to_ending(self) -> None:
        """For the host: straight to the brick house."""
        if self.phase in (Phase.INTRO, Phase.RUN, Phase.CRASH):
            self._start_level(len(LEVELS) - 1)
            self.progress = 1.0
            self.banner_steps = 0

    def step(self) -> list[str]:
        """Advance one step (1/30 of a second) and return any sounds."""
        self.steps += 1
        self.phase_steps += 1
        self.banner_steps = max(0, self.banner_steps - 1)
        handler = {
            Phase.INTRO: self._intro,
            Phase.RUN: self._run,
            Phase.ARRIVE: self._arrive,
        }.get(self.phase, self._scripted)
        return handler()

    def _enter(self, phase: Phase) -> None:
        self.phase, self.phase_steps = phase, 0

    def _start_level(self, level: int, retry: bool = False) -> None:
        self.level = level
        self.progress = 0.0
        self.obstacles.clear()
        self.wolf_y = self.vy = 0.0
        self.house_x = W + 4
        self.gap = 160.0
        self.banner_steps = 0 if retry else 60
        self._enter(Phase.RUN)

    def _scroll(self) -> None:
        self.scroll += self.speed
        for obstacle in self.obstacles:
            obstacle.x -= self.speed
        self.obstacles = [o for o in self.obstacles if o.x > -24]
        self.wolf_x = min(RUN_X, self.wolf_x + 1)

    def _intro(self) -> list[str]:
        sounds = ["alert"] if self.phase_steps == 1 else []
        if self.phase_steps > INTRO_NOTICE:
            self.granny_x += GRANNY_SPEED
            self._scroll()
        if self.phase_steps >= LENGTHS[Phase.INTRO]:
            self._start_level(0)
        return sounds

    def _run(self) -> list[str]:
        self._scroll()
        self._fall()
        level = self.current
        self.progress = min(1.0, self.progress + 1 / (STEPS_PER_SECOND * level.seconds))
        self._spawn(level)
        sounds = self._autopilot() if self.demo else []
        if self._hit():
            self._enter(Phase.CRASH)
            return [*sounds, "crash"]
        if self.progress >= 1 and not self.obstacles and self.on_ground:
            self._enter(Phase.ARRIVE)
        return sounds

    def _fall(self) -> None:
        if self.on_ground:
            return
        self.wolf_y += self.vy
        floaty = self.holding and self.vy < 0 and self.hold_steps < MAX_HOLD_STEPS
        self.vy += HOLD_GRAVITY if floaty else GRAVITY
        self.hold_steps += 1
        if self.wolf_y >= 0:
            self.wolf_y = self.vy = 0.0

    def _spawn(self, level: Level) -> None:
        self.gap -= self.speed
        if self.gap > 0 or self.progress >= 0.95:
            return
        first = Obstacle(self.rng.choice(list(OBSTACLES)), W + 4)
        self.obstacles.append(first)
        last = first
        if self.rng.random() < level.doubles:
            last = Obstacle(self.rng.choice(list(OBSTACLES)), 0)
            last.x = first.x + first.width + 12 + self.rng.random() * 8
            self.obstacles.append(last)
        # Measure the gap from the end of a pair, so landing a long jump over one
        # never drops you straight onto the next obstacle.
        low, high = level.gaps
        pair_length = last.x - first.x
        self.gap = low + self.rng.random() * (high - low) + self.speed * 8 + pair_length

    def _autopilot(self) -> list[str]:
        """Plays itself for demos: jumps in time, and holds for a pair."""
        ahead = [o for o in self.obstacles if o.x + o.width > self.wolf_x + 6]
        if self.on_ground and ahead:
            gap = ahead[0].x - (self.wolf_x + 26)
            if gap < 2 + self.speed * 3:
                pair = len(ahead) > 1 and ahead[1].x - ahead[0].x < 40
                sounds = self.press()
                if not pair:
                    self.release()
                return sounds
        if not self.on_ground and self.hold_steps >= MAX_HOLD_STEPS:
            self.release()
        return []

    def _hit(self) -> bool:
        left, right = self.wolf_x + 7, self.wolf_x + 25
        feet = GROUND_Y - 1 + self.wolf_y
        for obstacle in self.obstacles:
            o_left, o_right = obstacle.x + 2, obstacle.x + obstacle.width - 2
            o_top = GROUND_Y - len(obstacle.grid) + 2
            if right > o_left and left < o_right and feet > o_top:
                return True
        return False

    def _arrive(self) -> list[str]:
        self._scroll()
        self.house_x -= self.speed
        if self.house_x <= HOUSE_STOPS_AT:
            self.house_x = HOUSE_STOPS_AT
            self._enter(Phase.HUFF)
            return ["huff"]
        return []

    def _scripted(self) -> list[str]:
        """The huffing, puffing, and eating: timed, with no input needed."""
        p, phase = self.phase_steps, self.phase
        sounds: list[str] = []
        if phase is Phase.CLIMB:
            self._climb(p)
        elif phase is Phase.RUMMAGE:
            if p < RUMMAGE_FOUND and p % 15 == 5:
                sounds.append("clatter")
            elif p == RUMMAGE_FOUND:
                sounds.append("aha")
        elif phase is Phase.INSIDE and p % 12 == 1:
            sounds.append("chomp")
        elif phase is Phase.EXIT:
            if p <= EXIT_WALK:
                self.wolf_x += 1
            if p == EXIT_WALK + 5:
                sounds.append("burp")
            if EXIT_WALK + 20 < p < EXIT_WALK + 50 and p % 8 == 0:
                sounds.append("lick")
        elif phase is Phase.FLEE and p > FLEE_NOTICE:
            self.granny_x += GRANNY_SPEED
        if phase not in LENGTHS or p < LENGTHS[phase]:
            return sounds
        return [*sounds, *self._next_scene()]

    def _next_scene(self) -> list[str]:
        phase = self.phase
        if phase is Phase.HUFF:
            self._enter(Phase.PUFF)
            return ["puff"]
        if phase is Phase.PUFF:
            self._enter(Phase.FAIL if self.last_level else Phase.COLLAPSE)
            return ["sad" if self.last_level else "crumble"]
        if phase is Phase.COLLAPSE:
            self.granny_x = self.house_x + self.house_width / 2 - 8
            self._enter(Phase.FLEE)
            return ["alert"]
        if phase is Phase.FLEE:
            self._start_level(self.level + 1)
            return []
        if phase is Phase.FAIL:
            self._enter(Phase.CLIMB)
            return ["climb"]
        if phase is Phase.CLIMB:
            self._enter(Phase.RUMMAGE)
            return []
        if phase is Phase.RUMMAGE:
            self._enter(Phase.INSIDE)
            return []
        if phase is Phase.INSIDE:
            self.wolf_x, self.wolf_y = self.house_x + self.house_width / 2 - 16, 0.0
            self._enter(Phase.EXIT)
            return []
        if phase is Phase.EXIT:
            self._enter(Phase.GLITCH)
            return ["static"]
        if phase is Phase.GLITCH:
            self._enter(Phase.STATIC)
            return []
        self._enter(Phase.DONE)
        return []

    def _climb(self, p: int) -> None:
        """An arc from where he stands to the top of the chimney, then down it."""
        start_x = RUN_X
        chimney_x = self.house_x + sprites.chimney_center(self.current.house) - 16
        chimney_top = -(len(self.current.house) - 1)
        if p <= CLIMB_ARC:
            t = p / CLIMB_ARC
            self.wolf_x = start_x + (chimney_x - start_x) * t
            self.wolf_y = chimney_top * t - 40 * t * (1 - t)
        else:
            self.wolf_y += 2.5
