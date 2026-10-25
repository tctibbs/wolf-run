"""Stage three's on-screen display: the security-camera look over the live feed.

With a live picture the overlay is drawn on a transparent layer and keeps out of
the way: just a blinking REC. Without one (still connecting, or the stream
dropped) it draws static and NO SIGNAL instead.

It can also show guests where to hold up a card for the camera: a dashed outline
with HOLD HIS CARD HERE above it. While the card reads (something watching the camera
says so on the control port), the outline turns candle orange, says LIGHT UP THE
ROOM, and traces the card where the camera sees it.
"""

from dataclasses import dataclass
from datetime import datetime

from wolf_run.clock import H, W
from wolf_run.palette import NIGHT
from wolf_run.pixels import Canvas, text, text_width

OSD = "#e6e6e6"
REC = NIGHT.red
FOUND = NIGHT.glow
HOLD_IT = "HOLD HIS CARD HERE"
READ_IT = "LIGHT UP THE ROOM"
BRACKET = 7  # the corner brackets' arms, in canvas pixels
DASH, GAP = 3, 3

Box = tuple[float, float, float, float]  # x, y, width, height
Point = tuple[float, float]


@dataclass(frozen=True)
class CardView:
    """Where the card goes on the canvas, and where the camera sees it, if it does."""

    outline: Box | None = None
    seen: tuple[Point, ...] | None = None  # its four corners, while it reads


def picture_box(screen_w: int, screen_h: int, picture_w: int, picture_h: int) -> Box:
    """Where the camera picture sits on the 256x150 canvas, when both are fitted to
    a screen_w x screen_h window the way the window fits them: the canvas at a whole
    scale, the picture at any scale, each centred."""
    canvas_scale = max(1, int(min(screen_w / W, screen_h / H)))
    canvas_x = (screen_w - W * canvas_scale) // 2
    canvas_y = (screen_h - H * canvas_scale) // 2
    scale = min(screen_w / picture_w, screen_h / picture_h)
    width, height = round(picture_w * scale), round(picture_h * scale)
    x, y = (screen_w - width) // 2, (screen_h - height) // 2
    return (
        (x - canvas_x) / canvas_scale,
        (y - canvas_y) / canvas_scale,
        width / canvas_scale,
        height / canvas_scale,
    )


def on_picture(picture: Box, fraction: Point) -> Point:
    """A point given as fractions of the camera picture, on the canvas."""
    x, y, w, h = picture
    return x + fraction[0] * w, y + fraction[1] * h


def draw_camera_osd(
    canvas: Canvas, now: datetime, t: float, live: bool, card: CardView | None = None
) -> None:
    if not live:
        canvas.noise(0, 0, W, H, seed=int(t * 15), lo=16, hi=46)
        message = "NO SIGNAL"
        text(canvas, message, (W - text_width(message, 2)) // 2, 68, OSD, 2)
    elif card is not None and card.outline is not None:
        _card(canvas, card)
    if int(t * 2) % 2 == 0:
        canvas.fill(222, 8, 5, 5, REC)
    text(canvas, "REC", 230, 8, OSD)


def _card(canvas: Canvas, card: CardView) -> None:
    assert card.outline is not None
    x, y, w, h = (round(v) for v in card.outline)
    color = FOUND if card.seen else OSD
    _dashed(canvas, x, y, w, h, color)
    _brackets(canvas, x - 3, y - 3, w + 6, h + 6, color)
    words = READ_IT if card.seen else HOLD_IT
    words_y = y - 11 if y - 11 >= 0 else y + h + 5
    text(canvas, words, x + w // 2 - text_width(words) // 2, words_y, color)
    if card.seen:
        corners = [(round(px), round(py)) for px, py in card.seen]
        for a, b in zip(corners, corners[1:] + corners[:1], strict=True):
            _line(canvas, a, b, FOUND)


def _dashed(canvas: Canvas, x: int, y: int, w: int, h: int, color: str) -> None:
    for i in range(0, w, DASH + GAP):
        canvas.fill(x + i, y, min(DASH, w - i), 1, color)
        canvas.fill(x + i, y + h - 1, min(DASH, w - i), 1, color)
    for j in range(0, h, DASH + GAP):
        canvas.fill(x, y + j, 1, min(DASH, h - j), color)
        canvas.fill(x + w - 1, y + j, 1, min(DASH, h - j), color)


def _brackets(canvas: Canvas, x: int, y: int, w: int, h: int, color: str) -> None:
    right, bottom = x + w - BRACKET, y + h - BRACKET
    for cx, cy in ((x, y), (right, y), (x, bottom), (right, bottom)):
        canvas.fill(cx, y if cy == y else y + h - 1, BRACKET, 1, color)
        canvas.fill(x if cx == x else x + w - 1, cy, 1, BRACKET, color)


def _line(canvas: Canvas, a: tuple[int, int], b: tuple[int, int], color: str) -> None:
    """A one-pixel line from a to b."""
    (x0, y0), (x1, y1) = a, b
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for i in range(steps + 1):
        x = round(x0 + (x1 - x0) * i / steps)
        y = round(y0 + (y1 - y0) * i / steps)
        canvas.fill(x, y, 1, 1, color)
