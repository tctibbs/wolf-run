"""Render the README's GIFs and cast sheet from the real game code.

    uv run python scripts/make_readme_media.py

Every frame is drawn offscreen by the same scenes the screen uses, then stitched
into GIFs with ffmpeg (which needs to be installed). There's no camera footage:
the clips stop at the static, because the basement is somebody's real basement.
"""

import random
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage

from wolf_run import clock, sprites, ui
from wolf_run.game import Phase
from wolf_run.palette import NIGHT
from wolf_run.pixels import Grid, disc, paint, text, text_width
from wolf_run.stages import Screen, Stage

OUT = Path(__file__).resolve().parent.parent / "docs" / "images"
NOW = datetime(2026, 10, 31, 21, 47)
FPS = 15
STEP = 1 / 30
SCALE = 3


def wake_up() -> Iterator[QImage]:
    """Asleep for a few seconds, then primed: up he gets."""
    screen = Screen()
    for frame in range(FPS * 9):
        t = frame / FPS
        if t >= 3.5:
            screen.prime(3.5)
        yield ui.render(screen.draw, NOW, t)


def _game_at(level: int, progress: float, seed: int) -> tuple[Screen, float]:
    screen = Screen(seed=seed, demo=True)
    screen.prime(0.0)
    screen.press(0.0)
    assert screen.game is not None
    screen.game._start_level(level)
    screen.game.progress = progress
    screen.game.banner_steps = 0
    screen.game.scroll = 1000.0  # well past the clock's village
    return screen, 0.0


def _play(screen: Screen, t: float, seconds: float) -> Iterator[QImage]:
    for step in range(round(seconds / STEP)):
        t += STEP
        screen.update(t)
        if step % 2 == 0:
            yield ui.render(screen.draw, NOW, t)


def _has_a_pair_jump(seed: int, level: int, seconds: float) -> bool:
    screen, t = _game_at(level, 0.3, seed)
    held = False
    for _ in range(round(seconds / STEP)):
        t += STEP
        screen.update(t)
        game = screen.game
        held |= bool(game and not game.on_ground and game.holding)
        if not game or game.phase is Phase.CRASH:
            return False
    return held


def run() -> Iterator[QImage]:
    """A stretch of the brick level, picked so it shows a held jump over a pair."""
    seed = next(s for s in range(200) if _has_a_pair_jump(s, 2, 6))
    screen, t = _game_at(2, 0.3, seed)
    yield from _play(screen, t, 6)


def huff_and_puff() -> Iterator[QImage]:
    """The end of the straw level: huff, puff, the hut flies apart, she runs."""
    screen, t = _game_at(0, 1.0, 1)
    yield from _play(screen, t, 9)


def brick_house() -> Iterator[QImage]:
    """The bricks won't fall, so down the chimney he goes. Ends on a flash of
    static: random noise doesn't compress, so a long burst makes a huge GIF."""
    screen, t = _game_at(2, 1.0, 1)
    while screen.stage is Stage.GAME:
        t += STEP
        screen.update(t)
        if screen.game and screen.game.phase is Phase.HUFF:
            break
    static = 0.0
    while static < 0.5:
        t += STEP
        screen.update(t)
        game = screen.game
        if screen.stage is Stage.CAMERA or (game and game.phase is Phase.STATIC):
            static += STEP
        if round(t / STEP) % 2 == 0:
            yield ui.render(screen.draw, NOW, t)


def cast() -> QImage:
    """Every character and prop, drawn straight from sprites.py."""
    width, height = clock.W, 150
    image = QImage(width, height, QImage.Format_RGB32)
    canvas = ui.ImageCanvas(image)
    canvas.fill(0, 0, width, height, NIGHT.bg)
    rows: list[tuple[str, int, list[tuple[Grid, str]]]] = [
        (
            "THE WOLF",
            38,
            [
                (sprites.WOLF_SLEEP_A, NIGHT.bg),
                (sprites.WOLF_B, NIGHT.bg),
                (sprites.WOLF_A, NIGHT.bg),
                (sprites.WOLF_JUMP, NIGHT.bg),
                (sprites.WOLF_BLOW, NIGHT.bg),
                (sprites.WOLF_FAT, NIGHT.bg),
            ],
        ),
        (
            "GRANDMA AND THE THINGS IN HIS WAY",
            80,
            [
                (sprites.GRANNY, NIGHT.bg),
                (sprites.GRANNY_RUN_A, NIGHT.bg),
                (sprites.STRAW, NIGHT.bg),
                (sprites.STICKS, NIGHT.bg),
                (sprites.BRICKS, NIGHT.bg),
                (sprites.PAN, NIGHT.bg),
                (sprites.BOOK, NIGHT.bg),
                (sprites.SOCK, NIGHT.bg),
                (sprites.BONE, NIGHT.bg),
            ],
        ),
        (
            "THE THREE LITTLE PIGS' HOUSES",
            142,
            [
                (sprites.STRAW_HUT_BIG, NIGHT.glow),
                (sprites.STICK_HOUSE_BIG, NIGHT.glow),
                (sprites.BRICK_HOUSE_BIG, NIGHT.glow),
                (sprites.PUMPKIN, NIGHT.glow),
                (sprites.TOMBSTONE, NIGHT.bg),
            ],
        ),
    ]
    for title, baseline, pieces in rows:
        text(
            canvas,
            title,
            6,
            baseline - 34 if baseline < 100 else baseline - 52,
            NIGHT.dim,
        )
        x = 6
        for grid, holes in pieces:
            paint(canvas, grid, x, baseline - len(grid), NIGHT.ink, holes)
            x += len(grid[0]) + 6
    canvas.finish()
    return image


def social_preview() -> QImage:
    """The 1280x640 card GitHub shows when someone shares the repo's link."""
    width, height, ground = 320, 160, 136
    image = QImage(width, height, QImage.Format_RGB32)
    canvas = ui.ImageCanvas(image)
    canvas.fill(0, 0, width, height, NIGHT.bg)
    title, scale = "WOLF RUN", 4
    title_w = text_width(title, scale, sprites.BIG_FONT)
    title_x, title_y = (width - title_w) // 2 - 16, 22
    rng = random.Random(31)
    for _ in range(40):
        x, y = rng.randrange(width), rng.randrange(ground - 50)
        if (
            title_x - 6 <= x <= title_x + title_w + 6
            and title_y - 6 <= y <= title_y + 34
        ):
            continue
        canvas.fill(x, y, 1, 1, NIGHT.dim)
    disc(canvas, 284, 32, 14, NIGHT.ink)
    for dx, dy, w, h in ((-6, -5, 4, 3), (3, 4, 5, 4), (5, -7, 2, 2), (-5, 6, 2, 2)):
        canvas.fill(284 + dx, 32 + dy, w, h, NIGHT.dim)
    text(canvas, title, title_x, title_y, NIGHT.ink, scale, sprites.BIG_FONT)
    canvas.fill(0, ground, width, 1, NIGHT.ink)
    house = sprites.BRICK_HOUSE_BIG
    paint(canvas, house, 250, ground - len(house), NIGHT.ink, NIGHT.glow)
    paint(
        canvas,
        sprites.PUMPKIN,
        14,
        ground - len(sprites.PUMPKIN),
        NIGHT.ink,
        NIGHT.glow,
    )
    granny = sprites.GRANNY_RUN_A
    paint(canvas, granny, 212, ground - len(granny), NIGHT.ink, NIGHT.bg)
    paint(canvas, sprites.STRAW, 120, ground - len(sprites.STRAW), NIGHT.ink, NIGHT.bg)
    paint(canvas, sprites.WOLF_JUMP, 100, ground - 22 - 24, NIGHT.ink, NIGHT.bg)
    canvas.finish()
    return image


def save_gif(name: str, frames: Iterator[QImage]) -> Path:
    path = OUT / f"{name}.gif"
    with tempfile.TemporaryDirectory() as folder:
        count = 0
        for count, frame in enumerate(frames, start=1):
            big = frame.scaled(
                frame.width() * SCALE,
                frame.height() * SCALE,
                Qt.IgnoreAspectRatio,
                Qt.FastTransformation,
            )
            big.save(str(Path(folder) / f"{count:05d}.png"))
        palette = (
            "split[a][b];[a]palettegen=max_colors=32[p];[b][p]paletteuse=dither=none"
        )
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(Path(folder) / "%05d.png"),
                "-vf",
                palette,
                "-loop",
                "0",
                str(path),
            ],
            check=True,
        )
    print(f"{path.name}: {count} frames, {path.stat().st_size // 1024} KB")
    return path


def main() -> int:
    if shutil.which("ffmpeg") is None:
        print("This needs ffmpeg on your PATH (brew install ffmpeg).", file=sys.stderr)
        return 1
    ui.ensure_app(offscreen=True)
    OUT.mkdir(parents=True, exist_ok=True)
    save_gif("wake-up", wake_up())
    save_gif("run", run())
    save_gif("huff-and-puff", huff_and_puff())
    save_gif("brick-house", brick_house())
    sheet = cast()
    sheet.scaled(
        sheet.width() * SCALE,
        sheet.height() * SCALE,
        Qt.IgnoreAspectRatio,
        Qt.FastTransformation,
    ).save(str(OUT / "cast.png"))
    print("cast.png")
    card = social_preview()
    card.scaled(1280, 640, Qt.IgnoreAspectRatio, Qt.FastTransformation).save(
        str(OUT / "social-preview.png")
    )
    print("social-preview.png (upload it under Settings > General > Social preview)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
