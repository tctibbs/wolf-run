"""Stage one: a Halloween clock, with the wolf asleep in the corner.

When the screen is primed, the wolf wakes up, gets to his feet, and a prompt
blinks under the time. The clock shares the game's ground line, so the game can
start from this exact picture.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime

from wolf_run import sprites
from wolf_run.palette import NIGHT, Palette
from wolf_run.pixels import Canvas, Grid, disc, paint, text, text_width

W, H = 256, 150
GROUND_Y = 120
DIGIT_SCALE = 6
DIGIT_TOP = 24
DATE_Y = 88
PROMPT = "PRESS ANY BUTTON TO RUN"
PROMPT_SCALE = 2

# Stars stay out of the box around the time and date, so they never read as digits.
CLEAR = (44, 18, 214, 104)


def _scatter_stars(count: int, seed: int = 31) -> list[tuple[int, int, int]]:
    """The same sky every time: seeded, so stars don't jump around between runs."""
    rng = random.Random(seed)
    left, top, right, bottom = CLEAR
    stars: list[tuple[int, int, int]] = []
    while len(stars) < count:
        x, y = rng.randrange(2, W - 2), rng.randrange(3, 88)
        if not (left <= x <= right and top <= y <= bottom):
            stars.append((x, y, len(stars) % 3))
    return stars


STARS = _scatter_stars(26)
SPECKS = [((i * 61 + 13) % W, i % 3) for i in range(18)]
MOON = (228, 24, 12)

WOLF_X = 4
HEAD_X = 35  # where his head sits in the lying sprite, for the Zs and the start
STANDING_SHIFT = 12  # stands up where he lay, instead of jumping backwards
HOUSES = [
    (sprites.STRAW_HUT, 58),
    (sprites.STICK_HOUSE, 104),
    (sprites.BRICK_HOUSE, 152),
]
TOMBSTONE_X = 232
PUMPKIN_X = 196

BREATH = 3.0
SNORE_CYCLE = 3.6
WAKE_UP = 0.9
ON_HIS_FEET = 1.3
WAG = 0.2
BAT_CYCLE, BAT_FLIGHT = 24.0, 10.0
DRIP_CYCLE = 7.0


@dataclass(frozen=True)
class Bat:
    x: int
    y: int
    wings_up: bool


@dataclass(frozen=True)
class Pose:
    """How to draw the wolf in his corner right now."""

    grid: Grid
    lift: int = 0
    startled: bool = False
    shift: int = 0


@dataclass(frozen=True)
class Snore:
    x: int
    y: int
    scale: int


def time_parts(now: datetime) -> tuple[str, str]:
    """'9:47' and 'PM', the way a clock on the wall would say it."""
    hour = now.hour % 12 or 12
    return f"{hour}:{now.minute:02d}", "AM" if now.hour < 12 else "PM"


def date_line(now: datetime) -> str:
    return f"{now:%A %B} {now.day}".upper()


def colon_visible(t: float) -> bool:
    return t % 1 < 0.5


def wolf_pose(t: float, primed_at: float | None) -> Pose:
    """Asleep until primed; then a start, a hop to his feet, and a wagging tail."""
    if primed_at is None:
        breathing_in = t % BREATH < BREATH / 2
        return Pose(sprites.WOLF_SLEEP_B if breathing_in else sprites.WOLF_SLEEP_A)
    since = t - primed_at
    if since < WAKE_UP:
        return Pose(sprites.WOLF_STARTLED, startled=True)
    if since < ON_HIS_FEET:
        return Pose(sprites.WOLF_B, lift=3, shift=STANDING_SHIFT)
    wagging = int((since - ON_HIS_FEET) / WAG) % 2
    grid = sprites.WOLF_WAG if wagging else sprites.WOLF_B
    return Pose(grid, shift=STANDING_SHIFT)


def snores(t: float) -> list[Snore]:
    """Three Zs drifting up from his head, growing as they rise."""
    head_x, head_y = WOLF_X + HEAD_X, GROUND_Y - len(sprites.WOLF_SLEEP_A)
    rising = []
    for i in range(3):
        p = (t / SNORE_CYCLE + i / 3) % 1
        rising.append(
            Snore(
                x=round(head_x + 2 + p * 12),
                y=round(head_y - 8 - p * 26),
                scale=1 if p < 0.5 else 2,
            )
        )
    return rising


def prompt_visible(t: float, primed_at: float | None) -> bool:
    """Blinks once he's on his feet, like the dinosaur game's start screen."""
    if primed_at is None:
        return False
    since = t - primed_at
    return since >= ON_HIS_FEET and (since - ON_HIS_FEET) % 1 < 0.65


def bats(t: float) -> list[Bat]:
    """Two bats cross the sky together every so often."""
    flying = []
    for i, delay in enumerate((0.0, 1.3)):
        p = (t - delay) % BAT_CYCLE
        if p >= BAT_FLIGHT:
            continue
        x = round(W + 14 - (W + 30) * p / BAT_FLIGHT)
        y = round(4 + i * 7 + 3 * math.sin(p * 2.5 + i))
        flying.append(Bat(x, y, wings_up=int(p * 6) % 2 == 0))
    return flying


def drip(t: float, index: int) -> tuple[int, int | None]:
    """How long a digit's drip is, and how far its drop has fallen (if it has)."""
    p = (t / DRIP_CYCLE + index * 0.29) % 1
    if p < 0.75:
        return 1 + int(p / 0.75 * 7), None
    return 1, int((p - 0.75) / 0.25 * 10)


def draw_clock(
    canvas: Canvas,
    now: datetime,
    t: float,
    primed_at: float | None = None,
    palette: Palette = NIGHT,
) -> None:
    """Draw one frame: `now` is the wall time, `t` the seconds of animation so far.

    `primed_at` is the animation time the screen was primed, or None while the
    wolf is still asleep.
    """
    canvas.fill(0, 0, W, H, palette.bg)
    _sky(canvas, t, palette)
    _time(canvas, now, t, palette)
    if primed_at is None:
        line = date_line(now)
        text(canvas, line, (W - text_width(line)) // 2, DATE_Y, palette.dim)
    elif prompt_visible(t, primed_at):
        x = (W - text_width(PROMPT, PROMPT_SCALE)) // 2
        text(canvas, PROMPT, x, DATE_Y - 2, palette.ink, PROMPT_SCALE)
    _ground(canvas, t, palette)
    _wolf(canvas, t, primed_at, palette)


def _sky(canvas: Canvas, t: float, palette: Palette) -> None:
    for x, y, kind in STARS:
        if (int(t * 4) + kind) % 7 == 0:
            continue
        canvas.fill(x, y, 1, 1, palette.dim)
        if kind == 0:
            canvas.fill(x - 1, y, 3, 1, palette.dim)
            canvas.fill(x, y - 1, 1, 3, palette.dim)
    mx, my, r = MOON
    disc(canvas, mx, my, r, palette.ink)
    for dx, dy, cw, ch in ((-5, -4, 3, 3), (2, 3, 4, 3), (4, -6, 2, 2), (-4, 5, 2, 2)):
        canvas.fill(mx + dx, my + dy, cw, ch, palette.dim)
    for bat in bats(t):
        grid = sprites.BAT_UP if bat.wings_up else sprites.BAT_DOWN
        paint(canvas, grid, bat.x, bat.y, palette.ink, palette.bg)


def _time(canvas: Canvas, now: datetime, t: float, palette: Palette) -> None:
    hhmm, meridiem = time_parts(now)
    font, scale = sprites.BIG_FONT, DIGIT_SCALE
    width = text_width(hhmm, scale, font)
    tag_width = text_width(meridiem, 2)
    x = (W - (width + 4 + tag_width)) // 2
    digit = 0
    for ch in hhmm:
        glyph = font[ch]
        if ch != ":" or colon_visible(t):
            paint(canvas, glyph, x, DIGIT_TOP, palette.ink, palette.ink, scale)
        if ch != ":":
            _drip(canvas, glyph, x, t, digit, palette)
            digit += 1
        x += (len(glyph[0]) + 1) * scale
    bottom = DIGIT_TOP + 7 * scale
    text(canvas, meridiem, x - scale + 4, bottom - 10, palette.dim, 2)


def _drip(
    canvas: Canvas, glyph: Grid, x: int, t: float, index: int, palette: Palette
) -> None:
    """Hang a drip off the first inked pixel on the digit's bottom row."""
    column = glyph[-1].index("#")
    dx = x + column * DIGIT_SCALE + DIGIT_SCALE // 2 - 1
    top = DIGIT_TOP + 7 * DIGIT_SCALE
    length, fallen = drip(t, index)
    canvas.fill(dx, top, 2, length, palette.ink)
    if fallen is not None:
        canvas.fill(dx, top + 4 + fallen, 2, 2, palette.ink)


def _ground(canvas: Canvas, t: float, palette: Palette) -> None:
    canvas.fill(0, GROUND_Y, W, 1, palette.ink)
    for x, kind in SPECKS:
        if kind == 0:
            canvas.fill(x, GROUND_Y - 1, 3, 1, palette.ink)
        else:
            canvas.fill(x, GROUND_Y + 3 + kind * 3, 3 - kind, 1, palette.soft)
    for grid, x in HOUSES:
        paint(canvas, grid, x, GROUND_Y - len(grid), palette.ink, palette.glow)
    tomb = sprites.TOMBSTONE
    paint(canvas, tomb, TOMBSTONE_X, GROUND_Y - len(tomb), palette.ink, palette.bg)
    flicker = palette.glow if int(t * 7) % 5 else palette.dim
    pumpkin = sprites.PUMPKIN
    paint(canvas, pumpkin, PUMPKIN_X, GROUND_Y - len(pumpkin), palette.ink, flicker)


def _wolf(canvas: Canvas, t: float, primed_at: float | None, palette: Palette) -> None:
    pose = wolf_pose(t, primed_at)
    top = GROUND_Y - len(pose.grid) - pose.lift
    paint(canvas, pose.grid, WOLF_X + pose.shift, top, palette.ink, palette.bg)
    if pose.startled:
        text(canvas, "!", WOLF_X + HEAD_X - 2, top - 14, palette.glow, 2)
    if primed_at is None:
        for z in snores(t):
            text(canvas, "Z", z.x, z.y, palette.dim, z.scale)
