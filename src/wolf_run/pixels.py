"""Drawing pixel art onto anything that can fill a rectangle.

Everything here works in logical pixels on a 256x150 screen. The window scales that
up 4x to fill the 1024x600 panel, which is what keeps the pixels chunky.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Protocol

from wolf_run.sprites import FONT

Grid = Sequence[str]


class Canvas(Protocol):
    """Anything that can fill a rectangle, or fill one with grey static."""

    def fill(self, x: int, y: int, w: int, h: int, color: str) -> None: ...

    def noise(
        self, x: int, y: int, w: int, h: int, seed: int, lo: int = 0, hi: int = 255
    ) -> None: ...


def paint(
    canvas: Canvas,
    grid: Grid,
    x: int,
    y: int,
    ink: str,
    hole: str,
    scale: int = 1,
) -> None:
    """Draw a sprite: '#' in ink, 'o' in the hole colour, '.' left alone."""
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch == ".":
                continue
            color = hole if ch == "o" else ink
            canvas.fill(x + c * scale, y + r * scale, scale, scale, color)


def text_width(
    text: str, scale: int = 1, font: Mapping[str, Grid] = FONT, gap: int = 1
) -> int:
    """How wide a line of text is, in logical pixels."""
    if not text:
        return 0
    columns = sum(len(font[ch][0]) + gap for ch in text) - gap
    return columns * scale


def text(
    canvas: Canvas,
    line: str,
    x: int,
    y: int,
    color: str,
    scale: int = 1,
    font: Mapping[str, Grid] = FONT,
    gap: int = 1,
) -> int:
    """Draw a line of text and return where it ended."""
    for ch in line:
        glyph = font[ch]
        paint(canvas, glyph, x, y, color, color, scale)
        x += (len(glyph[0]) + gap) * scale
    return x - gap * scale


def text_runs(
    canvas: Canvas,
    runs: Sequence[tuple[str, str]],
    x: int,
    y: int,
    scale: int = 1,
    font: Mapping[str, Grid] = FONT,
    gap: int = 1,
) -> int:
    """Draw one line made of differently coloured pieces, spaced as if it were one
    string. Each run is (text, colour)."""
    for piece, color in runs:
        x = text(canvas, piece, x, y, color, scale, font, gap) + gap * scale
    return x - gap * scale


def disc(canvas: Canvas, cx: int, cy: int, r: int, color: str) -> None:
    """A filled circle, drawn one row at a time."""
    for dy in range(-r, r + 1):
        half = math.isqrt(r * r - dy * dy)
        canvas.fill(cx - half, cy + dy, 2 * half + 1, 1, color)
