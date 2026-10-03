"""Stage one: a Halloween clock that minds its own business.

The clock shares the game's ground line, so the game can start from this exact
picture: the wolf in the bush on the left, the pigs' houses along the ground.
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime

from wolf_run import sprites
from wolf_run.palette import NIGHT, Palette
from wolf_run.pixels import Canvas, disc, paint, text, text_width

W, H = 256, 150
GROUND_Y = 120
DIGIT_SCALE = 6
DIGIT_TOP = 24
DATE_Y = 96

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

BUSH_X = 4
EYES = ((9, 4), (13, 4))
SCENERY = [
    (sprites.STRAW_HUT, 66),
    (sprites.STICK_HOUSE, 116),
    (sprites.BRICK_HOUSE, 166),
    (sprites.TOMBSTONE, 230),
]
PUMPKIN_X = 188

EYES_CYCLE, EYES_FROM, EYES_UNTIL = 20.0, 2.0, 9.0
BLINKS = ((4.6, 4.75), (7.2, 7.35))
BAT_CYCLE, BAT_FLIGHT = 24.0, 10.0
DRIP_CYCLE = 7.0


@dataclass(frozen=True)
class Bat:
    x: int
    y: int
    wings_up: bool


def time_parts(now: datetime) -> tuple[str, str]:
    """'9:47' and 'PM', the way a clock on the wall would say it."""
    hour = now.hour % 12 or 12
    return f"{hour}:{now.minute:02d}", "AM" if now.hour < 12 else "PM"


def date_line(now: datetime) -> str:
    return f"{now:%A %B} {now.day}".upper()


def colon_visible(t: float) -> bool:
    return t % 1 < 0.5


def eyes_open(t: float) -> bool:
    """The wolf peeks out of the bush for a few seconds every cycle, and blinks."""
    p = t % EYES_CYCLE
    if not EYES_FROM <= p < EYES_UNTIL:
        return False
    return not any(start <= p < end for start, end in BLINKS)


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
    return 1, int((p - 0.75) / 0.25 * 18)


def draw_clock(
    canvas: Canvas, now: datetime, t: float, palette: Palette = NIGHT
) -> None:
    """Draw one frame of the clock at time `now`, `t` seconds into the animation."""
    canvas.fill(0, 0, W, H, palette.bg)
    _sky(canvas, t, palette)
    _time(canvas, now, t, palette)
    line = date_line(now)
    text(canvas, line, (W - text_width(line)) // 2, DATE_Y, palette.dim)
    _ground(canvas, t, palette)


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
    canvas: Canvas, glyph: list[str], x: int, t: float, index: int, palette: Palette
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
    for grid, x in SCENERY:
        paint(canvas, grid, x, GROUND_Y - len(grid), palette.ink, palette.bg)
    flicker = palette.glow if int(t * 7) % 5 else palette.dim
    pumpkin = sprites.PUMPKIN
    paint(canvas, pumpkin, PUMPKIN_X, GROUND_Y - len(pumpkin), palette.ink, flicker)
    bush = sprites.BUSH
    bush_y = GROUND_Y - len(bush)
    paint(canvas, bush, BUSH_X, bush_y, palette.soft, palette.soft)
    if eyes_open(t):
        for ex, ey in EYES:
            canvas.fill(BUSH_X + ex, bush_y + ey, 2, 1, palette.glow)
