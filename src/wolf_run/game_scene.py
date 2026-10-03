"""Drawing Wolf Run, one frame at a time.

The run starts from the primed clock: the time slides up out of the way and the
clock's little village scrolls off to the left as the wolf gets going.
"""

import random
from datetime import datetime
from functools import cache

from wolf_run import clock, sprites
from wolf_run.game import (
    CLIMB_ARC,
    EXIT_WALK,
    FLEE_NOTICE,
    INTRO_NOTICE,
    LENGTHS,
    LEVELS,
    RUMMAGE_FOUND,
    Game,
    Phase,
)
from wolf_run.palette import NIGHT, Palette
from wolf_run.pixels import Canvas, Grid, paint, text, text_runs, text_width

W, H, GROUND_Y = clock.W, clock.H, clock.GROUND_Y
SLIDE_STEPS = 18
TRY_AGAIN = ("PRESS ANY ", "BUTTON", " TO TRY AGAIN")
DEBRIS_TILE = 4
HOUSE_PHASES = {
    Phase.ARRIVE,
    Phase.HUFF,
    Phase.PUFF,
    Phase.FAIL,
    Phase.CLIMB,
    Phase.RUMMAGE,
    Phase.INSIDE,
    Phase.EXIT,
    Phase.GLITCH,
}
AFTER_RUMMAGE = {Phase.INSIDE, Phase.EXIT, Phase.GLITCH}
# What he throws out of the chimney: (sprite, when, sideways speed, upward speed).
JUNK = (
    (sprites.PAN, 6, -1.1, -3.4),
    (sprites.BOOK, 21, 1.0, -3.0),
    (sprites.SOCK, 36, -0.6, -3.8),
    (sprites.BONE, 51, 1.3, -2.8),
)
JUNK_GRAVITY = 0.22
RUMMAGE_WORDS = ("CLATTER!", "BANG!", "CRASH!")


def draw_game(
    canvas: Canvas, game: Game, now: datetime, t: float, palette: Palette = NIGHT
) -> None:
    if game.phase in (Phase.STATIC, Phase.DONE):
        canvas.noise(0, 0, W, H, seed=game.steps)
        return
    canvas.fill(0, 0, W, H, palette.bg)
    clock.draw_sky(canvas, t, palette, with_bats=False)
    if game.steps < SLIDE_STEPS:
        lift = round(80 * game.steps / SLIDE_STEPS)
        clock.draw_time(canvas, now, t, palette, top=clock.DIGIT_TOP - lift)
    clock.draw_ground(canvas, palette, scroll=game.scroll)
    clock.draw_scenery(canvas, t, palette, scroll=game.scroll)
    for obstacle in game.obstacles:
        grid = obstacle.grid
        paint(
            canvas,
            grid,
            round(obstacle.x),
            GROUND_Y - len(grid),
            palette.ink,
            palette.bg,
        )
    if game.phase is Phase.CLIMB and game.phase_steps > CLIMB_ARC:
        _wolf(canvas, game, palette)  # dropping down the chimney, behind the house
        _house(canvas, game, palette)
    else:
        _house(canvas, game, palette)
        _wolf(canvas, game, palette)
    _junk(canvas, game, palette)
    _granny(canvas, game, palette)
    _words(canvas, game, palette)
    running = game.phase in (Phase.RUN, Phase.CRASH, Phase.ARRIVE)
    if running and game.steps >= SLIDE_STEPS:
        _hud(canvas, game, palette)
    if game.phase is Phase.GLITCH:
        _glitch(canvas, game)


def _house(canvas: Canvas, game: Game, palette: Palette) -> None:
    house = game.current.house
    x, top = round(game.house_x), GROUND_Y - len(house)
    if game.phase is Phase.COLLAPSE:
        for tile, tx, ty in debris(game.level, game.house_x, game.phase_steps):
            paint(canvas, tile, tx, ty, palette.ink, palette.glow)
        return
    if game.phase not in HOUSE_PHASES:
        return
    windows = palette.glow
    p = game.phase_steps
    if game.phase is Phase.RUMMAGE and p < RUMMAGE_FOUND:
        x += 1 if (p // 3) % 4 == 1 else 0  # a rattle now and then
        windows = palette.bg if (p // 7) % 3 == 1 else palette.glow  # his shadow
    elif game.phase is Phase.INSIDE:
        x += 1 if p % 4 < 2 else -1  # shaking with every chomp
        windows = palette.glow if p % 6 < 3 else palette.dim
    paint(canvas, house, x, top, palette.ink, windows)


@cache
def _tiles(level: int) -> tuple[tuple[Grid, int, int, float, float], ...]:
    """Cut a house into small squares, each with its own way of flying off."""
    house = LEVELS[level].house
    rng = random.Random(level)
    tiles = []
    for row in range(0, len(house), DEBRIS_TILE):
        for col in range(0, len(house[0]), DEBRIS_TILE):
            tile = [
                line[col : col + DEBRIS_TILE] for line in house[row : row + DEBRIS_TILE]
            ]
            if any(ch != "." for line in tile for ch in line):
                vx = 1.0 + rng.random() * 2.5 + col / 20
                vy = -(0.5 + rng.random() * 3.0)
                tiles.append((tuple(tile), col, row, vx, vy))
    return tuple(tiles)


def debris(level: int, house_x: float, steps: int) -> list[tuple[Grid, int, int]]:
    """Where every piece of a blown-down house is, `steps` after the puff."""
    top = GROUND_Y - len(LEVELS[level].house)
    pieces = []
    for tile, col, row, vx, vy in _tiles(level):
        x = house_x + col + vx * steps
        y = top + row + vy * steps + 0.125 * steps * steps
        if x < W and y < H:
            pieces.append((tile, round(x), round(y)))
    return pieces


def junk(house: Grid, house_x: float, steps: int) -> list[tuple[Grid, int, int]]:
    """Everything thrown out of the chimney so far: in the air, or on the ground
    beside the house where it landed."""
    cx = house_x + sprites.chimney_center(list(house))
    cy = GROUND_Y - len(house)
    thrown = []
    for grid, when, vx, vy in JUNK:
        if steps < when:
            continue
        x, y, dx, dy = cx - len(grid[0]) / 2, float(cy - len(grid)), vx, vy
        floor = GROUND_Y - len(grid)
        for _ in range(steps - when):
            x, dy = x + dx, dy + JUNK_GRAVITY
            y += dy
            if y >= floor:
                y, dx, dy = floor, 0.0, 0.0
        thrown.append((grid, round(x), round(y)))
    return thrown


def _junk(canvas: Canvas, game: Game, palette: Palette) -> None:
    if not game.last_level:
        return
    if game.phase is Phase.RUMMAGE:
        steps = game.phase_steps
        _soot(canvas, game, palette)
    elif game.phase in AFTER_RUMMAGE:
        steps = LENGTHS[Phase.RUMMAGE]
    else:
        return
    for grid, x, y in junk(game.current.house, game.house_x, steps):
        paint(canvas, grid, x, y, palette.ink, palette.bg)


def _soot(canvas: Canvas, game: Game, palette: Palette) -> None:
    """Puffs of soot from the chimney while he tears the place apart."""
    p = game.phase_steps
    if p >= RUMMAGE_FOUND:
        return
    house = game.current.house
    cx = round(game.house_x + sprites.chimney_center(list(house)))
    cy = GROUND_Y - len(house)
    for j in range(3):
        q = (p + j * 7) % 21
        size = 2 + q // 7
        canvas.fill(cx - 1 + (j - 1) * 2 + q // 4, cy - 3 - q, size, size, palette.soft)


def wolf_frame(game: Game) -> Grid:
    phase = game.phase
    if phase in (Phase.RUN, Phase.ARRIVE) or (
        phase is Phase.INTRO and game.phase_steps > INTRO_NOTICE
    ):
        if game.wolf_y < 0:
            return sprites.WOLF_JUMP
        return sprites.WOLF_A if (game.steps // 4) % 2 else sprites.WOLF_B
    if phase is Phase.CRASH:
        return sprites.WOLF_OPEN
    if phase is Phase.HUFF:
        return sprites.WOLF_CHOMP  # cheeks full of air
    if phase is Phase.PUFF:
        return sprites.WOLF_BLOW
    if phase is Phase.CLIMB:
        return sprites.WOLF_JUMP
    if phase in (Phase.EXIT, Phase.GLITCH):
        return sprites.WOLF_FAT
    return sprites.WOLF_B


def _wolf(canvas: Canvas, game: Game, palette: Palette) -> None:
    if game.phase in (Phase.RUMMAGE, Phase.INSIDE):
        return
    grid = wolf_frame(game)
    x = round(game.wolf_x)
    top = GROUND_Y - len(grid) + round(game.wolf_y)
    if game.phase is Phase.HUFF:
        top -= 1 if game.phase_steps % 10 < 5 else 0  # chest heaving
    if game.phase is Phase.CLIMB and game.phase_steps > CLIMB_ARC:
        chimney_top = GROUND_Y - len(game.current.house)
        visible = max(0, chimney_top - top)
        grid = grid[:visible]  # disappearing into the chimney
    paint(canvas, grid, x, top, palette.ink, palette.bg)
    if game.phase is Phase.PUFF:
        _wind(canvas, game, x + 32, top + 6, palette)
    licking = (
        game.phase is Phase.EXIT and EXIT_WALK + 20 < game.phase_steps < EXIT_WALK + 52
    )
    if licking and (game.phase_steps // 4) % 2 == 0:
        paint(canvas, sprites.TONGUE, x + 30, top + 8, palette.ink, palette.bg)


def _wind(
    canvas: Canvas, game: Game, mouth_x: int, mouth_y: int, palette: Palette
) -> None:
    """Gusts streaming from his mouth to the house."""
    span = max(8, round(game.house_x) - mouth_x)
    for i in range(7):
        x = mouth_x + (game.phase_steps * 5 + i * 17) % span
        y = mouth_y + (i % 4) * 3 - 3
        canvas.fill(x, y, 6, 1, palette.dim)


def _granny(canvas: Canvas, game: Game, palette: Palette) -> None:
    p = game.phase_steps
    if game.phase is Phase.INTRO:
        noticed = p <= INTRO_NOTICE
    elif game.phase is Phase.FLEE:
        noticed = p <= FLEE_NOTICE
    else:
        return
    x = round(game.granny_x)
    if x >= W:
        return
    if noticed:
        grid = sprites.mirror(sprites.GRANNY)
        text(canvas, "!", x + 7, GROUND_Y - 38, palette.glow, 2)
    else:
        grid = sprites.GRANNY_RUN_A if (game.steps // 3) % 2 else sprites.GRANNY_RUN_B
    paint(canvas, grid, x, GROUND_Y - len(grid), palette.ink, palette.bg)


def banner(game: Game) -> str:
    """What the screen shouts as a level starts. The wolf doesn't know which house
    she'll run to next, so neither does the banner."""
    return "CATCH GRANDMA!" if game.level == 0 else "AFTER HER!"


def _words(canvas: Canvas, game: Game, palette: Palette) -> None:
    """The story beats, spelled out big."""
    p, phase = game.phase_steps, game.phase
    if phase is Phase.CRASH:
        _centered(canvas, "OUCH!", 40, 3, palette.ink)
        if p > 15 and (p // 15) % 2 == 0:
            before, red, after = TRY_AGAIN
            x = (W - text_width(before + red + after)) // 2
            runs = [(before, palette.ink), (red, palette.red), (after, palette.ink)]
            text_runs(canvas, runs, x, 66)
    elif phase is Phase.RUN and game.banner_steps:
        target = LEVELS[game.level].name
        line = (
            "CATCH GRANDMA!"
            if game.level == 0 and game.tries == 1
            else f"TO THE {target}"
        )
        _centered(canvas, line, 44, 2, palette.ink)
    elif phase is Phase.HUFF:
        _centered(canvas, "I'LL HUFF...", 44, 2, palette.ink)
    elif phase is Phase.PUFF:
        _centered(canvas, "AND PUFF!", 44, 2, palette.ink)
    elif phase is Phase.FAIL:
        line = "..." if p < 25 else "HMM."
        _centered(canvas, line, 44, 2, palette.ink)
    elif phase is Phase.CLIMB:
        _centered(canvas, "THE CHIMNEY!", 44, 2, palette.ink)
    elif phase is Phase.RUMMAGE:
        middle = round(game.house_x + game.house_width / 2)
        roof = GROUND_Y - len(game.current.house)
        if p >= RUMMAGE_FOUND:
            text(
                canvas,
                "AHA!",
                middle - text_width("AHA!", 3) // 2,
                roof - 24,
                palette.ink,
                3,
            )
        elif p % 15 < 10:
            word = RUMMAGE_WORDS[(p // 15) % len(RUMMAGE_WORDS)]
            dx = -46 if (p // 15) % 2 else 6
            text(canvas, word, middle + dx, roof - 16, palette.ink, 2)
    elif phase is Phase.INSIDE and (p // 12) % 2 == 0:
        middle = round(game.house_x + game.house_width / 2)
        roof = GROUND_Y - len(game.current.house)
        dx = -40 if (p // 24) % 2 else -4
        text(canvas, "CHOMP!", middle + dx, roof - 16, palette.ink, 2)
    elif phase is Phase.EXIT and EXIT_WALK + 5 <= p < EXIT_WALK + 45:
        text(
            canvas,
            "BURP!",
            round(game.wolf_x) + 2,
            GROUND_Y - 46 - (p - 40) // 4,
            palette.ink,
            2,
        )


def _hud(canvas: Canvas, game: Game, palette: Palette) -> None:
    """Progress to the next house on the left; houses done and tries on the right."""
    for x in range(12, 130, 3):
        canvas.fill(x, 9, 1, 1, palette.soft)
    paint(canvas, sprites.SPRITES["grannyHead"], 132, 4, palette.ink, palette.bg)
    wolf_head = sprites.SPRITES["wolfHead"]
    paint(canvas, wolf_head, 4 + round(game.progress * 112), 4, palette.ink, palette.bg)
    for i in range(len(LEVELS)):
        x = 158 + i * 8
        if i < game.level:
            canvas.fill(x, 6, 5, 5, palette.ink)
        else:
            for side in ((x, 6, 5, 1), (x, 10, 5, 1), (x, 6, 1, 5), (x + 4, 6, 1, 5)):
                canvas.fill(*side, palette.dim)
    text(canvas, f"TRY {game.tries}", 184, 6, palette.dim)


def _centered(canvas: Canvas, line: str, y: int, scale: int, color: str) -> None:
    text(canvas, line, (W - text_width(line, scale)) // 2, y, color, scale)


def _glitch(canvas: Canvas, game: Game) -> None:
    """Bands of static that thicken until the picture gives out."""
    rng = random.Random(game.steps)
    for _ in range(2 + game.phase_steps // 3):
        y = rng.randrange(H)
        h = 1 + rng.randrange(6)
        canvas.noise(0, y, W, h, seed=rng.randrange(1 << 16))
